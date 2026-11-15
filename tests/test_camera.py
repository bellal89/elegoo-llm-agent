import urllib.error

import pytest

from elegoo.camera import capture
from elegoo.errors import CameraError
from tests.conftest import JPEG, fake_camera


def test_capture_returns_jpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_camera(monkeypatch, [JPEG])
    assert capture() == JPEG


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param(urllib.error.URLError("No route to host"), id="no route"),
        pytest.param(TimeoutError(), id="timeout"),
        pytest.param(b"", id="empty body"),
    ],
)
def test_capture_failure_raises_camera_error(monkeypatch: pytest.MonkeyPatch, reply: bytes | Exception) -> None:
    fake_camera(monkeypatch, [reply])
    with pytest.raises(CameraError):
        capture()
