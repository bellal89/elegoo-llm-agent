import pytest

from elegoo.calibrate import cliff_threshold, fit_speed_cm_s, max_yaw_rate_dps, min_turning_pwm
from elegoo.errors import CalibrationError
from elegoo.protocol import MotionKind, StopReason, Tele

FLOOR = (1017, 45, 46)
EDGE = (1017, 1010, 1012)
LEFT_MASKED = 6
ALL_SENSORS = 7


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


def test_fit_speed_skips_start_and_no_echo() -> None:
    teles = [make_tele(ms, sonar_cm=150 - 3 * ms // 100) for ms in range(1000, 2100, 100)]
    teles[0] = make_tele(1000, sonar_cm=150)
    teles[5] = make_tele(1500, sonar_cm=0)
    assert fit_speed_cm_s(teles) == pytest.approx(30.0)


def test_fit_speed_without_samples() -> None:
    with pytest.raises(CalibrationError):
        fit_speed_cm_s([make_tele(0), make_tele(100), make_tele(300, sonar_cm=0)])


@pytest.mark.parametrize(
    ("yaw_rates", "pwm"),
    [
        pytest.param([(30, 12.0), (35, 0.1), (40, 1.7), (45, 0.2), (50, 16.3), (55, 25.9)], 50, id="backlash jolt"),
        pytest.param([(30, 15.0), (35, 20.0)], 30, id="turns at once"),
    ],
)
def test_min_turning_pwm(yaw_rates: list[tuple[int, float]], pwm: int) -> None:
    assert min_turning_pwm(iter(yaw_rates)) == pwm


@pytest.mark.parametrize(
    "yaw_rates",
    [
        pytest.param([(30, 0.0), (35, 0.5)], id="no turn"),
        pytest.param([(30, 0.0), (35, 15.0)], id="turn only at the last step"),
    ],
)
def test_min_turning_pwm_without_turn(yaw_rates: list[tuple[int, float]]) -> None:
    with pytest.raises(CalibrationError):
        min_turning_pwm(iter(yaw_rates))
