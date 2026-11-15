# Symmetric nodes: roles instead of privileged kernels, and the membership and recovery protocol

Written 15 November 2026 for the two owners, at the request of one of them: a system in which no kernel matters more than another. Nothing under `/Users/btw/Documents/repos` was edited. It builds on the two drafts of the same day, `nodes-memory-devices.md` (chunks that change owner, devices that follow their driver, a hardware node) and `ownership-alternatives.md` (the machine table read-only everywhere, written only through a write gate per node; the complement rule), whose recommendations the owners accepted. **Verified** means checked on the web today, with the source in part 9; **from memory** means not checked.

## 0. Verdict

1. **Symmetry between nodes is reachable; symmetry between physical cores is not.** Every privilege the design gives today to a node (the boot node, the hardware node, the anchor nodes 0 and 1, the start-up space that holds the root of authority) can be turned into a **role**: a duty with one holder at a time, recorded in the machine table, that holds no state that cannot be rebuilt from the live nodes, the kept memory and the hardware, and that moves to another node only after its holder is fenced, or by the holder's own last act. With roles, the boot node disappears entirely (the machine start-up becomes a phase that leaves nothing behind), the hardware node becomes one role per IOMMU unit and per IOAPIC, spread over the nodes, and the supervisor and the memory service live on any *k* nodes, with their start-up memory attached to a role rather than to nodes 0 and 1.
2. **What stays is hardware, and it makes some cores less trustworthy, never more important.** On x86-64 the core that firmware chose as bootstrap processor cannot be reset by INIT (it would run the firmware's boot code again), so it can only be stopped by its own kernel's NMI handler; a core in VMX root operation ignores INIT. On ARM64 and RISC-V no standard call lets one core stop another: every fence is cooperative, delivered at a priority the dying kernel cannot mask (SDEI, NMI, M-mode), but executed by its own code. A core hosting an ARM Trusted OS cannot be powered off at all. The rule that follows: a node whose core cannot be fenced by hardware never holds a kernel role. Whole-machine boot, and (from memory) resume from S3, still go through the bootstrap processor, because firmware does.
3. **The missing foundation is specified here**: evidence-based accusation checked by the gate, no voting; a fence per architecture that must be confirmed; a reclaim barrier per dependency; generations; a recovery reserve that pays for the work; eight calls of the cores group with their checks; and the role hand-over, planned and after a death. The central rule is the STONITH rule of clusters, brought inside one machine: **suspicion is cheap and can be wrong; nothing a node held is reused until its core is stopped.** Where the core cannot be stopped, its memory and its kernel roles are frozen, and the machine degrades instead of risking two writers.
4. **No existing system does all of this.** kmorph (Linux multikernel, 2025) confirms that a dead kernel's CPUs are stopped before taking over, which is the same rule; Hive (1995) had the double barrier and the per-page firewall, but simulated its agreement with an oracle; Cellular Disco agreed on the live set; nothing found recovers a per-core kernel whose memory changes owner, hands over IOMMU units between kernels, or has a formal model of such recovery.

## 1. Symmetry

### 1.1 The principle: importance belongs to a role

A **role** is a duty that must have exactly one holder at a time. A design is symmetric when every such duty is a role and every role obeys three rules:

1. **One holder, recorded in shared memory.** The role word in the machine table names the holder. It changes only by compare-and-swap through the gate.
2. **Nothing that cannot be rebuilt.** A holder may cache state, but everything the role needs must be recoverable from the kept memory (the read-only machine table, the kept image, the hardware's own tables), from the hardware's registers, and from what the live nodes report about themselves. A new holder never reads the dead holder's private memory as truth (D-107: a reloaded kernel adopts nothing).
3. **A single writer, by construction.** A role moves either by the holder's own last write (planned), or after the holder's core is confirmed stopped (after a death). No timeout ever moves a role.

Rule 2 is what makes any node able to take over. Rule 3 is what makes two holders impossible (part 3.4).

### 1.2 The asymmetries of the present design, and their fate

| Asymmetry | Where it is written | Fate | How |
|---|---|---|---|
| The boot core is node 0, first in the core list | Start-up state, entry `Cores` | **Removed** | Node index = rank by hardware identifier (APIC ID, MPIDR, hart ID). The boot core is flagged, nothing more |
| The boot node builds the first process and holds all authority (core and iommu capabilities, device untypeds, the pool) | Start-up state, slots 16 onwards; rule 6 | **Removed** | Every node builds its own first service, the **node agent**, from the kept image; every node's start-up space has the same slots and the same machine capabilities (1.3.2) |
| The image region belongs to the boot node's share | Start-up state, rules 2 and 5 | **Removed** | The image becomes kept, read-only memory common to all nodes, with its hash in the read-only machine table (1.3.1) |
| Free chunks start owned by node 0; device blocks start owned by node 0 | Draft of 15 November, "where everything sits" | **Removed** | They start **unclaimed**; any live node takes them through its gate (1.3.3) |
| The hardware node is the single writer of the IOMMU units, the interrupt remapping table and the IOAPICs | Draft of 15 November, part B | **Turned into roles** | One role per IOMMU unit and per IOAPIC (and per GIC ITS and distributor on ARM64), spread over the nodes; the remapping entries of each node are written by that node (1.3.4) |
| Lines can be claimed only on the boot (or hardware) node | Interrupts, "Nodes." | **Removed where the hardware allows** | Any node claims a line; the IOAPIC role holder programs the input; acknowledgement by the IOAPIC's EOI register where it exists (1.3.4) |
| Nodes 0 and 1 are anchors, with larger floors, and carry the supervisor and the memory service | kernel.md, D-108; draft of 15 November | **Turned into roles** | *k* **reserve roles**, each owning the memory one replica needs, held by any nodes; plain roles for leadership (1.3.5) |
| The start-up space of one node is the root of authority | Open points, "the depth rule and a machine that does not die" | **Removed** | Every node's start-up space is a root at depth 1 for that node's resources and holds roots of the machine objects (1.3.2). This answers the open point |
| The machine table is built by one core | Start-up state | **Irreducible, harmless** | Built once, before any node exists, then read-only or gate-written; nothing depends on who built it |
| The bootstrap processor | Hardware | **Irreducible** | Part 1.4: it cannot be fenced by INIT; firmware boots and (from memory) resumes from S3 on it |

### 1.3 The design that removes them

#### 1.3.1 Machine start-up is a phase, not a node

At power-on, firmware starts one core. Its kernel does the **machine start-up** and nothing else:

1. reads the MADT and the DMAR (or the device tree's equivalents), builds the read-only part of the machine table (core list sorted by hardware identifier, floors, reserves, chunk geometry, units, IOAPICs, the kept image's place and SHA-256, the kernel image slots, the membership times of the boot image) and zeroes its living part;
2. turns every IOMMU unit on in blocking mode, programs the remapping table base, masks every IOAPIC input and the legacy PIC;
3. writes the initial role words: unit role *j* held by node *j* mod *n*, reserve and plain roles vacant;
4. starts every other core, including the idle second hardware threads of D-028, which it parks in the park stub (part 2.6) with CR4.MCE set (a broadcast machine check would otherwise shut the machine down, part 1.4);
5. then runs the **node start-up** of its own node, the same code every other core runs on its own node.

After step 5 the boot core is an ordinary core: its node has the same start-up state as every other node, holds the roles step 3 gave it (none, if *n* > number of units), and nothing in the machine depends on it having booted the machine. A failure during steps 1 to 4 is a failed boot; that is irreducible, since firmware gives the machine to one core.

**The kept image.** The image region (the boot image's modules) becomes kept memory, read-only for every kernel and every process, never reclaimed. Every node's start-up space has a read-only frame capability for it (slot 14). The node start-up maps the first service's read-only and executable segments straight from it, and copies its writable segments into the node's floor. Its SHA-256 is in the read-only machine table, and a fresh start checks it before use (any damage is a containment violation: full stop with trace). Why: every recovery needs the code of the first service, the supervisor and the memory service from a place no dead node could have written. The cost: the image's size is kept for the life of the machine (a few MB to tens of MB).

#### 1.3.2 Every node starts the same way

The start-up space of every node, at machine start and at every fresh start, has the same layout:

| Slot | Capability |
|---|---|
| 1 to 11 | as today: its `cspace`, `aspace`, `thread`, `sched`, `debug`, its own `irq_control`, `ioports` (x86-64), its start-up task, the start-up page, the message page and its mapping copy |
| 12 | its `memory_control` (draft of 15 November) |
| 13 | the read-only frame of the living part of the machine table: ownership words, device table, member table, role table |
| 14 | the read-only frame of the kept image |
| 15 | its mailbox endpoint, with `recv` (part 2.11) |
| 16 onwards | one root `core` capability per node, in index order; one root `iommu` capability per IOMMU unit; one root `role` capability per role; then the untypeds of its floor; then one read-only frame per module of the kept image |

- **Machine objects** (`core`, `iommu`, `role`) are made at machine start, never destroyed, and have one root in every node's start-up space (part 2.11). So every node agent can start, stop and watch any node, attach devices on any unit (through the unit's role holder), and claim roles. All node agents run the same code from the same image; who does what among them is user-space policy, decided by roles.
- **Authority over memory and devices** is not handed out at start: it is taken. A node's floor is its own; everything else is unclaimed (1.3.3) and taken by `memory_take` through the node's `memory_control`.
- The open point of the contract ("one start-up space per core, each able to recreate the supervisor and the memory service, or another answer") is answered by the first branch, completed by reserve roles: any node agent can recreate a supervisor replica from the kept image and the memory of a reserve it claims.

#### 1.3.3 Memory with no initial owner

This amends the accepted draft in two points and keeps everything else (the word format, the calls, the gate, the audit):

- **Unclaimed.** At machine start every chunk outside the floors, the reserves and the kept ranges has the word *free, owner 0xFFFF* (unclaimed), and so does every device entry and every unused device entry. The gate lets any live node take an unclaimed word, by compare-and-swap against the value it read. The alternative, an equal initial split, also removes node 0, but makes every node's death freeze 1/*n* of the free memory until its reclaim; unclaimed memory belongs to whoever needs it first.
- **The words of the dead.** The gate also lets any live node take a word whose owner is a node in the **dead** state, whatever generation is in it, by compare-and-swap. That is the complement rule written as a gate check: once a node is dead (part 2.7), nothing alive reaches its memory, so its words are free for everyone, its next generation included. A word of a node that is fenced, unfenced or fencing is refused. On a chunk of a reserve (the read-only table lists them), a word of a dead owner counts as free for that reserve only: only the reserve role's holder may take it.
- **`memory_split`** is no longer reserved to the hardware node: a node splits a device entry it owns, and the upper half goes to the unused entry of lowest index, taken by compare-and-swap.
- Consequence for the single-writer rule of the draft: every write to a word is still made by one node at a time *by permission* (the owner; or, for an unclaimed or dead owner, the one whose compare-and-swap wins). The gate always writes by compare-and-swap against the value it checked, which also catches a word that changed under it.

#### 1.3.4 Shared hardware: one role per unit, and a data path that needs no role

The hardware node of the draft bundled several single-writer resources. Split, each is its own **unit role** (part 3):

| Resource | Why it needs one writer | Role |
|---|---|---|
| An IOMMU unit: Intel VT-d remapping unit, AMD-Vi IOMMU, Arm SMMUv3, RISC-V IOMMU. Its invalidation (command) queue, root and context tables (or stream tables), fault records, domain numbers | One queue per unit, a producer index that two writers would corrupt (verified for VT-d and AMD-Vi register sets and Linux's single queue per unit; RISC-V IOMMU has one command queue, verified; SMMUv3.3 adds optional per-CPU queues, ECMDQ, verified) | `iommu:u`, one per unit |
| An x86 IOAPIC: its redirection entries | Programmed through an index and a data register (from memory) | `ioapic:i`, one per IOAPIC |
| Arm GIC distributor: the configuration registers packed several interrupts per word (`GICD_ICFGR`, 16 per register, read-modify-write; verified) | Two writers of one word lose an update | `gicd`, one |
| Arm GIC ITS: its command queue (verified) | One queue | `its:k`, one per ITS |

What **needs no role**, so keeps running whoever holds or loses the roles:

- the **data path**: MMIO of a device by its driver's node; DMA through the tables the iospace's node owns; interrupt arrivals; acknowledgements at the local interrupt controller;
- the **remapping entries of a node**. The remapping table already gives each node a disjoint range of handles (*node* × 192 + *vector* − 48). Each node writes its own entries through its gate (which refuses an index outside the node's range) and asks the unit role holders only for the invalidation of the interrupt entry cache. With this, `irq_claim` of an MSI touches no other node's state;
- on Arm, routing an SPI (`GICD_IROUTER`, one 64-bit register per interrupt) and enabling or disabling it (`GICD_ISENABLER`/`ICENABLER`, write-1 registers), verified: the node that claims the SPI writes them itself;
- on RISC-V, the PLIC (one priority register per source, enables and claim per context, a context belonging to one hart), the IMSIC (one per hart) and the APLIC (one `sourcecfg` and one `target` register per source), verified: every register has a natural single writer, so **RISC-V interrupts need no role at all**;
- on x86, **level-triggered lines, acknowledged by the IOAPIC's EOI register**. Where the local APIC supports EOI-broadcast suppression (version register bit 24) and the IOAPIC has an EOI register (version 0x20 and later), the kernel sets suppression; a level arrival then leaves the input's Remote IRR set, which holds the line, and `irq_ack` writes the vector of the input's redirection entry into the IOAPIC's EOI register: one 32-bit write, any node (verified in the SDM; Linux does not use directed EOI, verified, so this path has little field experience). The node maps the IOAPIC page only inside its gate, which writes nothing but the EOI register outside the role. Without that hardware support, a level line's mask and unmask go to the IOAPIC role holder as requests: one message per level interrupt, slower, still correct.

With this, a death of a unit role holder stops **only changes** on that unit (attach, detach, unmap invalidations, claims of lines), for the time of the takeover; the data path of every device, and line interrupts already claimed, keep running. The draft's weakness "line interrupts stop while the hardware node is reloaded" disappears on hardware with directed EOI.

The initial holders are spread (unit *j* on node *j* mod *n*). Moving them is `role_hand`, a placement decision of user space.

#### 1.3.5 The supervisor and the memory service on any *k* nodes

- The boot image states *k* (2 ≤ *k* ≤ 8) and the size of one **reserve**: `floor_anchor + floor_anchor_per_gib × O`, rounded up to 2 MB (the anchor sizes of the draft). The machine start-up sets aside *k* runs of chunks of that size, recorded in the read-only machine table as reserve *j*.
- **Reserve role** *j* owns reserve *j*'s chunks: their free words carry the owner code 0xFFF0 + *j*, and the gate lets only the role's holder take them; when a block of them is destroyed, its words return to that code, not to the node. When the holder dies, the role becomes claimable once the holder is dead (its memory reclaimed); the claimant's node can then take the reserve's chunks, and its node agent starts a replica of the supervisor and of the memory service there, from the kept image.
- **Plain roles** (`supervisor-leader`, `memory-leader`, `platform`, and any the boot image names, at most 64) give user space the same single-holder guarantee: a plain role moves after a death once its holder is fenced, or by `role_hand`.
- Every node's floor becomes the same small `floor_node`. The anchors' extra memory is no longer bound to nodes 0 and 1, so losing nodes 0 and 1 together no longer matters more than losing any two nodes.
- **What user space must accept for this to work** (rule 2 of 1.1 applied to user space): the supervisor and the memory service keep no state that only one replica has. The truth about a node's processes and memory is held by that node's agent and by the ownership table; the replicas are coordinators that rebuild their view from the node agents' reports and from storage. This is a requirement on their design, not on the kernel.

### 1.4 What the hardware resists

**x86-64.**

| Fact | Consequence | Source |
|---|---|---|
| INIT sent to the bootstrap processor makes it run the firmware's boot-strap code instead of waiting for SIPI. Linux woke CPU0 with an NMI for that reason, and removed CPU0 hotplug in 2023 | The BSP core cannot be fenced or restarted with INIT: it is fenced by its own NMI handler and restarted from the park stub by NMI. It is **not fenceable by hardware**, so its node never holds a kernel role | Verified (Linux commits e1c467e69040 and the 2023 removal) |
| INIT is blocked in VMX root operation and while in SMM (latched until RSM, per KVM's maintainers) | A node in VMX root operation (micro-VM fallback, D-093) is fenced only through its NMI handler (VMXOFF), like the BSP. Linux disables VMX on panic for the same reason | Verified (SDM; Linux) |
| Machine checks are broadcast to all logical processors; a processor with CR4.MCE clear shuts the machine down. Linux brings every SMT sibling up once to set CR4.MCE | No core may stay in wait-for-SIPI (where CR4.MCE is clear) or never-started: the idle hardware threads of D-028 and every fenced core are parked in a stub with CR4.MCE set | Verified (SDM 15.10.4.1; Linux commit 0cc3cd21657b; l1tf.rst) |
| Linux tried parking CPUs in INIT and reverted it: client firmware waited for the lowest APIC ID as the SMI rendezvous master. SMIs are latched in wait-for-SIPI | Firmware itself has favourite cores. The park stub halts (serves SMIs) rather than leaving a core in INIT; the time between INIT and SIPI is kept to microseconds | Verified (Linux 45e34c8af58f and its revert) |
| SMIs stall cores for a time the OS does not control | `STALE_NS` must exceed the worst SMI; a false suspicion costs a node, never safety | From memory (durations to measure) |
| The SIPI vector names a 4 KB page below 1 MB | One page of kept memory below 1 MB for the trampoline and park stub | Verified (SDM 8.4.3) |
| The legacy 8259 delivers through LINT0 of the BSP in virtual-wire mode; the MADT's local APIC NMI structures say which processors' LINT pins carry NMI (0xFF: all) | The PIC stays masked (as today). Chipset NMIs arrive where firmware wired them; every node handles an unexpected NMI the same way (trace, continue) | Verified (coreboot citing ACPI 6.3; MP spec transcription) |
| UEFI runtime services forbid re-entry while a previous call runs on another processor | If they are used, one plain role serialises them; a node that dies inside a runtime call can leave firmware state inconsistent, which no OS can repair | Verified (UEFI 2.10 §8.1) |
| Resume from S3 enters the OS on the BSP | Whole-machine S3 needs the BSP core usable; s2idle does not | From memory (not found in the ACPI text; Linux restarts the APs itself after resume, verified) |
| INIT does not change the TSC | The clock survives the fence and restart of a core | Verified (SDM table 9-1) |

**ARM64.**

| Fact | Consequence | Source |
|---|---|---|
| PSCI `CPU_OFF` powers down only the calling core; no PSCI call turns off another core. `CPU_ON` on a core already on returns ALREADY_ON; `AFFINITY_INFO` reports ON, OFF or ON_PENDING | Every fence is cooperative: the dying kernel's handler must call `CPU_OFF`. `AFFINITY_INFO` gives the confirmation. A hung core cannot be restarted | Verified (PSCI DEN0022E) |
| SDEI event 0 can be signalled to a target PE (`SDEI_EVENT_SIGNAL`) and is delivered even when the OS has exceptions masked, after `PE_UNMASK` | The best available stop signal on ARM64, where firmware provides SDEI | Verified (TF-A docs; Linux arm_sdei.c) |
| Pseudo-NMI by GIC priority masking (Linux `ARM64_PSEUDO_NMI`); FEAT_NMI exists in the architecture but is not in mainline Linux | The fallback signal; the kernel never masks interrupts with PSTATE.I except at entry and exit | Verified |
| Linux escalates IPI stop (1 s), NMI stop (10 ms), SDEI (100 ms), then gives up and leaves the CPU running | Even Linux accepts unstoppable cores on ARM64; DodOS makes them **unfenced** and freezes what they could write | Verified (arch/arm64/kernel/smp.c) |
| A uniprocessor Trusted OS makes `CPU_OFF` fail with DENIED on its core, migratable or not, until `MIGRATE`; Linux refuses to offline that CPU | That core is never fenceable by hardware: no kernel role on it. Here symmetry ends in the firmware | Verified (PSCI; Linux psci.c) |
| GIC: per-interrupt routing and write-1 enable registers; packed configuration registers; one ITS command queue; SMMUv3 one command queue, optional ECMDQ from v3.3 | Roles `gicd`, `its:k`, `iommu:u`; ECMDQ would let each node invalidate for itself, removing the IOMMU role on such parts | Verified |

**RISC-V.**

| Fact | Consequence | Source |
|---|---|---|
| SBI `sbi_hart_stop` stops only the calling hart; `sbi_hart_start` fails with ALREADY_AVAILABLE on a started hart; `sbi_hart_get_status` reports STOPPED and the other states | Cooperative fence, confirmed by `sbi_hart_get_status` | Verified (SBI spec, HSM) |
| Interrupts for a higher privilege mode are always enabled while a hart runs in a lower one; Smrnmi (resumable NMI for M-mode) is ratified | M-mode firmware can stop a hung S-mode kernel. A firmware-specific SBI extension (its EID must embed the SBI implementation ID) could offer `fence_hart`; no standard call does | Verified (privileged spec; SBI spec) |
| No architectural boot hart; OpenSBI chooses one by lottery | Nothing to undo after boot | Verified (OpenSBI fw_base.S) |
| PLIC, IMSIC, APLIC registers have natural single writers; the IOMMU has one command queue | Interrupts need no role; one role per IOMMU | Verified |

### 1.5 The residue that cannot be removed

1. **Boot.** One core boots the machine, because firmware gives it to one core. After boot, nothing depends on it.
2. **Cores that cannot be fenced by hardware**: the x86-64 BSP, any x86-64 core in VMX root operation, every ARM64 and RISC-V core where firmware offers no forced stop, and the ARM64 core of a resident Trusted OS. They are *less* trusted: they may run user work and hold reserve and plain roles, but never a kernel role, and if one of them hangs it ends unfenced, its memory frozen. On ARM64 and RISC-V, without a firmware extension, that is every core: every kernel role then has to accept a cooperative fence, and the owners must decide whether that is enough (For the humans).
3. **Firmware state**: SMM (global, invisible), UEFI runtime services, ACPI's embedded controller and AML, the Trusted OS. A node that dies in the middle of a firmware interaction can leave state no OS can repair.
4. **Whole-machine sleep through firmware** (S3, PSCI `SYSTEM_SUSPEND`) resumes on one core chosen by firmware; on x86-64 it needs the BSP core (from memory).
5. **One kernel image, one gate, one machine table, one kept image**: read-only or gate-written state shared by all, and the same code on every node. A bug that every node reaches at once (a malformed message broadcast to all, a gate bug) is a common-mode failure that symmetry does nothing against. Symmetry removes single points of *location*, not single points of *design*.
## 2. Membership and recovery: the cores group

This part specifies what the contract lists as "not specified": how the live nodes agree that a node is dead, how its core is stopped, the order isolate, reset, reclaim, reload, and the calls of the cores group. Part 2.11 is written to be pasted into kernel-interface.md.

### 2.1 What a single machine gives, and what it does not

| Given | Not given |
|---|---|
| Coherent shared memory: every node can read a word another node wrote, and an aligned 64-bit compare-and-swap is atomic on x86-64, ARM64 (LSE `CAS`, or LDXR/STXR) and RISC-V (LR/SC, `amocas.d` with Zacas) | A way to stop another core from writing memory while it runs. No architecture lets one core cut another core's access to memory. Stopping its execution is the only fence |
| One clock, the same on every core (the invariant counter of [Clock](kernel-interface.md#clock)) | Bounded execution: an SMI stalls every core for an unbounded time, firmware decides (part 1.4) |
| Hardware signals that reach a core whatever it does: NMI and INIT on x86-64; on ARM64 and RISC-V only firmware-mediated ones (part 1.4) | A guarantee that a kernel that is still running is right. A kernel can be hung (it executes, but makes no progress) or wrong (it executes and writes nonsense) before it stops |
| No partition: two live nodes always see each other's memory | Agreement for free: two nodes can still read the same word at different moments and decide differently |

The consequence that shapes everything below: **suspicion is cheap and can be wrong; a fence makes it true.** A node is declared dead only after its core is stopped. A false suspicion then costs a node, never safety. This is the STONITH rule of high-availability clusters ("shoot the other node in the head" before taking over its resources) applied inside one machine, where the "power switch" is INIT on x86-64 and a firmware call on ARM64 and RISC-V (part 4.6 gives the precedents).

### 2.2 Words

- A **node** is the state of one per-core kernel (D-108). It is identified by its **index** (0 to *n* − 1) and its **generation** *g* (1 at machine start, one more at each fresh start).
- A **physical core** runs one node, or several when nodes are parked (D-108). The node normally run by core *i* is node *i*; **node indexes are the rank of the cores by hardware identifier** (APIC ID, MPIDR affinity, hart ID), so the boot core is no longer node 0 (part 1).
- The **machine table** (D-114) has a read-only part, written once at machine start, and a living part. The living part holds the ownership words and device table (draft of 15 November), and, new here, the **member table** (one word per node) and the **role table** (one word per role, part 3). It is mapped read-only in every kernel and written only through each node's **write gate** (the recommendation the owners accepted). A read-only frame of the living part is in slot 13 of every start-up space, so user space reads membership and roles without a call.
- Each node has a **node beacon** and each physical core a **core beacon**: pages that only that node (or that core) writes, and every other kernel reads (part 2.4).
- A **role** is a duty that must have one holder at a time: driving one IOMMU unit, one IOAPIC, owning one memory reserve, being the leader of the supervisors (part 3).

### 2.3 The states of a node

The member word of node *X*:

```
bits 0-3    state: 0 dead, 1 starting, 2 live, 3 sealing, 4 sealed,
                   5 fencing, 6 fenced, 7 unfenced (8-15 never written)
bits 4-6    evidence of the last accusation: 0 none, 1 self, 2 stale,
            3 stuck, 4 kill, 5 retire, 6 host
bits 7-15   zero
bits 16-31  driver: the node that drives the fence, 0xFFFF for none
bits 32-63  generation
```

| State | Meaning | Its core | Its objects | Its roles |
|---|---|---|---|---|
| **dead** (*g*) | Generation *g* is over and fully reclaimed. Generation 0 means never started | Parked by the fence, or never started | None: references to generation *g* are `gone` | None names it |
| **starting** (*g*) | Being built: start-up state, first thread | Running | Being made | None yet |
| **live** (*g*) | Normal | Running | Valid | May hold roles |
| **sealing** (*g*) | A planned stop is in progress (`core_stop` mode `seal`): it hands its kernel roles over and quiesces | Running | Valid | Handing over |
| **sealed** (*g*) | Stopped cleanly, its block sealed. It can be resumed with the same generation (`core_start` mode `resume`), on the same or another core | Parked | Kept, frozen | Keeps its reserve and plain roles; holds no kernel role |
| **fencing** (*g*) | Accused with evidence; its core is being stopped | Unknown | Frozen for others: references are `gone` | Kept until fenced |
| **fenced** (*g*) | Its core is confirmed stopped. Every live node is reclaiming (part 2.7) | Stopped | Being reclaimed | Kernel and plain roles are taken over; reserve roles wait for dead |
| **unfenced** (*g*) | The fence failed: the core did not confirm that it stopped within `FENCE_NS` | Unknown, possibly running | Quarantined for ever | Frozen (part 2.6) |

Allowed transitions, each made by one compare-and-swap through the gate, which checks the condition in the last column against the shared state before it writes:

| From | To | Made by | Condition the gate checks |
|---|---|---|---|
| dead (*g*) | starting (*g* + 1) | the node that calls `core_start` mode `fresh` | No role word names *X*; the core *X* is placed on is usable and runs no node |
| sealed (*g*) | starting (*g*) | the node that calls `core_start` mode `resume` | The core *X* is placed on is confirmed parked or runs no node |
| starting (*g*) | live (*g*) | *X* itself, at the end of its start-up | — |
| live (*g*) | sealing (*g*) | the node that calls `core_stop` mode `seal` | At least one other node is live |
| sealing (*g*) | sealed (*g*) | *X* itself, as its last write before it parks | No role word names *X* as the holder of a kernel role |
| starting, live, sealing, sealed (*g*) | fencing (*g*) | any live node, with evidence (part 2.5) | The evidence holds; at least one other node is live (except for evidence `self`) |
| fencing (*g*), driver *D* | fencing (*g*), driver *E* | *E*, a live node | *D* is not starting, live or sealing |
| fencing (*g*) | fenced (*g*) | the driver | The fence is confirmed (part 2.6) |
| fencing (*g*) | unfenced (*g*) | the driver | `FENCE_NS` has passed since the first fence action without confirmation |
| unfenced (*g*) | fenced (*g*) | any live node | The fence is confirmed after all (the core answered late) |
| fenced (*g*) | dead (*g*) | any live node | The reclaim barrier holds (part 2.7) |

There is no other transition. In particular nothing goes from a fenced, unfenced or dead state back to live except through dead and a fresh start with a new generation, and nothing starts a node that might still be running. A sealed node does not beat, so only the evidence `kill`, `retire` and `host` can accuse it.

**A node's own gate stops it (design choice).** Every write through a node's gate first reads that node's own member word, and refuses (the kernel then parks itself) unless it is starting, live or sealing with the node's generation. So a node that was hung and wakes up after it has been accused can no longer change any shared word, take memory, write a remapping entry or map a unit, even before its core is stopped. What it can still do, until the fence, is write the memory its page tables already reach: the reason for 2.7.

**Why a word per node and not a log of events (design choice).** The member word is the whole truth about a node: any node, user space included, decides from the current words alone, never from a history it might have missed. The alternative, a membership service with views and view changes (virtual synchrony, from memory), needs every node to agree on a sequence of views; here the states are monotone between two fresh starts and every decision is a function of the current words, so no sequence is needed.

### 2.4 Beacons, rings and what each node publishes

**Core beacon** (one 4 KB page per physical core, written only by that core):

| Field | Written | Meaning |
|---|---|---|
| `heartbeat` | at the exit of every kernel event of that core | A counter. It proves that the core's event loop runs |
| `idle_until` | when the core goes idle | The instant of its next armed timer, or the largest value if none. A core does not have to beat while idle |
| `running` | at every switch between parked nodes (D-108) | The index of the node whose block the core runs, 0xFFFF while it switches |
| `vmx` (x86-64) | before VMXON and after VMXOFF | Set while the core is in VMX root operation, where INIT is blocked (part 1.4) |
| `parked` | by the park stub (part 2.6), never by a kernel | The fence epoch the stub was entered with |

**Node beacon** (written only by the kernel that runs that node, mapped writable only while it runs it):

| Field | Meaning |
|---|---|
| `panic` | 0, or the code of a failure the node detected in itself, with its generation |
| `save_seal` | Written last when a parked node is saved, cleared first when it is loaded: generation and a checksum of the node block's header. A node whose seal is valid was not running |
| `acked[n]` | For each node *Y*, the generation of *Y* whose reclaim this node has finished (part 2.7) |
| `maps_of[n bits]` | Set, through the gate, before this node makes its first translation (CPU or DMA) to memory owned by node *Y*; cleared when it acks *Y*. It tells the barrier whom a stuck node could still write into |
| `observations[8]` | Written by the gate only: (target, kind, value, instant) of an open suspicion (part 2.5) |
| counters | idle, slack, kernel and recovery time, for `core_status` |

**Rings.** Each ordered pair of nodes has a ring for messages between kernels, with a producer index written by the sender and a consumer index written by the receiver. The contract already assumes them ("the rings between kernels", [Language split](kernel-interface.md#language-split)); the membership protocol only reads their two indexes.

**Size.** For *n* nodes: *n* core beacons of 4 KB, *n* node beacons of 4 KB + 8*n* + *n*/8 bytes rounded up to pages. For 128 nodes, 1 MB; for 1,024 nodes (the maximum, `NODES_MAX`), 12 MB. All of it is kept at machine start and never grows (rule 3).

### 2.5 Detection: evidence, not opinion

A node is accused only with **evidence that any other node can check in shared memory**. The accuser does not vote and does not need anyone's agreement: the gate checks the evidence at the moment of the compare-and-swap. A kernel that is wrong cannot accuse a healthy node, because the evidence would not hold, unless the gate itself is wrong (part 6).

| Evidence | Holds when | Who looks |
|---|---|---|
| **self** | *X*'s node beacon has `panic` ≠ 0 with *X*'s current generation. *X* writes it when it detects a failure in itself (a kernel assertion, a double fault, an unexpected exception in kernel mode, an uncorrectable machine check on its core), sends an interrupt to the next live node, and parks itself | Everyone, at the interrupt or at the next look |
| **stale** | The gate recorded an observation (*X*'s host core, heartbeat value *h*, instant *t*), and now: the heartbeat still reads *h*, now − *t* ≥ `STALE_NS`, and now > `idle_until` + `STALE_NS` | A node waiting for *X*; the sweep |
| **stuck** | The gate recorded an observation (ring *Y*→*X*, consumer index *c*, instant *t*) taken when the ring was not empty and after *Y* sent *X* an interrupt, and now the consumer index still reads *c* with now − *t* ≥ `STUCK_NS` | Any node that has a message waiting in a ring to *X* |
| **kill** | `core_stop` mode `kill` was called with `manage` on *X*'s `core` capability | The caller's kernel |
| **retire** | `core_stop` mode `retire`, or *X* reported a hardware fault of its core; the core is marked unusable | Same |
| **host** | *X* was bound to a core whose fence was decided for another node, and *X* was running there or its save seal is invalid | The driver of that fence |

- **Stale proves the core is stuck; stuck proves the node's protocol is stuck.** A core can beat (its event loop runs) and still never serve its rings because of a bug; a core can be idle for hours and owe nothing to anybody. So the protocol judges a node **only when someone needs it**: a thread that waits for *X* (a call, an acknowledgement of the core group, a request to a role holder) makes its kernel observe *X*, and an idle *X* that owes nothing is never woken. This is what lets cores sleep (D-108) without heartbeats every millisecond.
- **The sweep.** To find nodes that died silently while nobody needed them (they may hold a role or memory), every live node also observes its two successors among the non-dead nodes in cyclic index order every `SWEEP_NS`: if a successor is idle with no armed timer, it sends it an interrupt and a ping message, which turns into stuck evidence if it is not consumed. One wake-up per core per `SWEEP_NS`.
- **Observations are written by the gate only**, at most 8 open ones per node, and expire after 4 × `STALE_NS`. A node cannot invent an old observation of a heartbeat, because the gate stamps it with the clock.
- **No false positive from a slow but healthy node is excluded.** An SMI that lasts longer than `STALE_NS`, a core throttled hard by temperature, or a long run of interrupts can make a healthy node look stale. The cost is that node's processes; safety is not affected, because the node is fenced before anything it holds is reused. `STALE_NS` must therefore be well above the worst SMI the reference machines show (part 6, measure).
- **Why no majority vote (design choice).** A vote protects against a node that lies about what it sees. Here what is seen is in shared memory and is checked by the gate, so a single accuser with valid evidence is enough, and the last two nodes of a machine can still recover each other. A vote would make the last live node unable to recover anyone: with two nodes, one dead, no majority exists.

### 2.6 The fence: isolating a core

The **driver** is the node that made the accusation. It runs the fence below in its recovery reserve (part 2.8), in steps. Any live node replaces a driver that is no longer live (table of 2.3). Every step is idempotent, so two drivers that overlap do no harm.

Let *p* be the physical core that runs *X* (from *X*'s placement in the machine table).

**x86-64.**

1. Send an NMI to *p*. If *X*'s kernel can still run its NMI handler, the handler sees its member word in `fencing`, writes what it can of a crash record, leaves VMX root operation if it is in it (VMXOFF) and clears `vmx`, and stops in a loop with interrupts masked. Wait at most `NMI_GRACE_NS`.
2. Send INIT to *p*, unless *p* is the core that firmware started as the bootstrap processor (BSP). INIT is taken whatever the core does, except in VMX root operation, where it is blocked, and in SMM, where it is held until the SMI handler returns (part 1.4). On the BSP, INIT does not wait for a SIPI: the core runs the firmware's boot code again (part 1.4), which must never happen while the machine runs. **The BSP core is therefore fenced by the NMI of step 1 alone**: its own kernel's handler parks it in the park stub.
3. Send SIPI with the vector of the **park stub**, a page of kept memory below 1 MB (the SIPI vector gives the page), twice, 200 µs apart.
4. The park stub, in real mode, sets CR4.MCE, installs vectors for NMI and machine check that halt, writes the fence epoch into `parked` of the core beacon, and halts with interrupts masked. A core must never stay in the wait-for-SIPI state after an INIT: there CR4.MCE is clear, and a broadcast machine check would shut the whole machine down; and firmware may wait for that core in an SMI rendezvous, as the revert of Linux's INIT parking showed (part 1.4). A halted core serves SMIs and machine checks.
5. **Confirmed** when `parked` holds the epoch. **Also confirmed**, on a core other than the BSP, when INIT was sent and `vmx` was clear when it was sent, after `SETTLE_NS`: INIT then stops the execution of kernel code at once, or at the end of the current SMI, and a core in SMM runs firmware, not DodOS. If `vmx` is set, or the core is the BSP, and neither the NMI handler nor the stub answered within `FENCE_NS`, *X* becomes **unfenced**.

**ARM64.** There is no architectural way for one core to stop another (part 1.4). The fence is cooperative, but delivered at a priority the dying kernel cannot mask:

1. Signal *p* with an event the kernel cannot have masked: SDEI event 0 through `SDEI_EVENT_SIGNAL` when the firmware offers SDEI (every node registers its handler and calls `SDEI_PE_UNMASK` at start, since firmware delivers to a PE only after that), otherwise the architectural NMI (FEAT_NMI) or a pseudo-NMI SGI (the kernel then never masks interrupts with PSTATE.I outside its entry and exit, only with the GIC priority mask).
2. The handler, in *X*'s kernel, calls PSCI `CPU_OFF`.
3. **Confirmed** when PSCI `AFFINITY_INFO` for *p* returns OFF. Otherwise, after `FENCE_NS`, **unfenced**, and the driver asks again every `SWEEP_NS`.
4. A core that hosts a uniprocessor Trusted OS refuses `CPU_OFF` with DENIED, migratable or not, until the Trusted OS is moved by PSCI `MIGRATE` (part 1.4). A dying kernel cannot be trusted to migrate it, so on that core the handler parks in a loop and writes `parked`, which is confirmation by the dying kernel's own code. Such a core is never a candidate for a kernel role (part 3).

**RISC-V.**

1. Send an interrupt to *p* (the SBI IPI extension, or the IMSIC or ACLINT supervisor software interrupt).
2. The handler calls SBI `sbi_hart_stop`.
3. **Confirmed** when `sbi_hart_get_status` returns STOPPED. Otherwise, after `FENCE_NS`, **unfenced**.
4. Optional, where DodOS ships its own SBI firmware: a firmware-specific extension `fence_hart(hart)` makes M-mode on the target hart stop it, discarding S-mode, whatever S-mode masks. M-mode interrupts preempt S-mode even when S-mode has interrupts disabled (part 1.4). With it the RISC-V fence becomes forced, as INIT is on x86-64. No standard call does this.

**After a confirmed fence**, for every node *Z* bound to *p*: if *Z* ≠ *X* and *Z*'s save seal is valid, *Z* becomes **sealed** with its generation (it was parked, not running; [containment is per node](kernel.md#nodes-cores-and-load)); otherwise *Z* becomes fencing with evidence `host`, then fenced in the same step.

**An unfenced node.** Its core may still execute and write any memory its own page tables reach. Safety is kept by never reusing that memory:

- its own floor and chunks stay owned by it, and no gate accepts a write to its words;
- memory of other nodes that it maps (every node *Y* with `maps_of` bit *Y* set in its node beacon) cannot pass the reclaim barrier of 2.7, so those nodes, if they die, stay fenced, not dead, until the machine restarts;
- its devices are blocked by the unit role holders (DMA blocking does not need its core to be stopped);
- a kernel role it holds stays frozen: nobody takes it over, because two writers on one unit would corrupt it. The data path of that unit continues; its changes wait for ever (part 6).

An unfenced node is the price of the absence of a forced stop. On x86-64 it happens only when the node runs on the BSP core, or was in VMX root operation (the micro-VM fallback, D-093), and does not answer its NMI. On ARM64 and RISC-V it happens whenever a core is hung with its handler unable to run. The driver keeps trying every `SWEEP_NS`; a late confirmation moves the node to fenced, and recovery continues.

### 2.7 Reclaim: what every live node must do, and the barrier

When a live node *Y* sees *X* in **fencing**, it does at once, in its own kernel, the steps that need no fence:

- R0. It refuses every new message from *X* and every new request from *X* to a role *Y* holds; it fails with `gone` every thread of *Y* that waits for *X* (a call to an object of *X*, an acknowledgement of a core group that includes *X*, a request to a role held by *X*: those requests are sent again to the new holder instead, part 3). A reference to *X*'s generation is `gone` from now on.
- R1. If *Y* holds a unit role (part 3), it blocks *X*'s devices on that unit: it clears every context entry whose iospace root table lies in memory the ownership table gives to *X* or in *X*'s floor, clears *X*'s interrupt remapping entries on that unit (or, for an IOAPIC role, masks the inputs *X* claimed), and invalidates. This needs no fence: blocking DMA does not depend on *X*'s core.

When *Y* sees *X* in **fenced**, it finishes, in bounded steps in its recovery reserve:

- R2. It removes every translation *Y* holds to memory of *X*: the remote mappings recorded on *Y*'s side, in its address spaces (invalidating its own TLB) and in its iospaces (the invalidation goes through the unit role holders and waits for them, as any unmap). It destroys its copies of the address spaces whose home is *X* (D-108: the process is lost with its home node); their threads on *Y* fault *no address space* when they would run.
- R3. It drops the records of translations that *X* held to frames of *Y*. The frames stay pinned (their memory does not return to their untyped) until *X* is **dead**, because *X*'s devices could reach them until every unit holder has blocked them.
- R4. **Audit.** It checks that every ownership word covered by its own live blocks still reads taken (*Y*, its generation). A mismatch means that containment was violated (a gate bug, or a wild write that got through): the machine stops with a trace, as [kernel.md](kernel.md#recovery-of-one-cores-kernel) already orders for a violation of containment.
- R5. It clears `maps_of` bit *X* and writes `acked[X]` = *g* in its node beacon. This is its answer. It is a write to its own page, not a message: the barrier reads it.

**The reclaim barrier.** *X* (generation *g*) goes from fenced to dead when, for every node *Y* ≠ *X*:

| State of *Y* | Required |
|---|---|
| starting, live, sealing | `acked[X]` = *g* in *Y*'s beacon |
| sealed | `maps_of` bit *X* clear in *Y*'s beacon. A sealed node that maps *X*'s memory delays *X* until it is resumed (it then acks before running any thread) or killed |
| fencing, unfenced | `maps_of` bit *X* clear |
| fenced | `maps_of` bit *X* clear, or every node that is starting, live or sealing has acked *Y* (so *Y*'s devices are blocked; *Y*'s core is stopped) |
| dead | nothing |

and no unit role is held by *X* or is handing to or from *X*: the successor has taken it over and acked (part 3).

Any live node that sees the barrier hold makes the compare-and-swap; the gate re-checks it (at most *n* beacons and the role table: bounded). Then, in the same step of that node, the reserve roles held by *X* become vacant and the plain roles still naming *X* are vacated, and every live node, when it sees *X* dead, unpins the frames of R3.

**After dead**, by the ownership rules of part 1.3.3 (which amend the accepted draft): every ownership word and device entry owned by *X* is free for any live node to take through its gate (compare-and-swap), and for *X*'s next generation. This is the complement rule the owners accepted: the memory of the dead is what no live node claims.

**Why the barrier is per dependency and not a global round (design choice).** A global barrier ("every node acks every dead node, then all go dead together", as Hive's double barrier, part 4.6) delays every recovery by the slowest one, and a node that fences late extends everybody's barrier. The rule above delays *X* only for the nodes that could still write into *X*'s memory, which `maps_of` records. Its cost is one bitmap per node and one gate write before the first remote mapping to a new peer.

### 2.8 The recovery reserve: who pays for reclaim

Reclaim is work in the kernel that is not a call: the driver's fence and every node's steps R0 to R5. Rule 4 bounds calls; this work is bounded per step and runs on an internal scheduling context of each node, the **recovery reserve**: bandwidth `RECOVERY_BANDWIDTH` (1/64 of a core, period 10 ms, provisional), admitted from the start in the sum of the node, with the rules of [What runs next](kernel-interface.md#what-runs-next). Each step does at most 32 units of work (the step of a removal). When there is no recovery, the reserve's time is slack and goes to others.

- **Why a reserve and not "the running context pays" (design choice).** Recovery work charged to whatever thread runs breaks the guarantees of admission on every live node at the worst moment. A reserve keeps them: a node with every core admitted to the hilt still recovers its neighbour, at 1/64 of a core.
- **Bound on the time to reclaim.** The work of *Y* for *X* is bounded by what *Y* holds of *X*: its remote mappings and copies of *X*'s spaces, its threads waiting for *X*, and, for a unit holder, at most 65,536 context entries per unit and 192 remapping entries. The time is that work divided by the reserve's rate. It is measured (part 6).

### 2.9 Concurrency: who acts when the one who should is dead

- **Nobody is designated.** Any live node with valid evidence accuses; the compare-and-swap lets one accusation win. The fence has a driver only to avoid duplicate work; when the driver is no longer live, the first live node that notices takes the driver field and repeats the fence from step 1 (idempotent).
- **Two nodes die at once.** Each is accused and fenced on its own. Their barriers are independent except where `maps_of` links them; then the rule for a fenced *Y* in the table of 2.7 applies, and both reach dead once every live node has acked both.
- **A node dies during a recovery,** whatever its part: as the driver (replaced), as a node that has not acked yet (it leaves the set of nodes whose ack is required as soon as it is accused; its own `maps_of` bits then count instead), as the successor of a role (part 3: the next candidate takes over).
- **A node dies while starting.** The same path: it is accused (stale: no heartbeat within `START_NS`), fenced, reclaimed. Its next fresh start has generation *g* + 2.
- **A node dies while sealing.** Accused like a live node; the roles it had not yet handed over are taken over after the fence, by part 3.
- **All nodes but one die.** The last live node fences and reclaims all of them, holds every kernel role, and the machine runs on one core. `core_stop` refuses to kill or seal the last live node (`busy`), so the last node is lost only by its own failure, and then the machine is lost: no design survives the loss of every core.
- **Generations.** A generation is compared for equality only, so wrap-around after 2^32 starts of one node is harmless. A reference to an object of another node carries the node and generation (`NodeGen`); its use checks the member word and returns `gone` if the generation is not the current one, or if the node is in a fencing, fenced, unfenced or dead state. A word of the ownership table taken by a generation that is not current is free.

### 2.10 What user space sees and must do

- **Signals.** A node's watchers (`core_watch`, at most 4 per node) are signalled after every change of a member word or a role word that their node processes. They read the living part of the machine table in slot 13; the signal only says "look".
- **References.** Every capability that names an object of *X*'s generation returns `gone` from the moment *X* is accused. A thread that waited for *X* gets `gone`. A process whose home is *X* is lost; its threads on other nodes fault *no address space*.
- **What the supervisors do**, in the order of the states:
  - *X* fencing: stop placing work on *X*.
  - *X* fenced: the plain roles *X* held can be claimed (`role_claim`); the kernel roles move by themselves.
  - *X* dead: the reserve roles of *X* can be claimed; the memory service takes back *X*'s memory; the platform service resets at bus level the devices *X*'s drivers drove (their DMA and interrupts are already blocked) and restarts the drivers on other nodes; the supervisor restarts the processes whose home was *X*, from their manifests and storage.
  - Then, if it wants, it reloads *X* with `core_start` mode `fresh`. **The kernel never reloads a node by itself (design choice):** whether and when to restart a node, and with which first service, is a policy, and a node that fails repeatedly should stay dead. This replaces the sentence of kernel.md that stops the machine when a failure repeats: a failure that repeats retires the node, and the machine stops only when containment is violated.
- **The order isolate, reset, reclaim, reload**, as specified here:

| Step | What | Who | Ends when |
|---|---|---|---|
| isolate | Accusation; DMA and interrupts of *X*'s devices blocked (R1); *X*'s core fenced | Kernel: the accuser drives, unit holders block | *X* fenced |
| reset | The core: INIT and park stub, `CPU_OFF`, `sbi_hart_stop` (part of the fence). The devices: bus-level reset | Kernel for the core; platform service for the devices, after dead | Core parked; devices reset before a new driver uses them |
| reclaim | R2 to R5 on every live node; roles taken over | Kernel, every live node, in its recovery reserve | *X* dead (barrier) |
| reload | `core_start` mode `fresh`: generation *g* + 1, start-up state from *X*'s floor and the kept image | A supervisor | *X* live |

### 2.11 The cores group, ready for the contract

The text below is meant for kernel-interface.md, as the subsection "Cores", after [Tasks and marks](kernel-interface.md#tasks-and-marks).

> ### Cores
>
> **Proposed, 15 November 2026: written, no reference model yet, not reviewed.** It covers the `core` and `role` objects, the membership of nodes, the fence, and the calls `core_start`, `core_stop`, `core_status`, `core_idle`, `core_watch`, `core_place`, `role_claim` and `role_hand`. The rules of the sections above apply: order of checks, dying objects, bounded calls.
>
> #### Machine objects
>
> - A `core` names one node, by its index. A `role` names one role (see [Roles](#roles)). Both are **machine objects**: made by the kernel at machine start, never from an untyped, never destroyed, with no node as their holder. Their state is in the living part of the machine table, which every kernel reads. `untyped_retype` never makes them: kind `core` and kind `role` are `invalid` there, with `irq`, `irq_control`, `iommu` and `memory_control` (`core` was `unsupported` until now).
> - **A machine object has one root capability in the start-up space of every node** (design choice). Removing a root removes its descendants and destroys nothing. A node that is started fresh gets new roots. Why: a machine object must outlive any node, so it cannot live as long as one root capability held by one node, the rule of every other object.
> - Rights on a `core`: `read` for `core_status` and `core_watch`; `write` for `core_idle` and, as before, to configure scheduling contexts of that node; `manage` for `core_start`, `core_stop` and `core_place`; `send` to use it as the endpoint argument of `call` or `send` (the node's mailbox, below). Rights on a `role`: `read` (no call needs it; the role word is in slot 13) and `manage` for `role_claim` and `role_hand`.
> - **The mailbox of a node (design choice).** Each node has a start-up endpoint, made from no untyped, whose capability with `recv` is in slot 15 of its start-up space. `call` and `send` accept a `core` capability with `send` in place of an endpoint: the message goes to the mailbox of that node's current generation, and is `gone` if the node is not live. The receiver sees badge 0 and the sender's stamp, whose task identifier carries the sender's node. This is the only reference that follows a node across its generations; it is how the first services of the nodes find each other at machine start and after a reload. The alternative, capabilities to every other node's mailbox made at each start, needs a derivation recorded on both sides for each pair at every start, and leaves a reloaded node unreachable until someone hands its new mailbox around.
>
> #### Membership
>
> - Each node has a **member word** in the machine table: state, evidence, driver, generation. The states are dead, starting, live, sealing, sealed, fencing, fenced and unfenced; their meaning and the only allowed transitions are in [the states of a node](#the-states-of-a-node). Every transition is one compare-and-swap through the writing node's gate, which checks the condition of the transition first.
> - A node is **accused** only with evidence that the gate checks in shared memory: its own panic record (`self`); a host core whose heartbeat has not moved for `STALE_NS` while not idle (`stale`); a ring to the node not consumed for `STUCK_NS` after an interrupt (`stuck`); `core_stop` (`kill`, `retire`); or the fence of the core it was running on (`host`).
> - **A node is never declared dead before its core is stopped.** The fence (NMI, INIT and the park stub on x86-64; an SDEI or NMI-priority signal and PSCI `CPU_OFF` on ARM64; an interrupt and SBI `sbi_hart_stop` on RISC-V) must be confirmed; a node whose fence is not confirmed within `FENCE_NS` is unfenced, and its memory and kernel roles are never reused.
> - After the fence, every live node reclaims (refuses the node's messages, ends the waits on it with `gone`, removes its own translations to the node's memory, audits its own ownership words) and acknowledges in its node beacon. The node becomes dead when every node that could still reach its memory has acknowledged or is stopped ([the reclaim barrier](#the-reclaim-barrier)). Only then can its memory be taken and its generation be replaced.
> - Recovery work runs on each node's **recovery reserve**, a scheduling context of `RECOVERY_BANDWIDTH` admitted from start-up, in steps of at most 32 units.
>
> | Call | Arguments | Result | Rights and rules |
> |---|---|---|---|
> | `core_start` | core, mode, kernel image, module | | `manage` on the core. Mode 0 `fresh`, 1 `resume`. Kernel image 0 is the boot kernel, 1 the replacement slot; module is the index, in the kept boot image, of the first service to run (fresh), 0 for resume |
> | `core_stop` | core, mode | | `manage` on the core. Mode 0 `kill`, 1 `seal`, 2 `retire` |
> | `core_status` | core | member word, placement, idle, slack, kernel, recovery | `read` on the core |
> | `core_idle` | core, table (message words) | | `write` on the core |
> | `core_watch` | core, index, notify | | `read` on the core, which must name the caller's node. Notify 0 unbinds |
> | `core_place` | core, physical core | | `manage` on the core |
> | `role_claim` | role | new epoch | `manage` on the role |
> | `role_hand` | role, core | new epoch | `manage` on the role. Core 0 vacates (plain and reserve roles only) |
>
> Rules of `core_start`:
>
> - Plain arguments, in order (`invalid`): mode is 0 or 1; kernel image is 0 or 1; for mode 0, module is below the number of modules and names a module flagged as a first service; for mode 1, module is 0.
> - State, in order: mode 0: `busy` if the node is not dead; `busy` if the physical core it is placed on is marked unusable or runs a node that is not sealed; mode 1: `busy` if the node is not sealed, or if its core is not confirmed parked. Then `busy` if kernel image 1 is asked for and the replacement slot is empty.
> - Effect, mode 0: the member word becomes starting (*g* + 1). The caller's kernel starts the physical core (x86-64: a start request written in the park stub's page, then an NMI, which wakes the halted stub and sends it to the kernel's entry, the way Linux once woke CPU0 without INIT; ARM64: PSCI `CPU_ON`; RISC-V: SBI `sbi_hart_start`), in its recovery reserve, and returns at once. The node builds its start-up state from its floor and the kept image ([Start-up state](#start-up-state)), with generation *g* + 1, and its first thread runs the chosen module. It becomes live when its first thread is created. A node that does not beat within `START_NS` is accused with `stale`.
> - Effect, mode 1: the member word becomes starting (*g*); the node is loaded from its sealed block, checks that the block's format version is one the kernel image reads, and becomes live with the same generation; its objects are as they were. A version it cannot read makes it accuse itself (`self`): its objects are lost and it is reclaimed as after any failure.
> - Bound: constant work in the call, plus one start sequence of a physical core in the caller's recovery reserve.
>
> Rules of `core_stop`:
>
> - Plain argument (`invalid`): mode is 0, 1 or 2.
> - State, in order: mode 0 and 2: `busy` if the node is dead, fencing, fenced or unfenced; mode 1: `busy` if the node is not live. Then, for every mode, `busy` if no other node would be live afterwards.
> - Effect, modes 0 and 2: the node is accused (evidence `kill` or `retire`), and the caller's node drives the fence. Mode 2 also marks the physical core that runs the node as unusable until the machine restarts. Stopping the caller's own node is allowed: the call returns, the node parks itself at the end of the event, and another live node drives the fence.
> - Effect, mode 1: the member word becomes sealing. The node hands each kernel role it holds to its successor ([Roles](#roles)), finishes or refuses the requests it serves, saves and seals its block, writes sealed and parks its core. Its threads, its memory and its plain and reserve roles stay.
> - The call returns `ok` when the transition is begun; its end is seen through `core_watch` and the member word. Bound: constant work and one message to each live node.
>
> Rules of `core_status`: no state error. Result: word 0 is the member word; word 1 is the physical core the node is placed on (bits 0-31) and flags (bit 32 parked on a core that is not its own, bit 33 core marked unusable, bit 34 the core cannot be fenced by hardware); words 2 to 5 are the idle, slack, kernel and recovery time of the node in nanoseconds, as last published in its node beacon (for a node that is not live, the values it last wrote). Constant work: it reads shared memory and sends no message.
>
> Rules of `core_idle`:
>
> - The table travels as the message words of the call: at most 15 entries of 4 words, in order: exit latency (ns), minimum residency (ns), method in bits 0-31 and parameter in bits 32-63, flags. Methods: 0 the halt instruction; 1 x86-64 MWAIT, parameter the hint; 2 PSCI `CPU_SUSPEND`, parameter the power state; 3 SBI `sbi_hart_suspend`, parameter the suspend type. Flags: bit 0, the state loses the core's context; other bits 0.
> - Plain arguments, entry by entry (`invalid`): the number of words is a multiple of 4 and at most 60; each latency and residency is below 2^63; exit latencies strictly increase; the method is one of this architecture's; reserved flag bits are 0.
> - The table replaces the node's table; zero entries return the node to the halt instruction. On another node, the call becomes a message (rule 7). Constant work.
>
> Rules of `core_watch`:
>
> - Order: the core (slot, kind, `read`, then that it names the caller's node, `invalid`); the notify if not 0 (slot, kind, `send`, then that it belongs to the caller's node, `invalid`); index below 4 (`invalid`); state: `busy` if notify is not 0 and the index is bound.
> - Effect: the notify is signalled, with the badge of its capability or bit 0, at least once after each change of a member word or a role word that the node processes. Notify 0 unbinds, and succeeds if the index is unbound. Destroying a notify unbinds it in the steps of its removal, after its irqs, one unit each.
>
> Rules of `core_place`:
>
> - Plain argument (`invalid`): the physical core is below the number of cores.
> - State, in order: `busy` if the node is not live or sealed; `busy` if the core is marked unusable; `busy` if the core runs a node that is not live; `budget` if the sum of the admitted bandwidths of the nodes the core would run exceeds one core ([Parked nodes](#one-kernel-per-core)).
> - Effect: the node is bound to that core in the machine table. A live node moves at its next event boundary, by the protocol of parked nodes; a sealed node is resumed there by `core_start` mode 1. The interrupt entries of the node are retargeted by requests to the unit role holders (at most 192). Bound: constant work in the call.
>
> Order of checks for every call of the group, as in [Order of checks](#order-of-checks): the capability the call acts on, the other capabilities, the plain arguments, the state.
>
> **What each node keeps** for this group, in its node block or its beacons, all fixed at start: its member word's last value seen, its core binding, its four watch slots, its idle table (15 entries), its recovery reserve context, its 8 observations, its `acked` array and `maps_of` bitmap (*n* entries), the list heads of its threads waiting for each node and of its remote mapping records per node (*n* each), and its write gate.

Roles and `role_claim`, `role_hand` are specified in part 3.

### 2.12 Numbers (provisional, to measure)

| Name | Value | Why this value |
|---|---|---|
| `NODES_MAX` | 1,024 | Kept memory is *O*(*n*²) for `acked` (8 MB at 1,024). The interrupt remapping layout already limits claims to 341 nodes |
| `STALE_NS` | 100 ms | Above the SMIs seen on ordinary machines (to measure on the reference machines); the boot image may set 10 ms to 1 s |
| `STUCK_NS` | 100 ms | Same order as `STALE_NS` |
| `SWEEP_NS` | 1 s | One wake-up per core per second |
| `NMI_GRACE_NS` | 1 ms | Time for a crash record |
| `FENCE_NS` | 10 ms | Time for INIT, SIPI and the stub, or for `CPU_OFF` |
| `SETTLE_NS` | 1 ms | Lets writes the fenced core had posted to device registers reach them before a successor writes the same unit (part 3.5) |
| `START_NS` | 1 s | Time for a started node to beat |
| `RECOVERY_BANDWIDTH` | 2^32 / 64, period 10 ms | 156 µs of each 10 ms |
| `CORE_WATCH_SLOTS` | 4 | Node agent and up to three supervisor replicas |
| `IDLE_STATES_MAX` | 15 | Fits the 64 message words |
| `OBSERVATIONS_MAX` | 8 | Open suspicions per node |

The boot image states the times in a record `BootMembership`, read by the loader with the floors; the kernel refuses values outside the ranges above.
## 3. Roles and their hand-over

### 3.1 The role table

The roles are fixed at machine start: one unit role per IOMMU unit, per IOAPIC (x86-64), per GIC ITS and one for the GIC distributor (ARM64); the *k* reserve roles; and the plain roles the boot image names (at most 64). Their number *R* is in the read-only machine table with, for each role, a record: kind (0 unit, 1 reserve, 2 plain), the object it governs (unit index, IOAPIC index, reserve index, or plain index) and the slot of its capability in every start-up space.

The **role word**, in the living part of the machine table:

```
bits 0-1    state: 0 vacant, 1 held, 2 handing
bits 2-17   holder node (for handing: the node that hands)
bits 18-33  target node (handing only; otherwise 0xFFFF)
bits 34-63  epoch: one more at every change
```

| Kind | Who moves it | When it may change holder without the holder |
|---|---|---|
| **unit** | The kernel: planned by `role_hand`, after a death by the successor automatically | The holder is fenced (or dead), and `SETTLE_NS` has passed since the fence was confirmed |
| **reserve** | User space: `role_claim`, `role_hand` | The holder is dead (its memory is reclaimed) |
| **plain** | User space: `role_claim`, `role_hand` | The holder is fenced (or dead) |

A unit role is never vacant (the last live node holds every unit role it can). A unit role is never held by a sealed node: sealing hands kernel roles over first.

**Candidates for a unit role (design choice).** Each core has a **fence class** in the read-only machine table, updated only by the core's own `vmx` flag:

| Class | Meaning | Cores |
|---|---|---|
| 2, forced | Another core can stop it whatever its kernel does | x86-64 cores other than the BSP, while not in VMX root operation; RISC-V harts with the firmware extension `fence_hart` |
| 1, signalled | Another core can deliver a signal its kernel cannot mask; the kernel's own handler stops it, and hardware or firmware confirms | x86-64 BSP (NMI); x86-64 cores in VMX root operation; ARM64 cores with SDEI or NMI-priority interrupts; RISC-V harts without the extension (an ordinary interrupt, confirmed by HSM state) |
| 0, cooperative only | The core can only park itself; the confirmation is the dying kernel's own write | ARM64 core of a resident Trusted OS |

The **successor** of a unit role whose holder *X* is fenced is the first node after *X* in cyclic index order among the live nodes whose core has the highest fence class found among live nodes. The rule is a pure function of the member table and the read-only table, so every node computes the same successor from the same words. A node holding a unit role never enters VMX root operation (it hands its roles first). Why: a role is only as safe as the fence of its holder; ranking by fence class puts kernel roles on forced-fence cores wherever the machine has them, and still lets a machine where every core is class 1 (most ARM64 machines) run.

### 3.2 Requests to a role holder

- A request to the holder of a unit role (attach, detach, invalidate after an unmap, write or clear a line's redirection entry, invalidate an interrupt entry) carries the role's epoch as the requester read it. The holder refuses a request whose epoch is not the current one with the internal answer *moved*; the requester reads the role word again and sends the request to the holder it names. This is the fencing token of Chubby's sequencers and of Kleppmann's argument (part 4.6), with the epoch as the token: a request addressed to an old holder can never be executed by it after the role moved, because that holder either wrote the move itself or is stopped.
- The request is held by the thread that waits for it (state *waiting for another node*): no queue in kernel memory. Requests are idempotent (draft of 15 November), so sending one again after a move or a death is harmless.
- When the holder is accused, every requester's kernel, at step R0 of its reclaim (part 2.7), keeps the requests aimed at that role and sends them again once the role word names a live holder.

### 3.3 Planned hand-over

**Unit role *u* from *X* to *Y*** (by `role_hand`, or by *X* itself while sealing):

1. In the call, on *X*: the gate reads held (*X*, *e*); *X* stops accepting new requests for *u* (they get *moved* once the role has moved) and finishes the ones it has begun.
2. *X* waits until the unit's queue is drained (head equals tail, at most `IOMMU_WAIT_NS`; a unit that does not drain is a hardware fault of the unit, below).
3. *X* unmaps the unit's registers and tables from its own address space, through its gate, and invalidates its own TLB.
4. *X* writes, by compare-and-swap, handing (*X* → *Y*, *e* + 1). The gate refuses if *Y* is no longer live; *X* then maps the unit again and stays the holder (the call returns `busy`). This write is *X*'s last act on *u*. *X* sends *Y* a message.
5. *Y*, at the message or when it sees the word: maps the unit's registers and tables through its gate (which allows it because the word names *Y* as target), reads the queue registers (head equals tail, no error), and writes held (*Y*, *e* + 2). It does not rebuild: a healthy holder handed over a consistent state. Requesters see the change and send their requests to *Y*.

Failures inside it: *X* dies before step 4: the role is still held by *X*, and the takeover after a death applies. *X* dies after step 4: *Y* completes step 5 regardless (*X* has already stopped touching *u*). *Y* dies after step 4: the word is handing (*X* → *Y*) with *Y* accused; once *Y* is fenced, the successor of *Y* takes over with a rebuild.

**Plain role** from *X* to *Y*: one compare-and-swap held (*X*, *e*) → held (*Y*, *e* + 1); the call is the commit point, and user space on *X* stops acting as holder before it calls. **Reserve role**: the same, refused while any word of the reserve is taken (the replica on *X* must have been stopped and its blocks given back).

### 3.4 Take-over after a death

**Unit role** held by *X*, or handing to *X*, with *X* fenced or dead (a handing from a dead *X* to a live *Y* is completed by *Y* as in 3.3 step 5):

1. The successor *S* (3.1) waits until `SETTLE_NS` after the fence of *X* was confirmed.
2. *S* writes held (*S*, *e* + 1); the gate checks that *X* is fenced or dead.
3. *S* maps the unit and **rebuilds** it, without reading anything of *X*'s:
   - **IOMMU unit**: drain the queue (head equals tail, at most `IOMMU_WAIT_NS`; if the queue's error bit is set, replace the faulty descriptor with a wait descriptor and clear the error, from memory); ask every live node for its report on the unit (each iospace that serves devices of the unit: device, root table address, domain number; each remapping handle it has claimed); compare every context entry with the reports, keeping those that match, rewriting those that differ, clearing those that no live node claims (which blocks the devices of every fenced or dead node); rebuild the map of domain numbers; one global invalidation of the unit (context cache, IOTLB, interrupt entry cache).
   - **IOAPIC**: read each redirection entry; compare with the lines each live node reports as claimed; mask the inputs no live node claims; rebuild the record of which node claimed each input.
   - **GIC distributor**: rewrite the packed configuration of every SPI that a live node reports as claimed.
   - **GIC ITS**: drain the command queue; reissue the mapping commands for the devices and events live nodes report (they are idempotent), then a global invalidation and a synchronisation.
4. *S* serves requests, then acks the reclaim of *X* (step R1 for this unit is now done).

Each report is bounded (at most one message per iospace, 192 handles per node); the comparison of an IOMMU unit is at most 65,536 context entries, in steps of the recovery reserve.

**A unit that does not drain** (no confirmation within `IOMMU_WAIT_NS`) is a hardware fault of the unit, no longer of a node: *S* keeps the role and retries every `SWEEP_NS`; the devices behind the unit keep the translations they have; every change on the unit waits. The contract's present rule ("a hardware fault of the node that owns it") is replaced by this one, since killing the holder would not repair the unit.

**Plain role**: claimable by any live node with `role_claim` once the holder is fenced. **Reserve role**: claimable once the holder is dead. The kernel does nothing more: the node agent of the claimant starts the replica.

### 3.5 Why two nodes never hold a single-writer role at once

Say that a core is **active on unit *u*** when it can write *u*'s registers: the node it runs has *u*'s register page mapped, or a write it made to *u* has not yet reached the unit.

1. **Mapping follows the word.** A node maps *u*'s registers only through its gate, and the gate maps them only while the role word names that node as holder, or as target of a handing. No other kernel code maps unit registers: they are in no untyped ([Device memory](kernel-interface.md#device-memory)), and a build-time check finds no other code that writes page-table entries for them.
2. **The word has one holder.** It changes by compare-and-swap only.
3. **A planned hand-over unmaps before it moves.** *X* unmaps (step 3) before it writes handing (step 4); *Y* maps only after.
4. **A take-over waits for a fence.** The word leaves *X* without *X*'s own write only when *X* is fenced or dead, that is, when *X*'s core has been confirmed stopped. *X*'s core runs DodOS again only after a fresh start, which needs *X* to be dead, which needs no role word to name *X* (the barrier of 2.7). A fresh start maps nothing of *u* because the word does not name it.
5. **Writes in flight.** A write that *X* posted to *u* before its core stopped may still be on its way. `SETTLE_NS` (1 ms, provisional) between the confirmation and *S*'s first write covers it. That a stopped core's posted writes to device registers are not held longer than that is **from memory**, and is the one hardware assumption of the argument that must be tested.

So at every instant at most one core is active on *u*. The argument assumes: the gate is correct and is the only mapper; the confirmation of a fence is true (the hardware's or firmware's report, or the park stub's write, which no kernel can make, since it is in a page that every kernel maps read-only and that the stub writes in real mode); and the settle time is enough. For a class-1 core the stop itself is carried out by the dying kernel's handler, but its confirmation still comes from hardware or firmware (`AFFINITY_INFO`, `sbi_hart_get_status`, the park stub); only class 0 relies on the dying kernel's own write, which is why class 0 never holds a unit role.

### 3.6 The role calls, ready for the contract

> #### Roles
>
> A `role` names one duty with one holder at a time. Its word, in the living part of the machine table (slot 13), holds its state (vacant, held, handing), its holder, the target of a handing and an epoch. A role is of one of three kinds, fixed at machine start: **unit** (one IOMMU unit, one IOAPIC, one GIC ITS or the GIC distributor; moved by the kernel), **reserve** (the memory of one replica of the supervisor and the memory service), **plain** (any single-holder duty the boot image names, at most 64).
>
> - **No role ever moves by a timeout (design choice).** A role leaves its holder by the holder's own last write, or once the holder's core is confirmed stopped: fenced for a unit or plain role, dead for a reserve role. A unit role then goes to the successor, the first live node after the holder in index order among those whose core has the best fence class, which rebuilds the unit's state from the hardware and from the reports of the live nodes, never from the dead holder's memory.
> - A request to the holder of a unit role carries the role's epoch; a request with an old epoch is refused and sent again to the current holder.
>
> | Call | Arguments | Result | Rights and rules |
> |---|---|---|---|
> | `role_claim` | role | epoch | `manage` on the role. A unit role is `invalid`, judged right after the three checks of its slot |
> | `role_hand` | role, core | epoch | `manage` on the role. The core names the target node, and needs no right; 0 vacates. For a unit role, core 0 is `invalid`, judged as the first plain check |
>
> Rules of `role_claim`. State, in order: if the role is held by the caller's node, success with no change; `busy` if the role is held or handing and its holder or target is starting, live, sealing, sealed, fencing or unfenced; for a reserve role, `busy` also if the holder is fenced, or if a word of the reserve is taken by a node that is not dead. Effect: the word becomes held (the caller's node, epoch + 1). For a reserve role the caller's node may then take the reserve's chunks with `memory_take`; they are recorded with the owner code of the reserve, so no word is rewritten when the holder changes. Constant work.
>
> Rules of `role_hand`. State, in order: `busy` if the role is not held by the caller's node; if the target is the caller's node, success with no change; `busy` if the target is not live; for a unit role, `busy` if the target is not a candidate (its fence class is below the best among live nodes, or it is in VMX root operation); for a reserve role, `busy` if a word of the reserve is taken. Effect: for a plain or reserve role, the word becomes held (target, epoch + 1), or vacant for core 0. For a unit role, steps 1 to 4 of the planned hand-over: the call returns once the word is handing, and the target completes it. Bound: constant work, plus for a unit role one wait for the unit's queue of at most `IOMMU_WAIT_NS`.
## 4. What a formal or executable model must contain

kernel.md already asks for three models checked by state exploration: revocation between cores, change of size of a group, recovery of a kernel. This part says what the third must hold, now that recovery includes membership, roles and memory that changes owner. It is the part with the least precedent (4.5), so it should be written **before** the multi-core kernel, from parts 2 and 3, and the contract text corrected from what it finds, as was done for the one-core group (D-100, D-101).

### 4.1 State

Per node *X*:

- member word (state, evidence, driver, generation);
- the **core** that runs it and that core's hardware state: `running`, `hung` (executes, makes no progress, may still perform any write its mappings allow), `nmi` (in its NMI handler), `init_pending` (INIT latched by SMM or blocked by VMX), `wfs` (wait-for-SIPI), `parked`, `off`, `broken` (ignores every signal); the core's fence class and `vmx` flag;
- core beacon (heartbeat, idle until, running node, parked epoch) and node beacon (panic, save seal, `acked[·]`, `maps_of[·]`, observations);
- blocks: for each chunk, the set of objects of (*X*, *g*) on it, abstracted to "live object" or not;
- translations: CPU translations held by *X* to chunks (its own, and remote ones recorded on both sides); waiting threads by peer;
- the role words it believes, and the unit registers it has mapped.

Shared: ownership words (owner, state, generation) for a few chunks including one reserve chunk; the role table; rings (FIFO per pair, producer and consumer index).

Per unit *u*: the context entries (device → iospace root address, hence a chunk), the remapping entries (handle → node), the queue (producer index, writes in flight with their writer core), domain numbers. Per device: its current DMA reach (chunks), derived from its context entry and the iospace tables.

Time: a discrete clock with the constants `STALE_NS`, `STUCK_NS`, `FENCE_NS`, `SETTLE_NS` as small integers, plus a global **SMI pause** that stops every core's progress for a chosen number of ticks.

### 4.2 Actions

- Normal operation, enough to create every dependency recovery must undo: `memory_take`, `memory_give`, block destruction; a remote mapping of another node's frame (setting `maps_of` through the gate); unmapping; `iospace_attach` and `iospace_unmap` through the unit holder; `irq_claim` of an MSI and of a line; a call to another node's object that waits; `role_hand`, `role_claim`; `core_stop` in its three modes, `core_start` in its two, `core_place`.
- Membership: observe, accuse (each evidence kind), fence steps per architecture (NMI, INIT, SIPI, stub, `CPU_OFF`, `AFFINITY_INFO`, HSM status), driver replacement, the reclaim steps R0 to R5 of each live node, the barrier and its compare-and-swap, the take-over and rebuild of a unit role.
- Each gate operation as one atomic action that reads, checks and writes by compare-and-swap.

### 4.3 Faults to inject

| Fault | Why it matters |
|---|---|
| Crash-stop of any node before or after any atomic step | The protocol must be correct whatever step a node dies at, including the gate's compare-and-swap, a role hand-over, a block destruction cut in the middle, a fresh start |
| **Hang with late writes**: a node stops progressing but its core keeps running and, later, performs any write its mappings and gate allow, including writes to unit registers it has mapped and to remote frames | This is "a kernel can be wrong before it stops". Safety must not depend on a hung node staying quiet until it is fenced |
| Fence failure: the stub never answers, `AFFINITY_INFO` never says OFF, the core is `broken`; then a late success | The unfenced state, and the move to fenced after all |
| A posted write to a unit that lands up to `SETTLE_NS` after its writer is stopped | Checks the settle argument of 3.5; a variant with the write landing later must break invariant S3, which proves the model can see the danger |
| False suspicion: a healthy node delayed by an SMI pause longer than `STALE_NS` | It must be fenced and lost, never cause two writers or a reused page |
| Two or three nodes crashing in the same tick; the driver crashing; the successor of a role crashing during its rebuild; the target of a planned hand-over crashing between steps 4 and 5 | The concurrency rules of 2.9 and 3.3 |
| A node crashing while starting, while sealing, while parked on a core that is fenced for another node | The states starting, sealing and sealed |
| A wrong-index request to the gate (another node's word, another node's remapping handle, a unit the node does not hold) | The gate must refuse it; the model checks that refusal keeps every invariant |
| A bit flip in an ownership word | The check field catches it as "owned by another node" |
| All nodes but one crash | The last node must reach a state where it holds every unit role and all others are dead or unfenced |

Not modelled, and said so: a bug common to every node (the same code everywhere), a bug inside the gate (the gate is the trusted base of the model), and firmware misbehaviour beyond "a confirmation is late or never comes".

### 4.4 Invariants

Safety, checked in every reachable state:

- **S1, one owner.** Every chunk with a live object is covered by exactly one block, of one (node, generation), and its word is taken by that pair (or the chunk is in that node's floor). No chunk is owned by two live generations.
- **S2, no live reference to reclaimed memory.** If a chunk was taken at instant *t* by (*N*, *g*), then no CPU translation held by a core that is not stopped, no context entry of any unit, no remapping entry and no write in flight reaches that chunk unless it was made after *t* through a take, mapping or attach of (*N*, *g*) or of a node that recorded a remote mapping of it after *t*.
- **S3, one writer per unit.** For each unit, at most one core is active on it (mapped or with a write in flight).
- **S4, roles.** A unit role is never vacant, never held by a sealed or dead node, and never held by a node whose core has a lower fence class than another live candidate's at the moment it was taken over. A role word changes without its holder's write only when the holder is fenced or dead (reserve: dead).
- **S5, fence before reuse.** A node is dead only if its core is stopped (`parked`, `off`, `wfs` followed by the stub) and every node that could reach its memory has acked or is stopped (the barrier).
- **S6, generations.** A node starts only from dead (fresh, generation + 1) or sealed (resume, same generation); a reference with an old generation is `gone`.
- **S7, the last node.** A `core_stop` never leaves no live node.
- **S8, audit.** Every word covered by a live block of a live node reads taken by that node and generation (in the model, because only the gate writes; this is what the audit of R4 checks in the kernel).

Liveness, under weak fairness of the live nodes' steps, fences that eventually succeed, SMI pauses shorter than `STALE_NS`, and at least one live node:

- **L1.** Every accused node becomes fenced; every fenced node becomes dead.
- **L2.** Every unit role is eventually held by a live node and served, unless its holder is unfenced.
- **L3.** Every request to a role holder is eventually answered, or its thread gets `gone`.
- **L4.** Every thread that waits for a node that becomes fenced eventually gets `gone`.
- **L5, accuracy.** A node that keeps beating and consuming its rings within the times is never accused with `stale` or `stuck` evidence.
- **L6, progress with any one node dead.** From any state with one node crashed at any step, the others reach a state where every role is held by a live node, the crashed node is dead, and every other node is live.

### 4.5 How to check it, and at what size

- **TLA+ with TLC** for the exhaustive check of S1 to S8 and L1 to L6 on 3 nodes, 2 units, 4 chunks (one in a reserve), 2 devices, one plain role, crash and hang of up to 2 nodes. Apalache for the barrier and the successor rule with the number of nodes as a parameter, where TLC's explicit states explode.
- **An executable model in Rust**, sharing the gate functions with the kernel, driven by the deterministic simulation that kernel.md already plans ("kills a kernel at random at every merge"), with the fault list of 4.3 and 16 to 64 nodes. It is the oracle for the multi-core kernel, as the one-core reference model is for the one-core kernel.
- **Kani proofs** for the pure functions: the gate's checks of every transition table (member, role, ownership, remapping range), the successor function, the barrier predicate, the member and role word encodings.
- **A refinement check**: every transition the executable model makes must be a row of the tables of 2.3 and 3.1.

### 4.6 What prior work comes closest, and what has none

| Work | What it does on a failure (verified unless marked) | What it gives DodOS | What it lacks |
|---|---|---|---|
| **Hive** (SOSP 1995) | Cells detect failure by hints: an RPC timeout, a bus error, a per-tick counter of another cell that stops ("clock monitoring"), failed consistency checks. All cells then run a distributed agreement (the paper calls it group membership) before a cell is rebooted; recovery is a double global barrier (flush TLBs and remote mappings, revoke firewall write permission, discard the pages the failed cell could write, then resume). The per-page firewall is written only by the local processor | The heartbeat word (Hive's clock monitoring), "discard what the dead could write", the barrier | The agreement was simulated by an oracle, not implemented; the firewall is hardware that no current CPU has; memory does not change owner; no IOMMU |
| **Cellular Disco** (SOSP 1999) | Agrees on a live set (from hardware registers, or an n-round agreement for back-to-back faults), aborts pending RPCs to failed cells, kills the virtual machines that depended on them. Borrowed memory is not reclaimed | Agreement on the set of failed nodes before acting (our barrier reads it from the member table) | Trusts every cell's software; tested in simulation only |
| **Quest-V** | The faulting sandbox's own monitor detects (EPT violations) and recovers locally, or passes control to a remote monitor by IPI | Restarting one kernel while the others run | No remote detection of a hung kernel; a hypervisor in the trusted base; static partition |
| **Barrelfish/DC** (OSDI 2014) | Replaces a core's kernel; "we do not consider fault tolerance and isolation for now". The capability protocol handles failed operations, not failed nodes | The node block; replacement core by core (our mode `resume`) | No failure handling |
| **kmorph / Linux multikernel RFC** (2025) | Peers probe each other; death after 5 timeouts; the successor stops every CPU it does not own and confirms each one stopped, and "never proceeds with a CPU possibly still running the dead kernel", then resets the dead kernel's devices and hot-adds its memory | The closest precedent for fence-before-takeover between kernels on one machine | A spare kernel takes the whole machine; no roles, no memory changing owner at run time, no model; reviewers asked what stops one kernel from writing another's memory |
| **Tornado / K42** | Clustered objects and hot-swapping for adaptation; Hive-style cells judged too costly | Hot-swap of objects (replacement) | No fault tolerance |
| **fos** | Fleets of servers behind a name server, which can steer away from broken servers; "primarily focused on scalability and not fault tolerance" (search excerpt) | Services as fleets: the replicas of 1.3.5 | No kernel recovery, no membership |
| **Tessellation** | Nothing found on kernel-failure recovery | — | — |
| **Chandra–Toueg failure detectors; Isis** | Classes P and ◇P; Isis makes its detector look perfect by forcing a wrongly suspected process to crash itself | The formal name of our trick: the fence turns an unreliable suspicion into a perfect one | Processes, not kernels; crashing oneself needs the suspect's cooperation, which INIT does not |
| **Fetzer, crash leases** (IEEE TC 2003, abstract only) | A watchdog crashes a node whose lease is not renewed; a recovering node waits before rejoining | Time-free alternative we did not take: leases need a watchdog per core that hardware does not give | — |
| **SWIM** | Suspicion, gossiped, cleared by an Alive message, confirmed after a timeout; incarnation numbers | Incarnation numbers = our generations | Probabilistic, network-oriented |
| **STONITH (Pacemaker)** | "Fencing the original node ensures the resource can be safely started elsewhere" | The rule of 2.1 | Clusters of machines with power switches |
| **Chubby sequencers, fencing tokens** | A lock carries a generation number; the server rejects requests with an old one | Role epochs on requests (3.2) | — |
| **seL4 clustered multikernel** | Kernel isolation theorem: kernel memory partitioned between nodes | The shape of a theorem per generation | No recovery; memory never moves |
| **Otherworld** | A crash kernel resurrects processes from the dead kernel's memory, 97 % success | Why D-107 adopts nothing | Adopts state; one kernel |

**What has no precedent found:** recovering a per-core kernel while the others continue, on a machine where memory changes owner at run time; a single-writer hardware role (an IOMMU unit, an IOAPIC) moving between independent kernels, with a rebuild from the owners' reports instead of adoption; a reclaim barrier per dependency instead of a global barrier; per-architecture fence classes that decide where kernel roles may live; and any formal model of multikernel recovery (none found, verified as an absence in a non-exhaustive search).
## 5. What the one-core kernel and `abi/` must contain now

On one core *n* = 1: the member table has one word, always live; every role is held by node 0; `core_stop` in modes kill and seal is always `busy` (it would leave no live node); `core_start` is always `busy`. Everything else runs, and the executable model of part 4 takes *n* as a parameter, with phantom nodes. What must exist from the first line of code, so that nothing changes the layout of objects or the start-up page later:

### 5.1 In the one-core kernel

1. **Two start-up functions:** the machine start-up (part 1.3.1), run once by the boot core, and the node start-up, run by every node at machine start and at every fresh start. On one core the first calls the second. The boot core is not node 0 by definition: node indexes are ranks by hardware identifier.
2. **The kept image.** The boot image's modules are kept, read-only, common memory with their SHA-256 in the read-only machine table, mapped read-only by every kernel; their frames are machine frames, roots at depth 1 in every start-up space. The first service's writable segments are copied into the node's floor; the start-up page and the message page are made from the floor. The image untyped disappears.
3. **Machine objects.** `core`, `iommu` and `role` have no node and one root per start-up space; removing a root destroys nothing. The `core` capability with `send` is accepted as the endpoint of `call` and `send` (the mailbox in slot 15).
4. **The living part of the machine table**, as one read-only frame in slot 13: ownership words, device table, member table, role table, with their layouts in `abi/`. Kept, never growing.
5. **Beacons.** A core beacon and a node beacon, with the heartbeat written at the exit of every event and `idle_until` written when going idle. The park stub's `parked` word in a separate page that every kernel maps read-only.
6. **The write gate** (from the accepted survey), extended: ownership words (with the unclaimed and dead-owner rules of 1.3.3 and the reserve owner codes), member and role words (with the transition tables of 2.3 and 3.1), observations, `maps_of`, the node's own range of remapping entries, the IOAPIC EOI register, and the mapping of unit registers.
7. **Thread state *waiting for another node***, with the peer node index and links of a per-peer list in the thread object; per-peer list heads (*n*) in the node block, for waiting threads and for remote mapping records. Unused on one core, but they fix the thread object's layout.
8. **The recovery reserve.** An internal scheduling context of bandwidth 2^26 (1/64 of a core), period 10 ms, admitted in the node's sum from start-up, which the event loop runs in steps of 32 units. Consequence for the start-up state now: the first thread's context gets budget 9,843,750 ns over a period of 10 ms (bandwidth 63/64 of a core), not the whole core.
9. **Node block fields**: generation; core binding; 4 watch slots (and the unbinding of a destroyed notify from them); an idle table of 15 entries; 8 observations; the counters `core_status` publishes.
10. **Unit roles as a kernel interface**: every operation on an IOMMU unit, an IOAPIC, a GIC ITS or the GIC distributor goes through one function "request to the holder of role *r*, with epoch *e*". On one core it is a direct call. This is item 6 of the draft of 15 November, made per role instead of per hardware node.
11. **x86-64:** a kept page below 1 MB for the trampoline and park stub; every idle second hardware thread (D-028) brought up once and parked with CR4.MCE set; the NMI path able to reach the park stub; the `vmx` flag written around VMXON and VMXOFF.
12. **ARM64:** the SDEI handler registered and `SDEI_PE_UNMASK` called at start where firmware offers SDEI; interrupts masked only by the GIC priority mask outside entry and exit, so that a pseudo-NMI can always be taken; PSCI `MIGRATE_INFO_TYPE` read at start to mark the core of a resident Trusted OS as fence class 0.
13. **RISC-V:** the HSM extension required at start; the firmware extension `fence_hart` probed, setting fence class 2 if present.

### 5.2 In `abi/`

- **Calls** (positions continue after `MemorySplit` = 50 of the draft of 15 November; `CoreStart`, `CoreStop`, `CoreStatus` keep their places): `CoreIdle` = 51, `CoreWatch` = 52, `CorePlace` = 53, `RoleClaim` = 54, `RoleHand` = 55.
- **Object kinds**: `Role` = 20 (`MemoryControl` = 19 from the draft). `untyped_retype` with kind `Core` (14) or `Role` becomes `Invalid` (was `Unsupported` for `Core`).
- **Errors**: none new. The *moved* answer between kernels is internal and never reaches user space.
- **Member word**: `Member(u64)` with `state()`, `evidence()`, `driver()`, `generation()` and `from_raw` refusing states 8 to 15 and non-zero bits 7-15; `MemberState { Dead = 0, Starting = 1, Live = 2, Sealing = 3, Sealed = 4, Fencing = 5, Fenced = 6, Unfenced = 7 }`; `Evidence { None = 0, SelfReport = 1, Stale = 2, Stuck = 3, Kill = 4, Retire = 5, Host = 6 }`; `DRIVER_NONE = 0xFFFF`.
- **Role word**: `RoleWord(u64)` with `state()`, `holder()`, `target()`, `epoch()`; `RoleState { Vacant = 0, Held = 1, Handing = 2 }`; `RoleKind { Unit = 0, Reserve = 1, Plain = 2 }`.
- **Owner codes** of the ownership word: `OWNER_UNCLAIMED = 0xFFFF`, `OWNER_RESERVE_BASE = 0xFFF0` (reserves 0xFFF0 to 0xFFF7). `NODES_MAX = 1024`, so node indexes never reach them.
- **Modes and flags**: `CORE_START_FRESH = 0`, `CORE_START_RESUME = 1`; `CORE_STOP_KILL = 0`, `CORE_STOP_SEAL = 1`, `CORE_STOP_RETIRE = 2`; `CORE_STATUS_PARKED = 1 << 32`, `CORE_STATUS_UNUSABLE = 1 << 33`, `CORE_STATUS_SOFT_FENCE = 1 << 34`; `IDLE_METHOD_HALT = 0`, `IDLE_METHOD_MWAIT = 1`, `IDLE_METHOD_PSCI = 2`, `IDLE_METHOD_SBI = 3`, `IDLE_FLAG_LOSES_CONTEXT = 1`; `FENCE_CLASS_COOPERATIVE = 0`, `FENCE_CLASS_SIGNALLED = 1`, `FENCE_CLASS_FORCED = 2`.
- **Limits and times**: `CORE_WATCH_SLOTS = 4`, `IDLE_STATES_MAX = 15`, `OBSERVATIONS_MAX = 8`, `RESERVES_MAX = 8`, `ROLES_PLAIN_MAX = 64`, `KERNEL_IMAGE_SLOTS = 2`; `RECOVERY_BANDWIDTH = 1 << 26`, `RECOVERY_PERIOD_NS = 10_000_000`; defaults and ranges `STALE_NS` (100 ms; 10 ms to 1 s), `STUCK_NS` (100 ms; same range), `SWEEP_NS` (1 s; 100 ms to 60 s), `NMI_GRACE_NS = 1_000_000`, `FENCE_NS = 10_000_000`, `SETTLE_NS = 1_000_000`, `START_NS = 1_000_000_000`. `START_SCHED_BUDGET_NS = 9_843_750` beside `START_SCHED_PERIOD_NS`.
- **Start-up slots**: `START_SLOT_MEMORY_CONTROL = 12`, `START_SLOT_MACHINE = 13` (the draft's `START_SLOT_OWNERSHIP`, renamed), `START_SLOT_IMAGE = 14`, `START_SLOT_MAILBOX = 15`; `START_SLOT_FIRST` stays 16 and now begins the *n* `core` roots, then the `iommu` roots, then the `role` roots.
- **Start-up page**: `StartCore` keeps 24 bytes; its flags gain bits 1-2, the fence class; the list is sorted by hardware identifier and the boot core is only flagged. `StartNode` (16 bytes, four u32): index, number of nodes, generation, flags (bit 0 started fresh after a death, bit 1 resumed). This replaces both the present entry (which carries the boot node's index) and the draft's 24-byte version (boot node, hardware node, anchor flag). New kinds: `Machine = 17` (replaces the draft's `Ownership`): `StartMachine`, 48 bytes, the offsets in the slot-13 frame of the ownership words, device table, member table and role table (u64 each), the number of roles and the layout version (u32 each, layout 0); `Roles = 18`: `StartRole`, 8 bytes (kind u8, reserved u8, object u16, slot u32); `Reserves = 19`: `StartShare` records, one per reserve range; `Image = 20`: base and length (u64 each) and SHA-256 (32 bytes).
- **Boot image**: `BootFloors` becomes `floor_node`, `reserve_bytes`, `reserve_per_gib` (u64 each), `reserves` and `plain_roles` (u32 each), 32 bytes. `BootMembership`, 24 bytes: `stale_ms`, `stuck_ms`, `sweep_ms` (u32 each), and three reserved u32.
- **Kani proofs**: `Member::from_raw` and `RoleWord` read back what the constructors write; the gate's transition checks accept exactly the rows of the tables of 2.3 and 3.1; `successor(member_table, fence_classes, holder)` returns a live node of the highest class when one exists; the barrier predicate is monotone (once true for a generation it stays true).
## 6. Costs, weaknesses, and what must be measured

### 6.0 Attacks on the design, and how they end

| Attack | What happens | Verdict |
|---|---|---|
| Two nodes accuse the same node at once | One compare-and-swap wins; the other sees fencing and joins as a possible replacement driver | Holds |
| A wrong kernel accuses a healthy node | The gate checks the evidence in shared memory: a healthy node's heartbeat moves and its rings are consumed, so stale and stuck evidence fail. `kill` is not checkable (weakness 6) | Holds, except `kill` |
| A hung node wakes up after its accusation and keeps working | Its own gate refuses every shared write (2.3); requests it sends are refused (R0); it can only write memory it already maps, which the barrier keeps out of reuse until it is fenced | Holds |
| A slow but live driver sends INIT or SIPI after the node was reloaded | The driver must ack the node before the barrier holds, and it acks only after its last fence action; a fresh start needs dead. No fence action can follow a reload | Holds |
| The driver dies between INIT and SIPI, leaving the core in wait-for-SIPI | The replacement repeats from step 1 (idempotent) within `STALE_NS` of noticing; meanwhile a broadcast machine check would shut the machine down (CR4.MCE clear), and an SMI rendezvous waits for that core | **Open window**, milliseconds wide. Narrowed by having the driver's next step run in the same recovery step as INIT; not closed |
| Two successors take over the same unit role | Compare-and-swap; the loser never maps the unit | Holds |
| A take-over races a planned hand-over | The word is held (*X*), handing (*X* → *Y*) or held (*Y*); a take-over needs *X* fenced, and a handing needs *X*'s own write; the gate checks the word's exact value | Holds |
| ABA on a generation (a node restarted 2^32 times) | Generations are compared for equality against the member word, which no stale reference can match once the node moved on; a wrap needs 2^32 fresh starts during the life of one reference | Holds in practice |
| A fenced node's parked word is forged | The page is read-only for every kernel and written by the stub in real mode; forging needs a page-table bug | Holds, modulo page-table code |
| Every node is accused by one buggy message broadcast | Each node fails on its own bug; no node is left to fence anybody | **Fails**: common-mode (weakness 7) |
| The last two nodes accuse each other | The first compare-and-swap wins; the loser is now fencing, and its own gate refuses its accusation (2.3) | Holds |
| A node is sealed for a long time with a remote mapping of a node that dies | The dead node's reclaim waits for the sealed node | Degrades (weakness 11) |

### 6.1 Costs

| Cost | Size | Note |
|---|---|---|
| Kept image | The boot image's size, for the life of the machine (MBs to tens of MBs) | Was reclaimable after boot |
| Replacement kernel slot | One kernel image's size | The hook of `core_start`'s kernel image 1 |
| Beacons and `acked` | 1 MB at 128 nodes, 12 MB at 1,024 | *O*(*n*²) through `acked` |
| Machine object roots | *n* `core` roots in each of *n* start-up spaces, 64 bytes each: 1 MB at 128 nodes, 64 MB at 1,024 | The alternative (one machine capability and a call that derives a `core` by index) is listed for the humans |
| Reserves | *k* × (64 MB + 1 MB per GiB), recommended values of the draft | Was 2 anchors; now *k* ≥ 2 |
| Recovery reserve | 1/64 of every core's admissible bandwidth | Slack when there is no recovery |
| Heartbeat | One store per kernel event | Negligible |
| Sweep | One wake-up per core per `SWEEP_NS` (1 s) | Power: to measure in deep idle |
| Gate writes | Each first remote mapping to a new peer (`maps_of`), each remapping entry, each role or member change | Of the order of 0.14 µs each (the survey's Nested Kernel figure) |
| Mailbox call | One read of a member word more than a call on an endpoint | |
| Planned hand-over of a unit role | One wait of at most 1 ms for the unit's queue, in the call | |
| Take-over of a unit role | Up to 65,536 context entries compared, then a global invalidation: a burst of IOTLB misses for every device of the unit | To measure |
| Level lines without directed EOI | One message to the IOAPIC role holder per arrival and per acknowledgement | Only on old IOAPICs |

### 6.2 Weaknesses I could not remove

1. **On ARM64 and RISC-V every fence is cooperative**, unless the firmware is extended. The signal cannot be masked (SDEI, NMI, M-mode), but the stop is executed by the dying kernel's handler. A kernel whose handler cannot run ends unfenced, and on most ARM64 machines every core is class 1, so every unit role depends on this. Linux faces the same limit and simply gives up after 100 ms (verified).
2. **An unfenced node freezes what it could write until the machine restarts:** its memory, the memory of the nodes it mapped (their reclaim cannot complete), and any unit role it held (that unit's changes wait for ever). The machine survives, degraded; the only cure is a restart.
3. **The x86-64 BSP cannot be fenced by INIT**, and a node in VMX root operation cannot either. They are class 1: no kernel role while a class-2 node lives.
4. **Writes in flight after a fence** (3.5, item 5): that 1 ms is enough is from memory, and the single-writer argument depends on it.
5. **The gate is the trusted base of everything:** evidence checks, ownership, roles, remapping ranges, unit mappings. A gate bug is common to every node. The audit of R4 detects damage to ownership words, not a wrong member or role transition.
6. **Kill evidence trusts the caller's kernel.** The gate cannot check a capability; a wrong kernel can kill a healthy node through its own `core_stop` path (not by forging stale or stuck evidence, which the gate checks).
7. **Common-mode failure:** the same kernel on every node. A message that triggers a bug in every receiver kills them all. Symmetry removes single points of location, not of design; per-core-type binaries (kernel.md) help a little.
8. **False suspicion:** an SMI longer than `STALE_NS`, heavy throttling or a firmware stall costs a healthy node and its processes. `STALE_NS` trades detection time against this, and its right value depends on firmware.
9. **Unit role holders stay trusted for DMA** on their unit between two take-overs: a wrong holder can write a context entry that lets a device write anywhere. The rebuild verifies the unit only at a take-over.
10. ***O*(*n*²) structures** cap `NODES_MAX` at 1,024.
11. **A sealed node that maps a dead node's memory delays its reclaim** until it is resumed or killed; long seals are a placement mistake.
12. **Firmware state** (SMM, UEFI runtime services, the ACPI embedded controller and AML, the Trusted OS) cannot be repaired by any OS when a node dies in the middle of using it.
13. **The supervisors' design is constrained:** no state held only by one replica. The kernel cannot enforce it.
14. **Plain roles belong to nodes, not to processes:** a role-holding process that crashes on a live node keeps the role until its node agent hands it over.
15. **Directed EOI** has little field use (Linux does not enable it, verified); its hardware may have errata.
16. **Whole-machine sleep through firmware** depends on the boot core (from memory for S3).
17. **The model does not cover** gate bugs, common-mode bugs or firmware lies.

### 6.3 What must be measured

| Question | How | What decides |
|---|---|---|
| Longest SMI on the reference desktop and the Dell | A loop on every core reading the counter, recording the largest gap, with `MSR_SMI_COUNT`, through boot, suspend, firmware updates, a long session | `STALE_NS` must exceed it with margin |
| False suspicions in practice | Ten-hour runs under load, thermal stress and idle, counting accusations of healthy nodes | Must be zero at the chosen `STALE_NS` |
| Fence time per architecture | x86-64: NMI to parked, INIT to parked (desktop, Dell); ARM64: SDEI or pseudo-NMI to `AFFINITY_INFO` OFF (an ARM64 board with TF-A; the Mac has no PSCI or SDEI, from memory, so it cannot measure this); RISC-V: QEMU and a board, IPI to STOPPED | `FENCE_NS` |
| Writes in flight after INIT | A core writes a unit's queue tail (or a scratch device register) in a loop and is INITed; another core samples the register for 10 ms | `SETTLE_NS`, and whether the argument of 3.5 holds |
| Reclaim time | 24 nodes, kill one holding 1,000 remote mappings and 100 waiting threads; time from accusation to dead | The recovery gate (proposed: under 50 ms after detection) and the size of the recovery reserve |
| Take-over of a unit role | Kill the holder of the NVMe's IOMMU unit during fio; measure I/O stall (target: none), time to the first served attach, IOTLB-miss dip after the global invalidation | Whether to skip the global invalidation when every entry matched |
| Directed EOI | SCI and a level INTx on the Dell and the desktop: Remote IRR behaviour, no lost or stuck interrupt across 10⁶ arrivals | Whether lines can be acknowledged from any node |
| Sweep power | Package power in deep idle with `SWEEP_NS` = 1 s against none | `SWEEP_NS` |
| *n*² structures | QEMU with 128 and 1,024 nodes: memory, barrier scan time | `NODES_MAX` |
| Mailbox call | Round trip through a `core` capability against an endpoint, same and other node | Whether the extra member-word read matters |
## 7. Changes needed elsewhere

### 7.1 kernel-interface.md

- **Rule 3.** Add to the exceptions fixed at start: the member table, the role table and the beacons; the kept image and the replacement kernel slot; the park stub's page (x86-64); the machine objects `core`, `iommu` and `role`.
- **Rule 7.** Add: "except the machine objects (`core`, `iommu`, `role`), which belong to no node; their state is in the machine table, which every kernel reads, and changes only through the write gate."
- **Objects table.** `core`: "Control of one node: start, stop, placement, status, watch; with `write`, its idle table and the right to configure scheduling contexts on it; with `send`, the node's mailbox. A machine object". `iommu`: add "a machine object, driven by the holder of its role". New row `role`: "One duty with one holder at a time: an IOMMU unit, an IOAPIC, a memory reserve, a leadership. A machine object | Project".
- **System calls.** "48 calls" becomes 56 (with the three memory calls of the draft of 15 November). The Cores row lists `core_start`, `core_stop`, `core_status`, `core_idle`, `core_watch`, `core_place`, `role_claim`, `role_hand`, with the note "Replacement is `core_stop` mode seal followed by `core_start` mode resume; recovery is automatic up to dead, and a reload is `core_start` mode fresh". The sentence "except those of the groups not yet specified (cores, debugging)" drops "cores".
- **Order of checks, item 3.** `core` leaves the `unsupported` list for the `invalid` list, with `role` and `memory_control`. Same in the `untyped_retype` row.
- **IOMMU.** "The units are driven by the kernel of the boot node" becomes "Each unit is driven by the holder of its unit role ([Roles](#roles))". "A unit that does not confirm within 1 ms (provisional) is a hardware fault of the node that owns it" becomes "... is a hardware fault of the unit: the holder keeps the role and retries; changes on the unit wait".
- **Interrupts, "Nodes."** Replace the boot-node rule for lines by: "A line can be claimed through the `irq_control` of any node; the redirection entry is written by the holder of the IOAPIC's role, on request. Where the local APIC suppresses EOI broadcast and the IOAPIC has an EOI register, `irq_ack` on a level line writes that register from the claiming node; otherwise the mask and unmask of a level line are requests to the role holder." In the source word, remove "or a line on a node other than the boot node". The remapping bullet: "Each node writes its own remapping entries (handles *node* × 192 to *node* × 192 + 191) through its gate; the invalidation of the interrupt entry cache is a request to the holder of each unit's role."
- **Idle.** "through a call of the Cores group" becomes "by `core_idle`".
- **Start-up state.** "The kernel of the boot core starts one process, the first service of the boot image, and gives it everything" becomes "The boot core runs the machine start-up, then every node, the boot core's included, starts its own first service, the node agent, from the kept image, with the same start-up layout". Rules 1, 2, 5 and 6 of "Memory, by rule" change as in part 1.3: the image region is kept and common; no image untyped; no device untyped; unclaimed chunks and device entries. The slots table becomes the one of 1.3.2. The entry `Cores` is sorted by hardware identifier with the boot core flagged; `Node` loses the boot node's index. The first thread is attached to "the start-up task (identifier 1 of its node)". Its context: budget 9,843,750 ns, period 10 ms, cores set {its core}, configured "with its own node's core capability, slot 16 + its index". The section "Hooks for a reloaded kernel" is replaced by a pointer to the Cores group.
- **Points for the two owners.** The row "Devices and lines on the boot node" is replaced by "Shared hardware as roles" (part 8, point 4); new rows from part 8.
- **Open points.** The bullet "The depth rule and a machine that does not die" is answered (1.3.2) and removed. "The groups not yet specified" keeps debugging and `ioports`.

### 7.2 kernel.md

- **Recovery of one core's kernel.** Item 2 becomes "Detection: evidence checked in shared memory (a node's own panic record, a heartbeat that stops while the core is not idle, a ring left unconsumed), never a vote". Item 3 becomes the order of part 2.10. "A complete stop happens only if containment itself is violated or if the failure repeats" becomes "... only if containment is violated; a node that fails repeatedly is left dead, or its core retired". The sequence diagram is replaced by one with: accusation, fence confirmed, unit role holders block the devices, every live node acks, dead, then `core_start` by a supervisor.
- **Nodes, cores and load.** "No node is necessary to the machine. The supervisor and the memory service exist on at least two home nodes" becomes "No node is necessary to the machine: every duty that needs one holder is a role that moves after a fence. The supervisor and the memory service run on the *k* nodes that hold the reserve roles." The open question "how a survivor tells a reference to a reloaded node from an old one (a generation number)" is answered.

### 7.3 The two drafts of 15 November

- `nodes-memory-devices.md`: the hardware node becomes one unit role per unit (part 1.3.4); anchors and their floors become reserve roles (1.3.5); free chunks and device entries start unclaimed (1.3.3); `memory_split` is allowed to the entry's owner; `StartNode` takes the 16-byte form of part 5; its "successor writer" hook is the dead-owner rule of 1.3.3; its weakness 10 (the order of recovery) is answered by part 2.
- `ownership-alternatives.md`: its gate gains the transitions of parts 2 and 3; its "single exception for the successor of a removed node" becomes the dead-owner rule; its claim that a reloaded node accepts "only the words that name its node" is widened to "the words of any dead node", since after dead nothing alive reaches them.

### 7.4 Decision log

A new entry to propose: "Proposed: symmetric nodes. Every duty that needs one holder is a role (IOMMU unit, IOAPIC, memory reserve, leadership), moved by its holder's last write or after its holder's core is confirmed stopped; every node starts the same way from a kept image; membership by evidence checked by the write gate, a fence per architecture, a reclaim barrier per dependency; the cores group (eight calls). Amends D-107 (the image region becomes kept memory; the floors are uniform), D-108 (the anchors become reserve roles), D-110 (start-up state), D-114 (the gate also takes unclaimed words and the words of dead nodes by compare-and-swap)."
## 8. For the humans

Each point is a trade-off of product, risk or measured performance. The rule written above is my recommendation.

| # | Point | Rule written (recommended) | Alternatives | What each costs |
|---|---|---|---|---|
| 1 | Cooperative fences on ARM64 and RISC-V | Accept fence class 1 (a signal the kernel cannot mask, a stop by its own handler, a confirmation by hardware or firmware) for unit roles when no class-2 core is live | A: ship DodOS firmware extensions (an SBI `fence_hart` on RISC-V, an EL3 service on ARM64) and require them. B: on class-1 machines, never take a unit role over after a death; wait for a restart | Rule: a hung kernel with a broken handler freezes its roles. A: forced fences everywhere, but DodOS maintains firmware, and Apple machines have no EL3 to extend (from memory). B: safest; the first hung holder freezes its unit's changes until a restart |
| 2 | An unfenced node | Freeze its memory, the memory of the nodes it maps, and its unit roles until the machine restarts; the machine runs degraded | A: restart the machine at once, with a trace. B: after a long wait (say 10 s) without a sign of execution, treat it as fenced | Rule: survives, but leaks. A: the machine dies, which is the goal it was built against. B: two writers become possible, if the core was alive after all |
| 3 | The kept image | Kept, read-only, common, for the life of the machine | Keep it in the memory of reserve role 0, and reload it from storage after a loss | Rule: tens of MB kept. Alternative: recovering the supervisor would need storage, so drivers, so the services that recovery is restarting |
| 4 | Shared hardware | One unit role per IOMMU unit, IOAPIC, GIC ITS and the GIC distributor, spread over the nodes; each node writes its own remapping entries; lines acknowledged through the IOAPIC's EOI register where it exists | A: the hardware node of the draft (one node holds all). B: all lines on the IOAPIC role's holder node | Rule: more roles, but a death stops changes on one unit only, and lines survive. A: simpler; every change of every unit waits for one node's recovery. B: no reliance on directed EOI, which Linux does not use; line drivers must follow the role |
| 5 | Reserves | *k* from the boot image, 2 ≤ *k* ≤ 8; size as the draft's anchors | Fixed *k* = 2 | Each reserve is memory set aside for a replica |
| 6 | `STALE_NS` | 100 ms by default | 10 ms (faster recovery) or 1 s (fewer false suspicions) | Detection time against the risk of fencing a healthy node during a long SMI; decided by measurement |
| 7 | Reload policy | The kernel never reloads a node; a supervisor calls `core_start` | Automatic reload with back-off | Rule: no reload if every supervisor is gone. Alternative: policy in the kernel, and a node that fails at start loops |
| 8 | Repeated failures | Leave the node dead or retire its core; stop the machine only on a containment violation | Keep kernel.md's "complete stop if the failure repeats" | The present sentence contradicts the goal of a machine that never dies |
| 9 | Machine object capabilities | One root `core` capability per node in each start-up space | One `machine` capability and a call that derives the `core` of an index | Rule: *n*² slots (64 MB at 1,024 nodes), no new call. Alternative: one more call and object kind, *n* slots |
| 10 | The mailbox | A `core` capability with `send` reaches the current generation's mailbox | Capabilities to every other node's mailbox, made at each start | Rule: one deliberate exception to "a reference to a reloaded node is `gone`". Alternative: a derivation recorded on both sides for every pair at every start |
| 11 | The x86-64 BSP | Class 1; no kernel role while a class-2 node lives | Try clearing the BSP flag of `IA32_APIC_BASE` after start-up so that INIT parks it like any core (from memory: the flag may be writable) | Rule: one core loses kernel roles. Alternative: unknown firmware behaviour (SMM rendezvous and S3 resume may depend on the flag); a hardware trial before any decision |
| 12 | `NODES_MAX` | 1,024 | 4,096 | *n*² memory: 8 MB of `acked` at 1,024, about 134 MB at 4,096 |
## 9. Sources

Checked on 15 November 2026 by web search and page fetches. Where a source was read only through a search excerpt or a mirror, it says so.

**x86-64**

- INIT blocked in VMX root operation and in SMM: Intel SDM mirror, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-1240.html ; Linux disables VMX on panic so that INIT works, https://lkml.iu.edu/hypermail/linux/kernel/1704.2/03347.html ; INIT latched in SMM (KVM), https://lkml.iu.edu/hypermail/linux/kernel/1506.0/03009.html and https://lkml.iu.edu/hypermail/linux/kernel/2404.2/01546.html (also: SMIs blocked but latched in wait-for-SIPI).
- INIT on the BSP runs the firmware's boot-strap code: Linux commit e1c467e69040, https://github.com/torvalds/linux/commit/e1c467e69040 ; removal of CPU0 hotplug (2023), https://lkml.indiana.edu/2304.1/07216.html
- Machine-check broadcast and CR4.MCE: SDM 15.10.4.1, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-536.html ; SDM #MC, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-233.html ; Linux commit 0cc3cd21657b, https://android-kvm.googlesource.com/linux/+/0cc3cd21657be04cb0559fe8063f2130493f92cf ; l1tf.rst, https://raw.githubusercontent.com/torvalds/linux/master/Documentation/admin-guide/hw-vuln/l1tf.rst
- Linux's INIT parking and its revert (SMI rendezvous on the lowest APIC ID): https://lkml.rescloud.iu.edu/2306.2/04176.html ; https://github.com/torvalds/linux/commit/fbe1bf1e5ff1e3b298420d7a8434983ef8d72bd1 ; MSR_SMM_BLOCKED, SDM 34.17.3, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-1280.html
- SIPI vector and the page below 1 MB: SDM 8.4.3, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-276.html
- MADT local APIC NMI structure, 0xFF for all processors: coreboot citing ACPI 6.3 table 5-52, https://forge.a-lec.org/GNUBoot/coreboot-kgpe-d16/commit/f5552cef97c90ace253dc2fa095d754b58979285 ; x2APIC variant, https://docs.rs/crate/raw-acpi/0.0.2/source/src/madt/local_x2apic_nmi.rs ; 8259 through LINT0 (MP spec transcription), https://blog.csdn.net/hezp1984/article/details/5841593
- Directed EOI and the IOAPIC EOI register: SDM 10.8.5, https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-393.html ; Linux io_apic.c (EOI register from version 0x20; Linux does not set directed EOI; with remapping the RTE vector is the pin number), mainline source; https://lore.kernel.org/all/20160426073426.GD28545@pxdev.xzpeter.org/
- UEFI runtime services and re-entry: UEFI 2.10 §8.1 (search excerpt), https://uefi.org/specs/UEFI/2.10/08_Services_Runtime_Services.html
- One invalidation queue register set per VT-d unit: https://edc.intel.com/content/www/it/it/design/publications/12th-generation-core-processor-datasheet-volume-2-of-2/invalidation-queue-address-register-iqa-reg-0-0-0-vtdbar-offset-90 ; Linux `struct intel_iommu` (one `qi`), `struct amd_iommu` (one `cmd_buf`), mainline source.
- TSC unchanged by INIT: SDM table 9-1, https://www.manualsdir.com/manuals/129204/intel-ia-32.html?page=378
- Linux kdump stops other CPUs by NMI and proceeds after 1 s: https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/kernel/crash.c ; https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/kernel/reboot.c

**ARM64**

- PSCI `CPU_OFF`, `CPU_ON`, `AFFINITY_INFO`, `MIGRATE_INFO_TYPE`: PSCI DEN0022E, https://documentation-service.arm.com/static/640f584656ea36189d4e94a4 ; Linux refuses to offline the Trusted OS core, `arch/arm64/kernel/psci.c` and `drivers/firmware/psci/psci.c` (mainline).
- SDEI event 0 and delivery with exceptions masked: https://trustedfirmware-a.readthedocs.io/en/latest/components/sdei.html ; Linux `drivers/firmware/arm_sdei.c`, `include/uapi/linux/arm_sdei.h` (mainline).
- Pseudo-NMI: `arch/arm64/Kconfig` (`ARM64_PSEUDO_NMI`), `arch/arm64/include/asm/irqflags.h` (mainline); FEAT_NMI not yet upstream, https://lkml.iu.edu/2607.0/06225.html
- Linux arm64 stop escalation and giving up: `arch/arm64/kernel/smp.c` (mainline).
- GICv3 registers and the ITS command queue: IHI0069A, https://documentation-service.arm.com/static/6012f824773bb020e3de7aad
- SMMUv3.3 ECMDQ: https://lkml.iu.edu/hypermail/linux/kernel/2106.3/02253.html

**RISC-V**

- SBI HSM and extension ID spaces: https://github.com/riscv-non-isa/riscv-sbi-doc (`src/ext-hsm.adoc`, `src/ext-vendor.adoc`, `src/ext-firmware.adoc`).
- Higher-privilege interrupts always enabled; Smrnmi ratified: https://github.com/riscv/riscv-isa-manual (`src/priv/machine.adoc`, `src/priv/smrnmi.adoc`).
- OpenSBI boot lottery: https://github.com/riscv-software-src/opensbi (`firmware/fw_base.S`).
- PLIC: https://github.com/riscv/riscv-plic-spec ; AIA: https://github.com/riscv/riscv-aia ; IOMMU 1.0: https://github.com/riscv-non-isa/riscv-iommu

**Prior work**

- Hive (full text searched): https://pdos.csail.mit.edu/archive/6.824-2004/papers/hive.pdf
- Cellular Disco (full text searched): https://pages.cs.wisc.edu/~stjones/proj/vm_reading/cellular-disco.pdf
- Quest-V (full text searched): https://arxiv.org/pdf/1112.5136
- Barrelfish/DC: https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-zellweger.pdf ; Barrelfish capability management, https://barrelfish.org/publications/TN-013-CapabilityManagement.pdf ; Häcki, https://barrelfish.org/publications/ma-haeckir-consensus.pdf
- fos (search excerpt): https://www.princeton.edu/~wentzlaf/documents/Wentzlaff.2009.OSR.fos.pdf
- K42: https://www.cs.bu.edu/~jappavoo/Resources/Papers/Krieger06.pdf
- Pacemaker fencing: https://clusterlabs.org/projects/pacemaker/doc/2.1/Pacemaker_Explained/html/fencing.html
- Fencing tokens: https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html ; Chubby: https://static.googleusercontent.com/media/research.google.com/en//archive/chubby-osdi06.pdf
- Chandra and Toueg (with the Isis remark): https://cs.nyu.edu/~apanda/classes/sp25/papers/chandra-toueg.pdf ; Fetzer (summary only): https://people.eecs.berkeley.edu/~fox/summaries/dependable/fetzer_crash_leases.html
- SWIM: https://www.cs.cornell.edu/projects/Quicksilver/public_pdfs/SWIM.pdf
- kmorph: https://github.com/multikernel/kmorph ; Linux multikernel RFC: https://lists.infradead.org/pipermail/kexec/2025-September/033875.html
- Otherworld: https://www.usenix.org/legacy/event/hotdep08/tech/full_papers/depoutovitch/depoutovitch_html/index.html ; seL4 clustered multikernel: https://trustworthy.systems/publications/nictaabstracts/vonTessin_12.abstract
- The two drafts of 15 November (`nodes-memory-devices.md`, `ownership-alternatives.md`) for the Nested Kernel, Rio and the gate.

**From memory (not verified):** that an x86-64 core's posted writes to device registers reach them within 1 ms of an INIT; that S3 resume enters on the BSP (Linux restarting the APs after resume is verified); that the IOAPIC uses an index and a data register; the handling of the VT-d queue error bit; that the BSP flag of `IA32_APIC_BASE` may be writable; that Apple silicon has no PSCI, SDEI or EL3; the durations of SMIs; virtual synchrony's views; the cost figures carried over from the earlier drafts.
