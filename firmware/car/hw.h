#pragma once

#include <stdint.h>

#include "motion.h"
#include "safety.h"

enum class LedColor : uint8_t {
  Blue,
  Green,
  Red,
};

namespace hw {

// Sets pins, starts the IMU. Call once in setup().
void begin();

void motors(Out out);
// 0 = no echo. Triggers at most every 60 ms; returns the last value between triggers.
uint16_t sonarCm(uint32_t now_ms);
uint16_t line(LineSensor sensor);
uint16_t battMv();

bool imuOk();
// Centers the sonar servo, then measures the gyro bias. Blocks for 2.5 s with motors off.
// On an IMU failure, imuOk() turns false.
void gyroBias();
// Integrates gyro Z since the last call. Call each loop.
void updateYaw();
// Degrees, + = right, unbounded.
float yawDeg();

void led(LedColor color);

}  // namespace hw
