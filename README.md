# EcoNova — AI-Powered Smart Waste Segregation & Reward System

[![Smart India Hackathon Prototype](https://img.shields.io/badge/SIH-Software%20Prototype%20v1.0-10b981.svg)](https://github.com/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Backend-Flask%20%2B%20SQLite3-0284c7.svg)](https://flask.palletsprojects.com/)
[![YOLOv8](https://img.shields.io/badge/AI-YOLOv8%20%7C%20OpenCV-f59e0b.svg)](https://ultralytics.com)

**EcoNova** is an automated waste classification and segregation software prototype built for the **Smart India Hackathon**.

The application identifies waste items via a webcam or uploaded image, classifies them with computer vision into **Organic**, **Plastic**, or **Metal**, visually simulates segregation into virtual bins with lid animations, persists transactions in an SQLite database, issues unique scannable **QR-code rewards**, and tracks recycling impact through an analytics dashboard.

---

## 🚀 Key Features

- **Real-Time AI Classification**: YOLO model detects waste categories (**Organic 🍏**, **Plastic 🧴**, **Metal 🥫**). Includes confidence gating ($\ge 70\%$ required for segregation; $< 70\%$ prompts repositioning).
- **Dual Input Modes**: Seamless support for live physical webcams, simulated fallback camera streams, or uploaded waste images.
- **3D Virtual Segregation Stage**: Animated chutes, dynamic trajectory tokens, responsive bin lids, and Web Audio sound effects simulating physical sorting bins.
- **Persistent SQLite Ledger**: Stores every segregated item, confidence score, timestamps, user profiles, and reward redemption statuses.
- **Automated QR Code Rewards**: Generates cryptographically unique vouchers (`ECO-XXXXXX`) with high-resolution QR codes pointing to mobile-friendly redemption URLs.
- **Atomic User Points Connection**: Scanned rewards can be claimed by entering Name + Email, incrementing user points atomically with strict double-claim protection.
- **Real-Time Analytics Dashboard**: Displays total eco points, items recycled, estimated $\text{CO}_2$ offset, category breakdown charts, and complete reward transaction history.
- **Hackathon Presentation Mode**: Built-in instant demo shortcuts (`P`, `O`, `M`, `L`, `C`, `Enter`) allowing smooth presentation even without external props or lighting setup.

---

## ♻️ Waste Categories & Reward Economics

| Category | Icon | Accepted Items | Eco Points | Chute / Target Bin |
|:---------|:----:|:---------------|:----------:|:------------------:|
| **Organic** | 🍏 | Food leftovers, fruit/vegetable peels, tea bags, garden trimmings | **+3 Points** | Green Organic Bin |
| **Plastic** | 🧴 | PET water bottles, containers, polybags, beverage cups | **+5 Points** | Blue Plastic Bin |
| **Metal**   | 🥫 | Soda/beverage cans, food tins, aluminium foil, metal scraps | **+7 Points** | Yellow Metal Bin |

---

## 📐 System Architecture & User Flow

```
                      [ USER / CAMERA / UPLOAD ]
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │         1. YOLO AI DETECTOR         │
               │  Organic (3pts) | Plastic (5pts)    │
               │            Metal (7pts)             │
               │       Confidence Gate (≥ 70%)       │
               └──────────────────┬──────────────────┘
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │    2. VIRTUAL SEGREGATION STAGE     │
               │   Animated Chute & 3D Bin Lids      │
               └──────────────────┬──────────────────┘
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │    3. SQLite PERSISTENCE ENGINE     │
               │   waste_records & rewards tables    │
               └──────────────────┬──────────────────┘
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │      4. UNIQUE QR CODE REWARD       │
               │    Generates ECO-XXXXXX voucher     │
               └──────────────────┬──────────────────┘
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │    5. MOBILE REDEMPTION PORTAL      │
               │   Name + Email -> Points Bound      │
               └──────────────────┬──────────────────┘
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │       6. ANALYTICS DASHBOARD        │
               │   Total Points | History | CO2      │
               └─────────────────────────────────────┘
```

---

## 📂 Project Directory Structure

```
econova/
├── ai/                         # AI & Computer Vision Engine
│   ├── camera.py               # Webcam capture & synthetic fallback stream
│   ├── detector.py             # YOLO WasteDetector & inspection logic
│   ├── main.py                 # Standalone OpenCV visual HUD demo
│   └── models/
│       └── best.pt             # (Optional) Trained custom YOLO weights
│
├── backend/                    # Core Web Application & Database
│   ├── app.py                  # Flask API server & route handlers
│   ├── database.py             # SQLite schema, transactions & queries
│   └── reward.py               # Unique voucher & QR code generator
│
├── frontend/                   # Modern Glassmorphic Web Interface
│   ├── index.html              # Main Sorting Studio, How It Works & Categories
│   ├── dashboard.html          # Real-time statistics & rewards ledger
│   ├── redeem.html             # QR-code mobile redemption page
│   ├── script.js               # Frontend animation, canvas drawing & API client
│   └── style.css               # Responsive design system & animations
│
├── database/                   # SQLite database directory
│   └── econova.db              # Database file (auto-created on start)
│
├── rewards/                    # Generated QR Code PNG vouchers (auto-created)
│   └── ECO-XXXXXX.png
│
├── test_stage1.py              # Stage 1 Verification Suite (AI & Webcam)
├── test_stage2.py              # Stage 2 Verification Suite (Virtual UI)
├── test_stage3.py              # Stage 3 Verification Suite (Flask & SQLite)
├── test_stage4.py              # Stage 4 Verification Suite (Reward & QR)
├── test_stage5.py              # Stage 5 Verification Suite (User & Points)
├── test_stage6.py              # Stage 6 Verification Suite (Dashboard & E2E)
├── requirements.txt            # Python dependencies
└── README.md                   # Documentation & judge's walkthrough
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

*(Key libraries: `flask`, `opencv-python`, `qrcode[pil]`, `ultralytics`, `torch`, `torchvision`, `numpy`)*

### 3. Placing Your Trained YOLO Model Weights
To enable live real-time inference:
Place your custom trained YOLOv8 model weights file at:
```
ai/models/best.pt
```

**Required Classes**:
The model must be trained on these 3 waste categories:
- `Organic`
- `Plastic`
- `Metal`

*Note: If `best.pt` is not present, EcoNova strictly reports `YOLO_MODEL_MISSING` and displays an informative banner `"REAL YOLO MODEL REQUIRED"`. No fake or simulated 94% detections are shown in normal mode. A collapsible developer panel is available if manual testing is needed.*

---

## ⚡ Running the Application

### 1. Start the EcoNova Server
From the root directory:
```bash
python backend/app.py
```

The Flask server will start on:
- **Local URL**: `http://127.0.0.1:5000`
- **Network URL**: `http://0.0.0.0:5000`

### 2. Open in Your Browser
- **EcoNova Sorting Studio**: [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Analytics Dashboard**: [http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard)

### 3. Presenting with Phone QR Scanning on Local Wi-Fi
To allow judges to scan QR codes using their own mobile phones:
1. Find your machine's Wi-Fi IP address (e.g. run `ipconfig` on Windows or `ifconfig` on macOS/Linux, e.g. `192.168.1.15`).
2. Set the environment variable before running:
   ```powershell
   $env:ECONOVA_BASE_URL="http://192.168.1.15:5000"
   python backend/app.py
   ```
   *(Or on Linux/macOS: `export ECONOVA_BASE_URL="http://192.168.1.15:5000" && python backend/app.py`)*

Any generated QR code will now link directly to your laptop over Wi-Fi!

---

## 🎯 Step-by-Step Hackathon Demo Walkthrough (for Judges)

Here is the ideal 2-minute live demonstration flow:

1. **Introduction & Concept**:
   - Open `http://127.0.0.1:5000`.
   - Explain EcoNova's core mission: *"See. Sort. Reward."* Automated AI segregation replacing human error at the bin level.
   - Point out the **"How It Works"** (Detect $\to$ Classify $\to$ Sort $\to$ Reward) and **"Waste Categories"** cards.

2. **Detection & AI Classification**:
   - Scroll to the **Sorting Studio**.
   - Show the live webcam stream or click **📁 Upload Image** to test image-based classification.
   - Use the **Quick Triggers** (`Plastic`, `Organic`, `Metal`) to showcase confidence scores and category tagging.
   - Click **Low Conf (58%)** to demonstrate our **Safety Confidence Gate**: the system prevents sorting and asks the user to reposition waste.

3. **Virtual Sorting & Persistence**:
   - Switch to **Plastic (94%)** and click **✨ SORT WASTE** (or press `Enter`).
   - Observe the flying waste token fly into the blue **Plastic Bin**, the bin lid open with sound, and the item counter increment.
   - Mention that this transaction was immediately committed to the SQLite database.

4. **Reward Creation & QR Code**:
   - The celebration modal pops up displaying a newly generated voucher: `ECO-XXXXXX` and a high-resolution QR code (+5 Eco Points).
   - Click **"Open Redemption Page"** (or scan the QR code with a phone).

5. **Claiming Points**:
   - The voucher page displays: Category: Plastic, Value: +5 Eco Points, Status: `UNCLAIMED`.
   - Enter Name (e.g. `Kushagra`) and Email (`kushagra@example.com`), then click **⭐ CLAIM REWARD**.
   - Status instantly transitions to `CLAIMED` with total points updated.
   - Try clicking Claim again: notice the atomic transaction rejects double claims.

6. **Viewing the Analytics Dashboard**:
   - Click **"View EcoNova Dashboard"** (or visit `/dashboard`).
   - Point out:
     - Total Points balance for the user account.
     - Total Items Recycled counter and estimated $\text{CO}_2$ emissions offset.
     - Category breakdown bars (Organic / Plastic / Metal).
     - Full transaction ledger showing the exact `ECO-XXXXXX` reward, timestamp, and status.

---

## ⌨️ Presentation Keyboard Shortcuts

| Key | Action |
|:---:|:-------|
| `P` | Trigger Plastic waste detection (94% confidence) |
| `O` | Trigger Organic waste detection (92% confidence) |
| `M` | Trigger Metal waste detection (96% confidence) |
| `L` | Trigger Low Confidence condition (58% confidence, prompts reposition) |
| `C` | Resume continuous automatic cycle mode |
| `Enter` | Trigger virtual sorting for current item |
| `Esc` | Close reward modal |

---

## 📡 REST API Reference

| Method | Endpoint | Description | Sample Request / Response |
|:-------|:---------|:------------|:--------------------------|
| `GET`  | `/api/detector/status` | Model inspection status | `{"classes": ["Organic", "Plastic", "Metal"], "threshold": 0.7}` |
| `POST` | `/api/detect` | Run AI detection on image frame | Request: `{"image": "data:image/jpeg;base64,..."}` |
| `POST` | `/api/sort` | Sort item & persist to database | Request: `{"category": "Plastic", "confidence": 0.94}` |
| `GET`  | `/api/records` | Get recent waste disposal logs | Response: `{"records": [...], "stats": {"Plastic": 12, ...}}` |
| `POST` | `/api/reward/create` | Generate voucher & QR code | Request: `{"waste_id": 1}` |
| `GET`  | `/api/reward/<id>` | Inspect reward details & status | Response: `{"reward_id": "ECO-9AD5C8", "points": 5, "status": "UNCLAIMED"}` |
| `POST` | `/api/reward/<id>/claim` | Claim reward points for user | Request: `{"user_id": 1}` or `{"name": "...", "email": "..."}` |
| `POST` | `/api/user` | Register or find user account | Request: `{"name": "Kushagra", "email": "kush@example.com"}` |
| `GET`  | `/api/user/<id>` | Fetch user profile & points | Response: `{"id": 1, "name": "Kushagra", "points": 15}` |
| `GET`  | `/api/dashboard/summary` | Aggregated dashboard metrics | Query: `?user_id=1` |
| `GET`  | `/api/dashboard/stats` | Global disposal counts | Response: `{"items_recycled": 45, "category_counts": {...}}` |

---

## 🧪 Automated Verification Test Suite

Every stage has an independent, fully automated test suite that verifies functionality end-to-end:

```bash
# Stage 1: AI & Webcam Detection (bounding box, HUD, confidence gate)
python test_stage1.py

# Stage 2: Virtual Sorting UI (assets, overrides, detection API)
python test_stage2.py

# Stage 3: Flask + SQLite Persistence (records table, sort endpoint)
python test_stage3.py

# Stage 4: Reward + QR Code System (unique ID, QR generation, redemption)
python test_stage4.py

# Stage 5: User Accounts & Points Connection (atomic claim, duplicate check)
python test_stage5.py

# Stage 6: Final Dashboard & Full End-to-End Integration
python test_stage6.py

# Real-Time Pipeline: Model Lifecycle, Zero Simulation, & Auto-Sort Cooldown
python test_realtime_pipeline.py
```

*All 7 test suites execute cleanly with 100% pass rates.*

---

## 👥 Team EcoNova

Developed for the **Smart India Hackathon** — Software Edition.
*EcoNova: See. Sort. Reward.*
