import dataclasses
import datetime
import enum
import json
from pathlib import Path
from typing import Any

from elegoo.profile import Profile
from elegoo.protocol import StopReason, Tele
from elegoo.tools import TOOLS

RUNS_DIR = Path("runs")
EPISODE_FILE = "episode.json"
STEPS_FILE = "steps.jsonl"
FRAMES_DIR = "frames"
DIR_TIME_FORMAT = "%Y%m%dT%H%M%SZ"


class EpisodeResult(enum.StrEnum):
    FINISH = "finish"
    BUDGET = "budget"
    TIMEOUT = "timeout"
    ERROR = "error"
    OPERATOR = "operator"


class StepOutcome(enum.StrEnum):
    ACTION = "action"
    FINISH = "finish"
    BAD_TOOL = "bad_tool"
    NO_TOOL = "no_tool"
    MODEL_TIMEOUT = "model_timeout"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeHeader:
    instruction: str
    model_id: str
    started_at: str
    profile: Profile
    batt_mv: int
    imu_ok: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class StepRecord:
    index: int
    frame: str
    tele_before: Tele
    request: dict[str, Any] | None
    response: dict[str, Any] | None
    tool: str | None
    tool_input: dict[str, Any] | None
    outcome: StepOutcome
    error: str | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    stop_reason: StopReason | None
    tele_after: Tele | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Verdict:
    success: bool
    contact: bool
    intervention: bool


class EpisodeRecorder:
    def __init__(self, header: EpisodeHeader, *, root: Path = RUNS_DIR) -> None:
        self._dir = root / datetime.datetime.now(datetime.UTC).strftime(DIR_TIME_FORMAT)
        (self._dir / FRAMES_DIR).mkdir(parents=True)
        self._episode: dict[str, Any] = dataclasses.asdict(header) | {"tools": TOOLS}
        self._write_episode()

    @property
    def dir(self) -> Path:
        return self._dir

    def frame_name(self, index: int) -> str:
        return f"{FRAMES_DIR}/{index:03d}.jpg"

    def add_step(self, step: StepRecord, *, frame: bytes) -> None:
        (self._dir / step.frame).write_bytes(frame)
        with (self._dir / STEPS_FILE).open("a") as steps:
            steps.write(json.dumps(dataclasses.asdict(step)) + "\n")

    def close(self, result: EpisodeResult) -> None:
        self._episode |= {"result": result, "ended_at": datetime.datetime.now(datetime.UTC).isoformat()}
        self._write_episode()

    def set_verdict(self, verdict: Verdict) -> None:
        self._episode["verdict"] = dataclasses.asdict(verdict)
        self._write_episode()

    def _write_episode(self) -> None:
        (self._dir / EPISODE_FILE).write_text(json.dumps(self._episode, indent=2) + "\n")
