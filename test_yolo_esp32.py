from ai.detector import WasteDetector
from hardware.esp32_controller import ESP32Controller
import time

print("=" * 60)
print("EcoNova: YOLO → ESP32 → SERVO TEST")
print("=" * 60)

# Start YOLO
detector = WasteDetector()

# Connect ESP32
esp32 = ESP32Controller(port="COM7", baudrate=115200)

if not esp32.connect():
    print("❌ ESP32 connection failed")
    exit()

print("✅ ESP32 connected")

# Test each category
for category in ["Organic", "Plastic", "Metal"]:

    print(f"\nSending: {category}")

    success = esp32.sort(category)

    if success:
        print(f"✅ ESP32 received {category}")
    else:
        print(f"❌ Failed to send {category}")

    time.sleep(3)

esp32.close()

print("\n" + "=" * 60)
print("YOLO → ESP32 communication test complete!")
print("=" * 60)