# Heterogeneous cores: what exists, what DodOS should put in the kernel, and what it should not

Written 15 November 2026, in answer to one owner's thesis: DodOS should treat an assembly of unlike cores through an abstraction, as it treats CPU architectures, so that it uses each core for what it does best and gains responsiveness. He believes no current OS has really adapted. Nothing under `/Users/btw/Documents/repos` was edited. Verification marks: "verified" means checked on the web today, with the source in part 7. "From memory" means not checked.

**Verdict in one paragraph.** The premise is wrong as stated. Linux, Windows 11 and macOS have all adapted to unlike cores, and macOS has adapted deeply. What is really unsolved is narrower:

- knowing what a thread *needs* (the user's intent);
- knowing how much faster a given thread runs on a given core (the hardware hints have known limits);
- keeping time guarantees when a thread changes core;
- cores whose instruction sets differ, which every vendor and OS avoids.

DodOS is well placed on the first three, but not because of an abstraction. It is well placed because of three choices it already made:

- intent is carried by capabilities (the shell hands out the frame class);
- work is charged end to end (the budget follows the call);
- placement works from deadlines and exact per-context accounting, not from statistical estimates.

The analogy with architectures points the wrong way. An architecture layer *hides* differences that do not matter to policy. Here the differences *are* the input to policy, and hiding them loses what the placement service needs. The kernel's share is small and must be fixed now:

- describe each core as a *kind* with a feature set, not as a "class";
- keep every thread's vector state valid wherever it runs, through a feature mask fixed when the thread is made;
- pass on what only ring 0 can read: performance capabilities, the hardware feedback table, and the per-thread hardware class;
- count per context the instructions retired, besides the nanoseconds.

Budgets stay in nanoseconds of the core a context is on. The kernel scales nothing. The real cost of DodOS's structure is that moving a thread between unlike cores is a move between nodes, so placement must be sticky (role-based), not phase-by-phase as on Linux or Windows.

---

## 1. State of the art

### 1.1 Linux

- **Capacity-aware scheduling** (verified, kernel documentation). Each CPU has an *original capacity*, from `arch_scale_cpu_capacity()`. On arm64 and RISC-V it comes from the device-tree binding `capacity-dmips-mhz`. Task utilization is a PELT average made *frequency-invariant and capacity-invariant*: it "behaves as if the task ran on the highest-capacity CPU at maximum frequency".
  - A CFS task fits a CPU if its utilization is below that CPU's capacity. A task that does not fit ("misfit") is pulled to a bigger CPU by active load balancing.
  - The scheduling domains carry `SD_ASYM_CPUCAPACITY` and `SD_ASYM_CPUCAPACITY_FULL`.
  - `uclamp` lets user space clamp the utilization the scheduler sees: a high minimum pushes a small task to big CPUs, a low maximum lets a busy task run anywhere.
  - The documentation insists that utilization "is only ever estimated".
- **Energy Aware Scheduling (EAS)** (verified). At wake-up it picks, in each *performance domain* (a frequency domain), the CPU with the most spare capacity. It then compares the system energy, estimated from the Energy Model, against leaving the task on its previous CPU. Its requirements:
  - asymmetric capacity;
  - an energy model;
  - the `schedutil` governor;
  - invariant utilization;
  - no SMT ("EAS on SMT is not supported").

  It turns itself off as soon as a CPU of the root domain is above 80 % of its capacity ("over-utilized"), and ordinary load balancing takes over. So EAS is a policy for light load only.
- **Intel hybrid on Linux** (verified). From 2024, `intel_pstate` sets the asymmetric capacity of each CPU from `HWP_HIGHEST_PERF` in `MSR_HWP_CAPABILITIES`, replacing the older ITMT priority ordering. EAS was enabled for Intel hybrid platforms *without SMT*, for example Lunar Lake, in Linux 6.16 (merge of 28 May 2025).
- **Intel Thread Director and HFI on Linux** (verified). The HFI driver reads the per-CPU performance and energy-efficiency capabilities (0 to 255, one table per package, updated with a thermal interrupt). It "relays the update to userspace using the thermal notification framework".
  - The *classes* of Thread Director were proposed by Ricardo Neri from 2022 to 2024, with a per-task class read on the tick and HRESET at context switch. I found only mailing-list postings and no evidence of a merge. As far as I could verify, the mainline scheduler does not use the classes.
  - AMD has an equivalent: `amd_hfi` with workload classes and a ranking table, documented in mainline from 2025. Its documentation says the scheduler *can* use the rankings, not that it does.
- **`SCHED_DEADLINE` and capacity** (verified).
  - Capacity-aware admission (`dl_bw_capacity()`: the sum of the capacities of the root domain, not the number of CPUs) was added by Dietmar Eggemann's 2020 series, with an "XXX Fix" left for the default root domain. The deadline documentation still describes admission per number of CPUs.
  - A deadline task wakes on a CPU only if its bandwidth fits that CPU's capacity, otherwise "the task will remain on its current CPU".
  - Runtime is consumed in *scaled* time: frequency × capacity, from Juri Lelli's 2017 scale-invariance work. In 2025 that scaling had to be removed for the fair "deadline server": on big.LITTLE it turned a 50 ms budget into about 0.24 ms of scaled time and starved real-time tasks for over 10 s.
  - So Linux budgets are, in effect, in "work at maximum capacity" units, and the corner cases are still being found.
- **Feature asymmetry** (verified):
  - *AArch32 on some cores only* is the one case Linux supports. It needs an opt-in (`allow_mismatched_32bit_el0`). On `execve` of a 32-bit program the affinity is forced to the 32-bit-capable CPUs. `sched_setaffinity` keeps only those. The first 32-bit-capable CPU cannot be taken offline. `SCHED_DEADLINE` admission of such tasks on the default root domain is refused.
  - *SVE vector length*: the boot CPU sets the set of lengths, early secondaries narrow it, and a late CPU that lacks a length in use "dies early".
  - *RISC-V V*: every hart must have the same `vlenb`. A secondary hart that differs fails to boot. A maintainer: differing lengths are "just not something we support in Linux".
  - *x86 AMX*: the large state is enabled per process by `arch_prctl(ARCH_REQ_XCOMP_PERM)`. The first use traps, and the kernel then enlarges the task's buffer (SIGILL without permission, SIGSEGV if the allocation fails).
- **Clusters**. `CONFIG_SCHED_CLUSTER` adds a scheduling level for CPUs that share an L2 or a tag (Kunpeng 920: 4 CPUs per cluster), and the wake-up scans the cluster first (verified for the patches; merged in 5.16 with Intel Jacobsville as the other user, from memory).
- **Capacity that changes at run time**: "thermal pressure" became "hw pressure" (renamed in 2024): a reduction of capacity imposed by hardware or firmware limits, filtered, and subtracted from capacity (verified).
- **sched_ext**: policies loaded as BPF. `scx_lavd` packs work onto the fastest cores at low load ("core compaction"), with an option to prefer little cores (verified). This is Linux's own admission that the policy wants to live outside the core scheduler.

### 1.2 Windows 11

- **QoS levels** (verified, Microsoft Learn): High, Medium, Low, Utility, Eco, Media, Deadline. "On platforms with heterogeneous processors, the QoS of a thread may restrict scheduling to a subset of processors, or indicate a preference for a particular class of processor." Priority still decides what runs next; QoS decides the core type and the frequency.
- **Where the QoS comes from** (verified): the window state (in focus: High; visible: Medium; minimized or fully hidden: Low), audibility, explicit tagging (`SetProcessInformation`, `SetThreadInformation`: EcoQoS or HighQoS), the Multimedia Class Scheduler Service (Media, Deadline), and heuristics such as a lowered thread priority. Since 2025, the foreground application is lowered to Medium after a period without user input, on battery.
- **Intel Thread Director**: the processor reports per-thread hints, which the Windows 11 scheduler uses (vendor material; secondary sources, verified as reporting).
- **CPU sets** describe each logical processor with `CoreIndex` (SMT siblings), `LastLevelCacheIndex`, `NumaNodeIndex`, `EfficiencyClass` ("higher values... faster but less power-efficient"), a `Parked` flag, and `SchedulingClass` (verified). This is the closest precedent for "a table of numbers rather than a class".
- **Known failure** (verified as many user reports and one vendor note, not a controlled study): a render or archive job whose window is minimized drops to Low QoS and runs on E-cores, up to twice slower. Blender added an API call to keep all cores. Intent is inferred from window state, and the inference is wrong for long jobs the user waits for.

### 1.3 macOS on Apple silicon

- **QoS classes, declared by developers** (verified through Howard Oakley's measurements). Background QoS (9) and below run on E cores only, "even if they're all idle and the E cores are busy", and cannot be promoted. Utility and above go to P cores first, and spill to E cores when no P core is free.
- **Clusters are the unit** (verified):
  - On M4 Pro and Max, macOS fills one P cluster before opening the second.
  - The frequency of a P cluster follows the total active residency of the cluster (4,512 MHz for one thread, about 3,852 MHz at full load).
  - Threads move inside a cluster about every 0.1 s, but between clusters only every 4 to 5 s.
- **The XNU Edge scheduler** (verified, Apple's open-source design note). It keeps per-cluster run queues. It models the machine as a graph whose nodes are clusters and whose edges carry migration and steal permissions and a migration weight, one graph per QoS. The *performance controller* (CLPC) gives a recommended cluster per thread group and can change the edges at run time.
  - The kernel holds the mechanism (per-cluster queues, the graph), and a controller outside the scheduler core sets the policy. This is the nearest existing design to DodOS's split.
  - It also has policies for "shared resource" threads (round robin over clusters, or native cluster first) and a "stir-the-pot" rotation that swaps long-running threads between core types so parallel work progresses evenly.
- **Shared accelerators**: Apple's matrix unit (AMX, then SME on M4) is one block per cluster, shared by its cores. The E cluster's block is smaller and markedly slower (verified only through a community report and Oakley's measurements: no Apple statement).

### 1.4 Fuchsia (a microkernel precedent)

- Frequencies are set in user space, so the kernel must be told when a CPU's relative performance changes. `zx_system_set_performance_info` gives the kernel a fixed-point *performance scale* per CPU, relative to the fastest (verified, RFC-0123 and the syscall reference).
  - The RFC recommends calling it *before* a frequency decrease and *after* an increase.
  - For a deadline thread pinned to a CPU whose scale changes by α, "the actual time allotted to the thread is multiplied by 1/α".
- Zircon therefore normalises deadline budgets to work, like Linux. DodOS decided the opposite ("budgets are counted in time", Decided 14 November 2026). Part 3 keeps that decision and explains why.

### 1.5 Research

- **Li et al., HPCA 2010** (Intel), on cores with "asymmetric performance and overlapping, but non-identical instruction sets": *fault-and-migrate* (an instruction the core lacks traps, and the thread is moved to a core that has it), then faster-first scheduling (verified, abstract).
- **Sáez and Prieto-Matias, APSys 2022**, evaluated Thread Director on Alder Lake under Linux. Because of "various TD's limitations identified with our analysis", they built their own predictors from performance counters (machine learning) for throughput and fairness schedulers (verified, abstract; the list of limitations is in the paper, not read). Follow-up: PMCSched (2023), custom policies without kernel patches.
- **Helios (SOSP 2009)**: *satellite kernels*, one per unlike processor, with "a single, uniform set of OS abstractions" and affinity metadata for placement (verified, abstract). It is the closest research ancestor of one kernel per core *type*.
- **Popcorn Linux**: heterogeneous-ISA migration with compiler support (verified for the 2015 paper; the 2017 EuroSys paper was not found).
- **Barrelfish**: one kernel per core with heterogeneous hardware as a goal (already cited by the project).

### 1.6 The hard cases

| Case | What exists | Status |
|---|---|---|
| **Cores with different instruction-set features** | Alder Lake: AVX-512 was disabled (and in the end fused off) on the P-cores because the Gracemont E-cores lack it, "to ensure an even ISA" (verified; the fuse versus microcode question is disputed). AVX10 was first specified with a 256-bit converged width for E-cores; reports say the cap was later dropped and Nova Lake brings 512-bit on both core types (verified as press, not as Intel documentation). Arm: Linux refuses SVE length mismatches (verified). SME on M4 and on Arm C1 is a unit shared per cluster that every core can issue to (verified, secondary). RISC-V: Linux refuses a different `vlenb` (verified). The Kendryte K230 has RVV 1.0 on its 1.6 GHz core and none on its 800 MHz core, and is run as two separate OSes (verified) | **Avoided by everyone** in symmetric multiprocessing. Only AArch32 asymmetry is handled, by forcing affinity |
| **SMT siblings** | EAS does not support SMT (verified). Intel dropped Hyper-Threading on Lunar Lake and Arrow Lake ("we can scale using E-cores", verified). D-028 already idles the second hardware thread | The problem is shrinking on Intel client parts |
| **Clusters sharing a cache or a frequency domain** | Gracemont E-cores come in modules of 4 sharing one L2 (2 MB, then 4 MB) (verified; I found nothing on whether a module is one frequency domain). Apple P and E clusters share L2 and frequency (verified for frequency). Linux models frequency domains (EAS performance domains) and cache clusters (`SCHED_CLUSTER`). XNU schedules per cluster | Well understood. The interference between threads inside a module is not modelled by anyone except Apple's "shared resource" policies |
| **NUMA** | Orthogonal; every OS treats it separately (from memory) | Not specific to heterogeneity |
| **Capacity that changes at run time** | Intel HFI: "on some models, capabilities are set at boot time and never change. On others, capabilities may change every tens of milliseconds" (verified). Linux hw pressure. Fuchsia's performance scale | Mechanism exists. Using it without over-reacting is policy |
| **Three or more tiers** | Meteor Lake: P, E and LP-E cores (verified through Intel interviews). Arm C1 clusters mix Ultra, Premium, Pro and Nano cores (verified). On Meteor Lake, CPUID leaf 0x1A reports the same "Atom" type for E and LP-E cores, so further checks are needed (from a search summary of an Intel forum thread that could not be fetched; treat as from memory) | A binary "P or E" class is already wrong |
| **Accelerators reachable only from some cores** | No shipping SMP CPU has an in-core accelerator that only some cores can issue to. The real case is a *shared* unit per cluster (Apple AMX/SME, Arm C1-SME2), which is a contention problem. Devices (GPU, NPU) are reachable from every core | A feature per kind covers it; contention is policy |

### 1.7 The owner's claim, corrected

"No current OS has really adapted" is wrong:

- Linux has had capacity awareness, misfit migration, energy-aware placement, capacity-aware deadlines, utilization clamps, cluster domains and hardware pressure for years. Android runs EAS on its phones (from memory).
- Windows 11 uses Thread Director, QoS levels and efficiency classes.
- Apple designed the OS and the chip together: developer-declared QoS, a performance controller, per-cluster scheduling, and migration rates chosen for thermals.

What *is* true, and what DodOS can claim to address:

1. **Intent is guessed.** Windows infers it from window state and gets long jobs wrong. macOS trusts developers' declarations and never promotes Background. Linux has no intent signal unless the user sets `uclamp`.
2. **Speed per thread is guessed.** Linux uses one scalar capacity per CPU. Thread Director and AMD's classes exist because the speed-up depends on the instruction mix, but their hints have known limits, and Linux does not use the classes.
3. **Guarantees do not survive the move.** No mainstream OS gives a deadline guarantee that holds when a thread changes core type and the core is throttled. Linux's capacity-aware `SCHED_DEADLINE` is partial and still being corrected (2025).
4. **Heterogeneous ISA is unsolved**, because everyone forbids it.
5. **Migration costs against phase changes**: hints change every tens of milliseconds, while useful migrations between clusters are seconds apart on Apple.

### 1.8 What is genuinely still unsolved

- Predicting, per thread, the speed-up and energy on each core type, online and cheaply.
- Time guarantees under unlike cores and changing capacity.
- Execution across cores with different features, without pinning or emulation.
- Contention for shared cluster resources (L2, the matrix unit, a cluster's frequency) between threads of different classes.
- Policy from real intent: who is waiting for this work.

---

## 2. What the DodOS architecture makes easy or hard

### 2.1 Easy, or already better than the mainstream

- **Intent is explicit.** The frame class is a capability that the shell hands to the foreground surface and to the services on its path ([scheduling.md](scheduling.md#classes)). The placement service does not guess from window state. A minimized render that the user waits for can be given an interactive context by policy; Windows cannot express that without the application's help.
- **Work is charged end to end.** The budget follows the call: a passive server runs on its client's context, so the client's core and class apply to the server's work on the same core. Windows and Linux run a server thread at its own priority and QoS. macOS donates importance across XPC (from memory).
- **Exact accounting.** Each kernel debits budgets exactly, so the placement service knows each context's real consumption, without PELT estimates.
- **Deadlines instead of priorities.** A context declares *B* in *T*. With a measured speed per kind, the placement service can compute whether a context fits on an E-core, which a priority cannot say.
- **The OS owns code generation.** Applications are Wasm, compiled by the system's compile service. Heterogeneous ISA becomes a code-generation choice: compile to the features of the kinds a thread may run on. Linux cannot do this, because binaries arrive compiled and pick their code paths once, at load time (glibc `ifunc`, from memory). This is DodOS's one genuine structural advantage on unlike instruction sets.
- **Parking fits the "E-cores first" policy.** At low load, nodes parked on an efficiency core (Lunar Lake schedules "to the E-cores first", verified as Intel's claim) is the D-108 mechanism as it stands.

### 2.2 Hard, or worse than the mainstream

- **A move between unlike cores is a move between nodes.** On Linux a P to E migration is a run-queue change in one kernel. On DodOS it is a message protocol: admission at the destination, the thread object moved, and the address space present on one more node of the core group. So DodOS cannot follow hardware hints that change every tens of milliseconds. Placement must be *sticky*: by role and class, re-examined every few periods. Apple's cross-cluster interval of 4 to 5 s suggests that this loses little, but it is not measured.
- **What a budget means after a move.** A budget is nanoseconds of the core the context is on. On a slower core the same *B* buys less work. The kernel cannot fix this honestly: there is no single speed ratio between two kinds, since the ratio depends on the code (that is why Thread Director has classes). The placement service, which decides the move, must choose the new *B* (part 3 gives the move a way to carry it).
- **Admission "against one whole core" still means something**: *B* nanoseconds in each *T* on that core, guaranteed by the order of deadlines. It no longer means equal *work* across cores. It also loses meaning under SMT, where a sibling changes your speed. D-028 avoids that, and Intel's recent client parts have no SMT.
- **The kernel's own reflex** (an idle core takes a ready context from a neighbour, inside the context's cores set) moves contexts without changing their budgets. The cores set is the placement service's tool: a frame-class context whose work matters is given cores of one kind only.
- **The three multi-core candidates** of [kernel.md](kernel.md#nodes-cores-and-load):
  - *A node on one core*: the default and the cleanest; every move between kinds is a node move.
  - *Fixed groups*: **hardware clusters are the natural groups on hybrid parts.** The cores of a Gracemont module share an L2, so a lock line stays in that L2. They are of one kind, with one feature set and one meaning of a budget. On Apple and Arm they form one frequency domain, so their scheduling decisions interact anyway. XNU already schedules per cluster. On Intel, each P-core has a private L2, so groups degenerate to single cores, which is the node-per-core case. **Recommendation for the trial:** measure the group candidate on one E-core module of the reference desktop, if it is hybrid, and on one Apple cluster (the Mac trial).
  - *Dynamic groups*: a group may span kinds, so its lock would serialise a P-core behind an E-core holding it. If adopted, groups should not span kinds (policy, from the kind table).
- **Parked nodes** must be parked on a core that can run their threads. A P-node parked on an E-core runs its budgets in E-core time. That is acceptable at low load, but not for a frame-class context (policy). The feature rule is a kernel rule (part 3).
- **Sleeping cores and idle states** are already per core (the idle table is given per core by user space). Unlike cores change nothing there.
- **The memory minimum per node** (16 MB in the draft on nodes and memory) is paid by every core, LP E-cores included. On 24 cores that is under 0.6 % of 64 GB. It is not a reason to deny a node to small cores.

---

## 3. Proposal: what the kernel contract must contain now

Mechanism only. The placement policy is not designed here; 3.2 lists the inputs it needs.

### 3.1 Text ready for kernel-interface.md

Placed as a subsection of [Scheduling and time](kernel-interface.md#scheduling-and-time), after "One kernel per core".

> #### Unlike cores
>
> **Proposed, 15 November 2026: written, no reference model yet, not reviewed.** A machine may have cores that differ in speed, in energy, in instruction-set features and in vector length. The kernel describes each core, keeps every thread's register state valid wherever it runs, counts what each context did, and passes on what only the kernel can read from the hardware. It decides nothing about where work goes. The placement service decides, from these inputs. The rules are the same on x86-64, ARM64 and RISC-V; the architecture layer gives the bit lists and the registers.
>
> ##### Kinds
>
> - **A kind is a set of cores that report the same identification and the same features.** At start-up the boot kernel starts every core long enough to read them, then stops it. It reads:
>   - x86-64: CPUID leaves 0x1, 0x7, 0xD and 0x1A, `MSR_HWP_CAPABILITIES` or the AMD CPPC capability register;
>   - ARM64: `MIDR_EL1`, `MPIDR_EL1` and the `ID_AA64*` registers;
>   - RISC-V: the hart's ISA string given by firmware (ACPI RHCT or the device tree, the one firmware table the kernel reads on RISC-V, as it reads the MADT on x86-64) and `vlenb`.
>
>   Kinds are numbered from 0 in the order of their first core in the core list, so the boot core's kind is 0. Two cores that differ in any feature, or in an identification word, are of different kinds.
> - **The identification of a kind** is up to three raw 64-bit words, copied as read: on x86-64, CPUID.1.EAX and CPUID.1AH.EAX; on ARM64, `MIDR_EL1`; on RISC-V, `mvendorid`, `marchid` and `mimpid` as firmware gives them. The kernel gives them no meaning.
> - **Hardware threads of one physical core** are not separate entries: the core list has one entry per physical core, with its number of hardware threads (D-028: the second one stays idle).
>
> ##### Features
>
> - **A feature is one bit of a 64-bit word whose list is fixed per architecture in `abi/`.** Bits 0 to 31 are *state features*: they add registers that the kernel must enable, save and restore. Bits 32 to 63 are *instruction features*: they add instructions and no registers. A feature that is not listed is neither used nor reported by the kernel.
> - **One length per vector feature (design choice).** For each state feature that has a length (ARM64 SVE and SME, RISC-V V), the kernel uses one length on the whole machine:
>   - The length is the one supported by the most cores that have the feature, the longer on a tie.
>   - On ARM64 the kernel sets that length on every core that supports it (`ZCR_EL1`, `SMCR_EL1`).
>   - A core that cannot use that length counts as lacking the feature, and the feature is never enabled on it. RISC-V cannot shorten VLEN, so a hart of another VLEN lacks V.
>
>   Why: user code can read a vector length once and keep it, so a thread must never see two lengths, and the save area must have one size. Linux refuses such a core outright (SVE, RISC-V V). This rule keeps the core, without the feature. The alternative is to refuse to start the core.
> - **Baseline and optional state features.** A state feature that every kind has, and that the architecture layer does not list as *large*, is **baseline**: it is enabled for every thread. Every other state feature is **optional**: a thread may use it only if its feature mask holds it. Large features are always optional: x86-64 AMX (8 KB of tile data), ARM64 SME (the ZA array is SVL²/8 bytes). Instruction features are never in a mask.
>
> ##### The feature mask of a thread
>
> - **The feature mask is fixed when the thread is made, and never changes (design choice).** It is the size argument of `untyped_retype` for a thread, which was 0.
>   - A bit above 31, or one that names no listed state feature, is `invalid`.
>   - A bit for a feature that no kind of this machine has is `unsupported`.
>   - A bit for a baseline feature is accepted and has no effect.
>   - These are judged with the size argument (Order of checks, item 3).
>
>   Why: the kernel has no heap, so a thread's save area must be paid for when the thread is made, and a fixed mask makes every rule below a comparison of two words. The alternatives were allocation at first use, as Linux does for AMX and SVE, which needs kernel memory at fault time and which rule 3 forbids, or the area of every feature for every thread (AMX plus SME at the longest SVL would be 8 KB plus 512 KB per thread).
> - **The size of a thread** is the smallest power of two at least 1 KB + the baseline bytes + the bytes of each optional feature in the mask. Each value is the largest over the kinds, and is published in the entry `Features` of the start-up page. The entry `ObjectSizes` gives the size for mask 0.
> - **What a core enables for a thread.** On a core, the kernel enables the baseline, plus the optional features of the thread's mask that the core's kind has, and nothing else. It saves and restores exactly that set, so the layout of the area is the same on every core where the thread runs (x86-64: XSAVES and XRSTORS with that set as the requested features, from memory).
>   - x86-64: an optional feature that XFD covers (AMX) is disabled through `IA32_XFD`. Any other optional feature is disabled through XCR0, written at a switch between two threads whose enabled sets differ.
>   - ARM64: through `CPACR_EL1` (ZEN, SMEN).
>   - RISC-V: through `sstatus.VS` = Off.
> - **Using a feature that is not enabled for the thread raises the fault *undefined instruction*** (kind 2), with word 4 = 1 + the feature's bit when the trap names the feature: `IA32_XFD_ERR` on x86-64, the exception class on ARM64, `sstatus.VS` Off on RISC-V. An instruction that the core does not have at all raises the processor's own exception: kind 2, word 4 = 0. The kernel never emulates an instruction. A handler that receives kind 2 with word 4 = 0 on a thread that runs correctly elsewhere asks the placement service to move it: this is *fault-and-migrate* (Li et al., HPCA 2010), done in user space.
> - **Where a thread may go (the one placement rule the kernel enforces).** A thread is moved to another node only if that node's core kind has every optional feature of the thread's mask. The move protocol (multi-core part) judges this at the destination: after the destination is found to be in the context's cores set, and before admission. A failure is `busy`. A thread may run on the node where it was made even if that node's kind lacks a feature of its mask: the feature is then not enabled there, and no state of it exists yet.
> - **A node is parked only on a core whose kind has every feature, state and instruction, of the node's own kind (design choice).** Why: parking is invisible above the kernel (D-108), so a parked node's threads must not meet a missing instruction. The alternative, parking anywhere and letting threads fault, makes parking visible.
> - **Instruction features are not enforced for threads.** The kernel cannot know which instructions a thread's code holds. The compile service generates code for the features common to the kinds in the thread's cores set, and the placement service keeps the thread inside that set.
>
> ##### What the kernel publishes about the cores
>
> Fixed for a boot, in the machine table and the start-up page:
>
> - **Per core** (`StartCore`): its hardware identifier (x86-64 APIC ID, ARM64 `MPIDR_EL1` affinity, RISC-V hart ID), its node, the slot of its `core` capability, its kind, flags (bit 0 boot core), its number of hardware threads, its package, and three raw performance values, 0 where the architecture has none:
>   - the highest and the most efficient performance level from the performance-capability register (x86-64 `MSR_HWP_CAPABILITIES` or the AMD CPPC capability register);
>   - the power-efficiency class of the core's MADT GICC entry on ARM64 with ACPI.
>
>   These differ between cores of one kind (favoured cores).
> - **Per kind** (`StartKind`): its features, its identification words and its number of cores.
> - **For the machine** (`Features`): the baseline mask, the baseline bytes, and for each feature bit its save-area bytes and its length in bits (0 if it has none).
>
> **Not published by the kernel (design choice):** caches and clusters, frequency domains, NUMA proximity, idle and power states, and capacity or efficiency figures from firmware. The platform service reads them from firmware (ACPI PPTT, SRAT, `_CPC`, `_PSD`, or the device tree) and gives them to the placement service. Why: the kernel needs none of them to keep any rule, and reading them would put more firmware parsing in the kernel, against D-054. The values above are the exceptions, because only ring 0 can read them, or because the kernel reads that table anyway.
>
> Changing at run time:
>
> - **The current performance capabilities** of a core (x86-64: the four fields of `MSR_HWP_CAPABILITIES`, from memory) are returned by `core_status` (Cores group).
> - **The hardware feedback table** (Intel HFI, with the Thread Director classes when present) is kept memory, one per package, sized at start from CPUID (rule 3: fixed at start). The kernel points the processor at it and enables it before the first process. Its capability is a frame made from no untyped, `read` only, one per package, in the start-up space (see [Start-up state](#start-up-state)). The processor writes it; the kernel never does. Where the architecture or the processor has no such table, there is no frame.
> - **A change is signalled as an interrupt.** Source kind 3, *core event*, is claimed through the `irq_control` of the node, as any vector (see [Interrupts](#interrupts)). Event 1 means that the hardware feedback table or the performance capabilities of the node's core changed (x86-64: the thermal entry of the local APIC, from memory). It is an edge source and follows the rules of `irq_ack`. On an architecture without such an event, `irq_claim` with kind 3 is `unsupported`.
>
> ##### Scheduling contexts on unlike cores
>
> - **Budgets and periods are nanoseconds of the core the context is on, and the kernel scales nothing (design choice).** Admission stays per core, in time: *B* nanoseconds in each *T*, whatever the core. Why:
>   - There is no single speed ratio between two kinds: it depends on the code, which is why Thread Director and AMD give a capability per class.
>   - A guarantee in work would depend on a number that changes with temperature, and admission would stop holding when it changes.
>   - Time is invariant under frequency changes, and the order of deadlines guarantees it exactly.
>
>   The alternative, budgets normalised to work (Linux `SCHED_DEADLINE` scales consumed time by frequency and capacity; Zircon multiplies a deadline thread's allotment by 1/α when its CPU's scale changes by α), gives a guarantee in work that is only as good as the scale. The 2025 Linux fix for the deadline server shows where that leads. The decision "budgets are counted in time" (14 November 2026) stands.
> - **A move may carry new parameters.** The move protocol accepts, with the context, an optional new budget, period and class, which are admitted at the destination in place of the old ones, in the same step. With them, *r* = min(*r*, new *B*), and *d* and a replenishment instant are unchanged, as for `sched_configure`. So a context never runs on the destination with the budget of the source, and admission is judged with the bandwidth it will really have. The alternative, reconfiguring after the move, leaves a window with the wrong budget, and can be refused by admission with the old budget when the new one would fit.
> - **The kernel's reflex steal** takes a context only if the stealing core is in its cores set and the rule on optional features holds. It never changes the parameters. A placement service that wants a context to keep its meaning in work gives it cores of one kind.
> - **The hardware class of the work (design choice).** Where the processor classifies the running code (x86-64: Intel Thread Director, `MSR_IA32_HW_FEEDBACK_CHAR`, and AMD's workload classification), the kernel reads the class when a *context* stops running on the core, and records it in that context; then it resets the processor's history (Intel: HRESET; AMD: its reset register). `sched_read` returns it in bits 8 to 15 of the state word, as 1 + the class, or 0 when there is none. The kernel does not read it when only the thread changes inside one context (a call or an answer to a passive server). That work is charged to the context anyway, and the fast path keeps its cost. The alternative, reading at every thread switch as the Linux proposals did, adds an MSR read and an HRESET (about 28 to 45 cycles, measured by Intel) to every `call`.
> - **Instructions retired per context (design choice).** Each context counts, besides the nanoseconds in *consumed*, the instructions retired while it ran, in user and kernel mode (x86-64: fixed counter 0, enabled at start and never written again; ARM64: the activity monitor's instructions-retired counter; RISC-V: `instret`). The count is charged at the same events as the time. `sched_read` returns it as a fifth result, and 0 where the architecture layer cannot count. Why: instructions per nanosecond, per context and per kind, is the measured speed-up that the placement service needs on every architecture. ARM64 and RISC-V have no Thread Director, and the evaluation of Thread Director on Linux replaced its hints with counter-based models.
> - Lends are unchanged: a lend never crosses kernels, so a passive server always runs on the core of the client whose context it uses.
>
> ##### What stays in the placement service
>
> Which kind each context goes to; the cores set of each context; the budget each context gets on each kind; when to move; when to park; how to use the hardware feedback table and the classes; which clusters, frequency domains and NUMA nodes exist; frequency preferences; and the interference between threads that share a cluster's cache or matrix unit. The kernel holds no capacity scalar and no energy model.

### 3.2 Inputs the placement service needs, and where each comes from

| Input | Source |
|---|---|
| Kinds, features, vector lengths, sizes | Start-up page (`StartKind`, `Features`) |
| Which cores share a module, a cache, a frequency domain; NUMA | Platform service, from firmware (PPTT, `_PSD`, SRAT, device tree); on x86-64 also CPUID leaves 4 and 0x1F, which user code can execute on each core |
| Static and current performance capabilities per core | `StartCore`, then `core_status`; changes signalled by core event 1 |
| Per-class performance and efficiency per core (Intel HFI) | The read-only feedback frame of the package |
| Per-context time, instructions, hardware class, budget state | `sched_read` |
| Per-core idle, slack and kernel time | `core_status` |
| Intent | Capabilities: frame class from the shell, background from the manifest, latency contracts |
| Temperature, battery | Platform and power services |

### 3.3 Changes needed elsewhere in the contract

- **Start-up page, entry `Cores`.** Replace "`StartCore` records (24 bytes): APIC ID, node, class (0 performance, 1 efficiency, 0 for every core of a processor that has one type), flags (bit 0 boot core), slot of its `core` capability, reserved. ... At start-up the boot kernel starts each other core long enough to read its type (x86-64: CPUID leaf 0x1A), then stops it" with the `StartCore` of 3.4, and: "At start-up the boot kernel starts each other core long enough to read its identification, its features and its performance capabilities ([Unlike cores](#unlike-cores)), then stops it." Why the class goes: a binary class cannot express three tiers (Meteor Lake, Arm C1). On Meteor Lake CPUID leaf 0x1A reports the same type for E and LP-E cores (from a search summary, to confirm on hardware). ARM64 and RISC-V have no such register.
- **Start-up page:** add entries 18 `Kinds`, 19 `Features`, 20 `Feedback`. They are numbered after 17, which the nodes-and-memory draft takes.
- **Start-up slots, "16 onwards":** after the `iommu` capabilities, "one read-only frame per package for the hardware feedback table, in the order of the entry `Feedback`, where the processor has one". Each is the root of its object, at depth 1, with `read` only. **Rule 3** gains "the hardware feedback table of each package" in its list of fixed exceptions. **Kept** memory (Start-up state, rule 1) gains it too.
- **`untyped_retype` row:** "0 for the other kinds" becomes "the feature mask for a `thread` ([Unlike cores](#unlike-cores)), and 0 for the other kinds". **Order of checks**, item 3: add "for a thread, a mask bit that names no listed state feature is `invalid`, a bit for a feature no kind has is `unsupported`".
- **Object sizes, `thread` row:** "1 KB, plus the vector state area (1 KB in the one-core reference, which has no vector state), whose size depends on the processor" becomes "1 KB plus the save area of the baseline and of each optional feature of its mask, rounded up to a power of two ([Unlike cores](#unlike-cores)); `ObjectSizes` gives the size for mask 0".
- **Faults, words table, word 4:** add "for an undefined instruction, 1 + the bit of the feature whose disabled state trapped, or 0".
- **`sched_read` row:** results become "consumed, remaining, deadline, state, instructions", and the state word gains "bits 8-15: 1 + the last hardware class, 0 if none".
- **"What a move of a thread between kernels needs from this group":** add the feature rule (`busy`, before admission) and the optional new parameters.
- **"Parked nodes (D-108)":** add the parking rule on kinds.
- **Interrupts, the source word:** kind 3, *core event*, bits 8-15 the event number (1: feedback or performance capabilities changed), every other bit 0; claimable only on the node of that core; edge.
- **Registers, "The vector state is not in the block":** unchanged; add "its size depends on the thread's feature mask ([Unlike cores](#unlike-cores))".
- **Start-up state, the first thread:** its mask is 0 (baseline only).
- **Architectures:** add "The kinds, features and lengths of cores are described in the same terms on every architecture ([Unlike cores](#unlike-cores)); on RISC-V the kernel reads the hart ISA strings from firmware (ACPI RHCT or device tree), an exception to D-054 of the same nature as the MADT on x86-64."
- **Open points:** the Cores group must specify `core_status` with the current performance capabilities. The multi-core part must carry the feature rule and the new parameters in the move protocol.
- **scheduling.md**, Mechanism: "carries a budget, a period, a deadline and a core class" becomes "carries a budget, a period, a deadline, a slack class and the set of cores where it may be placed; which kind of core a context goes to is the placement service's choice, expressed by that set". Classes, "Core class in the contract (Aligned)": add "the promise is made by the placement service, through the cores set of the contexts it configures; the kernel holds no core class". "Hardware hints (Intel Thread Director, from memory)" becomes a reference to [Unlike cores](kernel-interface.md#unlike-cores), with the facts now verified.
- **kernel.md**, Hard points: "The real gain of one kernel per core for P and E cores... not measured" stays. Add: "a move between unlike cores is a move between nodes, so placement is by role and class, re-examined every few periods, not phase by phase (see the measurements in the draft on heterogeneous cores)". Hardware features, "Per-core-type kernel binary (Aligned)": add "low expected gain: kernel time is a small share; to keep only if measured".

### 3.4 Values `abi/` must gain

- **Calls, object kinds, errors.** None new. `sched_read` gains a fifth result.
- **`StartCore`**, `repr(C)`, 32 bytes, replacing the 24-byte record: `hw_id: u64`, `node: u32`, `slot: u32`, `kind: u16`, `flags: u16` (`START_CORE_BOOT = 1`), `threads: u8`, `perf_highest: u8`, `perf_efficient: u8`, `efficiency_class: u8`, `package: u32`, `reserved: u32`.
- **`StartKindRecord`**, 40 bytes: `features: u64`, `id: [u64; 3]`, `cores: u32`, `reserved: u32`.
- **`StartFeatures`**, 528 bytes: `baseline: u64`, `baseline_bytes: u32`, `reserved: u32`, then 64 × (`bytes: u32`, `length_bits: u32`), indexed by feature bit.
- **`StartFeedback`**, 16 bytes: `package: u32`, `slot: u32`, `bytes: u32`, `reserved: u32`.
- **`StartKind`** (the entry enum): `Kinds = 18`, `Features = 19`, `Feedback = 20`.
- **Feature bits.** `FEATURE_STATE_LAST = 31`, `FEATURE_INSTR_FIRST = 32`.
  - Module `x86_64`, state: `AVX = 0`, `AVX512 = 1` (opmask and ZMM), `AMX = 2` (tile configuration and data; large), `APX = 3`. Instruction, initial list: `AVX10_2 = 32`, `AVX_VNNI = 33`, `GFNI = 34`, `VAES = 35`, `SHA = 36`.
  - Module `aarch64`, state: `SVE = 0`, `SME = 1` (large), `SME2_ZT0 = 2`. Instruction: `SVE2 = 32`, `BF16 = 33`, `I8MM = 34`.
  - Module `riscv64`, state: `V = 0`. Instruction: `ZBA = 32`, `ZBB = 33`, `ZBS = 34`, `ZVBB = 35`.
  - The x86-64 baseline always includes x87 and SSE, which are not listed.
- **Scheduling.** `SCHED_STATE_HW_CLASS_SHIFT = 8`, `SCHED_STATE_HW_CLASS_MASK = 0xFF << 8`. `SCHED_BYTES` stays 128 if the reference layout has 8 free bytes for the instruction count; otherwise it becomes 256. That is to settle in the one-core model.
- **Interrupts.** `IrqSource::core_event(event)` with kind 3. `CORE_EVENT_FEEDBACK = 1`.
- **Faults.** No new kind. A doc comment on word 4 of kind 2.
- **Pure functions with a Kani proof:**
  - `thread_bytes(mask, &StartFeatures) -> Option<u64>`: a power of two, at least `THREAD_BYTES`, at least the exact sum, `None` on overflow;
  - `kind_covers(kind_features, mask) -> bool`, which is `mask & !kind_features & STATE_MASK == 0`;
  - `machine_length(lengths_of_cores) -> u32`: deterministic, the most common length, the longer on a tie.

### 3.5 What a reference model must check

- States: per thread, the mask and the enabled set on its current core. Per context, the hardware class and the instruction count. Per node, its kind.
- Invariants:
  1. The enabled set of a running thread is the baseline ∪ (mask ∩ kind).
  2. No thread is ever on a node whose kind lacks an optional feature of its mask, unless it was made there.
  3. A parked node's host kind covers the node's kind.
  4. The save area holds the enabled set at the same offsets on every node where the thread runs.
  5. The instruction count and the consumed time of a context change at the same events.
  6. A move with new parameters is admitted with the new bandwidth.

---

## 4. What to measure before deciding

| Question | How | What it decides |
|---|---|---|
| Which processor is the reference desktop, and is it hybrid? The documents say "Intel, no integrated GPU", without a model | Read CPUID; check for hybrid, HFI and Thread Director, SMT | Whether any of this matters on machine 1, or only on the Dell and the Mac |
| Speed-up of DodOS's own work on each kind | Instructions per nanosecond per context, P and E, for the compositor, Wasm JIT output, the compile service, inference, storage | If the ratio is near-constant across workloads, a scalar per kind is enough and the classes add little. If it spreads (1.2× to 3×), per-context measurement and the classes earn their place |
| Stability of the hardware class | Log the class per context at each context change, with the instruction rate | Whether classes predict the speed-up (Sáez found limits) and how often they change. This sets how often placement may react |
| Cost of a move between nodes | Thread + context + core-group join, against a Linux P to E migration | How sticky placement must be. Target: moves cost under 1 % of the time at the chosen rate |
| Cost at a context change | `MSR_IA32_HW_FEEDBACK_CHAR` read + HRESET; counter read; XFD and XCR0 writes; XSAVES of the baseline | Whether the class and the counter stay out of the IPC fast path and under 2 % of a context change |
| Frame deadlines by placement | Compositor, input and audio on P only, on E only, mixed, under background load, with throttling forced | How many P-cores the frame class needs, and whether E-cores can carry interactive work |
| Interference inside a module | A frame-class thread on one E-core of a Gracemont module, a background job on the other three | Whether a module is one placement unit (no frame work beside background work) |
| Energy of E-cores first | Parking on one E-core against spreading, on the Dell laptop at fixed work | The low-load policy and the value of parking |
| Do HFI capabilities change at run time on these machines? | Count core event 1 per minute, idle and under load | Whether the event is worth wiring into the policy |
| Group candidate on a cluster | The fixed-group candidate on one E-core module and on one Apple cluster, against nodes per core | Feeds the trial of D-108 |

## 5. What I would not do

- **No "core type abstraction" that hides unlike cores behind uniform virtual cores.** It loses exactly what policy needs. The abstraction the owner wants belongs at the placement service's interface (roles, classes, latency contracts), not in the kernel.
- **No capacity scalar, energy model or scaled budget in the kernel.** They are policy, they are wrong per workload, and Linux's corner cases show the cost (part 1.1).
- **No kernel-driven migration on hardware hints.** It cannot be cheap with one kernel per core, and the hints change every tens of milliseconds.
- **No transparent heterogeneous-ISA execution in the kernel**: no emulation, and no fault-and-migrate inside the kernel. User space can do it from fault kind 2.
- **No per-function code variants chosen by core identity at run time.** A thread preempted in a variant and moved breaks; compile to the cores set instead.
- **No support for two vector lengths in one thread's life.** One length per machine.
- **No frame-class work on an SMT sibling**, if SMT is ever enabled.
- **No cluster groups before the trial** has measured them.
- **No reading of PPTT, SRAT or `_PSD` in the kernel.** The platform service does it.

## 6. For the humans

| Point | Rule recommended | Alternative | What each costs |
|---|---|---|---|
| Vector lengths that differ between cores | One length per machine; cores that cannot use it lack the feature | Refuse to start such a core (Linux) | Rule: a core runs without its vector unit. Alternative: the core is lost |
| When a thread's save area is fixed | At creation, by a feature mask (the size argument) | A: allocation at first use (Linux). B: every thread gets every feature's area | Rule: the creator must know which large features a thread will use. A: kernel memory at fault time, against rule 3. B: up to hundreds of KB per thread with SME |
| Budgets across unlike cores | Nanoseconds, no scaling; a move carries new parameters chosen by the placement service | Budgets normalised to work by a per-core scale (Linux, Zircon) | Rule: the placement service must reconfigure on each move between kinds. Alternative: a guarantee only as good as the scale, and admission that drifts with temperature; contradicts the Decided "budgets are counted in time" |
| Per-context instruction counter | Yes, charged with the time | None; speed estimated from deadlines met | Rule: x86-64 takes fixed counter 0 from profilers' writes; a few cycles per context change. Alternative: no measured speed-up on ARM64 and RISC-V |
| Hardware class (Thread Director, AMD) | Read at each context change, recorded in the context | A: never. B: at every thread switch | Rule: classes mix client and server work inside a context, which is the work charged to it. A: loses the only hardware hint. B: about 30 to 45 cycles more on every `call` |
| What the kernel describes | Kinds, features, performance values readable only in ring 0, the HFI table | A richer table: caches, clusters, frequency domains, NUMA from firmware | Rule: the platform service must deliver topology before placement is good. Alternative: more firmware parsing in the kernel, against D-054 |
| HFI table memory | Kept memory per package, read-only frame at start | A frame given by user space and bound by a call | Rule: a few more pages outside any untyped. Alternative: a new call and a new kind of frame record |
| The core "class" | Removed from the kernel; the class of a capability is a placement promise expressed by cores sets | Keep a class per core in `StartCore` | Rule: an Aligned line of scheduling.md is reworded. Alternative: wrong on three-tier parts and on ARM64 and RISC-V |

---

## 7. Sources

Verified on 15 November 2026 (pages fetched, or search summaries where noted):

- Linux capacity-aware scheduling: https://docs.kernel.org/scheduler/sched-capacity.html
- Linux EAS: https://docs.kernel.org/scheduler/sched-energy.html
- Linux `SCHED_DEADLINE` documentation (no capacity text): https://docs.kernel.org/scheduler/sched-deadline.html. Capacity-aware admission, Eggemann 2020: https://lkml.iu.edu/2005.2/05109.html, https://lkml.iu.edu/hypermail/linux/kernel/2005.2/05111.html. Scale-invariant enforcement, Lelli 2017: https://lkml.iu.edu/hypermail/linux/kernel/1705.2/05886.html. Deadline server fix, 2025: https://lkml.rescloud.iu.edu/2506.3/04264.html, https://patchew.org/linux/175162039765.406.4702062609825995302.tip-bot2@tip-bot2
- Intel hybrid asymmetric capacity: https://lkml.iu.edu/hypermail/linux/kernel/2408.0/02392.html, https://lkml.iu.edu/hypermail/linux/kernel/2409.0/02975.html. EAS on Intel hybrid without SMT, 6.16: https://lkml.indiana.edu/hypermail/linux/kernel/2504.2/01419.html, https://git.radix-linux.su/kernel/linux.git/log/drivers/cpufreq/intel_pstate.c?showmsg=1 (search summary)
- Intel HFI: https://docs.kernel.org/arch/x86/intel-hfi.html (search summary). Thread Director classes, unmerged postings: https://lkml.iu.edu/hypermail/linux/kernel/2209.1/03079.html, https://lkml.iu.edu/2402.0/03269.html. HRESET and its cost: https://lkml.iu.edu/hypermail/linux/kernel/2302.0/06610.html, https://lkml.iu.edu/hypermail/linux/kernel/2402.0/03278.html
- AMD HFI: https://docs.kernel.org/arch/x86/amd-hfi.html
- arm64 asymmetric AArch32: https://docs.kernel.org/arch/arm64/asymmetric-32bit.html
- arm64 SVE syscall rules: https://docs.kernel.org/arch/arm64/sve.html. Vector-length map and late CPUs: https://lab.nexedi.cn/kirr/linux/-/commit/d06b76be8dad2e2fa62f68264887cc295d67a3ef (search summary)
- RISC-V vector: https://docs.kernel.org/arch/riscv/vector.html. vlenb mismatch: https://lists.infradead.org/pipermail/linux-riscv/2024-February/049777.html, https://lists.infradead.org/pipermail/linux-riscv/2024-May/054503.html (search summary)
- x86 dynamic XSAVE features: https://docs.kernel.org/arch/x86/xstate.html. XFD: https://lkml.iu.edu/hypermail/linux/kernel/2110.2/06592.html (search summary). XINUSE: https://www.felixcloutier.com/x86/xgetbv (search summary)
- Linux cluster scheduling patches: https://lkml.iu.edu/hypermail/linux/kernel/2011.3/06896.html. hw pressure: https://lkml.iu.edu/hypermail/linux/kernel/2404.3/00461.html
- scx_lavd: https://www.igalia.com/downloads/slides/ChangwooMin-TheCurrentStatusAndFutureDirectionOfTheLAVDScheduler.pdf (search summary)
- Windows QoS: https://learn.microsoft.com/en-us/windows/win32/procthread/quality-of-service. CPU sets: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_cpu_set_information. Minimized jobs on E-cores: https://www.xmg.gg/en/?p=35366, https://learn.microsoft.com/en-us/answers/questions/1027852/windows-11-22h2-thread-director-issues-with-intel, https://developer.blender.org/T99967 (search summaries)
- macOS: https://eclecticlight.co/2024/12/05/inside-m4-chips-cpu-core-management/, https://eclecticlight.co/2022/11/28/can-you-game-core-allocation-on-apple-silicon/ (search summary). XNU Edge scheduler: https://github.com/apple-oss-distributions/xnu/blob/main/doc/scheduler/sched_clutch_edge.md. M4 SME per cluster: https://raw.githubusercontent.com/tzakharko/m4-sme-exploration/main/reports/01-sme-overview.md (search summary)
- Fuchsia: https://fuchsia.dev/docs/contribute/governance/rfcs/0123_cpu_performance_info, https://fuchsia.dev/reference/syscalls/system_set_performance_info, https://fuchsia.googlesource.com/fuchsia/+/HEAD/docs/concepts/kernel/kernel_scheduling.md
- Li et al., HPCA 2010: https://dblp.org/rec/conf/hpca/LiBKKRH10 (abstract). Sáez and Prieto-Matias, APSys 2022: https://docta.ucm.es/entities/publication/39718b81-76c7-4f07-8532-338c120ab67c. PMCSched: https://docta.ucm.es/entities/publication/ace15010-3989-4909-8598-54e9701975db. Helios: https://www.microsoft.com/en-us/research/?p=157676. Popcorn: https://popcornlinux.org/publications/Systor2013_Popcorn_Final.pdf
- Alder Lake AVX-512: https://www.anandtech.com/show/16881/a-deep-dive-into-intels-alder-lake-microarchitectures/5, https://en.wikipedia.org/wiki/Alder_Lake (search summaries). AVX10 and Nova Lake: https://www.tomshardware.com/pc-components/cpus/avx-512-support-is-reportedly-returning-with-intels-next-gen-nova-lake-cpus-latest-linux-kernel-patches-reveal-p-cores-and-e-cores-will-gain-native-512-bit-execution, https://hothardware.com/news/intel-nova-lake-avx512-all-cores (press)
- Gracemont modules: https://en.wikipedia.org/wiki/Gracemont_(microarchitecture), https://www.anandtech.com/show/16881/a-deep-dive-into-intels-alder-lake-microarchitectures/4 (search summaries)
- Lunar Lake and Meteor Lake tiers, no Hyper-Threading: https://chipsandcheese.com/2024/06/03/intels-lion-cove-architecture-preview, https://pcgamer.com/hardware/processors/one-thread-per-core-we-can-deliver-better-than-hyper-threading-performance-without-hyper-threading-claims-intel-for-lunar-lake. Arrow Lake: https://digitaltrends.com/computing/intel-arrow-lake-hyper-threading (search summaries)
- Arm C1 cluster and SME2: https://www.androidauthority.com/arm-c1-cpu-mali-g1-gpu-deep-dive-3595933/, https://www.arm.com/technologies/dynamiq (search summaries)
- Kendryte K230: https://mediatum.ub.tum.de/doc/1759366/1759366.pdf, https://www.kendryte.com/k230/en/main/02_applications/tutorials/K230_RVV_optimization_performance_description.html (search summaries)
- CPUID leaf 0x1A: https://git.zx2c4.com/linux-rng/tree/arch/x86/include/asm/intel-family.h (search summary). LP-E cores on Meteor Lake: https://forums.intel.com/t5/Processors/Detecting-LP-E-Cores-on-Meteor-Lake-in-software/m-p/1585842 (could not be fetched, 403; search summary only)
- ACPI MADT GICC efficiency class: https://lists.infradead.org/pipermail/linux-arm-kernel/2022-March/726274.html

From memory (not verified): EAS merged in Linux 5.0 and used by Android; `SCHED_CLUSTER` merged in 5.16 with Jacobsville; macOS importance donation across XPC; glibc `ifunc`; the four fields of `MSR_HWP_CAPABILITIES` and their MSR number; HWP notifications and HFI both on the thermal LVT entry; the HFI table size in CPUID leaf 6; Thread Director's 4 classes on Alder Lake; that SVE requires every power-of-two length up to the maximum; the ARM64 activity monitor's instructions-retired counter; that XFD covers only AMX among current components; the cost of XSETBV; XSAVES layouts with a fixed requested set; Linux x86 preserving AVX-512 state across syscalls; the ARM64 exception classes for SVE and SME traps.
