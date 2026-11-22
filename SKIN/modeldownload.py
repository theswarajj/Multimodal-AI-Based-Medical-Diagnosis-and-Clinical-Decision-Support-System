

import os
import torch
import timm

NUM_CLASSES = 7  # HAM10000: akiec, bcc, bkl, df, mel, nv, vasc
MODEL_NAME = "efficientnet_b3"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, "checkpoints")
SAVE_PATH = os.path.join(SAVE_DIR, "efficientnet_b3_imagenet.pth")


def download_model():
    print(f"Downloading pretrained {MODEL_NAME} (ImageNet weights)...")

    # This triggers the download to the local timm/torch cache
    # (~/.cache/torch/hub/checkpoints on Linux/Mac,
    #  C:\\Users\\<user>\\.cache\\torch\\hub\\checkpoints on Windows)
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
    print(f"Num classes (head): {NUM_CLASSES}")

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
        output = model(dummy_input)
    print(f"Output shape: {output.shape}  (expected: [1, {NUM_CLASSES}])")
    assert output.shape == (1, NUM_CLASSES), "Output shape mismatch!"
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

    print("\nDone. Model is ready for fine-tuning on HAM10000.")


if __name__ == "__main__":
    main()