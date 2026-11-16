# Gates

Statuses are defined in the [README](../README.md#status-legend).

A **gate** is a measured target that a change must hold to be merged or kept. Latency is a contract, and every isolation layer has a budget.

Cadence (**Decided**, 14 November 2026): fast gates run at every merge; gates on hardware run at night; a merge that breaks a night gate is reverted. Gates are calibrated before the ratchet is armed; after that, a gate can only tighten.

## Latency gates

Targets to calibrate on the reference machine, at 120 Hz, measured by photodiode relative to a bare scanout. Lines marked "proposed" are **Proposed**; the others had no status.

| Gate | Target |
|---|---|
| Cursor, input → photon | ≤ 1 frame |
| Key → glyph displayed | ≤ 2 frames at p99 |
| Scrolling while a rendering engine is busy | 0 frame lost at p99.9 |
| Full-screen WebGPU | 0 frame added |
| Frame pacing during a local inference | < 0.1 % of frames missed |
| Audio output buffer | ≤ 5 ms |
| Agent: visual acknowledgement, then first sound | ≤ 100 ms, then ≤ 400 ms |
| Cold launch with cache | ≤ 200 ms to the first frame |
| Boot: firmware hand-off → first frame (proposed) | ≤ 1 s |
| Boot: firmware hand-off → usable shell (proposed) | ≤ 2 s |
| Shutdown: request → power off (proposed) | ≤ 1 s |
| Wake from sleep → first frame (proposed) | ≤ 0.5 s |

The latency gates are the authoritative test for the compositor (see [verification.md](verification.md#authoritative-test-suites)). Their realism is not established: the targets are to calibrate by measurement.

### Boot and shutdown

- seL4 publishes no boot bench (searched on the web on 14 November 2026, not in the sel4bench repository; the only neighbouring figure is 1.3 s for a stack of three processes on Cortex-A9, PARseL paper). The oracle is therefore of no use here; the reference is Linux, Windows and macOS on the same machine, to measure.
- Firmware time is not the project's: it is measured separately, and the total from button to image is published too.
- The levers and the probable long point are in [platform.md](../architecture/platform.md#boot).

## Overhead gates

**Proposed.** Each isolation layer has a budget, measured against a reference on the same machine. The targets are to calibrate by measurement.

| Gate | Reference | Starting target |
|---|---|---|
| IPC round trip between two processes, same core | seL4 MCS, with the same Spectre protections, measured on the project's machine (Decided, 14 November 2026). Published seL4 figures: about 740 cycles for the call and 600 for the reply on Skylake (verified 13 November 2026) | < 1.2 times seL4 (Decided) |
| Asynchronous WIT call between two processes, end to end (Decided, 14 November 2026) | | To set |
| IPC round trip between two cores | Same-core IPC | To set |
| Operation on the address space of a process on several cores (mapping, revocation) | Linux | To set |
| Wasm compute (Cranelift tier) | Same code compiled natively | ≤ 1.5 times; then ≤ 1.2 times with the optimised tier, which is deferred until after the alpha |
| Call between two components of the same process | Native function call | To measure, with and without async |
| Disk read and write | Raw NVMe device | ≥ 90 % of the throughput; one throughput gate per type of workload (Decided, 14 November 2026) |
| Network throughput | Linux on the same card | ≥ 90 % |
| IOMMU active | Same load, IOMMU off | ≤ 3 % |
| Kernel entries per unit of work: per displayed frame, per disk read, per network packet (Decided, 14 November 2026; see [data plane](../architecture/kernel-interface.md#data-plane)) | | To set |
| One page fault resolved by the memory service from memory already present (Proposed, 14 November 2026; see [memory outside the kernel](../architecture/kernel-interface.md#memory-outside-the-kernel)) | The same fault on Linux | To set |
| Page faults per megabyte on a cold sequential read (Decided, 14 November 2026; see [pager](../architecture/kernel-interface.md#pager)) | | To set |
| Verification of blobs | Read without verification | ≤ 5 % cold, 0 warm |
| Memory of an empty application process | | To set |
| Cost of a minor page fault and of a mapping | Linux | To set |
| Recovery time of one node | | To set |
| Size of the minimal image (embedded) | | To set |
| Storage of a demonstration application | Same application under Flatpak | Smaller |

The gates are calibrated before the ratchet is armed (**Decided**, 14 November 2026). The overhead measured on libsodium, for the Wasm gate, is in [wasm-abi.md](../architecture/wasm-abi.md#performance-levers).

## Expected costs

**Proposed.** Expected costs of isolation, to measure:

- Wasm execution at 1.5 to 2.4 times native (the main item).
- Copy at component boundaries (hence rule 6 of the [ABI](../architecture/wasm-abi.md#abi-rules)).
- One hash per block at the first read of a blob.
- IOMMU almost nil with long-lived mappings.

## How gates are measured

- Under QEMU, instructions are counted, not cycles (**Decided**, 14 November 2026). KVM on free runners is not the only gate.
- Latency and overhead gates run on the reference desktop at night, with a statistical threshold, and a regression is bisected automatically.
- Details are in [verification.md](verification.md#checks-per-stage).
