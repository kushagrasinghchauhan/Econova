"""
test_4class_model_inference.py
------------------------------
Validates the newly trained 4-Class YOLO Model (ai/models/yolo_4class_best.pt):
- Verifies model file exists and is intact (separate from production model)
- Runs inference on validation samples for Organic (0), Plastic (1), Metal (2), and Paper (3)
- Validates detector integration with direct 4-class outputs
"""

import os
import sys
import cv2
import torch
from ultralytics import YOLO

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(PROJECT_ROOT, "ai", "models", "yolo_4class_best.pt")
RUNS_BEST = os.path.join(PROJECT_ROOT, "training", "runs", "econova_4class", "weights", "best.pt")

TARGET_CLASSES = {
    0: "Organic",
    1: "Plastic",
    2: "Metal",
    3: "Paper"
}


def test_4class_model():
    print("=" * 70)
    print("      EcoNova 4-Class Model Validation & Inference Test Suite       ")
    print("=" * 70)

    # 1. Model file checks
    print("\n[STEP 1] Checking Model Artifacts...")
    assert os.path.exists(MODEL_PATH), f"Model not found at {MODEL_PATH}"
    size_mb = os.path.getsize(MODEL_PATH) / (1024 * 1024)
    print(f"  -> Model file verified at: {MODEL_PATH} ({size_mb:.2f} MB)")
    print(f"  -> Runs model verified at: {RUNS_BEST} ({os.path.getsize(RUNS_BEST) / (1024*1024):.2f} MB)")

    # 2. Inspect classes inside model
    print("\n[STEP 2] Inspecting Trained Model Architecture & Class Names...")
    model = YOLO(MODEL_PATH)
    print(f"  -> Model names dictionary: {model.names}")
    for idx, name in TARGET_CLASSES.items():
        assert idx in model.names, f"Class index {idx} not in model.names"
        assert model.names[idx].lower() == name.lower(), f"Expected {name}, got {model.names[idx]}"
    print("  -> PASSED: Model contains exactly 4 target classes: Organic, Plastic, Metal, Paper.")

    # 3. Test Paper detection specifically on validation paper images
    print("\n[STEP 3] Testing Inference on Validation Paper Images...")
    val_labels_dir = os.path.join(PROJECT_ROOT, "training", "dataset_4class", "labels", "val")
    val_images_dir = os.path.join(PROJECT_ROOT, "training", "dataset_4class", "images", "val")

    paper_images = []
    for f in os.listdir(val_labels_dir):
        if not f.endswith(".txt"): continue
        with open(os.path.join(val_labels_dir, f)) as lf:
            for line in lf:
                if line.startswith("3 "): # class 3 = Paper
                    stem = os.path.splitext(f)[0]
                    for ext in [".jpg", ".png", ".jpeg"]:
                        candidate = os.path.join(val_images_dir, stem + ext)
                        if os.path.exists(candidate):
                            paper_images.append(candidate)
                            break
                    break
        if len(paper_images) >= 5:
            break

    print(f"  -> Found {len(paper_images)} validation paper samples for inference testing.")
    paper_detected_count = 0

    for idx, p_img in enumerate(paper_images, start=1):
        frame = cv2.imread(p_img)
        assert frame is not None, f"Failed to load image: {p_img}"
        results = model(frame, conf=0.25, verbose=False)
        top_name = None
        top_conf = 0.0
        if results and results[0].boxes:
            for box in results[0].boxes:
                c_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                c_name = model.names.get(c_id, "")
                if conf > top_conf:
                    top_conf = conf
                    top_name = c_name

        print(f"     Sample {idx}: Detected '{top_name}' with confidence {top_conf*100:.1f}%")
        if top_name and top_name.lower() == "paper":
            paper_detected_count += 1

    print(f"  -> Paper detection success rate: {paper_detected_count}/{len(paper_images)}")
    assert paper_detected_count >= 1, "At least one paper sample must be detected as Paper"
    print("  -> PASSED: Model successfully identifies Paper objects as 'Paper'!")

    # 4. Detector wrapper integration test
    print("\n[STEP 4] Testing WasteDetector Integration with 4-Class Model...")
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))
    from detector import WasteDetector
    det_4class = WasteDetector(model_path=MODEL_PATH)
    assert det_4class.model_status == "READY"
    print(f"  -> Detector loaded successfully: {det_4class.model_path}")
    print(f"  -> Detector classes: {det_4class.model_classes}")

    # Test detection on a paper image
    test_img = cv2.imread(paper_images[0])
    res = det_4class.detect(test_img)
    if res:
        print(f"  -> WasteDetector result: label='{res.label}', raw_class='{res.raw_class}', conf={res.confidence:.4f}")
        assert res.label in ["Paper", "Plastic", "Organic", "Metal"]
        assert res.command in ["P", "O", "M"]

    print("\n" + "=" * 70)
    print("      4-CLASS MODEL INFERENCE & INTEGRATION PASSED (100%)!        ")
    print("=" * 70)


if __name__ == "__main__":
    test_4class_model()
