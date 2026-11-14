# Drivers

Statuses are defined in the [README](../README.md#status-legend).

Drivers run in user space, one process per driver, behind stable interfaces. Most of them are Linux drivers compiled against an emulation library. The NVIDIA driver does not go through that layer (see [gpu.md](gpu.md)).

## Driver framework

**Aligned.**

- One stable interface per device class: block, network, input, audio, display, GPU.
- Control goes through WIT; data goes through queues in shared memory.
- A driver manager matches devices and drivers by declarative rules.
- An emulated Linux driver and a native driver implement the same interface.
- The kernel programs the IOMMU per driver. The IOMMU is the hardware unit that restricts which memory a device can reach by DMA (direct memory access). Without it, a driver can write anywhere in memory by DMA and isolation is worth nothing.
- Models: DFv2 of Fuchsia, and sDDF of seL4 (version 0.7.0: single-producer single-consumer queues in shared memory, single-threaded drivers, explicit virtualisers to share a device). Verified 13 November 2026.
- Measurement published by sDDF: a saturated 1 Gb/s link at 65 % of one core, where Linux tops out at 500 Mb/s.

**USB** (**Decided**, 14 November 2026): a bus interface is added. The controller runs in one process, and the class drivers (native first) in others.

## Linux driver emulation layer

**Decided.**

- Drivers come from a long-term-support Linux kernel, taken from kernel.org without going through a distribution.
- They are compiled from source against a library that reimplements the internal API of the kernel, one process per driver.
- There is no virtual machine, no Linux kernel and no system call translation.
- The Linux subsystems a driver depends on (sound, Wi-Fi, DRM) are compiled with it, without rewriting them. This is what distinguishes the approach from LinuxKPI, whose hand rewriting is the painful point for FreeBSD.
- The **emulation library** is the code that supplies Linux drivers with the Linux kernel functions they expect.
- To read before writing it: SUD, LKL and Genode (**Decided**, 14 November 2026). The current state of Genode DDE Linux is "from memory".

### Linux version

- The version is fixed when the emulation layer starts: the latest long-term-support version at that time (**Decided**, 14 November 2026). The sources come from kernel.org, with no planned switch to a distribution afterwards.
- Linux 7.3 was the candidate. The announcement, attributed to Greg Kroah-Hartman, that it would be designated the 2026 long-term-support (LTS) kernel is not confirmed.
- There is no conflict with Debian, which serves only as a source of patches for libraries: drivers and libraries are never linked together.
- The project follows the fixes of the long-term-support Linux kernel (see [security.md](security.md#vulnerabilities)).

### Licence

**Decided, 14 November 2026; to be confirmed by legal counsel.** The emulation library is linked to GPLv2 code. It is published under the MIT licence, which is compatible. The whole driver process is under GPLv2. It talks to the rest of the system by IPC. The project licence is in [thesis.md](../thesis.md#licence).

### What the layer must emulate

- The `dma_map` functions translate directly to the IOMMU address-space object (see below).
- Sleep: the layer must replay the suspend callbacks of Linux drivers, in order, and handle the D3 device power states (see [platform.md](platform.md#power-and-sleep)).
- Input: device discovery as done by udev must be emulated for libinput (see [ui.md](ui.md#input)).
- An emulated Linux driver cannot be cancelled (see [scheduling.md](scheduling.md#the-budget-follows-the-call)).

## IOMMU

- Each driver process receives an input/output address space: a kernel object designated by a capability. The device can reach by DMA only the memory explicitly placed in that space.
- Data buffers are shared memory objects, visible to the client, the driver and the device at the same time: zero-copy queues remain possible.
- Mappings are long-lived (buffer pools) rather than one mapping per request, to limit the cost.
- Interrupt remapping is enabled: a device cannot forge interrupts.
- Devices that the hardware cannot separate go into the same driver process.
- The IOMMU is active before the first driver starts. On a machine without an IOMMU, drivers are declared trusted, and this is displayed.

The IOMMU domain is one of the three isolation boundaries (see [security.md](security.md#three-boundaries)).

## Restart of a driver

Every component of the system restarts or is replaced without rebooting the machine (see [platform.md](platform.md#restart-and-hot-replacement)). For a driver: the manager stops the process, resets the device at bus level (PCIe function reset or power cycle), recreates its IOMMU domain, and restarts the driver. The class interface decides what happens to requests in flight: replayed for the disk, lost for the network, last frame kept for the display.

After sleep, a driver that does not wake up is restarted by this protocol.

## Native drivers

| Driver | Position | Status |
|---|---|---|
| NVMe | Native driver (step 3 of the [kernel track](../plan/roadmap.md#kernel-track)) | Decided, 14 November 2026 |
| USB class drivers | Native first | Decided, 14 November 2026 |
| Network card | Linux emulation (step 3 of the kernel track) | Decided, 14 November 2026 |
| Camera | Native class driver, after the alpha | Decided, 14 November 2026 |
| virtio | Step 2 of the kernel track | Decided, 14 November 2026 |

The wider idea of writing native class drivers first, and of using the Linux driver as an oracle for a native driver, is in the [idea reservoir](../research/ideas.md#ecosystem-survival-without-porting-everything-from-linux).

## Driver manifest deduced from traces

**Aligned** (retained with the user's agreement, to be designed; second delegated study of 14 November 2026, not cross-checked). A driver's manifest is deduced from traces (MMIO ranges, DMA windows per ring, interrupts), and review bears on the difference at each update. Limit: rare paths (sleep, errors) are missing from the traces.

## Drivers in micro-VMs: alternative not retained

Principle: a minimal Linux in one virtual machine per driver, the device passed through by the IOMMU, the data through the same shared queues. LionsOS (seL4) does this as a fallback for network, disk, sound and a 2D GPU (verified 13 November 2026; figures of the authors).

| | Arguments |
|---|---|
| For | Every Linux driver works unmodified, including Wi-Fi, Bluetooth with BlueZ and the proprietary NVIDIA driver (CUDA, DLSS, full video decoding). No emulation layer to write or maintain. Kernel version upgrades are trivial. Equivalent isolation |
| Against | A hypervisor to add to the kernel, so more trusted code and more tests outside the oracle. 50 to 250 MB of memory and a Linux boot per VM (order of magnitude, from memory). A driver restart takes seconds. Interrupts cross the VM, so latency. Sleep must be coordinated with each guest. GPU: scanout and scheduling would stay in the guest, which breaks the latency gates and the role of the GPU service. No published overhead figure |

**Position.** The emulation layer is on the critical path. The micro-VM remains a possible fallback for the long tail (Wi-Fi, Bluetooth, exotic hardware), to be reopened only if emulation stalls. Virtual machines are otherwise out of scope (**Decided**; see [thesis.md](../thesis.md#scope)).
