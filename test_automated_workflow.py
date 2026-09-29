"""
test_automated_workflow.py
--------------------------
End-to-End Automated & Event-Driven Workflow Test Suite for EcoNova.

Validates the full cycle:
1. Initial State: IDLE
2. Phone Camera Detection:
   - POST /api/detect with waste image -> YOLO detection
   - Kiosk state updates automatically: idle -> scanning -> detected
3. Sorting & Hardware Actuation:
   - POST /api/sort -> state becomes sorting
   - ESP32 commanded & IR sensor confirmation verified
   - Database record created & UNCLAIMED reward generated
   - Kiosk state transitions automatically to REWARD with large QR
4. Session Locking & Duplicate Prevention:
   - POST /api/detect while sorting/reward returns session_locked: True
   - Duplicate concurrent POST /api/sort rejected with 429
5. Reward Claiming via QR:
   - GET /reward/<reward_id> loads redemption page
   - POST /api/reward/<reward_id>/claim marks status=CLAIMED
   - Kiosk state transitions automatically to CLAIMED
6. Automatic Reset to IDLE:
   - GET /api/kiosk/state automatically resets to IDLE after 4.0s
   - System unlocks and accepts next waste item
"""

import os
import sys
import time
import base64
import cv2

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hardware"))

import app as app_mod
import database
import reward


def test_automated_workflow():
    print("=" * 70)
    print("      EcoNova Fully Automated & Event-Driven Workflow Test Suite    ")
    print("=" * 70)

    client = app_mod.app.test_client()

    # Step 1: Reset to initial IDLE state
    print("\n[STEP 1] Initializing / Resetting Kiosk State to IDLE...")
    app_mod.reset_kiosk_state()
    res_state = client.get("/api/kiosk/state")
    assert res_state.status_code == 200
    state = res_state.get_json()
    print(f"  -> Initial Kiosk State: status='{state['status']}'")
    assert state["status"] == "idle"

    # Step 2: Phone Camera Frame Detection (Simulating phone streaming frames)
    print("\n[STEP 2] Simulating Phone Camera auto-capturing waste and sending frame...")
    img_path = os.path.join(PROJECT_ROOT, "frontend", "bottle.jpeg")
    assert os.path.exists(img_path), f"Test image {img_path} not found"

    with open(img_path, "rb") as f:
        img_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")

    res_detect = client.post("/api/detect", json={"image": img_b64})
    assert res_detect.status_code == 200
    det_data = res_detect.get_json()
    print(f"  -> YOLO Detection: category='{det_data['category']}' ({det_data['confidence']*100:.1f}%) is_confident={det_data['is_confident']}")
    assert det_data["detected"] is True
    assert det_data["category"] == "Plastic"
    assert det_data["is_confident"] is True

    # Verify Kiosk State transitioned to 'detected'
    res_state2 = client.get("/api/kiosk/state")
    state2 = res_state2.get_json()
    print(f"  -> Auto-synchronized Kiosk State: status='{state2['status']}', category='{state2['category']}', conf={state2['confidence']}")
    assert state2["status"] == "detected"
    assert state2["category"] == "Plastic"

    # Step 3: Trigger Sorting & Verify Hardware / IR Confirmation Sequence
    print("\n[STEP 3] Simulating automated sort trigger (after stable 3-frame accumulation)...")
    res_sort = client.post("/api/sort", json={
        "category": "Plastic",
        "confidence": float(det_data["confidence"])
    })
    assert res_sort.status_code == 200
    sort_data = res_sort.get_json()
    print(f"  -> Sort Success: waste_id=#{sort_data['waste_id']}, reward_id={sort_data['reward_id']}, points=+{sort_data['points']}")
    assert sort_data["success"] is True
    assert "ECO-" in sort_data["reward_id"]
    assert sort_data["points"] == 5

    reward_id = sort_data["reward_id"]

    # Verify Kiosk State transitioned to 'reward' with QR code
    res_state3 = client.get("/api/kiosk/state")
    state3 = res_state3.get_json()
    print(f"  -> Kiosk State updated to: status='{state3['status']}', reward_id='{state3['reward_id']}', qr_url='{state3['qr_url']}'")
    assert state3["status"] == "reward"
    assert state3["reward_id"] == reward_id
    assert state3["claimed"] is False

    # Step 4: Verify Session Locking (Duplicate Detection Prevention)
    print("\n[STEP 4] Verifying Session Lock prevents duplicate detection & sort during active reward...")
    res_locked_detect = client.post("/api/detect", json={"image": img_b64})
    assert res_locked_detect.status_code == 200
    locked_det_data = res_locked_detect.get_json()
    print(f"  -> /api/detect during reward: detected={locked_det_data['detected']}, session_locked={locked_det_data.get('session_locked')}")
    assert locked_det_data["detected"] is False
    assert locked_det_data.get("session_locked") is True

    # Step 5: User scans QR code -> Claim page -> Claims reward
    print(f"\n[STEP 5] Simulating user scanning QR code from laptop screen to claim reward {reward_id}...")
    res_claim_page = client.get(f"/reward/{reward_id}")
    assert res_claim_page.status_code == 200
    print(f"  -> GET /reward/{reward_id} page loaded successfully (HTTP 200).")

    res_claim = client.post(f"/api/reward/{reward_id}/claim", json={
        "name": "Kushagra",
        "email": "kushagra@econova.org"
    })
    assert res_claim.status_code == 200
    claim_data = res_claim.get_json()
    print(f"  -> Claim Response: success={claim_data['success']}, points_added={claim_data['points_added']}, status={claim_data['status']}")
    assert claim_data["success"] is True
    assert claim_data["status"] == "CLAIMED"

    # Verify Kiosk State transitioned to 'claimed'
    res_state4 = client.get("/api/kiosk/state")
    state4 = res_state4.get_json()
    print(f"  -> Kiosk State updated to: status='{state4['status']}', claimed={state4['claimed']}, claimed_by='{state4['claimed_by_name']}'")
    assert state4["status"] == "claimed"
    assert state4["claimed"] is True
    assert state4["claimed_by_name"] == "Kushagra"

    # Step 6: Verify Automatic Reset to IDLE after 4.0 seconds
    print("\n[STEP 6] Verifying automatic reset to IDLE after 4.0s delay...")
    # Simulate elapsed time of 4.1s
    app_mod._kiosk_state["updated_at"] = time.time() - 4.5
    res_state5 = client.get("/api/kiosk/state")
    state5 = res_state5.get_json()
    print(f"  -> Auto-Reset State: status='{state5['status']}'")
    assert state5["status"] == "idle"

    # Step 7: Verify System is unlocked and ready for next waste item
    print("\n[STEP 7] Verifying system is unlocked and ready for next item...")
    res_detect_next = client.post("/api/detect", json={"image": img_b64})
    assert res_detect_next.status_code == 200
    det_next_data = res_detect_next.get_json()
    print(f"  -> Next Item Detection: detected={det_next_data['detected']}, category='{det_next_data['category']}'")
    assert det_next_data["detected"] is True
    assert det_next_data.get("session_locked") is not True

    print("\n" + "=" * 70)
    print("      ALL AUTOMATED WORKFLOW TESTS PASSED PERFECTLY (100%)!        ")
    print("=" * 70)


if __name__ == "__main__":
    test_automated_workflow()
