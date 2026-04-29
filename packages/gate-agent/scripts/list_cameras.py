"""List available camera indices on macOS, with a JPEG snapshot per index
so you can identify visually which one is which."""

from __future__ import annotations

import time
from pathlib import Path

import cv2


SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "data" / "camera-probe"


def main() -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Probing camera indices 0..5 (AVFoundation)... snapshots → {SNAPSHOTS_DIR}")
    print()
    for idx in range(6):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        opened = cap.isOpened()
        if not opened:
            print(f"  [{idx}] open=NO")
            cap.release()
            continue

        # Drain a few frames so the cam has time to expose / focus
        ok = False
        frame = None
        for _ in range(8):
            ok, frame = cap.read()
            if ok:
                time.sleep(0.05)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        snap_path = SNAPSHOTS_DIR / f"cam-{idx}.jpg"
        if ok and frame is not None:
            cv2.imwrite(str(snap_path), frame)
            print(f"  [{idx}] open=YES   {w}x{h} @ {fps:.1f}fps   → {snap_path.name}")
        else:
            print(f"  [{idx}] open=YES   first_frame=NO  ({w}x{h} @ {fps:.1f}fps)")
        cap.release()

    print()
    print("Open the snapshots above to identify your USB cam, then set it in your YAML:")
    print(f"  open {SNAPSHOTS_DIR}")
    print("Then in configs/gate-webcam.yaml or gate-webcam-2.yaml: webcam_index: <N>")


if __name__ == "__main__":
    main()
