# Roadmap

Statuses are defined in the [README](../README.md#status-legend).

## Method

The team is two people and AI agents. Two tracks run in parallel:

- **Kernel track**: the kernel is written from its model and verified as described in [verification.md](verification.md#kernel-verification).
- **Hosted userland track**: the WIT worlds are implemented on Linux and macOS. This "hosted userland" is both the SDK and the way to develop the compositor, storage and the agent without waiting for the kernel.

## Build order

**Proposed**; the kernel track below was revised and **Decided** on 14 November 2026.

### Step 0

Before the first line of code: a template repository (Nix environment, `verify` command, `AGENTS.md`, GitHub Actions workflow, merge queue, `CODEOWNERS`) and the integration repository. Every new repository starts from the template, so it is born with its CI. This base is not enough: each step below brings its own checks (see [checks per stage](verification.md#checks-per-stage)).

Step 0 also holds the complete revision of `core.wit`, as its first contract (see [wasm-abi.md](../architecture/wasm-abi.md#corewit)), and the one-page threat model (see [security.md](../architecture/security.md#threat-model-outline)).

### Hosted track

On Linux and macOS:

1. Hosted runtime and `dodo` tool: a component reads and writes in storage.
2. Surface: the project's compositor in a hosted version, and a component that displays a catalogue interface through gpui.
3. Actions and agent: llama.cpp, A2UI, delegation, confirmations.
4. Shell.
5. Real blob store on a disk image, signed packages.

### Kernel track

On QEMU, then on the reference desktop:

0. The [kernel interface](../architecture/kernel-interface.md) (objects and system calls), written before any kernel code. Then debugging before features: serial console, debugger stub, trace buffer, crash record; a small native shell and tools as soon as a first process runs. The kernel boots on the reference desktop from the first week, not only on QEMU (**Decided**, 14 November 2026).
1. Platform bring-up (UEFI, ACPI, PCI, interrupts, timers, start of the other cores), capabilities, IPC, model and oracle on one core.
2. Nodes of one core first, talking by the reduced set of D-128 (grants of frames, stamped sends, signals, roles, recovery), then nodes of several cores (D-128: a multithreaded process lives in one node), under one node lock (D-138: a lock per object only if the measure on the reference desktop asks for it); recovery of a node, scheduling, memory, mlibc and the Rust standard library, first native service, virtio.
3. IOMMU, native NVMe driver, keyboard, network stack, Linux emulation for the network card, server image.
4. NVIDIA core, NVK, GPU service, USB, audio.

The server image is a decided milestone.

### Convergence

Dependencies of Ladybird, compositor on real scanout, latency gates, then sleep, input, accessibility. mlibc and the Rust standard library are in step 2 of the kernel track, and audio in step 4.

## Calendar

**Decided, 14 November 2026.** With a team of agents, the calendar counts in weeks. Week 1 is the week of 16 November 2026.

| Weeks | Hosted track | Kernel track | Milestone |
|---|---|---|---|
| 1-2 | Step 0, security model, runtime, `dodo`; shell trial that validates gpui (see [ui.md](../architecture/ui.md#shell)) | Trials: Zig and Rust boundary, kernel with no per-thread stack, oracle harness, NVIDIA core outside Linux; boot under QEMU | Base ready |
| 3-7 | Surface, actions, agent, confirmations, injection attacks | Contracts and one-core model; capabilities, IPC, basic memory | First public demonstration; IPC measured |
| 8-17 | Shell, real store, signed packages, hosted network stack | Nodes between them (grants, sends, signals), nodes of several cores, recovery of a node, scheduling, mlibc, Rust std, virtio | A `wasi:http` component served under QEMU; one node killed, the machine continues |
| 18-26 | Services ported to the target | Real desktop: ACPI, PCI, IOMMU, NVMe, keyboard, network card | Server image on the desktop |
| 27-36 | Dependencies of Ladybird | NVIDIA core, NVK, GPU service, USB, audio | Vulkan triangle, real compositor |
| 37-48 | Ladybird, latency gates | Hardening | Alpha (end of 2027) |
| 2028 | Laptops, companion application, device-to-device communication | | Beta |

This is a hypothesis, to recompute after week 2.

What bounds the pace: about thirty contracts to be re-read by two people, and a single target machine.

What does not compress with more agents: tuning on real hardware, calibration of the gates on the machine, review of the contract lane by two humans, what depends on upstream (Wasm threads, NVK), and the time of daily use before saying "beta".

## First public demonstration

**Proposed.** The agent acting safely on applications in the hosted userland (steps 1 to 3 of the hosted track), and the kernel booting under QEMU and passing the oracle.

## Applications of the alpha

**Decided, 14 November 2026.** Browser, terminal, object explorer, settings, text editor, agent.

## Deferred after the alpha

**Decided, 14 November 2026.**

- Periodic snapshot of all processes ([platform.md](../architecture/platform.md#process-state-suspend-resume-and-snapshots)).
- Optimised Wasm tier and the 1.2 gate ([wasm-abi.md](../architecture/wasm-abi.md#optimised-tier)).
- Device-to-device communication and the companion application ([devices.md](../architecture/devices.md)).
- On-demand frequency, and cores on demand (nodes that take and give cores at run time, an open point of the contract since D-128); in version 1, only per-class preferences, and nodes sized when they start ([scheduling.md](../architecture/scheduling.md#core-load)).
- Image upscaling ([gpu.md](../architecture/gpu.md#upscaling-and-frame-generation-at-system-level)).
- FRED ([kernel.md](../architecture/kernel.md#hardware-features)).
- Wi-Fi (with the laptops) and Bluetooth ([network.md](../architecture/network.md#wi-fi)).
- Camera class driver ([drivers.md](../architecture/drivers.md#native-drivers)).
- 1 GB pages ([memory.md](../architecture/memory.md#page-sizes)).
- Copy-on-write extents, per-block checksums and snapshot-based versions for the mutable extent type ([storage.md](../architecture/storage.md#on-disk-format)).
- Container registry as a distribution transport ([storage.md](../architecture/storage.md#packages-and-distribution)).

Version 1 has two rendering engines ([ui.md](../architecture/ui.md#tokens)).

## Publications

- A position paper (a safe OS for an agent: effect classes, provenance, confirmations) after the first public demonstration (**Decided**, 14 November 2026).
- Then measurement papers once the gates are in place: differential oracle and development by agents; reuse of Linux drivers without a VM; Wasm as the only ABI. The gates supply the figures.
- The position paper is not on virgin ground: AgentKernel (arXiv 2609.29647, September 2026) already proposes provenance labels in an "OS for agents"; read it before writing.
- Architecture paper: the defensible thesis is "the advantage of the monolithic kernel erodes", not "it will disappear".
- Conferences and dates for publications: from memory.
