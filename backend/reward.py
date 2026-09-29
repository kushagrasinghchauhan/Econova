"""
backend/reward.py
-----------------
EcoNova Reward & QR Code Generator.

Flow:
    1. Waste Segregated (Stage 2/3)
    2. create_reward(waste_id)
    3. Generate unique secure ID: ECO-XXXXXX
    4. Generate QR code pointing to {BASE_URL}/redeem/{reward_id}
    5. Save QR image in rewards/{reward_id}.png
    6. Store in SQLite with status UNCLAIMED
    7. Claim reward: UNCLAIMED -> CLAIMED
"""

import os
import sys
import socket
import secrets
import qrcode
from datetime import datetime

# Path resolution
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
REWARDS_DIR = os.path.join(PROJECT_ROOT, "rewards")

# Ensure rewards directory exists
os.makedirs(REWARDS_DIR, exist_ok=True)

# Add backend to path for database
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import database

# =====================================================================
# CONFIGURATION & LAN IP AUTO-DETECTION
# Automatically detects laptop LAN IPv4 (e.g. 192.168.1.5) so phones
# on the same Wi-Fi can scan the QR code and open /redeem/<reward_id>.
# =====================================================================
def get_lan_ip():
    """
    Automatically detects the primary LAN IPv4 address of the laptop.
    Falls back to '192.168.1.5' or '127.0.0.1' if detection fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass

    return "192.168.1.5"


def get_base_url():
    """
    Returns the base URL for QR codes.
    Checks PUBLIC_BASE_URL, RENDER_EXTERNAL_URL, or ECONOVA_BASE_URL env vars first,
    otherwise dynamically uses the laptop's detected LAN IPv4 address on port 5000 (e.g. https://192.168.1.5:5000).
    """
    env_url = (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("ECONOVA_BASE_URL")
    )
    if env_url:
        return env_url.rstrip("/")
    lan_ip = get_lan_ip()
    port = os.environ.get("PORT", "5000")
    scheme = os.environ.get("ECONOVA_SCHEME", "https")
    return f"{scheme}://{lan_ip}:{port}"


BASE_URL = get_base_url()

# Points mapping
POINTS_MAP = {
    "Organic": 3,
    "Plastic": 5,
    "Metal": 7,
    "Paper": 5
}


def generate_reward_id():
    """
    Generates a cryptographically random unique reward code: ECO-XXXXXX.
    Uses uppercase alphanumeric characters (excluding ambiguous O, 0, I, 1).
    """
    charset = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(charset) for _ in range(6))
    return f"ECO-{code}"


def generate_qr_image(reward_id, base_url=None):
    """
    Generates a high-contrast QR code pointing to {base_url}/reward/{reward_id}
    and saves it as a PNG file inside the rewards/ directory.
    Uses larger box size and crisp borders so it can be easily scanned from several feet away.
    Returns the absolute path to the generated QR code.
    """
    if base_url is None:
        base_url = get_base_url()

    # Claim URL using /reward/{reward_id} (or /redeem/{reward_id})
    redeem_url = f"{base_url.rstrip('/')}/reward/{reward_id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,  # Larger box size for high-resolution scannability from several feet away
        border=3,
    )
    qr.add_data(redeem_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0a0e17", back_color="#ffffff")

    filename = f"{reward_id}.png"
    filepath = os.path.join(REWARDS_DIR, filename)
    img.save(filepath)

    return filepath


def create_reward(waste_id):
    """
    Creates a new reward in the database for a segregated waste item.
    1. Looks up waste_record by waste_id.
    2. Calculates points from category.
    3. Generates unique reward ID and QR code.
    4. Inserts into SQLite rewards table with status UNCLAIMED.

    Returns dict with reward details, or raises ValueError on invalid waste_id.
    """
    conn = database.get_connection()
    cursor = conn.cursor()

    # 1. Look up waste record
    cursor.execute("SELECT * FROM waste_records WHERE id = ?;", (waste_id,))
    waste_record = cursor.fetchone()

    if not waste_record:
        conn.close()
        raise ValueError(f"Waste record #{waste_id} does not exist.")

    category = waste_record["category"]
    points = POINTS_MAP.get(category, 5)

    # 2. Check if a reward already exists for this waste record
    cursor.execute("SELECT * FROM rewards WHERE waste_id = ?;", (waste_id,))
    existing_reward = cursor.fetchone()
    if existing_reward:
        conn.close()
        reward_id = existing_reward["reward_id"] if "reward_id" in existing_reward.keys() and existing_reward["reward_id"] else existing_reward["id"]
        # Ensure QR exists
        generate_qr_image(reward_id)
        return {
            "success": True,
            "reward_id": reward_id,
            "points": existing_reward["points"],
            "status": existing_reward["status"],
            "qr_url": f"/redeem/{reward_id}",
            "qr_image_url": f"/rewards/{reward_id}.png",
            "category": category,
            "waste_id": waste_id,
            "already_existed": True
        }

    # 3. Generate unique reward ID (verify not in DB)
    while True:
        reward_id = generate_reward_id()
        cursor.execute("SELECT id FROM rewards WHERE id = ? OR (reward_id IS NOT NULL AND reward_id = ?);", (reward_id, reward_id))
        if not cursor.fetchone():
            break

    # 4. Generate QR code image
    generate_qr_image(reward_id)

    # 5. Insert into rewards table
    created_at = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO rewards (id, reward_id, waste_id, points, status, created_at)
        VALUES (?, ?, ?, ?, 'UNCLAIMED', ?);
    """, (reward_id, reward_id, waste_id, points, created_at))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "reward_id": reward_id,
        "points": points,
        "status": "UNCLAIMED",
        "qr_url": f"/redeem/{reward_id}",
        "qr_image_url": f"/rewards/{reward_id}.png",
        "category": category,
        "waste_id": waste_id,
        "created_at": created_at
    }


def get_reward_by_id(reward_id):
    """
    Fetches reward details from SQLite joined with waste_records to get category.
    Returns dict or None.
    """
    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.*, w.category, w.confidence
        FROM rewards r
        LEFT JOIN waste_records w ON r.waste_id = w.id
        WHERE r.id = ? OR r.reward_id = ?;
    """, (reward_id, reward_id))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    r_dict = dict(row)
    # Normalize reward_id field
    r_dict["reward_id"] = r_dict.get("reward_id") or r_dict["id"]
    r_dict["qr_image_url"] = f"/rewards/{r_dict['reward_id']}.png"
    r_dict["qr_url"] = f"/redeem/{r_dict['reward_id']}"
    return r_dict


def claim_reward(reward_id):
    """
    Claims a reward (UNCLAIMED -> CLAIMED).
    Prevents double-claiming.
    Returns (success: bool, message: str, reward_dict: dict or None).
    """
    reward = get_reward_by_id(reward_id)
    if not reward:
        return False, "Reward not found.", None

    if reward["status"] == "CLAIMED":
        return False, "Reward already claimed.", reward

    conn = database.get_connection()
    cursor = conn.cursor()

    claimed_at = datetime.now().isoformat()
    cursor.execute("""
        UPDATE rewards
        SET status = 'CLAIMED', claimed_at = ?
        WHERE id = ? OR reward_id = ?;
    """, (claimed_at, reward_id, reward_id))

    conn.commit()
    conn.close()

    reward["status"] = "CLAIMED"
    reward["claimed_at"] = claimed_at
    return True, "Reward claimed successfully!", reward
