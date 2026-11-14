# Kernel

Statuses are defined in the [README](../README.md#status-legend). Verification marks ("from memory", "not cross-checked", check dates) are defined there too.

The kernel is a capability microkernel. A **capability** is a token that designates a kernel object together with the rights its holder has on it; a program can act only through the capabilities it holds. A **microkernel** keeps only capabilities, inter-process communication (IPC), scheduling, memory and IOMMU programming in the kernel; everything else runs in user space.

## Base decisions

| Topic | Position | Status |
|---|---|---|
| Kernel | Capability microkernel, 64-bit only, written from the model and not translated from seL4 | Decided |
| seL4 ABI | No lasting dependency. seL4 serves only as a black-box oracle for differential tests (see [verification](../plan/verification.md#kernel-verification)) | Decided |
| Languages | Kernel in Zig and Rust: Zig for the hardware layer and the IPC fast path, Rust for the logic (capabilities, object life cycle, scheduling policy). Rust for the system userland. Odin rejected | Decided |
| Zig / Rust boundary | Types are defined once in Rust `repr(C)`; a C header is generated and imported by Zig. No call crosses the boundary on the fast path. `zig build` drives cargo and does the linking | Aligned |
| System calls | System calls sit behind a code page supplied by the kernel and are never called directly. A system call is accepted only when it comes from that page; this is checked on entry | Decided (the entry check on 14 November 2026) |
| Kernel shape | Event-driven kernel with no per-thread kernel stack, which allows hot replacement | Aligned |
| System call duration | Every system call has a bounded duration, with resumption points, and the bound is verified | Decided, 14 November 2026 |
| Kernel heap | None. See [memory.md](memory.md) | Proposed |

The feasibility of the Zig / Rust boundary and of the event-driven kernel with no per-thread stack is "from memory"; both are trial subjects in weeks 1-2 of the [calendar](../plan/roadmap.md#calendar).

The kernel has its own replacement mechanism, based on versioned object formats (see [Hot replacement](#core-by-core-replacement)).

## Multi-core structure

**Decided, 14 November 2026.** One kernel per core, with no shared state; kernels talk only by messages. The recovery of one core's kernel is part of version 1 (decision of the user), and the points below follow from it.

- **Core group.** The term has one meaning: the per-core kernels that hold, by messages, the address space of one process. How a group is sized and budgeted is in [scheduling.md](scheduling.md#core-group-of-a-multithreaded-process).
- **Page tables.** Each core has its own copy of the page table of a process that is spread over several cores.
- **Capabilities.** The derivation tree (the tree that links a capability to the capabilities derived from it) crosses kernels. Revocation is a distributed two-phase protocol, with a formal model. It is also the core of the "task revocable in one operation" (see [research axes](../research/prior-art.md#kernel-research-axes)).
- **Memory ownership invariant.** Nothing that a live kernel depends on is recorded only in another kernel. Every remote mapping is recorded on both sides. A reloaded kernel queries its neighbours before it reuses a page; a page whose status is unknown is put in quarantine.
- **Inter-kernel protocol.** It is versioned, and compatible from one version to the next, so that the kernel can be replaced core by core.
- **Formal models.** Three models are checked by state exploration (TLA+ or equivalent): revocation between cores, change of size of a group, recovery of a kernel.
- **Services.** A service chooses to have one thread or one thread per core.
- **Hardware threads of one physical core.** In version 1: one kernel per physical core, and the second hardware thread stays idle.
- **Prior art to cite.** Hive (SOSP 1995).

Reasons recorded for the messages-only variant: kernels that share no state and talk by messages make the failure of one kernel the failure of one node in a distributed system. A replicated log (the NrOS technique) is state shared between kernels, which is harder to make safe if a kernel dies in the middle of a write.

### Hard points

- A process with several threads on several cores shares one address space, so its page tables and its capabilities must stay coherent between kernels (messages, TLB invalidation; the TLB is the processor's cache of address translations).
- seL4 also retains a statically partitioned multikernel as its path to verified multi-core, and discourages IPC between cores in it (verified 14 November 2026 by web search, abstracts and official pages).
- An overhead gate is added for IPC between cores (see [gates](../plan/gates.md#overhead-gates)).
- Performance cores and efficiency cores (P and E cores): the placement policy stays in user space (see [scheduling.md](scheduling.md)).
- The real gain of one kernel per core for P and E cores, and the compared cost of the alternatives below, are not measured.

### Alternatives kept as comparison points

These variants are no longer candidates. They are measured on the same bench as the retained variant.

| Variant | Description |
|---|---|
| Shared kernel with a short lock | One kernel for the core group of a multithreaded process, with a short lock, the group changing size with the load |
| Global lock | One lock for the whole kernel |
| Replicated log | The split is by kind of state, not by core. State that belongs to one core (IPC, scheduling, interrupts) stays local and lock-free. State of a process spread over several cores (address space, capabilities) is replicated through a shared log. Formerly proposed as a "hybrid structure" |

Precedents for these variants are listed in [research/prior-art.md](../research/prior-art.md#multi-core-structure-precedents).

### Dynamic structure

**Proposed.** The number of active cores and their assignment follow the load. Barrelfish/DC adds, removes and replaces a core at run time. The replica of a process exists only on the cores where it has a thread. A core that is not needed is removed, then brought back by the normal core start-up path.

Cores on demand are deferred until after the alpha (**Decided**, 14 November 2026; see [roadmap](../plan/roadmap.md#deferred-after-the-alpha)).

## Capabilities and revocation

- Any call on a capability can fail, because a capability is revocable (rule 1 of the [ABI](wasm-abi.md#abi-rules)).
- Revocation walks the derivation tree, a mechanism borrowed from seL4 (see [borrowings](../research/prior-art.md#borrowings)). With one kernel per core it is the distributed two-phase protocol described above.
- A right is a capability and a revocable line in a central place; see [security.md](security.md#permissions).
- Capabilities typed by WIT (**Aligned**: retained with the user's agreement, to be designed; from the second delegated study of 14 November 2026, not cross-checked): the compiler emits the manifest, and the WIT keywords `own` and `borrow` become derivation and attenuation. This is already the project's design. The earlier claim that it "does not seem to be published" is softened (**Decided**, 14 November 2026; see [prior art](../research/prior-art.md#novelty-claims-and-verdicts)).

## Recovery of one core's kernel

**Decided for version 1, 14 November 2026** (decision of the user). The mechanism below was proposed at the user's request and replaces "stop everything": a kernel that panics restarts alone, and the machine continues.

1. **Containment.** Each kernel maps only its own memory, and validates every message it receives from another kernel. Without this, a faulty kernel can write into its neighbours and nothing is guaranteed.
2. **Detection.** Panic, heartbeat between kernels, hardware error reported on the core.
3. **Recovery.** The order is: isolate the core, reset the devices whose driver ran on it, reclaim the memory, reload the kernel. The kernel is reloaded through the normal core start-up path. References to its objects return `gone`, which rule 1 of the ABI already requires callers to handle. A driver follows the [driver restart protocol](drivers.md#restart-of-a-driver). Recovery does not assume process snapshots: what happens to the processes that ran on the core follows [platform.md](platform.md#process-state-suspend-resume-and-snapshots).
4. **Later, research.** Adopt the state of the old kernel after validation, instead of starting again from saved state (Otherworld does this for Linux, with a stated 97 % success rate).
5. **Core with a hardware fault.** It is removed, and the machine continues with the others.

Further rules:

- A complete stop happens only if containment itself is violated or if the failure repeats. A trace is written to a reserved area (see [storage.md](storage.md#partitions)), then the machine restarts.
- Check: the deterministic simulation kills a kernel at random at every merge and verifies that the rest survives. A gate is to be set: the recovery time of a core (see [gates](../plan/gates.md#overhead-gates)).
- Prior art (web search of 14 November 2026, abstracts only): Barrelfish/DC replaces the kernel of a core at run time, with no failure evaluation found; Quest-V recovers after a failure but isolates its kernels by virtualisation; Kmorph (Linux, out of tree) keeps a spare kernel that takes over the machine in about one second. Hive (SOSP 1995) is to be cited. Recovery was recorded as a candidate research axis to claim, with a strong argument on the server side, to be verified; it is now part of [research axis 2](../research/prior-art.md#kernel-research-axes) (**Decided**, 14 November 2026).

### Core-by-core replacement

The same path replaces the kernel core by core: a kernel update without a reboot. It relies on the versioned inter-kernel protocol and on versioned object formats.

## Entropy

**Decided, 14 November 2026.** The kernel has a random generator fed by the processor, the interrupts and the TPM (the machine's security chip).

## Hardware features

From the second delegated study of 14 November 2026 (not cross-checked; figures to re-read in the papers), unless noted.

| Feature | Position | Status |
|---|---|---|
| FRED (new x86 event delivery, with the stack chosen per level) | Suits a kernel with no per-thread stack, and no paper evaluates it. To verify: does the reference processor have it? The classic path through the IDT (interrupt descriptor table) stays mandatory. FRED is deferred until after the alpha | Deferred: Decided, 14 November 2026. Presence on the reference processor: Open |
| APX (32 general registers, announced for Nova Lake) | Plan a wider register-based IPC message format | Not cross-checked |
| LAM | Not to be used (SLAM attack, disabled in Linux) | Not cross-checked |
| CET | To be required | Not cross-checked |
| Distinct core types | To be treated as lasting: Arm, Apple, Intel and AMD converge on it; the rumour of an Intel "unified core" around 2028 does not change this choice | Decided |
| Per-core-type kernel binary | One kernel per core allows a binary tuned per core type | Aligned (retained) |
| User interrupts (xUI, ASPLOS 2025; Aeolia, SOSP 2025) | Deliver an event to a component without entering the kernel | Aligned (retained, to be designed) |

Rejected, from the same study: a single address space shared between components and separated by protection keys (it contradicts the rule of one process per publisher, and user-mode keys can be modified by the code); a language model in the kernel.

## Related

- Scheduling mechanism: [scheduling.md](scheduling.md).
- Memory mechanism: [memory.md](memory.md).
- IOMMU objects: [drivers.md](drivers.md#iommu).
- Kernel verification, oracle and proofs: [plan/verification.md](../plan/verification.md#kernel-verification).
- Research axes and novelty claims: [research/prior-art.md](../research/prior-art.md#kernel-research-axes).
- Kernel ideas not yet proposed: [research/ideas.md](../research/ideas.md#low-level-and-kernel).
