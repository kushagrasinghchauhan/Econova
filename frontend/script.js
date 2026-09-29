/**
 * ECOnova - Frontend Interactive Logic
 * "Nature Meets Technology" — 9-Screen Kiosk, Web & Mobile Architecture
 * Handles real-time webcam frame transmission, real YOLO detection sync,
 * stable detection accumulation (3 consecutive frames >= 70%), 3D virtual bin sorting,
 * and seamless navigation across Kiosk Screens 1 to 5 & Mobile Screens.
 */

// Category metadata & reward point values
const CATEGORY_META = {
  Organic: {
    name: "Organic",
    emoji: "🍏",
    sub: "Food Waste / Bio-degradable",
    points: 3,
    color: "#16a34a",
    binId: "bin-organic",
    countId: "count-organic"
  },
  Plastic: {
    name: "Plastic",
    emoji: "🧴",
    sub: "Plastic Bottle / Container",
    points: 5,
    color: "#0284c7",
    binId: "bin-plastic",
    countId: "count-plastic"
  },
  Metal: {
    name: "Metal",
    emoji: "🥫",
    sub: "Aluminium Can / Metallic Scrap",
    points: 7,
    color: "#ca8a04",
    binId: "bin-metal",
    countId: "count-metal"
  },
  Paper: {
    name: "Paper",
    emoji: "📄",
    sub: "Paper / Cardboard / Dry Waste",
    destination: "Dry/Plastic",
    points: 5,
    color: "#0284c7",
    binId: "bin-plastic",
    countId: "count-plastic"
  }
};

// =====================================================================
// Operating Mode Setup: Phone 1 (Prototype) vs Phone 2 (User) vs Laptop Kiosk
// =====================================================================
const urlParams = new URLSearchParams(window.location.search);
let currentMode = urlParams.get("mode");

if (currentMode) {
  currentMode = currentMode.toLowerCase().trim();
  sessionStorage.setItem("econova_mode", currentMode);
} else {
  currentMode = sessionStorage.getItem("econova_mode");
}

if (!currentMode) {
  currentMode = "kiosk";
  sessionStorage.setItem("econova_mode", currentMode);
}

const isPrototypeMode = (currentMode === "prototype");
const isPhoneMode = (currentMode === "phone");
const isKioskMode = (currentMode === "kiosk" || (!isPrototypeMode && !isPhoneMode));
console.log(`[EcoNova] Operating Mode: ${currentMode.toUpperCase()}`);

let lastKnownKioskState = null;
let qrCountdownInterval = null;

function applyModeUI() {
  const badge = document.getElementById("mode-pill-badge");
  const link = document.getElementById("mode-toggle-link");
  const playOverlay = document.getElementById("chamber-play-overlay");
  const errorOverlay = document.getElementById("chamber-error-overlay");
  const kioskOverlay = document.getElementById("chamber-kiosk-overlay");
  const statusPill = document.getElementById("camera-status-pill");
  const statusText = document.getElementById("camera-status-text");
  const kioskQrSection = document.getElementById("kiosk-qr-section");
  const phoneRewardSection = document.getElementById("phone-reward-section");
  const restartBtnLabel = document.getElementById("btn-restart-label");

  if (isKioskMode) {
    if (badge) badge.textContent = "🖥️ Laptop Kiosk";
    if (link) {
      link.textContent = "📱 Phone 1: Prototype Camera";
      link.href = "/prototype";
    }
    if (playOverlay) playOverlay.style.display = "none";
    if (errorOverlay) errorOverlay.style.display = "none";
    if (kioskOverlay) {
      kioskOverlay.style.display = "flex";
      const kt = document.getElementById("chamber-kiosk-title");
      const ks = document.getElementById("chamber-kiosk-sub");
      if (kt) kt.textContent = "PROTOTYPE CAMERA ACTIVE (PHONE 1)";
      const protoUrl = `${window.location.origin}/prototype`;
      if (ks) ks.innerHTML = `Phone 1 is mounted on the prototype and sends waste frames over Wi-Fi.<br>Open on Phone 1: <a href='${protoUrl}' target='_blank' style='color:#38bdf8; font-weight:700; text-decoration:underline;'>${protoUrl}</a>`;
    }
    if (statusPill) {
      statusPill.className = "camera-status-pill status-ready";
    }
    if (statusText) statusText.textContent = "Phone 1 Camera Active";
    if (kioskQrSection) kioskQrSection.style.display = "flex";
    if (phoneRewardSection) phoneRewardSection.style.display = "none";
    if (restartBtnLabel) restartBtnLabel.textContent = "Recycle Another Item";
  } else if (isPrototypeMode) {
    window.location.replace("/prototype");
  } else {
    // Phone Mode
    window.location.replace("/phone");
  }
}

// =====================================================================
// Laptop Kiosk Display Polling (Syncs with Phone Scanner in Real-Time)
// =====================================================================
async function pollKioskState() {
  if (!isKioskMode) return;
  if (isSortingActive) return; // Don't interrupt sorting animation in progress

  try {
    const res = await fetch("/api/kiosk/state");
    if (!res.ok) return;
    const state = await res.json();
    syncKioskWithBackendState(state);
  } catch (e) {
    // Silent ignore
  }
}

function syncKioskWithBackendState(state) {
  if (!state) return;

  // 1. Reward State: Display large QR code on laptop
  if (state.status === "reward") {
    if (currentKioskScreen !== 5 || lastKnownKioskState?.reward_id !== state.reward_id) {
      populateSuccessScreen(state.category || "Plastic", state.points || 5, state);
      switchKioskScreen(5);
    }
    lastKnownKioskState = state;
    return;
  }

  // 2. Claimed State: Reward claimed via phone scanning QR
  if (state.status === "claimed") {
    if (currentKioskScreen === 5) {
      const headline = document.getElementById("success-main-headline");
      const subhint = document.getElementById("success-main-subhint");
      const name = state.claimed_by_name || "User";
      if (headline) headline.textContent = "REWARD CLAIMED!";
      if (subhint) subhint.innerHTML = `✓ Points credited to <strong>${name}</strong>!<br>Thank you for recycling with EcoNova.`;
      clearInterval(qrCountdownInterval);
      setTimeout(() => {
        resetKioskSession();
      }, 4000);
    }
    lastKnownKioskState = state;
    return;
  }

  // 3. Sorting State: Show sorting animation
  if (state.status === "sorting") {
    if (currentKioskScreen !== 4 && !isSortingActive) {
      triggerKioskSort(state.category, state.confidence, true);
    }
    lastKnownKioskState = state;
    return;
  }

  // 4. Detected State: Show detected item (Screen 3)
  if (state.status === "detected") {
    populateDetectionResultScreen(state.category, state.raw_class, state.confidence);
    if (currentKioskScreen !== 3 && currentKioskScreen !== 4 && currentKioskScreen !== 5) {
      switchKioskScreen(3);
    }
    lastKnownKioskState = state;
    return;
  }

  // 5. Scanning State: Switch from Idle (Screen 1) to Screen 2
  if (state.status === "scanning") {
    if (currentKioskScreen === 1) {
      switchKioskScreen(2);
    }
    const chamberTag = document.getElementById("chamber-tag");
    const statusTitle = document.getElementById("kiosk-status-title");
    const statusDesc = document.getElementById("kiosk-status-desc");
    if (chamberTag) chamberTag.style.display = "none";
    if (statusTitle) statusTitle.textContent = "Scanning Chamber...";
    if (statusDesc) statusDesc.textContent = "Analyzing waste stream from phone camera...";
    lastKnownKioskState = state;
    return;
  }

  // 6. Idle State: Return to welcome if reset
  if (state.status === "idle") {
    if (currentKioskScreen !== 1) {
      resetKioskToWelcome();
    }
    lastKnownKioskState = state;
  }
}

// =====================================================================
// Phone Scanner Auto-Resumption (Resumes scanning after claim or reset)
// =====================================================================
let isAutoResetting = false;

async function pollPhoneState() {
  if (!isPhoneMode || isAutoResetting) return;
  // If phone is displaying the Screen 5 guidance box, listen for claim/reset
  if (currentKioskScreen === 5) {
    try {
      const res = await fetch("/api/kiosk/state");
      if (!res.ok) return;
      const state = await res.json();
      if (state.status === "claimed" || state.status === "idle") {
        isAutoResetting = true;
        console.log("[EcoNova Phone] Claim/Idle detected. Resuming camera scanner in 3.5s...");
        setTimeout(() => {
          isAutoResetting = false;
          if (currentKioskScreen === 5) {
            console.log("[EcoNova Phone] Automatically resuming camera scanner...");
            resetPhoneScanner();
          }
        }, 3500);
      }
    } catch (e) {}
  }
}

function resetPhoneScanner() {
  consecutiveCount = 0;
  activeBBox = null;
  currentDetection = null;
  switchKioskScreen(2);
  startPhoneCamera();
}

function startQrCountdown(seconds) {
  clearInterval(qrCountdownInterval);
  let remaining = seconds > 0 ? seconds : 120;
  const cdEl = document.getElementById("kiosk-qr-countdown");

  const updateDisplay = () => {
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    if (cdEl) cdEl.textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
    if (remaining <= 0) {
      clearInterval(qrCountdownInterval);
      resetKioskSession();
    }
    remaining--;
  };

  updateDisplay();
  qrCountdownInterval = setInterval(updateDisplay, 1000);
}

function resetKioskSession() {
  if (isPhoneMode) {
    resetPhoneScanner();
  } else {
    clearInterval(qrCountdownInterval);
    fetch("/api/kiosk/reset", { method: "POST" }).catch(() => {});
    resetKioskToWelcome();
  }
}

// Detection Constants
const STABLE_CONSECUTIVE_FRAMES = 3;
const CONFIDENCE_THRESHOLD = 0.70;
const COOLDOWN_MS = 2500;
const CAPTURE_INTERVAL_MS = 240; // ~4 FPS capture rate

// Runtime State
let currentKioskScreen = 1;
let currentDetection = null;
let consecutiveCount = 0;
let lastCategory = null;
let activeBBox = null;
let activeFrameSize = { width: 640, height: 480 };
let isDetecting = false;
let isSortingActive = false;
let lastSortTime = 0;
let modelMissing = false;

let binCounts = {
  Organic: 0,
  Plastic: 0,
  Metal: 0
};

let totalPoints = 0;
let cameraActive = false;
let videoStream = null;
let isImageMode = false;
let uploadedImage = null;
let uploadedBase64 = null;

// =====================================================================
// Web Audio Context for Chime Effects
// =====================================================================
let audioCtx = null;

function getAudioContext() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) {
      audioCtx = new AudioContext();
    }
  }
  return audioCtx;
}

function playSuccessChime() {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume();

    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, now); // D5
    osc.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5

    gain.gain.setValueAtTime(0.2, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(now);
    osc.stop(now + 0.4);
  } catch (e) {
    // Audio optional
  }
}

// =====================================================================
// Kiosk Screen Switcher (Screen 1 to 5)
// =====================================================================
function switchKioskScreen(screenNum) {
  currentKioskScreen = screenNum;

  // Toggle View Containers
  for (let i = 1; i <= 5; i++) {
    const view = document.getElementById(`kiosk-view-${i}`);
    const pill = document.getElementById(`pill-screen-${i}`);
    if (view) {
      view.style.display = (i === screenNum) ? "block" : "none";
    }
    if (pill) {
      pill.classList.toggle("active", i === screenNum);
    }
  }

  // Camera Management: Fixed prototype camera on laptop kiosk
  if (screenNum === 2) {
    if (!isPhoneMode && !cameraActive && !isImageMode) {
      initCamera();
    }
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetKioskToWelcome() {
  consecutiveCount = 0;
  activeBBox = null;
  currentDetection = null;
  const headline = document.getElementById("success-main-headline");
  const subhint = document.getElementById("success-main-subhint");
  if (headline) headline.textContent = "YOUR REWARD IS READY";
  if (subhint) subhint.textContent = "Scan this QR code with your phone";
  switchKioskScreen(1);
}

// =====================================================================
// Real-time Clock on Kiosk Header
// =====================================================================
function updateKioskClock() {
  const now = new Date();
  const options = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
  const dateStr = now.toLocaleDateString('en-GB', options);
  
  let hours = now.getHours();
  const minutes = now.getMinutes().toString().padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12;
  hours = hours ? hours : 12;
  const timeStr = `${hours}:${minutes} ${ampm}`;

  const dateEl = document.getElementById("kiosk-live-date");
  const timeEl = document.getElementById("kiosk-live-time");
  if (dateEl) dateEl.textContent = dateStr;
  if (timeEl) timeEl.textContent = timeStr;

  document.querySelectorAll(".date-string").forEach(el => el.textContent = dateStr);
  document.querySelectorAll(".time-string").forEach(el => el.textContent = timeStr);
}

// =====================================================================
// Camera Status & UI Management
// =====================================================================
function updateCameraStatus(state, labelText) {
  const pill = document.getElementById("camera-status-pill");
  const text = document.getElementById("camera-status-text");
  if (pill) {
    pill.classList.remove("status-starting", "status-ready", "status-failed");
    pill.classList.add(`status-${state}`);
  }
  if (text && labelText) {
    text.textContent = labelText;
  }
}

function showCameraError(title, htmlDesc) {
  updateCameraStatus("failed", "Camera access failed");
  const playOverlay = document.getElementById("chamber-play-overlay");
  const errorOverlay = document.getElementById("chamber-error-overlay");
  const errTitle = document.getElementById("chamber-error-title");
  const errDesc = document.getElementById("chamber-error-desc");

  if (playOverlay) playOverlay.style.display = "none";
  if (errTitle) errTitle.textContent = title || "Camera Access Failed";
  if (errDesc) errDesc.innerHTML = htmlDesc || "Please allow camera access and retry.";
  if (errorOverlay) errorOverlay.style.display = "flex";
}

function handleChamberClick(event) {
  if (isKioskMode) return;
  // If camera is not active or has error, tapping chamber attempts to start
  if (!cameraActive) {
    startPhoneCamera(event);
  }
}

// =====================================================================
// Phone Camera Management (Rear Camera, Secure Context, Autoplay)
// =====================================================================
async function startPhoneCamera(event) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }

  // PHONE MODE GUARD (Rule 1 & Rule 2): User's phone MUST NEVER be used for waste detection!
  // Legacy reference: Kiosk Display Mode: Laptop is display screen, camera initialization bypassed.
  if (isPhoneMode) {
    console.log("[Phone] Waste detection is disabled on phone. Prototype camera on laptop handles detection.");
    return;
  }
  console.log("[Prototype Camera] Initializing fixed prototype webcam on laptop kiosk...");

  // 1. Check Secure Context (HTTPS or Localhost)
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  const isSecure = window.isSecureContext || isLocal;
  if (!isSecure && window.location.protocol === "http:") {
    const host = window.location.hostname || "192.168.1.4";
    const port = window.location.port || "5000";
    const httpsUrl = `https://${host}:${port}${window.location.pathname}${window.location.search}${window.location.hash}`;
    showCameraError(
      "HTTPS Required on Phone",
      `Mobile browsers require HTTPS to access the rear camera.<br><br>` +
      `<a href="${httpsUrl}" target="_self" style="font-weight:700;color:#38bdf8;text-decoration:underline;">` +
      `Tap here to open via HTTPS (${httpsUrl})</a><br><br>` +
      `<span style="font-size:0.75rem;color:#cbd5e1;display:block;">` +
      `Note: If you see "Your connection is not private", tap <b>Advanced</b> &rarr; <b>Proceed to ${host}</b>.</span>`
    );
    return;
  }

  // 2. Check Browser MediaDevices Support
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showCameraError(
      "Camera Not Supported",
      "Your mobile browser does not support navigator.mediaDevices.getUserMedia. Please open this site in modern Chrome, Edge, or Safari."
    );
    return;
  }

  // Fast path: if videoStream is already active, simply ensure video plays
  if (videoStream && videoStream.active) {
    const video = document.getElementById("webcam");
    if (video) {
      if (video.srcObject !== videoStream) {
        video.srcObject = videoStream;
      }
      try {
        await video.play();
      } catch (e) {}
      cameraActive = true;
      updateCameraStatus("ready", "Camera ready");
      const playOverlay = document.getElementById("chamber-play-overlay");
      const errorOverlay = document.getElementById("chamber-error-overlay");
      if (playOverlay) playOverlay.style.display = "none";
      if (errorOverlay) errorOverlay.style.display = "none";
      return;
    }
  }

  // 3. Update status indicator to Starting
  updateCameraStatus("starting", "Starting camera...");
  const playTitle = document.getElementById("chamber-play-title");
  const playSub = document.getElementById("chamber-play-sub");
  const errorOverlay = document.getElementById("chamber-error-overlay");
  const playOverlay = document.getElementById("chamber-play-overlay");

  if (errorOverlay) errorOverlay.style.display = "none";
  if (playOverlay) playOverlay.style.display = "flex";
  if (playTitle) playTitle.textContent = "Connecting Camera...";
  if (playSub) playSub.textContent = "Requesting mobile rear camera access...";

  // 4. Stop existing stream if any
  if (videoStream) {
    try {
      videoStream.getTracks().forEach(track => track.stop());
    } catch (e) {}
    videoStream = null;
  }

  // 5. Constraints hierarchy targeting phone's rear camera
  const primaryConstraints = {
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    audio: false
  };

  const fallbackConstraints = {
    video: {
      facingMode: { ideal: "environment" }
    },
    audio: false
  };

  const genericConstraints = {
    video: true,
    audio: false
  };

  let stream = null;
  try {
    // Attempt 1: Ideal 720p rear camera
    stream = await navigator.mediaDevices.getUserMedia(primaryConstraints);
  } catch (err1) {
    console.warn("Primary camera constraints failed, attempting fallback...", err1);
    try {
      // Attempt 2: Flexible rear camera
      stream = await navigator.mediaDevices.getUserMedia(fallbackConstraints);
    } catch (err2) {
      console.warn("Fallback camera constraints failed, attempting generic camera...", err2);
      try {
        // Attempt 3: Generic default video
        stream = await navigator.mediaDevices.getUserMedia(genericConstraints);
      } catch (err3) {
        console.error("All getUserMedia attempts failed:", err3);
        let errorMsg = "Could not access camera. Please allow camera permissions and retry.";
        if (err3.name === "NotAllowedError" || err3.name === "PermissionDeniedError") {
          errorMsg = "Camera permission was denied. Please allow camera permissions in your mobile browser settings and tap Retry.";
        } else if (err3.name === "NotFoundError" || err3.name === "DevicesNotFoundError") {
          errorMsg = "No camera was found on this device.";
        } else if (err3.name === "NotReadableError" || err3.name === "TrackStartError") {
          errorMsg = "Camera is in use by another app or browser tab. Please close other apps using the camera and tap Retry.";
        }
        showCameraError("Camera Access Failed", errorMsg);
        return;
      }
    }
  }

  // 6. Connect stream to <video> element
  const video = document.getElementById("webcam");
  if (!video || !stream) {
    showCameraError("Camera Element Error", "Video chamber element not found.");
    return;
  }

  videoStream = stream;
  video.srcObject = stream;
  video.setAttribute("autoplay", "");
  video.setAttribute("playsinline", "");
  video.setAttribute("muted", "");
  video.muted = true;
  video.playsInline = true;
  video.autoplay = true;

  const markCameraReady = () => {
    cameraActive = true;
    updateCameraStatus("ready", "Camera ready");
    if (playOverlay) playOverlay.style.display = "none";
    if (errorOverlay) errorOverlay.style.display = "none";
  };

  video.onplaying = markCameraReady;
  video.onloadeddata = markCameraReady;

  try {
    await video.play();
    markCameraReady();
  } catch (playError) {
    console.warn("Autoplay promise rejected, waiting for user gesture:", playError);
    // Keep play button visible so user can tap
    if (playTitle) playTitle.textContent = "Tap to Start Video";
    if (playSub) playSub.textContent = "Browser requires a tap to play live stream";
  }
}

async function initCamera() {
  if (isKioskMode) {
    console.log("[Kiosk] Laptop kiosk mode active - camera stream provided by Phone 1 over Wi-Fi.");
    return;
  }
  if (isPhoneMode) {
    console.log("[Phone] Waste detection camera is disabled on phone. Prototype camera (Phone 1) handles detection.");
    return;
  }
  // Generic fallback if not kiosk/phone
  startPhoneCamera();
}

// =====================================================================
// Periodic Live Frame Capture & Transmission (Hidden Canvas)
// =====================================================================
async function captureAndDetectFrame() {
  // Laptop Kiosk does NOT capture frames locally - Phone 1 streams frames over Wi-Fi
  if (isKioskMode || isPhoneMode) return;
  // Only capture if user is on Screen 2 (Scanning)
  if (currentKioskScreen !== 2) return;
  if (isSortingActive || isDetecting || isImageMode) return;
  if (Date.now() - lastSortTime < COOLDOWN_MS) return;

  const video = document.getElementById("webcam");
  if (!video || !cameraActive || video.readyState < 2) return;
  if (!video.videoWidth || !video.videoHeight) return;

  // Use hidden capture canvas from DOM (Requirement 8)
  let hiddenCanvas = document.getElementById("hidden-capture-canvas");
  if (!hiddenCanvas) {
    hiddenCanvas = document.createElement("canvas");
    hiddenCanvas.id = "hidden-capture-canvas";
    hiddenCanvas.style.display = "none";
    document.body.appendChild(hiddenCanvas);
  }

  const vW = video.videoWidth;
  const vH = video.videoHeight;
  const targetW = 640;
  const targetH = Math.round((vH / vW) * targetW);

  if (hiddenCanvas.width !== targetW || hiddenCanvas.height !== targetH) {
    hiddenCanvas.width = targetW;
    hiddenCanvas.height = targetH;
  }

  const captureCtx = hiddenCanvas.getContext("2d", { willReadFrequently: false });
  captureCtx.drawImage(video, 0, 0, targetW, targetH);

  // Requirement 9: Send JPEG to POST /api/detect as { "image": canvas.toDataURL("image/jpeg", 0.8) }
  const dataUrl = hiddenCanvas.toDataURL("image/jpeg", 0.8);

  isDetecting = true;
  try {
    const res = await fetch("/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: dataUrl })
    });

    if (res.ok) {
      const data = await res.json();
      handleDetectionResponse(data);
    }
  } catch (err) {
    console.warn("Detection request error:", err);
  } finally {
    isDetecting = false;
  }
}

function handleDetectionResponse(data) {
  const alertBanner = document.getElementById("model-alert-banner");
  const chamberTag = document.getElementById("chamber-tag");
  const statusTitle = document.getElementById("kiosk-status-title");
  const statusDesc = document.getElementById("kiosk-status-desc");

  // Model Missing or Incompatible
  if (!data.success && (data.error === "YOLO_MODEL_MISSING" || data.error === "INCOMPATIBLE_CLASSES")) {
    modelMissing = true;
    if (alertBanner) alertBanner.style.display = "flex";
    if (statusTitle) statusTitle.textContent = "AI Model Required";
    if (statusDesc) statusDesc.textContent = "Please place trained best.pt in ai/models/";
    if (chamberTag) chamberTag.style.display = "none";
    activeBBox = null;
    return;
  }

  modelMissing = false;
  if (alertBanner) alertBanner.style.display = "none";

  // Kiosk Session Locked (Actively sorting, or displaying reward QR)
  if (data.session_locked) {
    activeBBox = null;
    currentDetection = null;
    consecutiveCount = 0;
    if (chamberTag) chamberTag.style.display = "none";
    if (statusTitle) statusTitle.textContent = "Processing Item...";
    if (statusDesc) statusDesc.textContent = data.message || "Sorting or reward active. Awaiting claim or reset...";
    return;
  }

  // Case: No waste detected in current frame
  if (!data.detected) {
    activeBBox = null;
    currentDetection = null;
    consecutiveCount = 0;
    if (chamberTag) chamberTag.style.display = "none";
    if (statusTitle) statusTitle.textContent = "Analyzing with AI...";
    if (statusDesc) statusDesc.textContent = "Please wait while we identify the waste.";
    return;
  }

  // Waste detected!
  activeBBox = data.bbox;
  activeFrameSize = data.frame_size || { width: 640, height: 480 };
  currentDetection = {
    category: data.category,
    confidence: data.confidence,
    isConfident: data.is_confident,
    rawClass: data.raw_class
  };

  const rawName = data.raw_class ? data.raw_class.toLowerCase() : data.category.toLowerCase();
  const confFixed = (data.confidence * 100).toFixed(2);
  const confShort = data.confidence.toFixed(2);

  // Update Dynamic Tag on Chamber (e.g. bottle 0.92)
  if (chamberTag) {
    chamberTag.style.display = "inline-flex";
    chamberTag.textContent = `${rawName} ${confShort}`;
  }

  // Update Status Card
  if (statusTitle) statusTitle.textContent = `Identified: ${data.category.toUpperCase()}`;
  if (statusDesc) statusDesc.textContent = `Confidence ${confFixed}% • Stabilizing item...`;

  // Pre-fill Screen 3 (Detection Result)
  populateDetectionResultScreen(data.category, data.raw_class, data.confidence);

  // Stability Accumulation Gate (3 consecutive frames >= 70%)
  if (data.is_confident && data.confidence >= CONFIDENCE_THRESHOLD) {
    if (data.category === lastCategory) {
      consecutiveCount++;
    } else {
      lastCategory = data.category;
      consecutiveCount = 1;
    }

    // When 3 frames confirmed, advance automatically!
    if (consecutiveCount >= STABLE_CONSECUTIVE_FRAMES && !isSortingActive) {
      console.log(`[EcoNova Kiosk] 3-Frame Stability reached for ${data.category}!`);
      consecutiveCount = 0;
      
      // Advance to Screen 3 (Detected) then trigger sort
      switchKioskScreen(3);
      setTimeout(() => {
        triggerKioskSort(data.category, data.confidence);
      }, 900);
    }
  } else {
    consecutiveCount = 0;
  }
}

// Populate Screen 3 UI Elements
function populateDetectionResultScreen(category, rawClass, confidence) {
  const meta = CATEGORY_META[category] || CATEGORY_META.Plastic;
  const nameEl = document.getElementById("result-item-name");
  const emojiEl = document.getElementById("result-item-emoji");
  const badgeEl = document.getElementById("result-category-badge");
  const confValEl = document.getElementById("result-confidence-val");
  const confBarEl = document.getElementById("result-confidence-bar");
  const noteEl = document.getElementById("kiosk-result-note");

  const displayName = rawClass ? (rawClass.charAt(0).toUpperCase() + rawClass.slice(1)) : meta.name;
  if (nameEl) nameEl.textContent = displayName;
  if (emojiEl) emojiEl.textContent = meta.emoji;

  if (badgeEl) {
    badgeEl.textContent = meta.name.toUpperCase();
    badgeEl.className = "result-category-badge " + meta.name.toLowerCase();
  }

  const pct = (confidence * 100).toFixed(2);
  if (confValEl) confValEl.textContent = `${pct}%`;
  if (confBarEl) confBarEl.style.width = `${Math.min(100, confidence * 100).toFixed(1)}%`;

  if (noteEl) {
    const destName = meta.destination || meta.name;
    noteEl.innerHTML = `This item will be sorted into the <strong>${destName}</strong> bin.`;
  }
}

// =====================================================================
// Bounding Box Drawing Loop on Canvas
// =====================================================================
function drawBoundingBox(canvas, ctx) {
  if (!canvas || !ctx || !activeBBox || !activeFrameSize) return;

  const scaleX = canvas.width / activeFrameSize.width;
  const scaleY = canvas.height / activeFrameSize.height;

  const boxX = activeBBox.x1 * scaleX;
  const boxY = activeBBox.y1 * scaleY;
  const boxW = (activeBBox.x2 - activeBBox.x1) * scaleX;
  const boxH = (activeBBox.y2 - activeBBox.y1) * scaleY;

  const strokeColor = "#10b981";

  // Box border
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 2.5;
  ctx.strokeRect(boxX, boxY, boxW, boxH);

  // Corner highlights
  const cl = 16;
  ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo(boxX, boxY + cl); ctx.lineTo(boxX, boxY); ctx.lineTo(boxX + cl, boxY); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(boxX + boxW - cl, boxY); ctx.lineTo(boxX + boxW, boxY); ctx.lineTo(boxX + boxW, boxY + cl); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(boxX, boxY + boxH - cl); ctx.lineTo(boxX, boxY + boxH); ctx.lineTo(boxX + cl, boxY + boxH); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(boxX + boxW - cl, boxY + boxH); ctx.lineTo(boxX + boxW, boxY + boxH); ctx.lineTo(boxX + boxW, boxY + boxH - cl); ctx.stroke();
}

function renderOverlayLoop() {
  const canvas = document.getElementById("overlay-canvas");
  const wrapper = document.getElementById("camera-wrapper");
  if (canvas && wrapper) {
    if (canvas.width !== wrapper.clientWidth || canvas.height !== wrapper.clientHeight) {
      canvas.width = wrapper.clientWidth;
      canvas.height = wrapper.clientHeight;
    }
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (activeBBox) {
      drawBoundingBox(canvas, ctx);
    }
  }
  requestAnimationFrame(renderOverlayLoop);
}

// =====================================================================
// SCREEN 4 & 5: SORTING ANIMATION & REWARD GENERATION
// =====================================================================
function triggerKioskSort(overrideCategory, overrideConfidence, skipApi = false) {
  if (isSortingActive) return;

  const category = overrideCategory || (currentDetection ? currentDetection.category : "Plastic");
  const confidence = overrideConfidence || (currentDetection ? currentDetection.confidence : 0.9218);
  const meta = CATEGORY_META[category] || CATEGORY_META.Plastic;

  isSortingActive = true;
  switchKioskScreen(4); // Switch to Screen 4 (Sorting Process)

  // Update subtitle to reflect destination (e.g. "Routing to Dry/Plastic Bin...")
  const sortingSub = document.getElementById("sorting-subtitle");
  if (sortingSub) {
    const destName = meta.destination || meta.name;
    sortingSub.textContent = `Routing to ${destName} Bin...`;
  }

  // Highlight the correct physical compartment (Dry/Plastic for both Plastic and Paper)
  ["bin-organic", "bin-plastic", "bin-metal"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("active-target");
  });
  const targetBin = document.getElementById(meta.binId);
  if (targetBin) targetBin.classList.add("active-target");

  // Step Chain: 1. Detected
  updateChainStep(1);

  // Step Chain: 2. Processing (after 400ms)
  setTimeout(() => {
    updateChainStep(2);
  }, 400);

  // Step Chain: 3. Sorting (after 900ms)
  setTimeout(() => {
    updateChainStep(3);
    const line = document.getElementById("trajectory-line");
    if (line) line.style.stroke = meta.color;
  }, 900);

  // Complete and deposit (after 1800ms)
  setTimeout(async () => {
    updateChainStep(4);
    playSuccessChime();

    let rewardData = null;
    if (!skipApi) {
      // Call backend /api/sort to register reward and generate real QR code
      try {
        const resp = await fetch("/api/sort", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, confidence })
        });

        if (resp.ok) {
          rewardData = await resp.json();
          if (rewardData.stats) {
            binCounts.Organic = rewardData.stats.Organic;
            binCounts.Plastic = rewardData.stats.Plastic;
            binCounts.Metal = rewardData.stats.Metal;
          }
        }
      } catch (e) {
        console.warn("Could not reach /api/sort:", e);
      }
    }

    // Populate Screen 5 (Success & QR)
    populateSuccessScreen(category, meta.points, rewardData);

    // Transition to Screen 5
    setTimeout(() => {
      switchKioskScreen(5);
      isSortingActive = false;
      lastSortTime = Date.now();
    }, 600);

  }, 1900);
}

function updateChainStep(stepNum) {
  for (let i = 1; i <= 4; i++) {
    const el = document.getElementById(`chain-step-${i}`);
    if (!el) continue;
    el.classList.remove("active", "completed");
    if (i === stepNum) {
      el.classList.add("active");
    } else if (i < stepNum) {
      el.classList.add("completed");
    }
  }
}

function populateSuccessScreen(category, points, rewardData) {
  const catNameEl = document.getElementById("success-cat-name");
  const ptsTextEl = document.getElementById("success-pts-text");
  const qrImgEl = document.getElementById("kiosk-qr-image");
  const rewardIdEl = document.getElementById("kiosk-reward-id");
  const headlineEl = document.getElementById("success-main-headline");
  const subhintEl = document.getElementById("success-main-subhint");
  const kioskQrSection = document.getElementById("kiosk-qr-section");
  const phoneRewardSection = document.getElementById("phone-reward-section");
  const phonePtsBadge = document.getElementById("phone-pts-badge");
  const restartBtnLabel = document.getElementById("btn-restart-label");

  if (headlineEl) headlineEl.textContent = "YOUR REWARD IS READY";
  if (subhintEl) subhintEl.textContent = "Scan this QR code with your phone";
  if (catNameEl) catNameEl.textContent = (category || "Plastic").toUpperCase();
  if (ptsTextEl) ptsTextEl.textContent = `Reward: +${points} Eco Points`;

  const rewId = (rewardData && rewardData.reward_id) ? rewardData.reward_id : "ECO-REWARD";
  if (rewardIdEl) rewardIdEl.textContent = rewId;

  if (rewardData && rewardData.qr_image_url && qrImgEl) {
    qrImgEl.src = `${rewardData.qr_image_url}?t=${Date.now()}`;
  }

  if (isPhoneMode) {
    // PHONE MODE: User is on phone; do NOT show large QR to scan own screen!
    if (kioskQrSection) kioskQrSection.style.display = "none";
    if (phoneRewardSection) phoneRewardSection.style.display = "block";
    if (phonePtsBadge) phonePtsBadge.textContent = `+${points} Eco Points`;
    if (restartBtnLabel) restartBtnLabel.textContent = "Scan Another Item";
  } else {
    // KIOSK MODE: Laptop display screen shows LARGE QR for phone to scan!
    if (kioskQrSection) kioskQrSection.style.display = "flex";
    if (phoneRewardSection) phoneRewardSection.style.display = "none";
    if (restartBtnLabel) restartBtnLabel.textContent = "Recycle Another Item";
    startQrCountdown(rewardData?.time_left || 120);
  }
}

// =====================================================================
// Static Image Upload Testing
// =====================================================================
function handleImageUpload(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function(e) {
    const dataUrl = e.target.result;
    uploadedBase64 = dataUrl;

    const img = new Image();
    img.onload = async function() {
      uploadedImage = img;
      isImageMode = true;

      const previewImg = document.getElementById("result-preview-img");
      if (previewImg) {
        previewImg.src = dataUrl;
        previewImg.style.display = "block";
      }

      try {
        const res = await fetch("/api/detect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: dataUrl })
        });

        if (res.ok) {
          const data = await res.json();
          handleDetectionResponse(data);
          // If detected, switch to Screen 3 to show the result
          if (data.detected) {
            switchKioskScreen(3);
          }
        }
      } catch (err) {
        console.warn("AI detection error on uploaded image:", err);
      }
    };
    img.src = dataUrl;
  };
  reader.readAsDataURL(file);
}

// =====================================================================
// Developer Presets (for evaluation & instant testing)
// =====================================================================
function setDevPreset(category, confidence) {
  if (category === null) {
    fetch("/api/demo_override", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: null })
    }).catch(() => {});
    return;
  }

  fetch("/api/demo_override", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, confidence })
  }).then(async () => {
    const res = await fetch("/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    if (res.ok) {
      const data = await res.json();
      handleDetectionResponse(data);
      switchKioskScreen(3);
    }
  }).catch(() => {});
}

// =====================================================================
// SCREEN 7: Mobile Auth Modal Management
// =====================================================================
let currentAuthMode = "login";

function openAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.style.display = "flex";
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.style.display = "none";
}

function setAuthMode(mode) {
  currentAuthMode = mode;
  const btnLogin = document.getElementById("tab-btn-login");
  const btnSignup = document.getElementById("tab-btn-signup");
  const formLogin = document.getElementById("form-login");
  const formSignup = document.getElementById("form-signup");
  const tagline = document.getElementById("auth-tagline");
  const switchText = document.getElementById("auth-switch-text");
  const switchLink = document.getElementById("auth-switch-link");

  if (mode === "login") {
    if (btnLogin) btnLogin.classList.add("active");
    if (btnSignup) btnSignup.classList.remove("active");
    if (formLogin) formLogin.style.display = "block";
    if (formSignup) formSignup.style.display = "none";
    if (tagline) tagline.textContent = "Join the recycling movement";
    if (switchText) switchText.textContent = "New to EcoNova?";
    if (switchLink) switchLink.textContent = "Create an account →";
  } else {
    if (btnLogin) btnLogin.classList.remove("active");
    if (btnSignup) btnSignup.classList.add("active");
    if (formLogin) formLogin.style.display = "none";
    if (formSignup) formSignup.style.display = "block";
    if (tagline) tagline.textContent = "Create your account";
    if (switchText) switchText.textContent = "Already have an account?";
    if (switchLink) switchLink.textContent = "Login here →";
  }
}

function toggleAuthMode() {
  setAuthMode(currentAuthMode === "login" ? "signup" : "login");
}

async function handleUserLogin() {
  const input = document.getElementById("login-identifier");
  const val = input ? input.value.trim() : "kushagra@econova.org";
  
  localStorage.setItem("econova_user_name", "Kushagra");
  localStorage.setItem("econova_user_email", val.includes("@") ? val : `${val}@econova.org`);
  
  // Register or retrieve user from SQLite
  try {
    const res = await fetch("/api/user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Kushagra", email: val.includes("@") ? val : `${val}@econova.org` })
    });
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem("econova_user_id", data.id);
    }
  } catch (e) {}

  closeAuthModal();
  alert(`Welcome back, Kushagra! You are now logged in.`);
}

async function handleUserSignup() {
  const name = document.getElementById("signup-name").value.trim();
  const mobile = document.getElementById("signup-mobile").value.trim();
  const email = `${mobile}@econova.org`;

  try {
    const res = await fetch("/api/user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email })
    });
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem("econova_user_id", data.id);
      localStorage.setItem("econova_user_name", name);
      localStorage.setItem("econova_user_email", email);
    }
  } catch (e) {}

  closeAuthModal();
  alert(`Account successfully created for ${name}!`);
}

function handleGoogleMockLogin() {
  localStorage.setItem("econova_user_name", "Kushagra");
  localStorage.setItem("econova_user_email", "kushagra.google@econova.org");
  closeAuthModal();
  alert("Signed in with Google as Kushagra!");
}

// =====================================================================
// Legacy Compatibility Helpers
// =====================================================================
function triggerVirtualSort(category, confidence) {
  triggerKioskSort(category, confidence);
}

function updateStabilityMeter() {}

// =====================================================================
// Lifecycle Initialization
// =====================================================================
window.addEventListener("DOMContentLoaded", () => {
  applyModeUI();
  updateKioskClock();
  setInterval(updateKioskClock, 1000);

  // Mode routing and lifecycle
  if (isPhoneMode) {
    console.log("[Phone] Phone mode active - waste detection camera is OFF.");
    window.location.replace("/phone");
  } else if (isPrototypeMode) {
    console.log("[Prototype] Prototype mode active - redirecting to Phone 1 HUD.");
    window.location.replace("/prototype");
  } else {
    // Laptop Kiosk: Poll kiosk state from backend (Phone 1 sends frames to /api/detect)
    setInterval(pollKioskState, 500);
    pollKioskState();
  }

  // Canvas rendering loop
  requestAnimationFrame(renderOverlayLoop);

  // Check URL hash for direct links (e.g. #scan, #auth)
  if (window.location.hash === "#scan") {
    switchKioskScreen(2);
  } else if (window.location.hash === "#auth") {
    openAuthModal();
  }
});
