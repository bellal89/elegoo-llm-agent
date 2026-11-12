import logging
import urllib.request

from elegoo.errors import CameraError
from elegoo.link import TCP_HOST

CAPTURE_URL = f"http://{TCP_HOST}/capture"
CAPTURE_TIMEOUT_S = 3.0

logger = logging.getLogger(__name__)


def capture() -> bytes:
    try:
        with urllib.request.urlopen(CAPTURE_URL, timeout=CAPTURE_TIMEOUT_S) as response:
            frame = response.read()
    except OSError as error:
        raise CameraError(f"cannot get a frame from {CAPTURE_URL}: {error}") from error
    if not frame:
        raise CameraError(f"empty frame from {CAPTURE_URL}")
    logger.debug("Frame %s bytes", len(frame))
    return frame
