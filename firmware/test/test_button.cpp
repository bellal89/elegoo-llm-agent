#include <stdint.h>

#include "button.h"
#include "check.h"

// Feeds `down` from start_ms to end_ms and counts the presses.
static int feed(Button& button, bool down, uint32_t start_ms, uint32_t end_ms) {
  int presses = 0;
  for (uint32_t now_ms = start_ms; now_ms != end_ms; ++now_ms) {
    presses += button.pressed(down, now_ms);
  }
  return presses;
}

static void testOnePressPerHold() {
  Button button;
  CHECK(feed(button, true, 1000, 1019) == 0);
  CHECK(feed(button, true, 1019, 3000) == 1);
  CHECK(feed(button, false, 3000, 3100) == 0);
  CHECK(feed(button, true, 4000, 4100) == 1);
}

static void testBounceIsIgnored() {
  Button button;
  int presses = 0;
  for (uint32_t now_ms = 1000; now_ms < 1100; ++now_ms) {
    presses += button.pressed(now_ms % 10 < 5, now_ms);
  }
  CHECK(presses == 0);
}

static void testAcrossMillisWrap() {
  Button button;
  CHECK(feed(button, true, UINT32_MAX - 10, 100) == 1);
}

int main() {
  testOnePressPerHold();
  testBounceIsIgnored();
  testAcrossMillisWrap();
  return checkSummary("test_button");
}
