import argparse
import dataclasses
import datetime
import logging
import time

import anthropic

from elegoo.accept import DONE_MARGIN_S, ask_yes
from elegoo.calibrate import PROFILE_PATH, TELE_PERIOD_MS, TELE_TIMEOUT_S
from elegoo.camera import capture
from elegoo.car import HB_MS_TCP, MS_PER_S, TURN_DONE_TIMEOUT_S, Car
from elegoo.episode import EpisodeHeader, EpisodeRecorder, EpisodeResult, StepOutcome, StepRecord, Verdict
from elegoo.errors import ElegooError, ModelTimeoutError, NotReadyError, ToolCallError
from elegoo.link import TcpLink
from elegoo.model import Model, Request
from elegoo.profile import Profile, load_profile
from elegoo.protocol import Param, StopReason, Tele
from elegoo.tools import Action, Finish, Move, Turn, parse_action

MAX_DECISIONS = 20
EPISODE_TIMEOUT_S = 180.0
DEFAULT_MODEL = "claude-haiku-5-5"
EPISODE_TIMEOUT_ERROR = "episode timeout"
NO_TOOL_CALL = "no tool call"

logger = logging.getLogger(__name__)


def check_ready(car: Car, profile: Profile) -> None:
    if car.imu_ok is not True:
        raise NotReadyError("the IMU does not work. Restart the car.")
    if profile.speed is None or profile.batt_mv is None:
        raise NotReadyError(f"{PROFILE_PATH} has no speed calibration. Run make calibrate-wifi STEP=speed.")


def execute(car: Car, action: Turn | Move, *, profile: Profile, batt_mv: int) -> StopReason:
    match action:
        case Turn():
            car.turn(action.deg)
            return car.wait_done(TURN_DONE_TIMEOUT_S)
        case Move():
            duration_ms = profile.ms_for_cm(action.cm, pwm=int(car.params()[Param.MOVE_PWM]), batt_mv=batt_mv)
            car.move(duration_ms)
            return car.wait_done(duration_ms / MS_PER_S + DONE_MARGIN_S)


def run_episode(
    car: Car, *, model: Model, recorder: EpisodeRecorder, profile: Profile, instruction: str
) -> EpisodeResult:
    """Closes the episode record. Ctrl-C stops the car and ends the episode."""
    try:
        result = _run_steps(car, model=model, recorder=recorder, profile=profile, instruction=instruction)
    except KeyboardInterrupt:
        car.stop()
        result = EpisodeResult.OPERATOR
    except ElegooError, anthropic.APIError:
        logger.exception("Episode failed")
        result = EpisodeResult.ERROR
    recorder.close(result)
    logger.info("Episode result %s", result)
    return result


def _run_steps(
    car: Car, *, model: Model, recorder: EpisodeRecorder, profile: Profile, instruction: str
) -> EpisodeResult:
    start_s = time.monotonic()
    history: list[str] = []
    for index in range(MAX_DECISIONS):
        if time.monotonic() - start_s >= EPISODE_TIMEOUT_S:
            return EpisodeResult.TIMEOUT
        frame = capture()
        tele = car.next_tele(TELE_TIMEOUT_S)
        request = Request(instruction=instruction, frame=frame, tele=tele, history=tuple(history))
        step, action = _decide(model, request, step=_empty_step(index, recorder=recorder, tele=tele))
        if action is not None and time.monotonic() - start_s >= EPISODE_TIMEOUT_S:
            recorder.add_step(dataclasses.replace(step, error=EPISODE_TIMEOUT_ERROR), frame=frame)
            return EpisodeResult.TIMEOUT
        match action:
            case None:
                pass
            case Finish():
                recorder.add_step(dataclasses.replace(step, outcome=StepOutcome.FINISH), frame=frame)
                return EpisodeResult.FINISH
            case Turn() | Move():
                reason = execute(car, action, profile=profile, batt_mv=tele.batt_mv)
                step = dataclasses.replace(step, stop_reason=reason, tele_after=car.next_tele(TELE_TIMEOUT_S))
        recorder.add_step(step, frame=frame)
        history.append(_history_line(step))
        logger.info("Step %s", history[-1])
    return EpisodeResult.BUDGET


def _empty_step(index: int, *, recorder: EpisodeRecorder, tele: Tele) -> StepRecord:
    return StepRecord(
        index=index,
        frame=recorder.frame_name(index),
        tele_before=tele,
        request=None,
        response=None,
        tool=None,
        tool_input=None,
        outcome=StepOutcome.ACTION,
        error=None,
        latency_ms=0,
        input_tokens=0,
        output_tokens=0,
        stop_reason=None,
        tele_after=None,
    )


def _decide(model: Model, request: Request, *, step: StepRecord) -> tuple[StepRecord, Action | None]:
    """Returns the step with the decision and the action, or None for a decision without a valid tool call."""
    try:
        decision = model.decide(request, frame_name=step.frame)
    except ModelTimeoutError as error:
        return dataclasses.replace(step, outcome=StepOutcome.MODEL_TIMEOUT, error=str(error)), None
    step = dataclasses.replace(
        step,
        request=decision.request,
        response=decision.response,
        latency_ms=decision.latency_ms,
        input_tokens=decision.input_tokens,
        output_tokens=decision.output_tokens,
    )
    if decision.call is None:
        error = f"{NO_TOOL_CALL}, stop reason {decision.stop_reason}"
        return dataclasses.replace(step, outcome=StepOutcome.NO_TOOL, error=error), None
    step = dataclasses.replace(step, tool=decision.call.name, tool_input=decision.call.input)
    try:
        return step, parse_action(decision.call.name, decision.call.input)
    except ToolCallError as error:
        return dataclasses.replace(step, outcome=StepOutcome.BAD_TOOL, error=str(error)), None


def _history_line(step: StepRecord) -> str:
    call = NO_TOOL_CALL
    if step.tool is not None and step.tool_input is not None:
        call = " ".join([step.tool, *(f"{key}={value}" for key, value in step.tool_input.items())])
    return f"{step.index + 1}. {call}: {step.stop_reason or step.error}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Drive the car to a target with an API model over the ESP32 Wi-Fi.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model ID")
    parser.add_argument("instruction", help='for example "drive to the red box"')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    profile = load_profile(PROFILE_PATH)

    with Car(TcpLink(), HB_MS_TCP) as car:
        check_ready(car, profile)
        car.tele(TELE_PERIOD_MS)
        input("Put the car at the start pose. Press Enter, then keep the car still for 3 s.")
        car.gyro()
        model = Model(anthropic.Anthropic(), model_id=args.model, sonar_stop_cm=int(car.params()[Param.SONAR_STOP_CM]))
        header = EpisodeHeader(
            instruction=args.instruction,
            model_id=args.model,
            started_at=datetime.datetime.now(datetime.UTC).isoformat(),
            profile=profile,
            batt_mv=car.next_tele(TELE_TIMEOUT_S).batt_mv,
            imu_ok=True,
        )
        recorder = EpisodeRecorder(header)
        result = run_episode(car, model=model, recorder=recorder, profile=profile, instruction=args.instruction)
        car.tele(0)
    print(f"Result: {result}. Record: {recorder.dir}")
    recorder.set_verdict(
        Verdict(
            success=ask_yes("Did the car reach the target?"),
            contact=ask_yes("Did the car touch the target?"),
            intervention=ask_yes("Did you touch the car during the episode?"),
        )
    )


if __name__ == "__main__":
    main()
