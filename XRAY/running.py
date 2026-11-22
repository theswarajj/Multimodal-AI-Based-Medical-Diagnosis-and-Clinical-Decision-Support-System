

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

# -- Force UTF-8 on Windows ---------------------------------------------------
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# =============================================================================
#  CLINICAL METADATA FOR EACH FINDING
# =============================================================================

FINDING_CLINICAL_INFO = {
    "No Finding": {
        "short": "Normal",
        "description": "No acute cardiopulmonary abnormality detected on this study.",
        "region": "Global",
        "urgency": "NONE",
        "severity": "NORMAL",
        "recommendation": "No acute intervention required. Routine follow-up as clinically indicated.",
        "color": "#238636",
    },
    "Enlarged Cardiomediastinum": {
        "short": "Widened Mediastinum",
        "description": (
            "Widened cardiomediastinal silhouette suggesting possible aortic "
            "aneurysm, mediastinal mass, or lymphadenopathy. May also be due "
            "to patient positioning (AP view can exaggerate width)."
        ),
        "region": "Mediastinum",
        "urgency": "MODERATE",
        "severity": "MODERATE",
        "recommendation": (
            "Correlate with clinical history. Consider CT chest with contrast "
            "to evaluate mediastinal structures if new or progressive."
        ),
        "color": "#FF8C00",
    },
    "Cardiomegaly": {
        "short": "Enlarged Heart",
        "description": (
            "Cardiac silhouette enlarged beyond 50% of thoracic diameter (CTR > 0.5). "
            "Suggests cardiomyopathy, valvular disease, pericardial effusion, or "
            "chronic heart failure."
        ),
        "region": "Heart",
        "urgency": "MODERATE",
        "severity": "MODERATE",
        "recommendation": (
            "Echocardiography recommended if new finding. Correlate with BNP/NT-proBNP. "
            "Consider cardiology referral for evaluation of underlying etiology."
        ),
        "color": "#FF8C00",
    },
    "Lung Opacity": {
        "short": "Lung Opacity",
        "description": (
            "Area of increased density in the lung parenchyma. Differential includes "
            "pneumonia, atelectasis, pulmonary edema, hemorrhage, or mass lesion. "
            "Clinical correlation is essential."
        ),
        "region": "Lung Parenchyma",
        "urgency": "MODERATE",
        "severity": "MODERATE",
        "recommendation": (
            "Correlate with clinical presentation (fever, cough, dyspnea). "
            "Consider CT chest for further characterization if mass or nodule suspected."
        ),
        "color": "#FF8C00",
    },
    "Lung Lesion": {
        "short": "Focal Lung Lesion",
        "description": (
            "Focal abnormal tissue in the lung. May represent a nodule, mass, "
            "granuloma, or malignancy. Size, morphology, and growth rate are "
            "critical for risk stratification."
        ),
        "region": "Lung Parenchyma",
        "urgency": "HIGH",
        "severity": "HIGH",
        "recommendation": (
            "CT chest recommended for further characterization. Apply Lung-RADS "
            "or Fleischner criteria for follow-up. Pulmonology/oncology referral "
            "if suspicious for malignancy."
        ),
        "color": "#FF4444",
    },
    "Edema": {
        "short": "Pulmonary Edema",
        "description": (
            "Fluid accumulation in the lungs, often presenting as bilateral "
            "perihilar opacities, Kerley B lines, or pleural effusions. "
            "Most commonly due to congestive heart failure."
        ),
        "region": "Bilateral Lungs",
        "urgency": "HIGH",
        "severity": "HIGH",
        "recommendation": (
            "URGENT clinical assessment. Check BNP, echocardiography, and oxygen "
            "saturation. Diuretic therapy may be indicated. Consider ICU admission "
            "if respiratory distress is present."
        ),
        "color": "#FF4444",
    },
    "Consolidation": {
        "short": "Consolidation",
        "description": (
            "Lung tissue filled with liquid (pus, blood, water) instead of air. "
            "Air bronchograms may be visible. Most common cause is bacterial "
            "pneumonia. Can also result from hemorrhage or aspiration."
        ),
        "region": "Lung Parenchyma",
        "urgency": "HIGH",
        "severity": "HIGH",
        "recommendation": (
            "URGENT: obtain sputum culture and blood cultures. Start empiric "
            "antibiotics per local guidelines. Monitor oxygen saturation. "
            "Consider CT if poor response to treatment."
        ),
        "color": "#FF4444",
    },
    "Pneumonia": {
        "short": "Pneumonia",
        "description": (
            "Lung infection/inflammation presenting as focal or multifocal opacities. "
            "Typical presentations include lobar consolidation, bronchopneumonia "
            "pattern, or ground-glass opacities."
        ),
        "region": "Lung Parenchyma",
        "urgency": "HIGH",
        "severity": "HIGH",
        "recommendation": (
            "URGENT: Initiate empiric antimicrobial therapy. Obtain blood cultures "
            "before antibiotics if possible. Calculate CURB-65 or PSI for severity "
            "stratification. Monitor respiratory status."
        ),
        "color": "#FF4444",
    },
    "Atelectasis": {
        "short": "Lung Collapse",
        "description": (
            "Partial or complete collapse of lung tissue. May be due to "
            "bronchial obstruction (mucus plug, tumor), post-surgical changes, "
            "or external compression."
        ),
        "region": "Lung Parenchyma",
        "urgency": "MODERATE",
        "severity": "MODERATE",
        "recommendation": (
            "Incentive spirometry and chest physiotherapy for post-operative cases. "
            "If new or progressive, consider bronchoscopy to rule out endobronchial "
            "obstruction."
        ),
        "color": "#FF8C00",
    },
    "Pneumothorax": {
        "short": "Collapsed Lung",
        "description": (
            "Air in the pleural space causing partial or complete lung collapse. "
            "Can be spontaneous, traumatic, or iatrogenic. Tension pneumothorax "
            "is a medical emergency."
        ),
        "region": "Pleural Space",
        "urgency": "URGENT",
        "severity": "CRITICAL",
        "recommendation": (
            "EMERGENT evaluation required. If tension pneumothorax suspected, "
            "immediate needle decompression followed by chest tube placement. "
            "Small stable pneumothorax may be observed with serial imaging."
        ),
        "color": "#DA3633",
    },
    "Pleural Effusion": {
        "short": "Fluid Around Lung",
        "description": (
            "Fluid collection in the pleural space, visible as blunting of "
            "costophrenic angles or layering on decubitus views. May be "
            "transudative (heart failure) or exudative (infection, malignancy)."
        ),
        "region": "Pleural Space",
        "urgency": "MODERATE",
        "severity": "MODERATE",
        "recommendation": (
            "Assess size and clinical context. Large or symptomatic effusions may "
            "require thoracentesis for both diagnostic (Light's criteria) and "
            "therapeutic purposes."
        ),
        "color": "#FF8C00",
    },
    "Pleural Other": {
        "short": "Pleural Abnormality",
        "description": (
            "Other pleural abnormality such as pleural thickening, calcification, "
            "or mass. May be related to prior infection, asbestos exposure, or "
            "mesothelioma."
        ),
        "region": "Pleural Space",
        "urgency": "LOW",
        "severity": "LOW",
        "recommendation": (
            "Correlate with occupational/exposure history. CT may help characterize "
            "the abnormality further. Follow-up imaging if new finding."
        ),
        "color": "#E3B341",
    },
    "Fracture": {
        "short": "Bone Fracture",
        "description": (
            "Bone fracture visible on chest X-ray, most commonly rib fractures. "
            "May also involve clavicle, scapula, or vertebral bodies. "
            "Evaluate for associated pneumothorax or hemothorax."
        ),
        "region": "Bony Thorax",
        "urgency": "MODERATE",
        "severity": "MODERATE",
        "recommendation": (
            "Assess for complications (pneumothorax, hemothorax). Pain management "
            "with incentive spirometry to prevent atelectasis. CT for complex "
            "or multiple fractures."
        ),
        "color": "#FF8C00",
    },
    "Support Devices": {
        "short": "Lines/Tubes/Devices",
        "description": (
            "Medical devices detected including endotracheal tubes, central venous "
            "catheters, chest tubes, pacemaker leads, nasogastric tubes, or "
            "other support hardware."
        ),
        "region": "Various",
        "urgency": "LOW",
        "severity": "INFORMATIONAL",
        "recommendation": (
            "Verify correct positioning of all devices. Check for complications "
            "such as malpositioned lines or pneumothorax post-insertion."
        ),
        "color": "#8B949E",
    },
}

URGENT_FLAGS = {"Pneumothorax", "Pneumonia", "Consolidation", "Edema"}

# =============================================================================
#  ANSI COLOR UTILITIES
# =============================================================================

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


# =============================================================================
#  MODEL
# =============================================================================

def load_model_and_config(checkpoint_path, metadata_path, device):
    with open(metadata_path) as f:
        metadata = json.load(f)

    labels = metadata["labels"]
    num_classes = metadata["num_classes"]
    img_size = metadata["preprocessing"]["img_size"]
    mean = metadata["normalization"]["mean"]
    std = metadata["normalization"]["std"]

    model = timm.create_model("densenet121", pretrained=False, num_classes=num_classes)
    state_dict = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.eval().to(device)

    transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])

    return model, transform, labels, img_size


# =============================================================================
#  GRAD-CAM HEATMAP
# =============================================================================

class GradCAM:
    """Grad-CAM for the last convolutional layer of DenseNet-121."""

    def __init__(self, model):
        self.model = model
        self.gradients = None
        self.activations = None
        self._hooks = []

        target_layer = model.features
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

    def generate(self, input_tensor, target_class, img_size):
        self.model.zero_grad()
        output = self.model(input_tensor)

        one_hot = torch.zeros_like(output)
        one_hot[0, target_class] = 1.0
        output.backward(gradient=one_hot, retain_graph=True)

        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1, keepdim=True)
        cam = F.relu(cam)
        cam = F.interpolate(cam, size=(img_size, img_size),
                            mode="bilinear", align_corners=False)
        cam = cam.squeeze().cpu().numpy()

        cam_min, cam_max = cam.min(), cam.max()
        if cam_max - cam_min > 1e-8:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = np.zeros_like(cam)

        return cam

    def remove_hooks(self):
        for h in self._hooks:
            h.remove()


# =============================================================================
#  INFERENCE
# =============================================================================

def predict_image(model, transform, labels, image_path, device, threshold, img_size):
    """Run multi-label inference with Grad-CAM on positive findings."""
    image_pil = Image.open(image_path).convert("RGB")
    tensor = transform(image_pil).unsqueeze(0).to(device)

    with torch.no_grad():
        with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
            logits = model(tensor)
        probs = torch.sigmoid(logits)[0].cpu().numpy()

    findings = []
    for i, label in enumerate(labels):
        prob = float(probs[i])
        positive = prob >= threshold
        info = FINDING_CLINICAL_INFO.get(label, {})
        findings.append({
            "label": label,
            "short": info.get("short", label),
            "probability": round(prob, 4),
            "positive": positive,
            "urgent": positive and label in URGENT_FLAGS,
            "urgency": info.get("urgency", "LOW") if positive else "NONE",
            "severity": info.get("severity", "LOW") if positive else "NORMAL",
            "region": info.get("region", "Unknown"),
        })

    findings.sort(key=lambda r: -r["probability"])

    positive_findings = [f for f in findings if f["positive"] and f["label"] != "No Finding"]
    heatmaps = {}
    if positive_findings:
        grad_cam = GradCAM(model)
        cam_input = tensor.requires_grad_(True)
        for pf in positive_findings[:4]:
            idx = labels.index(pf["label"])
            heatmap = grad_cam.generate(cam_input, idx, img_size)
            heatmaps[pf["label"]] = heatmap
        grad_cam.remove_hooks()

    n_positive = sum(1 for f in findings if f["positive"])
    n_urgent = sum(1 for f in findings if f["urgent"])
    has_no_finding = any(f["label"] == "No Finding" and f["positive"] for f in findings)

    severities = [f["severity"] for f in findings if f["positive"]]
    if "CRITICAL" in severities:
        overall_severity = "CRITICAL"
    elif "HIGH" in severities:
        overall_severity = "HIGH"
    elif "MODERATE" in severities:
        overall_severity = "MODERATE"
    elif n_positive == 0 or has_no_finding:
        overall_severity = "NORMAL"
    else:
        overall_severity = "LOW"

    result = {
        "image_path": image_path,
        "patient_id": os.path.splitext(os.path.basename(image_path))[0],
        "findings": findings,
        "n_positive": n_positive,
        "n_urgent": n_urgent,
        "overall_severity": overall_severity,
        "threshold": threshold,
        "timestamp": datetime.datetime.now().isoformat(),
        "_heatmaps": heatmaps,
        "_image_pil": image_pil,
        "_img_size": img_size,
    }
    return result


# =============================================================================
#  MATPLOTLIB CLINICAL DASHBOARD
# =============================================================================

def generate_clinical_figures(result, output_dir):
    """Generate a comprehensive radiology dashboard as PNG."""
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
    heatmaps = result.get("_heatmaps", {})
    img_size = result.get("_img_size", 320)
    if image_pil is None:
        return saved

    image_np = np.array(image_pil.resize((img_size, img_size)))
    findings = result["findings"]
    positive = [f for f in findings if f["positive"]]
    urgent = [f for f in findings if f["urgent"]]

    hm_labels = list(heatmaps.keys())[:3]
    n_hm = len(hm_labels)

    n_top_cols = 2 + n_hm
    fig = plt.figure(figsize=(max(22, 6 * n_top_cols), 16), facecolor="#0D1117")

    gs = gridspec.GridSpec(3, max(n_top_cols, 4),
                           height_ratios=[1.0, 0.1, 1.0],
                           hspace=0.25, wspace=0.3,
                           left=0.04, right=0.96, top=0.92, bottom=0.04)

    severity_colors = {
        "CRITICAL": "#DA3633", "HIGH": "#FF4444", "MODERATE": "#FF8C00",
        "LOW": "#E3B341", "NORMAL": "#238636", "INFORMATIONAL": "#8B949E",
    }
    sev = result["overall_severity"]
    sev_color = severity_colors.get(sev, "#8B949E")

    fig.suptitle("Chest X-Ray Analysis -- %s" % patient_id,
                 fontsize=24, fontweight="bold", color="white", y=0.97)

    # Row 0, Col 0: Original X-ray
    ax_orig = fig.add_subplot(gs[0, 0])
    ax_orig.imshow(image_np, cmap="gray" if len(image_np.shape) == 2 else None)
    ax_orig.set_title("Original Chest X-Ray", fontsize=13,
                      fontweight="bold", color="white", pad=10)
    ax_orig.axis("off")

    # Row 0, Col 1: Combined heatmap overlay
    ax_overlay = fig.add_subplot(gs[0, 1])
    ax_overlay.imshow(image_np, cmap="gray" if len(image_np.shape) == 2 else None)
    if heatmaps:
        combined = np.zeros((img_size, img_size), dtype=np.float32)
        for hm in heatmaps.values():
            combined = np.maximum(combined, hm)
        cam_cmap = LinearSegmentedColormap.from_list(
            "cam", [(0, 0, 0, 0), (1, 1, 0, 0.4), (1, 0, 0, 0.8)])
        ax_overlay.imshow(combined, cmap=cam_cmap, alpha=0.7)
        ax_overlay.set_title("Combined Attention Map\n(All Positive Findings)",
                             fontsize=13, fontweight="bold", color="white", pad=10)
    else:
        ax_overlay.set_title("Attention Map\n(No positive findings)",
                             fontsize=13, fontweight="bold", color="white", pad=10)
    ax_overlay.axis("off")

    # Row 0, Cols 2+: Individual finding heatmaps
    for i, label in enumerate(hm_labels):
        ax_hm = fig.add_subplot(gs[0, 2 + i])
        ax_hm.imshow(image_np, cmap="gray" if len(image_np.shape) == 2 else None)
        hm = heatmaps[label]
        cam_cmap = LinearSegmentedColormap.from_list(
            "cam", [(0, 0, 0, 0), (1, 1, 0, 0.4), (1, 0, 0, 0.8)])
        ax_hm.imshow(hm, cmap=cam_cmap, alpha=0.7)
        prob = next(f["probability"] for f in findings if f["label"] == label)
        info = FINDING_CLINICAL_INFO.get(label, {})
        fc = info.get("color", "#FF4444")
        ax_hm.set_title("%s\n(%.1f%%)" % (label, prob * 100),
                        fontsize=12, fontweight="bold", color=fc, pad=10)
        ax_hm.axis("off")

    # Row 1: Severity banner
    ax_banner = fig.add_subplot(gs[1, :])
    ax_banner.set_facecolor(sev_color + "33")
    ax_banner.set_xlim(0, 1)
    ax_banner.set_ylim(0, 1)
    ax_banner.axis("off")
    banner_text = "OVERALL SEVERITY: %s" % sev
    if urgent:
        urg_names = ", ".join(f["label"] for f in urgent)
        banner_text += "  |  !! %d URGENT FINDING(S): %s" % (len(urgent), urg_names)
    ax_banner.text(0.5, 0.5, banner_text, fontsize=16, fontweight="bold",
                   color=sev_color, ha="center", va="center",
                   transform=ax_banner.transAxes)
    border_b = FancyBboxPatch((0.005, 0.05), 0.99, 0.9, boxstyle="round,pad=0.01",
                              facecolor="none", edgecolor=sev_color, linewidth=2,
                              transform=ax_banner.transAxes)
    ax_banner.add_patch(border_b)

    # Row 2: Left half - Bar chart
    ax_bars = fig.add_subplot(gs[2, :2])
    ax_bars.set_facecolor("#0D1117")

    bar_labels = [f["label"] for f in findings]
    bar_values = [f["probability"] for f in findings]
    bar_colors = []
    for f in findings:
        info = FINDING_CLINICAL_INFO.get(f["label"], {})
        if f["positive"]:
            bar_colors.append(info.get("color", "#FF8C00"))
        else:
            bar_colors.append("#30363D")

    bars = ax_bars.barh(bar_labels, bar_values, color=bar_colors, height=0.6,
                        edgecolor="#0D1117", linewidth=2)

    ax_bars.axvline(x=result["threshold"], color="#DA3633", linestyle="--",
                    linewidth=1.5, alpha=0.7,
                    label="Threshold (%.0f%%)" % (result["threshold"] * 100))

    for bar, val, f in zip(bars, bar_values, findings):
        color = "white" if f["positive"] else "#8B949E"
        weight = "bold" if f["positive"] else "normal"
        suffix = " !!" if f["urgent"] else ""
        ax_bars.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                     "%.1f%%%s" % (val * 100, suffix), va="center", fontsize=10,
                     fontweight=weight, color=color)

    ax_bars.set_xlim(0, 1.15)
    ax_bars.set_title("Finding Probability Distribution",
                      fontsize=14, fontweight="bold", color="white", pad=12)
    ax_bars.invert_yaxis()
    ax_bars.tick_params(colors="white", labelsize=9)
    ax_bars.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: "%.0f%%" % (x * 100)))
    ax_bars.legend(loc="lower right", fontsize=10, facecolor="#161B22",
                   edgecolor="#30363D", labelcolor="white")
    for spine in ax_bars.spines.values():
        spine.set_color("#30363D")

    # Right half: Clinical summary card
    ax_card = fig.add_subplot(gs[2, 2:])
    ax_card.set_facecolor("#161B22")
    ax_card.set_xlim(0, 1)
    ax_card.set_ylim(0, 1)
    ax_card.axis("off")

    y_pos = 0.95
    ax_card.text(0.05, y_pos, "Clinical Summary", fontsize=16,
                 fontweight="bold", color="white", transform=ax_card.transAxes, va="top")
    y_pos -= 0.06

    ax_card.text(0.05, y_pos, "Severity: %s" % sev, fontsize=14,
                 fontweight="bold", color=sev_color,
                 transform=ax_card.transAxes, va="top")
    y_pos -= 0.05

    ax_card.text(0.05, y_pos,
                 "Positive Findings: %d / %d  |  Urgent: %d" % (len(positive), len(findings), len(urgent)),
                 fontsize=11, color="#C9D1D9", transform=ax_card.transAxes, va="top")
    y_pos -= 0.07

    if positive:
        ax_card.text(0.05, y_pos, "Active Findings:", fontsize=12,
                     fontweight="bold", color="#58A6FF",
                     transform=ax_card.transAxes, va="top")
        y_pos -= 0.05

        for f in positive[:6]:
            info = FINDING_CLINICAL_INFO.get(f["label"], {})
            fc = info.get("color", "#FF8C00")
            icon = "!!" if f["urgent"] else "*"
            ax_card.text(0.07, y_pos, "%s %s -- %.1f%%" % (icon, f["label"], f["probability"] * 100),
                         fontsize=10, fontweight="bold", color=fc,
                         transform=ax_card.transAxes, va="top")
            y_pos -= 0.035
            ax_card.text(0.10, y_pos, "Region: %s" % f["region"],
                         fontsize=9, color="#8B949E",
                         transform=ax_card.transAxes, va="top")
            y_pos -= 0.03
            rec = info.get("recommendation", "")
            if rec:
                wrapped = _wrap_for_figure(rec, 52)
                ax_card.text(0.10, y_pos, wrapped, fontsize=8,
                             color="#C9D1D9", transform=ax_card.transAxes, va="top",
                             family="monospace", linespacing=1.3)
                y_pos -= 0.03 * (wrapped.count('\n') + 1) + 0.02
    else:
        ax_card.text(0.05, y_pos, "[OK] No significant findings above threshold",
                     fontsize=12, color="#238636",
                     transform=ax_card.transAxes, va="top")
        y_pos -= 0.06

    border_card = FancyBboxPatch((0.01, 0.01), 0.98, 0.98,
                                 boxstyle="round,pad=0.02",
                                 facecolor="none", edgecolor=sev_color,
                                 linewidth=2, transform=ax_card.transAxes)
    ax_card.add_patch(border_card)

    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    path1 = os.path.join(output_dir, "%s_%s_xray_dashboard.png" % (patient_id, timestamp_str))
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


# =============================================================================
#  TERMINAL OUTPUT FORMATTING
# =============================================================================

def _wrap_text(text, width=62, indent="     "):
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


def _probability_gauge(prob, width=25):
    filled = int(round(prob * width))
    empty = width - filled
    if prob >= 0.7:
        color = C.RED
    elif prob >= 0.5:
        color = C.YELLOW
    elif prob >= 0.3:
        color = C.CYAN
    else:
        color = C.GREEN
    return "%s%s%s%s%s" % (color, "#" * filled, C.GRAY, "-" * empty, C.RESET)


def _severity_badge(severity):
    colors = {"CRITICAL": C.RED, "HIGH": C.RED, "MODERATE": C.YELLOW,
              "LOW": C.CYAN, "NORMAL": C.GREEN, "INFORMATIONAL": C.GRAY}
    color = colors.get(severity, C.GRAY)
    icons = {"CRITICAL": "[!!]", "HIGH": "[!]", "MODERATE": "[~]",
             "LOW": "[i]", "NORMAL": "[OK]", "INFORMATIONAL": "[i]"}
    icon = icons.get(severity, "[?]")
    return "%s  %s%s%s%s" % (icon, color, C.BOLD, severity, C.RESET)


def print_model_banner(args, device, n_files, labels):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("  %s%s%s%s" % (C.CYAN, C.BOLD, "=" * 68, C.RESET))
    print("  %s  CHEST X-RAY ANALYSIS -- CLINICAL REPORT%s" % (C.BOLD, C.RESET))
    print("  %s%s%s%s" % (C.CYAN, C.BOLD, "=" * 68, C.RESET))
    print()
    print("  %s  Model       %s DenseNet-121 (CheXpert, %d multi-label)" % (C.DIM, C.RESET, len(labels)))
    print("  %s  Dataset     %s CheXpert v1.0 (Stanford ML Group)" % (C.DIM, C.RESET))
    print("  %s  Mode        %s Multi-label (sigmoid -- multiple findings per image)" % (C.DIM, C.RESET))
    print("  %s  Findings    %s %d pathologies + support devices" % (C.DIM, C.RESET, len(labels)))
    print("  %s  Threshold   %s %.0f%% minimum probability" % (C.DIM, C.RESET, args.threshold * 100))
    print("  %s  Device      %s %s" % (C.DIM, C.RESET, device))
    print("  %s  Timestamp   %s %s" % (C.DIM, C.RESET, now))
    print("  %s  Images      %s %d file(s) queued for analysis" % (C.DIM, C.RESET, n_files))
    print()
    print("  %s%s%s" % (C.CYAN, "-" * 68, C.RESET))
    print()


def print_result_detailed(result):
    findings = result["findings"]
    positive = [f for f in findings if f["positive"]]
    urgent = [f for f in findings if f["urgent"]]
    sev = result["overall_severity"]

    # Patient header
    print("  %sIMAGE: %s%s%s" % (C.BOLD, C.CYAN, result["patient_id"], C.RESET))
    print("  %s   File: %s%s" % (C.DIM, result["image_path"], C.RESET))
    print()

    # Overall severity
    print("  %sOVERALL ASSESSMENT%s" % (C.BOLD, C.RESET))
    print("     Severity:  %s" % _severity_badge(sev))
    print("     Findings:  %s%d%s positive / %d evaluated" % (C.BOLD, len(positive), C.RESET, len(findings)))
    if urgent:
        urg_names = ", ".join(f["label"] for f in urgent)
        print("     %s%s!! URGENT: %s%s" % (C.RED, C.BOLD, urg_names, C.RESET))
    print()

    # Urgent findings first
    if urgent:
        print("  %s%s%s%s" % (C.RED, C.BOLD, "=" * 60, C.RESET))
        print("  %s%s  !!  URGENT FINDINGS -- IMMEDIATE CLINICAL REVIEW%s" % (C.RED, C.BOLD, C.RESET))
        print("  %s%s%s%s" % (C.RED, C.BOLD, "=" * 60, C.RESET))
        print()
        for f in urgent:
            info = FINDING_CLINICAL_INFO.get(f["label"], {})
            print("     %s%s!! %s%s  (%.1f%%)  Region: %s%s%s" % (
                C.RED, C.BOLD, f["label"], C.RESET,
                f["probability"] * 100, C.CYAN, f["region"], C.RESET))
            if info.get("description"):
                for line in _wrap_text(info["description"], width=58, indent="       "):
                    print("  %s%s%s" % (C.DIM, line, C.RESET))
            if info.get("recommendation"):
                for line in _wrap_text(info["recommendation"], width=58, indent="       "):
                    print("  %s%s%s" % (C.RED, line, C.RESET))
            print()

    # Non-urgent positive findings
    non_urgent_positive = [f for f in positive if not f["urgent"]]
    if non_urgent_positive:
        print("  %sPOSITIVE FINDINGS%s" % (C.BOLD, C.RESET))
        print()
        for f in non_urgent_positive:
            info = FINDING_CLINICAL_INFO.get(f["label"], {})
            urg_color = C.YELLOW if f["urgency"] in ("MODERATE", "HIGH") else C.GREEN
            print("     %s* %s%s  (%.1f%%)  Region: %s%s%s" % (
                urg_color, f["label"], C.RESET,
                f["probability"] * 100, C.CYAN, f["region"], C.RESET))
            if info.get("description"):
                for line in _wrap_text(info["description"], width=58, indent="       "):
                    print("  %s%s%s" % (C.DIM, line, C.RESET))
            if info.get("recommendation"):
                for line in _wrap_text(info["recommendation"], width=58, indent="       "):
                    print("  %s%s%s" % (urg_color, line, C.RESET))
            print()

    if not positive:
        print("  %s%s  [OK] No significant findings above threshold (%.0f%%)%s" % (
            C.GREEN, C.BOLD, result["threshold"] * 100, C.RESET))
        print()

    # Full probability breakdown
    print("  %sALL FINDING PROBABILITIES%s" % (C.BOLD, C.RESET))
    for f in findings:
        is_pos = f["positive"]
        is_urg = f["urgent"]
        if is_urg:
            tag = "%s[URG]%s" % (C.RED, C.RESET)
            color = C.RED
        elif is_pos:
            tag = "%s[POS]%s" % (C.YELLOW, C.RESET)
            color = C.YELLOW
        else:
            tag = "%s[---]%s" % (C.GRAY, C.RESET)
            color = C.GRAY

        gauge = _probability_gauge(f["probability"])
        name = f["label"]
        prob_str = "%.1f%%" % (f["probability"] * 100)
        region = f["region"]

        print("     %s %-28s  [%s]  %s%s%6s%s  %s%s%s" % (
            tag, name, gauge, color, C.BOLD, prob_str, C.RESET, C.DIM, region, C.RESET))
    print()

    print("  %s%s%s" % (C.CYAN, "-" * 68, C.RESET))
    print()


def print_batch_summary(results):
    if len(results) <= 1:
        return

    print()
    print("  %s%s%s%s" % (C.BOLD, C.CYAN, "=" * 68, C.RESET))
    print("  %sBATCH SUMMARY (%d images)%s" % (C.BOLD, len(results), C.RESET))
    print("  %s%s%s%s" % (C.BOLD, C.CYAN, "=" * 68, C.RESET))
    print()

    col_w = [20, 10, 10, 10, 20]
    header_line = "  | %-*s | %-*s | %-*s | %-*s | %-*s |" % (
        col_w[0], "Image", col_w[1], "Severity", col_w[2], "Findings",
        col_w[3], "Urgent", col_w[4], "Top Finding")
    sep_line = "  +" + "+".join("-" * (w + 2) for w in col_w) + "+"

    print("%s%s%s" % (C.DIM, sep_line, C.RESET))
    print("  %s%s%s" % (C.BOLD, header_line, C.RESET))
    print("%s%s%s" % (C.DIM, sep_line, C.RESET))

    for r in results:
        sev = r["overall_severity"]
        sev_colors = {"CRITICAL": C.RED, "HIGH": C.RED, "MODERATE": C.YELLOW,
                      "LOW": C.GREEN, "NORMAL": C.GREEN}
        sc = sev_colors.get(sev, C.GRAY)

        patient = r["patient_id"][:col_w[0]]
        n_pos = r["n_positive"]
        n_urg = r["n_urgent"]

        top = next((f for f in r["findings"] if f["positive"] and f["label"] != "No Finding"), None)
        top_name = top["label"][:col_w[4]] if top else "Normal"

        print("  | %-*s | %s%-*s%s | %-*d | %s%-*d%s | %-*s |" % (
            col_w[0], patient,
            sc, col_w[1], sev, C.RESET,
            col_w[2], n_pos,
            C.RED if n_urg else C.GREEN, col_w[3], n_urg, C.RESET,
            col_w[4], top_name))

    print("%s%s%s" % (C.DIM, sep_line, C.RESET))

    print()
    print("  %sSummary:%s  %d images analyzed" % (C.BOLD, C.RESET, len(results)))

    urgent_cases = [r for r in results if r["n_urgent"] > 0]
    if urgent_cases:
        print("  %s%s!! %d case(s) with urgent findings:%s" % (C.RED, C.BOLD, len(urgent_cases), C.RESET))
        for r in urgent_cases:
            urg = [f for f in r["findings"] if f["urgent"]]
            urg_names = ", ".join(f["label"] for f in urg)
            print("     %s* %s  --  %s%s" % (C.RED, r["patient_id"], urg_names, C.RESET))

    normal_cases = [r for r in results if r["overall_severity"] == "NORMAL"]
    print("  %s%d normal%s  |  %s%d moderate%s  |  %s%d urgent%s" % (
        C.GREEN, len(normal_cases), C.RESET,
        C.YELLOW, len(results) - len(normal_cases) - len(urgent_cases), C.RESET,
        C.RED, len(urgent_cases), C.RESET))
    print()


# =============================================================================
#  JSON REPORT EXPORT
# =============================================================================

def export_json_report(results, args, device, labels, report_path):
    report = {
        "report_type": "Chest X-Ray Multi-Label Classification",
        "generated_at": datetime.datetime.now().isoformat(),
        "model": {
            "architecture": "DenseNet-121",
            "dataset": "CheXpert v1.0",
            "checkpoint": args.model,
            "num_classes": len(labels),
            "labels": labels,
            "mode": "multi-label (sigmoid)",
            "threshold": args.threshold,
            "device": str(device),
        },
        "results": [],
        "summary": {
            "total_images": len(results),
            "urgent_cases": sum(1 for r in results if r["n_urgent"] > 0),
            "normal_cases": sum(1 for r in results if r["overall_severity"] == "NORMAL"),
        },
        "disclaimer": (
            "This is an AI-assisted screening tool trained on the CheXpert dataset. "
            "All findings are probabilistic and must be confirmed by a qualified "
            "radiologist. Not a substitute for professional medical diagnosis."
        ),
    }

    for r in results:
        entry = {
            "patient_id": r["patient_id"],
            "file": r["image_path"],
            "overall_severity": r["overall_severity"],
            "n_positive": r["n_positive"],
            "n_urgent": r["n_urgent"],
            "findings": [],
            "timestamp": r["timestamp"],
        }
        for f in r["findings"]:
            entry["findings"].append({
                "label": f["label"],
                "probability": f["probability"],
                "positive": f["positive"],
                "urgent": f["urgent"],
                "urgency": f["urgency"],
                "severity": f["severity"],
                "region": f["region"],
            })
        report["results"].append(entry)

    with open(report_path, "w") as fp:
        json.dump(report, fp, indent=2)
    return report_path


# =============================================================================
#  QUIET MODE
# =============================================================================

def print_quiet(result):
    entry = {
        "patient_id": result["patient_id"],
        "overall_severity": result["overall_severity"],
        "n_positive": result["n_positive"],
        "n_urgent": result["n_urgent"],
        "findings": [
            {"label": f["label"], "probability": f["probability"],
             "positive": f["positive"], "urgent": f["urgent"]}
            for f in result["findings"]
        ],
    }
    print(json.dumps(entry))


# =============================================================================
#  MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Chest X-Ray Analysis -- Clinical Inference Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python running.py\n"
            "  python running.py --image test.png\n"
            "  python running.py --image_dir test_images/ --report results.json\n"
            "  python running.py --image test.png --quiet\n"
        ),
    )
    parser.add_argument("--image", type=str, default=None,
                         help="Path to chest X-ray image")
    parser.add_argument("--image_dir", type=str, default=None,
                         help="Folder of images for batch analysis")
    parser.add_argument("--model", type=str,
                         default="checkpoints/densenet121_chexpert_best.pth")
    parser.add_argument("--metadata", type=str,
                         default="processed_chexpert/metadata.json")
    parser.add_argument("--threshold", type=float, default=0.5,
                         help="Probability threshold for positive finding (default: 0.5)")
    parser.add_argument("--report", type=str, default=None,
                         help="Export JSON report to this path")
    parser.add_argument("--output_dir", type=str, default="results",
                         help="Directory for generated figures (default: results/)")
    parser.add_argument("--no-figures", action="store_true",
                         help="Skip generating matplotlib figures")
    parser.add_argument("--quiet", action="store_true",
                         help="Machine-readable JSON-lines output only")
    args = parser.parse_args()

    # Resolve paths relative to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for attr in ("image", "model", "metadata", "output_dir"):
        val = getattr(args, attr)
        if val and not os.path.isabs(val):
            setattr(args, attr, os.path.join(script_dir, val))

    if args.quiet or not sys.stdout.isatty():
        C.disable()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load model & config
    model, transform, labels, img_size = load_model_and_config(
        args.model, args.metadata, device)

    # Collect images
    image_paths = []
    if args.image_dir:
        img_dir = args.image_dir if os.path.isabs(args.image_dir) else os.path.join(script_dir, args.image_dir)
        for fname in sorted(os.listdir(img_dir)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
                image_paths.append(os.path.join(img_dir, fname))
    elif args.image:
        image_paths.append(args.image)
    else:
        input_dir = os.path.join(script_dir, "input")
        if os.path.exists(input_dir) and os.path.isdir(input_dir):
            valid_files = []
            for fname in sorted(os.listdir(input_dir)):
                if fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
                    valid_files.append(os.path.join(input_dir, fname))
            
            if not valid_files:
                print("No image files found in 'input' directory.", file=sys.stderr)
                sys.exit(1)
            elif len(valid_files) == 1:
                image_paths.append(valid_files[0])
            else:
                print(f"\n  {C.CYAN}{C.BOLD}=== IMAGE SELECTION ==={C.RESET}")
                print(f"  {C.DIM}Multiple images found in 'input' directory. Please select one:{C.RESET}\n")
                for i, f in enumerate(valid_files):
                    print(f"    {C.YELLOW}[{i+1}]{C.RESET} {C.BOLD}{os.path.basename(f)}{C.RESET}")
                print(f"    {C.GREEN}[A]{C.RESET} {C.BOLD}All images (Batch Mode){C.RESET}\n")
                
                while True:
                    try:
                        choice = input(f"  {C.CYAN}Enter your choice (1-{len(valid_files)} or A): {C.RESET}").strip().upper()
                        if choice == 'A':
                            image_paths = valid_files
                            break
                        elif choice.isdigit() and 1 <= int(choice) <= len(valid_files):
                            image_paths.append(valid_files[int(choice)-1])
                            break
                        else:
                            print(f"  {C.RED}Invalid choice. Please try again.{C.RESET}")
                    except (EOFError, KeyboardInterrupt):
                        print("\nExiting.")
                        sys.exit(0)
        else:
            print("No input specified and 'input' directory not found.", file=sys.stderr)
            sys.exit(1)

    if not image_paths:
        print("No image files found.", file=sys.stderr)
        sys.exit(1)

    # Banner
    if not args.quiet:
        print_model_banner(args, device, len(image_paths), labels)

    # Run inference
    all_results = []
    for img_path in image_paths:
        try:
            if not os.path.exists(img_path):
                raise FileNotFoundError("Image not found: %s" % img_path)

            result = predict_image(model, transform, labels, img_path,
                                   device, args.threshold, img_size)
            all_results.append(result)

            if args.quiet:
                print_quiet(result)
            else:
                print_result_detailed(result)

                # Generate figures
                if not getattr(args, 'no_figures', False):
                    saved_figs = generate_clinical_figures(result, args.output_dir)
                    for fig_path in saved_figs:
                        print("  %s[*] Figure saved:%s %s" % (C.GREEN, C.RESET, fig_path))
                    print()

        except Exception as e:
            if args.quiet:
                print(json.dumps({"file": img_path, "error": str(e)}), file=sys.stderr)
            else:
                print("  %s%s[X] ERROR%s processing %s: %s" % (C.RED, C.BOLD, C.RESET, img_path, e))
                import traceback
                traceback.print_exc()
                print()

    # Clean up internal data
    for r in all_results:
        r.pop("_heatmaps", None)
        r.pop("_image_pil", None)
        r.pop("_img_size", None)

    # Batch summary
    if not args.quiet:
        print_batch_summary(all_results)

    # JSON report
    if args.report and all_results:
        path = export_json_report(all_results, args, device, labels, args.report)
        if not args.quiet:
            print("  %s%s[*] Report exported:%s %s" % (C.GREEN, C.BOLD, C.RESET, path))
            print()


if __name__ == "__main__":
    main()
