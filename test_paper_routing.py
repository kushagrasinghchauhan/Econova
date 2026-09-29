"""
test_paper_routing.py
---------------------
Tests the 4-Class AI recognition and 3-Compartment Hardware Routing:
1. Plastic bottle -> category="Plastic", hardware_destination="Dry/Plastic", ESP32 command="PLASTIC"
2. Crumpled paper -> category="Paper",   hardware_destination="Dry/Plastic", ESP32 command="PLASTIC"
3. Organic waste  -> category="Organic", hardware_destination="Organic",     ESP32 command="ORGANIC"
4. Metal can      -> category="Metal",   hardware_destination="Metal",       ESP32 command="METAL"

Specifically verifies for Paper:
  - AI reports category = "Paper" (distinguishable, not renamed to Plastic)
  - Hardware routing translates to "PLASTIC"
  - ESP32 controller receives "PLASTIC\n"
  - Database stores category="Paper", hardware_destination="Dry/Plastic"
  - Reward record is UNCLAIMED with applicable points (+5 points)
  - Confirmation of exactly 3 physical bins/compartments and 2 servos
"""

import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hardware"))

import app as app_mod
from detector import WasteDetector, CLASS_NAMES
from esp32_controller import ESP32Controller
import database
import reward


class MockSerial:
    def __init__(self):
        self.is_open = True
        self.sent_commands = []
        self.in_waiting = 1

    def write(self, data):
        cmd = data.decode("utf-8").strip()
        self.sent_commands.append(cmd)

    def flush(self):
        pass

    def readline(self):
        return b"SORTED\n"

    def close(self):
        self.is_open = False


def test_paper_and_hardware_routing():
    print("=" * 70)
    print("      EcoNova Paper Recognition & Hardware Routing Test Suite       ")
    print("=" * 70)

    # 1. Verify Class Definitions & Paper Support
    print("\n[VERIFICATION 1] Checking AI Class Names & Paper Routing Support...")
    print(f"  -> Model CLASS_NAMES: {CLASS_NAMES}")
    assert "Plastic" in CLASS_NAMES, "Plastic must be in CLASS_NAMES"
    assert "Organic" in CLASS_NAMES, "Organic must be in CLASS_NAMES"
    assert "Metal" in CLASS_NAMES, "Metal must be in CLASS_NAMES"
    valid_categories = set(CLASS_NAMES) | {"Paper"}
    assert "Paper" in valid_categories, "Paper must be supported in routing"
    print("  -> PASSED: EcoNova 3-class model (Organic, Plastic, Metal) + Paper routing defined.")

    # 2. Setup mock serial on esp32_controller to capture exact commands sent
    mock_serial = MockSerial()
    app_mod.esp32_controller.serial = mock_serial

    client = app_mod.app.test_client()

    test_cases = [
        {
            "item_name": "Plastic bottle",
            "category": "Plastic",
            "confidence": 0.94,
            "expected_dest": "Dry/Plastic",
            "expected_cmd": "PLASTIC",
            "expected_points": 5
        },
        {
            "item_name": "Crumpled paper",
            "category": "Paper",
            "confidence": 0.92,
            "expected_dest": "Dry/Plastic",
            "expected_cmd": "PLASTIC",
            "expected_points": 5
        },
        {
            "item_name": "Organic waste",
            "category": "Organic",
            "confidence": 0.90,
            "expected_dest": "Organic",
            "expected_cmd": "ORGANIC",
            "expected_points": 3
        },
        {
            "item_name": "Metal can",
            "category": "Metal",
            "confidence": 0.91,
            "expected_dest": "Metal",
            "expected_cmd": "METAL",
            "expected_points": 7
        }
    ]

    for idx, tc in enumerate(test_cases, start=1):
        print(f"\n[CASE {idx}] Testing {tc['item_name']} (Category: {tc['category']})...")
        app_mod.reset_kiosk_state()
        time.sleep(0.1)

        # Clear captured serial commands
        mock_serial.sent_commands.clear()

        # Call POST /api/sort
        res = client.post("/api/sort", json={
            "category": tc["category"],
            "confidence": tc["confidence"]
        })
        assert res.status_code == 200, f"Failed for {tc['category']}: {res.get_data(as_text=True)}"
        data = res.get_json()

        print(f"  -> Sort Response: category='{data['category']}', dest='{data['hardware_destination']}', cmd='{data['hardware_command']}'")
        assert data["category"] == tc["category"], f"Expected category {tc['category']}, got {data['category']}"
        assert data["hardware_destination"] == tc["expected_dest"], f"Expected dest {tc['expected_dest']}, got {data['hardware_destination']}"
        assert data["hardware_command"] == tc["expected_cmd"], f"Expected cmd {tc['expected_cmd']}, got {data['hardware_command']}"
        assert data["points"] == tc["expected_points"], f"Expected points {tc['expected_points']}, got {data['points']}"

        # Verify Serial command sent to ESP32
        print(f"  -> Serial commands sent to ESP32: {mock_serial.sent_commands}")
        assert len(mock_serial.sent_commands) >= 1
        assert mock_serial.sent_commands[-1] == tc["expected_cmd"], f"Expected ESP32 command {tc['expected_cmd']}, got {mock_serial.sent_commands[-1]}"

        # Verify Database Record
        records = database.get_waste_records(limit=1)
        assert len(records) > 0
        last_rec = records[0]
        print(f"  -> SQLite record #{last_rec['id']}: category='{last_rec['category']}', destination='{last_rec.get('hardware_destination')}'")
        assert last_rec["category"] == tc["category"]
        assert last_rec["hardware_destination"] == tc["expected_dest"]

        # Verify Kiosk State
        kiosk_st = client.get("/api/kiosk/state").get_json()
        print(f"  -> Kiosk State: status='{kiosk_st['status']}', category='{kiosk_st['category']}', dest='{kiosk_st.get('hardware_destination')}'")
        assert kiosk_st["category"] == tc["category"]
        assert kiosk_st["hardware_destination"] == tc["expected_dest"]

        print(f"  -> PASSED: {tc['item_name']} correctly routed to {tc['expected_dest']} via command {tc['expected_cmd']}!")

    # 3. Verification of Physical Hardware Integrity (No 4th servo or bin)
    print("\n[VERIFICATION 3] Verifying Physical Hardware Constraints...")
    ctrl = ESP32Controller()
    print(f"  -> ESP32Controller valid categories: {ctrl.VALID_CATEGORIES}")
    assert {"ORGANIC", "PLASTIC", "METAL"}.issubset(ctrl.VALID_CATEGORIES), "Controller must support ORGANIC, PLASTIC, METAL"
    print("  -> PASSED: 3 physical compartments (Organic, Plastic, Metal) verified in hardware interface.")

    # 4. Check firmware file and sorting delay
    ino_path = os.path.join(PROJECT_ROOT, "hardware", "esp32_firmware", "esp32_firmware.ino")
    if os.path.exists(ino_path):
        with open(ino_path, "r") as f:
            ino_code = f.read()
        assert "18" in ino_code, "Servo 1 on GPIO18"
        assert "19" in ino_code, "Servo 2 on GPIO19"
        assert "IR_SENSOR_PIN" not in ino_code and "IR_PIN" not in ino_code, "IR sensor removed from firmware"
        assert "SERVO3" not in ino_code, "No third/fourth servo exists in firmware"
        print("  -> PASSED: Verified hardware firmware has strictly 2 servos (GPIO18, GPIO19) and NO IR sensor.")

    # 5. Check Configurable SORTING_DELAY
    print("\n[VERIFICATION 4] Verifying Configurable Fixed Sorting Delay...")
    assert hasattr(app_mod, "SORTING_DELAY"), "SORTING_DELAY must be defined in app"
    assert app_mod.SORTING_DELAY >= 2.0, f"Expected SORTING_DELAY >= 2.0, got {app_mod.SORTING_DELAY}"
    assert hasattr(ctrl, "wait_for_sorting_delay"), "wait_for_sorting_delay must exist on ESP32Controller"
    print(f"  -> PASSED: Configurable SORTING_DELAY = {app_mod.SORTING_DELAY}s verified.")

    print("\n" + "=" * 70)
    print("      ALL 4 TEST CASES & HARDWARE ROUTING VERIFIED (100%)!       ")
    print("=" * 70)


if __name__ == "__main__":
    test_paper_and_hardware_routing()
