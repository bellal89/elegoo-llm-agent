#pragma once

#include <stdint.h>

#include "params.h"

enum class StopReason : uint8_t {
  None,
  Done,
  Cmd,
  Hb,
  Bridge,
  Sonar,
  Cliff,
  Timeout,
  Imu,
};

const char* stopReasonName(StopReason reason);

enum class LineSensor : uint8_t {
  Left,
  Middle,
  Right,
};

constexpr uint8_t kLineSensorCount = 3;

struct Sensors {
  uint32_t now_ms;
  uint32_t last_hb_ms;
  uint16_t sonar_cm;
  uint16_t line[kLineSensorCount];
  uint16_t batt_mv;
  bool imu_ok;
};

enum class Heading : uint8_t {
  Forward,
  Other,
};

struct Guard {
  Heading heading;
  bool needs_imu;
};

StopReason checkSafety(const Sensors& sensors, const Params& params, Guard guard);
bool motionAllowed(uint16_t batt_mv, const Params& params);
