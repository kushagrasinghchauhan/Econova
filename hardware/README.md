# EcoNova ESP32 Hardware Integration Guide

This directory contains both the **Host Python Driver** (running on your laptop) and the **ESP32 Firmware Sketch** (running on the microcontroller) to control the IR sensor and servo motors.

---

## Architecture Overview

```
[IR Proximity Sensor] 
         │ (GPIO 13)
         ▼
    ┌──────────┐   USB Serial (COM6 @ 115200)   ┌───────────────────────────┐
    │  ESP32   │ ◄────────────────────────────► │ Flask Backend & YOLO11n   │
    └────┬─────┘                                │ hardware/esp32_controller │
         │                                      └───────────────────────────┘
         ├─► (GPIO 18 PWM) Chute Flap Servo (SG90 / MG996R)
         └─► (GPIO 19 PWM) Trapdoor Release Servo (SG90 / MG996R)
```

---

## File Locations

1. **ESP32 Arduino Firmware (Microcontroller C++)**:
   - [`hardware/esp32_firmware/esp32_firmware.ino`](file:///C:/Users/kusha/OneDrive/Desktop/econova/hardware/esp32_firmware/esp32_firmware.ino)
2. **Host Python Serial Controller (Flask Backend)**:
   - [`hardware/esp32_controller.py`](file:///C:/Users/kusha/OneDrive/Desktop/econova/hardware/esp32_controller.py)

---

## Wiring & Pinout Diagram

### 1. IR Proximity Sensor (Intake Detection)
| IR Sensor Pin | ESP32 Pin | Note |
| :--- | :--- | :--- |
| **VCC** | **3.3V or 5V** | Depending on your IR module rating |
| **GND** | **GND** | Common Ground |
| **OUT** | **GPIO 13** | Digital input (reads LOW when waste enters chamber) |

---

### 2. Servo Motors (Sorting Mechanism)
> [!IMPORTANT]
> Always power SG90 or MG996R servos from an **external 5V (2A+) power supply**, sharing the **GND** with the ESP32. Do not power high-torque servos directly from the ESP32 3.3V pin.

#### Flap Servo (Direction / Bin Selector Chute)
| Servo Wire | Connection |
| :--- | :--- |
| **Signal (Orange/Yellow)** | **GPIO 18** (PWM) |
| **VCC (Red)** | **External +5V** |
| **GND (Brown/Black)** | **Common GND** |

#### Drop Trapdoor Servo (Release Mechanism)
| Servo Wire | Connection |
| :--- | :--- |
| **Signal (Orange/Yellow)** | **GPIO 19** (PWM) |
| **VCC (Red)** | **External +5V** |
| **GND (Brown/Black)** | **Common GND** |

---

## Sorting Angles Configuration

In [`esp32_firmware.ino`](file:///C:/Users/kusha/OneDrive/Desktop/econova/hardware/esp32_firmware/esp32_firmware.ino):

```cpp
#define FLAP_IDLE_ANGLE     90    // Center / neutral resting position
#define FLAP_ORGANIC_ANGLE  40    // Directs waste to Organic bin
#define FLAP_PLASTIC_ANGLE  90    // Directs waste to Plastic bin
#define FLAP_METAL_ANGLE   140    // Directs waste to Metal bin

#define DROP_CLOSED_ANGLE    0    // Holding tray closed
#define DROP_OPEN_ANGLE     90    // Opens to let waste fall into the selected bin
```

---

## How to Flash to ESP32

1. Open **Arduino IDE**.
2. Go to **Tools -> Manage Libraries...**, search for **`ESP32Servo`** (by Kevin Harrington), and click **Install**.
3. Open [`hardware/esp32_firmware/esp32_firmware.ino`](file:///C:/Users/kusha/OneDrive/Desktop/econova/hardware/esp32_firmware/esp32_firmware.ino).
4. Select **Tools -> Board -> ESP32 Arduino -> ESP32 Dev Module**.
5. Select **Tools -> Port -> COM6** (or your active COM port).
6. Click **Upload** (Arrow icon).
7. Once uploaded, the ESP32 will output `ECONOVA_ESP32_READY` at `115200` baud.
