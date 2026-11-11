# Calibration

Run after the hardware test, after a hardware change, or when the `move` distance error grows. Run the commands from the repository root. Calibration writes `profile.json` and sets parameters in the car EEPROM.

## Setup

- Laminate floor without carpet. A wall with 150 cm of free floor in front of it.
- A table with a free edge.
- Battery at approximately 8 V. A low battery gives a short braking distance and a low speed.
- S1 at "upload", USB connected, battery switch on. Keep the USB cable slack: a tight cable turns the car.
- For Wi-Fi: S1 at "cam", the Mac on the car access point. Use `make calibrate-wifi` and `make accept-wifi`.

After each Enter, do not touch the car for 3 s: the car measures the gyro bias.

## 1. Calibrate

Run `make calibrate-usb`: all steps in order. To run one step: `make calibrate-usb STEP=<step>`, for example `STEP="line floor"`. Follow the prompts.

| Step | What to do | Expected result |
| --- | --- | --- |
| `gyro` | Put the car on the floor. | The script ends without an error. |
| `line floor` | Keep the car on the floor. Motors stay off. | Floor levels in `profile.json`. |
| `line edge` | Put the car on the table: wheels on the table, line sensors in the air over the edge. | Edge levels in `profile.json`. The script sets `cliff_th` between the floor and edge levels. |
| `minpwm` | Put the car on the floor with free space around it. | The car turns in place on each side with a rising PWM. `min_pwm` per side, approximately 40–50. |
| `brake` | 3 runs: put the car 150 cm from the wall, facing it. | The car stops before the wall at PWM 100, 125 and 150. The script sets `sonar_stop_cm` to the max braking distance + 5 cm. |
| `speed` | 3 runs, the same placement. | Each run ends with a sonar stop. Speed per PWM in `profile.json`, approximately 33/45/53 cm/s. |

## 2. Acceptance

Run `make accept-usb TEST=<test>`, in the order of the table below. Each test makes 10 reps. To make fewer reps: `uv run python -m elegoo.accept --port <port> --reps <n> <test>`. After each rep, enter the measurement. The script prints pass or fail per rep and the total.

| Test | What to do | Pass criteria |
| --- | --- | --- |
| `turn` | Make a protractor from tape on the floor. Put the car axis at 0°. After the turn, read the angle. | Reason `done`, angle 90 ± 5°. |
| `move` | Make a straight tape line of 100 cm with a start mark, and 50 cm of free floor after its end. Put the front wheels on the start mark, the car along the line. After the stop, measure the drift (car center to the line) and the distance (front wheels to the start mark). | Reason `done`, drift ≤ 5 cm, distance 100 ± 10 cm. |
| `wall` | Put the car 60 cm from the wall, facing it. The PWM cycles through 3 values, from the higher `min_pwm` + 10 to `max_pwm`. If the car does not brake, catch it and answer `y`. | Reason `sonar`, no contact. |
| `cliff tape` | Put black tape, 3–4 cm wide, across the path, 50 cm ahead of the car. If the car crosses the tape, the tape is too light: use a different tape. | Reason `cliff`, no wheel on the tape. |
| `cliff edge` | Run only after `cliff tape` passes. Put the car on the table, 50 cm from the edge, square to it. Hold a hand at the edge. | Reason `cliff`, no wheel over the edge. |

Results: [results-2026-11-11.md](results-2026-11-11.md).
