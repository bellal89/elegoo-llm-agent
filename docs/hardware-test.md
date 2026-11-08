# Hardware test

Run after each firmware change. Run the commands from the repository root.

## 1. Upload

1. Set S1 to "upload". Connect USB. Set the battery switch to on.
2. Run `make upload`.

## 2. Wired test

1. Put the car on a table, wheels down, with 30 cm of free space around it. Keep USB connected.
2. Run `make hardware-test`. Do not touch the car until the script ends (about 20 s).

Expected: the car turns in place right and left a few times, then stops. The script prints `ALL PASS`.

## 3. Wall stop

1. Disconnect USB. Keep the battery switch on.
2. Put the car on the floor, a wall 0.5 to 1 m ahead.
3. Push the mode button once. Move the hand away.

Expected: the LED blinks blue for 3 s, stays blue for 2 s, then turns green and the car moves forward. The car stops without contact. The front wheels are approximately `sonar_stop_cm` + 3 cm from the wall (28 cm at the default 25). The LED is red.

## 4. Edge stop

1. Put the car on a table, the edge 0.5 m ahead. Hold a hand ready.
2. Push the mode button once. Move the hand away.

Expected: the same LED sequence. The car stops at the edge and backs off a short distance. The front wheels are approximately 9 cm from the edge. The LED is red.

