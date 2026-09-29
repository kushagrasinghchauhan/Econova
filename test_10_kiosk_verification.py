"""
Verification script for EcoNova "Nature Meets Technology" UI and Real Detection Kiosk.
Runs all 10 verification steps requested by user.
"""
import os
import sys
import json
import base64

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from backend.app import app
from backend.database import get_connection, init_db

def run_10_verification_tests():
    init_db()
    client = app.test_client()

    print("=" * 70)
    print("      EcoNova Kiosk UI & Real Detection 10-Step Verification Suite")
    print("=" * 70)

    # 1. GET / (Main Kiosk UI)
    print("\n[VERIFICATION 1] Testing GET / (Main Kiosk Screen 1 - 5 & 7)...")
    res1 = client.get("/")
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
    html1 = res1.get_data(as_text=True)
    assert "RECYCLE TODAY" in html1, "Missing headline 'RECYCLE TODAY'"
    assert "AI-Powered Smart Recycling Kiosk" in html1, "Missing subtitle"
    assert "START RECYCLING →" in html1, "Missing CTA 'START RECYCLING →'"
    assert "SCANNING..." in html1, "Missing Step 1 scanning elements"
    assert "sorting-progress-chain" in html1, "Missing 4-stage sorting progress chain"
    assert "WASTE SEGREGATED SUCCESSFULLY!" in html1, "Missing Screen 5 success modal"
    print("  -> PASSED: Welcome Kiosk, 3-step tracker, 4-stage sorting chain, and modal present.")

    # 2. GET /api/detector/status
    print("\n[VERIFICATION 2] Testing GET /api/detector/status...")
    res2 = client.get("/api/detector/status")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["status"]["is_ready"] is True
    assert "YOLO11n COCO" in data2["status"]["detector_title"]
    print(f"  -> PASSED: Detector ready ({data2['status']['detector_title']})")

    # 3. POST /api/detect with real bottle image
    print("\n[VERIFICATION 3] Testing POST /api/detect with real bottle image...")
    bottle_path = r"C:\Users\kusha\OneDrive\Desktop\bottle\bottle.jpeg"
    assert os.path.exists(bottle_path), f"Bottle image missing at {bottle_path}"
    with open(bottle_path, "rb") as f:
        img_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")
    res3 = client.post("/api/detect", json={"image": img_b64})
    assert res3.status_code == 200
    data3 = res3.get_json()
    assert data3["detected"] is True
    assert data3["raw_class"] == "bottle"
    assert data3["category"] == "Plastic"
    assert data3["confidence"] >= 0.70
    assert data3["is_confident"] is True
    print(f"  -> PASSED: YOLO raw '{data3['raw_class']}' mapped to '{data3['category']}' ({data3['confidence']*100:.2f}%) bbox={data3['bbox']}")

    # 4. POST /api/detect with empty frame
    print("\n[VERIFICATION 4] Testing POST /api/detect with empty frame...")
    res4 = client.post("/api/detect", json={})
    assert res4.status_code == 200
    data4 = res4.get_json()
    assert data4["detected"] is False
    print(f"  -> PASSED: Clean non-detection response without fabrication.")

    # 5. POST /api/sort (Virtual sorting & QR reward generation)
    print("\n[VERIFICATION 5] Testing POST /api/sort...")
    res5 = client.post("/api/sort", json={"category": "Plastic", "confidence": 0.9218})
    assert res5.status_code == 200
    data5 = res5.get_json()
    assert data5["success"] is True
    assert "ECO-" in data5["reward_id"]
    reward_id = data5["reward_id"]
    qr_img_path = os.path.join(ROOT, "rewards", f"{reward_id}.png")
    assert os.path.exists(qr_img_path), f"QR code file not found at {qr_img_path}"
    print(f"  -> PASSED: Created reward {reward_id} (+{data5['points']} pts), verified QR on disk.")

    # 6. GET /redeem/<reward_id>
    print(f"\n[VERIFICATION 6] Testing GET /redeem/{reward_id}...")
    res6 = client.get(f"/redeem/{reward_id}")
    assert res6.status_code == 200
    html6 = res6.get_data(as_text=True)
    assert "EcoNova Reward" in html6
    assert "CLAIM REWARD" in html6
    assert "VIEW MY IMPACT" in html6
    assert "GO TO HOME" in html6
    print("  -> PASSED: Redemption page loads with Screen 8 dual action buttons and claim structure.")

    # 7. POST /api/user (User registration)
    print("\n[VERIFICATION 7] Testing POST /api/user...")
    user_email = f"kiosk_verifier_{os.getpid()}@econova.org"
    res7 = client.post("/api/user", json={"name": "Kiosk Verifier", "email": user_email})
    assert res7.status_code in (200, 201)
    user_data = res7.get_json()
    user_id = user_data["id"]
    print(f"  -> PASSED: Registered User #{user_id} ({user_email})")

    # 8. POST /api/reward/<id>/claim (Reward claiming & double-claim prevention)
    print(f"\n[VERIFICATION 8] Testing POST /api/reward/{reward_id}/claim...")
    res8 = client.post(f"/api/reward/{reward_id}/claim", json={"user_id": user_id})
    assert res8.status_code == 200
    claim_data = res8.get_json()
    assert claim_data["success"] is True
    assert claim_data["points_added"] == 5
    # Double claim check
    res8_double = client.post(f"/api/reward/{reward_id}/claim", json={"user_id": user_id})
    assert res8_double.status_code == 400
    print(f"  -> PASSED: Reward claimed for User #{user_id}. Double claim rejected safely.")

    # 9. GET /api/dashboard/summary
    print("\n[VERIFICATION 9] Testing GET /api/dashboard/summary...")
    res9 = client.get(f"/api/dashboard/summary?user_id={user_id}")
    assert res9.status_code == 200
    dash_data = res9.get_json()
    assert dash_data["user"]["points"] >= 5
    assert dash_data["category_counts"]["Plastic"] >= 1
    print(f"  -> PASSED: Summary returned user points={dash_data['user']['points']}, total items={dash_data['items_recycled']}.")

    # 10. GET /dashboard (Screen 6 & 9)
    print("\n[VERIFICATION 10] Testing GET /dashboard (Screen 6 & 9)...")
    res10 = client.get("/dashboard")
    assert res10.status_code == 200
    html10 = res10.get_data(as_text=True)
    assert "EcoNova Dashboard" in html10
    assert "stat-total-points" in html10
    assert "stat-total-items" in html10
    assert "count-stat-plastic" in html10
    assert "count-stat-organic" in html10
    assert "count-stat-metal" in html10
    assert "Your Recycling Contribution" in html10
    assert "Total Impact" in html10
    assert "My Contributions" in html10
    assert "filter-btn-all" in html10
    assert "filter-btn-plastic" in html10
    assert "filter-btn-organic" in html10
    assert "filter-btn-metal" in html10
    assert "history-table" in html10
    print("  -> PASSED: Dashboard contains all 5 metric cards, Your Recycling Contribution, Total Impact, and My Contributions with category filter pills.")

    print("\n" + "=" * 70)
    print("      ALL 10 VERIFICATION TESTS COMPLETED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    run_10_verification_tests()
