

import os
import sys
import json
import re
import argparse
import datetime
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models.video as models

# ── Force UTF-8 on Windows to support box-drawing chars and emoji ────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

EXPECTED_CHANNELS = 4
DEFAULT_TARGET_SIZE = 128

# BraTS mask label values
MASK_LABELS = {"NCR_NET": 1, "ED": 2, "ET": 4}


# ═══════════════════════════════════════════════════════════════════════════════
#  CLINICAL LABEL METADATA
# ═══════════════════════════════════════════════════════════════════════════════

LABEL_CLINICAL_INFO = {
    "has_tumor": {
        "short": "Tumor Presence",
        "clinical": "Overall Tumor Presence (Whole Tumor — WT)",
        "description": (
            "Detects any tumor tissue in the MRI volume, including necrotic core, "
            "edema, and enhancing regions. A positive result indicates the presence "
            "of glioma-related abnormalities."
        ),
        "who_region": "Whole Tumor (WT)",
    },
    "has_NCR_NET": {
        "short": "Necrotic / Non-Enhancing Core",
        "clinical": "Necrotic & Non-Enhancing Tumor Core (NCR/NET)",
        "description": (
            "Identifies the necrotic and non-enhancing tumor core — tissue that has "
            "undergone cell death or lacks active contrast enhancement. Often found "
            "in the center of high-grade gliomas (GBM)."
        ),
        "who_region": "Tumor Core (TC) component",
    },
    "has_ED": {
        "short": "Peritumoral Edema",
        "clinical": "Peritumoral Edema (ED)",
        "description": (
            "Detects peritumoral edema — swelling around the tumor caused by fluid "
            "leakage from disrupted vasculature. Visible as hyperintensity on T2/FLAIR. "
            "Extent of edema can indicate tumor aggressiveness."
        ),
        "who_region": "Whole Tumor (WT) component",
    },
    "has_ET": {
        "short": "Enhancing Tumor",
        "clinical": "Enhancing Tumor (ET) — Active Growth",
        "description": (
            "Identifies actively enhancing tumor tissue — regions with contrast "
            "enhancement indicating active tumor growth and blood-brain barrier "
            "breakdown. Key marker for high-grade glioma (WHO Grade IV)."
        ),
        "who_region": "Enhancing Tumor (ET)",
    },
}

# Sub-type display info for the tumor location analysis
TUMOR_SUBTYPES = {
    1: {"name": "Necrotic / Non-Enhancing Core (NCR/NET)", "short": "NCR/NET", "color": "#FFD700"},
    2: {"name": "Peritumoral Edema (ED)",                  "short": "ED",      "color": "#00BFFF"},
    4: {"name": "Enhancing Tumor (ET)",                    "short": "ET",      "color": "#FF4444"},
}


# ═══════════════════════════════════════════════════════════════════════════════
#  ANSI COLOR UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

class _Colors:
    """ANSI escape codes for terminal colorization."""

    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"

    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"

    BG_RED    = "\033[41m"
    BG_GREEN  = "\033[42m"
    BG_YELLOW = "\033[43m"

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
#  MODEL BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def build_model(checkpoint_path, num_classes, device):
    """Reconstruct the exact adapted architecture from finetune.py, then
    load the trained weights from the checkpoint dict."""
    model = models.r3d_18(weights=None)
    model.stem[0] = nn.Conv3d(4, 64, kernel_size=(7, 7, 7), stride=(2, 2, 2),
                               padding=(3, 3, 3), bias=False)
    model.fc = nn.Linear(model.fc.in_features, num_classes)

    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    state_dict = ckpt["model_state"] if "model_state" in ckpt else ckpt
    model.load_state_dict(state_dict, strict=True)

    model.eval().to(device)
    return model, ckpt


# ═══════════════════════════════════════════════════════════════════════════════
#  PREPROCESSING (exact match to training pipeline)
# ═══════════════════════════════════════════════════════════════════════════════

def resize_volume(volume_np, target_size, device):
    """Same trilinear resize used in preprocessing. volume_np: (4, X, Y, Z)."""
    t = torch.from_numpy(volume_np.astype(np.float32)).unsqueeze(0).to(device)
    with torch.no_grad():
        out = F.interpolate(t, size=(target_size,) * 3, mode="trilinear", align_corners=False)
    return out.squeeze(0).cpu()


def normalize_channels(image, channel_mean, channel_std):
    mean = torch.tensor(channel_mean, dtype=torch.float32).view(-1, 1, 1, 1)
    std = torch.tensor(channel_std, dtype=torch.float32).view(-1, 1, 1, 1)
    return (image - mean) / (std + 1e-8)


def load_channel_stats(data_dir):
    stats_path = os.path.join(data_dir, "channel_stats.json")
    if not os.path.exists(stats_path):
        raise FileNotFoundError(
            f"channel_stats.json not found at {stats_path} — this is required, "
            f"the model was trained on channel-normalized inputs and will give "
            f"meaningless results without it."
        )
    with open(stats_path) as f:
        stats = json.load(f)
    return stats["mean"], stats["std"]


# ═══════════════════════════════════════════════════════════════════════════════
#  TUMOR LOCATION ANALYSIS (from mask)
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_tumor_location(mask):
    """Analyze the segmentation mask to extract tumor location, size, and
    sub-type composition. Returns None if no mask or no tumor present.

    mask: numpy array of shape (D, H, W) with values {0, 1, 2, 4}
    """
    if mask is None:
        return None

    tumor_mask = mask > 0
    total_voxels = mask.size
    tumor_voxels = int(np.sum(tumor_mask))

    if tumor_voxels == 0:
        return {"has_tumor": False, "tumor_volume_fraction": 0.0}

    # Center of mass (in voxel coordinates)
    coords = np.where(tumor_mask)
    center_d = float(np.mean(coords[0]))
    center_h = float(np.mean(coords[1]))
    center_w = float(np.mean(coords[2]))

    # Bounding box
    bbox = {
        "depth": [int(np.min(coords[0])), int(np.max(coords[0]))],
        "height": [int(np.min(coords[1])), int(np.max(coords[1]))],
        "width": [int(np.min(coords[2])), int(np.max(coords[2]))],
    }

    # Volume dimensions for relative positioning
    D, H, W = mask.shape

    # Approximate anatomical location (based on relative position in volume)
    rel_d = center_d / D  # 0=inferior, 1=superior
    rel_h = center_h / H  # 0=anterior, 1=posterior
    rel_w = center_w / W  # 0=right, 1=left (radiological convention)

    # Hemispheric laterality
    if rel_w < 0.40:
        laterality = "Right hemisphere"
    elif rel_w > 0.60:
        laterality = "Left hemisphere"
    else:
        laterality = "Midline / bilateral"

    # Approximate axial position
    if rel_d < 0.33:
        axial_pos = "Inferior"
    elif rel_d > 0.66:
        axial_pos = "Superior"
    else:
        axial_pos = "Central"

    # Sub-type breakdown
    subtypes = {}
    for val, info in TUMOR_SUBTYPES.items():
        count = int(np.sum(mask == val))
        subtypes[info["short"]] = {
            "name": info["name"],
            "voxel_count": count,
            "fraction_of_tumor": round(count / tumor_voxels, 4) if tumor_voxels > 0 else 0,
            "fraction_of_volume": round(count / total_voxels, 6),
        }

    # Size in bounding box dimensions
    bbox_size = {
        "depth_span": bbox["depth"][1] - bbox["depth"][0] + 1,
        "height_span": bbox["height"][1] - bbox["height"][0] + 1,
        "width_span": bbox["width"][1] - bbox["width"][0] + 1,
    }

    return {
        "has_tumor": True,
        "tumor_voxel_count": tumor_voxels,
        "tumor_volume_fraction": round(tumor_voxels / total_voxels, 4),
        "center_of_mass_voxel": {"D": round(center_d), "H": round(center_h), "W": round(center_w)},
        "center_of_mass_relative": {"D": round(rel_d, 3), "H": round(rel_h, 3), "W": round(rel_w, 3)},
        "bounding_box": bbox,
        "bounding_box_size": bbox_size,
        "laterality": laterality,
        "axial_position": axial_pos,
        "anatomical_summary": f"{axial_pos} {laterality.lower()}",
        "subtypes": subtypes,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  RESULT FOLDER & FILE UTILITIES (Prevent Overwrite)
# ═══════════════════════════════════════════════════════════════════════════════

def get_non_conflicting_path(file_path):
    """If file_path already exists, return a non-conflicting path with _1, _2, etc."""
    if not os.path.exists(file_path):
        return file_path
    base, ext = os.path.splitext(file_path)
    counter = 1
    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def get_patient_output_dir(base_results_dir, patient_id):
    """Creates and returns a separate folder for this patient/scan inside base_results_dir.
    If the folder already exists and contains files, creates patient_id_1, patient_id_2, etc.
    so previous results are never overwritten."""
    os.makedirs(base_results_dir, exist_ok=True)
    target_folder = os.path.join(base_results_dir, patient_id)

    if not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)
        return target_folder

    # If the folder already exists and has files, create a new separate run folder
    if len(os.listdir(target_folder)) > 0:
        counter = 1
        while True:
            candidate = os.path.join(base_results_dir, f"{patient_id}_{counter}")
            if not os.path.exists(candidate) or len(os.listdir(candidate)) == 0:
                os.makedirs(candidate, exist_ok=True)
                return candidate
            counter += 1

    return target_folder


def _save_patient_json(result, json_path, label_col):
    """Save structured JSON clinical report for a single patient."""
    level, _, _ = _risk_level(result["confidence"])
    info = LABEL_CLINICAL_INFO.get(label_col, {})
    entry = {
        "patient_id": result["patient_id"],
        "file": result.get("npz_path", ""),
        "timestamp": result.get("timestamp", datetime.datetime.now().isoformat()),
        "classification_task": {
            "label_column": label_col,
            "clinical_name": info.get("clinical", label_col),
            "description": info.get("description", ""),
        },
        "prediction": {
            "label": result["predicted_label"],
            "class": result["predicted_class"],
            "confidence": result["confidence"],
            "risk_level": level,
            "prob_negative": result["prob_negative"],
            "prob_positive": result["prob_positive"],
        },
        "original_volume_shape": result.get("original_shape"),
        "tumor_location": result.get("tumor_location"),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
#  MATPLOTLIB VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_clinical_figures(image, mask, result, tumor_info, label_col, output_dir):
    """Generate matplotlib clinical figures and save as PNG.
    Returns list of saved file paths."""
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import FancyBboxPatch
    import matplotlib.gridspec as gridspec

    os.makedirs(output_dir, exist_ok=True)
    saved = []

    patient_id = result["patient_id"]

    # ══════════════════════════════════════════════════════════════════════════
    #  FIGURE 1: MRI Slices with Tumor Overlay (3-panel: Axial, Coronal, Sagittal)
    # ══════════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(20, 14), facecolor="#0D1117")
    gs = gridspec.GridSpec(2, 3, height_ratios=[1.2, 0.8], hspace=0.35, wspace=0.25,
                           left=0.05, right=0.95, top=0.92, bottom=0.05)

    # Title
    fig.suptitle(f"MRI Tumor Analysis — {patient_id}",
                 fontsize=22, fontweight="bold", color="white", y=0.97)

    # Use T1ce (channel 1) as the base MRI image — best contrast for tumors
    mri = image[1]  # T1ce modality
    D, H, W = mri.shape

    # Determine slice positions (at tumor center if available, else middle)
    if tumor_info and tumor_info["has_tumor"]:
        com = tumor_info["center_of_mass_voxel"]
        slice_d = int(com["D"])
        slice_h = int(com["H"])
        slice_w = int(com["W"])
    else:
        slice_d, slice_h, slice_w = D // 2, H // 2, W // 2

    # Tumor overlay colormap: 0=transparent, 1=gold(NCR/NET), 2=cyan(ED), 4=red(ET)
    tumor_cmap_colors = [(0, 0, 0, 0)]  # 0 = transparent
    tumor_cmap_colors.append((1.0, 0.84, 0.0, 0.6))   # 1 = NCR/NET (gold)
    tumor_cmap_colors.append((0.0, 0.75, 1.0, 0.6))    # 2 = ED (cyan)
    tumor_cmap_colors.append((0, 0, 0, 0))              # 3 = unused
    tumor_cmap_colors.append((1.0, 0.27, 0.27, 0.7))   # 4 = ET (red)
    tumor_cmap = ListedColormap(tumor_cmap_colors)

    views = [
        ("Axial", mri[slice_d, :, :], mask[slice_d, :, :] if mask is not None else None,
         f"Slice {slice_d}/{D}", "H", "W"),
        ("Coronal", mri[:, slice_h, :], mask[:, slice_h, :] if mask is not None else None,
         f"Slice {slice_h}/{H}", "D", "W"),
        ("Sagittal", mri[:, :, slice_w], mask[:, :, slice_w] if mask is not None else None,
         f"Slice {slice_w}/{W}", "D", "H"),
    ]

    for i, (title, mri_slice, mask_slice, slice_label, ylabel, xlabel) in enumerate(views):
        ax = fig.add_subplot(gs[0, i])
        ax.set_facecolor("#0D1117")

        # MRI base
        ax.imshow(mri_slice.T if i == 0 else mri_slice, cmap="gray",
                  aspect="equal", origin="lower")

        # Tumor overlay
        if mask_slice is not None and np.any(mask_slice > 0):
            overlay = mask_slice.copy().astype(float)
            ax.imshow(overlay.T if i == 0 else overlay, cmap=tumor_cmap,
                      vmin=0, vmax=4, aspect="equal", origin="lower", alpha=0.7)

        ax.set_title(f"{title} View\n{slice_label}", fontsize=14,
                     fontweight="bold", color="white", pad=10)
        ax.set_xlabel(xlabel, fontsize=10, color="#8B949E")
        ax.set_ylabel(ylabel, fontsize=10, color="#8B949E")
        ax.tick_params(colors="#8B949E", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#30363D")

    # ── Bottom left: Tumor composition pie chart ──
    ax_pie = fig.add_subplot(gs[1, 0])
    ax_pie.set_facecolor("#0D1117")

    if tumor_info and tumor_info["has_tumor"]:
        st = tumor_info["subtypes"]
        pie_labels, pie_sizes, pie_colors = [], [], []
        for key, info_sub in [("NCR/NET", TUMOR_SUBTYPES[1]),
                               ("ED", TUMOR_SUBTYPES[2]),
                               ("ET", TUMOR_SUBTYPES[4])]:
            if st[key]["voxel_count"] > 0:
                pie_labels.append(f"{key}\n({st[key]['fraction_of_tumor']:.0%})")
                pie_sizes.append(st[key]["voxel_count"])
                pie_colors.append(info_sub["color"])

        if pie_sizes:
            wedges, texts = ax_pie.pie(
                pie_sizes, labels=pie_labels, colors=pie_colors,
                startangle=90, textprops={"color": "white", "fontsize": 11, "fontweight": "bold"},
                wedgeprops={"edgecolor": "#0D1117", "linewidth": 2},
            )
            ax_pie.set_title("Tumor Composition", fontsize=14,
                             fontweight="bold", color="white", pad=12)
    else:
        ax_pie.text(0.5, 0.5, "No tumor\ndetected", transform=ax_pie.transAxes,
                    ha="center", va="center", fontsize=16, color="#8B949E")
        ax_pie.set_title("Tumor Composition", fontsize=14,
                         fontweight="bold", color="white", pad=12)

    # ── Bottom center: Confidence gauge ──
    ax_gauge = fig.add_subplot(gs[1, 1])
    ax_gauge.set_facecolor("#0D1117")

    conf = result["confidence"]
    prob_neg = result["prob_negative"]
    prob_pos = result["prob_positive"]

    # Horizontal bar chart for probabilities
    bar_labels = ["Negative", "Positive"]
    bar_values = [prob_neg, prob_pos]
    bar_colors = ["#238636", "#DA3633"] if result["predicted_label"] == "POSITIVE" else ["#DA3633", "#238636"]
    bar_colors = ["#3D8BFD", "#DA3633"]  # Blue for negative, Red for positive

    bars = ax_gauge.barh(bar_labels, bar_values, color=bar_colors, height=0.5,
                         edgecolor="#0D1117", linewidth=2)

    # Add percentage text on bars
    for bar, val in zip(bars, bar_values):
        ax_gauge.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2,
                      f"{val:.1%}", va="center", fontsize=14, fontweight="bold",
                      color="white")

    ax_gauge.set_xlim(0, 1.15)
    ax_gauge.set_title("Prediction Probability", fontsize=14,
                       fontweight="bold", color="white", pad=12)
    ax_gauge.tick_params(colors="white", labelsize=12)
    ax_gauge.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    for spine in ax_gauge.spines.values():
        spine.set_color("#30363D")

    # ── Bottom right: Clinical summary card ──
    ax_card = fig.add_subplot(gs[1, 2])
    ax_card.set_facecolor("#161B22")
    ax_card.set_xlim(0, 1)
    ax_card.set_ylim(0, 1)
    ax_card.axis("off")

    # Risk color
    if conf >= 0.90:
        risk_color, risk_text = "#238636", "HIGH CONFIDENCE"
    elif conf >= 0.70:
        risk_color, risk_text = "#D29922", "MODERATE CONFIDENCE"
    else:
        risk_color, risk_text = "#DA3633", "LOW CONFIDENCE"

    pred_text = result["predicted_label"]
    info = LABEL_CLINICAL_INFO.get(label_col, {})
    task_name = info.get("short", label_col)

    # Card content
    card_lines = [
        (0.88, f"Clinical Summary", "white", 16, "bold"),
        (0.78, f"Task: {task_name}", "#8B949E", 12, "normal"),
        (0.66, f"Prediction: {pred_text}", "#DA3633" if pred_text == "POSITIVE" else "#238636", 15, "bold"),
        (0.55, f"Confidence: {conf:.1%}", risk_color, 15, "bold"),
        (0.44, f"Risk: {risk_text}", risk_color, 13, "bold"),
    ]

    if tumor_info and tumor_info["has_tumor"]:
        card_lines.append((0.32, f"Location: {tumor_info['anatomical_summary']}", "#C9D1D9", 11, "normal"))
        card_lines.append((0.22, f"Laterality: {tumor_info['laterality']}", "#C9D1D9", 11, "normal"))
        vol_pct = tumor_info["tumor_volume_fraction"] * 100
        card_lines.append((0.12, f"Tumor Volume: {vol_pct:.2f}% of brain", "#C9D1D9", 11, "normal"))

    for y, text, color, size, weight in card_lines:
        ax_card.text(0.08, y, text, fontsize=size, fontweight=weight,
                     color=color, transform=ax_card.transAxes)

    # Card border
    border = FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0.02",
                            facecolor="none", edgecolor=risk_color, linewidth=2,
                            transform=ax_card.transAxes)
    ax_card.add_patch(border)

    # ── Legend for tumor overlay colors ──
    legend_elements = [
        plt.Line2D([0], [0], marker='s', color="#0D1117", markerfacecolor="#FFD700",
                   markersize=10, label="NCR/NET (Necrotic Core)"),
        plt.Line2D([0], [0], marker='s', color="#0D1117", markerfacecolor="#00BFFF",
                   markersize=10, label="ED (Edema)"),
        plt.Line2D([0], [0], marker='s', color="#0D1117", markerfacecolor="#FF4444",
                   markersize=10, label="ET (Enhancing)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3,
               fontsize=11, frameon=False,
               labelcolor="white", bbox_to_anchor=(0.5, 0.0))

    path1 = get_non_conflicting_path(os.path.join(output_dir, f"{patient_id}_clinical_report.png"))
    fig.savefig(path1, dpi=150, facecolor="#0D1117", bbox_inches="tight")
    plt.close(fig)
    saved.append(path1)

    # ══════════════════════════════════════════════════════════════════════════
    #  FIGURE 2: All 4 MRI Modalities side by side (T1, T1ce, T2, FLAIR)
    # ══════════════════════════════════════════════════════════════════════════
    fig2, axes2 = plt.subplots(1, 4, figsize=(20, 5), facecolor="#0D1117")
    modalities = ["T1", "T1ce", "T2", "FLAIR"]

    for idx, (ax, mod_name) in enumerate(zip(axes2, modalities)):
        ax.set_facecolor("#0D1117")
        mri_slice_mod = image[idx][slice_d, :, :]
        ax.imshow(mri_slice_mod.T, cmap="gray", aspect="equal", origin="lower")

        # Overlay mask on each
        if mask is not None:
            mask_slice_d = mask[slice_d, :, :]
            if np.any(mask_slice_d > 0):
                ax.imshow(mask_slice_d.T.astype(float), cmap=tumor_cmap,
                          vmin=0, vmax=4, aspect="equal", origin="lower", alpha=0.5)

        ax.set_title(mod_name, fontsize=14, fontweight="bold", color="white")
        ax.tick_params(colors="#8B949E", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#30363D")

    fig2.suptitle(f"MRI Modalities at Axial Slice {slice_d} — {patient_id}",
                  fontsize=16, fontweight="bold", color="white", y=1.02)
    fig2.tight_layout()

    path2 = get_non_conflicting_path(os.path.join(output_dir, f"{patient_id}_modalities.png"))
    fig2.savefig(path2, dpi=150, facecolor="#0D1117", bbox_inches="tight")
    plt.close(fig2)
    saved.append(path2)

    return saved


# ═══════════════════════════════════════════════════════════════════════════════
#  INFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

def predict_one(npz_path, model, channel_mean, channel_std, target_size, device, label_col):
    """Run inference on a single .npz file. Also extracts the mask for
    tumor location analysis if available."""
    data = np.load(npz_path)
    if "image" not in data:
        raise KeyError(f"{npz_path}: no 'image' key found (keys: {list(data.keys())})")
    image = data["image"]  # (4, X, Y, Z)

    if image.ndim != 4 or image.shape[0] != EXPECTED_CHANNELS:
        raise ValueError(f"{npz_path}: expected image shape (4,X,Y,Z), got {image.shape}")

    original_shape = image.shape
    mask = data["mask"] if "mask" in data else None

    # Preprocessing
    resized = resize_volume(image, target_size, device)
    normalized = normalize_channels(resized, channel_mean, channel_std)
    input_tensor = normalized.unsqueeze(0).to(device)

    # Inference
    with torch.no_grad():
        with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
            logits = model(input_tensor)
        probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

    pred_class = int(probs.argmax())
    confidence = float(probs[pred_class])

    # Tumor location analysis
    tumor_info = analyze_tumor_location(mask)

    return {
        "npz_path": npz_path,
        "patient_id": os.path.splitext(os.path.basename(npz_path))[0],
        "original_shape": list(original_shape),
        "preprocessed_shape": [EXPECTED_CHANNELS, target_size, target_size, target_size],
        "predicted_class": pred_class,
        "predicted_label": "POSITIVE" if pred_class == 1 else "NEGATIVE",
        "confidence": round(confidence, 4),
        "prob_negative": round(float(probs[0]), 4),
        "prob_positive": round(float(probs[1]), 4),
        "label_col": label_col,
        "timestamp": datetime.datetime.now().isoformat(),
        "tumor_location": tumor_info,
        "_raw_image": image,   # kept for visualization, not serialized
        "_raw_mask": mask,     # kept for visualization, not serialized
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIDENCE GAUGE & RISK LEVEL
# ═══════════════════════════════════════════════════════════════════════════════

def _risk_level(confidence):
    if confidence >= 0.90:
        return "HIGH", C.GREEN, "●"
    elif confidence >= 0.70:
        return "MODERATE", C.YELLOW, "●"
    else:
        return "LOW", C.RED, "●"


def _confidence_gauge(confidence, width=30):
    filled = int(round(confidence * width))
    empty = width - filled
    _, color, _ = _risk_level(confidence)
    bar = f"{color}{'█' * filled}{C.GRAY}{'░' * empty}{C.RESET}"
    return f"  [{bar}]  {color}{C.BOLD}{confidence:.1%}{C.RESET}"


def _risk_badge(confidence):
    level, color, dot = _risk_level(confidence)
    return f"{color}{C.BOLD}{dot} {level} CONFIDENCE{C.RESET}"


# ═══════════════════════════════════════════════════════════════════════════════
#  CLINICAL INTERPRETATION
# ═══════════════════════════════════════════════════════════════════════════════

def _clinical_interpretation(result, label_col):
    info = LABEL_CLINICAL_INFO.get(label_col, {})
    clinical_name = info.get("short", label_col)
    who_region = info.get("who_region", "")

    is_positive = result["predicted_label"] == "POSITIVE"
    conf = result["confidence"]

    if is_positive and conf >= 0.90:
        return (
            f"The model detects {clinical_name.lower()} with {C.GREEN}high confidence "
            f"({conf:.1%}){C.RESET}. This finding is consistent with the presence of "
            f"{who_region} tissue. Clinical correlation with contrast-enhanced MRI "
            f"sequences is recommended for treatment planning."
        )
    elif is_positive and conf >= 0.70:
        return (
            f"The model suggests probable {clinical_name.lower()} ({C.YELLOW}{conf:.1%} "
            f"confidence{C.RESET}). While the prediction favors a positive finding, the "
            f"moderate confidence level warrants {C.BOLD}radiologist review{C.RESET} and "
            f"correlation with clinical history before making treatment decisions."
        )
    elif is_positive:
        return (
            f"The model suggests possible {clinical_name.lower()}, but confidence is "
            f"{C.RED}low ({conf:.1%}){C.RESET}. This result is {C.BOLD}borderline{C.RESET} "
            f"— recommend detailed radiologist review, correlation with prior imaging, "
            f"and consider repeat or supplementary imaging studies."
        )
    elif not is_positive and conf >= 0.90:
        return (
            f"No {clinical_name.lower()} detected ({C.GREEN}{conf:.1%} confidence{C.RESET}). "
            f"Findings are consistent with treatment response, absence of active disease, "
            f"or normal tissue in the {who_region} region. Routine follow-up per clinical "
            f"protocol is advised."
        )
    elif not is_positive and conf >= 0.70:
        return (
            f"The model does not detect {clinical_name.lower()} ({C.YELLOW}{conf:.1%} "
            f"confidence{C.RESET}). While likely negative, the moderate confidence suggests "
            f"{C.BOLD}clinical follow-up{C.RESET} may be appropriate, particularly if there "
            f"is clinical suspicion or prior positive findings."
        )
    else:
        return (
            f"The model does not detect {clinical_name.lower()}, but confidence is "
            f"{C.RED}low ({conf:.1%}){C.RESET}. {C.BOLD}Cannot reliably rule out{C.RESET} "
            f"small or diffuse components. Comprehensive radiologist assessment and "
            f"additional imaging studies are strongly advised."
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  RICH OUTPUT FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════

def _wrap_text(text, width=65, indent="     "):
    """Word-wrap text, accounting for ANSI escape codes in length."""
    ansi_re_pattern = re.compile(r'\033\[[0-9;]*m')
    words = text.split()
    lines, current_plain, current_rich = [], "", indent
    for w in words:
        w_plain = ansi_re_pattern.sub('', w)
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


def print_model_banner(args, ckpt, device, n_files):
    """Print a clean clinical report header."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info = LABEL_CLINICAL_INFO.get(args.label_col, {})
    clinical_task = info.get("clinical", args.label_col)

    epoch_str = str(ckpt.get("epoch", "N/A") + 1) if "epoch" in ckpt else "N/A"
    val_f1 = ckpt.get("best_val_f1", None)
    val_f1_str = f"{val_f1:.4f}" if val_f1 is not None else "N/A"

    print()
    print(f"  {C.CYAN}{C.BOLD}{'━' * 68}{C.RESET}")
    print(f"  {C.BOLD}  🧠  BraTS MRI TUMOR CLASSIFICATION — CLINICAL REPORT{C.RESET}")
    print(f"  {C.CYAN}{C.BOLD}{'━' * 68}{C.RESET}")
    print()
    print(f"  {C.DIM}  Model       {C.RESET} 3D ResNet-18 (Adapted for 4-ch BraTS MRI)")
    print(f"  {C.DIM}  Task        {C.RESET} {clinical_task}")
    print(f"  {C.DIM}  Checkpoint  {C.RESET} Epoch {epoch_str}  |  Best Val F1: {val_f1_str}")
    print(f"  {C.DIM}  Device      {C.RESET} {device}")
    print(f"  {C.DIM}  Timestamp   {C.RESET} {now}")
    print(f"  {C.DIM}  Scans       {C.RESET} {n_files} file(s) queued for analysis")
    print()
    print(f"  {C.CYAN}{'─' * 68}{C.RESET}")
    print()


def print_result_detailed(result, label_col):
    """Print a single result as a rich clinical report card."""
    info = LABEL_CLINICAL_INFO.get(label_col, {})
    clinical_name = info.get("clinical", label_col)
    description = info.get("description", "")

    is_positive = result["predicted_label"] == "POSITIVE"
    conf = result["confidence"]
    tumor_info = result.get("tumor_location", None)

    # ── Patient header ──
    print(f"  {C.BOLD}📂 PATIENT: {C.CYAN}{result['patient_id']}{C.RESET}")
    print(f"  {C.DIM}   File: {result['npz_path']}{C.RESET}")
    print(f"  {C.DIM}   Original Volume: {result['original_shape'][1]}x{result['original_shape'][2]}x{result['original_shape'][3]} "
          f"(T1, T1ce, T2, FLAIR){C.RESET}")
    print()

    # ── Classification task ──
    print(f"  {C.BOLD}📋 CLASSIFICATION TASK{C.RESET}")
    print(f"     {C.BOLD}{clinical_name}{C.RESET}")
    if description:
        for line in _wrap_text(description, width=65, indent="     "):
            print(f"  {C.DIM}{line}{C.RESET}")
    print()

    # ── Prediction result ──
    print(f"  {C.BOLD}🔬 PREDICTION RESULT{C.RESET}")
    if is_positive:
        pred_display = f"{C.RED}{C.BOLD}▲ POSITIVE{C.RESET}"
    else:
        pred_display = f"{C.GREEN}{C.BOLD}▼ NEGATIVE{C.RESET}"
    print(f"     Prediction:   {pred_display}")
    print(f"     Risk Level:   {_risk_badge(conf)}")
    print()

    # ── Confidence gauge ──
    print(f"  {C.BOLD}📊 CONFIDENCE{C.RESET}")
    print(f"  {_confidence_gauge(conf)}")
    print(f"     {C.DIM}P(negative) = {result['prob_negative']:.1%}    "
          f"P(positive) = {result['prob_positive']:.1%}{C.RESET}")
    print()

    # ── Tumor location (from mask) ──
    if tumor_info and tumor_info.get("has_tumor"):
        print(f"  {C.BOLD}📍 TUMOR LOCATION{C.RESET}")
        print(f"     Location:     {C.BOLD}{tumor_info['anatomical_summary']}{C.RESET}")
        print(f"     Laterality:   {tumor_info['laterality']}")
        com = tumor_info["center_of_mass_voxel"]
        print(f"     Center:       Voxel ({com['D']}, {com['H']}, {com['W']})")
        bb = tumor_info["bounding_box_size"]
        print(f"     Extent:       {bb['depth_span']} x {bb['height_span']} x {bb['width_span']} voxels")
        vol_pct = tumor_info["tumor_volume_fraction"] * 100
        print(f"     Volume:       {vol_pct:.2f}% of total brain volume")
        print()

        # Sub-type breakdown
        print(f"  {C.BOLD}🧬 TUMOR COMPOSITION{C.RESET}")
        st = tumor_info["subtypes"]
        for key, color_code in [("NCR/NET", C.YELLOW), ("ED", C.CYAN), ("ET", C.RED)]:
            sub = st[key]
            if sub["voxel_count"] > 0:
                pct = sub["fraction_of_tumor"] * 100
                bar_w = int(round(sub["fraction_of_tumor"] * 20))
                bar = f"{color_code}{'█' * bar_w}{C.GRAY}{'░' * (20 - bar_w)}{C.RESET}"
                print(f"     {color_code}{key:<10}{C.RESET}  [{bar}]  {pct:5.1f}%  ({sub['voxel_count']:,} voxels)")
            else:
                print(f"     {C.DIM}{key:<10}  Not detected{C.RESET}")
        print()
    elif tumor_info and not tumor_info.get("has_tumor"):
        print(f"  {C.BOLD}📍 TUMOR LOCATION{C.RESET}")
        print(f"     {C.GREEN}No tumor tissue detected in segmentation mask{C.RESET}")
        print()
    else:
        print(f"  {C.BOLD}📍 TUMOR LOCATION{C.RESET}")
        print(f"     {C.DIM}Segmentation mask not available in this file{C.RESET}")
        print()

    # ── Clinical interpretation ──
    interpretation = _clinical_interpretation(result, label_col)
    print(f"  {C.BOLD}💬 CLINICAL INTERPRETATION{C.RESET}")
    for line in _wrap_text(interpretation, width=65, indent="     "):
        print(f"  {line}")
    print()

    # ── Separator ──
    print(f"  {C.CYAN}{'─' * 68}{C.RESET}")
    print()


def print_batch_summary(results, label_col):
    """Print a formatted summary table for batch runs."""
    if len(results) <= 1:
        return

    info = LABEL_CLINICAL_INFO.get(label_col, {})
    task_name = info.get("short", label_col)

    print()
    print(f"  {C.BOLD}{C.CYAN}{'━' * 68}{C.RESET}")
    print(f"  {C.BOLD}📊 BATCH SUMMARY — {task_name} ({len(results)} scans){C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}{'━' * 68}{C.RESET}")
    print()

    # Table header
    col_w = [30, 12, 12, 18]
    print(f"  {C.DIM}┌{'─' * (col_w[0]+2)}┬{'─' * (col_w[1]+2)}┬{'─' * (col_w[2]+2)}┬{'─' * (col_w[3]+2)}┐{C.RESET}")
    print(f"  {C.DIM}│{C.RESET} {C.BOLD}{'Patient / File':<{col_w[0]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Prediction':<{col_w[1]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Confidence':<{col_w[2]}}{C.RESET} "
          f"{C.DIM}│{C.RESET} {C.BOLD}{'Risk Level':<{col_w[3]}}{C.RESET} {C.DIM}│{C.RESET}")
    print(f"  {C.DIM}├{'═' * (col_w[0]+2)}┼{'═' * (col_w[1]+2)}┼{'═' * (col_w[2]+2)}┼{'═' * (col_w[3]+2)}┤{C.RESET}")

    n_positive, n_negative = 0, 0
    for r in results:
        is_pos = r["predicted_label"] == "POSITIVE"
        n_positive += is_pos
        n_negative += not is_pos

        patient = r["patient_id"][:col_w[0]]
        pred_display = "POSITIVE" if is_pos else "NEGATIVE"
        pred_colored = f"{C.RED if is_pos else C.GREEN}{pred_display}{C.RESET}"
        conf_str = f"{r['confidence']:.1%}"
        level, color, dot = _risk_level(r["confidence"])
        risk_str = f"{color}{dot} {level}{C.RESET}"

        print(f"  {C.DIM}│{C.RESET} {patient:<{col_w[0]}} "
              f"{C.DIM}│{C.RESET} {pred_colored}{' ' * (col_w[1] - len(pred_display))} "
              f"{C.DIM}│{C.RESET} {conf_str:<{col_w[2]}} "
              f"{C.DIM}│{C.RESET} {risk_str}{' ' * max(0, col_w[3] - len(level) - 2)} {C.DIM}│{C.RESET}")

    print(f"  {C.DIM}└{'─' * (col_w[0]+2)}┴{'─' * (col_w[1]+2)}┴{'─' * (col_w[2]+2)}┴{'─' * (col_w[3]+2)}┘{C.RESET}")

    print()
    print(f"  {C.BOLD}Summary:{C.RESET}  {len(results)} scans  |  "
          f"{C.RED}{n_positive} Positive{C.RESET}  |  "
          f"{C.GREEN}{n_negative} Negative{C.RESET}")

    low_conf = [r for r in results if r["confidence"] < 0.70]
    if low_conf:
        print(f"  {C.YELLOW}{C.BOLD}⚠  {len(low_conf)} scan(s) with LOW confidence — recommend review:{C.RESET}")
        for r in low_conf:
            print(f"     {C.YELLOW}• {r['patient_id']}  ({r['confidence']:.1%}){C.RESET}")
    print()


def export_json_report(results, label_col, args, ckpt, device, report_path):
    """Export structured JSON report for PACS/EHR integration."""
    info = LABEL_CLINICAL_INFO.get(label_col, {})

    report = {
        "report_type": "BraTS MRI Tumor Classification",
        "generated_at": datetime.datetime.now().isoformat(),
        "model": {
            "architecture": "3D ResNet-18 (Adapted 4-channel BraTS)",
            "checkpoint": args.checkpoint,
            "training_epoch": ckpt.get("epoch", None),
            "best_val_f1": ckpt.get("best_val_f1", None),
            "device": str(device),
            "num_classes": args.num_classes,
        },
        "classification_task": {
            "label_column": label_col,
            "clinical_name": info.get("clinical", label_col),
            "description": info.get("description", ""),
        },
        "preprocessing": {
            "target_size": args.target_size,
            "channel_stats_source": args.data_dir,
        },
        "results": [],
        "summary": {
            "total_scans": len(results),
            "positive": sum(1 for r in results if r["predicted_label"] == "POSITIVE"),
            "negative": sum(1 for r in results if r["predicted_label"] == "NEGATIVE"),
            "avg_confidence": round(sum(r["confidence"] for r in results) / max(len(results), 1), 4),
            "low_confidence_count": sum(1 for r in results if r["confidence"] < 0.70),
        },
        "disclaimer": (
            "This is an AI-assisted screening tool. All findings are probabilistic "
            "and must be confirmed by a qualified radiologist or neuro-oncologist."
        ),
    }

    for r in results:
        level, _, _ = _risk_level(r["confidence"])
        entry = {
            "patient_id": r["patient_id"],
            "file": r["npz_path"],
            "result_dir": r.get("result_dir"),
            "original_volume_shape": r["original_shape"],
            "prediction": r["predicted_label"],
            "predicted_class": r["predicted_class"],
            "confidence": r["confidence"],
            "probability_negative": r["prob_negative"],
            "probability_positive": r["prob_positive"],
            "risk_level": level,
            "tumor_location": r.get("tumor_location"),
            "timestamp": r["timestamp"],
        }
        report["results"].append(entry)

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report_path


# ═══════════════════════════════════════════════════════════════════════════════
#  QUIET MODE OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def print_quiet(result):
    level, _, _ = _risk_level(result["confidence"])
    entry = {
        "patient_id": result["patient_id"],
        "prediction": result["predicted_label"],
        "confidence": result["confidence"],
        "prob_negative": result["prob_negative"],
        "prob_positive": result["prob_positive"],
        "risk_level": level,
        "tumor_location": result.get("tumor_location"),
    }
    print(json.dumps(entry))


# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT SELECTION UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_input_directory(script_dir, user_input_dir=None):
    """Find the target input directory, checking user arg, then INPUT/ or input/."""
    if user_input_dir:
        if os.path.isabs(user_input_dir):
            return user_input_dir
        if os.path.exists(user_input_dir):
            return os.path.abspath(user_input_dir)
        return os.path.join(script_dir, user_input_dir)

    for candidate in ["INPUT", "input"]:
        cand_path = os.path.join(script_dir, candidate)
        if os.path.isdir(cand_path):
            return cand_path

    # If neither exists, default to INPUT in script directory
    default_dir = os.path.join(script_dir, "INPUT")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


def prompt_select_scans(input_dir, npz_files, is_quiet=False, select_all=False):
    """If multiple .npz files are present in input_dir, display an interactive
    terminal prompt for the user to choose which scan(s) to process."""
    if not npz_files:
        return []

    if len(npz_files) == 1:
        if not is_quiet:
            print(f"  {C.CYAN}📂 1 scan detected in '{os.path.basename(input_dir)}':{C.RESET} {npz_files[0]}")
            print()
        return [os.path.join(input_dir, npz_files[0])]

    # If --all flag was given, process all without prompting
    if select_all:
        if not is_quiet:
            print(f"  {C.CYAN}📂 Batch mode (--all): queuing all {len(npz_files)} scans from '{os.path.basename(input_dir)}'{C.RESET}")
            print()
        return [os.path.join(input_dir, f) for f in npz_files]

    # Non-interactive fallback (e.g. redirected pipe or quiet mode)
    if is_quiet or not sys.stdin.isatty():
        return [os.path.join(input_dir, f) for f in npz_files]

    folder_name = os.path.basename(input_dir) or input_dir
    n = len(npz_files)

    print()
    print(f"  {C.CYAN}{C.BOLD}{'━' * 68}{C.RESET}")
    print(f"  {C.BOLD}  📁  BraTS MRI INPUT SCAN SELECTION{C.RESET}")
    print(f"  {C.CYAN}{C.BOLD}{'━' * 68}{C.RESET}")
    print()
    print(f"  Multiple MRI scans found in '{C.BOLD}{folder_name}{C.RESET}' ({n} files):")
    print()

    for idx, fname in enumerate(npz_files, 1):
        fpath = os.path.join(input_dir, fname)
        try:
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
            size_str = f"({size_mb:.2f} MB)"
        except Exception:
            size_str = ""
        print(f"    {C.CYAN}[{idx}]{C.RESET} {fname}  {C.DIM}{size_str}{C.RESET}")

    print(f"    {C.GREEN}[A]{C.RESET} Process ALL scans ({n} files — batch mode)")
    print(f"    {C.GRAY}[Q]{C.RESET} Quit")
    print()

    while True:
        try:
            choice = input(f"  Select a scan to analyze [1-{n}, A for all, Q to quit] (default: 1): ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {C.YELLOW}Selection cancelled by user.{C.RESET}")
            sys.exit(0)

        if not choice:
            choice = "1"

        if choice.lower() in ("q", "quit", "exit"):
            print(f"  {C.YELLOW}Exiting.{C.RESET}")
            sys.exit(0)

        if choice.lower() in ("a", "all", "*"):
            print(f"  {C.GREEN}✓ Selected ALL {n} scans for analysis{C.RESET}\n")
            return [os.path.join(input_dir, f) for f in npz_files]

        # Check for single number or comma/space-separated numbers (e.g. "1" or "1, 2")
        parts = [p.strip() for p in re.split(r'[, ]+', choice) if p.strip()]
        selected_indices = []
        valid = True
        for p in parts:
            if p.isdigit():
                val = int(p)
                if 1 <= val <= n:
                    if val not in selected_indices:
                        selected_indices.append(val)
                else:
                    valid = False
                    break
            else:
                valid = False
                break

        if valid and selected_indices:
            selected_files = [npz_files[i - 1] for i in selected_indices]
            if len(selected_files) == 1:
                print(f"  {C.GREEN}✓ Selected scan:{C.RESET} {selected_files[0]}\n")
            else:
                print(f"  {C.GREEN}✓ Selected {len(selected_files)} scans:{C.RESET} {', '.join(selected_files)}\n")
            return [os.path.join(input_dir, f) for f in selected_files]

        print(f"  {C.RED}Invalid selection '{choice}'. Please enter a number between 1 and {n}, 'A' for all, or 'Q' to quit.{C.RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="BraTS MRI Tumor Classification — Clinical Inference Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py                         # Interactive: select scan from INPUT/\n"
            "  python run.py --all                   # Process all scans in INPUT/\n"
            "  python run.py --input scans/          # Select from a custom folder\n"
            "  python run.py --npz INPUT/test.npz    # Run a specific scan\n"
            "  python run.py --no-figures            # Skip generating PNG figures\n"
        ),
    )
    parser.add_argument("path", nargs="?", default=None,
                         help="Optional path to a .npz file or input directory")
    parser.add_argument("--npz", type=str, default=None,
                         help="Path to a single raw BraTS .npz file")
    parser.add_argument("--input", "--input_dir", "--npz_dir", dest="input_dir", type=str, default=None,
                         help="Path to folder containing .npz files (default: INPUT)")
    parser.add_argument("--all", action="store_true",
                         help="Process all scans in the input directory without interactive prompt")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/best_model.pth",
                         help="Path to model checkpoint (default: checkpoints/best_model.pth)")
    parser.add_argument("--data_dir", type=str, default="processed_brats",
                         help="Folder containing channel_stats.json (default: processed_brats)")
    parser.add_argument("--label_col", type=str, default="has_ET",
                         help="Which label this checkpoint was trained on (default: has_ET)")
    parser.add_argument("--num_classes", type=int, default=2)
    parser.add_argument("--target_size", type=int, default=DEFAULT_TARGET_SIZE)
    parser.add_argument("--report", type=str, default=None,
                         help="Export structured JSON report to this path")
    parser.add_argument("--output_dir", type=str, default="results",
                         help="Directory for generated figures (default: results/)")
    parser.add_argument("--no-figures", action="store_true",
                         help="Skip generating matplotlib figures")
    parser.add_argument("--quiet", action="store_true",
                         help="Machine-readable JSON-lines output only")
    args = parser.parse_args()

    # ── Resolve paths relative to the script's directory ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if args.npz and not os.path.isabs(args.npz):
        args.npz = os.path.join(script_dir, args.npz)
    if not os.path.isabs(args.checkpoint):
        args.checkpoint = os.path.join(script_dir, args.checkpoint)
    if not os.path.isabs(args.data_dir):
        args.data_dir = os.path.join(script_dir, args.data_dir)
    if not os.path.isabs(args.output_dir):
        args.output_dir = os.path.join(script_dir, args.output_dir)

    # Disable colors in quiet mode or non-TTY
    if args.quiet or not sys.stdout.isatty():
        C.disable()

    # ── Collect input files ──
    npz_paths = []

    # 1. Did the user specify a specific file via positional arg or --npz?
    specific_file = None
    if args.npz:
        specific_file = args.npz
    elif args.path and os.path.isfile(args.path):
        specific_file = args.path

    if specific_file:
        if not os.path.isabs(specific_file):
            if os.path.exists(specific_file):
                specific_file = os.path.abspath(specific_file)
            else:
                specific_file = os.path.join(script_dir, specific_file)
        if not os.path.exists(specific_file):
            print(f"Error: Specified file not found: {specific_file}", file=sys.stderr)
            sys.exit(1)
        npz_paths.append(specific_file)
    else:
        # 2. Look in the input folder
        target_input_dir = None
        if args.input_dir:
            target_input_dir = args.input_dir
        elif args.path and os.path.isdir(args.path):
            target_input_dir = args.path

        input_folder = resolve_input_directory(script_dir, target_input_dir)

        if not os.path.exists(input_folder):
            print(f"Error: Input directory not found: {input_folder}", file=sys.stderr)
            sys.exit(1)

        available_files = [f for f in sorted(os.listdir(input_folder)) if f.lower().endswith(".npz")]

        if not available_files:
            folder_name = os.path.basename(input_folder)
            print(f"\n  {C.RED}{C.BOLD}✗ No .npz files found in input directory:{C.RESET} {input_folder}")
            print(f"  Please place your BraTS MRI scans (.npz) into the '{folder_name}' folder and run again.\n")
            sys.exit(1)

        npz_paths = prompt_select_scans(
            input_folder, available_files,
            is_quiet=args.quiet,
            select_all=args.all
        )

    if not npz_paths:
        print("No .npz files selected to process.", file=sys.stderr)
        sys.exit(1)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── Load prerequisites ──
    channel_mean, channel_std = load_channel_stats(args.data_dir)
    model, ckpt = build_model(args.checkpoint, args.num_classes, device)

    # ── Print banner (rich mode only) ──
    if not args.quiet:
        print_model_banner(args, ckpt, device, len(npz_paths))

    # ── Run inference ──
    all_results = []
    for npz_path in npz_paths:
        try:
            result = predict_one(npz_path, model, channel_mean, channel_std,
                                  args.target_size, device, args.label_col)
            all_results.append(result)

            if args.quiet:
                print_quiet(result)
            else:
                print_result_detailed(result, args.label_col)

            # ── Create separate folder per patient inside results/ and avoid overwriting ──
            patient_dir = get_patient_output_dir(args.output_dir, result["patient_id"])
            result["result_dir"] = patient_dir

            # Save individual structured clinical report JSON
            patient_json_path = get_non_conflicting_path(
                os.path.join(patient_dir, f"{result['patient_id']}_result.json")
            )
            _save_patient_json(result, patient_json_path, args.label_col)

            if not args.quiet:
                print(f"  {C.CYAN}📁 Result folder:{C.RESET} {patient_dir}")
                print(f"  {C.GREEN}📄 Result JSON saved:{C.RESET} {patient_json_path}")

            # Generate figures inside separate patient folder
            if not args.no_figures:
                raw_image = result.pop("_raw_image", None)
                raw_mask = result.pop("_raw_mask", None)
                if raw_image is not None:
                    saved_figs = generate_clinical_figures(
                        raw_image, raw_mask, result,
                        result.get("tumor_location"), args.label_col,
                        patient_dir
                    )
                    for fig_path in saved_figs:
                        print(f"  {C.GREEN}📊 Figure saved:{C.RESET} {fig_path}")
                    print()

        except Exception as e:
            if args.quiet:
                print(json.dumps({"file": npz_path, "error": str(e)}), file=sys.stderr)
            else:
                print(f"  {C.RED}{C.BOLD}✗ ERROR{C.RESET} processing {npz_path}: {e}")
                print()

    # ── Clean up raw data from results before export ──
    for r in all_results:
        r.pop("_raw_image", None)
        r.pop("_raw_mask", None)

    # ── Batch summary (rich mode, multiple files) ──
    if not args.quiet:
        print_batch_summary(all_results, args.label_col)

    # ── JSON report export ──
    if args.report and all_results:
        final_report_path = get_non_conflicting_path(args.report)
        path = export_json_report(all_results, args.label_col, args, ckpt, device, final_report_path)
        if not args.quiet:
            print(f"  {C.GREEN}{C.BOLD}📄 Report exported:{C.RESET} {path}")
            print()


if __name__ == "__main__":
    main()