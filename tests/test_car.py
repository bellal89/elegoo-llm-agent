import time
from collections.abc import Callable

import pytest

from elegoo.car import HB_MS_SERIAL, Car
from elegoo.errors import CommandRejectedError, ReplyTimeoutError
from elegoo.protocol import ErrReason, MotionKind, Param, StopReason
from tests.conftest import FakeLink

WAIT_S = 1.0
POLL_S = 0.01
HB_FRAME = "{hb}"
STOP_FRAME = "{stop}"
TELE_FRAME = "{t,1234,30,45,1017,46,9000,7810,turn,none}"


def wait_until(condition: Callable[[], bool]) -> bool:
    deadline_s = time.monotonic() + WAIT_S
    while not condition():
        if time.monotonic() >= deadline_s:
            return False
        time.sleep(POLL_S)
    return True


def test_start_sets_hb_ms_and_reads_params(link: FakeLink, car: Car) -> None:
    assert link.sent[0] == "{set,hb_ms,300}"
    assert car.imu_ok is True
    assert car.params() == {Param.MAX_PWM: 100, Param.KP: 4.0}


def test_failed_start_closes_link(link: FakeLink) -> None:
    del link.script["{get}"]
    with pytest.raises(ReplyTimeoutError):
        Car(link, HB_MS_SERIAL)
    assert link.closed


def test_turn_sends_frame(link: FakeLink, car: Car) -> None:
    link.script["{turn,-90}"] = ["{ok,turn}"]
    car.turn(-90)
    assert "{turn,-90}" in link.sent


@pytest.mark.parametrize(
    ("replies", "reason"),
    [
        pytest.param(["{ok,turn}", "{done,turn,cliff}"], StopReason.CLIFF, id="cliff"),
        pytest.param(["{ok,turn}", "{done,drive,cmd}", "{done,turn,done}"], StopReason.DONE, id="stale other cmd"),
        pytest.param(["{done,turn,cmd}", "{ok,turn}", "{done,turn,done}"], StopReason.DONE, id="preempted same cmd"),
    ],
)
def test_wait_done(link: FakeLink, car: Car, replies: list[str], reason: StopReason) -> None:
    link.script["{turn,90}"] = replies
    car.turn(90)
    assert car.wait_done(WAIT_S) is reason


def test_wait_done_keeps_done_received_during_other_command(link: FakeLink, car: Car) -> None:
    link.script["{move,2000}"] = ["{ok,move}"]
    link.script["{tele,100}"] = ["{done,move,sonar}", "{ok,tele}"]
    car.move(2000)
    car.tele(100)
    assert car.wait_done(WAIT_S) is StopReason.SONAR


def test_drive_sends_fast_flag(link: FakeLink, car: Car) -> None:
    link.script["{drive,100,-100,500,f}"] = ["{ok,drive}", "{done,drive,done}"]
    car.drive(100, right=-100, duration_ms=500, fast=True)
    assert car.wait_done(WAIT_S) is StopReason.DONE


def test_wait_done_times_out(link: FakeLink, car: Car) -> None:
    link.script["{turn,90}"] = ["{ok,turn}"]
    car.turn(90)
    with pytest.raises(ReplyTimeoutError):
        car.wait_done(0.1)


def test_err_reply_raises(link: FakeLink, car: Car) -> None:
    link.script["{move,1000}"] = ["{err,batt}"]
    with pytest.raises(CommandRejectedError) as error:
        car.move(1000)
    assert error.value.reason is ErrReason.BATT


def test_no_reply_raises(car: Car) -> None:
    with pytest.raises(ReplyTimeoutError):
        car.gyro()


def test_tele_updates_last_tele_after_bad_frames(link: FakeLink, car: Car) -> None:
    for frame in ["{zz}", "{t,1,2}", "{done,turn,zz}", TELE_FRAME]:
        link.push(frame)
    assert wait_until(lambda: car.last_tele is not None)
    tele = car.last_tele
    assert tele is not None
    assert tele.yaw_deg == 90.0
    assert tele.motion is MotionKind.TURN


def test_heartbeat_runs(link: FakeLink, car: Car) -> None:
    time.sleep(WAIT_S)
    assert link.sent.count(HB_FRAME) >= 2


def test_read_failure_stops_heartbeat(link: FakeLink) -> None:
    car = Car(link, HB_MS_SERIAL)
    link.broken = True
    time.sleep(WAIT_S / 2)
    count = link.sent.count(HB_FRAME)
    time.sleep(WAIT_S / 2)
    assert link.sent.count(HB_FRAME) == count
    with pytest.raises(ReplyTimeoutError):
        car.close()


def test_close_sends_stop(link: FakeLink) -> None:
    Car(link, HB_MS_SERIAL).close()
    assert STOP_FRAME in link.sent
    assert link.closed
