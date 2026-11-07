#include "hw.h"

#include <Arduino.h>
#include <FastLED.h>
#include <Servo.h>
#include <Wire.h>

namespace {

constexpr uint8_t kStbyPin = 3;
constexpr uint8_t kRightPwmPin = 5;
constexpr uint8_t kRightDirPin = 7;
constexpr uint8_t kLeftPwmPin = 6;
constexpr uint8_t kLeftDirPin = 8;
constexpr uint8_t kLineLeftPin = A2;
constexpr uint8_t kLineMiddlePin = A1;
constexpr uint8_t kLineRightPin = A0;
constexpr uint8_t kBattPin = A3;
constexpr uint8_t kSonarTrigPin = 13;
constexpr uint8_t kSonarEchoPin = 12;
constexpr uint8_t kServoPin = 10;
constexpr uint8_t kLedPin = 4;
constexpr uint8_t kLedCount = 1;

// Factory formula: divider ratio and ADC step, with a 1.08 correction.
constexpr float kBattVoltsPerStep = 0.0375f * 1.08f;
constexpr float kMvPerVolt = 1000;

// The echo of the last ping must fade before the next trigger.
constexpr uint32_t kSonarPeriodMs = 60;
// Bounds the loop block; about 2.5 m of range.
constexpr unsigned long kSonarTimeoutUs = 15000;
constexpr unsigned int kSonarTrigPulseUs = 10;
constexpr unsigned int kSonarSettleUs = 2;
constexpr unsigned long kSonarUsPerCm = 58;

constexpr uint8_t kServoCenterDeg = 90;
// Detached servo frees Timer1 and stops jitter.
constexpr uint32_t kServoSettleMs = 500;

constexpr uint8_t kImuAddr = 0x68;
constexpr uint8_t kImuPowerReg = 0x6B;
constexpr uint8_t kImuWake = 0;
constexpr uint8_t kImuGyroZReg = 0x47;
constexpr uint8_t kImuGyroZBytes = 2;
// Default full scale +-250 deg/s.
constexpr float kImuLsbPerDps = 131;
// The module is mounted Z up: raw Z is negative on a right turn (bench test).
constexpr float kGyroSign = -1;
constexpr uint32_t kI2cTimeoutUs = 3000;
constexpr uint32_t kGyroBiasMs = 2000;
constexpr float kUsPerS = 1e6f;

constexpr uint8_t kLedBrightness = 50;

Servo servo;
bool servo_attached = false;
uint32_t servo_attach_ms = 0;

uint32_t sonar_trigger_ms = 0;
bool sonar_triggered = false;
uint16_t sonar_cm = 0;

bool imu_ok = false;
float gyro_bias_dps = 0;
float yaw_deg = 0;
uint32_t yaw_us = 0;

CRGB leds[kLedCount];
bool led_set = false;
LedColor led_color = LedColor::Blue;

bool writeImuReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kImuAddr);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

// On NACK or I2C timeout the IMU is marked lost until reboot.
bool gyroZdps(float& out) {
  if (!imu_ok) {
    return false;
  }
  Wire.beginTransmission(kImuAddr);
  Wire.write(kImuGyroZReg);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(kImuAddr, kImuGyroZBytes) != kImuGyroZBytes) {
    imu_ok = false;
    return false;
  }
  uint8_t high = Wire.read();
  uint8_t low = Wire.read();
  int16_t raw = static_cast<int16_t>((high << 8) | low);
  out = kGyroSign * raw / kImuLsbPerDps;
  return true;
}

void imuInit() {
  Wire.begin();
  Wire.setWireTimeout(kI2cTimeoutUs, true);
  imu_ok = writeImuReg(kImuPowerReg, kImuWake);
}

CRGB ledRgb(LedColor color) {
  switch (color) {
    case LedColor::Blue:
      return CRGB::Blue;
    case LedColor::Green:
      return CRGB::Green;
    case LedColor::Red:
      return CRGB::Red;
  }
  return CRGB::Black;
}

uint8_t linePin(LineSensor sensor) {
  switch (sensor) {
    case LineSensor::Left:
      return kLineLeftPin;
    case LineSensor::Middle:
      return kLineMiddlePin;
    case LineSensor::Right:
      return kLineRightPin;
  }
  return kLineMiddlePin;
}

void motor(uint8_t pwm_pin, uint8_t dir_pin, int16_t value) {
  digitalWrite(dir_pin, value >= 0 ? HIGH : LOW);
  analogWrite(pwm_pin, abs(value));
}

}  // namespace

namespace hw {

void begin() {
  pinMode(kStbyPin, OUTPUT);
  pinMode(kRightPwmPin, OUTPUT);
  pinMode(kRightDirPin, OUTPUT);
  pinMode(kLeftPwmPin, OUTPUT);
  pinMode(kLeftDirPin, OUTPUT);
  pinMode(kSonarTrigPin, OUTPUT);
  pinMode(kSonarEchoPin, INPUT);
  motors({0, 0});

  servo.attach(kServoPin);
  servo.write(kServoCenterDeg);
  servo_attached = true;
  servo_attach_ms = millis();

  FastLED.addLeds<NEOPIXEL, kLedPin>(leds, kLedCount);
  FastLED.setBrightness(kLedBrightness);

  imuInit();
  yaw_us = micros();
}

void update(uint32_t now_ms) {
  if (servo_attached && now_ms - servo_attach_ms >= kServoSettleMs) {
    servo.detach();
    servo_attached = false;
  }
}

void motors(Out out) {
  digitalWrite(kStbyPin, out.left != 0 || out.right != 0 ? HIGH : LOW);
  motor(kLeftPwmPin, kLeftDirPin, out.left);
  motor(kRightPwmPin, kRightDirPin, out.right);
}

uint16_t sonarCm(uint32_t now_ms) {
  if (sonar_triggered && now_ms - sonar_trigger_ms < kSonarPeriodMs) {
    return sonar_cm;
  }
  sonar_triggered = true;
  sonar_trigger_ms = now_ms;
  digitalWrite(kSonarTrigPin, LOW);
  delayMicroseconds(kSonarSettleUs);
  digitalWrite(kSonarTrigPin, HIGH);
  delayMicroseconds(kSonarTrigPulseUs);
  digitalWrite(kSonarTrigPin, LOW);
  sonar_cm = static_cast<uint16_t>(pulseIn(kSonarEchoPin, HIGH, kSonarTimeoutUs) / kSonarUsPerCm);
  return sonar_cm;
}

uint16_t line(LineSensor sensor) { return static_cast<uint16_t>(analogRead(linePin(sensor))); }

uint16_t battMv() { return static_cast<uint16_t>(analogRead(kBattPin) * kBattVoltsPerStep * kMvPerVolt); }

bool imuOk() { return imu_ok; }

bool gyroBias() {
  motors({0, 0});
  float sum = 0;
  uint32_t count = 0;
  uint32_t start_ms = millis();
  while (millis() - start_ms < kGyroBiasMs) {
    float dps = 0;
    if (!gyroZdps(dps)) {
      return false;
    }
    sum += dps;
    ++count;
  }
  gyro_bias_dps = sum / count;
  yaw_us = micros();
  return true;
}

void updateYaw() {
  uint32_t now_us = micros();
  float dt_s = (now_us - yaw_us) / kUsPerS;
  yaw_us = now_us;
  float dps = 0;
  if (gyroZdps(dps)) {
    yaw_deg += (dps - gyro_bias_dps) * dt_s;
  }
}

float yawDeg() { return yaw_deg; }

void led(LedColor color) {
  if (led_set && color == led_color) {
    return;
  }
  led_set = true;
  led_color = color;
  leds[0] = ledRgb(color);
  FastLED.show();
}

}  // namespace hw
