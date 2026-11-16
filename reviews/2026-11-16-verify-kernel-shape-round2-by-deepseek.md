# C\*, second round: verification of the rules, the explorer, the hardware and the staging

**Date:** 16 November 2026. **Reviewer:** deepseek, as the second independent hand.
**Brief:** `scratchpad/pass14/XSHAPE2.md`.
**Under review:** the second round of the kernel-shape proposal, `Docs/research/drafts/kernel-shape-opus.md` §9 (lines 480-670), and the state explorer it ships, `Docs/research/drafts/kernel-shape-explorer.py`.
**Bases.** The proposal is cited by its own lines (`opus:516` = R-1). The contract is cited as `p14:NNN` = `Docs/architecture/kernel-interface.md` at the Docs HEAD of this session, `b501b32`; the proposal's own `p14:` citations were made at `b15f37c`/`ede3b38` and their line numbers have moved, so every contract citation below was re-read at this HEAD.
**Prior review:** `Docs/reviews/2026-11-16-verify-kernel-shape-opus-by-hydrogen.md`.

**Method, and its limits.** Every number below was produced in this session: Python 3, `-B`, each run under `timeout`, in `/tmp/xshape2-deepseek/`, which holds `author.py` (a verbatim copy of the delivered explorer), `refine.py` (my refined copy, with three new scenarios), and `refs/` (the three hardware documents). Nothing under the repository was changed except this file; nothing was committed. The hardware statements are quoted from the documents I fetched, named with version or order number and section; where I could not check a figure I say so. The exploration is exhaustive breadth-first over my model, so "holds" below means "no reachable state of *this* model violates it", not "proved".

---

## Verdicts

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | The delivered explorer reproduces the author's own results | **CONFIRMED** | `moves:correct` 601,259 states, 2,250,433 transitions, 33.6 s (author 26 s); `shootdown:correct` 331,860 / 1,363,487, 19.9 s; `seal:correct` 66,352 / 335,807, 1.4 s; `credits:correct` 1,050 / 5,005, 0.1 s |
| 2 | Every variant the author reports as failing does fail, in the steps reported | **CONFIRMED** | `r6_inflight` P7 in 13, `take_any_class` P6 in 4, `role_at_read` P6 in 10, `no_mark` P7 in 7, `giver_live_only` P7 in 7 |
| 3 | The properties are not vacuous | **CONFIRMED**, with two gaps | Each is refuted by a deliberately broken variant (§2.7); P1 and "no settle" are unreachable in my configuration, and the barrier's `ack` is only half-exercised |
| 4 | R-1's confirmation is sound | **REAL FAULT**: sound only if the park request is renewed *before* the word leaves *owned*, an order no rule states | `mv2s:word_then_request`, P2 in 11 steps; trace in §2.2 |
| 5 | A take may write the generation it read | **REAL FAULT**: unstated, load-bearing across a restart | `mv2s:gen_from_read`, P10 in 16 steps; trace in §2.3 |
| 6 | R-2's "confirmed, and `SETTLE_NS` after the last stop" | **CONFIRMED** load-bearing | `mv2s:r6_inflight` P7 in 20 steps |
| 7 | R-5's class rule covers the hand-over | **REAL FAULT** (in the contract, not only the proposal): the check examines the core the call runs on, not the taker's cores | `role:single_core` P6 in 2 steps; trace in §2.4 |
| 8 | A core can be lost and the machine goes on | **REAL GAP**: the bootstrap core, once its kernel dies, is free and untakeable for the rest of the boot | `mv2s:probe_bsplost`, 7 steps; §2.5 |
| 9 | A core is taken only after the previous kernel's code has stopped | **ARTEFACT** of the split, harmless, but invariant 1 is worded too strongly | `mv2s:probe_stub_take`, 5 steps; §2.6 |
| 10 | The reclaim barrier holds with three failures and four kernels | **HOLDS** | `barrier:correct` 58,227 states / 230,619 transitions, 2.6 s; `ack_all_live` REUSE in 8, `ack_no_clear` in 7, `reuse_early` in 3 |
| 11 | "A kernel message never waits for a user message" (R-13) | **FALSE as worded** with one FIFO ring per ordered pair | Argued in §2.8; not modelled by either explorer |
| 12 | On x86-64 "INIT is held while a core is in SMM" (p14:1089) | **NOT SUPPORTED** by the SDM | §3.2: the SDM says *inhibited*, and documents a pending NMI but no pending INIT |
| 13 | The bootstrap core can be confirmed parked (p14:1092) | **NOT AS WRITTEN**: the NMI handler writes no epoch, and the time-based fallback excludes the bootstrap core | §3.2; the cheapest fix in the document |
| 14 | §9.4's stage-1 list is complete | **NO**: eight areas missing or thin | §4.1-4.2 |
| 15 | Stage 1 pays nothing on the one-core hot path | **NO** for four items | §4.3 |
| 16 | The staged plan is sound | **YES, with three one-clause edits** | §5 |

---

## 1. The rules of §9.2, and where the explorer models them

### 1.1 What the model is

The delivered explorer is five scenarios: `moves` (three kernels A, B, C over four cores; A owns one frame F; cores of fence class *forced* and *signalled*; two deaths), `shootdown`, `seal`, `credits`, and `full` (moves with the frame, two accusations, about six minutes). Each state is a tuple of words: per core the core word (state, kernel, mark), what the core executes, its entry-stub phase, a pending start request, the park confirmation and whether one was ever written, a fence signal in flight, the TLB tag of F, a pending shootdown, and a take in progress; per kernel a member state; plus the frame's owner and mappings (`author.py:173-205`). A step is one transition of one or a few words.

Every property is stated at `opus:562-571`.

What the model abstracts, in the terms the brief asks for:

- **Atomic steps.** A fence is three steps (accuse, mark, send) and a fourth (the stop lands); a take is one step (read, check, commit); a park is one step; a kernel's R6 is one step that clears the words and writes dead. So the model cannot see any order *inside* those steps. §2 splits them, and two of the four real faults found live exactly there.
- **Impossible failures.** A sent stop always lands; a core always halts; no stop is lost, duplicated or deferred; a marked word is never rewritten; the park stub always writes its confirmation. Real hardware fails on all five (§3).
- **Counts.** Three kernels, four cores, two deaths, one frame, fence class per core, no kernel restart in `moves` (generations exist only in `seal`), no more than one unit role in play.
- **Kernel restarts.** `moves` has none: a kernel dies and stays dead. `seal` has resume, but its core moves are atomic, so a restart is never interleaved with a take. My refinement gives kernels a generation and one restart, which is what produced the second fault, §2.3.
- **Time.** `SETTLE_NS` becomes "no stop in flight"; `SEAL_NS` is one step; `STALE_NS`, `NMI_GRACE_NS`, `FENCE_NS` do not appear. Nothing is measured in time, and the proposal's own bound rules (R-6) cannot be checked here at all.
- **Memory.** One frame, one mapping bit, no ownership words, no gate, no capabilities. Memory-side rules (R0–R6, the barrier) appear only as the four words the barrier scenario needs.

### 1.2 Rule by rule

| Rule | Where modelled | What the model turns it into | Verdict on the modelling |
|---|---|---|---|
| **R-1** park request (`opus:516`) | `moves`: a request counter per core, `parked` compared with it; variants `stale_parked`, `no_request` | equality of two counters | Modelled as written, including the per-architecture evidence collapsed to one equality. The *order* the rule needs is absent — §2.2 |
| **R-2** fence mark (`opus:517`) | `moves`: `mark` bit, CAS by the fence, takes refuse a marked word, R6 refuses a marked word; `no_mark`, `giver_live_only`, `r6_inflight` | a boolean per core | Modelled; "confirmed stopped and `SETTLE_NS` after the last stop" becomes "no signal in flight". Both halves are load-bearing (`r6_inflight` fails in 20 steps without the second) |
| **R-3** entry stub (`opus:518`) | `moves`: the stub phase (masked/unmasked) and the power-off when the word no longer reads joining | one step in the stub | Partly: "a stop lost while masked is sent again" is not modelled — the fence never loses a stop, so the *repetition* clause is untested |
| **R-4** cores that never move (`opus:519`) | `moves`: class-0 cores absent, the bootstrap core by number; `bsp_moves` | a constant per core | Modelled for the bootstrap core; the class-0 case has no instance, and the firmware requirement on `fence_hart` is unmodelled. The rule's hole is §2.5 |
| **R-5** class at the commit (`opus:520`) | `moves`: a re-read of the role at the take; `take_any_class`, `role_at_read` | one role word, one class per core | First sentence modelled at the take. The second sentence (the new holder gives away weaker-class cores) is **not modelled**; §2.4 shows why it matters |
| **R-6** bounds with a lock (`opus:521`) | nowhere | — | Not modelled at all, and not checkable by exploration |
| **R-7** idle kernels (`opus:522`) | `seal`: a kernel with no cores, sleeping in place | a state | Modelled |
| **R-8** `SEAL_NS` (`opus:523`) | `seal`: accusation by seal after one step; `no_seal_timeout` | `SEAL_NS` = one step | Modelled as a step, as the author says |
| **R-9** resume (`opus:524`) | `seal`: resume takes the number of admitted contexts; `resume_any` | a constant per kernel | The *count* is modelled; admission as a bandwidth sum is not |
| **R-10** rebuild (`opus:525`) | `seal`: `rebuild_live_only` | live memory as a predicate | Modelled |
| **R-11** sealed vectors (`opus:526`) | nowhere | — | Not modelled (the author says so) |
| **R-12** retirement (`opus:527`) | `seal`: `retire_then_give` | steps | Modelled |
| **R-13** two credit classes (`opus:528`) | `credits`: two pools, the kernel class never used by a user thread; `shared_credit` | counters, not positions | Modelled as *credits*; the sentence "a kernel message never waits for a user message" is not modelled and is false with one FIFO ring (§2.8) |
| **R-14** generations of the counters (`opus:529`) | `credits`: `no_gen_reset`, `no_purge` | generation tags on counts | Modelled |
| **R-15** shootdown (`opus:530`) | `shootdown`: `park_no_ack` fails, `acks_wait_only` holds | per-core acknowledgement word | Modelled |
| **R-16** `core_give` (`opus:531`) | `moves`: a give is "write leaving" and a park | one step | Only the words are modelled. The retarget of vectors and the unit holder's answer as kernel work are **not modelled**, and R-16's step list is where the first fault's missing clause belongs (§2.2) |

### 1.3 Rules, or clauses of rules, the explorer does not model at all

1. R-6, entirely: the lock, the (*k* − 1) terms, "no kernel lock is held across a wait".
2. R-11, entirely: masked and unmasked vectors of a sealing kernel.
3. R-13's ordering claim; R-14's counters are modelled but not their *classes* on the wire.
4. R-16's retarget and holder answer; only its two words are modelled.
5. R-5's second sentence, and any check over a *set* of cores.
6. R-3's repetition of a lost stop, and the SDEI unmask.
7. R-1's per-architecture evidence: three different hardware facts are one equality.
8. R-9's admission sums; R-7's idle table.
9. Every rule about *memory* (R0–R6, the barrier except in my `barrier` scenario) and every rule about *messages* except credits.
10. The write skew between the role word and the core word, which the author lists at `opus:581` and which cannot be closed by one compare-and-swap on two words (a suspicion, stated as one: the fix is a single gate call that checks and writes both, which no rule states).
11. Anything with a duration: `FENCE_NS`, `SETTLE_NS`, `STALE_NS`, `SEAL_NS`, R-6's bound.

---

## 2. Breaking it

### 2.1 The refinement I built

`refine.py` keeps the author's engine and adds three scenarios. `mv2`/`mv2s` refines `moves`: 13 fields per core (word state, kernel, generation, mark, executing kernel, entry phase, start request, park request, confirmation, ever-confirmed, stop in flight, take in progress, the tuple read by a take); the fence split into mark / new park request / cancel start / send stop / confirm; a take split into a read and a compare-and-swap on all four fields read; a park split into "enters the stub" / "writes its confirmation" / "halts"; a start split into "entry stub" / "enter or power off"; a give renews the park request before writing *leaving* (in `correct`); R6 split into "clear the words" then "dead". Kernels carry a generation and may be restarted once; cores in either stub belong to no kernel, so P2 says nothing about them. Configuration `mv2s`: two kernels, three cores, the bootstrap core 2, two deaths — small enough for exhaustive breadth-first search in Python. `role` models the R-5 skew with two kernels (A owns cores 0 and 1, of which core 1 is class 1; B owns core 2) and one unit role. `barrier` models four kernels, `maps_of` bits, `acked` words, one frame F of A, and three accusations.

`mv2s:correct` holds: **440,963 states, 1,357,055 transitions, 22.8 s**, every state reaching a quiet state. So the refinement is not vacuous by construction.

### 2.2 Fault 1 — the park request must be renewed before the word leaves *owned* (real)

```
mv2s:word_then_request: VIOLATION after 11 steps:
  P2: core 0 runs A but its word no longer names it (3, 2, 0, mark 0)
  1. A gives core 0 (the word becomes leaving)
  2. core 0 enters the park stub
  3. core 0 writes its park confirmation
  4. core 0 halts
  5. A reads core 0 (leaving) to take
  6. A takes core 0 (word joining, start request)
  7. core 0 starts in A's entry stub
  8. core 0 reads its word and enters A
  9. A gives core 0 (the word becomes leaving)
 10. B reads core 0 (leaving) to take
 11. B takes core 0 (word joining, start request)
```

R-1 says "each park ... **first** writes a new value of that core's park request" (`opus:516`). R-16's list of steps for a give is "retarget the vectors, wait for the unit holder's answer as kernel work rather than as a thread's wait, write *leaving*, park" (`opus:531`) — no renewal of the request anywhere. Between the write of *leaving* and the park, a taker that sees *leaving* compares `parked` with the request as it stands, and the request still answers the *previous* park. Step 11 above is a taker committing to a core that is executing the giver's code at that instant: a real escape from the fence, not a refinement artefact.

Fix, one clause: "a give, and a fence, write the new park request before they write *leaving* or mark the word, and a take requires the confirmation to answer a request written after the word left *owned*." The counter is already in the layout (§9.4 item 2), so nothing else moves.

### 2.3 Fault 2 — a take must write the taker's current generation (real, unstated)

```
mv2s:gen_from_read: VIOLATION after 16 steps:
  P10: core 0 names B generation 0, slot live at generation 1
  ...
  9. fence B confirmed: every core it names is stopped
 10. R6 for B, step 1: the words naming it cleared
 11. R6 for B, step 2: B dead
 12. supervisor starts B fresh on free core 2
 13. core 2 starts in B's entry stub
 14. core 2 reads its word and enters B
 15. B reads core 0 (leaving) to take
 16. B takes core 0 (word joining, start request)
```

The core word's bits 32-63 carry the kernel's generation (§9.4 item 1). If the take writes the generation it read from B's slot before its compare-and-swap, and B is restarted in between (which R-9 and the contract's "a supervisor may start *X* again before *Y* has seen it dead", p14:1112, both allow), the core names a generation that is no longer live. P2 still holds textually — the word names B — but the fence's *scope* is "the cores whose word names that kernel and carries the mark" (R-2), and R6 clears words of the current generation, so this core is attributable to no fence and cleared by no reclaim. Real, and unstated in §4.2 and §9.2; the fix is a sentence: "the gate writes the generation the taker holds at the compare-and-swap, and the compare-and-swap fails if the slot's generation changed since the read."

### 2.4 Fault 3 — the class rule checks one core, not the taker's cores (real, and in the contract)

```
role:single_core: VIOLATION after 2 steps:
  P6: A holds the unit role and owns core 1 of fence class 1 (its cores [0, 1])
  1. B hands the unit role to A: the word becomes handing
  2. A becomes the holder
```

`role:correct` — which checks every core of the kernel concerned — holds in 5 states; `role:no_check` fails in 2 steps like `single_core`. The contract's role word carries a *node* in bits 2-17 and no cores at all (p14:1211), and the class rule is policy in the proposal — "unit roles go to kernels whose cores are all of the best class" (`opus:197`) — so a class check at a hand-over must read that node's array of cores, and no rule says it does; my `single_core` variant models the check as the hand-over's word write, which examines the node the call runs on. R-5's second sentence ("a new holder, after it writes held and before it maps the unit, gives away any core of a weaker class", `opus:520`) is a *promise with a window*: becoming holder while owning a class-1 core is reachable, and only then does the give happen, which itself needs a park. If the weak core is unfenceable (the class exists because its stop cannot be trusted), the unit's registers stay reachable from it for as long as the fence cannot confirm the stop — the condition the class rule exists to keep out (p14:1099, p14:1898). Real fault; the fix is that both commits — the hand-over and the take — must check the taker's whole core set, which is one condition on a set that the node block already holds (§9.4 item 6, the cores array).

The *skew* proper (a claim landing between a take's re-read and its compare-and-swap) cannot be closed by a compare-and-swap on two words. Two gate calls of the same kernel are serialised by the kernel lock, so it is not reachable between two calls; I state it as a suspicion, not a finding, and it needs a single gate call that checks the role and writes the word, which no rule states.

### 2.5 Gap — the bootstrap core is lost when its kernel dies (real)

```
mv2s:probe_bsplost: VIOLATION after 7 steps:
  PROBE: the bootstrap core 2 reads free and, by R-4, no kernel may take it
  1. accuse B
  2. fence B marks core 2 (one CAS on the word)
  3. fence B sends its stop to core 2
  4. stop of B lands on core 2
  5. core 2 halts
  6. fence B confirmed: every core it names is stopped
  7. R6 for B, step 1: the words naming it cleared
```

R-4 says the bootstrap core "is never given or taken: the gate refuses *leaving* and *joining* on their words after machine start-up" (`opus:519`). A fresh start on a *free* core writes *joining*, so once R6 frees the bootstrap core no kernel may ever start there: the machine runs one core short for the rest of the boot, permanently. This is a consequence of a rule that exists for a good reason (on x86-64 an INIT returns the bootstrap processor to firmware, p14:1089, step 2, and the SDM says why: §3.2), but it is stated nowhere in §9.4 or in D-117. Fix: state it, and either exempt a *fresh* start on a free bootstrap core (which reintroduces the INIT hazard) or declare the bootstrap core lost with its first kernel and let the boot image place its most durable kernel there.

### 2.6 Artefact — a take may commit while the core is still in the park stub (not a fault)

```
mv2s:probe_stub_take: VIOLATION after 5 steps:
  PROBE: A takes core 0 while it is still in the park stub, executing the previous kernel's code
  1. A gives core 0 (the word becomes leaving)
  2. core 0 enters the park stub
  3. core 0 writes its park confirmation
  4. A reads core 0 (leaving) to take
  5. A takes core 0 (word joining, start request)
```

An artefact of splitting "writes its confirmation" from "halts": the take is allowed at step 5, between the stub's two steps, and the stub is executing the *previous* kernel's kept code. It is harmless — the stub touches only its own beacon and the machine keeps it at a fixed vector (p14:1091, step 4) — but it does contradict the shape's invariant 1 ("a core given away has stopped", opus §4) as worded, and R-3/R-1 must say that the stub's late write cannot equal a later park request. R-1's equality plus a counter wide enough never to wrap does that; saying so costs one clause.

### 2.7 The rest of the refutation run, and the vacuity checks

| Variant | Result | What it shows |
|---|---|---|
| `mv2s:no_request` | P2 in 11 steps | as `word_then_request`: no request, no safety |
| `mv2s:stale_parked` | P2 in 12 steps | any park ever confirmed is not enough (the author's finding, reproduced at finer grain) |
| `mv2s:no_mark` | P7 in 8 steps | a stop lands on a core B now runs: the verifier's Test 4 race |
| `mv2s:r6_inflight` | P7 in 20 steps | R6 clearing words while a stop is in flight: the second half of R-2 is load-bearing |
| `mv2s:free_early` | P2 in 1 step | a taker reading only the word takes a running core |
| `mv2s:bsp_moves` | P8 in 9 steps | the bootstrap core moves |
| `mv2s:no_dead_step` | P10 in 7 steps | P10 is not vacuous: writing dead before clearing the words is caught |
| `role:single_core`, `role:no_check` | P6 in 2 steps | P6 is not vacuous |
| `barrier:reuse_early` | REUSE in 3 steps | P4 is not vacuous |
| `barrier:ack_all_live` | REUSE in 8 steps | the contract's *fencing*, *fenced* rows (p14:1128-1129) are load-bearing: a fencing node that is skipped lets F be reused |
| `barrier:ack_no_clear` | REUSE in 7 steps | an acknowledgement without clearing the `maps_of` bit is not an acknowledgement |
| `mv2s:no_settle` | **holds** | a live kernel can still take a *leaving* core in my model; reported as a property my refinement does not exercise, not as a finding |
| `mv2s:start_while_running` | **holds** | P1 is unreachable in this configuration (nothing starts a core whose word it does not own); a limitation of the size, not a result |
| `barrier:bit_only` | **holds** | my barrier cannot distinguish "the bit is clear" from "the translations are gone", so R5's `acked` is only half-exercised — as in the author's model |

### 2.8 Two things neither explorer can see

- **R-13 as worded is false.** With one ring per ordered pair of kernels (p14:§credits, and R-13's "the ring of each ordered pair of kernels has two classes of credits"), a user message already ahead in the ring delays the kernel message behind it. Two credit classes bound how much a user thread can *consume*; they do not remove head-of-line blocking. The honest claim is "a kernel message never waits for a *credit*", or the design needs two rings per pair. This is a wording fault with a real cost, and it is invisible to a model that counts credits rather than positions.
- **R-6's bound has a term the explorer never sees:** the wait for another core's acknowledgement, which R-6 forbids under the lock. My `barrier` and `shootdown` models both have that wait as a *step*, i.e. as a state, which is the shape R-6 asks for; that the shape is possible is a weak confirmation that the rule is implementable.

---

## 3. Hardware: is "a core is taken only once confirmed parked" implementable, and how long

### 3.1 ARM64 — PSCI

Arm DEN 0022E (PSCI, issue E):

- §5.7.1: *OFF* means "all the cores in the affinity instance have called `CPU_OFF` and each of these calls has been processed by the PSCI implementation"; *ON_PENDING* is a separate state, and *DISABLED* exists for faulty cores.
- §5.7.2: "callers must be aware that the state returned by the `AFFINITY_INFO` call is affected by calls to `CPU_ON` and `CPU_OFF`, both of which could be in flight at the same time."
- §5.5.1: "the call is not expected to return"; "a core can only power itself down."
- §5.5.2: "the calling OS must have migrated all threads and interrupts away from the core that is being powered down. Asynchronous wakeups on a core that has been switched off through a PSCI `CPU_OFF` call result in an erroneous state"; "`CPU_OFF` can have varying latency ... the caller must not make any assumptions about latency."
- §6.6: *OFF* also covers "the core has not been booted yet. The core is not available for computation."

So: **implementable for a core that can still run code** — the party on the core calls `CPU_OFF` (from a SDEI event-0 handler for a forced park), the taker polls `AFFINITY_INFO` until *OFF*. Three caveats, all cited: *OFF* does not prove *this* request parked the core (§6.6: never booted reads *OFF* too), which is exactly why R-1's epoch pairing is needed and why the contract's "`AFFINITY_INFO` returns OFF **after** the request" (p14:1092) is the right formulation; *ON_PENDING* must be treated as running by a taker; and the latency has **no bound** — the contract's `FENCE_NS` of 10 ms (p14:1242) is a policy with no firmware guarantee behind it. A core that has stopped executing (hung, or in a secure world that returns `DENIED`) never calls `CPU_OFF` and is never confirmed: it stays unfenced, which the contract already admits for class 0 (p14:1033).

### 3.2 x86-64 — INIT and SIPI

Intel SDM, order 325384, December 2024:

- Vol 3A §12.4.7.3: on an INIT, "the processor responds by beginning the initialization process of the processor core and the local APIC ... This state is also referred to as the 'wait-for-SIPI' state".
- Vol 3A §10.4.2, the sentence that decides the bootstrap question: "if the MP protocol has completed and a BSP is chosen, subsequent INITs (either to a specific processor or system wide) do not cause the MP protocol to be repeated. Instead, each logical processor examines its BSP flag (in the `IA32_APIC_BASE` MSR) to determine whether it should execute the BIOS boot-strap code (if it is the BSP) or enter a wait-for-SIPI state (if it is an AP)." Vol 3A §10.4.1: the BSP flag is set for the bootstrap processor and cleared for the others.
- Vol 3C §27.1.3: "INIT signals cause VM exits. A logical processor performs none of the operations normally associated with these events. Such exits do not modify register state or clear pending events as they would outside of VMX operation. (If a logical processor is in the wait-for-SIPI state, INIT signals are blocked.)"; external interrupts are blocked in the shutdown and wait-for-SIPI states; NMIs are blocked in wait-for-SIPI; "if a logical processor is not in the wait-for-SIPI activity state when a SIPI arrives, no VM exit occurs and the SIPI is discarded."
- Vol 3B §33.5.1: "maskable hardware interrupts, exceptions, NMI interrupts, SMI interrupts, A20M interrupts, single-step traps, breakpoint traps, and INIT operations are **inhibited** when the processor enters SMM." Vol 3B §33.6 (exceptions and interrupts within SMM): "if an NMI request is pending when the processor executes the RSM instruction, the NMI is serviced before the next instruction."

Reading, with the citations doing the work:

- **Can an INIT be pending and delivered after another kernel restarted the core?** The SDM documents *inhibition* (SMM) and a *latch* for NMI across RSM, and it documents no latch for INIT anywhere I could find. So the honest statement is: an INIT received in SMM is, as documented, not delivered and not promised for later, i.e. **the stop can be lost, not deferred** — which is what R-3's "the fence repeats its steps until each core it covers is confirmed" (`opus:518`) is for. The contract's "INIT ... held while it is in SMM" (p14:1089, citing the project's recovery draft) is stronger than the SDM supports, and should be reworded to "inhibited; the fence must repeat".
- **After a restart, a stale INIT cannot fire.** Since the only documented latch is the NMI, a second kernel's fresh start is not exposed to a previous kernel's INIT. What *is* exposed is (a) the BSP flag (§10.4.2): a core whose BSP flag is set runs firmware's boot code on an INIT instead of waiting for a SIPI, which is exactly why R-4 keeps the bootstrap core out and why the contract's open point — "whether clearing the bootstrap flag after start-up removes the exception" (p14:1094) — aims at the right bit; the SDM names the bit but does not, in the pages I read, say whether software may clear it after boot; and (b) a core in VMX non-root operation, where an INIT becomes a VM exit to the host and performs no reset (§27.1.3). The SDM's documented exception is therefore non-root operation, not root; so the contract's "INIT is blocked while a core is in VMX root operation" (p14:1089) should be re-derived — blocked in non-root (an exit to the host, no reset), and in root the SDM's ordinary INIT, which the class-1 rule distrusts for another reason; and (c) SMM, as above.
- **A SIPI to an active core** is discarded in VMX (§27.1.3); outside VMX the pages I read do not say, and the design does not need to know, because every SIPI in it points at the one kept stub page.

**Finding, and the cheapest fix in the document.** The contract confirms a parked core by `parked` holding the epoch (p14:1092, step 5), and `parked` is written by the park stub (step 4). The bootstrap core is never sent an INIT (step 2) and the time-based fallback explicitly excludes it, so its only stop is the NMI handler of step 1 — and step 1 has that handler write the crash record and stop, **not** write `parked`. By the contract's own words, the bootstrap core can therefore never be confirmed parked: it becomes *unfenced* after `FENCE_NS`, its memory is never reused, and its roles move only after `FENCE_NS` + `SETTLE_NS` (p14:1033). One clause fixes it: the NMI handler writes the current park request into `parked` before it parks, which is exactly R-1's equality and needs nothing new.

**How long.** The contract's own numbers are policies: `NMI_GRACE_NS` 1 ms, `FENCE_NS` 10 ms, `SETTLE_NS` 1 ms (p14:1241-1243), and two SIPIs 200 µs apart (p14:1091). Barrelfish/DC measured stopping a core at 0.8 to 3.5 µs and starting one at 0.5 to 1.2 ms in the booted core plus 7 to 29 ms of preparation, as the proposal reports from §5.1 table 2 (`opus:77`, `opus:209`); I did not open the paper, so treat those as the author's figures. On x86-64 the fence's floor is the two SIPIs plus the stub, i.e. hundreds of microseconds; on ARM64 and RISC-V the specification gives no bound at all.

### 3.3 RISC-V — SBI HSM

`riscv-non-isa/riscv-sbi-doc`, master, fetched today, "Hart State Management Extension (EID #0x48534D)":

- The state table: 1 `STOPPED` — "the hart is not executing in supervisor-mode or any lower privilege mode. It is probably powered-down by the SBI implementation if the underlying platform has a mechanism to physically power-down harts"; 2 `START_PENDING`; 3 `STOP_PENDING`.
- FID #1 `sbi_hart_stop`: "request the SBI implementation to stop executing **the calling hart** in supervisor-mode and return its ownership to the SBI implementation. This call is not expected to return under normal conditions."
- FID #2 `sbi_hart_get_status` returns that state; FID #0 `sbi_hart_start` is asynchronous and returns `SBI_ERR_ALREADY_AVAILABLE` for a started hart.

So an SBI hart stop confirms exactly one thing — the calling hart's own cooperative stop, observed as `STOPPED` (not `STOP_PENDING`) — and it is **always self-stop**: nothing in SBI stops another hart, and nothing says a forced stop leaves the hart reusable in `STOPPED`. That is the requirement the project puts on its own `fence_hart` extension (p14:1095, `opus:519`), a firmware obligation verified nowhere. A hung hart without that extension is unfenceable, and the class-0 fallback is the only honest answer.

### 3.4 The answer, per architecture

| Architecture | Implementable? | Confirmation | Time |
|---|---|---|---|
| x86-64, any core but the bootstrap one | **Yes**: NMI, then INIT, then two SIPIs to the kept stub, epoch equality; a time-based fallback if the stub does not run and VMX is clear | `parked` = request, or `SETTLE_NS` after the INIT | policy 10 ms; floor ~2 × 200 µs + stub |
| x86-64, the bootstrap core | **No as written**: no INIT (BSP flag, SDM §10.4.2), no epoch written by the NMI handler, the fallback excludes it | none | never confirmed → unfenced |
| ARM64 | **For a core that can still run code**: SDEI event 0 → the kernel's own `CPU_OFF`; a taker polls `AFFINITY_INFO` | state *OFF* **and** the epoch pairing (a never-booted core also reads *OFF*) | unbounded by the specification; a hung core is never confirmed |
| RISC-V | **Only cooperatively, or with the project's `fence_hart`** | `hart_get_status` = `STOPPED`, or the extension's answer | unbounded; a hung hart is never confirmed |

So "a core is taken only once confirmed parked" is implementable on all three architectures for a cooperative give, and for a forced stop only on x86-64 (and not on its bootstrap core) and on ARM64 through a handler that still runs. For a genuinely hung core it is not implementable on ARM64 or RISC-V without firmware the project writes, and on x86-64 only by a timer, which is a guess rather than a confirmation. C\*'s unfenced class is therefore not an edge case: it is the ordinary outcome on two of the three architectures.

---

## 4. Stage 1: is §9.4 complete?

### 4.1 The eight areas the brief names

| Area | In §9.4? | Judgement |
|---|---|---|
| Per-core data | item 6, the array of `CORES_PER_KERNEL_MAX` per-core parts | **Thin.** The parenthetical drops the timer queue that p14:608 does list (documentary). It misses the per-core *page-aligned* objects: the interrupt descriptor table or vector base, the kernel stack and trap frame, the exception stacks, the per-core scratch registers, and the park stub's stack. Those cannot live as fields inside the node block; the block must be enlarged by *k* aligned slabs, and the list does not say so |
| Interrupt path | item 13, the table per core with a target core in each entry | **Wrong shape.** A per-core table with a target-core field duplicates the claim state: two cores could claim one vector. What stage 2 needs is one table per *kernel* with an owning-core field, plus per-core *delivery* state (the IDT, the masked bits), which is missing. On ARM64 the claimable set is SPIs only — "SGIs (0-15), PPIs (16-31) and extended PPIs ... are per core and never claimable" (p14:699) — so a kernel spanning cores cannot route its internal wakeups through the `irq` model at all; the IPI path inside one kernel is missing |
| Scheduler admission | item 12, the core whose sum holds a `sched` | **Incomplete.** The contract's admission is per kernel and `sched_set_cores` takes the core capability of the holder (p14:615); with *k* cores each core has its own capacity, so the sum, the queues and the idle table are per core (item 6) while `sched_set_cores`, `sched_count` (D-118's on-demand counts) and the parked nodes of D-108 keep their per-kernel meaning. No item says what a `sched`'s core does when a thread of it runs elsewhere, or how two levels of sharing (k cores, parked nodes) compose |
| TLB tags | item 10 (the set of cores that loaded an aspace's tag) and item 6 (the tags loaded on a core) | **Present but idle.** Missing: the tag width and its boot-image value, and the *invalidation* of each architecture — an ARM64 broadcast invalidation costs no IPI, an x86-64 one is per core, RISC-V needs the SBI remote fence — which changes R-6's bound and R-15's acknowledgement count. The list says nothing about which architecture's shootdown is broadcast |
| IPC fast path | nowhere | **Missing.** A call whose receiver thread runs on another core of the same kernel cannot use the direct switch, because the receiver cannot run on the calling core: it needs a queue and an IPI, and its lend survives (a lend exists only inside one kernel, p14:615) while the bound gains a wait that R-6 must allow. The credit rings are per ordered pair of kernels (R-13), so *k* cores share one ring: either it splits per core or it needs atomics on the send path, and `CREDITS_*` (item 20) is a boot-image number the list does not tie to *k* |
| Debugger | nowhere | **Missing.** One debug area per node, one crash record per node, "only the kernel that runs the node writes its area" (p14:1260); a breakpoint on a thread on another core means stopping that core and waiting, which R-6 forbids under the lock. The `debug` object is "made at a node's start-up" (p14:1575) and no item says whether it is per kernel or per core |
| Crash record | nowhere | **Missing.** One record of 4,032 bytes per node (p14:1325), written by "the kernel of the node" (p14:1341). With *k* cores two can fail at once: the record needs a per-core section or a first-commit-wins rule, and `NMI_GRACE_NS` (1 ms) is per core while the record is one page |
| R0–R6 for a multi-core kernel | item 15 covers R6's words and the mark; items 14-16 cover the gate checks | **Missing the per-core case.** R0 to R6 all trigger on a *node's* generation ending (p14:1104-1140); a core dying inside a live kernel triggers none of them. Nothing says which waits of the threads on that core end, with which code, when that core's slot in the per-core parts array is torn down, or that R6 does not apply at all because the memory belongs to the same generation and is still *taken* by it. A live kernel needs its own per-core reclaim, and no rule states it |

### 4.2 What else is missing

1. **The bootstrap core's fate** (§3.2 and §9.4 item 1): the word of a core that R-4 keeps out and R6 frees. Also `CORES_PER_KERNEL_MAX` (item 18) as a boot-image value must be checked against the binary's compiled *k* at start-up, in both directions; the list states the value, not the check.
2. **The recovery reserve per core** (p14:1142): "bandwidth 1/64 of a core ... admitted in the node's sum". With per-core sums each core needs its own reserve admission, and the driver's fence runs on one core; item 6's array does not include the reserve context.
3. **The reclaim barrier per core**: its `acked`/`maps_of` words are per kernel (p14:1123-1130); a *core* death inside a live kernel needs a per-core equivalent or it needs nothing, and the list does not say which.
4. **Item 1's stage-1 transitions** are right (only *owned*, the mark, *free*, *free* → *joining* → *owned*), but the *fence on the bootstrap core* uses a path stage 1 already needs (§3.2), so stage 1 is where that clause must land.

### 4.3 What costs on a one-core hot path

The owner's principle — a guarantee is paid at a failure or a rare event — divides the list cleanly. Reserving **fields** is free; adopting the **protocol** on the read or write path is not. Four items cross that line, and two more cost memory:

| Item | Cost | On which path |
|---|---|---|
| 7 `cspace` sequence counter per 128 slots | A second cache line per lookup (the directory is a separate line from the slot) and a load-compare-load sequence on every capability lookup, for a race that cannot exist with one core. The proposal's own trial measured the multi-core cost as p99 1.7 × W and p99.9 2.1 × W at W = 1 µs (`opus:32`) | every call |
| 8 `notify` in a word "an atomic OR can update" | A locked read-modify-write on every signal where a plain OR would do: 20-30 cycles on the most frequent operation. The trial's 6 to 8 % at *k* = 4 (`opus:32`) is this instruction | every signal |
| 11 `thread` state *leaving its core* | A new value in the thread state machine, tested on suspension and destruction and in every switch that already branches on state. Stage 1 never reaches it | suspension, rare |
| 13 interrupt table per core | 12 KB × cores of kept memory (p14:1572, p14:699), and the claim bookkeeping problem above | never hot; memory only |
| 6 node block per-core array | Growth of the block the kernel touches on every event (queues, sum, running context are in it): cache footprint, not instructions | every event |

The recommendation is the distinction, not the deletion: stage 1 keeps the **layout** (the 16-byte directory entry, the notify word, the state value, the fields), which is what stage 2 needs before the kernel is written, and defers the **protocol** (the seqlock read, the atomic OR, the new state being reachable) to stage 2, behind the same ABI. G12's gate lock (item 6) is fine by the principle: it is paid on gate calls only, which are maps, unmaps, role words and core words, all rare.

---

## 5. Judgement

1. The shape is sound, and the second round did what a second round should: every rule the first round needed is now stated, and the explorer's claims reproduce exactly.
2. The staging is the strongest part. Fixing layouts, word formats and gate checks before the one-core kernel is written is the only order that avoids a rewrite, and §9.4 is the right artefact even where it is incomplete.
3. Three one-clause edits are real and cheap: the park request before *leaving* (§2.2), the taker's current generation in the commit (§2.3), and the park epoch written by the NMI handler on the bootstrap core (§3.2).
4. One rule needs a real fix, not a clause: R-5 must check the taker's whole core set at the hand-over and at the take (§2.4), because the gate allows a role holder to own a class-1 core today.
5. One consequence must be written down rather than fixed: the bootstrap core is lost for the rest of the boot when its kernel dies (§2.5).
6. §9.4 is not complete: per-core trap state, the intra-kernel IPI path, per-core admission, per-core invalidation, the cross-core call path, the debugger, the crash record, and the per-core reclaim after a core death (§4.1-4.2).
7. The explorer's blind spots are exactly the ones the protocol's *bounds* depend on — no time, no ordering, no locks — so it can confirm rules but can never confirm R-6.
8. The hardware verdict is the sharpest limit: a core can be taken on confirmation only while it can still run a handler; a hung core is unfenceable on ARM64 and RISC-V without firmware the project writes, and on x86-64 only by a timer (§3.4).
9. Nothing in the second round needs a new object or a new call, which is the right test for a contract already frozen elsewhere.
10. What would make me abandon it: a measured fence on ARM64 or RISC-V above a few hundred microseconds for an ordinary give, or no stop at all for a hung core on either — because then "a core is taken only once confirmed parked" is a policy that works on one architecture only, and C\* becomes a one-architecture design carrying a three-architecture cost.

---

## Appendix A — How to reproduce

```
cd /tmp/xshape2-deepseek
timeout 240 python3 -B author.py moves:correct shootdown:correct seal:correct credits:correct
timeout 240 python3 -B refine.py mv2s:correct role:correct barrier:correct
timeout 240 python3 -B refine.py mv2s:word_then_request mv2s:gen_from_read role:single_core barrier:ack_all_live
timeout 240 python3 -B refine.py mv2s:probe_bsplost mv2s:probe_stub_take
```

`author.py` is a byte-for-byte copy of the delivered explorer; `refine.py` differs only by the three scenarios, the split steps and the extra properties (P9, P10, REUSE, PROBE). `mv2` with its default size (three kernels, four cores) is too large for Python breadth-first search; `mv2s` is the two-kernel, three-core instance used throughout.

## Appendix B — Sources

- `Docs/research/drafts/kernel-shape-opus.md` (the proposal, §9 in full, lines 480-670).
- `Docs/research/drafts/kernel-shape-explorer.py` (the delivered explorer, 850 lines).
- `Docs/architecture/kernel-interface.md` at `b501b32`: p14:608 (per-core list), p14:615, p14:699 (interrupt table), p14:1033/p14:1048 (unfenced and fencing rows), p14:1085-1094 (the x86-64 fence), p14:1095 (RISC-V), p14:1104-1140 (R0-R6), p14:1123-1130 (the barrier), p14:1142 (the recovery reserve), p14:1241-1243 (the constants), p14:1260-1282 and p14:1325-1342 (debug area, crash record), p14:1558-1582 (object sizes), p14:1668 (kept ranges).
- **Arm DEN 0022E**, *Power State Coordination Interface (PSCI)*, issue E: §5.5.1, §5.5.2, §5.7.1, §5.7.2, §6.6.
- Intel, *Software Developer's Manual*, order 325384, December 2024: Vol 3A §10.4.1, §10.4.2, §12.4.7.3; Vol 3B §33.5.1, §33.6; Vol 3C §27.1.3.
- RISC-V, *SBI specification* (`riscv-non-isa/riscv-sbi-doc`, master, fetched 16 November 2026): *Hart State Management Extension*, EID `0x48534D`, state table, FID #0, #1, #2.
- `Docs/decisions/README.md` (D-026, D-027, D-028, D-094, D-107, D-108, D-111, D-113 to D-125).
- `Docs/architecture/kernel.md` (the shape's own section, D-042, the three candidate answers).
- `Docs/reviews/2026-11-16-verify-kernel-shape-opus-by-hydrogen.md` (the first hand's review and its five tests).
