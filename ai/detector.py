from pathlib import Path
from typing import Optional

from ultralytics import YOLO


# ============================================================
# EcoNova 3-Class Waste Detector
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = BASE_DIR / "ai" / "models" / "yolo_3class_best.pt"

CLASS_NAMES = [
    "Organic",
    "Plastic",
    "Metal",
]

CONFIDENCE_THRESHOLD = 0.70


class DetectionResult:
    def __init__(
        self,
        label: str,
        confidence: float,
        command: Optional[str],
        box: Optional[tuple] = None,
        is_confident: bool = True,
    ):
        self.label = label
        self.confidence = confidence
        self.command = command
        self.box = box
        self.is_confident = is_confident

    def to_dict(self):
        return {
            "label": self.label,
            "confidence": self.confidence,
            "command": self.command,
            "box": self.box,
            "is_confident": self.is_confident,
        }


class WasteDetector:

    def __init__(self, model_path=MODEL_PATH):

        self.model_path = Path(model_path)
        self.detector_title = "EcoNova 3-Class Waste Detector"

        print(
            f"[Detector] Loading EcoNova 3-class model from "
            f"{self.model_path}"
        )

        self.model = None

        if not self.model_path.exists():
            print(
                f"[Detector] WARNING: Model not found: "
                f"{self.model_path}"
            )
            return

        try:
            self.model = YOLO(str(self.model_path))

            print(
                "[Detector] EcoNova 3-Class Waste Detection "
                "successfully initialized!"
            )

            print(
                "[Detector] Classes enabled: "
                "Organic, Plastic, Metal"
            )

            print(
                f"[Detector] Model classes: {self.model.names}"
            )

        except Exception as e:
            print(
                f"[Detector] ERROR loading model: {e}"
            )
            self.model = None

        self.last_rejection = None

    # ========================================================
    # Backend compatibility status
    # ========================================================

    def get_status(self):

        if self.model is None:
            return {
                "model_status": "YOLO_MODEL_MISSING",
                "model_path": str(self.model_path),
                "detector_title": self.detector_title,
                "classes": CLASS_NAMES,
                "ready": False,
                "is_ready": False,
            }

        return {
            "model_status": "YOLO_MODEL_READY",
            "model_path": str(self.model_path),
            "detector_title": self.detector_title,
            "classes": CLASS_NAMES,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "ready": True,
            "is_ready": True,
        }

    # ========================================================
    # Waste detection
    # ========================================================

    def detect(self, frame) -> Optional[DetectionResult]:

        if self.model is None:
            return None

        results = self.model(
            frame,
            conf=0.25,
            verbose=False
        )

        if not results:
            return None

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            self.last_rejection = None
            return None

        best_index = None
        best_confidence = 0.0

        # Find highest-confidence detection
        for i, box in enumerate(result.boxes):
            confidence = float(box.conf[0])
            if confidence > best_confidence:
                best_confidence = confidence
                best_index = i

        if best_index is None:
            self.last_rejection = None
            return None

        box = result.boxes[best_index]
        class_id = int(box.cls[0])

        if class_id < 0 or class_id >= len(CLASS_NAMES):
            self.last_rejection = None
            return None

        label = CLASS_NAMES[class_id]

        # Extract box coordinates (x1, y1, x2, y2) if present
        box_coords = None
        try:
            xyxy = box.xyxy[0].tolist()
            box_coords = (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))
        except Exception:
            box_coords = None

        # Require 70% confidence
        if best_confidence < CONFIDENCE_THRESHOLD:
            self.last_rejection = {
                "label": label,
                "confidence": best_confidence,
                "threshold": CONFIDENCE_THRESHOLD,
            }
            return None

        self.last_rejection = None

        # ====================================================
        # ESP32 commands
        #
        # Organic -> O -> G18 = 0°
        # Plastic -> P -> G18 = 30°
        # Metal   -> M -> G18 = 90°
        # ====================================================

        command_map = {
            "Organic": "O",
            "Plastic": "P",
            "Metal": "M",
        }

        command = command_map.get(label)

        return DetectionResult(
            label=label,
            confidence=best_confidence,
            command=command,
            box=box_coords,
        )