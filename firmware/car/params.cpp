#include "params.h"

#include <string.h>

#ifdef ARDUINO
#include <EEPROM.h>
#endif

namespace {

struct ParamSpec {
  const char* name;
  float min;
  float max;
  float def;
  bool integer;
};

constexpr float kPwmMin = 0;
constexpr float kPwmMax = 255;

ParamSpec paramSpec(Param param) {
  switch (param) {
    case Param::MaxPwm:
      return {"max_pwm", kPwmMin, kPwmMax, 100, true};
    case Param::MovePwm:
      return {"move_pwm", kPwmMin, kPwmMax, 100, true};
    case Param::TurnPwm:
      return {"turn_pwm", kPwmMin, kPwmMax, 110, true};
    case Param::TurnSlowPwm:
      return {"turn_slow_pwm", kPwmMin, kPwmMax, 90, true};
    case Param::TurnSlowDeg:
      return {"turn_slow_deg", 0, 90, 20, false};
    case Param::TurnMargin:
      return {"turn_margin", 0, 90, 5, false};
    case Param::Kp:
      return {"kp", 0, 50, 4.0f, false};
    case Param::SonarStopCm:
      return {"sonar_stop_cm", 1, 200, 25, true};
    case Param::CliffTh:
      return {"cliff_th", 0, 1023, 950, true};
    case Param::BackPwm:
      return {"back_pwm", kPwmMin, kPwmMax, 90, true};
    case Param::BackMs:
      return {"back_ms", 0, 2000, 300, true};
    case Param::MaxCmdMs:
      return {"max_cmd_ms", 100, 30000, 5000, true};
    case Param::BattMinMv:
      return {"batt_min_mv", 6000, 8400, 7000, true};
    case Param::HbMs:
      return {"hb_ms", 100, 60000, 1000, true};
  }
  return {"", 0, 0, 0, false};
}

}  // namespace

const char* paramName(Param param) { return paramSpec(param).name; }

bool paramFromName(const char* name, Param& out) {
  for (uint8_t i = 0; i < kParamCount; ++i) {
    Param param = static_cast<Param>(i);
    if (strcmp(name, paramName(param)) == 0) {
      out = param;
      return true;
    }
  }
  return false;
}

float paramDefault(Param param) { return paramSpec(param).def; }

bool paramInRange(Param param, float value) {
  ParamSpec spec = paramSpec(param);
  if (!(value >= spec.min && value <= spec.max)) {
    return false;
  }
  return !spec.integer || static_cast<float>(static_cast<int32_t>(value)) == value;
}

bool paramIsInteger(Param param) { return paramSpec(param).integer; }

Params::Params() {
  for (uint8_t i = 0; i < kParamCount; ++i) {
    values_[i] = paramDefault(static_cast<Param>(i));
  }
}

float Params::get(Param param) const { return values_[static_cast<uint8_t>(param)]; }

void Params::set(Param param, float value) { values_[static_cast<uint8_t>(param)] = value; }

#ifdef ARDUINO

namespace {

constexpr int kMagicAddr = 0;
constexpr int kVersionAddr = 1;
constexpr int kHeaderSize = 2;
constexpr uint8_t kMagic = 0xE7;
constexpr uint8_t kVersion = 1;

int slotAddr(Param param) { return kHeaderSize + static_cast<uint8_t>(param) * static_cast<int>(sizeof(float)); }

}  // namespace

void Params::load() {
  bool header_ok = EEPROM.read(kMagicAddr) == kMagic && EEPROM.read(kVersionAddr) == kVersion;
  for (uint8_t i = 0; i < kParamCount; ++i) {
    Param param = static_cast<Param>(i);
    float value = paramDefault(param);
    if (header_ok && param != Param::HbMs) {
      EEPROM.get(slotAddr(param), value);
    }
    // Erased EEPROM reads as NaN; paramInRange rejects it.
    set(param, paramInRange(param, value) ? value : paramDefault(param));
    // EEPROM.put writes only the bytes that differ.
    store(param);
  }
  EEPROM.update(kMagicAddr, kMagic);
  EEPROM.update(kVersionAddr, kVersion);
}

void Params::store(Param param) const {
  if (param == Param::HbMs) {
    return;
  }
  EEPROM.put(slotAddr(param), get(param));
}

#endif
