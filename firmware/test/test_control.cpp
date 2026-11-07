#include "check.h"
#include "control.h"

constexpr uint32_t kNowMs = 10000;
constexpr uint16_t kFloor = 500;
constexpr uint16_t kNoFloor = 1017;

static Params distinctParams() {
  Params params;
  params.set(Param::MaxPwm, 11);
  params.set(Param::MovePwm, 12);
  params.set(Param::TurnPwm, 13);
  params.set(Param::TurnSlowPwm, 14);
  params.set(Param::TurnSlowDeg, 15.5f);
  params.set(Param::TurnMargin, 16.5f);
  params.set(Param::Kp, 17.5f);
  params.set(Param::SonarStopCm, 18);
  params.set(Param::CliffTh, 19);
  params.set(Param::BackPwm, 20);
  params.set(Param::BackMs, 21);
  params.set(Param::MaxCmdMs, 122);
  params.set(Param::BattMinMv, 6023);
  params.set(Param::HbMs, 124);
  params.set(Param::LineMask, 5);
  return params;
}

static Sensors safeSensors() {
  Sensors value = {};
  value.now_ms = kNowMs;
  value.last_hb_ms = kNowMs;
  value.sonar_cm = 100;
  for (uint16_t& level : value.line) {
    level = kFloor;
  }
  value.batt_mv = 7400;
  value.imu_ok = true;
  return value;
}

static Cmd forwardCmd() {
  Cmd cmd = {};
  cmd.type = CmdType::Drive;
  cmd.left = 100;
  cmd.right = 100;
  cmd.ms = 1000;
  return cmd;
}

static void testMotionParamsFrom() {
  MotionParams value = motionParamsFrom(distinctParams());
  CHECK(value.max_pwm == 11);
  CHECK(value.move_pwm == 12);
  CHECK(value.turn_pwm == 13);
  CHECK(value.turn_slow_pwm == 14);
  CHECK(value.turn_slow_deg == 15.5f);
  CHECK(value.turn_margin == 16.5f);
  CHECK(value.kp == 17.5f);
  CHECK(value.back_pwm == 20);
  CHECK(value.back_ms == 21);
  CHECK(value.max_cmd_ms == 122);
}

static void testLimitsFrom() {
  Limits value = limitsFrom(distinctParams());
  CHECK(value.sonar_stop_cm == 18);
  CHECK(value.cliff_th == 19);
  CHECK(value.batt_min_mv == 6023);
  CHECK(value.hb_ms == 124);
  CHECK(value.line_mask == 5);
}

static void testResetsHeartbeat() {
  CHECK(resetsHeartbeat(CmdType::Hb));
  CHECK(resetsHeartbeat(CmdType::Drive));
  CHECK(!resetsHeartbeat(CmdType::BridgeStop));
  CHECK(!resetsHeartbeat(CmdType::Ignore));
  CHECK(!resetsHeartbeat(CmdType::Err));
}

static void testSafetyStopsMotion() {
  Params params;
  MotionParams motion_params = motionParamsFrom(params);
  Limits limits = limitsFrom(params);
  Motion motion(motion_params);
  motion.start(forwardCmd(), kNowMs, 0);

  checkMotionSafety(motion, safeSensors(), limits);
  CHECK(motion.active());

  Sensors obstacle = safeSensors();
  obstacle.sonar_cm = 5;
  checkMotionSafety(motion, obstacle, limits);
  CHECK(!motion.active());
  CHECK(motion.lastReason() == StopReason::Sonar);
}

static void testCliffStartsBackoffWithoutRecheck() {
  Params params;
  MotionParams motion_params = motionParamsFrom(params);
  Limits limits = limitsFrom(params);
  Motion motion(motion_params);
  motion.start(forwardCmd(), kNowMs, 0);

  Sensors cliff = safeSensors();
  cliff.now_ms = kNowMs + 200;
  cliff.line[static_cast<uint8_t>(LineSensor::Middle)] = kNoFloor;
  checkMotionSafety(motion, cliff, limits);
  CHECK(motion.kind() == MotionKind::Back);
  CHECK(!motion.takeEnded());

  cliff.last_hb_ms = 0;
  checkMotionSafety(motion, cliff, limits);
  CHECK(motion.kind() == MotionKind::Back);
}

int main() {
  testMotionParamsFrom();
  testLimitsFrom();
  testResetsHeartbeat();
  testSafetyStopsMotion();
  testCliffStartsBackoffWithoutRecheck();
  return checkSummary("test_control");
}
