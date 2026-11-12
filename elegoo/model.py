import base64
import dataclasses
import logging
import time
from typing import Any

import anthropic

from elegoo.calibrate import NO_ECHO_CM
from elegoo.car import MS_PER_S
from elegoo.errors import ModelTimeoutError
from elegoo.protocol import Tele
from elegoo.tools import TOOLS, ToolCall

# One test decision took 11.7 s.
DECISION_TIMEOUT_S = 20.0
MAX_TOKENS = 4000
# Set the effort explicitly: the default differs between models.
EFFORT = "medium"
SUCCESS_SONAR_CM = 30
FRAME_MEDIA_TYPE = "image/jpeg"
TOOL_USE_BLOCK = "tool_use"
REFUSAL_STOP_REASON = "refusal"
SYSTEM_PROMPT = """\
You drive a small robot car, approx. 25 cm long, on the floor. The camera faces forward.
Each request gives one camera frame, the sonar distance, and the earlier actions with their stop reasons.
Call exactly one tool.
turn: turn in place, positive deg turns right. move: drive straight forward. The car cannot drive backward.
The car stops by itself {sonar_stop_cm} cm before an obstacle ahead. Stop reason "sonar" means this stop.
The sonar beam is approx. 30 deg wide: the sonar gives the distance to the nearest object ahead, not its direction.
Call finish with reached=true only when both are true: the target center is in the middle third of the frame width,\
 and the sonar distance is at most {success_sonar_cm} cm.
Call finish with reached=false when you decide that the task cannot be done."""
USER_TEXT = """\
Task: {instruction}
Sonar: {sonar}
Earlier actions:
{history}"""
NO_ECHO_TEXT = "no echo"
NO_HISTORY_TEXT = "none"

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Request:
    instruction: str
    frame: bytes
    tele: Tele
    history: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Decision:
    """`call` is None if the response has no tool call, more than one, or a refusal."""

    call: ToolCall | None
    stop_reason: str | None
    request: dict[str, Any]
    response: dict[str, Any]
    latency_ms: int
    input_tokens: int
    output_tokens: int


class Model:
    def __init__(self, client: anthropic.Anthropic, *, model_id: str, sonar_stop_cm: int) -> None:
        self._client = client.with_options(timeout=DECISION_TIMEOUT_S, max_retries=0)
        self._model_id = model_id
        self._system = SYSTEM_PROMPT.format(sonar_stop_cm=sonar_stop_cm, success_sonar_cm=SUCCESS_SONAR_CM)

    def decide(self, request: Request, *, frame_name: str) -> Decision:
        """Raises ModelTimeoutError after DECISION_TIMEOUT_S. `frame_name` replaces the image in the recorded request."""
        image = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": FRAME_MEDIA_TYPE,
                "data": base64.standard_b64encode(request.frame).decode(),
            },
        }
        params = self._params(request, image=image)
        start_s = time.monotonic()
        try:
            message = self._client.messages.create(**params)
        except anthropic.APITimeoutError as error:
            raise ModelTimeoutError(f"no model response in {DECISION_TIMEOUT_S} s") from error
        latency_ms = round((time.monotonic() - start_s) * MS_PER_S)
        calls = [block for block in message.content if block.type == TOOL_USE_BLOCK]
        decision = Decision(
            call=ToolCall(name=calls[0].name, input=calls[0].input)
            if len(calls) == 1 and message.stop_reason != REFUSAL_STOP_REASON
            else None,
            stop_reason=message.stop_reason,
            request=self._params(request, image={"type": "image", "frame": frame_name}),
            response=message.to_dict(),
            latency_ms=latency_ms,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
        logger.debug("Receive %s", decision.response)
        logger.info(
            "Decision %s in %s ms, %s/%s tokens",
            decision.call,
            latency_ms,
            decision.input_tokens,
            decision.output_tokens,
        )
        return decision

    def _params(self, request: Request, *, image: dict[str, Any]) -> dict[str, Any]:
        sonar = NO_ECHO_TEXT if request.tele.sonar_cm == NO_ECHO_CM else f"{request.tele.sonar_cm} cm"
        user_text = USER_TEXT.format(
            instruction=request.instruction,
            sonar=sonar,
            history="\n".join(request.history) or NO_HISTORY_TEXT,
        )
        return {
            "model": self._model_id,
            "max_tokens": MAX_TOKENS,
            "system": self._system,
            "tools": TOOLS,
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "output_config": {"effort": EFFORT},
            "messages": [{"role": "user", "content": [image, {"type": "text", "text": user_text}]}],
        }
