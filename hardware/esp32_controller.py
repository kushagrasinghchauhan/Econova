"""
hardware/esp32_controller.py
----------------------------
Serial controller interface for physical ESP32 waste segregation hardware.
Controls the two-servo physical sorting mechanism over USB-UART (default COM7 @ 115200 baud).

Physical Servo Roles:
- G18 (GPIO 18): DESTINATION SELECTOR SERVO — Directs waste to designated bin compartment (0°, 30°, 90°).
- G19 (GPIO 19): WASTE RELEASE SERVO — Flap holding waste; opens to 180° to drop waste, closes to 0°.

Speed & Smooth Movement Control:
- G18_MOVE_DELAY_MS = 15 ms/deg (controlled medium/slow speed)
- G19_OPEN_DELAY_MS = 8 ms/deg (moderately fast opening)
- G19_CLOSE_DELAY_MS = 12 ms/deg (slightly slower closing to reduce mechanical impact)

Exact Required Sorting Sequence:
1. G18 moves smoothly to destination angle FIRST (Organic=0°, Plastic/Paper=30°, Metal=90°).
2. Settle delay (G18_SETTLE_DELAY = 0.5s) for G18 to physically settle.
3. ONLY AFTER G18 settles, G19 opens smoothly to 180° (G19_RELEASE_OPEN = 180°).
4. Flap open delay (G19_OPEN_TIME = 1.2s) for waste to fall through.
5. G19 closes smoothly back to 0° (G19_RELEASE_CLOSED = 0°).
6. Flap close delay (G19_CLOSE_DELAY = 0.5s).
7. Sorting complete ("SORTED").
"""

import os
import time
import serial


# ==============================================================================
# CONFIGURABLE SERVO ANGLES (Calibrate for your physical mechanism)
# ==============================================================================
# G18: Destination Selector Servo (GPIO 18)
G18_DEFAULT_ANGLE = 30      # Neutral / center startup position (30°)
G18_ORGANIC_ANGLE = 0       # Directs waste to Organic bin (Left: 0°)
G18_DRY_PLASTIC_ANGLE = 30  # Directs waste to Dry/Plastic bin (Center: 30°)
G18_METAL_ANGLE = 90        # Directs waste to Metal bin (Right: 90°)

# Standard aliases
ORGANIC_ANGLE = G18_ORGANIC_ANGLE
DRY_PLASTIC_ANGLE = G18_DRY_PLASTIC_ANGLE
METAL_ANGLE = G18_METAL_ANGLE

# G19: Waste Release Flap Servo (GPIO 19)
G19_RELEASE_CLOSED = 0      # Flap CLOSED (holds waste at 0°)
G19_RELEASE_OPEN = 180      # Flap OPEN (releases waste to fall at 180°)

# Standard aliases
RELEASE_CLOSED = G19_RELEASE_CLOSED
RELEASE_OPEN = G19_RELEASE_OPEN

# Backward-compatibility aliases
SERVO1_HOME = G18_DEFAULT_ANGLE
SERVO1_OPEN = G18_DRY_PLASTIC_ANGLE
SERVO2_HOME = G19_RELEASE_CLOSED
SERVO2_ORGANIC = G18_ORGANIC_ANGLE
SERVO2_DRY_PLASTIC = G18_DRY_PLASTIC_ANGLE
SERVO2_METAL = G18_METAL_ANGLE


# G18: Controlled medium/slow speed for destination selector (ms/deg)
G18_MOVE_DELAY_MS = 15

# G19: Fast & Smooth S-Curve Trajectory Constants (50 Hz PWM synchronized)
G19_UPDATE_INTERVAL_MS = 20    # 20ms update interval matches 50Hz PWM cycle
G19_OPEN_DURATION_MS = 300     # 300ms opening stroke (~15 frames @ 20ms, max physical speed)
G19_CLOSE_DURATION_MS = 360    # 360ms closing stroke (~18 frames @ 20ms, soft landing)

# Backward-compatible alias constants
G19_OPEN_DELAY_MS = 8          # Equivalent speed reference (ms/deg)
G19_CLOSE_DELAY_MS = 12        # Equivalent speed reference (ms/deg)


# ==============================================================================
# CONFIGURABLE TIMING CONSTANTS (Seconds)
# ==============================================================================
G18_SETTLE_DELAY = 0.5   # Wait for G18 to reach destination and settle (0.5s)
G19_OPEN_TIME = 1.2      # Time G19 flap remains open for waste to fall (1.2s)
G19_CLOSE_DELAY = 0.5    # Wait after G19 flap closes before completing (0.5s)

# Total physical sorting sequence delay
SORTING_DELAY = round(G18_SETTLE_DELAY + G19_OPEN_TIME + G19_CLOSE_DELAY, 2)  # 2.2s total

# Backward-compatibility timing aliases
SORTER_SETTLE_DELAY = G18_SETTLE_DELAY
UPPER_FLAP_OPEN_TIME = G19_OPEN_TIME
POST_RELEASE_DELAY = G19_CLOSE_DELAY
SERVO2_RETURN_DELAY = 0.0


class ESP32Controller:
    """Controller for EcoNova ESP32 physical dual-servo sorting mechanism."""

    VALID_CATEGORIES = {"ORGANIC", "PLASTIC", "METAL", "PAPER", "O", "P", "M"}

    def __init__(self, port=None, baudrate=115200):
        if port is None:
            port = os.environ.get("ESP32_PORT", "COM6")
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.last_sequence_plan = None
        self.last_telemetry = []
        self.current_g18_angle = G18_DEFAULT_ANGLE
        self.current_g19_angle = G19_RELEASE_CLOSED

    @property
    def is_connected(self):
        """Returns True if the serial port is currently open."""
        return bool(self.serial and self.serial.is_open)

    def connect(self):
        """
        Attempts connection to ESP32 on the configured COM port.
        Returns True if successful, False if unavailable.
        """
        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=2
            )
            # Allow ESP32 bootloader settling time after DTR toggle
            time.sleep(2)
            print(f"[ESP32] Connected on {self.port}", flush=True)
            return True
        except Exception:
            self.serial = None
            print(f"[ESP32] Hardware unavailable on {self.port} - running in software-only mode", flush=True)
            return False

    def get_sequence_plan(self, category):
        """
        Returns the deterministic physical sequence plan for a given category:
        1. G18 (Destination Selector, GPIO18) moves to target angle FIRST
        2. Wait G18_SETTLE_DELAY (0.5s) for G18 to physically settle
        3. ONLY AFTER G18 settles, G19 (Release Flap, GPIO19) opens to 180°
        4. Wait G19_OPEN_TIME (1.2s) for waste to fall through
        5. G19 closes back to 0°
        6. Wait G19_CLOSE_DELAY (0.5s) for flap to settle closed
        7. Sorting complete.
        """
        cat_upper = category.upper()
        if cat_upper in ("PLASTIC", "PAPER", "P"):
            dest_angle = G18_DRY_PLASTIC_ANGLE
            dest_name = "DRY/PLASTIC"
            cmd = "PLASTIC"
        elif cat_upper in ("ORGANIC", "O"):
            dest_angle = G18_ORGANIC_ANGLE
            dest_name = "ORGANIC"
            cmd = "ORGANIC"
        elif cat_upper in ("METAL", "M"):
            dest_angle = G18_METAL_ANGLE
            dest_name = "METAL"
            cmd = "METAL"
        else:
            raise ValueError(f"Unknown category: {category}")

        return [
            {
                "step": 1,
                "servo": "G18",
                "role": "DESTINATION_SELECTOR",
                "action": "MOVE",
                "pin": 18,
                "target": dest_name,
                "angle": dest_angle,
                "step_delay_ms": G18_MOVE_DELAY_MS,
                "description": f"G18 destination selector moves smoothly to {dest_name} ({dest_angle}° @ {G18_MOVE_DELAY_MS}ms/deg)"
            },
            {
                "step": 2,
                "action": "WAIT",
                "duration": G18_SETTLE_DELAY,
                "description": f"Wait {G18_SETTLE_DELAY}s for G18 to physically settle"
            },
            {
                "step": 3,
                "servo": "G19",
                "role": "WASTE_RELEASE",
                "action": "OPEN",
                "pin": 19,
                "angle": G19_RELEASE_OPEN,
                "duration_ms": G19_OPEN_DURATION_MS,
                "step_delay_ms": G19_OPEN_DELAY_MS,
                "description": f"G19 waste release flap opens fast & smooth to {G19_RELEASE_OPEN}° (S-curve, {G19_OPEN_DURATION_MS}ms)"
            },
            {
                "step": 4,
                "action": "WAIT",
                "duration": G19_OPEN_TIME,
                "description": f"Wait {G19_OPEN_TIME}s for waste to fall through"
            },
            {
                "step": 5,
                "servo": "G19",
                "role": "WASTE_RELEASE",
                "action": "CLOSE",
                "pin": 19,
                "angle": G19_RELEASE_CLOSED,
                "duration_ms": G19_CLOSE_DURATION_MS,
                "step_delay_ms": G19_CLOSE_DELAY_MS,
                "description": f"G19 waste release flap closes fast & smooth back to {G19_RELEASE_CLOSED}° (S-curve, {G19_CLOSE_DURATION_MS}ms)"
            },
            {
                "step": 6,
                "action": "WAIT",
                "duration": G19_CLOSE_DELAY,
                "description": f"Wait {G19_CLOSE_DELAY}s for flap to settle closed"
            }
        ]

    def sort(self, category):
        """
        Initiates physical sorting sequence for the given category.
        Translates Paper -> PLASTIC hardware compartment.
        Returns True if transmitted successfully or planned, False otherwise.
        """
        cat_upper = category.upper()
        if cat_upper in ("PAPER", "P"):
            command = "PLASTIC"
        elif cat_upper in ("ORGANIC", "O"):
            command = "ORGANIC"
        elif cat_upper in ("METAL", "M"):
            command = "METAL"
        elif cat_upper in self.VALID_CATEGORIES:
            command = cat_upper
        else:
            print(f"[ESP32] Unsupported category: {category}", flush=True)
            return False

        # Build sequence plan
        self.last_sequence_plan = self.get_sequence_plan(category)
        self.last_telemetry = []

        if not self.is_connected:
            print(f"[ESP32 Software-Only] Planned sequence for {category} -> command {command}", flush=True)
            return True

        payload = f"{command}\n"
        self.serial.write(payload.encode("utf-8"))
        self.serial.flush()
        print(f"[ESP32] Sent: {command} (category: {category})", flush=True)
        return True

    def wait_for_sorting_delay(self, delay=None):
        """
        Waits for the physical two-servo sorting sequence to complete:
        1. G18 moves smoothly to destination angle (0°, 30°, 90°) and settles (0.5s)
        2. G19 opens smoothly to 180° to release waste (1.2s)
        3. G19 closes smoothly back to 0° (0.5s)
        Captures telemetry from real hardware or simulates progress in software mode.
        """
        wait_time = delay if delay is not None else SORTING_DELAY
        print(
            f"[ESP32 Hardware] Sequence execution (base delay: {wait_time}s): "
            f"G18 move -> settle ({G18_SETTLE_DELAY}s) -> "
            f"G19 open ({G19_OPEN_TIME}s) -> close ({G19_CLOSE_DELAY}s)...",
            flush=True
        )

        start_time = time.time()

        if self.is_connected:
            # Read real ESP32 telemetry from serial buffer
            max_wait_time = max(wait_time + 5.0, 10.0)
            while (time.time() - start_time) < max_wait_time:
                if hasattr(self.serial, "in_waiting") and self.serial.in_waiting > 0:
                    try:
                        line = self.serial.readline().decode("utf-8", errors="ignore").strip()
                        if line:
                            self.last_telemetry.append(line)
                            print(f"[ESP32 Telemetry] {line}", flush=True)
                            if "SORTED" in line:
                                break
                    except Exception:
                        pass
                time.sleep(0.05)

            # Ensure minimum transit duration has elapsed
            elapsed = time.time() - start_time
            if elapsed < wait_time:
                time.sleep(wait_time - elapsed)
        else:
            # Software-only simulated sequence telemetry
            if self.last_sequence_plan:
                plan = self.last_sequence_plan
                g18_move = next(s for s in plan if s.get("servo") == "G18" and s.get("action") == "MOVE")
                cmd = "PLASTIC" if g18_move["target"] == "DRY/PLASTIC" else g18_move["target"]
                self.last_telemetry = [
                    f"RECEIVED: {cmd}",
                    f"G18_DESTINATION: {g18_move['target']} (angle: {g18_move['angle']})",
                    "G18_MOVING",
                    "G18_SETTLED",
                    f"G19_OPEN (angle: {G19_RELEASE_OPEN})",
                    f"G19_CLOSE (angle: {G19_RELEASE_CLOSED})",
                    "SORTED"
                ]
            time.sleep(wait_time)

        print(f"[ESP32 Hardware] Sorting sequence completed ({wait_time}s).", flush=True)
        return True

    def wait_for_ir_confirmation(self, timeout=None):
        """
        Deprecated: Retained as alias for wait_for_sorting_delay for backward compatibility.
        """
        return self.wait_for_sorting_delay(SORTING_DELAY)

    def close(self):
        """Closes the serial connection safely."""
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
                print("[ESP32] Connection closed", flush=True)
            except Exception:
                pass
        self.serial = None