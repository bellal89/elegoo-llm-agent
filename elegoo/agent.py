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
from elegoo.errors import ElegooError, ModelTimeoutError, NotReadyError, ProfileError, ToolCallError
from elegoo.link import TcpLink
from elegoo.model import Model, Request
from elegoo.profile import Profile, load_profile
from elegoo.protocol import Param
from elegoo.tools import MOVE_CM_MIN, Action, Finish, Move, Turn, parse_action

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
    try:
        profile.ms_for_cm(MOVE_CM_MIN, pwm=int(car.params()[Param.MOVE_PWM]), batt_mv=profile.batt_mv)
    except ProfileError as error:
        raise NotReadyError(f"{error}. Run make calibrate-wifi STEP=speed.") from error


def run_episode(
    car: Car, *, model: Model, recorder: EpisodeRecorder, profile: Profile, move_pwm: int, instruction: str
) -> EpisodeResult:
    """Closes the episode record also when an exception leaves it. Ctrl-C stops the car and ends the episode."""
    result = EpisodeResult.ERROR
    try:
        result = _run_steps(
            car, model=model, recorder=recorder, profile=profile, move_pwm=move_pwm, instruction=instruction
        )
    except KeyboardInterrupt:
        result = EpisodeResult.OPERATOR
        car.stop()
    except ElegooError, anthropic.APIError:
        logger.exception("Episode failed")
    finally:
        recorder.close(result)
        logger.info("Episode result %s", result)
    return result


def _run_steps(
    car: Car, *, model: Model, recorder: EpisodeRecorder, profile: Profile, move_pwm: int, instruction: str
) -> EpisodeResult:
    deadline_s = time.monotonic() + EPISODE_TIMEOUT_S
    history: list[str] = []
    for index in range(MAX_DECISIONS):
        if time.monotonic() >= deadline_s:
            return EpisodeResult.TIMEOUT
        frame = capture()
        tele = car.next_tele(TELE_TIMEOUT_S)
        request = Request(instruction=instruction, frame=frame, tele=tele, history=tuple(history))
        step = StepRecord(index=index, frame=recorder.frame_name(index), tele_before=tele, outcome=StepOutcome.ACTION)
        # A failed or interrupted step is training data too: record it before the exception leaves.
        try:
            step, action = _decide(model, request, step=step)
            step, result = _act(car, step, action, profile=profile, move_pwm=move_pwm, deadline_s=deadline_s)
        except BaseException as error:
            recorder.add_step(dataclasses.replace(step, error=_error_text(error)), frame=frame)
            raise
        recorder.add_step(step, frame=frame)
        if result is not None:
            return result
        history.append(_history_line(step))
        logger.info("Step %s", history[-1])
    return EpisodeResult.BUDGET


def _decide(model: Model, request: Request, *, step: StepRecord) -> tuple[StepRecord, Action | None]:
    """Returns the step with the decision and the action, or None for a decision without a valid tool call."""
    try:
        decision = model.decide(request, frame_name=step.frame)
    except ModelTimeoutError as error:
        return dataclasses.replace(step, outcome=StepOutcome.MODEL_TIMEOUT, error=str(error)), None
    step = dataclasses.replace(step, decision=decision)
    if decision.call is None:
        error = f"{NO_TOOL_CALL}, stop reason {decision.stop_reason}"
        return dataclasses.replace(step, outcome=StepOutcome.NO_TOOL, error=error), None
    try:
        return step, parse_action(decision.call)
    except ToolCallError as error:
        return dataclasses.replace(step, outcome=StepOutcome.BAD_TOOL, error=str(error)), None


def _act(
    car: Car, step: StepRecord, action: Action | None, *, profile: Profile, move_pwm: int, deadline_s: float
) -> tuple[StepRecord, EpisodeResult | None]:
    """Returns the step with the action result and the episode result if the episode ends."""
    if action is not None and time.monotonic() >= deadline_s:
        return dataclasses.replace(step, error=EPISODE_TIMEOUT_ERROR), EpisodeResult.TIMEOUT
    match action:
        case None:
            return step, None
        case Finish():
            return dataclasses.replace(step, outcome=StepOutcome.FINISH), EpisodeResult.FINISH
        case Turn():
            car.turn(action.deg)
            reason = car.wait_done(TURN_DONE_TIMEOUT_S)
        case Move():
            duration_ms = profile.ms_for_cm(action.cm, pwm=move_pwm, batt_mv=step.tele_before.batt_mv)
            car.move(duration_ms)
            reason = car.wait_done(duration_ms / MS_PER_S + DONE_MARGIN_S)
    return dataclasses.replace(step, stop_reason=reason, tele_after=car.next_tele(TELE_TIMEOUT_S)), None


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


def _history_line(step: StepRecord) -> str:
    call = NO_TOOL_CALL
    if step.decision is not None and step.decision.call is not None:
        tool = step.decision.call
        call = " ".join([tool.name, *(f"{key}={value}" for key, value in tool.input.items())])
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
        params = car.params()
        model = Model(anthropic.Anthropic(), model_id=args.model, sonar_stop_cm=int(params[Param.SONAR_STOP_CM]))
        header = EpisodeHeader(
            instruction=args.instruction,
            model_id=args.model,
            started_at=datetime.datetime.now(datetime.UTC).isoformat(),
            profile=profile,
            batt_mv=car.next_tele(TELE_TIMEOUT_S).batt_mv,
        )
        recorder = EpisodeRecorder(header)
        result = run_episode(
            car,
            model=model,
            recorder=recorder,
            profile=profile,
            move_pwm=int(params[Param.MOVE_PWM]),
            instruction=args.instruction,
        )
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
