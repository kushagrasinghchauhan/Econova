import serial
import time

PORT = "COM7"
BAUD = 115200

esp32 = serial.Serial(PORT, BAUD, timeout=2)

print("ESP32 connected on", PORT)

time.sleep(2)

commands = ["ORGANIC", "PLASTIC", "METAL"]

for command in commands:
    print("Sending:", command)

    esp32.write((command + "\n").encode())

    response = esp32.readline().decode(errors="ignore").strip()

    if response:
        print("ESP32:", response)
    else:
        print("No response")

    time.sleep(2)

esp32.close()

print("Phase 2 communication test complete!")