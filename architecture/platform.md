# Platform

Statuses are defined in the [README](../README.md#status-legend). Sections with no status line had none in the source.

This file covers boot, time, process state, restart, crash and shutdown, observability, power and sleep, installation, the reference hardware and the deployment surfaces.

## Platform service

**Decided, 14 November 2026.** The platform service is a trusted process that carries uACPI, PCI enumeration and interrupt routing.

ACPI (the firmware interface that describes and controls the hardware) is handled by uACPI (MIT, version 7.0.0 of October 2026, designed to be embedded; verified 13 November 2026), rather than ACPICA. It is needed in any case to enumerate the hardware.

Platform bring-up (UEFI, ACPI, PCI, interrupts, timers, start of the other cores) is step 1 of the [kernel track](../plan/roadmap.md#kernel-track).

## Boot

- Secure boot and the single signed EFI image are in [security.md](security.md#secure-boot); the boot image and the A/B/R slots are in [storage.md](storage.md#updates).
- Levers for boot time: a single EFI image; services started at the first use of their capability; Wasm code already compiled in the cache; verification of blobs on read; drivers started in parallel.
- The shell starts normally; only an idle Wasm component may be restored from an automatic snapshot (**Decided**, 14 November 2026).
- Probable long point: loading the firmware of the GPU (to measure; from memory).
- Devices are reset at boot, not at shutdown.
- Microcode: a blob of the system, loaded by the kernel at boot (**Proposed**, 14 November 2026).
- The boot and shutdown targets are in [plan/gates.md](../plan/gates.md#boot-and-shutdown).

## Time

**Proposed, 14 November 2026, to validate.** The kernel has only a monotonic clock. Wall-clock time is a service (NTS), and time zones are a blob.

## Process state: suspend, resume and snapshots

**Decided, 14 November 2026.** A **snapshot** is the frozen state of a process, stored so that the process can resume later. Version 1:

1. A component saves its state itself, to its `home` collection, through the exports `suspend` and `resume`. They belong to the `service` world, which the `app` world includes (see [wasm-abi.md](wasm-abi.md#corewit)). `resume` is called instead of `start` on a new instance when `suspend` completed before.
2. An automatic snapshot exists only for an idle Wasm component, after a one-week trial with Wasmtime.
3. There is no snapshot for native code: a service restarts and reloads its state from storage.
4. Memory pressure and crash recovery no longer assume snapshots.

- The periodic snapshot of all processes is deferred until after the alpha.
- Moving a surface between devices goes through `suspend` and `resume`, the only path that crosses two architectures.
- The wider idea of the process snapshot as a primitive is in the [idea reservoir](../research/ideas.md#low-level-and-kernel).

## Restart and hot replacement

Every component of the system restarts or is replaced without rebooting the machine.

- **Driver**: see [drivers.md](drivers.md#restart-of-a-driver).
- **Service**: its durable state lives in storage and in the persistent handle table. Clients receive the error `gone` or reconnect, which rule 1 of the [ABI](wasm-abi.md#abi-rules) already requires them to handle.
- **Kernel**: its own mechanism; see [kernel.md](kernel.md#node-by-node-replacement).
- **Cost**: a pause, not a freeze. The pause is visible when it concerns the system disk or the GPU.

## Crash and shutdown

**Proposed**, with the changes decided on 14 November 2026.

Principle: shutdown and crash follow the same path ("crash-only" software, Candea and Fox 2003, from memory). If the state on disk is consistent at every instant, switching off has nothing to tidy, and crash recovery is tested at every shutdown.

| Event | Handling |
|---|---|
| A component or a service falls | Restart as above. A service reloads its state from storage; an application has the state it saved through `suspend` |
| Power cut | Blobs are immutable and consistency comes from the SQLite journal (see [storage.md](storage.md#on-disk-format)), so there is no disk check at reboot. Modifiable objects are versioned. The periodic snapshot of processes, which would bound the loss to a few seconds of input (interval to set), is deferred until after the alpha |
| Panic of one node's kernel | The node restarts alone and the machine continues (D-128: recovery is of one node, which may cover several cores); see [kernel.md](kernel.md#recovery-of-one-node) |
| Hang | A hardware watchdog (who arms it is open: the kernel contract recommends the platform service, fed by the service manager, since the kernel reads no table that describes it, D-112; see [Open points](kernel-interface.md#open-points)); a heartbeat per service, watched by the service manager; the hang of a node is detected by the other nodes, on evidence ([Detection](kernel-interface.md#detection-evidence-not-opinion)), and a core that stops answering its node makes the node accuse itself (D-129) |
| Reboot loop | A/B/R slots, automatic rollback (see [storage.md](storage.md#updates)) |
| Requested shutdown | Decided, 14 November 2026: the system calls `suspend` on the running applications with a bounded delay (starting value 500 ms, to calibrate), calls `sync` on storage, then powers off. A crash skips the first step; that is the only difference between shutdown and crash. Devices are reset at boot, not at shutdown |

**Black box.** A ring buffer of the last seconds of messages per task, always active, attached to the crash report. The report is stored in the user zone, and reading it marks the reading task with the marks of the messages it holds. The report stays local; the agent can explain it. A report leaves the machine only with the user's agreement, report by report (see [project-level questions](../research/open-questions.md#project-level-questions)).

## Observability

**Decided, 14 November 2026.** A system log, a profiler per capability, and a kernel debugger through the USB debug port. The kernel debugger is a stub of development images, over a stub link that is a serial port or the USB debug port (which link the reference desktop uses is open: [Open points](kernel-interface.md#open-points)); the log service reads the kernel's trace rings through the kept frame of the crash area ([Debugging](kernel-interface.md#debugging-call-reference)).

## Power and sleep

- **Desktop**: no sleep at first. Screen off, processor idle states, frequency managed by the hardware (HWP).
- **Laptop**: modern standby (s2idle), the only one that recent Intel laptops offer. The emulation layer must then replay the suspend callbacks of Linux drivers, in order.
- **Resume after sleep**: a driver that does not wake up is restarted by the [driver restart protocol](drivers.md#restart-of-a-driver). The emulation layer must handle the D3 states.
- **Wake word during sleep: a goal, not yet achieved.** Recent Intel laptops have a low-power signal processor that stays powered during sleep, and the open firmware SOF can run a keyword detector on it that wakes the machine. Obstacle: this firmware must be signed by the manufacturer, so only the existing signed firmware can be loaded, and a model injected into it if it contains the required module. To test on the Dell. Windows removed this function in 24H2 for power consumption reasons. On the desktop there is no such processor: light sleep with a detector on the CPU, or a small USB microphone with a microcontroller that wakes the machine. Verified 13 November 2026.

## Installer and recovery

**Proposed, 14 November 2026, to validate.**

- Installer: the USB image is the system in an ephemeral session; to install is to write the partitions and copy the blobs.
- Dual boot: cohabitation on a dedicated disk or on free space, without resizing the partitions of another system in version 1.
- Recovery slot: a minimal image with network, storage, reinstallation, restore, diagnostics.
- Firmware updates: UEFI capsules; source LVFS (from memory, to verify).

## Printing and scanning

**Proposed, 14 November 2026, to validate.** Driverless protocols (IPP Everywhere, eSCL), as a component, after version 1.

## Hardware reference

1. **Intel + NVIDIA desktop**: first (**Decided**). No battery and no mandatory Wi-Fi. The processor has no integrated GPU: the first pixels come from the firmware framebuffer (UEFI GOP), then from NVIDIA alone. The Intel path is developed on the Dell.
2. **All-Intel Dell laptop**: next, when the emulation layer is mature. It requires the i915 or xe driver and the DRM interface that Mesa expects.
3. **Mac M5**: when Asahi has progressed.

**Machines** (**Decided**, 14 November 2026): two only, the reference desktop and the Dell laptop. The laptop serves as the control machine of the desktop (power, console, image) as long as it is not itself a target. The Mac M5 machines wait for Asahi; the project does no reverse engineering of its own. Hardware trials are therefore in series, and QEMU carries most of the work.

## Deployment surfaces

**Proposed.** Order:

1. Reference desktop.
2. (1 bis) Headless server image: almost free once the kernel has the disk and the network, and the first ground on which to sell the recovery of one node. The server image is a decided milestone (**Decided**, 14 November 2026).
3. Laptops.
4. Companion application on Android, iOS, Linux, macOS and Windows.
5. Phones with an unlockable bootloader.
6. Embedded, the last phase.

This order was not written down before 14 November 2026.

### Server

**Proposed, 14 November 2026, to validate.**

- A server runs `wasi:http` components launched per request; native software through POSIX as a library, later.
- Administration: no remote root shell. The `dodo` tool and the agent go through the key-addressed transport (see [network.md](network.md#key-addressed-services)), with delegated administration capabilities. The configuration of a server is a hash.
- Arguments: recovery of one node, kernel update without reboot, boot in one second.

### Embedded

What embedded imposes from now on, at low cost:

- **Kernel**: everything that depends on x86-64 sits behind an architecture layer, to port to ARM64 and RISC-V. Target: processors with an MMU; microcontrollers without an MMU are out of scope.
- **Wasm**: components compiled ahead of time, with no compiler on the device; an interpreter as fallback.
- **Configuration**: the system is a hash, so an embedded image is another hash, with fewer services. No service assumes a screen, a GPU, a keyboard or a local agent.
- **Interface**: the catalogue describes meaning (button, field, list), not layout. Each surface has its rendering template.
- **Real time**: scheduling contexts with a budget and a deadline already suit it.
- **Memory**: a gate "memory of an empty process" and the size of the minimal image, to set.
- **Storage**: system and device zones only (see [storage.md](storage.md#zones)).
