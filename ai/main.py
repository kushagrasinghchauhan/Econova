"""
main.py
-------
EcoNova - Stage 1: AI & Webcam Waste Detection.

Opens the webcam, runs waste classification on each frame, renders bounding
boxes and HUD status overlays, and handles high/low confidence states.

Serial communication to ESP32 will be integrated in Stage 2. For now,
DEMO_MODE is active and displays the command that WOULD be sent.

Run with:  python main.py   (from inside the ai/ directory)
           or python ai/main.py (from project root)

Keyboard Controls:
    q : Quit application
    o : Demo force Organic (94% confidence)
    p : Demo force Plastic (95% confidence)
    m : Demo force Metal (92% confidence)
    l : Demo force Low Confidence (58% confidence - reposition message)
    c : Return to automatic rotation / continuous detection
"""

import sys
import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
import cv2

# Ensure the directory containing this file is in Python's import path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from camera import get_camera
from detector import WasteDetector, CONFIDENCE_THRESHOLD

# ---------------------------------------------------------------
# DEMO_MODE: In Stage 1, this is set to True. ESP32 is not touched.
# Commands are formatted and printed so the logic is fully verifiable.
# ---------------------------------------------------------------
DEMO_MODE = True

# Color definitions (BGR for OpenCV)
COLOR_BG = (28, 28, 30)
COLOR_TEXT_WHITE = (245, 245, 245)
COLOR_GREEN = (46, 204, 113)     # Confident / Organic
COLOR_BLUE = (235, 149, 52)      # Plastic (Sky/Cyan tint in BGR)
COLOR_YELLOW = (0, 215, 255)     # Metal (Gold/Amber)
COLOR_ORANGE = (0, 140, 255)     # Warning / Low confidence
COLOR_MUTED = (160, 160, 160)

CLASS_COLORS = {
    "Organic": (46, 204, 113),   # Fresh Green
    "Plastic": (235, 149, 52),   # Blue / Cyan
    "Metal": (0, 215, 255),      # Gold
}


def draw_hud(frame, result):
    """
    Renders top status panel, bounding box, and keyboard help footer.
    """
    h, w = frame.shape[:2]

    # --- 1. Top HUD Bar ---
    # Draw translucent dark header panel
    hud_h = 95
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_h), COLOR_BG, thickness=-1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.line(frame, (0, hud_h), (w, hud_h), (60, 60, 65), 1)

    # --- 2. Process Detection State ---
    if result is None:
        cv2.putText(frame, "Waiting for waste item...", (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_TEXT_WHITE, 2)
        cv2.putText(frame, "Place an object in camera view", (20, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_MUTED, 1)
        return frame

    # Bounding Box Rendering
    if result.box is not None:
        x1, y1, x2, y2 = result.box
        box_color = CLASS_COLORS.get(result.label, COLOR_GREEN) if result.is_confident else COLOR_ORANGE

        # Draw main bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

        # Draw corner accents for high-tech HUD feel
        corner_len = 20
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), box_color, 4)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), box_color, 4)
        cv2.line(frame, (x2, y1), (x2 - corner_len, y1), box_color, 4)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), box_color, 4)
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), box_color, 4)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_len), box_color, 4)
        cv2.line(frame, (x2, y2), (x2 - corner_len, y2), box_color, 4)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_len), box_color, 4)

        # Bounding box tag badge
        tag_text = f"{result.label.upper()}: {result.confidence*100:.0f}%"
        (tw, th), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        tag_y1 = max(hud_h + 5, y1 - th - 10)
        cv2.rectangle(frame, (x1, tag_y1), (x1 + tw + 14, tag_y1 + th + 10), box_color, -1)
        cv2.putText(frame, tag_text, (x1 + 7, tag_y1 + th + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    # Status Display inside Top HUD Bar
    if not result.is_confident:
        # LOW CONFIDENCE STATE (< 0.70)
        cv2.putText(frame, "Low confidence", (20, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, COLOR_ORANGE, 2)
        cv2.putText(frame, "Please reposition waste", (20, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, COLOR_ORANGE, 2)
        cv2.putText(frame, f"(Detected: {result.label} at {result.confidence*100:.0f}%)",
                    (w - 280, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_MUTED, 1)
    else:
        # HIGH CONFIDENCE STATE (>= 0.70)
        accent_color = CLASS_COLORS.get(result.label, COLOR_GREEN)
        detected_text = f"Detected: {result.label.upper()}"
        conf_text = f"Confidence: {result.confidence*100:.0f}%"
        status_text = f"ESP32 Command: {result.command}   |   Status: Ready for Sorting"

        cv2.putText(frame, detected_text, (20, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, accent_color, 2)
        cv2.putText(frame, conf_text, (20, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_TEXT_WHITE, 1)
        cv2.putText(frame, status_text, (20, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 255, 180), 1)

    # Simulation watermark badge
    if result.simulated:
        cv2.putText(frame, "[DEMO / SIMULATED MODE]", (w - 250, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

    # --- 3. Bottom Footer Keyboard Guide ---
    footer_y = h - 12
    footer_text = "Keys: [O] Organic  [P] Plastic  [M] Metal  [L] Low Conf  [C] Cycle  [Q] Quit"
    cv2.putText(frame, footer_text, (15, footer_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    return frame


def print_detection_log(result):
    """
    Outputs clean log to console when a confident detection is made.
    """
    print(f"Detected: {result.label.upper()}")
    print(f"Confidence: {result.confidence*100:.0f}%")
    print(f"ESP32 Command: {result.command}")
    if DEMO_MODE:
        print("Status: Ready for Sorting (DEMO_MODE - not sent to ESP32)")
    else:
        print("Status: Ready for Sorting (Sent to ESP32)")
    print("-" * 45)


def main():
    print("=" * 55)
    print("      EcoNova - Stage 1: Waste Detection System      ")
    print(f"      DEMO_MODE = {DEMO_MODE}                           ")
    print(f"      Confidence Threshold = {CONFIDENCE_THRESHOLD*100:.0f}%                     ")
    print("=" * 55)

    detector = WasteDetector()
    status = detector.get_status()

    print("-" * 55)
    print("MODEL INSPECTION REPORT:")
    print(f"  Model Path  : {status['model_path']}")
    print(f"  File Exists : {status['model_exists']}")
    print(f"  Active Mode : {status['mode']}")
    print(f"  Classes     : {status['classes']}")
    print(f"  Note        : {status['note']}")
    print("-" * 55)

    cam = get_camera(source=0)
    if not cam.available:
        print("\n[ERROR] No webcam available to open.")
        print("[Tip] If your webcam is busy with another app, close it and retry.")
        print("[Tip] If using an external USB webcam, change source=1 in ai/main.py.\n")
        sys.exit(1)

    print("\n[Live] Press 'q' in the camera window to exit.")
    print("[Live] Interactive demo keys: 'o'=Organic, 'p'=Plastic, 'm'=Metal, 'l'=Low conf, 'c'=Cycle\n")

    last_reported_state = None

    try:
        while True:
            ok, frame = cam.read()
            if not ok or frame is None:
                # Brief sleep to avoid 100% CPU on frame read retry
                cv2.waitKey(10)
                continue

            result = detector.detect(frame)
            frame = draw_hud(frame, result)

            if result is not None and result.is_confident:
                state_key = (result.label, int(result.confidence * 10))
                if state_key != last_reported_state:
                    print_detection_log(result)
                    last_reported_state = state_key
            else:
                last_reported_state = None

            cv2.imshow("EcoNova - AI Waste Segregation", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                print("\n[EcoNova] 'q' pressed. Exiting...")
                break
            elif key == ord('o'):
                print("[Key Demo] Forced Organic (94%)")
                detector.set_manual_override("Organic", 0.94)
            elif key == ord('p'):
                print("[Key Demo] Forced Plastic (95%)")
                detector.set_manual_override("Plastic", 0.95)
            elif key == ord('m'):
                print("[Key Demo] Forced Metal (92%)")
                detector.set_manual_override("Metal", 0.92)
            elif key == ord('l'):
                print("[Key Demo] Forced Low Confidence (58% - Reposition prompt)")
                detector.set_manual_override("Plastic", 0.58)
            elif key == ord('c'):
                print("[Key Demo] Resumed automatic rotation")
                detector.set_manual_override(None)

    except KeyboardInterrupt:
        print("\n[EcoNova] Interrupted by user (Ctrl+C).")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print("[EcoNova] Camera released. Windows closed. Done.")


if __name__ == "__main__":
    main()
