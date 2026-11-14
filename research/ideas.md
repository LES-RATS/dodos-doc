# Idea reservoir

Status of everything in this file: **Open** (exploration, nothing decided). Statuses are defined in the [README](../README.md#status-legend).

A new OS is the occasion to explore. The ideas are known or not; novelty is verified for none of them. A star (★) marks those proposed for study first. Where an idea has since been partly decided, the line says so and links to the current position.

## Low level and kernel

- ★ **Process snapshot as a primitive.** The state of a Wasm component is explicit (linear memory, tables, handles), so it can be frozen, stored and resumed. It opens exact resumption after a reboot or an update, migration to another device, and rollback. Ancestors: orthogonal persistence of EROS and KeyKOS. Version 1 is reduced; see [platform.md](../architecture/platform.md#process-state-suspend-resume-and-snapshots).
- ★ **Kernel specialised at installation.** The compile service builds the kernel for the exact machine (FRED or IDT, APX, number and type of cores), with no feature test at run time. The system being a hash, each variant stays verifiable.
- **The system call page as an optimiser.** Because no call is made directly, the kernel chooses per machine between an immediate call, execution in user mode and batching in a ring, and can change this at each version.
- **Message rings as the main IPC** for async (the default of the ABI), with a synchronous fast path beside it. Ancestors: FlexSC, io_uring, sDDF.
- **Page tables shared by hash.** The compiled code of a blob is immutable, so its pages and their page-table subtrees are shared between processes.
- **Large pages for Wasm linear memories; zeroing of freed memory by idle efficiency cores.** Current position on page sizes and zeroing: [memory.md](../architecture/memory.md#page-sizes).
- **Deterministic execution.** The imports of a component are recorded, so a task replays identically (audit of the agent, debugging).

## Performance

- ★ **Distributed optimised compilation.** The optimised tier runs at the publisher or on a service, and the machine code arrives signed, indexed by component hash and instruction set. No LLVM on the machine. It requires reproducible compilation. Ancestor: cloud profiles of ART.
- ★ **Launch by snapshot.** The initialisation of a component is run at installation (like Wizer); the launch only maps the result.
- **Caches by hash shared with packages**: compiled GPU pipelines, decoded images, rasterised fonts.
- **Pre-warming by the agent**: it knows the intention, so it prepares the next component before the request.
- **Roles per core type**: the frame path on fast cores; compilation, hashing, indexing and background inference on efficiency cores.
- **NVMe and network queues per core**, mapped into the service that serves them.

## Ecosystem survival, without porting everything from Linux

- ★ **Port the toolkits, not the applications.** Flutter, Qt, Slint, egui, Dioxus, Tauri and SDL targeting `wasi:webgpu` and the project's surface bring their applications at once.
- ★ **Porting factory run by agents.** A nightly chain compiles free applications into Wasm components, their tests serving as oracle, and publishes those that pass.
- ★ **The Linux driver as oracle.** An agent writes a native driver, and its trace (MMIO, DMA, interrupts) is compared with that of the Linux driver under emulation, as seL4 serves as oracle for the kernel.
- **Native class drivers first**: NVMe, AHCI, xHCI, USB classes (HID, audio, storage, camera, network), HDA, Bluetooth HCI, virtio. About fifteen drivers cover most devices. Partly decided; see [drivers.md](../architecture/drivers.md#native-drivers).
- **Peripherals through the web**: WebUSB, WebHID, WebSerial and Web Bluetooth in the project's engine, backed by capabilities; the configuration tools of manufacturers already exist in this form.
- **The hosted userland as a product**: the shell and the agent run on Linux and macOS before the kernel exists, so the ecosystem starts without waiting for the hardware.
- **Remote surface**: a Linux or Windows application running on another machine or in the cloud is displayed as a surface. Local VMs stay out of scope.
- **The agent replaces the long tail**: an applet generated on demand stands in for a small application.
- **Readers of foreign formats and file systems** as Wasm components, to import one's data.
- **A reference machine** sold or recommended, rather than all PCs.

## Experience

- ★ **Nothing closes, nothing is lost.** With the process snapshot, a reboot or an update gives back every surface in its exact state.
- ★ **Global timeline.** Versioned objects and the log of effects give an undo at the scale of the system.
- ★ **"Why" inspector.** Pointing at any pixel says who drew it, what that component can reach and what it did.
- **Grant by gesture.** Choosing a file or dragging it is giving it; no permission dialog. Ancestors: the powerbox of CapDesk and of macOS. Decided in part; see [ui.md](../architecture/ui.md#giving-an-object-to-an-application).
- **Automation by demonstration.** Actions being typed, what the user does is recorded as a replayable script.
- **Notifications with a budget.** Interrupting is a capability, with a quota; the agent sorts the rest.
- **Continuity.** Move a running surface to another device.
- **Shared presence.** The agent and the user act on the same surface; the agent shows what it does.
- **Instant guest session.** Lend the machine with a reduced set of capabilities.
- **Local semantic search** over all objects, with their provenance.

## Additions of 14 November 2026

- **Boot by snapshot.** At each update, the state of the services already started is frozen; booting comes down to mapping that image.
- **Interrupts aligned on the frame.** Devices with no urgency wake a core only at the start of a period.
- **Black box per task** (see [platform.md](../architecture/platform.md#crash-and-shutdown)): it also serves to replay and to explain what the agent did.
- **Interface catalogue per surface template.** The same tree rendered as desktop, phone, television, car, watch or voice only (see [platform.md](../architecture/platform.md#deployment-surfaces)).
