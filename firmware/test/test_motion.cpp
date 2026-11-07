#include "check.h"
#include "motion.h"

constexpr uint32_t kStartMs = 1000;

static MotionParams defaults() {
  MotionParams params = {};
  params.max_pwm = 100;
  params.move_pwm = 100;
  params.turn_pwm = 110;
  params.turn_slow_pwm = 90;
  params.turn_slow_deg = 20;
  params.turn_margin = 5;
  params.kp = 4;
  params.back_pwm = 90;
  params.back_ms = 300;
  params.max_cmd_ms = 5000;
  return params;
}

static Cmd driveCmd(int16_t left, int16_t right, uint16_t ms, bool fast) {
  Cmd cmd = {};
  cmd.type = CmdType::Drive;
  cmd.left = left;
  cmd.right = right;
  cmd.ms = ms;
  cmd.fast = fast;
  return cmd;
}

static Cmd moveCmd(uint16_t ms, bool fast) {
  Cmd cmd = {};
  cmd.type = CmdType::Move;
  cmd.ms = ms;
  cmd.fast = fast;
  return cmd;
}

static Cmd turnCmd(int16_t deg) {
  Cmd cmd = {};
  cmd.type = CmdType::Turn;
  cmd.deg = deg;
  return cmd;
}

static bool outIs(Out out, int16_t left, int16_t right) { return out.left == left && out.right == right; }

static void testIdle() {
  MotionParams params = defaults();
  Motion motion(params);
  CHECK(!motion.active());
  CHECK(motion.kind() == MotionKind::Idle);
  CHECK(motion.lastReason() == StopReason::None);
  CHECK(outIs(motion.step(kStartMs, 0), 0, 0));
  CHECK(!motion.takeEnded());
}

static void testDriveCappedAndDone() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(driveCmd(150, 150, 500, false), kStartMs, 0);
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

static void testDriveFastAndReverse() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(driveCmd(150, 150, 500, true), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 150, 150));

  motion.start(driveCmd(-150, 50, 500, false), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), -100, 50));
}

static void testDriveTimeout() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(driveCmd(100, 100, 5000, false), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 5000, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);

  motion.start(driveCmd(100, 100, 5001, false), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 4999, 0), 100, 100));
  CHECK(outIs(motion.step(kStartMs + 5000, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Timeout);
}

static void testTurnRight() {
  MotionParams params = defaults();
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
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(turnCmd(-90), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), -110, 110));
  CHECK(outIs(motion.step(kStartMs + 20, -100), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
}

static void testTurnFromNonZeroYaw() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 400);
  CHECK(outIs(motion.step(kStartMs + 10, 480), 90, -90));
  CHECK(outIs(motion.step(kStartMs + 20, 485), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
}

static void testTurnInsideMarginEndsAtOnce() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(turnCmd(3), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
}

static void testTurnIgnoresMaxPwm() {
  MotionParams params = defaults();
  params.max_pwm = 50;
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, 0), 110, -110));
}

static void testTurnTimeout() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + kTurnTimeoutMs - 1, 10), 110, -110));
  CHECK(outIs(motion.step(kStartMs + kTurnTimeoutMs, 10), 0, 0));
  CHECK(motion.lastReason() == StopReason::Timeout);
}

static void testMoveHoldsHeading() {
  MotionParams params = defaults();
  params.move_pwm = 80;
  Motion motion(params);
  motion.start(moveCmd(1000, false), kStartMs, 10);
  CHECK(outIs(motion.step(kStartMs + 10, 10), 80, 80));
  CHECK(outIs(motion.step(kStartMs + 20, 12.1f), 72, 88));
  CHECK(outIs(motion.step(kStartMs + 30, -20), 100, 0));
  CHECK(outIs(motion.step(kStartMs + 1000, 10), 0, 0));
  CHECK(motion.lastReason() == StopReason::Done);
  CHECK(motion.lastCmd() == CmdType::Move);
}

static void testMoveFast() {
  MotionParams params = defaults();
  params.move_pwm = 80;
  Motion motion(params);
  motion.start(moveCmd(1000, true), kStartMs, 0);
  CHECK(outIs(motion.step(kStartMs + 10, -10), 120, 40));
}

static void testGuard() {
  MotionParams params = defaults();
  Motion motion(params);
  CHECK(motion.guard().heading == Heading::Other);
  CHECK(!motion.guard().needs_imu);

  motion.start(moveCmd(1000, false), kStartMs, 0);
  CHECK(motion.guard().heading == Heading::Forward);
  CHECK(motion.guard().needs_imu);

  motion.start(turnCmd(90), kStartMs, 0);
  CHECK(motion.guard().heading == Heading::Other);
  CHECK(motion.guard().needs_imu);

  motion.start(driveCmd(100, 100, 500, false), kStartMs, 0);
  CHECK(motion.guard().heading == Heading::Forward);
  CHECK(!motion.guard().needs_imu);

  motion.start(driveCmd(100, -100, 500, false), kStartMs, 0);
  CHECK(motion.guard().heading == Heading::Other);

  motion.start(driveCmd(100, 0, 500, false), kStartMs, 0);
  CHECK(motion.guard().heading == Heading::Other);
}

static void testNewCommandPreempts() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(turnCmd(90), kStartMs, 0);
  motion.start(driveCmd(60, 60, 500, false), kStartMs + 100, 0);
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

static void testStopAndBackoffWhileIdle() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.cliffBackoff(kStartMs);
  CHECK(!motion.active());
  motion.stop(StopReason::Cmd);
  CHECK(!motion.takeEnded());
  CHECK(motion.lastReason() == StopReason::None);
}

static void testParamsChangeAppliesToActiveMotion() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(driveCmd(100, 100, 500, false), kStartMs, 0);
  params.max_pwm = 60;
  CHECK(outIs(motion.step(kStartMs + 10, 0), 60, 60));
}

static void testCliffBackoffShorterThanForward() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(moveCmd(2000, false), kStartMs, 0);
  motion.step(kStartMs + 200, 0);
  motion.cliffBackoff(kStartMs + 200);
  CHECK(motion.kind() == MotionKind::Back);
  CHECK(motion.active());
  CHECK(!motion.takeEnded());
  CHECK(motion.guard().heading == Heading::Other);
  CHECK(outIs(motion.step(kStartMs + 210, 0), -90, -90));
  CHECK(outIs(motion.step(kStartMs + 399, 0), -90, -90));
  CHECK(outIs(motion.step(kStartMs + 400, 0), 0, 0));
  CHECK(!motion.active());
  CHECK(motion.takeEnded());
  CHECK(motion.lastReason() == StopReason::Cliff);
  CHECK(motion.lastCmd() == CmdType::Move);
}

static void testCliffBackoffCappedByBackMs() {
  MotionParams params = defaults();
  Motion motion(params);
  motion.start(driveCmd(100, 100, 3000, false), kStartMs, 0);
  motion.cliffBackoff(kStartMs + 1000);
  CHECK(outIs(motion.step(kStartMs + 1299, 0), -90, -90));
  CHECK(outIs(motion.step(kStartMs + 1300, 0), 0, 0));
  CHECK(motion.lastReason() == StopReason::Cliff);
  CHECK(motion.lastCmd() == CmdType::Drive);
}

int main() {
  testIdle();
  testDriveCappedAndDone();
  testDriveFastAndReverse();
  testDriveTimeout();
  testTurnRight();
  testTurnLeftOvershoot();
  testTurnFromNonZeroYaw();
  testTurnInsideMarginEndsAtOnce();
  testTurnIgnoresMaxPwm();
  testTurnTimeout();
  testMoveHoldsHeading();
  testMoveFast();
  testGuard();
  testNewCommandPreempts();
  testStopAndBackoffWhileIdle();
  testParamsChangeAppliesToActiveMotion();
  testCliffBackoffShorterThanForward();
  testCliffBackoffCappedByBackMs();
  return checkSummary("test_motion");
}
