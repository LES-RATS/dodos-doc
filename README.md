# DodOS documentation

DodOS is an operating system that is still being designed. Its direction, in four points:

- a capability microkernel (a small kernel in which every right is an explicit, revocable token called a capability), with one kernel instance per processor core;
- WebAssembly (Wasm) components as the only application binary interface (ABI);
- system services and drivers in user space, behind stable typed interfaces;
- an AI agent that acts for the user safely, through typed actions that applications export.

State of the documentation: 14 November 2026. The content comes from a brainstorming process. Only statements marked **Decided** are firm.

## Map

| File | Content |
|---|---|
| [thesis.md](thesis.md) | Thesis, principles, scope, licence, what is out of scope |
| [architecture/overview.md](architecture/overview.md) | Layer diagram and how the pieces fit |
| [architecture/kernel.md](architecture/kernel.md) | Kernel structure, multi-core by messages, capabilities and revocation, recovery of one core's kernel |
| [architecture/kernel-interface.md](architecture/kernel-interface.md) | Kernel objects, system calls, synchronous and asynchronous paths, data plane, pager, tasks, debugging, language split |
| [architecture/scheduling.md](architecture/scheduling.md) | Scheduling contexts, classes, placement service, background execution |
| [architecture/memory.md](architecture/memory.md) | Memory objects, paging, accounting, pressure |
| [architecture/storage.md](architecture/storage.md) | On-disk format, zones, packages and distribution, backup, A/B/R updates |
| [architecture/drivers.md](architecture/drivers.md) | Driver framework, Linux driver emulation layer and its licence, IOMMU, native class drivers |
| [architecture/gpu.md](architecture/gpu.md) | WebGPU for applications, NVIDIA port, GPU service, GPU memory |
| [architecture/network.md](architecture/network.md) | Network service, listening capabilities, key-addressed services, Wi-Fi, Bluetooth |
| [architecture/devices.md](architecture/devices.md) | Device-to-device communication |
| [architecture/security.md](architecture/security.md) | Isolation, chain of trust, secure boot, keys, signing, accounts, threat model outline |
| [architecture/agent.md](architecture/agent.md) | The agent, effect classes, provenance marks, confirmation matrix |
| [architecture/ui.md](architecture/ui.md) | Compositor, shell, design system, catalogue, agent surface, input, accessibility, audio |
| [architecture/web.md](architecture/web.md) | Web engine (Ladybird fork), its port, web content and capabilities |
| [architecture/media.md](architecture/media.md) | Codecs, protected video, hardware video decoding, fonts |
| [architecture/wasm-abi.md](architecture/wasm-abi.md) | ABI rules, compile service, how userland builds against the OS, developer journey |
| [architecture/platform.md](architecture/platform.md) | Boot, process state, restart, crash and shutdown, power and sleep, hardware reference, deployment surfaces |
| [plan/roadmap.md](plan/roadmap.md) | Method, build order, calendar, milestones, what is deferred after alpha |
| [plan/gates.md](plan/gates.md) | Latency gates and overhead gates |
| [plan/verification.md](plan/verification.md) | Agent harness, checks per stage, kernel verification, development workflow |
| [decisions/README.md](decisions/README.md) | Decision log: one row per firm decision |
| [research/prior-art.md](research/prior-art.md) | Borrowings, prior art, novelty claims and their verdicts |
| [research/ideas.md](research/ideas.md) | The idea reservoir |
| [research/open-questions.md](research/open-questions.md) | What is still open, open items of the contract files, recorded conflicts, project-level questions |
| [research/verification-status.md](research/verification-status.md) | What was verified and when, what is from memory |
| [reviews/2026-11-14-design-review.md](reviews/2026-11-14-design-review.md) | Independent design review of 14 November 2026 (French, 27 findings, unchanged) |
| [archive/DIRECTION.fr.md](archive/DIRECTION.fr.md) | The original single-file direction document (French, archived, not edited) |
| `contracts/` | The WIT contract, maintained separately: [core.wit](contracts/README.md) (shared types and the worlds `service`, `app`, `agent`), [store.wit](contracts/README.md), [ui.wit](contracts/README.md), [actions.wit](contracts/README.md), [catalog.wit](contracts/README.md). Packages `os:core`, `os:catalog-agent` and `os:catalog-app`, all at 0.1.0. Described in [architecture/wasm-abi.md](architecture/wasm-abi.md#corewit) |

## Status legend

Every statement carries one of four statuses.

| Status | Meaning |
|---|---|
| **Decided** | Firm. Listed in the [decision log](decisions/README.md). |
| **Aligned** | A proposal that was discussed without objection. An agreed direction, not yet firm. |
| **Proposed** | A proposal that still has to be validated. |
| **Open** | Not settled. |

How statuses were carried over from the archived document:

- A statement with no status mark in the source is reproduced with no status. It is not firm.
- The source used a few other words. "Under discussion" is recorded as Proposed. "Retained, with the user's agreement, to be designed" is recorded as Aligned. The idea reservoir ("exploration, nothing decided") is recorded as Open.
- The source section "Decisions after the review (14 November 2026)" states that it settles each point of the review and overrides older lines. Its statements are recorded as Decided, dated 14 November 2026, unless the statement itself carries a reservation, which is then kept. The decision log says, for each row, whether the source marked it "decided" explicitly.

## Verification marks

Facts carry a mark that says how far they were checked.

| Mark | Meaning |
|---|---|
| A date ("verified 13 November 2026") | Checked on that date, against the source named with it |
| "from memory" | Not verified. To check before relying on it |
| "not cross-checked" | Comes from a delegated study that the project did not cross-check |

The full list is in [research/verification-status.md](research/verification-status.md).

## How to change the docs

- One topic per file. A statement lives in one file; other files link to it instead of repeating it.
- Every statement keeps a status and, for facts, a verification mark. Dates are absolute.
- When a position changes, edit the statement in place in its topic file. Do not add a separate "after review" layer. Remove the superseded text.
- When a decision becomes firm, add a row to the [decision log](decisions/README.md) and link it to the file that details it.
- When two current statements conflict and nothing settles the conflict, keep both and list the conflict in [research/open-questions.md](research/open-questions.md).
- Documentation is written in English (Decided, 14 November 2026; see [thesis.md](thesis.md)).
- `archive/` and `reviews/` are records. They are not edited.
- A documentation change follows the maintenance lane of the [development workflow](plan/verification.md#development-workflow). A change to a contract (kernel, `os:core`, package format, security model) follows the contract lane.
