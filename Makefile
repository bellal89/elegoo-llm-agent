PORT := /dev/cu.usbserial-1110
STEP := all

.PHONY: init install lint test upload hardware-test calibrate calibrate-wifi

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

hardware-test:
	uv run tools/hardware_test_wired.py --port $(PORT)

# STEP: gyro, line floor, line edge, minpwm, brake, speed or all. Example: make calibrate STEP="line floor".
calibrate:
	uv run python -m elegoo.calibrate --port $(PORT) $(STEP)

calibrate-wifi:
	uv run python -m elegoo.calibrate --tcp $(STEP)
