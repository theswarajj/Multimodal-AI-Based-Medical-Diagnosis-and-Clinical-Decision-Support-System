
import os

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import re
import sys
import json
import time
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

MASK_LABELS = {"NCR_NET": 1, "ED": 2, "ET": 4}
TARGET_SIZE = 128
RANDOM_SEED = 42
CLIP_SIGMA = 5.0
EXPECTED_CHANNELS = 4

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def get_device():
    if torch.cuda.is_available():
        device = torch.device("cuda")
        log.info("Using GPU: %s (VRAM: %.1f GB)", torch.cuda.get_device_name(0),
                 torch.cuda.get_device_properties(0).total_memory / 1e9)
    else:
        device = torch.device("cpu")
        log.warning("CUDA not available — using CPU only")
    return device


def load_splits(data_dir, npz_files):
    splits_path = os.path.join(data_dir, "dataset_splits.json")
    patient_ids = [os.path.splitext(os.path.basename(f))[0] for f in npz_files]

    if os.path.exists(splits_path):
        log.info("Found dataset_splits.json — using the dataset's own split")
        with open(splits_path) as f:
            splits = json.load(f)
        raw_train = splits.get("train", splits.get("Train", []))
        raw_val = splits.get("val", splits.get("validation", splits.get("Validation", [])))
        raw_test = splits.get("test", splits.get("Test", []))

        def _strip(ids):
            return set(os.path.splitext(x)[0] if x.endswith(".npz") else x for x in ids)

        return _strip(raw_train), _strip(raw_val), _strip(raw_test)

    log.warning("dataset_splits.json not found — generating deterministic 80/10/10 split (seed=%d)", RANDOM_SEED)
    rng = np.random.RandomState(RANDOM_SEED)
    shuffled = list(patient_ids)
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train, n_val = int(n * 0.8), int(n * 0.1)
    train_ids = set(shuffled[:n_train])
    val_ids = set(shuffled[n_train:n_train + n_val])
    test_ids = set(shuffled[n_train + n_val:])
    generated = {"train": sorted(train_ids), "val": sorted(val_ids), "test": sorted(test_ids)}
    with open(os.path.join(data_dir, "dataset_splits_generated.json"), "w") as f:
        json.dump(generated, f, indent=2)
    return train_ids, val_ids, test_ids


def validate_npz(data, patient_id):
    if "image" not in data or "mask" not in data:
        raise KeyError(f"{patient_id}: missing 'image' or 'mask' key")
    image, mask = data["image"], data["mask"]
    if image.ndim != 4 or image.shape[0] != EXPECTED_CHANNELS:
        raise ValueError(f"{patient_id}: bad image shape {image.shape}")
    if mask.ndim != 3 or image.shape[1:] != mask.shape:
        raise ValueError(f"{patient_id}: bad mask shape {mask.shape}")
    return image, mask


def resize_volume_gpu(volume_np, target_size, device, mode, normalize=False):
    added_channel = False
    if volume_np.ndim == 3:
        volume_np = volume_np[np.newaxis, ...]
        added_channel = True
    t = torch.from_numpy(volume_np.astype(np.float32)).unsqueeze(0).to(device)
    with torch.no_grad():
        if mode == "trilinear":
            out = F.interpolate(t, size=(target_size,) * 3, mode="trilinear", align_corners=False)
        else:
            out = F.interpolate(t, size=(target_size,) * 3, mode="nearest")

        out = out.squeeze(0)

        if normalize:
            C = out.shape[0]
            brain_mask = out != 0
            counts = brain_mask.sum(dim=(1, 2, 3))

            for c in range(C):
                if counts[c] < 100:
                    continue
                bm = brain_mask[c]
                brain_vals = out[c][bm]
                mu, sigma = brain_vals.mean(), brain_vals.std(unbiased=False)
                if sigma < 1e-8:
                    continue
                lo, hi = mu - CLIP_SIGMA * sigma, mu + CLIP_SIGMA * sigma
                out[c] = torch.clamp(out[c], min=lo.item(), max=hi.item())

                brain_clipped = out[c][bm]
                mu2, sigma2 = brain_clipped.mean(), brain_clipped.std(unbiased=False)
                if sigma2 >= 1e-8:
                    out[c] -= mu2
                    out[c] /= sigma2
                else:
                    out[c] -= mu2
                out[c][~bm] = 0.0

            return out.half().cpu()

    if added_channel:
        return torch.round(out[0]).to(torch.uint8).cpu()

    return out.half().cpu()


def derive_labels(mask):
    total_voxels = mask.size
    labels = {}
    for name, val in MASK_LABELS.items():
        count = int(np.sum(mask == val))
        labels[f"has_{name}"] = int(count > 0)
        labels[f"frac_{name}"] = round(count / total_voxels, 6)
    wt = int(np.sum(mask > 0))
    tc = int(np.sum((mask == 1) | (mask == 4)))
    et = int(np.sum(mask == 4))
    labels["frac_WT"] = round(wt / total_voxels, 6)
    labels["frac_TC"] = round(tc / total_voxels, 6)
    labels["frac_ET_composite"] = round(et / total_voxels, 6)
    labels["has_tumor"] = int(wt > 0)
    return labels


def sharded_path(out_dir, split_name, patient_id):
    digits = re.sub(r"\D", "", patient_id)
    bucket = digits[-2:] if len(digits) >= 2 else "00"
    return os.path.join(out_dir, "volumes", split_name, bucket, f"{patient_id}.pt")


def write_volume_cpu(image_tensor, mask_tensor, dst_path):
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    torch.save({"image": image_tensor, "mask": mask_tensor}, dst_path)


def process_split(npz_files, patient_ids_in_split, split_name, out_dir, target_size, device,
                   write_workers=2, accumulate_stats=False):
    files = [f for f in npz_files if os.path.splitext(os.path.basename(f))[0] in patient_ids_in_split]
    log.info("  %s: %d volumes to process (hybrid GPU resize + CPU write pipeline)", split_name, len(files))
    if not files:
        return pd.DataFrame(), [], None

    for b in range(100):
        os.makedirs(os.path.join(out_dir, "volumes", split_name, f"{b:02d}"), exist_ok=True)

    rows, errors = [], []
    start = time.time()

    running_sum = np.zeros(EXPECTED_CHANNELS, dtype=np.float64) if accumulate_stats else None
    running_sq = np.zeros(EXPECTED_CHANNELS, dtype=np.float64) if accumulate_stats else None
    stats_count = 0

    with ThreadPoolExecutor(max_workers=write_workers) as write_pool:
        pending_writes = []

        for i, npz_path in enumerate(files):
            patient_id = os.path.splitext(os.path.basename(npz_path))[0]
            dst = sharded_path(out_dir, split_name, patient_id)

            # ── RESUME LOGIC: skip volumes already processed in a prior run ──
            if os.path.exists(dst):
                try:
                    cached = torch.load(dst)
                    resized_mask_np = cached["mask"].numpy()
                    labels = derive_labels(resized_mask_np)
                    rows.append({"patient_id": patient_id, "volume_path": dst,
                                 "original_shape": "cached (resumed)", **labels})

                    # Still need this volume's contribution to channel stats
                    # if we're computing them, since a prior crashed run
                    # never got to save its in-memory accumulation.
                    if accumulate_stats:
                        img64 = cached["image"].to(torch.float64)
                        for c in range(EXPECTED_CHANNELS):
                            running_sum[c] += img64[c].sum().item()
                            running_sq[c] += (img64[c] ** 2).sum().item()
                        stats_count += 1
                        del img64

                    if (i + 1) % 25 == 0 or (i + 1) == len(files):
                        elapsed = time.time() - start
                        rate = (i + 1) / elapsed if elapsed > 0 else 0
                        log.info("    %s: %d/%d  (%.2f vol/s, resumed=cached)", split_name, i + 1, len(files), rate)
                    continue
                except Exception as e:
                    log.warning("  Cached file %s unreadable (%s) — reprocessing", dst, e)
                    # fall through to normal processing below

            try:
                with np.load(npz_path) as data:
                    image, mask = validate_npz(data, patient_id)
                    image = np.array(image)
                    mask = np.array(mask)
                orig_shape = f"{image.shape[1]}x{image.shape[2]}x{image.shape[3]}"

                normed_image = resize_volume_gpu(image, target_size, device, "trilinear", normalize=False)
                del image
                resized_mask = resize_volume_gpu(mask, target_size, device, "nearest", normalize=False)
                del mask

                if accumulate_stats:
                    img64 = normed_image.to(torch.float64)
                    for c in range(EXPECTED_CHANNELS):
                        running_sum[c] += img64[c].sum().item()
                        running_sq[c] += (img64[c] ** 2).sum().item()
                    stats_count += 1
                    del img64

                labels = derive_labels(resized_mask.numpy())

                future = write_pool.submit(write_volume_cpu, normed_image, resized_mask, dst)
                pending_writes.append((future, patient_id, dst, orig_shape, labels))

                if len(pending_writes) >= write_workers * 2:
                    fut, pid, d, osh, lbls = pending_writes.pop(0)
                    try:
                        fut.result()
                        rows.append({"patient_id": pid, "volume_path": d, "original_shape": osh, **lbls})
                    except Exception as e:
                        errors.append({"patient_id": pid, "error": str(e)})

                if device.type == "cuda" and (i + 1) % 25 == 0:
                    torch.cuda.empty_cache()

            except Exception as e:
                log.error("  SKIP %s: %s", patient_id, e)
                errors.append({"patient_id": patient_id, "error": str(e)})

            if (i + 1) % 25 == 0 or (i + 1) == len(files):
                elapsed = time.time() - start
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                log.info("    %s: %d/%d  (%.2f vol/s)", split_name, i + 1, len(files), rate)

        for fut, pid, d, osh, lbls in pending_writes:
            try:
                fut.result()
                rows.append({"patient_id": pid, "volume_path": d, "original_shape": osh, **lbls})
            except Exception as e:
                errors.append({"patient_id": pid, "error": str(e)})

    elapsed = time.time() - start
    log.info("  %s done: %d OK, %d errors  (%.1fs, %.2f vol/s avg)",
              split_name, len(rows), len(errors), elapsed, len(rows) / elapsed if elapsed > 0 else 0)

    acc_stats = None
    if accumulate_stats and stats_count > 0:
        acc_stats = {"running_sum": running_sum, "running_sq": running_sq, "n": stats_count}

    return pd.DataFrame(rows), errors, acc_stats


def compute_channel_stats_from_accumulated(out_dir, acc_stats, target_size):
    log.info("Finalizing per-channel mean/std from accumulated stats (%d volumes)...", acc_stats["n"])
    n = acc_stats["n"]
    voxel_count = target_size ** 3
    total = n * voxel_count
    means = acc_stats["running_sum"] / total
    stds = np.sqrt(acc_stats["running_sq"] / total - means ** 2)
    stats = {
        "channel_names": ["T1", "T1CE", "T2", "FLAIR"],
        "mean": means.tolist(), "std": stds.tolist(),
        "computed_from_n_volumes": n,
    }
    with open(os.path.join(out_dir, "channel_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    log.info("Saved channel stats.")
    return stats


def print_label_distribution(name, df):
    log.info("")
    log.info("%s set: %d volumes", name, len(df))
    if len(df) == 0:
        return
    for label in ["has_NCR_NET", "has_ED", "has_ET", "has_tumor"]:
        if label in df.columns:
            pos = df[label].sum()
            log.info("  %-16s %4d positive (%5.1f%%)", label, pos, 100 * pos / len(df))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, required=True)
    parser.add_argument("--out_dir", type=str, default="processed_brats")
    parser.add_argument("--target_size", type=int, default=TARGET_SIZE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write_workers", type=int, default=2)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--skip_stats", action="store_true")
    args = parser.parse_args()

    cwd = os.path.abspath(args.out_dir)
    if "onedrive" in cwd.lower() or "dropbox" in cwd.lower() or "google drive" in cwd.lower():
        log.warning("=" * 70)
        log.warning("OUTPUT PATH IS INSIDE A CLOUD-SYNCED FOLDER: %s", cwd)
        log.warning("Strongly consider pausing sync or moving --out_dir outside it.")
        log.warning("=" * 70)

    os.makedirs(args.out_dir, exist_ok=True)
    device = torch.device("cpu") if args.cpu else get_device()

    try:
        all_files = os.listdir(args.data_dir)
    except FileNotFoundError:
        log.error("Directory not found: %s", args.data_dir)
        sys.exit(1)
    npz_files = sorted([os.path.join(args.data_dir, f) for f in all_files
                         if f.startswith("BraTS2021_") and f.endswith(".npz")])
    log.info("Found %d patient volumes in %s", len(npz_files), args.data_dir)
    if not npz_files:
        log.error("No BraTS2021_*.npz files found")
        sys.exit(1)

    if args.limit:
        npz_files = npz_files[:args.limit]
        log.info("Limited to %d for this run", len(npz_files))

    train_ids, val_ids, test_ids = load_splits(args.data_dir, npz_files)
    log.info("Split sizes: train=%d, val=%d, test=%d", len(train_ids), len(val_ids), len(test_ids))

    total_start = time.time()
    all_errors = []
    train_df, errs, train_acc_stats = process_split(
        npz_files, train_ids, "train", args.out_dir, args.target_size, device,
        args.write_workers, accumulate_stats=(not args.skip_stats))
    all_errors.extend(errs)
    val_df, errs, _ = process_split(npz_files, val_ids, "val", args.out_dir, args.target_size, device, args.write_workers)
    all_errors.extend(errs)
    test_df, errs, _ = process_split(npz_files, test_ids, "test", args.out_dir, args.target_size, device, args.write_workers)
    all_errors.extend(errs)
    log.info("Total processing time: %.1fs", time.time() - total_start)

    print_label_distribution("Train", train_df)
    print_label_distribution("Val", val_df)
    print_label_distribution("Test", test_df)

    train_df.to_csv(os.path.join(args.out_dir, "train.csv"), index=False)
    val_df.to_csv(os.path.join(args.out_dir, "val.csv"), index=False)
    test_df.to_csv(os.path.join(args.out_dir, "test.csv"), index=False)

    if all_errors:
        with open(os.path.join(args.out_dir, "preprocessing_errors.json"), "w") as f:
            json.dump(all_errors, f, indent=2)
        log.warning("Saved %d errors to preprocessing_errors.json", len(all_errors))

    channel_stats = None
    if not args.skip_stats and train_acc_stats is not None:
        channel_stats = compute_channel_stats_from_accumulated(args.out_dir, train_acc_stats, args.target_size)

    metadata = {
        "dataset": "BraTS2021",
        "target_shape": [EXPECTED_CHANNELS, args.target_size, args.target_size, args.target_size],
        "modalities": ["T1", "T1CE", "T2", "FLAIR"],
        "mask_labels": MASK_LABELS,
        "classification_labels": ["has_NCR_NET", "has_ED", "has_ET", "has_tumor"],
        "splits": {"train": len(train_df), "val": len(val_df), "test": len(test_df)},
        "errors": len(all_errors),
        "channel_stats": channel_stats,
    }
    with open(os.path.join(args.out_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    log.info("Preprocessing complete! Train/Val/Test: %d / %d / %d", len(train_df), len(val_df), len(test_df))


if __name__ == "__main__":
    main()