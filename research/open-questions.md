# Open questions

Statuses are defined in the [README](../README.md#status-legend).

This file has three parts: an index of the open points that are detailed in the topic files, the conflicts recorded between current statements, and the project-level questions, which are detailed here.

## Open points by area

Each line points to the file that holds the detail.

| Area | Open point | Detailed in |
|---|---|---|
| Kernel | Hard points of one kernel per core; nothing measured on its gain for P and E cores | [kernel.md](../architecture/kernel.md#hard-points) |
| Kernel | Does the reference processor have FRED | [kernel.md](../architecture/kernel.md#hardware-features) |
| Kernel | Formal proof of the kernel | [verification.md](../plan/verification.md#formal-proof) |
| Kernel | Research axes, none designed yet | [prior-art.md](prior-art.md#kernel-research-axes) |
| Scheduling | Starting values to calibrate; gates to set | [scheduling.md](../architecture/scheduling.md#classes), [gates.md](../plan/gates.md#overhead-gates) |
| Storage | Six open points with proposed answers (heavily modified objects, several disks, quotas, version retention, swap, visibility of packages) | [storage.md](../architecture/storage.md#open-points-and-proposed-answers) |
| Storage | Distribution through a standard container registry | [storage.md](../architecture/storage.md#packages-and-distribution) |
| Drivers | Licence of the emulation library, to be confirmed by legal counsel | [drivers.md](../architecture/drivers.md#licence) |
| GPU | Performance of NVK on the reference card; channel priorities; eviction of video memory | [gpu.md](../architecture/gpu.md) |
| GPU | Upscaling and frame generation at system level | [gpu.md](../architecture/gpu.md#upscaling-and-frame-generation-at-system-level) |
| Network | Network stack: own extraction of Netstack3, gap with upstream | [network.md](../architecture/network.md#network-stack) |
| Network | Bluetooth host stack: read Sapphire and the Fuchsia profiles | [network.md](../architecture/network.md#bluetooth) |
| Devices | What other platforms open up; AirPlay, Cast, Miracast, Matter | [devices.md](../architecture/devices.md#to-study) |
| Security | Executable code for the web content process (JIT of LibJS) | [web.md](../architecture/web.md#jit-in-the-web-content-process) |
| Security | Disk key, secure boot, accounts, signing keys: proposals to validate | [security.md](../architecture/security.md) |
| Agent | Known weaknesses of the provenance model; labels per value | [agent.md](../architecture/agent.md#known-weaknesses) |
| UI | Shell trial: gpui, then Rune and LibWeb; gpui window back end | [ui.md](../architecture/ui.md#shell) |
| UI | Accessibility tree format | [ui.md](../architecture/ui.md#accessibility) |
| UI | Ladybird text composition on the project's input protocol | [ui.md](../architecture/ui.md#input) |
| UI | Message format (Fluent or MessageFormat 2) | [ui.md](../architecture/ui.md#localisation) |
| Media | Hardware video decoding; protected video; patents | [media.md](../architecture/media.md) |
| Wasm | Optimised compilation tier | [wasm-abi.md](../architecture/wasm-abi.md#optimised-tier) |
| Wasm | Cost of async between components | [wasm-abi.md](../architecture/wasm-abi.md#cost-of-async) |
| Wasm | Threads | [wasm-abi.md](../architecture/wasm-abi.md#threads) |
| Wasm | `core.wit`: remaining open points | [wasm-abi.md](../architecture/wasm-abi.md#corewit) |
| Wasm | Shell to port, after the withdrawal of Nushell | [wasm-abi.md](../architecture/wasm-abi.md#terminal-and-shell) |
| Platform | Wake word during sleep | [platform.md](../architecture/platform.md#power-and-sleep) |
| Plan | Calendar hypothesis, to recompute after week 2 | [roadmap.md](../plan/roadmap.md#calendar) |
| Plan | The "Checks per stage" list awaits a review | [verification.md](../plan/verification.md#checks-per-stage) |
| Plan | Realism of the latency and overhead gates | [gates.md](../plan/gates.md) |
| Research | Facts still from memory or not cross-checked | [verification-status.md](verification-status.md) |

## Recorded conflicts

Two current statements conflict and the source does not settle the conflict. Both are kept.

| # | Statement A | Statement B | Where |
|---|---|---|---|
| 1 | Boot lever: the shell is rendered from its snapshot | Version 1 (Decided, 14 November 2026): an automatic snapshot exists only for an idle Wasm component, and none for native code | [platform.md](../architecture/platform.md#boot) |
| 2 | Requested shutdown (Proposed): "last snapshot, root switch, power off" | Decided, 14 November 2026: recovery no longer assumes snapshots, and "root switch" designates only the change of system slot. No new shutdown sequence is written | [platform.md](../architecture/platform.md#crash-and-shutdown) |
| 3 | Storage (Proposed): a second object type, modifiable by extents, copy-on-write, with a checksum per block, whose versions are snapshots, and where the SQLite databases of applications live | Storage (Decided, 14 November 2026): application databases live on simple extent files, allocated in large chunks. Whether the rest of the proposed object type stands is not said | [storage.md](../architecture/storage.md#open-points-and-proposed-answers) |
| 4 | Shell (Aligned, trial to do): gpui, with Rune as fallback and LibWeb compared in the same trial | Catalogue (Decided, 14 November 2026): two rendering engines in version 1, gpui in the shell and CSS in LibWeb | [ui.md](../architecture/ui.md#shell) |
| 5 | Task cycle: a human writes the brief and writes or validates the tests of every task, and a human merges; proposed merge rule: function lane, one human | Human capacity (Decided, 14 November 2026): humans re-read the contracts and tests of the contract lane; the function lane is reviewed by agents of another family, and a sample by a human | [verification.md](../plan/verification.md#development-workflow) |
| 6 | Decision records are numbered in `docs/decisions/` of each repository | Decision records live in the common documentation repository, because decisions cross repositories (Proposed, 14 November 2026). The documentation keeps a decision log (Decided, 14 November 2026) | [verification.md](../plan/verification.md#development-workflow) |
| 7 | Research axis 2 (Proposed): a multikernel with replicated process state, verified | Multi-core structure (Decided, 14 November 2026): no shared state, messages only; the replicated log is only a comparison point | [prior-art.md](prior-art.md#kernel-research-axes) |

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
