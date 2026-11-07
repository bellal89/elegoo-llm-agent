#include "hw.h"
#include "motion.h"
#include "params.h"
#include "proto.h"
#include "safety.h"
#include "tx_frame.h"

constexpr unsigned long kBaud = 9600;
constexpr uint16_t kTeleOff = 0;

constexpr const char* kOkKind = "ok";
constexpr const char* kErrKind = "err";
constexpr const char* kDoneKind = "done";
constexpr const char* kParamKind = "p";
constexpr const char* kTeleKind = "t";
constexpr const char* kImuKey = "imu";

// {get} replies: one param per step, then imu, then ok.
constexpr uint8_t kGetImuStep = kParamCount;
constexpr uint8_t kGetOkStep = kParamCount + 1;
constexpr uint8_t kGetIdle = kParamCount + 2;

Params params;
MotionParams motion_params = {};
Limits limits = {};
Motion motion(motion_params);
FrameReader reader;
uint32_t last_hb_ms = 0;
uint16_t tele_period_ms = kTeleOff;
uint32_t tele_ms = 0;
uint8_t get_step = kGetIdle;

void applyParams() {
  motion_params.max_pwm = static_cast<int16_t>(params.get(Param::MaxPwm));
  motion_params.move_pwm = static_cast<int16_t>(params.get(Param::MovePwm));
  motion_params.turn_pwm = static_cast<int16_t>(params.get(Param::TurnPwm));
  motion_params.turn_slow_pwm = static_cast<int16_t>(params.get(Param::TurnSlowPwm));
  motion_params.turn_slow_deg = params.get(Param::TurnSlowDeg);
  motion_params.turn_margin = params.get(Param::TurnMargin);
  motion_params.kp = params.get(Param::Kp);
  motion_params.back_pwm = static_cast<int16_t>(params.get(Param::BackPwm));
  motion_params.back_ms = static_cast<uint16_t>(params.get(Param::BackMs));
  motion_params.max_cmd_ms = static_cast<uint16_t>(params.get(Param::MaxCmdMs));
  limits.hb_ms = static_cast<uint16_t>(params.get(Param::HbMs));
  limits.sonar_stop_cm = static_cast<uint16_t>(params.get(Param::SonarStopCm));
  limits.cliff_th = static_cast<uint16_t>(params.get(Param::CliffTh));
  limits.batt_min_mv = static_cast<uint16_t>(params.get(Param::BattMinMv));
  limits.line_mask = static_cast<uint8_t>(params.get(Param::LineMask));
}

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

bool resetsHeartbeat(CmdType type) {
  switch (type) {
    case CmdType::Hb:
    case CmdType::Stop:
    case CmdType::Drive:
    case CmdType::Move:
    case CmdType::Turn:
    case CmdType::Gyro:
    case CmdType::Tele:
    case CmdType::Set:
    case CmdType::Get:
      return true;
    case CmdType::BridgeStop:
    case CmdType::Ignore:
    case CmdType::Err:
      return false;
  }
  return false;
}

void startMotion(const Cmd& cmd) {
  uint32_t now_ms = millis();
  if (!motionAllowed(readSensors(now_ms), limits)) {
    sendErr(ErrReason::Batt);
    return;
  }
  motion.start(cmd, now_ms, hw::yawDeg());
  // A preempted motion reports {done,<old>,cmd} before {ok,<new>}.
  reportEnded();
  sendOk(cmd.type);
  hw::led(LedColor::Green);
}

void calibrateGyro() {
  motion.stop(StopReason::Cmd);
  reportEnded();
  bool bias_ok = hw::gyroBias();
  last_hb_ms = millis();
  if (bias_ok) {
    sendOk(CmdType::Gyro);
  } else {
    sendErr(ErrReason::Imu);
  }
}

void handleCmd(const Cmd& cmd) {
  if (resetsHeartbeat(cmd.type)) {
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
      applyParams();
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

void checkMotionSafety(const Sensors& sensors, uint32_t now_ms) {
  if (!motion.active() || motion.kind() == MotionKind::Back) {
    return;
  }
  StopReason reason = checkSafety(sensors, limits, motion.guard());
  switch (reason) {
    case StopReason::None:
      break;
    case StopReason::Cliff:
      motion.cliffBackoff(now_ms);
      break;
    case StopReason::Done:
    case StopReason::Cmd:
    case StopReason::Hb:
    case StopReason::Bridge:
    case StopReason::Sonar:
    case StopReason::Timeout:
    case StopReason::Imu:
      motion.stop(reason);
      break;
  }
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
  TxFrame frame = get_step == kGetImuStep ? imuFrame() : paramFrame(static_cast<Param>(get_step));
  if (sendIfFits(frame)) {
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
  applyParams();
  hw::begin();
  hw::led(LedColor::Blue);
  // On failure imuOk() turns false; the imu frame below reports it.
  hw::gyroBias();
  for (uint8_t i = 0; i < kParamCount; ++i) {
    sendNow(paramFrame(static_cast<Param>(i)));
  }
  sendNow(imuFrame());
  last_hb_ms = millis();
}

void loop() {
  readCommands();
  uint32_t now_ms = millis();
  hw::update(now_ms);
  hw::updateYaw();
  Sensors sensors = readSensors(now_ms);
  checkMotionSafety(sensors, now_ms);
  hw::motors(motion.step(now_ms, hw::yawDeg()));
  reportEnded();
  sendNextGetReply();
  sendTelemetry(sensors);
}
