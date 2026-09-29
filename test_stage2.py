"""
Automated test suite for Stage 2: Virtual Sorting UI and Flask Server.
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))

from app import app


def test_stage2_flask_endpoints():
    print("========================================")
    print("Testing EcoNova Stage 2 (Virtual Sorting UI)")
    print("========================================")

    client = app.test_client()

    print("[TEST 1] Testing GET / (Main HTML page)...")
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    html = res.get_data(as_text=True)
    assert "ECOnova" in html, "Page should contain ECOnova"
    assert "Virtual Segregation Stage" in html, "Page should contain Virtual Segregation Stage"
    assert "bin-organic" in html and "bin-plastic" in html and "bin-metal" in html, "Page should contain the 3 virtual bins"
    print("  -> Passed GET / test.")

    print("\n[TEST 2] Testing static assets...")
    css_res = client.get("/static/style.css")
    assert css_res.status_code == 200, "style.css should load"
    assert "bin-container" in css_res.get_data(as_text=True)
    print("  -> Passed style.css test.")

    js_res = client.get("/static/script.js")
    assert js_res.status_code == 200, "script.js should load"
    assert "triggerVirtualSort" in js_res.get_data(as_text=True)
    print("  -> Passed script.js test.")

    print("\n[TEST 3] Testing GET /api/detector/status...")
    status_res = client.get("/api/detector/status")
    assert status_res.status_code == 200
    status_data = status_res.get_json()
    print("  Detector status response:", status_data)
    assert "classes" in status_data
    assert status_data["points_map"] == {"Organic": 3, "Plastic": 5, "Metal": 7}
    print("  -> Passed /api/detector/status test.")

    print("\n[TEST 4] Testing POST /api/demo_override...")
    override_res = client.post("/api/demo_override", json={"category": "Organic", "confidence": 0.92})
    assert override_res.status_code == 200
    print("  -> Passed /api/demo_override test.")

    print("\n[TEST 5] Testing POST /api/detect...")
    detect_res = client.post("/api/detect", json={})
    assert detect_res.status_code == 200
    detect_data = detect_res.get_json()
    print("  Detection API response:", detect_data)
    assert detect_data["detected"] is True
    assert detect_data["category"] == "Organic"
    assert detect_data["points"] == 3
    assert detect_data["is_confident"] is True
    print("  -> Passed /api/detect test.")

    print("\n[TEST 6] Testing low confidence state...")
    client.post("/api/demo_override", json={"category": "LowConf", "confidence": 0.58})
    low_res = client.post("/api/detect", json={})
    low_data = low_res.get_json()
    print("  Low conf response:", low_data)
    assert low_data["is_confident"] is False
    assert "Low confidence" in low_data["message"]
    print("  -> Passed low confidence check.")

    print("\nALL STAGE 2 TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_stage2_flask_endpoints()
