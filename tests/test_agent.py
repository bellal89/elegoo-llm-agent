import json
import time
import urllib.error
from pathlib import Path
from typing import Any

import httpx2
import pytest

from elegoo import agent
from elegoo.agent import check_ready, run_episode
from elegoo.car import HB_MS_SERIAL, Car
from elegoo.episode import EpisodeHeader, EpisodeRecorder, EpisodeResult
from elegoo.errors import NotReadyError, ReplyTimeoutError
from elegoo.model import Model
from elegoo.profile import Profile
from elegoo.protocol import MotionKind, StopReason
from tests.conftest import JPEG, MODEL_ID, FakeLink, fake_camera, model_with, reply, scripted_model, text, tool_use

BATT_MV = 7800
MOVE_PWM = 100
PROFILE = Profile(batt_mv=BATT_MV, speed=((100, 50.0),))
INSTRUCTION = "drive to the red box"
TELE = f"{{t,0,106,1017,50,46,0,{BATT_MV},{MotionKind.IDLE},none}}"
GET = ["{p,move_pwm,100}", "{p,sonar_stop_cm,17}", "{p,pwm_limit,150}", "{p,imu,1}", "{ok,get}"]
TELE_FRAMES = 1000


def turn(deg: int) -> httpx2.Response:
    return reply([tool_use("turn", {"deg": deg})])


def move(cm: int) -> httpx2.Response:
    return reply([tool_use("move", {"cm": cm})])


FINISH = reply([tool_use("finish", {"reached": True, "reason": "box ahead"})])


@pytest.fixture
def agent_link(link: FakeLink) -> FakeLink:
    link.script["{get}"] = GET
    link.script["{tele,100}"] = ["{ok,tele}"]
    link.streams["{tele,100}"] = [TELE] * TELE_FRAMES
    for deg in (10, 20):
        link.script[f"{{turn,{deg}}}"] = ["{ok,turn}", f"{{done,turn,{StopReason.DONE}}}"]
    link.script["{move,600}"] = ["{ok,move}", f"{{done,move,{StopReason.SONAR}}}"]
    return link


@pytest.fixture
def recorder(tmp_path: Path) -> EpisodeRecorder:
    header = EpisodeHeader(
        instruction=INSTRUCTION,
        model_id=MODEL_ID,
        started_at="2026-11-12T10:00:00Z",
        profile=PROFILE,
        batt_mv=BATT_MV,
    )
    return EpisodeRecorder(header, root=tmp_path)


@pytest.fixture
def tele_car(agent_link: FakeLink, car: Car) -> Car:
    car.tele(100)
    return car


def run(car: Car, model: Model, recorder: EpisodeRecorder) -> EpisodeResult:
    return run_episode(car, model=model, recorder=recorder, profile=PROFILE, move_pwm=MOVE_PWM, instruction=INSTRUCTION)


def read_steps(recorder: EpisodeRecorder) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (recorder.dir / "steps.jsonl").read_text().splitlines()]


def read_result(recorder: EpisodeRecorder) -> str:
    return json.loads((recorder.dir / "episode.json").read_text())["result"]


def motion_frames(link: FakeLink) -> list[str]:
    return [frame for frame in link.sent if frame.startswith(("{turn,", "{move,"))]


def test_episode_reaches_finish(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG] * 3)
    model = scripted_model([turn(20), move(30), FINISH], [])
    assert run(tele_car, model, recorder) is EpisodeResult.FINISH
    steps = read_steps(recorder)
    assert [step["outcome"] for step in steps] == ["action", "action", "finish"]
    assert [step["stop_reason"] for step in steps] == ["done", "sonar", None]
    assert steps[1]["tele_after"]["batt_mv"] == BATT_MV
    assert motion_frames(agent_link) == ["{turn,20}", "{move,600}"]
    assert read_result(recorder) == "finish"
    assert (recorder.dir / "frames/002.jpg").read_bytes() == JPEG


def test_history_carries_stop_reason(tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_camera(monkeypatch, [JPEG] * 2)
    sent: list[dict[str, Any]] = []
    run(tele_car, scripted_model([move(30), FINISH], sent), recorder)
    assert "1. move cm=30: sonar" in json.dumps(sent[1])


def test_budget_ends_episode(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG] * agent.MAX_DECISIONS)
    model = scripted_model([turn(10)] * agent.MAX_DECISIONS, [])
    assert run(tele_car, model, recorder) is EpisodeResult.BUDGET
    assert len(read_steps(recorder)) == agent.MAX_DECISIONS


def test_bad_decisions_count_toward_budget(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG] * agent.MAX_DECISIONS)
    sent: list[dict[str, Any]] = []
    model = scripted_model([move(80), reply([text("A box.")], "end_turn")] * (agent.MAX_DECISIONS // 2), sent)
    assert run(tele_car, model, recorder) is EpisodeResult.BUDGET
    assert {step["outcome"] for step in read_steps(recorder)} == {"bad_tool", "no_tool"}
    assert motion_frames(agent_link) == []
    assert "cm must be 5..50, got 80" in json.dumps(sent[1])


def test_model_timeout_is_a_step(tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_camera(monkeypatch, [JPEG] * 2)
    model = scripted_model([httpx2.ReadTimeout("slow"), FINISH], [])
    assert run(tele_car, model, recorder) is EpisodeResult.FINISH
    assert [step["outcome"] for step in read_steps(recorder)] == ["model_timeout", "finish"]


def test_timeout_after_decision_skips_action(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG])
    monkeypatch.setattr(agent, "EPISODE_TIMEOUT_S", 0.05)

    def slow(_: httpx2.Request) -> httpx2.Response:
        time.sleep(0.1)
        return turn(20)

    assert run(tele_car, model_with(slow), recorder) is EpisodeResult.TIMEOUT
    [step] = read_steps(recorder)
    assert step["error"] == "episode timeout"
    assert motion_frames(agent_link) == []


def test_ctrl_c_stops_car_and_closes_episode(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG, KeyboardInterrupt()])
    assert run(tele_car, scripted_model([turn(20)], []), recorder) is EpisodeResult.OPERATOR
    assert "{stop}" in agent_link.sent
    assert len(read_steps(recorder)) == 1
    assert read_result(recorder) == "operator"


def test_camera_error_ends_episode(tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_camera(monkeypatch, [urllib.error.URLError("No route to host")])
    assert run(tele_car, scripted_model([], []), recorder) is EpisodeResult.ERROR
    assert read_result(recorder) == "error"


def test_ctrl_c_during_move_records_the_step(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG])

    def interrupt(_: float) -> StopReason:
        raise KeyboardInterrupt

    monkeypatch.setattr(tele_car, "wait_done", interrupt)
    assert run(tele_car, scripted_model([move(30)], []), recorder) is EpisodeResult.OPERATOR
    [step] = read_steps(recorder)
    assert (step["decision"]["call"]["name"], step["error"]) == ("move", "KeyboardInterrupt")
    assert "{stop}" in agent_link.sent


def test_ctrl_c_with_failed_stop_closes_episode(
    agent_link: FakeLink, tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [KeyboardInterrupt()])
    stop_replies = agent_link.script.pop("{stop}")
    with pytest.raises(ReplyTimeoutError):
        run(tele_car, scripted_model([], []), recorder)
    agent_link.script["{stop}"] = stop_replies
    assert read_result(recorder) == "operator"


def test_api_error_records_the_step(tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_camera(monkeypatch, [JPEG])
    bad_request = httpx2.Response(
        400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}
    )
    assert run(tele_car, scripted_model([bad_request], []), recorder) is EpisodeResult.ERROR
    [step] = read_steps(recorder)
    assert "BadRequestError" in step["error"]


def test_unexpected_error_closes_episode(
    tele_car: Car, recorder: EpisodeRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_camera(monkeypatch, [JPEG])
    with pytest.raises(AttributeError):
        run(tele_car, scripted_model([httpx2.Response(200, text="captive portal")], []), recorder)
    assert read_result(recorder) == "error"


@pytest.mark.parametrize(
    ("imu", "profile"),
    [
        pytest.param("0", PROFILE, id="imu failure"),
        pytest.param("1", Profile(), id="no speed calibration"),
        pytest.param("1", Profile(batt_mv=BATT_MV, speed=((125, 44.6),)), id="move_pwm outside the speed table"),
    ],
)
def test_check_ready_rejects(link: FakeLink, imu: str, profile: Profile) -> None:
    link.script["{get}"] = ["{p,move_pwm,100}", f"{{p,imu,{imu}}}", "{ok,get}"]
    with Car(link, HB_MS_SERIAL) as car, pytest.raises(NotReadyError):
        check_ready(car, profile)
