#pragma once

#include <stdint.h>

#include "proto.h"
#include "safety.h"

constexpr uint16_t kTurnTimeoutMs = 3000;
constexpr int16_t kFastPwmCap = 255;

enum class MotionKind : uint8_t {
  Idle,
  Drive,
  Move,
  Turn,
  Back,
};

const char* motionKindName(MotionKind kind);

struct MotionParams {
  int16_t max_pwm;
  int16_t move_pwm;
  int16_t turn_pwm;
  int16_t turn_slow_pwm;
  float turn_slow_deg;
  float turn_margin;
  float kp;
  int16_t back_pwm;
  uint16_t back_ms;
  uint16_t max_cmd_ms;
};

struct Out {
  int16_t left;
  int16_t right;
};

// Yaw is in degrees, + = right turn. Params are read by reference: a change
// takes effect on the next start().
class Motion {
 public:
  explicit Motion(const MotionParams& params);

  // Accepts Drive, Move, Turn. An active motion ends first with StopReason::Cmd.
  void start(const Cmd& cmd, uint32_t now_ms, float yaw_deg);
  Out step(uint32_t now_ms, float yaw_deg);
  void stop(StopReason reason);
  void cliffBackoff(uint32_t now_ms);

  bool active() const;
  MotionKind kind() const;
  Guard guard() const;
  // Command and reason of the last ended motion.
  CmdType lastCmd() const;
  StopReason lastReason() const;
  // True once after each end of a motion.
  bool takeEnded();

 private:
  void end(StopReason reason);
  Out stepTimed(uint32_t now_ms, Out out);
  Out stepMove(uint32_t now_ms, float yaw_deg);
  Out stepTurn(uint32_t now_ms, float yaw_deg);
  Out stepBack(uint32_t now_ms);
  int16_t pwmCap() const;

  const MotionParams& params_;
  MotionKind kind_ = MotionKind::Idle;
  Cmd cmd_ = {};
  uint32_t start_ms_ = 0;
  uint32_t duration_ms_ = 0;
  bool timeout_at_end_ = false;
  float ref_yaw_deg_ = 0;
  uint32_t back_start_ms_ = 0;
  uint32_t back_duration_ms_ = 0;
  CmdType last_cmd_ = CmdType::Stop;
  StopReason last_reason_ = StopReason::None;
  bool ended_ = false;
};
