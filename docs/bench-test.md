# Bench test

Run after each firmware upload. The user is present for all steps.

## Setup

1. Set S1 to "upload". Connect USB. Set the battery switch to on: USB power alone does not drive the motors.
2. Upload:

   ```sh
   ACLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
   "$ACLI" upload -b arduino:avr:uno -p /dev/cu.usbserial-1110 firmware/car
   ```

3. Open the serial port at 9600 baud. Each port open resets the UNO: boot and gyro bias take about 4 s. Do not touch the car during this time.
4. Send `{set,hb_ms,60000}`. Each command then resets the heartbeat timer, so no `{hb}` is necessary for 60 s. `hb_ms` is not stored: a reset sets it to 1000 again.

## Checklist

| # | Action | Expected |
| --- | --- | --- |
| 1 | Boot | `{p,…}` for all params, then `{p,imu,1}`. On this car `line_mask` is 6 (left line sensor is dead). |
| 2 | Wheels off the ground. `{drive,100,100,1000}` | `{ok,drive}`. Both sides turn forward for 1 s. `{done,drive,done}`. |
| 3 | Wheels off the ground. `{drive,100,-100,1000}` | Left side forward, right side back. `{done,drive,done}`. |
| 4 | Car on the floor. `{turn,90}` | `{ok,turn}`, `{done,turn,done}`. The car turns right by approximately 90°. Do not turn the car by hand: the hand is too slow for the 3 s turn timeout. |
| 5 | Car on the floor, wall ahead. `{drive,100,100,5000}` | `{done,drive,sonar}` at 25 cm. The car stops at approximately 18 cm, without contact. Keep hands away from the sonar before the start: one reading below 25 cm stops the car. |
| 6 | Car on a table, edge ahead. Hold a hand ready. `{drive,100,100,5000}` | `{done,drive,cliff}` after a short back-off. The wheels stay on the table. Do not use PWM above 150 near an edge. |
| 7 | `{set,hb_ms,1000}`, then `{drive,100,100,3000}`. Send nothing more. | `{done,drive,hb}` after approximately 1 s. |
| 8 | `{tele,100}`, then `{tele,0}` | `{t,…}` frames every 100 ms. The stream stops after `{tele,0}`. |
| 9 | `{drive,100,100,3000}`, then `{stop}` | `{ok,stop}`, then `{done,drive,cmd}`. |
