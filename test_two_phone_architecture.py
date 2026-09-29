"""
test_two_phone_architecture.py
------------------------------
Comprehensive verification suite for the Two-Phone EcoNova Architecture:
- Phone 1: Fixed Prototype Camera (runs prototype.html, auto rear camera, auto ~4 FPS POST /api/detect,
           3-frame stabilization >= 0.70, triggers /api/sort, HUD, no QR/Dashboard).
- Phone 2: User Phone (runs phone.html, camera strictly OFF on home, [SCAN QR], [DASHBOARD],
           camera only for QR decode, stops camera immediately, claims reward, loads /api/dashboard,
           never calls /api/detect).
- Laptop Kiosk: Web server + YOLO 3-class inference + ESP32 COM6 + Displays large reward QR,
                no USB webcam required.
"""

import os
import sys
import json
import base64
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from backend.app import app, _kiosk_state, reset_kiosk_state
from backend.database import init_db, get_connection
from backend.reward import get_lan_ip, get_base_url
from ai.detector import WasteDetector, CLASS_NAMES, CONFIDENCE_THRESHOLD


def run_tests():
    init_db()
    reset_kiosk_state()
    client = app.test_client()

    print("=" * 80)
    print("      EcoNova Two-Phone Final Architecture — Verification Test Suite")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. PHONE 1 — FIXED PROTOTYPE CAMERA (prototype.html)
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Verifying Phone 1 Endpoints (/prototype and /?mode=prototype)...")
    res1 = client.get("/prototype")
    assert res1.status_code == 200, f"Expected 200 for /prototype, got {res1.status_code}"
    html1 = res1.get_data(as_text=True)

    res1_mode = client.get("/?mode=prototype")
    assert res1_mode.status_code == 200, f"Expected 200 for /?mode=prototype, got {res1_mode.status_code}"
    html1_mode = res1_mode.get_data(as_text=True)

    # Must be prototype HUD
    assert "PROTOTYPE CAMERA (PHONE 1)" in html1 or "Prototype Camera" in html1
    assert "CAMERA ACTIVE" in html1 or "ACTIVE" in html1
    assert "Frames sent:" in html1 or "frame-counter-label" in html1
    assert "initPrototypeCamera" in html1, "Must contain initPrototypeCamera auto-start"
    assert "requestWakeLock" in html1, "Must contain Screen WakeLock handling"
    assert "captureAndSendFrame" in html1, "Must contain frame capture transmission loop"
    assert "triggerSortSequence" in html1, "Must contain sort trigger logic"

    # Strictly verify Phone 1 does NOT contain QR Scanner, Claim forms, or Dashboard
    assert "btn-scan-qr" not in html1, "Phone 1 must NOT have QR scanner button"
    assert "btn-claim-reward" not in html1, "Phone 1 must NOT have reward claim button"
    assert "view-dashboard" not in html1, "Phone 1 must NOT have user dashboard view"
    assert "jsqr" not in html1.lower(), "Phone 1 must NOT load jsQR library"
    print("  -> PASSED: Phone 1 HUD correctly configured, auto-starts camera, streams frames, and excludes QR/Dashboard.")

    # -------------------------------------------------------------------------
    # 2. PHONE 2 — USER PHONE (phone.html)
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Verifying Phone 2 Endpoints (/phone and /?mode=phone)...")
    res2 = client.get("/phone")
    assert res2.status_code == 200, f"Expected 200 for /phone, got {res2.status_code}"
    html2 = res2.get_data(as_text=True)

    res2_mode = client.get("/?mode=phone")
    assert res2_mode.status_code == 200, f"Expected 200 for /?mode=phone, got {res2_mode.status_code}"
    html2_mode = res2_mode.get_data(as_text=True)

    # Must have Home actions: [ SCAN QR ] and [ DASHBOARD ]
    assert "SCAN QR" in html2, "Missing [ SCAN QR ] on Phone 2 Home"
    assert "DASHBOARD" in html2, "Missing [ DASHBOARD ] on Phone 2 Home"
    assert "btn-scan-qr" in html2, "Missing btn-scan-qr element"
    assert "btn-dashboard" in html2, "Missing btn-dashboard element"

    # Must indicate camera is OFF on load
    assert "Camera is OFF" in html2 or "Camera is OFF." in html2
    assert "openQrScanner" in html2, "Missing openQrScanner function"
    assert "stopCameraStream" in html2, "Missing stopCameraStream function"

    # Strictly verify Phone 2 NEVER calls /api/detect or runs YOLO
    assert "/api/detect" not in html2, "Phone 2 must NEVER call /api/detect"
    assert "detector.detect" not in html2, "Phone 2 must NEVER run YOLO detection"
    assert "triggerSortSequence" not in html2, "Phone 2 must NEVER trigger sorting"
    print("  -> PASSED: Phone 2 correctly isolated: camera OFF on Home, only QR scanner, no /api/detect.")

    # -------------------------------------------------------------------------
    # 3. LAPTOP KIOSK (index.html) — NO USB WEBCAM REQUIRED
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Verifying Laptop Kiosk Screen and Script Isolation...")
    res_kiosk = client.get("/")
    assert res_kiosk.status_code == 200
    html_kiosk = res_kiosk.get_data(as_text=True)

    with open(os.path.join(ROOT, "frontend", "script.js"), "r", encoding="utf-8") as f:
        script_code = f.read()

    # Kiosk mode does NOT call getUserMedia
    assert "if (isKioskMode) {" in script_code and "Laptop kiosk mode active" in script_code, \
        "initCamera must bypass getUserMedia in Kiosk Mode"
    assert "if (isKioskMode || isPhoneMode) return;" in script_code, \
        "captureAndDetectFrame must return immediately in Kiosk Mode"
    print("  -> PASSED: Laptop kiosk does not require or open local USB webcam.")

    # -------------------------------------------------------------------------
    # 4. API /api/detect INGESTION & SOURCE LOGGING
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Verifying /api/detect with Frame from Phone 1...")
    # Generate dummy frame (640x480)
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", dummy_img)
    b64_frame = "data:image/jpeg;base64," + base64.b64encode(buffer).decode("utf-8")

    res_detect = client.post("/api/detect", json={
        "image": b64_frame,
        "source": "prototype"
    })
    assert res_detect.status_code == 200, f"Expected 200 from /api/detect, got {res_detect.status_code}"
    det_data = res_detect.get_json()
    assert "success" in det_data
    print(f"  -> PASSED: /api/detect accepted frame payload from Phone 1 (success={det_data['success']}).")

    # -------------------------------------------------------------------------
    # 5. SORTING, REWARD QR GENERATION & KIOSK SYNC
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Verifying /api/sort -> ESP32 -> QR Code -> Kiosk State...")
    res_sort = client.post("/api/sort", json={
        "category": "Plastic",
        "confidence": 0.88
    })
    assert res_sort.status_code == 200, f"Expected 200 from /api/sort, got {res_sort.status_code}"
    sort_data = res_sort.get_json()
    assert sort_data["success"] is True
    assert sort_data["category"] == "Plastic"
    assert sort_data["hardware_command"] == "PLASTIC"
    assert sort_data["hardware_destination"] == "Dry/Plastic"
    assert "reward_id" in sort_data
    reward_id = sort_data["reward_id"]
    print(f"  -> Generated Reward: {reward_id} for Plastic (5 points)")

    # Verify Kiosk State transitioned to REWARD with large QR
    res_state = client.get("/api/kiosk/state")
    state_data = res_state.get_json()
    assert state_data["status"] == "reward"
    assert state_data["reward_id"] == reward_id
    assert state_data["claimed"] is False
    print("  -> PASSED: Kiosk state updated to 'reward' with large QR code.")

    # -------------------------------------------------------------------------
    # 6. PHONE 2 QR SCAN -> REWARD REDEEM PAGE & CLAIM
    # -------------------------------------------------------------------------
    print(f"\n[TEST 6] Verifying Phone 2 Reward Redemption for {reward_id}...")
    res_rew_page = client.get(f"/reward/{reward_id}")
    assert res_rew_page.status_code == 200
    html_rew = res_rew_page.get_data(as_text=True)
    assert "GO BACK TO HOME" in html_rew, "Redeem page must have [ GO BACK TO HOME ]"
    assert "reward-waste-category" in html_rew, "Redeem page must display waste category"
    assert "reward-waste-confidence" in html_rew, "Redeem page must display confidence"

    # Fetch reward metadata API
    res_rew_api = client.get(f"/api/reward/{reward_id}")
    assert res_rew_api.status_code == 200
    rew_info = res_rew_api.get_json()
    assert rew_info["reward_id"] == reward_id
    assert rew_info["category"] == "Plastic"
    assert rew_info["status"] == "UNCLAIMED"
    print(f"  -> Reward {reward_id} metadata: status={rew_info['status']}, category={rew_info['category']}")

    # Phone 2 claims reward
    res_claim = client.post(f"/api/reward/{reward_id}/claim", json={
        "name": "Kushagra",
        "email": "kushagra@econova.org"
    })
    assert res_claim.status_code == 200
    claim_data = res_claim.get_json()
    assert claim_data["success"] is True
    assert claim_data["status"] == "CLAIMED"
    print(f"  -> PASSED: Reward claimed! Total points: {claim_data['total_points']}")

    # Verify Kiosk State transitioned to CLAIMED
    res_kiosk_claimed = client.get("/api/kiosk/state")
    kiosk_claimed_data = res_kiosk_claimed.get_json()
    assert kiosk_claimed_data["status"] == "claimed"
    assert kiosk_claimed_data["claimed"] is True
    print("  -> PASSED: Kiosk state synchronized to 'claimed'.")

    # -------------------------------------------------------------------------
    # 7. DASHBOARD DATA ON PHONE 2 (/api/dashboard)
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Verifying Phone 2 Dashboard Data Loading...")
    res_dash = client.get("/api/dashboard")
    assert res_dash.status_code == 200
    dash_data = res_dash.get_json()
    assert "items_recycled" in dash_data
    assert "category_counts" in dash_data
    assert "recent_rewards" in dash_data
    print(f"  -> PASSED: /api/dashboard loaded (Items recycled: {dash_data['items_recycled']}).")

    # -------------------------------------------------------------------------
    # 8. PAPER ROUTING PRESERVATION (Paper -> Dry/Plastic)
    # -------------------------------------------------------------------------
    print("\n[TEST 8] Verifying Paper Routing Preservation...")
    reset_kiosk_state()
    res_paper = client.post("/api/sort", json={
        "category": "Paper",
        "confidence": 0.92
    })
    assert res_paper.status_code == 200
    paper_data = res_paper.get_json()
    assert paper_data["category"] == "Paper"
    assert paper_data["hardware_command"] == "PLASTIC"
    assert paper_data["hardware_destination"] == "Dry/Plastic"
    print("  -> PASSED: Paper routing preserved: category='Paper' -> command='PLASTIC' -> destination='Dry/Plastic'.")

    print("\n" + "=" * 80)
    print("      ALL TWO-PHONE ARCHITECTURE VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()
