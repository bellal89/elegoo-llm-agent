#include "button.h"
#include "hw.h"
#include "motion.h"
#include "params.h"
#include "proto.h"
#include "safety.h"
#include "tx_frame.h"

constexpr unsigned long kBaud = 9600;
constexpr uint16_t kTeleOff = 0;
// The hand must leave the car before the gyro bias starts.
constexpr uint32_t kSelfTestDelayMs = 3000;
constexpr uint32_t kBlinkMs = 250;

constexpr const char* kOkKind = "ok";
constexpr const char* kErrKind = "err";
constexpr const char* kDoneKind = "done";
constexpr const char* kParamKind = "p";
constexpr const char* kTeleKind = "t";
constexpr const char* kImuKey = "imu";
constexpr const char* kPwmLimitKey = "pwm_limit";

// {get} replies: one param per step, then pwm_limit, then imu, then ok.
constexpr uint8_t kGetPwmLimitStep = kParamCount;
constexpr uint8_t kGetImuStep = kParamCount + 1;
constexpr uint8_t kGetOkStep = kParamCount + 2;
constexpr uint8_t kGetIdle = kParamCount + 3;

Params params;
Motion motion(params);
FrameReader reader;
uint32_t last_hb_ms = 0;
uint16_t tele_period_ms = kTeleOff;
uint32_t tele_ms = 0;
uint8_t get_step = kGetIdle;
Button button;
bool self_test_active = false;

// Blocks while the TX buffer is full. Use only for short frames: ok, err, done, p.
void sendNow(const TxFrame& frame) { Serial.write(frame.text(), frame.length()); }

bool sendIfFits(const TxFrame& frame) {
  if (!frame.valid() || Serial.availableForWrite() < frame.length()) {
    return false;
  }
  sendNow(frame);
  return true;
}

void sendOk(CmdType type) { sendNow(TxFrame(kOkKind).add(cmdName(type))); }

void sendErr(ErrReason reason) { sendNow(TxFrame(kErrKind).add(errReasonName(reason))); }

TxFrame paramFrame(Param param) {
  TxFrame frame(kParamKind);
  frame.add(paramName(param));
  float value = params.get(param);
  if (paramIsInteger(param)) {
    frame.add(static_cast<int32_t>(value));
  } else {
    frame.add(value);
  }
  return frame;
}

TxFrame pwmLimitFrame() { return TxFrame(kParamKind).add(kPwmLimitKey).add(static_cast<int32_t>(kPwmLimit)); }

TxFrame imuFrame() { return TxFrame(kParamKind).add(kImuKey).add(static_cast<uint32_t>(hw::imuOk())); }

LedColor endColor(StopReason reason) {
  switch (reason) {
    case StopReason::None:
    case StopReason::Done:
    case StopReason::Cmd:
      return LedColor::Blue;
    case StopReason::Hb:
    case StopReason::Bridge:
    case StopReason::Sonar:
    case StopReason::Cliff:
    case StopReason::Timeout:
    case StopReason::Imu:
      return LedColor::Red;
  }
  return LedColor::Red;
}

void reportEnded() {
  if (!motion.takeEnded()) {
    return;
  }
  sendNow(TxFrame(kDoneKind).add(cmdName(motion.lastCmd())).add(stopReasonName(motion.lastReason())));
  hw::led(endColor(motion.lastReason()));
  self_test_active = false;
}

Sensors readSensors(uint32_t now_ms) {
  Sensors sensors = {};
  sensors.now_ms = now_ms;
  sensors.last_hb_ms = last_hb_ms;
  sensors.sonar_cm = hw::sonarCm(now_ms);
  for (uint8_t i = 0; i < kLineSensorCount; ++i) {
    sensors.line[i] = hw::line(static_cast<LineSensor>(i));
  }
  sensors.batt_mv = hw::battMv();
  sensors.imu_ok = hw::imuOk();
  return sensors;
}

void startMotion(const Cmd& cmd) {
  if (!motionAllowed(hw::battMv(), params)) {
    sendErr(ErrReason::Batt);
    hw::led(LedColor::Red);
    return;
  }
  motion.start(cmd, millis(), hw::yawDeg());
  // A preempted motion reports {done,<old>,cmd} before {ok,<new>}.
  reportEnded();
  sendOk(cmd.type);
  hw::led(LedColor::Green);
}

// loop() does not run during a blocking step, so stop the motors before it.
void stopBeforeBlocking() {
  motion.stop(StopReason::Cmd);
  hw::motors({0, 0});
  reportEnded();
}

void calibrateGyro() {
  stopBeforeBlocking();
  hw::gyroBias();
  last_hb_ms = millis();
  if (hw::imuOk()) {
    sendOk(CmdType::Gyro);
  } else {
    sendErr(ErrReason::Imu);
  }
}

void blinkUntilHandAway() {
  uint32_t start_ms = millis();
  while (millis() - start_ms < kSelfTestDelayMs) {
    hw::led((millis() - start_ms) / kBlinkMs % 2 == 0 ? LedColor::Blue : LedColor::Off);
  }
}

// Blocks for the delay and the gyro bias, then moves forward until a stop.
void startSelfTest() {
  stopBeforeBlocking();
  blinkUntilHandAway();
  hw::led(LedColor::Blue);
  hw::gyroBias();
  last_hb_ms = millis();
  Cmd cmd = {};
  cmd.type = CmdType::Move;
  cmd.ms = static_cast<uint16_t>(params.get(Param::MaxCmdMs));
  startMotion(cmd);
  self_test_active = motion.active();
}

void handleCmd(const Cmd& cmd) {
  if (isHostCommand(cmd.type)) {
    last_hb_ms = millis();
  }
  switch (cmd.type) {
    case CmdType::Hb:
    case CmdType::Ignore:
      break;
    case CmdType::Stop:
      motion.stop(StopReason::Cmd);
      sendOk(CmdType::Stop);
      break;
    case CmdType::BridgeStop:
      motion.stop(StopReason::Bridge);
      break;
    case CmdType::Err:
      sendErr(cmd.err);
      break;
    case CmdType::Drive:
      startMotion(cmd);
      break;
    case CmdType::Move:
    case CmdType::Turn:
      if (hw::imuOk()) {
        startMotion(cmd);
      } else {
        sendErr(ErrReason::Imu);
      }
      break;
    case CmdType::Gyro:
      if (hw::imuOk()) {
        calibrateGyro();
      } else {
        sendErr(ErrReason::Imu);
      }
      break;
    case CmdType::Tele:
      tele_period_ms = cmd.period_ms;
      tele_ms = millis();
      sendOk(CmdType::Tele);
      break;
    case CmdType::Set:
      params.set(cmd.param, cmd.value);
      params.store(cmd.param);
      sendOk(CmdType::Set);
      break;
    case CmdType::Get:
      get_step = 0;
      break;
  }
}

void readCommands() {
  while (Serial.available() > 0) {
    Cmd cmd = {};
    if (reader.feed(static_cast<char>(Serial.read()), cmd)) {
      handleCmd(cmd);
    }
  }
}

TxFrame getReplyFrame(uint8_t step) {
  if (step == kGetPwmLimitStep) {
    return pwmLimitFrame();
  }
  if (step == kGetImuStep) {
    return imuFrame();
  }
  return paramFrame(static_cast<Param>(step));
}

// The TX buffer cannot hold all {get} replies: send one per loop when it fits.
void sendNextGetReply() {
  if (get_step == kGetIdle) {
    return;
  }
  if (get_step == kGetOkStep) {
    sendOk(CmdType::Get);
    get_step = kGetIdle;
    return;
  }
  if (sendIfFits(getReplyFrame(get_step))) {
    ++get_step;
  }
}

void sendTelemetry(const Sensors& sensors) {
  if (tele_period_ms == kTeleOff || sensors.now_ms - tele_ms < tele_period_ms) {
    return;
  }
  tele_ms = sensors.now_ms;
  TxFrame frame(kTeleKind);
  frame.add(sensors.now_ms).add(static_cast<uint32_t>(sensors.sonar_cm));
  for (uint16_t level : sensors.line) {
    frame.add(static_cast<uint32_t>(level));
  }
  frame.add(static_cast<int32_t>(lround(hw::yawDeg() * kFixedScale)))
      .add(static_cast<uint32_t>(sensors.batt_mv))
      .add(motionKindName(motion.kind()))
      .add(stopReasonName(motion.lastReason()));
  sendIfFits(frame);
}

void setup() {
  Serial.begin(kBaud);
  params.load();
  hw::begin();
  hw::led(LedColor::Blue);
  hw::gyroBias();
  for (uint8_t i = 0; i < kParamCount; ++i) {
    sendNow(paramFrame(static_cast<Param>(i)));
  }
  sendNow(pwmLimitFrame());
  sendNow(imuFrame());
  last_hb_ms = millis();
}

void loop() {
  readCommands();
  uint32_t now_ms = millis();
  if (button.pressed(hw::buttonDown(), now_ms)) {
    // now_ms is stale after the blocking start.
    startSelfTest();
    return;
  }
  // No host is connected during a self-test.
  if (self_test_active) {
    last_hb_ms = now_ms;
  }
  hw::update(now_ms);
  hw::updateYaw();
  Sensors sensors = readSensors(now_ms);
  motion.applySafety(sensors);
  hw::motors(motion.step(now_ms, hw::yawDeg()));
  reportEnded();
  sendNextGetReply();
  sendTelemetry(sensors);
}
