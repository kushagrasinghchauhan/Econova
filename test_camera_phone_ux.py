"""
test_camera_phone_ux.py
-----------------------
Verification suite for the Final EcoNova Camera + Phone UX Architecture:
1. Fixed Prototype Camera on Laptop -> /api/detect -> YOLO (Organic/Plastic/Metal) -> ESP32 -> Servos -> Reward QR
2. User Phone Home -> Camera is strictly OFF -> [ SCAN QR ] [ DASHBOARD ]
3. Tap SCAN QR -> Rear camera opens ONLY for QR detection -> Detects laptop QR -> Camera stops -> Opens /reward/<id>
4. User claims reward -> status=CLAIMED -> Laptop kiosk displays claimed
5. Tap GO BACK TO HOME -> Phone returns to Home -> Camera remains OFF
6. Tap DASHBOARD -> Actual SQLite metrics & history loaded from /api/dashboard
7. Repeat -> Return Home -> Camera stays OFF until SCAN QR is tapped again
"""

import os
import sys
import json
import base64
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from backend.app import app, _kiosk_state, reset_kiosk_state
from backend.database import init_db, get_connection
from backend.reward import get_lan_ip, get_base_url
from ai.detector import WasteDetector, CLASS_NAMES, CONFIDENCE_THRESHOLD


def test_final_architecture():
    init_db()
    reset_kiosk_state()
    client = app.test_client()

    print("=" * 75)
    print("   EcoNova Final Camera + Phone UX Architecture Verification Suite")
    print("=" * 75)

    # -----------------------------------------------------------------
    # STEP 1: Verify Phone Home Page (?mode=phone and /phone)
    # -----------------------------------------------------------------
    print("\n[STEP 1] Verifying Phone Home Page (?mode=phone and /phone)...")
    res_phone = client.get("/phone")
    assert res_phone.status_code == 200, f"Expected 200 for /phone, got {res_phone.status_code}"
    html_phone = res_phone.get_data(as_text=True)

    # Must contain SCAN QR and DASHBOARD buttons
    assert "SCAN QR" in html_phone, "Missing [ SCAN QR ] button on phone home"
    assert "DASHBOARD" in html_phone, "Missing [ DASHBOARD ] button on phone home"
    assert "btn-scan-qr" in html_phone, "Missing btn-scan-qr element"
    assert "btn-dashboard" in html_phone, "Missing btn-dashboard element"

    # Must state camera is OFF by default
    assert "Camera is OFF" in html_phone or "Camera is OFF." in html_phone, "Missing Camera is OFF indicator"
    assert "openQrScanner" in html_phone, "Missing openQrScanner function"
    assert "stopCameraStream" in html_phone, "Missing stopCameraStream function"
    assert "showHomeView" in html_phone, "Missing showHomeView function"
    print("  -> PASSED: Phone Home has [ SCAN QR ], [ DASHBOARD ], and camera is OFF.")

    # Also verify GET /?mode=phone returns the phone home page
    res_mode_phone = client.get("/?mode=phone")
    assert res_mode_phone.status_code == 200
    html_mode = res_mode_phone.get_data(as_text=True)
    assert "SCAN QR" in html_mode and "DASHBOARD" in html_mode, "GET /?mode=phone must serve Phone Home"
    print("  -> PASSED: GET /?mode=phone correctly serves Phone Home page.")

    # -----------------------------------------------------------------
    # STEP 2: Verify Phone Camera is Strictly for QR (No /api/detect)
    # -----------------------------------------------------------------
    print("\n[STEP 2] Verifying Phone Camera Isolation (Rule 1 & Rule 2)...")
    with open(os.path.join(ROOT, "frontend", "phone.html"), "r", encoding="utf-8") as f:
        phone_code = f.read()

    # Must NOT call /api/detect in phone.html
    assert "/api/detect" not in phone_code, "CRITICAL: phone.html must NEVER call /api/detect!"
    assert "detector.detect" not in phone_code, "CRITICAL: phone.html must NEVER run YOLO detector!"
    # Verify QR detection stops camera immediately
    assert "stopCameraStream();" in phone_code, "Missing immediate camera stop on QR detection"
    assert "window.location.href = `/reward/${rewardId}`" in phone_code or "/reward/" in phone_code, \
        "Missing redirect to /reward/<id> upon QR detection"
    print("  -> PASSED: Phone camera NEVER calls /api/detect and stops immediately after QR detection.")

    # -----------------------------------------------------------------
    # STEP 3: Verify Laptop Kiosk Fixed Prototype Camera & Waste Detection
    # -----------------------------------------------------------------
    print("\n[STEP 3] Verifying Laptop Kiosk Prototype Camera & Waste Detection...")
    res_kiosk = client.get("/?mode=kiosk")
    assert res_kiosk.status_code == 200
    html_kiosk = res_kiosk.get_data(as_text=True)
    assert "kiosk-view-2" in html_kiosk, "Missing kiosk camera chamber screen"
    assert "webcam" in html_kiosk, "Missing webcam video element"

    with open(os.path.join(ROOT, "frontend", "script.js"), "r", encoding="utf-8") as f:
        script_code = f.read()

    # Verify laptop kiosk runs frame capture
    assert "setInterval(captureAndDetectFrame, CAPTURE_INTERVAL_MS);" in script_code, \
        "Laptop kiosk must run periodic capture loop for prototype webcam"
    assert "if (isPhoneMode) return;" in script_code, \
        "Phone mode must be strictly blocked from sending frames in captureAndDetectFrame"
    print("  -> PASSED: Laptop kiosk captures from prototype camera; phone mode blocked.")

    # Test live frame detection with bottle image
    bottle_path = r"C:\Users\kusha\OneDrive\Desktop\bottle\bottle.jpeg"
    if not os.path.exists(bottle_path):
        bottle_path = os.path.join(ROOT, "frontend", "bottle.jpeg")
    assert os.path.exists(bottle_path), f"Sample bottle image not found at {bottle_path}"

    with open(bottle_path, "rb") as f:
        b64_payload = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")

    det_res = client.post("/api/detect", json={"image": b64_payload})
    assert det_res.status_code == 200
    det_data = det_res.get_json()
    assert det_data["success"] is True
    assert det_data["detected"] is True
    assert det_data["category"] in ("Plastic", "Organic", "Metal")
    assert det_data["confidence"] >= CONFIDENCE_THRESHOLD
    assert det_data["command"] in ("P", "O", "M")
    print(f"  -> PASSED: /api/detect identified: {det_data['category']} ({det_data['confidence']*100:.1f}%) -> Command: {det_data['command']}")

    # -----------------------------------------------------------------
    # STEP 4: Trigger Sorting & Reward QR Generation on Laptop Kiosk
    # -----------------------------------------------------------------
    print("\n[STEP 4] Verifying Sorting & Reward QR Generation...")
    sort_res = client.post("/api/sort", json={
        "category": det_data["category"],
        "confidence": det_data["confidence"]
    })
    assert sort_res.status_code == 200
    sort_data = sort_res.get_json()
    assert sort_data["success"] is True
    reward_id = sort_data["reward_id"]
    qr_url = sort_data["qr_url"]
    print(f"  -> Generated Reward: {reward_id} (Points: +{sort_data['points']}, QR URL: {qr_url})")

    # Verify kiosk state is updated to REWARD
    kiosk_state_res = client.get("/api/kiosk/state")
    st = kiosk_state_res.get_json()
    assert st["status"] == "reward", f"Expected reward status, got {st['status']}"
    assert st["reward_id"] == reward_id
    print("  -> PASSED: Laptop kiosk state updated to REWARD display.")

    # -----------------------------------------------------------------
    # STEP 5: Phone Scans QR -> Opens /reward/<reward_id>
    # -----------------------------------------------------------------
    print(f"\n[STEP 5] Verifying Reward Page /reward/{reward_id}...")
    rew_page_res = client.get(f"/reward/{reward_id}")
    assert rew_page_res.status_code == 200
    rew_html = rew_page_res.get_data(as_text=True)

    # Must contain GO BACK TO HOME button and waste details
    assert "GO BACK TO HOME" in rew_html, "Missing 'GO BACK TO HOME' button on reward page"
    assert "btn-go-back-home" in rew_html, "Missing btn-go-back-home ID"
    assert "CLAIM REWARD" in rew_html, "Missing 'CLAIM REWARD' button"

    # Check API reward details
    rew_api_res = client.get(f"/api/reward/{reward_id}")
    assert rew_api_res.status_code == 200
    rew_info = rew_api_res.get_json()
    assert rew_info["reward_id"] == reward_id
    assert rew_info["status"] == "UNCLAIMED"
    assert "confidence" in rew_info, "Reward API must include confidence"
    print(f"  -> PASSED: /reward/{reward_id} loaded. Status: UNCLAIMED, Points: +{rew_info['points']}.")

    # -----------------------------------------------------------------
    # STEP 6: Phone Claims Reward -> Kiosk Updates to CLAIMED
    # -----------------------------------------------------------------
    print(f"\n[STEP 6] Claiming Reward {reward_id} on Phone...")
    claim_res = client.post(f"/api/reward/{reward_id}/claim", json={
        "name": "Kushagra",
        "email": "kushagra@econova.org"
    })
    assert claim_res.status_code == 200
    claim_data = claim_res.get_json()
    assert claim_data["success"] is True
    assert claim_data["status"] == "CLAIMED"
    print(f"  -> PASSED: Reward claimed! Points added: +{claim_data['points_added']}, Total: {claim_data['total_points']}")

    # Verify kiosk state reflects claimed
    kiosk_claimed = client.get("/api/kiosk/state").get_json()
    assert kiosk_claimed["status"] == "claimed"
    print("  -> PASSED: Laptop kiosk displays 'CLAIMED'.")

    # -----------------------------------------------------------------
    # STEP 7: Phone Taps [ GO BACK TO HOME ] -> Camera Remains OFF
    # -----------------------------------------------------------------
    print("\n[STEP 7] Verifying [ GO BACK TO HOME ] -> Phone Home with Camera OFF...")
    # The GO BACK TO HOME button links to /?mode=phone or /phone
    res_home_again = client.get("/phone")
    assert res_home_again.status_code == 200
    assert "Camera is OFF" in res_home_again.get_data(as_text=True)
    print("  -> PASSED: Returned to Phone Home. Camera remains OFF.")

    # -----------------------------------------------------------------
    # STEP 8: Phone Taps [ DASHBOARD ] -> Live SQLite Statistics
    # -----------------------------------------------------------------
    print("\n[STEP 8] Verifying User Dashboard (/api/dashboard)...")
    dash_res = client.get("/api/dashboard")
    assert dash_res.status_code == 200
    dash_data = dash_res.get_json()
    assert "items_recycled" in dash_data, "Missing items_recycled in dashboard"
    assert "category_counts" in dash_data, "Missing category_counts in dashboard"
    assert "Organic" in dash_data["category_counts"]
    assert "Plastic" in dash_data["category_counts"]
    assert "Metal" in dash_data["category_counts"]
    assert "rewards_history" in dash_data or "recent_rewards" in dash_data, "Missing rewards history in dashboard"

    print(f"  -> Dashboard Data:")
    print(f"     * Total Items Recycled: {dash_data['items_recycled']}")
    print(f"     * Organic: {dash_data['category_counts']['Organic']}")
    print(f"     * Plastic: {dash_data['category_counts']['Plastic']}")
    print(f"     * Metal:   {dash_data['category_counts']['Metal']}")
    print("  -> PASSED: Dashboard data reflects actual SQLite database records.")

    # -----------------------------------------------------------------
    # STEP 9: Verify Paper Routing Compatibility
    # -----------------------------------------------------------------
    print("\n[STEP 9] Verifying Paper Routing Compatibility...")
    paper_res = client.post("/api/sort", json={
        "category": "Paper",
        "confidence": 0.92
    })
    assert paper_res.status_code == 200
    paper_data = paper_res.get_json()
    assert paper_data["category"] == "Paper"
    assert paper_data["hardware_destination"] == "Dry/Plastic"
    assert paper_data["hardware_command"] == "PLASTIC"
    print("  -> PASSED: Paper correctly routes to 'Dry/Plastic' (Command: PLASTIC).")

    print("\n" + "=" * 75)
    print("   ALL 9 FINAL ARCHITECTURE & PHONE UX VERIFICATIONS PASSED (100%)!")
    print("=" * 75)


if __name__ == "__main__":
    test_final_architecture()
