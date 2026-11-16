# Verification of the multicore challenge by gemini-hydrogen, by Opus

Report verified: [research/drafts/multicore-challenge-hydrogen.md](../research/drafts/multicore-challenge-hydrogen.md) (234 lines). Its tests: `scratchpad/pass14/challenge_breaks_hydrogen.rs` (8 tests). I did not read `multicore-challenge-opus.md`.

Sources I used: the contract `architecture/kernel-interface.md` and `decisions/README.md` at Docs `4b12baf` (the contract is unchanged since `3bc7597`). The model is `dodos-kernel` branch `model` at `2afc901`. I also read the reviews in `reviews/`, the trial `trials/multicore/results-mac-m5.md` at `f9933bd` (the scratchpad copy the report cites), and the primary sources fetched on 16 November 2026 (URLs below).

**How I ran the tests.** I cloned the model into `/tmp/xcheck-hydrogen-opus/k`. `System::deliver(index)` now panics when an older message with the same `from` and `to` is in flight (`model/src/system.rs:165-170` of the copy). I added two read-only accessors to my copy (`Model::xcheck_wait` and `Model::xcheck_unit_entries`, `model/src/lib.rs`) so that a test can read a thread's wait and a unit's context entries. The report's tests are `model/tests/challenge_breaks.rs`; mine are `model/tests/xcheck.rs`. Every run was `timeout 600..1200 nix develop -c cargo test -p dodos-model --test <name>`.

## Table of verdicts

| # | Claim of the report | Verdict | Where I checked |
|---|---|---|---|
| C1 | "49 of 61 confirmed faults" (80 %) of rounds 6–7 lie in cross-node protocols, shared tables or the gate | **WRONG.** My count is 34 of 71 strictly between nodes (48 %), 44 of 71 with the gate (62 %). The report counts non-faults and leaves out confirmed one-node faults (section A) | `reviews/2026-11-16-*` |
| C2 | Rounds 1–5 hold no cross-node finding | CONFIRMED (the word "node" appears in none of rounds 2–5) | `grep -c node reviews/2026-11-14-*` |
| C3 | "Zero of the remaining hardware faults exist in a single-kernel SMP design" | **WRONG.** At least 6 apply to any kernel: R6 Mistral F4, F5, F7, F8, F10, F11 | `2026-11-16-model-review-6-mistral.md:53-112` |
| C4 | Repeat offenders: grant names without serial, sealed and co-hosted nodes, dead generations in table words, omissions in `capability_arguments()` | CONFIRMED | section A |
| C5 | "18 shared mutable kernel tables" contradict the thesis | **WRONG as stated.** The living part of the machine table is a decided exception (D-114, D-115): words written by one writer at a time, through the gate, by compare-and-swap. Of the 18 fields, 8 are single-writer, several are fixed or written by hardware, and one (`reports`) is a model shortcut for messages | section B |
| C6 | 18 `Body` variants in `remote.rs` | CONFIRMED | `model/src/remote.rs:37-138` |
| C7 | `Carry`/`CarryDone`/`Ping` are "work stealing", with no application need | **WRONG.** `Carry` carries `core_idle` and `core_perf` to another node's core; `Ping` is the failure sweep's probe | `remote.rs:30-33, 313-325`; contract `kernel-interface.md:1070, 1188, 1192` |
| T1 | Remote `cap_derive` and secondary remote `SchedBind` panic | CONFIRMED (known: R7 Hydrogen F7) | test passes; panics at `lib.rs:1635` and `sched.rs:620` |
| T2 | A stale `RevokeStep` breaks invariant 58 and hangs a third node's revoker, in FIFO order | CONFIRMED (known: R7 Hydrogen F1(1)(2)) | report's test and my `xc2b`: thread stays in `Wait::Node` |
| T3 | A stale `Request(Signal)` signals a third node's notify, in FIFO order | CONFIRMED (known: R7 Hydrogen F3) | report's test asserts `Poll` directly |
| T4 | A PCIe identifier is "permanently wedged" after death and fresh start | CONFIRMED IN PART (known: R7 Argon 1.1). The restarted node can free it, so it is not permanent | my `xc4` |
| T5 | A unit request is lost when the role bounces back | **NOT REPRODUCED** by the report's scenario: the thread completes with `Ok(Done)`. The report's test passes only because of a vacuous assertion. F8 itself stands, on the earlier verifiers' own tests | my `xc5` |
| T6 | NEW: `roles::rebuild` wipes a sealed node's attached IOMMU entry | CONFIRMED (contract and model). The report's test does not show it (its `Busy` comes from the node's own record); my test reads the unit table | my `xc6` |
| T7 | NEW: a `CapDelete` retried while the grantee is fencing hangs for ever | CONFIRMED (contract gap and model). The report's assertion is vacuous; my test reads the wait | my `xc7` and its control |
| T8 | NEW: on an ARM64 signalled core, a failed replacement resume wedges the node in `Unfenced` | CONFIRMED, and wider than stated: any self-park on a class-1 ARM64 core ends unfenced, including `core_stop` kill of one's own node | my `xc8_*` |
| T9 | The 8 tests pass on `4k`, `16k` and `32k` | CONFIRMED, also with ring order enforced | runs |
| F1 | Trial: candidate 3 leads by 2–4 % at 1 % changes and by 27–32 % at 10 % changes | CONFIRMED as figures; read unfairly (needs the modelled 1 µs interrupt; 7–11 % at `ipi` 0) | `results-mac-m5.md:647-649` |
| F2 | Capability changes 2.3–9.6 times faster in candidate 3; IPC within 1–2 % (624k against 638k, 354k against 362k) | CONFIRMED | `results-mac-m5.md:651, 653, 777, 785` |
| F3 | Unmap: "1.44–1.55× (1.50M vs 1.17M at W = 50 ns)" at `ipi` 1 µs; 1.55–2.01× in `br` | **WRONG in part.** 1.50M against 1.17M is the `ipi` 0 cell, a ratio of 1.28. The `br` range 1.55–2.0 is right. Subtree revocation is not measured | `results-mac-m5.md:943-948, 971-980` |
| F4 | Signals: candidate 1 wins 6–8 % "against a locked notify" (1.80M against 1.94M) | CONFIRMED IN PART: 1.80M is the *atomic* notify | `results-mac-m5.md:893` |
| F5 | "A fine-locked shared kernel" is compatible with the fixed points | **WRONG.** Candidate 3 is several cores sharing one kernel node, which breaks "one kernel per core" | `trials/multicore/README.md` "The model" table; `CHALLENGE.md` "Fixed" |
| H1 | `SETTLE_NS` = 1 ms has no hardware basis | CONFIRMED, but the contract says so itself ("the one hardware assumption, to test"). DMA is covered by the IOMMU (R1), not by `SETTLE_NS` | `kernel-interface.md:1099, 1217, 1875` |
| H2 | x86-64: INIT cannot stop the bootstrap core; INIT is blocked in VMX root | CONFIRMED, and already in the contract (D-117) | `kernel-interface.md:1081, 1873` |
| H3 | ARM64: SDEI refuses an EL1 kernel | **WRONG for the present design.** The contract already puts the kernel at EL2 (fixed in pass 13) | `kernel-interface.md:1086`; TF-A `sdei.rst:196-204` |
| H4 | ARM64: on FEAT_NMI cores `PSTATE.ALLINT` masks the NMI | **WRONG** (Non-secure `ALLINT` does not mask EL3 Group 0). The real mask is `SDEI_PE_MASK`, which the gate's firmware allow-list leaves out | `2026-11-16-model-review-7-verify-mistral-by-hydrogen.md:21, 48`; `kernel.md:162` |
| H5 | RISC-V `fence_hart` ships in no firmware | CONFIRMED; the contract says so and runs one node without it | `kernel-interface.md:1087-1088` |
| H6 | Reload assumes peer DRAM survives a warm reset | **WRONG.** A node is reloaded by `core_start` on one core; the machine is not reset. The only warm-reset question in the contract is the crash record | `kernel-interface.md:1150, 1887` |
| P1 | Epoch-stamped grants replace `Revoke`/`RevokeStep`/`Release`/`pinned` | **UNSAFE and blocking** (scenarios in G2): DMA under a grant, stale page-table leaves, a sealed or idle node, a full grant table | section G |
| P2 | Mandatory stage-2 monitor, no `core_place`, no co-hosting | **Contradicts D-117** and a fixed point (a cost on every TLB miss and on every IPI if the ICR is trapped). It is not novel: it is recommendation 1 of `fencing-without-cooperation.md`, which D-117 overruled | section G |
| P3 | Prior art: 18 systems | 9 CONFIRMED, 6 CONFIRMED IN PART, 2 with WRONG figures (Quest-V cycles, Atmosphere ratio), 1 NOT VERIFIED (Popcorn) | section F |

## A. The count of faults (C1–C4)

**My method.** I count one unit per numbered finding of a finder in rounds 6 and 7, plus each new finding of a verifier (N, S, DS). The table below lists what I left out and why. Round 7 counts only what at least one verifier marked CONFIRMED or CONFIRMED IN PART. Round 6 has no verification files, so its findings count as "answered by pass 13" ([D-124](../decisions/README.md), line 134, answers "the 38 findings of the sixth review"). They are not independently confirmed.

| Domain | Round 6 | Round 7 | Total |
|---|---|---|---|
| A. Protocols between nodes (messages, recovery, roles, moves, co-hosting) | Hydrogen F1–F11; Argon F1 (12) | Hydrogen F1–F10 (F9 and F10 only in part); Opus N1, N2, N4; DeepSeek N1; Hydrogen N1-S1, N2-S1, DS-N1-S1; DeepSeek F12 (18) | 30 |
| B. Machine-table words between nodes | DeepSeek F3 (1) | Argon 1.1, Opus S1, S2 (3) | 4 |
| C. The gate over one node's page tables | DeepSeek F1, F2, F4, F10 (4) | DeepSeek F5, F6, F7, F11; Hydrogen N4; Opus S3 (6) | 10 |
| D. One-node rules (any kernel has them) | DeepSeek F7, F8, F9, F11; Argon F2; Mistral F4, F5, F8, F10, F11 (10) | DeepSeek F1, F2, F3, F4, F9, F10; Hydrogen N1, N5 (8) | 18 |
| E. Hardware of other architectures | Mistral F1, F2, F3, F6, F7, F9 (6) | Mistral F2 (in part), F3, F4 (3) | 9 |
| **Total** | 33 | 38 | **71** |

Left out:
- Test and tooling items: R6 DeepSeek F5, F6; R6 Argon F3, F4, F5; R7 Hydrogen F11; Opus N3 and X1; R7 Argon parts 2–4.
- Judged not a fault: R7 DeepSeek F8; Hydrogen N3; R7 Mistral F5.
- Judged wrong: R7 Mistral F1.
- A duplicate: N2 is the same fault as DeepSeek F2.

Sources: the verdict tables at `2026-11-16-model-review-7-verify-deepseek-by-hydrogen.md:18-31`, `-verify-hydrogen-by-opus.md:20-32`, `-verify-hydrogen-by-deepseek.md:22-34`, `-verify-new-findings-by-hydrogen.md` (Verdicts table), `-verify-new-findings-by-opus.md:15-22, 167-203`, and `-verify-mistral-by-hydrogen.md:19-48`.

- Strictly between nodes (A+B): **34 of 71 (48 %)**. With the gate (A+B+C): **44 of 71 (62 %)**. The fence and role items of E exist only because of recovery (R6 Mistral F1, F2, F6; R7 Mistral F2); with them it is 48 of 71 (68 %). The verified round 7 alone gives 21 of 38 between nodes (55 %).
- The report's 61 includes R7 Mistral "F5.1/F5.3". Those are confirmations that pass 13 was right, not faults (`2026-11-16-model-review-7-mistral.md:63-67`). It does not drop R7 Mistral F1, which its verifier judged wrong. Its "shared table, write gate" group of 20 includes one-node `abi` items (`Geometry::valid`, N1 and N5).
- Including rounds 1–5 (about 180 findings, none between nodes) would lower every share further. The multi-node contract only exists from round 6, so it is fair to leave them out, as the report does.
- Repeat offenders (C4), confirmed:
  - grant names without the serial: R6 H F1, then R7 H F1, F3, Opus N2, N2-S1;
  - sealed and co-hosted nodes: R6 H F2, F6–F8, then R7 H F4, Opus N4, and T6 and T8 here;
  - a destroyed thread's request: R6 H F3, then R7 H F5, Opus N1, N1-S1;
  - dead generations in table words: R6 H F5, F10, then Argon 1.1, S1, S2.
- The cross-node class does keep producing faults: 12 in round 6 and 18 in round 7.

## B. The "18 shared mutable kernel tables" (C5)

The fixed point says "no mutable kernel state shared between kernels" (`CHALLENGE.md`). The decision log narrowed it in writing:
- D-114 adds a living part of the machine table ([decisions/README.md](../decisions/README.md) line 124).
- D-115 protects it with a write gate: "mapped read-only in every kernel, one small piece of code is the only writer" (line 125).

The contract then fixes the discipline:
- The living part is "written only through the write gate of the writing node" (`kernel-interface.md:751`).
- "A word of the living part has one writer at a time, by the rules of its kind ... Every write is a compare-and-swap against the value the gate read" (`kernel-interface.md:752`).

So the design forbids shared structures that several kernels write under locks. It allows words that every kernel reads and that change hands by a gated compare-and-swap.

How the 18 fields of `model/src/table.rs:148-221` fall:
- **Single writer:**
  - `beacons`, `core_beacons` (their own node or core, `kernel-interface.md:1052-1053`);
  - `grants`, `uses`, `maps`, `classes` (owner only, except the cleared values of R6, `:752, 1110`);
  - `units` (the role holder);
  - `admitted` (each node publishes its own).
- **Contested by compare-and-swap, as the contract allows:**
  - `owners`, `identifiers` and `devices` (when free, unclaimed or held by a dead node, `:770-776`);
  - `members` (accuser, driver, the node itself, `:1027-1043`);
  - `roles`;
  - the driver field of `fences`.
- **Fixed, or written by hardware:**
  - `off` (`AFFINITY_INFO`), `unusable`, and `placed` (`core_place`).
- **A model shortcut:** `reports`. In the contract, a new unit holder *asks* every live node for its report by message (`:1214`); the model reads a shared vector instead.

What remains true in the report:
- `aspace_map`, `aspace_unmap` and `aspace_protect` write the owner's map counts (G4, `:888`), a shared word, at every mapping change. These are single-writer words, not locks.
- The containment of all these words rests on a gate that is not built and not measured (`:902`, open point `:1889`).
- The member words, role words and ownership compare-and-swaps are a second family of protocols between nodes, through shared memory, beside the messages. The report is right that they hold faults (T4, T6, S1, S2).

"Contradicts the core thesis" is wrong. "The design keeps a small set of gated, compare-and-swap words, and their rules are part of the protocol surface" is right.

## C. The tests (T1–T9)

All 8 of the report's tests pass on `4k`, `16k` and `32k` with ring order enforced, so none relies on overtaking. But three of them assert a "hang for ever" with `ThreadConfigure` returning `Busy`. The contract makes `thread_configure` `busy` whenever the thread "must be suspended and must not wait" is false (`kernel-interface.md:174`; model `threads.rs:44-47`). Every thread in those tests was resumed, so `Busy` holds whether it waits or not. Those assertions prove nothing. I re-ran each scenario reading `runnable()` and the thread's wait.

- **T2** (part B): node 1's revoker stays `runnable=false wait=Node(..)` after 2 s; `check()` passes, so the invariants do not see it. CONFIRMED. This is R7 Hydrogen F1(2), already confirmed by two verifiers.
- **T5:** at the end, node 0's attaching thread is `runnable=true wait=None woken=Some(Ok(Done))`. **NOT REPRODUCED.** F8 is still real on the scenarios of `-verify-hydrogen-by-opus.md:27` and `-by-deepseek.md:29`.
- **T6:** with the unit table read directly:
  - after the attach, `[(0, (0, 1))]`;
  - after node 1's death and node 2's take-over while node 0 is sealed, `[]`;
  - after node 0 resumes, still `[]`, and `check()` passes.

  Node 0 believes device 0 is attached (`memory.rs:495-496` answers `busy` from the node's own `attached`), but no context entry exists, so its device's DMA is blocked without notice. The contract is the cause. It says the rebuild "clears those that no live node claims" (`:1214`), and a sealed node is not live although it keeps its objects (`:1022`). The model follows it (`roles.rs:446`). **CONFIRMED, contract and model.** Fix: count the reports of starting, live, sealing *and sealed* nodes. A sealed node holds no unit role but may own devices.
- **T7:** after the first `CapDelete` the thread waits on `Node(2)`. R0 at `recover(1)` wakes it with `gone`. The retry while node 1 is fencing returns `Waits` on `Node(3)`. After node 1 is dead and the grant is freed (`grant_entries() == []`), the thread is still in `Node(3)`. The control without a retry ends with `gone`, and a later `CapDelete` returns `Done`. **CONFIRMED.** The contract gap: R0 ends the waits that exist when *Y* sees *X* fencing (`:1098`). A removal that reaches an anchor whose grantee is already fencing sends a request and waits (`:842`), and nothing ends that new wait. Pinning (R3, `:843, 1104`) starts only at fenced. Fix: treat a grantee that is fencing like a pinned one (`again`, no message), or end any wait begun on an accused node at once.
- **T8:**
  - On ARM64 class 1, a live node that panics (`sys.panic`, core left running its handler) ends `Dead`.
  - A node that parks itself, by a failed resume or by `core_stop` kill of its own node, ends `Unfenced`, core `Parked`.
  - On class 2 the same self-stop ends `Dead`.

  The model's SDEI signal is delivered only to a `Running` or `Hung { nmi: true }` core (`system.rs:370-384`), and `ParkSelf` sets `Parked` (`:395-401`). The contract says a failing node "parks itself" (`:1062`) but not how on ARM64. If the park loop masks SDEI, no confirmation ever comes, and the node's memory is lost until restart (`:1091`). **CONFIRMED, wider than reported.** Fix: on ARM64, a node that parks itself calls PSCI `CPU_OFF` (allowed for its own core, `kernel.md:162`), so `AFFINITY_INFO` confirms.
- **T4:** node 2's attach is `Denied`. But node 1's new generation can attach then detach (`Waits`, `Waits`), after which node 2's attach is `Done`. CONFIRMED IN PART, as the Opus verifier found (`-verify-new-findings-by-opus.md:20`). Its fix, "the rule of taking judges the generation" (`:143`), is the report's Change 4.
- **T1, T3:** confirmed by the tests' own direct assertions. Both are known (R7 F7, F3).

The report's "three newly found" bugs are T6, T7 and T8. All three are real; none needs a redesign. T6 needs one word in a rule, T7 one rule, T8 one firmware call.

## D. The trial figures (F1–F5)

The figures are mostly copied right. The reading is not fair:
- **Which candidate.** "Candidate 3" is "the k cores of the multithreaded process share one node" (`trials/multicore/README.md`, "The model"). It is a kernel shared by several cores, under locks. The owners fixed "one kernel per core" (`CHALLENGE.md`). The contract keeps one node per core and leaves the question to the trial (`kernel-interface.md:1888`, D-111, D-116 point 2). The report's verdict line 6 and its "Change 3" recommend what the brief said to keep fixed, while §5 claims "every option preserves all six constraints". Its "Keep: 1 kernel per core / per L3 cluster" also breaks it.
- **What the margin depends on.** The 27–32 % holds only with the *modelled* 1 µs interrupt. At `ipi` 0 it is 7–11 %, and at 1 % changes the candidates are level (2–4 %) (`results-mac-m5.md:647-649`). The trial says the real interrupt cost, change rate and W "still decide the a1 rows" (`:688-689`).
- **What is not measured.** For unmaps, the trial warns that the revocation of a subtree "is not measured, and the numbers above say nothing about it" (`:971-980`). The bench measures synchronisation only. Neither the containment nor the recovery of a shared group kernel is measured (README, first paragraph).
- **Where candidate 1 wins.** Left out by the report: many-to-one signals by 6–8 % at k = 4 (`:893-896`), lookup tails (1.04 × W against 1.7 × W), and the k = 8 rows run about half on efficiency cores (`:631`).
- F3: "1.50M vs 1.17M" is the `ipi` 0 row, a ratio of 1.28. At `ipi` 1 µs the group lock gives 1.07M/731k = 1.46 and 940k/676k = 1.39 (`:946-947`); the 1.50M/1.17M cell is `:943`.

## E. Hardware fencing (H1–H6)

- **H1.** The contract already names `SETTLE_NS` as "the one hardware assumption, to test" (`:1217`) and lists it among the times to measure (`:1875`). DMA is blocked through the IOMMU in R1 (`:1099`), not by waiting. The report's "hung DMA engines" point is therefore covered.
- **H2.** True, and already the decided residue of D-117 (`:1081`, open point `:1873`). Running DodOS as a guest under KVM or Hyper-V is not addressed by the contract: a gap (suspicion), not verified.
- **H3.** TF-A: "the dispatcher will only allow SDEI calls to be made from: EL2, if EL2 is implemented" (`sdei.rst:196-204`, v2.12.0, https://raw.githubusercontent.com/TrustedFirmware-A/trusted-firmware-a/v2.12.0/docs/components/sdei.rst). The contract already says "The kernel runs at the highest non-secure exception level ... EL2" (`:1086`). The report cites an R6 fault fixed in pass 13 as present.
- **H4.** The R7 verifier found: "NS `PSTATE.ALLINT` does not mask EL3 Group 0 interrupts, but interrupted NS software can block/delay SDEI event 0 via `SDEI_PE_MASK`" (`-verify-mistral-by-hydrogen.md:21`). TF-A requires `PE_UNMASK` before dispatch (`sdei.rst:253-254`). The gate's ARM64 allow-list holds only "SDEI registration and `SDEI_EVENT_SIGNAL`" (`kernel.md:162`), and G11 forbids firmware calls outside the gate. So that mask is closed by design, except for a wild jump into the gate. The contract should name `SDEI_PE_MASK` as refused.
- **H5.** Correct, and decided: such harts are class 0, and the machine runs one node unless the monitor is declared (`:1087-1088`).
- **H6.** Reload is "`core_start` mode fresh ... from *X*'s floor and the kept image" (`:1150`). The warm reset appears only for the crash record handover (`:1887`).

## F. Prior art (P3)

| System | Report's claim | Verdict | Source |
|---|---|---|---|
| seL4 | big-lock SMP, multikernel proof Q3 2028 | CONFIRMED. The FAQ also says: "It is not meant to scale to many cores, where instead a multikernel is the right approach" (this supports DodOS's direction) | https://sel4.systems/About/FAQ.html ; https://sel4.systems/roadmap.html ("Project scheduled to complete Q3/28") |
| LionsOS | static | CONFIRMED ("The system is static") | https://lionsos.org/ |
| seL4 CMK | "confirms cross-cluster revocation complexity" | NOT VERIFIED (not on the page: an OLD project page, "Clustered-Multikernel Design Problem") | https://trustworthy.systems/projects/OLD/cmp |
| Barrelfish TN-013 | distributed revoke/delete across cores | CONFIRMED IN PART: revoke through mark commands and remote relations (TN-013 pp. 23 and following, `KernelCmd_Revoke_mark_*`, conflicts section). "2-phase" is the report's label | https://barrelfish.org/publications/TN-013-CapabilityManagement.pdf |
| Barrelfish/DC | kernel replaced, state moved, cores added and removed | CONFIRMED (abstract) | https://www.usenix.org/conference/osdi14/technical-sessions/presentation/zellweger |
| NrOS | replicas with operation logs | CONFIRMED ("replicates kernel state on each NUMA node and uses operation logs"); verified-nrkernel not checked | https://www.usenix.org/conference/osdi21/presentation/bhardwaj |
| Popcorn | replicated-kernel, migration | NOT VERIFIED (the README gave no readable text) | https://github.com/ssrg-vt/popcorn-kernel |
| Hive | firewall bits, discard of suspect pages | CONFIRMED ("a write permission bit-vector associated with each page", "preemptively discarded") | https://www.scs.stanford.edu/nyu/04fa/sched/readings/hive.pdf |
| K42 | clustered objects with representatives | CONFIRMED | https://www.cs.bu.edu/~jappavoo/Resources/Papers/a6-appavoo.pdf |
| Corey | address ranges, kernel cores, shares | CONFIRMED | Corey OSDI'08 HTML |
| fos | spatial servers | CONFIRMED in substance ("replaces time sharing with space sharing"); the quote "no sharing between cores" was not found | fos OSR 2009 PDF |
| Tessellation | space-time partitioning, cells | CONFIRMED | HotPar'10 PDF |
| Quest-V | EPT sandboxes; "707–885 cycles"; "1.45×10^7 cycles" | CONFIRMED IN PART: interrupts "without monitor intervention", one trap "every 3 to 5 minutes". **The two cycle figures are not in the cited paper** (they come from `fencing-without-cooperation.md:327`, which cites no page of it). Proposal 2's "Quest-V hypercall baseline 497–961 cycles" is **WRONG**: that is Hyperkernel's figure (`fencing-without-cooperation.md:32`) | https://www.cs.bu.edu/~richwest/papers/vee2014.pdf |
| Theseus | fault recovery of OS components | CONFIRMED ("cell-level" not on the page) | OSDI'20 page |
| Hubris | zero heap, static tables, no capability revocation | CONFIRMED IN PART: restartable drivers and isolation are on the page; the rest NOT VERIFIED | https://hubris.oxide.computer/ |
| Atmosphere | SMP locking, proof:code 3.32 | **WRONG figure:** the cited page says "big-lock synchronization" and "proof-to-code ratio of 7.5:1" | https://mars-research.github.io/projects/atmo/ |
| CortenMM | fine-grained locked VM | CONFIRMED IN PART ("RCU-based page table lock protocol"). "Outperforms cross-core messages" is the report's own inference from the M5 trial | https://github.com/TELOS-syslab/CortenMM-Artifact |
| Linux multikernel RFC v2 | kexec, per-core instances, IPI | CONFIRMED (Cong Wang, 18 Oct 2025: "Improved fault isolation", "Generic IPI communication framework"); CXL NOT VERIFIED | https://lwn.net/Articles/1042586/ |

WASI 0.3.0 without threads: the figure matches `wasm-abi.md:128`; I did not re-check it upstream.

## G. The proposals: what is lost, what is false, what is missing

The needs come from `architecture/*.md`:
- The data plane uses rings in shared frames between a driver's node and an application's node (`kernel-interface.md:1782-1784`).
- Devices follow their driver's node (`drivers.md:58`).
- Memory moves between nodes by the memory service (`memory.md:11`).
- Native code needs real threads from the start (`wasm-abi.md:128`).
- Kernel replacement is seal and resume with image 1 (`:1175`).
- Sleeping cores park their nodes on an awake core (D-108).

**Option A (rings and a fence; the rest in user space).**
- *Before:* a thread calls an endpoint or a notify on another node directly (rule 7, `:17`). A capability travels in a message to another node (`:836`). The placement service moves a thread (`thread_move`). The power service sets `core_idle` and `core_perf` on any node (`:1188, 1192`).
- *After:* every cross-node call is marshalled by a user-level coordinator, threads never move, and the power service needs a thread on every node.
- *False:* it keeps "SPSC shared memory frames (`Frame` grants only)" but cuts `Revoke`, `RevokeStep` and `Release`. A frame grant cannot be freed until the holder has removed its leaves (G6, `:890`; `:842`), so the revocation protocol stays for frames. The "~0.1–0.5 µs" per hop has no measure behind it in the repository. Cutting `Ping` removes the detection of idle nodes that died silently (`:1070`).
- *Missing:* the coordinator is itself a distributed, replicated service with its own recovery. Barrelfish's monitor shows the same conflicts reappear in user space (TN-013, conflict cases).

**Option B (static partitions).**
- *Lost:* memory that moves between nodes, which the user asked for when rejecting the equal split ([D-112](../decisions/README.md), line 122). Devices that follow a driver that moves (D-113). Parked nodes for sleeping cores (D-108).
- It reverses two user decisions; the report does not say so.

**Option C (one owner, non-delegatable names).**
- The contract already has one owner and one hop: "every grant is between the object's node and one holder, and the use of a remote capability never walks more than one hop" (`:839`).
- *Lost:* a client on *Y* passes a frame it received from *X* to a driver on *Z* for DMA. Today the kernel asks *X* for a new grant; after, user space must do an RPC to *X*.
- *False:* "removes 80 % of `remote.rs`" (no measure). Removing `Revoke`, `RevokeStep` and `Release` removes the memory safety of granted frames (`:842`) and the reuse of grant entries.

**Option D (notify and frames only).**
- *Lost:* a synchronous call to a server on another node: the supervisor and memory service replicas on the reserve nodes (`:1216`), and budget lending (`:858`).
- It keeps frames, so the same contradiction as A applies.

**Option E (replicated log, synchronous epoch).**
- The contract considered and refused a log: "Why a word per node and not a log of events ... a membership service with views needs every node to agree on a sequence of views" (`:1047`).
- A synchronous epoch over live nodes makes every `memory_take` and role change wait for a hung node until it is fenced (`STALE_NS` 100 ms, `:1231`).
- A shared log with several writers is more shared mutable state than today, not less.

### G1. Novel proposal 1: epoch-stamped grants

The proposal: *X* bumps `rev_epoch`, sends a doorbell, waits until every live core's `flush_epoch` passes it, then frees, with no `RevokeStep` and no `Release`. Four scenarios:

1. **Unsafe, DMA.**
   - *Y* maps *X*'s frame in an iospace under the grant (`iospace_map`, `:841`).
   - *X* revokes, every CPU core passes its flush epoch, and *X* returns the frame to an untyped and reuses it (say as page-table pages).
   - *Y*'s device still holds the leaf in *Y*'s iospace tables and in the IOTLB. The IOMMU invalidation is a request to the unit holder (`:865`), and no CPU flush epoch covers it. The device writes into *X*'s reused memory.
2. **Unsafe, CPU.**
   - A flush only empties TLBs. *Y*'s page-table leaves are still there, and the next TLB miss on *Y* walks them again: the hardware does not read `rev_epoch` ("never on an ordinary memory access or a TLB miss", `:870`).
   - So *Y* must remove its leaves itself, in bounded steps (`:842`), and tell *X* when done. That is `RevokeStep` under another name.
3. **Blocking, or unsafe.**
   - "Each live core" includes cores that are idle without a timer and never advance an epoch unless interrupted. Every revocation then costs an interrupt to every core, not one message to one grantee, and a hung unrelated node blocks every revocation until it is fenced.
   - If sealed nodes are skipped (a sealed node is never observed, `:1070`), a sealed holder resumes with its leaves intact: case 2.
4. **Blocking by exhaustion.**
   - Without `Release`, a grant entry is freed only when *X* revokes it.
   - A server on *X* that hands short-lived capabilities to clients on *Y* fills its 4,096 fixed entries (`:834`).
   - Every later transfer then fails (`no_memory`, `caps_dropped`, `:836`).

Also:
- "`G12` flush_epoch, already required" is wrong. G12 applies only "if the trial adopts" several cores per node, and it is per node (`:896, 1888`).
- The serial already is a per-entry epoch, and the contract already requires it on every message that acts on a grant (`:834, 855`). T2 and T3 are model omissions of that rule; the cure is to apply it, not a new field.

### G2. Novel proposal 2: a mandatory stage-2 monitor (check against D-117)

D-117 ([decisions/README.md](../decisions/README.md) line 127) says:
- the principle: "a guarantee is paid for at failure time or at a rare event, not on every memory access";
- point 2: "A faulty kernel is then bounded to its own memory without two-stage translation";
- point 3: the monitor "is not the default: it becomes an optional hardening layer that the image declares".

The proposal makes it mandatory. That costs:
- a two-stage walk on every TLB miss (compile −0.6 %, graph500 6 % → 13 % with 2 MB blocks, `fencing-without-cooperation.md:28-31, 179`);
- "+1 exit if the ICR is intercepted" on every IPI between nodes (`:176`), that is every cross-node message wake-up, which is not a rare event.

It breaks the owners' principle, which `CHALLENGE.md` lists among the fixed points. It is not new: it is that draft's recommendation 1 (`:34-35`), overruled by D-117.

*Lost:*
- Kernel replacement without losing a node's processes (seal, then resume with image 1, `:1175`): the proposal drops co-hosted sealing and `core_place`, and its "unserved needs" names only "live core migration".
- Parked nodes for sleeping cores (D-108).
- Machines where the OS enters at EL1 under a vendor hypervisor, which still need today's design (`fencing-without-cooperation.md:37`).

*Missing:* a protocol between monitors to stop another core, and who owns the IOMMU units.

"Fixes T6 and T8 by construction" needs no monitor: T6 needs one word in the rebuild rule, T8 one `CPU_OFF`.

### G3. The ranked list

- **"Cut" 1 bundles two things.** Removing remote destinations from `cap_derive`, `cap_move` and `untyped_retype` (`:836`) is a defensible narrowing: transfer in a message does the same, and the model has no executable check for them (`:1894`). Cutting `RevokeStep`, `Release` and `pinned` removes the safety of granted memory (G1 above).
- **"Cut" 2:** `Carry` and `Ping` are not stealing (C7). Sealing is how a kernel is replaced.
- **"Change" 4 and 5** are right. They are the contract fix already proposed by Opus (`-verify-new-findings-by-opus.md:143`) and the contract's own rule (`:855`) applied in the model.

## H. What the report missed

1. **Its own evidence method.** Three of its eight tests use a probe that is always true, and one of them (T5) does not reproduce. This is R7 F11 again (`liveness.rs` cannot see a thread stuck on another node: `-verify-hydrogen-by-opus.md:30`). It is the weak point that lets cross-node faults survive pass after pass.
2. **T8 is general.** Any self-park on an ARM64 class-1 core is never confirmed in the model. The contract does not say how an ARM64 kernel parks itself (`:1062`).
3. **T6 and T7 are contract gaps**, not only model bugs: "no live node claims" (`:1214`), and waits begun after R0 (`:1098`).
4. **A simpler alternative to every redesign.** Most round-7 faults between nodes belong to one class: a message acts on a name (grant, move, request) that was reused. A single checking function at message receipt would close F1, F3, N2, N2-S1, T2 and T3 at once. It would check the sender, its generation, the grant index, the serial and the object kind (rule `:855`).
5. **The models that would find these classes without hand-written scenarios** are still to do: "the three models checked by state exploration (revocation between nodes ...; change of size of a group; recovery ...)" (`:1893`, D-027). Thirteen passes of scenario tests find these faults one at a time; an explorer over 3 nodes, FIFO per pair and one death would find them in bulk.
6. **Suspicion, not verified:** TF-A refuses a dispatch while "A dispatch for the same event must not be outstanding" (`sdei.rst:265-266`, stated for explicit dispatch). If a dying kernel faults inside its SDEI handler before `CPU_OFF`, a second signal may never be delivered, and a class-1 core would end unfenced. This should be checked against DEN 0054 for `SDEI_EVENT_SIGNAL`.

## My judgement, in ten lines

1. I would not cut what the report proposes to cut. Its strongest numbers are wrong (49/61) or read unfairly (the trial).
2. Its only performance argument is a shared group kernel, which the owners fixed out.
3. Its "three new bugs" are real, but each has a one-rule fix: a word in the rebuild rule, a rule for waits begun after R0, `CPU_OFF` on an ARM64 self-park.
4. Epoch-stamped grants are unsafe under DMA and stale page-table leaves, block on idle or sealed nodes, and exhaust the grant table.
5. The mandatory monitor reverses D-117 and puts a cost on every TLB miss and every cross-node IPI.
6. One cut I would accept: no remote destination for `cap_derive`, `cap_move` and `untyped_retype`; transfer by message instead.
7. The fault data does show a real problem: half the confirmed faults are between nodes, in the same few classes, pass after pass.
8. The cure that data points to is cheaper than a redesign: one receive-check function for every message (sender, generation, serial, kind).
9. Add a probe that sees any thread stuck on another node, and build the state-exploration models D-027 already asks for.
10. If that explorer still finds new protocol faults after those fixes, reopen the cut. Not before.

## Appendix: my tests (`/tmp/xcheck-hydrogen-opus/k/model/tests/xcheck.rs`, helpers copied from the report)

```rust
// Accessors added to the copy only (model/src/lib.rs, impl Model):
pub fn xcheck_wait(&self, thread: ObjId) -> String {
    self.threads.get(&thread).map(|t| format!("{:?}", t.wait)).unwrap_or("none".into())
}
pub fn xcheck_unit_entries(&self, role: usize) -> Vec<(u16, (u16, u32))> {
    self.table.units.get(&role).map(|u| u.entries.iter().map(|(&d, &e)| (d, e)).collect()).unwrap_or_default()
}

// T6: unit entries read directly. Output: after attach [(0, (0, 1))]; after rebuild []; after resume [].
// T7: output: retry -> Ok(Waits) on Node(3); member1 Dead; grants []; end: runnable=false wait=Node(3).
//     Control without retry: woken=Some(Err(Gone)); CapDelete afterwards -> Ok(Done).
// T5: output: end: runnable=true wait=None woken=Some(Ok(Done))  (not reproduced).
// T8, self-stop on ARM64:
#[test]
fn xc8_self_stop_arm64_signalled() {
    for class in [FENCE_CLASS_FORCED, FENCE_CLASS_SIGNALLED] {
        let (mut sys, t) = arm(class); // machine_n(2), arch Other, cores[1].fence = class
        let r = sys.apply(1, t[1], Syscall::CoreStop { core: core(1), mode: CORE_STOP_KILL });
        sys.run(sys.now() + 2000 * MS, MS);
        eprintln!("class {class}: {r:?} -> {:?} core={:?}", sys.member(1).state(), sys.core(1));
    }
}
// Output: class 2: Ok(Done) -> Dead core=Off ; class 1: Ok(Done) -> Unfenced core=Parked.
// A live node that panics with its handler running ends Dead on both classes.
// T4: node 2 attach Denied; node 1 gen 2 attach Waits, detach Waits; node 2 attach then Done.
```
