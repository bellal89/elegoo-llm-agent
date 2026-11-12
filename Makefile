PORT := /dev/cu.usbserial-1110
STEP := all
TEST := turn
TASK := drive to the red box
MODEL := claude-haiku-5-5

.PHONY: init install lint test upload hardware-test calibrate-usb calibrate-wifi accept-usb accept-wifi agent

init:
	uv python install
	git config core.hooksPath .githooks

install:
	uv sync --locked

lint:
	uv run ruff check
	uv run ruff format --check
	uv run pyright

test:
	$(MAKE) -C firmware/test
	uv run pytest

# firmware/car/sketch.yaml sets the board and the library versions.
upload:
	arduino-cli compile --warnings all --build-property "compiler.cpp.extra_flags=-Werror=switch" firmware/car
	arduino-cli upload -p $(PORT) firmware/car
	@$(MAKE) --no-print-directory hardware-test

hardware-test:
	uv run tools/hardware_test.py --port $(PORT)

# STEP: gyro, line floor, line edge, minpwm, brake, speed or all. Example: make calibrate-usb STEP="line floor".
calibrate-usb:
	uv run python -m elegoo.calibrate --port $(PORT) $(STEP)

calibrate-wifi:
	uv run python -m elegoo.calibrate --tcp $(STEP)

# TEST: turn, move, wall or cliff. Example: make accept-usb TEST=wall.
accept-usb:
	uv run python -m elegoo.accept --port $(PORT) $(TEST)

accept-wifi:
	uv run python -m elegoo.accept --tcp $(TEST)

# The computer must be on the car Wi-Fi and have internet through the phone: see README, Usage.
agent:
	uv run python -m elegoo.agent --model $(MODEL) "$(TASK)"
