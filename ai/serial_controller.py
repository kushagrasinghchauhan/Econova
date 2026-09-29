"""
serial_controller.py
--------------------
Manages USB Serial communication between the laptop and the ESP32.

Target Protocol:
    Laptop -> ESP32:
        "O" = Organic
        "P" = Plastic
        "M" = Metal

    ESP32 -> Laptop:
        "[CATEGORY] RECEIVED"
        "SORTED"

Error Handling:
    If ESP32 is unplugged, missing, or the port is invalid, this module
    gracefully fails without crashing, allowing EcoNova to operate in Demo Mode.
"""

import os
import sys
import time

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


# =====================================================================
# CONFIGURATION
# Change SERIAL_PORT to match your ESP32 COM port on Windows (e.g. "COM3", "COM4", "COM5").
# You can also set the ECONOVA_PORT environment variable without editing this file.
# =====================================================================
SERIAL_PORT = os.environ.get("ECONOVA_PORT", "COM5")
BAUD_RATE = 115200


# Category to single-character command mapping
CATEGORY_MAP = {
    "Organic": "O",
    "Plastic": "P",
    "Metal": "M",
    "O": "O",
    "P": "P",
    "M": "M",
}


def list_ports():
    """Returns a list of descriptions of currently available COM ports."""
    if not PYSERIAL_AVAILABLE:
        return []
    ports = serial.tools.list_ports.comports()
    return [(p.device, p.description) for p in ports]


class SerialController:
    def __init__(self, port=SERIAL_PORT, baud_rate=BAUD_RATE, timeout=1.5):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.connection = None

    def is_connected(self):
        """Returns True if the serial port is currently open and valid."""
        return self.connection is not None and self.connection.is_open

    def connect(self):
        """
        Attempts connection to ESP32.
        If ESP32 is not connected, does NOT crash - logs notice and returns False.
        """
        if not PYSERIAL_AVAILABLE:
            print("[Serial] pyserial is not installed. Install with: pip install pyserial")
            return False

        try:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            # ESP32 auto-resets when DTR is toggled on connection; allow it to boot
            time.sleep(2.0)
            # Flush any bootloader logs
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()
            print(f"[Serial] Connected to ESP32 on {self.port} at {self.baud_rate} baud.")
            return True

        except (serial.SerialException, OSError) as e:
            self.connection = None
            print(f"[Serial] ESP32 not connected on {self.port} — running in Demo Mode.")
            return False

    def disconnect(self):
        """Safely closes the serial connection if open."""
        if self.is_connected():
            try:
                self.connection.close()
                print(f"[Serial] Disconnected from {self.port}.")
            except Exception:
                pass
        self.connection = None

    def send_category(self, category):
        """
        Translates category ("Organic", "Plastic", "Metal") into "O", "P", or "M"
        and transmits it over USB serial to the ESP32.

        Returns (success: bool, command_sent: str or None)
        """
        cmd = CATEGORY_MAP.get(category)
        if not cmd:
            print(f"[Serial] Unknown category: {category}. Must be Organic, Plastic, or Metal.")
            return False, None

        if not self.is_connected():
            return False, cmd

        try:
            # Send single character command followed by newline
            payload = (cmd + "\n").encode("utf-8")
            self.connection.write(payload)
            self.connection.flush()
            print(f"[Serial] Transmitted '{cmd}' to ESP32.")
            return True, cmd
        except (serial.SerialException, OSError) as e:
            print(f"[Serial] Transmission error on {self.port}: {e}")
            self.disconnect()
            return False, cmd

    def read_line(self, timeout=None):
        """
        Reads a line of text sent back from the ESP32 (e.g. 'ORGANIC RECEIVED', 'SORTED').
        Returns trimmed string, or None if timed out / not connected.
        """
        if not self.is_connected():
            return None

        orig_timeout = self.connection.timeout
        if timeout is not None:
            self.connection.timeout = timeout

        try:
            line = self.connection.readline().decode("utf-8", errors="replace").strip()
            return line if line else None
        except Exception:
            return None
        finally:
            if timeout is not None:
                self.connection.timeout = orig_timeout
