import pytest

from elegoo import calibrate
from elegoo.calibrate import (
    brake_trigger,
    calibrate_brake,
    calibrate_minpwm,
    calibrate_speed,
    cliff_threshold,
    fit_speed_cm_s,
    max_yaw_rate_dps,
    min_turning_pwm,
)
from elegoo.car import HB_MS_SERIAL, Car
from elegoo.errors import CalibrationError, ReplyTimeoutError
from elegoo.profile import Profile
from elegoo.protocol import MotionKind, StopReason, Tele
from tests.conftest import FakeLink

FLOOR = (1017, 45, 46)
EDGE = (1017, 1010, 1012)
LEFT_MASKED = 6
ALL_SENSORS = 7
WALL_RUN_GET = ["{p,move_pwm,90}", "{p,max_cmd_ms,5000}", "{p,pwm_limit,150}", "{p,imu,1}", "{ok,get}"]
WALL_RUN_MOVE = "{move,5000}"
GYRO = "{gyro}"
SONAR_ERROR_CM = 98
RESTORE_MOVE_PWM = "{set,move_pwm,90}"
HB_FRAME = "{hb}"
STOP_BY_CMD = ["{ok,stop}", "{done,move,cmd}"]


def tele_frame(sonar_cm: int, motion: MotionKind, *, ms: int = 0) -> str:
    return f"{{t,{ms},{sonar_cm},45,1017,46,0,7800,{motion},none}}"


def brake_run(*, trigger_cm: int, final_cm: int) -> list[str]:
    """Has a single sonar error in the first frame after the stop."""
    return [
        tele_frame(120, MotionKind.MOVE),
        tele_frame(trigger_cm + 3, MotionKind.MOVE),
        tele_frame(trigger_cm, MotionKind.MOVE),
        tele_frame(SONAR_ERROR_CM, MotionKind.IDLE),
        *[tele_frame(final_cm, MotionKind.IDLE)] * 5,
    ]


@pytest.fixture
def calibration_link(link: FakeLink, monkeypatch: pytest.MonkeyPatch) -> FakeLink:
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr(calibrate, "SETTLE_S", 0)
    link.script["{get}"] = WALL_RUN_GET
    link.script[WALL_RUN_MOVE] = ["{ok,move}"]
    link.script[GYRO] = ["{ok,gyro}"]
    link.script["{stop}"] = STOP_BY_CMD
    for pwm in (90, 100, 125, 150):
        link.script[f"{{set,move_pwm,{pwm}}}"] = ["{ok,set}"]
    link.script["{set,sonar_stop_cm,15}"] = ["{ok,set}"]
    return link


def make_tele(ms: int, *, sonar_cm: int = 100, yaw_deg: float = 0.0) -> Tele:
    return Tele(
        ms=ms,
        sonar_cm=sonar_cm,
        line=FLOOR,
        yaw_deg=yaw_deg,
        batt_mv=7800,
        motion=MotionKind.DRIVE,
        stop_reason=StopReason.NONE,
    )


def test_cliff_threshold_skips_masked_sensor() -> None:
    assert cliff_threshold(FLOOR, EDGE, line_mask=LEFT_MASKED) == 528


def test_cliff_threshold_rejects_overlap() -> None:
    with pytest.raises(CalibrationError):
        cliff_threshold(FLOOR, EDGE, line_mask=ALL_SENSORS)


@pytest.mark.parametrize(
    ("yaws", "rate_dps"),
    [
        pytest.param([0.0, 1.0, 3.0], 20.0, id="right"),
        pytest.param([0.0, -2.0, -2.5], 20.0, id="left"),
        pytest.param([0.0], 0.0, id="one frame"),
    ],
)
def test_max_yaw_rate_dps(yaws: list[float], rate_dps: float) -> None:
    teles = [make_tele(index * 100, yaw_deg=yaw) for index, yaw in enumerate(yaws)]
    assert max_yaw_rate_dps(teles) == pytest.approx(rate_dps)


def wall_approach() -> list[Tele]:
    """30 cm/s toward the wall."""
    return [make_tele(ms, sonar_cm=150 - 3 * ms // 100) for ms in range(1000, 2100, 100)]


def test_fit_speed_skips_start_and_no_echo() -> None:
    teles = wall_approach()
    teles[:3] = [make_tele(ms, sonar_cm=150) for ms in range(1000, 1300, 100)]
    teles[5] = make_tele(1500, sonar_cm=0)
    assert fit_speed_cm_s(teles) == pytest.approx(30.0)


def test_fit_speed_ignores_sonar_error() -> None:
    teles = wall_approach()
    teles[6] = make_tele(1600, sonar_cm=58)
    assert fit_speed_cm_s(teles) == pytest.approx(30.0, abs=1.0)


@pytest.mark.parametrize(
    "teles",
    [
        pytest.param([make_tele(0), make_tele(100), make_tele(300, sonar_cm=0)], id="no samples"),
        pytest.param([make_tele(ms, sonar_cm=50 + 3 * ms // 100) for ms in range(0, 1000, 100)], id="receding wall"),
    ],
)
def test_fit_speed_rejects(teles: list[Tele]) -> None:
    with pytest.raises(CalibrationError):
        fit_speed_cm_s(teles)


@pytest.mark.parametrize(
    ("sonars", "trigger_ms"),
    [
        pytest.param([123, 58, 114, 70, 59, 55], 500, id="sonar error"),
        pytest.param([80, 0, 60, 57], 300, id="no echo"),
        pytest.param([80, 70, 65], None, id="far"),
    ],
)
def test_brake_trigger(sonars: list[int], trigger_ms: int | None) -> None:
    trigger = brake_trigger(iter([make_tele(index * 100, sonar_cm=sonar) for index, sonar in enumerate(sonars)]))
    assert (None if trigger is None else trigger.ms) == trigger_ms


def test_min_turning_pwm_ignores_backlash_jolt() -> None:
    yaw_rates = [(30, 12.0), (35, 0.1), (40, 1.7), (45, 0.2), (50, 16.3), (55, 25.9)]
    assert min_turning_pwm(iter(yaw_rates)) == 50


def test_min_turning_pwm_rejects_turn_only_at_last_step() -> None:
    with pytest.raises(CalibrationError):
        min_turning_pwm(iter([(30, 0.0), (35, 15.0)]))


def test_calibrate_brake_sets_sonar_stop_cm(calibration_link: FakeLink, car: Car) -> None:
    calibration_link.streams[WALL_RUN_MOVE] = brake_run(trigger_cm=55, final_cm=45)
    assert calibrate_brake(car, Profile()).brake == ((100, 10.0), (125, 10.0), (150, 10.0))
    sent = [frame for frame in calibration_link.sent if frame != HB_FRAME]
    assert sent[-2:] == [RESTORE_MOVE_PWM, "{set,sonar_stop_cm,15}"]
    assert [frame for frame in sent if frame in (GYRO, WALL_RUN_MOVE)] == [GYRO, WALL_RUN_MOVE] * 3


@pytest.mark.parametrize(
    ("run", "stop_replies"),
    [
        pytest.param(
            [tele_frame(120, MotionKind.MOVE), "{done,move,sonar}", tele_frame(90, MotionKind.IDLE)],
            STOP_BY_CMD,
            id="stopped before the trigger",
        ),
        pytest.param(brake_run(trigger_cm=55, final_cm=45), ["{ok,stop}", "{done,move,cliff}"], id="cliff stop"),
        pytest.param(brake_run(trigger_cm=55, final_cm=0), STOP_BY_CMD, id="no echo after the stop"),
        pytest.param(brake_run(trigger_cm=55, final_cm=58), STOP_BY_CMD, id="negative brake"),
    ],
)
def test_calibrate_brake_rejects_bad_run(
    calibration_link: FakeLink, car: Car, run: list[str], stop_replies: list[str]
) -> None:
    calibration_link.streams[WALL_RUN_MOVE] = run
    calibration_link.script["{stop}"] = stop_replies
    with pytest.raises(CalibrationError):
        calibrate_brake(car, Profile())
    assert RESTORE_MOVE_PWM in calibration_link.sent


def test_calibrate_brake_needs_pwm_limit(calibration_link: FakeLink) -> None:
    calibration_link.script["{get}"] = [frame for frame in WALL_RUN_GET if "pwm_limit" not in frame]
    with Car(calibration_link, HB_MS_SERIAL) as car, pytest.raises(CalibrationError):
        calibrate_brake(car, Profile())


def test_calibrate_speed_rejects_run_without_sonar_stop(calibration_link: FakeLink, car: Car) -> None:
    calibration_link.streams[WALL_RUN_MOVE] = [
        *[tele_frame(150 - 3 * ms // 100, MotionKind.MOVE, ms=ms) for ms in range(0, 1000, 100)],
        "{done,move,done}",
        tele_frame(120, MotionKind.IDLE, ms=1000),
    ]
    with pytest.raises(CalibrationError):
        calibrate_speed(car, Profile())


def test_calibrate_minpwm_measures_gyro_bias_first(calibration_link: FakeLink, car: Car) -> None:
    with pytest.raises(ReplyTimeoutError):
        calibrate_minpwm(car, Profile())
    assert [frame for frame in calibration_link.sent if frame not in (HB_FRAME, "{get}")][-2:] == [
        GYRO,
        "{drive,30,0,300}",
    ]
