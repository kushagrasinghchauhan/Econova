/*
 * ==============================================================================
 * EcoNova ESP32 Hardware Firmware (Two-Servo Sorting Mechanism with Speed Control)
 * File: hardware/esp32_firmware/esp32_firmware.ino
 * 
 * Hardware Roles:
 * 1. G18 (GPIO 18) — DESTINATION SELECTOR SERVO:
 *    - Determines the physical compartment the waste will enter.
 *    - Moves FIRST to the required destination angle before G19 opens:
 *      * Organic     -> G18 = 0°
 *      * Dry/Plastic -> G18 = 30° (for both Plastic and Paper)
 *      * Metal       -> G18 = 90°
 *      * Startup     -> G18 = 30°
 * 
 * 2. G19 (GPIO 19) — WASTE RELEASE SERVO:
 *    - Controls the flap that physically holds the waste.
 *    - Starts CLOSED at 0° (keeps waste on the upper platform during camera scanning).
 *    - Opens to 180° ONLY AFTER G18 has reached the destination and settled.
 *    - Closes back to 0° after waste has fallen through.
 * 
 * Motion Architecture & Speed Optimization:
 *   - G18 Selector: moveServoSmoothly() with G18_MOVE_DELAY_MS = 15 ms/deg for smooth chute travel.
 *   - G19 Flap: moveG19FastSmooth() with S-Curve Cosine Easing:
 *       * 20ms update interval matches the 50 Hz PWM frame rate of the servo.
 *       * Eliminates high-frequency command flood (the root cause of 2ms/3ms/4ms jitter).
 *       * S-curve acceleration gently breaks stiction, surges at max physical speed
 *         through the middle, and softly lands at endpoints without mechanical bouncing.
 *       * G19_OPEN_DURATION_MS = 300 ms (Fast physical opening stroke, ~15 frames @ 20ms)
 *       * G19_CLOSE_DURATION_MS = 360 ms (Controlled closing stroke, ~18 frames @ 20ms)
 *   - Position tracking: currentG18Angle, currentG19Angle.
 * 
 * Required Sorting Sequence:
 *   1. Announce G18 destination
 *   2. G18 moves smoothly to destination angle (G18_MOVING)
 *   3. Settle delay (G18_SETTLE_DELAY_MS: 500ms) -> G18_SETTLED
 *   4. ONLY AFTER G18 settles: G19 opens fast & smooth to 180° (G19_OPEN)
 *   5. Hold open (G19_OPEN_TIME_MS: 1200ms) so waste falls
 *   6. G19 closes fast & smooth back to 0° (G19_CLOSE)
 *   7. Close delay (G19_CLOSE_DELAY_MS: 500ms)
 *   8. Sorting complete -> "SORTED"
 * 
 * NO IR sensor required.
 * Baud rate: 115200 baud
 * Library Requirement: "ESP32Servo" by Kevin Harrington
 * ==============================================================================
 */

#include <ESP32Servo.h>
#include <math.h>

// ==============================================================================
// PIN DEFINITIONS
// ==============================================================================
#define G18_PIN           18   // G18: DESTINATION SELECTOR SERVO (GPIO 18)
#define G19_PIN           19   // G19: WASTE RELEASE FLAP SERVO (GPIO 19)
#define LED_STATUS_PIN     2   // Built-in Blue LED for status indication

// ==============================================================================
// G18 DESTINATION ANGLES (Calibrate for your physical mechanism)
// ==============================================================================
#define G18_DEFAULT_ANGLE      30   // Safe / neutral startup position (Center: 30°)
#define G18_ORGANIC_ANGLE       0   // Directs waste to Organic bin (Left: 0°)
#define G18_DRY_PLASTIC_ANGLE  30   // Directs waste to Dry/Plastic bin (Center: 30°)
#define G18_METAL_ANGLE        90   // Directs waste to Metal bin (Right: 90°)

// Backward-compatible alias constants
#define ORGANIC_ANGLE          G18_ORGANIC_ANGLE
#define DRY_PLASTIC_ANGLE      G18_DRY_PLASTIC_ANGLE
#define METAL_ANGLE            G18_METAL_ANGLE

// ==============================================================================
// G19 RELEASE SERVO ANGLES
// ==============================================================================
#define G19_RELEASE_CLOSED      0   // Flap CLOSED / resting position (holds waste: 0°)
#define G19_RELEASE_OPEN      180   // Flap OPEN position (releases waste to fall: 180°)

// Backward-compatible alias constants
#define RELEASE_CLOSED         G19_RELEASE_CLOSED
#define RELEASE_OPEN           G19_RELEASE_OPEN

// ==============================================================================
// SERVO SPEED & MOTION PROFILE CONSTANTS
// ==============================================================================
// G18: Controlled medium/slow speed for destination selector chute (ms per degree)
#define G18_MOVE_DELAY_MS      15   

// G19: Fast & Smooth S-Curve Trajectory Constants
// 50 Hz PWM frame interval (20ms): commands synchronize 1:1 with hardware PWM cycles
#define G19_UPDATE_INTERVAL_MS 20
// Total opening duration for 0° -> 180°: 300ms (~15 frames @ 20ms, max physical speed of SG90)
#define G19_OPEN_DURATION_MS   180
// Total closing duration for 180° -> 0°: 360ms (~18 frames @ 20ms, soft landing without slamming)
#define G19_CLOSE_DURATION_MS  220

// Backward-compatible alias constants
#define G19_OPEN_DELAY_MS       8
#define G19_CLOSE_DELAY_MS     12

// ==============================================================================
// TIMING CONFIGURATION (Milliseconds) - Easily adjustable for calibration
// ==============================================================================
#define G18_SETTLE_DELAY_MS    500   // Wait for G18 to settle at destination (0.5s)
#define G19_OPEN_TIME_MS      1200   // Hold G19 open for waste to fall through (1.2s)
#define G19_CLOSE_DELAY_MS     500   // Wait after G19 closes before sequence completes (0.5s)

// ==============================================================================
// GLOBAL OBJECTS & STATE
// ==============================================================================
Servo servoG18;   // G18: Destination Selector (GPIO 18)
Servo servoG19;   // G19: Waste Release Flap (GPIO 19)

// Track actual current servo angles to enable smooth movement from current position
int currentG18Angle = G18_DEFAULT_ANGLE;
int currentG19Angle = G19_RELEASE_CLOSED;

String inputCommand = "";

// Function declarations
void processSerialCommands();
void handleSortCommand(String command);
void executeSortSequence(int destinationAngle, String destination);
int moveServoSmoothly(Servo &servo, int currentAngle, int targetAngle, int stepDelayMs);
int moveG19FastSmooth(Servo &servo, int startAngle, int targetAngle, int durationMs);

// ==============================================================================
// G18 GRADUAL SERVO MOVEMENT FUNCTION (LINEAR DEGREE STEPPING)
// ==============================================================================
int moveServoSmoothly(Servo &servo, int currentAngle, int targetAngle, int stepDelayMs) {
  if (currentAngle == targetAngle) {
    servo.write(targetAngle);
    return targetAngle;
  }
  int step = (targetAngle > currentAngle) ? 1 : -1;
  for (int angle = currentAngle; angle != targetAngle; angle += step) {
    servo.write(angle);
    delay(stepDelayMs);
  }
  servo.write(targetAngle);
  delay(stepDelayMs);
  return targetAngle;
}

// ==============================================================================
// G19 FAST & SMOOTH S-CURVE TRAJECTORY FUNCTION (COSINE EASING @ 50HZ PWM RATE)
// ==============================================================================
int moveG19FastSmooth(Servo &servo, int startAngle, int targetAngle, int durationMs) {
  if (startAngle == targetAngle) {
    servo.write(targetAngle);
    return targetAngle;
  }

  int stroke = abs(targetAngle - startAngle);
  int effectiveDuration = (durationMs * stroke) / 180;
  if (effectiveDuration < G19_UPDATE_INTERVAL_MS) {
    effectiveDuration = G19_UPDATE_INTERVAL_MS;
  }

  int totalSteps = effectiveDuration / G19_UPDATE_INTERVAL_MS;
  if (totalSteps < 1) totalSteps = 1;

  for (int step = 1; step <= totalSteps; step++) {
    float progress = (float)step / (float)totalSteps;
    // S-curve velocity profile via cosine easing:
    // Soft start (no gear shock) -> max physical speed through middle -> soft landing (no bounce)
    float ease = 0.5f * (1.0f - cosf(progress * 3.14159265f));
    int angle = (int)round(startAngle + (targetAngle - startAngle) * ease);
    servo.write(angle);
    delay(G19_UPDATE_INTERVAL_MS);
  }

  // Ensure exact final endpoint
  servo.write(targetAngle);
  return targetAngle;
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(LED_STATUS_PIN, OUTPUT);
  digitalWrite(LED_STATUS_PIN, LOW);

  // Allocate hardware PWM timers for ESP32
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  // 1. Attach both servos
  servoG18.setPeriodHertz(50);
  servoG18.attach(G18_PIN, 500, 2400);

  servoG19.setPeriodHertz(50);
  servoG19.attach(G19_PIN, 500, 2400);

  // 2. G19 MUST start at 0° (CLOSED). Do NOT move G19 to 180° during startup!
  servoG19.write(G19_RELEASE_CLOSED);
  currentG19Angle = G19_RELEASE_CLOSED;
  delay(500);

  // 3. G18 moves to safe startup angle (30°)
  servoG18.write(G18_DEFAULT_ANGLE);
  currentG18Angle = G18_DEFAULT_ANGLE;
  delay(500);

  // Blink status LED to confirm readiness
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_STATUS_PIN, HIGH);
    delay(100);
    digitalWrite(LED_STATUS_PIN, LOW);
    delay(100);
  }

  // 4. Only then report SYSTEM READY
  Serial.println("ECONOVA_ESP32_READY");
}

// ==============================================================================
// MAIN LOOP
// ==============================================================================
void loop() {
  // Process incoming Serial commands from EcoNova backend
  processSerialCommands();
}

// ==============================================================================
// SERIAL COMMAND PROCESSOR
// ==============================================================================
void processSerialCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      inputCommand.trim();
      inputCommand.toUpperCase();

      if (inputCommand.length() > 0) {
        handleSortCommand(inputCommand);
      }
      inputCommand = "";
    } else {
      inputCommand += c;
    }
  }
}

// ==============================================================================
// SORTING ACTUATION SEQUENCE
// ==============================================================================
void handleSortCommand(String command) {
  // Echo receipt back to EcoNova host
  Serial.print("RECEIVED: ");
  Serial.println(command);

  int targetAngle = -1;
  String destination = "";

  if (command == "ORGANIC" || command == "O") {
    targetAngle = G18_ORGANIC_ANGLE;
    destination = "ORGANIC";
  } 
  else if (command == "PLASTIC" || command == "PAPER" || command == "P") {
    targetAngle = G18_DRY_PLASTIC_ANGLE;
    destination = "DRY/PLASTIC";
  } 
  else if (command == "METAL" || command == "M") {
    targetAngle = G18_METAL_ANGLE;
    destination = "METAL";
  } 
  else if (command == "STATUS") {
    Serial.println("STATUS: READY");
    return;
  } 
  else if (command.startsWith("G18:")) {
    int angle = command.substring(4).toInt();
    Serial.print("CALIBRATE_G18: ");
    Serial.println(angle);
    currentG18Angle = moveServoSmoothly(servoG18, currentG18Angle, angle, G18_MOVE_DELAY_MS);
    return;
  }
  else if (command.startsWith("G19:")) {
    int angle = command.substring(4).toInt();
    Serial.print("CALIBRATE_G19: ");
    Serial.println(angle);
    int duration = (angle > currentG19Angle) ? G19_OPEN_DURATION_MS : G19_CLOSE_DURATION_MS;
    currentG19Angle = moveG19FastSmooth(servoG19, currentG19Angle, angle, duration);
    return;
  }
  else {
    Serial.print("ERROR: UNKNOWN_COMMAND: ");
    Serial.println(command);
    return;
  }

  digitalWrite(LED_STATUS_PIN, HIGH);
  executeSortSequence(targetAngle, destination);
  digitalWrite(LED_STATUS_PIN, LOW);
}

void executeSortSequence(int destinationAngle, String destination) {
  // STEP 1: Announce G18 destination
  Serial.print("G18_DESTINATION: ");
  Serial.print(destination);
  Serial.print(" (angle: ");
  Serial.print(destinationAngle);
  Serial.println(")");

  // STEP 2: Move G18 smoothly to destination angle FIRST
  Serial.println("G18_MOVING");
  currentG18Angle = moveServoSmoothly(servoG18, currentG18Angle, destinationAngle, G18_MOVE_DELAY_MS);

  // STEP 3: Wait settle delay for G18
  delay(G18_SETTLE_DELAY_MS);
  Serial.println("G18_SETTLED");

  // STEP 4: ONLY AFTER G18 has reached destination and settled, open G19 release flap (180°)
  Serial.print("G19_OPEN (angle: ");
  Serial.print(G19_RELEASE_OPEN);
  Serial.println(")");
  currentG19Angle = moveG19FastSmooth(servoG19, currentG19Angle, G19_RELEASE_OPEN, G19_OPEN_DURATION_MS);

  // STEP 5: Keep G19 open for waste to fall through
  delay(G19_OPEN_TIME_MS);

  // STEP 6: Close G19 flap back to 0°
  Serial.print("G19_CLOSE (angle: ");
  Serial.print(G19_RELEASE_CLOSED);
  Serial.println(")");
  currentG19Angle = moveG19FastSmooth(servoG19, currentG19Angle, G19_RELEASE_CLOSED, G19_CLOSE_DURATION_MS);

  // STEP 7: Wait close delay
  delay(G19_CLOSE_DELAY_MS);

  // STEP 8: Sorting is complete
  Serial.println("SORTED");
}

void resetServosToHome() {
  currentG19Angle = moveG19FastSmooth(servoG19, currentG19Angle, G19_RELEASE_CLOSED, G19_CLOSE_DURATION_MS);
  currentG18Angle = moveServoSmoothly(servoG18, currentG18Angle, G18_DEFAULT_ANGLE, G18_MOVE_DELAY_MS);
}
