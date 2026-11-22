

import os
import json
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
import timm
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from sklearn.metrics import roc_auc_score


# ---------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------

class CheXpertDataset(Dataset):
    def __init__(self, csv_path, labels, transform=None):
        import pandas as pd
        import os
        df = pd.read_csv(csv_path)
        # Filter out any missing files on disk automatically
        exists_mask = df["image_path"].apply(os.path.isfile)
        if not exists_mask.all():
            missing_count = (~exists_mask).sum()
            print(f"[{os.path.basename(csv_path)}] Filtered out {missing_count} missing images from dataset.")
            df = df[exists_mask].reset_index(drop=True)
        self.df = df
        self.labels = labels
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        image = Image.open(row["image_path"]).convert("RGB")
        target = torch.tensor(row[self.labels].values.astype("float32"))
        if self.transform:
            image = self.transform(image)
        return image, target


def get_transforms(img_size, mean, std):
    # No horizontal flip — chest X-ray anatomy isn't left-right symmetric.
    # Mild rotation/translation/brightness only, since medical images
    # need conservative augmentation to avoid destroying diagnostic signal.
    train_tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.RandomRotation(10),
        transforms.RandomAffine(degrees=0, translate=(0.05, 0.05), scale=(0.95, 1.05)),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
        transforms.RandomErasing(p=0.1, scale=(0.02, 0.1)),  # Simulates occlusion
    ])
    eval_tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])
    return train_tf, eval_tf


# ---------------------------------------------------------------------
# EMA (Exponential Moving Average)
# ---------------------------------------------------------------------

class EMA:
    """Exponential Moving Average of model weights for smoother evaluation.

    Keeps a shadow copy of the model parameters that is updated as:
        shadow = decay * shadow + (1 - decay) * current_params

    Use apply()/restore() to swap EMA weights in for evaluation.
    """

    def __init__(self, model, decay=0.999):
        self.decay = decay
        self.shadow = {}
        for name, param in model.named_parameters():
            if param.requires_grad:
                self.shadow[name] = param.data.clone()

    @torch.no_grad()
    def update(self, model):
        """Update shadow params toward current model params."""
        for name, param in model.named_parameters():
            if param.requires_grad and name in self.shadow:
                self.shadow[name].mul_(self.decay).add_(param.data, alpha=1.0 - self.decay)

    def apply(self, model):
        """Swap model params with EMA params. Returns backup for restore()."""
        backup = {}
        for name, param in model.named_parameters():
            if name in self.shadow:
                backup[name] = param.data.clone()
                param.data.copy_(self.shadow[name])
        return backup

    def restore(self, model, backup):
        """Restore original (non-EMA) params from backup."""
        for name, param in model.named_parameters():
            if name in backup:
                param.data.copy_(backup[name])


# ---------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------

def build_model(checkpoint_path, num_classes, device):
    """Build DenseNet-121 with proper checkpoint loading and head replacement.

    Auto-detects whether the checkpoint is ImageNet (1000-class) or already
    fine-tuned (num_classes). Handles both cases correctly.

    Returns:
        (model, backbone_params, head_params) — separated for differential LR.
    """
    if checkpoint_path and os.path.exists(checkpoint_path):
        print(f"Loading pretrained checkpoint: {checkpoint_path}")
        state_dict = torch.load(checkpoint_path, map_location=device, weights_only=True)

        # Detect checkpoint type by classifier weight shape
        clf_key = "classifier.weight"
        if clf_key in state_dict:
            ckpt_classes = state_dict[clf_key].shape[0]
        else:
            ckpt_classes = 1000  # Assume ImageNet if key missing

        if ckpt_classes == num_classes:
            # Checkpoint is already fine-tuned for our task — load directly
            print(f"  Checkpoint has {ckpt_classes} classes (matches target) — loading directly")
            model = timm.create_model("densenet121", pretrained=False, num_classes=num_classes)
            model.load_state_dict(state_dict, strict=True)
        else:
            # Checkpoint is ImageNet or different num_classes — load backbone, swap head
            print(f"  Checkpoint has {ckpt_classes} classes — loading backbone, replacing head")
            model = timm.create_model("densenet121", pretrained=False, num_classes=ckpt_classes)
            model.load_state_dict(state_dict, strict=True)
            in_features = model.classifier.in_features
            model.classifier = nn.Linear(in_features, num_classes)
            nn.init.xavier_uniform_(model.classifier.weight)
            nn.init.zeros_(model.classifier.bias)
    else:
        print("No local checkpoint found — using timm's pretrained ImageNet weights")
        model = timm.create_model("densenet121", pretrained=True, num_classes=1000)
        in_features = model.classifier.in_features
        model.classifier = nn.Linear(in_features, num_classes)
        nn.init.xavier_uniform_(model.classifier.weight)
        nn.init.zeros_(model.classifier.bias)

    model = model.to(device)

    # Separate parameter groups for differential learning rate
    head_params = list(model.classifier.parameters())
    head_param_ids = {id(p) for p in head_params}
    backbone_params = [p for p in model.parameters() if id(p) not in head_param_ids]

    return model, backbone_params, head_params


# ---------------------------------------------------------------------
# Train / eval
# ---------------------------------------------------------------------

def train_one_epoch(model, loader, optimizer, criterion, device, scaler,
                    scheduler=None, ema=None, accum_steps=1):
    """Train for one epoch with gradient accumulation, per-step scheduling, and EMA."""
    model.train()
    total_loss = 0.0
    optimizer.zero_grad(set_to_none=True)

    for step, (images, targets) in enumerate(loader):
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)

        with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
            outputs = model(images)
            loss = criterion(outputs, targets) / accum_steps  # Scale for accumulation

        scaler.scale(loss).backward()

        # Optimizer step after accumulating gradients
        if (step + 1) % accum_steps == 0 or (step + 1) == len(loader):
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)

            if scheduler is not None:
                scheduler.step()

            if ema is not None:
                ema.update(model)

        total_loss += loss.item() * accum_steps * images.size(0)

    return total_loss / len(loader.dataset)


def evaluate(model, loader, criterion, device, labels):
    model.eval()
    total_loss = 0
    all_probs, all_targets = [], []
    with torch.no_grad():
        for images, targets in loader:
            images, targets = images.to(device, non_blocking=True), targets.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                outputs = model(images)
                loss = criterion(outputs, targets)
            total_loss += loss.item() * images.size(0)
            probs = torch.sigmoid(outputs).cpu().numpy()
            all_probs.append(probs)
            all_targets.append(targets.cpu().numpy())

    avg_loss = total_loss / len(loader.dataset)
    all_probs = np.concatenate(all_probs, axis=0)
    all_targets = np.concatenate(all_targets, axis=0)

    per_label_auroc = {}
    for i, label in enumerate(labels):
        y_true = all_targets[:, i]
        y_score = all_probs[:, i]
        # AUROC is undefined if a label has only one class present
        # (e.g. all-negative in a small val/test set) — skip gracefully.
        if len(np.unique(y_true)) < 2:
            per_label_auroc[label] = float("nan")
        else:
            per_label_auroc[label] = roc_auc_score(y_true, y_score)

    valid_aurocs = [v for v in per_label_auroc.values() if not np.isnan(v)]
    mean_auroc = float(np.mean(valid_aurocs)) if valid_aurocs else float("nan")

    return avg_loss, mean_auroc, per_label_auroc


def print_auroc_table(per_label_auroc):
    for label, auroc in per_label_auroc.items():
        val_str = f"{auroc:.4f}" if not np.isnan(auroc) else "N/A (single class)"
        print(f"    {label:28s}: {val_str}")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune DenseNet-121 on CheXpert with differential LR, EMA, and gradient accumulation",
    )
    parser.add_argument("--data_dir", type=str, default="processed_chexpert")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/densenet121_imagenet.pth")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4,
                        help="Learning rate for classifier head (default: 1e-4)")
    parser.add_argument("--backbone_lr_factor", type=float, default=0.1,
                        help="Backbone LR = lr × this factor (default: 0.1 → 10× lower)")
    parser.add_argument("--weight_decay", type=float, default=1e-5)
    parser.add_argument("--num_workers", type=int, default=4)
    parser.add_argument("--out_dir", type=str, default="checkpoints")
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--accum_steps", type=int, default=2,
                        help="Gradient accumulation steps (effective batch = batch_size × accum_steps)")
    parser.add_argument("--ema_decay", type=float, default=0.999,
                        help="EMA decay rate (0 to disable EMA)")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    # --- Load metadata (normalization, pos_weights, labels, img_size) ---
    meta_path = os.path.join(args.data_dir, "metadata.json")
    with open(meta_path) as f:
        metadata = json.load(f)

    labels = metadata["labels"]
    num_classes = metadata["num_classes"]
    img_size = metadata["preprocessing"]["img_size"]
    mean = metadata["normalization"]["mean"]
    std = metadata["normalization"]["std"]
    pos_weights = torch.tensor(metadata["pos_weights_list"], dtype=torch.float32).to(device)

    print(f"Loaded metadata: {num_classes} labels, img_size={img_size}")

    # --- Data ---
    train_tf, eval_tf = get_transforms(img_size, mean, std)
    train_ds = CheXpertDataset(os.path.join(args.data_dir, "train.csv"), labels, train_tf)
    val_ds = CheXpertDataset(os.path.join(args.data_dir, "val.csv"), labels, eval_tf)
    test_ds = CheXpertDataset(os.path.join(args.data_dir, "test.csv"), labels, eval_tf)

    eff_batch = args.batch_size * args.accum_steps
    print(f"Train: {len(train_ds)} | Val: {len(val_ds)} | Test: {len(test_ds)}")
    print(f"Effective batch size: {args.batch_size} × {args.accum_steps} = {eff_batch}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                               num_workers=args.num_workers, pin_memory=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                             num_workers=args.num_workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False,
                              num_workers=args.num_workers, pin_memory=True)

    # --- Model with differential LR ---
    model, backbone_params, head_params = build_model(args.checkpoint, num_classes, device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weights)

    backbone_lr = args.lr * args.backbone_lr_factor
    optimizer = torch.optim.AdamW([
        {"params": backbone_params, "lr": backbone_lr},
        {"params": head_params,     "lr": args.lr},
    ], weight_decay=args.weight_decay)

    print(f"Learning rates — backbone: {backbone_lr:.1e}, head: {args.lr:.1e}")

    # OneCycleLR: built-in warmup (10%) + cosine decay, works with early stopping
    steps_per_epoch = (len(train_loader) + args.accum_steps - 1) // args.accum_steps
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=[backbone_lr, args.lr],
        epochs=args.epochs,
        steps_per_epoch=steps_per_epoch,
        pct_start=0.1,          # 10% of training for warmup
        anneal_strategy="cos",
    )

    scaler = torch.amp.GradScaler(enabled=(device.type == "cuda"))

    # --- EMA ---
    ema = EMA(model, decay=args.ema_decay) if args.ema_decay > 0 else None
    if ema:
        print(f"EMA enabled (decay={args.ema_decay})")

    best_mean_auroc = 0.0
    epochs_without_improvement = 0
    best_path = os.path.join(args.out_dir, "densenet121_chexpert_best.pth")

    for epoch in range(args.epochs):
        start = time.time()

        train_loss = train_one_epoch(
            model, train_loader, optimizer, criterion, device, scaler,
            scheduler=scheduler, ema=ema, accum_steps=args.accum_steps,
        )

        # Evaluate with EMA weights if available
        if ema:
            ema_backup = ema.apply(model)

        val_loss, val_mean_auroc, val_per_label = evaluate(
            model, val_loader, criterion, device, labels,
        )

        elapsed = time.time() - start

        # Log current LR (from head param group) for debugging
        current_lr = optimizer.param_groups[1]["lr"]
        print(f"\nEpoch {epoch+1}/{args.epochs} | "
              f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | "
              f"Val Mean AUROC: {val_mean_auroc:.4f} | "
              f"LR: {current_lr:.2e} | {elapsed:.1f}s")

        if val_mean_auroc > best_mean_auroc:
            best_mean_auroc = val_mean_auroc
            epochs_without_improvement = 0
            # Save EMA weights (or regular weights if EMA disabled)
            torch.save(model.state_dict(), best_path)
            print(f"  -> New best model saved (mean AUROC: {best_mean_auroc:.4f})")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"\nNo improvement for {args.patience} epochs — stopping early.")
                if ema:
                    ema.restore(model, ema_backup)
                break

        # Restore non-EMA weights for continued training
        if ema:
            ema.restore(model, ema_backup)

    print(f"\nTraining complete. Best val mean AUROC: {best_mean_auroc:.4f}")
    print(f"Best model saved to: {best_path}")

    # --- Final validation report ---
    print("\nFinal validation per-label AUROC (best checkpoint):")
    model.load_state_dict(torch.load(best_path, map_location=device, weights_only=True))
    _, val_mean_auroc, val_per_label = evaluate(model, val_loader, criterion, device, labels)
    print(f"  Mean AUROC: {val_mean_auroc:.4f}")
    print_auroc_table(val_per_label)

    # --- Final test report (small official test set — interpret with caution) ---
    print(f"\nFinal TEST set per-label AUROC ({len(test_ds)} images — small, high variance):")
    _, test_mean_auroc, test_per_label = evaluate(model, test_loader, criterion, device, labels)
    print(f"  Mean AUROC: {test_mean_auroc:.4f}")
    print_auroc_table(test_per_label)


if __name__ == "__main__":
    main()