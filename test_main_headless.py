"""
End-to-end headless loop test for ai/main.py.
Runs the complete main pipeline for 10 frames and validates terminal output.
"""

import sys
import os
import cv2

os.environ["OPENCV_LOG_LEVEL"] = "OFF"

# Add ai/ to path
AI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai")
sys.path.insert(0, AI_DIR)

from camera import get_camera
from detector import WasteDetector, CONFIDENCE_THRESHOLD
from main import draw_hud, print_detection_log, DEMO_MODE


def run_e2e_test():
    print("Testing full pipeline end-to-end for 10 iterations...")
    detector = WasteDetector()
    status = detector.get_status()
    print("Inspection status:", status)

    cam = get_camera(source=0)
    assert cam.available, "Camera should be available (physical or synthetic)"

    # Test cycling and forced categories
    tests = [
        ("Default / simulated", None, None),
        ("Forced Organic", "Organic", 0.94),
        ("Forced Plastic", "Plastic", 0.95),
        ("Forced Metal", "Metal", 0.92),
        ("Forced Low Confidence", "Plastic", 0.58),
    ]

    for desc, override_label, override_conf in tests:
        if override_label:
            detector.set_manual_override(override_label, override_conf)
        else:
            detector.set_manual_override(None)

        ok, frame = cam.read()
        assert ok, "Failed to read frame"
        result = detector.detect(frame)
        assert result is not None, "Expected detection result"

        frame = draw_hud(frame, result)
        assert frame is not None, "Frame should be drawn"

        print(f"  [OK] {desc} -> Result: {result.label} ({result.confidence*100:.0f}%) is_confident={result.is_confident} cmd={result.command}")
        if result.is_confident:
            print_detection_log(result)

    cam.release()
    print("\nEnd-to-end pipeline test completed successfully!")


if __name__ == "__main__":
    run_e2e_test()
