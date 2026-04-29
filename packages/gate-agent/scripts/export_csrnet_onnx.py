"""Export a pretrained CSRNet PyTorch checkpoint to ONNX.

Usage:
    uv run python scripts/export_csrnet_onnx.py \
        --weights /path/to/PartBmodel_best.pth.tar \
        --output ../../assets/csrnet.onnx \
        --input-size 768 1024

The checkpoint can be downloaded from the reference repo:
    https://github.com/leeyeehoo/CSRNet-pytorch
which links to a Google Drive folder. Alternative mirrors:
    - https://huggingface.co/cvlab-stonybrook/DM-Count (a related model)
    - any community fork that ships the .pth in releases

After export, edit configs/gate-crowd-stage.yaml:

    crowd:
      engine: csrnet
      csrnet_onnx_path: ../../assets/csrnet.onnx
      csrnet_input_size: [768, 1024]   # H, W

Then `pnpm gate:crowd-stage`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

# Make the package importable when running from packages/gate-agent
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gate_agent.models.csrnet import CSRNet, load_csrnet_from_pretrained  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export CSRNet PyTorch → ONNX")
    parser.add_argument("--weights", required=False, help="Path to a CSRNet .pth/.pth.tar checkpoint")
    parser.add_argument(
        "--output",
        default="../../assets/csrnet.onnx",
        help="Destination ONNX path (default: ../../assets/csrnet.onnx)",
    )
    parser.add_argument(
        "--input-size",
        nargs=2,
        type=int,
        default=[768, 1024],
        metavar=("H", "W"),
        help="Static export height and width (default 768 1024)",
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=17,
        help="ONNX opset version (default 17)",
    )
    parser.add_argument(
        "--no-weights",
        action="store_true",
        help="Export the architecture with random init (just to validate the graph)",
    )
    args = parser.parse_args()

    device = "cpu"
    if args.no_weights:
        print("[csrnet] exporting with RANDOM init (not for inference, only to test the graph)")
        model = CSRNet().to(device).eval()
    else:
        if not args.weights:
            print("error: --weights is required (or use --no-weights for graph-only export)", file=sys.stderr)
            return 2
        weights_path = Path(args.weights)
        if not weights_path.exists():
            print(f"error: weights not found at {weights_path}", file=sys.stderr)
            return 2
        print(f"[csrnet] loading weights from {weights_path}")
        model = load_csrnet_from_pretrained(str(weights_path), device=device)

    h, w = args.input_size
    dummy = torch.zeros(1, 3, h, w, device=device)

    with torch.no_grad():
        out = model(dummy)
    print(f"[csrnet] forward pass OK. input={tuple(dummy.shape)}  output={tuple(out.shape)}")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[csrnet] exporting ONNX → {output_path} (opset={args.opset})")
    # Use the legacy (TorchScript-based) exporter via dynamo=False to keep
    # weights inline in a single .onnx file. The new dynamo path emits an
    # external-data .onnx + .onnx.data which makes deployment trickier.
    torch.onnx.export(
        model,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["density"],
        opset_version=args.opset,
        do_constant_folding=True,
        dynamo=False,
        dynamic_axes={
            "input": {0: "batch", 2: "height", 3: "width"},
            "density": {0: "batch", 2: "height", 3: "width"},
        },
    )

    # Sanity check the ONNX file and confirm it's self-contained
    try:
        import onnx  # type: ignore

        loaded = onnx.load(str(output_path))
        onnx.checker.check_model(loaded)
        external_count = sum(
            1 for init in loaded.graph.initializer if init.data_location == onnx.TensorProto.EXTERNAL
        )
        if external_count:
            print(f"[csrnet] WARNING: {external_count} initializers are still external — re-saving as embedded")
            for init in loaded.graph.initializer:
                if init.data_location == onnx.TensorProto.EXTERNAL:
                    onnx.external_data_helper.load_external_data_for_tensor(init, str(output_path.parent))
                    init.data_location = onnx.TensorProto.DEFAULT
            onnx.save(loaded, str(output_path))
        print("[csrnet] onnx.checker.check_model: OK (single-file)")
    except ImportError:
        print("[csrnet] (skip) `onnx` not installed, file written but not validated")

    print()
    print(f"✓ Exported: {output_path}")
    print()
    print("Next: edit configs/gate-crowd-stage.yaml →")
    print("  crowd:")
    print("    engine: csrnet")
    print(f"    csrnet_onnx_path: {output_path}")
    print(f"    csrnet_input_size: [{h}, {w}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
