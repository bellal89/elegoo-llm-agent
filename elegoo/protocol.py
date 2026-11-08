import dataclasses
import enum

FRAME_MAX_LEN = 32
FAST_FLAG = "f"
IMU_KEY = "imu"
IMU_OK = "1"
IMU_FAIL = "0"
YAW_SCALE = 100
FIELD_SEPARATOR = ","
FRAME_START = "{"
FRAME_END = "}"


class Command(enum.StrEnum):
    HB = "hb"
    STOP = "stop"
    DRIVE = "drive"
    MOVE = "move"
    TURN = "turn"
    GYRO = "gyro"
    TELE = "tele"
    SET = "set"
    GET = "get"


class ReplyKind(enum.StrEnum):
    OK = "ok"
    ERR = "err"
    DONE = "done"
    PARAM = "p"
    TELE = "t"


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


class ErrReason(enum.StrEnum):
    FRAME = "frame"
    KEY = "key"
    RANGE = "range"
    BATT = "batt"
    IMU = "imu"


class MotionKind(enum.StrEnum):
    IDLE = "idle"
    DRIVE = "drive"
    MOVE = "move"
    TURN = "turn"
    BACK = "back"


class Param(enum.StrEnum):
    MAX_PWM = "max_pwm"
    MOVE_PWM = "move_pwm"
    TURN_PWM = "turn_pwm"
    TURN_SLOW_PWM = "turn_slow_pwm"
    TURN_SLOW_DEG = "turn_slow_deg"
    TURN_MARGIN = "turn_margin"
    KP = "kp"
    SONAR_STOP_CM = "sonar_stop_cm"
    CLIFF_TH = "cliff_th"
    BACK_PWM = "back_pwm"
    BACK_MS = "back_ms"
    MAX_CMD_MS = "max_cmd_ms"
    BATT_MIN_MV = "batt_min_mv"
    HB_MS = "hb_ms"
    LINE_MASK = "line_mask"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Ok:
    cmd: Command


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Err:
    reason: ErrReason


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Done:
    cmd: Command
    reason: StopReason


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ParamValue:
    param: Param
    value: float


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ImuStatus:
    ok: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Tele:
    ms: int
    sonar_cm: int
    line: tuple[int, int, int]
    yaw_deg: float
    batt_mv: int
    motion: MotionKind
    stop_reason: StopReason


type Reply = Ok | Err | Done | ParamValue | ImuStatus | Tele


def encode(command: Command, *args: float | str) -> str:
    fields = [command, *(format(arg, "g") if isinstance(arg, float) else format(arg) for arg in args)]
    frame = FRAME_START + FIELD_SEPARATOR.join(fields) + FRAME_END
    if len(frame) > FRAME_MAX_LEN:
        raise ValueError(f"frame {frame} is longer than {FRAME_MAX_LEN} chars")
    return frame


def parse_reply(frame: str) -> Reply | None:
    """Returns None for a malformed frame or an unknown reply kind."""
    if not (frame.startswith(FRAME_START) and frame.endswith(FRAME_END)):
        return None
    kind, *fields = frame.removeprefix(FRAME_START).removesuffix(FRAME_END).split(FIELD_SEPARATOR)
    try:
        return _parse_fields(ReplyKind(kind), fields)
    except ValueError:
        return None


def _parse_fields(kind: ReplyKind, fields: list[str]) -> Reply:
    match kind:
        case ReplyKind.OK:
            [cmd] = fields
            return Ok(cmd=Command(cmd))
        case ReplyKind.ERR:
            [reason] = fields
            return Err(reason=ErrReason(reason))
        case ReplyKind.DONE:
            cmd, reason = fields
            return Done(cmd=Command(cmd), reason=StopReason(reason))
        case ReplyKind.PARAM:
            key, value = fields
            if key == IMU_KEY:
                return ImuStatus(ok=_parse_imu_flag(value))
            return ParamValue(param=Param(key), value=float(value))
        case ReplyKind.TELE:
            ms, sonar_cm, left, middle, right, yaw_cdeg, batt_mv, motion, stop_reason = fields
            return Tele(
                ms=int(ms),
                sonar_cm=int(sonar_cm),
                line=(int(left), int(middle), int(right)),
                yaw_deg=int(yaw_cdeg) / YAW_SCALE,
                batt_mv=int(batt_mv),
                motion=MotionKind(motion),
                stop_reason=StopReason(stop_reason),
            )


def _parse_imu_flag(value: str) -> bool:
    if value not in (IMU_OK, IMU_FAIL):
        raise ValueError(f"bad imu flag {value}")
    return value == IMU_OK
