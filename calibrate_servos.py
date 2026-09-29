"""
calibrate_servos.py
-------------------
Manual Hardware Calibration & Servo Verification Tool for EcoNova.

Helps physically align:
- G18 (GPIO 18) Destination Selector:
    0°   -> Organic bin
    30°  -> Dry/Plastic bin (Center / Startup default)
    90°  -> Metal bin
- G19 (GPIO 19) Waste Release Flap:
    0°   -> Closed (holds waste)
    180° -> Open (releases waste)

Usage:
    python calibrate_servos.py                      # Interactive menu
    python calibrate_servos.py --g18 30             # Set G18 to specific angle
    python calibrate_servos.py --g19 0              # Set G19 to specific angle
    python calibrate_servos.py --sort Organic       # Test Organic sorting cycle
    python calibrate_servos.py --sort Plastic       # Test Plastic sorting cycle
    python calibrate_servos.py --sort Paper         # Test Paper sorting cycle
    python calibrate_servos.py --sort Metal         # Test Metal sorting cycle
    python calibrate_servos.py --test-all           # Run automated calibration sweep
"""

import os
import sys
import time
import argparse
import serial

PORT = os.environ.get("ESP32_PORT", "COM7")
BAUD = 115200


def open_serial():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=2)
        time.sleep(2)  # ESP32 bootloader settling time
        print(f"[OK] Connected to ESP32 on {PORT} @ {BAUD} baud.")
        return ser
    except Exception as e:
        print(f"[ERROR] Could not connect to ESP32 on {PORT}: {e}")
        print("Tip: Check device manager for the correct COM port or run:")
        print("     $env:ESP32_PORT='COM6'; python calibrate_servos.py")
        return None


def send_command(ser, cmd):
    print(f"\n>>> Sending: {cmd}")
    ser.write(f"{cmd}\n".encode("utf-8"))
    ser.flush()

    start = time.time()
    while time.time() - start < 3.5:
        if ser.in_waiting > 0:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                print(f"    [ESP32] {line}")
                if "SORTED" in line:
                    break
        time.sleep(0.05)


def run_interactive(ser):
    menu = """
=====================================================
          EcoNova Servo Hardware Calibration
=====================================================
G18 (Destination Selector - GPIO 18):
  [1] G18 -> 0°   (Organic compartment)
  [2] G18 -> 30°  (Dry/Plastic compartment - Neutral)
  [3] G18 -> 90°  (Metal compartment)

G19 (Waste Release Flap - GPIO 19):
  [4] G19 -> 0°   (Flap CLOSED - holds waste)
  [5] G19 -> 180° (Flap OPEN - releases waste)

Full Sorting Cycle Tests:
  [6] Full sequence: ORGANIC (G18: 0° -> wait -> G19: 180° -> 0°)
  [7] Full sequence: PLASTIC (G18: 30° -> wait -> G19: 180° -> 0°)
  [8] Full sequence: PAPER   (G18: 30° -> wait -> G19: 180° -> 0°)
  [9] Full sequence: METAL   (G18: 90° -> wait -> G19: 180° -> 0°)

  [A] Automated calibration sweep (tests all positions)
  [Q] Quit
=====================================================
Enter choice: """

    while True:
        choice = input(menu).strip().upper()
        if choice == "1":
            send_command(ser, "G18:0")
        elif choice == "2":
            send_command(ser, "G18:30")
        elif choice == "3":
            send_command(ser, "G18:90")
        elif choice == "4":
            send_command(ser, "G19:0")
        elif choice == "5":
            send_command(ser, "G19:180")
        elif choice == "6":
            send_command(ser, "ORGANIC")
        elif choice == "7":
            send_command(ser, "PLASTIC")
        elif choice == "8":
            send_command(ser, "PAPER")
        elif choice == "9":
            send_command(ser, "METAL")
        elif choice == "A":
            run_sweep(ser)
        elif choice in ("Q", "QUIT", "EXIT"):
            print("Exiting calibration tool.")
            break
        else:
            print("Invalid choice, please select 1-9, A, or Q.")


def run_sweep(ser):
    print("\n--- Starting Calibration Sweep ---")
    steps = [
        ("G18:30", "Moving G18 to center position (30°)..."),
        ("G19:0", "Ensuring G19 flap is CLOSED (0°)..."),
        ("G18:0", "Moving G18 to Organic position (0°)..."),
        ("G18:30", "Moving G18 to Dry/Plastic position (30°)..."),
        ("G18:90", "Moving G18 to Metal position (90°)..."),
        ("G18:30", "Returning G18 to center position (30°)..."),
        ("G19:180", "Opening G19 release flap (180°)..."),
        ("G19:0", "Closing G19 release flap back to CLOSED (0°)...")
    ]
    for cmd, desc in steps:
        print(f"\n[SWEEP] {desc}")
        send_command(ser, cmd)
        time.sleep(1.0)
    print("\n[OK] Calibration sweep completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="EcoNova Servo Hardware Calibration Tool")
    parser.add_argument("--g18", type=int, help="Move G18 directly to angle (e.g. 0, 30, 90)")
    parser.add_argument("--g19", type=int, help="Move G19 directly to angle (e.g. 0, 180)")
    parser.add_argument("--sort", type=str, choices=["Organic", "Plastic", "Paper", "Metal"], help="Execute full sorting sequence")
    parser.add_argument("--test-all", action="store_true", help="Run automated calibration sweep")
    args = parser.parse_args()

    ser = open_serial()
    if not ser:
        sys.exit(1)

    try:
        if args.g18 is not None:
            send_command(ser, f"G18:{args.g18}")
        elif args.g19 is not None:
            send_command(ser, f"G19:{args.g19}")
        elif args.sort:
            cmd = "PLASTIC" if args.sort == "Paper" else args.sort.upper()
            send_command(ser, cmd)
        elif args.test_all:
            run_sweep(ser)
        else:
            run_interactive(ser)
    finally:
        ser.close()
        print("\nSerial connection closed.")


if __name__ == "__main__":
    main()
