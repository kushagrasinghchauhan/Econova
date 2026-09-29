import serial
import time

PORT = "COM6"
BAUD = 115200

esp32 = serial.Serial(PORT, BAUD, timeout=2)

time.sleep(2)

print("ESP32 connected!")

for command in ["PLASTIC", "ORGANIC", "METAL"]:
    print("Sending:", command)

    esp32.write((command + "\n").encode())

    time.sleep(0.5)

    response = esp32.readline().decode(errors="ignore").strip()

    print("ESP32:", response)

esp32.close()
print("Test complete!")


