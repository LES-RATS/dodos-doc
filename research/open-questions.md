# Open questions

Statuses are defined in the [README](../README.md#status-legend).

This file has four parts: an index of the open points that are detailed in the topic files, the open items of the contract files, the conflicts recorded between current statements, and the project-level questions, which are detailed here.

## Open points by area

Each line points to the file that holds the detail.

| Area | Open point | Detailed in |
|---|---|---|
| Kernel | Hard points of one kernel per core; nothing measured on its gain for P and E cores | [kernel.md](../architecture/kernel.md#hard-points) |
| Kernel | Does the reference processor have FRED | [kernel.md](../architecture/kernel.md#hardware-features) |
| Kernel | Formal proof of the kernel | [verification.md](../plan/verification.md#formal-proof) |
| Kernel | Research axes, none designed yet | [prior-art.md](prior-art.md#kernel-research-axes) |
| Scheduling | Starting values to calibrate; gates to set | [scheduling.md](../architecture/scheduling.md#classes), [gates.md](../plan/gates.md#overhead-gates) |
| Storage | Five open points with proposed answers (several disks, quotas, version retention, swap, visibility of packages) | [storage.md](../architecture/storage.md#open-points-and-proposed-answers) |
| Storage | Distribution through a standard container registry | [storage.md](../architecture/storage.md#packages-and-distribution) |
| Drivers | Licence of the emulation library, to be confirmed by legal counsel | [drivers.md](../architecture/drivers.md#licence) |
| GPU | Performance of NVK on the reference card; channel priorities; eviction of video memory | [gpu.md](../architecture/gpu.md) |
| GPU | Upscaling and frame generation at system level | [gpu.md](../architecture/gpu.md#upscaling-and-frame-generation-at-system-level) |
| Network | Network stack: own extraction of Netstack3, gap with upstream | [network.md](../architecture/network.md#network-stack) |
| Network | Bluetooth host stack: read Sapphire and the Fuchsia profiles | [network.md](../architecture/network.md#bluetooth) |
| Devices | What other platforms open up; AirPlay, Cast, Miracast, Matter | [devices.md](../architecture/devices.md#to-study) |
| Security | Executable code for the web content process (JIT of LibJS) | [web.md](../architecture/web.md#jit-in-the-web-content-process) |
| Security | Disk key, secure boot, accounts, signing keys: proposals to validate | [security.md](../architecture/security.md) |
| Agent | Known weaknesses of the provenance model; labels per value | [security.md](../architecture/security.md#known-weaknesses) |
| Security and agent | Threat model and agent security model, to validate: fourteen points for the two owners (class of external actions, wording of D-036, the model and remote providers, marks across nodes, speech, scope of a task) | [security.md](../architecture/security.md#points-for-the-two-owners) |
| UI | Shell trial in weeks 1-2, validating gpui; gpui window back end | [ui.md](../architecture/ui.md#shell) |
| UI | Accessibility tree format | [ui.md](../architecture/ui.md#accessibility) |
| UI | Ladybird text composition on the project's input protocol | [ui.md](../architecture/ui.md#input) |
| UI | Message format (Fluent or MessageFormat 2) | [ui.md](../architecture/ui.md#localisation) |
| Media | Hardware video decoding; protected video; patents | [media.md](../architecture/media.md) |
| Wasm | Optimised compilation tier | [wasm-abi.md](../architecture/wasm-abi.md#optimised-tier) |
| Wasm | Cost of async between components | [wasm-abi.md](../architecture/wasm-abi.md#cost-of-async) |
| Wasm | Threads | [wasm-abi.md](../architecture/wasm-abi.md#threads) |
| Wasm | Contract: open items of the files, and the missing package manifest contract | [Open items in the contract files](#open-items-in-the-contract-files) |
| Wasm | Shell to port, after the withdrawal of Nushell | [wasm-abi.md](../architecture/wasm-abi.md#terminal-and-shell) |
| Platform | Wake word during sleep | [platform.md](../architecture/platform.md#power-and-sleep) |
| Plan | Calendar hypothesis, to recompute after week 2 | [roadmap.md](../plan/roadmap.md#calendar) |
| Plan | The "Checks per stage" list awaits a review | [verification.md](../plan/verification.md#checks-per-stage) |
| Plan | Realism of the latency and overhead gates | [gates.md](../plan/gates.md) |
| Research | Facts still from memory or not cross-checked | [verification-status.md](verification-status.md) |

## Open items in the contract files

The contract files in `contracts/` mark their unsettled points with `// OPEN:`. The detail is in each file.

| File | Open items |
|---|---|
| [core.wit](../contracts/README.md) | Every size cap is a provisional number. Textual form of the publisher key. The WASI 0.3 imports are not listed in the worlds yet. Background wake-up by the notification service has no interface. The three other ways to draw, and text input, have no interface. Objects handed to the agent with a request have no path |
| [store.wit](../contracts/README.md) | No purge offered to components. Width and alphabet of the object identifier. Which versions stay readable (retention policy). The query filter has no "or", no negation, no full-text or semantic search. Pasted text travels as an object, with no by-value shortcut |
| [actions.wit](../contracts/README.md) | Schema language of actions (JSON Schema 2020-12 assumed) and how a schema marks a storage item. The WIT breaking-change check does not see a schema change. Marks between a task and its sub-task. The interfaces `inference`, `memory` and `audio` are stubs |
| [catalog.wit](../contracts/README.md) | The list of semantic icon names is a starting set. The fields of the application-level kinds are a minimum. How one draws into `canvas` |
| [ui.wit](../contracts/README.md) | None |

**The package manifest format is a contract that does not exist yet.** It has to fix the declaration of actions (name, description, schemas, effect class), the textual form of the publisher key, the capabilities a package requests, and the check that sees a breaking change of an action schema.

## Recorded conflicts

Two current statements conflict and the source does not settle the conflict: such a pair is kept in the topic files and listed here.

No conflict is recorded at present. The seven conflicts recorded on 14 November 2026 were settled the same day; the resolutions are in the topic files and in the [decision log](../decisions/README.md) (D-080 to D-086).

## Project-level questions

From the block "Project" of the proposed answers of 14 November 2026 (decisions of the user and recommendations, to validate), unless marked.

### Who buys

**Open; to settle.** Candidates:

1. A commercial licence for device makers and integrators who do not want the AGPL.
2. Support and licence on the server side.
3. Optional services (relay, backup, store).
4. A reference machine.

### Name

Verified 14 November 2026: the name `dodos` is taken on GitHub by a user account, so another organisation name is needed; `dodos.org` (2010) and `dodos.io` (2021) are taken; `dod-os.org` is free. The trademark is not verified.

Repository: `github.com/Vehicoule/dodOS` (public, created on 13 November 2026, empty). Organisation name: later.

### Licence and legal counsel

The licence itself is decided (see [thesis.md](../thesis.md#licence)). Points for legal counsel:

- Confirmation of the licence of the Linux emulation library and of the driver process (see [drivers.md](../architecture/drivers.md#licence)).
- Contribution agreement. A contributor agreement is necessary for the dual licence (**Open**). Proposed: a contribution licence with the right to relicense, rather than an assignment. The text, and the status of code written by agents, go to legal counsel.
- A legal opinion before a commercial version, on the reading of other kernels' code (see [verification.md](../plan/verification.md#reading-the-code-of-other-kernels)).
- Patents on H.264 and AAC (see [media.md](../architecture/media.md#codecs)).

### Telemetry

**Proposed.** None by default; a crash report leaves on agreement, report by report.

### Recorded elsewhere

- First public demonstration and calendar: [roadmap.md](../plan/roadmap.md).
- Cost of agents: [verification.md](../plan/verification.md#cost-of-agents).
- Publications: [roadmap.md](../plan/roadmap.md#publications).
