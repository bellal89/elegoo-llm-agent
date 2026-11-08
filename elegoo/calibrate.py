import argparse
import dataclasses
import enum
import itertools
import logging
import statistics
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from elegoo.car import HB_MS_SERIAL, HB_MS_TCP, MS_PER_S, Car
from elegoo.errors import CalibrationError
from elegoo.link import SerialLink, TcpLink
from elegoo.profile import LineLevels, LineSample, MinPwm, Profile, load_profile, save_profile
from elegoo.protocol import MotionKind, Param, StopReason, Tele

PROFILE_PATH = Path("profile.json")
TELE_PERIOD_MS = 100
TELE_TIMEOUT_S = 1.0
DONE_TIMEOUT_S = 1.0
LINE_SAMPLES = 20
LINE_SENSORS = 3
NO_ECHO_CM = 0
MINPWM_START = 30
MINPWM_STOP = 150
MINPWM_STEP = 5
MINPWM_STEP_MS = 300
MINPWM_YAW_RATE_DPS = 10.0
RUN_PWMS = (100, 125, 150)
BRAKE_TRIGGER_CM = 60
BRAKE_SETTLE_S = 0.5
SONAR_STOP_MARGIN_CM = 5
# The firmware PWM limit. Calibration runs up to it.
MAX_PWM = 150
SPEED_SKIP_MS = 300

logger = logging.getLogger(__name__)


class Step(enum.StrEnum):
    GYRO = "gyro"
    LINE = "line"
    MINPWM = "minpwm"
    BRAKE = "brake"
    SPEED = "speed"
    ALL = "all"


class Surface(enum.StrEnum):
    FLOOR = "floor"
    EDGE = "edge"


class Side(enum.StrEnum):
    LEFT = "left"
    RIGHT = "right"


def cliff_threshold(floor: LineSample, edge: LineSample, *, line_mask: int) -> int:
    """Uses only the sensors with their bit set in `line_mask`."""
    enabled = [sensor for sensor in range(LINE_SENSORS) if line_mask & (1 << sensor)]
    max_floor = max(floor[sensor] for sensor in enabled)
    min_edge = min(edge[sensor] for sensor in enabled)
    if max_floor >= min_edge:
        raise CalibrationError(f"floor level {max_floor} is not below edge level {min_edge}")
    return (max_floor + min_edge) // 2


def max_yaw_rate_dps(teles: list[Tele]) -> float:
    return max(
        (abs(b.yaw_deg - a.yaw_deg) / (b.ms - a.ms) * MS_PER_S for a, b in itertools.pairwise(teles)),
        default=0.0,
    )


def fit_speed_cm_s(teles: list[Tele]) -> float:
    """Fits the approach speed to the wall. Skips the acceleration and the frames without a sonar echo."""
    samples = [tele for tele in teles if tele.sonar_cm != NO_ECHO_CM and tele.ms - teles[0].ms >= SPEED_SKIP_MS]
    if len(samples) < 2:
        raise CalibrationError(f"only {len(samples)} speed samples")
    fit = statistics.linear_regression([tele.ms for tele in samples], [tele.sonar_cm for tele in samples])
    return -fit.slope * MS_PER_S


def calibrate_line(car: Car, profile: Profile, *, surface: Surface) -> Profile:
    teles = [car.next_tele(TELE_TIMEOUT_S) for _ in range(LINE_SAMPLES)]
    left, middle, right = (
        round(statistics.mean(tele.line[sensor] for tele in teles)) for sensor in range(LINE_SENSORS)
    )
    sample = (left, middle, right)
    logger.info("Line %s: %s", surface, sample)
    line = profile.line or LineLevels()
    match surface:
        case Surface.FLOOR:
            line = dataclasses.replace(line, floor=sample)
        case Surface.EDGE:
            line = dataclasses.replace(line, edge=sample)
    if line.floor is not None and line.edge is not None:
        threshold = cliff_threshold(line.floor, line.edge, line_mask=int(car.params()[Param.LINE_MASK]))
        car.set_param(Param.CLIFF_TH, threshold)
        logger.info("Cliff threshold: %s", threshold)
    return dataclasses.replace(profile, line=line)


def calibrate_minpwm(car: Car, profile: Profile) -> Profile:
    min_pwm = MinPwm(left=_min_pwm(car, Side.LEFT), right=_min_pwm(car, Side.RIGHT))
    logger.info("Min PWM: %s", min_pwm)
    return dataclasses.replace(profile, min_pwm=min_pwm)


def calibrate_brake(car: Car, profile: Profile) -> Profile:
    max_cmd_ms = int(car.params()[Param.MAX_CMD_MS])
    brake = tuple((pwm, _brake_cm(car, pwm, max_cmd_ms=max_cmd_ms)) for pwm in RUN_PWMS)
    car.set_param(Param.SONAR_STOP_CM, round(max(dict(brake).values())) + SONAR_STOP_MARGIN_CM)
    return dataclasses.replace(profile, brake=brake)


def calibrate_speed(car: Car, profile: Profile) -> Profile:
    max_cmd_ms = int(car.params()[Param.MAX_CMD_MS])
    speed: list[tuple[int, float]] = []
    batt_mvs: list[int] = []
    for pwm in RUN_PWMS:
        input(f"Place the car ~150 cm from a wall for the speed run at PWM {pwm}. Press Enter.")
        car.drive(pwm, right=pwm, duration_ms=max_cmd_ms)
        teles = list(_drive_teles(car))
        logger.info("Speed run at PWM %s ended: %s", pwm, car.wait_done(DONE_TIMEOUT_S))
        speed.append((pwm, fit_speed_cm_s(teles)))
        batt_mvs.extend(tele.batt_mv for tele in teles)
    logger.info("Speed: %s", speed)
    return dataclasses.replace(profile, speed=tuple(speed), batt_mv=round(statistics.mean(batt_mvs)))


def calibrate_all(car: Car) -> None:
    input("Put the car on the floor. Do not touch it. Press Enter.")
    car.gyro()
    input("Keep the car on the floor for the floor line levels. Press Enter.")
    _update_profile(lambda profile: calibrate_line(car, profile, surface=Surface.FLOOR))
    input("Put the car on a table: wheels on the table, line sensors in the air over the edge. Press Enter.")
    _update_profile(lambda profile: calibrate_line(car, profile, surface=Surface.EDGE))
    input("Put the car on the floor with free space around it for the min PWM runs. Press Enter.")
    _update_profile(lambda profile: calibrate_minpwm(car, profile))
    _update_profile(lambda profile: calibrate_brake(car, profile))
    _update_profile(lambda profile: calibrate_speed(car, profile))


def _min_pwm(car: Car, side: Side) -> int:
    for pwm in range(MINPWM_START, MINPWM_STOP + 1, MINPWM_STEP):
        match side:
            case Side.LEFT:
                car.drive(pwm, right=0, duration_ms=MINPWM_STEP_MS)
            case Side.RIGHT:
                car.drive(0, right=pwm, duration_ms=MINPWM_STEP_MS)
        teles = list(_drive_teles(car))
        car.wait_done(DONE_TIMEOUT_S)
        if max_yaw_rate_dps(teles) > MINPWM_YAW_RATE_DPS:
            return pwm
    raise CalibrationError(f"{side} side does not move at PWM {MINPWM_STOP}")


def _brake_cm(car: Car, pwm: int, *, max_cmd_ms: int) -> float:
    input(f"Place the car ~150 cm from a wall for the brake run at PWM {pwm}. Press Enter.")
    car.drive(pwm, right=pwm, duration_ms=max_cmd_ms)
    trigger = next(
        (tele for tele in _drive_teles(car) if NO_ECHO_CM < tele.sonar_cm <= BRAKE_TRIGGER_CM),
        None,
    )
    if trigger is None:
        raise CalibrationError(f"car stopped before {BRAKE_TRIGGER_CM} cm: {car.wait_done(DONE_TIMEOUT_S)}")
    car.stop()
    reason = car.wait_done(DONE_TIMEOUT_S)
    if reason is not StopReason.CMD:
        raise CalibrationError(f"car stopped by {reason}, not by the stop command")
    time.sleep(BRAKE_SETTLE_S)
    brake_cm = trigger.sonar_cm - car.next_tele(TELE_TIMEOUT_S).sonar_cm
    logger.info("Brake at PWM %s: %s cm", pwm, brake_cm)
    return brake_cm


def _drive_teles(car: Car) -> Iterator[Tele]:
    """Yields telemetry until the drive ends."""
    while (tele := car.next_tele(TELE_TIMEOUT_S)).motion is MotionKind.DRIVE:
        yield tele


def _update_profile(change: Callable[[Profile], Profile]) -> None:
    save_profile(change(load_profile(PROFILE_PATH)), PROFILE_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Calibrate the car. Write the results to {PROFILE_PATH}.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--port", help="serial port of the UNO")
    target.add_argument("--tcp", action="store_true", help="connect through the ESP32 Wi-Fi bridge")
    steps = parser.add_subparsers(dest="step", required=True)
    steps.add_parser(Step.GYRO, help="measure the gyro bias")
    line = steps.add_parser(Step.LINE, help="measure the line sensor levels, motors off")
    line.add_argument("surface", choices=list(Surface))
    steps.add_parser(Step.MINPWM, help="find the min start PWM per side")
    steps.add_parser(Step.BRAKE, help="measure the braking distance to a wall, set sonar_stop_cm")
    steps.add_parser(Step.SPEED, help="measure the speed toward a wall")
    steps.add_parser(Step.ALL, help="run all steps in order")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    with Car(TcpLink(), HB_MS_TCP) if args.tcp else Car(SerialLink(args.port), HB_MS_SERIAL) as car:
        car.set_param(Param.MAX_PWM, MAX_PWM)
        car.tele(TELE_PERIOD_MS)
        match Step(args.step):
            case Step.GYRO:
                car.gyro()
            case Step.LINE:
                _update_profile(lambda profile: calibrate_line(car, profile, surface=Surface(args.surface)))
            case Step.MINPWM:
                _update_profile(lambda profile: calibrate_minpwm(car, profile))
            case Step.BRAKE:
                _update_profile(lambda profile: calibrate_brake(car, profile))
            case Step.SPEED:
                _update_profile(lambda profile: calibrate_speed(car, profile))
            case Step.ALL:
                calibrate_all(car)
        car.tele(0)


if __name__ == "__main__":
    main()
