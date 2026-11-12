import dataclasses
import enum
from typing import Any

from elegoo.errors import ToolCallError

TURN_DEG_MAX = 180
MOVE_CM_MIN = 5
MOVE_CM_MAX = 50


class ToolName(enum.StrEnum):
    TURN = "turn"
    MOVE = "move"
    FINISH = "finish"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Turn:
    deg: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Move:
    cm: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Finish:
    reached: bool
    reason: str


type Action = Turn | Move | Finish


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    name: str
    input: dict[str, Any]


# Strict tool schemas do not accept minimum and maximum: parse_action checks the ranges.
TOOLS: list[dict[str, Any]] = [
    {
        "name": ToolName.TURN,
        "description": f"Turn in place by deg, {-TURN_DEG_MAX}..{TURN_DEG_MAX}. Positive deg turns right.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"deg": {"type": "integer"}},
            "required": ["deg"],
            "additionalProperties": False,
        },
    },
    {
        "name": ToolName.MOVE,
        "description": f"Drive straight forward by cm, {MOVE_CM_MIN}..{MOVE_CM_MAX}.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"cm": {"type": "integer"}},
            "required": ["cm"],
            "additionalProperties": False,
        },
    },
    {
        "name": ToolName.FINISH,
        "description": "End the task. reached: true if the car is at the target.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"reached": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["reached", "reason"],
            "additionalProperties": False,
        },
    },
]


def parse_action(call: ToolCall) -> Action:
    """Raises ToolCallError with a message for the model."""
    try:
        tool = ToolName(call.name)
    except ValueError:
        raise ToolCallError(f"unknown tool {call.name}") from None
    match tool:
        case ToolName.TURN:
            deg = _arg(call, key="deg", kind=int)
            if abs(deg) > TURN_DEG_MAX:
                raise ToolCallError(f"deg must be {-TURN_DEG_MAX}..{TURN_DEG_MAX}, got {deg}")
            return Turn(deg=deg)
        case ToolName.MOVE:
            cm = _arg(call, key="cm", kind=int)
            if not MOVE_CM_MIN <= cm <= MOVE_CM_MAX:
                raise ToolCallError(f"cm must be {MOVE_CM_MIN}..{MOVE_CM_MAX}, got {cm}")
            return Move(cm=cm)
        case ToolName.FINISH:
            return Finish(reached=_arg(call, key="reached", kind=bool), reason=_arg(call, key="reason", kind=str))


def _arg[T](call: ToolCall, *, key: str, kind: type[T]) -> T:
    value = call.input.get(key)
    # Exact type: bool is a subclass of int.
    if type(value) is not kind:
        raise ToolCallError(f"{key} must be {kind.__name__}, got {value!r}")
    return value
