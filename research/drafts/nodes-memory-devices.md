# Draft: memory that changes node, devices that follow their driver

Written 15 November 2026 for the two owners, in answer to D-112 ("a dynamic allocation between nodes is to be designed"; "a design where devices follow their driver is to be written"). Nothing under `/Users/btw/Documents/repos` was edited. Verification marks: "verified" means checked on the web today, with the source in part 6; "from memory" means not checked.

**Verdict in one paragraph.** A is sound, and simpler than the brief feared: with a rule that only the owner of a chunk writes its word, the transfer needs **no message between kernels and no compare-and-swap**. The giver writes "free, owned by Y" as its last act on the chunk, and Y takes it when its memory service asks. Every crash leaves each word in a state that one rule resolves. Its real cost is not in the kernel. A chunk can leave a node only when nothing made from it lives, so the memory service must keep movable memory apart from pinned memory, as Linux must with `ZONE_MOVABLE`. B is sound for the data path (MMIO, DMA, MSI keep running while the node that drives the shared hardware is reloaded), and I found no precedent for that exact property. It does not remove three things: one node stays in the trusted base of every other node for DMA; every IOMMU *change* waits for that node during its reload, including the kill or restart of a driver; and legacy line interrupts (ACPI SCI, PS/2) stop.

---

## 1. The design

### 1.1 Why ownership must move: the alternative of fixed shares and remote frames

Today (D-107, [Start-up state](kernel-interface.md#start-up-state) rule 4), memory is split equally and never moves. A process larger than its home node's share takes frames made on other nodes and maps them remotely.

What happens to a process P whose home is B and which uses frames made on node A, when A is reloaded:

1. D-107: a reloaded kernel adopts nothing. The frames are objects of A, so they die with A's generation. Every reference to them returns `gone`.
2. B must remove every translation to A's frames before the new A reuses that memory. Otherwise P could read A's new kernel objects. This is the quarantine of the [memory ownership invariant](kernel.md#multi-core-structure).
3. P has lost part of its memory with no warning. A native process cannot continue, and a Wasm instance whose linear memory had pages there is corrupt. P dies, or its supervisor restarts it.

So with fixed shares, a process depends on **every node whose memory it uses**. On 24 cores and 64 GB a share is about 2.6 GB, so a 10 GB process depends on four nodes, and a reload of any one of them kills it. That contradicts D-108 ("If another node of the group is lost the process loses the threads that ran there ... and continues"). It also turns every private mapping of a large process into a remote mapping, recorded on both sides with a message per change.

With chunks that change owner (A below), the memory service moves memory to the process's home node before it makes the frames. A process then depends on its home node alone, which is what D-108 already promises. Remote mappings stay, but only for memory that really is shared between two processes on two nodes (rings, buffers).

What fixed shares do better: no shared writable table, no transfer rule, and D-107 holds word for word. That is the whole of their advantage.

**Decision recommended:** A for private memory, and remote frames only for sharing. A *pool* of chunks that the memory service hands out takes the role the "share" had.

### 1.2 A. Chunks, floors and the ownership table

#### Words

- A **chunk** is 2 MB of physical memory, aligned on 2 MB.
- A node's **floor** is the memory fixed to it at start-up that never moves. It is the "share" of D-107, made small.
- A **run** is 2^k contiguous chunks, naturally aligned, with 0 ≤ k ≤ 9 (2 MB to 1 GB).
- A **block** is the untyped object that a node makes from a run of ordinary memory, or from an entry of the device table, by `memory_take`.
- The **ownership table** has one word per chunk. The **device table** has one entry per block of device memory. Together they form the writable part of the machine table.
- The **hardware node** is the one node that drives the shared interrupt and IOMMU hardware (part B).

#### Chunk size: 2 MB, fixed on every machine (design choice)

| Option | Table for 1 TB | Table for 4 GB | Effect |
|---|---|---|---|
| **2 MB (chosen)** | 512 Ki words, 4 MB (0.4 ‰ of RAM) | 2 Ki words, 16 KB | The large-page size, so a 2 MB frame never straddles two owners. It equals `SHARE_ALIGN`, already in `abi/`. A 4 GB machine still has about 1,900 movable chunks |
| 1 GB | 1 Ki words | 4 words | Too coarse for small machines: on 2 cores and 4 GB, two floors leave three movable chunks |
| Per machine (for example RAM / 4096) | 4 Ki words | 4 Ki words of 1 MB | Below 2 MB on small machines, which breaks 2 MB pages. Adds a parameter to every computation, and saves only table memory, which is already negligible |

- A transfer moves a run of up to 512 chunks (1 GB) as one block, so a 1 GB page is possible on moved memory, and no call touches more than 512 words.
- Linux makes memory movable for hotplug in blocks of 128 MiB on x86-64, and uses 2 GiB blocks from 64 GiB of RAM up (verified, part 6). It chose that size to reduce the number of sysfs entries, a constraint that does not exist here.
- **Cost of the choice:** a block made on moved memory is at most 1 GB, so a frame of 512 pages of 1 GB (512 GB) can be made only on a floor. One frame of 1 GB pages is at most 1 GB on moved memory. That is acceptable: such a frame is a convenience, and several frames do the same work.

#### The floor of each node, on any machine (design choice)

A floor must let a node restart without asking anyone. On the two **anchor** nodes it must also let the supervisor and the memory service restart (D-108: they exist on two home nodes). The floor sizes come from the **boot image**, because only the boot image knows what its services need. The kernel applies a fixed rule and chooses no number itself, which keeps the start-up state "determined by the machine, the boot image and the kept memory".

- The boot image states three numbers: `floor_node` (bytes), `floor_anchor` (bytes) and `floor_anchor_per_gib` (bytes per GiB of ordinary memory).
- With *O* the ordinary memory in GiB, the floor of every node is `align_up(floor_node, 2 MB)`. Nodes 0 and 1 (node 0 alone on a machine with one usable core) are the anchors. Each of them adds `align_up(floor_anchor + floor_anchor_per_gib × O, 2 MB)`.
- The kernel refuses to start, with a message on the serial console, if the floors and the image region do not fit in ordinary memory.
- Recommended values, to be measured (part 4): `floor_node` = 16 MB (the node agent, its tables and its stacks, and a first pool of zeroed pages); `floor_anchor` = 64 MB (supervisor and memory service); `floor_anchor_per_gib` = 1 MB. The memory service's metadata grows with RAM: one record per chunk and per handed-out frame, estimated at 0.1 % of RAM, from memory.

| Machine | Floors | Share of RAM fixed | Movable |
|---|---|---|---|
| 2 cores, 4 GB | 2 × (16 + 68) = 168 MB | 4.1 % | ≈ 3.8 GB |
| 24 cores, 64 GB | 2 × (16 + 128) + 22 × 16 = 640 MB | 1.0 % | ≈ 63 GB |
| 128 cores, 1 TB | 2 × (16 + 1,088) + 126 × 16 = 4,224 MB | 0.4 % | ≈ 1,020 GB |

Why a kernel-enforced floor and not just a policy of the memory service: a memory service with a bug, or one that is dead, must not be able to leave a node with nothing to restart from. `memory_give` cannot give a floor, because a floor is not made of chunk words.

#### Where everything sits at start-up

1. **Kept**, as today (plus the two tables, and the kernel page tables that map the node's own memory, sized for all RAM at 2 MB per entry).
2. **Image region**, as today. It is part of node 0's floor.
3. The ordinary memory is cut into 2 MB chunks. The pieces smaller than 2 MB at the edges of each range go to node 0's floor.
4. **Floors** are taken from the chunks in ascending address order: node 0's first (after the image region), then node 1's, and so on. Each floor is recorded in the read-only part of the machine table as a list of ranges, and copied into the entry `Floors`.
5. **Every other chunk** has the word *free, owner 0*. Node 0 is the boot node, and at start-up it is also the hardware node. These free chunks are the **pool**. They give no capability at start-up. The first process takes what it needs with `memory_take` (in 1 GB runs, 1,024 calls for 1 TB).
6. **Device memory**: the blocks cut today by the rule of rule 6 become the first entries of the device table, *free, owner 0*. The table holds those entries plus 8,192 unused entries (provisional) for splits. No device untyped is given at start-up any more.

What is lost if node 0 dies: no memory. The free chunks it owned stay its own. They cannot be taken until node 0 is reloaded, because only the owner writes. They become available again to its next generation. For the time of the reload, the pool is unavailable to others. The recommended policy, which is the memory service's and not the kernel's, is that the memory service gives half of the spare pool to each anchor as soon as both run, so that one reload leaves half the pool usable.

#### The ownership word (design choice: one word per chunk, written by its owner only)

```
bits 0-1   state: 0 none, 1 free, 2 taken, 3 never written (a word with 3 fails its check)
bits 2-15  check: the top 14 bits of (v × 0x9E37_79B9_7F4A_7C15) mod 2^64,
           where v = state | owner << 2 | generation << 18 (50 bits)
bits 16-31 owner: a node index
bits 32-63 generation: the owner's generation when it took the chunk (taken); 0 when free
```

- **none** (the word is all zero, and its check is 0): the chunk is not ordinary memory, or it is kept, in the image region or in a floor. This never changes after start-up.
- **free**: it belongs to the owner, and no block of it exists.
- **taken**: it belongs to the owner, and a block made by that generation of the owner covers it. If the generation is not the owner's current one, the block died with the node, and the chunk is free for the current generation (see *Reload*).

**The single-writer rule.** A kernel writes a word only if the word's owner is its own node, whatever generation is in it. Its writes are: free → taken (`memory_take`); taken → free with the same owner (destruction of a block); taken → free with **another** owner (`memory_give`). The last one is the final write that node ever makes to that word. So at any instant one kernel at most may write a word. Two kernels never race on a word, and no compare-and-swap is needed. Every kernel may read every word; an aligned 64-bit load is atomic.

Alternatives considered:

- **Compare-and-swap by any kernel.** It has the same number of states, and lets a faulty kernel take any chunk by one atomic operation. The single writer makes the protocol a sequence of local writes.
- **One bitmap per node, each in that node's own memory.** A faulty kernel could corrupt only its own claims. But "who owns chunk *c*" means reading *n* maps, and the leak and double-claim windows need a third state. It is better for containment and worse in everything else. I rank it second. The owners may prefer it, see part 5.
- **No shared table at all,** with each node keeping its list and a reloaded node asking every live node. That fails when two nodes die together: neither list says which of the two owned a chunk.

**Containment.** The table is the one structure that every kernel maps writable. The rings between kernels are already shared and writable, so the rule "each kernel maps only its own memory" already admits shared communication structures that are validated on every read. The table is treated the same way:

- every read checks the check field;
- a word that fails is treated as owned by another node (`busy`), and the kernel writes a trace record;
- a kernel's own memory is mapped in its own address space only while it holds the chunk, by `memory_take`, and is unmapped by `memory_give` or by destruction.

The check catches stray writes of usual values (zero, a pointer, a small integer). It does not catch a deliberate write: ring-0 code can do anything, and containment only protects against bugs.

#### The object `memory_control`

One per node. It is made at start-up and never from an untyped, like `irq_control`. It is the authority to take, give and split the blocks of its node. Its root capability is in slot 12 of the node's start-up space. A block's capability is a child of the `memory_control` capability through which it was taken (as an `irq` is a child of `irq_control`), so `cap_revoke` on a `memory_control` capability destroys every block taken through it.

**(design choice:** the alternative, a block made as a root at depth 1, cannot be placed in a memory service's space under the depth rule of D-103, and could not be revoked from one place.**)**

#### Calls

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `memory_take` | memory_control, kind, place, size, destination | | `manage` on the memory_control. Kind 0: a run of ordinary memory; *place* is its physical base and *size* its log2 (21 to 30). Kind 1: an entry of the device table; *place* is its index and *size* must be 0. Makes a block: an untyped whose capability is a child of the memory_control capability |
| `memory_give` | memory_control, untyped, node | | `manage` on the memory_control, `write` on the untyped, which must be a block capability of the memory_control's node (`invalid`, judged right after its three checks). Destroys the block and gives its chunks, or its device entry, to *node* |
| `memory_split` | memory_control, untyped | index of the new entry | `manage` on the memory_control, which must be the hardware node's (`invalid`, judged right after its three checks). `write` on the untyped, which must be a block capability of a device entry, of more than 4 KB (`invalid`, judged right after its three checks). Cuts the entry into two halves |

**Checks of `memory_take`**, in the order of [Order of checks](kernel-interface.md#order-of-checks):

1. The memory_control: slot, kind, `manage`. A dying one is `gone`.
2. The destination: its `via` capability and its range.
3. The plain arguments, each `invalid` if it fails:
   - the kind is 0 or 1;
   - kind 0: the size is from 21 to 30; the place is a multiple of 2^size; the run lies inside the ownership table (computed without overflow); no word of the run is *none*;
   - kind 1: the size is 0; the place is below the capacity of the device table;
   - then the depth checks: the new capability is one deeper than the memory_control capability, at most 64, and an untyped may be placed only in a space whose root is not deeper.
4. The state, in order:
   - `busy` if a word of the run (kind 0), or the entry's word (kind 1), fails its check, names another owner, or is *taken* with this node's current generation, or if the entry is unused;
   - `no_slot` if the destination is not empty.

**Effect of `memory_take`.**

- Each word becomes *taken (this node, its current generation)*, in ascending order.
- For kind 0, the kernel maps the run into its own address space with 2 MB entries.
- The new untyped is ordinary (kind 0) or device (kind 1). It covers the run or the entry's range, with its watermark at the start. Kind 0 has its clean mark at the start, because the memory is dirty: it may hold another node's objects. Kind 1 has no clean mark.
- Its capability has every right of an untyped, except `exec`. It has `exec` only if the kind is 0 and the memory_control capability has `exec`.
- The capability records that it is a block, its kind and its place.

**Checks of `memory_give`.**

1. The memory_control: slot, kind, `manage`.
2. The untyped: slot, kind, `write`, then whether it is a block capability of the memory_control's node (`invalid`). A dying one is `gone`.
3. The node: below the number of nodes, not this node, and not marked *removed* in the machine table (`invalid`).
4. The state: `busy` if the untyped capability has a descendant, then `busy` if a piece of it lives (its watermark is not at the start).

**Effect of `memory_give`.**

- The capability is removed and its slot becomes empty; the block is destroyed.
- For kind 0, the run is unmapped from the kernel's own address space and the local translations are invalidated.
- Each word becomes *free (node)*, in ascending order.
- **Nothing is sent to the other node (design choice).** Its kernel needs nothing until its memory service calls `memory_take`. The memory services tell each other by IPC. Why: an offer and an acceptance would add two states, a timeout and a case for each crash, and buy nothing, since a *free* chunk can never hold an object.
- The alternative, a give that waits for the other node, is what the brief suggested. It is not needed, because the target holds no kernel state for a chunk it has not taken.

**Checks and effect of `memory_split`.**

- Checks: the memory_control (slot, kind, `manage`, then whether it is the hardware node's, `invalid`); the untyped (slot, kind, `write`, then whether it is a block capability of a device entry of more than 4 KB, `invalid`).
- State: `busy` if the untyped has a descendant; `busy` if a piece lives; `busy` if the device table has no unused entry.
- Effect: the capability is removed; the entry keeps the lower half (its size is halved); the unused entry with the lowest index takes the upper half; both are *free (this node)*. The result is the index of the new entry.
- **Unused entries belong to the hardware node (design choice).** Only it splits, so even the unused entries have one writer. Device blocks start on the hardware node, and the platform service cuts them there once it has enumerated PCI, before it gives them to the drivers' nodes. A block that must be cut later is given back to the hardware node first.
- No merge exists: the layout of MMIO is fixed for a boot.

**Destruction of a block** (its capability removed by any removal): for kind 0, the run is unmapped from the kernel's own space and the words become *free (this node)*; for kind 1, the entry's word becomes *free (this node)*. This counts as one unit of the 32 of a step. It writes at most 512 words.

**Destruction of a `memory_control`.** Removing its root capability first removes the blocks taken through it, by the usual steps. The object then gives its memory back to no one, and the node cannot take blocks again until it is reloaded. That is the same rule as `irq_control`.

**Bounds.** `memory_take` reads and writes at most 512 words, and writes at most 512 entries of the kernel's own tables. `memory_give` writes at most 512 words, clears at most 512 entries and does one local invalidation. `memory_split` does constant work. None returns `again`.

**Calls through another node.** By rule 7, `memory_take` and `memory_give` on the `memory_control` of another node become a message, and the caller waits in *waiting for another node*. The recommended policy is that the memory service has a thread on every node (D-028), so these calls stay local.

#### Recovery: a kernel that dies in the middle of a transfer

Each word is resolved alone, so a run that is cut in two by a crash simply belongs to two nodes. The memory services reconcile by reading the table: its frame is in slot 13.

| Who dies, when | Words left | Result |
|---|---|---|
| Giver X, before it removes the block | *taken (X, g)* | The block dies with X. After X's reload these words are *taken* with an old generation, so they are free for X |
| Giver X, after k of n words were written | k words *free (Y)*, n − k words *taken (X, g)* | k chunks are Y's; n − k return to X after its reload |
| Target Y, before it takes | *free (Y)* | Still Y's. They cannot be taken until Y is reloaded, then they are free for it |
| Target Y, during `memory_take`, after k words | k words *taken (Y, g)*, the rest *free (Y)* | All Y's. The block was never made, or died with Y |
| Y, after taking | *taken (Y, g)* | Its objects are lost with Y (D-107). After recovery, the chunks are free for Y's new generation |
| A node removed for a hardware fault | every word it owns | The recovery protocol names a successor node, which becomes the writer of those words. This is a hook for the cores group |

**Reload (design choice).** A reloaded node of generation *g* takes nothing automatically. Its first process reads the table and calls `memory_take`, which accepts *taken* words whose generation is not *g* as free. This is safe only because `core_start` runs after the recovery protocol has confirmed that no live node, and no device, holds a translation to the dead generation's memory: the order "isolate, reset, reclaim, reload" of [Recovery](kernel.md#recovery-of-one-cores-kernel). The cores group must guarantee that order, and this design depends on it. Generations are compared for equality, not order, so wrap-around is harmless.

**Invariants** (for the reference model):

1. Only the owner writes a word.
2. A chunk is covered by at most one block.
3. An object lies on memory whose word is *taken* by the current generation of the object's node, or on that node's floor.
4. A word that is *free* covers no object and no translation.
5. No word ever changes from *none* or to *none* after start-up.

#### What A asks of the memory service (not the kernel)

- **Movable and pinned chunks.** A run can be given away only when nothing made from it lives. One thread object pins a whole 1 GB block, which is the problem `ZONE_MOVABLE` solves in Linux (verified, part 6). The memory service makes kernel objects (threads, spaces, endpoints, page tables of address spaces) from a few dedicated small runs, and frames from the others. To free a run of frames, it migrates them: it copies the contents, remaps, and deletes the old frames. It cannot migrate frames that are pinned for DMA.
- **Where a process's memory comes from.** Its home node. The memory service gives runs to that node before it makes the process's frames.
- **Compression and preloading** of memory are the user-space memory service's job, not the kernel's. The kernel only provides the blocks.

### 1.3 B. Devices that follow their driver

#### What the hardware imposes (verified unless marked)

- **How an MSI or MSI-X targets a core.** The device writes the data word to an address in 0xFEEx_xxxx. In the compatibility format, the destination APIC ID is in bits 19:12 of the address and the vector is in bits 7:0 of the data. Moving the interrupt to another core then means rewriting the address in the device: the MSI capability in configuration space, or the MSI-X table entry in a BAR (verified).
- **With interrupt remapping,** bit 4 of the address selects the remappable format. The address carries a handle into the **interrupt remapping table**, one table per IOMMU unit. The entry holds the destination, the vector, edge or level, and source validation (the requester ID). Moving the interrupt means rewriting the entry and invalidating the interrupt entry cache, with no change in the device. In the remapped format, destination and vector sit in the low 64 bits of the 128-bit entry, so a move is one aligned 64-bit store (layout from memory). Linux uses `cmpxchg16b` only for the posted format, whose fields straddle both halves (verified).
- **Interrupt remapping needs queued invalidation.** The interrupt entry cache can be invalidated only through the invalidation queue (verified). Once the queue is on, register-based invalidation may not be used, and from VT-d version 6 it does not exist (verified). So each unit has **one** invalidation queue: one ring with a head and a tail register, and no second queue on VT-d (from memory). It must have one writer, or a lock shared between kernels.
- **Adding a translation needs no invalidation** when the unit reports caching mode 0, which is the case on real hardware; caching mode is set by emulated IOMMUs. Only removing or reducing a translation needs one (verified through the readings of the Linux and Xen maintainers, not through the text of the specification). A unit that requires write-buffer flushing (RWBF) needs a register write after every table update (from memory).
- **The IOAPIC** is programmed through an index register and a data register, a two-step access that cannot be shared between kernels without a lock (from memory).

#### The device table

Device memory is recorded like RAM, but by **entries** and not by fixed chunks, because the MMIO holes span up to 2^MAXPHYADDR (64 TB for 46 bits) and cannot be covered by one word per 2 MB.

- An entry is 16 bytes: `base | log2 size` (base aligned on its size, at least 4 KB; log2 in bits 0-5; bit 6 set when the entry is used), then an ownership word of the format above.
- Its capacity is fixed at start-up: the boot cut plus 8,192 entries (provisional; 16 B each, so about 130 KB kept).
- A driver's node takes its device blocks (`memory_take` kind 1), maps their frames into its own address space, and gives them back or onward by `memory_give`. A device whose BAR shares a 4 KB page with another device's BAR goes to the same node as that device. PCI firmware usually aligns BARs on at least 4 KB on x86 for this reason (from memory).

#### The hardware node (design choice)

**Exactly one node at a time drives the shared hardware.** It drives:

- the registers of the IOMMU units, their invalidation queues, their fault records, the root and context tables, and the domain numbers;
- the interrupt remapping table;
- the IOAPICs.

At machine start it is the boot node. Its index is in the machine table and in the entry `Node`. It changes only when its core is removed for a hardware fault, by the recovery protocol, which names the next one: a hook for the cores group.

- Why one: the invalidation queue and the IOAPIC each need one writer, and D-026 forbids a lock between kernels.
- The alternatives: a lock in the shared hardware, which D-026 rejects; or one queue per node, which VT-d does not have. SMMUv3.3 adds per-CPU command queues (ECMDQ) on Arm (from memory), so an Arm port could let each node invalidate for itself.

**What stays with the owner of the device** (the node where its driver runs):

- the device blocks (MMIO) and the frames made from them;
- the `iospace` and **all its tables**, made from the owner's memory;
- the vectors claimed through the owner's `irq_control`. The remapping handle is already *node × 192 + vector − 48*, so the handles of different nodes never overlap;
- the authoritative record of which devices an `iospace` serves, and under which domain number (the iospace's header);
- `iospace_map`, which writes only the owner's own tables: **no message to the hardware node** (caching mode 0). If a unit reports caching mode 1 or RWBF, the start-up page says so (entry `Memory`, flags bit 0), and every `iospace_map` then also goes through the hardware node.

**What goes through the hardware node** (a request; the caller waits in *waiting for another node*):

| Change | Request |
|---|---|
| `iospace_attach` with an iospace, or with 0 | write or clear the context entry, give or free the domain number, invalidate |
| `iospace_unmap` of a mapping in an iospace that serves devices; unhooking an empty table; the removal steps that undo such mappings (frame destruction, revocation, killing a driver), and the destruction of an iospace | invalidate (IOTLB, and the paging-structure caches for an unhook) and wait for the unit |
| `irq_claim` of an MSI on a node other than the hardware node | write the remapping entry, invalidate the interrupt entry cache |
| Destruction of such an `irq` | clear the entry, invalidate |
| A node moved to another core (D-108) | rewrite the destination of its at most 192 entries |
| Lines (IOAPIC) | claimed only through the hardware node's `irq_control`, as today for the boot node |

- **Requests are idempotent and are sent again whole** when the hardware node comes back. The waiting thread holds the request, so no queue in kernel memory is needed.
- For `iospace_attach`, the six states keep their order. The iospace's node sends with the request the iospace's unit, its number of devices, and whether it already lists the device. The hardware node then judges the six states in the written order.
- A thread that waits for another node is not ended by `thread_cancel` (the call succeeds and ends nothing). `task_revoke` stops it when its call returns. Its wait ends when the other node answers, or when the recovery protocol declares that node dead and it answers in its new generation.

#### When an ordinary node Y dies

Before Y's memory is reused (the *reclaim* step), the hardware node does the following:

- It clears every context entry whose iospace root table lies in memory owned by Y. It finds them by looking up the root pointer in the ownership table and the floors, with no help from the dead Y. This is a sweep of at most 65,536 entries per unit, in bounded steps.
- It clears Y's 192 remapping entries.
- It invalidates the caches.

Y's devices are then blocked; their drivers died with Y. The other nodes remove their translations to Y's frames. Their unmaps wait for the hardware node's invalidations as usual.

#### When the hardware node H is reloaded: what keeps running

**Without any software**, the hardware keeps doing the following, because the tables it reads are kept memory (the root and context tables, the remapping table, the IOAPIC registers) or the owners' memory (the iospace tables), and H's reload touches neither:

- **MMIO**: the driver's address space is on its own node.
- **DMA**: the unit walks the context entries and the owner's tables. The unit is never turned off.
- **MSI**: a device writes its handle, and the unit delivers to the owner's core with no software in the path.

**H's new generation (H′) proceeds in order:**

1. It boots from kept memory only. It does not turn the units off, and it does not reload their root pointers.
2. It drains each invalidation queue: it waits for head = tail, at most 1 ms. If the queue error bit is set, it overwrites the faulty descriptor with a wait descriptor that has no status write, and clears the error (from memory).
3. It clears every context entry whose tables lie in H's own memory, and H's own remapping entries. Their drivers died with H.
4. It asks each live node for its report: its iospaces that serve devices (unit, device, root table address, domain number) and its claimed MSI vectors with their requester IDs. This is at most one message per iospace and 192 entries per node, in bounded messages.
5. It compares every context entry and every remapping entry with the reports. Matching entries stay untouched. Different ones are rewritten. Entries that no live owner claims are cleared. It rebuilds the domain-number maps from the reports.
6. It does one global invalidation of each unit (context cache, IOTLB, interrupt entry cache). This also covers the unmaps that other nodes made while H was away, whose memory was never reused because their threads were still waiting.
7. It masks every IOAPIC input. The lines were H's objects, and they died with it.
8. It announces itself. The other nodes send their pending requests again.
9. Only then does H′ take the memory of its old generation (*Reload* above).

| What | During H's reload | What a driver on another node sees |
|---|---|---|
| MMIO, DMA through existing mappings, MSI arrivals | Continue | Nothing |
| `iospace_map` | Continues (caching mode 0) | Nothing |
| `iospace_unmap` with devices attached, the destruction of a mapped frame, revocation, killing or restarting a driver, `iospace_attach`, `irq_claim` of an MSI, destruction of an `irq`, moving a node | Waits | The call takes longer, with no error |
| Line interrupts (ACPI SCI, PS/2, legacy INTx) | Stop. Their drivers ran on H, so they die and are restarted | Power button, lid and laptop keyboard dead for that time |
| PCI configuration space through the platform service, if it runs on H | Waits for the restart of the platform service | Configuration accesses by IPC fail with `gone` and are retried (user-space protocol) |

**How long things wait.** The wait lasts the recovery time of H: detection (the heartbeat period, not yet set), isolation, reclaim confirmations, the start of the kernel, and the rebuild of steps 2 to 8. The rebuild handles at most 65,536 remapping entries and the context entries of every unit, which is microseconds to a few milliseconds of memory work (estimate, from memory). No figure for the whole wait exists. The target I propose for a gate is that changes resume within 50 ms of detection on the reference desktop, and that the data path stalls for no time at all.

#### Precedents

- **Linux kdump.** A crash kernel that finds translation on copies the old kernel's VT-d translation tables (Roedel, 2015), so existing mappings survive until each driver takes over. The AMD driver does the same (verified). The remapping table is copied in the same way (from memory). This is the closest precedent for "a reloaded kernel keeps DMA alive". It **adopts** the tables, whereas H′ *verifies* them against the owners, which keeps D-107's rule against adopting.
- **Barrelfish.** Drivers run on any core. Kaluga starts them. Interrupt routing to any core is computed as a constraint problem, and the driver receives an interrupt capability (verified, Barrelfish HPET report and the 2017 interrupt-routing paper). Barrelfish/DC states that it does not consider fault tolerance (D-107). I found no Barrelfish work on keeping devices running while the core that drives the IOMMU is replaced.
- **Hive (SOSP 1995)** lends page frames between cells, and on a cell failure discards the pages that the failed cell could write. That is a precedent for A and for quarantine, with no IOMMU (verified through summaries; to re-read in the paper).
- **No precedent found:** device ownership that follows the driver across independent kernels with one designated hardware node; reloading that node while other kernels' devices keep their DMA and MSI; and rebuilding its state from the owners instead of from the tables.

---

## 2. Text changes

### 2.1 kernel-interface.md

**Rule 3.** Replace

> the interrupt table of each node and its `irq_control`; the interrupt remapping table; the tables of the IOMMU units and their `iommu` objects; the clock page.

with

> the interrupt table of each node and its `irq_control`; the `memory_control` of each node; the ownership table and the device table; the interrupt remapping table; the tables of the IOMMU units and their `iommu` objects; the clock page; the tables through which each kernel maps its own memory.

**Rule 7.** Add after the existing text:

> Memory belongs to one node at a time: each 2 MB chunk of ordinary memory and each block of device memory has one owner, recorded in the ownership tables, and only the owner writes that record (see [Memory and devices between nodes](#memory-and-devices-between-nodes)).

**Objects table.** Add after `iommu`:

> | `memory_control` | The authority to take, give and split the blocks of memory of one node. One per node, made at start-up | Project |

**Paragraph after the objects table.** Replace

> Device memory (MMIO) is an `untyped` marked as device memory; it can only become a `frame` that is mapped, or a child `untyped`, never a kernel object.

with

> Device memory (MMIO) is an `untyped` marked as device memory; it can only become a `frame` that is mapped, or a child `untyped`, never a kernel object. It belongs to the node that took it from the device table, normally the node where its driver runs.

**System calls.** Replace "48 calls." with "51 calls.". Replace the Memory row with:

> | Memory | `untyped_retype`, `aspace_map`, `aspace_unmap`, `aspace_protect`, `memory_take`, `memory_give`, `memory_split` | `aspace_map` maps up to 512 pages of one frame, so one call maps up to 2 MB, 1 GB or 512 GB depending on the page size of the frame. `memory_take` and `memory_give` move memory between nodes in runs of up to 1 GB |

**Order of checks, item 3.** Replace "a kind that is never made from an untyped (`irq`, `irq_control`, `iommu`) is `invalid` (D-110)" with "a kind that is never made from an untyped (`irq`, `irq_control`, `iommu`, `memory_control`) is `invalid` (D-110)".

**`untyped_retype` row.** Replace "An `irq`, an `irq_control` or an `iommu` is never made by this call (`invalid`, D-110)." with "An `irq`, an `irq_control`, an `iommu` or a `memory_control` is never made by this call (`invalid`, D-110)."

**TLB, several cores.** Replace

> Meanwhile the calling thread waits in a state reserved for this, *waiting for the core group*, which the one-core reference never uses.

with

> Meanwhile the calling thread waits in a state reserved for this, *waiting for another node*, which the one-core reference never uses. The same state serves the requests to the hardware node and every call on an object of another node (rule 7). `thread_cancel` does not end it (the call succeeds and ends nothing), and `task_revoke` stops such a thread when its call returns. The wait ends when the other node answers, or answers in its new generation after the recovery protocol has declared it dead.

**IOMMU, first bullet.** Replace "The units are driven by the kernel of the boot node." with "The units are driven by the kernel of the hardware node ([Memory and devices between nodes](#memory-and-devices-between-nodes)); the tables of every `iospace` are in the memory of the iospace's own node."

**IOMMU, `iommu` objects.** After "with its root capability in the start-up space (see [Start-up state](#start-up-state))", add: "of the hardware node. A reloaded hardware node makes them again; the old ones are `gone` for their holders and their loss detaches nothing: the attachments are rebuilt from the iospaces that hold them."

**`iospace_unmap` row.** Replace "If the iospace serves devices, the unit's translation cache is invalidated before the call returns" with "If the iospace serves devices, the unit's translation cache is invalidated before the call returns, by the hardware node: a call made on another node waits for it".

**IOMMU, invalidations.** Replace "A unit that does not confirm within 1 ms (provisional) is a hardware fault of the node that owns it" with "A unit that does not confirm within 1 ms (provisional) is a hardware fault of the hardware node".

**Interrupts, "Nodes." paragraph.** Replace

> Line interrupts can be claimed only through the `irq_control` of the boot node (`invalid` elsewhere, judged with the source). The inputs of the IOAPICs are shared by the whole machine, and one owner avoids a protocol between kernels for a legacy path (the ACPI SCI, PS/2, legacy INTx).

with

> Line interrupts can be claimed only through the `irq_control` of the hardware node (`invalid` elsewhere, judged with the source). The inputs of the IOAPICs are shared by the whole machine and programmed through an index and a data register, so one writer avoids a lock between kernels for a legacy path (the ACPI SCI, PS/2, legacy INTx). While the hardware node is reloaded, line interrupts stop.

In the source-word bullet, replace "or a line on a node other than the boot node" with "or a line on a node other than the hardware node".

**Interrupt remapping cache bullet.** Replace "The IOMMU units are driven by the kernel of the boot node ([IOMMU](#iommu)), so a claim on another node writes its remapping entry by a message between kernels (rule 7)." with "The remapping table is written by the hardware node ([Memory and devices between nodes](#memory-and-devices-between-nodes)), so a claim on another node writes its remapping entry by a request to it, and the caller waits; an arrival never involves the hardware node."

**New subsection**, placed after [Interrupts](#interrupts) and before [Tasks and marks](#tasks-and-marks):

> ### Memory and devices between nodes
>
> **Proposed, 15 November 2026: written, no reference model yet, not reviewed.** Answers D-112. It settles who owns memory and devices when there are several nodes, and fixes now what the one-core kernel and `abi/` must hold.
>
> #### Chunks, floors and the ownership table
>
> - Ordinary memory is cut into **chunks** of 2 MB, aligned on 2 MB. Each node has a **floor**, fixed at start-up, that never moves (see [Start-up state](#start-up-state)). Every other chunk has one **owner node** at a time.
> - The **ownership table** has one 64-bit word per chunk, from physical address 0 to the end of the highest ordinary memory. It is kept memory and part of the machine table. Word: bits 0-1 the state (0 none, 1 free, 2 taken, 3 invalid); bits 2-15 a check, the top 14 bits of (*v* × 0x9E37_79B9_7F4A_7C15) mod 2^64 with *v* = state | owner << 2 | generation << 18; bits 16-31 the owner; bits 32-63 the owner's generation when the word is taken, 0 otherwise. *None* (the word 0) marks a chunk that is not ordinary memory, kept, in the image region or in a floor; it never changes. *Free*: no block covers it. *Taken*: a block made by that generation of the owner covers it.
> - The **device table** has one 16-byte entry per block of device memory: base and log2 size (bits 0-5, bit 6 set when the entry is used), then an ownership word of the same format. Its capacity is fixed at start-up. Unused entries belong to the hardware node.
> - **Only the owner writes a word (design choice).** A kernel writes a word only if its owner is the kernel's node, whatever the generation in it. Its writes are: free to taken; taken to free with the same owner; and taken to free with another owner, its last write to that word. Any kernel reads any word. No compare-and-swap is used. Every read checks the check field; a word that fails counts as owned by another node and is traced. The alternatives, compare-and-swap by any kernel or one bitmap per node, are discussed in the draft of 15 November 2026.
> - **A block** is an untyped made from a run of chunks (2^*k* chunks naturally aligned, 0 ≤ *k* ≤ 9, so at most 1 GB) or from one device entry, by `memory_take`. Its capability is a child of the `memory_control` capability used, and records that it is a block, its kind and its place. A kernel maps a run of ordinary memory into its own address space only while it holds it as a block.
> - `memory_control` is one object per node, made at start-up and never from an untyped. Its root capability is in slot 12 of the node's start-up space.
>
> | Call | Arguments | Result | Rights and rules |
> |---|---|---|---|
> | `memory_take` | memory_control, kind, place, size, destination | | `manage` on the memory_control. Kind 0: *place* is the physical base of a run, *size* its log2 (21 to 30). Kind 1: *place* is a device-table index, *size* is 0 |
> | `memory_give` | memory_control, untyped, node | | `manage` on the memory_control; `write` on the untyped, which must be a block capability of the memory_control's node (`invalid`, judged right after its three checks) |
> | `memory_split` | memory_control, untyped | index of the new entry | `manage` on the memory_control, which must be the hardware node's (`invalid`, judged right after its three checks); `write` on the untyped, which must be a block capability of a device entry of more than 4 KB (`invalid`, judged right after its three checks) |
>
> Rules of `memory_take`:
>
> - Plain arguments, in order (`invalid`): the kind is 0 or 1. Kind 0: the size is 21 to 30, the place is a multiple of 2^size, the run lies inside the table (computed without overflow), and no word of the run is *none*. Kind 1: the size is 0 and the place is below the capacity. Then the depth checks: the new capability is one deeper than the memory_control capability, at most 64, and an untyped may be placed only in a space whose root is not deeper.
> - State, in order: `busy` if a word of the run, or the entry's word, fails its check, names another owner, or is *taken* with the node's current generation, or if the entry is unused; then `no_slot`.
> - Effect: each word becomes *taken* (this node, its current generation), in ascending order. A run is mapped into the kernel's own address space. The untyped is ordinary or device, with its watermark at the start. For ordinary memory the clean mark is at the start (the memory is dirty); device memory has no clean mark. Its capability has every right of an untyped, with `exec` only for ordinary memory taken through a memory_control capability that has `exec`.
> - A *taken* word whose generation is not the node's current one is accepted as free: its block died with an earlier generation. This is safe because a reloaded node starts only after the recovery protocol has confirmed that nothing translates to the memory of its dead generation ([Recovery](kernel.md#recovery-of-one-cores-kernel)).
>
> Rules of `memory_give`:
>
> - Plain argument (`invalid`): the node is below the number of nodes, is not this node, and is not marked removed in the machine table. State, in order: `busy` if the untyped capability has a descendant, then `busy` if a piece of it lives.
> - Effect: the capability is removed, its slot becomes empty and the block is destroyed. A run is unmapped from the kernel's own space and the local translations are invalidated. Each word becomes *free* (node), in ascending order.
> - **Nothing is sent to the other node (design choice).** It takes the memory with `memory_take` when its memory service asks; the memory services tell each other by IPC. A *free* chunk holds no object, so the target needs no kernel state before it takes it.
>
> Rules of `memory_split`: state, in order: `busy` if the untyped has a descendant, if a piece lives, or if no entry is unused. Effect: the capability is removed; the entry keeps the lower half and the unused entry of lowest index takes the upper half, both *free* (this node). Entries are never merged.
>
> - **Destruction of a block**, by any removal, unmaps a run from the kernel's own space and writes *free* (this node) into its words: one unit of the 32 of a step. Removing the root capability of a `memory_control` removes the blocks taken through it, then the object; the node takes no block until it is reloaded.
> - **Bounds.** Each call reads and writes at most 512 words and 512 entries of the kernel's own tables, and does at most one local invalidation. None returns `again`.
> - **A kernel that dies in a transfer.** Each word is resolved alone. A word *free* (Y) is Y's; a word *taken* by a dead generation is free for the owner's next generation; a word that a giver had not yet written stays the giver's. A run cut by a crash belongs to two nodes; the memory services reconcile by reading the table (slot 13). The words of a node removed for a hardware fault get a successor writer, named by the recovery protocol (cores group).
> - **What stays with the memory service:** where a process's memory comes from (its home node), the split between movable and pinned runs, migration, compression and preloading.
>
> #### The hardware node
>
> - **One node at a time, the hardware node, drives the shared hardware (design choice):** the registers, invalidation queues, fault records, root and context tables and domain numbers of the IOMMU units, the interrupt remapping table and the IOAPICs. At start-up it is the boot node. Its index is in the machine table and in the entry `Node`. It changes only when its core is removed for a hardware fault, by the recovery protocol (cores group). Why: each unit has one invalidation queue, and the IOAPIC is reached through an index and a data register; both need one writer, and kernels share no lock (D-026).
> - **What stays with the owner of a device:** its device blocks and their frames; its `iospace`, whose tables come from the owner's memory; its vectors, claimed through the owner's `irq_control`; and the record of the devices each iospace serves and of its domain number. `iospace_map` writes only the owner's tables and sends nothing, because a unit that reports caching mode 0 needs no invalidation when a translation is added. If a unit reports caching mode 1 or needs write-buffer flushing, bit 0 of the flags of the entry `Memory` is set, and every `iospace_map` also goes through the hardware node.
> - **What goes through the hardware node**, as a request for which the caller waits in *waiting for another node*: attaching or detaching a device; the invalidation after an unmap or the unhooking of a table in an iospace that serves devices, including those done by removal steps; writing, clearing or retargeting a remapping entry. For `iospace_attach`, the request carries the iospace's unit, its number of devices and whether it lists the device, and the hardware node judges the six states in their written order. Requests are idempotent; a node sends its pending requests again, whole, when the hardware node announces a new generation.
> - **When an ordinary node dies**, the hardware node, before that node's memory is reused, clears every context entry whose root table lies in memory the ownership table or the floors give to the dead node, clears its remapping entries, and invalidates. It needs nothing from the dead node.
> - **When the hardware node is reloaded**, MMIO, DMA through existing mappings and MSI arrivals continue: the hardware reads kept tables and the owners' tables, and the units are never turned off. The new generation:
>   1. drains each invalidation queue;
>   2. clears the context entries and remapping entries that lead to its own old memory;
>   3. asks every live node for its iospaces that serve devices and its claimed vectors;
>   4. keeps the entries that match, rewrites those that differ and clears those that no live owner claims;
>   5. rebuilds the domain numbers;
>   6. invalidates every unit globally;
>   7. masks every IOAPIC input;
>   8. announces itself;
>   9. only then takes the memory of its old generation.
>
>   Meanwhile the changes listed above wait, with no error, and line interrupts stop. It verifies the tables against the owners; it does not adopt them (D-107).

**Object sizes.** Replace the last row with:

> | `irq_control`, `iommu`, `memory_control` | Kernel memory kept at start-up; not made from an untyped |

**Start-up state, "Memory, by rule.":** replace items 1 and 4 to 6 with:

> 1. **Kept.** As before, plus the `memory_control` of the boot node, the ownership table and the device table, and the tables through which the kernel maps its own memory (sized for all ordinary memory in 2 MB entries).
>
> 4. **Chunks and floors.** Ordinary memory is cut into 2 MB chunks; the parts of a range smaller than a chunk go to the floor of node 0. Let *n* be the number of usable cores, *O* the ordinary memory in GiB, and `floor_node`, `floor_anchor`, `floor_anchor_per_gib` the three numbers the boot image states. Every node's floor is `floor_node` rounded up to 2 MB; nodes 0 and 1 (node 0 alone if *n* = 1), the anchors, add `floor_anchor + floor_anchor_per_gib × O` rounded up to 2 MB. Floors are taken in ascending address order, node 0 first, after the image region, which belongs to node 0's floor. The kernel refuses to start if they do not fit. A floor never changes (D-107). Floors and the core list are in the read-only part of the machine table; every other chunk has the word *free*, owner 0, and the device blocks of rule 6 are the first entries of the device table, *free*, owner 0, followed by 8,192 unused entries (provisional).
> 5. **Untypeds of the boot node.** The image untyped first, then each range of node 0's floor, cut by the rule of naturally aligned blocks as before. Other nodes' floors become the untypeds of their start-up space when the node is started. Chunks outside the floors give no capability at start-up; the first process takes them with `memory_take`. The clean mark rule is unchanged.
> 6. **Device memory.** Every physical address below 2^MAXPHYADDR that is not ordinary memory, not in the image region, not kept, and not of the UEFI type unusable memory, is cut into blocks by the same rule. Each block is an entry of the device table, owned by node 0, the hardware node at start-up. No device untyped is given at start-up; it is taken with `memory_take` by the node that will drive the device.

**Slots table.** Replace the rows "12-15 | empty" and "16 onwards":

> | 12 | the `memory_control` of the node |
> | 13 | the frame of the ownership tables, `read` only, made from no untyped (pages of 4 KB if the tables fit in 512 of them, otherwise of 2 MB); the device table starts at the offset the entry `Ownership` gives |
> | 14-15 | empty |
> | 16 onwards | contiguous, in this order: one `core` capability per core, in the order of the core list, so the boot core's is in slot 16; one `iommu` capability per IOMMU unit, in the order of the entry `Iommu`; then the untypeds: the image untyped, then the floor's blocks by ascending address; then one frame per module, in module order |

In "Number of slots", the untypeds are now the image untyped and the floor's blocks. In "Depth and rights", add: "The frame in slot 13 is the root of its object, at depth 1, with `read` only."

**Start-up page table.** Change rows 11, 12 and 15, and add 17:

> | 11 | Node | `StartNode` (24 bytes): this node's index, number of nodes, generation, index of the boot node, index of the hardware node, flags (bit 0 anchor) |
> | 12 | Floors | `StartShare` records (24 bytes): node, reserved, base, length of each range of each node's floor; sorted by node, then base |
> | 15 | Memory | `StartMemory` (40 bytes): ... as before, the last u32 becomes flags: bit 0, `iospace_map` goes through the hardware node (a unit with caching mode 1 or write-buffer flushing) |
> | 17 | Ownership | `StartOwnership` (32 bytes): number of words of the ownership table (u64), offset of the device table in the frame of slot 13 (u64), capacity of the device table, log2 of the chunk (21), log2 of the largest run (30), reserved (u32 each) |

**Hooks for a reloaded kernel.** Replace the first bullet with:

> - The floors, the core list, the boot node and the hardware node are in the read-only part of the machine table; the ownership words and the device table are its writable part, each word written only by its owner. A kernel that is reloaded on a node rebuilds the start-up state of that node from its floor by the same rules: the same slots 1 to 13, its floor's untypeds, no `core` capability and no device untyped; the `iommu` capabilities only if it is the hardware node. The memory it held beyond its floor is *taken* with an old generation, and its first process takes it again with `memory_take`. What its first thread runs is fixed by `core_start`.

**Points for the two owners.** Replace the sentence "**To measure with the multi-core trial:** whether a node may run on several cores at once (the three candidates of [kernel.md](kernel.md#nodes-cores-and-load)), and with it the share of memory per node and the node that owns the devices." with "**To measure with the multi-core trial:** whether a node may run on several cores at once (the three candidates of [kernel.md](kernel.md#nodes-cores-and-load)). The share of memory per node and the node that owns the devices are replaced by chunks that change owner and by the hardware node (D-112, proposed 15 November 2026)." Replace the two table rows "Share of memory per node" and "Devices and lines on the boot node" with:

> | Memory between nodes | A floor per node from three numbers of the boot image; every other 2 MB chunk has one owner, written only by it; `memory_give` writes the new owner and sends nothing | A: equal fixed shares and remote frames. B: one bitmap per node in its own memory. C: compare-and-swap by any kernel | Rule: one table every kernel maps writable, guarded by a check field; the memory service must separate movable and pinned memory. A: a process dies with any node whose memory it uses. B: better containment, *n* maps to read at recovery. C: same states, any kernel can take any chunk in one operation |
> | Devices and shared hardware | Devices, their `iospace` tables and their MSI vectors belong to the driver's node; one hardware node drives the IOMMU queues, the context and remapping tables and the IOAPICs, and rebuilds them from the owners after its reload | A: every device on the boot node (the earlier rule). B: a lock between kernels on the shared hardware | Rule: data path untouched by a reload of the hardware node; changes wait; lines stop; the hardware node is trusted by all for DMA. A: every driver loses MMIO when the boot node is reloaded. B: contradicts D-026 |

**Open points.** Replace the bullet "**The depth rule and a machine that does not die.** ..." ending "...as the root task of seL4 is." with a version that names the floors and slot 12 as placed hooks and keeps "the protocol is not". In the bullet "Left to the multi-core part by the D-110 groups", replace "which untyped pays for the tables of a remote copy of an address space" with "which block of the node that holds a remote copy of an address space pays for its tables (recommended: a block the memory service gives that node for the process)". Add:

> - Left to the cores group by the ownership tables: failure detection and the order isolate, reset, reclaim, reload, on which `memory_take` relies for words of a dead generation; the successor writer of the words of a node removed for a hardware fault; the choice of a new hardware node.

**Values to add to `abi/`:** see part 3.

### 2.2 kernel.md

**Multi-core structure, "Memory ownership invariant".** Replace

> - **Memory ownership invariant.** Nothing that a live kernel depends on is recorded only in another kernel. Every remote mapping is recorded on both sides. A reloaded kernel queries its neighbours before it reuses a page; a page whose status is unknown is put in quarantine.

with

> - **Memory ownership invariant.** Nothing that a live kernel depends on is recorded only in another kernel. Every 2 MB chunk of ordinary memory and every block of device memory has one owner node, recorded in the ownership tables and written only by that owner; a node keeps a small floor that never moves, and the rest moves between nodes by `memory_give` and `memory_take` (D-112, see [Memory and devices between nodes](kernel-interface.md#memory-and-devices-between-nodes)). Every remote mapping is recorded on both sides. A reloaded kernel reuses no memory before every live node, and the hardware node for the devices, has confirmed that nothing translates to the memory of its dead generation.

**Nodes, cores and load.** Replace "**A node is the state of one per-core kernel**, held in one block of memory with a defined, versioned format: the root of its capability tree, its scheduling state, its share of physical memory." with "... the root of its capability tree, its scheduling state, its floor of physical memory and its generation." Replace

> - **The share of physical memory belongs to the node** and is fixed at start-up (D-107). A node that is reloaded is rebuilt from its share.

with

> - **The floor of physical memory belongs to the node** and is fixed at start-up (D-107); it is enough to restart the node, and on the two anchor nodes the supervisor and the memory service. The rest of memory is in chunks that change owner, driven by the memory service. A node that is reloaded is rebuilt from its floor, then takes back the chunks it held.
> - **Shared hardware has one driving node**, the hardware node: the IOMMU units and the IOAPICs. Devices, their DMA tables and their MSI vectors belong to the node of their driver, and keep working while the hardware node is reloaded; only changes wait.

Replace "- **A process has a home node**, the one its memory comes from." with "- **A process has a home node**, the one its memory comes from: the memory service moves chunks to that node before it makes the process's frames, so a process does not depend on the nodes whose memory it does not share."

**Recovery of one core's kernel, item 3.** Replace

> 3. **Recovery.** The order is: isolate the core, reset the devices whose driver ran on it, reclaim the memory, reload the kernel.

with

> 3. **Recovery.** The order is: isolate the core, reset the devices whose driver ran on it, reclaim the memory (every live node removes its translations to the dead node's memory; the hardware node clears the context and remapping entries that lead there), reload the kernel. If the dead node was the hardware node, its new generation first rebuilds the IOMMU and remapping state from the reports of the live nodes, without turning the units off; meanwhile the devices of other nodes keep their MMIO, their DMA and their interrupts, and only IOMMU changes wait.

In the sequence diagram, replace `M->>A: which pages of B do you still map?` and the following line with:

```
    M->>A: remove your translations to B's memory
    A-->>M: done; the hardware node has invalidated the units
```

Then add after `V->>B: core_start with a kernel image`:

```
    Note over B: takes back with memory_take the chunks of its old generation
```

### 2.3 Elsewhere (not asked; listed so nothing contradicts)

- **memory.md**, "Physical memory per core": replace "The shares are fixed at start-up (D-107 ...); memory of another share is used through remote mappings recorded on both sides." with "Each kernel has a fixed floor (D-107); the rest of memory moves between kernels in 2 MB chunks, driven by the memory service; memory of another node is used through remote mappings recorded on both sides only when it is shared."
- **drivers.md**, IOMMU: add "A driver's `iospace` and its device memory belong to the node where the driver runs; one hardware node drives the IOMMU units, and its reload does not stop the devices of other nodes."
- **Decision log**, a new entry to propose: "D-113, proposed: chunks of 2 MB that change owner, one word per chunk written only by its owner, floors from the boot image; devices follow their driver, one hardware node, rebuilt from the owners. Amends D-107: the fixed share becomes the floor, and the machine table gains a writable part (the ownership words)." D-107 says the share is "fixed at start-up and read-only". The floor keeps that, but the machine table is no longer entirely read-only, so the owners must accept that amendment explicitly.

---

## 3. What the one-core kernel and `abi/` must contain now

On one core *n* = 1, so `memory_give` always returns `invalid` for its node. Everything else runs, and the reference model can take *n* as a parameter so that the table's rules (single writer, generations, crashes in the middle of a transfer) are explored with phantom nodes.

**In the one-core kernel:**

1. **Its own memory mapped by range, not by a direct map of all RAM.** The kernel maps its floor at start-up, and maps a run only from `memory_take` to its destruction. This must be true from the first line of the memory code, or containment cannot be added later.
2. **The ownership table and the device table** in kept memory, with the word format and its check, and the frame in slot 13.
3. **`memory_control`** (slot 12), the three calls, and the destruction hook of a block (unmap, then *free* words).
4. **Untyped state in the slot:** the block flag, the kind, and the place (chunk base or device index), next to the watermark and the clean mark. The 64-byte slot has room for this.
5. **A generation in the node block**, 1 at start-up, written in every *taken* word.
6. **One kernel function for "request to the hardware node"** (context entries, invalidations, remapping entries, IOAPIC). On one core it is a direct call. On several, it becomes a message, without changing any call's semantics.
7. **`iospace_map` never invalidates** (it does so only if the flag of the entry `Memory` says so), **and the iospace header records its domain number**. **The node keeps a list of its iospaces that serve devices** (a link in the iospace header), so that its report to a rebuilding hardware node is bounded.
8. **The state *waiting for another node*** in the thread object's state encoding, unused on one core.
9. **Start-up:** floors from the boot image, no device untyped, slots 12 and 13, and the entries `Node`, `Floors`, `Memory` (flags) and `Ownership`.

**In `abi/`** (numbers continue the contract's list):

- **Calls.** `MemoryTake = 48`, `MemoryGive = 49`, `MemorySplit = 50`.
- **Object kinds.** `MemoryControl = 19`. The entry `ObjectSizes` covers kinds 0 to 19 and gives 0 for 19.
- **Errors.** None new.
- **Constants.** `CHUNK_SHIFT = 21`, `CHUNK_BYTES = 2 * 1024 * 1024` (the same value as `SHARE_ALIGN`, which is renamed `CHUNK_BYTES`); `RUN_SHIFT_MAX = 30`; `RUN_MAX_CHUNKS = 512`; `DEVICE_TABLE_SPARE = 8192`; `MEMORY_KIND_ORDINARY = 0`, `MEMORY_KIND_DEVICE = 1`; `ANCHOR_NODES = 2`; `OWNERSHIP_CHECK_MUL: u64 = 0x9E37_79B9_7F4A_7C15`.
- **`Ownership(u64)`**: `none()`, `free(owner)`, `taken(owner, generation)`, `from_raw(u64) -> Option<Self>` (refuses a failed check and state 3), `state()`, `owner()`, `generation()`. Kani proofs: `from_raw` reads back exactly what each constructor wrote; `none()` is 0; `from_raw` refuses every word with state 3.
- **`DeviceEntry`**, `repr(C)`, 16 bytes: `base_and_size: u64`, `ownership: u64`. Bit 6 of the first word is `DEVICE_ENTRY_USED`.
- **Start-up.** `START_SLOT_MEMORY_CONTROL = 12`, `START_SLOT_OWNERSHIP = 13`. `StartKind::Floors = 12` (renamed from `Shares`; `StartShare` is unchanged). `StartKind::Ownership = 17`. `StartNode` grows to 24 bytes (six u32: index, nodes, generation, boot node, hardware node, flags), with `START_NODE_ANCHOR = 1`. The last u32 of `StartMemory` becomes `flags`, with `START_MEMORY_IOSPACE_MAP_VIA_HARDWARE = 1`. `StartOwnership`, `repr(C)`, 32 bytes: `ram_words: u64`, `device_offset: u64`, `device_entries: u32`, `chunk_shift: u32`, `run_shift_max: u32`, `reserved: u32`. Sizes asserted in `layouts_are_fixed`.
- **Boot image.** `BootFloors`, `repr(C)`, 24 bytes: `floor_node: u64`, `floor_anchor: u64`, `floor_anchor_per_gib: u64`, read by the loader with the entry point and the reserve of tables.
- **Pure function with a Kani proof.** `floors(ordinary_bytes, n, BootFloors) -> per-node sizes`: every size is a multiple of 2 MB, and the sum is computed without overflow.

---

## 4. What must be measured, and how, before it is decided

| Question | How | What decides |
|---|---|---|
| Do the reference desktop and the Dell report caching mode 0 and no write-buffer flushing? | Read the capability register of every DMAR unit at start-up (log CM, RWBF, C, QI and IR) on both machines | If not 0, every `iospace_map` crosses to the hardware node, and B's "map needs nothing" is lost on that machine |
| Data-path continuity during a reload of the hardware node | NVMe driver on node Y running a read and write load (fio-like); network driver on node Z under traffic; kill the hardware node 100 times | No I/O stall, MSI counters keep rising, no DMA fault in the trace. Gate: zero stall |
| How long changes wait | On the same runs, time from detection to the first answered `iospace_attach`, with 24 nodes and every device attached | The recovery gate. Proposed: under 50 ms after detection |
| Cost of an unmap through the hardware node | Microbenchmark: `iospace_unmap` from node Y against the same call on the hardware node; then 10,000 unmaps per second from 8 nodes | If the queue saturates, batch invalidations per request (a range or a domain), which needs no contract change beyond a bound |
| Cost of the global invalidation after a rebuild | Throughput of NVMe and the network for 100 ms around step 6 | If the dip is large, skip the global invalidation for units whose entries all matched (unsafe if H died between a write and its invalidation: to model first) |
| Floors | Footprint of the node agent, the supervisor and the memory service on QEMU with 2, 24 and 128 nodes and 4 GB to 1 TB | The three numbers of the boot image |
| Movable memory in practice | Replay memory-service traces (boot, desktop session, a 20 GB inference process); measure the share of runs that can be freed on demand, and the time to free 8 GB with migration | If pinned runs fragment memory, give kernel objects their own runs (policy), or lower the largest run to 2 MB for kernel objects |
| Table corruption | Fault injection: random stray writes into the table page from a kernel under test | How many the check catches; whether the owners prefer one bitmap per node (part 5) |
| Retargeting MSI when a node moves (D-108) | Time to rewrite 192 remapping entries plus one invalidation, through the hardware node | Whether parking a node may depend on the hardware node, or interrupts should go to the old core, which wakes |

---

## 5. Weaknesses I could not remove

1. **One node is trusted by every other node for DMA and interrupts.** A bug in the hardware node's kernel can write a context entry that lets a device write anywhere. Containment rule 1 does not hold for that node. Until its new generation verifies the tables (steps 3 to 6), a corrupt entry stays live. This was already true of the boot node in the current contract; B makes it explicit and does not remove it.
2. **Every IOMMU change waits for the hardware node during its reload.** That includes killing or restarting a driver, which undoes iospace mappings, attach and detach, hotplug, claiming an MSI, and moving a node to another core. Nothing fails, but these wait for the whole recovery time, which is not measured.
3. **Line interrupts stop during that reload**, and their drivers die with the hardware node, because the IOAPIC has one writer. On the Dell laptop this means the PS/2 keyboard, the lid and the power button (ACPI SCI), and possibly touchpads behind GPIO lines (from memory). The platform service, which needs the SCI, lives on the hardware node and restarts with it. The reference desktop (USB keyboard, MSI) is far less affected.
4. **The ownership table is writable by every kernel.** The check field catches stray writes of usual values, not every corruption. One bitmap per node would confine a faulty kernel to its own claims, at the cost of *n* maps to read at recovery and a third state. I rank it second; the owners may choose it.
5. **Pinned memory blocks transfers.** One kernel object pins a whole run. The memory service must separate movable and pinned runs and migrate frames, and frames pinned for DMA cannot move. A machine under pressure may be unable to move memory to where a process needs it, as Linux fails to offline memory without `ZONE_MOVABLE`.
6. **Free chunks of a node that is down cannot be used until it is back.** For node 0 at the beginning, that is the whole pool. The defence is a policy: spread the pool over the anchors. A node removed for good needs a successor writer, which belongs to the cores group and is not designed here.
7. **Blocks on moved memory are at most 1 GB**, so a 512 GB frame of 1 GB pages exists only on a floor.
8. **The global invalidation after a rebuild costs every device a burst of IOTLB misses.**
9. **One invalidation queue per unit serialises the unmaps of all nodes** through one kernel, at the cost of one message between kernels per unmap. drivers.md already asks for long-lived mappings, which keeps this rare. An emulated Linux driver that maps per request would feel it.
10. **`memory_take` of a dead generation's memory relies on the order of recovery** ("reload only after reclaim"), which the cores group has yet to specify and model. If that order is broken, a reloaded node can make objects in memory that a device or a remote mapping still reaches.

---

## 6. Sources

Verified on 15 November 2026 (web search, and pages fetched where named):

- Hive, fault containment and memory sharing between cells: the paper's PDF, https://pdos.csail.mit.edu/archive/6.824-2004/papers/hive.pdf (not readable by the fetch tool; the search summary and the following were used); course handout, https://pdos.csail.mit.edu/6.824-2004/handouts/hive.txt (firewall, losing data of the failed node); slides, https://www.sambuz.com/doc/hive-fault-containment-for-shared-memory-multiprocessors-presentation-771691 (page frames loaned between cells, given back when freed or on failure). To re-read in the paper.
- Linux memory hotplug, block sizes and `ZONE_MOVABLE`: https://docs.kernel.org/admin-guide/mm/memory-hotplug.html; 2 GiB blocks from 64 GiB, Tatashin's commit: https://lab.nexedi.cn/kirr/linux/-/commit/078eb6aa50dc50cd85f09a22226b7e238b3397ce
- Queued invalidation required for interrupt remapping: Linux commit https://git.phytec.com/phyus/linux-vybrid_public/commit/fe962e90cb17a8426e144dee970e77ed789d98ee; Zephyr commit https://pigweed.googlesource.com/third_party/github/zephyrproject-rtos/zephyr/+/2c904b379bf7e1f8301be37520e86d843672ff1e
- No register-based invalidation while queued invalidation is on, and none from VT-d version 6: Xen, https://lore.kernel.org/all/f4b3ad3b-16b9-5e42-c7a6-0c5c81b1f392@suse.com/; QEMU, https://git.cs.tu-dortmund.de/SYS-OSS/FRET-qemu/commit/ed7b8fbcfb888716c850c8f908f5b5329de46d7c
- Caching mode 0, no invalidation from not-present to present: https://lkml.iu.edu/hypermail/linux/kernel/2404.1/01404.html; https://lkml.iu.edu/hypermail/linux/kernel/2103.2/02636.html; Xen, real hardware reports CM = 0: https://lore.kernel.org/all/8b873e30-c1d1-3174-9e67-506887deedcc@suse.com/
- Atomic update of a remapping entry, `cmpxchg16b` for the posted format only: https://lkml.iu.edu/hypermail/linux/kernel/1510.1/05657.html
- MSI address format (0xFEE, destination ID in bits 19:12, vector in data bits 7:0; bit 4 for the remappable format): Intel SDM volume 3 mirror, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-396.html; Xen, https://lists.xen.org/archives/html/xen-devel/2017-08/msg01029.html
- Linux kdump copies the VT-d translation tables of the dead kernel: https://git.evolution-x.org/anierin/msm-5.15/commit/091d42e; https://lists.openwall.net/linux-kernel/2015/06/13/87; AMD: https://ayakael.net/forge/linux-uconsole/commit/3ac3e5ee5ed5
- Barrelfish: memory and kernel objects by capabilities, https://www.sigops.org/2021/fish-in-a-barrel-an-insiders-retrospective-of-the-sosp09-multikernel-paper/; capabilities in a multikernel with an ownership property, Nevill 2012, https://barrelfish.org/publications/nevill-master-capabilities.pdf (abstract only); Gerber 2018, https://barrelfish.org/publications/gerbesim-phd.pdf (abstract only); interrupt routing via Kaluga and the SKB, https://barrelfish.org/publications/intern-rana-hpet.pdf; Humbel, Achermann, Cock, Roscoe 2017, DOI 10.1145/3144555.3144557.

From memory (not verified): the layout of a remapped-format remapping entry (destination and vector in the low 64 bits); the IOAPIC's index and data registers; one invalidation queue per VT-d unit; the handling of the queue error bit; RWBF; SMMUv3.3 ECMDQ; the 4 KB alignment of BARs by x86 firmware; that Linux kdump also copies the remapping table; the 0.1 % estimate for the memory service's metadata; the PS/2 and GPIO lines on laptops.
