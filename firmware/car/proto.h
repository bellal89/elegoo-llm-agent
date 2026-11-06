#pragma once

#include <stdint.h>

#include "params.h"

// Bridge forwards frames of any length; 32 keeps the parser buffer small.
constexpr uint8_t kFrameMaxLen = 32;

enum class CmdType : uint8_t {
  Hb,
  Stop,
  Drive,
  Move,
  Turn,
  Gyro,
  Tele,
  Set,
  Get,
  BridgeStop,
  Ignore,
  Err,
};

enum class ErrReason : uint8_t {
  Frame,
  Key,
  Range,
  Batt,
  Imu,
};

const char* cmdName(CmdType type);
const char* errReasonName(ErrReason reason);

struct Cmd {
  CmdType type;
  int16_t left;
  int16_t right;
  uint16_t ms;
  int16_t deg;
  uint16_t period_ms;
  Param param;
  float value;
  bool fast;
  ErrReason err;
};

class FrameReader {
 public:
  bool feed(char ch, Cmd& out);

 private:
  static constexpr uint8_t kContentMaxLen = kFrameMaxLen - 2;

  char content_[kContentMaxLen + 1] = {};
  uint8_t length_ = 0;
  bool inFrame_ = false;
  bool overflow_ = false;
};
