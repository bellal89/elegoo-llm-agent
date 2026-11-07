#include "control.h"

MotionParams motionParamsFrom(const Params& params) {
  MotionParams value = {};
  value.max_pwm = static_cast<int16_t>(params.get(Param::MaxPwm));
  value.move_pwm = static_cast<int16_t>(params.get(Param::MovePwm));
  value.turn_pwm = static_cast<int16_t>(params.get(Param::TurnPwm));
  value.turn_slow_pwm = static_cast<int16_t>(params.get(Param::TurnSlowPwm));
  value.turn_slow_deg = params.get(Param::TurnSlowDeg);
  value.turn_margin = params.get(Param::TurnMargin);
  value.kp = params.get(Param::Kp);
  value.back_pwm = static_cast<int16_t>(params.get(Param::BackPwm));
  value.back_ms = static_cast<uint16_t>(params.get(Param::BackMs));
  value.max_cmd_ms = static_cast<uint16_t>(params.get(Param::MaxCmdMs));
  return value;
}

Limits limitsFrom(const Params& params) {
  Limits value = {};
  value.hb_ms = static_cast<uint16_t>(params.get(Param::HbMs));
  value.sonar_stop_cm = static_cast<uint16_t>(params.get(Param::SonarStopCm));
  value.cliff_th = static_cast<uint16_t>(params.get(Param::CliffTh));
  value.batt_min_mv = static_cast<uint16_t>(params.get(Param::BattMinMv));
  value.line_mask = static_cast<uint8_t>(params.get(Param::LineMask));
  return value;
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

void checkMotionSafety(Motion& motion, const Sensors& sensors, const Limits& limits) {
  if (!motion.active() || motion.kind() == MotionKind::Back) {
    return;
  }
  StopReason reason = checkSafety(sensors, limits, motion.guard());
  switch (reason) {
    case StopReason::None:
      break;
    case StopReason::Cliff:
      motion.cliffBackoff(sensors.now_ms);
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
