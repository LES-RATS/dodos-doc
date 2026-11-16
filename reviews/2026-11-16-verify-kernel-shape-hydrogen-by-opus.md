# Verification of `kernel-shape-hydrogen.md` ("shape D"), by Opus

- **Reviewer:** Claude Opus 5.5, 16 November 2026, for the brief `pass14/XSHAPE.md`.
- **Report judged:** [`research/drafts/kernel-shape-hydrogen.md`](../research/drafts/kernel-shape-hydrogen.md) (cited below as "H:N", N being its line).
- **Baselines:**
  - `kernel-interface.md` and `kernel.md` are cited at `3bc7597`, the report's own baseline, as "ki:N" and "k:N". The contract was committed as pass 14 (`c178228`) while I worked. Pass 14 moves some lines but keeps rule 7, the proxies, the frame definition and the TLB hook that this review relies on. I checked that by diffing the two commits for those terms.
  - The model is cited at `2afc901`, the report's baseline. At today's `model` head (`6a8a666`) `PROXIES_PER_PEER` sits at line 225, not 209.
  - The trial is cited at `trial-multicore` `f9933bd`, as "M5:N" for `trials/multicore/results-mac-m5.md`. I read all of these through `git archive` into `/tmp/xshape-opus`; I never checked out a branch.
- **The report's own tests:** none. The report proposes three TLA+ specifications and one new test (H:219-231), and none was written. No `.tla` file exists in `Docs` or `dodos-kernel`. The authoring transcript under `~/.t3/userdata/providers/antigravity/.../brain/f53e2265-.../logs/transcript.jsonl` shows no run for this report. The tests it cites already existed. So its claims about its own mechanisms are **not verified** by anything it ran.
- **What I ran:** [`/tmp/xshape-opus/explore.py`](/tmp/xshape-opus/explore.py), a breadth-first explorer (Python 3, run with `timeout 120`) of two of the report's mechanisms, with variants that break on purpose. Results are in section 3.

## Table of verdicts

| # | Claim or mechanism | Verdict |
|---|---|---|
| 1 | `GRANTS = 4096` (`abi/src/machine.rs:101`) | CONFIRMED |
| 2 | P1: a 4 GiB heap on 16 nodes needs 30,720 grants under the present contract | CONFIRMED only for 4 KiB pages. The report leaves the condition out: a frame is already a run of up to *E* = 512 pages (ki:27, ki:236), so with 2 MiB pages the heap is 4 frames, i.e. 60 grants with no new mechanism |
| 3 | 18 `Body` variants (`model/src/remote.rs:37-138`) | CONFIRMED (counted: 18) |
| 4 | `PROXIES_PER_PEER = 16`, 64 MB of proxies at 64 cores | CONFIRMED (`machine.rs:209-210`; 64 × 64 × 16 × 1 KiB = 64 MiB) |
| 5 | Shape D has "9 message variants" (H:163) | WRONG: its own text needs at least 15 (section 3.4) |
| 6 | Lazy map "matches" ki:318 | WRONG: ki:318 and ki:320 make a map eager and say added translations "may cause no fault". Lazy faults are a contract change, not a match |
| 7 | M5:971-978 shows `cap_revoke` "deadlocked in lock ordering" and C "breaks D-042" | WRONG: M5:975-978 says the lock order "is not settled; it is not measured" |
| 8 | gate-page-tables.md:602: C "breaks" the sequential Verus proofs | Overstated: the line says G12 adds a lock and that VerusSync-style reasoning is "unfinished". That the one-core gate keeps sequential reasoning (:601) is CONFIRMED |
| 9 | Lookups favour D/A over C (M5:93-96) | Numbers CONFIRMED. The reading is unfair: these are first-series rows with every lookup under the group lock, and the second series (seqlock) makes the p50 equal (M5:355-356, M5:398) |
| 10 | E-core stalls "quantified" at 7.90-8.06 µs (M5:96, M5:103) | WRONG attribution: those rows show the single lock saturating at W = 1 µs and k = 8, and M5:42-45 says k = 6-8 rows "say little". Lock-free lookups remove the effect (M5:345-349) |
| 11 | Lazy adds: derive p50 −39 % / −43 % (M5:362, M5:495) | Numbers CONFIRMED; misattributed. They measure capability derive, not `aspace_map`. The trial's "lazy adds" still send every copy and only stop waiting (M5:321-324), with no fault at all. Shape A can take the same switch |
| 12 | Unmap one initiator (M5:546), all initiators (M5:944, M5:947) | Numbers CONFIRMED. D's figures are candidate 1 with the trial's switches, which A also gets. The report omits that C with range locks leads at `ipi` 0 too (1.39M against 1.04M, M5:944) |
| 13 | IPC (M5:785), signals (M5:802, M5:894, M5:926), `srv` (M5:994, M5:1026-1029), single-lock ceiling (M5:80) | Numbers CONFIRMED. The single-lock ceiling is used against a 64-core C that would use the finer locks of the third and fourth series, which removed that ceiling |
| 14 | `notify_loses_no_wake_up` fails 3/3 runs with check-then-set | CONFIRMED (M5:857-861; the report cites M5:850, the section heading) |
| 15 | Cited tests and Kani proofs exist (`nodes.rs:643`, `:1048`, `recovery.rs:971`, `liveness.rs`, `machine.rs:1289`, `:1322`) | CONFIRMED. Their FIFO failure is as reported in verify-opus-by-hydrogen:107 |
| 16 | Review findings reused (32 releases, `roles::rebuild`, T8, D-108 bug history) | CONFIRMED (verify-opus-by-hydrogen:109; verify-hydrogen-by-opus:27, 70, 120) |
| 17 | WASI 0.3 has no threads (wasm-abi:128) | CONFIRMED, but cut short: the same line says "Native code (Ladybird, inference) needs real threads from the start" |
| 18 | Idle and detection rules (ki:595, 1052, 1063, 1069), no vote (ki:1073), `core_stop` refuses if no other node stays live (ki:1181) | CONFIRMED |
| 19 | k:44, 48, 49 (C's blast radius, home loss, reserve replicas) | CONFIRMED. ki:43 cited for D-108 is a wrong line (it is the `debug` row) |
| 20 | Hardware: 14600KF has 6P+8E | CONFIRMED (Intel ARK; Memory Express listing) |
| 21 | Hardware: INIT blocked in VMX root; Linux `e1c467e69040` wakes CPU0 by NMI because INIT runs firmware boot code; `sbi_hart_stop` stops only the caller | CONFIRMED (SDM Vol. 3C mirrors; `gh api` commit message; RISC-V SBI HSM spec) |
| 22 | Hardware: SDEI DEN0054C §3.2.1, PSCI `CPU_OFF`, SDM §28.3/§34.8, Arm `TLBI VALE1` | NOT VERIFIED by me at source. The report copies them from the repository's drafts and reviews (verify-opus-by-hydrogen:115 confirmed the Arm TLB point) |
| 23 | Waking from deep sleep takes "microseconds" | Misleading: Linux's Alder Lake table gives exit latencies of 220 µs (C6), 280 µs (C8) and 680 µs (C10). Raptor Lake has no entry and uses firmware tables |
| 24 | **Run-grants**: safety of revocation | Holds in my model if the grantee clears its use entry atomically with its final answer |
| 25 | **Run-grants**: liveness of revocation | BROKEN as written (scenario 3.1). The report has the *granter's* gate refuse new mappings (H:173), but the grantee's gate installs them, so a thread that keeps faulting makes `cap_revoke` return `again` for ever |
| 26 | **Run-grants**: partial revocation, fragmentation | BROKEN on the table bound. A hole in the middle forces revoking the whole run on every peer. Under fragmentation the grant count returns to 15,360 > 4,096 |
| 27 | **Lazy `aspace_map`** racing an unmap | BROKEN as written (scenario 3.2, found by the explorer). `AspaceSupply` travels on a separate fault ring (H:181), overtakes nothing in FIFO terms, and installs a freed frame after the unmap returned. Fixed by a sequence check |
| 28 | Lazy map: who answers, home death, cost | The home answers, so it is a blocking remote wait that the report says D removes. Home death ends it with `gone` (sound). Cost against the saved message: not measured anywhere |
| 29 | **Stateless signal grants** | BROKEN on authority (scenario 3.3): any kernel can mint a valid token from slot 13, the badge comes from the sender, and selective revocation is lost. Serial wrap is reachable in 14 to 72 minutes of local churn (a suspicion; the present 30-bit grant serial has the same unaddressed exposure) |
| 30 | **Idle cores sleep in place** | Sound as a power mechanism. It applies equally to C, so the report's case 4 against C is WRONG. It does not serve "the number of kernels following the demand" |
| 31 | **"WASI has no threads, so the many-threads process is not central"** | WRONG as a ground for D: native Ladybird and inference need threads from the start (wasm-abi:128). And if the claim held, it would also remove D's own lazy-aspace and run-grant machinery |

## 1. Claims about the present design and the measures

- **Measured or modelled.** Every trial figure is from an Apple M5, with interrupts and TLB invalidation modelled (`ipi` 0 or 1 µs, `tlb` 100 ns: M5:51-52). Rows with k = 8 ran about half on efficiency cores and are low trust (M5:335-336, M5:882-883). Nothing beyond 8 cores was measured, so every 64-core statement in the report, for any shape, is extrapolation.
- **Which candidate is which.** The report labels "candidate 1, first settings" as Shape A and "candidate 1, fair settings" as Shape D (H:239-244). The fair settings are the trial's switches: a cheaper copy and derives that do not wait for remote copies (M5:317-331). Nothing in them is specific to D. A repaired A gets the same numbers, so the table shows no D-over-A gain.
- **What the report leaves out of its comparison:**
  - C wins capability changes by 2.3 to 11 times lower p50 (M5:402).
  - C wins all-initiator unmaps by 1.55 to 2.0 times (M5:1060).
  - C's lookups are level at the p50 once reads are lock-free (M5:398, M5:401).

  The report's verdict that C "loses on common-path lookups, IPC, and signals" (H:18) keeps the two rows where candidate 1 leads by 2 to 8 % and drops the rows where C leads by large factors. Its own risk 4 (H:264) admits the unmap gap.
- **P1.** The present contract already makes a frame "a run of 1 to *E* physical pages" (ki:27), with *E* = 512 (ki:87). So the grant explosion appears only when the heap is mapped in 4 KiB pages: 2,048 frames of 2 MiB each. The other report states that condition correctly (kernel-shape-opus.md:28, read for point 4). Run-grants therefore add something only for 4 KiB-page heaps. That case is real (a JIT or a GC needs 4 KiB protection), but the report never says it.

## 2. Claims about other systems and hardware

- **Opened at source:**
  - The 14600KF core counts ([Intel ARK](https://www.intel.com/content/www/us/en/products/sku/236778/specifications.html), [Memory Express](https://www.memoryexpress.com/Products/MX00127137)).
  - INIT blocked in VMX root ([SDM Vol. 3C mirror](https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-1207.html)).
  - Linux commit `e1c467e69040` ("Wake up CPU0 via NMI instead of INIT, SIPI, SIPI", because INIT makes the BSP run "the BIOS boot-strap code"; read with `gh api repos/torvalds/linux/commits/e1c467e69040`).
  - `sbi_hart_stop` stops "the calling hart" ([RISC-V SBI HSM](https://docs.riscv.org/reference/sbi/v3.0/ext-hsm.html)).
  - Idle exit latencies: `drivers/idle/intel_idle.c`, `adl_cstates`, read with `gh api`, lists C6 220 µs, C8 280 µs and C10 680 µs. Raptor Lake is absent from the match table, so the 14600KF uses firmware `_CST` values, which are unknown here.
- **Not opened by me:** SDEI, PSCI and the Arm TLBI point. The report took them from `fencing-without-cooperation.md` and the reviews.
- **SMM (H:104).** The report says an E-core "stalling in SMM never holds a spinlock needed by a P-core". From memory, not verified: SMIs are usually broadcast to every core, so per-core kernels would stall together too.

## 3. The mechanisms, attacked

### 3.1 Run-grants (one grant over contiguous chunks)

**What the gate checks per mapping.** G3 (ki:887) already accepts a leaf when "a live grant to this node covers it". With run-grants, the grantee P installs leaves into H's chunks without a frame capability on its side. So:

- the per-mapping record of ki:245 is gone;
- the owner's per-chunk map count (G4) no longer counts remote leaves, because P cannot write H's gate words;
- P counts only one `map_count` per grant in its use entry (H:188);
- P's gate must also find the covering grant among `GRANTS` use entries per leaf. The report gives no index for that search.

**Safety holds** in my model (`M1 check=use` and `check=state`: no chunk given away is still mapped). The reason is that P answers `done` and drops its use entry in one kernel event.

**Liveness breaks as written.** The report has "Grant: Live → Revoking (*granter* gate refuses new mappings)" (H:173). But P's gate installs P's leaves. If P checks only its own use entry:

1. H calls `cap_revoke`; the grant becomes *revoking*; H sends `Revoke`.
2. P removes up to 32 leaves and answers `RevokeStep(done = false)`.
3. A thread of P touches a page in the run. P's gate sees its use entry and reinstalls the leaf.
4. Steps 2 and 3 repeat. H's caller gets `again` for ever.

The explorer finds this cycle (`M1 livelock check=use: VIOLATION`). It disappears when P's gate also reads H's grant word and refuses unless it is *live* (`check=state: holds`). The report must state that check, at the grantee's gate.

**Partial revocation.** D-Inv1 makes `memory_give` refuse any chunk covered by a live run (H:197). Since H cannot tell which chunks of a run P maps, freeing or giving one 2 MiB chunk in the middle of a 1 GiB run means:

- revoking the whole run on every peer: 512 chunks, in steps of 32, so 16 steps per peer and 240 rounds for 15 peers;
- writing two new grants per peer;
- every peer re-faulting what it used.

Heaps free in the middle. Under alternating holes a 4 GiB heap is 1,024 runs per peer, so 15,360 grants, more than 4,096. At full fragmentation the table fills at 4 peers. Run-grants move the P1 ceiling; they do not remove it.

**Re-delegation.** D removes `TransferAsk` (H:181), and only the granting node's gate can write a grant. So a node that received a buffer cannot pass it on: for example a file service handing a client's buffer to a block driver. The report does not mention this loss of zero-copy forwarding.

### 3.2 Lazy `aspace_map` resolved by a minor fault on the other core

**Who answers.** Either P reads H's page tables directly, or P sends `AspaceFetch` and H answers `AspaceSupply` (H:61, H:181).

- The direct read needs H's kernel table pages mapped read-only in P. G3 point 3 (ki:887) forbids any leaf to a table page outside the gate's own view, so that variant needs a gate change.
- The message variant is a blocking wait on another node. The report says D removes those ("no cross-core synchronous wait", H:128), but it keeps three: fetch, `AspaceInvalidate` and `UnitRequest`.

**Unmap racing a lazy fault: BROKEN as written.** H:181 puts `AspaceSupply` on "the fixed per-node fault ring", a ring separate from the one that carries `AspaceInvalidate`. The explorer (`M2 ring=fault`) finds, in 6 steps:

1. P faults and sends `AspaceFetch`.
2. H answers `AspaceSupply(pte = frame f)` on the fault ring.
3. H's `aspace_unmap` clears the entry and sends `AspaceInvalidate`.
4. P applies the invalidate (it has no copy yet) and acks.
5. H gets the ack, the unmap returns, and f is freed and reused.
6. P takes the `AspaceSupply` and installs f.

P now maps memory that has been given to someone else: D-Inv3 and the memory-ownership invariant both fail. The race holds if Supply shares the FIFO ring with Invalidate (`ring=same`). It also holds if P drops a Supply older than the last invalidate seq it applied (`ring=fault seq`). The report already numbers its invalidates with `seq` but never compares it on Supply.

**Home death.** R0 ends the fetch with `gone`. R2 destroys the copy, and the process is lost with its home anyway (k:48). That is sound.

**Cost.** The cost is not measured anywhere: M5 has no fault-driven adds (M5:321-324). From the trial's own model, a fetch costs at least one `ipi` round trip plus a trap per page per peer. A shared heap touched by every thread pays up to 2,048 × 15 faults, where an eager map sends batched messages without waiting (the trial's switch 2). Lazy wins only for pages most peers never touch, which a malloc or GC heap is not.

**Shrink.** If a peer sleeps with its active bit set, every unmap waits for it to leave deep idle: up to 680 µs on the Alder Lake table. The report does not say when a peer clears its bit.

### 3.3 Stateless signal grants, checked by (generation, serial)

- **Authority.** `NotifyGenTable` lives in slot 13, which "every kernel reads" (D-115 point 1; H:189 says any sender verifies "locally with one read"). A token is (node, gen, notify_id, serial, badge) and the receiver keeps no record of holders. So any kernel can build a valid token for any notify of any node, with any badge. Today a remote capability is backed by a grant entry that the owner wrote, which names the grantee and its generation (ki:833), and the badge comes from the owner's anchor. D drops that.

  User code cannot forge a token, since tokens live in kernel slots. But the fault model is a buggy kernel, and a buggy kernel can now wake any notify and impersonate any client's badge. Note that the present rule for calls (ki:855) also does not list a grantee check, so the present design is less strict than its table suggests (a suspicion, not tested).
- **Selectivity.** One serial per notify means a revoke invalidates every holder. Revoking one client means bumping the serial and re-sending tokens to all the others, each as a stamped send. The derivation tree's selective revoke is lost. So the "0 messages" claim (H:74) holds only for revoke-all.
- **A signal in flight** with an old serial is dropped at delivery (D-Inv2). That is sound, and fire-and-forget.
- **Serial wrap.** The serial is 32 bits, and a bump is one local call. 2³² bumps take 72 minutes at 1 µs and 14 minutes at 0.2 µs, after which an old token is accepted again. Across objects this needs control of slot reuse (a suspicion). The present grant serial is 30 bits and grows at each reuse (ki:833-834), with no stated wrap rule either. That gap is shared, but it is faster to reach in D because a bump costs no message.
- **What the receiver must keep:** `NOTIFY_SLOTS` per node (1,024 in the example), which is a new table that fills. The report names no quota, so one process can exhaust the slots of its node.

### 3.4 What crosses, counted

- **H:163 says "only 9".** Its table and its note need:
  - `StampedSend`, `StatelessSignal`, `Revoke`, `RevokeStep`, `Release`, `AspaceInvalidate`, `AspaceAck`, `UnitRequest`, `UnitAnswer`, `Handed`, `Ping` (11);
  - `AspaceFetch`, `AspaceSupply`, `AspaceJoin`, `AspaceLeave` (H:63, H:181), bringing the total to 15.
- **Inline grants.** H:73 says `Device` capabilities cross, but the inline grant type has only run-grants and signal tokens (H:171).
- **Ring memory.** The report never sizes its own rings: per-pair credit, 64 slots, 64 words inline plus 4 grants. At about 600 bytes a slot and N² pairs, that is about 150 MiB at 64 cores and 37.5 GiB at `NODES_MAX` = 1,024 (my estimate). Against that, it claims to save 64 MiB of proxies.

### 3.5 Idle cores that hand their roles and sleep in place

- **Who wakes a sleeping core:** any message's interrupt, its own timer, or a device interrupt (ki:595).
- **How long a wake takes:** hundreds of µs from deep states (section 2). Everyone that needs the sleeping core's objects pays that: the home of a process, a peer in an unmap, a holder of a grant being revoked.
- **What it does not do.** Sleeping in place keeps one kernel per core, all the time. "The number of kernels following the demand" is not served, and neither is "several cores under one kernel": D rejects both owner wishes and argues they are not needed. The report should say so plainly.
- **It works for C too.** Sleeping in place applies to C just as well: a core of a several-core kernel can `MWAIT` with nothing to detach. So H:98 ("C must run a cross-core detach protocol every time a core goes idle") is wrong.

## 4. The case against the other shapes

- **Threads.** wasm-abi:128 says Wasm parallelism goes through instances, "which suits one kernel per core", and that native Ladybird and inference "need real threads from the start". So the 16-thread process is central from day one, for the web engine (web.md:13-33) and for local inference (agent.md:11, llama.cpp).
  - The argument also cuts against D. If such processes were rare, D's lazy aspace and run-grants would be machinery for a rare case, and B would do.
  - If they are central, D gives them the protocol k:55 calls "the hardest point of the project", and C gives them one address space inside one kernel.
- **Unit of failure.** C's group dies whole (k:44): CONFIRMED and real. But D's 16-thread process also dies with its home (k:48). The difference is only for the other processes that share C's cores.
- **The 2-core argument (H:108)** assumes C merges both cores. C as briefed keeps cores "apart as the safety net" (k:57), so on 2 cores it stays two kernels, which is D.
- **Bounded operations (D-042).** Nothing shows that C breaks it: revocation is already stepwise with `again` (ki:842-843), and a step can hold a lock for a bounded time. What is open is the lock order (M5:975-977). D keeps sequential kernels. But its run revocation takes time proportional to the run, not to the mappings, and its lazy faults add waits on other nodes.
- **Proofs.** D keeps the one-core gate proof (gate-page-tables.md:601), but adds range-covered grants and gate-written notify generations, which are not in P_gate (:571-581). C needs concurrent reasoning that is still unfinished (:602).
- **P and E cores.** scheduling.md:95 already keeps a group to one core type by default, so "C cannot grow a process across P+E" (H:105) is equally true of A and of D's default.
- **64 cores.** No shape was measured beyond 8. D's O(N²) rings (section 3.4) offset its proxy savings.
- **Replacement (case 7).** Replacing the home of a 16-thread process stalls the whole process in D too: its faults and unmaps wait on the sealed home.
- **Supervisor (case 8).** Anti-affinity of replicas is a placement rule every shape needs (k:49). It does not show that elasticity fails.

## 5. What it would cost against the present contract and model

**What survives:** the rules other than rule 7; the objects; G1-G11 and G13-G14; detection, the fence, R0-R6, roles, start-up; the per-pair FIFO and uniform sender check (which the reviews ask for anyway); stamped send; frame grants.

**What goes:** rule 7 (ki:847-860), the proxies, the transfer rules, `thread_move`, `Carry`, and D-108 parking.

**What must be written new:**

- the grantee-side checks of run-grants and their indexing;
- the TLB hook rewritten for lazy adds (ki:318, ki:320), with the seq check of section 3.2;
- the notify-generation table and its quota;
- user-level RPC across cores, plus a user-level move of threads that cannot carry endpoint capabilities (only frames, notifies and devices cross: H:73);
- the three models, none written.

In the model, 11 of 18 `Body` variants go and at least 8 new ones arrive. `remote.rs` and the parts of `system.rs` and `roles.rs` that touch proxies and parking are rewritten. The tests at `nodes.rs:643` and `:1048` and `recovery.rs:971` must be rewritten for FIFO (verify-opus-by-hydrogen:107).

## 6. What it missed, and a combination

**What it missed:**

- the frame is already a run (ki:27), which undercuts its headline mechanism;
- the grantee-side refusal for run-grants;
- the Supply/Invalidate ordering;
- the authority hole of stateless tokens;
- re-delegation;
- its own ring sizes;
- deep-idle exit latency;
- that sleeping in place helps C as much as D.

**A combination that beats both reports' extremes:**

- **Build first:** one-core kernels with the pruned boundary. That means stamped send with credits, a non-blocking remote signal checked against an owner-written grant (not a stateless token), frame grants, and roles with a fixed mailbox outside any proxy pool. This is B, and the other report calls it "a sound first stage" (kernel-shape-opus.md:29).
- **Add later, behind its model:** kernels of several cores for multithreaded native processes, instead of D's lazy cross-kernel aspace. That keeps one address space inside one kernel and leaves the gate's concurrency to a later, separately proved step.
- **Worth keeping from D:** credit-bounded sends, the role mailbox, and sleeping in place.

## Judgement

1. I would not build shape D as written.
2. Of its three mechanisms, the lazy map is unsafe on its stated ring layout, and run-grants livelock as worded. Both are fixable, but neither is modelled.
3. Stateless signals trade the owner-written grant for a public serial. That is a loss of authority between kernels that a per-core design does not need.
4. Its case against C relies on first-series lock rows and on the M5:96/103 attribution, both read unfairly, and on a WASI line whose second half contradicts it.
5. It serves neither of the owner's two wishes. It says they are unnecessary, without data.
6. What it gets right: the reduced boundary, FIFO rings with credits, the role mailbox, no co-hosting, and sleeping in place.
7. Before choosing, measure on the 14600KF the lock-free per-core boundary (B) against a 2-to-6-core kernel with lock-free slot reads, using call and map rates traced from Ladybird and llama.cpp.
8. Measure fault-driven adds against eager non-waiting adds on a shared heap touched by every thread, and deep-idle exit latency on P and E cores.
9. Model first: run-grant revocation with grantee faults, and fetch/invalidate ordering across two rings, both with crashes.
10. Explorer: `/tmp/xshape-opus/explore.py`. Each property fails on its broken variant, and the script's assertions catch a flip.
