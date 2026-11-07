#include <stdint.h>
#include <string.h>

#include "check.h"
#include "safety.h"

constexpr uint16_t kFloor = 500;
constexpr uint16_t kNoFloor = 1017;
constexpr uint8_t kAllLineSensors = 0b111;
constexpr uint8_t kNoLeftSensor = 0b110;
constexpr Guard kForward = {Heading::Forward, false};
constexpr Guard kOther = {Heading::Other, false};

static Limits limits() {
  Limits value = {};
  value.hb_ms = 300;
  value.sonar_stop_cm = 25;
  value.cliff_th = 950;
  value.batt_min_mv = 7000;
  value.line_mask = kAllLineSensors;
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

static void testSafeSensors() { CHECK(checkSafety(safeSensors(), limits(), kForward) == StopReason::None); }

static void testHeartbeat() {
  Sensors sensors = safeSensors();
  sensors.now_ms = sensors.last_hb_ms + 301;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::Hb);
  CHECK(checkSafety(sensors, limits(), kOther) == StopReason::Hb);

  sensors.now_ms = sensors.last_hb_ms + 300;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::None);
}

static void testHeartbeatAcrossMillisWrap() {
  Sensors sensors = safeSensors();
  sensors.last_hb_ms = UINT32_MAX - 100;
  sensors.now_ms = 100;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::None);

  sensors.now_ms = 250;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::Hb);
}

static void testImu() {
  Sensors sensors = safeSensors();
  sensors.imu_ok = false;
  CHECK(checkSafety(sensors, limits(), {Heading::Forward, true}) == StopReason::Imu);
  CHECK(checkSafety(sensors, limits(), {Heading::Other, true}) == StopReason::Imu);
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::None);
}

static void testCliff() {
  for (uint8_t i = 0; i < kLineSensorCount; ++i) {
    Sensors sensors = safeSensors();
    sensors.line[i] = 951;
    CHECK(checkSafety(sensors, limits(), kForward) == StopReason::Cliff);
    CHECK(checkSafety(sensors, limits(), kOther) == StopReason::None);
  }
  Sensors atThreshold = safeSensors();
  atThreshold.line[static_cast<uint8_t>(LineSensor::Middle)] = 950;
  CHECK(checkSafety(atThreshold, limits(), kForward) == StopReason::None);
}

static void testLineMask() {
  Limits noLeft = limits();
  noLeft.line_mask = kNoLeftSensor;
  Sensors deadLeft = safeSensors();
  deadLeft.line[static_cast<uint8_t>(LineSensor::Left)] = kNoFloor;
  CHECK(checkSafety(deadLeft, noLeft, kForward) == StopReason::None);
  CHECK(checkSafety(deadLeft, limits(), kForward) == StopReason::Cliff);

  Sensors middleLost = safeSensors();
  middleLost.line[static_cast<uint8_t>(LineSensor::Middle)] = kNoFloor;
  CHECK(checkSafety(middleLost, noLeft, kForward) == StopReason::Cliff);
}

static void testSonar() {
  Sensors sensors = safeSensors();
  sensors.sonar_cm = 0;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::None);

  sensors.sonar_cm = 1;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::Sonar);
  sensors.sonar_cm = 24;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::Sonar);
  CHECK(checkSafety(sensors, limits(), kOther) == StopReason::None);

  sensors.sonar_cm = 25;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::None);
}

static void testPriority() {
  Sensors sensors = safeSensors();
  sensors.sonar_cm = 10;
  sensors.line[0] = 1000;
  CHECK(checkSafety(sensors, limits(), kForward) == StopReason::Cliff);

  sensors.imu_ok = false;
  CHECK(checkSafety(sensors, limits(), {Heading::Forward, true}) == StopReason::Imu);

  sensors.now_ms = sensors.last_hb_ms + 1000;
  CHECK(checkSafety(sensors, limits(), {Heading::Forward, true}) == StopReason::Hb);
}

static void testMotionAllowed() {
  Sensors sensors = safeSensors();
  sensors.batt_mv = 7000;
  CHECK(motionAllowed(sensors, limits()));
  sensors.batt_mv = 6999;
  CHECK(!motionAllowed(sensors, limits()));
}

static void testStopReasonNames() {
  CHECK(strcmp(stopReasonName(StopReason::None), "none") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Done), "done") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Cmd), "cmd") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Hb), "hb") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Bridge), "bridge") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Sonar), "sonar") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Cliff), "cliff") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Timeout), "timeout") == 0);
  CHECK(strcmp(stopReasonName(StopReason::Imu), "imu") == 0);
}

int main() {
  testSafeSensors();
  testHeartbeat();
  testHeartbeatAcrossMillisWrap();
  testImu();
  testCliff();
  testLineMask();
  testSonar();
  testPriority();
  testMotionAllowed();
  testStopReasonNames();
  return checkSummary("test_safety");
}
