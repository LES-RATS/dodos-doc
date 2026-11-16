# The agent

Statuses are defined in the [README](../README.md#status-legend).

The agent is the AI assistant built into the system. It acts for the user through **actions**: typed operations that every application exports. Prompt injection (hostile instructions hidden in content the agent reads) is contained by the system, not by the model.

## Base positions

| Topic | Position | Status |
|---|---|---|
| Agent | Voice detection is always active; the rest runs on demand. Models are interchangeable, local or cloud. Local inference by llama.cpp (1.0 stable since 13 November 2026), Vulkan back end | Aligned |
| Agent memory | Objects of the store that belong to the user, with provenance | Aligned |

## How the agent acts

- It acts through the typed actions that each application exports, never by clicking on pixels. System services (settings, windows, network, installation, power) export the same interface: managing the OS is not a separate API.
- It has three outputs: actions, a declarative 2D interface, and applets (3D and free cases). Applets are objects of the store, reused and fed with data rather than regenerated. The interface format is in [ui.md](ui.md#agent-interface-format).
- It has no authority of its own, and no task combines private data, untrusted content and external communication: see [Security model](#security-model).
- Reading the accessibility tree of another application is a capability; it also serves the agent as a fallback for web sites, which export no actions (see [ui.md](ui.md#accessibility)).

## The agent in the contract

The `agent` world ([contracts/core.wit](../contracts/README.md)) exports one function, `handle`, called once per user request with the user's words, a `task` and an `overlay` surface.

- The **task** is the unit of delegation ([contracts/actions.wit](../contracts/README.md)). It carries the delegated rights, the marks and the journal, and is revocable as a whole. Everything the agent can do comes from it, and nothing survives it. In the kernel, the mechanism is a `task` object that carries the marks and stops the task's threads in one operation; the delegated rights are capabilities that the supervisor then removes (D-110, proposed; see [Tasks and marks](kernel-interface.md#tasks-and-marks)).
- Through the task the agent reads its marks, lists the actions of its scope (`available`), invokes one (`invoke`), undoes one journal entry (`undo`), reads the journal, and creates a sub-task with a subset of the scope.
- The world imports `inference`, `memory` and `audio`. These three interfaces are stubs in the contract: nothing is fixed yet.

## Security model

The security model of the agent (delegation by task, effect classes, provenance marks, the confirmation matrix, the rule against combining the three risks, what the system draws, the agent's entity, speech, and the known weaknesses with their rules) is one page of [security.md](security.md#security-model-of-the-agent), written on 16 November 2026 as the decision of 14 November 2026 asked (D-035, D-036). It is not repeated here.

<a id="effect-class"></a>
<a id="known-weaknesses"></a>

- Effect class: [security.md](security.md#effect-class).
- Known weaknesses: [security.md](security.md#known-weaknesses).

## Memory

The agent's memory is made of store objects that belong to the user, with provenance (**Aligned**). It sits in the user zone (see [storage.md](storage.md#zones)). Across devices it is an append-only log merged by union (see [devices.md](devices.md#what-it-gives)).

## Voice

- The wake-word detector is a component that has only the microphone as input and a signal as output, with no network and no storage.
- Echo cancellation by the audio module of WebRTC, so that the agent can be interrupted while it speaks.
- The agent is called by a key or by the wake word (see [ui.md](ui.md#agent-surface)).
- Wake word during sleep: see [platform.md](platform.md#power-and-sleep).
- The agent's voice dictation goes through the text input protocol, and its speech synthesis is used by the screen reader (see [ui.md](ui.md#input)).
- The security rules of speech (the always-on detector, the origin of a spoken request, the machine's own sound, synthesis reading a window) are in [security.md](security.md#speech).

## Related

- Scheduling class of inference: [scheduling.md](scheduling.md#classes).
- GPU sharing between frames and inference: [gpu.md](gpu.md#gpu-scheduling).
- Latency targets (visual acknowledgement, first sound): [plan/gates.md](../plan/gates.md#latency-gates).
- Prior art on agents and provenance: [research/prior-art.md](../research/prior-art.md).
- The crash "black box" that the agent can explain: [platform.md](platform.md#crash-and-shutdown).
