"""
Automated test suite for EcoNova Stage 5: User Accounts & Points Connection.
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))

import database
import reward
from app import app


def test_stage5():
    print("==================================================")
    print("Testing EcoNova Stage 5 (User Accounts & Points)")
    print("==================================================")

    client = app.test_client()

    # -------------------------------------------------------------
    # TEST 1: Create a new user
    # -------------------------------------------------------------
    import time
    unique_email = f"kushagra_{int(time.time() * 1000)}@example.com"
    user_res = client.post("/api/user", json={
        "name": "Kushagra",
        "email": unique_email
    })
    assert user_res.status_code == 200, f"Expected 200, got {user_res.status_code}"
    user_data = user_res.get_json()
    print("  POST /api/user response:", user_data)
    assert user_data["success"] is True
    assert user_data["name"] == "Kushagra"
    assert user_data["email"] == unique_email
    assert user_data["points"] == 0, f"Expected 0 points for new user, got {user_data['points']}"
    user_id = user_data["id"]
    print(f"  -> Passed TEST 1 (User #{user_id} created with 0 points).")

    # Verify duplicate registration returns existing user without resetting points
    dup_res = client.post("/api/user", json={
        "name": "Kushagra",
        "email": unique_email
    })
    assert dup_res.status_code == 200
    assert dup_res.get_json()["id"] == user_id
    print("  Verified re-registration with same email returns existing user.")

    # -------------------------------------------------------------
    # TEST 2: Claim Plastic reward -> User gets +5 points
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing claiming Plastic reward (+5 points)...")
    p_waste = database.save_waste_record("Plastic", 0.94)
    p_rew = reward.create_reward(p_waste["id"])
    plastic_reward_id = p_rew["reward_id"]
    print(f"  Generated Plastic reward {plastic_reward_id} for waste #{p_waste['id']}")

    claim_p = client.post(f"/api/reward/{plastic_reward_id}/claim", json={"user_id": user_id})
    assert claim_p.status_code == 200
    claim_p_data = claim_p.get_json()
    print("  Claim response:", claim_p_data)
    assert claim_p_data["success"] is True
    assert claim_p_data["points_added"] == 5
    assert claim_p_data["total_points"] == 5
    print("  -> Passed TEST 2 (User points updated to 5).")

    # -------------------------------------------------------------
    # TEST 3: Claim same reward again -> No additional points
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing double-claim prevention on claimed reward...")
    claim_dup = client.post(f"/api/reward/{plastic_reward_id}/claim", json={"user_id": user_id})
    assert claim_dup.status_code == 400
    claim_dup_data = claim_dup.get_json()
    print("  Double claim rejection:", claim_dup_data)
    assert claim_dup_data["success"] is False
    assert "Reward already claimed" in claim_dup_data["message"]

    # Verify user points remain exactly 5 in DB
    u_chk = database.get_user_by_id(user_id)
    assert u_chk["points"] == 5, f"Points should remain 5, got {u_chk['points']}"
    print("  Verified user points remain at 5 without duplicate increments.")
    print("  -> Passed TEST 3 (Double-claim prevented).")

    # -------------------------------------------------------------
    # TEST 4: Claim Metal reward -> User gets +7 points (5 -> 12)
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing claiming Metal reward (+7 points)...")
    m_waste = database.save_waste_record("Metal", 0.96)
    m_rew = reward.create_reward(m_waste["id"])
    metal_reward_id = m_rew["reward_id"]

    claim_m = client.post(f"/api/reward/{metal_reward_id}/claim", json={"user_id": user_id})
    assert claim_m.status_code == 200
    claim_m_data = claim_m.get_json()
    print("  Claim response:", claim_m_data)
    assert claim_m_data["points_added"] == 7
    assert claim_m_data["total_points"] == 12
    print("  -> Passed TEST 4 (User points updated to 12).")

    # -------------------------------------------------------------
    # TEST 5: Claim Organic reward -> User gets +3 points (12 -> 15)
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing claiming Organic reward (+3 points)...")
    o_waste = database.save_waste_record("Organic", 0.92)
    o_rew = reward.create_reward(o_waste["id"])
    organic_reward_id = o_rew["reward_id"]

    claim_o = client.post(f"/api/reward/{organic_reward_id}/claim", json={"user_id": user_id})
    assert claim_o.status_code == 200
    claim_o_data = claim_o.get_json()
    print("  Claim response:", claim_o_data)
    assert claim_o_data["points_added"] == 3
    assert claim_o_data["total_points"] == 15
    print("  -> Passed TEST 5 (User points updated to 15).")

    # -------------------------------------------------------------
    # TEST 6: Refresh the page / direct SQLite query -> Points remain 15
    # -------------------------------------------------------------
    print("\n[TEST 6] Testing SQLite database persistence after claims...")
    db_user = database.get_user_by_id(user_id)
    assert db_user is not None
    assert db_user["points"] == 15, f"Expected 15 points in SQLite, got {db_user['points']}"
    print(f"  Verified SQLite user table: ID={db_user['id']}, Points={db_user['points']}")
    print("  -> Passed TEST 6 (Points persisted cleanly in SQLite).")

    # -------------------------------------------------------------
    # TEST 7: Open user endpoint GET /api/user/<user_id>
    # -------------------------------------------------------------
    print(f"\n[TEST 7] Testing GET /api/user/{user_id} endpoint...")
    get_u = client.get(f"/api/user/{user_id}")
    assert get_u.status_code == 200
    u_json = get_u.get_json()
    print("  GET /api/user response:", u_json)
    assert u_json["id"] == user_id
    assert u_json["name"] == "Kushagra"
    assert u_json["email"] == unique_email
    assert u_json["points"] == 15
    print("  -> Passed TEST 7 (User profile endpoint returns correct total points).")

    # -------------------------------------------------------------
    # TEST 8: Open reward history endpoint GET /api/user/<user_id>/rewards
    # -------------------------------------------------------------
    print(f"\n[TEST 8] Testing GET /api/user/{user_id}/rewards endpoint...")
    hist_res = client.get(f"/api/user/{user_id}/rewards")
    assert hist_res.status_code == 200
    hist = hist_res.get_json()
    print(f"  Retrieved {len(hist)} claimed reward records for User #{user_id}:")
    for r in hist:
        print(f"    - {r['reward_id']} | Category: {r['category']} | Points: +{r['points']} | Status: {r['status']}")

    assert len(hist) == 3, f"Expected 3 claimed rewards, got {len(hist)}"
    categories = [r["category"] for r in hist]
    assert "Plastic" in categories
    assert "Metal" in categories
    assert "Organic" in categories
    print("  -> Passed TEST 8 (Claimed rewards history verified).")

    print("\nALL STAGE 5 TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_stage5()
