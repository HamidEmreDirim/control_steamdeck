#!/usr/bin/env python3
import cv2, pathlib
from cv2 import dnn_superres as dsr

# ───── user knobs ────────────────────────────────────────────────
DEVICE = "/dev/video0"
SRC_W, SRC_H = 640, 480
TARGET_W, TARGET_H = 1280, 800           # Steam-Deck screen
MODEL, SCALE = "fsrcnn", 2               # 2× FSRCNN (≈8 ms latency)
MODELDIR = pathlib.Path("~/superres/models").expanduser()
# ─────────────────────────────────────────────────────────────────

model_path = MODELDIR / f"FSRCNN-small_x2.pb"
if not model_path.exists():
    raise SystemExit(f"Model not found → {model_path}")

sr = dsr.DnnSuperResImpl_create()
sr.readModel(str(model_path))
sr.setModel(MODEL, SCALE)
sr.setPreferableTarget(cv2.dnn.DNN_TARGET_OPENCL)   # GPU on Deck

cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  SRC_W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SRC_H)

# make ONE window, once
WIN = "Super-Res 1280×800"
cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WIN, TARGET_W, TARGET_H)

def crop16x10(img):
    h, w = img.shape[:2]
    want = TARGET_W / TARGET_H          # 1.6
    if w / h > want:                    # too wide → crop width
        new_w = int(h * want)
        x0 = (w - new_w) // 2
        img = img[:, x0:x0 + new_w]
    else:                               # too tall → crop height
        new_h = int(w / want)
        y0 = (h - new_h) // 2
        img = img[y0:y0 + new_h]
    return cv2.resize(img, (TARGET_W, TARGET_H),
                      interpolation=cv2.INTER_AREA)

while cap.isOpened():
    ok, frame = cap.read()
    if not ok:
        print("⚠️  no frame"); break
    up   = sr.upsample(frame)   # 640×480 → 1280×960
    view = crop16x10(up)        # 1280×960 → 1280×800
    cv2.imshow(WIN, view)       # always SAME window name
    if cv2.waitKey(1) & 0xFF in (27, ord('q')):   # Esc or q quits
        break

cap.release()
cv2.destroyAllWindows()
