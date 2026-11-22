
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from PIL import Image


def check_image(path):
    try:
        with Image.open(path) as img:
            img.verify()  # checks file integrity without fully decoding
        # verify() closes the file, need to reopen to actually load pixel data
        with Image.open(path) as img:
            img.convert("RGB")
        return True
    except Exception:
        return False


def clean_csv(csv_path, workers, delete_bad_files):
    df = pd.read_csv(csv_path)
    print(f"\nChecking {csv_path} ({len(df)} images)...")

    bad_indices = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_image, row["image_path"]): idx
                   for idx, row in df.iterrows()}
        done = 0
        for future in as_completed(futures):
            idx = futures[future]
            ok = future.result()
            if not ok:
                bad_indices.append(idx)
            done += 1
            if done % 5000 == 0 or done == len(df):
                print(f"\r  {done}/{len(df)} checked, {len(bad_indices)} bad so far", end="", flush=True)

    print(f"\n  Found {len(bad_indices)} corrupted/unreadable images")

    if bad_indices:
        for idx in bad_indices:
            path = df.iloc[idx]["image_path"]
            print(f"    BAD: {path}")
            if delete_bad_files and os.path.exists(path):
                os.remove(path)

        clean_df = df.drop(index=bad_indices).reset_index(drop=True)
        clean_df.to_csv(csv_path, index=False)
        print(f"  Removed {len(bad_indices)} rows, saved cleaned {csv_path} ({len(clean_df)} rows remain)")
    else:
        print("  All images OK, no changes needed.")

    return len(bad_indices)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="processed_chexpert")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--delete_bad_files", action="store_true",
                         help="Also delete the corrupted files from disk (so a rerun of "
                              "preprocessing with --overwrite would regenerate them)")
    args = parser.parse_args()

    total_bad = 0
    for split in ["train.csv", "val.csv", "test.csv"]:
        csv_path = os.path.join(args.data_dir, split)
        if os.path.exists(csv_path):
            total_bad += clean_csv(csv_path, args.workers, args.delete_bad_files)

    print(f"\nDone. Total bad images removed across all splits: {total_bad}")
    if total_bad > 0 and not args.delete_bad_files:
        print("Tip: rerun with --delete_bad_files if you also want the corrupt files "
              "removed from disk (e.g. before re-running preprocessing to regenerate them).")


if __name__ == "__main__":
    main()