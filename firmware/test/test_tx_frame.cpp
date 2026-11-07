#include <stdint.h>
#include <string.h>

#include "check.h"
#include "tx_frame.h"

static bool hasText(const TxFrame& frame, const char* expected) {
  return frame.valid() && strcmp(frame.text(), expected) == 0 && frame.length() == strlen(expected);
}

static void testKindOnly() { CHECK(hasText(TxFrame("ok"), "{ok}\n")); }

static void testTextFields() { CHECK(hasText(TxFrame("done").add("turn").add("cliff"), "{done,turn,cliff}\n")); }

static void testIntegers() {
  CHECK(hasText(TxFrame("t").add(static_cast<int32_t>(-1234)).add(static_cast<uint32_t>(0)), "{t,-1234,0}\n"));
  CHECK(hasText(TxFrame("t").add(INT32_MIN).add(UINT32_MAX), "{t,-2147483648,4294967295}\n"));
}

static void testFloats() {
  CHECK(hasText(TxFrame("p").add(4.0f), "{p,4.00}\n"));
  CHECK(hasText(TxFrame("p").add(0.125f), "{p,0.13}\n"));
  CHECK(hasText(TxFrame("p").add(-2.5f), "{p,-2.50}\n"));
  CHECK(hasText(TxFrame("p").add(-0.001f), "{p,0.00}\n"));
}

static void testCapacity() {
  char field[kTxFrameCapacity] = {};
  memset(field, 'x', kTxFrameCapacity - 5);
  TxFrame full("t");
  full.add(field);
  CHECK(full.valid());
  CHECK(full.length() == kTxFrameCapacity);

  TxFrame over("t");
  over.add(field).add("y");
  CHECK(!over.valid());
}

int main() {
  testKindOnly();
  testTextFields();
  testIntegers();
  testFloats();
  testCapacity();
  return checkSummary("test_tx_frame");
}
