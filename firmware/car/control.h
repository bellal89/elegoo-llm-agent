#pragma once

#include "motion.h"
#include "params.h"
#include "proto.h"
#include "safety.h"

MotionParams motionParamsFrom(const Params& params);
Limits limitsFrom(const Params& params);
// Bridge and invalid frames do not prove that the host is alive.
bool resetsHeartbeat(CmdType type);
// Skips the check during the cliff backoff: the car must back off the edge.
void checkMotionSafety(Motion& motion, const Sensors& sensors, const Limits& limits);
