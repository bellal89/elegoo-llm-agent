#include "motion.h"

namespace {

constexpr Out kStopped = {0, 0};

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

Motion::Motion(const MotionParams& params) : params_(params) {}

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
  duration_ms_ = cmd.ms < params_.max_cmd_ms ? cmd.ms : params_.max_cmd_ms;
  timeout_at_end_ = cmd.ms > params_.max_cmd_ms;
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

void Motion::cliffBackoff(uint32_t now_ms) {
  if (!active()) {
    return;
  }
  uint32_t forward_ms = now_ms - start_ms_;
  kind_ = MotionKind::Back;
  back_start_ms_ = now_ms;
  back_duration_ms_ = forward_ms < params_.back_ms ? forward_ms : params_.back_ms;
}

bool Motion::active() const { return kind_ != MotionKind::Idle; }

MotionKind Motion::kind() const { return kind_; }

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

CmdType Motion::lastCmd() const { return last_cmd_; }

StopReason Motion::lastReason() const { return last_reason_; }

bool Motion::takeEnded() {
  bool ended = ended_;
  ended_ = false;
  return ended;
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
  float correction = params_.kp * (yaw_deg - ref_yaw_deg_);
  int16_t cap = pwmCap();
  return stepTimed(now_ms, {clampForward(params_.move_pwm - correction, cap),
                            clampForward(params_.move_pwm + correction, cap)});
}

Out Motion::stepTurn(uint32_t now_ms, float yaw_deg) {
  int16_t direction = cmd_.deg > 0 ? 1 : -1;
  float remaining_deg = direction * (ref_yaw_deg_ - yaw_deg);
  if (remaining_deg <= params_.turn_margin) {
    end(StopReason::Done);
    return kStopped;
  }
  if (now_ms - start_ms_ >= kTurnTimeoutMs) {
    end(StopReason::Timeout);
    return kStopped;
  }
  int16_t pwm = remaining_deg < params_.turn_slow_deg ? params_.turn_slow_pwm : params_.turn_pwm;
  return {static_cast<int16_t>(direction * pwm), static_cast<int16_t>(-direction * pwm)};
}

Out Motion::stepBack(uint32_t now_ms) {
  if (now_ms - back_start_ms_ >= back_duration_ms_) {
    end(StopReason::Cliff);
    return kStopped;
  }
  return {static_cast<int16_t>(-params_.back_pwm), static_cast<int16_t>(-params_.back_pwm)};
}

int16_t Motion::pwmCap() const { return cmd_.fast ? kFastPwmCap : params_.max_pwm; }
