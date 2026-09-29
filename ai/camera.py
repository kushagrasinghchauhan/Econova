"""
camera.py
---------
Handles webcam access for EcoNova.

Wraps OpenCV's VideoCapture with multiple backend fallbacks (DirectShow, MSMF, Default).
If no physical webcam is connected or if it's locked by another process, it provides
a synthetic test feed so the presentation and HUD can still be demonstrated without crashing.
"""

import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
import time
import cv2
import numpy as np


class Camera:
    def __init__(self, source=0, width=640, height=480, allow_synthetic_fallback=True):
        """
        source: webcam index. 0 = default laptop webcam.
        allow_synthetic_fallback: if True, generates synthetic camera frames
                                  when no physical camera is accessible.
        """
        self.source = source
        self.width = width
        self.height = height
        self.allow_synthetic_fallback = allow_synthetic_fallback
        self.cap = None
        self.available = False
        self.is_synthetic = False
        self._frame_count = 0
        self._open()

    def _open(self):
        # 1. Try Windows DirectShow first (fastest startup)
        try:
            if os.name == "nt":
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
        except Exception:
            self.cap = None

        # 2. Fallback to default backend if DSHOW failed
        if self.cap is None or not self.cap.isOpened():
            try:
                self.cap = cv2.VideoCapture(self.source)
            except Exception:
                self.cap = None

        # 3. Check if physical camera opened successfully
        if self.cap is not None and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.available = True
            self.is_synthetic = False
            return

        # 4. If physical camera is unavailable and synthetic fallback is enabled
        if self.allow_synthetic_fallback:
            self.available = True
            self.is_synthetic = True
        else:
            self.available = False
            self.is_synthetic = False

    def read(self):
        """
        Returns (success, frame).
        If physical camera is active, grabs real frame.
        If synthetic fallback is active, generates synthetic camera feed.
        """
        if not self.available:
            return False, None

        if self.is_synthetic:
            self._frame_count += 1
            frame = self._generate_synthetic_frame()
            # Simulate ~30 FPS frame rate
            time.sleep(0.03)
            return True, frame

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return False, None
        return True, frame

    def _generate_synthetic_frame(self):
        """Generates a synthetic waste inspection stage for demo testing."""
        frame = np.full((self.height, self.width, 3), 45, dtype=np.uint8)

        # Draw inspection platform surface
        cv2.rectangle(frame, (80, 100), (self.width - 80, self.height - 40), (60, 60, 60), -1)
        cv2.rectangle(frame, (80, 100), (self.width - 80, self.height - 40), (90, 90, 90), 2)

        # Grid guidelines
        for x in range(120, self.width - 80, 80):
            cv2.line(frame, (x, 100), (x, self.height - 40), (70, 70, 70), 1)
        for y in range(140, self.height - 40, 60):
            cv2.line(frame, (80, y), (self.width - 80, y), (70, 70, 70), 1)

        # Notice watermark
        cv2.putText(frame, "[SYNTHETIC CAMERA FEED - NO PHYSICAL WEBCAM DETECTED]",
                    (20, self.height - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 180, 255), 1)
        return frame

    def release(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.available = False


def get_camera(source=0, width=640, height=480, allow_synthetic_fallback=True):
    """
    Convenience factory with clear status reporting.
    """
    cam = Camera(source=source, width=width, height=height,
                 allow_synthetic_fallback=allow_synthetic_fallback)
    if cam.available and not cam.is_synthetic:
        print(f"[Camera] Physical webcam opened successfully (source={source}).")
    elif cam.is_synthetic:
        print(f"[Camera] NOTICE: Physical webcam not detected on source={source}.")
        print("[Camera] Synthetic camera feed enabled - demo UI will run without crashing.")
    else:
        print(f"[Camera] WARNING: Could not open webcam (source={source}).")
    return cam
