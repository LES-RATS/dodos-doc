# Memory management

Statuses are defined in the [README](../README.md#status-legend). Unless a line says otherwise, this file is **Proposed** (14 November 2026); the lines marked Decided come from the decisions of 14 November 2026.

The split is the same as for scheduling: the mechanism is in the kernel and the policy is in user space.

## Kernel memory

- **No heap in the kernel.** All the memory the kernel needs for an object comes from a memory capability supplied by whoever creates the object (model of seL4, from memory). A program therefore cannot exhaust kernel memory. The exact rule is rule 3 of the [kernel interface](kernel-interface.md#rules): no kernel memory that grows at run time; only fixed tables sized when the machine or a node starts (the machine table, the interrupt table, the IOMMU units, the kept image) and the start-up objects are outside any untyped (D-110).
- **Memory service** (**Decided**). The memory service, in user space, holds the memory capabilities and supplies pages and page tables at the time of a page fault. The page reserve of each kernel is an advance that the memory service handed to it.
- **Physical memory per node.** Each node slot has a fixed floor (D-107, amended by D-114); the rest of memory moves between nodes in chunks (one first large page, 2 MB on the reference machine), driven by the memory service with `memory_take` and `memory_give`; who owns each chunk is recorded in the machine table, written only by the owner's gate (D-112 to D-115, [Memory and devices between nodes](kernel-interface.md#memory-and-devices-between-nodes)). Memory of another node is used only through a grant, recorded on both sides, and only when it is shared. The memory service keeps movable runs apart from runs pinned by kernel objects or by DMA, since a run can leave a node only when nothing made from it lives.
- **NUMA** (machines whose memory is split between processor sockets) is out of scope as long as no target has it (**Decided**).

## Memory objects

A **memory object** (model of Fuchsia) is a set of pages designated by a capability. It can be mapped, shared and copied on write. It is the unit of sharing between processes and the support of the [snapshot](platform.md#process-state-suspend-resume-and-snapshots).

## Paging in user space

- A page fault on an object backed by storage becomes a message to the storage service.
- Blobs (immutable content-addressed data; see [storage.md](storage.md)) are mapped as they are: the page cache is the set of blobs, shared by hash between all processes.
- A Wasm component does not map a blob into its own memory: the copy is accepted. The shared cache serves compiled code and native programs (**Decided**).

## Address space

- Page tables are the only structure that translates (approach of CortenMM). The mapping record in a frame capability names a mapping and is kept coherent with it by the kernel; it is not a second translation map (see [Mapping records](kernel-interface.md#mapping-records)). This lead is **Aligned** (retained, to be designed; second delegated study of 14 November 2026, not cross-checked): the page table as the only representation, with a minimal, verified concurrent part; CortenMM (SOSP 2025) is announced as 1.2 to 26 times faster than Linux.
- TLB invalidation (flushing the processor's cache of address translations) is limited to the cores of the process's node that loaded its address space. A process lives in one node (D-128) and an address space has one page table, shared by the node's cores (D-129; see [TLB, one core and several](kernel-interface.md#tlb-one-core-and-several)).
- Memory copy as a kernel service with a deadline (Copier, SOSP 2025): **Aligned** (retained, to be designed; same study, not cross-checked).

## Page sizes

- The page of the machine by default (D-121: 4 KB on x86-64; [Values of the machine](kernel-interface.md#values-of-the-machine)). The first large page (2 MB on the reference machine) for Wasm memories and compiled code only above a size threshold (**Decided**, D-044, restated in the machine's sizes by D-121).
- A Wasm memory reserves its virtual space with guard pages, which removes bounds checks. This holds for 32-bit memories only (**Decided**).
- The second large page (1 GB on the reference machine), for inference, comes after the alpha (**Decided**). The kernel supports it from its first version (D-110).

## Budget, without overcommit

- Every task carries a memory budget. The budget of a task is drawn on by all its processes (**Decided**).
- Accounting is done at reservation time (**Decided**).
- An anonymous page is charged to the task; a page of a shared blob is charged to the system. A shared anonymous object is charged to its creator (**Decided**).
- Budget exceeded: an allocation error is returned to the runtime. "No process killed later by surprise" holds for Wasm; an allocation error can stop native code (**Decided**).

## Pressure

Pressure handling is the policy of the memory service. It does not assume process snapshots (**Decided**). In order:

1. Empty the caches.
2. Compress in memory the pages of background tasks.
3. Freeze the non-visible surfaces into a snapshot and free their memory. Automatic snapshots exist only for an idle Wasm component (see [platform.md](platform.md#process-state-suspend-resume-and-snapshots)).
4. Overflow to disk.
5. Kill a process. This is the last resort, reserved for force majeure (nothing left to free and a frame-class task threatened), and it is logged.

## Compression and swap

- Compression is the equivalent of zram (compressed pages kept in memory, with no disk), built into the memory service rather than disguised as a swap disk. It is in version 1.
- The equivalent of zswap (the coldest compressed pages overflow to disk) comes afterwards, to an encrypted region of the store.

## Other rules

- **Zeroing.** Every page is zeroed before it changes process, by idle efficiency cores. A frame the kernel makes is already zero (D-110, proposed: [rules of `untyped_retype`](kernel-interface.md#capabilities-and-objects)); the memory service zeroes the pages it moves from one process to another without passing through an untyped.
- **Drivers.** Pinned memory through a separate capability, and long-lived IOMMU mappings (see [drivers.md](drivers.md#iommu)). The separate capability is a derived frame capability mapped in the driver's `iospace`: the frame cannot be freed while that mapping exists, and revoking the capability unmaps it from the device first ([IOMMU](kernel-interface.md#iommu)).
- **Protections.** Write or execute, never both; address space layout randomisation; guard pages around stacks.
- **GPU memory.** See [gpu.md](gpu.md#gpu-memory).

## Boot-image services

**Decided.** The services of the boot image are pinned in memory. The list is: kernel, storage service, disk driver, service manager, memory service, placement service. The boot image itself is described in [storage.md](storage.md#updates).

## Gates to add

Cost of a minor page fault and of a mapping, compared with Linux; memory of an empty process. See [plan/gates.md](../plan/gates.md#overhead-gates).
