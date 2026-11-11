import dataclasses
import itertools
import json
from pathlib import Path

from elegoo.car import MS_PER_S
from elegoo.errors import ProfileError

type Table = tuple[tuple[int, float], ...]
type LineSample = tuple[int, int, int]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class MinPwm:
    left: int
    right: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class LineLevels:
    floor: LineSample | None = None
    edge: LineSample | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    """`batt_mv` is the battery voltage during the speed runs. `speed` is cm/s and `brake` is cm, both by PWM."""

    batt_mv: int | None = None
    min_pwm: MinPwm | None = None
    speed: Table | None = None
    brake: Table | None = None
    line: LineLevels | None = None

    def ms_for_cm(self, cm: float, *, pwm: int, batt_mv: int) -> int:
        if self.speed is None or self.batt_mv is None:
            raise ProfileError("profile has no speed calibration")
        cm_s = self._table_speed(self.speed, pwm) * batt_mv / self.batt_mv
        return round(cm / cm_s * MS_PER_S)

    def _table_speed(self, speed: Table, pwm: int) -> float:
        speeds = dict(speed)
        if pwm in speeds:
            return speeds[pwm]
        for (pwm0, cm_s0), (pwm1, cm_s1) in itertools.pairwise(sorted(speed)):
            if pwm0 < pwm < pwm1:
                return cm_s0 + (cm_s1 - cm_s0) * (pwm - pwm0) / (pwm1 - pwm0)
        raise ProfileError(f"PWM {pwm} is outside the speed table")


def load_profile(path: Path) -> Profile:
    """Returns an empty profile if the file does not exist."""
    if not path.exists():
        return Profile()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ProfileError(f"bad JSON in {path}") from error
    if not isinstance(data, dict):
        raise ProfileError(f"{path} is not a JSON object")
    return Profile(
        batt_mv=_parse_int(data.get("batt_mv")),
        min_pwm=_parse_min_pwm(data.get("min_pwm")),
        speed=_parse_table(data.get("speed")),
        brake=_parse_table(data.get("brake")),
        line=_parse_line(data.get("line")),
    )


def save_profile(profile: Profile, path: Path) -> None:
    path.write_text(json.dumps(dataclasses.asdict(profile), indent=2) + "\n")


def _parse_int(value: object) -> int | None:
    match value:
        case None:
            return None
        case int():
            return value
        case _:
            raise ProfileError(f"bad integer {value}")


def _parse_min_pwm(value: object) -> MinPwm | None:
    match value:
        case None:
            return None
        case {"left": int(left), "right": int(right)}:
            return MinPwm(left=left, right=right)
        case _:
            raise ProfileError(f"bad min_pwm {value}")


def _parse_table(value: object) -> Table | None:
    match value:
        case None:
            return None
        case list():
            return tuple(_parse_point(point) for point in value)
        case _:
            raise ProfileError(f"bad table {value}")


def _parse_point(value: object) -> tuple[int, float]:
    match value:
        case [int(pwm), int() | float() as number]:
            return pwm, float(number)
        case _:
            raise ProfileError(f"bad table point {value}")


def _parse_line(value: object) -> LineLevels | None:
    match value:
        case None:
            return None
        case dict():
            return LineLevels(floor=_parse_line_sample(value.get("floor")), edge=_parse_line_sample(value.get("edge")))
        case _:
            raise ProfileError(f"bad line {value}")


def _parse_line_sample(value: object) -> LineSample | None:
    match value:
        case None:
            return None
        case [int(left), int(middle), int(right)]:
            return left, middle, right
        case _:
            raise ProfileError(f"bad line sample {value}")
