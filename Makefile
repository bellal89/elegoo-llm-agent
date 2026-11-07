PORT := /dev/cu.usbserial-1110

.PHONY: upload hardware-test

# firmware/car/sketch.yaml sets the board and the library versions.
upload:
	arduino-cli compile --warnings all --build-property "compiler.cpp.extra_flags=-Werror=switch" firmware/car
	arduino-cli upload -p $(PORT) firmware/car

hardware-test:
	uv run tools/hardware_test_wired.py --port $(PORT)
