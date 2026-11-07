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

int main() {
  testParamNames();
  testNanOutOfRange();
  return checkSummary("test_params");
}
