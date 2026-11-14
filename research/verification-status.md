# Verification status

This file says how far the facts in the documentation were checked. The marks ("verified" with a date, "from memory", "not cross-checked") are defined in the [README](../README.md#verification-marks). The same marks appear next to the facts in the topic files.

## Verified on 13 November 2026

Against primary sources, by five delegated audits and direct checks in the repositories.

| Area | What was verified |
|---|---|
| Ladybird | Process architecture, dependencies, Rust crates, JIT, accessibility, input methods, WebGPU, contribution policy (commit c8b525e) |
| Wasm | WASI 0.3, Wasmtime and its compilers, state of each language, uutils, brush, A2UI 1.0, llama.cpp 1.0 |
| GPU and interface | NVIDIA port of Haiku and its Mesa fork, gpui, gpui-kit, Rune, wgpu, performance of NVK |
| System | Bluetooth stacks, wake word through the signal processor, uACPI, sDDF, DFv2, Netstack3, long-term-support Linux kernels |
| Harness | Articles of GitHub and Microsoft, conventions of `AGENTS.md` and skills, free offers |
| Performance and miscellaneous | libsodium bench of 2026, Segue, Cranelift inliner, weval, SpaceWasm, IPC figures of seL4, ANR (figures of the publisher only), Vulkan Video in NVK, Wi-Fi stack of Fuchsia, distribution by `wkg`, drivers in VMs of LionsOS |

## Verified on 14 November 2026

By web search (abstracts and official pages; papers not read in full): the multikernel of seL4 and the date of its proof, NrOS, Barrelfish/DC, Popcorn Linux, the finding of HongMeng, LionsOS (figures of the authors), the Intel patent on super cores, the calendar of WASI threads, the existence of AgentKernel and ActPlane.

Also on 14 November 2026:

- Comparison of the storage layout with Fuchsia: official documentation.
- Prior art on the recovery of a kernel: web search, abstracts only.
- AV2, Widevine and EME: web search; community sources for EME.
- Name availability (GitHub, domains): verified; trademark not verified.
- Absence of a seL4 boot bench: searched on the web, not in the sel4bench repository.
- RFC-14 of seL4 (budget thresholds): read through a search summary; merge state not verified.

## Not cross-checked

Two studies were delegated to DeepSeek on 14 November 2026 and were not cross-checked by the project:

- Prior art of the kernel research axes: sources read in full for the works of 2026, abstracts only for older ones. See [prior-art.md](prior-art.md#novelty-claims-and-verdicts).
- Leads from recent research: figures to re-read in the papers. See [prior-art.md](prior-art.md#leads-from-recent-research).

Other figures that come from their authors or publisher only: ANR (publisher's figures, not verified by a third party), LionsOS (authors' figures).

## Still from memory

To verify before relying on them.

- Detail of the borrowings from recent microkernels (HongMeng, sDDF, seL4 MCS, Asterinas): papers to read in full.
- Real gain of the per-core kernel for P and E cores, and compared cost of the replicated log and of the kernel per core group: nothing measured.
- Conferences and dates for publications.
- Feasibility of the Zig and Rust boundary, and of the event-driven kernel with no per-thread stack.
- SQLite with a custom VFS in WAL mode.
- Rust standard library plugged onto mlibc (supposed precedent: Managarm).
- WASI 0.1 adapter for Zig and Swift, and the state of Odin.
- Current state of Genode DDE Linux, the Wi-Fi stack of FreeBSD, the exact role of Nova.
- Borrowings from Plan 9, Genode, Horizon, SepOS and Minix 3: design inspirations, not re-read.
- Realism of the latency and overhead gates: targets to calibrate by measurement.
- Hardware planes and channel priority exposed by the NVIDIA core without its Linux layer.
- TPM and secure boot: known mechanisms, not re-read. A loader signed by Microsoft for a non-Linux OS: not verified.
- WIT variants: an added case breaks compatibility.
- Hardware video decoding in Ladybird: state unknown.
- Kernel shipped by Debian 14: inconsistent release notes.
- Scheduler activations, crash-only software, Wi-Fi Aware on iOS, Quick Share and AirDrop, GPU firmware: from memory.

Further "from memory" marks placed next to individual facts: the model of seL4 MCS and of seL4 memory, HWP, Intel Thread Director, layer offload in llama.cpp, the Vulkan memory budget extension, memory and boot cost of a micro-VM, LVFS, SIMD and tail calls in Wasm, Perfetto as a trace format.

## What the review could not confirm

The [design review of 14 November 2026](../reviews/2026-11-14-design-review.md) checked about forty facts of the direction document and reports, in its finding 18, what it found false, misleading or not confirmed. The points below are the review's, not re-verified since.

Acted on in the decisions of 14 November 2026:

- The announcement of Linux 7.3 as the 2026 long-term-support kernel is not confirmed (see [drivers.md](../architecture/drivers.md#linux-version)).
- The Barrelfish/DC removal-time figure is withdrawn until the paper is read (see [prior-art.md](prior-art.md#multi-core-structure-precedents)).
- "Deterministic cycle counts under QEMU" is replaced by instruction counts; the reference desktop is not a runner (see [verification.md](../plan/verification.md)).
- The defence against a lie on the effect class holds only with a fresh instance per action (see [agent.md](../architecture/agent.md#effect-class)).

Not confirmed by the review, and still stated in the documentation:

- sDDF: "1 Gb/s saturated at 65 % of one core, where Linux tops out at 500 Mb/s" ([drivers.md](../architecture/drivers.md#driver-framework)).
- NVK at "less than half" of the proprietary driver on RTX 5080: the direction is confirmed, the figure is not ([gpu.md](../architecture/gpu.md#nvidia-port)).
- Atmosphere: 6,000 lines, 2.5 person-years and a global lock ([verification.md](../plan/verification.md#formal-proof)).
- seL4 "discourages IPC between cores" in its multikernel ([kernel.md](../architecture/kernel.md#hard-points)).
- A2UI: version 1.0 exists; the "Express format" was not verified ([ui.md](../architecture/ui.md#agent-interface-format)).

The review also lists what it confirmed against primary sources, and its own sources.
