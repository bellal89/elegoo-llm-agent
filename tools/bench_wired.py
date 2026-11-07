# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial==3.5"]
# ///
import argparse
import dataclasses
import time

import serial

DEFAULT_PORT = "/dev/cu.usbserial-1110"
BAUD = 9600
READ_TIMEOUT_S = 0.05
BOOT_TIMEOUT_S = 8.0
REPLY_TIMEOUT_S = 0.5
SETTLE_S = 0.3
FIXED_SCALE = 100

HB_MS_LONG = 60000
HB_MS_DEFAULT = 1000
TELE_PERIOD_MS = 100
SPIN_PWM = 100
SPIN_MS = 1000
LONG_SPIN_MS = 3000
STOP_AFTER_S = 0.5
TURN_DEG = 90

EXPECTED_LINE_MASK = 6
MIN_BATT_MV = 7000
MIN_SPIN_DEG = 20
TURN_TOLERANCE_DEG = 10
TIMING_TOLERANCE_S = 0.3
TELE_WINDOW_S = 1.0
MIN_TELE_FRAMES = 8
MAX_TELE_FRAMES = 12

TELE_YAW_FIELD = 6
TELE_BATT_FIELD = 7


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Frame:
    time_s: float
    fields: tuple[str, ...]


class Link:
    def __init__(self, port: str) -> None:
        self._serial = serial.Serial(port, BAUD, timeout=READ_TIMEOUT_S)
        self._start_s = time.monotonic()
        self.frames: list[Frame] = []

    def send(self, *fields: object) -> float:
        text = "{" + ",".join(str(field) for field in fields) + "}"
        sent_s = self._now()
        print(f"{sent_s:7.2f} > {text}")
        self._serial.write(text.encode())
        return sent_s

    def read_until(self, *prefix: str, timeout_s: float) -> Frame | None:
        """Reads frames until one starts with `prefix`; None after `timeout_s`."""
        end_s = self._now() + timeout_s
        while self._now() < end_s:
            frame = self._read()
            if frame is not None and frame.fields[: len(prefix)] == prefix:
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
        tele = [frame for frame in self.frames if frame.fields[0] == "t"]
        return int(tele[-1].fields[TELE_YAW_FIELD]) / FIXED_SCALE

    def batt_mv(self) -> int:
        tele = [frame for frame in self.frames if frame.fields[0] == "t"]
        return int(tele[-1].fields[TELE_BATT_FIELD])

    def _now(self) -> float:
        return time.monotonic() - self._start_s

    def _read(self) -> Frame | None:
        line = self._serial.readline().decode(errors="replace").strip()
        if not line:
            return None
        frame = Frame(time_s=self._now(), fields=tuple(line.strip("{}").split(",")))
        if frame.fields[0] != "t":
            print(f"{frame.time_s:7.2f} < {line}")
        self.frames.append(frame)
        return frame


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, name: str, *, passed: bool, detail: str) -> None:
        self.failures += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")


def check_boot(link: Link, report: Report) -> None:
    imu = link.read_until("p", "imu", timeout_s=BOOT_TIMEOUT_S)
    params = {frame.fields[1]: frame.fields[2] for frame in link.frames if frame.fields[0] == "p"}
    report.check("A1 boot imu", passed=imu is not None and imu.fields[2] == "1", detail=f"imu={params.get('imu')}")
    line_mask = params.get("line_mask")
    report.check("A1 boot line_mask", passed=line_mask == str(EXPECTED_LINE_MASK), detail=f"line_mask={line_mask}")


def expect_reply(link: Link, report: Report, *, name: str, fields: tuple[str, ...]) -> None:
    reply = link.read_until(*fields, timeout_s=REPLY_TIMEOUT_S)
    report.check(name, passed=reply is not None, detail="{" + ",".join(fields) + "}")


def run_motion(link: Link, report: Report, *, name: str, cmd: tuple[object, ...], timeout_s: float) -> float:
    """Sends `cmd` and waits for its done frame. Returns the yaw change in degrees."""
    yaw_before = link.yaw_deg()
    link.send(*cmd)
    ok = link.read_until("ok", str(cmd[0]), timeout_s=REPLY_TIMEOUT_S)
    done = link.read_until("done", str(cmd[0]), timeout_s=timeout_s)
    link.read_for(SETTLE_S)
    passed = ok is not None and done is not None and done.fields[2] == "done"
    detail = "no done frame" if done is None else f"{{{','.join(done.fields)}}}"
    report.check(name, passed=passed, detail=detail)
    return link.yaw_deg() - yaw_before


def check_spin(link: Link, report: Report, *, name: str, sign: int) -> None:
    yaw_change = run_motion(
        link, report, name=name, cmd=("drive", sign * SPIN_PWM, -sign * SPIN_PWM, SPIN_MS), timeout_s=2.0
    )
    report.check(
        f"{name} direction", passed=sign * yaw_change >= MIN_SPIN_DEG, detail=f"yaw change {yaw_change:+.1f} deg"
    )


def check_turn(link: Link, report: Report, *, name: str, deg: int) -> None:
    yaw_change = run_motion(link, report, name=name, cmd=("turn", deg), timeout_s=4.0)
    passed = abs(yaw_change - deg) <= TURN_TOLERANCE_DEG
    report.check(f"{name} angle", passed=passed, detail=f"yaw change {yaw_change:+.1f} deg")


def check_stop(link: Link, report: Report) -> None:
    link.send("drive", SPIN_PWM, -SPIN_PWM, LONG_SPIN_MS)
    link.read_for(STOP_AFTER_S)
    link.send("stop")
    expect_reply(link, report, name="A5 stop reply", fields=("ok", "stop"))
    expect_reply(link, report, name="A5 stop done", fields=("done", "drive", "cmd"))
    link.read_for(SETTLE_S)


def check_tele(link: Link, report: Report) -> None:
    count = sum(frame.fields[0] == "t" for frame in link.read_for(TELE_WINDOW_S))
    passed = MIN_TELE_FRAMES <= count <= MAX_TELE_FRAMES
    report.check("A6 tele rate", passed=passed, detail=f"{count} frames in {TELE_WINDOW_S} s")
    link.send("tele", 0)
    expect_reply(link, report, name="A6 tele off reply", fields=("ok", "tele"))
    late = sum(frame.fields[0] == "t" for frame in link.read_for(SETTLE_S * 2))
    report.check("A6 tele off", passed=late == 0, detail=f"{late} frames after tele off")


def check_heartbeat(link: Link, report: Report) -> None:
    link.send("set", "hb_ms", HB_MS_DEFAULT)
    expect_reply(link, report, name="A7 set hb_ms", fields=("ok", "set"))
    link.send("drive", SPIN_PWM, -SPIN_PWM, LONG_SPIN_MS)
    ok = link.read_until("ok", "drive", timeout_s=REPLY_TIMEOUT_S)
    done = link.read_until("done", "drive", timeout_s=LONG_SPIN_MS / 1000)
    if ok is None or done is None:
        report.check("A7 heartbeat stop", passed=False, detail="no ok or done frame")
        return
    after_s = done.time_s - ok.time_s
    passed = done.fields[2] == "hb" and abs(after_s - HB_MS_DEFAULT / 1000) <= TIMING_TOLERANCE_S
    report.check("A7 heartbeat stop", passed=passed, detail=f"{{{','.join(done.fields)}}} after {after_s:.2f} s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the wired part of the bench test.")
    parser.add_argument("--port", default=DEFAULT_PORT)
    port = parser.parse_args().port

    link = Link(port)
    report = Report()
    check_boot(link, report)
    link.send("set", "hb_ms", HB_MS_LONG)
    expect_reply(link, report, name="setup hb_ms", fields=("ok", "set"))
    link.send("tele", TELE_PERIOD_MS)
    expect_reply(link, report, name="setup tele", fields=("ok", "tele"))
    link.read_for(SETTLE_S)
    batt_mv = link.batt_mv()
    report.check("A1 battery", passed=batt_mv >= MIN_BATT_MV, detail=f"{batt_mv} mV")

    check_spin(link, report, name="A2 spin right", sign=1)
    check_spin(link, report, name="A3 spin left", sign=-1)
    check_turn(link, report, name="A4 turn right", deg=TURN_DEG)
    check_turn(link, report, name="A4 turn left", deg=-TURN_DEG)
    check_stop(link, report)
    check_tele(link, report)
    check_heartbeat(link, report)

    print(f"\n{'ALL PASS' if report.failures == 0 else f'{report.failures} FAILED'}")
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
