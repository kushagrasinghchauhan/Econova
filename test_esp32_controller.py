import os
from hardware.esp32_controller import ESP32Controller

port = os.environ.get("ESP32_PORT", "COM7")
esp32 = ESP32Controller(port=port)

try:
    esp32.connect()

    esp32.sort("Plastic")
    esp32.sort("Organic")
    esp32.sort("Metal")

finally:
    esp32.close()