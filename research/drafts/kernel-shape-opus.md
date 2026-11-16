# A shape for DodOS's kernels and cores (Opus)

Written 16 November 2026 by Claude Opus 5.5, for the brief `pass14/ELASTIC.md`. A research draft, not the contract. Another model did the same work separately; I have not read its file.

**What I read.** `architecture/kernel.md` (lines 24 to 181); the contract `architecture/kernel-interface.md` (the rules, the TLB, one kernel per core, unlike cores, interrupts, "Memory and devices between nodes", "The gate over page tables", "Cores", the data plane, the open points); decisions D-026, D-027, D-094, D-107, D-108, D-113 to D-117, D-120 and D-122 (`decisions/README.md`, lines 36 to 132); the trial on branch `trial-multicore` at `f9933bd`, read with `git show` (`trials/multicore/results-mac-m5.md`, cited below as "M5" with its line numbers, and `trials/multicore/README.md`); the two critiques `research/drafts/multicore-challenge-opus.md` and `research/drafts/multicore-challenge-hydrogen.md`, and their two verifications in `reviews/` (cited as "verify-opus" and "verify-hydrogen"); the model on branch `model` at `2afc901` (`model/src/remote.rs`, `system.rs`, `table.rs`, `moves.rs`, and the list of the rest); `scheduling.md`, `wasm-abi.md` and the research draft `heterogeneous-cores.md` where cited.

**What I fetched** (16 November 2026, with `curl`, PDFs turned to text with `pdftotext`; addresses in appendix B): von Tessin, *The Clustered Multikernel* (2012); Chapin et al., *Hive* (SOSP 1995); Zellweger et al., *Decoupling Cores, Kernels, and Operating Systems* (Barrelfish/DC, OSDI 2014); Arm's descriptions of `TLBI ASIDE1IS` and of `TTBR0_EL1`; the RISC-V SBI RFENCE extension.

**What I ran.** An exhaustive state explorer of the one new protocol the recommended shape adds: cores that move between kernels, the fence of a kernel of several cores, and a TLB shootdown racing a move (`/tmp/opus-elastic/model/elastic.py`, appendix A, Python 3, every run bounded by `timeout`). I changed nothing in `/Users/btw/Documents/repos` except this file, committed nothing, and used no subagent.

**Conventions.** A citation `:N` without a file is `architecture/kernel-interface.md` line *N*. Line numbers of `kernel-interface.md` and `kernel.md` are those of the committed files (Docs at `b15f37c`; `kernel-interface.md` last changed in `3bc7597`, `kernel.md` in `7f1f9d0`): someone else edited both files in the working tree at 11:38 on 16 November, after I had taken my citations, and those uncommitted edits move some lines by up to about ten. "Node" is the contract's word for one kernel's state; below, "kernel" means one running kernel instance with its node block, whatever the number of its cores. **[new]** marks an idea I found in no system I read; it is shown only as far as the explorer or the arithmetic shows it. A suspicion is marked as one.

---

## 0. The answer, briefly

**I recommend shape C, made precise. I call it C\*.** **[2nd round: C\* is no longer proposed as the shape to build first: kernels of one core come first, and kernels of several cores are stage 2, part 9.4]** A kernel covers a set of one or more cores; a core moves from one kernel to another only by being stopped and started again, so it carries nothing; the placement service creates, grows, shrinks and retires kernels; every kernel object of a process lives in one kernel; inside a kernel the cores share state under one lock first (with lock-free reads of capability slots); between kernels only **one-shot** operations cross, plus grants of memory and the failure machinery that exists today. No node is ever parked on another kernel's core.

Four choices make C\* more than the C of the brief:

1. **The one-shot boundary.** Between kernels, an operation crosses only if the target kernel completes it in one bounded step and keeps nothing for the requester afterwards, apart from the ring slot of an unread message and the grant entries of what it lent. Remote waits, proxies, moves of capabilities and moves of threads do not cross. This one rule removes every family of confirmed faults that came from state held for another kernel (part 1.1).
2. **A process lives in one kernel.** The process grows by its kernel taking cores, not by spreading over kernels. There is no core-group protocol between kernels at all.
3. **Cores are owned through words, like memory.** Each physical core gets an ownership word in the living part of the machine table, written only through the gates, with the same discipline as the chunk words of D-115. A core is taken only when it is confirmed parked, by the same evidence a fence uses.
4. **No co-hosting.** A kernel with little to do gives cores back and keeps one in deep idle, or seals with no core at all. The parking of D-108 goes; its purpose (cores that sleep) is met inside each kernel. **[2nd round: sealing with no core as an idle state is withdrawn; an idle kernel sleeps in place, R-7, part 9.2]**

**Why the others lose.**

- **A repaired** keeps rule 7 (`:17`), so it keeps the 18 message kinds of `model/src/remote.rs:37-138`, the proxies, `thread_move` and co-hosting, where the confirmed faults cluster. Its hardest case, one address space on many cores, is the protocol nobody has written (`:1877`); its planned form, a copy per node with frames under grants (`:320`), fills the 4,096-entry grant table at three nodes for a 4 GiB heap mapped in 4 KiB pages, that is 2,048 frames of at most 2 MiB (multicore-challenge-opus.md, P1, confirmed by verify-opus line 122). The trial measured a kernel shared by the process's cores ahead on exactly those operations: capability changes 2.3 to 9.6 times lower latency with a modelled 1 µs interrupt (M5:651), unmaps by every thread 1.55 to 2.0 times the throughput with range locks (M5:1060). **[2nd round: both figures come from finer locks than the one lock C\* starts with; with one lock, unmaps by every thread are 6 to 21 % slower than one node per core at `ipi` 0, M5:383-386]** The second verification advised repairing before cutting (verify-hydrogen lines 278-281); that advice was given while one kernel per core was fixed. Once a kernel may span cores, the hardest protocol A would repair, the core group across kernels, is not needed at all, and the repair buys less than the cut.
- **B** (one kernel per core, the reduced set between them) cannot give one address space to the 16 threads of case 1 without a coherence protocol rebuilt in user space, which hits the same grant ceiling; it gives idle cores nothing better than idling in place. B is C\* with every kernel of size one. It is a sound first stage of C\*, not an end.
- **C as briefed** leaves open what crosses, whether a core may host several kernels and how a core changes kernel. Left open, each choice brings back one of A's fault families.

**What C\* costs against A on the common path** (trial figures, with an interrupt that is modelled, not measured): a longer tail on capability lookups in a busy kernel (p99 1.7 × W and p99.9 2.1 × W at W = 1 µs with 10 % changes, against 1.04 × W: M5:650); many-to-one signals 6 to 8 % slower at k = 4 with a notify updated by one atomic OR (M5:1056); IPC between cores of one kernel 4 to 7 % slower with one lock at k = 4 (M5:377-380), 1.0 to 2.4 % with a lock per endpoint (M5:652, M5:1113). Beyond the trial: a kernel to verify under concurrency (the seL4 clustered multikernel needed new thread states and a 1,000-line invariant proof for one such problem, part 1.3); a larger unit of failure; no gain on a machine of two cores.

**What I showed.** **[2nd round: this first explorer is superseded by part 9.3; it did not model stops in flight, park epochs, roles, zero-core kernels or credits]** The explorer covers three kernels, four cores, one frame, at most two accusations, and every interleaving of core moves, shootdowns, fences and reclaims: 1,819,997 states, every safety property holds and every state can reach a quiet state; with kernels that also retire and start again, 54,971,344 states and 369,929,808 transitions, with the same result. Four versions with one rule removed each break a property within 1 to 6 steps. The first run found a stuck state in my own protocol (a core given away that no other kernel takes); the protocol below includes the fix.

**The experiment that would prove C\* wrong** (part 8): on the reference desktop, a kernel of 2 to 6 cores with one lock and lock-free slot reads, against the same number of one-core kernels, on the trial's workloads with real interrupts and with the call and mapping rates traced from Ladybird and an inference engine. If the lock costs more on lookups, IPC and signals than the shared kernel saves on changes and unmaps at those rates, C\* is wrong for this machine.

---

## 1. What the repository already establishes

### 1.1 Where the faults are

The two verifications agree on the structure, and differ on the shares:

- The faults between nodes are about half of the confirmed ones in rounds 6 and 7: 17 of 38 in round 6 and 13 of 24 in round 7 by the first critique's rule (verify-opus lines 36-37), 34 of 71 strictly between nodes by the second verification's recount (verify-hydrogen line 65). The claim "49 of 61" was found wrong (verify-hydrogen line 13); I do not use it.
- The families that recur (verify-hydrogen lines 68-73, multicore-challenge-opus.md part 2): names of grants reused while a message naming them is in flight; teardown of state held for another node (proxies, held requests, transfers, a destroyed thread's request); sealed, parked and co-hosted nodes; roles and units; `thread_move`; pinned grants and clearing; dead generations in table words.
- Of these, four come from state that one kernel holds for another (proxies and held requests, transfers in flight, moves, the request of a destroyed thread) or from one core hosting several node lifecycles. Three come from what recovery itself needs (roles, pinned grants, generations in words) and stay in every shape.
- For names in flight, the second verification proposes one check at every message receipt: sender, generation, grant index, serial, kind (verify-hydrogen line 266, applying the contract's own rule `:855`); the first critique's one type for the full name of a grant (its W5, confirmed by verify-opus line 59) points the same way.

### 1.2 What the trial measured, and what it did not

The trial (M5) simulated the kernel-side synchronisation of three candidates with real threads on an Apple M5; interrupts (0 or 1 µs) and TLB invalidation (100 ns) are modelled, not measured (M5:51-52). Candidate 1 is one node per core; candidate 3 is "the k cores of the multithreaded process share one node; every other core is a node alone" (README "The model"). Candidate 3 is, workload for workload, what C\* does when the placement service gives a process its own kernel.

| Workload (k = 4) | Favours | Margin | Source |
|---|---|---|---|
| Lookups, median | Level (seqlock slot read) | p50 = W in both | M5:650 |
| Lookups, tail at W = 1 µs, 10 % changes | 1 | p99 1.04 × W against 1.7 × W; p99.9 against 2.1 × W | M5:650 |
| Capability changes, latency, `ipi` 1 µs | 3 | 2.3 to 9.6 times lower p50 | M5:651 |
| a1 throughput, 10 % changes | 3 | 7 to 11 % (`ipi` 0); 27 to 32 % (`ipi` 1 µs) | M5:648-649 |
| a1 throughput, 1 % changes | Level | 2 to 4 % | M5:647 |
| IPC, one lock in the group | 1 | 4 to 7 %; 1.7 to 2.3 times at k = 8, W = 1 µs | M5:377-380 |
| IPC, a lock per endpoint | 1 | 1.0 to 2.4 % | M5:652, M5:1113 |
| Many-to-one signal, atomic notify | 1 | 6 to 8 %; level when the receiver is busy | M5:1056-1057 |
| Unmap, one initiator | 3 | 5 to 13 % lower p50 | M5:1059 |
| Unmap, every thread, one lock in the group | 1 at `ipi` 0, 3 at `ipi` 1 µs | 6 to 21 % (`ipi` 0); 1.07 to 1.49 times (`ipi` 1 µs) | M5:383-386 |
| Unmap, every thread, range locks | 3 | 28 to 45 % (`ipi` 0); 1.55 to 2.0 times (`ipi` 1 µs) | M5:1060 |
| Other processes beside the big one | Level for 1 and 3 | fixed groups hurt them in the first series; level for lookups once lookups are lock-free, writes not measured | M5:205-211, M5:387-392 |
| Moving a core between nodes | 3 affordable | about 0.2 µs of protocol plus modelled work; 3,000 moves/s about 1 % of a core | M5:224-235 |

What it did not measure: real interrupts and invalidations (M5:260-263); the gate; the revocation of a subtree under locks (M5:971-980); the memory of candidate 1's copies (M5:307-308); containment and recovery of any candidate (README, first paragraph); rows with k = 6 and 8 mix core types (M5:40-44); its core move is a lock hand-over, not the stop and start of a core that C\* uses.

### 1.3 Precedents, checked at their sources

- **The clustered multikernel** (von Tessin, 2012) is C without elasticity. "Instead of running one node per CPU, multiple CPUs can be clustered into (assigned to) a node. Within each node, we apply the big-lock design"; between nodes, "IPC only works within a node, communication across nodes has to be implemented via shared userlevel memory" (both §3). Clusters are configured at boot. Its cost inside a node: a thread may be suspended or deleted while it runs on another CPU of the same node; fixing it took "only 80 LOC of C code", but "two thread states and 8 preemption points had to be added", and "adding a newly required invariant required a 1000-LOC proof" (§4.4.1). Two correspondence proofs were left missing (§6.1.1).
- **Hive** (SOSP 1995) made a kernel of several processors the unit of failure. "When the system boots, each cell is assigned a range of nodes that it owns throughout execution. Each cell manages the processors, memory, and I/O devices on those nodes" (§3). Write access to a page "is granted to all processors of a cell as a group ... allows it to freely reschedule the process on any of its processors without sending RPCs to remote cells" (§4.2). Its cells are fixed for a boot.
- **Barrelfish/DC** (OSDI 2014) decoupled cores from kernel state (a kernel control block per kernel) and started, stopped and replaced kernels at run time, but "we do not consider fault tolerance and isolation for now" (§4). Measured (§5.1, Table 2): stopping a core 0.8 to 3.5 µs; bringing one up 0.5 to 1.2 ms in the booted core, plus 7 to 29 ms of preparation by the boot driver, which includes loading the kernel image from storage.
- I found no system that changes the set of cores of a fault-containment kernel at run time and recovers one such kernel while the others run. That is a statement about what I read, not a survey.

---

## 2. The shapes, defined on one page

Each shape is defined by four answers: how many cores a kernel covers, whether that changes at run time, what crosses between kernels, and where a multithreaded process lives.

| | A, repaired | B | C, as briefed | D1: fixed clusters | D2: shared tables across per-core kernels | **C\*** (recommended) |
|---|---|---|---|---|---|---|
| Cores per kernel | 1 (D-108, `kernel.md:42`) | 1 | a set, changing | a set fixed at boot | 1 | a set of 1 to *k*, changing, by policy |
| Several kernels on one core | yes, parked nodes (`kernel.md:43`, `:1090`) | no | open | no | no | **no** |
| What crosses | rule 7: any call on any object (`:17`, `:847-860`), transfers, revocation, `thread_move`, carried calls, roles, failure: 18 message kinds | signal, stamped send with frame grants, frame revocation, failure | "the reduced set" | IPC through user memory only | B plus loading another kernel's page-table root | **one-shot operations** (part 4.4), grants of memory, failure |
| A 16-thread process | one copy of its address space per node, frames under grants, changes acknowledged by every node (`:320`); protocol not written (`:1877`) | not in one address space, unless user space rebuilds coherence | one kernel | one cluster, if it fits | one table owned by the home node, loaded by the others | **one kernel, grown to 16 cores** |
| Unit of failure | one core's node; the process dies with its home (`kernel.md:48`) | one core's kernel | a kernel | a cluster | one core's kernel; loaders of a dead home's root stop | **a kernel**, sized by policy |
| Precedent | none found with recovery | seL4's static multikernel (reported in multicore-challenge-opus.md part 4, confirmed by verify-opus line 22; not re-checked by me) | Hive cells, but fixed | clustered multikernel, Hive | Barrelfish's single page table per process (NrOS §6.3, quoted in multicore-challenge-opus.md, confirmed by verify-opus line 18; not re-checked by me) | none found |

**A, repaired.** The present contract with every repair proposed today: one receive-check function for every message (`:855`, verify-hydrogen line 266); proxies charged per task, or remote waits cut (multicore-challenge-opus.md W3); rings written into the contract with FIFO order, capacity and a full-ring rule (W4); one type for the full name of a grant (W5); ordering of the shared words and a model at word granularity (W7); the three fixes of verify-hydrogen lines 120-127 (count sealed nodes in a unit rebuild, end waits begun on an accused node, `CPU_OFF` on an ARM64 self-park); and the core-group protocol, still to write.

**B.** One kernel per core. Between kernels: a remote signal, a stamped send into a bounded per-peer queue carrying grants of frames, revocation and release of frame grants, and the failure machinery (membership, fence, reclaim, roles). Everything else at user level, through per-kernel agents. No parking (multicore-challenge-opus.md W6). This is the critique's alternative A.

**C, as briefed.** Kernels of several cores that change at run time, locks inside, the reduced set between. It leaves four questions open: whether a core may run several kernels in turn; what exactly crosses; how a core leaves and joins; where a process lives when its kernel cannot grow.

**D1, fixed clusters.** The clustered multikernel: clusters set at boot. It loses both abilities the owner wants to keep (growth at run time, sleeping cores), and the trial measured a fixed group smaller than the process as the slowest on unmaps (M5:189-191, D-116 point 2), a cost the fourth series says the earlier tables overstated by up to 14 % in some cells (M5:1081-1092).

**D2, one table per process owned by its home, loaded by other per-core kernels.** The critique's W2. It removes the per-node copies, but its verification found three hazards it did not answer: accessed and dirty bits written by the walkers of other cores, ARM64 break-before-make faults on the loaders, and Armv8 ASIDs (verify-opus lines 151-157). Inside one kernel those are the ordinary hazards of any SMP kernel; across kernels they couple two failure units. C\* keeps the shared table and drops the coupling.

**D3, C with co-hosting.** C plus the parked nodes of D-108. Rejected: co-hosting is one of the recurring fault families (part 1.1), and C\* gets sleeping cores without it (case 4).

**D4, C with processes that move between kernels** **[new, not recommended]**. A process whose kernel objects all lie in chunks of its own could move to another kernel by handing over the ownership words of those chunks. Its capabilities to objects outside its chunks would have to become grants at the move, which is rule 7's transparency again. **Decided in this proposal: a process never changes kernel.** A process that must leave its kernel is restarted elsewhere by its supervisor. This is settled now, not deferred, so the contract needs no hook for it.

**C\*.** Defined in part 4. In one sentence: C, with the one-shot boundary, one kernel per process, cores owned through gated words and moved by stop and start, and no co-hosting.

---

## 3. The eight cases, shape by shape

C\* is specified in part 4; the cases use its terms early. **Core word**: the ownership word of a physical core, states *free*, *owned* (*K*, *g*), *leaving* (*K*, *g*), *joining* (*K*, *g*) with *K* a kernel and *g* its generation. **Confirmed parked** **[2nd round: amended: the confirmation must answer a new park request, R-1, part 9.2; a stale `parked` passes otherwise]**: the same evidence a fence uses (x86-64: the park stub's epoch in the core beacon, `:1084`; ARM64: PSCI `AFFINITY_INFO` returns OFF, `:1086`; RISC-V: the hart is stopped, `:1087`). **One-shot call**: a call on a remote capability that the owning kernel executes in one bounded step without waiting (part 4.4).

### 3.1 A WebAssembly process with 16 threads

The process is either a WebAssembly process with shared-everything threads, which WASI 0.3 does not have yet, or native code such as Ladybird or an inference engine, which "needs real threads from the start" (`wasm-abi.md:128`).

**A.** Process *P* has home node *h*. Its threads reach other nodes by `thread_move`, one `Move` and one `Moved` per thread, each into a thread made beforehand on the destination (`:672-677`). Each node of the core group holds a copy of the address space, an `aspace` of that node, mapping *P*'s frames under grants from the frames' node (`:320`). A map, unmap or protect is applied to the home copy, sent to every other node of the group, applied there with a local invalidation, acknowledged; the caller waits in *waiting for another node* for every acknowledgement (`:320`). At 16 nodes that is 15 requests and 15 acknowledgements per change, plus interrupts, batched. Growth from 1 to 16 adds 15 nodes to the group; how a node joins or leaves is not written (`:1877`). Grants: every frame of *P* needs a grant to each of the 15 other nodes; a 4 GiB heap in 4 KiB pages is 2,048 frames of at most 2 MiB (a frame holds at most *E* pages, `:236-237`), so 2,048 × 15 entries against `GRANTS` = 4,096 per node (`:833`); large frames avoid this at 2 MB granularity (multicore-challenge-opus.md P1).
*Deaths.* *h* dies: *P* is lost; its threads elsewhere raise *no address space* (R2, `:1103`). Another node *n* dies: *P* loses its threads there (`kernel.md:48`). Suspicion: a native program that loses a thread holding a lock does not continue in practice, so *P*'s exposure grows with the number of its nodes. *n* dies during a broadcast: R0 ends the caller's wait with `gone` (`:1098`), but which copies applied the change is not specified, because the protocol is not written.

**B.** The kernel offers no address space across kernels. Either *P* runs on one core and its parallelism goes through several processes sharing frames, or *P*'s runtime keeps one address space per kernel mapping the same frames (one grant per frame per kernel, the same ceiling as A) and a user-level agent per kernel applies each unmap and acknowledges. The kernel's TLB guarantee (`:318`) then holds per kernel only; memory safety still holds, because a frame cannot be given away until every grant of it is revoked (G6, `:890`), but the latency of an unmap is that of user-level messages and the progress of *P* depends on 16 agents.

**C\*.** *P* lives in kernel *K*. Every object of *P* (threads, contexts, capability space, address space and its tables, endpoints, notifies) is made from *K*'s memory.
- *Growing by one core.* The placement service asks the owner *J* of a free-able core *c* to give it (one-shot `core_give`), then asks *K* to take it (one-shot `core_take`):
  1. **[2nd round: `core_give` is not a one-shot call, R-16; a stop must never be sent to a core whose word is unmarked, R-2]** *J* moves the contexts admitted on *c* to its other cores, checking each core's admission (a local operation under *J*'s lock; refused with `budget` if they do not fit, as `core_place` is today, `:1194`); retargets the interrupt remapping entries that name *c* (at most 192, with an idempotent invalidation request to the unit role holder, as `core_place` does today); its gate writes *leaving* (*J*, *h*).
  2. *c* finishes the shootdowns addressed to it, invalidates its whole TLB, and parks (x86-64: the park stub; ARM64: `CPU_OFF`; RISC-V: `sbi_hart_stop`).
  3. *K*'s gate checks that *c* is confirmed parked, that *c*'s kind has *K*'s baseline features and vector length (D-118), and writes *joining* (*K*, *g*) by compare-and-swap; it starts *c* by the existing start path (x86-64: a start request in the park stub's page and an NMI; ARM64: `CPU_ON`; RISC-V: `sbi_hart_start`; `:1174`).
  4. *c* enters *K*'s entry, invalidates its whole TLB again, sets up its per-core state under *K*'s lock, and *K*'s gate (running on *c*) writes *owned* (*K*, *g*). *P*'s threads may now run on *c*, within their contexts' cores sets (D-040).
- *Growing from 1 to 16* is fifteen such moves. *Shrinking* is the same with *K* as the giver; *P*'s threads keep running on *K*'s remaining cores.
- *Map, unmap, protect.* *K*'s gate writes *P*'s single page table (G3 unchanged). An unmap invalidates locally, then sends a shootdown to the cores of *K* that may hold *P*'s tag, and waits for their acknowledgements in *K*'s memory **[2nd round: a leaving core acknowledges before it parks, R-15]**: on x86-64 by interrupt, as the trial models it (README "Interrupts"); on ARM64 by one broadcast instruction, since `TLBI ASIDE1IS` "applies to all PEs in the same Inner Shareable shareability domain"; on RISC-V by an interrupt or by SBI `sbi_remote_sfence_vma_asid` with a hart mask. No message crosses kernels; no grant is used; the TLB guarantee of `:318` holds for *K*.
- *Deaths at each step of a move.* *J* dies before *c* parks: *c* still runs *J*, its word names *J*, so *J*'s fence stops it; *K*'s take is refused until then (the core is not confirmed parked). *J* dies after *c* parked: *c* may be taken at once, or is freed by R6. *K* dies after step 3: *c*'s word names *K*, so *K*'s fence stops it, and clears a start request not yet acted on. *K* dies after step 4: *c* is one of *K*'s cores. The placement service dies: nothing was held for it; its successor reads the core words in slot 13. The explorer of part 6 checks these cases.
- *Deaths of P's kernel or others.* *K* dies: *P* is lost, as with A's home. Another kernel dies: *P* is untouched, unless it mapped frames granted by that kernel (R2 removes those mappings).

### 3.2 A client and a service on different kernels

**A.** Client thread *T* on node *X* calls endpoint *E* of node *Y* through a remote capability (grant *G* from *Y*). *X* checks the slot and sends `Request` with the arguments; *T* waits in *waiting for another node*; on *Y* a proxy, one of 16 per peer, stands in *E*'s queue (`:856`); the server receives without a lend and is marked as having lost its context (`:858`); its reply goes back as `Answer`. A capability handed over in the call travels by `TransferAsk` and `TransferGrant`: *X*'s gate writes the grant entry, *Y*'s writes the use entry and the slot, the sender waits (`:836`). Revocation is two-phase: the grant becomes *revoking*, *Y* removes in steps of at most 32 units and answers each, *X* frees the entry at the end (`:842`).
*Deaths.* *Y* dies mid-call: R0 ends *T*'s wait with `gone` (`:1098`). *X* dies: *Y* frees the proxies standing for *X*'s threads (R0). Known faults: sixteen idle remote waits freeze every request of the node to that peer (multicore-challenge-opus.md C1, confirmed by verify-opus line 44); stale names in flight (verify-hydrogen lines 21-22); teardown of a destroyed thread's request (line 71).

**B and C\*** (the same between kernels).
- *Connection.* The client makes, through its kernel's gate, a grant of its ring frame and a grant of its own notify with the `send` right only, to the service's kernel and generation, then sends a stamped message to the service kernel's mailbox (`:1002`) carrying the two grants. The send returns at once, or `busy` when the sender has no credit left for that peer (part 4.4). The service's kernel queues the message; when a service thread receives it, that kernel's gate writes the use entries and the slots. The service maps the ring frame under the grant (`:841`) and keeps the client's notify as a remote capability.
- *A call.* The client writes a request in the ring and sends a remote signal to the service's notify; the service writes the reply and signals the client's notify; the client waits on its own, local notify. Each signal is one message and, where the receiver sleeps, one interrupt. The trial found that a call between cores "costs a wake-up in every candidate" (M5:145-149); rings with a signal only when a ring goes from empty to non-empty are already the data plane's rule (`:1753`, `:1784`).
- *Revocation.* A frame grant with mappings: the two-phase protocol of `:842`, unchanged. A notify grant: no mapping, so the entry is freed at once and its serial grows (`:842`).
- *Deaths at each step.* The client's kernel *X* dies after making the grants and before delivery: at delivery the receive check finds *X*'s generation over and drops the message; no use entry is written. *X* dies after delivery: the service's kernel removes its remote capabilities of *X* and their mappings in R2, and acknowledges; *X*'s memory is not reused before (`:1114-1124`). The service's kernel *Y* dies before delivery: *X*'s grants to that generation are freed when it is over (R3). *Y* dies after mapping the ring: the ring frame stays pinned until *Y*'s generation is over (R3, `:1104`), then returns to the client. *Y* dies while the client waits for a reply: the client's wait is local and does not end by itself. **This is a real loss against A**: in A, R0 ends the wait with `gone`; in B and C\*, the client's runtime binds a watch on the service's kernel (`core_watch`, `:1190`), whose notify is signalled at every change of that kernel's member word, and treats it as the end of the wait. A library rule, not a kernel one.
- *What C\* adds to B.* Calls on remote capabilities that do not wait cross as one-shot calls (part 4.4), so a supervisor, a debugger or a pager acts on another kernel's objects without an agent there. Inside one kernel, client and service have today's synchronous call with lending (`:1749`), now across all of that kernel's cores.

### 3.3 A driver, its interrupts, its IOMMU, its clients on other kernels

**A.** The device belongs to the driver's node (D-113, `:784`): its blocks, its `iospace` and all its tables, its MSI vectors through that node's `irq_control`, its remapping entries in the node's own range of 192 handles (`:864`). An `irq` is "one vector of that node's core" (`:687`), so every interrupt of the device lands on one core (multicore-challenge-opus.md P4). Attach, detach and invalidation go to the holder of the unit's role as idempotent requests carrying the role's epoch (`:865`, `:1212`). Clients exchange data through rings in granted frames.
*Deaths.* The driver's node dies: unit role holders block its DMA at once (R1, `:1099`), the platform service resets the device after the barrier (`:1148`), a new driver starts. The role holder dies: the successor takes the unit after `SETTLE_NS` and rebuilds it from the live nodes' reports (`:1205`, `:1214`); the device's DMA and interrupts keep working (`:866`).

**B.** As A, without remote calls; clients already use rings and signals.

**C\*.** The device belongs to the driver's kernel *K_d*, which may hold several cores. An `irq` becomes one vector of one core of *K_d*, so a multi-queue NIC or NVMe controller spreads its vectors over *K_d*'s cores, each remapping entry written by *K_d*'s gate in *K_d*'s handle range. This removes P4 for any driver whose kernel has more than one core. When a core leaves *K_d*, *K_d* retargets the vectors on it first (step 1 of 3.1). Roles, R1, the rebuild and the restart of a driver are unchanged.
*Deaths.* As A, with one difference of scale: *K_d*'s death stops every device of every driver in *K_d*. Policy: drivers of unrelated devices in separate kernels. A death during a retarget: the role holder's invalidation request is idempotent (`:1212`), and *K_d*'s fence covers the core.

### 3.4 An idle machine

**A.** Parked nodes (D-108, `kernel.md:43`): the nodes of idle cores run in turn on one awake core, and the rest sleep. This needs the save seal, the *host* evidence, the transition from live to sealed by the driver of another node's fence, and the rules after a confirmed stop on a shared core (`:1036`, `:1067`, `:1089-1090`), the family of five confirmed fault lifecycles that verify-opus line 60 counts. Without parking (multicore-challenge-opus.md W6), each node idles in place: no heartbeat while idle (`idle_until`, `:1052`), woken by an interrupt.

**B.** Each kernel idles on its own core in its deepest idle state.

**C\*.**
- A kernel with little runnable work gives cores away until it holds one; its timers and claimed interrupts move to that core (local); the cores given away park and stay free. A free parked core runs nothing and is held by nobody.
-  **[2nd round: withdrawn: R-7 to R-12, part 9.2]** A kernel with no armed timer and no claimed interrupt may seal (`core_stop` mode seal, `:1183`): its block is saved, its last core leaves, and it holds no core at all; its memory and objects stay, frozen (`:1022`). It is resumed on any free core when its supervisor needs it.
- **Who holds what the sleeping cores held:** nothing, because a core holds nothing: its kernel's state is in the kernel's memory, which the kernel keeps.
- **Waking:** an interrupt or a timer wakes a kernel's last core, which runs everything of that kernel; when load rises, the placement service gives the kernel more cores (3.1).
- The minimum number of cores not parked is the number of kernels that hold an armed timer or a claimed interrupt. Policy keeps that small by putting background processes in few kernels.
- **What this costs against parking, in energy:** *n* idle kernels each keep one core in deep idle, where A's parking keeps one core awake for all. Not measured; it is the measure W6 of multicore-challenge-opus.md asks for (package power).

### 3.5 Performance and efficiency cores; two cores; 64 cores

**Performance and efficiency cores** (the reference desktop is "probably an Intel Core i5-14600KF (6 performance cores with two threads each and 8 efficiency cores)", D-116 point 4, to confirm).
- **A.** One node per core; a thread changes kind by `thread_move` between nodes, so placement is by role and class, "re-examined every few periods" (`kernel.md:72`).
- **C\*.** A kernel may hold cores of several kinds if they have the same features and vector lengths; its baseline is then the features common to its cores, and a core joins only if its kind has them (the parked-node rule of `:645`, applied to joining). Placement on P or E cores is the context's cores set inside one kernel (D-040): no `thread_move`. The research draft on heterogeneous cores reports that Intel disabled AVX-512 on Alder Lake's P cores "to ensure an even ISA" (`heterogeneous-cores.md:103`); whether the 14600KF's two kinds report the same features is to read with CPUID on the machine. Two warnings from that draft: a lock in a kernel spanning kinds "would serialise a P-core behind an E-core holding it" (`heterogeneous-cores.md:157`), and the E cores come in modules of 4 sharing one L2 (`heterogeneous-cores.md:105`). Measure the lock across kinds before letting a kernel span them; until then, a policy of one kind per kernel costs nothing in the contract.

**Two cores.** Recovery needs a survivor: the supervisor and the memory service run on at least two kernels (`kernel.md:49`), and the last live kernel cannot be stopped (`:1138`). So C\* on two cores runs two one-core kernels, and a process with two threads runs them on one core. A, with its core group written, could spread the process over both nodes, though it would die with either. **C\* is B on two cores, and loses this case to A.** The project's machines have more cores (the reference desktop, 14); the ARM64 board of D-120 point 4 is not chosen yet.

**64 cores.**
- **A.** An unmap of a 64-node process waits for 63 acknowledgements sent one by one (multicore-challenge-opus.md P6); the 4,096 grants of a node are shared by 63 peers; proxies are 16 per peer.
- **C\*.** The number of kernels is a policy, for example 8 to 16 kernels of 4 to 8 cores. A 64-thread process in one kernel of 64 cores sends shootdowns by interrupt to up to 63 cores on x86-64, acknowledged in shared memory, or one broadcast instruction on ARM64. Nothing in the repository supports one lock for 64 cores: the trial measured up to 8 cores, half of them efficiency cores, with low trust (M5:40-44). Above the measured size, finer locks (per endpoint, per address-space range) are needed (M5:665-669, M5:960-970), and the revocation of a subtree under such locks is not measured (M5:971-980). **Unknown, and the risk of part 8.**

### 3.6 A kernel dies

**A.** One node is one core. The fence stops that core (`:1077-1092`), every live node runs R0 to R5, one runs R6, and the barrier declares the node dead (`:1096-1126`).

**C\*.** Kernel *K* holds cores *c*₁ to *c*ₖ.
- **What is lost:** every object of *K*'s generation, every process that lives in *K*, the grants *K* made (they die with its generation, `:845`); *K*'s devices are blocked and reset.
- **Who notices:** the same evidence (`:1058-1067`), with the heartbeat per physical core as today (`:1052`). A core of *K* that hangs while the others run is noticed first by its siblings (a lock or a shootdown acknowledgement that does not come), which accuse *K* with evidence *self*; from outside, *stale* evidence on any core whose word names *K* accuses *K*.
- **What is fenced:** every core whose word names (*K*, *g*), whether *owned*, *leaving* or *joining*, and every start request aimed at *K*. *K* becomes *fenced* when every one of them is confirmed stopped. The rule that "a node's own gate stops it" (`:1046`) applies to each of *K*'s cores: once *K* is accused, none of them can change a shared word.
- **What each architecture must give, per core, in parallel:**
  - *x86-64:* NMI, INIT, two SIPIs and the park stub, as today (`:1080-1084`), sent through the gate to each core of *K*; G10 changes from "a core whose node the caller drives the fence of" to "a core whose word names a kernel whose fence the caller drives". The bootstrap core and a core in VMX root operation are of class 1 (`:1081`, `:1088`).
  - *ARM64:* SDEI event 0 to each core, whose handler calls `CPU_OFF`; confirmed by `AFFINITY_INFO` per core (`:1086`). Class 1.
  - *RISC-V:* `fence_hart` per hart, where firmware offers it; otherwise class 0 (`:1087`).
  - **A kernel's fence class is the lowest class among its cores** (design rule).  **[2nd round: now a gate rule, R-4, and the class is checked at the commit, R-5]** Policy: the bootstrap core stays in a kernel of one core, as the contract already keeps unit roles off it (`:1874`); unit roles go to kernels whose cores are all of the best class (`:1211`).
- **A gain on weak machines.** Where a core is of class 0 and no monitor is declared, the contract runs one node, on one core (`:1088`). Under C\*, that one kernel may hold every core: an ordinary multiprocessor kernel without recovery, instead of a machine reduced to one core.
- **How long:** detection is immediate for *self* and at least `STALE_NS` (100 ms, provisional, `:1231`) for a silent death; the fence is bounded by `FENCE_NS` (10 ms, `:1234`), now for all of *K*'s cores at once; R6 visits each chunk of the table once in steps of the recovery reserve (`:1110`, `:1130`), a time not measured.
- **What the survivors never wait for:** the stop of *K*'s cores before blocking DMA (R1 needs no stop, `:1099`); an answer from *K* (R0 ends the waits for one-shot calls to *K* with `gone`; requests to a role *K* holds are kept and sent again to its successor; revocation steps of grants *K* holds are pinned, `:1104`, with the fix that a removal reaching a grant whose holder is already accused returns `again` without a message, verify-hydrogen line 121); *K*'s cooperation to release a core it was giving (a taker waits only for *K*'s fence); any other kernel, since the barrier waits only for the kernels whose `maps_of` bit names *K* (`:1126`).
- **What is simpler than A:** R0 has no proxies to free, no move to unwind, no transfer half done, no group acknowledgement to end; the *host* evidence and the co-hosting transitions disappear.
- **What is harder than A:** several cores to stop instead of one; one core of class 1 lowers the whole kernel; an unfenced kernel (`:1091`) freezes more memory, since a kernel holds more.

### 3.7 A kernel replaced by a new version while the machine runs

**A.** `core_stop` mode seal, then `core_start` mode resume with kernel image 1, node by node (`:1175`), relying on the versioned node block and the versioned protocol between kernels (`kernel.md:32`, `kernel.md:181`).

**C\*.**
- **By seal and resume, kernel by kernel.** *K* hands its unit roles over (`:1213`), answers or refuses with `gone` the one-shot calls it serves, stops taking work; each of its cores reaches the end of its current event and parks; the last one saves and seals the block. Then `core_start` mode resume with image 1, on any free cores. *K*'s processes pause for the seal and the resume; the other kernels do not. Barrelfish/DC measured the cost of the comparable step on its machines (stop 0.8 to 3.5 µs, start 0.5 to 1.2 ms in the core, §5.1); DodOS's image is already in memory (D-122), but nothing is measured here.
- **By attrition** **[new]**. New kernels start from image 1 (`core_start` already takes the image as an argument, `:1158`); old kernels keep image 0 until their processes end, or until a quiet moment for their seal and resume. It needs kernels of two versions to talk, which the versioned protocol already requires; the one-shot set is a smaller surface to keep compatible than 18 kinds with held state.

### 3.8 The supervisor and the memory service survive any one kernel's death

**A.** They run on the nodes that hold the reserve roles, at least two (`kernel.md:49`, `:1216`); a reserve's memory follows its role, not a node (`:758`); they keep no state that only one replica has.

**C\*.** The same, with two placement rules: each replica in a different kernel, and no kernel ever hosts two replicas of the same service. Kernels never merge (part 4.5), so growth cannot break the second rule. The replicas' kernels should stay small (one core), so that a kernel bug triggered by an unrelated heavy process does not take a replica with it (a suspicion about how kernel bugs are triggered, not a measure). When a replica's kernel dies, the other replica serves; it starts a kernel on a free core (`core_start` mode fresh) and a new replica in it.

### 3.9 The cases at a glance, every shape

| Case | A, repaired | B | C, as briefed | D1, fixed clusters | D2, home table loaded by others | C\* |
|---|---|---|---|---|---|---|
| 1. 16 threads, 1 → 16 → 1 | a copy per node, 30 messages per change at 16 nodes, grant ceiling at 3 nodes, join and leave unwritten | no address space across kernels; user-level coherence with the same ceiling | one kernel; how cores move is open | fits only in a cluster fixed at boot; no growth | one table, no copies; walker, break-before-make and ASID hazards across kernels; `thread_move` still needed | one kernel grows and shrinks by stopping and starting cores; shootdown inside the kernel; no grant |
| 2. Client and service | transparent call through proxies (fault C1), 18 kinds | rings, signal, stamped send; a wait does not end by itself on the peer's death | open | as B between clusters | as A or B | as B, plus one-shot calls; synchronous calls with lending inside a kernel |
| 3. Driver | every vector on one core | the same | vectors spread if the kernel has cores | spread inside the cluster | one core | spread over the driver kernel's cores |
| 4. Idle machine | parking, with its fault family, or idling in place | idling in place | parking or not is open | idling in place | as B | shrink to one core, or seal with none |
| 5. P and E; 2; 64 cores | `thread_move` between kinds; uses both cores of 2; 63 acknowledgements per change at 64 | no process over several cores; 2 cores as A without the spread | depends on the open choices | fixed | as A for moves | kinds inside one kernel; on 2 cores the same as B; 64 unmeasured |
| 6. A kernel dies | one core fenced; R0's long list; co-hosted nodes sealed or accused | one core; short R0 | several cores fenced | several cores, fixed | loaders of a dead home's table lose their threads of that process | several cores fenced in parallel; short R0; class is the lowest of the cores |
| 7. Replacement | node by node | kernel by kernel | kernel by kernel | cluster by cluster | node by node | kernel by kernel, or by attrition |
| 8. Supervisor and memory service | reserve roles on two nodes | the same | the same | the same | the same | the same, with replicas in distinct kernels |

---

## 4. C\* in full

### 4.1 The principles it follows

- **The owner's principle.** Guarantees are paid at a failure or a rare event. C\* adds no cost on a memory access or a TLB miss: translation stays one stage, and the gate's guarantee G (`:872-879`) is unchanged, stated per kernel instead of per core. What C\* does add on the common path is a lock on the kernel entries of a kernel that has more than one core. That is the price of sharing state between cores, not of a guarantee, and it is stated as such in part 7. A kernel of one core skips it, as the trial's one-core node did (README "The model").
- **A kernel holds nothing for another kernel**, except the ring slot of a message not yet read, the grant entries of what it lent, the use entries of what it holds and the records of the roles it holds (part 4.4).
- **A core holds nothing.** Its state lives in its kernel's memory; it is stopped before it changes kernel and starts with an empty TLB.
- **Shared words, not shared structures, between kernels**, as D-115 already decided: every word of the living part has one writer at a time and changes by compare-and-swap through the writer's gate (`:752`).

### 4.2 Kernels, cores and their words

- **Kernel slots.** The machine table keeps *n* kernel slots, fixed at machine start, each with its floor (D-107, D-114) and its member word, as nodes have today. *n* is a number of the boot image; with *n* equal to the number of physical cores, floors cost what they cost now. A kernel is a slot that is starting, live, sealing or sealed; a slot that is dead can be started fresh with the next generation.
- **The core word** **[new]**: one word per physical core in the living part, with the layout of an ownership word (`:759-766`): bits 0-1 the state (0 *free*, 1 *owned*, 2 *leaving*, 3 *joining*), bits 2-15 the check, bits 16-31 the kernel slot (0xFFFF for none), bits 32-63 the kernel's generation. The core beacon keeps its heartbeat, `idle_until`, `vmx` and the park stub's epoch (`:1052`); its field `running` is no longer needed, since a core runs at most one kernel.

| From | To | Written by | What the gate checks |
|---|---|---|---|
| *free* | *joining* (*K*, *g*) | *K*'s gate (`core_take`, `core_start`) | *K* is starting or live with generation *g*; the core is confirmed parked and not marked unusable; its kind has *K*'s baseline features and vector lengths; the fence-class rule of the image |
| *leaving* (*J*, *h*) | *joining* (*K*, *g*) | *K*'s gate | as above (*K* may be *J* itself, taking its core back) |
| *leaving* (*J*, *h*) | *free* | any live kernel's gate | the core is confirmed parked |
| *joining* (*K*, *g*) | *owned* (*K*, *g*) | *K*'s gate, running on that core | *K* is starting or live with *g* |
| *owned* (*K*, *g*) | *leaving* (*K*, *g*) | *K*'s gate (`core_give`; a seal; a retirement) | *K* is live or sealing with *g*; unless *K* seals or retires, another core stays *owned* by *K* |
| any state naming (*K*, *g*) | *free* | the kernel that runs R6 for *K* | *K* is fenced and its barrier holds (R6, `:1110`) |

- The row *leaving* → *free* was added after the first run of the explorer, which found a core given away that no other kernel took staying *leaving* for ever (part 6).
- **Member words** keep their states and transitions (`:1006-1043`) except the one that exists for co-hosting, "starting, live → sealed" by "the driver of the fence of another node placed on the same core" (`:1036`); the evidence *host* (`:1067`) goes with it. *Fencing* → *fenced* now requires every core whose word names (*K*, *g*), and every start request aimed at *K*, to be confirmed stopped.
- **A sealed kernel holds no core.** It keeps its memory and its objects (`:1022`) and is resumed on free cores. **[2nd round: only during a replacement, bounded by `SEAL_NS`, with admission at resume, R-8, R-9]**
- **A kernel's fence class** is the lowest class among the cores its words name; a kernel may take a core of a lower class only if the image allows it **[2nd round: replaced by R-5: refused at the commit for a unit-role holder]**, and a unit role goes only to a kernel whose cores are all of the best class found (the successor rule of `:1211`, applied per kernel).

### 4.3 Inside a kernel

- **The lock.** Version 1 of a kernel of several cores: one lock per kernel, a queue lock (the trial's choice, for its bounded wait: M5:71-78), held for one kernel event, with two exceptions the trial measured and whose correctness argument is short: a capability lookup reads its slot under a sequence counter per range of slots (the third series' "slot read", which "does the work, not the fine locks" in a1: M5:659-664), and a signal is one atomic OR on the notify's word, the lock taken only to wake a waiter (M5:857-861, with a test that hammers the lost wake-up). A lock per endpoint (M5:665-669) and a lock per address-space range (M5:960-970) are the next steps, each added when a measure on the reference desktop asks for it. The price of waiting: with one lock, the trial measured IPC 4 to 7 % slower than one node per core at k = 4 and 1.7 to 2.3 times slower at k = 8 and W = 1 µs (M5:377-380), and unmaps by every thread 6 to 21 % slower when interrupts cost nothing (M5:383-386); and one lock saturates near 1 / (W + hand-over), about 0.91 M operations per second at W = 1 µs (M5:80-82). With one lock, every kernel event stays atomic, so the reference model's rule "every event of a node runs alone" (`model/src/system.rs:5-7`) stays true per kernel.
- **The gate** gains its lock and the flush epochs of G12 (`:896`), which the contract already wrote for this case: "if several cores per node are adopted, the gate gains its lock and flush epochs" (`:1888`).
- **Threads running on another core of the same kernel.** Suspending, configuring or destroying a thread that runs on another core of the kernel needs that core to leave the thread first: an interrupt to it, and a bounded wait inside the kernel. This is the problem the clustered multikernel met (part 1.3); it costs new thread states and a new invariant, and it must be in the reference model.
- **Scheduling.** Admission is "per kernel" today (`:605`), where a kernel is one core; in C\* it stays per core: each core of a kernel has its own sum of admitted bandwidth and its own queues; the kernel moves a context between its cores only when the target core admits it, a local operation under the lock that replaces `thread_move` between nodes. A lend crosses cores inside a kernel: a passive server runs on its client's core and context, as it does today on one core (`:677`).
- **TLB tags.** One table of tags per kernel (G7, `:891`), valid on all its cores. A core flushes its whole TLB when it leaves and when it joins, so no tag of one kernel survives on a core of another. On ARM64, `TTBRn_EL1.CnP` stays 0: with 0, translation entries "are permitted to differ from corresponding entries ... for other PEs", while with 1 cores that share an ASID must point to the same tables, otherwise "the results of translations are CONSTRAINED UNPREDICTABLE" (Arm, `TTBR0_EL1`). A broadcast `TLBI ASIDE1IS` from one kernel also removes entries of the same ASID on other kernels' cores; that costs them performance, never safety. An optional refinement **[new]**: blocks of ASIDs owned by kernels through words like chunk words, so that broadcasts never touch another kernel's entries.
- **Interrupts and timers.** An `irq` is a vector of one core of the kernel; a timer is armed on one core. Before a core leaves, its vectors are retargeted (at most 192 remapping entries, the bound `core_place` already has, `:1194`) and its timers moved; before it joins, nothing is needed.
- **Idle.** Per core, as today (`:593-597`), with the idle table given per kind of core.

### 4.4 What crosses between kernels: the complete list

**The one-shot rule.** A request from kernel *X* to kernel *Y* is allowed only if *Y* completes it in one bounded step and keeps no state for *X* once it has answered. The requester may wait for the answer (it holds its request, as today, `:852`); the target never waits for the requester, and never holds a thread, a wait or an object for it.

**Shared words** (each written by compare-and-swap through the writer's gate):

| # | Words | Writers | States | When a writer dies |
|---|---|---|---|---|
| W1 | Chunk ownership words (`:759-777`) | the owner; contested takes when free, unclaimed or dead | none, free, taken | unchanged (`:813`), plus a lost compare-and-swap in the middle of a take undoes the words already written and returns `busy` (multicore-challenge-opus.md C3, confirmed by verify-opus line 111) |
| W2 | Device table and identifier words (`:780-784`) | the owner | as W1 | unchanged; the rule of taking judges the generation (verify-hydrogen line 128) |
| W3 | **Core words** (part 4.2) | as in the table of 4.2 | free, owned, leaving, joining | R6 frees every word naming the dead generation, after its fence |
| W4 | Member words (`:1006-1043`) | as today, minus co-hosting | dead, starting, live, sealing, sealed, fencing, fenced, unfenced | unchanged |
| W5 | Role words (`:1201`) | as today | vacant, held, handing | unchanged |
| W6 | Grant and use tables (`:833`) | the granting kernel; the holding kernel | grant: free, live, revoking, pinned; use: free, used, **release pending** **[new]** | R6 clears them (`:1110`) |
| W7 | Node and core beacons (`:1052-1053`) | each kernel; each core; the park stub | heartbeat, `idle_until`, `vmx`, `parked`, `panic`, `save_seal`, `acked`, `maps_of`, observations, plus **a counter per peer of stamped messages consumed** **[new]** | read as evidence |

**Messages** (every message carries its sender's slot and generation; one function checks every message at receipt: the sender's member word is starting, live or sealing with that generation; a grant is named by granting kernel, generation, index and serial; the kind of the named object; the epoch of a role; a failed check changes nothing and is traced, as `:855` already says):

| # | Kind | Direction and purpose | States | Bound when the ring is full | When a party dies |
|---|---|---|---|---|---|
| M1 | `Signal` | OR bits into a notify of another kernel, through a grant of that notify with `send` | none: idempotent | merged into a fixed table of pending signals per peer at the sender; `busy` when that table is full | sender dies: bits already sent stay; receiver dies: the grant is invalid, the signal is `gone` |
| M2 | `Send` | a stamped message into the receiving kernel's mailbox (`:1002`), carrying at most 4 grants of frames or notifies, made by the sender's gate before the message leaves; derivation only, never a move | sent, queued, received or refused | credit per peer: at most *Q* unread messages per (sender, receiver), *Q* a number of the image, counted from the receiver's consumed counter (W7); a task may use at most a quarter of them; otherwise `busy` at once | sender dies: queued messages naming its generation are dropped at receipt by the check; receiver dies: the grants die with nobody holding them and are freed when its generation is over (R3) |
| M3 | `Call1`, `Answer1` | a one-shot call on a remote capability (list below) | asked, answered | `Call1` is credited like M2 **[2nd round: one pool for every class is withdrawn: two classes, R-13, R-14]**; an `Answer1` uses a slot reserved in the reverse ring, one per credit | target dies: R0 ends the wait with `gone`; caller dies: the answer fails the check and is dropped |
| M4 | `Revoke`, `RevokeStep` | revocation of a grant whose holder has mappings under it (`:842`) | live → revoking → freed; steps of at most 32 units, one answer each | `Revoke` credited; `RevokeStep` uses a reserved answer slot | holder dies: pinned until its generation is over (R3); a removal reaching a grant whose holder is already accused returns `again` without a message (the fix of verify-hydrogen line 121); granter dies: the holder removes in R2 |
| M5 | `Release` | the holder removed the root remote capability of a grant (`:844`) | one-way | kept as *release pending* in the holder's use entry and sent when the ring has room (W6) | as today |
| M6 | `UnitRequest`, `UnitAnswer` | attach, detach, invalidate, program a line, on a unit role's holder (`:865`) | epoch-checked, idempotent | `UnitRequest` credited; answer reserved | kept and sent again to the next holder (`:1098`) |
| M7 | `Handed` | step 4 of a planned hand-over of a unit role (`:1213`) | handing → held | one per hand-over in flight, bounded by the number of roles | as today |
| M8 | `ReportAsk`, `Report` | the rebuild of a unit after its holder's death (`:1214`), which the model now shortcuts through a shared table (verify-opus line 47) | asked, reported | credited; bounded by one report per iospace and 192 handles per kernel | the rebuild goes on with the live kernels' reports |
| M9 | `Ping` | the sweep's probe of an idle successor (`:1070`) | one-way | at most one pending per peer | unconsumed, it becomes *stuck* evidence |

**The one-shot calls** allowed on a remote capability (M3): `thread_suspend`, `thread_resume`, `thread_cancel`, `thread_read_regs`, `thread_write_regs`, `thread_configure`, `sched_configure`, `sched_set_cores`, `sched_bind`, `sched_unbind`, `sched_read`, `poll`, `cap_derive` and `untyped_retype` whose objects and destination all belong to the target kernel, removal steps (`cap_delete`, `cap_revoke`, each step bounded, `again` between steps), `aspace_map`, `aspace_unmap`, `aspace_protect` (the shootdown happens inside the target kernel, which completes the operation even if the caller dies), `memory_take`, `memory_give`, `memory_split`, `core_take`, `core_give`, `core_idle`, `core_perf`, `task_revoke` (its threads all live in the target kernel), and the calls that change no object state (`:859`). Every capability argument other than the target must belong to the target kernel, as `:851` already requires.

**Refused across kernels** (`invalid`, judged with the target capability): `call`, `send` on an endpoint, `recv`, `reply_recv`, `wait`, and any placement of a capability into a slot of another kernel except through M2. The replacement is the data plane's own pattern: rings in granted frames, M1 to wake, M2 to connect.

**What is gone, and what replaces it:**

| Gone | Replaced by |
|---|---|
| Remote waits held by proxies (`:856`), `Cancel`, `PROXIES_PER_PEER` | local waits on local notifies, woken by M1 |
| `TransferAsk`, `TransferGrant`, `Refused`, `Returned` (`:836-839`) | grants made before M2 by the sender's gate; the receiver writes its use entries at delivery, or sends M5 |
| `Move`, `Moved`: `thread_move` (`:672-677`) | a context moving between cores of one kernel, under its lock |
| `Carry`, `CarryDone` | `core_idle` and `core_perf` as one-shot calls (M3) |
| The core group's copies and acknowledgements (`:320`, `:1877`) | one kernel per process |
| Parked and co-hosted nodes (`:1090`, `:1036`, `:1067`, `:1089`) | a kernel shrinks to one core, or seals with none |
| `core_place` (`:1194`) | `core_give` and `core_take` |

**Rings.** One ring per ordered pair of kernel slots, FIFO, of a capacity fixed at machine start (a value of the machine), written into the contract with its rule for a full ring, which the table gives kind by kind: every kind is either credited at the sender, or owed against a reserved slot, or kept in state that already exists until there is room. No kernel ever waits on a full ring, and no ring needs memory beyond what is fixed at start.

### 4.5 Lifecycles

- **A core moves** by `core_give` on its owner and `core_take` on its new kernel (3.1, steps 1 to 4). Moves are rare events: the cost of starting a core is not measured on DodOS, and Barrelfish/DC measured 0.5 to 1.2 ms in the booted core alone (§5.1). The placement service decides with hysteresis, at the pace "re-examined every few periods" of `kernel.md:72`.
- **A kernel is created** by `core_start` mode fresh on a dead slot, naming a free parked core: the slot becomes starting (*g* + 1), the core *joining*, then the kernel builds its start-up state from its floor and the kept image (`:1174`).
- **It grows and shrinks** by core moves; it keeps at least one core while it is live.
-  **[2nd round: amended by R-9 and R-12]** **It seals** with `core_stop` mode seal: unit roles handed over, one-shot calls finished or refused, every core *leaving*, the block saved, the member word sealed; it is resumed by `core_start` mode resume on free cores, with image 0 or 1.
- **It retires** when it holds no process: its last core leaves, its memory is given back with `memory_give`, and the slot is dead (a clean death needs no fence: every core is confirmed parked).
- **It dies**: 3.6.
- **Never:** two kernels merge; a kernel splits; a process changes kernel (D4 in part 2). Each of these is decided now, so the contract needs no hook for them.

### 4.6 The invariants

1. **One kernel per core at a time.** A physical core executes at most one kernel, and executes kernel *K* only while its core word names *K*'s current generation (*owned*, *leaving* or *joining*).
2. **Stopped before released.** A core word stops naming a kernel only after the core is confirmed parked, or by R6 after the kernel is fenced.
3. **Clean cores.** A core starts executing a kernel only from the parked state and with an empty TLB.
4. **No state held for another kernel** other than an unread ring slot (bounded by credits and reservations), the grant entries of what it lent, the use entries of what it holds, and the records of the roles it holds.
5. **A process in one kernel.** Every kernel object of a process lives in memory of one kernel, and its threads run only on that kernel's cores.
6. **Memory** (`kernel.md:31`, unchanged): nothing a live kernel depends on is recorded only in another kernel, and no memory of a dead kernel is reused before all its cores are stopped and every live kernel that could reach it has acknowledged.
7. **Shootdown.** When an unmap returns, no core of the kernel can use the removed translation; a core that left the kernel counts as acknowledged only because it flushed when it left (invariant 3).
8. **Names.** Every message names its sender's generation, and every grant by kernel, generation, index and serial; one check at receipt validates all of them for every kind.
9. **Rings.** No kernel waits on a full ring; every message kind is credited, reserved, or kept in existing state.
10. **Fence class.** A kernel's fence class is the lowest of its cores'; unit roles go to kernels of the best class.

---

## 5. What the contract and the model keep, lose and gain

### 5.1 `architecture/kernel-interface.md`

| Section | Keep | Lose | Gain |
|---|---|---|---|
| Rules (`:9-18`) | 1 to 6, 8 | rule 7's promise that any call on another kernel's object gives "the same result, later" (`:17`); the proxies in rule 3's list of fixed memory (`:13`) | rule 7 restated: objects belong to one kernel; a call on another kernel's object crosses only if it is one-shot (4.4); the core words in rule 3's list |
| TLB, one core and several (`:316-320`) | the guarantee (`:318`), now per kernel | the copy per node of a group's address space (`:320`) | the shootdown inside a kernel, per architecture (4.3); the flush of a core at leave and join |
| One kernel per core (`:599-614`) | what is per core (queues, sums, timer, idle) | parked nodes (`:614`); "a lend exists only inside one kernel" stays, but a kernel now spans cores | per-core admission inside a kernel; contexts moving between a kernel's cores; lends across a kernel's cores |
| Unlike cores (`:616-681`) | kinds, features, vector lengths, masks, `sched_count` | `thread_move` (`:670-677`); "a node runs on its own core or is parked" (`:645`) | a kernel's baseline is the features common to its cores; a core joins only if its kind has them |
| Interrupts (`:683-740`) | everything else | "one vector of that node's core" (`:687`) | one vector of one core of the kernel; retargeting before a core leaves |
| Memory and devices between nodes (`:742-866`) | the machine table, chunk words, device table, `memory_control`, the write gate, grants and their revocation, devices and roles | moves of capabilities across kernels (`:838`); remote destinations of `cap_derive`, `cap_move` and `untyped_retype` (`:836`, the cut verify-hydrogen line 277 already accepts); proxies and remote waits (`:852-856`) | "Calls on an object of another kernel" rewritten as the one-shot list; grants made before a stamped send; *release pending* in the use entry; the complete ring rule |
| The gate over page tables (`:868-905`) | G, G1 to G11, G13, G14 | — | G12 becomes active (`:896`); G1 also covers core words; G7's tag table per kernel; G10's INIT, SIPI and NMI to "a core whose word names a kernel whose fence the caller drives" |
| Cores (`:991-1245`) | machine objects, membership, beacons, detection, the fence, reclaim, the barrier, the recovery reserve, roles | the transition by the driver of another node's fence on a shared core (`:1036`); evidence *host* (`:1067`); the rules after a stop on a shared core (`:1089-1090`); `core_place` (`:1194`); `PROXIES_PER_PEER` (`:1890`) | core words and their transitions; the fence of every core of a kernel; a kernel's fence class; `core_give`, `core_take`; `core_start` naming the first physical core; the credit *Q* and the table of pending signals among the numbers |
| Synchronous or asynchronous (`:1743-1755`) | the rows on notifications, faults, data plane, long operations | "IPC to another core: ... a message between kernels, and the caller thread waits" (`:1750`) | IPC between cores of one kernel is synchronous, with lending; between kernels, rings and a signal |
| Open points (`:1872-1894`) | the others | the core-group protocol (`:1877`); "a node on several cores" (`:1888`), now decided | the measures of part 7 |

### 5.2 `architecture/kernel.md` and the decisions

- **Multi-core structure** (`kernel.md:24-37`): "one kernel per core" becomes "kernels of one or more cores, sized at run time"; the core group (`:28`) becomes the cores of a kernel; "each core has its own copy of the page table" (`:29`) becomes one table per process; the three formal models (`:33`) are redefined (part 6).
- **Nodes, cores and load** (`kernel.md:38-63`): the open question of `:51-59` is answered by its third row, "groups that change size with the load", without parked nodes (`:43`).
- **Dynamic structure** (`kernel.md:86-90`) becomes the mechanism. **Conflict to settle:** "Cores on demand are deferred until after the alpha (**Decided**, 14 November 2026)" (`kernel.md:90`). Under C\*, the core words, `core_give`, `core_take` and the fence of a kernel of several cores are in the contract and the model from the start (the rule of D-107 that a kernel feature is not deferred by default); what the alpha may defer is the placement policy that moves cores, so the alpha could run kernels of fixed sizes chosen at start.
- **Recovery of one core's kernel** (`kernel.md:99-131`) becomes recovery of one kernel; **core-by-core replacement** (`kernel.md:179-181`) becomes kernel by kernel, or by attrition.
- **Decisions that change** (each a decision of the owners): D-026 ("one kernel per core, no shared state, messages only") becomes "kernels of one or more cores; between kernels, no shared state other than gated single-writer words, and messages only for one-shot operations; locks inside a kernel". D-028's "one kernel per physical core in version 1". D-108's binding of a node to one core and its parking; its "process ... survives the loss of the other nodes of its group" disappears, since a process is in one kernel. D-116 point 2 is decided for groups sized to the process. D-122's `thread_move` goes.
- **Decisions kept:** D-027 (two-phase revocation, now for grants with mappings; three models, redefined), D-094 (the multikernel by messages from the start), D-107 and D-114 (floors, now per kernel slot), D-113, D-115, D-117 (the fence, applied to every core of a kernel), D-120.

### 5.3 The model (`dodos-kernel`, branch `model`, at `2afc901`)

- **`model/src/remote.rs`** (1,424 lines). Functions that go whole: `proxy_index`, `serve_request`, `proxy_at`, `answer_proxy`, `cancel_proxy`, `cancel_remote`, `defer_transfer`, `transfer_wait`, `transfer_reply`, `refused`, `returned`: 211 lines, counted from the function boundaries. **[2nd round: wrong: 174 lines from `fn` to `}`, 197 with doc comments; my count included blank lines]** Functions that shrink, not counted: the parts of `request`, `forward`, `receive_packet`, `misdirected`, `answered_request` and `place_transfer` that serve waits, moves and returns. Kept: `send_packet`, `receive_packet` (to become the one check), `valid`, `mailbox`, `stamp_of`, `capability_arguments` (the one-shot list), `make_grant`, `place_remote`, `remote_destroyed`, `released`, `anchor`, `grant_of`, `free_grant`, `revoke_anchor`, `revoke_step`, `revoked_step`, `build_kernel_space`. I do not repeat the earlier estimate of 900 lines, which its verification put at 500 to 600 (verify-opus line 129).
- **`model/src/moves.rs`** (269 lines): removed.
- **`model/src/system.rs`**: keeps `CoreState` per physical core and the messages in flight; gains core words and kernels with sets of cores. With one lock per kernel, "every event of a node runs alone" (`system.rs:5-7`) stays true per kernel; what is new to interleave is the lock-free slot read and the shootdown acknowledgements between a kernel's cores.
- **`model/src/table.rs`**: gains the core words; loses `placed`, the one physical core of each node (`table.rs:186-191`).
- **`model/src/recovery.rs`**: R0 shrinks; the fence covers every core of a kernel; the co-hosting paths go.
- **`model/src/roles.rs`**: the take-over reports become messages (M8).
- **`model/src/lib.rs`**: the core group's waiting state, never entered (`lib.rs:19-20`), goes.
- **Tests**: those of moves, proxies, transfers with moves and co-hosting in `model/tests/nodes.rs`, `adversarial_nodes.rs`, `recovery.rs` and `cores.rs` go; new tests for core moves, the fence of a kernel of several cores, shootdowns racing moves, the one-shot list, credits and the full-ring rule; and the probe that sees a thread stuck on another kernel (verify-hydrogen lines 263 and 280).

---

## 6. How C\* would be modelled, and what I checked

 **[2nd round: the explorer of 6.2 and appendix A is superseded by part 9.3]**

### 6.1 The models to build

D-027 asks for three models checked by state exploration (`kernel.md:33`, `:1893`). Under C\* they become:

1. **Grants, stamped sends and revocation between kernels.** Three kernels with generations and fresh starts; one FIFO ring per ordered pair, with credits and reserved answer slots; grant and use tables whose entries are reused with growing serials; one-shot calls on remote capabilities; a death at every step. Properties: (a) a granted frame never returns to an untyped while a holder may translate to it (G6, `:890`); (b) no message acts on a grant of another serial or generation, or comes from a sender whose generation is over (`:855`); (c) every wait ends, by an answer or by `gone` once the target is accused (R0); (d) no ring overflows and no kernel waits on a full ring (invariant 9); (e) the only state a kernel keeps for a peer is in rings, credits, grant and use entries and role records (invariant 4), checked on every reachable state.
2. **Core moves and the life of kernels** (D-027's "change of size of a group" becomes this). A first cut is below. Still to add: generations carried in core words, unit roles held by a kernel whose cores move, the retargeting of interrupts, refusals for admission, memory taken and given while cores move.
3. **Recovery at word granularity**: membership, the fence of every core of a kernel, R0 to R6, the barrier, roles; each word read or write a step, under x86-TSO and the Armv8 model, with two failures. This is where the torn read of the barrier and the run taken in halves live (multicore-challenge-opus.md C3, confirmed as contract gaps by verify-opus lines 110-113).

Beside them, the reference model of one kernel: with one lock, its events stay atomic, as `system.rs:5-7` already assumes. The three places where a kernel's cores interleave without the lock (the slot read, the shootdown acknowledgements, a thread running on another core of the kernel) are each a small model of their own.

Tools: TLA+ with TLC; or exploration in Rust over the reference model's own functions, by turning `System::deliver` and each core's step into choice points; `loom` or `shuttle` for the gate's functions at word granularity, as the first critique also suggests (its W7).

### 6.2 What I ran

`/tmp/opus-elastic/model/elastic.py` (appendix A) explores every interleaving, breadth first, of this configuration: kernels A, B, C; four physical cores (A holds 0 and 1, B holds 2, C holds 3); a frame F of A mapped in A's address space; at most two accusations, never of the last live kernel. Events: a live kernel gives one of its cores (keeping one); the core parks; any live kernel takes a free core or a parked leaving one, and starts it; the core joins; a parked leaving core settles free; a core running A loads a translation of F; A unmaps F with a shootdown to its cores; A gives F away and a live kernel takes it; a kernel is accused, fenced core by core, confirmed, cleared by R6 and declared dead. With `--lifecycle`, a kernel that holds nothing retires (its last core leaves) and a dead or retired kernel is started again on a free core.

Properties: **P1** a core that is executing is never started; **P2** a core executes kernel *K* only while its word names *K*; **P3** no core executes a dead kernel (nor a retired one, outside its last leave); **P4** once F is not A's, no core executing A holds A's translation of F; **P5** a core executing *K* holds no translation installed by another kernel. **Liveness**: from every reachable state, a quiet state (no fence in progress, no core leaving or joining, no start pending, no shootdown in flight) is reachable.

| Run | States | Transitions | Result |
|---|---|---|---|
| `correct` | 1,819,997 | 9,015,693 | every property holds; no state is stuck (about a minute) |
| `correct --lifecycle` | 54,971,344 | 369,929,808 | every property holds; no state is stuck (47 minutes) |
| `old_no_settle`: my first version, where only another kernel could take a parked leaving core | — | — | **stuck** after 3 steps: B and C accused, A gives core 0; nobody can take it and its word stays *leaving* for ever. Fixed by the row *leaving* → *free* of part 4.2 |
| `fence_owned`: the fence stops only the cores whose word reads *owned* | — | — | **P2** after 5 steps: A gives core 0, A is accused, the fence stops core 1 only, A is declared dead and R6 frees core 0's word while core 0 still runs A |
| `free_early`: a giver writes *free* before the core parks, and a taker reads only the word | — | — | **P2** after 1 step; with P2 not checked, **P1** after 3: A takes core 0 back and starts it while it still runs A |
| `no_flush`: no TLB flush when a core leaves or joins | — | — | **P5** after 5 steps: core 0 loads F for A, moves to B, and runs B with A's translation |
| `acks_owned`: a shootdown waits only for cores whose word reads *owned* | — | — | **P4** after 6 steps: core 0 loads F, A gives core 0 (now *leaving*, still running A), A unmaps F, core 1 acknowledges, A gives F away while core 0 still holds its translation |

**What this shows.** In this configuration, the core-move protocol, the fence of every core a kernel's words name, the clearing of core words by R6, and the rule that a core which left counts as acknowledged only because it flushed, hold together under every interleaving with up to two deaths; and each of the four rules tested is necessary, since removing it breaks a property within six steps. The stuck state of my first version is the kind of fault scenario tests do not find and an explorer finds at once (the point verify-hydrogen makes at line 267).

**What it does not show.** Memory ordering (each word access is atomic and seen at once by all); generations carried in words (a restart happens only after R6 has cleared every word naming the kernel, which the explorer enforces instead of checking); messages and rings (core moves need none; the one-shot calls that ask for them are not modelled); unit roles, devices, interrupts, grants, admission; more than four cores or three kernels; time.

---

## 7. What C\* costs on the common path, against A

Only the repository's figures are used. They come from a simulation on an Apple M5 in which interrupts and invalidations are modelled, not measured; "candidate 1" stands for A's one node per core and "candidate 3" for a C\* kernel holding one process (part 1.2). Candidate 1 also simplifies A: its changes go through a home node and copies, but no grant, no proxy and no gate is simulated.

| Path | C\* against A | Source | What the figure does not cover |
|---|---|---|---|
| Capability lookup, every call | same median; longer tail under concurrent changes in the same kernel: p99 1.7 × W and p99.9 2.1 × W against 1.04 × W at W = 1 µs, 10 % changes | M5:650 | the real length of a slot read (M5:418-420) |
| IPC between two cores | inside one kernel, C\* slower by 4 to 7 % with one lock at k = 4 (1.7 to 2.3 times at k = 8, W = 1 µs), by 1.0 to 2.4 % with a lock per endpoint | M5:377-380, M5:652, M5:1113 | the cost of an uncontended lock hand-over on x86-64, "now the whole IPC gap" (M5:694-695) |
| IPC between kernels | ring plus two signals in C\*, against `Request` and `Answer` in A; both need a wake-up each way | M5:145-149 | not measured for rings |
| Many-to-one signals | with the atomic notify, C\* slower by 6 to 8 % when the receiver often waits, level when it is busy; without it, 7 % to 2.2 times slower | M5:905-917, M5:1056-1057, M5:379-380 | the interrupt A sends a busy receiver once per batch (M5:915-917) |
| Capability changes | C\* 2.3 to 11 times lower latency with one lock, 2.3 to 9.6 times with finer locks (`ipi` 1 µs) | M5:402, M5:651 | the revocation of a subtree under fine locks (M5:691-693) |
| a1 throughput | level at 1 % changes; at 10 %, C\* ahead 3 to 8 % (`ipi` 0) or 17 to 33 % (`ipi` 1 µs) with one lock and the slot read, 7 to 11 % or 27 to 32 % with finer locks | M5:398-400, M5:647-649 | the real change rate of programs (M5:688-690) |
| Unmap | C\* 5 to 13 % lower p50 with one initiator, whatever the lock (M5:957-959); when every thread unmaps, with one lock C\* is 6 to 21 % slower at `ipi` 0 and 1.07 to 1.49 times faster at `ipi` 1 µs, with range locks 28 to 45 % faster at `ipi` 0 and 1.55 to 2.0 times at `ipi` 1 µs | M5:383-386, M5:1059-1060 | an unmap that frees a table page or spans ranges (M5:971-980) |
| Other processes | level | M5:205-211, M5:387-392 | their writes (M5:390-392) |
| A core move | the trial measured about 0.2 µs of protocol for a lock hand-over; C\* stops and starts the core | M5:224-235 | the stop and start of a real core: no figure in the repository (outside it, Barrelfish/DC measured 0.8 to 3.5 µs to stop and 0.5 to 1.2 ms to start in the core, on other machines, §5.1) |
| Memory | one page table per process; no grant per frame | — | A's copies per node are not measured (M5:307-308) |
| Gate | the same gate calls per mapping change; plus the gate's lock in a kernel of several cores (G12); on ARM64, shootdowns inside a kernel need no interrupt, so no gate call for them (`kernel.md:163` makes every interrupt to another core a gate call) | `kernel.md:177` | no gate cost is measured on any machine of the project (`kernel.md:135`) |

**Reading.** On the paths every call takes (lookups, IPC, signals), C\* costs a few per cent in the median at k = 4, more in the tail, and much more at k = 8 if it keeps one lock; on the paths a multithreaded process takes when it changes its capabilities, it gains several times, more as interrupts cost more; on unmaps by every thread it gains only with range locks once interrupts are cheap. Which matters more depends on rates the repository does not have: how often real programs change mappings and capabilities, and what an interrupt costs (M5:250-256).

**What must be measured on the reference desktop** (an Intel Core i5-14600KF, to confirm, D-116 point 4):

1. An interrupt between two cores through the gate, round trip: P to P, P to E, E to E inside one module of four E cores and across modules.
2. A TLB shootdown inside a kernel to 1, 3, 5 and 13 other cores, by interrupt, with its acknowledgements in shared memory; against the same unmap done by messages between one-core kernels.
3. The queue lock: uncontended and contended hand-over, P to P, P to E, E to E (the risk of `heterogeneous-cores.md:157`).
4. The lock-free slot read on the call path, in the one-core kernel's real code.
5. A core move: from `core_give` to the core confirmed parked, and from `core_take` to the first instruction of the kernel on that core (park stub and NMI), with the full TLB flush.
6. The fence of a kernel of 4 cores: from accusation to every core confirmed stopped (NMI, INIT, SIPI, park stub), on cores other than the bootstrap core; and whether clearing the bootstrap flag removes the exception (the open point `:1874`).
7. Package power with *n* − 1 cores parked in the stub, against the same cores idle in their deepest state inside their kernels (the measure W6 of multicore-challenge-opus.md asks for).
8. The gate measures already listed in `kernel.md:177`.
9. The rates of `mmap`, `munmap`, `mprotect`, of waits between threads and of calls between processes in Ladybird and an inference engine on 4 to 8 cores (experiment 1 of multicore-challenge-opus.md): they set the weights of the table above.

---

## 8. The risks of C\*, and the experiment that would prove it wrong

### 8.1 Risks

1. **A kernel to verify under concurrency.** One lock keeps each kernel event atomic, but the slot read without lock, the shootdown acknowledgements and threads that run on another core of the same kernel are concurrency. The clustered multikernel's one such problem cost two thread states, eight preemption points and a 1,000-line invariant proof (part 1.3). The project's kernel is written from its model; the model must then interleave a kernel's cores where the lock does not cover them.
2. **A larger unit of failure.** A kernel's death kills every process in it. A policy that puts a fragile heavy process in the same kernel as the user interface makes the machine less available than A, whose unit is one core. The kernel cannot enforce a good policy.
3. **Slow moves.** If starting a core on the reference desktop costs milliseconds, as on Barrelfish/DC's machines (§5.1), cores move at the pace of placement decisions, not of bursts. A program whose parallelism changes faster than that runs on the cores its kernel kept, idle or not.
4. **Large kernels.** One lock is measured up to 8 cores, half of them efficiency cores, with low trust (M5:40-44). The owner's example, a process growing to 16 cores, is beyond what the trial measured; 64 cores is far beyond.
5. **Fence class of a whole kernel.** One core of class 1 (the bootstrap core, a core in VMX root operation) lowers the whole kernel; an unfenced kernel freezes all its memory until a restart (`:1091`), which is more memory than one node holds in A.
6. **Two cores.** No gain over B (3.5).
7. **The one-shot boundary may prove too narrow.** A service that must wait on another kernel's object (a pager that blocks a fault until data arrives, for example) must be rebuilt around rings and signals, or keep an instance in each kernel it serves. The verification of the first critique warned that per-kernel agents become a trusted base whose crash leaves a kernel live but unmanaged (verify-opus lines 142-144). C\* needs fewer of them than B, because kernels are fewer than cores, but needs some.
8. **Kernels spanning kinds.** A lock held by an efficiency core delays a performance core (`heterogeneous-cores.md:157`); a policy of one kind per kernel avoids it at the cost of splitting a process that wants both kinds.
9. **Admission when a core leaves.** Giving a core away must move its admitted contexts to the kernel's other cores; when they do not fit, `core_give` is refused with `budget`, and the placement service must choose between a kernel's guarantees and another kernel's growth.

### 8.2 The experiment that would prove it wrong

**Performance.** On the reference desktop, extend the one-core kernel to a kernel of 2 to 6 cores with one queue lock and the lock-free slot read, and run, natively and with real interrupts, the trial's suites a1, a2, a3, b and c against the same number of one-core kernels; then weight each suite by the rates traced in item 9 of part 7. **C\* is wrong for this machine if** the weighted cost of the lock on lookups, IPC and signals exceeds the weighted gain on capability changes and unmaps. A second criterion, independent of the weights: if a shootdown by interrupt inside a kernel of 6 cores is not faster than the same unmap done by messages between one-core kernels, the main argument of case 3.1 fails.

**Containment.** In the same kernel, kill one core of a kernel of 4 cores at random points of kernel code (including loops with interrupts masked), fence the kernel, and check with guard pages that no write of the dying kernel lands in memory reused afterwards; measure the time to *fenced*. **C\* is wrong if** a sibling core escapes the fence where a one-core kernel would not, or if the time to fence grows with the number of cores beyond `FENCE_NS`.

**Protocol.** Extend the explorer of part 6 to generations, rings with credits, grants and unit roles. **C\* is wrong if** it finds a violation that no change of the protocol in part 4 can remove without bringing back state held for another kernel.

---

## 9. Second round

Written 16 November 2026, after `reviews/2026-11-16-verify-kernel-shape-opus-by-hydrogen.md` (cited as "vx:N") judged this draft and `reviews/2026-11-16-verify-kernel-shape-hydrogen-by-opus.md` (cited as "vy:N") judged the other proposal. I was asked not to defend C\*: where the verifier is right, I repair or withdraw; where it is wrong, I show it by a run. The first round's text above is kept; what it withdraws or amends is marked there with **[2nd round: …]**.

**Baselines.** `p14:N` is `architecture/kernel-interface.md` line *N* at Docs `ede3b38` (pass 14). The first round's `:N` stays at `b15f37c`. The model is cited at `2afc901` as before.

**What I ran.**
- The verifier's seven tests (`/tmp/verify-opus-shape/verify_elastic.py`, `timeout 120`): all seven fail as the verifier reports (Tests 1, 2, 3a, 3b, 4, 5, 6).
- A new explorer, `research/drafts/kernel-shape-explorer.py` (part 9.3), with a corrected protocol and one broken variant per repaired rule.
- The line count of `remote.rs` at `2afc901`, read with `git show`.

Both verifications end on the same order of construction: kernels of one core, with the reduced set between kernels, first; kernels of several cores second (vx:141-157, vy:197-199). I agree, and part 9.4 turns it into a list for the contract.

### 9.1 Verdicts

| # | Break claimed by the verifier | Reproduced | Verdict | Repair |
|---|---|---|---|---|
| 1a | A stale `parked` lets `core_take` pass before the core has stopped (vx:19, Test 1) | Test 1 fails in 8 steps; explorer `moves:stale_parked` breaks P2 in 9 steps | **Right.** I defined "confirmed parked" as "the same evidence a fence uses" (part 3), but `parked` is "the fence epoch written by the park stub" (p14:1060), and a voluntary give has no fence epoch | R-1, R-4 |
| 1b | A stop (INIT, SDEI) sent while the word names the giver lands after another kernel took the core (vx:20, Test 4) | Test 4 fails in 6 steps; `moves:no_mark` breaks P7 in 7 steps | **Right.** | R-2, R-3 |
| 1b′ | The verifier's repair: refuse a take while the giver is not live (vx:153) | `moves:giver_live_only` breaks P7 in 7 steps | **Not enough.** The taker reads the giver's member word, the giver is accused, its fence sends a stop, then the taker's compare-and-swap on the core word succeeds: two words, no atomicity | R-2 instead |
| 2a | A unit-role holder takes a core of a weaker fence class (vx:21, Test 2) | Test 2 fails in 1 step; `moves:take_any_class` breaks P6 in 4 steps | **Right.** My rule was policy. My first repair, checking the role when the take reads the word, also failed: `moves:role_at_read` breaks P6 in 10 steps, because the role moves to the taker between its read and its compare-and-swap | R-5 |
| 2b | G12 needs concurrent proofs of the gate (vx:121) | — (a proof cost, not a run) | **Right.** "On one core, sequential reasoning suffices"; G12 "adds a lock and flush epochs. VerusSync-style reasoning is unfinished even in Asterinas" (`gate-page-tables.md:601-602`). The first round did not weigh it | Staging (9.4) |
| 2c | One lock breaks the bounds of D-042 (vx:23) | — | **Partly right.** D-042 asks for "a bounded, verified duration" (`decisions/README.md:52`). One lock adds a wait bounded by (*k* − 1) × the longest hold, so the bound holds but grows with *k* and with the slowest kind of core (`heterogeneous-cores.md:157`). The "either hold the lock across the shootdown or lose atomicity" dilemma is false: the wait for acknowledgements is a state of the waiting thread, and the unmap is two kernel events | R-6 |
| 3 | Kernels sealed with zero cores: reclaim barrier, revocation, IOMMU entries, wake path, budget, retirement (vx:22, Tests 3a, 3b) | Tests 3a, 3b fail; explorer `seal:no_seal_timeout` (stuck in 3 steps), `seal:resume_any` (budget, 3), `seal:rebuild_live_only` (IOMMU, 4), `seal:retire_then_give` (3) | **Right on every point.** Zero-core sealing as an idle state is **withdrawn** | R-7 to R-12 |
| 4 | One shared credit lets user messages starve kernel messages; counters and pending signals not reset at a peer's death (vx:24, Test 6) | Test 6 fails in 5 steps; `credits:shared_credit` stuck in 11 steps; `credits:no_gen_reset` stuck in 6; `credits:no_purge` delivers a stale signal in 5 | **Right.** | R-13, R-14 |
| 5 | "211 lines" of `remote.rs` (vx:15) | Recounted at `2afc901`: 174 lines from `fn` to `}`, 197 with doc comments | **Right.** My script counted blank lines up to the next function. Corrected: **174 (197 with doc comments)** | — |
| — | Test 5: an unmap waits for a core that parked without acknowledging (vx:25) | Test 5 fails on its own model; in mine, `shootdown:park_no_ack` (the test's assumption) is stuck in 10 steps, but `shootdown:acks_wait_only` holds | **A gap in my prose, not in the protocol.** Step 2 of a leave (part 3.1) has the core finish its shootdowns before it parks. Test 5 assumes it does not. The extra rule "a parked core counts as acknowledged" is redundant while step 2 holds | R-15 (prose) |
| — | `core_give` is called one-shot, but step 1 waits for the unit holder's answer (vx:75) | — | **Right.** | R-16 |
| — | On ARM64, a joining core is ON before it unmasks SDEI, so the whole kernel is unfenced (vx:71) | `--witness "lost on core" moves:correct` reaches a stop lost on a masked joining core in 9 steps, and `moves:correct` holds | **Wrong as a safety claim.** The fence repeats its stops until each core is confirmed, and the entry stub unmasks before it reads its word (R-3). The window costs time, not containment | R-3 |
| — | ARM64 cores of a resident Trusted OS refuse `CPU_OFF` (vx:71) | — | **Right, and already settled by pass 14:** `MIGRATE_INFO_TYPE` finds that core at start and makes it class 0 (p14:1094) | R-4: such a core never moves |
| — | The trial figures headlined in part 0 are fine-lock and range-lock results, while C\* starts with one lock (vx:14) | — | **Right for part 0.** Parts 1.2 and 7 carry the one-lock rows (C\* slower on unmaps by every thread at `ipi` 0, M5:383-386); part 0 is now marked | — |
| — | "Overstates Wasm 0.3 multithreading" (vx:26, vx:113) | — | **Wrong.** Part 3.1 says WASI 0.3 does not have threads yet and names native code, citing `wasm-abi.md:128`, which says native Ladybird and inference "need real threads from the start" | — |

### 9.2 The repaired rules, as sentences for the contract

Each rule names the explorer variant that removes it and fails.

- **R-1, park request** (`moves:stale_parked`). "Each park of a physical core, by a fence or by `core_give`, first writes a new value of that core's park request through the requester's gate. The core counts as parked only when the confirmation answers that request: on x86-64, `parked`, written by the park stub only, equals the current request; on ARM64, `AFFINITY_INFO` returns OFF after the request; on RISC-V, the hart's state is STOPPED after the request."
- **R-2, fence mark** (`moves:no_mark`, `moves:giver_live_only`, `moves:r6_inflight`). "Before it sends any stop (NMI, INIT, SIPI, SDEI event 0, `fence_hart`) to a core, the driver marks that core's word by compare-and-swap. A marked word is never taken, settled or rewritten except by R6. R6 frees it only once the core is confirmed stopped and `SETTLE_NS` after the last stop sent to it." This replaces G10's "a core whose node the caller drives the fence of" (p14:902) by "a core whose word names that kernel and carries the mark".
- **R-3, entry stub.** "A core started into a kernel runs the kept image's entry stub. The stub unmasks its stop signal (ARM64: `SDEI_PE_UNMASK`) before it reads its core word, and powers its core off if the word no longer reads *joining* by a live kernel. A stop lost while the core was masked is sent again: the fence repeats its steps until each core it covers is confirmed." No variant, since the run shows retries are enough; `--witness "lost on core"` shows the case is reached.
- **R-4, cores that never move** (`moves:bsp_moves`). "The bootstrap core and a core of fence class 0 are never given or taken: the gate refuses *leaving* and *joining* on their words after machine start-up." On RISC-V, the project's `fence_hart` extension must leave a stopped hart in the HSM state STOPPED, so that `sbi_hart_start` can reuse it. That is a requirement on firmware the project writes (p14:1095), not checked anywhere.
- **R-5, class at the commit** (`moves:take_any_class`, `moves:role_at_read`). "The gate call that writes *joining* re-reads the role table and refuses a core whose fence class is below the lowest class of the taker's cores, when a unit role names the taker as holder or target. A new holder, after it writes held and before it maps the unit, gives away any core of a weaker class." The second sentence closes a write skew between the role word and the core word that the explorer cannot see, since its steps are atomic.
- **R-6, bounds with a lock.** "In a kernel of *k* cores, a call's verified bound is its one-core bound plus (*k* − 1) times the longest hold of the kernel lock on the slowest kind of core in that kernel. No kernel lock is held across a wait for another core (a shootdown acknowledgement, a thread leaving a core): that wait is a state of the waiting thread."
- **R-7, idle kernels** (withdraws the first round's zero-core idle state). "An idle kernel keeps its last core and sleeps in place in the deepest state its idle table allows. Sealing is only the first half of a replacement." vy:150 found that sleeping in place serves C as well as one kernel per core.
- **R-8, SEAL_NS** (`seal:no_seal_timeout`). "A kernel sealed for longer than `SEAL_NS` may be accused by any live kernel with evidence *seal*; the gate checks the seal's instant in the node beacon. So the barrier, the revocations and the requests that wait for a sealed kernel end at most `SEAL_NS` + `FENCE_NS` later." It uses evidence code 6, which pass 14 gives to *host* (p14:1019) and which co-hosting no longer needs.
- **R-9, resume** (`seal:resume_any`). "`core_start` mode resume takes at least as many cores as the sealed kernel's admitted contexts need (`budget` otherwise). Before any thread runs, the kernel serves its pending revocations and runs R2 for every kernel whose generation ended while it was sealed."
- **R-10, rebuild** (`seal:rebuild_live_only`). "A unit's rebuild keeps the context entries whose root table lies in memory the ownership table gives to a starting, live, sealing or sealed kernel, and clears the others." p14:1222 now says "clears those that no live node claims". The earlier fix, counting the reports of sealed nodes (verify-hydrogen line 120), cannot work when the sealed kernel has no core to answer.
- **R-11, vectors of a sealed kernel** (not modelled). "A sealing kernel masks every vector it claimed, through its own remapping entries and gate, and unmasks them at resume."
- **R-12, retirement** (`seal:retire_then_give`). "A retiring kernel gives back every block with `memory_give` while it still holds a core, then its last core leaves; its floor stays with its slot."
- **R-13, two credit classes** (`credits:shared_credit`). "The ring of each ordered pair of kernels has two classes of credits. The kernel class covers revocation, unit requests, reports, hand-over, pings and every answer; it is sized at machine start and never used by a user thread. The user class covers stamped sends and one-shot calls made by user threads, with a cap per task. A kernel message never waits for a user message."
- **R-14, generations of the counters** (`credits:no_gen_reset`, `credits:no_purge`). "The counts of messages sent and consumed name both kernels' generations. A sender resets its counts for a peer when it runs R0 for that peer, and R0 drops every pending signal that names the peer's ended generation."
- **R-15, shootdown** (prose; `shootdown:park_no_ack` fails, `shootdown:acks_wait_only` holds). "A leaving core finishes the shootdowns addressed to it before it parks. An unmap may also count as acknowledged a core whose word no longer names the kernel, or whose word reads *leaving* with its current park request confirmed."
- **R-16, `core_give`.** "`core_give` records the request and returns; it is not one of the one-shot calls. The owner completes the leave in steps: retarget the vectors, wait for the unit holder's answer as kernel work rather than as a thread's wait, write *leaving*, park. Its end is seen in the core word."

### 9.3 The explorer, second version

**File:** `research/drafts/kernel-shape-explorer.py`. Python 3, no dependency. Run `python3 -I kernel-shape-explorer.py` for every scenario and variant (about 80 s wall clock on the machine it was written on: 70 s of CPU), or name scenarios (`moves`, `shootdown`, `seal`, `credits`, `full`) or `scenario:variant`. `--witness TEXT scenario:variant` prints the shortest trace to a transition whose label contains the text. The program exits non-zero if a corrected protocol fails or a broken variant holds. Every run reported here was bounded by `timeout`.

**What each scenario covers**, with what the verifier said the first explorer left out (vx:101-107):

| Scenario | Configuration | Added since the first round |
|---|---|---|
| `moves` | Kernels A, B, C; four cores (A holds 0 and 1, B 2, C 3); core 1 of fence class 1 (signalled), the others class 2; core 3 is the bootstrap core; B holds a unit role; at most two accusations | The park request and its confirmation per class; a stop **in flight** across a move, lost on a masked joining core and sent again; fence marks; takes in two steps (read, then compare-and-swap); the unit-role holder and its take-over by class; the bootstrap core |
| `shootdown` | The same, plus a frame F of A mapped in A's address space, at most one accusation | P4 and P5 with the park request, moves and one fence |
| `full` | `moves` and `shootdown` together, two accusations | (run only when named) |
| `seal` | Kernels A, B, C, four cores; B has contexts admitted on two cores; A grants a frame to B; B owns a device whose IOMMU entry sits on C's unit; A holds a block; the supervisor may disappear; core moves are atomic here | A kernel with **zero cores** and its wake, resume, the reclaim barrier, a revocation, the IOMMU rebuild, admission at resume, retirement, fresh starts |
| `credits` | Kernel X to kernel Y; four user tasks whose messages Y never reads; X's kernel requests; Y dies twice and starts fresh; one pending signal | **Credits** of kernel and user messages, counters across generations, pending signals |

**The `moves` scenario without the frame is a sound reduction**, not a sample. The frame's transitions (loads, unmap, acknowledgements, give, take) write only the frame's fields. No guard of a move, a fence, a take-over or R6 reads those fields. So removing them changes no reachable value of the other fields, and P1-P3, P6-P8 and the liveness of moves and fences are decided exactly. The reduction is what makes the default run finish: the combined model is 7.2 million states and six minutes.

**Results** (16 November 2026):

| Run | States | Transitions | Time | Result |
|---|---|---|---|---|
| `moves:correct` | 601,259 | 2,250,433 | 26 s | every property holds; no state is stuck |
| `shootdown:correct` | 331,860 | 1,363,487 | 17 s | holds |
| `full:correct` | 7,182,906 | 34,774,226 | 342 s | holds (the same result as `moves` and `shootdown` separately, with two accusations and the frame together) |
| `seal:correct` | 66,352 | 335,807 | 0.9 s | holds |
| `credits:correct` | 1,050 | 5,005 | < 0.1 s | holds |
| 9 broken `moves` variants, 4 broken `shootdown` variants, 4 `seal`, 3 `credits` | — | — | each under 1 s, except `park_no_ack` (15 s) | each breaks its property in 1 to 13 steps (table 9.1) |
| `shootdown:acks_wait_only` | 331,682 | 1,267,200 | 20 s | holds, as expected: the "counts as acknowledged" path is redundant while a leaving core acknowledges before it parks |

**Properties.**
- **P1:** a core that is executing is never started.
- **P2:** a core executes kernel *K* only while its word names *K*.
- **P3:** no core executes a dead kernel.
- **P4:** once F is not A's, no core running A holds A's translation of F.
- **P5:** a core running *K* holds no translation another kernel installed.
- **P6:** a unit-role holder never takes a core of a weaker class.
- **P7:** a stop never lands on a core that runs or starts another kernel.
- **P8:** the bootstrap core never moves.
- **Seal:** no live kernel holds fewer cores than its admitted contexts need; an attached device of a live or sealed kernel keeps its IOMMU entry; a retired kernel holds no block.
- **Credits:** the ring never overflows; no signal of an ended generation is delivered.
- **Liveness, everywhere:** from every reachable state a quiet state is reachable.

**Found by this explorer while I built it** (both now in the rules):
- the class check made when a take reads the word (`role_at_read`), refuted by a take-over that comes between the read and the compare-and-swap;
- a modelling error of mine, a take committed by a kernel whose cores were already stopped. The fix ties every take to a core that runs the taker, as on hardware.

**What it does not cover.**
- Memory ordering: each word access is atomic and seen at once.
- Generations in the core word of `moves`: no kernel restarts there; fresh starts are covered only in `seal`, where core moves are atomic.
- The write skew between the role word and the core word (R-5, second sentence).
- Real time: `SETTLE_NS` is modelled as "no stop in flight", and `SEAL_NS` as one step.
- Interrupt retargeting and the unit holder's answer in `core_give` (R-16).
- The vectors of a sealed kernel (R-11).
- Grants beyond one frame; one-shot calls and their answers; more than three kernels or four cores.
- An unfenced kernel.
- The lock inside a kernel, the slot read, cross-core thread suspension (the clustered multikernel's thread-deletion problem, part 1.3).

### 9.4 Staging: what stage 1 must already contain

**Stage 1:** kernels of one core, the reduced one-shot set between kernels, no co-hosting, idle cores sleeping in place. **Stage 2:** a kernel takes and gives cores; a process lives in one kernel on several cores. The owner's rule is that what stage 2 needs in the contract, in `abi/` and in the layout of objects is settled before the one-core kernel is written. This is that list.

**A. The words that own a core, and its states**

1. **The core word**, one per physical core, in the living part (beside the list of p14:758). Bits 0-1: the state, 0 *free*, 1 *owned*, 2 *leaving*, 3 *joining*. Bit 2: the fence mark. Bits 3-15: the check (13 bits, the hash of p14:759's family). Bits 16-31: the kernel slot (0xFFFF for none). Bits 32-63: the kernel's generation. Stage 1 writes only *owned*, the mark, *free* (R6), and *free* → *joining* → *owned* (a fresh start on a free core). Stage 2 adds *leaving*, settling, and taking a live kernel's core: the same word and the same gate entry, with more transitions allowed.
2. **The park request**, one word per core in the park stub's page, written by gates; **`parked`** in the core beacon (p14:1060), written by the stub only. Confirmation is equality (R-1). Stage 1 needs this for the fence already.
3. **Kernel slots apart from physical cores.** The fixed part of the machine table names *n* kernel slots, each with its floor, member word, node beacon, grant and use tables and rings, and the core list apart. `StartCore` (p14:1728) keeps "the node whose own core it is" as the initial owner only; calls that act on a physical core name its core number.
4. **The member word** (p14:1018-1022): the co-hosting transition (p14:1044) and evidence *host* go; evidence 6 becomes *seal* (R-8).
5. **Node beacons:** consumed counters per peer and per credit class, tagged with generations (R-14).

**B. Where a lock would sit in each object** (sizes of p14:1564-1572; stage 1 reserves the fields and never contends them)

6. **Node block:** one kernel lock word and the gate lock of G12 (p14:904); an array of `CORES_PER_KERNEL_MAX` per-core parts holding what p14:608 lists as per core (queues, sum, running context, previous instant, hardware timer, idle table), plus the core's flush epoch, the TLB tags loaded on it, and its pending shootdowns.
7. **`cspace`:** a sequence counter per segment of 128 slots, for the lock-free slot read. The directory's 8 bytes per 128 slots (p14:1570) become 16.
8. **`notify`:** its bits in a word an atomic OR can update (the trial's `sync::Notify`, M5:857-861), inside its 64 bytes (p14:1565).
9. **`endpoint`:** one lock word reserved inside its 64 bytes, for the per-endpoint lock if a measure asks for it.
10. **`aspace`:** in its header page (p14:1569), the set of the kernel's cores that loaded its tag, for shootdown targeting, and eight range-lock words.
11. **`thread`:** in its 1 KB fixed part (p14:1568), the core of its kernel that runs it, and a state *leaving its core* for suspension or destruction from another core (the clustered multikernel's problem, part 1.3).
12. **`sched`:** the core of its kernel whose admission sum holds it, inside its 256 bytes (p14:1566).
13. **`irq`:** the interrupt table becomes per physical core, not per node: 12 KB per core, kept at machine start (p14:1572). Each entry names its target core, and the table of a core belongs to the kernel its word names.

**C. What the gate must already check in stage 1**

14. G10 against core words: stops and starts go only to a core whose word names a kernel whose fence the caller drives and carries the mark, or to a core whose word reads *joining* by the caller (R-2).
15. The core-word transitions, R6's "confirmed, and `SETTLE_NS` after the last stop" (R-2), the park request (R-1), the cores that never move (R-4), and the class at the commit (R-5).
16. The two credit classes and the generation-tagged counters (R-13, R-14).

**D. `abi/` values** (beside today's in `abi/src/machine.rs` at `model` head `c60ad75`: `FENCE_CLASS_*`, `CORE_START_*`, `CORE_STOP_*`, `Member`, `Evidence`, `RoleWord`)

17. `CoreWord`, `CoreState`, `CORE_MARK`; the stub page's start and park requests.
18. `KERNEL_SLOTS` (boot image); `CORES_PER_KERNEL_MAX` (1 in stage 1).
19. `Evidence::Seal`, `SEAL_NS`.
20. The credit numbers (`CREDITS_KERNEL`, `CREDITS_USER`, the cap per task), `PENDING_SIGNALS`, the ring capacity.
21. `core_start`'s physical-core argument; `core_give` and `core_take` with their numbers and checks (stage 1 answers `busy` while `CORES_PER_KERNEL_MAX` is 1); the removal of `core_place` (p14:1202) and `PROXIES_PER_PEER`.
22. The thread state value; the 16-byte `cspace` directory entry; the interrupt table per core.

**E. Contract sections** (at `ede3b38`)

- Rule 7 (p14:17) restated as the one-shot rule, and rule 3's list (p14:13): core words and park requests in, proxies out.
- TLB (p14:318-322): "several cores" means inside one kernel.
- One kernel per core (p14:606-621): per-core admission inside a kernel; parked nodes go.
- `thread_move` goes (p14:59, p14:616); "where a thread may run" (p14:652) becomes "on the cores of its kernel".
- Interrupts (p14:694): a vector of one core of the kernel.
- The living part (p14:758) gains core words; grants by derivation only; calls on another node (p14:854) become the one-shot list.
- G10 and G12 (p14:902, p14:904): G12 written as a rule that applies when `CORES_PER_KERNEL_MAX` > 1.
- Cores: beacons (p14:1060), evidence (p14:1019), the fence over every core a kernel's words name (p14:1083-1101), successor by kernel class (p14:1219), rebuild (p14:1222), calls (p14:1162-1210), numbers (p14:1232-1251).
- Open points: "a node on several cores" (p14:1921) is decided as this staging.

**What a multithreaded native process can do in stage 1: one core.** All its threads live in one kernel, and stage 1's kernels have one core. They run concurrently, time-shared on that core, never in parallel. Parallelism comes only from splitting into processes that share frames and wake each other with signals:
- The web engine already splits that way: "one process per web site" (`web.md:33`), with a Hub, a `RequestServer` and an `AudioServer` (`web.md:23-25`). Each process gets a core, and the threads inside one process (the JavaScript engine, layout, the compositor's core) share it.
- Local inference is planned on llama.cpp "with a Vulkan back end" (`agent.md:11`), so its heavy work may run on the GPU. Whatever it runs on the CPU runs on **one core**.

**The smallest stage-2 subset that lifts it: kernels created with several cores that never change size.** A fresh start takes *k* free cores at once (*free* → *joining* → *owned* on each), and nothing moves after that: no give, no settle, no take of a live kernel's core.

It needs:
- the kernel lock and per-core parts (laid out in stage 1);
- G12's gate lock and flush epochs, with their concurrent proof;
- the shootdown inside a kernel;
- the thread state for cross-core suspension;
- per-core admission;
- the fence of every core a kernel's words name (rules already in stage 1).

It does not need: *leaving*, settling, takes of a live kernel's core, R-16, or the class check at a commit beyond the one made at creation.

The placement service sizes the kernel when the process starts, from its manifest. This is the clustered multikernel of part 1.3, with kernels created at run time. Elastic growth and shrinking are the next increment, on the same words.

### 9.5 What the first round withdraws or amends

Each item is marked in the text above.
- The definition of "confirmed parked" (part 3): amended by R-1.
- Zero-core sealing as an idle state (parts 0, 3.4, 4.2, 4.5): **withdrawn** (R-7).
- The class rule as policy (parts 3.6, 4.2): amended by R-4 and R-5.
- `core_give` among the one-shot calls (parts 3.1, 4.4): amended by R-16.
- One credit pool (part 4.4): **withdrawn** (R-13, R-14).
- The resume and retirement wording (part 4.5): amended by R-9 and R-12.
- "211 lines" (part 5.3): **wrong**, corrected to 174 (197 with doc comments).
- The first explorer (part 6, appendix A): superseded by 9.3. Its runs stand for what they covered, but they did not cover in-flight stops, park epochs, roles, zero-core kernels or credits.
- Part 0's headline on unmaps and changes: amended, since it quoted finer-lock rows.
- C\* as the shape to build first: **withdrawn.** Kernels of several cores are stage 2 (9.4).

### 9.6 What stays unproven

- **No kernel exists.** Every statement about cost is still the trial's simulation, with interrupts modelled (part 7). The measures of part 7 on the i5-14600KF are still to make.
- **The gate of a kernel of several cores** (G12) has no proof, and the tool that would give one is unfinished (`gate-page-tables.md:602`).
- **The bound of R-6** depends on the longest hold of a kernel lock, which no code yet has.
- **Memory ordering of the core word**, the mark and the park request on x86-TSO and Armv8: not modelled. That is the third model of 6.1.
- **The write skew of R-5** between the role word and the core word, which the explorer cannot see.
- **The firmware behaviour R-1 and R-4 rely on:** that `AFFINITY_INFO` reports OFF only after the request's `CPU_OFF`, and that `fence_hart` leaves a hart STOPPED. Neither is checked at source in this draft.
- **What the move protocol costs on hardware** (park, NMI, start), and whether a kernel spanning P and E cores is acceptable (`heterogeneous-cores.md:157`).
- **Grants, one-shot calls and their answers** under the explorer's rings: only the credit counts are modelled.

---

## Appendix A. The explorer

**[2nd round: superseded by `research/drafts/kernel-shape-explorer.py`, part 9.3. This appendix keeps the first explorer as it was run.]**

File: `/tmp/opus-elastic/model/elastic.py`, a standalone Python 3 program with no dependency, written for this draft and kept in that directory. Run, each bounded by `timeout`:

```
cd /tmp/opus-elastic/model
timeout 900 python3 -I elastic.py                      # the six versions, without kernel lifecycle
timeout 300 python3 -I elastic.py free_early --no-p2   # the same broken version, P2 not checked
timeout 7000 python3 -I elastic.py correct --lifecycle # with retirement and fresh starts
```

Output of the first command on 16 November 2026 (about two minutes; the same output came from the first version, which kept whole states in memory):

```
correct: OK, 1819997 states, 9015693 transitions, every state can reach a quiescent state
old_no_settle: VIOLATION after 3 steps: LIVENESS: no quiescent state reachable from here
  1. accuse B
  2. accuse C
  3. A gives core 0
fence_owned: VIOLATION after 5 steps: P2: core 0 executes A but its word is ('free', None)
  1. A gives core 0
  2. accuse A
  3. fence A stops core 1
  4. fence A confirmed
  5. reclaim A: dead
free_early: VIOLATION after 1 steps: P2: core 0 executes A but its word is ('free', None)
  1. A gives core 0
no_flush: VIOLATION after 5 steps: P5: core 0 executes B with a translation installed by A
  1. core 0 loads F for A
  2. A gives core 0
  3. core 0 parks
  4. B takes core 0
  5. core 0 starts in B
acks_owned: VIOLATION after 6 steps: P4: F is free but core 0 still runs A with A's translation of F
  1. core 0 loads F for A
  2. A gives core 0
  3. A unmaps F
  4. core 1 flushes, acks
  5. unmap done
  6. A gives F
```

Output of the second:

```
free_early: VIOLATION after 3 steps: P1: core 0 started into A while it executes A
  1. A gives core 0
  2. A takes core 0
  3. core 0 starts in A
```

Output of the third:

```
correct: OK, 54971344 states, 369929808 transitions, every state can reach a quiescent state
timeout 7000 python3 -I elastic.py correct --lifecycle  2491.24s user 19.78s system 89% cpu 46:46.37 total
```

The program:

```python
"""Exhaustive state exploration of the core-ownership protocol of elastic
kernels (DodOS research draft kernel-shape-opus.md, part 6).

Three kernels A, B, C and four physical cores. A starts with cores 0 and 1,
B with core 2, C with core 3. A frame F belongs to A and is mapped in A's
address space. Every interleaving of these events is explored:

- a live kernel gives one of its cores away (it must keep one), the core
  parks itself, another live kernel takes it and starts it;
- a core running A's user code loads a translation of F;
- A unmaps F (TLB shootdown to its cores), then gives F away, and another
  kernel takes F (memory reused);
- any kernel is accused (at most MAX_DEATHS, never the last live one); a
  live kernel fences it (stops every core whose core word names it),
  confirms, clears its words (R6) and declares it dead;
- with --lifecycle: a kernel that holds nothing retires (its last core
  leaves), and a dead or retired kernel is started again on a free core.

Safety properties, checked in every reachable state or transition:
  P1 a core that is executing is never started (no core runs two kernels);
  P2 a core executes kernel K only while its core word names K;
  P3 no core executes a dead kernel;
  P4 once F is not A's, no core executing A holds A's translation of F;
  P5 a core executing K holds no translation installed by another kernel.
Liveness (no stuck state): from every reachable state, a quiescent state
(no fence, no core leaving or joining, no shootdown in flight) is reachable.

Variants (each breaks one rule of the protocol; the explorer must find it):
  correct         the protocol of the draft
  old_no_settle   the first version, where a parked leaving core could be
                  taken only by another kernel (found stuck by this explorer)
  fence_owned    the fence stops only cores whose word reads owned(K)
  free_early      a leaving kernel writes `free` before the core has parked,
                  and a taker checks only the word
  no_flush        no TLB flush when a core leaves or joins
  acks_owned      a shootdown waits only for cores whose word reads owned(A)
"""

import sys
from collections import deque

KERNELS = ("A", "B", "C")
CORES = 4
INITIAL_OWNER = ("A", "A", "B", "C")
MAX_DEATHS = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--deaths=")), "2"))


def initial():
    word = tuple(("owned", k) for k in INITIAL_OWNER)
    execs = INITIAL_OWNER
    startp = (None,) * CORES
    tlb = (None,) * CORES
    pend = (False,) * CORES
    member = (("A", "live"), ("B", "live"), ("C", "live"))
    return (word, execs, startp, tlb, pend, member, "A", "A", "none", 0)
    # fields: word, exec, start pending, tlb tag of F, shootdown pending,
    # member states, owner of F ("A", "B", "C" or "free"),
    # address space that maps F ("A" or None), unmap state, deaths


def mem(member, k):
    return dict(member)[k]


def set_mem(member, k, v):
    return tuple((x, v if x == k else s) for x, s in member)


def names(w, k):
    return w[1] == k and w[0] in ("owned", "leaving", "joining")


def rep(t, i, v):
    return t[:i] + (v,) + t[i + 1:]


def successors(s, variant):
    """Yield (label, next state, violation or None)."""
    word, execs, startp, tlb, pend, member, fown, amap, unmap, deaths = s
    live = [k for k in KERNELS if mem(member, k) == "live"]

    # Accusation (panic, stale heartbeat or kill): any live or retiring
    # kernel, if another live kernel remains to drive the fence.
    if deaths < MAX_DEATHS:
        for k in KERNELS:
            if mem(member, k) in ("live", "retired") and any(x != k for x in live):
                yield (f"accuse {k}",
                       (word, execs, startp, tlb, pend, set_mem(member, k, "fencing"),
                        fown, amap, unmap, deaths + 1), None)

    if LIFECYCLE:
        for k in KERNELS:
            st = mem(member, k)
            # A dead or retired kernel is started again (fresh generation)
            # on a free parked core, by a supervisor on a live kernel.
            if st in ("dead", "retired") and live and not any(
                    names(word[c], k) or execs[c] == k or startp[c] == k for c in range(CORES)):
                for c in range(CORES):
                    if word[c] == ("free", None) and execs[c] is None and startp[c] is None:
                        yield (f"start kernel {k} on core {c}",
                               (rep(word, c, ("joining", k)), execs, rep(startp, c, k), tlb, pend,
                                set_mem(member, k, "live"), fown, amap, unmap, deaths), None)
            # A live kernel that holds nothing more retires: its gate's last
            # write marks its last core leaving and the kernel retired.
            if st == "live" and any(x != k for x in live) and fown != k and amap != k and not (
                    k == "A" and unmap == "wait"):
                mine = [c for c in range(CORES) if names(word[c], k)]
                if len(mine) == 1 and word[mine[0]] == ("owned", k) and execs[mine[0]] == k:
                    c = mine[0]
                    yield (f"{k} retires, last core {c} leaving",
                           (rep(word, c, ("leaving", k)), execs, startp, tlb, pend,
                            set_mem(member, k, "retired"), fown, amap, unmap, deaths), None)

    for k in KERNELS:
        st = mem(member, k)
        if st == "fencing" and live:
            # The fence stops the cores whose word names k.
            for c in range(CORES):
                covered = (word[c] == ("owned", k)) if variant == "fence_owned" else names(word[c], k)
                if covered and (execs[c] == k or startp[c] == k):
                    yield (f"fence {k} stops core {c}",
                           (word, rep(execs, c, None), rep(startp, c, None), tlb, pend,
                            member, fown, amap, unmap, deaths), None)
            # Confirmed when every covered core is stopped.
            if variant == "fence_owned":
                done = all(not (word[c] == ("owned", k) and (execs[c] == k or startp[c] == k))
                           for c in range(CORES))
            else:
                done = all(execs[c] != k and startp[c] != k for c in range(CORES))
            if done:
                yield (f"fence {k} confirmed",
                       (word, execs, startp, tlb, pend, set_mem(member, k, "fenced"),
                        fown, amap, unmap, deaths), None)
        if st == "fenced" and live:
            # R6: words that name k become free; k's memory becomes free.
            w2 = tuple(("free", None) if names(w, k) else w for w in word)
            f2 = "free" if fown == k else fown
            a2 = None if amap == k else amap
            v = None
            nm = set_mem(member, k, "dead")
            ns = (w2, execs, startp, tlb, pend, nm, f2, a2, unmap, deaths)
            yield (f"reclaim {k}: dead", ns, v)

    # A core running A's user code loads a translation of F.
    for c in range(CORES):
        k = execs[c]
        if k is not None and amap == k and tlb[c] != k:
            yield (f"core {c} loads F for {k}",
                   (word, execs, startp, rep(tlb, c, k), pend, member, fown, amap, unmap, deaths), None)

    # Unmap of F by A, with a shootdown to A's cores.
    if unmap == "none" and amap == "A" and mem(member, "A") == "live" and "A" in execs:
        if variant == "acks_owned":
            targets = [c for c in range(CORES) if word[c] == ("owned", "A")]
        else:
            targets = [c for c in range(CORES) if names(word[c], "A")]
        p2 = tuple(c in targets for c in range(CORES))
        yield ("A unmaps F",
               (word, execs, startp, tlb, p2, member, fown, None, "wait", deaths), None)
    for c in range(CORES):
        if pend[c]:
            if execs[c] == "A":
                t2 = rep(tlb, c, None) if tlb[c] == "A" else tlb
                yield (f"core {c} flushes, acks",
                       (word, execs, startp, t2, rep(pend, c, False), member, fown, amap, unmap, deaths), None)
            else:
                # A core that no longer runs A counts as acknowledged.
                yield (f"core {c} gone, counts as ack",
                       (word, execs, startp, tlb, rep(pend, c, False), member, fown, amap, unmap, deaths), None)
    if unmap == "wait" and not any(pend):
        yield ("unmap done", (word, execs, startp, tlb, pend, member, fown, amap, "done", deaths), None)
    if unmap == "done" and fown == "A" and mem(member, "A") == "live":
        yield ("A gives F", (word, execs, startp, tlb, pend, member, "free", amap, unmap, deaths), None)
    if fown == "free":
        for k in live:
            yield (f"{k} takes F", (word, execs, startp, tlb, pend, member, k, amap, unmap, deaths), None)

    # Elasticity: a core leaves its kernel and joins another.
    for c in range(CORES):
        w = word[c]
        k = w[1]
        if w[0] == "owned" and k in live and execs[c] == k:
            others = sum(1 for d in range(CORES) if d != c and word[d] == ("owned", k))
            if others >= 1:
                nw = ("free", None) if variant == "free_early" else ("leaving", k)
                yield (f"{k} gives core {c}",
                       (rep(word, c, nw), execs, startp, tlb, pend, member, fown, amap, unmap, deaths), None)
        leaving_of = k if w[0] == "leaving" else None
        runs = execs[c]
        if runs is not None and (leaving_of == runs or (variant == "free_early" and w == ("free", None))):
            t2 = tlb if variant == "no_flush" else rep(tlb, c, None)
            yield (f"core {c} parks",
                   (word, rep(execs, c, None), startp, t2, rep(pend, c, False), member,
                    fown, amap, unmap, deaths), None)
        # A leaving core whose park is confirmed (the stub's epoch in the
        # core beacon) becomes free; any live kernel's gate may write it.
        # (The first run of this explorer found the stuck state without it:
        # a core given away that no other live kernel takes.)
        if variant != "old_no_settle" and w[0] == "leaving" and execs[c] is None and live:
            yield (f"core {c} settles free",
                   (rep(word, c, ("free", None)), execs, startp, tlb, pend, member,
                    fown, amap, unmap, deaths), None)
        for k2 in live:
            if variant == "free_early":
                ok = w == ("free", None) and startp[c] is None
            elif variant == "old_no_settle":
                ok = startp[c] is None and (
                    (w == ("free", None)) or
                    (w[0] == "leaving" and w[1] != k2 and execs[c] is None))
            else:
                ok = startp[c] is None and (
                    (w == ("free", None)) or
                    (w[0] == "leaving" and execs[c] is None))
            if ok:
                yield (f"{k2} takes core {c}",
                       (rep(word, c, ("joining", k2)), execs, rep(startp, c, k2), tlb, pend,
                        member, fown, amap, unmap, deaths), None)
        if startp[c] is not None:
            k2 = startp[c]
            v = None
            if execs[c] is not None:
                v = f"P1: core {c} started into {k2} while it executes {execs[c]}"
            t2 = tlb if variant == "no_flush" else rep(tlb, c, None)
            yield (f"core {c} starts in {k2}",
                   (word, rep(execs, c, k2), rep(startp, c, None), t2, pend, member,
                    fown, amap, unmap, deaths), v)
        if w[0] == "joining" and execs[c] == w[1] and w[1] in live:
            yield (f"core {c} joined {w[1]}",
                   (rep(word, c, ("owned", w[1])), execs, startp, tlb, pend, member,
                    fown, amap, unmap, deaths), None)


CHECK_P2 = "--no-p2" not in sys.argv
LIFECYCLE = "--lifecycle" in sys.argv


def check_state(s):
    word, execs, startp, tlb, pend, member, fown, amap, unmap, deaths = s
    for c in range(CORES):
        k = execs[c]
        if k is None:
            continue
        if CHECK_P2 and not names(word[c], k):
            return f"P2: core {c} executes {k} but its word is {word[c]}"
        if mem(member, k) == "dead":
            return f"P3: core {c} executes dead kernel {k}"
        if mem(member, k) == "retired" and word[c] != ("leaving", k):
            return f"P3: core {c} executes retired kernel {k} outside its last leave"
        if tlb[c] is not None and tlb[c] != k:
            return f"P5: core {c} executes {k} with a translation installed by {tlb[c]}"
        if fown != "A" and k == "A" and tlb[c] == "A":
            return f"P4: F is {fown} but core {c} still runs A with A's translation of F"
    return None


def quiescent(s):
    word, execs, startp, tlb, pend, member, fown, amap, unmap, deaths = s
    if any(st in ("fencing", "fenced") for _, st in member):
        return False
    if any(w[0] in ("leaving", "joining") for w in word):
        return False
    if any(x is not None for x in startp):
        return False
    return unmap != "wait"


KCODE = {None: 0, "A": 1, "B": 2, "C": 3}
KNAME = {v: k for k, v in KCODE.items()}
WCODE = {"free": 0, "owned": 1, "leaving": 2, "joining": 3}
WNAME = {v: k for k, v in WCODE.items()}
MCODE = {"live": 0, "fencing": 1, "fenced": 2, "dead": 3, "retired": 4}
MNAME = {v: k for k, v in MCODE.items()}
FCODE = {"free": 0, "A": 1, "B": 2, "C": 3}
FNAME = {v: k for k, v in FCODE.items()}
UCODE = {"none": 0, "wait": 1, "done": 2}
UNAME = {v: k for k, v in UCODE.items()}


def encode(s):
    """Pack a state into one integer (61 bits), to keep millions in memory."""
    word, execs, startp, tlb, pend, member, fown, amap, unmap, deaths = s
    n = 0
    for c in range(CORES):
        n = (n << 4) | (WCODE[word[c][0]] << 2) | KCODE[word[c][1]]
        n = (n << 7) | (KCODE[execs[c]] << 5) | (KCODE[startp[c]] << 3) | (KCODE[tlb[c]] << 1) | int(pend[c])
    for _, st in member:
        n = (n << 3) | MCODE[st]
    n = (n << 2) | FCODE[fown]
    n = (n << 2) | KCODE[amap]
    n = (n << 2) | UCODE[unmap]
    n = (n << 2) | deaths
    return n


def decode(n):
    deaths = n & 3; n >>= 2
    unmap = UNAME[n & 3]; n >>= 2
    amap = KNAME[n & 3]; n >>= 2
    fown = FNAME[n & 3]; n >>= 2
    ms = []
    for k in reversed(KERNELS):
        ms.append((k, MNAME[n & 7])); n >>= 3
    member = tuple(reversed(ms))
    word, execs, startp, tlb, pend = [], [], [], [], []
    for _ in range(CORES):
        pend.append(bool(n & 1)); tlb.append(KNAME[(n >> 1) & 3])
        startp.append(KNAME[(n >> 3) & 3]); execs.append(KNAME[(n >> 5) & 3]); n >>= 7
        word.append((WNAME[(n >> 2) & 3], KNAME[n & 3])); n >>= 4
    rv = lambda x: tuple(reversed(x))
    return (rv(word), rv(execs), rv(startp), rv(tlb), rv(pend), member, fown, amap, unmap, deaths)


def explore(variant):
    from array import array
    s0 = initial()
    assert decode(encode(s0)) == s0
    ids = {encode(s0): 0}
    codes = array("Q", [encode(s0)])
    parent = array("i", [-1])
    plabel = [None]
    offsets = array("Q", [0])
    flat = array("I")
    i = 0
    while i < len(codes):
        s = decode(codes[i])
        v = check_state(s)
        if v:
            return report_ids(variant, codes, parent, plabel, i, v)
        for label, n, tv in successors(s, variant):
            e = encode(n)
            j = ids.get(e)
            if j is None:
                j = len(codes)
                ids[e] = j
                codes.append(e)
                parent.append(i)
                plabel.append(sys.intern(label))
            if tv:
                return report_ids(variant, codes, parent, plabel, j, tv)
            flat.append(j)
        offsets.append(len(flat))
        i += 1
    nstates, ntrans = len(codes), len(flat)
    del ids
    # Liveness: reverse reachability from quiescent states (CSR reverse graph).
    indeg = array("I", bytes(4 * nstates))
    for j in flat:
        indeg[j] += 1
    roff = array("Q", bytes(8 * (nstates + 1)))
    acc = 0
    for j in range(nstates):
        roff[j] = acc
        acc += indeg[j]
    roff[nstates] = acc
    del indeg
    fill = array("Q", roff[:nstates])
    rflat = array("I", bytes(4 * ntrans))
    for src in range(nstates):
        for k in range(offsets[src], offsets[src + 1]):
            dst = flat[k]
            rflat[fill[dst]] = src
            fill[dst] += 1
    del fill, flat
    good = bytearray(nstates)
    q = deque()
    for j in range(nstates):
        if quiescent(decode(codes[j])):
            good[j] = 1
            q.append(j)
    while q:
        n = q.popleft()
        for k in range(roff[n], roff[n + 1]):
            p = rflat[k]
            if not good[p]:
                good[p] = 1
                q.append(p)
    stuck = [j for j in range(nstates) if not good[j]]
    if stuck:
        return report_ids(variant, codes, parent, plabel, stuck[0],
                          "LIVENESS: no quiescent state reachable from here")
    print(f"{variant}: OK, {nstates} states, {ntrans} transitions, "
          f"every state can reach a quiescent state", flush=True)
    return True


def report_ids(variant, codes, parent, plabel, j, why):
    trace = []
    while parent[j] != -1:
        trace.append(plabel[j])
        j = parent[j]
    trace.reverse()
    print(f"{variant}: VIOLATION after {len(trace)} steps: {why}")
    for i, label in enumerate(trace, 1):
        print(f"  {i}. {label}")
    sys.stdout.flush()
    return False


if __name__ == "__main__":
    variants = [a for a in sys.argv[1:] if not a.startswith("--")] or [
        "correct", "old_no_settle", "fence_owned", "free_early", "no_flush", "acks_owned"]
    results = [explore(v) for v in variants]
    sys.exit(0 if results[0] or variants[0] != "correct" else 1)
```

## Appendix B. Sources fetched

All fetched on 16 November 2026 with `curl`; PDFs read through `pdftotext -layout` (poppler-utils, through `nix shell`).

- M. von Tessin, *The Clustered Multikernel: An Approach to Formal Verification of Multiprocessor OS Kernels*, 2012: https://trustworthy.systems/publications/nicta_full_text/5618.pdf (§3 the design, §4.4.1 the thread-deletion problem, §6 and §6.1.1 the proof effort and the missing proofs).
- J. Chapin et al., *Hive: Fault Containment for Shared-Memory Multiprocessors*, SOSP 1995: https://pdos.csail.mit.edu/archive/6.824-2004/papers/hive.pdf (§3 cells fixed at boot, §4.2 write access granted to all processors of a cell).
- G. Zellweger et al., *Decoupling Cores, Kernels, and Operating Systems*, OSDI 2014: https://barrelfish.org/publications/zellweger-decoupling-cores.pdf (§4 "we do not consider fault tolerance and isolation for now", §5.1 and Table 2 the cost of stopping and starting cores).
- Arm, `TLBI ASIDE1IS`: https://df.lth.se/~getz/ARM/SysReg/AArch64-tlbi-aside1is.html ("The invalidation applies to all PEs in the same Inner Shareable shareability domain as the PE that executes this System instruction"; with `HCR_EL2.{E2H, TGE}` = {1, 1} it applies to the EL2&0 regime, the one an EL2 kernel with the virtualization host extensions uses). The same mirror of Arm's register descriptions is the one `kernel.md:161` cites.
- Arm, `TTBR0_EL1`, field `CnP`: https://df.lth.se/~getz/ARM/SysReg/AArch64-ttbr0_el1.html.
- RISC-V SBI v3.0, RFENCE extension: https://docs.riscv.org/reference/sbi/v3.0/ext-rfence.html (`sbi_remote_sfence_vma_asid` takes a hart mask and an ASID).

## Appendix C. What I did not verify

- Whether the 14600KF's performance and efficiency cores report the same features (to read with CPUID on the machine); whether the reference desktop is that processor (D-116 point 4 says "probably").
- The cost of starting and stopping a core on any DodOS target; the figures cited are Barrelfish/DC's, on other machines, with a boot path that loads the image.
- Whether one write of the x2APIC can interrupt several cores at once, and whether the reference processor has a broadcast TLB invalidation; the proposal uses neither.
- The seL4 static multikernel and Barrelfish's single page table per process: taken from the first critique as confirmed by its verification, not re-read by me.
- The energy comparison of case 3.4.
- I did not run the reference model's tests: the proposal changes nothing in it yet, and the explorer of part 6 is a separate program.
