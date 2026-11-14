# Prior art, borrowings and novelty claims

Statuses are defined in the [README](../README.md#status-legend). Verification marks matter in this file: much of it comes from memory or from delegated studies. The full list of marks is in [verification-status.md](verification-status.md).

## Borrowings

| Source | What is taken |
|---|---|
| seL4 | Memory supplied by user space, scheduling contexts, revocation by derivation tree |
| Fuchsia | Memory objects, declarative routing of capabilities, model of blobfs, TUF, A/B/R slots |
| Plan 9 | A single protocol for everything, network transparency, an agent that guards secrets |
| Genode | Recursive parent-child structure, exchange of resources, a tiny trusted compositor |
| Horizon | Signed manifest per process, fixed resource limits |
| Barrelfish | One kernel per core |
| SepOS | Key service with a narrow interface, data protection classes |
| Minix 3 | Automatic restart of drivers |
| Nix | A machine described by a declarative file, generations |
| Ubuntu Core | Signed assertions, channels, progressive rollout, recovery |
| bootc | A standard container registry as a means of distribution: its layers are already blobs addressed by hash |
| Debian | Its patches for porting outside Linux (Hurd), for the project's dependencies on mlibc |
| ART | Compilation at installation, then optimisation in the background |
| A2UI | Interface format emitted by the agent, catalogue mechanism |

The borrowings from Plan 9, Genode, Horizon, SepOS and Minix 3 are design inspirations that were not re-read (from memory).

**To add to the borrowings and to cite** (**Decided**, 14 November 2026): Singularity, Midori, Hive, Escort, Redline, SUD, LKL, FIDES. The [design review](../reviews/2026-11-14-design-review.md) gives, per claim, the works it found missing.

### Borrowings to study

From memory, to verify in the papers:

- HongMeng: differentiated isolation classes, services that can be grouped in one address space without changing their code, no state held twice.
- sDDF of LionsOS: lock-free single-producer single-consumer queues in shared memory, single-threaded drivers.
- seL4 MCS: time as a capability, for the latency classes.
- Barrelfish: cores treated as devices, kernel state externalised into capabilities.
- NrOS: replication library, verified page table.
- Asterinas: a minimal, audited `unsafe` base.

## Multi-core structure precedents

These precedents concern the variants described in [kernel.md](../architecture/kernel.md#alternatives-kept-as-comparison-points). Verified 14 November 2026 by web search (abstracts and official pages, papers not read in full).

- NrOS (OSDI 2021): state replicated through a shared log, one replica per NUMA node.
- Popcorn Linux (ICDCS 2015): coherence of an address space between kernels; one kernel per core or per group.
- Barrelfish/DC (OSDI 2014): replacement of a kernel core by core; adds, removes and replaces a core at run time. The figure previously quoted for the removal time is withdrawn until the paper is read (**Decided**, 14 November 2026).
- seL4: the proof of its multikernel is planned for the third quarter of 2028.
- Atmosphere (SOSP 2025): see [verification.md](../plan/verification.md#formal-proof).

## Kernel research axes

**Proposed.**

1. Provenance carried by IPC and enforced by the kernel, to bound what an agent can do with untrusted content.
2. A multikernel with replicated process state, verified.
3. A kernel written from a model by agents, with a differential oracle and bounded proofs.
4. The task as a kernel object: a single object gathers the delegated rights, the time budget, the provenance label and the log of an agent task, revocable in one operation.
5. No executable page outside the compile service, enforced by the kernel.

The recovery of one core's kernel is a candidate for a further axis to claim (see [kernel.md](../architecture/kernel.md#recovery-of-one-cores-kernel)).

Honest finding: today the mechanisms of the kernel are all borrowed (model of seL4, structure of Barrelfish). The novelty is in the method, in the combination and in these axes, none of which is designed yet.

Prior art to read before any claim: AgentKernel (arXiv 2609.29647), ActPlane (arXiv 2606.25189), HongMeng (OSDI 2024). The existence of AgentKernel and ActPlane was verified on 14 November 2026 by web search.

## Novelty claims and verdicts

From a study delegated to DeepSeek on 14 November 2026: sources read in full for the works of 2026, abstracts only for older ones; **not cross-checked** by the project.

The ground is already occupied: an AgenticOS workshop exists (March 2026, then SOSP 2026).

| Claim | Verdict |
|---|---|
| (a) The task as a kernel object, revoked in one operation | To claim; the combination appears new. Each brick exists (seL4 MCS, Resource Containers, HiStar and Asbestos, Cinder, Fuchsia jobs). The closest is Agate (AgenticOS '26), with no flow label and no effect log. Defence: a formal model of revocation |
| (b) Provenance in IPC messages, effect class, and human confirmation as the only way to lift a label | To claim; the combination appears new. The closest: ActPlane (eBPF under Linux) and CaMeL (outside the kernel) |
| (c) Dynamic core groups | To claim. The clustered multikernel of von Tessin (2012) is the same idea in static form; Barrelfish/DC is it without sharing. Only dynamic grouping is free, and it breaks the proof structure that a static partition brings |
| Method (kernel written by agents, seL4 oracle, Kani and Verus) | No precedent found, but hard to defend: the oracle sees only the surface of the ABI |
| Speculative tasks | Not to present as new: "Fork, Explore, Commit" (arXiv 2602.08199) and "Externalization Barriers" (AgenticOS '26), already published with code |
| No executable page outside the compile service | Not to present as new: iOS and Singularity |
| Capabilities with a budget | Not to present as new: seL4 MCS and Cinder |
| Explanation of authority | Not to present as new: a query on the derivation tree |
| Kernel per core type | Not to present as new: Barrelfish/DC and Popcorn |

The items not to present as new remain useful to the product. The weaknesses the study listed for the agent model are in [agent.md](../architecture/agent.md#known-weaknesses).

Softened claims (**Decided**, 14 November 2026): the statements "no kernel found" (display-anchored scheduling) and "does not seem to be published" (capabilities typed by WIT) are softened.

## Leads from recent research

From a second study delegated to DeepSeek on 14 November 2026: **not cross-checked**; figures to re-read in the papers.

Retained leads (**Aligned**: agreement of the user, to be designed) are recorded where they apply:

| Lead | Recorded in |
|---|---|
| (a) GPU submissions in the same deadline graph as the processor (the display-anchored clock part is superseded) | [scheduling.md](../architecture/scheduling.md#latency-contracts) |
| (b) Latency contracts carried by capabilities | [scheduling.md](../architecture/scheduling.md#latency-contracts) |
| (c) Capabilities typed by WIT | [kernel.md](../architecture/kernel.md#capabilities-and-revocation) |
| (d) Driver manifest deduced from traces | [drivers.md](../architecture/drivers.md#driver-manifest-deduced-from-traces) |
| (e) Memory in the manner of CortenMM (SOSP 2025) | [memory.md](../architecture/memory.md#address-space) |
| (f) Memory copy as a kernel service with a deadline (Copier, SOSP 2025) | [memory.md](../architecture/memory.md#address-space) |
| (g) User interrupts (xUI, ASPLOS 2025; Aeolia, SOSP 2025) | [kernel.md](../architecture/kernel.md#hardware-features) |
| (h) Flux as a proof tool (TickTock, SOSP 2025) | [verification.md](../plan/verification.md#formal-proof) |
| Hardware: FRED, APX, LAM, CET, core types | [kernel.md](../architecture/kernel.md#hardware-features) |
| Heterogeneous cores | [scheduling.md](../architecture/scheduling.md#classes) and [kernel.md](../architecture/kernel.md#hardware-features) |
| Rejected leads | [kernel.md](../architecture/kernel.md#hardware-features) |

From the same study:

- Direct competitor: Agate (AgenticOS '26), a capability microkernel for agents, AArch64, with no evaluation and no proof.
- WALI (EuroSys 2025): Wasm on top of system calls, to cite to say what DodOS removes.

## Other prior art recorded elsewhere

- Recovery of a kernel (Hive, Barrelfish/DC, Quest-V, Kmorph, Otherworld): [kernel.md](../architecture/kernel.md#recovery-of-one-cores-kernel).
- Linux drivers in user space (SUD, LKL, Genode, LinuxKPI, LionsOS): [drivers.md](../architecture/drivers.md).
- Agent security (lethal trifecta, rule of two, FIDES, RTBAS, IsolateGPT): [agent.md](../architecture/agent.md#security-model).
- Distributed capabilities (CapTP, Cap'n Proto) and Plan 9: [devices.md](../architecture/devices.md#principle).
- Ancestors of individual ideas: [ideas.md](ideas.md).
