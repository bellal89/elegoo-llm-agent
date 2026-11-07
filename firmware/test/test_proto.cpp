#include <string.h>

#include "check.h"
#include "params.h"
#include "proto.h"

constexpr int kMaxFrames = 4;

struct Parsed {
  int count;
  Cmd frames[kMaxFrames];
};

static Parsed parse(const char* text) {
  FrameReader reader;
  Parsed parsed = {};
  for (const char* p = text; *p != '\0'; ++p) {
    Cmd cmd = {};
    if (reader.feed(*p, cmd) && parsed.count < kMaxFrames) {
      parsed.frames[parsed.count++] = cmd;
    }
  }
  return parsed;
}

static Cmd parseOne(const char* text) {
  Parsed parsed = parse(text);
  CHECK(parsed.count == 1);
  return parsed.frames[0];
}

static bool isFrameErr(const char* text) {
  Cmd cmd = parseOne(text);
  return cmd.type == CmdType::Err && cmd.err == ErrReason::Frame;
}

static void testDrive() {
  Cmd cmd = parseOne("{drive,120,-120,800}");
  CHECK(cmd.type == CmdType::Drive);
  CHECK(cmd.left == 120);
  CHECK(cmd.right == -120);
  CHECK(cmd.ms == 800);
  CHECK(!cmd.fast);

  CHECK(parseOne("{drive,200,200,500,f}").fast);
}

static void testMove() {
  Cmd cmd = parseOne("{move,1500}");
  CHECK(cmd.type == CmdType::Move);
  CHECK(cmd.ms == 1500);
  CHECK(!cmd.fast);

  CHECK(parseOne("{move,1500,f}").fast);
}

static void testTurn() {
  Cmd cmd = parseOne("{turn,-90}");
  CHECK(cmd.type == CmdType::Turn);
  CHECK(cmd.deg == -90);
}

static void testNoArgCommands() {
  CHECK(parseOne("{hb}").type == CmdType::Hb);
  CHECK(parseOne("{stop}").type == CmdType::Stop);
  CHECK(parseOne("{gyro}").type == CmdType::Gyro);
  CHECK(parseOne("{get}").type == CmdType::Get);
}

static void testTele() {
  Cmd cmd = parseOne("{tele,100}");
  CHECK(cmd.type == CmdType::Tele);
  CHECK(cmd.period_ms == 100);

  CHECK(parseOne("{tele,0}").period_ms == 0);
}

static void testSet() {
  Cmd cmd = parseOne("{set,kp,4.5}");
  CHECK(cmd.type == CmdType::Set);
  CHECK(cmd.param == Param::Kp);
  CHECK(cmd.value == 4.5f);
}

static void testBridgeFrames() {
  CHECK(parseOne("{\"N\":100}").type == CmdType::BridgeStop);
  CHECK(parseOne("{Factory}").type == CmdType::Ignore);
  CHECK(parseOne("{WA_OK}").type == CmdType::Ignore);
  CHECK(parseOne("{WA_NO}").type == CmdType::Ignore);
}

static void testMalformedFrames() {
  CHECK(isFrameErr("{drive,1}"));
  CHECK(isFrameErr("{bogus}"));
  CHECK(isFrameErr("{}"));
  CHECK(isFrameErr("{turn,abc}"));
  CHECK(isFrameErr("{turn,0}"));
  CHECK(isFrameErr("{turn,400}"));
  CHECK(isFrameErr("{drive,300,0,500}"));
  CHECK(isFrameErr("{drive,100,100,0}"));
  CHECK(isFrameErr("{move,1500,x}"));
  CHECK(isFrameErr("{tele,-1}"));
  CHECK(isFrameErr("{tele,50}"));
  CHECK(isFrameErr("{hb,1}"));
}

static void testFrameLength() {
  // 32 chars including braces is the limit.
  CHECK(parseOne("{set,turn_slow_deg,20.000000000}").type == CmdType::Set);
  CHECK(isFrameErr("{set,turn_slow_deg,20.0000000000}"));

  Parsed parsed = parse("{xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx}{stop}");
  CHECK(parsed.count == 2);
  CHECK(parsed.frames[0].type == CmdType::Err);
  CHECK(parsed.frames[0].err == ErrReason::Frame);
  CHECK(parsed.frames[1].type == CmdType::Stop);
}

static void testBytesOutsideBraces() {
  CHECK(parseOne("xx\r\n{hb}yy").type == CmdType::Hb);
  CHECK(parseOne("{hb{stop}").type == CmdType::Stop);
}

static void testSetErrors() {
  Cmd unknown = parseOne("{set,nope,1}");
  CHECK(unknown.type == CmdType::Err);
  CHECK(unknown.err == ErrReason::Key);

  Cmd tooHigh = parseOne("{set,max_pwm,300}");
  CHECK(tooHigh.type == CmdType::Err);
  CHECK(tooHigh.err == ErrReason::Range);

  Cmd notInteger = parseOne("{set,max_pwm,100.5}");
  CHECK(notInteger.type == CmdType::Err);
  CHECK(notInteger.err == ErrReason::Range);

  CHECK(isFrameErr("{set,kp,abc}"));

  CHECK(parseOne("{set,line_mask,6}").type == CmdType::Set);
  CHECK(parseOne("{set,line_mask,0}").err == ErrReason::Range);
  CHECK(parseOne("{set,line_mask,8}").err == ErrReason::Range);
}

static void testParamNames() {
  for (uint8_t i = 0; i < kParamCount; ++i) {
    Param param = static_cast<Param>(i);
    Param found = Param::HbMs;
    CHECK(paramFromName(paramName(param), found));
    CHECK(found == param);
    CHECK(paramInRange(param, paramDefault(param)));
  }
  Param unused = Param::HbMs;
  CHECK(!paramFromName("nope", unused));
}

static void testParamIsInteger() {
  CHECK(paramIsInteger(Param::MaxPwm));
  CHECK(paramIsInteger(Param::HbMs));
  CHECK(paramIsInteger(Param::LineMask));
  CHECK(!paramIsInteger(Param::TurnSlowDeg));
  CHECK(!paramIsInteger(Param::TurnMargin));
  CHECK(!paramIsInteger(Param::Kp));
}

static void testParamsStore() {
  Params params;
  CHECK(params.get(Param::MaxPwm) == paramDefault(Param::MaxPwm));
  params.set(Param::Kp, 7.5f);
  CHECK(params.get(Param::Kp) == 7.5f);
}

static void testErrReasonNames() {
  CHECK(strcmp(errReasonName(ErrReason::Frame), "frame") == 0);
  CHECK(strcmp(errReasonName(ErrReason::Key), "key") == 0);
  CHECK(strcmp(errReasonName(ErrReason::Range), "range") == 0);
  CHECK(strcmp(errReasonName(ErrReason::Batt), "batt") == 0);
  CHECK(strcmp(errReasonName(ErrReason::Imu), "imu") == 0);
}

int main() {
  testDrive();
  testMove();
  testTurn();
  testNoArgCommands();
  testTele();
  testSet();
  testBridgeFrames();
  testMalformedFrames();
  testFrameLength();
  testBytesOutsideBraces();
  testSetErrors();
  testParamNames();
  testParamIsInteger();
  testParamsStore();
  testErrReasonNames();
  return checkSummary("test_proto");
}
