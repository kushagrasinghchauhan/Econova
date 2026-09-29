"""
test_new_architecture.py
-------------------------
Verification suite for the new EcoNova architecture:
PHONE = Camera Scanner
LAPTOP = AI + Backend + ESP32 + Database + QR Generator + Large QR Display
PHONE scans QR from Laptop screen to claim rewards.
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


def test_new_architecture():
    init_db()
    reset_kiosk_state()
    client = app.test_client()

    print("=" * 70)
    print("      EcoNova Dual-Mode Architecture & Reward Flow Test Suite")
    print("=" * 70)

    # -----------------------------------------------------------------
    # TEST 1: Laptop Kiosk Display Mode (?mode=kiosk)
    # -----------------------------------------------------------------
    print("\n[TEST 1] Testing Laptop Kiosk Display Mode (?mode=kiosk)...")
    res1 = client.get("/?mode=kiosk")
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
    html1 = res1.get_data(as_text=True)

    # 1. Verify Kiosk elements exist
    assert "chamber-kiosk-overlay" in html1, "Missing chamber-kiosk-overlay for laptop display"
    assert "kiosk-qr-section" in html1, "Missing kiosk-qr-section for laptop display"
    assert "kiosk-qr-countdown" in html1, "Missing QR expiration countdown"
    assert "YOUR REWARD IS READY" in html1, "Missing 'YOUR REWARD IS READY' headline"
    assert "Scan this QR code with your phone" in html1, "Missing 'Scan this QR code with your phone' prompt"

    # 2. Verify JavaScript safeguards for Kiosk Mode (Laptop NEVER calls getUserMedia)
    with open(os.path.join(ROOT, "frontend", "script.js"), "r", encoding="utf-8") as f:
        js_code = f.read()

    assert "isKioskMode" in js_code, "Missing isKioskMode flag in script.js"
    assert "Kiosk Display Mode: Laptop is display screen, camera initialization bypassed." in js_code, \
        "Missing camera initialization guard for kiosk mode in startPhoneCamera"
    assert "Kiosk Display Mode: Camera initialization bypassed." in js_code, \
        "Missing camera guard in initCamera"

    # 3. Check /api/kiosk/state initial state
    res_state = client.get("/api/kiosk/state")
    assert res_state.status_code == 200
    st_data = res_state.get_json()
    assert st_data["status"] == "idle", f"Expected idle status, got {st_data['status']}"

    print("  -> PASSED: Laptop Kiosk Display Mode verified. Camera access is strictly bypassed.")

    # -----------------------------------------------------------------
    # TEST 2: Phone Camera Scanner Mode (?mode=phone) & /api/detect
    # -----------------------------------------------------------------
    print("\n[TEST 2] Testing Phone Camera Scanner Mode (?mode=phone) & /api/detect...")
    res2 = client.get("/?mode=phone")
    assert res2.status_code == 200
    html2 = res2.get_data(as_text=True)

    # 1. Verify Phone Mode elements exist
    assert "phone-reward-section" in html2, "Missing phone-reward-section in HTML"
    assert "LOOK AT THE LAPTOP SCREEN" in html2, "Missing prompt directing phone user to laptop screen"
    assert "hidden-capture-canvas" in html2, "Missing hidden capture canvas"

    # 2. Verify rear-camera constraints
    assert 'facingMode: { ideal: "environment" }' in js_code, "Missing rear camera environment constraint"
    assert 'canvas.toDataURL("image/jpeg", 0.8)' in js_code or 'hiddenCanvas.toDataURL("image/jpeg", 0.8)' in js_code, \
        "Missing 0.8 JPEG capture constraint"

    # 3. Test sending live phone frame to /api/detect with real bottle image
    bottle_path = r"C:\Users\kusha\OneDrive\Desktop\bottle\bottle.jpeg"
    assert os.path.exists(bottle_path), f"Bottle image missing at {bottle_path}"
    with open(bottle_path, "rb") as f:
        b64_payload = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")

    res_detect = client.post("/api/detect", json={"image": b64_payload})
    assert res_detect.status_code == 200
    det_data = res_detect.get_json()
    assert det_data["detected"] is True
    assert det_data["category"] == "Plastic"
    assert det_data["confidence"] >= 0.70
    assert det_data["is_confident"] is True

    # 4. Verify detection state synchronized to backend kiosk state for laptop
    res_st2 = client.get("/api/kiosk/state")
    st2_data = res_st2.get_json()
    assert st2_data["status"] == "detected", f"Expected detected status, got {st2_data['status']}"
    assert st2_data["category"] == "Plastic"
    assert st2_data["confidence"] >= 0.70

    print(f"  -> PASSED: Phone frame received. YOLO detected raw '{det_data['raw_class']}' -> Plastic ({det_data['confidence']*100:.1f}%).")
    print(f"  -> PASSED: Kiosk state synchronized: category='{st2_data['category']}' status='{st2_data['status']}'.")

    # -----------------------------------------------------------------
    # TEST 3: Sorting & Reward Generation on Laptop Kiosk
    # -----------------------------------------------------------------
    print("\n[TEST 3] Testing Sorting & Reward Generation on Laptop Kiosk Display...")
    res_sort = client.post("/api/sort", json={"category": "Plastic", "confidence": 0.9218})
    assert res_sort.status_code == 200
    sort_data = res_sort.get_json()
    assert sort_data["success"] is True
    reward_id = sort_data["reward_id"]
    points = sort_data["points"]
    assert points == 5

    # Check that reward record was saved with UNCLAIMED status
    conn = get_connection()
    row = conn.execute("SELECT * FROM rewards WHERE reward_id = ?;", (reward_id,)).fetchone()
    conn.close()
    assert row is not None, f"Reward record {reward_id} missing from SQLite"
    assert row["status"] == "UNCLAIMED", f"Reward must start as UNCLAIMED, got {row['status']}"

    # Check kiosk state updated to 'reward' for laptop display
    res_st3 = client.get("/api/kiosk/state")
    st3_data = res_st3.get_json()
    assert st3_data["status"] == "reward", f"Expected status reward, got {st3_data['status']}"
    assert st3_data["reward_id"] == reward_id
    assert st3_data["points"] == 5
    assert st3_data["category"] == "Plastic"

    # Check QR file exists on disk
    qr_disk_path = os.path.join(ROOT, "rewards", f"{reward_id}.png")
    assert os.path.exists(qr_disk_path), f"QR code file missing at {qr_disk_path}"

    print(f"  -> PASSED: Sorting complete. Reward {reward_id} generated with {points} points (status=UNCLAIMED).")
    print(f"  -> PASSED: Laptop kiosk state updated to REWARD display.")

    # -----------------------------------------------------------------
    # TEST 4: Phone Scans QR from Laptop Screen & Claims Reward
    # -----------------------------------------------------------------
    print("\n[TEST 4] Testing Phone Scanning QR from Laptop Screen & Claiming Reward...")

    # 1. Read QR image and decode its encoded URL
    qr_mat = cv2.imread(qr_disk_path)
    detector = cv2.QRCodeDetector()
    decoded_url, bbox, _ = detector.detectAndDecode(qr_mat)
    print(f"  -> Decoded QR URL from image: {decoded_url}")

    # Check that URL is NOT localhost or 127.0.0.1
    assert "127.0.0.1" not in decoded_url, f"QR contains localhost/127.0.0.1: {decoded_url}"
    assert "localhost" not in decoded_url, f"QR contains localhost: {decoded_url}"
    lan_ip = get_lan_ip()
    assert lan_ip in decoded_url, f"QR does not contain LAN IP {lan_ip}: {decoded_url}"
    assert f"/reward/{reward_id}" in decoded_url or f"/redeem/{reward_id}" in decoded_url

    # 2. Simulate phone opening the scanned QR URL
    reward_path = f"/reward/{reward_id}"
    res_reward_page = client.get(reward_path)
    assert res_reward_page.status_code == 200, f"Expected 200 for {reward_path}, got {res_reward_page.status_code}"
    reward_html = res_reward_page.get_data(as_text=True)
    assert "CLAIM REWARD" in reward_html
    assert "EcoNova Reward" in reward_html

    # Also check /redeem/<reward_id> backward compatibility
    res_redeem_page = client.get(f"/redeem/{reward_id}")
    assert res_redeem_page.status_code == 200

    # 3. Phone user claims the reward
    claim_payload = {
        "name": "Kushagra",
        "email": "kushagra.phone@econova.org"
    }
    res_claim = client.post(f"/api/reward/{reward_id}/claim", json=claim_payload)
    assert res_claim.status_code == 200
    claim_data = res_claim.get_json()
    assert claim_data["success"] is True
    assert claim_data["status"] == "CLAIMED"
    assert claim_data["points_added"] == 5

    # 4. Verify database reflects CLAIMED state
    conn = get_connection()
    row_claimed = conn.execute("SELECT * FROM rewards WHERE reward_id = ?;", (reward_id,)).fetchone()
    conn.close()
    assert row_claimed["status"] == "CLAIMED", f"Expected CLAIMED, got {row_claimed['status']}"

    # 5. Verify Laptop Kiosk registers claim in real-time
    res_st4 = client.get("/api/kiosk/state")
    st4_data = res_st4.get_json()
    assert st4_data["status"] == "claimed"
    assert st4_data["claimed"] is True

    # 6. Test session reset back to idle
    res_reset = client.post("/api/kiosk/reset")
    assert res_reset.status_code == 200
    assert res_reset.get_json()["state"]["status"] == "idle"

    print(f"  -> PASSED: Phone opened {reward_path} and claimed reward.")
    print(f"  -> PASSED: Database updated: status=CLAIMED, points added=+5.")
    print(f"  -> PASSED: Laptop display synchronized: status=claimed, then reset to idle.")

    print("\n" + "=" * 70)
    print("      ALL DUAL-MODE ARCHITECTURE TESTS PASSED (100%)!")
    print("=" * 70)


if __name__ == "__main__":
    test_new_architecture()
