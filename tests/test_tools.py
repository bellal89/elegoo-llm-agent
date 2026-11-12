from typing import Any

import pytest

from elegoo.errors import ToolCallError
from elegoo.tools import TOOLS, Action, Finish, Move, ToolCall, ToolName, Turn, parse_action


@pytest.mark.parametrize(
    ("name", "args", "action"),
    [
        pytest.param("turn", {"deg": -180}, Turn(deg=-180), id="turn min"),
        pytest.param("turn", {"deg": 180}, Turn(deg=180), id="turn max"),
        pytest.param("move", {"cm": 5}, Move(cm=5), id="move min"),
        pytest.param("move", {"cm": 50}, Move(cm=50), id="move max"),
        pytest.param(
            "finish", {"reached": True, "reason": "box ahead"}, Finish(reached=True, reason="box ahead"), id="finish"
        ),
    ],
)
def test_parse_action(name: str, args: dict[str, Any], action: Action) -> None:
    assert parse_action(ToolCall(name=name, input=args)) == action


@pytest.mark.parametrize(
    ("name", "args"),
    [
        pytest.param("turn", {"deg": 181}, id="turn above range"),
        pytest.param("turn", {"deg": -181}, id="turn below range"),
        pytest.param("move", {"cm": 4}, id="move below range"),
        pytest.param("move", {"cm": 51}, id="move above range"),
        pytest.param("move", {"cm": True}, id="bool is not int"),
        pytest.param("move", {"cm": 20.5}, id="float"),
        pytest.param("turn", {}, id="missing argument"),
        pytest.param("finish", {"reached": "yes", "reason": ""}, id="reached not bool"),
        pytest.param("reverse", {"cm": 10}, id="unknown tool"),
    ],
)
def test_parse_action_rejects(name: str, args: dict[str, Any]) -> None:
    with pytest.raises(ToolCallError):
        parse_action(ToolCall(name=name, input=args))


def test_tools_match_tool_names() -> None:
    assert [tool["name"] for tool in TOOLS] == list(ToolName)
    assert all(tool["strict"] and not tool["input_schema"]["additionalProperties"] for tool in TOOLS)
