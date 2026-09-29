"""
Automated test suite for EcoNova Stage 3: Flask + SQLite Integration.
"""

import sys
import os
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ai"))

import database
from app import app


def test_stage3():
    print("========================================")
    print("Testing EcoNova Stage 3 (Flask + SQLite)")
    print("========================================")

    print("[TEST 1] Testing database initialization...")
    database.init_db()
    assert os.path.exists(database.DB_PATH), f"Database file not created at {database.DB_PATH}"

    # Verify tables exist
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    print("  Created tables:", tables)
    assert "users" in tables, "users table missing"
    assert "waste_records" in tables, "waste_records table missing"
    assert "rewards" in tables, "rewards table missing"
    print("  -> Passed table verification test.")

    print("\n[TEST 2] Testing direct database operations...")
    rec = database.save_waste_record("Plastic", 0.94)
    print("  Inserted waste record:", rec)
    assert rec["id"] is not None
    assert rec["category"] == "Plastic"
    assert abs(rec["confidence"] - 0.94) < 1e-4

    stats = database.get_waste_statistics()
    print("  Waste stats:", stats)
    assert stats["Plastic"] >= 1
    assert stats["total"] >= 1
    print("  -> Passed direct database insertion test.")

    print("\n[TEST 3] Testing Flask POST /api/sort endpoint...")
    client = app.test_client()

    # 1. Sort Plastic (94%)
    sort_res = client.post("/api/sort", json={"category": "Plastic", "confidence": 0.94})
    assert sort_res.status_code == 200
    sort_data = sort_res.get_json()
    print("  POST /api/sort response:", sort_data)
    assert sort_data["success"] is True
    assert sort_data["category"] == "Plastic"
    assert sort_data["points"] == 5
    assert sort_data["waste_id"] is not None
    assert "saved to sqlite" in sort_data["message"].lower()

    # 2. Sort Organic (91%)
    org_res = client.post("/api/sort", json={"category": "Organic", "confidence": 0.91})
    assert org_res.status_code == 200
    org_data = org_res.get_json()
    assert org_data["points"] == 3
    print("  POST /api/sort Organic: OK (points=3, waste_id={})".format(org_data["waste_id"]))

    # 3. Sort Metal (96%)
    met_res = client.post("/api/sort", json={"category": "Metal", "confidence": 0.96})
    assert met_res.status_code == 200
    met_data = met_res.get_json()
    assert met_data["points"] == 7
    print("  POST /api/sort Metal: OK (points=7, waste_id={})".format(met_data["waste_id"]))

    print("\n[TEST 4] Testing confidence gate on /api/sort (< 0.70 rejected)...")
    low_res = client.post("/api/sort", json={"category": "Plastic", "confidence": 0.58})
    assert low_res.status_code == 400
    low_data = low_res.get_json()
    print("  Low confidence rejection:", low_data)
    assert "Low confidence" in low_data["error"]
    print("  -> Passed confidence gate test.")

    print("\n[TEST 5] Testing GET /api/records endpoint...")
    rec_res = client.get("/api/records?limit=10")
    assert rec_res.status_code == 200
    rec_data = rec_res.get_json()
    print(f"  Retrieved {len(rec_data['records'])} records from SQLite.")
    print("  Latest record:", rec_data["records"][0])
    print("  Updated stats:", rec_data["stats"])
    assert len(rec_data["records"]) >= 3
    assert rec_data["stats"]["total"] >= 3
    print("  -> Passed GET /api/records test.")

    print("\nALL STAGE 3 TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_stage3()
