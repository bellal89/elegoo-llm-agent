import json
from pathlib import Path
from typing import Any

from elegoo.episode import EpisodeHeader, EpisodeRecorder, EpisodeResult, StepOutcome, StepRecord, Verdict
from elegoo.profile import Profile
from elegoo.protocol import MotionKind, StopReason, Tele
from tests.conftest import JPEG

TELE = Tele(
    ms=0,
    sonar_cm=106,
    line=(1017, 50, 46),
    yaw_deg=0.0,
    batt_mv=7800,
    motion=MotionKind.IDLE,
    stop_reason=StopReason.NONE,
)
HEADER = EpisodeHeader(
    instruction="drive to the red box",
    model_id="claude-haiku-5-5",
    started_at="2026-11-12T10:00:00Z",
    profile=Profile(batt_mv=7658),
    batt_mv=7800,
)
STEP = StepRecord(
    index=0,
    frame="frames/000.jpg",
    tele_before=TELE,
    request={"model": "claude-haiku-5-5"},
    response={"stop_reason": "tool_use"},
    tool="move",
    tool_input={"cm": 30},
    outcome=StepOutcome.ACTION,
    error=None,
    latency_ms=1700,
    input_tokens=1400,
    output_tokens=200,
    stop_reason=StopReason.DONE,
    tele_after=TELE,
)


def read_episode(recorder: EpisodeRecorder) -> dict[str, Any]:
    return json.loads((recorder.dir / "episode.json").read_text())


def test_recorder_writes_episode(tmp_path: Path) -> None:
    recorder = EpisodeRecorder(HEADER, root=tmp_path)
    recorder.add_step(STEP, frame=JPEG)
    recorder.close(EpisodeResult.FINISH)
    recorder.set_verdict(Verdict(success=True, contact=False, intervention=False))
    episode = read_episode(recorder)
    assert episode["result"] == "finish"
    assert episode["verdict"] == {"success": True, "contact": False, "intervention": False}
    assert episode["instruction"] == HEADER.instruction
    assert episode["profile"] == {"batt_mv": 7658, "min_pwm": None, "speed": None, "brake": None, "line": None}
    assert [tool["name"] for tool in episode["tools"]] == ["turn", "move", "finish"]
    [line] = (recorder.dir / "steps.jsonl").read_text().splitlines()
    step = json.loads(line)
    assert step["frame"] == "frames/000.jpg"
    assert step["tele_before"]["sonar_cm"] == TELE.sonar_cm
    assert step["outcome"] == "action"
    assert (recorder.dir / "frames/000.jpg").read_bytes() == JPEG


def test_steps_survive_without_close(tmp_path: Path) -> None:
    recorder = EpisodeRecorder(HEADER, root=tmp_path)
    recorder.add_step(STEP, frame=JPEG)
    assert len((recorder.dir / "steps.jsonl").read_text().splitlines()) == 1
    assert "result" not in read_episode(recorder)


def test_frame_name_has_three_digits(tmp_path: Path) -> None:
    assert EpisodeRecorder(HEADER, root=tmp_path).frame_name(7) == "frames/007.jpg"
