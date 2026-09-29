"""
Unit and functional test for EcoNova Stage 1: AI & Detection Module.
"""

import sys
import os
import numpy as np

# Ensure ai directory is importable
AI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai")
sys.path.insert(0, AI_DIR)

from detector import WasteDetector, CONFIDENCE_THRESHOLD, CLASS_NAMES
from camera import Camera


def test_detector_logic():
    print("[TEST 1] Testing WasteDetector initialization & inspection...")
    detector = WasteDetector()
    status = detector.get_status()
    print("  Status:", status)
    assert status["model_status"] in ["READY", "YOLO_MODEL_MISSING", "INCOMPATIBLE_CLASSES"], "Status must be valid"
    assert status["classes"] == CLASS_NAMES, "Classes must match target classes"
    print("  -> Passed WasteDetector init & inspection test.")

    print("\n[TEST 2] Testing frame detection without weights (returns None / no fake predictions)...")
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detector.detect(dummy_frame)
    print("  Detection result without model:", result)
    assert result is None, "Expected None when model weights are missing (no fake predictions)"
    print("  -> Passed real detector integrity test (no fake predictions without model).")

    print("\n[TEST 3] Testing manual overrides (Organic, Plastic, Metal, Low Conf)...")
    detector.set_manual_override("Organic", 0.94)
    res_org = detector.detect(dummy_frame)
    assert res_org.label == "Organic" and res_org.confidence == 0.94 and res_org.command == "O" and res_org.is_confident
    print("  Organic override OK (label=Organic, conf=0.94, cmd=O, is_confident=True)")

    detector.set_manual_override("Plastic", 0.95)
    res_pla = detector.detect(dummy_frame)
    assert res_pla.label == "Plastic" and res_pla.confidence == 0.95 and res_pla.command == "P" and res_pla.is_confident
    print("  Plastic override OK (label=Plastic, conf=0.95, cmd=P, is_confident=True)")

    detector.set_manual_override("Metal", 0.92)
    res_met = detector.detect(dummy_frame)
    assert res_met.label == "Metal" and res_met.confidence == 0.92 and res_met.command == "M" and res_met.is_confident
    print("  Metal override OK (label=Metal, conf=0.92, cmd=M, is_confident=True)")

    detector.set_manual_override("Plastic", 0.58)
    res_low = detector.detect(dummy_frame)
    assert not res_low.is_confident, "Confidence 0.58 should be flagged as not confident (< 0.70)"
    print("  Low confidence override OK (conf=0.58, is_confident=False -> reposition prompt)")

    detector.set_manual_override(None)
    print("  -> Passed manual override tests.")


def test_camera_robustness():
    print("\n[TEST 4] Testing Camera class...")
    cam = Camera(source=0)
    print(f"  Camera available: {cam.available}")
    if cam.available:
        ok, frame = cam.read()
        print(f"  Frame read success: {ok}, Frame shape: {frame.shape if ok else None}")
        cam.release()
        print("  Camera released.")
    else:
        print("  Camera source 0 not currently accessible (device busy or no webcam attached).")
        print("  Graceful fallback confirmed (no crash).")


def test_drawing_pipeline():
    print("\n[TEST 5] Testing draw_hud overlay rendering without display...")
    from main import draw_hud
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detector = WasteDetector()

    # Test with confident result
    detector.set_manual_override("Plastic", 0.94)
    res = detector.detect(dummy_frame)
    out_frame = draw_hud(dummy_frame.copy(), res)
    assert out_frame.shape == dummy_frame.shape

    # Test with low confidence result
    detector.set_manual_override("Organic", 0.55)
    res_low = detector.detect(dummy_frame)
    out_frame_low = draw_hud(dummy_frame.copy(), res_low)
    assert out_frame_low.shape == dummy_frame.shape

    # Test with None
    out_frame_none = draw_hud(dummy_frame.copy(), None)
    assert out_frame_none.shape == dummy_frame.shape

    print("  -> Passed drawing and HUD overlay test.")


if __name__ == "__main__":
    print("========================================")
    print("Running EcoNova Stage 1 Verification Suite")
    print("========================================")
    test_detector_logic()
    test_camera_robustness()
    test_drawing_pipeline()
    print("\nALL STAGE 1 TESTS PASSED SUCCESSFULLY!")
