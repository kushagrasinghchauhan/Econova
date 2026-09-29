"""
backend/app.py
--------------
Flask application for EcoNova.
Serves the web dashboard, virtual sorting interface, and AI detection endpoints.
"""

import os
import sys
import time
import base64
import numpy as np
import cv2
from flask import Flask, render_template, request, jsonify, send_from_directory

# Add ai/, hardware/, and backend/ to system path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
AI_DIR = os.path.join(PROJECT_ROOT, "ai")
HARDWARE_DIR = os.path.join(PROJECT_ROOT, "hardware")
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)
if HARDWARE_DIR not in sys.path:
    sys.path.insert(0, HARDWARE_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from detector import WasteDetector, CONFIDENCE_THRESHOLD, CLASS_NAMES
from esp32_controller import (
    ESP32Controller,
    SORTING_DELAY,
    G18_SETTLE_DELAY,
    G19_OPEN_TIME,
    G19_CLOSE_DELAY,
    G18_DEFAULT_ANGLE,
    G18_ORGANIC_ANGLE,
    G18_DRY_PLASTIC_ANGLE,
    G18_METAL_ANGLE,
    G19_RELEASE_CLOSED,
    G19_RELEASE_OPEN,
    G18_MOVE_DELAY_MS,
    G19_OPEN_DELAY_MS,
    G19_CLOSE_DELAY_MS,
    G19_UPDATE_INTERVAL_MS,
    G19_OPEN_DURATION_MS,
    G19_CLOSE_DURATION_MS,
    SORTER_SETTLE_DELAY,
    UPPER_FLAP_OPEN_TIME,
    POST_RELEASE_DELAY,
    SERVO2_RETURN_DELAY,
    SERVO1_HOME,
    SERVO1_OPEN,
    SERVO2_HOME,
    SERVO2_ORGANIC,
    SERVO2_DRY_PLASTIC,
    SERVO2_METAL
)
import database
import reward

# Initialize SQLite database schema
database.init_db()

# Directory paths
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
REWARDS_DIR = os.path.join(PROJECT_ROOT, "rewards")
os.makedirs(REWARDS_DIR, exist_ok=True)
app = Flask(__name__,
            static_folder=FRONTEND_DIR,
            static_url_path="/static",
            template_folder=FRONTEND_DIR)

# Initialize authoritative EcoNova 3-class detector
detector = WasteDetector()
det_status = detector.get_status()
if not det_status.get("ready"):
    print(f"[Detector] FATAL ERROR: EcoNova 3-class model could not be loaded from {detector.model_path}!")
    print(f"[Detector] Status: {det_status}")
    raise RuntimeError(f"Failed to load required EcoNova 3-class model from {detector.model_path}")

# Initialize ESP32 hardware controller (default COM6)
DEFAULT_PORT = os.environ.get("ESP32_PORT", "COM6")
esp32_controller = ESP32Controller(port=DEFAULT_PORT, baudrate=115200)
try:
    esp32_controller.connect()
except Exception:
    print(f"[ESP32] Hardware unavailable on {DEFAULT_PORT} - running in software-only mode")

# Category point values
POINTS_MAP = {
    "Organic": 3,
    "Plastic": 5,
    "Metal": 7,
    "Paper": 5
}

# Physical Compartment Routing (Only 3 physical compartments exist)
HARDWARE_COMMANDS = {
    "Organic": "ORGANIC",
    "Plastic": "PLASTIC",
    "Paper": "PLASTIC",
    "Metal": "METAL"
}

HARDWARE_DESTINATIONS = {
    "Organic": "Organic",
    "Plastic": "Dry/Plastic",
    "Paper": "Dry/Plastic",
    "Metal": "Metal"
}


@app.route("/")
def index():
    """Serves the main EcoNova web app, prototype camera, or phone home."""
    mode = request.args.get("mode")
    if mode == "prototype":
        return send_from_directory(FRONTEND_DIR, "prototype.html")
    elif mode == "phone":
        return send_from_directory(FRONTEND_DIR, "phone.html")
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/prototype")
def prototype_camera_page():
    """Serves the dedicated EcoNova Prototype Camera interface (Phone 1)."""
    return send_from_directory(FRONTEND_DIR, "prototype.html")


@app.route("/phone")
def phone_home():
    """Serves the dedicated EcoNova user phone home page (Phone 2)."""
    return send_from_directory(FRONTEND_DIR, "phone.html")


@app.route("/<path:path>")
def static_files(path):
    """Serves CSS, JS, and asset files from the frontend directory."""
    return send_from_directory(FRONTEND_DIR, path)


# Cooldown tracker to prevent duplicate concurrent sorts
_last_sort_time = 0
_last_sort_category = None
SORT_COOLDOWN_SECONDS = 2.0

# =====================================================================
# KIOSK SYNCHRONIZATION STATE (PHONE SCANNER -> LAPTOP DISPLAY)
# =====================================================================
_kiosk_state = {
    "status": "idle",       # "idle", "scanning", "detected", "sorting", "reward", "claimed"
    "category": None,
    "raw_class": None,
    "hardware_destination": None,
    "hardware_command": None,
    "confidence": 0.0,
    "confidence_pct": 0.0,
    "bbox": None,
    "points": 0,
    "reward_id": None,
    "qr_url": None,
    "qr_image_url": None,
    "waste_id": None,
    "claimed": False,
    "claimed_by_name": None,
    "updated_at": time.time(),
    "expires_in": 120       # Seconds before reward screen returns to idle
}


def reset_kiosk_state():
    global _kiosk_state
    _kiosk_state = {
        "status": "idle",
        "category": None,
        "raw_class": None,
        "hardware_destination": None,
        "hardware_command": None,
        "confidence": 0.0,
        "confidence_pct": 0.0,
        "bbox": None,
        "points": 0,
        "reward_id": None,
        "qr_url": None,
        "qr_image_url": None,
        "waste_id": None,
        "claimed": False,
        "claimed_by_name": None,
        "updated_at": time.time(),
        "expires_in": 120
    }
    return _kiosk_state


@app.route("/api/kiosk/state", methods=["GET"])
def get_kiosk_state():
    """
    Returns the real-time kiosk session state for Laptop / Kiosk display synchronization.
    Automatically handles state transitions:
      - claimed -> idle (after 4.0 seconds)
      - reward -> idle (after expiration timer)
      - detected/scanning -> idle (if inactive for 5.0 seconds)
    """
    global _kiosk_state
    now = time.time()

    # Automatic transition: claimed -> idle after 4 seconds of showing claim success
    if _kiosk_state["status"] == "claimed":
        if now - _kiosk_state["updated_at"] > 4.0:
            reset_kiosk_state()
    # Automatic transition: reward -> idle after expiration
    elif _kiosk_state["status"] == "reward":
        if now - _kiosk_state["updated_at"] > _kiosk_state.get("expires_in", 120):
            reset_kiosk_state()
    # Inactivity decay: detected/scanning -> idle if no frames for 5 seconds
    elif _kiosk_state["status"] in ("detected", "scanning"):
        if now - _kiosk_state["updated_at"] > 5.0:
            _kiosk_state["status"] = "idle"
            _kiosk_state["category"] = None

    time_left = max(0, int(_kiosk_state.get("expires_in", 120) - (now - _kiosk_state["updated_at"])))
    state_copy = dict(_kiosk_state)
    state_copy["time_left"] = time_left
    return jsonify(state_copy)


@app.route("/api/kiosk/reset", methods=["POST"])
def reset_kiosk_state_api():
    """
    Resets the kiosk state to idle.
    """
    st = reset_kiosk_state()
    return jsonify({"success": True, "state": st})


@app.route("/api/detector/status", methods=["GET"])
def detector_status():
    """Returns AI model inspection status and hardware status."""
    is_conn = esp32_controller.is_connected
    return jsonify({
        "status": detector.get_status(),
        "threshold": CONFIDENCE_THRESHOLD,
        "classes": CLASS_NAMES,
        "points_map": POINTS_MAP,
        "hardware": {
            "connected": is_conn,
            "port": esp32_controller.port,
            "mode": "ESP32" if is_conn else "SOFTWARE_ONLY"
        }
    })


@app.route("/api/hardware/status", methods=["GET"])
def hardware_status():
    """
    Returns the real ESP32 hardware connection status, servo roles, and timing configuration.
    """
    is_conn = esp32_controller.is_connected
    return jsonify({
        "connected": is_conn,
        "port": esp32_controller.port,
        "mode": "ESP32" if is_conn else "SOFTWARE_ONLY",
        "servos": {
            "g18": {
                "pin": 18,
                "role": "DESTINATION_SELECTOR",
                "description": "Moves to compartment destination angle FIRST before G19 opens",
                "default_angle": G18_DEFAULT_ANGLE,
                "organic_angle": G18_ORGANIC_ANGLE,
                "dry_plastic_angle": G18_DRY_PLASTIC_ANGLE,
                "metal_angle": G18_METAL_ANGLE
            },
            "g19": {
                "pin": 19,
                "role": "WASTE_RELEASE_FLAP",
                "description": "Holds waste (0°); opens to release waste (180°) only after G18 settles; closes to 0°",
                "closed_angle": G19_RELEASE_CLOSED,
                "open_angle": G19_RELEASE_OPEN
            },
            "servo1": {
                "pin": 18,
                "role": "DESTINATION_SELECTOR",
                "home_angle": G18_DEFAULT_ANGLE,
                "open_angle": G18_DRY_PLASTIC_ANGLE
            },
            "servo2": {
                "pin": 19,
                "role": "WASTE_RELEASE_FLAP",
                "home_angle": G19_RELEASE_CLOSED,
                "organic_angle": G18_ORGANIC_ANGLE,
                "dry_plastic_angle": G18_DRY_PLASTIC_ANGLE,
                "metal_angle": G18_METAL_ANGLE
            }
        },
        "timing": {
            "g18_settle_delay": G18_SETTLE_DELAY,
            "g19_open_time": G19_OPEN_TIME,
            "g19_close_delay": G19_CLOSE_DELAY,
            "total_sorting_delay": SORTING_DELAY,
            "sorter_settle_delay": G18_SETTLE_DELAY,
            "upper_flap_open_time": G19_OPEN_TIME,
            "post_release_delay": G19_CLOSE_DELAY
        },
        "speed": {
            "g18_move_delay_ms": G18_MOVE_DELAY_MS,
            "g19_open_delay_ms": G19_OPEN_DELAY_MS,
            "g19_close_delay_ms": G19_CLOSE_DELAY_MS,
            "g19_open_duration_ms": G19_OPEN_DURATION_MS,
            "g19_close_duration_ms": G19_CLOSE_DURATION_MS,
            "g19_update_interval_ms": G19_UPDATE_INTERVAL_MS,
            "g19_motion_profile": "S_CURVE_COSINE_EASE"
        }
    })


@app.route("/api/detect", methods=["POST"])
def detect_waste():
    """
    Receives an image frame from the browser webcam (base64 encoded JPEG/PNG),
    checks YOLO model status, and runs real YOLO inference.
    """
    # 1. Check if model is missing or incompatible (unless developer override active)
    status_info = detector.get_status()
    dev_override_active = status_info.get("developer_override", False)

    if not dev_override_active:
        if status_info["model_status"] == "YOLO_MODEL_MISSING":
            return jsonify({
                "success": False,
                "error": "YOLO_MODEL_MISSING",
                "message": f"Real YOLO model weights not found at {detector.model_path}. Drop your trained best.pt file to enable live AI waste detection."
            }), 200
        elif status_info["model_status"] == "INCOMPATIBLE_CLASSES":
            return jsonify({
                "success": False,
                "error": "INCOMPATIBLE_CLASSES",
                "message": f"Model classes do not match required classes: {CLASS_NAMES}."
            }), 200

    # 2. Check if kiosk session is currently locked (active sorting or showing reward QR)
    if _kiosk_state["status"] in ("sorting", "reward", "claimed"):
        return jsonify({
            "success": True,
            "detected": False,
            "session_locked": True,
            "status": _kiosk_state["status"],
            "message": f"Session locked ({_kiosk_state['status']}). Awaiting reward claim or reset before scanning next item."
        })

    # 3. Decode incoming frame
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image")
    source = data.get("source", "prototype")
    payload_len = len(image_b64) if image_b64 else 0
    print(f"\n[API/detect] >>> POST /api/detect received | source={source} | payload length={payload_len} chars")
    print(f"[Prototype Camera] Frame received", flush=True)

    frame = None
    if image_b64:
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]
            image_bytes = base64.b64decode(image_b64)
            print(f"[API/detect] Decoded base64 bytes: length={len(image_bytes)} bytes")
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                print(f"[API/detect] Frame successfully decoded: shape={frame.shape}, dtype={frame.dtype}")
            else:
                print(f"[API/detect] ERROR: cv2.imdecode returned None! (invalid image buffer)")
        except Exception as e:
            print(f"[API/detect] ERROR decoding frame: {e}")
            frame = None
    else:
        print(f"[API/detect] No image payload provided in request")

    # 4. Model diagnostic (Requirement 15)
    model_name = getattr(detector, "model_path", None)
    model_filename = model_name.name if model_name else "yolo_3class_best.pt"
    print(f"[API/detect] Model: {model_filename}")
    print(f"[API/detect] Classes: {', '.join(CLASS_NAMES)}")

    # 5. Run real inference via EcoNova 3-class WasteDetector
    result = detector.detect(frame)

    if result is None:
        rejection = getattr(detector, "last_rejection", None)
        if rejection and rejection.get("confidence", 0) > 0:
            print(f"[API/detect] EcoNova detector: detection rejected")
            print(f"  confidence={rejection['confidence']:.2f} threshold={rejection['threshold']:.2f}")
        else:
            print(f"[API/detect] EcoNova detector: no accepted detection")

        if _kiosk_state["status"] == "detected" and (time.time() - _kiosk_state["updated_at"] > 4.0):
            _kiosk_state["status"] = "idle"
            _kiosk_state["category"] = None
        return jsonify({
            "success": True,
            "detected": False,
            "message": "No waste detected in frame"
        })

    # Accepted detection (confidence >= CONFIDENCE_THRESHOLD)
    print(f"[EcoNova Detector] {result.label} confidence={result.confidence:.2f} command={result.command}", flush=True)
    print(f"[API/detect] EcoNova detector result:\n  label={result.label} confidence={result.confidence:.2f} command={result.command}")
    print(f"[API/detect] EcoNova detection:\n  {result.label}\n  confidence={result.confidence:.2f}\n  command={result.command}")

    points = POINTS_MAP.get(result.label, 5)
    bbox_dict = None
    if getattr(result, "box", None):
        bbox_dict = {
            "x1": result.box[0],
            "y1": result.box[1],
            "x2": result.box[2],
            "y2": result.box[3]
        }

    hw_dest = HARDWARE_DESTINATIONS.get(result.label, "Dry/Plastic")
    hw_cmd = HARDWARE_COMMANDS.get(result.label, "PLASTIC")

    frame_h = frame.shape[0] if frame is not None else 480
    frame_w = frame.shape[1] if frame is not None else 640

    # Synchronize state for Laptop Kiosk display
    if _kiosk_state["status"] not in ("sorting", "reward"):
        _kiosk_state.update({
            "status": "detected",
            "category": result.label,
            "raw_class": result.label,
            "hardware_destination": hw_dest,
            "hardware_command": hw_cmd,
            "confidence": round(result.confidence, 4),
            "confidence_pct": round(result.confidence * 100, 2),
            "bbox": bbox_dict,
            "points": points,
            "updated_at": time.time()
        })

    return jsonify({
        "success": True,
        "detected": True,
        "category": result.label,
        "hardware_destination": hw_dest,
        "hardware_command": hw_cmd,
        "raw_class": result.label,
        "detector": getattr(detector, "detector_title", "EcoNova 3-Class Waste Detector"),
        "confidence": round(result.confidence, 4),
        "confidence_pct": round(result.confidence * 100, 2),
        "is_confident": True,
        "bbox": bbox_dict,
        "frame_size": {
            "width": frame_w,
            "height": frame_h
        },
        "command": result.command,
        "points": points,
        "threshold": CONFIDENCE_THRESHOLD,
        "message": "Ready for sorting"
    })


@app.route("/api/demo_override", methods=["POST"])
def demo_override():
    """
    Developer fallback endpoint: allows forcing a specific category for testing.
    """
    data = request.get_json(silent=True) or {}
    category = data.get("category")
    confidence = data.get("confidence", 0.94)

    if category in CLASS_NAMES:
        detector.set_manual_override(category, float(confidence))
    elif category == "LowConf":
        detector.set_manual_override("Plastic", 0.58)
    else:
        detector.set_manual_override(None)

    return jsonify({
        "success": True,
        "override": category
    })


@app.route("/api/sort", methods=["POST"])
def sort_waste():
    """
    Called when waste is segregated (manually or automatically via stable detection).
    Validates confidence >= 0.70, protects against rapid duplicate requests,
    saves the waste record to SQLite, and returns database confirmation.
    """
    global _last_sort_time, _last_sort_category
    import time

    data = request.get_json(silent=True) or {}
    category = data.get("category")
    confidence = float(data.get("confidence", 0.0))

    valid_sort_categories = set(CLASS_NAMES) | {"Paper"}
    if category not in valid_sort_categories:
        return jsonify({
            "success": False,
            "error": f"Invalid category '{category}'. Must be {', '.join(valid_sort_categories)}."
        }), 400

    if confidence < CONFIDENCE_THRESHOLD:
        return jsonify({
            "success": False,
            "error": "Low confidence - please reposition the waste."
        }), 400

    # Guard against concurrent sorting actuation
    if _kiosk_state["status"] == "sorting":
        return jsonify({
            "success": False,
            "session_locked": True,
            "error": "Sorting actuation already in progress. Please wait for completion."
        }), 429

    # Cooldown check: prevent duplicate simultaneous sorts for the same item
    now = time.time()
    if (now - _last_sort_time) < SORT_COOLDOWN_SECONDS and category == _last_sort_category:
        return jsonify({
            "success": False,
            "error": "Cooldown active. Please wait before sorting the next item."
        }), 429

    _last_sort_time = now
    _last_sort_category = category

    hw_cmd = HARDWARE_COMMANDS.get(category, "PLASTIC")
    hw_dest = HARDWARE_DESTINATIONS.get(category, "Dry/Plastic")

    # Update kiosk state to sorting animation on laptop display
    _kiosk_state.update({
        "status": "sorting",
        "category": category,
        "hardware_destination": hw_dest,
        "hardware_command": hw_cmd,
        "confidence": round(confidence, 4),
        "updated_at": time.time()
    })

    # Send command to ESP32 controller (Paper routes to PLASTIC)
    print(f"[Hardware] Sorting category: {category} -> physical destination: {hw_dest} (command: {hw_cmd})", flush=True)
    if esp32_controller.is_connected:
        try:
            cmd_ok = esp32_controller.sort(hw_cmd)
            if not cmd_ok:
                return jsonify({
                    "success": False,
                    "error": f"ESP32 rejected sorting command for category {category}."
                }), 500
            print(f"[Hardware] Sorting command accepted. Waiting for automatic sorting delay ({SORTING_DELAY}s)...", flush=True)
            esp32_controller.wait_for_sorting_delay(SORTING_DELAY)
            print(f"[Hardware] Sorting complete after {SORTING_DELAY}s delay.", flush=True)
        except Exception as e:
            print(f"[Hardware] ESP32 communication error: {e}", flush=True)
            return jsonify({
                "success": False,
                "error": f"ESP32 communication failure: {str(e)}"
            }), 500
    else:
        print(f"[Hardware] ESP32 unavailable — software-only sorting ({hw_cmd})", flush=True)
        esp32_controller.wait_for_sorting_delay(SORTING_DELAY)

    # 1. Save waste record to SQLite with hardware_destination ONLY AFTER ESP32 sorting & fixed sorting delay
    record = database.save_waste_record(category, confidence, hardware_destination=hw_dest)
    points = POINTS_MAP.get(category, 5)
    stats = database.get_waste_statistics()

    # 2. Automatically generate unique reward and QR code for segregation
    rew = reward.create_reward(record["id"])

    # 3. Synchronize Kiosk State for Laptop Screen: Transition to LARGE REWARD QR
    _kiosk_state.update({
        "status": "reward",
        "category": category,
        "hardware_destination": hw_dest,
        "hardware_command": hw_cmd,
        "confidence": record["confidence"],
        "points": points,
        "reward_id": rew["reward_id"],
        "qr_url": rew["qr_url"],
        "qr_image_url": rew["qr_image_url"],
        "waste_id": record["id"],
        "claimed": False,
        "claimed_by_name": None,
        "updated_at": time.time(),
        "expires_in": 120
    })

    print(f"[Database] Saved waste record #{record['id']}: {category} [Dest: {hw_dest}] ({confidence*100:.0f}%) -> +{points} points (Reward: {rew['reward_id']})", flush=True)

    return jsonify({
        "success": True,
        "waste_id": record["id"],
        "reward_id": rew["reward_id"],
        "qr_url": rew["qr_url"],
        "qr_image_url": rew["qr_image_url"],
        "category": record["category"],
        "hardware_destination": hw_dest,
        "hardware_command": hw_cmd,
        "confidence": record["confidence"],
        "points": points,
        "created_at": record["created_at"],
        "stats": stats,
        "message": f"Successfully segregated {category} into {hw_dest} bin and saved to SQLite!"
    })


@app.route("/api/records", methods=["GET"])
def list_records():
    """Returns recent waste segregation records from SQLite."""
    limit = request.args.get("limit", 20, type=int)
    records = database.get_waste_records(limit=limit)
    stats = database.get_waste_statistics()
    return jsonify({
        "records": records,
        "stats": stats
    })


# =====================================================================
# STAGE 4: REWARD & QR CODE API
# =====================================================================

@app.route("/rewards/<path:filename>")
def serve_qr_image(filename):
    """Serves generated QR code images from the rewards/ directory."""
    return send_from_directory(REWARDS_DIR, filename)


@app.route("/api/reward/create", methods=["POST"])
def create_reward_api():
    """
    Creates a unique reward and generates a QR code for a segregated waste record.
    Request JSON: { "waste_id": 1 }
    """
    data = request.get_json(silent=True) or {}
    waste_id = data.get("waste_id")

    if not waste_id:
        return jsonify({
            "success": False,
            "error": "Missing 'waste_id' in request body."
        }), 400

    try:
        waste_id_int = int(waste_id)
        result = reward.create_reward(waste_id_int)
        return jsonify(result)
    except ValueError as ve:
        return jsonify({
            "success": False,
            "error": str(ve)
        }), 404
    except Exception as e:
        print(f"[Reward API] Error creating reward: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to generate reward: {str(e)}"
        }), 500


@app.route("/api/reward/<reward_id>", methods=["GET"])
def get_reward_api(reward_id):
    """
    Returns reward details: ID, points, status, and category.
    Returns 404 if not found.
    """
    rew = reward.get_reward_by_id(reward_id)
    if not rew:
        return jsonify({
            "success": False,
            "error": "Reward not found."
        }), 404

    return jsonify({
        "success": True,
        "reward_id": rew["reward_id"],
        "points": rew["points"],
        "status": rew["status"],
        "category": rew.get("category", "Recycled Waste"),
        "confidence": rew.get("confidence", 0.84),
        "created_at": rew.get("created_at"),
        "claimed_at": rew.get("claimed_at"),
        "qr_url": rew["qr_url"],
        "qr_image_url": rew["qr_image_url"]
    })


# =====================================================================
# STAGE 5: USER ACCOUNTS & REWARD CLAIMING
# =====================================================================

@app.route("/api/user", methods=["POST"])
def register_or_get_user():
    """
    Creates a new user with 0 points if email doesn't exist,
    or returns the existing user.
    Request JSON: { "name": "Kushagra", "email": "kushagra@example.com" }
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()

    if not name or not email:
        return jsonify({
            "success": False,
            "error": "Both 'name' and 'email' are required."
        }), 400

    user = database.get_or_create_user(name, email)
    return jsonify({
        "success": True,
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "points": user["points"]
    })


@app.route("/api/user/login", methods=["POST"])
def login_user_api():
    """
    Authenticates/retrieves an existing user by email.
    Request JSON: { "email": "user@example.com" }
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()

    if not email:
        return jsonify({
            "success": False,
            "error": "Email address is required to sign in."
        }), 400

    user = database.get_user_by_email(email)
    if not user:
        return jsonify({
            "success": False,
            "error": f"No account found for '{email}'. Please sign up!"
        }), 404

    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "points": user["points"]
        }
    })


@app.route("/api/user/signup", methods=["POST"])
def signup_user_api():
    """
    Registers a new user or returns existing user.
    Request JSON: { "name": "...", "email": "..." }
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()

    if not name or not email:
        return jsonify({
            "success": False,
            "error": "Both name and email are required."
        }), 400

    user = database.get_or_create_user(name, email)
    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "points": user["points"]
        }
    })


@app.route("/api/user/<int:user_id>", methods=["GET"])
def get_user_api(user_id):
    """Returns user profile and total points."""
    user = database.get_user_by_id(user_id)
    if not user:
        return jsonify({
            "success": False,
            "error": "User not found."
        }), 404

    return jsonify({
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "points": user["points"]
    })


@app.route("/api/user/<int:user_id>/rewards", methods=["GET"])
def get_user_rewards_api(user_id):
    """Returns list of claimed rewards for the specified user."""
    user = database.get_user_by_id(user_id)
    if not user:
        return jsonify({
            "success": False,
            "error": "User not found."
        }), 404

    rewards_list = database.get_user_claimed_rewards(user_id)
    return jsonify(rewards_list)


@app.route("/api/reward/<reward_id>/claim", methods=["POST"])
def claim_reward_api(reward_id):
    """
    Claims a reward (UNCLAIMED -> CLAIMED) and assigns points to user.
    Request JSON: { "user_id": 1 } or { "name": "...", "email": "..." }
    """
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")

    # If name/email passed, auto-resolve or register user
    if not user_id and data.get("email"):
        name = data.get("name", "Eco User")
        user = database.get_or_create_user(name, data.get("email"))
        user_id = user["id"]
    elif not user_id:
        # Fallback for anonymous/guest claims (backward compatibility with Stage 4)
        guest = database.get_or_create_user("Guest User", "guest@econova.local")
        user_id = guest["id"]

    success, message, result = database.claim_reward_for_user(reward_id, user_id)
    if success:
        print(f"[Reward] Claimed: {reward_id}", flush=True)

    if not success:
        status_code = 404 if "not found" in message.lower() else 400
        return jsonify({
            "success": False,
            "message": message
        }), status_code

    # Synchronize Kiosk State: mark reward as claimed on laptop display
    if _kiosk_state.get("reward_id") == reward_id:
        _kiosk_state["status"] = "claimed"
        _kiosk_state["claimed"] = True
        _kiosk_state["claimed_by_name"] = name if data.get("email") else "User"
        _kiosk_state["updated_at"] = time.time()

    return jsonify({
        "success": True,
        "message": "Reward claimed successfully",
        "points_added": result["points_added"],
        "total_points": result["total_points"],
        "reward_id": result["reward_id"],
        "status": "CLAIMED",
        "user_id": user_id
    })


@app.route("/reward/<reward_id>")
def reward_claim_page(reward_id):
    """
    Serves the reward redemption page opened when scanning the QR code from the laptop screen.
    """
    return send_from_directory(FRONTEND_DIR, "redeem.html")


@app.route("/redeem/<reward_id>")
def redeem_page(reward_id):
    """
    Serves the reward redemption page opened when scanning the QR code.
    """
    return send_from_directory(FRONTEND_DIR, "redeem.html")


# =====================================================================
# STAGE 6: DASHBOARD ENDPOINTS
# =====================================================================

@app.route("/dashboard")
def dashboard_page():
    """
    Serves the EcoNova analytics dashboard.
    """
    return send_from_directory(FRONTEND_DIR, "dashboard.html")


@app.route("/history")
def history_page():
    """
    Serves the mobile contributions history page (Screen 9).
    """
    return send_from_directory(FRONTEND_DIR, "history.html")


@app.route("/api/dashboard/summary", methods=["GET"])
@app.route("/api/dashboard", methods=["GET"])
def dashboard_summary_api():
    """
    Returns aggregated items, category breakdown, user profile, and reward history.
    Query param: ?user_id=<int> (optional)
    """
    user_id = request.args.get("user_id", type=int)
    print("[Dashboard] User/session data loaded", flush=True)
    summary = database.get_dashboard_summary(user_id=user_id)
    return jsonify(summary)


@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats_api():
    """
    Returns raw aggregate counts of segregated items and points.
    """
    stats = database.get_waste_statistics()
    return jsonify({
        "success": True,
        "items_recycled": stats["total"],
        "category_counts": {
            "Organic": stats["Organic"],
            "Plastic": stats["Plastic"],
            "Metal": stats["Metal"]
        }
    })


# =====================================================================
# STAGE 7: PRODUCTION HEALTH CHECK (Render / Cloud Orchestrators)
# =====================================================================

@app.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint for Render, cloud reverse proxies, and monitoring agents.
    Does NOT require ESP32 hardware, camera access, or YOLO model inference.
    """
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    import argparse
    from reward import get_lan_ip, get_base_url

    default_port = int(os.environ.get("PORT", 5000))
    default_host = os.environ.get("HOST", "0.0.0.0")

    parser = argparse.ArgumentParser(description="EcoNova AI Server")
    parser.add_argument("--host", type=str, default=default_host, help="Server host (default: 0.0.0.0 or $HOST)")
    parser.add_argument("--port", type=int, default=default_port, help="Server port (default: 5000 or $PORT)")
    parser.add_argument("--no-ssl", action="store_true", help="Disable HTTPS (run plain HTTP)")
    args = parser.parse_args()

    port = int(os.environ.get("PORT", args.port))
    host = os.environ.get("HOST", args.host)

    is_render = "RENDER" in os.environ
    use_ssl = not (args.no_ssl or is_render or os.environ.get("FLASK_ENV") == "production" or os.environ.get("NO_SSL"))
    scheme = "https" if use_ssl else "http"
    ssl_ctx = "adhoc" if use_ssl else None

    lan_ip = get_lan_ip()
    base_url = get_base_url()

    print("=" * 65)
    print("        EcoNova - AI Smart Recycling Kiosk Server                  ")
    print("=" * 65)
    print(f"  * Host Binding:           {host}:{port}")
    print(f"  * Public Base URL:        {base_url}")
    print(f"  * Laptop / Kiosk Display: {scheme}://127.0.0.1:{port}/?mode=kiosk")
    print(f"  * Phone 1 Prototype Cam:  {scheme}://{lan_ip}:{port}/prototype")
    print(f"  * Phone 2 User Phone:     {scheme}://{lan_ip}:{port}/phone")
    if use_ssl:
        print("  * SSL Mode: Development Ad-Hoc HTTPS (Required for local phone camera)")
        print("  * Note: In phone browser, tap 'Advanced' -> 'Proceed' to trust self-signed cert.")
    else:
        print("  * SSL Mode: Plain HTTP (Render / Cloud reverse proxy terminates HTTPS)")
    print("=" * 65, flush=True)

    app.run(host=host, port=port, ssl_context=ssl_ctx, debug=False)

