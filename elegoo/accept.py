import argparse
import dataclasses
import enum
import itertools
import logging
from collections.abc import Callable

from elegoo.calibrate import PROFILE_PATH, TELE_PERIOD_MS, TELE_TIMEOUT_S, move_at, move_pwm_restored
from elegoo.car import HB_MS_SERIAL, HB_MS_TCP, MS_PER_S, TURN_DONE_TIMEOUT_S, Car
from elegoo.errors import ProfileError
from elegoo.link import SerialLink, TcpLink
from elegoo.profile import Profile, load_profile
from elegoo.protocol import Param, StopReason

REPS = 10
TURN_TARGET_DEG = 90
TURN_ERR_MAX_DEG = 5
MOVE_TARGET_CM = 100
MOVE_DRIFT_MAX_CM = 5
MOVE_DIST_ERR_MAX_CM = 10
WALL_PWM_MARGIN = 10
WALL_START_CM = 60
CLIFF_START_CM = 50
DONE_MARGIN_S = 1.0
YES = "y"
NO = "n"


class AcceptTest(enum.StrEnum):
    TURN = "turn"
    MOVE = "move"
    WALL = "wall"
    CLIFF = "cliff"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RepResult:
    passed: bool
    measurement: str


def ask_number(prompt: str) -> float:
    while True:
        answer = input(prompt)
        try:
            return float(answer)
        except ValueError:
            print(f"Enter a number, not {answer!r}.")


def ask_yes(prompt: str) -> bool:
    while (answer := input(f"{prompt} ({YES}/{NO}) ").strip().lower()) not in (YES, NO):
        print(f"Enter {YES} or {NO}.")
    return answer == YES


def wall_pwms(profile: Profile, *, max_pwm: int) -> tuple[int, int, int]:
    if profile.min_pwm is None:
        raise ProfileError("profile has no min PWM calibration")
    low = max(profile.min_pwm.left, profile.min_pwm.right) + WALL_PWM_MARGIN
    return low, (low + max_pwm) // 2, max_pwm


def turn_rep(car: Car) -> RepResult:
    _wait_placed("Put the car on the floor protractor at 0 deg.")
    car.gyro()
    car.turn(TURN_TARGET_DEG)
    reason = car.wait_done(TURN_DONE_TIMEOUT_S)
    angle_deg = ask_number("Angle by the protractor, deg: ")
    return RepResult(
        passed=reason is StopReason.DONE and abs(angle_deg - TURN_TARGET_DEG) <= TURN_ERR_MAX_DEG,
        measurement=f"{reason}, {angle_deg} deg",
    )


def move_rep(car: Car, profile: Profile) -> RepResult:
    _wait_placed(f"Put the car at the start of the floor tape line, {MOVE_TARGET_CM} cm of free space ahead.")
    car.gyro()
    duration_ms = profile.ms_for_cm(
        MOVE_TARGET_CM,
        pwm=int(car.params()[Param.MOVE_PWM]),
        batt_mv=car.next_tele(TELE_TIMEOUT_S).batt_mv,
    )
    car.move(duration_ms)
    reason = car.wait_done(duration_ms / MS_PER_S + DONE_MARGIN_S)
    drift_cm = ask_number("Drift from the tape line, cm: ")
    distance_cm = ask_number("Distance along the tape line, cm: ")
    return RepResult(
        passed=reason is StopReason.DONE
        and abs(drift_cm) <= MOVE_DRIFT_MAX_CM
        and abs(distance_cm - MOVE_TARGET_CM) <= MOVE_DIST_ERR_MAX_CM,
        measurement=f"{reason}, drift {drift_cm} cm, distance {distance_cm} cm",
    )


def wall_rep(car: Car, *, pwm: int) -> RepResult:
    _wait_placed(f"Place the car ~{WALL_START_CM} cm from a wall.")
    reason = _move_until_stop(car, pwm)
    contact = ask_yes("Did the car touch the wall?")
    return RepResult(
        passed=reason is StopReason.SONAR and not contact,
        measurement=f"PWM {pwm}, {reason}, {'contact' if contact else 'no contact'}",
    )


def cliff_rep(car: Car) -> RepResult:
    _wait_placed(f"Place the car ~{CLIFF_START_CM} cm before the black tape or the table edge. Hold a hand ready.")
    reason = _move_until_stop(car, int(car.params()[Param.MAX_PWM]))
    reached = ask_yes("Did a wheel reach the tape or the edge?")
    return RepResult(
        passed=reason is StopReason.CLIFF and not reached,
        measurement=f"{reason}, {'a wheel reached' if reached else 'no wheel reached'} the tape or the edge",
    )


def run_reps(rep: Callable[[], RepResult], *, reps: int) -> None:
    passed = 0
    for index in range(reps):
        print(f"Rep {index + 1}/{reps}")
        result = rep()
        print(f"Rep {index + 1}: {'pass' if result.passed else 'fail'}, {result.measurement}")
        passed += result.passed
    print(f"Total: {passed}/{reps} pass")


def _wait_placed(place: str) -> None:
    input(f"{place} Press Enter, then keep the car still for 3 s.")


def _move_until_stop(car: Car, pwm: int) -> StopReason:
    with move_pwm_restored(car):
        duration_ms = move_at(car, pwm)
        return car.wait_done(duration_ms / MS_PER_S + DONE_MARGIN_S)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Run the acceptance tests with the calibration in {PROFILE_PATH}.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--port", help="serial port of the UNO")
    target.add_argument("--tcp", action="store_true", help="connect through the ESP32 Wi-Fi bridge")
    parser.add_argument("--reps", type=int, default=REPS)
    tests = parser.add_subparsers(dest="test", required=True)
    tests.add_parser(AcceptTest.TURN, help=f"turn {TURN_TARGET_DEG} deg, measure the angle")
    tests.add_parser(AcceptTest.MOVE, help=f"move {MOVE_TARGET_CM} cm, measure the drift and the distance")
    tests.add_parser(AcceptTest.WALL, help="move toward a wall at 3 PWMs, check the sonar stop")
    tests.add_parser(AcceptTest.CLIFF, help="move at max_pwm toward black tape or a table edge")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    profile = load_profile(PROFILE_PATH)

    with Car(TcpLink(), HB_MS_TCP) if args.tcp else Car(SerialLink(args.port), HB_MS_SERIAL) as car:
        car.tele(TELE_PERIOD_MS)
        match AcceptTest(args.test):
            case AcceptTest.TURN:
                run_reps(lambda: turn_rep(car), reps=args.reps)
            case AcceptTest.MOVE:
                run_reps(lambda: move_rep(car, profile), reps=args.reps)
            case AcceptTest.WALL:
                pwms = itertools.cycle(wall_pwms(profile, max_pwm=int(car.params()[Param.MAX_PWM])))
                run_reps(lambda: wall_rep(car, pwm=next(pwms)), reps=args.reps)
            case AcceptTest.CLIFF:
                run_reps(lambda: cliff_rep(car), reps=args.reps)
        car.tele(0)


if __name__ == "__main__":
    main()
