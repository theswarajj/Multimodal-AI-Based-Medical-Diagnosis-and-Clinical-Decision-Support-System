

import os
import torch
import timm

# The 14 standard CheXpert observation columns, in the order they appear
# in train.csv / valid.csv. Keep this order consistent everywhere.
CHEXPERT_LABELS = [
    "No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Opacity",
    "Lung Lesion", "Edema", "Consolidation", "Pneumonia", "Atelectasis",
    "Pneumothorax", "Pleural Effusion", "Pleural Other", "Fracture",
    "Support Devices",
]
NUM_CLASSES = len(CHEXPERT_LABELS)  # 14

MODEL_NAME = "densenet121"
SAVE_DIR = "checkpoints"
SAVE_PATH = os.path.join(SAVE_DIR, "densenet121_imagenet.pth")


def download_model():
    print(f"Downloading pretrained {MODEL_NAME} (ImageNet weights)...")
    # num_classes=NUM_CLASSES replaces the 1000-way ImageNet head with a
    # 14-way head. We'll apply sigmoid (not softmax) at train/inference
    # time since labels are independent, not mutually exclusive.
    model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=NUM_CLASSES)
    print("Download complete.")
    return model


def print_model_info(model):
    cfg = model.default_cfg
    print("\n--- Model Config ---")
    print(f"Architecture      : {MODEL_NAME}")
    print(f"Expected input    : {cfg['input_size']}")
    print(f"Normalize mean    : {cfg['mean']}")
    print(f"Normalize std     : {cfg['std']}")
    print(f"Num classes (head): {NUM_CLASSES} (multi-label)")
    print(f"Labels            : {CHEXPERT_LABELS}")

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Total parameters  : {total_params:,}")
    print(f"Trainable params  : {trainable_params:,}")


def sanity_check(model, device):
    print("\nRunning sanity check (forward pass)...")
    model.eval().to(device)
    input_size = model.default_cfg["input_size"][1]
    dummy_input = torch.randn(1, 3, input_size, input_size).to(device)
    with torch.no_grad():
        logits = model(dummy_input)
        probs = torch.sigmoid(logits)  # multi-label -> sigmoid, not softmax
    print(f"Output shape: {logits.shape}  (expected: [1, {NUM_CLASSES}])")
    assert logits.shape == (1, NUM_CLASSES), "Output shape mismatch!"
    print(f"Sigmoid probs sample: {probs[0][:5].cpu().numpy()}")
    print("Sanity check passed.")


def save_checkpoint(model):
    os.makedirs(SAVE_DIR, exist_ok=True)
    torch.save(model.state_dict(), SAVE_PATH)
    print(f"\nModel weights saved to: {SAVE_PATH}")


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    model = download_model()
    print_model_info(model)
    sanity_check(model, device)
    save_checkpoint(model)

    print("\nDone. Model is ready for fine-tuning on CheXpert.")
    print("Note: use BCEWithLogitsLoss (not CrossEntropyLoss) for multi-label training.")


if __name__ == "__main__":
    main()