import socket
from collections.abc import Iterator

import pytest

from elegoo.errors import LinkError
from elegoo.link import BRIDGE_HEARTBEAT, TcpLink

LOCALHOST = "127.0.0.1"
ANY_PORT = 0
RECV_TIMEOUT_S = 0.3
RECV_SIZE = 64


@pytest.fixture
def server() -> Iterator[socket.socket]:
    with socket.create_server((LOCALHOST, ANY_PORT)) as server:
        yield server


@pytest.fixture
def link(server: socket.socket) -> Iterator[TcpLink]:
    link = TcpLink(LOCALHOST, server.getsockname()[1])
    yield link
    link.close()


@pytest.fixture
def bridge(server: socket.socket, link: TcpLink) -> Iterator[socket.socket]:
    connection, _ = server.accept()
    with connection:
        yield connection


@pytest.mark.parametrize(
    ("chunks", "frames"),
    [
        pytest.param([b"{ok,stop}\n{ok,get}\n"], ["{ok,stop}", "{ok,get}"], id="two frames"),
        pytest.param([b"{done,tu", b"rn,done}\n"], ["{done,turn,done}"], id="split frame"),
        pytest.param([b"noise}x{ok,set}"], ["{ok,set}"], id="noise outside braces"),
        pytest.param([b"{ok,tu{ok,stop}"], ["{ok,stop}"], id="truncated frame"),
        pytest.param([b"{" + b"x" * 70, b"}{ok,set}"], ["{ok,set}"], id="oversized frame"),
        pytest.param([BRIDGE_HEARTBEAT.encode() + b"{ok,set}"], ["{ok,set}"], id="bridge heartbeat"),
    ],
)
def test_recv_splits_frames(link: TcpLink, bridge: socket.socket, chunks: list[bytes], frames: list[str]) -> None:
    for chunk in chunks:
        bridge.sendall(chunk)
    assert [link.recv(RECV_TIMEOUT_S) for _ in frames] == frames
    assert link.recv(RECV_TIMEOUT_S) is None


def test_send_and_bridge_heartbeat(link: TcpLink, bridge: socket.socket) -> None:
    link.send("{stop}")
    received = b""
    while b"{stop}" not in received:
        received += bridge.recv(RECV_SIZE)
    assert BRIDGE_HEARTBEAT.encode() in received


def test_closed_connection_raises(link: TcpLink, bridge: socket.socket) -> None:
    # Unread data makes close() send RST instead of FIN.
    bridge.recv(RECV_SIZE)
    bridge.close()
    with pytest.raises(LinkError):
        link.recv(RECV_TIMEOUT_S)


def test_connect_failure_raises(server: socket.socket) -> None:
    port = server.getsockname()[1]
    server.close()
    with pytest.raises(LinkError):
        TcpLink(LOCALHOST, port)
