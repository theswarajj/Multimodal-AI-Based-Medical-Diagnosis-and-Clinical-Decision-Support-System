"""
app.py - Multimodal AI Clinical Decision-Support System (v2)
============================================================
Place app.py and clinical_text.py in FINAL_PROJECT/ (next to MRI/, SKIN/, XRAY/, INPUT/, OUTPUT/).

Flow
  1. Patient details + vital signs + clinical history
  2. Optional reports: labs / prescriptions (PDF, photo, txt, docx) or typed text
  3. Choose CNN model(s) -> pick scan from INPUT/<MODEL>/
  4. CNNs run -> figures + JSON in OUTPUT/<MODEL>/<case_id>/
  5. Triage agent (rules) -> alerts + URGENT / PRIORITY / ROUTINE flag
  6. MedGemma: detailed analysis, then quick-read bullet summary
  7. Report in OUTPUT/REPORTS/<case_id>_summary.txt

Speed: imports + model loading run in the background while you type, and figure
drawing runs in parallel with the AI summary.

Run:  python app.py            (options: --no-figures  --no-llm)
"""

import os
import sys
import re
import gc
import json
import time
import argparse
import datetime
import importlib.util
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import clinical_text as ct

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# =============================================================================
#  CONFIG
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "INPUT"
OUTPUT_DIR = BASE_DIR / "OUTPUT"
REPORTS_DIR = OUTPUT_DIR / "REPORTS"
TEXT_DIR = INPUT_DIR / "TEXT"            # lab reports / prescriptions / notes

LLM_MODEL = "medgemma-text"
LLM_NUM_CTX = 6144                       # lower to 4096 if `ollama ps` shows CPU offload
LLM_DETAIL_TOKENS = 900
LLM_QUICK_TOKENS = 250
LLM_TEMPERATURE = 0.25
DOC_PROMPT_CHARS = 3000                  # max report text sent to the LLM

SKIN_THRESHOLD = 0.5
XRAY_THRESHOLD = 0.5
MRI_LABEL_COL = "has_ET"
MRI_TARGET_SIZE = 128

FIG_DPI = 110                            # figures were 150 dpi; None keeps the original
QUICK_SUMMARY_FIRST = False             # True = bullets before the detailed analysis in the report

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

MODALITIES = {
    "1": {"key": "SKIN", "title": "Skin lesion analysis   (EfficientNet-B3, HAM10000)",
          "exts": IMAGE_EXTS, "scripts": ["running.py"],
          "ckpt": "checkpoints/efficientnet_b3_ham10000_v2_best.pth"},
    "2": {"key": "XRAY", "title": "Chest X-ray analysis    (DenseNet-121, CheXpert)",
          "exts": IMAGE_EXTS, "scripts": ["running.py"],
          "ckpt": "checkpoints/densenet121_chexpert_best.pth",
          "metadata": "processed_chexpert/metadata.json"},
    "3": {"key": "MRI", "title": "Brain MRI analysis      (3D ResNet-18, BraTS 2021)",
          "exts": (".npz",), "scripts": ["run.py", "p1.py"],
          "ckpt": "checkpoints/best_model.pth", "stats_dir": "processed_brats"},
}

CLINICAL_QUESTIONS = [
    ("chief_complaint", "Chief complaint / reason for imaging"),
    ("duration", "Onset & duration of symptoms (e.g. 3 weeks, gradual)"),
    ("symptoms", "Associated symptoms"),
    ("history", "Past medical / surgical history"),
    ("medications", "Current medications (or load a prescription file later)"),
    ("allergies", "Known allergies"),
    ("family_history", "Relevant family history"),
    ("lifestyle", "Smoking / alcohol / occupational exposure"),
    ("doctor_question", "Doctor's specific question for the AI summary"),
]

MODALITY_QUESTIONS = {
    "SKIN": [("lesion_site", "Lesion location on the body"),
             ("lesion_change", "Change in size / colour / shape? Itching or bleeding?"),
             ("sun_history", "Sun exposure, sunburns, previous skin cancer")],
    "XRAY": [("resp_symptoms", "Cough / fever / breathlessness / chest pain details"),
             ("exposure", "TB contact, recent travel, smoking history")],
    "MRI": [("neuro", "Headache / seizures / focal deficits / cognitive change"),
            ("prior_tx", "Prior surgery, radiotherapy or chemotherapy")],
}

# Background workers (one each, so heavy imports never race each other)
LOADER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="loader")
DOCS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="docs")
FIGS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="figs")

# =============================================================================
#  CONSOLE HELPERS
# =============================================================================

def banner(text):
    print()
    print("=" * 72)
    print("  " + text)
    print("=" * 72)


def section(text):
    print()
    print("--- " + text + " " + "-" * max(0, 66 - len(text)))


def ask(prompt, default="", required=False):
    while True:
        suffix = " [%s]" % default if default else ""
        val = input("  %s%s: " % (prompt, suffix)).strip()
        if not val:
            val = default
        if val or not required:
            return val
        print("    This field is required.")


def ask_int(prompt, lo, hi):
    while True:
        val = input("  %s: " % prompt).strip()
        if val.isdigit() and lo <= int(val) <= hi:
            return int(val)
        print("    Please enter a number between %d and %d." % (lo, hi))


def ask_float(prompt, lo, hi):
    while True:
        val = input("  %s: " % prompt).strip()
        if not val:
            return None
        try:
            x = float(val)
            if lo <= x <= hi:
                return x
        except ValueError:
            pass
        print("    Enter a number between %g and %g (or press Enter to skip)." % (lo, hi))


def ask_bp():
    while True:
        val = input("  Blood pressure, e.g. 120/80: ").strip()
        if not val:
            return None, None
        m = re.match(r"^(\d{2,3})\s*/\s*(\d{2,3})$", val)
        if m and 40 <= int(m.group(1)) <= 300 and 20 <= int(m.group(2)) <= 200:
            return int(m.group(1)), int(m.group(2))
        print("    Use the format 120/80 (or press Enter to skip).")


def ask_choice(prompt, options):
    for i, o in enumerate(options, 1):
        print("    [%d] %s" % (i, o))
    while True:
        val = input("  %s: " % prompt).strip()
        if val.isdigit() and 1 <= int(val) <= len(options):
            return options[int(val) - 1]
        for o in options:
            if val.lower() == o.lower():
                return o
        print("    Please choose a valid option.")


def parse_selection(val, n):
    """'1,3' / '1 3' / 'a' -> list of 1-based indices, or None if invalid."""
    val = val.strip().lower()
    if val in ("a", "all"):
        return list(range(1, n + 1))
    parts = [p for p in re.split(r"[,\s]+", val) if p]
    if parts and all(p.isdigit() and 1 <= int(p) <= n for p in parts):
        out = []
        for p in parts:
            if int(p) not in out:
                out.append(int(p))
        return out
    return None


def slugify(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:30] or "patient"


def tick(label, t0):
    print("    [time] %s: %.1fs" % (label, time.perf_counter() - t0))


def free_gpu():
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def json_default(o):
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=json_default)

# =============================================================================
#  INPUT COLLECTION
# =============================================================================

def collect_patient():
    section("PATIENT DETAILS")
    p = {}
    p["name"] = ask("Full name", required=True)
    p["patient_id"] = ask("Patient ID / MRN (optional)")
    p["age"] = ask_int("Age (years)", 0, 120)
    p["sex"] = ask_choice("Sex", ["Male", "Female", "Other"])
    p["referring_doctor"] = ask("Referring / consulting doctor (optional)")
    return p


def collect_vitals():
    section("VITAL SIGNS  (Enter to skip any)")
    v = {}
    t = ask_float("Temperature (C or F)", 30, 115)
    if t is not None and t > 45:
        t = round((t - 32) * 5.0 / 9.0, 1)
    v["temp_c"] = t
    v["hr"] = ask_float("Heart rate (bpm)", 20, 300)
    v["bp_sys"], v["bp_dia"] = ask_bp()
    v["spo2"] = ask_float("SpO2 (%)", 50, 100)
    v["rr"] = ask_float("Respiratory rate (/min)", 4, 80)
    return v


def vitals_text(v):
    parts = []
    if v.get("temp_c") is not None:
        parts.append("Temp %.1f C" % v["temp_c"])
    if v.get("hr") is not None:
        parts.append("HR %.0f bpm" % v["hr"])
    if v.get("bp_sys") is not None:
        parts.append("BP %d/%d" % (v["bp_sys"], v["bp_dia"]))
    if v.get("spo2") is not None:
        parts.append("SpO2 %.0f%%" % v["spo2"])
    if v.get("rr") is not None:
        parts.append("RR %.0f/min" % v["rr"])
    return ", ".join(parts)


def collect_clinical():
    section("CLINICAL HISTORY  (press Enter to skip any question)")
    return {key: ask(q) for key, q in CLINICAL_QUESTIONS}


def collect_modality_questions(key):
    qs = MODALITY_QUESTIONS.get(key, [])
    if not qs:
        return {}
    section("%s-SPECIFIC QUESTIONS  (Enter to skip)" % key)
    return {qkey: ask(q) for qkey, q in qs}


def collect_documents():
    section("ADDITIONAL REPORTS - labs, prescriptions, notes (optional)")
    print("    [1] Load file(s) from %s" % TEXT_DIR)
    print("        pdf, jpg/png (OCR), txt, docx, csv")
    print("    [2] Type / paste text now")
    print("    [3] Both")
    choice = input("  Your choice (Enter to skip): ").strip()
    paths, typed = [], ""
    if choice in ("1", "3"):
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(f for f in TEXT_DIR.iterdir() if f.is_file() and f.suffix.lower() in ct.DOC_EXTS)
        if not files:
            print("    No supported files in %s" % TEXT_DIR)
        else:
            for i, f in enumerate(files, 1):
                print("    [%d] %s  (%.2f MB)" % (i, f.name, f.stat().st_size / 1048576.0))
            while True:
                sel = input("  Select files (e.g. 1,3 or A; Enter to skip): ").strip()
                if not sel:
                    break
                idx = parse_selection(sel, len(files))
                if idx:
                    paths = [files[i - 1] for i in idx]
                    break
                print("    Invalid selection.")
    if choice in ("2", "3"):
        print("  Paste or type text; finish with an empty line:")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        typed = "\n".join(lines)
    if not paths and not typed:
        return None
    return {"paths": paths, "typed": typed}


def process_inputs(spec, sex_letter):
    docs = [ct.process_document(p, sex_letter) for p in spec["paths"]]
    if spec["typed"]:
        docs.append(ct.process_typed(spec["typed"], sex_letter))
    return docs


def choose_modalities():
    section("SELECT IMAGING MODEL(S) TO RUN")
    for k, m in MODALITIES.items():
        print("    [%s] %s" % (k, m["title"]))
    print("    [A] Run all three")
    while True:
        idx = parse_selection(input("  Your choice (e.g. 1   or   1,3   or   A): "), len(MODALITIES))
        if idx:
            return [MODALITIES[str(i)] for i in idx]
        print("    Invalid selection.")


def choose_file(mod):
    folder = INPUT_DIR / mod["key"]
    folder.mkdir(parents=True, exist_ok=True)
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in mod["exts"])
    section("SELECT %s INPUT FILE" % mod["key"])
    if not files:
        print("    No %s files found in: %s" % ("/".join(mod["exts"]), folder))
        return None
    for i, f in enumerate(files, 1):
        print("    [%d] %s  (%.2f MB)" % (i, f.name, f.stat().st_size / 1048576.0))
    while True:
        val = input("  Select file [1-%d] (default 1, S to skip): " % len(files)).strip()
        if not val:
            return files[0]
        if val.lower() == "s":
            return None
        if val.isdigit() and 1 <= int(val) <= len(files):
            return files[int(val) - 1]
        print("    Invalid selection.")

# =============================================================================
#  BACKGROUND WARM-UP + MODEL PIPELINES
# =============================================================================

def cap_figure_dpi(dpi):
    """Your figure code saves at dpi=150; cap it for faster saving."""
    import matplotlib.figure as mf
    orig = mf.Figure.savefig

    def savefig(self, fname, *a, **kw):
        if kw.get("dpi") and kw["dpi"] > dpi:
            kw["dpi"] = dpi
        return orig(self, fname, *a, **kw)
    mf.Figure.savefig = savefig


def warm_up():
    """Runs in the background while the doctor types."""
    for name in ("numpy", "PIL.Image", "torch", "torchvision", "timm"):
        try:
            __import__(name)
        except Exception:
            pass
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot  # noqa: F401
        if FIG_DPI:
            cap_figure_dpi(FIG_DPI)
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            torch.zeros(1, device="cuda")      # create the CUDA context now
    except Exception:
        pass


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def find_script(folder, names):
    for n in names:
        if (folder / n).exists():
            return folder / n
    raise FileNotFoundError("None of %s found in %s" % (names, folder))


def resolve_file(primary, folder, suffixes, label):
    if primary.exists():
        return primary
    cands = [f for f in folder.iterdir() if f.suffix.lower() in suffixes] if folder.exists() else []
    if len(cands) == 1:
        return cands[0]
    raise FileNotFoundError("%s not found at %s (candidates: %s). Edit MODALITIES in app.py."
                            % (label, primary, [c.name for c in cands]))


def get_device():
    import torch
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# prepare_*  : load script + weights (runs in the background)
# infer_*    : run the CNN, return (result_dict, figure_job)
#              figure_job(out_dir) draws the PNGs and runs in a separate thread

def prepare_skin(cfg):
    folder = BASE_DIR / "SKIN"
    mod = load_module("skin_pipeline", find_script(folder, cfg["scripts"]))
    ckpt = resolve_file(folder / cfg["ckpt"], folder / "checkpoints", (".pth", ".pt"), "Skin checkpoint")
    device = get_device()
    return {"mod": mod, "device": device, "transform": mod.get_eval_transform(),
            "model": mod.load_model(str(ckpt), device)}


def infer_skin(ctx, path):
    mod = ctx["mod"]
    result = mod.predict_image(ctx["model"], str(path), ctx["transform"], ctx["device"], SKIN_THRESHOLD, True)
    fig_args = dict(result)                  # keeps heatmap + image for the figure thread
    result.pop("_heatmap", None)
    result.pop("_image_pil", None)
    return result, (lambda out_dir: mod.generate_clinical_figures(fig_args, str(out_dir)))


def prepare_xray(cfg):
    folder = BASE_DIR / "XRAY"
    mod = load_module("xray_pipeline", find_script(folder, cfg["scripts"]))
    ckpt = resolve_file(folder / cfg["ckpt"], folder / "checkpoints", (".pth", ".pt"), "X-ray checkpoint")
    meta = folder / cfg["metadata"]
    if not meta.exists():
        for d in sorted(folder.iterdir()):
            if d.is_dir() and d.name.lower().startswith("processed") and (d / "metadata.json").exists():
                meta = d / "metadata.json"
                break
    if not meta.exists():
        raise FileNotFoundError("metadata.json not found for the X-ray model (looked in %s)" % folder)
    device = get_device()
    model, transform, labels, img_size = mod.load_model_and_config(str(ckpt), str(meta), device)
    return {"mod": mod, "device": device, "model": model, "transform": transform,
            "labels": labels, "img_size": img_size}


def infer_xray(ctx, path):
    mod = ctx["mod"]
    result = mod.predict_image(ctx["model"], ctx["transform"], ctx["labels"], str(path),
                               ctx["device"], XRAY_THRESHOLD, ctx["img_size"])
    fig_args = dict(result)
    for k in ("_heatmaps", "_image_pil", "_img_size"):
        result.pop(k, None)
    return result, (lambda out_dir: mod.generate_clinical_figures(fig_args, str(out_dir)))


def prepare_mri(cfg):
    folder = BASE_DIR / "MRI"
    mod = load_module("mri_pipeline", find_script(folder, cfg["scripts"]))
    ckpt = resolve_file(folder / cfg["ckpt"], folder / "checkpoints", (".pth", ".pt"), "MRI checkpoint")
    device = get_device()
    mean, std = mod.load_channel_stats(str(folder / cfg["stats_dir"]))
    model, _ = mod.build_model(str(ckpt), 2, device)
    return {"mod": mod, "device": device, "model": model, "mean": mean, "std": std}


def infer_mri(ctx, path):
    mod = ctx["mod"]
    result = mod.predict_one(str(path), ctx["model"], ctx["mean"], ctx["std"],
                             MRI_TARGET_SIZE, ctx["device"], MRI_LABEL_COL)
    raw_image = result.pop("_raw_image", None)
    raw_mask = result.pop("_raw_mask", None)
    result["task_name"] = mod.LABEL_CLINICAL_INFO.get(MRI_LABEL_COL, {}).get("clinical", MRI_LABEL_COL)
    snapshot = dict(result)

    def job(out_dir):
        if raw_image is None:
            return []
        return mod.generate_clinical_figures(raw_image, raw_mask, snapshot,
                                             snapshot.get("tumor_location"), MRI_LABEL_COL, str(out_dir))
    return result, job


PIPELINES = {"SKIN": (prepare_skin, infer_skin),
             "XRAY": (prepare_xray, infer_xray),
             "MRI": (prepare_mri, infer_mri)}

# =============================================================================
#  RESULT -> TEXT
# =============================================================================

def describe_skin(r):
    lines = ["SKIN LESION MODEL (EfficientNet-B3, HAM10000 dermoscopy; classes: akiec, bcc, bkl, df, mel, nv, vasc)"]
    if r.get("uncertain"):
        lines.append("- Result: UNCERTAIN - top confidence %.1f%% is below the %.0f%% threshold"
                     % (r["confidence"] * 100, SKIN_THRESHOLD * 100))
        lines.append("- Best guess: %s (%s)" % (r.get("top_guess", "?"), r.get("top_guess_name", "")))
    else:
        lines.append("- Top prediction: %s [%s], confidence %.1f%%"
                     % (r["full_name"], r["prediction"], r["confidence"] * 100))
        lines.append("- Model risk category: %s; urgency: %s" % (r.get("risk_level", "N/A"), r.get("urgency", "N/A")))
    lines.append("- Malignant-class probability (akiec+bcc+mel): %.1f%%" % (r["malignant_probability"] * 100))
    top = list(r["all_class_scores"].items())[:3]
    lines.append("- Top class scores: " + ", ".join("%s %.1f%%" % (k, v * 100) for k, v in top))
    return "\n".join(lines)


def describe_xray(r):
    thr = r.get("threshold", XRAY_THRESHOLD)
    findings = r["findings"]
    nf = next((f for f in findings if f["label"] == "No Finding"), None)
    pos = [f for f in findings if f["positive"] and f["label"] != "No Finding"]
    lines = ["CHEST X-RAY MODEL (DenseNet-121, CheXpert, multi-label, threshold %.0f%%)" % (thr * 100)]
    lines.append("- Overall severity (rule-based from model output): %s" % r["overall_severity"])
    if pos:
        items = []
        for f in pos:
            s = "%s %.1f%%" % (f["label"], f["probability"] * 100)
            if f.get("urgent"):
                s += " [urgent flag]"
            items.append(s)
        lines.append("- ABNORMAL findings above threshold: " + "; ".join(items))
    else:
        lines.append("- No abnormal finding above threshold")
    if nf is not None:
        s = "- 'No Finding' probability: %.1f%%" % (nf["probability"] * 100)
        if nf["positive"] and pos:
            s += "  ** CONFLICT: this contradicts the abnormal findings above **"
        lines.append(s)
    border = [f for f in findings if not f["positive"] and f["label"] != "No Finding" and f["probability"] >= 0.30]
    if border:
        lines.append("- Sub-threshold but notable: " + "; ".join("%s %.1f%%" % (f["label"], f["probability"] * 100) for f in border))
    return "\n".join(lines)


def describe_mri(r):
    lines = ["BRAIN MRI MODEL (3D ResNet-18, BraTS 2021, 4 channels: T1, T1ce, T2, FLAIR)"]
    lines.append("- Task: %s (binary classification)" % r.get("task_name", r.get("label_col", "")))
    lines.append("- Prediction: %s, confidence %.1f%% (P(positive) %.1f%%, P(negative) %.1f%%)"
                 % (r["predicted_label"], r["confidence"] * 100, r["prob_positive"] * 100, r["prob_negative"] * 100))
    t = r.get("tumor_location")
    if t is None:
        lines.append("- No segmentation mask was supplied with this scan, so tumour location/size are unavailable.")
    elif not t.get("has_tumor"):
        lines.append("- The supplied segmentation mask contains no tumour voxels.")
    else:
        lines.append("- Location/composition below come from the SEGMENTATION MASK supplied with the scan "
                     "(not predicted by the classifier); laterality is approximate.")
        lines.append("- Approximate location: %s (%s)" % (t["anatomical_summary"], t["laterality"]))
        lines.append("- Tumour volume: %.2f%% of the volume" % (t["tumor_volume_fraction"] * 100))
        parts = ["%s %.0f%%" % (n, s["fraction_of_tumor"] * 100) for n, s in t["subtypes"].items() if s["voxel_count"] > 0]
        if parts:
            lines.append("- Composition: " + ", ".join(parts))
    return "\n".join(lines)


DESCRIBERS = {"SKIN": describe_skin, "XRAY": describe_xray, "MRI": describe_mri}

# =============================================================================
#  TRIAGE AGENT (deterministic rules, auditable)
# =============================================================================

SEV = {"INFO": 0, "PRIORITY": 1, "URGENT": 2}


def alerts_skin(r):
    out = []
    if r.get("uncertain"):
        out.append(("PRIORITY", "Skin: model is uncertain (top confidence %.0f%%). Image quality problem or a "
                                "lesion outside the 7 trained classes is possible - needs clinician review."
                    % (r["confidence"] * 100)))
        return out
    pred, name, conf = r["prediction"], r["full_name"], r["confidence"] * 100
    if pred == "mel":
        out.append(("URGENT", "Skin: melanoma-class prediction (%.1f%%) - urgent dermatology assessment / biopsy." % conf))
    elif pred in ("bcc", "akiec"):
        out.append(("PRIORITY", "Skin: %s predicted (%.1f%%) - malignant/pre-malignant category, prompt dermatology referral." % (name, conf)))
    elif r["malignant_probability"] >= 0.30:
        out.append(("PRIORITY", "Skin: top class is benign (%s) but combined malignant-class probability is %.0f%%."
                    % (name, r["malignant_probability"] * 100)))
    if conf < 70:
        out.append(("INFO", "Skin: only moderate confidence (%.0f%%) in the top class." % conf))
    return out


def alerts_xray(r):
    out = []
    findings = r["findings"]
    pos = [f for f in findings if f["positive"] and f["label"] != "No Finding"]
    nf = next((f for f in findings if f["label"] == "No Finding"), None)
    for f in pos:
        if f.get("urgent") or f["severity"] == "CRITICAL":
            lvl = "URGENT"
        elif f["severity"] in ("HIGH", "MODERATE"):
            lvl = "PRIORITY"
        else:
            lvl = "INFO"
        out.append((lvl, "Chest X-ray: %s flagged (%.1f%%), region: %s." % (f["label"], f["probability"] * 100, f["region"])))
    if nf is not None and nf["positive"] and pos:
        out.append(("PRIORITY", "Chest X-ray: model is internally inconsistent - 'No Finding' %.0f%% together with %s. "
                                "Interpret with caution; radiologist review needed."
                    % (nf["probability"] * 100, ", ".join(f["label"] for f in pos))))
    return out


def alerts_mri(r):
    out = []
    conf = r["confidence"] * 100
    task = r.get("task_name", "tumour component")
    if r["predicted_label"] == "POSITIVE":
        lvl = "URGENT" if conf >= 90 else "PRIORITY"
        out.append((lvl, "Brain MRI: %s predicted PRESENT (%.1f%%) - prompt neuro-radiology / neuro-oncology review." % (task, conf)))
    elif conf < 70:
        out.append(("PRIORITY", "Brain MRI: negative with low confidence (%.0f%%) - finding cannot be reliably excluded." % conf))
    if r.get("tumor_location") is None:
        out.append(("INFO", "Brain MRI: no segmentation mask supplied - tumour location/size unavailable."))
    return out


def alerts_labs(labs):
    out = []
    crit = [l for l in labs if l["critical"]]
    abn = [l for l in labs if l["flag"] and not l["critical"]]
    if crit:
        out.append(("URGENT", "Labs: CRITICAL value(s): " + "; ".join("%s %g %s" % (l["name"], l["value"], l["unit"]) for l in crit)))
    if len(abn) >= 3:
        out.append(("PRIORITY", "Labs: %d abnormal values (%s)." % (len(abn), ", ".join("%s %s" % (l["name"], l["flag"]) for l in abn[:8]))))
    elif abn:
        out.append(("INFO", "Labs: abnormal - " + ", ".join("%s %s" % (l["name"], l["flag"]) for l in abn)))
    return out


def alerts_vitals(v):
    out = []
    spo2, t, hr, sbp, rr = v.get("spo2"), v.get("temp_c"), v.get("hr"), v.get("bp_sys"), v.get("rr")
    if spo2 is not None:
        if spo2 < 90:
            out.append(("URGENT", "Vitals: SpO2 %.0f%% (hypoxaemia)." % spo2))
        elif spo2 < 94:
            out.append(("PRIORITY", "Vitals: SpO2 %.0f%% (borderline low)." % spo2))
    if t is not None:
        if t < 35.0:
            out.append(("PRIORITY", "Vitals: temperature %.1f C (hypothermia range)." % t))
        elif t >= 39.5:
            out.append(("PRIORITY", "Vitals: temperature %.1f C (high fever)." % t))
        elif t >= 38.0:
            out.append(("INFO", "Vitals: fever (%.1f C)." % t))
    if hr is not None:
        if hr > 130 or hr < 40:
            out.append(("URGENT", "Vitals: heart rate %.0f bpm." % hr))
        elif hr > 100 or hr < 50:
            out.append(("PRIORITY", "Vitals: heart rate %.0f bpm." % hr))
    if sbp is not None:
        if sbp < 90:
            out.append(("URGENT", "Vitals: systolic BP %d (hypotension)." % sbp))
        elif sbp >= 180:
            out.append(("PRIORITY", "Vitals: systolic BP %d (severely raised)." % sbp))
    if rr is not None:
        if rr > 30:
            out.append(("URGENT", "Vitals: respiratory rate %.0f/min." % rr))
        elif rr > 24:
            out.append(("PRIORITY", "Vitals: respiratory rate %.0f/min." % rr))
    return out


def run_triage(vitals, runs, labs):
    alerts = []
    for run in runs:
        fn = {"SKIN": alerts_skin, "XRAY": alerts_xray, "MRI": alerts_mri}[run["key"]]
        alerts += fn(run["result"])
    alerts += alerts_labs(labs)
    alerts += alerts_vitals(vitals)
    alerts.sort(key=lambda a: -SEV[a[0]])
    top = max([SEV[a[0]] for a in alerts], default=0)
    level = {2: "URGENT", 1: "PRIORITY", 0: "ROUTINE"}[top]
    return {"level": level, "alerts": [{"level": l, "text": t} for l, t in alerts]}


def triage_lines(triage):
    lines = ["TRIAGE FLAG (rule-based, for clinician review): %s" % triage["level"]]
    if not triage["alerts"]:
        lines.append("  No alerts raised.")
    for a in triage["alerts"]:
        lines.append("  [%-8s] %s" % (a["level"], a["text"]))
    return lines

# =============================================================================
#  LLM (MedGemma via Ollama) - detailed analysis, then quick bullets
# =============================================================================

SYSTEM_DETAIL = (
    "You are a clinical decision-support assistant writing for a physician. You receive: patient age and sex, "
    "vital signs, clinical history, laboratory results, prescription/report text, outputs of AI imaging models, "
    "and RULE-BASED ALERTS computed by software.\n"
    "Rules:\n"
    "1. Patient-specific statements must come only from the provided data. Never invent values, findings or history. "
    "If something is missing, write 'not provided'.\n"
    "2. You may use general medical knowledge for considerations and next steps.\n"
    "3. Never give a definitive diagnosis. Use hedged wording such as 'suggestive of', 'consistent with', 'cannot exclude'.\n"
    "4. Mention every item in the RULE-BASED ALERTS. If an imaging output contradicts itself, say so plainly "
    "instead of choosing a side.\n"
    "5. Point out low confidence and any mismatch between imaging, labs, vitals and history.\n"
    "6. Be specific. Avoid vague filler such as 'further evaluation may be warranted' - say which evaluation and why.\n"
    "7. Plain text only, no tables, about 300-450 words.\n"
    "Use exactly these headings, in this order:\n"
    "1. CLINICAL SNAPSHOT (2-3 sentences: patient, presentation, key background)\n"
    "2. IMAGING FINDINGS (one short paragraph per model that was run: finding, confidence, what it means)\n"
    "3. LABS AND MEDICATIONS (abnormal values and their possible relevance; medications relevant to the findings; "
    "write 'Not provided' if none)\n"
    "4. CORRELATION (where imaging, labs, vitals and history agree or disagree)\n"
    "5. CONSIDERATIONS (possible explanations, most relevant first, hedged)\n"
    "6. SUGGESTED NEXT STEPS (numbered, specific actions for the clinician to consider)\n"
    "7. LIMITATIONS (2-3 bullets specific to this case)"
)

SYSTEM_QUICK = (
    "You condense a clinical analysis into a quick-read summary for a busy physician. Use only the text provided. "
    "Output 5 to 7 bullet points. Each bullet starts with '- ' and has at most 20 words. Order by importance: the most "
    "urgent finding first, then supporting findings, then correlation or conflicts, and finish with one bullet that "
    "starts with 'Next:' giving the single most important next step. No headings and no other text."
)


def build_user_prompt(patient, vitals, clinical, docs_text, runs, triage):
    L = ["PATIENT: %s-year-old %s" % (patient.get("age", "?"), patient.get("sex", "?"))]
    vt = vitals_text(vitals)
    L.append("VITAL SIGNS: %s" % (vt or "not provided"))
    L += ["", "CLINICAL HISTORY"]
    any_hist = False
    for key, label in CLINICAL_QUESTIONS:
        if key != "doctor_question" and clinical.get(key):
            L.append("- %s: %s" % (label, clinical[key]))
            any_hist = True
    for key, answers in clinical.get("modality_specific", {}).items():
        for qkey, qtext in MODALITY_QUESTIONS.get(key, []):
            if answers.get(qkey):
                L.append("- %s: %s" % (qtext, answers[qkey]))
                any_hist = True
    if not any_hist:
        L.append("- (no history provided)")
    if clinical.get("doctor_question"):
        L += ["", "DOCTOR'S QUESTION: %s" % clinical["doctor_question"]]
    if docs_text:
        L += ["", docs_text]
    L += ["", "AI IMAGING MODEL OUTPUTS"]
    for run in runs:
        L += [run["text"], ""]
    L.append("RULE-BASED ALERTS (verified by software; triage level %s)" % triage["level"])
    if triage["alerts"]:
        for a in triage["alerts"]:
            L.append("- [%s] %s" % (a["level"], a["text"]))
    else:
        L.append("- none")
    L += ["", "Write the analysis now."]
    return "\n".join(L)


def check_llm():
    try:
        import ollama
    except ImportError:
        return False, "Python package 'ollama' not installed (python -m pip install ollama)"
    try:
        ollama.show(LLM_MODEL)
        return True, ""
    except Exception as e:
        return False, "Cannot reach Ollama or model '%s' missing (%s)" % (LLM_MODEL, e)


def llm_stream(system, user, max_tokens, keep_alive):
    import ollama
    chunks, truncated = [], False
    stream = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        options={"temperature": LLM_TEMPERATURE, "num_ctx": LLM_NUM_CTX, "num_predict": max_tokens},
        stream=True, keep_alive=keep_alive)
    for part in stream:
        piece = part["message"]["content"]
        print(piece, end="", flush=True)
        chunks.append(piece)
        if getattr(part, "done_reason", None) == "length":
            truncated = True
    print()
    return "".join(chunks).strip(), truncated


def generate_analysis(user_prompt, triage):
    """Returns (detail, quick, error)."""
    try:
        import ollama  # noqa: F401
    except ImportError:
        return None, None, "Python package 'ollama' not installed"
    try:
        print("\n  DETAILED ANALYSIS\n  " + "-" * 20)
        detail, cut = llm_stream(SYSTEM_DETAIL, user_prompt, LLM_DETAIL_TOKENS, "5m")
        if cut:
            detail += "\n[note: output was cut at the token limit]"
            print("  [warning] detailed analysis hit the token limit; raise LLM_DETAIL_TOKENS if needed")
    except Exception as e:
        return None, None, str(e)
    try:
        alert_txt = "\n".join("- [%s] %s" % (a["level"], a["text"]) for a in triage["alerts"]) or "- none"
        quick_user = "RULE-BASED ALERTS:\n%s\n\nDETAILED ANALYSIS:\n%s\n\nWrite the bullets now." % (alert_txt, detail)
        print("\n  QUICK SUMMARY\n  " + "-" * 20)
        quick, _ = llm_stream(SYSTEM_QUICK, quick_user, LLM_QUICK_TOKENS, 0)     # 0 = free VRAM afterwards
    except Exception as e:
        return detail, None, "quick summary failed: %s" % e
    return detail, quick, None

# =============================================================================
#  REPORT
# =============================================================================

DISCLAIMER = (
    "This report is produced by AI-assisted tools for clinician decision support only. It is not a "
    "diagnosis. Triage flags are rule-based. OCR-extracted text and lab values may contain errors and "
    "must be verified against the source documents. All findings are probabilistic and must be reviewed "
    "and confirmed by a qualified physician before any clinical action."
)


def build_report_text(case_id, patient, vitals, clinical, docs, labs, runs, triage, detail, quick, llm_error):
    bar, thin = "=" * 76, "-" * 76
    L = [bar, "  MULTIMODAL AI CLINICAL DECISION-SUPPORT REPORT", bar,
         "Case ID     : %s" % case_id,
         "Generated   : %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "",
         "PATIENT", "  Name      : %s" % patient["name"]]
    if patient.get("patient_id"):
        L.append("  Patient ID: %s" % patient["patient_id"])
    L.append("  Age / Sex : %s / %s" % (patient["age"], patient["sex"]))
    if patient.get("referring_doctor"):
        L.append("  Doctor    : %s" % patient["referring_doctor"])
    L += ["", thin] + triage_lines(triage) + [thin, "", "VITAL SIGNS: %s" % (vitals_text(vitals) or "not provided"), "",
                                                "CLINICAL HISTORY (as entered)"]
    shown = False
    for key, label in CLINICAL_QUESTIONS:
        if clinical.get(key):
            L.append("  %s: %s" % (label, clinical[key]))
            shown = True
    for key, answers in clinical.get("modality_specific", {}).items():
        for qkey, qtext in MODALITY_QUESTIONS.get(key, []):
            if answers.get(qkey):
                L.append("  %s: %s" % (qtext, answers[qkey]))
                shown = True
    if not shown:
        L.append("  (none entered)")
    if docs:
        L += ["", thin, "ADDITIONAL REPORTS (extracted locally)", thin]
        for d in docs:
            if d.get("error"):
                L.append("  %s: could not be read - %s" % (d["file"], d["error"]))
            else:
                L.append("  %s  [%s, %s, %d lab value(s)]" % (d["file"], d["method"], d["kind"], len(d["labs"])))
        if labs:
            L += [""] + ct.lab_table(labs)
    L += ["", thin, "IMAGING MODEL OUTPUTS (computed by the CNNs, not by the language model)", thin]
    for run in runs:
        L += ["", "[%s]  file: %s" % (run["key"], Path(run["file"]).name), run["text"]]
        for fig in run["figures"]:
            L.append("  figure: %s" % fig)

    def quick_block():
        return [thin, "QUICK SUMMARY (key points, AI-generated)", thin, "", quick or "(unavailable)", ""]

    def detail_block():
        return [thin, "DETAILED ANALYSIS (MedGemma 4B, running locally)", thin, "", detail or "(unavailable)", ""]

    L.append("")
    if llm_error:
        L += [thin, "AI SUMMARY", thin, "", "AI summary unavailable: %s" % llm_error,
              "The imaging outputs, alerts and lab table above are unaffected.", ""]
    elif QUICK_SUMMARY_FIRST:
        L += quick_block() + detail_block()
    else:
        L += detail_block() + quick_block()
    L += [thin, "DISCLAIMER", DISCLAIMER, bar]
    return "\n".join(L)

# =============================================================================
#  MAIN
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description="Multimodal AI Clinical Decision-Support System")
    ap.add_argument("--no-figures", action="store_true", help="skip PNG figures (fastest)")
    ap.add_argument("--no-llm", action="store_true", help="skip the MedGemma summary")
    args = ap.parse_args()

    t_all = time.perf_counter()
    banner("MULTIMODAL AI CLINICAL DECISION-SUPPORT SYSTEM")
    print("  All processing is local. Patient data never leaves this machine.")
    LOADER.submit(warm_up)                       # imports + CUDA init while the doctor types

    llm_ok = False
    if not args.no_llm:
        llm_ok, llm_msg = check_llm()
        if not llm_ok:
            print("\n  [warning] AI summary will be unavailable: %s" % llm_msg)

    patient = collect_patient()
    sex_letter = {"Male": "M", "Female": "F"}.get(patient["sex"])
    vitals = collect_vitals()
    clinical = collect_clinical()

    doc_spec = collect_documents()
    doc_future = DOCS.submit(process_inputs, doc_spec, sex_letter) if doc_spec else None

    selected = choose_modalities()
    prep = {m["key"]: LOADER.submit(PIPELINES[m["key"]][0], m) for m in selected}   # load weights in background

    clinical["modality_specific"] = {}
    for m in selected:
        answers = collect_modality_questions(m["key"])
        if any(answers.values()):
            clinical["modality_specific"][m["key"]] = answers
    chosen = []
    for m in selected:
        f = choose_file(m)
        if f is not None:
            chosen.append((m, f))

    case_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + slugify(patient["name"])
    runs, fig_futures = [], []

    for m, file_path in chosen:
        key = m["key"]
        out_dir = OUTPUT_DIR / key / case_id
        out_dir.mkdir(parents=True, exist_ok=True)
        section("RUNNING %s MODEL" % key)
        try:
            t0 = time.perf_counter()
            if not prep[key].done():
                print("    finishing model load in the background ...")
            ctx = prep[key].result()
            tick("model ready (loaded while you were typing)", t0)
            t1 = time.perf_counter()
            result, fig_job = PIPELINES[key][1](ctx, file_path)
            tick("inference", t1)
            ctx.clear()
        except Exception as e:
            print("  [ERROR] %s model failed: %s" % (key, e))
            traceback.print_exc()
            free_gpu()
            continue
        free_gpu()
        text = DESCRIBERS[key](result)
        save_json(result, out_dir / ("%s_result.json" % key))
        run = {"key": key, "title": m["title"], "file": str(file_path), "result": result,
               "figures": [], "text": text}
        runs.append(run)
        if not args.no_figures:
            fig_futures.append((run, FIGS.submit(fig_job, out_dir)))     # draws in the background
        print()
        print(text)

    if not runs:
        print("\n  No model produced results. Exiting.")
        os._exit(0)

    # ---- documents / labs -----------------------------------------------------
    docs, labs = [], []
    if doc_future is not None:
        t0 = time.perf_counter()
        docs = doc_future.result()
        tick("report text extraction", t0)
        labs = [l for d in docs for l in d["labs"]]
        for d in docs:
            if d.get("error"):
                print("  [warn] %s: %s" % (d["file"], d["error"]))
            else:
                print("  [docs] %s -> %s, %d chars, %d lab value(s), type: %s"
                      % (d["file"], d["method"], len(d["text"]), len(d["labs"]), d["kind"]))

    # ---- triage ---------------------------------------------------------------
    triage = run_triage(vitals, runs, labs)
    section("TRIAGE AGENT")
    for line in triage_lines(triage):
        print("  " + line)

    # ---- LLM ------------------------------------------------------------------
    detail = quick = None
    llm_error = None
    if args.no_llm:
        llm_error = "skipped (--no-llm)"
    elif not llm_ok:
        llm_error = "Ollama / model not available"
    else:
        section("CLINICAL ANALYSIS WITH MEDGEMMA")
        t0 = time.perf_counter()
        docs_text = ct.docs_to_prompt(docs, DOC_PROMPT_CHARS) if docs else ""
        prompt = build_user_prompt(patient, vitals, clinical, docs_text, runs, triage)
        detail, quick, llm_error = generate_analysis(prompt, triage)
        tick("language model", t0)
        if llm_error:
            print("  [warning] %s" % llm_error)

    # ---- figures finished in parallel ----------------------------------------
    for run, fut in fig_futures:
        try:
            run["figures"] = [str(p) for p in fut.result()]
        except Exception as e:
            print("  [warn] %s figures failed: %s" % (run["key"], e))
        for p in run["figures"]:
            print("  figure saved: %s" % p)

    # ---- report ---------------------------------------------------------------
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report_text(case_id, patient, vitals, clinical, docs, labs, runs, triage, detail, quick, llm_error)
    txt_path = REPORTS_DIR / ("%s_summary.txt" % case_id)
    txt_path.write_text(report, encoding="utf-8")
    if docs:
        raw = []
        for d in docs:
            raw += ["=" * 70, "%s  [%s]" % (d["file"], d["method"]), "=" * 70, d["text"] or d.get("error", ""), ""]
        (REPORTS_DIR / ("%s_extracted_text.txt" % case_id)).write_text("\n".join(raw), encoding="utf-8")
    save_json({"case_id": case_id, "patient": patient, "vitals": vitals, "clinical": clinical,
               "triage": triage, "labs": labs,
               "runs": [{k: v for k, v in r.items() if k != "text"} for r in runs],
               "detailed_analysis": detail, "quick_summary": quick, "llm_error": llm_error},
              REPORTS_DIR / ("%s_case.json" % case_id))

    banner("DONE   (total %.0fs)" % (time.perf_counter() - t_all))
    print("  Triage  : %s" % triage["level"])
    print("  Report  : %s" % txt_path)
    for r in runs:
        print("  Images  : %s" % (OUTPUT_DIR / r["key"] / case_id))
    print()
    sys.stdout.flush()
    os._exit(0)          # do not wait for unused background pre-loads


if __name__ == "__main__":
    import sys
    if "--cli" in sys.argv:
        try:
            main()
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            os._exit(1)
    else:
        import uvicorn
        from backend.config import SERVER_SESSION_OTP
        banner("CLINICALLENS LOCAL CLINICAL SERVER")
        print("  Starting FastAPI server on http://127.0.0.1:8000")
        print()
        print("  ****************************************************************")
        print("  *  ADMIN SESSION 2FA CODE :  [  %s  ]                   *" % SERVER_SESSION_OTP)
        print("  *  (Valid for this entire backend run until server stops)      *")
        print("  ****************************************************************")
        print()
        print("  To run original terminal CLI instead: python app.py --cli")
        uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
