from collections.abc import Iterator

import pytest

from elegoo.accept import CliffTarget, ask_number, ask_yes, cliff_rep, move_rep, turn_rep, wall_pwms, wall_rep
from elegoo.car import Car
from elegoo.profile import MinPwm, Profile
from elegoo.protocol import MotionKind
from tests.conftest import FakeLink

BATT_MV = 7800
PROFILE = Profile(batt_mv=BATT_MV, speed=((100, 50.0),))
GET = ["{p,move_pwm,100}", "{p,max_pwm,150}", "{p,max_cmd_ms,5000}", "{p,pwm_limit,150}", "{p,imu,1}", "{ok,get}"]
GYRO = "{gyro}"


def answers(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    """Answers each input() call with the next line."""
    replies: Iterator[str] = iter(lines)
    monkeypatch.setattr("builtins.input", lambda _: next(replies))


@pytest.fixture
def accept_link(link: FakeLink) -> FakeLink:
    link.script["{get}"] = GET
    link.script[GYRO] = ["{ok,gyro}"]
    link.streams[GYRO] = [f"{{t,0,120,45,1017,46,0,{BATT_MV},{MotionKind.IDLE},none}}"] * 20
    for pwm in (100, 150):
        link.script[f"{{set,move_pwm,{pwm}}}"] = ["{ok,set}"]
    return link


def test_ask_number_reprompts_on_bad_input(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, "x", "", "88.5")
    assert ask_number("angle: ") == 88.5


def test_ask_yes_reprompts_on_bad_input(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, "maybe", "N")
    assert not ask_yes("contact? ")


def test_wall_pwms_start_above_min_pwm() -> None:
    assert wall_pwms(MinPwm(left=40, right=45), max_pwm=150) == (55, 102, 150)


@pytest.mark.parametrize(
    ("reason", "angle", "passed"),
    [
        pytest.param("done", "86", True, id="pass"),
        pytest.param("done", "84.5", False, id="angle error"),
        pytest.param("sonar", "90", False, id="sonar stop"),
    ],
)
def test_turn_rep(
    accept_link: FakeLink, car: Car, monkeypatch: pytest.MonkeyPatch, reason: str, angle: str, passed: bool
) -> None:
    accept_link.script["{turn,90}"] = ["{ok,turn}", f"{{done,turn,{reason}}}"]
    answers(monkeypatch, "", angle)
    assert turn_rep(car).passed is passed
    assert GYRO in accept_link.sent


@pytest.mark.parametrize(
    ("drift", "distance", "passed"),
    [
        pytest.param("-5", "91", True, id="pass"),
        pytest.param("5.5", "100", False, id="drift"),
        pytest.param("0", "111", False, id="distance error"),
    ],
)
def test_move_rep(
    accept_link: FakeLink, car: Car, monkeypatch: pytest.MonkeyPatch, drift: str, distance: str, passed: bool
) -> None:
    accept_link.script["{move,2000}"] = ["{ok,move}", "{done,move,done}"]
    answers(monkeypatch, "", drift, distance)
    assert move_rep(car, PROFILE).passed is passed


@pytest.mark.parametrize(
    ("reason", "contact", "passed"),
    [
        pytest.param("sonar", "n", True, id="pass"),
        pytest.param("sonar", "y", False, id="contact"),
        pytest.param("timeout", "n", False, id="no sonar stop"),
    ],
)
def test_wall_rep(
    accept_link: FakeLink, car: Car, monkeypatch: pytest.MonkeyPatch, reason: str, contact: str, passed: bool
) -> None:
    accept_link.script["{move,5000}"] = ["{ok,move}", f"{{done,move,{reason}}}"]
    answers(monkeypatch, "", contact)
    assert wall_rep(car, pwm=150).passed is passed
    assert [frame for frame in accept_link.sent if frame.startswith("{set,move_pwm")] == [
        "{set,move_pwm,150}",
        "{set,move_pwm,100}",
    ]


@pytest.mark.parametrize(
    ("reason", "on_surface", "passed"),
    [
        pytest.param("cliff", "y", True, id="pass"),
        pytest.param("cliff", "n", False, id="wheel over the edge"),
        pytest.param("sonar", "y", False, id="no cliff stop"),
    ],
)
def test_cliff_rep(
    accept_link: FakeLink, car: Car, monkeypatch: pytest.MonkeyPatch, reason: str, on_surface: str, passed: bool
) -> None:
    accept_link.script["{move,5000}"] = ["{ok,move}", f"{{done,move,{reason}}}"]
    answers(monkeypatch, "", on_surface)
    assert cliff_rep(car, target=CliffTarget.EDGE).passed is passed
    assert "{set,move_pwm,150}" in accept_link.sent
