#pragma once

#include <stdint.h>

// The UNO TX ring buffer has 64 bytes and holds at most 63.
constexpr uint8_t kTxFrameCapacity = 63;

// Builds "{kind,field,...}\n". A frame that exceeds kTxFrameCapacity is invalid.
class TxFrame {
 public:
  explicit TxFrame(const char* kind);

  TxFrame& add(const char* text);
  TxFrame& add(int32_t value);
  TxFrame& add(uint32_t value);
  // Two decimals.
  TxFrame& add(float value);

  bool valid() const;
  const char* text() const;
  uint8_t length() const;

 private:
  void append(const char* text);
  void appendUnsigned(uint32_t value);

  char text_[kTxFrameCapacity + 1] = {};
  uint8_t length_ = 0;
  bool overflow_ = false;
};
