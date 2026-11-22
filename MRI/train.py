

import os

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import re
import sys
import json
import time
import math
import logging
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.amp import autocast, GradScaler
import torchvision.models.video as models

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  1.  DATASET — reads the exact .pt format from preprocess.py
# ═══════════════════════════════════════════════════════════════════════════════
class BraTSDataset(Dataset):
    """
    Reads preprocessed .pt volumes produced by preprocess.py.

    Each .pt file contains:
        image : float16 tensor [4, 128, 128, 128]   (T1, T1ce, T2, FLAIR)
        mask  : uint8   tensor [128, 128, 128]       (NCR_NET=1, ED=2, ET=4)

    The CSV manifest (train.csv, val.csv, test.csv) provides:
        patient_id, volume_path, has_tumor, has_NCR_NET, has_ED, has_ET, ...
    """

    def __init__(self, csv_path, label_col="has_tumor", channel_mean=None,
                 channel_std=None, augment=False):
        self.df = pd.read_csv(csv_path)
        self.label_col = label_col
        self.augment = augment

        # Channel-wise normalization (from channel_stats.json)
        self.channel_mean = (
            torch.tensor(channel_mean, dtype=torch.float32).view(4, 1, 1, 1)
            if channel_mean else None
        )
        self.channel_std = (
            torch.tensor(channel_std, dtype=torch.float32).view(4, 1, 1, 1)
            if channel_std else None
        )

        # Validate paths exist
        missing = self.df[~self.df["volume_path"].apply(os.path.exists)]
        if len(missing) > 0:
            log.warning("%d volume paths missing — they will be skipped", len(missing))
            self.df = self.df[self.df["volume_path"].apply(os.path.exists)].reset_index(drop=True)

        log.info("Dataset loaded: %d samples from %s  (label=%s, augment=%s)",
                 len(self.df), csv_path, label_col, augment)

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        data = torch.load(row["volume_path"], weights_only=True)

        # image: [4, 128, 128, 128] float16 → float32
        image = data["image"].float()

        # Channel-wise normalization
        if self.channel_mean is not None and self.channel_std is not None:
            image = (image - self.channel_mean) / (self.channel_std + 1e-8)

        # 3D augmentations (training only) — all are GPU-free, fast tensor ops
        if self.augment:
            image = self._augment_3d(image)

        label = int(row[self.label_col])
        return image, label

    @staticmethod
    def _augment_3d(image):
        """
        Lightweight 3D augmentations for medical volumes.
        All operations work on [C, D, H, W] tensors.
        """
        # Random horizontal flip (along W axis)
        if torch.rand(1).item() > 0.5:
            image = torch.flip(image, dims=[3])

        # Random vertical flip (along H axis) — less common but useful for brain
        if torch.rand(1).item() > 0.5:
            image = torch.flip(image, dims=[2])

        # Random axial flip (along D axis)
        if torch.rand(1).item() > 0.5:
            image = torch.flip(image, dims=[1])

        # Random intensity shift per channel (±5%)
        if torch.rand(1).item() > 0.5:
            shift = (torch.rand(4, 1, 1, 1) - 0.5) * 0.1  # [-0.05, +0.05]
            image = image + shift

        # Random intensity scale per channel (0.9–1.1×)
        if torch.rand(1).item() > 0.5:
            scale = 0.9 + torch.rand(4, 1, 1, 1) * 0.2     # [0.9, 1.1]
            image = image * scale

        # Additive Gaussian noise (σ = 0.01)
        if torch.rand(1).item() > 0.3:
            noise = torch.randn_like(image) * 0.01
            image = image + noise

        return image


# ═══════════════════════════════════════════════════════════════════════════════
#  2.  MODEL — reconstruct the exact same architecture from download.py
# ═══════════════════════════════════════════════════════════════════════════════
def build_model(weights_path, num_classes=2, freeze_backbone=True):
    """
    Reconstruct the adapted 3D ResNet-18 and load saved weights.

    The architecture MUST match download.py exactly:
      • stem[0]: Conv3d(4, 64, kernel_size=7³, stride=2³, padding=3³)
      • fc:      Linear(512, num_classes)
    """
    model = models.r3d_18(weights=None)

    # Rebuild stem with isotropic kernel for 4-channel MRI
    model.stem[0] = nn.Conv3d(
        4, 64, kernel_size=(7, 7, 7), stride=(2, 2, 2), padding=(3, 3, 3), bias=False
    )
    model.fc = nn.Linear(model.fc.in_features, num_classes)

    # Load adapted weights
    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    log.info("Loaded adapted weights from %s", weights_path)

    # ── Freeze / unfreeze strategy ──
    # Phase 1 (default): freeze the backbone, only train fc
    # Phase 2 (after warmup): unfreeze all layers with a lower LR
    if freeze_backbone:
        for name, param in model.named_parameters():
            if "fc" not in name:
                param.requires_grad = False
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        log.info("Backbone frozen: %d / %d params trainable (%.2f%%)",
                 trainable, total, 100 * trainable / total)
    else:
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        log.info("Full model trainable: %d / %d params (%.2f%%)",
                 trainable, total, 100 * trainable / total)

    return model


def unfreeze_backbone(model, backbone_lr, fc_lr):
    """Unfreeze all parameters and return param groups with differential LR."""
    for param in model.parameters():
        param.requires_grad = True

    backbone_params, fc_params = [], []
    for name, param in model.named_parameters():
        if "fc" in name:
            fc_params.append(param)
        else:
            backbone_params.append(param)

    param_groups = [
        {"params": backbone_params, "lr": backbone_lr},
        {"params": fc_params, "lr": fc_lr},
    ]
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    log.info("Backbone unfrozen: %d params now trainable  "
             "(backbone_lr=%.1e, fc_lr=%.1e)", trainable, backbone_lr, fc_lr)
    return param_groups


# ═══════════════════════════════════════════════════════════════════════════════
#  3.  LEARNING-RATE SCHEDULER — cosine annealing with linear warmup
# ═══════════════════════════════════════════════════════════════════════════════
class CosineWarmupScheduler(optim.lr_scheduler._LRScheduler):
    def __init__(self, optimizer, warmup_steps, total_steps, min_lr=1e-7, last_epoch=-1):
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self.min_lr = min_lr
        super().__init__(optimizer, last_epoch)

    def get_lr(self):
        step = self.last_epoch
        if step < self.warmup_steps:
            # Linear warmup
            scale = step / max(1, self.warmup_steps)
        else:
            # Cosine decay
            progress = (step - self.warmup_steps) / max(1, self.total_steps - self.warmup_steps)
            scale = 0.5 * (1.0 + math.cos(math.pi * progress))
        return [max(self.min_lr, base_lr * scale) for base_lr in self.base_lrs]


# ═══════════════════════════════════════════════════════════════════════════════
#  4.  METRICS
# ═══════════════════════════════════════════════════════════════════════════════
class MetricsAccumulator:
    """Accumulates predictions and targets over an epoch for metric computation."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.all_preds = []
        self.all_probs = []
        self.all_targets = []
        self.running_loss = 0.0
        self.n_samples = 0

    def update(self, logits, targets, loss):
        probs = torch.softmax(logits, dim=1)[:, 1]           # P(positive)
        preds = logits.argmax(dim=1)
        self.all_preds.append(preds.cpu())
        self.all_probs.append(probs.cpu())
        self.all_targets.append(targets.cpu())
        self.running_loss += loss * targets.size(0)
        self.n_samples += targets.size(0)

    def compute(self):
        preds = torch.cat(self.all_preds)
        probs = torch.cat(self.all_probs)
        targets = torch.cat(self.all_targets)

        acc = (preds == targets).float().mean().item()
        avg_loss = self.running_loss / max(1, self.n_samples)

        # Per-class metrics
        tp = ((preds == 1) & (targets == 1)).sum().float()
        fp = ((preds == 1) & (targets == 0)).sum().float()
        fn = ((preds == 0) & (targets == 1)).sum().float()
        tn = ((preds == 0) & (targets == 0)).sum().float()

        precision = (tp / (tp + fp + 1e-8)).item()
        recall = (tp / (tp + fn + 1e-8)).item()
        specificity = (tn / (tn + fp + 1e-8)).item()
        f1 = (2 * precision * recall) / (precision + recall + 1e-8)

        # AUC (manual trapezoidal — avoids sklearn dependency)
        auc = self._compute_auc(probs, targets)

        return {
            "loss": avg_loss,
            "accuracy": acc,
            "precision": precision,
            "recall": recall,
            "specificity": specificity,
            "f1": f1,
            "auc": auc,
        }

    @staticmethod
    def _compute_auc(probs, targets):
        """Compute AUC-ROC using the trapezoidal rule (no sklearn needed)."""
        if targets.sum() == 0 or targets.sum() == len(targets):
            return float("nan")  # AUC is undefined for single-class data

        sorted_indices = torch.argsort(probs, descending=True)
        sorted_targets = targets[sorted_indices].float()
        n_pos = sorted_targets.sum()
        n_neg = len(sorted_targets) - n_pos

        tpr_prev, fpr_prev, auc = 0.0, 0.0, 0.0
        tp_count, fp_count = 0.0, 0.0

        for t in sorted_targets:
            if t == 1:
                tp_count += 1
            else:
                fp_count += 1
            tpr = tp_count / n_pos
            fpr = fp_count / n_neg
            auc += 0.5 * (tpr + tpr_prev) * (fpr - fpr_prev)
            tpr_prev, fpr_prev = tpr, fpr

        return auc


# ═══════════════════════════════════════════════════════════════════════════════
#  5.  TRAINING LOOP
# ═══════════════════════════════════════════════════════════════════════════════
def train_one_epoch(model, loader, criterion, optimizer, scaler, scheduler,
                    device, grad_accum_steps=1):
    model.train()
    metrics = MetricsAccumulator()
    optimizer.zero_grad(set_to_none=True)

    for step, (images, labels) in enumerate(loader):
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        with autocast(device_type="cuda", dtype=torch.float16):
            logits = model(images)
            loss = criterion(logits, labels)
            loss = loss / grad_accum_steps   # normalize for accumulation

        scaler.scale(loss).backward()

        if (step + 1) % grad_accum_steps == 0 or (step + 1) == len(loader):
            # Gradient clipping for stability
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)

        # Step scheduler after every batch (outside accumulation guard)
        # to ensure optimizer.step() happens before scheduler.step()
        if (step + 1) % grad_accum_steps == 0 or (step + 1) == len(loader):
            scheduler.step()

        metrics.update(logits.detach(), labels, loss.item() * grad_accum_steps)

        # Free GPU memory
        del images, labels, logits, loss

    return metrics.compute()


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    metrics = MetricsAccumulator()

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        with autocast(device_type="cuda", dtype=torch.float16):
            logits = model(images)
            loss = criterion(logits, labels)

        metrics.update(logits, labels, loss.item())
        del images, labels, logits, loss

    return metrics.compute()


# ═══════════════════════════════════════════════════════════════════════════════
#  6.  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Fine-tune 3D ResNet-18 on BraTS 2021")
    # Paths
    parser.add_argument("--data_dir", type=str, default="processed_brats",
                        help="Path to preprocessed data directory")
    parser.add_argument("--weights", type=str, default="resnet18_3d_brats_adapted.pth",
                        help="Path to adapted model weights")
    parser.add_argument("--checkpoint_dir", type=str, default="checkpoints",
                        help="Directory to save checkpoints")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to checkpoint to resume training from")

    # Training hyperparams
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=2,
                        help="Per-GPU batch size (effective = batch_size × grad_accum)")
    parser.add_argument("--grad_accum", type=int, default=4,
                        help="Gradient accumulation steps (effective batch = batch_size × grad_accum)")
    parser.add_argument("--lr", type=float, default=3e-4,
                        help="Peak learning rate for FC head")
    parser.add_argument("--backbone_lr_factor", type=float, default=0.1,
                        help="Backbone LR = lr × this factor after unfreezing")
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--warmup_epochs", type=int, default=1)
    parser.add_argument("--unfreeze_epoch", type=int, default=2,
                        help="Epoch at which to unfreeze the backbone (0 = train all from start)")

    # Classification
    parser.add_argument("--label_col", type=str, default="has_ET",
                        help="CSV column name for the classification label")
    parser.add_argument("--num_classes", type=int, default=2)

    # DataLoader
    parser.add_argument("--num_workers", type=int, default=4)
    parser.add_argument("--prefetch", type=int, default=2)

    # Early stopping
    parser.add_argument("--patience", type=int, default=10,
                        help="Early stopping patience (epochs without improvement)")

    args = parser.parse_args()

    # ── Device setup ──
    if not torch.cuda.is_available():
        log.error("CUDA not available. This script is GPU-optimized — exiting.")
        sys.exit(1)

    device = torch.device("cuda")
    torch.backends.cudnn.benchmark = True  # auto-tune conv algorithms for 128³ input
    log.info("GPU: %s  |  VRAM: %.1f GB",
             torch.cuda.get_device_name(0),
             torch.cuda.get_device_properties(0).total_memory / 1e9)
    log.info("Effective batch size: %d  (batch=%d × accum=%d)",
             args.batch_size * args.grad_accum, args.batch_size, args.grad_accum)

    # ── Load channel stats ──
    stats_path = os.path.join(args.data_dir, "channel_stats.json")
    channel_mean, channel_std = None, None
    if os.path.exists(stats_path):
        with open(stats_path) as f:
            stats = json.load(f)
        channel_mean = stats["mean"]
        channel_std = stats["std"]
        log.info("Channel stats: mean=%s, std=%s", channel_mean, channel_std)
    else:
        log.warning("channel_stats.json not found — skipping per-channel normalization")

    # ── Datasets & DataLoaders ──
    train_ds = BraTSDataset(
        os.path.join(args.data_dir, "train.csv"),
        label_col=args.label_col,
        channel_mean=channel_mean,
        channel_std=channel_std,
        augment=True,
    )
    val_ds = BraTSDataset(
        os.path.join(args.data_dir, "val.csv"),
        label_col=args.label_col,
        channel_mean=channel_mean,
        channel_std=channel_std,
        augment=False,
    )

    # Class weighting for imbalanced data (common in BraTS tumor detection)
    train_labels = train_ds.df[args.label_col].values
    class_counts = np.bincount(train_labels, minlength=args.num_classes)
    safe_counts = np.maximum(class_counts, 1)

    # ── Weighted sampler: oversample minority class so batches are balanced ──
    # Without this, batch_size=4 with 2.1% minority → ~92% of batches have
    # ZERO minority samples, making gradient signal extremely noisy.
    sample_weight_per_class = 1.0 / safe_counts
    sample_weights = np.array([sample_weight_per_class[l] for l in train_labels])
    sample_weights = sample_weights / sample_weights.sum()
    sampler = torch.utils.data.WeightedRandomSampler(
        weights=torch.from_numpy(sample_weights).double(),
        num_samples=len(train_labels),
        replacement=True,
    )
    log.info("Class distribution: %s  (using WeightedRandomSampler for balanced batches)",
             class_counts.tolist())

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        sampler=sampler,            # replaces shuffle=True
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=True if args.num_workers > 0 else False,
        prefetch_factor=args.prefetch if args.num_workers > 0 else None,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=True if args.num_workers > 0 else False,
        prefetch_factor=args.prefetch if args.num_workers > 0 else None,
    )

    # ── Model ──
    freeze_at_start = args.unfreeze_epoch > 0
    model = build_model(args.weights, num_classes=args.num_classes,
                        freeze_backbone=freeze_at_start)
    model = model.to(device)

    # ── Loss, Optimizer, Scaler ──
    # No class weights in loss — the WeightedRandomSampler already balances
    # batches at the data level. Stacking loss weights on top double-rebalances
    # and causes the model to predict all-minority-class.
    criterion = nn.CrossEntropyLoss()

    optimizer = optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.lr,
        weight_decay=args.weight_decay,
    )

    scaler = GradScaler("cuda")

    steps_per_epoch = math.ceil(len(train_loader) / args.grad_accum)
    total_steps = steps_per_epoch * args.epochs
    warmup_steps = steps_per_epoch * args.warmup_epochs

    scheduler = CosineWarmupScheduler(optimizer, warmup_steps, total_steps)

    # ── Resume checkpoint ──
    start_epoch = 0
    best_val_f1 = 0.0
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state"])
        optimizer.load_state_dict(ckpt["optimizer_state"])
        scaler.load_state_dict(ckpt["scaler_state"])
        scheduler.load_state_dict(ckpt["scheduler_state"])
        start_epoch = ckpt["epoch"] + 1
        best_val_f1 = ckpt.get("best_val_f1", 0.0)
        log.info("Resumed from epoch %d  (best_val_f1=%.4f)", start_epoch, best_val_f1)

    # ── Checkpoint directory ──
    os.makedirs(args.checkpoint_dir, exist_ok=True)

    # ── Training log file ──
    log_path = os.path.join(args.checkpoint_dir, "training_log.csv")
    if not os.path.exists(log_path) or start_epoch == 0:
        with open(log_path, "w") as f:
            f.write("epoch,phase,loss,accuracy,precision,recall,specificity,f1,auc,lr\n")

    def append_log(epoch, phase, m, lr):
        with open(log_path, "a") as f:
            f.write(f"{epoch},{phase},{m['loss']:.6f},{m['accuracy']:.4f},"
                    f"{m['precision']:.4f},{m['recall']:.4f},{m['specificity']:.4f},"
                    f"{m['f1']:.4f},{m['auc']:.4f},{lr:.2e}\n")

    # ═══════════════════════════════════════════════════════════════════════════
    #  TRAINING LOOP
    # ═══════════════════════════════════════════════════════════════════════════
    patience_counter = 0
    backbone_unfrozen = not freeze_at_start

    log.info("=" * 80)
    log.info("Starting training: %d epochs, patience=%d, unfreeze_epoch=%d",
             args.epochs, args.patience, args.unfreeze_epoch)
    log.info("=" * 80)

    for epoch in range(start_epoch, args.epochs):
        epoch_start = time.time()

        # ── Unfreeze backbone at the designated epoch ──
        if not backbone_unfrozen and epoch >= args.unfreeze_epoch:
            backbone_lr = args.lr * args.backbone_lr_factor
            param_groups = unfreeze_backbone(model, backbone_lr, args.lr)
            optimizer = optim.AdamW(param_groups, weight_decay=args.weight_decay)

            # Rebuild scheduler for remaining epochs
            remaining_steps = steps_per_epoch * (args.epochs - epoch)
            warmup_remaining = steps_per_epoch * 2  # 2-epoch warmup after unfreeze
            scheduler = CosineWarmupScheduler(optimizer, warmup_remaining, remaining_steps)
            scaler = GradScaler("cuda")

            backbone_unfrozen = True

        # ── Train ──
        current_lr = optimizer.param_groups[0]["lr"]
        train_metrics = train_one_epoch(
            model, train_loader, criterion, optimizer, scaler, scheduler,
            device, grad_accum_steps=args.grad_accum,
        )

        # ── Validate ──
        val_metrics = evaluate(model, val_loader, criterion, device)

        epoch_time = time.time() - epoch_start

        # ── Log ──
        log.info(
            "Epoch %02d/%02d  [%.0fs]  "
            "Train: loss=%.4f acc=%.3f f1=%.3f  |  "
            "Val: loss=%.4f acc=%.3f f1=%.3f auc=%.3f  |  lr=%.1e",
            epoch + 1, args.epochs, epoch_time,
            train_metrics["loss"], train_metrics["accuracy"], train_metrics["f1"],
            val_metrics["loss"], val_metrics["accuracy"], val_metrics["f1"],
            val_metrics["auc"], current_lr,
        )

        append_log(epoch, "train", train_metrics, current_lr)
        append_log(epoch, "val", val_metrics, current_lr)

        # ── Checkpointing ──
        checkpoint = {
            "epoch": epoch,
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scaler_state": scaler.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "train_metrics": train_metrics,
            "val_metrics": val_metrics,
            "best_val_f1": best_val_f1,
            "args": vars(args),
        }

        # Always save last checkpoint (for resuming)
        torch.save(checkpoint, os.path.join(args.checkpoint_dir, "last_checkpoint.pth"))

        # Save best model by validation F1
        if val_metrics["f1"] > best_val_f1:
            best_val_f1 = val_metrics["f1"]
            checkpoint["best_val_f1"] = best_val_f1
            torch.save(checkpoint, os.path.join(args.checkpoint_dir, "best_model.pth"))
            log.info("  ★ New best val F1: %.4f — saved best_model.pth", best_val_f1)
            patience_counter = 0
        else:
            patience_counter += 1
            log.info("  No improvement (%d/%d patience)", patience_counter, args.patience)

        # Early stopping
        if patience_counter >= args.patience:
            log.info("Early stopping triggered at epoch %d", epoch + 1)
            break

        # Periodic GPU cleanup
        if device.type == "cuda":
            torch.cuda.empty_cache()

    # ═══════════════════════════════════════════════════════════════════════════
    #  FINAL EVALUATION ON TEST SET
    # ═══════════════════════════════════════════════════════════════════════════
    log.info("=" * 80)
    log.info("Training complete! Loading best model for test evaluation...")

    best_ckpt_path = os.path.join(args.checkpoint_dir, "best_model.pth")
    if os.path.exists(best_ckpt_path):
        best_ckpt = torch.load(best_ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(best_ckpt["model_state"])
        log.info("Loaded best model from epoch %d  (val_f1=%.4f)",
                 best_ckpt["epoch"] + 1, best_ckpt["best_val_f1"])

    test_csv = os.path.join(args.data_dir, "test.csv")
    if os.path.exists(test_csv):
        test_ds = BraTSDataset(
            test_csv, label_col=args.label_col,
            channel_mean=channel_mean, channel_std=channel_std, augment=False,
        )
        test_loader = DataLoader(
            test_ds, batch_size=args.batch_size, shuffle=False,
            num_workers=args.num_workers, pin_memory=True,
        )
        test_metrics = evaluate(model, test_loader, criterion, device)
        log.info("TEST RESULTS:")
        log.info("  Loss:        %.4f", test_metrics["loss"])
        log.info("  Accuracy:    %.4f", test_metrics["accuracy"])
        log.info("  Precision:   %.4f", test_metrics["precision"])
        log.info("  Recall:      %.4f", test_metrics["recall"])
        log.info("  Specificity: %.4f", test_metrics["specificity"])
        log.info("  F1 Score:    %.4f", test_metrics["f1"])
        log.info("  AUC-ROC:     %.4f", test_metrics["auc"])

        # Save test results
        with open(os.path.join(args.checkpoint_dir, "test_results.json"), "w") as f:
            json.dump(test_metrics, f, indent=2)
    else:
        log.warning("test.csv not found — skipping test evaluation")

    log.info("=" * 80)
    log.info("All done! Checkpoints saved to: %s", args.checkpoint_dir)


if __name__ == "__main__":
    main()
