# What `abi/` must gain or change, and what pass 12 of the reference model must cover

Written 16 November 2026, with the integration of the drafts into the [kernel contract](../../architecture/kernel-interface.md) (branch `contract-integration`). `abi/` is the reference for values; this file lists every value the contract of 16 November 2026 adds or changes, against `abi/` at commit `40c6863` of the kernel repository. Nothing here is a rule: the rules are in the contract, and each line names the section that holds them.

## 1. Calls

The position in `Call` is the call's number in `abi/` (rule 6: numbers are private to the code page and may change between kernel versions). Positions 0 to 47 keep their place; 48 to 63 are new.

| Number | `Call` | Group | Change |
|---|---|---|---|
| 0 | `CapDerive` | Capabilities | An `ioports` capability keeps its range; a destination on another node makes a grant |
| 1 | `CapMove` | Capabilities | A destination on another node makes a grant (the anchor takes the source's place) |
| 2 | `CapDelete` | Capabilities | A thread of a revoked task gets `gone` here too |
| 3 | `CapRevoke` | Capabilities | Removing an anchor revokes its grant (may wait for the holder's node) |
| 4 | `CapInspect` | Capabilities | Badge of an `ioports` capability is its range; executed by the caller's kernel |
| 5 | `CSpaceGrow` | Capabilities | — |
| 6 | `UntypedRetype` | Capabilities | Size argument of a thread is its feature mask; kinds `Core`, `IoPorts`, `Debug`, `MemoryControl`, `Role` are `Invalid` |
| 7 | `ASpaceMap` | Memory | Map-count overflow `Busy`; up to *E* pages; remote frames under a grant |
| 8 | `ASpaceUnmap` | Memory | — |
| 9 | `ASpaceProtect` | Memory | — |
| 10 | `Call` | IPC | The endpoint may be a `core` capability with `send` (mailbox) |
| 11 | `ReplyRecv` | IPC | May return `Again` (a fault *no context* recorded) |
| 12 | `Recv` | IPC | May return `Again` (the same) |
| 13 | `Send` | IPC | The endpoint may be a `core` capability with `send` |
| 14 | `Signal` | Notifications | — |
| 15 | `Wait` | Notifications | — |
| 16 | `Poll` | Notifications | — |
| 17 | `NotifyBind` | Notifications | — |
| 18 | `ThreadConfigure` | Threads | Message page: one page of *P* bytes |
| 19 | `ThreadReadRegs` | Threads | Result: the block, then the fault record (6 words) |
| 20 | `ThreadWriteRegs` | Threads | x86-64 block of 26 words (breakpoints, user-interrupt word) |
| 21 | `ThreadResume` | Threads | Clears the fault record |
| 22 | `ThreadSuspend` | Threads | — |
| 23 | `Yield` | Scheduling | — |
| 24 | `SchedConfigure` | Scheduling | Pending parameters |
| 25 | `SchedBind` | Scheduling | — |
| 26 | `SchedUnbind` | Scheduling | — |
| 27 | `SchedSetCores` | Scheduling | Core numbers of the start-up page |
| 28 | `TimerSet` | Time | — |
| 29 | `TimerCancel` | Time | — |
| 30 | `IrqBind` | Interrupts | — |
| 31 | `IrqAck` | Interrupts | `Busy` when the notify is dying |
| 32 | `IoSpaceMap` | Interrupts and devices | — |
| 33 | `IoSpaceUnmap` | Interrupts and devices | Invalidation through the unit's role holder |
| 34 | `IoSpaceAttach` | Interrupts and devices | Through the unit's role holder |
| 35 | `TaskExempt` | Tasks | — |
| 36 | `TaskAttach` | Tasks | — |
| 37 | `TaskMark` | Tasks | — |
| 38 | `TaskRevoke` | Tasks | — |
| 39 | `TaskRead` | Tasks | — |
| 40 | `CoreStart` | Cores | Arguments: core, mode, kernel image, module |
| 41 | `CoreStop` | Cores | Arguments: core, mode |
| 42 | `CoreStatus` | Cores | 7 result words |
| 43 | `DebugWrite` | Debug | — |
| 44 | `TraceEmit` | Debug | — |
| 45 | `ThreadCancel` | Threads | Forwarded to a proxy's node for a wait on another node |
| 46 | `IrqClaim` | Interrupts | Source kind 3, core event; a line from any node |
| 47 | `SchedRead` | Scheduling | Fifth result: instructions; state bits 4 and 8-15 |
| 48 | `MemoryTake` | Memory | New |
| 49 | `MemoryGive` | Memory | New |
| 50 | `MemorySplit` | Memory | New |
| 51 | `CoreIdle` | Cores | New (was "a call of the Cores group") |
| 52 | `CoreWatch` | Cores | New |
| 53 | `CorePlace` | Cores | New |
| 54 | `RoleClaim` | Cores | New |
| 55 | `RoleHand` | Cores | New |
| 56 | `ThreadSetFeatures` | Threads | New |
| 57 | `ThreadMove` | Threads | New |
| 58 | `SchedCount` | Scheduling | New |
| 59 | `IoportIn` | I/O ports | New |
| 60 | `IoportOut` | I/O ports | New |
| 61 | `IoportsIssue` | I/O ports | New |
| 62 | `EntropyRead` | Entropy | New |
| 63 | `CorePerf` | Cores | New |

## 2. Errors

None new. `Error` keeps its twelve codes. What changes is where they occur: `Again` from `Recv` and `ReplyRecv`; `NoMemory` from `ThreadSetFeatures` (save area too small) and from a transfer to another node when a grant or use table is full; `Unsupported` from a feature mask (bit 31, a feature or a length the node's kind lacks), from the user-interrupt word of `ThreadWriteRegs`, from the port calls off x86-64 and from `CorePerf` without a performance register. The answer *moved* between kernels is internal and never reaches user space.

## 3. Object kinds

| Number | `ObjectKind` | Change |
|---|---|---|
| 0 to 10, 12, 13 | unchanged | — |
| 11 | `IoPorts` | `untyped_retype` refuses it with `Invalid` (was `Unsupported`) |
| 14 | `Core` | A machine object; `Invalid` in `untyped_retype` (was `Unsupported`) |
| 15 | `Debug` | `Invalid` in `untyped_retype` (was `Unsupported`) |
| 16 | `Vcpu` | Reserved, still `Unsupported` |
| 17 | `IrqControl` | — |
| 18 | `Iommu` | A machine object |
| 19 | `MemoryControl` | New |
| 20 | `Role` | New, a machine object |

The entry `ObjectSizes` covers kinds 0 to 20.

## 4. Sizes, limits and values of the machine

| Value | Before | After | Contract section |
|---|---|---|---|
| `PageSize` | `Size4K`, `Size2M`, `Size1G` with fixed bytes | A page size *index* 0 to 3; the bytes are read from `StartMemory`. Module `x86_64` keeps `PAGE = 4096`, `LARGE = [2 << 20, 1 << 30]` | Values of the machine |
| `TABLE_BYTES`, `TABLE_ENTRIES` | 4096, 512 | Machine values (*P*, *E*); module `x86_64` keeps 4096 and 512. New `TABLE_ENTRIES_MAX = 4096` | Values of the machine |
| `FRAME_MAX_PAGES` | 512 | *E* (a machine value; at most 4096) | Frames |
| `ASPACE_BYTES`, `IOSPACE_BYTES` | 8192 | Two pages (`x86_64`: 8192) | Address spaces and their tables |
| `UNTYPED_MIN_BYTES` | 4096 | One page (`x86_64`: 4096) | Capabilities and objects |
| `THREAD_BYTES` | 1024 | Renamed `THREAD_FIXED_BYTES = 1024`; the size of a thread comes from the start-up page. Module `x86_64`: `XSTATE_X87_SSE_AVX_BYTES = 832`, so a thread of mask 0 is 2048 on the reference machine | Object sizes, Unlike cores |
| `SCHED_BYTES` | 128 | 256 | Object sizes |
| `USER_RANGE_END` | absent | Machine value; module `x86_64`: `0x7F80_0000_0000` | Values of the machine |
| `SHARE_ALIGN` | 2 MB | Removed: the chunk is the first large page (`x86_64`: 2 MB) | Chunks, floors and the ownership words |
| `START_RESERVE_BYTES` | 256 KB | Removed (64 pages of the start-up untyped) | Start-up state |
| `START_MESSAGE_PAGE_ADDR`, `START_PAGE_ADDR` | 0x1000, 0x2000 | *P* and 2 × *P*; module `x86_64` keeps 0x1000 and 0x2000 | Start-up state |
| `FIRST_SERVICE_MIN_ADDR` | 0x20_0000 | The first large page; module `x86_64` keeps 0x20_0000 | Start-up state |
| `CHUNK_RUN_MAX` | — | *E* chunks per run | Chunks |
| `DEVICE_TABLE_SPARE` | — | 8192 | The device table |
| `GRANTS` | — | 4096 per node | Grants |
| `GRANT_ENTRY_BYTES`, `USE_ENTRY_BYTES` | — | 128, 32 | Grants |
| `PROXIES_PER_PEER`, `PROXY_BYTES` | — | 16, 1024 | Calls on an object of another node |
| `NODES_MAX` | — | 1024 | Cores |
| `RESERVES_MAX`, `ROLES_PLAIN_MAX` | — | 8, 64 | Roles |
| `CORE_WATCH_SLOTS`, `IDLE_STATES_MAX`, `OBSERVATIONS_MAX` | — | 4, 15, 8 | Cores |
| `STALE_NS`, `STUCK_NS` | — | 100 ms, range 10 ms to 1 s | Detection |
| `SWEEP_NS` | — | 1 s, range 100 ms to 60 s | Detection |
| `NMI_GRACE_NS`, `FENCE_NS`, `SETTLE_NS`, `START_NS` | — | 1 ms, 10 ms, 1 ms, 1 s | The fence, the calls |
| `RECOVERY_BANDWIDTH`, `RECOVERY_PERIOD_NS` | — | `1 << 26`, 10_000_000 | The recovery reserve |
| `START_SCHED_BUDGET_NS` | — (budget = period) | 9_843_750 beside `START_SCHED_PERIOD_NS` | Start-up state, the first thread |
| `CHECK_MUL` of the ownership word | — | `0x9E37_79B9_7F4A_7C15` | Chunks |
| `OWNER_UNCLAIMED`, `OWNER_RESERVE_BASE` | — | 0xFFFF, 0xFFF0 (reserves 0xFFF0 to 0xFFF7) | Chunks |
| `ENTROPY_MAX_BYTES` | — | 64 | Entropy |
| Debug sizes | — | `DEBUG_AREA_BYTES = 69_632`, `DEBUG_HEADER_BYTES = 64`, `NODE_CRASH_RECORD_BYTES = 4_032`, `CRASH_HEADER_BYTES = 4_096`, `TRACE_ENTRY_BYTES = 64`, `TRACE_KERNEL_ENTRIES = 256`, `TRACE_USER_ENTRIES = 768`, `TRACE_TEXT_BYTES = 24`, `DEBUG_WRITE_MAX = 512`, `TRACE_BURST = 16`, `TRACE_BURST_NS = 1_000_000`, `CONSOLE_STEP_BYTES = 16`, `CONSOLE_TICK_NS = 1_000_000`, `STUB_STOP_NS = 10_000_000`, `CRASH_RECORD_KERNEL_ENTRIES = 32`, `CRASH_RECORD_USER_ENTRIES = 16` | Debugging (call reference) |
| Module `x86_64`, registers | `REGS_WORDS = 20` | `REGS_WORDS = 26`; `REG_DR0..REG_DR3 = 20..23`, `REG_DR7 = 24`, `REG_UINTR = 25`; `DR7_USER_MASK` (to write from the Intel SDM: the local enables and the condition and length fields, without the general-detect bit and without the I/O condition); `HW_BREAKPOINTS = 4` | Register calls, Debugging a component |
| Module `x86_64`, ports | — | `KERNEL_PORTS = [(0x20, 0x21), (0xA0, 0xA1)]`, `PCI_CONFIG_PORTS = (0xCF8, 0xCFF)`, `UART_PORTS = 8`; the reset port is named by the architecture layer, not fixed here | I/O ports |
| `REMOVAL_STEP`, `REMOVAL_SLOTS`, `CLEAR_STEP_BYTES`, `CSPACE_SEGMENT_SLOTS`, `TREE_DEPTH`, `CSPACE_MAX_SLOTS` | — | Unchanged (byte and step bounds) | — |

## 5. Bit layouts and types

| Type | Layout | Contract section |
|---|---|---|
| The slot (`SLOT_*` constants) | Word 0: bits 0-1 state (0 empty, 1 full, 2 dead, 3 remote), 2 dying, 3 root, 4-9 kind, 10-17 rights, 18-24 depth, 25-63 by kind; word 1 object (or, remote: node 0-9, grant 10-21, serial 22-51, use entry 52-63); words 2-3 by kind; 4-5 derivation list; 6-7 space list or binding. Frame by-kind bits: 25-26 page size index, 27-28 memory type, 29 device, 30-41 pages − 1, 42-53 first page of the record; word 2 record kind and rights and space; word 3 address and count − 1. Untyped: 25-30 log2 size, 31 device, 32 clean mark, 33 block, 34 device entry, 35-50 entry index | The capability slot |
| `Ownership(u64)` | bits 0-1 state, 2-15 check, 16-31 owner, 32-63 generation; `from_raw` refuses a failed check and state 3 | Chunks, floors and the ownership words |
| `DeviceEntry` (16 bytes) | base and log2 size (bits 0-5), bit 6 used; then an `Ownership` | The device table |
| `Member(u64)` | bits 0-3 state, 4-6 evidence, 7-15 zero, 16-31 driver (0xFFFF none), 32-63 generation; `MemberState`, `Evidence` | The states of a node |
| `RoleWord(u64)` | bits 0-1 state, 2-17 holder, 18-33 target, 34-63 epoch; `RoleState`, `RoleKind`, what a role governs | Roles |
| `FeatureMask(u64)` | bits 0-30 optional state features, 31 user interrupts (reserved), 32-47 vector length in bytes, 48-63 zero; feature lists per architecture (`x86_64`: `AVX = 0`, `AVX512 = 1`, `AMX = 2` large, `APX = 3`; instruction features from 32. `aarch64`: `SVE = 0`, `SME = 1` large, `SME2_ZT0 = 2`. `riscv64`: `V = 0`) | Unlike cores |
| `IrqSource` | kind 3 *core event*: bits 0-7 = 3, bits 8-15 the event (`CORE_EVENT_FEEDBACK = 1`) | Unlike cores |
| `FaultKind` | `HardwareBreakpoint = 9` | Faults |
| Scheduling | `SCHED_STATE_COUNTED = 1 << 4`, `SCHED_STATE_HW_CLASS_SHIFT = 8`, mask `0xFF << 8` | Scheduling contexts, Unlike cores |
| Cores | `CORE_START_FRESH = 0`, `CORE_START_RESUME = 1`; `CORE_STOP_KILL = 0`, `SEAL = 1`, `RETIRE = 2`; `CORE_STATUS_PARKED = 1 << 32`, `UNUSABLE = 1 << 33`, fence class in bits 34-35; `IDLE_METHOD_HALT = 0`, `MWAIT = 1`, `PSCI = 2`, `SBI = 3`; `IDLE_FLAG_LOSES_CONTEXT = 1`; `FENCE_CLASS_COOPERATIVE = 0`, `SIGNALLED = 1`, `FORCED = 2` | Cores |
| Debugging | `TraceCode` 1 to 10, 16, 17; `TRACE_FLAG_CONTINUED`; `TraceEntry` (64); `DebugAreaHeader` (64); `NodeCrashRecord` (4,032); `CrashAreaHeader`; `CrashReason` 1 to 8; `ConsoleKind` (`None = 0`, `Uart16550Port = 1`, `Uart16550Mmio = 2`, `Pl011 = 3`, `SbiDbcn = 4`); the console message numbers 1 to 14; `Build` | Debugging (call reference) |
| `IoPortRange(u64)` | first in bits 0-15, last in 16-31 | I/O ports |
| `Header` | unchanged; `add_marks` is cleared at delivery | Tasks and marks |

## 6. Start-up page and boot image

| Item | Before | After |
|---|---|---|
| `START_VERSION` | 1 | 2 |
| `START_SLOT_*` | 1 to 11; 12-15 empty | 12 `MEMORY_CONTROL`, 13 `MACHINE_LIVING`, 14 `MACHINE_FIXED`, 15 `MAILBOX`; `START_SLOT_FIRST = 16` now begins the *n* `core` roots, then `iommu`, `role`, feedback frames, floor untypeds, copied segments, kept frames of modules, crash frames |
| `START_UNTYPED_IMAGE` | bit 1 | Removed (no image untyped) |
| `StartKind` 0 `ObjectSizes` | kinds 0 to 18 | kinds 0 to 20; thread for mask 0 |
| `StartKind` 2 `Cores`, `StartCore` | 24 bytes, boot core first | 32 bytes: `hw_id: u64`, `slot: u32`, `kind: u16`, `flags: u16` (bit 0 booted by firmware, bits 1-2 fence class), `threads`, `perf_highest`, `perf_efficient`, `efficiency_class` (u8), `package: u32`, `reserved: u32`; sorted by hardware identifier |
| `StartKind` 8 `CrashRecord` | raw bytes | `StartCrash` (32): base, length, sequence (u64), slot, flags (u32) |
| `StartKind` 10 `Modules`, `StartModule` | 32 bytes | 40 bytes: `first_slot`, `slots` (u32), `vaddr`, `len` (u64), `flags`, `name_offset`, `name_len`, `reserved` (u32); flag bit 4 first service; name area after the records |
| `StartKind` 11 `Node`, `StartNode` | index, nodes, generation, boot | index, nodes, generation, flags (bit 0 fresh after a death, bit 1 resumed) |
| `StartKind` 12 | `Shares` | Renamed `Floors` (`StartShare` unchanged) |
| `StartKind` 13 `Interrupts` | flags bits 0-1 | bit 2: directed end of interrupt possible |
| `StartKind` 15 `Memory`, `StartMemory` | 40 bytes | 56 bytes: `user_end`, `code_page`, `clock_page` (u64), `page_shift: [u8; 4]`, `table_entries`, `levels`, `iospace_width`, `iospace_page_sizes`, `flags` (bit 0 map through the role holder, bit 1 gate without window, bit 2 control-flow protection, bit 3 hardening monitor), two `reserved` (u32) |
| `StartKind` 16 `Iommu`, `StartIommu` | last field reserved | last field: the index of its role |
| `StartKind` 17 `Machine` | — | `StartMachine` (64): eight u32 offsets in slot 13's frame (ownership, device table, gate words, page classes, members, roles, grants, uses), `chunks: u64`, device capacity, roles, `GRANTS`, layout (u32), reserved (u64) |
| `StartKind` 18 `Roles` | — | `StartRole` (8): kind (u8), governs (u8), object (u16), slot (u32) |
| `StartKind` 19 `Reserves` | — | `StartShare` records |
| `StartKind` 20 `Image` | — | `StartImage` (48): base, length (u64), SHA-256 (32 bytes) |
| `StartKind` 21 `Kinds` | — | `StartKindRecord` (56): `features`, `baseline` (u64), `id: [u64; 3]`, `cores`, `vector_bytes`, `baseline_bytes`, `reserved` (u32) |
| `StartKind` 22 `Features` | — | per kind, 32 u32: save-area bytes of each state feature |
| `StartKind` 23 `Feedback` | — | `StartFeedback` (16): package, slot, bytes, reserved (u32) |
| `StartKind` 24 `Debug` | — | `StartDebug` (56, then port pairs): build, console kind (u32), console address (u64), current crash area base and length (u64), slot, bytes per area (u32), kernel entries, user entries, entry bytes, hardware breakpoints, watchpoints, reserved (u16), then the refused port ranges (u16 pairs) |
| `BootFloors` (boot image) | — | 32 bytes: `floor_node`, `reserve_bytes`, `reserve_per_gib` (u64), `reserves`, `plain_roles` (u32); the names of the plain roles follow |
| `BootMembership` (boot image) | — | 24 bytes: `stale_ms`, `stuck_ms`, `sweep_ms` (u32), three reserved (u32) |
| `NodeGen` | generation 0-31, node 32-47 | Unchanged, for messages between kernels |

`layouts_are_fixed` asserts every size above.

## 7. Pure functions with a Kani proof

- `Ownership::from_raw` reads back what each constructor writes; `none()` is 0; state 3 is refused. `may_take(word, node, generation, member_of_owner, holds_reserve)` accepts exactly rules 1 to 4 of taking.
- `Member::from_raw`, `RoleWord` read back; the gate's transition check accepts exactly the rows of the transition table; `successor(members, fence_classes, holder)` returns a live node of the best class when one exists; the barrier predicate is monotone.
- `FeatureMask::check(mask, kind)` returns `Invalid`, then `Unsupported`, in the contract's order; `thread_bytes(mask, kind) -> Option<u64>` is a power of two, at least `THREAD_FIXED_BYTES`, at least the exact sum, `None` on overflow; `kind_covers(host, node)` (features and lengths).
- `module_frames(phys, virt, len, page_shifts, entries)`: the frames cover the module in order, each of one supported size aligned at its position, at most *E* pages, the last one ending at the length rounded up to a page.
- `floors(ordinary, n, BootFloors)`: every size a multiple of the chunk, the sum computed without overflow.
- `clear_steps(watermark, clean, start, end)`: each step clears at most `CLEAR_STEP_BYTES`, stops at the end, and the number of steps is between ⌈*b* / 64 KB⌉ and ⌈2*b* / 64 KB⌉.
- `IoPortRange::contains(port, width)`, `ioport_check(range, port, width, value)`, `trace_index(seq, entries)`.
- Unchanged: the mapping check (now with *E*), `firing_instant`, `bandwidth`, `IrqSource::from_raw` (with kind 3).

## 8. What pass 12 of the reference model must cover

The reference model is tested with two page sizes (D-121: 4 KB with *E* = 512 and *L* = 4, and a second geometry with a larger page), so that no constant stays hidden in it. The new groups take the number of nodes as a parameter, with phantom nodes whose steps the model chooses, so that the rules between nodes are explored on one core.

### 8.1 The settled problems of pass 11

States to add: the clean mark covering the padding; the recorded fault of a thread (kind and five words); the pending parameters of a context; the change list and the no-context list of a node; the list of devices of an `iommu`; the runs of frames of a module.

Invariants:

1. Between two steps of a creation, the memory from the watermark to the clean mark is all zero, the padding included; the last step stops at the end of the object.
2. A fault *no context* is never delivered to a receiver without an own context; when it is not delivered, the faulting thread is suspended with the fault recorded, and no second fault is raised in the event.
3. A thread has a recorded fault only while it is suspended; `thread_resume` clears it.
4. When several contexts enter queues in one event, their order of entry is the order of the change list; the faults *no context* of an event are raised in the order of the no-context list. No order depends on an object's address or age.
5. A context's parameters in force change only at a replenishment or a reset of the wake-up rule; a replenishment that leaves *r* ≤ 0 exhausts the context again in the same event.
6. Nothing is delivered to a dying notify: no signal from a timer or an interrupt.
7. An `iommu` with no device attached is destroyed in one step; each step detaches at most 32.
8. The frames of a module cover it exactly, in order, in consecutive slots.
9. A step of a removal puts at most 96 contexts in a new queue position, a step of `task_revoke` at most 32, any other call at most 4.

### 8.2 Memory and devices between nodes, and the gate

States: per chunk an ownership word, a map count and the page classes of its pages; the device table; per node its generation, its blocks, its grant table and use table, its remote slots; the global read-only set.

Invariants:

1. Only the owner writes a word, except a take by compare-and-swap of an unclaimed word, a word of a dead node, or a word of a reserve by the holder of its role.
2. A chunk is covered by at most one block.
3. An object lies on memory whose word is *taken* by the current generation of the object's node, or on that node's floor.
4. A *free* word covers no object and no translation.
5. No word changes from or to *none* after machine start-up.
6. A node maps a run in its kernel space exactly when every word of the run reads *taken* by it with its generation.
7. (G) Every translation of a node leads only to memory it owns, memory granted to it and not revoked, the global read-only set, or device memory it owns; no table or gate page is mapped writable or to user; every map count equals the number of leaves that target its chunk.
8. A grant entry is live only while its anchor is in the granting node's list; every remote slot of a live grant has the serial of the entry; a revoked grant's memory returns to an untyped only after the holder reports no mapping under it.
9. `memory_give` never succeeds while a map count of the run is not 0, a piece of the block lives, or a grant covers it.
10. A slot never names a slot of another node.

### 8.3 Unlike cores

States: per kind its features, baseline and vector length; per thread its mask and the size of its save area; per node its own kind and the core it runs on; per context its counting mode, its instruction count and its hardware class.

Invariants:

1. The enabled set of a running thread is its node's baseline ∪ the optional features of its mask.
2. No node runs on a core whose kind lacks a feature or a vector length of the node's own kind.
3. A thread's save area is at least what its mask needs; `thread_set_features` never makes the mask need more.
4. The instruction count and the consumed time of a counted context change at the same events; an uncounted context's count is 0.
5. `thread_move` admits the destination context with the bandwidth it will have, and the destination thread's effective marks contain the source's.

### 8.4 Cores and roles

States, per node: the member word, its core and that core's hardware state (running, hung, in its NMI handler, INIT pending, parked, off, broken), its fence class, its beacons (heartbeat, idle until, panic, save seal, `acked`, `maps_of`, observations); per role its word and the unit state it governs (context entries, remapping entries, queue with writes in flight); a discrete clock with the times as small integers, and a global firmware stall that stops every core.

Safety invariants, in every reachable state:

1. **One owner.** Every chunk with a live object is covered by exactly one block of one node and generation.
2. **No live reference to reclaimed memory.** No translation of a core that is not stopped, no context entry and no write in flight reaches memory taken after a death by another node, unless made after that take.
3. **One writer per unit.** At most one core can write a unit's registers (mapped, or with a write in flight).
4. **Roles.** A unit role is never vacant, never held by a sealed or dead node; a role changes without its holder's write only when the holder is fenced, dead, or unfenced past `FENCE_NS` + `SETTLE_NS` (reserve: dead).
5. **Stop before reuse.** A node is dead only if its core is stopped and every node that could reach its memory has acknowledged or is stopped.
6. **Generations.** A node starts only from dead (generation + 1) or sealed (the same); a reference of an old generation is `gone`.
7. **The last node.** `core_stop` never leaves no live node.
8. **Audit.** Every word covered by a live block of a live node reads *taken* by that node and generation.

Liveness (for the model checked by state exploration, under fairness of the live nodes, stops that eventually succeed, firmware stalls shorter than `STALE_NS`, and one live node): every accused node becomes fenced, every fenced node dead; every unit role is eventually held by a live node; every request to a role holder is answered or its thread gets `gone`; a node that beats and consumes its rings is never accused with stale or stuck; from any state with one node crashed at any step, the others reach a state where every role is held by a live node and the crashed node is dead.

On one core: `core_stop` and `core_start` are always `busy`, every role is held by node 0, and the model's phantom nodes exercise the rest.

### 8.5 Debugging, I/O ports, entropy

Invariants:

1. For every ring, the next sequence is one more than the greatest sequence written, and the entry with sequence *s* is at index (*s* − 1) mod *N*.
2. The user ring holds only codes 16 and 17; the kernel ring never holds them; no call on `debug` changes the kernel ring.
3. `debug_write` of length *L* > 0 writes exactly ⌈*L* / 24⌉ consecutive entries, all but the last *continued*, with the caller's task identifier and effective marks; length 0 writes nothing.
4. In any window of 1 ms, at most 16 kernel entries of one code other than 6; every suppressed entry is counted once and reported by one entry of code 3.
5. A node record is accepted only if its commit equals the boot identifier; the fence handler never overwrites a committed record of the same generation; the previous crash area is never written.
6. Every `ioports` range lies inside its parent's; no successful port access touches a port refused to the caller's node; off x86-64 the three port calls return `unsupported`.
7. A bound endpoint or notify that is destroyed leaves the other unbound, its waiters untouched and its pending word kept; destroying a thread undoes at most 8 links in the stated order.
8. `entropy_read` changes no state but the generator's, and its errors follow the contract; its bytes are not compared.
9. A breakpoint word of a thread never names an address outside the user range; a hit is a fault of kind 9.

Outside the model (hardware, tested on QEMU and the machines): console output and pacing, the reading of IOMMU fault records, the warm reset and the handover of the previous area, the stub, the fence of a core, the gate's mechanism.

### 8.6 Two leftovers of pass 11

- **Invariant 16 was weakened** (commit `5d84989`) to "a thread that waits has no outcome yet, unless it waits on a fault that the kernel raised before it ran again". The strongest form that is true under the contract of 16 November 2026: **a thread that waits has no outcome yet, unless it waits as a caller on a fault of kind 7 (*no address space*) or kind 8 (*no context*) that the kernel raised after its last call ended and before it ran again; its outcome is then the result of that last call, and word 0 of the fault is the address after that call.** Only those two kinds can be raised for a thread that has not run since its call ended: kind 7 at the choice, kind 8 at step 5 of an event; every other kind needs the thread to execute an instruction, which consumes its outcome first. Pass 12 restores the check with the kind named, so that a page fault that waits with an outcome is again a failure.
- **The coverage floor of `sent_refused`** fell from 1 (commit `517b289`) to 0 (commit `6aaf4cc`), so the property test no longer proves that a `send` whose listed move the depth rule refuses at delivery is reached. Pass 12 restores `at_least([reached.sent, reached.sent_refused], [4, 1])` and, if the random seeds do not reach it, adds a directed case: a receiver waiting with a receive range in a space whose root is at least as deep as the root of the space being moved, so that the capabilities are dropped at delivery and `send` returns the flag `caps_dropped`.
