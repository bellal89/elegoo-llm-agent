#include <math.h>

#include "check.h"
#include "params.h"

static void testParamNames() {
  for (uint8_t i = 0; i < kParamCount; ++i) {
    Param param = static_cast<Param>(i);
    Param found = Param::HbMs;
    CHECK(paramFromName(paramName(param), found));
    CHECK(found == param);
    CHECK(paramInRange(param, paramDefault(param)));
  }
}

static void testNanOutOfRange() {
  // Erased EEPROM reads as NaN: Params::load relies on this rejection.
  CHECK(!paramInRange(Param::Kp, NAN));
}

static void testPwmLimit() {
  const Param pwm_params[] = {Param::MaxPwm, Param::MovePwm, Param::TurnPwm, Param::TurnSlowPwm, Param::BackPwm};
  for (Param param : pwm_params) {
    CHECK(paramInRange(param, kPwmLimit));
    CHECK(!paramInRange(param, kPwmLimit + 1));
  }
}

int main() {
  testParamNames();
  testNanOutOfRange();
  testPwmLimit();
  return checkSummary("test_params");
}
