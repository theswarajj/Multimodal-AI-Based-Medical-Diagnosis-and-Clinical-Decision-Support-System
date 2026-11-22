
import os
import sys
import json
import re
import argparse
import datetime
import numpy as np
import torch
import torch.nn.functional as F
import timm
from PIL import Image
from torchvision import transforms

# ── Force UTF-8 on Windows ───────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMG_SIZE = 300
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]

# ═══════════════════════════════════════════════════════════════════════════════
#  CLINICAL METADATA FOR EACH LESION CLASS
# ═══════════════════════════════════════════════════════════════════════════════

CLASS_CLINICAL_INFO = {
    "akiec": {
        "name": "Actinic Keratoses / Intraepithelial Carcinoma",
        "short": "Actinic Keratosis",
        "malignant": True,
        "risk": "PRE-CANCEROUS / MALIGNANT",
        "description": (
            "Actinic keratoses are rough, scaly patches on sun-damaged skin. "
            "They are considered pre-cancerous as they can progress to squamous "
            "cell carcinoma (SCC). Bowen's disease (intraepithelial carcinoma) is "
            "the in-situ form of SCC."
        ),
        "recommendation": (
            "Dermatology referral recommended. Treatment options include cryotherapy, "
            "topical 5-fluorouracil, imiquimod, or photodynamic therapy. "
            "Monitor for progression to invasive SCC."
        ),
        "urgency": "MODERATE",
        "color": "#FF8C00",  # Dark orange
    },
    "bcc": {
        "name": "Basal Cell Carcinoma",
        "short": "Basal Cell Carcinoma",
        "malignant": True,
        "risk": "MALIGNANT",
        "description": (
            "Basal cell carcinoma is the most common type of skin cancer. "
            "It typically appears as a pearly or waxy bump, or a flat, flesh-colored "
            "or brown scar-like lesion. While it rarely metastasizes, it can cause "
            "significant local tissue destruction if untreated."
        ),
        "recommendation": (
            "Prompt dermatology referral required. Biopsy recommended to confirm "
            "diagnosis. Treatment typically involves surgical excision (Mohs surgery "
            "for high-risk areas) or topical therapy for superficial variants."
        ),
        "urgency": "HIGH",
        "color": "#FF4444",  # Red
    },
    "bkl": {
        "name": "Benign Keratosis-like Lesions",
        "short": "Benign Keratosis",
        "malignant": False,
        "risk": "BENIGN",
        "description": (
            "Includes seborrheic keratoses, solar lentigines, and lichen planus-like "
            "keratoses. These are common, non-cancerous growths that appear as brown, "
            "black, or light tan patches. They are cosmetically concerning but "
            "medically benign."
        ),
        "recommendation": (
            "Generally no treatment required. May be removed for cosmetic reasons "
            "or if irritated. If rapid change in size/color is noted, re-evaluate "
            "to rule out melanoma mimicry."
        ),
        "urgency": "LOW",
        "color": "#238636",  # Green
    },
    "df": {
        "name": "Dermatofibroma",
        "short": "Dermatofibroma",
        "malignant": False,
        "risk": "BENIGN",
        "description": (
            "Dermatofibromas are firm, small nodules commonly found on the legs. "
            "They are benign fibrohistiocytic tumors that often develop after minor "
            "trauma or insect bites. They typically present as a dimple when pinched "
            "(positive dimple sign)."
        ),
        "recommendation": (
            "No treatment necessary unless symptomatic or cosmetically concerning. "
            "Excision is curative if removal is desired. Recurrence is uncommon."
        ),
        "urgency": "LOW",
        "color": "#238636",
    },
    "mel": {
        "name": "Melanoma",
        "short": "Melanoma",
        "malignant": True,
        "risk": "MALIGNANT — HIGH PRIORITY",
        "description": (
            "Melanoma is the most dangerous form of skin cancer, arising from "
            "melanocytes. It can metastasize rapidly if not caught early. "
            "Look for the ABCDE criteria: Asymmetry, Border irregularity, "
            "Color variation, Diameter >6mm, and Evolving size/shape/color."
        ),
        "recommendation": (
            "URGENT dermatology referral required. Excisional biopsy with appropriate "
            "margins is the gold standard. Sentinel lymph node biopsy may be indicated "
            "for lesions >1mm Breslow thickness. Early detection is critical for survival."
        ),
        "urgency": "URGENT",
        "color": "#DA3633",  # Bright red
    },
    "nv": {
        "name": "Melanocytic Nevi (Mole)",
        "short": "Melanocytic Nevus",
        "malignant": False,
        "risk": "BENIGN",
        "description": (
            "Melanocytic nevi are benign neoplasms of melanocytes (common moles). "
            "They can be flat or raised, uniformly colored, and typically round/oval. "
            "While most are harmless, atypical nevi with irregular features warrant "
            "monitoring for melanoma transformation."
        ),
        "recommendation": (
            "Routine monitoring recommended. Document size and appearance for baseline. "
            "Apply ABCDE criteria at follow-up visits. Consider excision if atypical "
            "features develop (asymmetry, irregular borders, color changes)."
        ),
        "urgency": "LOW",
        "color": "#238636",
    },
    "vasc": {
        "name": "Vascular Lesions",
        "short": "Vascular Lesion",
        "malignant": False,
        "risk": "BENIGN",
        "description": (
            "Vascular lesions include angiomas, angiokeratomas, pyogenic granulomas, "
            "and hemorrhage. Cherry angiomas are the most common, appearing as small "
            "red dots. These are typically benign collections of blood vessels."
        ),
        "recommendation": (
            "Generally no treatment required. Laser therapy or electrocautery can be "
            "used for cosmetic removal. Pyogenic granulomas may require excision if "
            "they bleed frequently."
        ),
        "urgency": "LOW",
        "color": "#238636",
    },
}

UNCERTAIN_LABEL = "uncertain_other"


# ═══════════════════════════════════════════════════════════════════════════════
#  ANSI COLOR UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

class _Colors:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"

    @classmethod
    def disable(cls):
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith("_"):
                setattr(cls, attr, "")

def _enable_windows_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

_enable_windows_ansi()
C = _Colors


# ═══════════════════════════════════════════════════════════════════════════════
#  MODEL
# ═══════════════════════════════════════════════════════════════════════════════

def get_eval_transform():
    return transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])


def load_model(checkpoint_path, device):
    model = timm.create_model("efficientnet_b3", pretrained=False, num_classes=len(CLASSES))
    state_dict = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(state_dict)
    model.eval().to(device)
    return model


def tta_predict(model, image_tensor, device, use_tta=True):
    """Average predictions over original + flipped versions."""
    variants = [image_tensor]
    if use_tta:
        variants.append(torch.flip(image_tensor, dims=[3]))  # horizontal
        variants.append(torch.flip(image_tensor, dims=[2]))  # vertical

    probs_sum = None
    with torch.no_grad():
        for v in variants:
            v = v.to(device)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                logits = model(v)
            probs = F.softmax(logits, dim=1)
            probs_sum = probs if probs_sum is None else probs_sum + probs

    return probs_sum / len(variants)


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAD-CAM HEATMAP
# ═══════════════════════════════════════════════════════════════════════════════

class GradCAM:
    """Simple Grad-CAM for the last convolutional layer of EfficientNet."""

    def __init__(self, model):
        self.model = model
        self.gradients = None
        self.activations = None
        self._hooks = []

        # EfficientNet-B3 in timm: last conv block is model.conv_head
        target_layer = model.conv_head
        self._hooks.append(
            target_layer.register_forward_hook(self._save_activation)
        )
        self._hooks.append(
            target_layer.register_full_backward_hook(self._save_gradient)
        )

    def _save_activation(self, module, input, output):
        self.activations = output.detach()

    def _save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def generate(self, input_tensor, target_class=None):
        self.model.zero_grad()
        output = self.model(input_tensor)

        if target_class is None:
            target_class = output.argmax(dim=1).item()

        one_hot = torch.zeros_like(output)
        one_hot[0, target_class] = 1.0
        output.backward(gradient=one_hot, retain_graph=True)

        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1, keepdim=True)
        cam = F.relu(cam)
        cam = F.interpolate(cam, size=(IMG_SIZE, IMG_SIZE), mode="bilinear", align_corners=False)
        cam = cam.squeeze().cpu().numpy()

        # Normalize to [0, 1]
        cam_min, cam_max = cam.min(), cam.max()
        if cam_max - cam_min > 1e-8:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = np.zeros_like(cam)

        return cam, target_class

    def remove_hooks(self):
        for h in self._hooks:
            h.remove()


# ═══════════════════════════════════════════════════════════════════════════════
#  INFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

def predict_image(model, image_path, transform, device, threshold, use_tta):
    """Run inference on a single image with Grad-CAM."""
    image_pil = Image.open(image_path).convert("RGB")
    tensor = transform(image_pil).unsqueeze(0)

    # Regular prediction with TTA
    probs = tta_predict(model, tensor, device, use_tta)[0].cpu().numpy()

    top_idx = int(probs.argmax())
    top_class = CLASSES[top_idx]
    top_conf = float(probs[top_idx])
    all_scores = {CLASSES[i]: float(probs[i]) for i in range(len(CLASSES))}

    # Grad-CAM heatmap (without TTA, for clean spatial attribution)
    grad_cam = GradCAM(model)
    cam_input = tensor.to(device).requires_grad_(True)
    heatmap, _ = grad_cam.generate(cam_input, target_class=top_idx)
    grad_cam.remove_hooks()

    # Malignancy assessment
    malignant_prob = sum(probs[i] for i, cls in enumerate(CLASSES)
                        if CLASS_CLINICAL_INFO[cls]["malignant"])
    benign_prob = 1.0 - malignant_prob

    # Build result
    if top_conf < threshold:
        result = {
            "prediction": UNCERTAIN_LABEL,
            "full_name": "Uncertain / Outside Trained Classes",
            "confidence": float(round(top_conf, 4)),
            "top_guess": top_class,
            "top_guess_name": CLASS_CLINICAL_INFO[top_class]["name"],
            "uncertain": True,
        }
    else:
        info = CLASS_CLINICAL_INFO[top_class]
        result = {
            "prediction": top_class,
            "full_name": info["name"],
            "confidence": float(round(top_conf, 4)),
            "malignant": info["malignant"],
            "risk_level": info["risk"],
            "urgency": info["urgency"],
            "uncertain": False,
        }

    result.update({
        "image_path": image_path,
        "patient_id": os.path.splitext(os.path.basename(image_path))[0],
        "all_class_scores": {k: float(round(v, 4)) for k, v in
                            sorted(all_scores.items(), key=lambda x: -x[1])},
        "malignant_probability": float(round(malignant_prob, 4)),
        "benign_probability": float(round(benign_prob, 4)),
        "timestamp": datetime.datetime.now().isoformat(),
        "_heatmap": heatmap,       # kept for visualization, not serialized
        "_image_pil": image_pil,   # kept for visualization, not serialized
    })

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  MATPLOTLIB CLINICAL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

def generate_clinical_figures(result, output_dir):
    """Generate a comprehensive clinical dashboard as PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.patches import FancyBboxPatch
    from matplotlib.colors import LinearSegmentedColormap

    os.makedirs(output_dir, exist_ok=True)
    saved = []

    patient_id = result["patient_id"]
    image_pil = result.get("_image_pil")
    heatmap = result.get("_heatmap")
    if image_pil is None:
        return saved

    image_np = np.array(image_pil.resize((IMG_SIZE, IMG_SIZE)))
    pred_class = result["prediction"]
    info = CLASS_CLINICAL_INFO.get(pred_class, {})

    # ══════════════════════════════════════════════════════════════════════
    #  MAIN DASHBOARD
    # ══════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(22, 14), facecolor="#0D1117")
    gs = gridspec.GridSpec(2, 4, height_ratios=[1.2, 1.0], hspace=0.3, wspace=0.3,
                           left=0.04, right=0.96, top=0.92, bottom=0.06)

    fig.suptitle(f"Skin Lesion Analysis — {patient_id}",
                 fontsize=24, fontweight="bold", color="white", y=0.97)

    # ── Top-left: Original image ──
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.imshow(image_np)
    ax1.set_title("Original Dermoscopic Image", fontsize=13,
                  fontweight="bold", color="white", pad=10)
    ax1.axis("off")

    # ── Top-center-left: Grad-CAM heatmap overlay ──
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(image_np)
    if heatmap is not None:
        # Custom colormap: transparent -> yellow -> red
        cam_cmap = LinearSegmentedColormap.from_list(
            "cam", [(0, 0, 0, 0), (1, 1, 0, 0.4), (1, 0, 0, 0.8)])
        ax2.imshow(heatmap, cmap=cam_cmap, alpha=0.7)
    ax2.set_title("Grad-CAM Attention Map\n(Model Focus Area)", fontsize=13,
                  fontweight="bold", color="white", pad=10)
    ax2.axis("off")

    # ── Top-center-right: Heatmap only (isolated) ──
    ax3 = fig.add_subplot(gs[0, 2])
    if heatmap is not None:
        ax3.imshow(heatmap, cmap="inferno", vmin=0, vmax=1)
        ax3.set_title("Attention Intensity\n(Hot = High Focus)", fontsize=13,
                      fontweight="bold", color="white", pad=10)
    ax3.axis("off")

    # ── Top-right: Clinical summary card ──
    ax_card = fig.add_subplot(gs[0, 3])
    ax_card.set_facecolor("#161B22")
    ax_card.set_xlim(0, 1)
    ax_card.set_ylim(0, 1)
    ax_card.axis("off")

    risk_color = info.get("color", "#8B949E")
    urgency = info.get("urgency", result.get("urgency", "N/A"))
    is_malignant = info.get("malignant", result.get("malignant", False))

    urgency_colors = {"URGENT": "#DA3633", "HIGH": "#FF4444", "MODERATE": "#FF8C00", "LOW": "#238636"}
    u_color = urgency_colors.get(urgency, "#8B949E")

    card_lines = [
        (0.92, "Clinical Summary", "white", 17, "bold"),
        (0.84, f"Class: {result.get('full_name', pred_class)}", "#C9D1D9", 11, "normal"),
        (0.73, f"Prediction: {pred_class.upper()}", risk_color, 16, "bold"),
        (0.64, f"Confidence: {result['confidence']:.1%}", "white", 15, "bold"),
        (0.55, f"Risk: {info.get('risk', 'N/A')}", risk_color, 13, "bold"),
        (0.46, f"Urgency: {urgency}", u_color, 13, "bold"),
        (0.36, f"Malignant Prob: {result['malignant_probability']:.1%}",
         "#DA3633" if result['malignant_probability'] > 0.5 else "#238636", 12, "bold"),
        (0.27, f"Benign Prob: {result['benign_probability']:.1%}",
         "#238636" if result['benign_probability'] > 0.5 else "#DA3633", 12, "normal"),
    ]

    if is_malignant:
        card_lines.append((0.14, "⚠ SPECIALIST REFERRAL ADVISED", "#DA3633", 12, "bold"))
    else:
        card_lines.append((0.14, "✓ Likely benign — routine monitoring", "#238636", 11, "normal"))

    for y, text, color, size, weight in card_lines:
        ax_card.text(0.08, y, text, fontsize=size, fontweight=weight,
                     color=color, transform=ax_card.transAxes)

    border = FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0.02",
                            facecolor="none", edgecolor=risk_color, linewidth=2.5,
                            transform=ax_card.transAxes)
    ax_card.add_patch(border)

    # ── Bottom-left: Class probability bar chart ──
    ax_bars = fig.add_subplot(gs[1, :2])
    ax_bars.set_facecolor("#0D1117")

    scores = result["all_class_scores"]
    bar_classes = list(scores.keys())
    bar_values = [scores[c] for c in bar_classes]
    bar_colors_list = []
    for c in bar_classes:
        ci = CLASS_CLINICAL_INFO.get(c, {})
        bar_colors_list.append(ci.get("color", "#8B949E"))

    bar_labels = [f"{c} ({CLASS_CLINICAL_INFO.get(c, {}).get('short', c)})" for c in bar_classes]

    bars = ax_bars.barh(bar_labels, bar_values, color=bar_colors_list, height=0.6,
                        edgecolor="#0D1117", linewidth=2)
    for bar, val in zip(bars, bar_values):
        ax_bars.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                     f"{val:.1%}", va="center", fontsize=11, fontweight="bold", color="white")

    ax_bars.set_xlim(0, 1.12)
    ax_bars.set_title("Class Probability Distribution", fontsize=14,
                      fontweight="bold", color="white", pad=12)
    ax_bars.invert_yaxis()
    ax_bars.tick_params(colors="white", labelsize=10)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    for spine in ax_bars.spines.values():
        spine.set_color("#30363D")

    # ── Bottom-right: Malignant vs Benign donut chart ──
    ax_donut = fig.add_subplot(gs[1, 2])
    ax_donut.set_facecolor("#0D1117")

    mal_prob = result["malignant_probability"]
    ben_prob = result["benign_probability"]
    donut_colors = ["#DA3633", "#238636"]
    wedges, texts, autotexts = ax_donut.pie(
        [mal_prob, ben_prob],
        labels=["Malignant", "Benign"],
        colors=donut_colors,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.75,
        textprops={"color": "white", "fontsize": 12, "fontweight": "bold"},
        wedgeprops={"edgecolor": "#0D1117", "linewidth": 3, "width": 0.4},
    )
    for at in autotexts:
        at.set_fontsize(11)
        at.set_fontweight("bold")
    ax_donut.set_title("Malignancy Assessment", fontsize=14,
                       fontweight="bold", color="white", pad=12)

    # ── Bottom far-right: Recommendation text ──
    ax_rec = fig.add_subplot(gs[1, 3])
    ax_rec.set_facecolor("#161B22")
    ax_rec.set_xlim(0, 1)
    ax_rec.set_ylim(0, 1)
    ax_rec.axis("off")

    desc = info.get("description", "")
    rec = info.get("recommendation", "")

    ax_rec.text(0.05, 0.95, "Clinical Notes", fontsize=14, fontweight="bold",
                color="white", transform=ax_rec.transAxes, va="top")

    # Word-wrap description
    if desc:
        ax_rec.text(0.05, 0.82, _wrap_for_figure(desc, 38), fontsize=9,
                    color="#C9D1D9", transform=ax_rec.transAxes, va="top",
                    family="monospace", linespacing=1.4)

    if rec:
        ax_rec.text(0.05, 0.38, "Recommendation:", fontsize=11, fontweight="bold",
                    color="#58A6FF", transform=ax_rec.transAxes, va="top")
        ax_rec.text(0.05, 0.30, _wrap_for_figure(rec, 38), fontsize=9,
                    color="#C9D1D9", transform=ax_rec.transAxes, va="top",
                    family="monospace", linespacing=1.4)

    border2 = FancyBboxPatch((0.01, 0.01), 0.98, 0.98, boxstyle="round,pad=0.02",
                             facecolor="none", edgecolor="#30363D", linewidth=1.5,
                             transform=ax_rec.transAxes)
    ax_rec.add_patch(border2)

    path1 = os.path.join(output_dir, f"{patient_id}_clinical_dashboard.png")
    fig.savefig(path1, dpi=150, facecolor="#0D1117", bbox_inches="tight")
    plt.close(fig)
    saved.append(path1)

    return saved


def _wrap_for_figure(text, width):
    """Simple word-wrap for matplotlib text."""
    words = text.split()
    lines, current = [], ""
    for w in words:
        if len(current) + len(w) + 1 > width and current:
            lines.append(current)
            current = w
        else:
            current = current + " " + w if current else w
    if current:
        lines.append(current)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  TERMINAL OUTPUT FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════

def _wrap_text(text, width=65, indent="     "):
    ansi_re_pat = re.compile(r'\033\[[0-9;]*m')
    words = text.split()
    lines, current_plain, current_rich = [], "", indent
    for w in words:
        w_plain = ansi_re_pat.sub('', w)
        if len(current_plain) + len(w_plain) + 1 > width and current_plain.strip():
            lines.append(current_rich)
            current_plain = w_plain
            current_rich = indent + w
        else:
            current_plain += (" " if current_plain.strip() else "") + w_plain
            current_rich += (" " if current_rich.strip() else "") + w
    if current_rich.strip():
        lines.append(current_rich)
    return lines


def _confidence_gauge(confidence, width=30):
    filled = int(round(confidence * width))
    empty = width - filled
    if confidence >= 0.80:
        color = C.GREEN
    elif confidence >= 0.60:
        color = C.YELLOW
    else:
        color = C.RED
    bar = f"{color}{'█' * filled}{C.GRAY}{'░' * empty}{C.RESET}"
    return f"  [{bar}]  {color}{C.BOLD}{confidence:.1%}{C.RESET}"


def _urgency_badge(urgency):
    colors = {"URGENT": C.RED, "HIGH": C.RED, "MODERATE": C.YELLOW, "LOW": C.GREEN}
    color = colors.get(urgency, C.GRAY)
    return f"{color}{C.BOLD}● {urgency}{C.RESET}"


def print_model_banner(args, device, n_files):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print()
    print(f"  {C.MAGENTA}{C.BOLD}{'━' * 68}{C.RESET}")
    print(f"  {C.BOLD}  🔬  SKIN LESION CLASSIFICATION — CLINICAL REPORT{C.RESET}")
    print(f"  {C.MAGENTA}{C.BOLD}{'━' * 68}{C.RESET}")
    print()
    print(f"  {C.DIM}  Model       {C.RESET} EfficientNet-B3 (HAM10000, 7 classes)")
    print(f"  {C.DIM}  Dataset     {C.RESET} HAM10000 Dermoscopic Skin Lesion Database")
    print(f"  {C.DIM}  Classes     {C.RESET} akiec, bcc, bkl, df, mel, nv, vasc")
    print(f"  {C.DIM}  TTA         {C.RESET} {'Enabled (3x: original + H-flip + V-flip)' if not args.no_tta else 'Disabled'}")
    print(f"  {C.DIM}  Threshold   {C.RESET} {args.threshold:.0%} minimum confidence")
    print(f"  {C.DIM}  Device      {C.RESET} {device}")
    print(f"  {C.DIM}  Timestamp   {C.RESET} {now}")
    print(f"  {C.DIM}  Images      {C.RESET} {n_files} file(s) queued for analysis")
    print()
    print(f"  {C.MAGENTA}{'─' * 68}{C.RESET}")
    print()


def print_result_detailed(result):
    pred = result["prediction"]
    info = CLASS_CLINICAL_INFO.get(pred, {})
    conf = result["confidence"]
    is_uncertain = result.get("uncertain", False)

    # ── Patient header ──
    print(f"  {C.BOLD}📂 IMAGE: {C.CYAN}{result['patient_id']}{C.RESET}")
    print(f"  {C.DIM}   File: {result['image_path']}{C.RESET}")
    print()

    # ── Prediction ──
    print(f"  {C.BOLD}🔬 PREDICTION{C.RESET}")
    if is_uncertain:
        print(f"     Result:     {C.YELLOW}{C.BOLD}⚠ UNCERTAIN / OUTSIDE TRAINED CLASSES{C.RESET}")
        print(f"     Best guess: {result.get('top_guess', 'N/A')} "
              f"({result.get('top_guess_name', '')}) at {conf:.1%}")
        print(f"     {C.DIM}Image quality may be poor or condition not in training set{C.RESET}")
    else:
        is_malignant = info.get("malignant", False)
        if is_malignant:
            pred_color = C.RED
            risk_icon = "⚠"
        else:
            pred_color = C.GREEN
            risk_icon = "✓"

        print(f"     Diagnosis:  {pred_color}{C.BOLD}{risk_icon} {info.get('name', pred)}{C.RESET}")
        print(f"     Class:      {C.BOLD}{pred.upper()}{C.RESET}")
        print(f"     Risk:       {pred_color}{C.BOLD}{info.get('risk', 'N/A')}{C.RESET}")
        print(f"     Urgency:    {_urgency_badge(info.get('urgency', 'N/A'))}")
    print()

    # ── Confidence gauge ──
    print(f"  {C.BOLD}📊 CONFIDENCE{C.RESET}")
    print(f"  {_confidence_gauge(conf)}")
    print()

    # ── Malignancy assessment ──
    mal_prob = result["malignant_probability"]
    ben_prob = result["benign_probability"]
    print(f"  {C.BOLD}🛡️  MALIGNANCY ASSESSMENT{C.RESET}")

    mal_bar_w = int(round(mal_prob * 25))
    ben_bar_w = int(round(ben_prob * 25))
    print(f"     {C.RED}Malignant  [{C.RED}{'█' * mal_bar_w}{C.GRAY}{'░' * (25 - mal_bar_w)}{C.RESET}]  "
          f"{C.RED}{C.BOLD}{mal_prob:.1%}{C.RESET}")
    print(f"     {C.GREEN}Benign     [{C.GREEN}{'█' * ben_bar_w}{C.GRAY}{'░' * (25 - ben_bar_w)}{C.RESET}]  "
          f"{C.GREEN}{C.BOLD}{ben_prob:.1%}{C.RESET}")

    # Malignant classes breakdown
    print(f"     {C.DIM}(akiec + bcc + mel = malignant; bkl + df + nv + vasc = benign){C.RESET}")
    print()

    # ── All class scores ──
    print(f"  {C.BOLD}📋 ALL CLASS PROBABILITIES{C.RESET}")
    for cls, score in result["all_class_scores"].items():
        ci = CLASS_CLINICAL_INFO.get(cls, {})
        is_mal = ci.get("malignant", False)
        color = C.RED if is_mal else C.GREEN
        tag = f"{C.RED}[MAL]{C.RESET}" if is_mal else f"{C.GREEN}[BEN]{C.RESET}"
        bar_w = int(round(score * 25))
        name_short = ci.get("short", cls)
        print(f"     {tag} {cls:6s}  [{color}{'█' * bar_w}{C.GRAY}{'░' * (25 - bar_w)}{C.RESET}]  "
              f"{score:6.1%}  {C.DIM}{name_short}{C.RESET}")
    print()

    # ── Clinical description ──
    if info.get("description"):
        print(f"  {C.BOLD}📖 CLINICAL DESCRIPTION{C.RESET}")
        for line in _wrap_text(info["description"], width=62, indent="     "):
            print(f"  {C.DIM}{line}{C.RESET}")
        print()

    # ── Recommendation ──
    if info.get("recommendation"):
        urgency = info.get("urgency", "LOW")
        rec_color = C.RED if urgency in ("URGENT", "HIGH") else C.YELLOW if urgency == "MODERATE" else C.GREEN
        print(f"  {C.BOLD}💊 RECOMMENDATION{C.RESET}")
        for line in _wrap_text(info["recommendation"], width=62, indent="     "):
            print(f"  {rec_color}{line}{C.RESET}")
        print()

    print(f"  {C.MAGENTA}{'─' * 68}{C.RESET}")
    print()


def print_batch_summary(results):
    if len(results) <= 1:
        return

    print()
    print(f"  {C.BOLD}{C.MAGENTA}{'━' * 68}{C.RESET}")
    print(f"  {C.BOLD}📊 BATCH SUMMARY ({len(results)} images){C.RESET}")
    print(f"  {C.BOLD}{C.MAGENTA}{'━' * 68}{C.RESET}")
    print()

    col_w = [22, 10, 12, 10, 16]
    print(f"  {C.DIM}┌{'─'*(col_w[0]+2)}┬{'─'*(col_w[1]+2)}┬{'─'*(col_w[2]+2)}┬{'─'*(col_w[3]+2)}┬{'─'*(col_w[4]+2)}┐{C.RESET}")
    print(f"  {C.DIM}│{C.RESET} {C.BOLD}{'Image':<{col_w[0]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Class':<{col_w[1]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Confidence':<{col_w[2]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Mal.%':<{col_w[3]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Urgency':<{col_w[4]}}{C.RESET} {C.DIM}│{C.RESET}")
    print(f"  {C.DIM}├{'═'*(col_w[0]+2)}┼{'═'*(col_w[1]+2)}┼{'═'*(col_w[2]+2)}┼{'═'*(col_w[3]+2)}┼{'═'*(col_w[4]+2)}┤{C.RESET}")

    n_malignant, n_benign, n_uncertain = 0, 0, 0
    for r in results:
        ci = CLASS_CLINICAL_INFO.get(r["prediction"], {})
        is_mal = ci.get("malignant", False)
        if r.get("uncertain"):
            n_uncertain += 1
        elif is_mal:
            n_malignant += 1
        else:
            n_benign += 1

        patient = r["patient_id"][:col_w[0]]
        pred = r["prediction"][:col_w[1]]
        pred_color = C.RED if is_mal else C.GREEN
        conf_str = f"{r['confidence']:.1%}"
        mal_str = f"{r['malignant_probability']:.1%}"
        urgency = ci.get("urgency", "N/A")

        print(f"  {C.DIM}│{C.RESET} {patient:<{col_w[0]}} "
              f"{C.DIM}│{C.RESET} {pred_color}{pred:<{col_w[1]}}{C.RESET} "
              f"{C.DIM}│{C.RESET} {conf_str:<{col_w[2]}} "
              f"{C.DIM}│{C.RESET} {mal_str:<{col_w[3]}} "
              f"{C.DIM}│{C.RESET} {_urgency_badge(urgency)}{' '*(col_w[4]-len(urgency)-2)} {C.DIM}│{C.RESET}")

    print(f"  {C.DIM}└{'─'*(col_w[0]+2)}┴{'─'*(col_w[1]+2)}┴{'─'*(col_w[2]+2)}┴{'─'*(col_w[3]+2)}┴{'─'*(col_w[4]+2)}┘{C.RESET}")

    print()
    print(f"  {C.BOLD}Summary:{C.RESET}  {len(results)} images  |  "
          f"{C.RED}{n_malignant} Malignant{C.RESET}  |  "
          f"{C.GREEN}{n_benign} Benign{C.RESET}  |  "
          f"{C.YELLOW}{n_uncertain} Uncertain{C.RESET}")

    # Flag urgent cases
    urgent = [r for r in results if CLASS_CLINICAL_INFO.get(r["prediction"], {}).get("urgency") in ("URGENT", "HIGH")]
    if urgent:
        print(f"  {C.RED}{C.BOLD}⚠  {len(urgent)} case(s) require specialist referral:{C.RESET}")
        for r in urgent:
            ci = CLASS_CLINICAL_INFO.get(r["prediction"], {})
            print(f"     {C.RED}• {r['patient_id']}  —  {ci.get('name', r['prediction'])}  ({r['confidence']:.1%}){C.RESET}")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  JSON REPORT EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def export_json_report(results, args, device, report_path):
    report = {
        "report_type": "Skin Lesion Classification",
        "generated_at": datetime.datetime.now().isoformat(),
        "model": {
            "architecture": "EfficientNet-B3",
            "dataset": "HAM10000",
            "checkpoint": args.model,
            "num_classes": len(CLASSES),
            "classes": CLASSES,
            "tta_enabled": not args.no_tta,
            "confidence_threshold": args.threshold,
            "device": str(device),
        },
        "results": [],
        "summary": {
            "total_images": len(results),
            "malignant": sum(1 for r in results if CLASS_CLINICAL_INFO.get(r["prediction"], {}).get("malignant")),
            "benign": sum(1 for r in results if not CLASS_CLINICAL_INFO.get(r["prediction"], {}).get("malignant") and not r.get("uncertain")),
            "uncertain": sum(1 for r in results if r.get("uncertain")),
            "avg_confidence": float(round(sum(r["confidence"] for r in results) / max(len(results), 1), 4)),
        },
        "disclaimer": (
            "This is an AI-assisted screening tool trained on the HAM10000 dataset. "
            "All findings are probabilistic and must be confirmed by a qualified "
            "dermatologist. Not a substitute for professional medical diagnosis."
        ),
    }

    for r in results:
        ci = CLASS_CLINICAL_INFO.get(r["prediction"], {})
        entry = {
            "patient_id": r["patient_id"],
            "file": r["image_path"],
            "prediction": r["prediction"],
            "full_name": r.get("full_name", ""),
            "confidence": r["confidence"],
            "malignant": ci.get("malignant", False),
            "risk_level": ci.get("risk", "N/A"),
            "urgency": ci.get("urgency", "N/A"),
            "malignant_probability": r["malignant_probability"],
            "benign_probability": r["benign_probability"],
            "all_class_scores": r["all_class_scores"],
            "timestamp": r["timestamp"],
        }
        report["results"].append(entry)

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    return report_path


# ═══════════════════════════════════════════════════════════════════════════════
#  QUIET MODE
# ═══════════════════════════════════════════════════════════════════════════════

def print_quiet(result):
    ci = CLASS_CLINICAL_INFO.get(result["prediction"], {})
    entry = {
        "patient_id": result["patient_id"],
        "prediction": result["prediction"],
        "full_name": result.get("full_name", ""),
        "confidence": result["confidence"],
        "malignant": ci.get("malignant", False),
        "urgency": ci.get("urgency", "N/A"),
        "malignant_probability": result["malignant_probability"],
        "all_scores": result["all_class_scores"],
    }
    print(json.dumps(entry))


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Skin Lesion Classification — Clinical Inference Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python running.py\n"
            "  python running.py --image test.jpg\n"
            "  python running.py --image_dir test_images/ --report results.json\n"
            "  python running.py --image test.jpg --quiet\n"
        ),
    )
    parser.add_argument("--image", type=str, default=None,
                         help="Path to a skin lesion image")
    parser.add_argument("--image_dir", type=str, default=None,
                         help="Path to folder of images for batch analysis")
    parser.add_argument("--input", type=str, default="INPUT",
                         help="Path to input file or folder (default: INPUT)")
    parser.add_argument("--model", type=str, default="checkpoints/efficientnet_b3_ham10000_v2_best.pth")
    parser.add_argument("--threshold", type=float, default=0.5,
                         help="Confidence below this is reported as Uncertain (default: 0.5)")
    parser.add_argument("--no_tta", action="store_true", help="Disable test-time augmentation")
    parser.add_argument("--report", type=str, default=None,
                         help="Export structured JSON report to this path")
    parser.add_argument("--output_dir", type=str, default="results",
                         help="Directory for generated figures (default: results/)")
    parser.add_argument("--no-figures", action="store_true",
                         help="Skip generating matplotlib figures")
    parser.add_argument("--quiet", action="store_true",
                         help="Machine-readable JSON-lines output only")
    args = parser.parse_args()

    # ── Resolve paths relative to script directory ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if args.image and not os.path.isabs(args.image):
        args.image = os.path.join(script_dir, args.image)
    if args.image_dir and not os.path.isabs(args.image_dir):
        args.image_dir = os.path.join(script_dir, args.image_dir)
    if not os.path.isabs(args.input):
        args.input = os.path.join(script_dir, args.input)
    if not os.path.isabs(args.model):
        args.model = os.path.join(script_dir, args.model)
        
    if not os.path.isabs(args.output_dir):
        args.output_dir = os.path.join(script_dir, args.output_dir)
        
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_dir = os.path.join(args.output_dir, f"run_{timestamp_str}")
    os.makedirs(args.output_dir, exist_ok=True)

    if args.quiet or not sys.stdout.isatty():
        C.disable()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── Load model ──
    model = load_model(args.model, device)
    transform = get_eval_transform()

    # ── Collect images ──
    image_paths = []
    target_path = args.input
    if args.image:
        target_path = args.image
    elif args.image_dir:
        target_path = args.image_dir

    if os.path.isdir(target_path):
        valid_files = []
        for fname in sorted(os.listdir(target_path)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
                valid_files.append(os.path.join(target_path, fname))
        
        if len(valid_files) == 1:
            image_paths.append(valid_files[0])
        elif len(valid_files) > 1:
            print()
            print(f"  {C.CYAN}{C.BOLD}╭{'─' * 52}╮{C.RESET}")
            print(f"  {C.CYAN}{C.BOLD}│  📂 MULTIPLE IMAGES DETECTED{' ' * 23}│{C.RESET}")
            print(f"  {C.CYAN}{C.BOLD}╰{'─' * 52}╯{C.RESET}")
            print(f"  {C.DIM}Target folder: {target_path}{C.RESET}\n")
            
            for idx, f in enumerate(valid_files):
                print(f"  {C.BOLD}{C.GREEN}[{idx + 1:2d}]{C.RESET} {os.path.basename(f)}")
            print(f"  {C.BOLD}{C.MAGENTA}[{len(valid_files) + 1:2d}]{C.RESET} {C.BOLD}Process all images (Batch Mode){C.RESET}")
            
            print()
            while True:
                try:
                    choice = input(f"  {C.YELLOW}▶ Select an option (1-{len(valid_files) + 1}): {C.RESET}")
                    idx = int(choice) - 1
                    if 0 <= idx < len(valid_files):
                        image_paths.append(valid_files[idx])
                        break
                    elif idx == len(valid_files):
                        image_paths.extend(valid_files)
                        break
                    else:
                        print("Invalid selection. Try again.")
                except ValueError:
                    print("Please enter a valid number.")
    elif os.path.isfile(target_path):
        if target_path.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
            image_paths.append(target_path)

    if not image_paths:
        print(f"No image files found in {target_path}.", file=sys.stderr)
        sys.exit(1)

    # ── Banner ──
    if not args.quiet:
        print_model_banner(args, device, len(image_paths))

    # ── Run inference ──
    all_results = []
    for img_path in image_paths:
        try:
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"Image not found: {img_path}")

            result = predict_image(model, img_path, transform, device,
                                   args.threshold, not args.no_tta)
            all_results.append(result)

            if args.quiet:
                print_quiet(result)
            else:
                print_result_detailed(result)

                # Generate figures
                if not getattr(args, 'no_figures', False):
                    saved_figs = generate_clinical_figures(result, args.output_dir)
                    for fig_path in saved_figs:
                        print(f"  {C.GREEN}📊 Figure saved:{C.RESET} {fig_path}")
                    print()

        except Exception as e:
            if args.quiet:
                print(json.dumps({"file": img_path, "error": str(e)}), file=sys.stderr)
            else:
                print(f"  {C.RED}{C.BOLD}✗ ERROR{C.RESET} processing {img_path}: {e}")
                print()

    # ── Clean up internal data ──
    for r in all_results:
        r.pop("_heatmap", None)
        r.pop("_image_pil", None)

    # ── Batch summary ──
    if not args.quiet:
        print_batch_summary(all_results)

    # ── JSON report ──
    if all_results:
        report_path = args.report if args.report else os.path.join(args.output_dir, "report.json")
        path = export_json_report(all_results, args, device, report_path)
        if not args.quiet:
            print(f"  {C.GREEN}{C.BOLD}📄 Report exported:{C.RESET} {path}")
            print()


if __name__ == "__main__":
    main()
