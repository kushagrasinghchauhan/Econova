"""
test_stage6.py
--------------
Automated end-to-end integration test suite for EcoNova Stage 6:
Full System Integration: AI -> Sorter -> SQLite -> QR Code -> User Claim -> Dashboard.
"""

import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))

import database
import reward
from app import app


def test_stage6_full_integration():
    print("=" * 60)
    print("      EcoNova Stage 6 - Full System Integration Test       ")
    print("=" * 60)

    client = app.test_client()

    # -------------------------------------------------------------
    # 1. FRONTEND ROUTE CHECKS
    # -------------------------------------------------------------
    print("\n[STEP 1] Testing Web Routes & Page Delivery...")
    
    # Check Home page
    res_home = client.get("/")
    assert res_home.status_code == 200, f"Expected 200 for /, got {res_home.status_code}"
    home_html = res_home.get_data(as_text=True)
    assert "ECOnova" in home_html
    assert "How EcoNova Works" in home_html
    assert "Waste Categories & Rewards" in home_html
    assert "Upload Image" in home_html
    assert "Dashboard" in home_html
    print("  -> Home page (/) contains all required Stage 6 components.")

    # Check Dashboard page
    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200, f"Expected 200 for /dashboard, got {res_dash.status_code}"
    dash_html = res_dash.get_data(as_text=True)
    assert "EcoNova Dashboard" in dash_html
    assert "stat-total-points" in dash_html
    assert "stat-total-items" in dash_html
    assert "history-table" in dash_html
    print("  -> Dashboard page (/dashboard) delivers analytics & history layout.")

    # Check Redemption page
    res_redeem = client.get("/redeem/ECO-TEST01")
    assert res_redeem.status_code == 200, f"Expected 200 for /redeem/<id>, got {res_redeem.status_code}"
    redeem_html = res_redeem.get_data(as_text=True)
    assert "EcoNova Reward Redemption" in redeem_html
    assert "btn-claim-reward" in redeem_html
    print("  -> Redemption page (/redeem/<id>) delivers voucher layout.")

    # -------------------------------------------------------------
    # 2. AI DETECTOR ENDPOINT CHECKS
    # -------------------------------------------------------------
    print("\n[STEP 2] Testing AI Detector Endpoints...")
    res_status = client.get("/api/detector/status")
    assert res_status.status_code == 200
    status_data = res_status.get_json()
    assert "classes" in status_data
    assert "Organic" in status_data["classes"]
    assert "Plastic" in status_data["classes"]
    assert "Metal" in status_data["classes"]
    assert status_data["points_map"]["Plastic"] == 5
    print("  -> AI Detector status confirmed:", status_data["classes"])

    res_detect = client.post("/api/detect", json={})
    assert res_detect.status_code == 200
    detect_data = res_detect.get_json()
    assert (detect_data.get("error") == "YOLO_MODEL_MISSING") or ("detected" in detect_data)
    print("  -> AI Detect endpoint verified (Missing model detected cleanly: YOLO_MODEL_MISSING)")

    # -------------------------------------------------------------
    # 3. END-TO-END SORTING & REWARD CREATION
    # -------------------------------------------------------------
    print("\n[STEP 3] Testing Sorting -> SQLite Record -> QR Code Generation...")
    sort_res = client.post("/api/sort", json={
        "category": "Plastic",
        "confidence": 0.94
    })
    assert sort_res.status_code == 200
    sort_data = sort_res.get_json()
    assert sort_data["success"] is True
    assert sort_data["category"] == "Plastic"
    assert sort_data["points"] == 5
    plastic_reward_id = sort_data["reward_id"]
    assert plastic_reward_id.startswith("ECO-")
    print(f"  -> Generated Reward ID: {plastic_reward_id} (+5 Points)")

    # Verify QR code image file exists on disk
    qr_filename = f"{plastic_reward_id}.png"
    qr_filepath = os.path.join(PROJECT_ROOT, "rewards", qr_filename)
    assert os.path.exists(qr_filepath), f"QR code file {qr_filepath} does not exist!"
    assert os.path.getsize(qr_filepath) > 0, "QR code image file is empty!"
    print(f"  -> QR code image verified on disk ({os.path.getsize(qr_filepath)} bytes)")

    # Verify Reward API inspection
    rew_res = client.get(f"/api/reward/{plastic_reward_id}")
    assert rew_res.status_code == 200
    rew_data = rew_res.get_json()
    assert rew_data["reward_id"] == plastic_reward_id
    assert rew_data["points"] == 5
    assert rew_data["status"] == "UNCLAIMED"
    print("  -> Reward API confirmed UNCLAIMED status.")

    # -------------------------------------------------------------
    # 4. USER REGISTRATION & REWARD CLAIM
    # -------------------------------------------------------------
    print("\n[STEP 4] Testing User Creation & Reward Claiming...")
    unique_email = f"hackathon_winner_{int(time.time() * 1000)}@econova.org"
    user_res = client.post("/api/user", json={
        "name": "SIH Participant",
        "email": unique_email
    })
    assert user_res.status_code == 200
    user_data = user_res.get_json()
    user_id = user_data["id"]
    assert user_data["points"] == 0, f"New user must start with 0 points, got {user_data['points']}"
    print(f"  -> Created User #{user_id} ({unique_email}) with initial 0 points.")

    # Claim Plastic (+5 points)
    claim1_res = client.post(f"/api/reward/{plastic_reward_id}/claim", json={
        "user_id": user_id
    })
    assert claim1_res.status_code == 200
    claim1_data = claim1_res.get_json()
    assert claim1_data["success"] is True
    assert claim1_data["points_added"] == 5
    assert claim1_data["total_points"] == 5
    print("  -> Claimed Plastic reward: User total points = 5")

    # Double claim prevention
    claim_dup = client.post(f"/api/reward/{plastic_reward_id}/claim", json={
        "user_id": user_id
    })
    assert claim_dup.status_code == 400
    dup_data = claim_dup.get_json()
    assert dup_data["success"] is False
    assert "already claimed" in dup_data["message"].lower()
    print("  -> Double-claim correctly prevented with HTTP 400.")

    # -------------------------------------------------------------
    # 5. SORT & CLAIM METAL REWARD (+7 Points)
    # -------------------------------------------------------------
    print("\n[STEP 5] Sorting & Claiming Metal Waste (+7 Points)...")
    sort_metal = client.post("/api/sort", json={
        "category": "Metal",
        "confidence": 0.96
    })
    assert sort_metal.status_code == 200
    metal_reward_id = sort_metal.get_json()["reward_id"]

    claim_metal = client.post(f"/api/reward/{metal_reward_id}/claim", json={
        "user_id": user_id
    })
    assert claim_metal.status_code == 200
    metal_data = claim_metal.get_json()
    assert metal_data["points_added"] == 7
    assert metal_data["total_points"] == 12  # 5 + 7 = 12
    print(f"  -> Claimed Metal reward: User total points = {metal_data['total_points']}")

    # -------------------------------------------------------------
    # 6. SORT & CLAIM ORGANIC REWARD (+3 Points) VIA EMAIL RESOLUTION
    # -------------------------------------------------------------
    print("\n[STEP 6] Sorting & Claiming Organic Waste (+3 Points) via Email Auto-Resolve...")
    sort_org = client.post("/api/sort", json={
        "category": "Organic",
        "confidence": 0.92
    })
    assert sort_org.status_code == 200
    org_reward_id = sort_org.get_json()["reward_id"]

    # Claim using name + email without explicit user_id
    claim_org = client.post(f"/api/reward/{org_reward_id}/claim", json={
        "name": "SIH Participant",
        "email": unique_email
    })
    assert claim_org.status_code == 200
    org_data = claim_org.get_json()
    assert org_data["points_added"] == 3
    assert org_data["total_points"] == 15  # 12 + 3 = 15
    print(f"  -> Claimed Organic reward: User total points = {org_data['total_points']}")

    # -------------------------------------------------------------
    # 7. DASHBOARD SUMMARY & STATS API VERIFICATION
    # -------------------------------------------------------------
    print("\n[STEP 7] Verifying Dashboard Summary & Statistics API...")
    summary_res = client.get(f"/api/dashboard/summary?user_id={user_id}")
    assert summary_res.status_code == 200
    summary_data = summary_res.get_json()

    print("  Dashboard Summary API Response:")
    print(f"    - Total Account Points: {summary_data['user']['points']}")
    print(f"    - User Name: {summary_data['user']['name']}")
    print(f"    - Total Items Recycled: {summary_data['items_recycled']}")
    print(f"    - Category Counts: {summary_data['category_counts']}")
    print(f"    - Rewards History Count: {len(summary_data['rewards_history'])}")

    # Verify user points match
    assert summary_data["user"]["points"] == 15, f"Expected 15 points, got {summary_data['user']['points']}"
    assert summary_data["user"]["id"] == user_id

    # Verify category counts include our 3 items
    assert summary_data["category_counts"]["Organic"] >= 1
    assert summary_data["category_counts"]["Plastic"] >= 1
    assert summary_data["category_counts"]["Metal"] >= 1

    # Verify reward history entries
    history_ids = [r["reward_id"] for r in summary_data["rewards_history"]]
    assert plastic_reward_id in history_ids, f"{plastic_reward_id} missing in history"
    assert metal_reward_id in history_ids, f"{metal_reward_id} missing in history"
    assert org_reward_id in history_ids, f"{org_reward_id} missing in history"
    print("  -> Confirmed all 3 claimed rewards appear in dashboard history.")

    # Check global stats API
    stats_res = client.get("/api/dashboard/stats")
    assert stats_res.status_code == 200
    stats_data = stats_res.get_json()
    assert stats_data["success"] is True
    assert stats_data["items_recycled"] >= 3
    print(f"  -> Global stats confirmed: {stats_data['items_recycled']} total items sorted.")

    print("\n" + "=" * 60)
    print("  ALL STAGE 6 & FULL INTEGRATION TESTS PASSED SUCCESSFULLY!  ")
    print("=" * 60)


if __name__ == "__main__":
    test_stage6_full_integration()
