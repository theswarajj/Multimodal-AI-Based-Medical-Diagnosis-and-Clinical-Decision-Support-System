

import os
import copy
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import timm
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets, transforms
from sklearn.metrics import balanced_accuracy_score, classification_report

CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
IMG_SIZE = 300
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


# ---------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------

def get_transforms():
    train_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(25),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.15, hue=0.02),
        transforms.RandomAffine(degrees=0, translate=(0.05, 0.05), scale=(0.9, 1.1)),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
        transforms.RandomErasing(p=0.2, scale=(0.02, 0.1)),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    return train_tf, eval_tf


def make_weighted_sampler(dataset):
    """Oversample rare classes so each batch sees roughly balanced classes."""
    targets = np.array(dataset.targets)
    class_counts = np.bincount(targets)
    class_weights = 1.0 / class_counts
    sample_weights = class_weights[targets]
    return WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)


# ---------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------

def build_model(checkpoint_path, device, drop_rate=0.4, drop_path_rate=0.2):
    use_pretrained = checkpoint_path is None or not os.path.exists(checkpoint_path)
    model = timm.create_model(
        "efficientnet_b3",
        pretrained=use_pretrained,
        num_classes=len(CLASSES),
        drop_rate=drop_rate,          # dropout before classifier head
        drop_path_rate=drop_path_rate,  # stochastic depth, strong regularizer
    )
    if not use_pretrained:
        print(f"Loading pretrained checkpoint: {checkpoint_path}")
        state_dict = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(state_dict, strict=False)
    return model.to(device)


def set_backbone_trainable(model, trainable: bool):
    """Freeze/unfreeze everything except the final classifier layer."""
    for name, param in model.named_parameters():
        if "classifier" in name or "fc" in name:
            param.requires_grad = True
        else:
            param.requires_grad = trainable


# ---------------------------------------------------------------------
# MixUp
# ---------------------------------------------------------------------

def mixup_data(x, y, alpha=0.2, device="cuda"):
    lam = np.random.beta(alpha, alpha) if alpha > 0 else 1.0
    index = torch.randperm(x.size(0)).to(device)
    mixed_x = lam * x + (1 - lam) * x[index]
    return mixed_x, y, y[index], lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ---------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------

class ModelEMA:
    """Exponential moving average of model weights."""
    def __init__(self, model, decay=0.999):
        self.ema = copy.deepcopy(model).eval()
        for p in self.ema.parameters():
            p.requires_grad_(False)
        self.decay = decay

    @torch.no_grad()
    def update(self, model):
        for ema_p, p in zip(self.ema.state_dict().values(), model.state_dict().values()):
            if ema_p.dtype.is_floating_point:
                ema_p.mul_(self.decay).add_(p.detach(), alpha=1 - self.decay)
            else:
                ema_p.copy_(p)


# ---------------------------------------------------------------------
# Train / eval loops
# ---------------------------------------------------------------------

def train_one_epoch(model, loader, optimizer, criterion, device, scaler, ema, use_mixup, clip_grad=1.0):
    model.train()
    total_loss = 0
    for images, labels in loader:
        images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
        optimizer.zero_grad()

        with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
            if use_mixup:
                mixed_images, y_a, y_b, lam = mixup_data(images, labels, alpha=0.2, device=device)
                outputs = model(mixed_images)
                loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
            else:
                outputs = model(images)
                loss = criterion(outputs, labels)

        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip_grad)
        scaler.step(optimizer)
        scaler.update()

        if ema is not None:
            ema.update(model)

        total_loss += loss.item() * images.size(0)
    return total_loss / len(loader.dataset)


def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0
    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                outputs = model(images)
                loss = criterion(outputs, labels)
            total_loss += loss.item() * images.size(0)
            preds = outputs.argmax(1).cpu().numpy()
            all_preds.extend(preds)
            all_labels.extend(labels.cpu().numpy())
    avg_loss = total_loss / len(loader.dataset)
    bal_acc = balanced_accuracy_score(all_labels, all_preds)
    return avg_loss, bal_acc, all_labels, all_preds


def get_lr_lambda(epoch, warmup_epochs, total_epochs):
    if epoch < warmup_epochs:
        return (epoch + 1) / warmup_epochs
    progress = (epoch - warmup_epochs) / max(1, total_epochs - warmup_epochs)
    return 0.5 * (1 + np.cos(np.pi * progress))


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="processed")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/efficientnet_b3_imagenet.pth")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--freeze_epochs", type=int, default=5, help="Epochs to train head only before unfreezing backbone")
    parser.add_argument("--warmup_epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr_head", type=float, default=3e-4)
    parser.add_argument("--lr_backbone", type=float, default=3e-5)
    parser.add_argument("--weight_decay", type=float, default=5e-4)
    parser.add_argument("--label_smoothing", type=float, default=0.1)
    parser.add_argument("--num_workers", type=int, default=4)
    parser.add_argument("--out_dir", type=str, default="checkpoints")
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--no_mixup", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    train_tf, eval_tf = get_transforms()
    train_ds = datasets.ImageFolder(os.path.join(args.data_dir, "train"), transform=train_tf)
    val_ds = datasets.ImageFolder(os.path.join(args.data_dir, "val"), transform=eval_tf)
    print(f"Train images: {len(train_ds)} | Val images: {len(val_ds)}")
    print(f"Class mapping: {train_ds.class_to_idx}")

    sampler = make_weighted_sampler(train_ds)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, sampler=sampler,
                               num_workers=args.num_workers, pin_memory=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                             num_workers=args.num_workers, pin_memory=True)

    model = build_model(args.checkpoint, device)

    # Phase 1: freeze backbone, train head only
    set_backbone_trainable(model, trainable=False)

    criterion = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr_head, weight_decay=args.weight_decay)
    scaler = torch.amp.GradScaler(enabled=(device.type == "cuda"))
    ema = ModelEMA(model, decay=0.999)

    best_bal_acc = 0
    epochs_without_improvement = 0
    best_path = os.path.join(args.out_dir, "efficientnet_b3_ham10000_v2_best.pth")
    backbone_unfrozen = False

    for epoch in range(args.epochs):
        start = time.time()

        # Unfreeze backbone after warmup phase, switch to discriminative LR
        if epoch == args.freeze_epochs and not backbone_unfrozen:
            print(f"\n>>> Unfreezing backbone at epoch {epoch+1}, switching to discriminative LR")
            set_backbone_trainable(model, trainable=True)
            backbone_params = [p for n, p in model.named_parameters() if "classifier" not in n]
            head_params = [p for n, p in model.named_parameters() if "classifier" in n]
            optimizer = torch.optim.AdamW([
                {"params": backbone_params, "lr": args.lr_backbone},
                {"params": head_params, "lr": args.lr_head},
            ], weight_decay=args.weight_decay)
            backbone_unfrozen = True

        # Apply warmup + cosine decay on top of each param group's base LR.
        # Param group order matches how optimizer was constructed:
        #   frozen phase  -> single group @ lr_head
        #   unfrozen phase -> [backbone @ lr_backbone, head @ lr_head]
        lr_scale = get_lr_lambda(epoch, args.warmup_epochs, args.epochs)
        base_lrs = [args.lr_backbone, args.lr_head] if backbone_unfrozen else [args.lr_head]
        for g, base_lr in zip(optimizer.param_groups, base_lrs):
            g["lr"] = base_lr * lr_scale

        use_mixup = (not args.no_mixup) and epoch >= args.warmup_epochs
        train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device, scaler, ema, use_mixup)

        val_loss, val_bal_acc, labels, preds = evaluate(model, val_loader, criterion, device)
        ema_val_loss, ema_val_bal_acc, ema_labels, ema_preds = evaluate(ema.ema, val_loader, criterion, device)

        elapsed = time.time() - start
        print(f"Epoch {epoch+1}/{args.epochs} | "
              f"Train Loss: {train_loss:.4f} | "
              f"Val Bal Acc: {val_bal_acc:.4f} | "
              f"EMA Val Bal Acc: {ema_val_bal_acc:.4f} | "
              f"{elapsed:.1f}s"
              f"{'  [frozen]' if not backbone_unfrozen else ''}")

        # Track best across both regular and EMA weights
        candidate_acc = max(val_bal_acc, ema_val_bal_acc)
        if candidate_acc > best_bal_acc:
            best_bal_acc = candidate_acc
            epochs_without_improvement = 0
            save_model = ema.ema if ema_val_bal_acc >= val_bal_acc else model
            torch.save(save_model.state_dict(), best_path)
            print(f"  -> New best model saved (balanced acc: {best_bal_acc:.4f}"
                  f"{' [EMA]' if ema_val_bal_acc >= val_bal_acc else ' [raw]'})")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"\nNo improvement for {args.patience} epochs — stopping early.")
                break

    print(f"\nTraining complete. Best val balanced accuracy: {best_bal_acc:.4f}")
    print(f"Best model saved to: {best_path}")

    print("\nFinal validation classification report (best checkpoint):")
    final_model = build_model(None, device)
    final_model.load_state_dict(torch.load(best_path, map_location=device))
    _, _, labels, preds = evaluate(final_model, val_loader, criterion, device)
    idx_to_class = {v: k for k, v in train_ds.class_to_idx.items()}
    target_names = [idx_to_class[i] for i in range(len(idx_to_class))]
    print(classification_report(labels, preds, target_names=target_names, zero_division=0))


if __name__ == "__main__":
    main()