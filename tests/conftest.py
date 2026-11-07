import queue
import threading
from collections.abc import Iterator

import pytest

from elegoo.car import HB_MS_SERIAL, Car
from elegoo.errors import LinkError

DEFAULT_SCRIPT = {
    "{set,hb_ms,300}": ["{ok,set}"],
    "{get}": ["{p,max_pwm,100}", "{p,kp,4.00}", "{p,imu,1}", "{ok,get}"],
    "{stop}": ["{ok,stop}"],
}


class FakeLink:
    """Answers each sent frame with the frames from `script`."""

    def __init__(self) -> None:
        self.script: dict[str, list[str]] = dict(DEFAULT_SCRIPT)
        self.closed = False
        self.broken = False
        self._sent: list[str] = []
        self._lock = threading.Lock()
        self._incoming: queue.Queue[str] = queue.Queue()

    @property
    def resets_car(self) -> bool:
        return False

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

    def recv(self, timeout_s: float) -> str | None:
        if self.broken:
            raise LinkError("fake link broken")
        try:
            return self._incoming.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def link() -> FakeLink:
    return FakeLink()


@pytest.fixture
def car(link: FakeLink) -> Iterator[Car]:
    with Car(link, HB_MS_SERIAL) as car:
        yield car
