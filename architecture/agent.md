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
- It has no authority of its own: each task receives delegated rights, which are logged and can be cancelled.
- No agent task combines private data, untrusted content and external communication. This rule targets the agent's tasks (**Decided**, 14 November 2026); it takes up the "lethal trifecta" (Willison) and the "rule of two" (Meta), which are to be cited.
- Reading the accessibility tree of another application is a capability; it also serves the agent as a fallback for web sites, which export no actions (see [ui.md](ui.md#accessibility)).

## Security model

**Decided, 14 November 2026.** The points below are to be written in the page of the security model, before `core.wit` is frozen.

### Effect class

The **effect class** of an action says what the action can change. It has two fields:

| Field | Values |
|---|---|
| Modification | none, reversible, irreversible |
| Scope | local, external |

- The actions and their classes are in the signed manifest; they are not returned by a function.
- Each action runs in a fresh instance, which receives only the capabilities of its class. With this, the class declared by an application fixes the capabilities handed over for the call, so lying about the class gains nothing. The mapping described earlier, in the terms of the former single-field class, was: a read action receives only read capabilities and no network; a reversible action receives only versioned storage; only an external action receives the network.

### Provenance marks

Provenance follows the data. A task carries two marks: "has read private data" and "has read untrusted content".

- The output of an action is untrusted by default for any third-party application. Only the system and the user's own data are trusted; a publisher does not declare itself trusted.
- A secret field never emits its value to the agent; the value goes to the action directly.

### Confirmation matrix

| Action | Task without the "untrusted" mark | Task marked "untrusted" |
|---|---|---|
| Local read | Automatic | Automatic |
| Local reversible modification | Automatic, can be undone | Automatic, can be undone |
| Local irreversible modification | Confirmation | Confirmation, provenance displayed |
| External read | Automatic | Automatic without the "private" mark, confirmation otherwise |
| External modification | Confirmation | Confirmation, provenance and exact content displayed |

- The confirmation screen is drawn by the system from the typed schema of the action, never from the text of the model. It is drawn above the surface concerned (see [ui.md](ui.md#agent-surface)).
- A suite of injection attacks becomes a gate of the hosted track (see [roadmap](../plan/roadmap.md#calendar)).
- Labels per value rather than per task (FIDES, RTBAS, IsolateGPT): to read, after version 1.

### Known weaknesses

From the delegated prior-art study of 14 November 2026 (not cross-checked). To address:

- Everything quickly becomes "untrusted" and the user confirms everything.
- A label does not follow the influence of content on the model's decision.
- An application can lie about the effect class of its actions (addressed by the fresh instance per action, above).
- An external effect cannot be undone.
- A copied budget becomes a shared counter.

## Memory

The agent's memory is made of store objects that belong to the user, with provenance (**Aligned**). It sits in the user zone (see [storage.md](storage.md#zones)). Across devices it is an append-only log merged by union (see [devices.md](devices.md#what-it-gives)).

## Voice

- The wake-word detector is a component that has only the microphone as input and a signal as output, with no network and no storage.
- Echo cancellation by the audio module of WebRTC, so that the agent can be interrupted while it speaks.
- The agent is called by a key or by the wake word (see [ui.md](ui.md#agent-surface)).
- Wake word during sleep: see [platform.md](platform.md#power-and-sleep).
- The agent's voice dictation goes through the text input protocol, and its speech synthesis is used by the screen reader (see [ui.md](ui.md#input)).

## Related

- Scheduling class of inference: [scheduling.md](scheduling.md#classes).
- GPU sharing between frames and inference: [gpu.md](gpu.md#gpu-scheduling).
- Latency targets (visual acknowledgement, first sound): [plan/gates.md](../plan/gates.md#latency-gates).
- Prior art on agents and provenance: [research/prior-art.md](../research/prior-art.md).
- The crash "black box" that the agent can explain: [platform.md](platform.md#crash-and-shutdown).
