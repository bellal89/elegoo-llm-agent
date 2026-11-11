#include "check.h"
#include "motion.h"

constexpr uint32_t kStartMs = 1000;
constexpr uint16_t kFloor = 500;
constexpr uint16_t kNoFloor = 1017;
constexpr uint16_t kObstacleCm = 5;

static Cmd driveCmd(int16_t left, int16_t right, uint16_t ms) {
  Cmd cmd = {};
  cmd.type = CmdType::Drive;
  cmd.left = left;
  cmd.right = right;
  cmd.ms = ms;
  return cmd;
}

static Cmd moveCmd(uint16_t ms) {
  Cmd cmd = {};
  cmd.type = CmdType::Move;
  cmd.ms = ms;
  return cmd;
}

static Cmd turnCmd(int16_t deg) {
  Cmd cmd = {};
  cmd.type = CmdType::Turn;
  cmd.deg = deg;
  return cmd;
}

static Sensors safeSensors(uint32_t now_ms) {
  Sensors value = {};
  value.now_ms = now_ms;
  value.last_hb_ms = now_ms;
  value.sonar_cm = 100;
  for (uint16_t& level : value.line) {
    level = kFloor;
  }
  value.batt_mv = 7400;
  value.imu_ok = true;
  return value;
}

static Sensors obstacle(uint32_t now_ms) {
  Sensors value = safeSensors(now_ms);
  value.sonar_cm = kObstacleCm;
  return value;
}

static Sensors imuLost(uint32_t now_ms) {
  Sensors value = safeSensors(now_ms);
  value.imu_ok = false;
  return value;
}

static Sensors cliff(uint32_t now_ms) {
  Sensors value = safeSensors(now_ms);
  value.line[static_cast<uint8_t>(LineSensor::Middle)] = kNoFloor;
  return value;
}

static bool outIs(Out out, int16_t left, int16_t right) { return out.left == left && out.right == right; }

static void testIdle() {
  Params params;
  Motion motion(params);
  CHECK(!motion.active());
  CHECK(motion.kind() == MotionKind::Idle);
  CHECK(motion.lastReason() == StopReason::None);
  CHECK(outIs(motion.step(kStartMs, 0), 0, 0));
  CHECK(!motion.takeEnded());

  motion.applySafety(cliff(kStartMs));
  motion.stop(StopReason::Cmd);
  CHECK(!motion.active());
  CHECK(!motion.takeEnded());
  CHECK(motion.lastReason() == StopReason::None);
}

static void testDriveCappedAndDone() {
  Params params;
  Motion motion(params);
  motion.start(driveCmd(150, 150, 500), kStartMs, 0);
  CHECK(motion.active());
  CHECK(motion.kind() == MotionKind::Drive);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 100, 100));
  CHECK(outIs(motion.step(kStartMs + 499, 0), 100, 100));
  CHECK(outIs(motion.step(kStartMs + 500, 0), 0, 0));
  CHECK(!motion.active());
  CHECK(motion.lastReason() == StopReason::Done);
  CHECK(motion.lastCmd() == CmdType::Drive);
  CHECK(motion.takeEnded());
  CHECK(!motion.takeEnded());
}

static void testDriveReverseCapped() {
  Params params;
  Motion motion(params);
  motion.start(driveCmd(-150, 50, 500), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), -100, 50));
}

static void testDriveTimeout() {
  Params params;
  Motion motion(params);
  motion.start(driveCmd(100, 100, 5000), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 5000, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);

  motion.start(driveCmd(100, 100, 5001), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 4999, 0), 100, 100));
  CHECK(outIs(motion.step(kStartMs + 5000, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Timeout);
}

static void testTurnRight() {
  Params params;
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  CHECK(motion.kind() == MotionKind::Turn);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 110, -110));
  CHECK(outIs(motion.step(kStartMs + 20, 75), 90, -90));
  CHECK(outIs(motion.step(kStartMs + 30, 85), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
  CHECK(motion.lastCmd() == CmdType::Turn);
}

static void testTurnLeftOvershoot() {
  Params params;
  Motion motion(params);
  motion.start(turnCmd(-90), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), -110, 110));
  CHECK(outIs(motion.step(kStartMs + 20, -100), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
}

static void testTurnFromNonZeroYaw() {
  Params params;
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 400);
  CHECK(outIs(motion.step(kStartMs + 10, 480), 90, -90));
  CHECK(outIs(motion.step(kStartMs + 20, 485), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
}

static void testTurnIgnoresMaxPwm() {
  Params params;
  params.set(Param::MaxPwm, 50);
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 110, -110));
}

static void testTurnTimeout() {
  Params params;
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + kTurnTimeoutMs - 1, 10), 110, -110));
  CHECK(outIs(motion.step(kStartMs + kTurnTimeoutMs, 10), 0, 0));
  CHECK(motion.lastReason() == StopReason::Timeout);
}

static void testMoveHoldsHeading() {
  Params params;
  params.set(Param::MovePwm, 80);
  Motion motion(params);
  motion.start(moveCmd(1000), kStartMs, 10);
  CHECK(outIs(motion.step(kStartMs + 10, 10), 80, 80));
  CHECK(outIs(motion.step(kStartMs + 20, 12.1f), 72, 88));
  CHECK(outIs(motion.step(kStartMs + 30, -20), 100, 0));
  CHECK(outIs(motion.step(kStartMs + 1000, 10), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
  CHECK(motion.lastCmd() == CmdType::Move);
}

static bool stopsOn(const Cmd& cmd, const Sensors& sensors, StopReason reason) {
  Params params;
  Motion motion(params);
  motion.start(cmd, sensors.now_ms, 0);
  motion.applySafety(sensors);
  return reason == StopReason::None ? motion.active() : !motion.active() && motion.lastReason() == reason;
}

static void testSafetyByMotionKind() {
  CHECK(stopsOn(driveCmd(100, 100, 500), obstacle(kStartMs), StopReason::Sonar));
  CHECK(stopsOn(driveCmd(100, -100, 500), obstacle(kStartMs), StopReason::None));
  CHECK(stopsOn(driveCmd(100, 0, 500), obstacle(kStartMs), StopReason::None));
  CHECK(stopsOn(driveCmd(100, 100, 500), imuLost(kStartMs), StopReason::None));
  CHECK(stopsOn(moveCmd(1000), obstacle(kStartMs), StopReason::Sonar));
  CHECK(stopsOn(moveCmd(1000), imuLost(kStartMs), StopReason::Imu));
  CHECK(stopsOn(turnCmd(90), obstacle(kStartMs), StopReason::None));
  CHECK(stopsOn(turnCmd(90), imuLost(kStartMs), StopReason::Imu));
}

static void testNewCommandPreempts() {
  Params params;
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  motion.start(driveCmd(60, 60, 500), kStartMs + 100, 0);
  CHECK(motion.takeEnded());
  CHECK(motion.lastCmd() == CmdType::Turn);
  CHECK(motion.lastReason() == StopReason::Cmd);
  CHECK(motion.kind() == MotionKind::Drive);
  CHECK(outIs(motion.step(kStartMs + 110, 0), 60, 60));

  motion.stop(StopReason::Cmd);
  CHECK(outIs(motion.step(kStartMs + 120, 0), 0, 0));
  CHECK(!motion.active());
  CHECK(motion.takeEnded());
  CHECK(motion.lastCmd() == CmdType::Drive);
  CHECK(motion.lastReason() == StopReason::Cmd);
}

static void testParamsChangeAppliesToActiveMotion() {
  Params params;
  Motion motion(params);
  motion.start(driveCmd(100, 100, 500), kStartMs, 0);
  params.set(Param::MaxPwm, 60);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 60, 60));
}

static void testCliffBackoffShorterThanForward() {
  Params params;
  Motion motion(params);
  motion.start(moveCmd(2000), kStartMs, 0);
  motion.step(kStartMs + 200, 0);
  motion.applySafety(cliff(kStartMs + 200));
  CHECK(motion.kind() == MotionKind::Back);
  CHECK(!motion.takeEnded());
  CHECK(outIs(motion.step(kStartMs + 210, 0), -90, -90));

  Sensors heartbeatLost = cliff(kStartMs + 300);
  heartbeatLost.last_hb_ms = 0;
  motion.applySafety(heartbeatLost);
  CHECK(motion.kind() == MotionKind::Back);

  CHECK(outIs(motion.step(kStartMs + 399, 0), -90, -90));
  CHECK(outIs(motion.step(kStartMs + 400, 0), 0, 0));
  CHECK(!motion.active());
  CHECK(motion.takeEnded());
  CHECK(motion.lastReason() == StopReason::Cliff);
  CHECK(motion.lastCmd() == CmdType::Move);
}

static void testCliffBackoffCappedByBackMs() {
  Params params;
  Motion motion(params);
  motion.start(driveCmd(100, 100, 3000), kStartMs, 0);
  motion.applySafety(cliff(kStartMs + 1000));
  CHECK(outIs(motion.step(kStartMs + 1299, 0), -90, -90));
  CHECK(outIs(motion.step(kStartMs + 1300, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Cliff);
  CHECK(motion.lastCmd() == CmdType::Drive);
}

int main() {
  testIdle();
  testDriveCappedAndDone();
  testDriveReverseCapped();
  testDriveTimeout();
  testTurnRight();
  testTurnLeftOvershoot();
  testTurnFromNonZeroYaw();
  testTurnIgnoresMaxPwm();
  testTurnTimeout();
  testMoveHoldsHeading();
  testSafetyByMotionKind();
  testNewCommandPreempts();
  testParamsChangeAppliesToActiveMotion();
  testCliffBackoffShorterThanForward();
  testCliffBackoffCappedByBackMs();
  return checkSummary("test_motion");
}
