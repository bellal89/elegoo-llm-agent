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
bool paramIsInteger(Param param);

class Params {
 public:
  Params();
  float get(Param param) const;
  void set(Param param, float value);
#ifdef ARDUINO
  // Bad header or out-of-range values: writes defaults. HbMs keeps its default.
  void load();
  // Ignores HbMs: it is set per session by the host.
  void store(Param param) const;
#endif

 private:
  float values_[kParamCount];
};
