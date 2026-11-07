#include "safety.h"

namespace {

// The sonar returns 0 when no echo comes back: nothing is in range.
constexpr uint16_t kSonarNoEcho = 0;

bool lineLost(const Sensors& sensors, const Limits& limits) {
  for (uint8_t i = 0; i < kLineSensorCount; ++i) {
    bool enabled = (limits.line_mask >> i) & 1u;
    if (enabled && sensors.line[i] > limits.cliff_th) {
      return true;
    }
  }
  return false;
}

bool obstacleAhead(const Sensors& sensors, const Limits& limits) {
  return sensors.sonar_cm != kSonarNoEcho && sensors.sonar_cm < limits.sonar_stop_cm;
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

StopReason checkSafety(const Sensors& sensors, const Limits& limits, Guard guard) {
  if (sensors.now_ms - sensors.last_hb_ms > limits.hb_ms) {
    return StopReason::Hb;
  }
  if (guard.needs_imu && !sensors.imu_ok) {
    return StopReason::Imu;
  }
  if (!movesForward(guard)) {
    return StopReason::None;
  }
  if (lineLost(sensors, limits)) {
    return StopReason::Cliff;
  }
  if (obstacleAhead(sensors, limits)) {
    return StopReason::Sonar;
  }
  return StopReason::None;
}

bool motionAllowed(const Sensors& sensors, const Limits& limits) {
  return sensors.batt_mv >= limits.batt_min_mv;
}
