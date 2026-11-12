import json
from typing import Any

import httpx2
import pytest

from elegoo.errors import ModelTimeoutError
from elegoo.model import Request
from elegoo.protocol import MotionKind, StopReason, Tele
from tests.conftest import INPUT_TOKENS, JPEG, OUTPUT_TOKENS, reply, scripted_model, text, tool_use

FRAME_NAME = "frames/000.jpg"


def tele(sonar_cm: int) -> Tele:
    return Tele(
        ms=0,
        sonar_cm=sonar_cm,
        line=(1017, 50, 46),
        yaw_deg=0.0,
        batt_mv=7800,
        motion=MotionKind.IDLE,
        stop_reason=StopReason.NONE,
    )


def request(*, sonar_cm: int = 106, history: tuple[str, ...] = ()) -> Request:
    return Request(instruction="drive to the red box", frame=JPEG, tele=tele(sonar_cm), history=history)


def user_text(body: dict[str, Any]) -> str:
    [message] = body["messages"]
    return next(block["text"] for block in message["content"] if block["type"] == "text")


def test_decide_returns_tool_call() -> None:
    sent: list[dict[str, Any]] = []
    model = scripted_model([reply([text("Box to the right."), tool_use("turn", {"deg": 20})])], sent)
    decision = model.decide(request(), frame_name=FRAME_NAME)
    assert decision.call is not None
    assert (decision.call.name, decision.call.input) == ("turn", {"deg": 20})
    assert (decision.input_tokens, decision.output_tokens) == (INPUT_TOKENS, OUTPUT_TOKENS)
    assert sent[0]["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert [tool["name"] for tool in sent[0]["tools"]] == ["turn", "move", "finish"]
    recorded = json.dumps(decision.request)
    assert FRAME_NAME in recorded and "base64" not in recorded


@pytest.mark.parametrize(
    ("content", "stop_reason"),
    [
        pytest.param([text("I see a box.")], "end_turn", id="text only"),
        pytest.param([tool_use("turn", {"deg": 20}), tool_use("move", {"cm": 10})], "tool_use", id="two calls"),
        pytest.param([tool_use("turn", {"deg": 20})], "refusal", id="refusal"),
    ],
)
def test_decide_without_tool_call(content: list[dict[str, Any]], stop_reason: str) -> None:
    decision = scripted_model([reply(content, stop_reason)], []).decide(request(), frame_name=FRAME_NAME)
    assert decision.call is None
    assert decision.stop_reason == stop_reason


def test_decide_timeout() -> None:
    model = scripted_model([httpx2.ReadTimeout("slow")], [])
    with pytest.raises(ModelTimeoutError):
        model.decide(request(), frame_name=FRAME_NAME)


@pytest.mark.parametrize(
    ("sonar_cm", "shown", "hidden"),
    [
        pytest.param(0, "no echo", "0 cm", id="no echo"),
        pytest.param(25, "25 cm", "no echo", id="echo"),
    ],
)
def test_request_text_shows_sonar(sonar_cm: int, shown: str, hidden: str) -> None:
    sent: list[dict[str, Any]] = []
    scripted_model([reply([tool_use("move", {"cm": 10})])], sent).decide(
        request(sonar_cm=sonar_cm), frame_name=FRAME_NAME
    )
    assert shown in user_text(sent[0])
    assert hidden not in user_text(sent[0])


@pytest.mark.parametrize(
    ("history", "shown"),
    [
        pytest.param(("1. turn deg=20: done",), "1. turn deg=20: done", id="history"),
        pytest.param((), "none", id="no history"),
    ],
)
def test_request_text_has_history(history: tuple[str, ...], shown: str) -> None:
    sent: list[dict[str, Any]] = []
    scripted_model([reply([tool_use("move", {"cm": 10})])], sent).decide(
        request(history=history), frame_name=FRAME_NAME
    )
    assert shown in user_text(sent[0])
