"""
backend/database.py
-------------------
SQLite database manager for EcoNova.

Tables:
    - users (id, name, email, points, created_at)
    - waste_records (id, category, confidence, created_at)
    - rewards (id, waste_id, points, status, user_id, created_at, claimed_at)
"""

import os
import sqlite3
from datetime import datetime

# Path to SQLite database file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
DB_DIR = os.path.join(PROJECT_ROOT, "database")
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(DB_DIR, "econova.db"))


def get_connection():
    """
    Returns a connection to the SQLite database.
    Ensures the parent directory exists.
    """
    db_parent = os.path.dirname(os.path.abspath(DB_PATH))
    if db_parent and not os.path.exists(db_parent):
        os.makedirs(db_parent, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """
    Initializes database tables if they don't already exist.
    Safe to call multiple times.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. waste_records table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS waste_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. rewards table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id TEXT PRIMARY KEY,
            reward_id TEXT,
            waste_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            status TEXT DEFAULT 'UNCLAIMED',
            user_id INTEGER NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            claimed_at TIMESTAMP NULL,
            FOREIGN KEY (waste_id) REFERENCES waste_records (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)

    # Migration check: ensure reward_id column exists if table was created earlier
    cursor.execute("PRAGMA table_info(rewards);")
    columns = [col[1] for col in cursor.fetchall()]
    if "reward_id" not in columns:
        try:
            cursor.execute("ALTER TABLE rewards ADD COLUMN reward_id TEXT;")
        except Exception:
            pass

    # Migration check: ensure hardware_destination column exists in waste_records
    cursor.execute("PRAGMA table_info(waste_records);")
    waste_cols = [col[1] for col in cursor.fetchall()]
    if "hardware_destination" not in waste_cols:
        try:
            cursor.execute("ALTER TABLE waste_records ADD COLUMN hardware_destination TEXT DEFAULT NULL;")
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"[Database] SQLite database initialized at {DB_PATH}")


def save_waste_record(category, confidence, hardware_destination=None):
    """
    Saves a newly segregated waste item to the database.
    Returns the newly created record dictionary.
    """
    if hardware_destination is None:
        if category in ("Plastic", "Paper"):
            hardware_destination = "Dry/Plastic"
        elif category == "Organic":
            hardware_destination = "Organic"
        elif category == "Metal":
            hardware_destination = "Metal"
        else:
            hardware_destination = category

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO waste_records (category, confidence, hardware_destination, created_at)
        VALUES (?, ?, ?, ?);
    """, (category, float(confidence), hardware_destination, datetime.now().isoformat()))

    waste_id = cursor.lastrowid
    conn.commit()

    # Fetch inserted record
    cursor.execute("SELECT * FROM waste_records WHERE id = ?;", (waste_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else {"id": waste_id, "category": category, "confidence": confidence, "hardware_destination": hardware_destination}


def get_waste_records(limit=50):
    """Fetches the most recent waste records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM waste_records
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_waste_statistics():
    """
    Returns aggregated counts for Organic, Plastic, Metal, and Total.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM waste_records
        GROUP BY category;
    """)
    rows = cursor.fetchall()

    counts = {"Organic": 0, "Plastic": 0, "Metal": 0, "Paper": 0, "total": 0}
    total = 0
    for r in rows:
        cat = r["category"]
        cnt = r["count"]
        if cat in counts:
            counts[cat] = cnt
        total += cnt

    counts["total"] = total
    conn.close()
    return counts


# =====================================================================
# STAGE 5: USER ACCOUNTS & ATOMIC REWARD CLAIMING
# =====================================================================

def get_or_create_user(name, email):
    """
    Finds a user by email, or creates a new user with points=0.
    Returns user dict: {id, name, email, points, created_at}.
    """
    email_clean = email.strip().lower()
    name_clean = name.strip()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?;", (email_clean,))
    row = cursor.fetchone()

    if row:
        user_dict = dict(row)
        conn.close()
        return user_dict

    created_at = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO users (name, email, points, created_at)
        VALUES (?, ?, 0, ?);
    """, (name_clean, email_clean, created_at))
    user_id = cursor.lastrowid
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    new_user = dict(cursor.fetchone())
    conn.close()
    print(f"[Database] Registered new user #{user_id}: {name_clean} ({email_clean})")
    return new_user


def get_user_by_email(email):
    """Fetches user dict by email (case-insensitive), or None if not found."""
    if not email:
        return None
    email_clean = email.strip().lower()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?;", (email_clean,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Fetches user dict by ID, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_claimed_rewards(user_id):
    """Returns list of claimed rewards for the specified user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.reward_id, w.category, r.points, r.status, r.claimed_at
        FROM rewards r
        LEFT JOIN waste_records w ON r.waste_id = w.id
        WHERE r.user_id = ? AND r.status = 'CLAIMED'
        ORDER BY r.claimed_at DESC;
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def claim_reward_for_user(reward_id, user_id):
    """
    Atomically claims a reward for a user:
    1. Validates reward is UNCLAIMED.
    2. Validates user exists.
    3. Atomically sets status to CLAIMED and assigns user_id.
    4. Increments user's points in SQLite.
    Returns (success: bool, message: str, data: dict or None).
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE;")

        # Find reward
        cursor.execute("""
            SELECT * FROM rewards
            WHERE id = ? OR (reward_id IS NOT NULL AND reward_id = ?);
        """, (reward_id, reward_id))
        rew_row = cursor.fetchone()

        if not rew_row:
            conn.rollback()
            conn.close()
            return False, "Reward not found.", None

        reward_dict = dict(rew_row)
        if reward_dict["status"] == "CLAIMED":
            conn.rollback()
            conn.close()
            return False, "Reward already claimed.", None

        # Find user
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            conn.rollback()
            conn.close()
            return False, "User not found.", None

        claimed_at = datetime.now().isoformat()
        points_to_add = reward_dict["points"]

        # Atomically update reward status only if still UNCLAIMED
        cursor.execute("""
            UPDATE rewards
            SET status = 'CLAIMED', user_id = ?, claimed_at = ?
            WHERE (id = ? OR reward_id = ?) AND status = 'UNCLAIMED';
        """, (user_id, claimed_at, reward_id, reward_id))

        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            return False, "Reward already claimed.", None

        # Increment user points
        cursor.execute("""
            UPDATE users
            SET points = points + ?
            WHERE id = ?;
        """, (points_to_add, user_id))

        # Commit transaction
        conn.commit()

        # Fetch updated user
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        updated_user = dict(cursor.fetchone())
        conn.close()

        print(f"[Database] Reward {reward_id} claimed by User #{user_id}. Points: +{points_to_add} (Total: {updated_user['points']})")

        return True, "Reward claimed successfully", {
            "reward_id": reward_dict.get("reward_id") or reward_dict["id"],
            "points_added": points_to_add,
            "total_points": updated_user["points"],
            "user": updated_user
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[Database] Error in claim_reward_for_user: {e}")
        return False, f"Database error: {str(e)}", None


def get_all_rewards_history(limit=50):
    """
    Returns system-wide reward history with waste category and user info.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.reward_id, w.category, r.points, r.status, r.created_at, r.claimed_at,
               u.name as user_name, u.email as user_email
        FROM rewards r
        LEFT JOIN waste_records w ON r.waste_id = w.id
        LEFT JOIN users u ON r.user_id = u.id
        ORDER BY r.rowid DESC
        LIMIT ?;
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dashboard_summary(user_id=None):
    """
    Aggregates stats for the dashboard:
    - total waste items segregated
    - category breakdown (Organic, Plastic, Metal)
    - user details and points (if user_id given)
    - relevant reward history
    """
    stats = get_waste_statistics()

    user = None
    user_rewards = []
    if user_id:
        user = get_user_by_id(user_id)
        if user:
            user_rewards = get_user_claimed_rewards(user_id)

    system_rewards = get_all_rewards_history(limit=25)

    history = user_rewards if user_rewards else system_rewards

    return {
        "items_recycled": stats["total"],
        "category_counts": {
            "Organic": stats["Organic"],
            "Plastic": stats["Plastic"],
            "Metal": stats["Metal"]
        },
        "user": user,
        "user_rewards": user_rewards,
        "recent_rewards": system_rewards,
        "rewards_history": history
    }


if __name__ == "__main__":
    init_db()
    test_rec = save_waste_record("Plastic", 0.94)
    print("Test Record Saved:", test_rec)
    print("Current Stats:", get_waste_statistics())
