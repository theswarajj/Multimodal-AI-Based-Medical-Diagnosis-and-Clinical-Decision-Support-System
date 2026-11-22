import torch
import torchvision.models.video as models
import torch.nn as nn
import torch.nn.functional as F
import os

def download_and_save_pretrained_resnet18_3d():
    save_path = 'resnet18_3d_pretrained.pth'
    print("Downloading pretrained 3D ResNet-18 (Kinetics-400)...")
    
    # Load the pretrained model (trained on Kinetics-400 video dataset)
    # Using torchvision.models.video.r3d_18 which provides a 3D ResNet-18
    model = models.r3d_18(weights=models.R3D_18_Weights.DEFAULT)
    
    # Save the original state dictionary
    torch.save(model.state_dict(), save_path)
    print(f"Original model weights saved successfully to {save_path}")
    
    # ---------------------------------------------------------
    # Adaptation for BraTS 2021 Dataset
    # ---------------------------------------------------------
    print("\nAdapting model for BraTS 2021 (4 input channels and isotropic volumes)...")
    
    # 1. Adapt input channels (3 -> 4)
    # 2. Adapt stem stride and kernel for isotropic 3D MRI (Video models have anisotropic stems)
    original_conv1 = model.stem[0]
    
    # Create a new conv layer with 4 input channels, and isotropic kernel/stride
    new_conv1 = nn.Conv3d(
        in_channels=4, 
        out_channels=original_conv1.out_channels, 
        kernel_size=(7, 7, 7),     # Was (3, 7, 7) for video
        stride=(2, 2, 2),          # Was (1, 2, 2) for video
        padding=(3, 3, 3),         # Was (1, 3, 3) for video
        bias=False
    )
    
    # We need to resize the pretrained weights from (3, 7, 7) to (7, 7, 7)
    # to preserve the pretrained features for the isotropic stem.
    with torch.no_grad():
        # Interpolate spatial dimensions: (64, 3, 3, 7, 7) -> (64, 3, 7, 7, 7)
        # F.interpolate treats it as (batch, channels, D, H, W)
        resized_weights = F.interpolate(
            original_conv1.weight, 
            size=(7, 7, 7),
            mode='trilinear',
            align_corners=False
        )
        
        # Copy the interpolated weights for the first 3 channels
        new_conv1.weight[:, :3, :, :, :] = resized_weights
        
        # For the 4th channel (FLAIR), initialize it with the mean of the other 3 channels
        new_conv1.weight[:, 3:4, :, :, :] = resized_weights.mean(dim=1, keepdim=True)
        
    # Replace the layer in the model
    model.stem[0] = new_conv1
    
    # Adapt the final fully connected layer for your specific task.
    # For BraTS, if you are doing classification (e.g., MGMT promoter methylation)
    # or segmentation (you would likely use the ResNet as an encoder in a UNet, but here is a classification example)
    num_ftrs = model.fc.in_features
    # Example: changing to 2 output classes for binary classification
    model.fc = nn.Linear(num_ftrs, 2) 
    
    # Save the adapted model
    adapted_save_path = 'resnet18_3d_brats_adapted.pth'
    torch.save(model.state_dict(), adapted_save_path)
    print(f"Adapted model weights saved successfully to {adapted_save_path}")

if __name__ == "__main__":
    download_and_save_pretrained_resnet18_3d()
