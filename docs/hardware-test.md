# Hardware test

Run after each firmware change. Run the commands from the repository root.

1. Set S1 to "upload". Connect USB. Set the battery switch to on.
2. Run `make upload`. The command flashes the car, then starts the hardware test.
3. At the prompt, put the car on a table, wheels down, with 30 cm of free space around it. Keep USB connected. Press Enter. Do not touch the car until the script ends (about 20 s).

Expected: the car turns in place right and left a few times, then stops. The script prints `ALL PASS`.

To run only the hardware test: `make hardware-test`.
