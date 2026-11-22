"""
clinical_text.py - local text extraction + rule-based lab parsing
=================================================================
Reads lab reports, prescriptions and notes from PDF, image (OCR), TXT, CSV or
DOCX and turns them into text for the language model. Nothing leaves the PC.

Install once (only needed for PDF / image / docx inputs):
    python -m pip install pymupdf rapidocr-onnxruntime
    python -m pip install python-docx        (only for .docx)

Lab values are parsed by regex (not by the LLM), so flags like H / L are
deterministic and auditable. Always verify against the source report.
"""

import re
import csv
from pathlib import Path

TEXT_EXTS = (".txt", ".md", ".csv", ".log")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
DOC_EXTS = TEXT_EXTS + IMAGE_EXTS + (".pdf", ".docx")

# =============================================================================
#  ROW RECONSTRUCTION  (turns scattered words/boxes back into table rows)
# =============================================================================

def rows_from_items(items):
    """items: list of (x_left, y_center, height, text). Returns list of row strings."""
    if not items:
        return []
    items = sorted(items, key=lambda t: t[1])
    heights = sorted(t[2] for t in items)
    med = heights[len(heights) // 2] or 10.0
    rows, cur, cur_y = [], [], None
    for it in items:
        if cur_y is None or abs(it[1] - cur_y) <= 0.6 * med:
            cur.append(it)
            cur_y = sum(i[1] for i in cur) / len(cur)
        else:
            rows.append(cur)
            cur, cur_y = [it], it[1]
    rows.append(cur)
    return ["  ".join(i[3] for i in sorted(r, key=lambda t: t[0])) for r in rows]

# =============================================================================
#  OCR
# =============================================================================

_OCR = None


def _get_ocr():
    """Return run(np_array) -> [(box, text)]. Tries RapidOCR, then EasyOCR."""
    global _OCR
    if _OCR is not None:
        return _OCR
    try:
        from rapidocr_onnxruntime import RapidOCR
        eng = RapidOCR()

        def run(img):
            res, _ = eng(img)
            return [(r[0], r[1]) for r in (res or [])]
        _OCR = run
        return _OCR
    except ImportError:
        pass
    try:
        from rapidocr import RapidOCR
        eng = RapidOCR()

        def run(img):
            out = eng(img)
            boxes = getattr(out, "boxes", None)
            txts = getattr(out, "txts", None)
            if boxes is None or txts is None:
                return []
            return [(b.tolist() if hasattr(b, "tolist") else b, t) for b, t in zip(boxes, txts)]
        _OCR = run
        return _OCR
    except ImportError:
        pass
    try:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)

        def run(img):
            return [(b, t) for b, t, _c in reader.readtext(img)]
        _OCR = run
        return _OCR
    except ImportError:
        pass
    raise RuntimeError("No OCR engine installed. Run:  python -m pip install rapidocr-onnxruntime")


def ocr_array(arr):
    items = []
    for box, text in _get_ocr()(arr):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append((min(xs), (min(ys) + max(ys)) / 2.0, max(ys) - min(ys), str(text)))
    return rows_from_items(items)


def ocr_image_file(path):
    from PIL import Image
    import numpy as np
    img = Image.open(str(path)).convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest < 1400:                       # small screenshots: upscale
        s = 1400.0 / longest
        img = img.resize((int(w * s), int(h * s)))
    elif longest > 2800:                     # phone photos: downscale
        s = 2800.0 / longest
        img = img.resize((int(w * s), int(h * s)))
    return ocr_array(np.array(img))

# =============================================================================
#  FILE READERS
# =============================================================================

def _read_pdf(path):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PDF support needs PyMuPDF:  python -m pip install pymupdf")
    import numpy as np
    doc = fitz.open(str(path))
    lines, ocr_pages, n_pages = [], 0, len(doc)
    for page in doc:
        words = page.get_text("words")
        items = [(w[0], (w[1] + w[3]) / 2.0, (w[3] - w[1]), w[4]) for w in words]
        page_lines = rows_from_items(items)
        if sum(len(l) for l in page_lines) < 40:          # scanned page -> OCR it
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            page_lines = ocr_array(arr)
            ocr_pages += 1
        lines.extend(page_lines)
        lines.append("")
    doc.close()
    if ocr_pages == 0:
        method = "pdf-text"
    elif ocr_pages == n_pages:
        method = "pdf-ocr"
    else:
        method = "pdf-text+ocr"
    return "\n".join(lines), method


def _read_docx(path):
    try:
        import docx
    except ImportError:
        raise RuntimeError("DOCX support needs python-docx:  python -m pip install python-docx")
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            parts.append("  ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts)


def _read_csv(path):
    rows = []
    with open(str(path), newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            rows.append("  ".join(c.strip() for c in row))
    return "\n".join(rows)


def extract_text(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        return _read_csv(path), "csv"
    if ext in TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    if ext == ".docx":
        return _read_docx(path), "docx"
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in IMAGE_EXTS:
        return "\n".join(ocr_image_file(path)), "ocr"
    raise ValueError("Unsupported file type: %s" % ext)

# =============================================================================
#  LAB PARSING
# =============================================================================

_NUM = r"\d[\d,]*\.?\d*"
LINE_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z][A-Za-z0-9 ()/%.,'+\-]{1,45}?)\s*[:|]?\s+"
    r"(?P<value>[<>]?\s*" + _NUM + r")(?P<tail>.*)$")
RANGE_RE = re.compile(r"(%s)\s*(?:-|\u2013|\u2014|to)\s*(%s)" % (_NUM, _NUM))
UPPER_RE = re.compile(r"(?:<=|<|\u2264|up\s*to|upto)\s*(%s)" % _NUM, re.I)
LOWER_RE = re.compile(r"(?:>=|>|\u2265)\s*(%s)" % _NUM)
FLAG_RE = re.compile(r"(?<![A-Za-z])(HH|LL|H|L|HIGH|LOW|High|Low)(?![A-Za-z])")
DATE_RE = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
BLOCK_RE = re.compile(
    r"^(date|age|page|phone|mobile|reg|registration|id|sample|collected|received|reported|bill|"
    r"lab|dr|ref|patient|name|sex|gender|doctor|barcode|accession|time|no|sr)\b", re.I)
HEADER_RE = re.compile(r"(range|interval|normal|reference|method|specimen|remarks|note)", re.I)

# (low, high) critical limits are applied only when the unit is recognised.
ANALYTES = [
    {"name": "HbA1c", "pat": r"hba1c|a1c|glyc(o)?sylated|glycated", "units": ("%",),
     "range": (4.0, 5.6), "crit": (None, None)},
    {"name": "Hemoglobin", "pat": r"^(hemoglobin|haemoglobin|hb|hgb)\b(?!.*(corpuscular|mch|a1c))",
     "units": ("g/dl", "gm/dl", "g%", "gms/dl"),
     "range": {"M": (13.0, 17.0), "F": (12.0, 15.5)}, "crit": (7.0, None)},
    {"name": "WBC", "pat": r"^(wbc|tlc|total (leu[ck]ocyte|wbc)( count)?|white blood cell)",
     "units": "count", "range": (4.0, 11.0), "crit": (1.0, 30.0)},
    {"name": "Platelets", "pat": r"^(platelet|plt)(?!.*(width|volume|ratio|distribution))",
     "units": "count", "range": (150.0, 450.0), "crit": (20.0, None)},
    {"name": "Creatinine", "pat": r"^(serum )?creatinine(?!.*(clearance|ratio|urine))",
     "units": ("mg/dl",), "range": (0.6, 1.3), "crit": (None, None)},
    {"name": "ALT", "pat": r"^(alt|sgpt|alanine)", "units": ("u/l", "iu/l"),
     "range": (0.0, 40.0), "crit": (None, None)},
    {"name": "AST", "pat": r"^(ast|sgot|aspartate)", "units": ("u/l", "iu/l"),
     "range": (0.0, 40.0), "crit": (None, None)},
    {"name": "Total bilirubin", "pat": r"^(total bilirubin|bilirubin,? total|bilirubin)$",
     "units": ("mg/dl",), "range": (0.1, 1.2), "crit": (None, None)},
    {"name": "Sodium", "pat": r"^(serum )?(sodium|na\+?)$", "units": ("mmol/l", "meq/l"),
     "range": (135.0, 145.0), "crit": (120.0, 160.0)},
    {"name": "Potassium", "pat": r"^(serum )?(potassium|k\+?)$", "units": ("mmol/l", "meq/l"),
     "range": (3.5, 5.1), "crit": (2.5, 6.0)},
    {"name": "TSH", "pat": r"^tsh|thyroid stimulating", "units": ("miu/l", "uiu/ml", "miu/ml"),
     "range": (0.4, 4.0), "crit": (None, None)},
    {"name": "CRP", "pat": r"^(crp|c[- ]reactive)", "units": ("mg/l",),
     "range": None, "crit": (None, None)},
    {"name": "Glucose", "pat": r"glucose|^fbs$|^rbs$|blood sugar", "units": ("mg/dl",),
     "range": None, "crit": (40.0, None)},
]


def _f(s):
    return float(s.replace(",", "").rstrip(".").strip())


def norm_unit(u):
    u = (u or "").lower().replace("\u00b5", "u").replace("\u03bc", "u").replace("\u00b3", "3")
    u = u.replace(" ", "").replace("^", "").replace("*", "")
    return re.sub(r"^x", "", u)


def _count_to_thousands(value, unit):
    """WBC / platelet value -> x10^3/uL, or None if the unit is unclear."""
    u = norm_unit(unit)
    if any(s in u for s in ("103/ul", "103/mm3", "109/l", "thou", "k/ul")):
        return value
    if "lakh" in u:
        return value * 100.0
    if any(s in u for s in ("/cumm", "/mm3", "/ul")):
        return value / 1000.0
    return None


def _convert(an, value, unit):
    if an["units"] == "count":
        return _count_to_thousands(value, unit)
    return value if norm_unit(unit) in an["units"] else None


def match_analyte(name):
    n = re.sub(r"[^a-z0-9+%,/ ]", " ", name.lower())
    n = " ".join(n.split())
    for an in ANALYTES:
        if re.search(an["pat"], n):
            return an
    return None


def _evaluate(lab, an, sex):
    v, unit = lab["value"], lab["unit"]
    lo, hi = lab["ref_low"], lab["ref_high"]
    flag, src = "", ""
    if lo is not None or hi is not None:
        src = "report"
        if lo is not None and v < lo:
            flag = "L"
        elif hi is not None and v > hi:
            flag = "H"
    elif lab["flag_ocr"]:
        flag, src = lab["flag_ocr"][0].upper(), "report-flag"
    elif an and an.get("range"):
        conv = _convert(an, v, unit)
        rng = an["range"]
        if isinstance(rng, dict):
            rng = rng.get(sex)
        if conv is not None and rng:
            src = "generic"
            lab["ref"] = "%g-%g (generic adult range)" % rng
            if conv < rng[0]:
                flag = "L"
            elif conv > rng[1]:
                flag = "H"
    crit = False
    if an:
        conv = _convert(an, v, unit)
        c_lo, c_hi = an["crit"]
        if conv is not None:
            if c_lo is not None and conv < c_lo:
                crit, flag = True, "L"
            elif c_hi is not None and conv > c_hi:
                crit, flag = True, "H"
    lab["flag"], lab["ref_source"], lab["critical"] = flag, src, crit


def parse_labs(text, sex=None):
    """sex: 'M', 'F' or None. Returns a list of lab dicts."""
    labs, seen = [], set()
    for raw in text.splitlines():
        line = " ".join(raw.replace("|", "  ").split())
        if len(line) < 4 or DATE_RE.search(line):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip(" .:-,")
        if (not name or len(name.split()) > 6 or BLOCK_RE.match(name) or HEADER_RE.search(name)):
            continue
        try:
            value = _f(m.group("value").lstrip("<>").strip())
        except ValueError:
            continue
        tail = m.group("tail").strip()
        unit, rest = "", tail
        if tail:
            first, _, remainder = tail.partition(" ")
            if (re.search(r"[A-Za-z\u00b5\u03bc%]", first) and not FLAG_RE.fullmatch(first.strip("()[]"))
                    and first.lower() not in ("to", "up", "upto", "normal", "low", "high")):
                unit, rest = first.strip("()[]"), remainder
        lo = hi = None
        rm = RANGE_RE.search(rest)
        if rm:
            try:
                a, b = _f(rm.group(1)), _f(rm.group(2))
                if a < b:
                    lo, hi = a, b
            except ValueError:
                pass
        if lo is None and hi is None:
            um = UPPER_RE.search(rest)
            lm = LOWER_RE.search(rest)
            try:
                if um:
                    hi = _f(um.group(1))
                elif lm:
                    lo = _f(lm.group(1))
            except ValueError:
                pass
        fm = FLAG_RE.search(rest)
        an = match_analyte(name)
        if an is None and lo is None and hi is None:
            continue
        key = (name.lower(), value)
        if key in seen:
            continue
        seen.add(key)
        if lo is not None and hi is not None:
            ref = "%g-%g" % (lo, hi)
        elif hi is not None:
            ref = "<%g" % hi
        elif lo is not None:
            ref = ">%g" % lo
        else:
            ref = ""
        lab = {"name": name, "value": value, "unit": unit, "ref": ref,
               "ref_low": lo, "ref_high": hi, "flag_ocr": fm.group(1) if fm else "",
               "flag": "", "ref_source": "", "critical": False}
        _evaluate(lab, an, sex)
        labs.append(lab)
    return labs


def _lab_str(l):
    s = "%s %g%s" % (l["name"], l["value"], (" " + l["unit"]) if l["unit"] else "")
    bits = []
    if l["flag"]:
        bits.append({"H": "HIGH", "L": "LOW"}.get(l["flag"], l["flag"]))
    if l["critical"]:
        bits.append("CRITICAL")
    if l["ref"]:
        bits.append("ref " + l["ref"])
    return s + (" (" + "; ".join(bits) + ")" if bits else "")


def labs_to_text(labs, max_each=25):
    if not labs:
        return ""
    crit = [l for l in labs if l["critical"]]
    abn = [l for l in labs if l["flag"] and not l["critical"]]
    nrm = [l for l in labs if not l["flag"]]
    out = ["LAB RESULTS (auto-extracted by rules; verify against the source report)"]
    if crit:
        out.append("- CRITICAL: " + "; ".join(_lab_str(l) for l in crit[:max_each]))
    if abn:
        out.append("- Abnormal: " + "; ".join(_lab_str(l) for l in abn[:max_each]))
    if nrm:
        out.append("- No abnormal flag: " + ", ".join("%s %g" % (l["name"], l["value"]) for l in nrm[:max_each]))
    return "\n".join(out)


def lab_table(labs):
    """Plain-text table for the saved report."""
    if not labs:
        return []
    rows = ["  %-28s %-14s %-26s %s" % ("Test", "Value", "Reference", "Flag")]
    for l in labs:
        val = "%g %s" % (l["value"], l["unit"])
        flag = {"H": "HIGH", "L": "LOW"}.get(l["flag"], "")
        if l["critical"]:
            flag = "CRITICAL " + flag
        rows.append("  %-28s %-14s %-26s %s" % (l["name"][:28], val[:14], (l["ref"] or "-")[:26], flag))
    return rows

# =============================================================================
#  DOCUMENT PROCESSING
# =============================================================================

def classify(text, labs, filename=""):
    if len(labs) >= 3:
        return "labs"
    meds = len(re.findall(r"\b(tab|tablet|cap|capsule|syp|syrup|inj|mg|mcg|bd|od|tds|qid|bid|sos)\b",
                          text, re.I))
    if meds >= 3 or re.search(r"prescri|\brx\b|medic|drug", filename, re.I):
        return "medication"
    return "report"


def _finish(name, text, method, sex):
    labs = parse_labs(text, sex)
    return {"file": name, "method": method, "text": text, "labs": labs,
            "kind": classify(text, labs, name), "error": None}


def process_document(path, sex=None):
    path = Path(path)
    try:
        text, method = extract_text(path)
        return _finish(path.name, text, method, sex)
    except Exception as e:
        return {"file": path.name, "method": "", "text": "", "labs": [],
                "kind": "report", "error": str(e)}


def process_typed(text, sex=None):
    return _finish("typed input", text, "typed", sex)


def _clip(text, n):
    text = text.strip()
    return text if len(text) <= n else text[:n].rstrip() + " ... [truncated]"


def docs_to_prompt(docs, total_chars=3000):
    """Text block for the LLM: lab summary first, then clipped free text."""
    labs = [l for d in docs for l in d.get("labs", [])]
    out = []
    lt = labs_to_text(labs)
    if lt:
        out.append(lt)
    budget = total_chars
    for d in docs:
        if d.get("error") or d["kind"] == "labs" or not d["text"].strip():
            continue
        title = {"medication": "PRESCRIPTION / MEDICATION TEXT", "report": "OTHER REPORT / NOTES TEXT"}[d["kind"]]
        chunk = _clip(d["text"], max(300, min(1500, budget)))
        out.append("%s (%s; OCR/extraction may contain errors):\n%s" % (title, d["file"], chunk))
        budget -= len(chunk)
        if budget <= 0:
            break
    return "\n\n".join(out)