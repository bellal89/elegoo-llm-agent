#pragma once

#include <stdint.h>

// Append new members only at the end: the index is the EEPROM slot.
enum class Param : uint8_t {
  MaxPwm,
  MovePwm,
  TurnPwm,
  TurnSlowPwm,
  TurnSlowDeg,
  TurnMargin,
  Kp,
  SonarStopCm,
  CliffTh,
  BackPwm,
  BackMs,
  MaxCmdMs,
  BattMinMv,
  HbMs,
};

constexpr uint8_t kParamCount = 14;

const char* paramName(Param param);
bool paramFromName(const char* name, Param& out);
float paramDefault(Param param);
bool paramInRange(Param param, float value);

class Params {
 public:
  Params();
  float get(Param param) const;
  void set(Param param, float value);

 private:
  float values_[kParamCount];
};
