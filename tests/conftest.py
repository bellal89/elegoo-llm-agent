import json
import queue
import threading
import time
import typing
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

import anthropic
import httpx2
import pytest

from elegoo.car import HB_MS_SERIAL, Car
from elegoo.errors import LinkError
from elegoo.model import Model

DEFAULT_SCRIPT = {
    "{set,hb_ms,300}": ["{ok,set}"],
    "{get}": ["{p,max_pwm,100}", "{p,kp,4.00}", "{p,pwm_limit,150}", "{p,imu,1}", "{ok,get}"],
    "{stop}": ["{ok,stop}"],
}
STREAM_PERIOD_S = 0.02
JPEG = b"\xff\xd8 frame \xff\xd9"
HTTP_OK = 200
MODEL_ID = "claude-haiku-5-5"
SONAR_STOP_CM = 17
INPUT_TOKENS = 1400
OUTPUT_TOKENS = 200


class FakeLink:
    """Answers each sent frame with the frames from `script`, then with the frames from `streams` one per period.

    A new stream replaces the old one: the car sends one telemetry stream.
    """

    def __init__(self) -> None:
        self.script: dict[str, list[str]] = dict(DEFAULT_SCRIPT)
        self.streams: dict[str, list[str]] = {}
        self._stream_id = 0
        self.closed = False
        self.broken = False
        self._sent: list[str] = []
        self._lock = threading.Lock()
        self._incoming: queue.Queue[str] = queue.Queue()

    resets_car = False

    @property
    def sent(self) -> list[str]:
        with self._lock:
            return list(self._sent)

    def push(self, frame: str) -> None:
        self._incoming.put(frame)

    def send(self, frame: str) -> None:
        with self._lock:
            self._sent.append(frame)
        for reply in self.script.get(frame, []):
            self.push(reply)
        if frame in self.streams:
            self._stream_id += 1
            threading.Thread(target=self._stream, args=[self._stream_id, self.streams[frame]], daemon=True).start()

    def recv(self, timeout_s: float) -> str | None:
        if self.broken:
            raise LinkError("fake link broken")
        try:
            return self._incoming.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True

    def _stream(self, stream_id: int, frames: list[str]) -> None:
        for frame in frames:
            time.sleep(STREAM_PERIOD_S)
            if stream_id != self._stream_id:
                return
            self.push(frame)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.status = HTTP_OK
        self._body = body

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def read(self) -> bytes:
        return self._body


def fake_camera(monkeypatch: pytest.MonkeyPatch, replies: list[bytes | BaseException]) -> None:
    """Answers each urlopen() call with the next reply: bytes are the body, an exception is raised."""
    queued = iter(replies)

    def urlopen(_url: str, *, timeout: float) -> FakeResponse:
        reply = next(queued)
        if isinstance(reply, BaseException):
            raise reply
        return FakeResponse(reply)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def tool_use(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{name}", "name": name, "input": tool_input}


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def reply(content: list[dict[str, Any]], stop_reason: str = "tool_use") -> httpx2.Response:
    return httpx2.Response(
        HTTP_OK,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": MODEL_ID,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": INPUT_TOKENS, "output_tokens": OUTPUT_TOKENS},
        },
    )


def model_with(handler: Callable[[httpx2.Request], httpx2.Response]) -> Model:
    client = anthropic.Anthropic(
        api_key="test", http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    )
    return Model(client, model_id=MODEL_ID, sonar_stop_cm=SONAR_STOP_CM)


def scripted_model(replies: list[httpx2.Response | Exception], sent: list[dict[str, Any]]) -> Model:
    """Answers each API call with the next reply and appends the request body to `sent`."""
    queued = iter(replies)

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        reply = next(queued)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return model_with(handler)


@pytest.fixture
def link() -> FakeLink:
    return FakeLink()


@pytest.fixture
def car(link: FakeLink) -> Iterator[Car]:
    with Car(link, HB_MS_SERIAL) as car:
        yield car
