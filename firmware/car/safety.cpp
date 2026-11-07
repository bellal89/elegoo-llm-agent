#include "safety.h"

namespace {

// The sonar returns 0 when no echo comes back: nothing is in range.
constexpr uint16_t kSonarNoEcho = 0;

bool lineLost(const Sensors& sensors, const Params& params) {
  // Bit i of line_mask enables the line sensor with LineSensor index i.
  uint8_t mask = static_cast<uint8_t>(params.get(Param::LineMask));
  for (uint8_t i = 0; i < kLineSensorCount; ++i) {
    bool enabled = (mask >> i) & 1u;
    if (enabled && sensors.line[i] > params.get(Param::CliffTh)) {
      return true;
    }
  }
  return false;
}

bool obstacleAhead(const Sensors& sensors, const Params& params) {
  return sensors.sonar_cm != kSonarNoEcho && sensors.sonar_cm < params.get(Param::SonarStopCm);
}

bool movesForward(Guard guard) {
  switch (guard.heading) {
    case Heading::Forward:
      return true;
    case Heading::Other:
      return false;
  }
  return false;
}

}  // namespace

const char* stopReasonName(StopReason reason) {
  switch (reason) {
    case StopReason::None:
      return "none";
    case StopReason::Done:
      return "done";
    case StopReason::Cmd:
      return "cmd";
    case StopReason::Hb:
      return "hb";
    case StopReason::Bridge:
      return "bridge";
    case StopReason::Sonar:
      return "sonar";
    case StopReason::Cliff:
      return "cliff";
    case StopReason::Timeout:
      return "timeout";
    case StopReason::Imu:
      return "imu";
  }
  return "";
}

StopReason checkSafety(const Sensors& sensors, const Params& params, Guard guard) {
  if (sensors.now_ms - sensors.last_hb_ms > static_cast<uint32_t>(params.get(Param::HbMs))) {
    return StopReason::Hb;
  }
  if (guard.needs_imu && !sensors.imu_ok) {
    return StopReason::Imu;
  }
  if (!movesForward(guard)) {
    return StopReason::None;
  }
  if (lineLost(sensors, params)) {
    return StopReason::Cliff;
  }
  if (obstacleAhead(sensors, params)) {
    return StopReason::Sonar;
  }
  return StopReason::None;
}

bool motionAllowed(uint16_t batt_mv, const Params& params) { return batt_mv >= params.get(Param::BattMinMv); }
