PORT := /dev/cu.usbserial-1110

.PHONY: init install lint test upload hardware-test

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

# firmware/car/sketch.yaml sets the board and the library versions.
upload:
	arduino-cli compile --warnings all --build-property "compiler.cpp.extra_flags=-Werror=switch" firmware/car
	arduino-cli upload -p $(PORT) firmware/car

hardware-test:
	uv run tools/hardware_test_wired.py --port $(PORT)
