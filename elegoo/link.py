import logging
import socket
import threading
import time
import typing

import serial

from elegoo.errors import LinkError
from elegoo.protocol import FRAME_END, FRAME_START

BAUD = 9600
READ_TIMEOUT_S = 0.05
# Longest UNO frame: kTxFrameCapacity in firmware/car/tx_frame.h.
RX_FRAME_MAX_LEN = 63
ENCODING = "ascii"

TCP_HOST = "192.168.4.1"
TCP_PORT = 100
TCP_CONNECT_TIMEOUT_S = 3.0
# The ESP32 bridge drops the client after 3 missed heartbeats, 1 s apart.
BRIDGE_HEARTBEAT = "{Heartbeat}"
BRIDGE_HEARTBEAT_S = 1.0

logger = logging.getLogger(__name__)


class Link(typing.Protocol):
    @property
    def resets_car(self) -> bool:
        """True if the UNO reboots when the link opens."""
        ...

    def send(self, frame: str) -> None: ...

    def recv(self, timeout_s: float) -> str | None: ...

    def close(self) -> None: ...


class _FrameBuffer:
    def __init__(self) -> None:
        self._text = ""

    def feed(self, data: bytes) -> None:
        self._text += data.decode(ENCODING, errors="replace")

    def pop(self) -> str | None:
        """Returns the next {...} frame. Drops the text outside braces and the frames longer than the limit."""
        while (end := self._text.find(FRAME_END)) >= 0:
            start = self._text.rfind(FRAME_START, 0, end)
            frame = self._text[start : end + 1]
            self._text = self._text[end + 1 :]
            if start >= 0 and len(frame) <= RX_FRAME_MAX_LEN:
                return frame
        start = self._text.rfind(FRAME_START)
        too_long = start < 0 or len(self._text) - start > RX_FRAME_MAX_LEN
        self._text = "" if too_long else self._text[start:]
        return None


class SerialLink:
    def __init__(self, port: str) -> None:
        try:
            self._serial = serial.Serial(port, BAUD, timeout=READ_TIMEOUT_S)
        except OSError as error:
            raise LinkError(f"cannot open {port}: {error}") from error
        self._lock = threading.Lock()
        self._frames = _FrameBuffer()

    @property
    def resets_car(self) -> bool:
        # Opening the port toggles DTR, and DTR resets the UNO.
        return True

    def send(self, frame: str) -> None:
        with self._lock:
            try:
                self._serial.write(frame.encode(ENCODING))
            except OSError as error:
                raise LinkError(f"serial write failed: {error}") from error

    def recv(self, timeout_s: float) -> str | None:
        deadline_s = time.monotonic() + timeout_s
        while (frame := self._frames.pop()) is None:
            if time.monotonic() >= deadline_s:
                return None
            try:
                self._frames.feed(self._serial.read(max(1, self._serial.in_waiting)))
            except OSError as error:
                raise LinkError(f"serial read failed: {error}") from error
        return frame

    def close(self) -> None:
        self._serial.close()


class TcpLink:
    def __init__(self, host: str = TCP_HOST, port: int = TCP_PORT) -> None:
        try:
            self._socket = socket.create_connection((host, port), timeout=TCP_CONNECT_TIMEOUT_S)
        except OSError as error:
            raise LinkError(f"cannot connect to {host}:{port}: {error}") from error
        self._socket.settimeout(READ_TIMEOUT_S)
        self._lock = threading.Lock()
        self._frames = _FrameBuffer()
        self._closed = threading.Event()
        self._heartbeat = threading.Thread(target=self._send_heartbeats, daemon=True)
        self._heartbeat.start()

    @property
    def resets_car(self) -> bool:
        return False

    def send(self, frame: str) -> None:
        with self._lock:
            try:
                self._socket.sendall(frame.encode(ENCODING))
            except OSError as error:
                raise LinkError(f"socket write failed: {error}") from error

    def recv(self, timeout_s: float) -> str | None:
        deadline_s = time.monotonic() + timeout_s
        while (frame := self._frames.pop()) is None or frame == BRIDGE_HEARTBEAT:
            if time.monotonic() >= deadline_s:
                return None
            self._frames.feed(self._read())
        return frame

    def close(self) -> None:
        self._closed.set()
        self._heartbeat.join()
        self._socket.close()

    def _read(self) -> bytes:
        try:
            data = self._socket.recv(RX_FRAME_MAX_LEN)
        except TimeoutError:
            return b""
        except OSError as error:
            raise LinkError(f"socket read failed: {error}") from error
        if not data:
            raise LinkError("bridge closed the connection")
        return data

    def _send_heartbeats(self) -> None:
        try:
            while True:
                self.send(BRIDGE_HEARTBEAT)
                if self._closed.wait(BRIDGE_HEARTBEAT_S):
                    return
        except LinkError:
            logger.exception("Bridge heartbeat failed")
