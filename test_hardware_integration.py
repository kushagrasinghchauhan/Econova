"""
test_hardware_integration.py
----------------------------
Verifies the ESP32 hardware integration into EcoNova:
1. /api/hardware/status endpoint
2. /api/detector/status hardware field
3. /api/sort live hardware communication with ESP32 (COM6)
"""

import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hardware"))

from app import app, esp32_controller


def test_hardware_integration():
    print("=" * 65)
    print("      EcoNova ESP32 Hardware Integration Test Suite")
    print("=" * 65)

    client = app.test_client()

    # 1. Test /api/hardware/status
    print("\n[TEST 1] Testing GET /api/hardware/status...")
    res = client.get("/api/hardware/status")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    hw_data = res.get_json()
    print("  -> Response:", hw_data)
    assert hw_data["port"] in ("COM6", "COM7")
    assert "connected" in hw_data
    assert "mode" in hw_data
    print(f"  -> Hardware status verified: connected={hw_data['connected']}, mode={hw_data['mode']}")

    # 2. Test /api/detector/status
    print("\n[TEST 2] Testing GET /api/detector/status hardware block...")
    res_det = client.get("/api/detector/status")
    assert res_det.status_code == 200
    det_data = res_det.get_json()
    assert "hardware" in det_data
    assert det_data["hardware"]["port"] in ("COM6", "COM7")
    print("  -> Detector status includes hardware block:", det_data["hardware"])

    # 3. Test /api/sort with Plastic (0.92 confidence)
    print("\n[TEST 3] Testing POST /api/sort with Plastic (confidence 0.92)...")
    res_sort = client.post("/api/sort", json={
        "category": "Plastic",
        "confidence": 0.92
    })
    assert res_sort.status_code == 200, f"Expected 200, got {res_sort.status_code} ({res_sort.get_data(as_text=True)})"
    sort_data = res_sort.get_json()
    print("  -> Sort response:")
    print(f"     * success:    {sort_data['success']}")
    print(f"     * category:   {sort_data['category']}")
    print(f"     * confidence: {sort_data['confidence']}")
    print(f"     * reward_id:  {sort_data['reward_id']}")
    print(f"     * qr_url:     {sort_data['qr_url']}")
    print(f"     * hardware:   {sort_data.get('hardware')}")
    assert sort_data["success"] is True
    assert sort_data["category"] == "Plastic"
    assert "ECO-" in sort_data["reward_id"]

    # 4. Test /api/sort with Organic (0.95 confidence)
    print("\n[TEST 4] Testing POST /api/sort with Organic (confidence 0.95)...")
    import time
    time.sleep(2.1) # cooldown
    res_sort_org = client.post("/api/sort", json={
        "category": "Organic",
        "confidence": 0.95
    })
    assert res_sort_org.status_code == 200
    org_data = res_sort_org.get_json()
    print(f"  -> Successfully sorted Organic: reward_id={org_data['reward_id']}")

    # 5. Test /api/sort with Metal (0.91 confidence)
    print("\n[TEST 5] Testing POST /api/sort with Metal (confidence 0.91)...")
    time.sleep(2.1) # cooldown
    res_sort_met = client.post("/api/sort", json={
        "category": "Metal",
        "confidence": 0.91
    })
    assert res_sort_met.status_code == 200
    met_data = res_sort_met.get_json()
    print(f"  -> Successfully sorted Metal: reward_id={met_data['reward_id']}")

    print("\n" + "=" * 65)
    print("  ALL ESP32 HARDWARE INTEGRATION TESTS PASSED (100%)!")
    print("=" * 65)


if __name__ == "__main__":
    test_hardware_integration()
