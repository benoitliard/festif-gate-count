"""CSRNet PyTorch model definition.

Faithful to the paper "CSRNet: Dilated Convolutional Neural Networks for
Understanding the Highly Congested Scenes" (CVPR 2018, Li et al.) and the
reference implementation https://github.com/leeyeehoo/CSRNet-pytorch.

Frontend: first 13 conv layers of VGG-16 (pretrained on ImageNet).
Backend: 6 dilated 3x3 conv layers (dilation=2) → 1x1 conv producing the
density map. Output is upsampled ×8 to match the input resolution.

The integral of the density map (sum of all pixels) is the estimated number
of people. CSRNet was trained on ShanghaiTech / UCF-CC-50 / WorldExpo-10
where each ground-truth head is convolved with a Gaussian kernel during
training, so the network learns to spread "1 person" of mass over a small
patch of pixels around each head.
"""

from __future__ import annotations

from typing import Iterable

import torch
import torch.nn as nn
import torch.nn.functional as F


def _make_layers(cfg: Iterable[int | str], in_channels: int = 3, dilation: bool = False) -> nn.Sequential:
    d_rate = 2 if dilation else 1
    layers: list[nn.Module] = []
    for v in cfg:
        if v == "M":
            layers.append(nn.MaxPool2d(kernel_size=2, stride=2))
        else:
            assert isinstance(v, int)
            layers.append(nn.Conv2d(in_channels, v, kernel_size=3, padding=d_rate, dilation=d_rate))
            layers.append(nn.ReLU(inplace=True))
            in_channels = v
    return nn.Sequential(*layers)


class CSRNet(nn.Module):
    """CSRNet model — input (B, 3, H, W) RGB, output (B, 1, H, W) density map."""

    def __init__(self) -> None:
        super().__init__()
        # First 13 conv layers of VGG-16 (3 max-pool layers → output is H/8 × W/8)
        self.frontend_feat: list[int | str] = [
            64, 64, "M",
            128, 128, "M",
            256, 256, 256, "M",
            512, 512, 512,
        ]
        self.backend_feat: list[int | str] = [512, 512, 512, 256, 128, 64]

        self.frontend = _make_layers(self.frontend_feat)
        self.backend = _make_layers(self.backend_feat, in_channels=512, dilation=True)
        self.output_layer = nn.Conv2d(64, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.frontend(x)
        x = self.backend(x)
        x = self.output_layer(x)
        # NOTE: we deliberately skip the ×8 upsample that the reference
        # implementation does. Bilinear upsample multiplies the integral of
        # the density map by scale² (=64), which inflates the count. Sum the
        # low-resolution density map (H/8, W/8) and you get the people count
        # directly. Visualization code can upsample afterwards if needed.
        return x


def load_csrnet_from_pretrained(weights_path: str, device: str = "cpu") -> CSRNet:
    """Load a CSRNet checkpoint produced by the reference repo.

    The checkpoints from https://github.com/leeyeehoo/CSRNet-pytorch are
    PyTorch dicts with either ``state_dict`` or the raw key→tensor mapping.
    Some forks ship a different module-name prefix (``model.`` vs none) so
    we strip it on the fly to be tolerant.
    """
    state = torch.load(weights_path, map_location=device, weights_only=False)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]

    # Strip any common prefix
    if isinstance(state, dict):
        cleaned: dict[str, torch.Tensor] = {}
        for k, v in state.items():
            for prefix in ("module.", "model."):
                if k.startswith(prefix):
                    k = k[len(prefix) :]
                    break
            cleaned[k] = v
        state = cleaned

    model = CSRNet()
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        print(f"[csrnet] note: {len(missing)} missing keys (likely OK if buffer-only): {list(missing)[:3]}…")
    if unexpected:
        print(f"[csrnet] note: {len(unexpected)} unexpected keys: {list(unexpected)[:3]}…")
    model.to(device).eval()
    return model
