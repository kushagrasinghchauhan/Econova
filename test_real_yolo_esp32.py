import sys
import os
import cv2

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hardware"))

from detector import WasteDetector
from esp32_controller import ESP32Controller


IMAGE_PATH = r"C:\Users\kusha\OneDrive\Desktop\bottle\bottle.jpeg"
ESP32_PORT = "COM7"


print("=" * 60)
print("EcoNova: REAL YOLO → ESP32 → SERVO")
print("=" * 60)


# 1. Load YOLO
print("\n[1] Loading YOLO...")

detector = WasteDetector()

print("✅ YOLO loaded")


# 2. Connect ESP32
print("\n[2] Connecting to ESP32...")

esp32 = ESP32Controller(
    port=ESP32_PORT,
    baudrate=115200
)

if not esp32.connect():
    print("❌ ESP32 connection failed")
    exit()

print("✅ ESP32 connected on COM7")


# 3. Load bottle image
print("\n[3] Loading real bottle image...")

if not os.path.exists(IMAGE_PATH):
    print("❌ Bottle image not found:")
    print(IMAGE_PATH)
    esp32.close()
    exit()

frame = cv2.imread(IMAGE_PATH)

if frame is None:
    print("❌ Could not read bottle image")
    esp32.close()
    exit()

print("✅ Bottle image loaded")


# 4. Run YOLO
print("\n[4] Running YOLO...")

result = detector.detect(frame)

if result is None:
    print("❌ YOLO did not detect any waste")
    esp32.close()
    exit()


print("\nYOLO RESULT")
print("----------------------------")
print("Raw class   :", result.raw_class)
print("Category    :", result.label)
print("Confidence  :", f"{result.confidence:.2%}")
print("Confident   :", result.is_confident)


# 5. Check confidence
if not result.is_confident:
    print("\n❌ Detection confidence too low")
    print("Servo will NOT move.")
    esp32.close()
    exit()


# 6. Send category to ESP32
print("\n[5] Sending YOLO result to ESP32...")

print(f"Sending category: {result.label}")

success = esp32.sort(result.label)

if success:
    print(f"✅ ESP32 received: {result.label}")
else:
    print("❌ Failed to send command")
    esp32.close()
    exit()


# 7. Success
print("\n" + "=" * 60)
print("🎉 REAL YOLO → ESP32 → SERVO TEST PASSED!")
print("=" * 60)

print("\nComplete pipeline:")
print("Bottle image")
print("     ↓")
print("YOLO")
print(f"     ↓")
print(f"{result.raw_class} → {result.label}")
print("     ↓")
print("ESP32 COM7")
print("     ↓")
print("Servo")


esp32.close()

print("\nESP32 connection closed.")