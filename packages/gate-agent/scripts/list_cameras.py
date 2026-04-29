"""List available camera indices on macOS via OpenCV/AVFoundation."""

from __future__ import annotations

import cv2


def main() -> None:
    print("Probing camera indices 0..5 (AVFoundation)...")
    print()
    for idx in range(6):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        opened = cap.isOpened()
        ok, _frame = (False, None)
        if opened:
            ok, _frame = cap.read()
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            print(f"  [{idx}] open=YES   first_frame={'YES' if ok else 'NO '}   {w}x{h} @ {fps:.1f}fps")
        else:
            print(f"  [{idx}] open=NO")
        cap.release()
    print()
    print("Pick the index for your USB cam and put it in your YAML as `webcam_index: <N>`.")
    print("Note: macOS Camera permission is per-binary; if you flip indices, the prompt")
    print("might appear again the first time the new index is opened.")


if __name__ == "__main__":
    main()
