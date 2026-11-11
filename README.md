# LLM agent for the Elegoo robot car

A research project: an LLM agent drives the Elegoo Smart Robot Car V4.0 from a natural-language instruction. The project compares three agent "brains": a frontier model through an API, a local open model and a small fine-tuned model. This repository contains the car firmware with onboard safety and a Python host that controls and calibrates the car over USB or Wi-Fi. Details: [About](#about).

## Prerequisites

- [arduino-cli](https://arduino.github.io/arduino-cli/): `brew install arduino-cli`. The first `make upload` downloads the board core and the libraries that `firmware/car/sketch.yaml` sets.
- [uv](https://docs.astral.sh/uv/): `brew install uv`.

## Usage

| Command | Action |
| --- | --- |
| `make init install` | Set up Python and the git hooks |
| `make lint` | Lint and type check the Python code |
| `make test` | Run the firmware and Python tests on the computer |
| `make upload` | Compile the firmware and flash the car |
| `make hardware-test` | Run the wired part of the hardware test |
| `make calibrate-usb` | Calibrate the car over USB. Write the results to `profile.json`. `STEP` selects one step |
| `make calibrate-wifi` | The same through the ESP32 Wi-Fi |

The default serial port is `/dev/cu.usbserial-1110`. To find the port of the car, run `arduino-cli board list`. To use another port, give the full path, for example: `make upload PORT=/dev/cu.usbserial-1420`.

To turn the car 90° to the right, run `uv run python -m elegoo.car --port /dev/cu.usbserial-1110 turn 90`. Through the ESP32 Wi-Fi, use `--tcp` instead of `--port PORT`.

The pre-commit hook formats the Python code.

Hardware test after a firmware change: [docs/hardware-test.md](docs/hardware-test.md).

## About

An agent drives the Elegoo robot car from a natural-language instruction. It checks each step with the camera and the sensors. The operator watches the car video on a monitor and gives a task, for example: "drive to the red box and turn to face the door".

At start, the agent calibrates the car. Then it converts the instruction into a plan, executes the steps through a safe set of actions, and makes a new plan when a step fails.

**Research question:** can a small fine-tuned model check the steps not worse than a frontier model by more than a fixed margin, with a much lower decision latency and a shorter task time? The project compares three "brains":

- a proprietary frontier model through an API;
- an open model that runs locally;
- a small fast model, fine-tuned on data from the project's own runs.

## Hardware and the main constraint

The UNO cannot execute new code at run time; a code change needs a new flash. Thus "code for the car" has three levels, and fast reactions run on board.

Kit: [Smart Robot Car Kit V4.0 with camera](https://www.elegoo.com/products/elegoo-smart-robot-car-kit-v-4-0), per the [listing specification](https://www.desertcart.lk/products/128067046-elegoo-uno-project-smart-robot-car-kit):

| Component | Part | Role in the project |
| --- | --- | --- |
| Controller | Elegoo UNO R3 | Executes behaviors, fast loop |
| Motors | 4 × 1:48 motors, TB6612 driver | Motion; calibration removes left/right asymmetry |
| Range sensor | Ultrasonic | Emergency stop, distance check |
| Line sensors | IR | Optional: track marks for tests |
| Camera | OV2640, up to 1024×768, on ESP32-WROVER | Video for the operator and the model |
| Link | Wi-Fi through ESP32, UART to UNO | Commands and telemetry |
| Pan mount | SG90, horizontal only, 0–180° | Scene scan without a body turn |
| Battery | 7.4 V, approx. 2 h in line mode | Limits the length of a run series |

Three levels of "code for the car":

1. **MVP.** The agent runs on the computer and sends simple commands over Wi-Fi.
2. **Behavior interpreter in the firmware.** The agent sends programs such as "drive while the obstacle is more than 20 cm away, max 3 s". The car reacts on board, without the model. This solves the real-time problem.
3. **Optional: generated firmware.** The agent writes C++, compiles it, and flashes it with arduino-cli. Slow, but a good demo.

The project replaces the factory firmware: a command protocol for the agent is easier to design from zero.

## Architecture: three loops

The agent has three loops with different speeds. The model is not in the fast loop.

```mermaid
%%{init: {"theme": "neutral", "flowchart": {"curve": "basis"}}}%%
flowchart TB
    op("<b>Operator</b><br/>Human at a web dashboard")
    llm("<b>Large model · seconds</b><br/>Plan, step checks, replan")
    pc("<b>Computer · hundreds of ms</b><br/>Car MCP server, fast frame checks")
    subgraph car [Car]
        uno("<b>UNO · milliseconds</b><br/>Behaviors, sonar stop, watchdog")
        cam("<b>ESP32 camera</b>")
    end

    op -- instruction --> llm
    llm -. plan and status .-> op
    llm -- tool calls --> pc
    pc -. frames and step status .-> llm
    pc -- behavior programs --> uno
    uno -. telemetry .-> pc
    cam -. frames .-> pc

    classDef fast stroke-width:3px
    class uno fast
```

Solid arrows are commands. Dotted arrows are observations.

The model plans and checks the steps at checkpoints. In front of an obstacle, the car stops by itself in milliseconds. Thus API latency makes a task slower, but not dangerous.

## Auto-calibration at start

Before the first task, the agent runs a short series of tests and saves a calibration profile. Reference: an ArUco marker on the wall. The camera finds the car position from it.

| Test | Measurement | Result |
| --- | --- | --- |
| Drive straight 1–2 s | Heading drift against the marker | Power correction for left and right side |
| Turn in place | Angle in a given time | Turn rate, °/s |
| Sonar at a wall | Reading against a known distance | Range sensor offset and noise, cm |
| Pan servo | Marker position in the frame | Camera center and turn limits |
| Video | Monitor timer, filmed by the camera | Frame latency, ms |

The planner uses the profile to convert "turn 90°" into a duration and a power. Speed decreases as the battery discharges. Thus, repeat the calibration at the start of each run series.

## Model comparison and evaluation

Main result: a "model × metric" table on one task set. Live runs are expensive and noisy. Thus most of the comparison uses recorded episodes.

| Variant | Runs on | Strength | Risk |
| --- | --- | --- | --- |
| Proprietary frontier model | API | Scene understanding and planning | Network latency, cost per call |
| Open VLM | Local: Mac with MLX or llama.cpp, or vLLM on a rented GPU | No network latency, free calls | Weaker planning |
| Small fine-tuned VLM | Local | Fastest on narrow checks | Fails outside its tasks |

The small model is fine-tuned with LoRA on frames from the project's runs. A teacher model labels the frames: step done or not, obstacle or not, target position in the frame. The small model learns only the step checks, not the planning.

Two experiments:

| Experiment | Variant | Plans | Checks the steps |
| --- | --- | --- | --- |
| A. Full brain | Frontier | Frontier VLM | Frontier VLM |
| | Open | Open VLM | Open VLM |
| B. Hybrid | Frontier | Frontier VLM | Frontier VLM |
| | Hybrid | Frontier VLM | Small fine-tuned VLM |

All variants get the same inputs, the same actions and the same limits: frame size, telemetry, action set, step budget.

Data split: by whole episodes and by scene configurations, not by frames. Thus frames of one run and of one scene are not in train and in test together. A person labels the test frames by hand. Teacher labels are for training only, because with teacher labels the test cannot show an error that the teacher also makes.

Related work reports that fine-tuned failure detectors can be worse than general VLMs. Thus "the small model checks steps worse" is also a valid result.

**Baselines:**

- classic CV without a model: color or ArUco detection and PID; shows if a VLM is necessary;
- zero-shot VLM policy: the model selects an action directly from the frame, without a plan.

Before live runs, select the local models on Point-Bench for target pointing.

**Task set** (max 20 reps each):

- drive to a colored object;
- go around an obstacle and return to the course;
- find an object with a camera pan and face it;
- park between two boxes;
- multi-step: drive to the door, turn around, return to the start.

**Metrics:** task success rate, SPL (success weighted by path length), execution time, number of operator interventions, collisions, decision latency (p50 and p95, ms), output tokens per decision, cost per task.

**Step check metrics:** precision and recall of "step done", separately. A false "step done" is more dangerous than a false "step not done": the agent goes to the next step from a wrong position.

**Two evaluation modes:**

- offline replay: the models make decisions on the same recorded frames and telemetry; reproducible and cheap;
- live runs: final check in a closed loop.

Offline errors do not accumulate, live errors do. Thus the report gives the correlation of the model ranks between the two modes.

"No significant difference" does not show that two models are equal. Thus the main claim uses a non-inferiority test with a margin δ that is set before the runs: the small model checks the steps not worse than the frontier model by more than δ = 5 percentage points of precision of "step done", one-sided α = 0.05.

The test runs on step check decisions in offline replay. Live runs cannot give the claim: a live test of a success rate near 0.8 with a margin of 15 percentage points needs about 90 runs per variant (power 0.8); the task set has max 20 per task. Live runs confirm the offline result: the same rank of the variants and no large drop in success rate. Each rate has a Wilson confidence interval.

Related work and its relation to the project: [docs/papers/README.md](docs/papers/README.md).

## Techniques and technologies

| Area | Techniques | Track |
| --- | --- | --- |
| Embedded and link | Arduino C++, ESP32 and video stream, UART bridge, custom command protocol, watchdog, arduino-cli | Robotics |
| Control | Open and closed loop, PID for heading and distance, calibration, ArUco markers with OpenCV, latency compensation, hierarchical control | Robotics |
| Agents | Tool calling, structured output, planner–executor–verifier, code-as-policy on a mini-language, replanning, MCP server for the car | Agents |
| Vision and VLM | Frame resolution against latency, object pointing with points and boxes, step completion detection, classic CV against VLM | Agents, VLM |
| Models | Local inference (MLX, llama.cpp, vLLM), quantization for speed, LoRA fine-tuning of a VLM, distillation, data collection | Post-training, inference |
| Evaluation | Task set design, offline and live evaluation, latency profiling, intervals for rates, failure classification | Evaluation |
| Infrastructure | async Python, WebSocket, web dashboard with video, chat, telemetry and plan, episode logging | Engineering |

The MCP server gives all models the same tools. Thus the comparison is fairer.

## Roadmap

Each stage ends with a result that you can check.

- [ ] **MVP.** Custom firmware with simple commands, video to the computer, one task, API model, episode recording. Done when the car sometimes reaches the red object.
- [ ] **Onboard safety.** Watchdog, sonar stop, behavior interpreter. Done when model latency cannot cause a collision.
- [ ] **Calibration.** Tests and profile from the section above. Target: 90° turn with an error of max 10°.
- [ ] **Agent and dashboard.** Plan, step checks, replanning, MCP server, web UI with video and chat.
- [ ] **Task set and baselines.** Five tasks, live runs with the proprietary model, the classic CV and the zero-shot VLM baselines, offline replay of the recordings.
- [ ] **Open and fine-tuned models.** Selection on Point-Bench, local inference, teacher labels, LoRA, hand labels for the test frames, experiments A and B, non-inferiority test of the step checks.
- [ ] **Report and demo.** Results table with intervals, offline–live rank correlation and a short video of a command execution.
