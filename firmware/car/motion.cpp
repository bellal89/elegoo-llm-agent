#include "motion.h"

namespace {

constexpr Out kStopped = {0, 0};
constexpr int16_t kFastPwmCap = 255;

int16_t clampSigned(int16_t value, int16_t cap) {
  if (value > cap) {
    return cap;
  }
  if (value < -cap) {
    return -cap;
  }
  return value;
}

int16_t clampForward(float value, int16_t cap) {
  if (value <= 0) {
    return 0;
  }
  if (value >= cap) {
    return cap;
  }
  return static_cast<int16_t>(value + 0.5f);
}

}  // namespace

const char* motionKindName(MotionKind kind) {
  switch (kind) {
    case MotionKind::Idle:
      return "idle";
    case MotionKind::Drive:
      return "drive";
    case MotionKind::Move:
      return "move";
    case MotionKind::Turn:
      return "turn";
    case MotionKind::Back:
      return "back";
  }
  return "";
}

Motion::Motion(const Params& params) : params_(params) {}

void Motion::start(const Cmd& cmd, uint32_t now_ms, float yaw_deg) {
  MotionKind kind = MotionKind::Idle;
  switch (cmd.type) {
    case CmdType::Drive:
      kind = MotionKind::Drive;
      break;
    case CmdType::Move:
      kind = MotionKind::Move;
      break;
    case CmdType::Turn:
      kind = MotionKind::Turn;
      break;
    case CmdType::Hb:
    case CmdType::Stop:
    case CmdType::Gyro:
    case CmdType::Tele:
    case CmdType::Set:
    case CmdType::Get:
    case CmdType::BridgeStop:
    case CmdType::Ignore:
    case CmdType::Err:
      return;
  }
  stop(StopReason::Cmd);
  kind_ = kind;
  cmd_ = cmd;
  start_ms_ = now_ms;
  uint32_t max_cmd_ms = static_cast<uint32_t>(params_.get(Param::MaxCmdMs));
  duration_ms_ = cmd.ms < max_cmd_ms ? cmd.ms : max_cmd_ms;
  timeout_at_end_ = cmd.ms > max_cmd_ms;
  ref_yaw_deg_ = kind == MotionKind::Turn ? yaw_deg + cmd.deg : yaw_deg;
}

Out Motion::step(uint32_t now_ms, float yaw_deg) {
  switch (kind_) {
    case MotionKind::Idle:
      return kStopped;
    case MotionKind::Drive:
      return stepTimed(now_ms, {clampSigned(cmd_.left, pwmCap()), clampSigned(cmd_.right, pwmCap())});
    case MotionKind::Move:
      return stepMove(now_ms, yaw_deg);
    case MotionKind::Turn:
      return stepTurn(now_ms, yaw_deg);
    case MotionKind::Back:
      return stepBack(now_ms);
  }
  return kStopped;
}

void Motion::stop(StopReason reason) {
  if (active()) {
    end(reason);
  }
}

void Motion::applySafety(const Sensors& sensors) {
  if (!active() || kind_ == MotionKind::Back) {
    return;
  }
  StopReason reason = checkSafety(sensors, params_, guard());
  switch (reason) {
    case StopReason::None:
      break;
    case StopReason::Cliff:
      cliffBackoff(sensors.now_ms);
      break;
    case StopReason::Done:
    case StopReason::Cmd:
    case StopReason::Hb:
    case StopReason::Bridge:
    case StopReason::Sonar:
    case StopReason::Timeout:
    case StopReason::Imu:
      end(reason);
      break;
  }
}

bool Motion::active() const { return kind_ != MotionKind::Idle; }

MotionKind Motion::kind() const { return kind_; }

CmdType Motion::lastCmd() const { return last_cmd_; }

StopReason Motion::lastReason() const { return last_reason_; }

bool Motion::takeEnded() {
  bool ended = ended_;
  ended_ = false;
  return ended;
}

Guard Motion::guard() const {
  switch (kind_) {
    case MotionKind::Drive:
      return {cmd_.left > 0 && cmd_.right > 0 ? Heading::Forward : Heading::Other, false};
    case MotionKind::Move:
      return {Heading::Forward, true};
    case MotionKind::Turn:
      return {Heading::Other, true};
    case MotionKind::Idle:
    case MotionKind::Back:
      return {Heading::Other, false};
  }
  return {Heading::Other, false};
}

void Motion::cliffBackoff(uint32_t now_ms) {
  uint32_t forward_ms = now_ms - start_ms_;
  uint32_t back_ms = static_cast<uint32_t>(params_.get(Param::BackMs));
  kind_ = MotionKind::Back;
  back_start_ms_ = now_ms;
  back_duration_ms_ = forward_ms < back_ms ? forward_ms : back_ms;
}

void Motion::end(StopReason reason) {
  kind_ = MotionKind::Idle;
  last_cmd_ = cmd_.type;
  last_reason_ = reason;
  ended_ = true;
}

Out Motion::stepTimed(uint32_t now_ms, Out out) {
  if (now_ms - start_ms_ >= duration_ms_) {
    end(timeout_at_end_ ? StopReason::Timeout : StopReason::Done);
    return kStopped;
  }
  return out;
}

Out Motion::stepMove(uint32_t now_ms, float yaw_deg) {
  float correction = params_.get(Param::Kp) * (yaw_deg - ref_yaw_deg_);
  float move_pwm = params_.get(Param::MovePwm);
  int16_t cap = pwmCap();
  return stepTimed(now_ms, {clampForward(move_pwm - correction, cap), clampForward(move_pwm + correction, cap)});
}

Out Motion::stepTurn(uint32_t now_ms, float yaw_deg) {
  int16_t direction = cmd_.deg > 0 ? 1 : -1;
  float remaining_deg = direction * (ref_yaw_deg_ - yaw_deg);
  if (remaining_deg <= params_.get(Param::TurnMargin)) {
    end(StopReason::Done);
    return kStopped;
  }
  if (now_ms - start_ms_ >= kTurnTimeoutMs) {
    end(StopReason::Timeout);
    return kStopped;
  }
  int16_t turn_pwm = pwm(remaining_deg < params_.get(Param::TurnSlowDeg) ? Param::TurnSlowPwm : Param::TurnPwm);
  return {static_cast<int16_t>(direction * turn_pwm), static_cast<int16_t>(-direction * turn_pwm)};
}

Out Motion::stepBack(uint32_t now_ms) {
  if (now_ms - back_start_ms_ >= back_duration_ms_) {
    end(StopReason::Cliff);
    return kStopped;
  }
  int16_t back_pwm = pwm(Param::BackPwm);
  return {static_cast<int16_t>(-back_pwm), static_cast<int16_t>(-back_pwm)};
}

int16_t Motion::pwm(Param param) const { return static_cast<int16_t>(params_.get(param)); }

int16_t Motion::pwmCap() const { return cmd_.fast ? kFastPwmCap : pwm(Param::MaxPwm); }
