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

// Sets pins, centers the sonar servo, starts the IMU. Call once in setup().
void begin();
// Detaches the servo after it reaches center. Call each loop.
void update(uint32_t now_ms);

void motors(Out out);
// 0 = no echo. Triggers at most every 60 ms; returns the last value between triggers.
uint16_t sonarCm(uint32_t now_ms);
uint16_t line(LineSensor sensor);
uint16_t battMv();

bool imuOk();
// Blocks for 2 s with motors off. On an IMU failure, imuOk() turns false.
void gyroBias();
// Integrates gyro Z since the last call. Call each loop.
void updateYaw();
// Degrees, + = right, unbounded.
float yawDeg();

void led(LedColor color);

}  // namespace hw
