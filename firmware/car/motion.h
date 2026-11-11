#pragma once

#include <stdint.h>

#include "params.h"
#include "proto.h"
#include "safety.h"

constexpr uint16_t kTurnTimeoutMs = 3000;

enum class MotionKind : uint8_t {
  Idle,
  Drive,
  Move,
  Turn,
  Back,
};

const char* motionKindName(MotionKind kind);

struct Out {
  int16_t left;
  int16_t right;
};

// Yaw is in degrees, + = right turn. Params are read by reference: a change
// takes effect at once, also for an active motion.
class Motion {
 public:
  explicit Motion(const Params& params);

  // Accepts Drive, Move, Turn. An active motion ends first with StopReason::Cmd.
  void start(const Cmd& cmd, uint32_t now_ms, float yaw_deg);
  Out step(uint32_t now_ms, float yaw_deg);
  void stop(StopReason reason);
  // Stops the motion on a safety stop; on a cliff, starts the back-off.
  // Skips the check during the back-off: the car must back off the edge.
  void applySafety(const Sensors& sensors);

  bool active() const;
  MotionKind kind() const;
  // Command and reason of the last ended motion.
  CmdType lastCmd() const;
  StopReason lastReason() const;
  // True once after each end of a motion.
  bool takeEnded();

 private:
  Guard guard() const;
  void cliffBackoff(uint32_t now_ms);
  void end(StopReason reason);
  Out stepTimed(uint32_t now_ms, Out out);
  Out stepMove(uint32_t now_ms, float yaw_deg);
  Out stepTurn(uint32_t now_ms, float yaw_deg);
  Out stepBack(uint32_t now_ms);
  int16_t pwm(Param param) const;

  const Params& params_;
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
