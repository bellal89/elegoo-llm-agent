#include "button.h"

namespace {

constexpr uint32_t kDebounceMs = 20;

}  // namespace

bool Button::pressed(bool down, uint32_t now_ms) {
  if (down != raw_down_) {
    raw_down_ = down;
    raw_change_ms_ = now_ms;
  }
  if (raw_down_ == down_ || now_ms - raw_change_ms_ < kDebounceMs) {
    return false;
  }
  down_ = raw_down_;
  return down_;
}
