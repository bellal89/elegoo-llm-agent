import dataclasses
import http
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from elegoo.episode import EpisodeHeader, EpisodeRecorder, EpisodeResult, StepOutcome, StepRecord, Verdict
from elegoo.model import Decision
from elegoo.profile import Profile
from elegoo.protocol import MotionKind, StopReason, Tele
from elegoo.tools import ToolCall
from elegoo.view import make_server
from tests.conftest import JPEG, text, tool_use

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
MODEL_TEXT = "The box is <left> of center."
STEP = StepRecord(
    index=0,
    frame="frames/000.jpg",
    tele_before=TELE,
    outcome=StepOutcome.ACTION,
    decision=Decision(
        call=ToolCall(name="turn", input={"deg": -20}),
        stop_reason="tool_use",
        request={"system": "You drive a small robot car."},
        response={"content": [text(MODEL_TEXT), tool_use("turn", {"deg": -20})]},
        latency_ms=1700,
        input_tokens=1400,
        output_tokens=200,
    ),
    stop_reason=StopReason.DONE,
    tele_after=TELE,
)


@pytest.fixture
def recorder(tmp_path: Path) -> EpisodeRecorder:
    return EpisodeRecorder(HEADER, root=tmp_path)


@pytest.fixture
def url(tmp_path: Path) -> Iterator[str]:
    with make_server(tmp_path, port=0) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_port}/"
        server.shutdown()


def get(url: str) -> str:
    with urllib.request.urlopen(url) as response:
        return response.read().decode()


def post(url: str, body: bytes) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST")) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def post_note(url: str, *, key: str, text: str) -> int:
    return post(url, json.dumps({"key": key, "text": text}).encode())


def test_view_shows_the_episode_steps(recorder: EpisodeRecorder, url: str) -> None:
    recorder.add_step(STEP, frame=JPEG)
    recorder.close(EpisodeResult.FINISH)
    recorder.set_verdict(Verdict(success=False, contact=True, intervention=False))
    name = recorder.dir.name

    index = get(url)
    page = get(f"{url}{name}/")

    assert f'href="{name}/"' in index
    assert "failure</span> contact" in index
    assert "The box is &lt;left&gt; of center." in page
    assert "{&quot;name&quot;: &quot;turn&quot;, &quot;input&quot;: {&quot;deg&quot;: -20}}" in page
    assert "You drive a small robot car." in page
    assert '<img src="frames/000.jpg">' in page
    assert urllib.request.urlopen(f"{url}{name}/frames/000.jpg").read() == JPEG


def test_view_shows_a_step_without_decision(recorder: EpisodeRecorder, url: str) -> None:
    timeout_step = dataclasses.replace(
        STEP, outcome=StepOutcome.MODEL_TIMEOUT, decision=None, error="no model response in 20.0 s", stop_reason=None
    )
    recorder.add_step(timeout_step, frame=JPEG)

    index = get(url)
    page = get(f"{url}{recorder.dir.name}/")

    assert "not closed" in index
    assert "no verdict" in index
    assert "outcome model_timeout" in page
    assert "no model response in 20.0 s" in page
    assert "stop None" not in page


def test_view_shows_an_episode_without_steps(recorder: EpisodeRecorder, url: str) -> None:
    assert "<td>0</td>" in get(url)
    assert recorder.dir.name in get(f"{url}{recorder.dir.name}/")


def test_view_numbers_the_episodes_in_time_order(tmp_path: Path, url: str) -> None:
    EpisodeRecorder(HEADER, root=tmp_path).dir.rename(tmp_path / "20261115T000000Z")
    later = EpisodeRecorder(HEADER, root=tmp_path)

    index = get(url)

    assert '<tr><td>1</td><td><a href="20261115T000000Z/">' in index
    assert f'<tr><td>2</td><td><a href="{later.dir.name}/">' in index


def test_view_saves_the_notes_and_shows_them(recorder: EpisodeRecorder, url: str) -> None:
    recorder.add_step(STEP, frame=JPEG)
    notes_url = f"{url}{recorder.dir.name}/"

    assert post_note(notes_url, key="episode", text="Lost the <box>.") == http.HTTPStatus.NO_CONTENT
    assert post_note(notes_url, key="0", text="Turned the wrong way.") == http.HTTPStatus.NO_CONTENT
    assert post_note(notes_url, key="0", text="Turned left, box on the right.") == http.HTTPStatus.NO_CONTENT
    assert post_note(notes_url, key="1", text="Typo.") == http.HTTPStatus.NO_CONTENT
    assert post_note(notes_url, key="1", text=" \n") == http.HTTPStatus.NO_CONTENT

    assert json.loads((recorder.dir / "notes.json").read_text()) == {
        "episode": "Lost the <box>.",
        "0": "Turned left, box on the right.",
    }
    assert "<td>Lost the &lt;box&gt;.</td>" in get(url)
    page = get(f"{url}{recorder.dir.name}/")
    assert 'data-key="episode" placeholder="Note">Lost the &lt;box&gt;.</textarea>' in page
    assert 'data-key="0" placeholder="Note">Turned left, box on the right.</textarea>' in page


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"not json", id="not-json"),
        pytest.param(b"\xff", id="not-utf8"),
        pytest.param(b"[]", id="not-object"),
        pytest.param(json.dumps({"key": "verdict", "text": "x"}).encode(), id="unknown-key"),
        pytest.param(json.dumps({"key": 0, "text": "x"}).encode(), id="key-not-string"),
        pytest.param(json.dumps({"key": "0", "text": None}).encode(), id="text-not-string"),
    ],
)
def test_view_rejects_a_bad_note(recorder: EpisodeRecorder, url: str, body: bytes) -> None:
    assert post(f"{url}{recorder.dir.name}/", body) == http.HTTPStatus.BAD_REQUEST
    assert not (recorder.dir / "notes.json").exists()


def test_view_rejects_a_note_for_an_unknown_episode(recorder: EpisodeRecorder, url: str) -> None:
    assert post_note(f"{url}..%2F..%2Fetc/", key="episode", text="x") == http.HTTPStatus.NOT_FOUND
