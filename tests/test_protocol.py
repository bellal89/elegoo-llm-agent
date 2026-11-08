import pytest

from elegoo.protocol import (
    Command,
    Done,
    Err,
    ErrReason,
    ImuStatus,
    MotionKind,
    Ok,
    Param,
    ParamValue,
    PwmLimit,
    Reply,
    StopReason,
    Tele,
    encode,
    parse_reply,
)


@pytest.mark.parametrize(
    ("command", "args", "frame"),
    [
        pytest.param(Command.TURN, (-90,), "{turn,-90}", id="negative int"),
        pytest.param(Command.SET, (Param.KP, 4.5), "{set,kp,4.5}", id="param and float"),
        pytest.param(Command.SET, (Param.HB_MS, 300.0), "{set,hb_ms,300}", id="whole float"),
        pytest.param(Command.GET, (), "{get}", id="no args"),
    ],
)
def test_encode(command: Command, args: tuple[int | float | str, ...], frame: str) -> None:
    assert encode(command, *args) == frame


def test_encode_rejects_long_frame() -> None:
    with pytest.raises(ValueError):
        encode(Command.SET, Param.TURN_SLOW_PWM, 12345678901234)


@pytest.mark.parametrize(
    ("frame", "reply"),
    [
        pytest.param("{ok,turn}", Ok(cmd=Command.TURN), id="ok"),
        pytest.param("{err,batt}", Err(reason=ErrReason.BATT), id="err"),
        pytest.param("{done,move,cliff}", Done(cmd=Command.MOVE, reason=StopReason.CLIFF), id="done"),
        pytest.param("{p,kp,4.00}", ParamValue(param=Param.KP, value=4.0), id="float param"),
        pytest.param("{p,imu,1}", ImuStatus(ok=True), id="imu ok"),
        pytest.param("{p,imu,0}", ImuStatus(ok=False), id="imu fail"),
        pytest.param("{p,pwm_limit,150}", PwmLimit(value=150), id="pwm limit"),
        pytest.param(
            "{t,1234,0,45,1017,46,-9050,7810,turn,none}",
            Tele(
                ms=1234,
                sonar_cm=0,
                line=(45, 1017, 46),
                yaw_deg=-90.5,
                batt_mv=7810,
                motion=MotionKind.TURN,
                stop_reason=StopReason.NONE,
            ),
            id="tele",
        ),
    ],
)
def test_parse_reply(frame: str, reply: Reply) -> None:
    assert parse_reply(frame) == reply


@pytest.mark.parametrize(
    "frame",
    [
        pytest.param("ok,turn}", id="no opening brace"),
        pytest.param("{ok,turn", id="no closing brace"),
        pytest.param("{ok}", id="missing field"),
        pytest.param("{zz,turn}", id="unknown kind"),
        pytest.param("{done,turn,zz}", id="unknown stop reason"),
        pytest.param("{p,nope,1}", id="unknown param"),
        pytest.param("{p,kp,x}", id="bad param value"),
        pytest.param("{p,imu,2}", id="bad imu flag"),
        pytest.param("{p,pwm_limit,1.5}", id="fractional pwm limit"),
        pytest.param("{t,1,2}", id="short tele"),
        pytest.param("{t,1,0,45,1017,46,x,7810,turn,none}", id="bad tele number"),
    ],
)
def test_parse_reply_rejects_bad_frame(frame: str) -> None:
    assert parse_reply(frame) is None
