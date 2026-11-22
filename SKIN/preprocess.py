
import os
import time
import argparse
from multiprocessing import Pool, cpu_count

from PIL import Image
import pandas as pd
from sklearn.model_selection import train_test_split

CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

VAL_SIZE = 0.15
TEST_SIZE = 0.15
RANDOM_SEED = 42
IMG_SIZE = 300
JPEG_QUALITY = 95


def build_image_lookup(data_dir):
    lookup = {}
    for folder in ["HAM10000_images_part_1", "HAM10000_images_part_2"]:
        folder_path = os.path.join(data_dir, folder)
        if not os.path.isdir(folder_path):
            print(f"Warning: folder not found: {folder_path}")
            continue
        for fname in os.listdir(folder_path):
            if fname.lower().endswith((".jpg", ".jpeg", ".png")):
                img_id = os.path.splitext(fname)[0]
                lookup[img_id] = os.path.join(folder_path, fname)
    return lookup


def load_and_clean_metadata(data_dir, image_lookup):
    csv_path = os.path.join(data_dir, "HAM10000_metadata.csv")
    df = pd.read_csv(csv_path)
    print(f"Loaded metadata: {len(df)} rows")

    df["image_path"] = df["image_id"].map(image_lookup)

    missing = df["image_path"].isna().sum()
    if missing > 0:
        print(f"Warning: {missing} rows have no matching image file — dropping them")
        df = df.dropna(subset=["image_path"])

    unknown = ~df["dx"].isin(CLASSES)
    if unknown.sum() > 0:
        print(f"Warning: {unknown.sum()} rows have unrecognized dx labels — dropping them")
        df = df[~unknown]

    df["label"] = df["dx"].map(CLASS_TO_IDX)
    return df.reset_index(drop=True)


def split_by_lesion(df):
    """Split so all images of the same lesion_id stay in one split,
    stratified by class so rare classes appear in every split."""
    lesion_class = df.groupby("lesion_id")["dx"].first()
    lesion_ids = lesion_class.index.values
    lesion_labels = lesion_class.values

    train_ids, temp_ids, train_labels, temp_labels = train_test_split(
        lesion_ids, lesion_labels,
        test_size=(VAL_SIZE + TEST_SIZE),
        stratify=lesion_labels,
        random_state=RANDOM_SEED,
    )
    val_ids, test_ids = train_test_split(
        temp_ids,
        test_size=TEST_SIZE / (VAL_SIZE + TEST_SIZE),
        stratify=temp_labels,
        random_state=RANDOM_SEED,
    )

    train_df = df[df["lesion_id"].isin(train_ids)].reset_index(drop=True)
    val_df = df[df["lesion_id"].isin(val_ids)].reset_index(drop=True)
    test_df = df[df["lesion_id"].isin(test_ids)].reset_index(drop=True)
    return train_df, val_df, test_df


def _resize_one(args):
    """Worker function: resize a single image and save it.
    Runs in a separate process — must be a top-level function (picklable)."""
    src_path, dst_path, img_size, overwrite = args
    try:
        # Skip only if file exists AND matches target size (avoids the
        # silent stale-resize bug from checking existence alone)
        if os.path.exists(dst_path) and not overwrite:
            with Image.open(dst_path) as existing:
                if existing.size == (img_size, img_size):
                    return ("skipped", None)

        with Image.open(src_path) as img:
            img = img.convert("RGB")  # force RGB, handles grayscale/RGBA sources
            img = img.resize((img_size, img_size), Image.LANCZOS)  # antialiased downsize
            img.save(dst_path, "JPEG", quality=JPEG_QUALITY)
        return ("ok", None)
    except Exception as e:
        return ("error", f"{src_path}: {e}")


def process_images(df, split_name, out_dir, img_size=IMG_SIZE, workers=None, overwrite=False):
    split_dir = os.path.join(out_dir, split_name)
    for cls in CLASSES:
        os.makedirs(os.path.join(split_dir, cls), exist_ok=True)

    tasks = []
    new_paths = [""] * len(df)
    for i, (idx, row) in enumerate(df.iterrows()):
        src_path = row["image_path"]
        class_name = row["dx"]
        filename = os.path.basename(src_path)
        dst_path = os.path.join(split_dir, class_name, filename)
        new_paths[i] = dst_path
        tasks.append((src_path, dst_path, img_size, overwrite))

    workers = workers or max(1, cpu_count() - 1)
    print(f"\n  {split_name}: resizing {len(tasks)} images with {workers} worker processes...")

    start = time.time()
    ok, skipped, errors = 0, 0, []
    with Pool(processes=workers) as pool:
        for i, (status, err) in enumerate(pool.imap_unordered(_resize_one, tasks, chunksize=32)):
            if status == "ok":
                ok += 1
            elif status == "skipped":
                skipped += 1
            else:
                errors.append(err)

            if (i + 1) % 200 == 0 or (i + 1) == len(tasks):
                elapsed = time.time() - start
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"\r    {i+1}/{len(tasks)} ({rate:.0f} img/s)", end="", flush=True)

    elapsed = time.time() - start
    print(f"\n  {split_name} done: {ok} resized, {skipped} already existed, "
          f"{len(errors)} errors  ({elapsed:.1f}s)")
    for err in errors[:10]:
        print(f"    ERROR: {err}")

    df = df.copy()
    df["image_path"] = new_paths
    return df


def print_class_distribution(name, df):
    print(f"\n{name} set: {len(df)} images")
    counts = df["dx"].value_counts().reindex(CLASSES, fill_value=0)
    for cls, count in counts.items():
        pct = 100 * count / len(df) if len(df) else 0
        print(f"  {cls:6s}: {count:5d} ({pct:5.1f}%)")


def suggest_class_weights(train_df):
    counts = train_df["dx"].value_counts().reindex(CLASSES, fill_value=1)
    weights = (1.0 / counts) * counts.sum() / len(CLASSES)
    print("\nSuggested class weights (for CrossEntropyLoss):")
    for cls in CLASSES:
        print(f"  {cls:6s}: {weights[cls]:.3f}")
    return weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, required=True)
    parser.add_argument("--out_dir", type=str, default="processed")
    parser.add_argument("--img_size", type=int, default=IMG_SIZE)
    parser.add_argument("--workers", type=int, default=None,
                         help="Number of worker processes (default: CPU count - 1)")
    parser.add_argument("--overwrite", action="store_true",
                         help="Force re-resize even if output file already exists at target size")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print("Locating images...")
    image_lookup = build_image_lookup(args.data_dir)
    print(f"Found {len(image_lookup)} image files")

    df = load_and_clean_metadata(args.data_dir, image_lookup)
    print(f"\nUnique lesions: {df['lesion_id'].nunique()}")
    print(f"Total usable images: {len(df)}")

    train_df, val_df, test_df = split_by_lesion(df)

    total_start = time.time()
    print(f"\nResizing images to {args.img_size}x{args.img_size} ...")
    train_df = process_images(train_df, "train", args.out_dir, args.img_size, args.workers, args.overwrite)
    val_df = process_images(val_df, "val", args.out_dir, args.img_size, args.workers, args.overwrite)
    test_df = process_images(test_df, "test", args.out_dir, args.img_size, args.workers, args.overwrite)
    print(f"\nTotal processing time: {time.time() - total_start:.1f}s")

    print_class_distribution("Train", train_df)
    print_class_distribution("Val", val_df)
    print_class_distribution("Test", test_df)
    suggest_class_weights(train_df)

    train_df.to_csv(os.path.join(args.out_dir, "train.csv"), index=False)
    val_df.to_csv(os.path.join(args.out_dir, "val.csv"), index=False)
    test_df.to_csv(os.path.join(args.out_dir, "test.csv"), index=False)

    print(f"\nSaved ImageFolder structure + CSVs to: {args.out_dir}/")
    print("Preprocessing complete. Ready for fine-tuning EfficientNet-B3.")


if __name__ == "__main__":
    main()