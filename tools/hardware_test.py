import argparse
import dataclasses
import enum
import time

import serial

BAUD = 9600
READ_TIMEOUT_S = 0.05
BOOT_TIMEOUT_S = 8.0
REPLY_TIMEOUT_S = 0.5
SETTLE_S = 0.3
FIXED_SCALE = 100

HB_MS_LONG = 60000
HB_MS_DEFAULT = 1000
TELE_PERIOD_MS = 100
TELE_OFF = 0
SPIN_PWM = 100
SPIN_MS = 1000
LONG_SPIN_MS = 3000
STOP_AFTER_S = 0.5
TURN_DEG = 90

EXPECTED_LINE_MASK = "6"
IMU_OK = "1"
MIN_BATT_MV = 7000
MIN_SPIN_DEG = 20
TURN_TOLERANCE_DEG = 10
TIMING_TOLERANCE_S = 0.3
TELE_WINDOW_S = 1.0
TELE_OFF_WINDOW_S = 0.6
MIN_TELE_FRAMES = 8
MAX_TELE_FRAMES = 12

SPIN_TIMEOUT_S = 2.0
TURN_TIMEOUT_S = 4.0

TELE_YAW_ARG = 5
TELE_BATT_ARG = 6
DONE_REASON_ARG = 1


class FrameKind(enum.StrEnum):
    OK = "ok"
    ERR = "err"
    DONE = "done"
    PARAM = "p"
    TELE = "t"


class Cmd(enum.StrEnum):
    STOP = "stop"
    DRIVE = "drive"
    TURN = "turn"
    TELE = "tele"
    SET = "set"


class StopReason(enum.StrEnum):
    NONE = "none"
    DONE = "done"
    CMD = "cmd"
    HB = "hb"
    BRIDGE = "bridge"
    SONAR = "sonar"
    CLIFF = "cliff"
    TIMEOUT = "timeout"
    IMU = "imu"


class ParamKey(enum.StrEnum):
    IMU = "imu"
    LINE_MASK = "line_mask"
    HB_MS = "hb_ms"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Frame:
    time_s: float
    line: str
    kind: FrameKind
    args: tuple[str, ...]
    reason: StopReason | None


class Link:
    def __init__(self, port: str) -> None:
        self._serial = serial.Serial(port, BAUD, timeout=READ_TIMEOUT_S)
        self._start_s = time.monotonic()
        self.frames: list[Frame] = []

    def send(self, *fields: object) -> float:
        text = format_frame(*fields)
        sent_s = self._now()
        print(f"{sent_s:7.2f} > {text}")
        self._serial.write(text.encode())
        return sent_s

    def read_until(self, kind: FrameKind, *args: str, timeout_s: float) -> Frame | None:
        """Reads frames until one has `kind` and starts with `args`; None after `timeout_s`."""
        end_s = self._now() + timeout_s
        while self._now() < end_s:
            frame = self._read()
            if frame is not None and frame.kind is kind and frame.args[: len(args)] == args:
                return frame
        return None

    def read_for(self, seconds: float) -> list[Frame]:
        end_s = self._now() + seconds
        frames = []
        while self._now() < end_s:
            frame = self._read()
            if frame is not None:
                frames.append(frame)
        return frames

    def yaw_deg(self) -> float:
        """Yaw from the last telemetry frame. Degrees, + = right."""
        return int(self._last_tele().args[TELE_YAW_ARG]) / FIXED_SCALE

    def batt_mv(self) -> int:
        return int(self._last_tele().args[TELE_BATT_ARG])

    def _now(self) -> float:
        return time.monotonic() - self._start_s

    def _read(self) -> Frame | None:
        line = self._serial.readline().decode(errors="replace").strip()
        if not line:
            return None
        time_s = self._now()
        kind_text, *args = line.strip("{}").split(",")
        try:
            kind = FrameKind(kind_text)
            reason = StopReason(args[DONE_REASON_ARG]) if kind is FrameKind.DONE else None
        except ValueError, IndexError:
            print(f"{time_s:7.2f} ! {line}")
            return None
        if kind is not FrameKind.TELE:
            print(f"{time_s:7.2f} < {line}")
        frame = Frame(time_s=time_s, line=line, kind=kind, args=tuple(args), reason=reason)
        self.frames.append(frame)
        return frame

    def _last_tele(self) -> Frame:
        return [frame for frame in self.frames if frame.kind is FrameKind.TELE][-1]


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, name: str, *, passed: bool, detail: str) -> None:
        self.failures += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")


def format_frame(*fields: object) -> str:
    return "{" + ",".join(str(field) for field in fields) + "}"


def check_boot(link: Link, report: Report) -> None:
    link.read_until(FrameKind.PARAM, ParamKey.IMU, timeout_s=BOOT_TIMEOUT_S)
    params = {frame.args[0]: frame.args[1] for frame in link.frames if frame.kind is FrameKind.PARAM}
    imu = params.get(ParamKey.IMU)
    report.check("boot imu", passed=imu == IMU_OK, detail=f"imu={imu}")
    line_mask = params.get(ParamKey.LINE_MASK)
    report.check("boot line_mask", passed=line_mask == EXPECTED_LINE_MASK, detail=f"line_mask={line_mask}")


def expect_reply(link: Link, report: Report, *, name: str, kind: FrameKind, args: tuple[str, ...]) -> None:
    reply = link.read_until(kind, *args, timeout_s=REPLY_TIMEOUT_S)
    report.check(name, passed=reply is not None, detail=format_frame(kind, *args))


def run_motion(link: Link, report: Report, *, name: str, cmd: Cmd, args: tuple[int, ...], timeout_s: float) -> float:
    """Sends `cmd` and waits for its done frame. Returns the yaw change in degrees."""
    yaw_before = link.yaw_deg()
    link.send(cmd, *args)
    ok = link.read_until(FrameKind.OK, cmd, timeout_s=REPLY_TIMEOUT_S)
    done = link.read_until(FrameKind.DONE, cmd, timeout_s=timeout_s)
    link.read_for(SETTLE_S)
    passed = ok is not None and done is not None and done.reason is StopReason.DONE
    report.check(name, passed=passed, detail="no done frame" if done is None else done.line)
    return link.yaw_deg() - yaw_before


def check_spin(link: Link, report: Report, *, name: str, sign: int) -> None:
    args = (sign * SPIN_PWM, -sign * SPIN_PWM, SPIN_MS)
    yaw_change = run_motion(link, report, name=name, cmd=Cmd.DRIVE, args=args, timeout_s=SPIN_TIMEOUT_S)
    report.check(
        f"{name} direction", passed=sign * yaw_change >= MIN_SPIN_DEG, detail=f"yaw change {yaw_change:+.1f} deg"
    )


def check_turn(link: Link, report: Report, *, name: str, deg: int) -> None:
    yaw_change = run_motion(link, report, name=name, cmd=Cmd.TURN, args=(deg,), timeout_s=TURN_TIMEOUT_S)
    passed = abs(yaw_change - deg) <= TURN_TOLERANCE_DEG
    report.check(f"{name} angle", passed=passed, detail=f"yaw change {yaw_change:+.1f} deg")


def check_stop(link: Link, report: Report) -> None:
    link.send(Cmd.DRIVE, SPIN_PWM, -SPIN_PWM, LONG_SPIN_MS)
    link.read_for(STOP_AFTER_S)
    link.send(Cmd.STOP)
    expect_reply(link, report, name="stop reply", kind=FrameKind.OK, args=(Cmd.STOP,))
    expect_reply(link, report, name="stop done", kind=FrameKind.DONE, args=(Cmd.DRIVE, StopReason.CMD))
    link.read_for(SETTLE_S)


def check_tele(link: Link, report: Report) -> None:
    count = sum(frame.kind is FrameKind.TELE for frame in link.read_for(TELE_WINDOW_S))
    passed = MIN_TELE_FRAMES <= count <= MAX_TELE_FRAMES
    report.check("tele rate", passed=passed, detail=f"{count} frames in {TELE_WINDOW_S} s")
    link.send(Cmd.TELE, TELE_OFF)
    expect_reply(link, report, name="tele off reply", kind=FrameKind.OK, args=(Cmd.TELE,))
    late = sum(frame.kind is FrameKind.TELE for frame in link.read_for(TELE_OFF_WINDOW_S))
    report.check("tele off", passed=late == 0, detail=f"{late} frames after tele off")


def check_heartbeat(link: Link, report: Report) -> None:
    link.send(Cmd.SET, ParamKey.HB_MS, HB_MS_DEFAULT)
    expect_reply(link, report, name="set hb_ms", kind=FrameKind.OK, args=(Cmd.SET,))
    link.send(Cmd.DRIVE, SPIN_PWM, -SPIN_PWM, LONG_SPIN_MS)
    ok = link.read_until(FrameKind.OK, Cmd.DRIVE, timeout_s=REPLY_TIMEOUT_S)
    done = link.read_until(FrameKind.DONE, Cmd.DRIVE, timeout_s=LONG_SPIN_MS / 1000)
    if ok is None or done is None:
        report.check("heartbeat stop", passed=False, detail="no ok or done frame")
        return
    after_s = done.time_s - ok.time_s
    passed = done.reason is StopReason.HB and abs(after_s - HB_MS_DEFAULT / 1000) <= TIMING_TOLERANCE_S
    report.check("heartbeat stop", passed=passed, detail=f"{done.line} after {after_s:.2f} s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the hardware test.")
    parser.add_argument("--port", required=True)
    port = parser.parse_args().port

    link = Link(port)
    report = Report()
    check_boot(link, report)
    link.send(Cmd.SET, ParamKey.HB_MS, HB_MS_LONG)
    expect_reply(link, report, name="setup hb_ms", kind=FrameKind.OK, args=(Cmd.SET,))
    link.send(Cmd.TELE, TELE_PERIOD_MS)
    expect_reply(link, report, name="setup tele", kind=FrameKind.OK, args=(Cmd.TELE,))
    link.read_for(SETTLE_S)
    batt_mv = link.batt_mv()
    report.check("battery", passed=batt_mv >= MIN_BATT_MV, detail=f"{batt_mv} mV")

    check_spin(link, report, name="spin right", sign=1)
    check_spin(link, report, name="spin left", sign=-1)
    check_turn(link, report, name="turn right", deg=TURN_DEG)
    check_turn(link, report, name="turn left", deg=-TURN_DEG)
    check_stop(link, report)
    check_tele(link, report)
    check_heartbeat(link, report)

    print(f"\n{'ALL PASS' if report.failures == 0 else f'{report.failures} FAILED'}")
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
