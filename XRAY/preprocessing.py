
import os
import re
import sys
import json
import time
import hashlib
import logging
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from PIL import Image, ImageFile

# Allow loading of truncated images instead of crashing
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHEXPERT_LABELS = [
    "No Finding",
    "Enlarged Cardiomediastinum",
    "Cardiomegaly",
    "Lung Opacity",
    "Lung Lesion",
    "Edema",
    "Consolidation",
    "Pneumonia",
    "Atelectasis",
    "Pneumothorax",
    "Pleural Effusion",
    "Pleural Other",
    "Fracture",
    "Support Devices",
]

# Classes where uncertain (-1) is mapped to 1 under the U-Ones policy
# (per the CheXpert paper: these conditions are more likely present
# when the radiologist expressed uncertainty)
U_ONES_CLASSES = {"Atelectasis", "Edema"}

# DenseNet-121 (ImageNet) expects 224×224, but the CheXpert paper
# uses 320×320 for higher resolution. We default to 320.
IMG_SIZE = 320

# ImageNet normalization constants (used at training time, saved in metadata)
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

VAL_FRACTION = 0.1
RANDOM_SEED = 42
NUM_WORKERS = 8

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label resolution
# ---------------------------------------------------------------------------


def resolve_labels(df: pd.DataFrame, policy: str = "u_ones") -> pd.DataFrame:
    """Resolve uncertain (-1) and missing (NaN) labels to binary 0/1.

    Policies:
        u_ones   — map -1 → 1 for Atelectasis & Edema, -1 → 0 for others (paper default)
        u_zeros  — map -1 → 0 for all
        u_all_ones — map -1 → 1 for all
    NaN (not mentioned) is always mapped to 0.
    """
    df = df.copy()
    for label in CHEXPERT_LABELS:
        col = df[label].fillna(0.0)
        if policy == "u_ones":
            uncertain_value = 1 if label in U_ONES_CLASSES else 0
        elif policy == "u_zeros":
            uncertain_value = 0
        elif policy == "u_all_ones":
            uncertain_value = 1
        else:
            raise ValueError(f"Unknown policy: {policy}")
        col = col.replace(-1.0, uncertain_value)
        df[label] = col.astype(np.int8)
    return df


# ---------------------------------------------------------------------------
# Path resolution and filtering
# ---------------------------------------------------------------------------


def extract_patient_id(path: str) -> str:
    """Extract patient ID (e.g., 'patient00001') from a CheXpert path."""
    match = re.search(r"(patient\d+)", path)
    return match.group(1) if match else "unknown"


def resolve_image_path(data_dir: str, csv_path: str) -> str:
    """Convert the CSV's relative path to an absolute filesystem path.

    The CSV stores paths like 'CheXpert-v1.0-small/train/patient.../view.jpg'.
    If data_dir IS 'CheXpert-v1.0-small', we strip the prefix and join.
    """
    # Strip the 'CheXpert-v1.0-small/' prefix if present
    cleaned = re.sub(r"^CheXpert-v1\.0-small[/\\]", "", csv_path)
    candidate = os.path.join(data_dir, cleaned)
    if os.path.isfile(candidate):
        return candidate
    # Fallback: try joining from the parent directory
    candidate2 = os.path.join(os.path.dirname(data_dir), csv_path)
    if os.path.isfile(candidate2):
        return candidate2
    return candidate  # Return best guess; we'll check existence later


def load_and_prepare(
    data_dir: str,
    csv_name: str,
    policy: str,
    frontal_only: bool = True,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load a CheXpert CSV, resolve labels, resolve paths, filter, validate."""
    csv_path = os.path.join(data_dir, csv_name)
    if not os.path.isfile(csv_path):
        log.error(f"CSV not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    log.info(f"Loaded {csv_name}: {len(df):,} rows, {len(df.columns)} columns")

    # --- Filter to frontal views only (standard benchmark) ---
    if frontal_only:
        before = len(df)
        df = df[df["Frontal/Lateral"] == "Frontal"].reset_index(drop=True)
        log.info(f"  Frontal-only filter: {before:,} → {len(df):,} rows (dropped {before - len(df):,} lateral)")

    # --- Optional row limit for debugging ---
    if limit and limit < len(df):
        df = df.sample(n=limit, random_state=RANDOM_SEED).reset_index(drop=True)
        log.info(f"  Limited to {len(df):,} rows for this run")

    # --- Resolve labels ---
    df = resolve_labels(df, policy=policy)

    # --- Extract patient IDs and resolve image paths ---
    df["patient_id"] = df["Path"].apply(extract_patient_id)
    df["image_path"] = df["Path"].apply(lambda p: resolve_image_path(data_dir, p))

    # --- Validate: check which files actually exist ---
    exists_mask = df["image_path"].apply(os.path.isfile)
    missing = (~exists_mask).sum()
    if missing > 0:
        log.warning(f"  {missing:,} images not found on disk — dropping those rows")
        df = df[exists_mask].reset_index(drop=True)

    log.info(f"  Final: {len(df):,} rows, {df['patient_id'].nunique():,} patients")
    return df


# ---------------------------------------------------------------------------
# Patient-level train/val split (prevents data leakage)
# ---------------------------------------------------------------------------


def split_train_val_by_patient(
    df: pd.DataFrame,
    val_fraction: float = VAL_FRACTION,
    seed: int = RANDOM_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split dataframe by patient ID so no patient appears in both sets."""
    patient_ids = df["patient_id"].dropna().unique()
    rng = np.random.RandomState(seed)
    rng.shuffle(patient_ids)

    n_val = max(1, int(len(patient_ids) * val_fraction))
    val_patients = set(patient_ids[:n_val])

    val_mask = df["patient_id"].isin(val_patients)
    train_df = df[~val_mask].reset_index(drop=True)
    val_df = df[val_mask].reset_index(drop=True)

    log.info(
        f"  Patient-level split: {len(train_df):,} train images "
        f"({df['patient_id'].nunique() - len(val_patients):,} patients), "
        f"{len(val_df):,} val images ({len(val_patients):,} patients)"
    )
    return train_df, val_df


# ---------------------------------------------------------------------------
# Image processing (PIL-based, portable, no GPU dependency)
# ---------------------------------------------------------------------------


def process_single_image(
    src_path: str,
    dst_path: str,
    img_size: int,
    overwrite: bool = False,
) -> tuple[bool, str]:
    """Resize a single image to img_size×img_size and save.

    Returns:
        (success: bool, message: str)
    """
    if not overwrite and os.path.isfile(dst_path):
        return True, "skipped (exists)"

    try:
        with Image.open(src_path) as img:
            # Convert to RGB (some CheXpert images may be grayscale or RGBA)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Resize with high-quality Lanczos resampling
            img_resized = img.resize((img_size, img_size), Image.LANCZOS)

            # Save as JPEG with high quality
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            img_resized.save(dst_path, "JPEG", quality=95)

        return True, "ok"
    except Exception as e:
        return False, str(e)


def build_output_path(
    csv_path: str,
    split_name: str,
    out_dir: str,
) -> str:
    """Build the destination path for a processed image.

    Structure: out_dir/images/{split}/{patient_id}_{study}_{view}.jpg
    This keeps a flat-ish structure (one level) that's easy to iterate.
    """
    # Parse components from the original path
    # e.g. "CheXpert-v1.0-small/train/patient00001/study1/view1_frontal.jpg"
    parts = Path(csv_path.replace("\\", "/")).parts
    # Find patient, study, view parts
    patient = study = view = ""
    for part in parts:
        if part.startswith("patient"):
            patient = part
        elif part.startswith("study"):
            study = part
        elif part.startswith("view"):
            view = part

    if not all([patient, study, view]):
        # Fallback: hash the original path
        h = hashlib.md5(csv_path.encode()).hexdigest()[:12]
        filename = f"{h}.jpg"
    else:
        filename = f"{patient}_{study}_{view}"

    return os.path.join(out_dir, "images", split_name, filename)


def process_split(
    df: pd.DataFrame,
    split_name: str,
    out_dir: str,
    img_size: int,
    overwrite: bool = False,
    num_workers: int = NUM_WORKERS,
) -> pd.DataFrame:
    """Process all images for a split (train/val/test): resize and save.

    Returns the dataframe with an updated 'image_path' column pointing
    to the processed images.
    """
    split_dir = os.path.join(out_dir, "images", split_name)
    os.makedirs(split_dir, exist_ok=True)

    # Build destination paths
    dst_paths = [
        build_output_path(row["Path"], split_name, out_dir)
        for _, row in df.iterrows()
    ]

    # Figure out which images actually need processing
    to_process = []
    for i, (src, dst) in enumerate(zip(df["image_path"], dst_paths)):
        if overwrite or not os.path.isfile(dst):
            to_process.append((i, src, dst))

    skipped = len(df) - len(to_process)
    log.info(f"  {split_name}: {len(to_process):,} to process, {skipped:,} already exist")

    if not to_process:
        df = df.copy()
        df["image_path"] = dst_paths
        return df

    # Process images in parallel using thread pool
    ok_count = 0
    error_count = 0
    errors = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(process_single_image, src, dst, img_size, overwrite): (i, src)
            for i, src, dst in to_process
        }

        done = 0
        for future in as_completed(futures):
            idx, src_path = futures[future]
            success, msg = future.result()
            done += 1

            if success and msg == "ok":
                ok_count += 1
            elif success and msg == "skipped (exists)":
                pass  # Already counted in skipped
            else:
                error_count += 1
                errors.append(f"  {src_path}: {msg}")

            # Progress update every 500 images
            if done % 500 == 0 or done == len(to_process):
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                print(
                    f"\r    [{split_name}] {done:,}/{len(to_process):,} "
                    f"({rate:.0f} img/s, {error_count} errors)",
                    end="", flush=True,
                )

    elapsed = time.time() - start
    print()  # newline after progress
    log.info(
        f"  {split_name} done: {ok_count:,} resized, {skipped:,} skipped, "
        f"{error_count} errors ({elapsed:.1f}s)"
    )

    if errors:
        log.warning(f"  First {min(10, len(errors))} errors:")
        for err in errors[:10]:
            log.warning(err)

    df = df.copy()
    df["image_path"] = dst_paths
    return df


# ---------------------------------------------------------------------------
# Statistics and metadata
# ---------------------------------------------------------------------------


def print_label_distribution(name: str, df: pd.DataFrame) -> dict:
    """Print and return label distribution for a split."""
    stats = {}
    log.info(f"\n{name} set: {len(df):,} images, {df['patient_id'].nunique():,} patients")
    for label in CHEXPERT_LABELS:
        pos = int(df[label].sum())
        neg = len(df) - pos
        pct = 100.0 * pos / len(df) if len(df) else 0
        log.info(f"  {label:28s}: {pos:6,} positive ({pct:5.1f}%)")
        stats[label] = {"positive": pos, "negative": neg, "pct": round(pct, 2)}
    return stats


def compute_pos_weights(df: pd.DataFrame) -> dict[str, float]:
    """Compute pos_weight for each label (for BCEWithLogitsLoss).

    pos_weight = num_negatives / num_positives
    This upweights rare positive classes during training.
    """
    weights = {}
    for label in CHEXPERT_LABELS:
        pos = int(df[label].sum())
        neg = len(df) - pos
        weights[label] = round(neg / pos, 4) if pos > 0 else 1.0
    return weights


def save_metadata(
    out_dir: str,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    pos_weights: dict,
    args: argparse.Namespace,
) -> None:
    """Save a comprehensive metadata JSON for the training pipeline."""
    metadata = {
        "dataset": "CheXpert-v1.0-small",
        "preprocessing": {
            "img_size": args.img_size,
            "policy": args.policy,
            "frontal_only": not args.include_lateral,
            "val_fraction": VAL_FRACTION,
            "random_seed": RANDOM_SEED,
        },
        "normalization": {
            "note": "Apply these at training time (torchvision.transforms.Normalize)",
            "mean": IMAGENET_MEAN,
            "std": IMAGENET_STD,
        },
        "splits": {
            "train": {
                "num_images": len(train_df),
                "num_patients": int(train_df["patient_id"].nunique()),
            },
            "val": {
                "num_images": len(val_df),
                "num_patients": int(val_df["patient_id"].nunique()),
            },
            "test": {
                "num_images": len(test_df),
                "num_patients": int(test_df["patient_id"].nunique()),
            },
        },
        "labels": CHEXPERT_LABELS,
        "num_classes": len(CHEXPERT_LABELS),
        "pos_weights": pos_weights,
        "pos_weights_list": [pos_weights[l] for l in CHEXPERT_LABELS],
    }

    meta_path = os.path.join(out_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    log.info(f"Saved metadata to {meta_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess CheXpert-v1.0-small for DenseNet-121 fine-tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data_dir", type=str, required=True,
        help="Path to the CheXpert-v1.0-small directory",
    )
    parser.add_argument(
        "--out_dir", type=str, default="processed_chexpert",
        help="Output directory for processed data (default: processed_chexpert)",
    )
    parser.add_argument(
        "--img_size", type=int, default=IMG_SIZE,
        help=f"Target image size (default: {IMG_SIZE})",
    )
    parser.add_argument(
        "--policy", type=str, default="u_ones",
        choices=["u_ones", "u_zeros", "u_all_ones"],
        help="Uncertainty label resolution policy (default: u_ones)",
    )
    parser.add_argument(
        "--include_lateral", action="store_true",
        help="Include lateral views (default: frontal-only)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of rows to process (for debugging)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-process images even if they already exist",
    )
    parser.add_argument(
        "--workers", type=int, default=NUM_WORKERS,
        help=f"Number of parallel workers for image processing (default: {NUM_WORKERS})",
    )
    args = parser.parse_args()

    # Validate data directory
    if not os.path.isdir(args.data_dir):
        log.error(f"Data directory not found: {args.data_dir}")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    frontal_only = not args.include_lateral

    # ---------------------------------------------------------------
    # Step 1: Load and prepare CSVs
    # ---------------------------------------------------------------
    log.info("=" * 60)
    log.info("Step 1: Loading and preparing datasets")
    log.info("=" * 60)

    log.info("\n--- Loading train.csv ---")
    full_train_df = load_and_prepare(
        args.data_dir, "train.csv", args.policy,
        frontal_only=frontal_only, limit=args.limit,
    )

    log.info("\n--- Splitting train → train + val (by patient) ---")
    train_df, val_df = split_train_val_by_patient(full_train_df)

    log.info("\n--- Loading valid.csv as held-out TEST set ---")
    test_df = load_and_prepare(
        args.data_dir, "valid.csv", args.policy,
        frontal_only=frontal_only, limit=None,  # Never limit the test set
    )

    # ---------------------------------------------------------------
    # Step 2: Resize and save images
    # ---------------------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("Step 2: Resizing images")
    log.info("=" * 60)

    total_start = time.time()

    train_df = process_split(
        train_df, "train", args.out_dir, args.img_size,
        overwrite=args.overwrite, num_workers=args.workers,
    )
    val_df = process_split(
        val_df, "val", args.out_dir, args.img_size,
        overwrite=args.overwrite, num_workers=args.workers,
    )
    test_df = process_split(
        test_df, "test", args.out_dir, args.img_size,
        overwrite=args.overwrite, num_workers=args.workers,
    )

    elapsed = time.time() - total_start
    log.info(f"\nTotal image processing time: {elapsed:.1f}s")

    # ---------------------------------------------------------------
    # Step 3: Save clean CSVs
    # ---------------------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("Step 3: Saving output CSVs and metadata")
    log.info("=" * 60)

    # Keep only the columns needed for training
    keep_cols = ["image_path", "patient_id"] + CHEXPERT_LABELS

    train_csv_path = os.path.join(args.out_dir, "train.csv")
    val_csv_path = os.path.join(args.out_dir, "val.csv")
    test_csv_path = os.path.join(args.out_dir, "test.csv")

    train_df[keep_cols].to_csv(train_csv_path, index=False)
    val_df[keep_cols].to_csv(val_csv_path, index=False)
    test_df[keep_cols].to_csv(test_csv_path, index=False)

    log.info(f"Saved {train_csv_path} ({len(train_df):,} rows)")
    log.info(f"Saved {val_csv_path} ({len(val_df):,} rows)")
    log.info(f"Saved {test_csv_path} ({len(test_df):,} rows)")

    # ---------------------------------------------------------------
    # Step 4: Print statistics and save metadata
    # ---------------------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("Step 4: Dataset statistics")
    log.info("=" * 60)

    print_label_distribution("Train", train_df)
    print_label_distribution("Val", val_df)
    print_label_distribution("Test", test_df)

    pos_weights = compute_pos_weights(train_df)
    log.info("\npos_weight per label (for BCEWithLogitsLoss):")
    for label, w in pos_weights.items():
        log.info(f"  {label:28s}: {w:.4f}")

    save_metadata(args.out_dir, train_df, val_df, test_df, pos_weights, args)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("Preprocessing complete!")
    log.info("=" * 60)
    log.info(f"Output directory: {os.path.abspath(args.out_dir)}")
    log.info(f"  train.csv  : {len(train_df):,} images")
    log.info(f"  val.csv    : {len(val_df):,} images")
    log.info(f"  test.csv   : {len(test_df):,} images")
    log.info(f"  metadata.json : normalization, pos_weights, config")
    log.info(f"\nReady for DenseNet-121 fine-tuning.")
    log.info(f"  • Loss: BCEWithLogitsLoss(pos_weight=metadata['pos_weights_list'])")
    log.info(f"  • Normalize: mean={IMAGENET_MEAN}, std={IMAGENET_STD}")
    log.info(f"  • Image size: {args.img_size}×{args.img_size}")


if __name__ == "__main__":
    main()