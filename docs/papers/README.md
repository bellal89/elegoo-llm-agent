# Related work

Publications that relate to the [research question](../../README.md#about). The PDF files are not in git. To get a file, open the link.

No found work compares a frontier, an open and a distilled small model on a low-cost real robot car for success rate and decision latency. Most related work uses simulation or expensive robots.

"—" in the Code column: the paper and the project page give no code.

## Closest to the project

| File | Publication | Code | Relation to the project |
| --- | --- | --- | --- |
| `2026-localnav.pdf` | [LocalNav: Distilling Frontier VLMs and Embodied RL for On-Device Object Goal Navigation](https://arxiv.org/abs/2606.27871), 2026 | — | Same question, in simulation (HM3D-OVON). Qwen3.5-4B distilled from frontier traces: 37.4% success against 41.6% for the cloud model. Token generation is the main latency cause; shorter outputs and quantization reduce latency by 80%. We measure output tokens per decision for this reason. |
| `2025-la-rcs.pdf` | [LA-RCS: LLM-Agent-Based Robot Control System](https://arxiv.org/abs/2505.18214), 2025 | — | Two LLM agents plan, observe the camera and replan on a small wheeled robot. 90% mean success over four scenario types. One model only, no latency comparison. |
| — | [Latency-Aware Benchmarking of LLMs for Natural-Language Robot Navigation in ROS 2](https://doi.org/10.3390/s26020608), 2026 | — | Metric set: latency, parse success, task success, tokens. Simulation only. |

## Step checks and the small model

| File | Publication | Code | Relation to the project |
| --- | --- | --- | --- |
| `2023-vlm-success-detectors.pdf` | [Vision-Language Models as Success Detectors](https://arxiv.org/abs/2303.07280), 2023 | — | Proposes distillation into a small model for fast online step checks. Motivation for the small model. |
| `2025-i-failsense.pdf` | [I-FailSense: Towards General Robotic Failure Detection with VLMs](https://arxiv.org/abs/2509.16072), 2025 | [clemgris/I-FailSense](https://github.com/clemgris/I-FailSense) | LoRA on PaliGemma2-3B for failure detection. A recipe for the small model. |
| `2026-failbench.pdf` | [FailBench: How Reliable are VLMs at Judging Robot Task Success?](https://arxiv.org/abs/2609.03611), 2026 | [Metric-AI-Lab/failbench](https://github.com/Metric-AI-Lab/failbench) | Risk for the hypothesis. Fine-tuned failure detectors are worse than general VLMs and worse than their own base models. Accuracy is near chance when the result depends on contact. Manipulation data, not navigation. |

## Baselines

| File | Publication | Code | Relation to the project |
| --- | --- | --- | --- |
| `2024-vlmnav.pdf` | [VLMnav: End-to-End Navigation with Vision Language Models](https://arxiv.org/abs/2411.05755), 2024 | [Jirl-upenn/VLMnav](https://github.com/Jirl-upenn/VLMnav) | Zero-shot baseline: the VLM selects an action directly from the frame. |
| `2024-pivot.pdf` | [PIVOT: Iterative Visual Prompting Elicits Actionable Knowledge for VLMs](https://arxiv.org/abs/2402.07872), 2024 | [Demo](https://huggingface.co/spaces/pivot-prompt/pivot-prompt-demo) | Prompting baseline: the VLM selects one of the arrows drawn on the frame. Weaker than VLMnav in its comparisons. |
| `2022-saycan.pdf` | [Do As I Can, Not As I Say (SayCan)](https://arxiv.org/abs/2204.01691), 2022 | [google-research/saycan](https://github.com/google-research/google-research/tree/master/saycan) | Planning with a fixed set of safe skills. Same as our action set. |
| `2022-inner-monologue.pdf` | [Inner Monologue](https://arxiv.org/abs/2207.05608), 2022 | — | Replanning from step-check feedback. Same as our planner–verifier loop. |
| `2022-code-as-policies.pdf` | [Code as Policies](https://arxiv.org/abs/2209.07753), 2022 | [google-research/code_as_policies](https://github.com/google-research/google-research/tree/master/code_as_policies), [prompts](https://code-as-policies.github.io) | The model writes programs for the robot. Same as our behavior mini-language. |

## Test sets

| File | Publication | Code | Relation to the project |
| --- | --- | --- | --- |
| `2025-pointarena.pdf` | [PointArena: Language-Guided Pointing](https://arxiv.org/abs/2505.09990), 2025 | [pointarena/pointarena](https://github.com/pointarena/pointarena), [data](https://huggingface.co/datasets/PointArena) | Point-Bench: select the local models for target pointing before live runs. |
| `2025-point-it-out.pdf` | [Point-It-Out: Embodied Reasoning in Multi-Stage Visual Grounding](https://arxiv.org/abs/2509.25794), 2025 | [xavihart/PIO](https://github.com/xavihart/PIO), [data](https://huggingface.co/pio-benchmark/PIO) | GPT-4o is worse than open models such as Molmo at precise pointing. In the hybrid, an open model can point to the target. |

## Evaluation method

| File | Publication | Code | Relation to the project |
| --- | --- | --- | --- |
| `2025-step-policy-comparison.pdf` | [STEP: Policy Comparison with Near-Optimal Stopping](https://arxiv.org/abs/2503.10966), 2025 | [TRI-ML/sequentialized_barnard_tests](https://github.com/TRI-ML/sequentialized_barnard_tests) | Sequential test for two success rates with few trials. Stops when the result is significant. Fewer runs per battery charge. |
| `2026-n-score.pdf` | [N-SCORE: Sample-Efficient and Statistically Rigorous Robot Policy Comparison](https://arxiv.org/abs/2603.13616), 2026 | — | The same for non-binary metrics, for example time and interventions. |
| `2025-metavqa.pdf` | [MetaVQA: Embodied Scene Understanding for VLMs](https://arxiv.org/abs/2501.09167), 2025 | [metadriverse/MetaVQA](https://github.com/metadriverse/MetaVQA) | Measures the correlation between open-loop and closed-loop VLM scores. Method for offline replay against live runs. |
| `2025-static-and-plugged.pdf` | [Static and Plugged: Make Embodied Evaluation Simple](https://arxiv.org/abs/2508.06553), 2025 | [Data subset](https://huggingface.co/datasets/xiaojiahao/StaticEmbodiedBench) | Evaluation on key frames, with correlation to real-world scores. |
| `2025-rosbag-mcp.pdf` | [ROSBag MCP Server](https://arxiv.org/abs/2511.03497), 2025 | [binabik-ai/mcp-rosbags](https://github.com/binabik-ai/mcp-rosbags) | Tool-call success of 8 LLMs through MCP depends on the tool schema, the argument count and the tool count. Input for the car MCP server design. |

## Architecture

| File | Publication | Code | Relation to the project |
| --- | --- | --- | --- |
| `2024-hirt.pdf` | [HiRT: Hierarchical Robot Transformers](https://arxiv.org/abs/2410.05273), 2024 | — | Slow VLM guides a fast low-level policy. Same as our three loops. |
| `2024-dp-vla.pdf` | [DP-VLA: A Dual Process VLA](https://arxiv.org/abs/2410.15549), 2024 | — | The same split: large model at low frequency, small fast executor. |
| `2025-robocerebra.pdf` | [RoboCerebra: Long-Horizon Robotic Manipulation Evaluation](https://arxiv.org/abs/2506.06677), 2025 | [buaa-colalab/RoboCerebra](https://github.com/buaa-colalab/RoboCerebra) | The VLM plans subgoals and monitors progress; benchmark for this planner role. |
| `2026-slow-brain-fast-planner.pdf` | [Slow Brain, Fast Planner: Latency-Resilient VLM-Augmented Urban Navigation](https://arxiv.org/abs/2606.20458), 2026 | — | A VLM with 1–3 s latency cannot drive a 5–20 Hz loop directly. Asynchronous fusion keeps >80% success with delays up to 5 s. Supports the onboard fast loop. |
