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

## The agent in the contract

The `agent` world ([contracts/core.wit](../contracts/README.md)) exports one function, `handle`, called once per user request with the user's words, a `task` and an `overlay` surface.

- The **task** is the unit of delegation ([contracts/actions.wit](../contracts/README.md)). It carries the delegated rights, the marks and the journal, and is revocable as a whole. Everything the agent can do comes from it, and nothing survives it. In the kernel, the mechanism is a `task` object that carries the marks and stops the task's threads in one operation; the delegated rights are capabilities that the supervisor then removes (D-110, proposed; see [Tasks and marks](kernel-interface.md#tasks-and-marks)).
- Through the task the agent reads its marks, lists the actions of its scope (`available`), invokes one (`invoke`), undoes one journal entry (`undo`), reads the journal, and creates a sub-task with a subset of the scope.
- The world imports `inference`, `memory` and `audio`. These three interfaces are stubs in the contract: nothing is fixed yet.

## Security model

**Decided, 14 November 2026.** The points below are to be written in the page of the security model, before `core.wit` is frozen.

### Effect class

The **effect class** of an action says what the action can change. It has two fields:

| Field | Name in the contract | Values |
|---|---|---|
| Modification | `change` | `none`, `reversible`, `irreversible` |
| Scope | `reach` | `local`, `external` |

- The actions and their classes are in the signed package manifest: for each action, its name, description, input schema, output schema and effect class. There is no `list-actions` function: a function could change its answer after installation, and the component would have to run to be asked. The system reads the manifest and serves it to the agent as `action-info`.
- Each action runs in a fresh instance, on which the system calls only `actions.invoke`. The instance shares no memory with the running application and is destroyed afterwards. It holds only what the request carries (input, bound objects, the `home` collection), attenuated to the class.
- The imports of an action instance are linked to match its class: storage is read-only when `change` is `none`, and every network import answers `denied` when `reach` is `local`. The declared class is therefore binding, and lying about it gains nothing. Every write to the store is versioned, which is why a store capability is safe to hand to an action whose change is `reversible`.
- The contract is in [contracts/actions.wit](../contracts/README.md) and [contracts/core.wit](../contracts/README.md).

### Provenance marks

Provenance follows the data. A task carries two marks: "has read private data" and "has read untrusted content".

- In the contract the marks are the flags `private` and `untrusted`, and a provenance is an origin (`system`, `user`, `app:<component>`, `web:<origin>`) plus marks. Provenance is set by the system only, never by the producer. Marks are only ever added; reading data adds its marks to the reading task.
- The output of an action is untrusted by default for any third-party application. Only the system and the user's own data are trusted; a publisher does not declare itself trusted.
- A secret field never emits its value to the agent; the value goes to the action directly, read by the system when the button is activated.

### Confirmation matrix

| Action | Task without the "untrusted" mark | Task marked "untrusted" |
|---|---|---|
| Local read | Automatic | Automatic |
| Local reversible modification | Automatic, can be undone | Automatic, can be undone |
| Local irreversible modification | Confirmation | Confirmation, provenance displayed |
| External read | Automatic | Automatic without the "private" mark, confirmation otherwise |
| External modification | Confirmation | Confirmation, provenance and exact content displayed |

- The confirmation screen is drawn by the system from the typed schema of the action and the exact input, never from the text of the model. The agent cannot draw, skip or answer it; a refusal by the user is the error `refused`. It is drawn above the surface concerned (see [ui.md](ui.md#agent-surface)).
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
