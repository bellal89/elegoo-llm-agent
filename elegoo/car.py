import argparse
import enum
import logging
import queue
import threading
import time
import types
import typing

from elegoo.errors import CommandRejectedError, LinkError, ReplyTimeoutError
from elegoo.link import Link, SerialLink, TcpLink
from elegoo.protocol import (
    Command,
    Done,
    Err,
    ImuStatus,
    Ok,
    Param,
    ParamValue,
    PwmLimit,
    StopReason,
    Tele,
    encode,
    parse_reply,
)

HB_MS_SERIAL = 300
HB_MS_TCP = 1000
HB_PER_PERIOD = 3
REPLY_TIMEOUT_S = 0.5
GYRO_TIMEOUT_S = 3.0
BOOT_TIMEOUT_S = 8.0
READ_POLL_S = 0.1
MS_PER_S = 1000
TURN_DONE_TIMEOUT_S = 6.0

logger = logging.getLogger(__name__)

type CommandReply = Ok | Err | Done | ParamValue | ImuStatus | PwmLimit
type ParamReply = ParamValue | ImuStatus | PwmLimit


class CliCommand(enum.StrEnum):
    TURN = "turn"


class Car:
    def __init__(self, link: Link, hb_ms: int) -> None:
        self._link = link
        self._hb_period_s = hb_ms / MS_PER_S / HB_PER_PERIOD
        self._replies: queue.Queue[CommandReply] = queue.Queue()
        self._pending_dones: list[Done] = []
        self._motion: Command | None = None
        self._last_tele: Tele | None = None
        self._tele_received = threading.Condition()
        self._imu_ok: bool | None = None
        self._pwm_limit: int | None = None
        self._stopped = threading.Event()
        self._reader = threading.Thread(target=self._read_frames, daemon=True)
        self._heartbeat = threading.Thread(target=self._send_heartbeats, daemon=True)
        try:
            self._start(hb_ms)
        except BaseException:
            self._shutdown()
            raise

    @property
    def last_tele(self) -> Tele | None:
        return self._last_tele

    @property
    def imu_ok(self) -> bool | None:
        return self._imu_ok

    @property
    def pwm_limit(self) -> int | None:
        """None if the firmware does not report it."""
        return self._pwm_limit

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.close()

    def drive(self, left: int, *, right: int, duration_ms: int) -> None:
        """PWM -150..150 per side, capped by max_pwm, open loop."""
        self._start_motion(Command.DRIVE, left, right, duration_ms)

    def move(self, duration_ms: int) -> None:
        self._start_motion(Command.MOVE, duration_ms)

    def turn(self, deg: int) -> None:
        """Positive deg turns right."""
        self._start_motion(Command.TURN, deg)

    def stop(self) -> None:
        self._command(Command.STOP)

    def gyro(self) -> None:
        """Measures the gyro bias. The car must not move for 2 s."""
        self._command(Command.GYRO, timeout_s=GYRO_TIMEOUT_S)

    def set_param(self, param: Param, value: float) -> None:
        self._command(Command.SET, param, value)

    def params(self) -> dict[Param, float]:
        values: dict[Param, float] = {}
        for reply in self._command(Command.GET):
            match reply:
                case ParamValue():
                    values[reply.param] = reply.value
                case ImuStatus():
                    self._imu_ok = reply.ok
                case PwmLimit():
                    self._pwm_limit = reply.value
        return values

    def tele(self, period_ms: int) -> None:
        """Telemetry period: 0 = off, else 100..65535 ms."""
        self._command(Command.TELE, period_ms)

    def next_tele(self, timeout_s: float) -> Tele:
        """Waits for a telemetry frame that comes after this call."""
        with self._tele_received:
            previous = self._last_tele
            self._tele_received.wait_for(lambda: self._last_tele is not previous, timeout_s)
            tele = self._last_tele
        if tele is None or tele is previous:
            raise ReplyTimeoutError("no telemetry from the car")
        return tele

    def wait_done(self, timeout_s: float) -> StopReason:
        """Returns the stop reason of the last motion command."""
        deadline_s = time.monotonic() + timeout_s
        while True:
            done = self._pending_dones.pop(0) if self._pending_dones else self._next_done(deadline_s)
            if done.cmd is self._motion:
                return done.reason
            logger.debug("Drop stale %s", done)

    def close(self) -> None:
        try:
            self.stop()
        finally:
            self._shutdown()

    def _start(self, hb_ms: int) -> None:
        self._reader.start()
        if self._link.resets_car:
            self._wait_boot()
        try:
            self.set_param(Param.HB_MS, hb_ms)
        except ReplyTimeoutError as error:
            # A boot report came, so only the UNO RX is cut off: S1 routes it to the ESP32.
            if self._link.resets_car:
                raise LinkError('the car sends but does not receive. Set switch S1 to "upload".') from error
            raise
        self._heartbeat.start()
        self.params()

    def _shutdown(self) -> None:
        self._stopped.set()
        for thread in (self._reader, self._heartbeat):
            if thread.is_alive():
                thread.join()
        self._link.close()

    def _wait_boot(self) -> None:
        deadline_s = time.monotonic() + BOOT_TIMEOUT_S
        while not isinstance(reply := self._next_reply(deadline_s, expected="boot report"), ImuStatus):
            logger.debug("Drop boot %s", reply)
        self._imu_ok = reply.ok

    def _start_motion(self, command: Command, *args: int | str) -> None:
        self._command(command, *args)
        self._motion = command
        # The UNO sends the done of a preempted motion before the ok of the new one.
        self._pending_dones.clear()

    def _command(self, command: Command, *args: float | str, timeout_s: float = REPLY_TIMEOUT_S) -> list[ParamReply]:
        """Sends the command and waits for its ok. Returns the param replies that came before the ok."""
        self._send(encode(command, *args))
        deadline_s = time.monotonic() + timeout_s
        values: list[ParamReply] = []
        while True:
            reply = self._next_reply(deadline_s, expected=f"ok for {command}")
            match reply:
                case Ok() if reply.cmd is command:
                    return values
                case Ok():
                    logger.warning("Drop unexpected %s", reply)
                case Err():
                    raise CommandRejectedError(reply.reason)
                case Done():
                    self._pending_dones.append(reply)
                case ParamValue() | ImuStatus() | PwmLimit():
                    values.append(reply)

    def _next_done(self, deadline_s: float) -> Done:
        while True:
            reply = self._next_reply(deadline_s, expected="done")
            match reply:
                case Done():
                    return reply
                case Ok() | Err() | ParamValue() | ImuStatus() | PwmLimit():
                    logger.warning("Drop unexpected %s", reply)

    def _next_reply(self, deadline_s: float, *, expected: str) -> CommandReply:
        try:
            return self._replies.get(timeout=max(0.0, deadline_s - time.monotonic()))
        except queue.Empty:
            raise ReplyTimeoutError(f"no {expected} from the car") from None

    def _send(self, frame: str) -> None:
        logger.debug("Send %s", frame)
        self._link.send(frame)

    def _read_frames(self) -> None:
        try:
            while not self._stopped.is_set():
                frame = self._link.recv(READ_POLL_S)
                if frame is not None:
                    self._handle_frame(frame)
        except Exception:
            logger.exception("Reader failed, stop the heartbeat")
            self._stopped.set()

    def _handle_frame(self, frame: str) -> None:
        logger.debug("Receive %s", frame)
        reply = parse_reply(frame)
        match reply:
            case None:
                logger.warning("Drop bad frame %s", frame)
            case Tele():
                with self._tele_received:
                    self._last_tele = reply
                    self._tele_received.notify_all()
            case Ok() | Err() | Done() | ParamValue() | ImuStatus() | PwmLimit():
                self._replies.put(reply)

    def _send_heartbeats(self) -> None:
        try:
            while not self._stopped.wait(self._hb_period_s):
                self._send(encode(Command.HB))
        except Exception:
            logger.exception("Heartbeat failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one command to the car.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--port", help="serial port of the UNO")
    target.add_argument("--tcp", action="store_true", help="connect through the ESP32 Wi-Fi bridge")
    commands = parser.add_subparsers(dest="command", required=True)
    turn = commands.add_parser(CliCommand.TURN, help="turn in place, positive = right")
    turn.add_argument("deg", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    with Car(TcpLink(), HB_MS_TCP) if args.tcp else Car(SerialLink(args.port), HB_MS_SERIAL) as car:
        match CliCommand(args.command):
            case CliCommand.TURN:
                car.turn(args.deg)
                print(car.wait_done(TURN_DONE_TIMEOUT_S))


if __name__ == "__main__":
    main()
