from pathlib import Path

import pytest

from elegoo.errors import ProfileError
from elegoo.profile import LineLevels, MinPwm, Profile, load_profile, save_profile

SPEED = ((100, 20.0), (160, 50.0))
BRAKE = ((100, 2.0), (130, 4.0), (160, 6.0))


def make_profile() -> Profile:
    return Profile(
        batt_mv=7400,
        min_pwm=MinPwm(left=70, right=75),
        speed=SPEED,
        brake=BRAKE,
        line=LineLevels(floor=(1017, 45, 46), edge=(1017, 1010, 1012)),
    )


@pytest.mark.parametrize(
    ("pwm", "batt_mv", "ms"),
    [
        pytest.param(100, 7400, 5000, id="table point"),
        pytest.param(130, 7400, 2857, id="interpolated"),
        pytest.param(100, 3700, 10000, id="low battery"),
    ],
)
def test_ms_for_cm(pwm: int, batt_mv: int, ms: int) -> None:
    assert make_profile().ms_for_cm(100, pwm=pwm, batt_mv=batt_mv) == ms


@pytest.mark.parametrize(
    ("profile", "pwm"),
    [
        pytest.param(make_profile(), 99, id="below table"),
        pytest.param(make_profile(), 161, id="above table"),
        pytest.param(Profile(batt_mv=7400), 100, id="no speed"),
        pytest.param(Profile(speed=SPEED), 100, id="no battery"),
    ],
)
def test_ms_for_cm_rejects(profile: Profile, pwm: int) -> None:
    with pytest.raises(ProfileError):
        profile.ms_for_cm(100, pwm=pwm, batt_mv=7400)


@pytest.mark.parametrize(
    "profile",
    [
        pytest.param(make_profile(), id="full"),
        pytest.param(Profile(line=LineLevels(floor=(1017, 45, 46))), id="partial"),
    ],
)
def test_save_load_round_trip(tmp_path: Path, profile: Profile) -> None:
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    assert load_profile(path) == profile


def test_load_missing_file(tmp_path: Path) -> None:
    assert load_profile(tmp_path / "profile.json") == Profile()


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("{", id="bad json"),
        pytest.param("[]", id="not an object"),
        pytest.param('{"batt_mv": "7400"}', id="string number"),
        pytest.param('{"speed": [[100]]}', id="short point"),
        pytest.param('{"line": {"floor": [1, 2]}}', id="two sensors"),
        pytest.param('{"min_pwm": {"left": 70}}', id="no right"),
    ],
)
def test_load_rejects(tmp_path: Path, text: str) -> None:
    path = tmp_path / "profile.json"
    path.write_text(text)
    with pytest.raises(ProfileError):
        load_profile(path)
