#!/usr/bin/env python3
"""
OpenCV camera viewer (no upscale, max FPS)
- Captures directly from /dev/video0
- Displays frames as fast as possible
- Prints and overlays send rate (Hz) every second
"""

import cv2
import time

# ───── user knobs ────────────────────────────────────────────────
DEVICE       = "/dev/video0"
SRC_W, SRC_H = 640, 480        # capture size
WINDOW_NAME  = "Camera"
SHOW_HUD     = True            # overlay FPS text on the frame
# ─────────────────────────────────────────────────────────────────

def main():
    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)

    # Low-latency capture settings (best-effort; not all cams support these)
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    except Exception:
        pass
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  SRC_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SRC_H)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera: {DEVICE}")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_AUTOSIZE)

    # FPS accounting
    last_report = time.perf_counter()
    frames = 0
    fps_display = "— Hz"

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("⚠️ no frame from camera; retrying…")
                time.sleep(0.01)
                continue

            # Update FPS once per second
            frames += 1
            now = time.perf_counter()
            if now - last_report >= 1.0:
                hz = frames / (now - last_report)
                fps_display = f"{hz:.1f} Hz"
                print(fps_display)
                frames = 0
                last_report = now

            # Optional HUD
            if SHOW_HUD:
                cv2.putText(
                    frame, fps_display, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA
                )

            cv2.imshow(WINDOW_NAME, frame)

            # 1 ms wait; ESC or 'q' to quit
            k = cv2.waitKey(1) & 0xFF
            if k == 27 or k == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
