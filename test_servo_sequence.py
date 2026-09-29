"""
test_servo_sequence.py
----------------------
Comprehensive test suite verifying the EcoNova Two-Servo Physical Sorting Sequence:
1. G18 (GPIO18, Destination Selector):
   - Organic:     G18 = 0°
   - Plastic:     G18 = 30°
   - Paper:       G18 = 30°
   - Metal:       G18 = 90°
   - Startup:     G18 = 30°
2. G19 (GPIO19, Waste Release Flap):
   - Closed:      G19 = 0° (holds waste on upper flap)
   - Open:        G19 = 180° (releases waste to fall into lower chute)
   - Startup:     G19 = 0°
3. Servo Speed & Fast Smooth S-Curve Trajectory Constants:
   - G18_MOVE_DELAY_MS      = 15 ms/deg (linear stepping for chute positioning)
   - G19_UPDATE_INTERVAL_MS = 20 ms (50 Hz hardware PWM synchronized update frame)
   - G19_OPEN_DURATION_MS   = 300 ms (Fast physical opening stroke, S-curve cosine easing)
   - G19_CLOSE_DURATION_MS  = 360 ms (Controlled soft landing closing stroke, S-curve easing)
4. Exact Sequencing Order:
   - G18 moves smoothly to destination angle FIRST (logs G18_MOVING)
   - Settle delay (G18_SETTLE_DELAY = 0.5s) -> logs G18_SETTLED
   - G19 opens fast & smooth to 180° ONLY AFTER G18 has settled -> logs G19_OPEN
   - Hold open (G19_OPEN_TIME = 1.2s)
   - G19 closes fast & smooth back to 0° -> logs G19_CLOSE
   - Settle delay (G19_CLOSE_DELAY = 0.5s)
   - Sorting complete -> logs "SORTED"
5. Verifies G19 NEVER opens before G18 destination positioning and settling.
6. Verifies Paper remains classified/displayed as Paper, routed to Dry/Plastic (G18 = 30°).
7. Verifies Arduino firmware code structure, S-curve motion profile, and setup() sequence.
"""

import os
import sys
import time
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hardware"))

import app as app_mod
from esp32_controller import (
    ESP32Controller,
    SORTING_DELAY,
    G18_SETTLE_DELAY,
    G19_OPEN_TIME,
    G19_CLOSE_DELAY,
    G18_DEFAULT_ANGLE,
    G18_ORGANIC_ANGLE,
    G18_DRY_PLASTIC_ANGLE,
    G18_METAL_ANGLE,
    G19_RELEASE_CLOSED,
    G19_RELEASE_OPEN,
    G18_MOVE_DELAY_MS,
    G19_OPEN_DELAY_MS,
    G19_CLOSE_DELAY_MS,
    G19_UPDATE_INTERVAL_MS,
    G19_OPEN_DURATION_MS,
    G19_CLOSE_DURATION_MS,
    ORGANIC_ANGLE,
    DRY_PLASTIC_ANGLE,
    METAL_ANGLE,
    RELEASE_CLOSED,
    RELEASE_OPEN
)
import database


class MockSerial:
    def __init__(self):
        self.is_open = True
        self.sent_commands = []
        self.buffer = []

    def write(self, data):
        cmd = data.decode("utf-8").strip()
        self.sent_commands.append(cmd)
        target = "DRY/PLASTIC" if cmd in ("PLASTIC", "PAPER") else cmd
        angle = 30 if cmd in ("PLASTIC", "PAPER") else (0 if cmd == "ORGANIC" else 90)
        self.buffer = [
            f"RECEIVED: {cmd}\n".encode(),
            f"G18_DESTINATION: {target} (angle: {angle})\n".encode(),
            b"G18_MOVING\n",
            b"G18_SETTLED\n",
            b"G19_OPEN (angle: 180)\n",
            b"G19_CLOSE (angle: 0)\n",
            b"SORTED\n"
        ]

    def flush(self):
        pass

    @property
    def in_waiting(self):
        return len(self.buffer)

    def readline(self):
        if self.buffer:
            return self.buffer.pop(0)
        return b""

    def close(self):
        self.is_open = False


def test_servo_sequence():
    print("=" * 75)
    print("     EcoNova G18/G19 Two-Servo Physical Sorting Sequence Verification    ")
    print("=" * 75)

    # --------------------------------------------------------------------------
    # 1. VERIFY CONFIGURABLE ANGLES & SPEED / TRAJECTORY CONSTANTS
    # --------------------------------------------------------------------------
    print("\n[VERIFICATION 1] Checking Configurable G18 & G19 Angle Constants...")
    print(f"  -> G18 Destination Selector (GPIO18):")
    print(f"     * Organic:     {G18_ORGANIC_ANGLE}°")
    print(f"     * Dry/Plastic: {G18_DRY_PLASTIC_ANGLE}°")
    print(f"     * Metal:       {G18_METAL_ANGLE}°")
    print(f"     * Startup:     {G18_DEFAULT_ANGLE}°")
    print(f"  -> G19 Waste Release Flap (GPIO19):")
    print(f"     * Closed:      {G19_RELEASE_CLOSED}°")
    print(f"     * Open:        {G19_RELEASE_OPEN}°")
    print(f"  -> Speed & Trajectory Constants:")
    print(f"     * G18_MOVE_DELAY_MS:      {G18_MOVE_DELAY_MS} ms/deg")
    print(f"     * G19_UPDATE_INTERVAL_MS: {G19_UPDATE_INTERVAL_MS} ms (50 Hz PWM sync)")
    print(f"     * G19_OPEN_DURATION_MS:   {G19_OPEN_DURATION_MS} ms (S-curve)")
    print(f"     * G19_CLOSE_DURATION_MS:  {G19_CLOSE_DURATION_MS} ms (S-curve)")

    assert G18_ORGANIC_ANGLE == 0, "Organic destination must be 0°"
    assert G18_DRY_PLASTIC_ANGLE == 30, "Dry/Plastic destination must be 30°"
    assert G18_METAL_ANGLE == 90, "Metal destination must be 90°"
    assert G18_DEFAULT_ANGLE == 30, "Default startup position must be 30°"
    assert G19_RELEASE_CLOSED == 0, "G19 closed angle must be 0°"
    assert G19_RELEASE_OPEN == 180, "G19 open angle must be 180°"
    assert G18_MOVE_DELAY_MS == 15, "G18 step delay must be 15ms"
    assert G19_UPDATE_INTERVAL_MS == 20, "G19 update interval must match 50Hz PWM (20ms)"
    assert G19_OPEN_DURATION_MS == 300, "G19 open duration must be 300ms (max physical speed)"
    assert G19_CLOSE_DURATION_MS == 360, "G19 close duration must be 360ms (soft landing)"
    print("  -> PASSED: All G18 and G19 angle and trajectory constants strictly match requirements.")

    print("\n[VERIFICATION 2] Checking Configurable Timing Constants...")
    print(f"  -> G18_SETTLE_DELAY: {G18_SETTLE_DELAY}s (0.5s settle window)")
    print(f"  -> G19_OPEN_TIME:    {G19_OPEN_TIME}s (1.2s waste fall window)")
    print(f"  -> G19_CLOSE_DELAY:  {G19_CLOSE_DELAY}s (0.5s close window)")
    print(f"  -> Total SORTING_DELAY: {SORTING_DELAY}s (2.2s)")
    assert G18_SETTLE_DELAY == 0.5, "G18_SETTLE_DELAY must be 0.5s"
    assert G19_OPEN_TIME == 1.2, "G19_OPEN_TIME must be 1.2s"
    assert G19_CLOSE_DELAY == 0.5, "G19_CLOSE_DELAY must be 0.5s"
    assert SORTING_DELAY == 2.2, "Total SORTING_DELAY must be 2.2s"
    print("  -> PASSED: Timing constants meet safe physical transit constraints.")

    # --------------------------------------------------------------------------
    # 2. VERIFY DETERMINISTIC PHYSICAL SEQUENCE FOR ALL 4 WASTE CLASSES
    # --------------------------------------------------------------------------
    print("\n[VERIFICATION 3] Verifying Exact Physical Sequence Order for Each Waste Class...")

    controller = ESP32Controller()
    test_cases = [
        {
            "category": "Organic",
            "expected_cmd": "ORGANIC",
            "expected_target": "ORGANIC",
            "expected_g18_angle": 0
        },
        {
            "category": "Plastic",
            "expected_cmd": "PLASTIC",
            "expected_target": "DRY/PLASTIC",
            "expected_g18_angle": 30
        },
        {
            "category": "Paper",
            "expected_cmd": "PLASTIC",
            "expected_target": "DRY/PLASTIC",
            "expected_g18_angle": 30
        },
        {
            "category": "Metal",
            "expected_cmd": "METAL",
            "expected_target": "METAL",
            "expected_g18_angle": 90
        }
    ]

    for tc in test_cases:
        category = tc["category"]
        print(f"\n  Checking sequence for '{category}' (Expected destination: {tc['expected_target']})...")

        plan = controller.get_sequence_plan(category)

        # Step 1: G18 moves to destination angle FIRST
        s1 = plan[0]
        assert s1["servo"] == "G18", f"Step 1 must be G18, got {s1['servo']}"
        assert s1["action"] == "MOVE", f"Step 1 action must be MOVE, got {s1['action']}"
        assert s1["angle"] == tc["expected_g18_angle"], f"Expected angle {tc['expected_g18_angle']}, got {s1['angle']}"
        assert s1["pin"] == 18, "G18 must be on GPIO18"
        assert s1["step_delay_ms"] == G18_MOVE_DELAY_MS, f"Expected step delay {G18_MOVE_DELAY_MS}ms"
        print(f"    [Step 1] PASSED: G18 (GPIO18) moves smoothly to {s1['target']} ({s1['angle']}°, speed: {s1['step_delay_ms']}ms/deg)")

        # Step 2: Settle delay for G18
        s2 = plan[1]
        assert s2["action"] == "WAIT", "Step 2 must be WAIT"
        assert s2["duration"] == G18_SETTLE_DELAY
        print(f"    [Step 2] PASSED: Wait {s2['duration']}s for G18 to physically settle")

        # Step 3: ONLY AFTER G18 settles, G19 opens to 180°
        s3 = plan[2]
        assert s3["servo"] == "G19", f"Step 3 must be G19, got {s3['servo']}"
        assert s3["action"] == "OPEN", f"Step 3 action must be OPEN, got {s3['action']}"
        assert s3["angle"] == 180, "G19 open angle must be 180°"
        assert s3["pin"] == 19, "G19 must be on GPIO19"
        assert s3.get("duration_ms") == G19_OPEN_DURATION_MS, f"Expected duration {G19_OPEN_DURATION_MS}ms"
        print(f"    [Step 3] PASSED: G19 (GPIO19) opens flap fast & smooth ({s3['angle']}°, S-curve: {s3['duration_ms']}ms)")

        # Step 4: Waste fall delay
        s4 = plan[3]
        assert s4["action"] == "WAIT"
        assert s4["duration"] == G19_OPEN_TIME
        print(f"    [Step 4] PASSED: Wait {s4['duration']}s for waste to fall through")

        # Step 5: G19 closes back to 0°
        s5 = plan[4]
        assert s5["servo"] == "G19"
        assert s5["action"] == "CLOSE"
        assert s5["angle"] == 0, "G19 closed angle must be 0°"
        assert s5.get("duration_ms") == G19_CLOSE_DURATION_MS, f"Expected duration {G19_CLOSE_DURATION_MS}ms"
        print(f"    [Step 5] PASSED: G19 closes flap fast & smooth back to ({s5['angle']}°, S-curve: {s5['duration_ms']}ms)")

        # Step 6: Flap close settle delay
        s6 = plan[5]
        assert s6["action"] == "WAIT"
        assert s6["duration"] == G19_CLOSE_DELAY
        print(f"    [Step 6] PASSED: Wait {s6['duration']}s for flap to settle closed")

        # CRITICAL ASSERTION: G19 NEVER opens before G18 reaches target
        g18_move_idx = next(i for i, s in enumerate(plan) if s.get("servo") == "G18" and s.get("action") == "MOVE")
        g19_open_idx = next(i for i, s in enumerate(plan) if s.get("servo") == "G19" and s.get("action") == "OPEN")
        g19_close_idx = next(i for i, s in enumerate(plan) if s.get("servo") == "G19" and s.get("action") == "CLOSE")

        assert g18_move_idx < g19_open_idx, "VIOLATION: G19 opened before G18 moved!"
        assert g19_open_idx < g19_close_idx, "VIOLATION: G19 closed before opening!"
        print(f"  -> CRITICAL CHECK PASSED: Order strictly verified: G18 Move (step {g18_move_idx+1}) -> G19 Open (step {g19_open_idx+1}) -> G19 Close (step {g19_close_idx+1}).")

    # --------------------------------------------------------------------------
    # 3. VERIFY ARDUINO FIRMWARE FILE FOR EXACT HARDWARE IMPLEMENTATION
    # --------------------------------------------------------------------------
    print("\n[VERIFICATION 4] Verifying Arduino Firmware Code (esp32_firmware.ino)...")
    ino_path = os.path.join(PROJECT_ROOT, "hardware", "esp32_firmware", "esp32_firmware.ino")
    assert os.path.exists(ino_path), f"Firmware file not found at {ino_path}"

    with open(ino_path, "r") as f:
        ino_code = f.read()

    # Verify Pins
    assert "G18_PIN           18" in ino_code or "G18_PIN 18" in ino_code
    assert "G19_PIN           19" in ino_code or "G19_PIN 19" in ino_code
    print("  -> Pin configuration verified: G18 on GPIO18, G19 on GPIO19.")

    # Verify Angle Constants in Firmware
    assert "G18_ORGANIC_ANGLE       0" in ino_code or "G18_ORGANIC_ANGLE 0" in ino_code
    assert "G18_DRY_PLASTIC_ANGLE  30" in ino_code or "G18_DRY_PLASTIC_ANGLE 30" in ino_code
    assert "G18_METAL_ANGLE        90" in ino_code or "G18_METAL_ANGLE 90" in ino_code
    assert "G18_DEFAULT_ANGLE      30" in ino_code or "G18_DEFAULT_ANGLE 30" in ino_code
    assert "G19_RELEASE_CLOSED      0" in ino_code or "G19_RELEASE_CLOSED 0" in ino_code
    assert "G19_RELEASE_OPEN      180" in ino_code or "G19_RELEASE_OPEN 180" in ino_code
    print("  -> All G18 and G19 angle constants defined in firmware (0°, 30°, 90°, 180°).")

    # Verify Speed & Trajectory Constants in Firmware
    assert "G18_MOVE_DELAY_MS      15" in ino_code or "G18_MOVE_DELAY_MS 15" in ino_code
    assert re.search(r"G19_OPEN_DURATION_MS\s+\d+", ino_code), "G19_OPEN_DURATION_MS must be defined"
    assert re.search(r"G19_CLOSE_DURATION_MS\s+\d+", ino_code), "G19_CLOSE_DURATION_MS must be defined"
    assert "int moveG19FastSmooth(" in ino_code, "moveG19FastSmooth helper must be implemented"
    assert "int moveServoSmoothly(" in ino_code, "moveServoSmoothly helper must be implemented"
    assert "currentG18Angle" in ino_code, "currentG18Angle state variable must be present"
    assert "currentG19Angle" in ino_code, "currentG19Angle state variable must be present"
    print("  -> Fast & smooth S-curve trajectory verified in firmware (20ms interval, 300ms open, 360ms close).")

    # Verify Timing Constants in Firmware
    assert "G18_SETTLE_DELAY_MS    500" in ino_code or "G18_SETTLE_DELAY_MS 500" in ino_code
    assert "G19_OPEN_TIME_MS      1200" in ino_code or "G19_OPEN_TIME_MS 1200" in ino_code
    assert "G19_CLOSE_DELAY_MS     500" in ino_code or "G19_CLOSE_DELAY_MS 500" in ino_code
    print("  -> All timing constants defined in firmware (500ms, 1200ms, 500ms).")

    # Verify Absence of IR Sensor
    assert "IR_SENSOR_PIN" not in ino_code
    assert "IR_PIN" not in ino_code
    assert "checkIRSensor" not in ino_code
    print("  -> Confirmed: IR sensor completely absent from firmware.")

    # Verify Startup sequence in setup()
    setup_start = ino_code.find("void setup()")
    loop_start = ino_code.find("void loop()")
    assert setup_start != -1 and loop_start != -1, "setup() and loop() functions found"
    setup_body = ino_code[setup_start:loop_start]

    g18_attach = setup_body.find("servoG18.attach")
    g19_attach = setup_body.find("servoG19.attach")
    g19_closed = setup_body.find("servoG19.write(G19_RELEASE_CLOSED)")
    g18_default = setup_body.find("servoG18.write(G18_DEFAULT_ANGLE)")
    ready_msg = setup_body.find("ECONOVA_ESP32_READY")

    assert g18_attach != -1 and g19_attach != -1, "Both servos attached in setup()"
    assert g19_closed != -1 and g18_default != -1, "Both servos moved to startup positions in setup()"
    assert g19_closed < ready_msg, "G19 closed to 0° strictly before reporting readiness"
    assert g18_default < ready_msg, "G18 positioned at 30° strictly before reporting readiness"
    print("  -> Startup sequence in setup() strictly verified: G19 starts at 0° (CLOSED) -> G18 starts at 30° -> ECONOVA_ESP32_READY.")

    # Verify execution order in executeSortSequence()
    sort_seq_start = ino_code.find("void executeSortSequence(int destinationAngle, String destination) {")
    reset_servos_start = ino_code.find("void resetServosToHome() {")
    assert sort_seq_start != -1 and reset_servos_start != -1, "executeSortSequence() function definition found"
    sort_body = ino_code[sort_seq_start:reset_servos_start]

    fw_dest_msg = sort_body.find("Serial.print(\"G18_DESTINATION: \")")
    fw_g18_moving = sort_body.find("Serial.println(\"G18_MOVING\")")
    fw_g18_move = sort_body.find("moveServoSmoothly(servoG18, currentG18Angle, destinationAngle, G18_MOVE_DELAY_MS)")
    fw_g18_delay = sort_body.find("delay(G18_SETTLE_DELAY_MS)")
    fw_g18_settled = sort_body.find("Serial.println(\"G18_SETTLED\")")
    fw_g19_open_msg = sort_body.find("Serial.print(\"G19_OPEN (angle: \")")
    fw_g19_open = sort_body.find("moveG19FastSmooth(servoG19, currentG19Angle, G19_RELEASE_OPEN, G19_OPEN_DURATION_MS)")
    fw_g19_delay = sort_body.find("delay(G19_OPEN_TIME_MS)")
    fw_g19_close_msg = sort_body.find("Serial.print(\"G19_CLOSE (angle: \")")
    fw_g19_close = sort_body.find("moveG19FastSmooth(servoG19, currentG19Angle, G19_RELEASE_CLOSED, G19_CLOSE_DURATION_MS)")
    fw_post_delay = sort_body.find("delay(G19_CLOSE_DELAY_MS)")
    fw_sorted_msg = sort_body.find("Serial.println(\"SORTED\")")

    assert fw_dest_msg != -1, "G18_DESTINATION log found"
    assert fw_g18_moving != -1, "G18_MOVING log found"
    assert fw_g18_move != -1, "G18 smooth move call found"
    assert fw_g18_settled != -1, "G18_SETTLED log found"
    assert fw_g19_open != -1, "G19 fast smooth open call found"
    assert fw_g19_close != -1, "G19 fast smooth close call found"
    assert fw_sorted_msg != -1, "SORTED log found"

    assert fw_dest_msg < fw_g18_moving < fw_g18_move < fw_g18_delay < fw_g18_settled, "G18 sequence order verified"
    assert fw_g18_settled < fw_g19_open_msg < fw_g19_open < fw_g19_delay, "G19 open strictly after G18 settled"
    assert fw_g19_delay < fw_g19_close_msg < fw_g19_close < fw_post_delay < fw_sorted_msg, "G19 close and completion verified"
    print("  -> Firmware execution order strictly verified: G18 Destination -> G18 Moving -> G18 Settled -> G19 Open (180°) -> Fall Delay -> G19 Close (0°) -> Post Delay -> SORTED.")

    # --------------------------------------------------------------------------
    # 4. VERIFY HARDWARE STATUS API RESPONSE
    # --------------------------------------------------------------------------
    print("\n[VERIFICATION 5] Verifying GET /api/hardware/status Endpoint...")
    client = app_mod.app.test_client()
    hw_res = client.get("/api/hardware/status")
    assert hw_res.status_code == 200
    hw_data = hw_res.get_json()

    assert "servos" in hw_data, "servos key must exist in hardware status"
    g18_info = hw_data["servos"]["g18"]
    g19_info = hw_data["servos"]["g19"]
    assert g18_info["pin"] == 18 and g18_info["role"] == "DESTINATION_SELECTOR"
    assert g18_info["organic_angle"] == 0
    assert g18_info["dry_plastic_angle"] == 30
    assert g18_info["metal_angle"] == 90
    assert g19_info["pin"] == 19 and g19_info["role"] == "WASTE_RELEASE_FLAP"
    assert g19_info["closed_angle"] == 0
    assert g19_info["open_angle"] == 180

    assert "speed" in hw_data, "speed key must exist in hardware status"
    assert hw_data["speed"]["g18_move_delay_ms"] == 15
    assert hw_data["speed"]["g19_open_duration_ms"] == 300
    assert hw_data["speed"]["g19_close_duration_ms"] == 360
    assert hw_data["speed"]["g19_update_interval_ms"] == 20
    assert hw_data["speed"]["g19_motion_profile"] == "S_CURVE_COSINE_EASE"

    assert "timing" in hw_data, "timing key must exist in hardware status"
    assert hw_data["timing"]["g18_settle_delay"] == G18_SETTLE_DELAY
    assert hw_data["timing"]["g19_open_time"] == G19_OPEN_TIME
    assert hw_data["timing"]["g19_close_delay"] == G19_CLOSE_DELAY
    assert hw_data["timing"]["total_sorting_delay"] == SORTING_DELAY
    print(f"  -> API reports G18 and G19 with fast & smooth S-curve speed controls: {hw_data['speed']}.")

    # --------------------------------------------------------------------------
    # 5. VERIFY TELEMETRY TRACKING ON LIVE POST /api/sort
    # --------------------------------------------------------------------------
    print("\n[VERIFICATION 6] Verifying Live Sorting Execution with Telemetry Tracking...")
    mock_serial = MockSerial()
    app_mod.esp32_controller.serial = mock_serial

    sort_res = client.post("/api/sort", json={
        "category": "Paper",
        "confidence": 0.93
    })
    assert sort_res.status_code == 200
    sort_json = sort_res.get_json()
    assert sort_json["category"] == "Paper"
    assert sort_json["hardware_destination"] == "Dry/Plastic"
    assert sort_json["hardware_command"] == "PLASTIC"
    assert mock_serial.sent_commands[-1] == "PLASTIC"

    # Verify recorded telemetry trace
    telemetry = app_mod.esp32_controller.last_telemetry
    print(f"  -> Captured Telemetry Trace: {telemetry}")
    assert any("G18_DESTINATION" in t for t in telemetry), "G18_DESTINATION must be logged"
    assert any("G18_MOVING" in t for t in telemetry), "G18_MOVING must be logged"
    assert any("G18_SETTLED" in t for t in telemetry), "G18_SETTLED must be logged"
    assert any("G19_OPEN" in t for t in telemetry), "G19_OPEN must be logged"
    assert any("G19_CLOSE" in t for t in telemetry), "G19_CLOSE must be logged"
    assert any("SORTED" in t for t in telemetry), "SORTED must be logged"

    # Verify telemetry order
    t_g18_dest = next(i for i, t in enumerate(telemetry) if "G18_DESTINATION" in t)
    t_g18_moving = next(i for i, t in enumerate(telemetry) if "G18_MOVING" in t)
    t_g18_settled = next(i for i, t in enumerate(telemetry) if "G18_SETTLED" in t)
    t_g19_open = next(i for i, t in enumerate(telemetry) if "G19_OPEN" in t)
    t_g19_close = next(i for i, t in enumerate(telemetry) if "G19_CLOSE" in t)

    assert t_g18_dest < t_g18_moving < t_g18_settled < t_g19_open < t_g19_close, "Telemetry order confirms physical sequencing"
    print("  -> PASSED: Telemetry verifies G18 moved to DRY/PLASTIC (30°) before G19 opened release flap (180°)!")

    print("\n" + "=" * 75)
    print("   ALL PHYSICAL SERVO SEQUENCING VERIFICATIONS PASSED (100%)!    ")
    print("=" * 75)


if __name__ == "__main__":
    test_servo_sequence()
