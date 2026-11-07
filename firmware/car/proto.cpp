#include "proto.h"

#include <stdlib.h>
#include <string.h>

namespace {

constexpr char kFrameStart = '{';
constexpr char kFrameEnd = '}';
constexpr char kFieldSeparator = ',';
constexpr uint8_t kMaxFields = 5;
constexpr const char* kFastFlag = "f";
constexpr const char* kBridgeStop = "\"N\":100";
constexpr const char* kIgnoredFrames[] = {"Factory", "WA_OK", "WA_NO"};
constexpr CmdType kHostCommands[] = {
    CmdType::Hb,   CmdType::Stop, CmdType::Drive, CmdType::Move, CmdType::Turn,
    CmdType::Gyro, CmdType::Tele, CmdType::Set,   CmdType::Get,
};

constexpr long kPwmLimit = 255;
constexpr long kMsMin = 1;
constexpr long kMsMax = 65535;
constexpr long kDegLimit = 360;
constexpr long kTelePeriodOff = 0;
// Below 100 ms the telemetry stream does not fit 9600 baud.
constexpr long kTelePeriodMinMs = 100;
constexpr long kTelePeriodMaxMs = 65535;

Cmd makeCmd(CmdType type) {
  Cmd cmd = {};
  cmd.type = type;
  return cmd;
}

Cmd makeErr(ErrReason reason) {
  Cmd cmd = makeCmd(CmdType::Err);
  cmd.err = reason;
  return cmd;
}

uint8_t splitFields(char* content, char* fields[kMaxFields + 1]) {
  uint8_t count = 0;
  fields[count++] = content;
  for (char* p = content; *p != '\0'; ++p) {
    if (*p != kFieldSeparator) {
      continue;
    }
    *p = '\0';
    if (count > kMaxFields) {
      return count;
    }
    fields[count++] = p + 1;
  }
  return count;
}

bool parseLong(const char* text, long min, long max, long& out) {
  char* end = nullptr;
  long value = strtol(text, &end, 10);
  if (*text == '\0' || *end != '\0' || value < min || value > max) {
    return false;
  }
  out = value;
  return true;
}

bool parseFloat(const char* text, float& out) {
  char* end = nullptr;
  double value = strtod(text, &end);
  if (*text == '\0' || *end != '\0') {
    return false;
  }
  out = static_cast<float>(value);
  return true;
}

bool parseFastFlag(char* const fields[], uint8_t count, uint8_t baseCount, bool& fast) {
  if (count == baseCount) {
    fast = false;
    return true;
  }
  if (count == baseCount + 1 && strcmp(fields[baseCount], kFastFlag) == 0) {
    fast = true;
    return true;
  }
  return false;
}

Cmd parseDrive(char* const fields[], uint8_t count) {
  Cmd cmd = makeCmd(CmdType::Drive);
  long left = 0;
  long right = 0;
  long ms = 0;
  if (!parseFastFlag(fields, count, 4, cmd.fast) ||
      !parseLong(fields[1], -kPwmLimit, kPwmLimit, left) ||
      !parseLong(fields[2], -kPwmLimit, kPwmLimit, right) ||
      !parseLong(fields[3], kMsMin, kMsMax, ms)) {
    return makeErr(ErrReason::Frame);
  }
  cmd.left = static_cast<int16_t>(left);
  cmd.right = static_cast<int16_t>(right);
  cmd.ms = static_cast<uint16_t>(ms);
  return cmd;
}

Cmd parseMove(char* const fields[], uint8_t count) {
  Cmd cmd = makeCmd(CmdType::Move);
  long ms = 0;
  if (!parseFastFlag(fields, count, 2, cmd.fast) || !parseLong(fields[1], kMsMin, kMsMax, ms)) {
    return makeErr(ErrReason::Frame);
  }
  cmd.ms = static_cast<uint16_t>(ms);
  return cmd;
}

Cmd parseTurn(char* const fields[], uint8_t count) {
  long deg = 0;
  if (count != 2 || !parseLong(fields[1], -kDegLimit, kDegLimit, deg) || deg == 0) {
    return makeErr(ErrReason::Frame);
  }
  Cmd cmd = makeCmd(CmdType::Turn);
  cmd.deg = static_cast<int16_t>(deg);
  return cmd;
}

Cmd parseTele(char* const fields[], uint8_t count) {
  long period = 0;
  if (count != 2 || !parseLong(fields[1], kTelePeriodOff, kTelePeriodMaxMs, period) ||
      (period != kTelePeriodOff && period < kTelePeriodMinMs)) {
    return makeErr(ErrReason::Frame);
  }
  Cmd cmd = makeCmd(CmdType::Tele);
  cmd.period_ms = static_cast<uint16_t>(period);
  return cmd;
}

Cmd parseSet(char* const fields[], uint8_t count) {
  if (count != 3) {
    return makeErr(ErrReason::Frame);
  }
  Cmd cmd = makeCmd(CmdType::Set);
  if (!paramFromName(fields[1], cmd.param)) {
    return makeErr(ErrReason::Key);
  }
  if (!parseFloat(fields[2], cmd.value)) {
    return makeErr(ErrReason::Frame);
  }
  if (!paramInRange(cmd.param, cmd.value)) {
    return makeErr(ErrReason::Range);
  }
  return cmd;
}

Cmd parseCommand(CmdType type, char* const fields[], uint8_t count) {
  switch (type) {
    case CmdType::Hb:
    case CmdType::Stop:
    case CmdType::Gyro:
    case CmdType::Get:
      return count == 1 ? makeCmd(type) : makeErr(ErrReason::Frame);
    case CmdType::Drive:
      return parseDrive(fields, count);
    case CmdType::Move:
      return parseMove(fields, count);
    case CmdType::Turn:
      return parseTurn(fields, count);
    case CmdType::Tele:
      return parseTele(fields, count);
    case CmdType::Set:
      return parseSet(fields, count);
    case CmdType::BridgeStop:
    case CmdType::Ignore:
    case CmdType::Err:
      return makeErr(ErrReason::Frame);
  }
  return makeErr(ErrReason::Frame);
}

Cmd parseContent(char* content) {
  if (strcmp(content, kBridgeStop) == 0) {
    return makeCmd(CmdType::BridgeStop);
  }
  for (const char* ignored : kIgnoredFrames) {
    if (strcmp(content, ignored) == 0) {
      return makeCmd(CmdType::Ignore);
    }
  }
  char* fields[kMaxFields + 1] = {};
  uint8_t count = splitFields(content, fields);
  for (CmdType type : kHostCommands) {
    if (strcmp(fields[0], cmdName(type)) == 0) {
      return parseCommand(type, fields, count);
    }
  }
  return makeErr(ErrReason::Frame);
}

}  // namespace

const char* cmdName(CmdType type) {
  switch (type) {
    case CmdType::Hb:
      return "hb";
    case CmdType::Stop:
      return "stop";
    case CmdType::Drive:
      return "drive";
    case CmdType::Move:
      return "move";
    case CmdType::Turn:
      return "turn";
    case CmdType::Gyro:
      return "gyro";
    case CmdType::Tele:
      return "tele";
    case CmdType::Set:
      return "set";
    case CmdType::Get:
      return "get";
    case CmdType::BridgeStop:
    case CmdType::Ignore:
    case CmdType::Err:
      return "";
  }
  return "";
}

const char* errReasonName(ErrReason reason) {
  switch (reason) {
    case ErrReason::Frame:
      return "frame";
    case ErrReason::Key:
      return "key";
    case ErrReason::Range:
      return "range";
    case ErrReason::Batt:
      return "batt";
    case ErrReason::Imu:
      return "imu";
  }
  return "";
}

bool FrameReader::feed(char ch, Cmd& out) {
  if (ch == kFrameStart) {
    inFrame_ = true;
    overflow_ = false;
    length_ = 0;
    return false;
  }
  if (!inFrame_) {
    return false;
  }
  if (ch != kFrameEnd) {
    if (length_ < kContentMaxLen) {
      content_[length_++] = ch;
    } else {
      overflow_ = true;
    }
    return false;
  }
  inFrame_ = false;
  content_[length_] = '\0';
  out = overflow_ ? makeErr(ErrReason::Frame) : parseContent(content_);
  return true;
}
