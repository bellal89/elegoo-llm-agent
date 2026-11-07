#pragma once

#include <stdint.h>

class Button {
 public:
  // True once for each press.
  bool pressed(bool down, uint32_t now_ms);

 private:
  bool raw_down_ = false;
  uint32_t raw_change_ms_ = 0;
  bool down_ = false;
};
