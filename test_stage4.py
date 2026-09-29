"""
Automated test suite for EcoNova Stage 4: Reward + QR Code System.
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))

import database
import reward
from app import app


def test_stage4():
    print("========================================")
    print("Testing EcoNova Stage 4 (Reward + QR)")
    print("========================================")

    client = app.test_client()

    # -------------------------------------------------------------
    # TEST 1: Create Plastic waste record -> 5 points -> ECO-XXXXXX -> QR generated
    # -------------------------------------------------------------
    print("\n[TEST 1] Testing Plastic disposal and reward generation...")
    # Step 1a: Save waste record
    p_rec = database.save_waste_record("Plastic", 0.94)
    waste_id_plastic = p_rec["id"]
    print(f"  Created Plastic waste record #{waste_id_plastic}")

    # Step 1b: Call /api/reward/create
    rew_res = client.post("/api/reward/create", json={"waste_id": waste_id_plastic})
    assert rew_res.status_code == 200, f"Expected 200, got {rew_res.status_code}"
    rew_data = rew_res.get_json()
    print("  Reward creation response:", rew_data)

    assert rew_data["success"] is True
    assert rew_data["points"] == 5, f"Expected 5 points for Plastic, got {rew_data['points']}"
    assert rew_data["status"] == "UNCLAIMED"
    reward_id = rew_data["reward_id"]
    assert reward_id.startswith("ECO-"), f"Reward ID {reward_id} should start with ECO-"
    assert len(reward_id) == 10, f"Reward ID {reward_id} expected length 10 (ECO-XXXXXX)"

    # Step 1c: Verify QR code PNG file exists in rewards/
    qr_filename = f"{reward_id}.png"
    qr_filepath = os.path.join(reward.REWARDS_DIR, qr_filename)
    assert os.path.exists(qr_filepath), f"QR code file not found at {qr_filepath}"
    assert os.path.getsize(qr_filepath) > 100, "QR code image file is empty or too small"
    print(f"  Verified QR code generated at {qr_filepath} ({os.path.getsize(qr_filepath)} bytes)")

    # Step 1d: Test GET /rewards/<filename>
    qr_img_res = client.get(f"/rewards/{qr_filename}")
    assert qr_img_res.status_code == 200
    assert qr_img_res.mimetype == "image/png"
    print("  -> Passed TEST 1 (Plastic -> 5 points -> ECO-XXXXXX -> QR generated).")

    # -------------------------------------------------------------
    # TEST 2: Open QR/redeem URL -> Reward page appears
    # -------------------------------------------------------------
    print(f"\n[TEST 2] Testing redemption page at /redeem/{reward_id}...")
    page_res = client.get(f"/redeem/{reward_id}")
    assert page_res.status_code == 200
    html = page_res.get_data(as_text=True)
    assert "EcoNova Reward" in html
    assert "CLAIM REWARD" in html
    print("  -> Passed TEST 2 (Redemption page loads with HTTP 200).")

    # Also test GET /api/reward/<reward_id>
    get_res = client.get(f"/api/reward/{reward_id}")
    assert get_res.status_code == 200
    get_data = get_res.get_json()
    assert get_data["reward_id"] == reward_id
    assert get_data["points"] == 5
    assert get_data["status"] == "UNCLAIMED"
    assert get_data["category"] == "Plastic"
    print("  Verified GET /api/reward/<id> returns valid details.")

    # -------------------------------------------------------------
    # TEST 3: Claim reward -> UNCLAIMED -> CLAIMED
    # -------------------------------------------------------------
    print(f"\n[TEST 3] Testing reward claiming for {reward_id}...")
    claim_res = client.post(f"/api/reward/{reward_id}/claim")
    assert claim_res.status_code == 200
    claim_data = claim_res.get_json()
    print("  Claim response:", claim_data)
    assert claim_data["success"] is True
    assert claim_data["status"] == "CLAIMED"

    # Verify status in database
    db_reward = reward.get_reward_by_id(reward_id)
    assert db_reward["status"] == "CLAIMED"
    assert db_reward["claimed_at"] is not None
    print(f"  Verified SQLite status updated to CLAIMED at {db_reward['claimed_at']}.")
    print("  -> Passed TEST 3 (Reward claimed successfully).")

    # -------------------------------------------------------------
    # TEST 4: Claim same reward again -> "Reward already claimed."
    # -------------------------------------------------------------
    print(f"\n[TEST 4] Testing double-claim prevention for {reward_id}...")
    second_claim = client.post(f"/api/reward/{reward_id}/claim")
    assert second_claim.status_code == 400
    second_data = second_claim.get_json()
    print("  Second claim rejection response:", second_data)
    assert second_data["success"] is False
    assert "Reward already claimed" in second_data["message"]
    print("  -> Passed TEST 4 (Double-claiming safely prevented).")

    # -------------------------------------------------------------
    # TEST 5: Create Organic disposal -> 3 points
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Organic disposal and reward (3 points)...")
    o_rec = database.save_waste_record("Organic", 0.91)
    o_rew_res = client.post("/api/reward/create", json={"waste_id": o_rec["id"]})
    assert o_rew_res.status_code == 200
    o_rew_data = o_rew_res.get_json()
    print("  Organic reward response:", o_rew_data)
    assert o_rew_data["points"] == 3, f"Expected 3 points for Organic, got {o_rew_data['points']}"
    assert o_rew_data["status"] == "UNCLAIMED"
    assert os.path.exists(os.path.join(reward.REWARDS_DIR, f"{o_rew_data['reward_id']}.png"))
    print("  -> Passed TEST 5 (Organic -> 3 points).")

    # -------------------------------------------------------------
    # TEST 6: Create Metal disposal -> 7 points
    # -------------------------------------------------------------
    print("\n[TEST 6] Testing Metal disposal and reward (7 points)...")
    m_rec = database.save_waste_record("Metal", 0.96)
    m_rew_res = client.post("/api/reward/create", json={"waste_id": m_rec["id"]})
    assert m_rew_res.status_code == 200
    m_rew_data = m_rew_res.get_json()
    print("  Metal reward response:", m_rew_data)
    assert m_rew_data["points"] == 7, f"Expected 7 points for Metal, got {m_rew_data['points']}"
    assert m_rew_data["status"] == "UNCLAIMED"
    assert os.path.exists(os.path.join(reward.REWARDS_DIR, f"{m_rew_data['reward_id']}.png"))
    print("  -> Passed TEST 6 (Metal -> 7 points).")

    # -------------------------------------------------------------
    # TEST 7: Error handling for invalid waste IDs and 404 lookups
    # -------------------------------------------------------------
    print("\n[TEST 7] Testing error handling (invalid IDs and missing rewards)...")
    invalid_create = client.post("/api/reward/create", json={"waste_id": 999999})
    assert invalid_create.status_code == 404
    print("  Missing waste_id rejection OK (404)")

    not_found_get = client.get("/api/reward/ECO-FAKE99")
    assert not_found_get.status_code == 404
    print("  Unknown reward ID lookup OK (404)")

    print("\nALL STAGE 4 TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_stage4()
