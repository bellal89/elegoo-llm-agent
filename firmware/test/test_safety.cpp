#include <stdint.h>

#include "check.h"
#include "safety.h"

constexpr uint16_t kFloor = 500;
constexpr uint16_t kNoFloor = 1017;
constexpr float kNoLeftSensor = 0b110;
constexpr Guard kForward = {Heading::Forward, false};
constexpr Guard kOther = {Heading::Other, false};

static Params params() {
  Params value;
  value.set(Param::HbMs, 300);
  return value;
}

static Sensors safeSensors() {
  Sensors value = {};
  value.now_ms = 10000;
  value.last_hb_ms = 10000;
  value.sonar_cm = 100;
  for (uint16_t& level : value.line) {
    level = kFloor;
  }
  value.batt_mv = 7400;
  value.imu_ok = true;
  return value;
}

static void testHeartbeat() {
  Sensors sensors = safeSensors();
  sensors.now_ms = sensors.last_hb_ms + 301;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::Hb);
  CHECK(checkSafety(sensors, params(), kOther) == StopReason::Hb);

  sensors.now_ms = sensors.last_hb_ms + 300;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::None);
}

static void testHeartbeatAcrossMillisWrap() {
  Sensors sensors = safeSensors();
  sensors.last_hb_ms = UINT32_MAX - 100;
  sensors.now_ms = UINT32_MAX - 50;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::None);

  sensors.now_ms = 100;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::None);

  sensors.now_ms = 250;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::Hb);
}

static void testImu() {
  Sensors sensors = safeSensors();
  sensors.imu_ok = false;
  CHECK(checkSafety(sensors, params(), {Heading::Forward, true}) == StopReason::Imu);
  CHECK(checkSafety(sensors, params(), {Heading::Other, true}) == StopReason::Imu);
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::None);
}

static void testCliff() {
  for (uint8_t i = 0; i < kLineSensorCount; ++i) {
    Sensors sensors = safeSensors();
    sensors.line[i] = 951;
    CHECK(checkSafety(sensors, params(), kForward) == StopReason::Cliff);
    CHECK(checkSafety(sensors, params(), kOther) == StopReason::None);
  }
  Sensors atThreshold = safeSensors();
  atThreshold.line[static_cast<uint8_t>(LineSensor::Middle)] = 950;
  CHECK(checkSafety(atThreshold, params(), kForward) == StopReason::None);
}

static void testLineMask() {
  Params noLeft = params();
  noLeft.set(Param::LineMask, kNoLeftSensor);
  Sensors deadLeft = safeSensors();
  deadLeft.line[static_cast<uint8_t>(LineSensor::Left)] = kNoFloor;
  CHECK(checkSafety(deadLeft, noLeft, kForward) == StopReason::None);

  Sensors middleLost = safeSensors();
  middleLost.line[static_cast<uint8_t>(LineSensor::Middle)] = kNoFloor;
  CHECK(checkSafety(middleLost, noLeft, kForward) == StopReason::Cliff);
}

static void testSonar() {
  Sensors sensors = safeSensors();
  sensors.sonar_cm = 0;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::None);

  sensors.sonar_cm = 24;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::Sonar);
  CHECK(checkSafety(sensors, params(), kOther) == StopReason::None);

  sensors.sonar_cm = 25;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::None);
}

static void testPriority() {
  Sensors sensors = safeSensors();
  sensors.sonar_cm = 10;
  sensors.line[0] = 1000;
  CHECK(checkSafety(sensors, params(), kForward) == StopReason::Cliff);

  sensors.imu_ok = false;
  CHECK(checkSafety(sensors, params(), {Heading::Forward, true}) == StopReason::Imu);

  sensors.now_ms = sensors.last_hb_ms + 1000;
  CHECK(checkSafety(sensors, params(), {Heading::Forward, true}) == StopReason::Hb);
}

static void testMotionAllowed() {
  CHECK(motionAllowed(7000, params()));
  CHECK(!motionAllowed(6999, params()));
}

int main() {
  testHeartbeat();
  testHeartbeatAcrossMillisWrap();
  testImu();
  testCliff();
  testLineMask();
  testSonar();
  testPriority();
  testMotionAllowed();
  return checkSummary("test_safety");
}
