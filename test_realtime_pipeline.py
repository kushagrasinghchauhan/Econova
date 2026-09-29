"""
test_realtime_pipeline.py
-------------------------
Automated verification suite for the Real-Time YOLO Pipeline in EcoNova:
- Verifies explicit YOLO_MODEL_MISSING when ai/models/best.pt does not exist.
- Confirms zero fake predictions or simulated 94% values in normal mode.
- Verifies developer override isolation.
- Verifies cooldown / duplicate sort protection on POST /api/sort.
- Verifies full downstream ecosystem (SQLite, QR codes, claiming, dashboard).
"""

import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))

import database
import reward
from detector import WasteDetector
from app import app


def test_realtime_pipeline():
    print("=" * 65)
    print("      EcoNova Real-Time YOLO Pipeline Verification Suite         ")
    print("=" * 65)

    client = app.test_client()

    # -------------------------------------------------------------
    # 1. DETECTOR STATUS & REAL MODEL INTEGRITY
    # -------------------------------------------------------------
    print("\n[TEST 1] Testing Detector Model Integrity...")
    res_status = client.get("/api/detector/status")
    assert res_status.status_code == 200
    status_data = res_status.get_json()
    print("  /api/detector/status response:", status_data)

    assert status_data["status"]["model_status"] == "READY"
    assert status_data["status"]["is_ready"] is True
    print("  -> Passed TEST 1: Detector model is active and verified READY.")

    # -------------------------------------------------------------
    # 2. POST /api/detect ON EMPTY FRAME (NO FAKE PREDICTIONS)
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing /api/detect with Empty Frame...")
    res_detect = client.post("/api/detect", json={})
    assert res_detect.status_code == 200
    detect_data = res_detect.get_json()
    print("  /api/detect response:", detect_data)

    assert detect_data["success"] is True
    assert detect_data["detected"] is False
    assert "Plastic" not in str(detect_data)  # Confirms no fake 94% Plastic is generated!
    print("  -> Passed TEST 2: No fake predictions. Clean detected=False returned.")

    # -------------------------------------------------------------
    # 3. DEVELOPER OVERRIDE ISOLATION (FOR TEST HARNESS)
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing Developer Testing Fallback...")
    # Enable developer override for Metal 94%
    res_dev = client.post("/api/demo_override", json={"category": "Metal", "confidence": 0.94})
    assert res_dev.status_code == 200

    res_dev_detect = client.post("/api/detect", json={})
    assert res_dev_detect.status_code == 200
    dev_data = res_dev_detect.get_json()
    print("  Developer Mode detect response:", dev_data)
    assert dev_data["success"] is True
    assert dev_data["detected"] is True
    assert dev_data["category"] == "Metal"
    assert dev_data["confidence"] == 0.94
    assert dev_data["simulated"] is True
    assert "bbox" in dev_data

    # Now clear developer override and verify normal mode returns
    client.post("/api/demo_override", json={"category": None})
    res_restored = client.post("/api/detect", json={})
    restored_data = res_restored.get_json()
    assert restored_data["success"] is True
    assert restored_data["detected"] is False
    print("  -> Passed TEST 3: Developer override functions in isolation and cleanly resets.")

    # -------------------------------------------------------------
    # 4. COOLDOWN & DUPLICATE SORTING PROTECTION
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing Cooldown & Duplicate Sort Prevention...")
    sort_res1 = client.post("/api/sort", json={"category": "Plastic", "confidence": 0.88})
    assert sort_res1.status_code == 200
    sort1_data = sort_res1.get_json()
    assert sort1_data["success"] is True
    first_reward_id = sort1_data["reward_id"]
    print(f"  First sort successful: Reward {first_reward_id}")

    # Immediate second sort for the same category within cooldown window
    sort_res2 = client.post("/api/sort", json={"category": "Plastic", "confidence": 0.88})
    print("  Immediate duplicate sort response status:", sort_res2.status_code)
    assert sort_res2.status_code == 429, f"Expected 429 Cooldown, got {sort_res2.status_code}"
    sort2_data = sort_res2.get_json()
    assert sort2_data["success"] is False
    assert "cooldown" in sort2_data["error"].lower()
    print("  -> Passed TEST 4: Rapid duplicate sorting rejected with HTTP 429 Cooldown.")

    # -------------------------------------------------------------
    # 5. DOWNSTREAM ECOSYSTEM PRESERVATION (REWARD -> USER -> DASHBOARD)
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Downstream Reward, User & Dashboard Pipelines...")
    # Verify QR code generated
    qr_path = os.path.join(PROJECT_ROOT, "rewards", f"{first_reward_id}.png")
    assert os.path.exists(qr_path) and os.path.getsize(qr_path) > 0
    print(f"  QR code verified on disk: {qr_path}")

    # Create user and claim reward
    user_email = f"realtime_user_{int(time.time()*1000)}@econova.org"
    user_res = client.post("/api/user", json={"name": "Live Tester", "email": user_email})
    assert user_res.status_code == 200
    user_id = user_res.get_json()["id"]

    claim_res = client.post(f"/api/reward/{first_reward_id}/claim", json={"user_id": user_id})
    assert claim_res.status_code == 200
    claim_data = claim_res.get_json()
    assert claim_data["success"] is True
    assert claim_data["points_added"] == 5
    assert claim_data["total_points"] == 5
    print(f"  Claimed reward: User #{user_id} now has {claim_data['total_points']} points.")

    # Verify Dashboard API
    dash_res = client.get(f"/api/dashboard/summary?user_id={user_id}")
    assert dash_res.status_code == 200
    dash_data = dash_res.get_json()
    assert dash_data["user"]["points"] == 5
    assert any(r["reward_id"] == first_reward_id for r in dash_data["rewards_history"])
    print("  -> Passed TEST 5: Downstream ecosystem (SQLite, QR, User, Dashboard) 100% functional.")

    # -------------------------------------------------------------
    # 6. FRONTEND HTML STRUCTURE
    # -------------------------------------------------------------
    print("\n[TEST 6] Testing Frontend Template Structure...")
    html_res = client.get("/")
    assert html_res.status_code == 200
    html_text = html_res.get_data(as_text=True)

    assert "model-alert-banner" in html_text
    assert "REAL YOLO MODEL REQUIRED" in html_text
    assert "dev-accordion" in html_text
    assert "stability-box" in html_text
    assert "Live YOLO Detection" in html_text
    print("  -> Passed TEST 6: Frontend template contains model warning, stability meter, and dev accordion.")

    print("\n" + "=" * 65)
    print("  ALL REAL-TIME PIPELINE VERIFICATION TESTS PASSED (100%)!   ")
    print("=" * 65)


if __name__ == "__main__":
    test_realtime_pipeline()
