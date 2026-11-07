#include "tx_frame.h"

#include <string.h>

namespace {

constexpr const char* kFrameStart = "{";
constexpr const char* kFieldSeparator = ",";
constexpr const char* kFrameEnd = "}\n";
constexpr uint8_t kFrameEndLen = 2;
constexpr uint8_t kUint32MaxDigits = 10;
constexpr uint8_t kDecimalBase = 10;
constexpr float kRoundHalf = 0.5f;

}  // namespace

TxFrame::TxFrame(const char* kind) {
  append(kFrameStart);
  append(kind);
}

TxFrame& TxFrame::add(const char* text) {
  append(kFieldSeparator);
  append(text);
  return *this;
}

TxFrame& TxFrame::add(int32_t value) {
  append(kFieldSeparator);
  if (value < 0) {
    append("-");
  }
  // 0u - value is exact for INT32_MIN, where -value overflows.
  appendUnsigned(value < 0 ? 0u - static_cast<uint32_t>(value) : static_cast<uint32_t>(value));
  return *this;
}

TxFrame& TxFrame::add(uint32_t value) {
  append(kFieldSeparator);
  appendUnsigned(value);
  return *this;
}

TxFrame& TxFrame::add(float value) {
  float scaled = value * kFixedScale;
  int32_t rounded = static_cast<int32_t>(scaled < 0 ? scaled - kRoundHalf : scaled + kRoundHalf);
  append(kFieldSeparator);
  if (rounded < 0) {
    append("-");
  }
  uint32_t magnitude = rounded < 0 ? 0u - static_cast<uint32_t>(rounded) : static_cast<uint32_t>(rounded);
  uint32_t units = magnitude / static_cast<uint32_t>(kFixedScale);
  uint32_t fraction = magnitude % static_cast<uint32_t>(kFixedScale);
  appendUnsigned(units);
  append(fraction < kDecimalBase ? ".0" : ".");
  appendUnsigned(fraction);
  return *this;
}

bool TxFrame::valid() const { return !overflow_; }

const char* TxFrame::text() const { return text_; }

uint8_t TxFrame::length() const { return length_ + kFrameEndLen; }

void TxFrame::append(const char* text) {
  size_t text_len = strlen(text);
  if (length_ + text_len + kFrameEndLen > kTxFrameCapacity) {
    overflow_ = true;
    return;
  }
  memcpy(text_ + length_, text, text_len);
  length_ += text_len;
  strcpy(text_ + length_, kFrameEnd);
}

void TxFrame::appendUnsigned(uint32_t value) {
  char digits[kUint32MaxDigits + 1] = {};
  uint8_t pos = kUint32MaxDigits;
  do {
    digits[--pos] = static_cast<char>('0' + value % kDecimalBase);
    value /= kDecimalBase;
  } while (value != 0);
  append(digits + pos);
}
