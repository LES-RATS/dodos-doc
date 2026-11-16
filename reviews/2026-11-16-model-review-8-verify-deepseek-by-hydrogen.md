# Verification of DeepSeek's review of `dodos-model` (pass 8)

Target reviewed: [`2026-11-16-model-review-8-deepseek.md`](./2026-11-16-model-review-8-deepseek.md), which reviews `dodos-kernel` (branch `model`, commit `633f6f3`) against [`kernel-interface.md`](../architecture/kernel-interface.md) (decisions read to D-133).

All baseline checks, probes, and mutations ran in an isolated temporary copy (`/Users/btw/.t3/userdata/antigravity-tmp/0d967d28df3f/run-DgmX6w/dk-verify-hydrogen`) and were reverted afterward; `/Users/btw/Documents/repos/dodos-kernel` was not modified. Baseline in the copy (`nix develop -c cargo test -p dodos-model`): **941 passed, 0 failed** (319 unit tests + 622 integration tests across 15 binaries; `check/tests.rs` has 191 `#[test]` functions, matching DeepSeek line 380).

## Summary of Verdicts

| Item | DeepSeek claim | Verdict | Key point |
|---|---|---|---|
| Finding 1 | Taskless sender's stamp `0` read as node `0` and dropped | **confirmed with another correction** | Defect holds in both contract and model; `task.counter() != 0` never refuses a legitimate task (counters start at 1), **but** DeepSeek's `(task.counter() != 0 && task.node() != sender)` accepts forged non-zero counter-0 stamps (`TaskId::new(2, 0)`). |
| Finding 2 | `RESERVE` check `owed <= 34` cannot fail | **confirmed with another correction** | Tautology confirmed (`<= 24 <= 34`), **but** DeepSeek's proposed `free >= owed` falsely fails legal states (`23 < 34` reproduced) because it double-counts an unconsumed `Report` already sitting in `y -> x`. |
| Finding 3 | Fence check `park_requests[core] != 0` cannot fail | **confirmed with another correction** | Invariant weakness confirmed (`915 <-> 917` swap passes all 941 tests), **but** DeepSeek's `FenceRecord` fix doubles the ABI struct (544 → 1,056 bytes) AND **still passes with the swap in place**. |
| Limitation | `memory.rs:528` checks grant before raising `used.leaves` (`kernel-interface.md:880`) | **confirmed** | Model events are atomic, so post-state invariants cannot distinguish the two orders without an intra-event trace. |
| Tables (Q4) | Four sentence-by-sentence mapping tables | **9/10 sampled rows right, 1 wrong** | **Table 2 Row 17 is wrong**: `resume_step` omits R0 and unpinned R3 freeing when a peer is `Dead` or fresh-started while sealed (broken `CREDIT` reproduced). Also Section 4's claim that swapping `nodes.rs:917` and `:919` fails `check/machine.rs:73` is **false**. |

---

## Finding 1 — Taskless sender stamp `0` dropped as node `0`

**Verdict: confirmed with another correction.**

### Line and quote check
- Contract quotes match verbatim: `kernel-interface.md:14` (Rule 4), `:1061` ("identifier 0 means \"no task\""), `:1083` ("0 if the sender is attached to none"), `:934` ("a `Send`'s stamp carries a task identifier of the sender's node. A message that fails any of these changes nothing, is consumed, and is traced (code 11 of [What the kernel traces](#what-the-kernel-traces)).").
- Code citations match: `grants.rs:292` (`stamp_of`), `:261` (`let (task, marks) = self.stamp_of(thread);`, with `Body::Send` at `:266-268`), `rings.rs:432` (`Body::Send { stamp, .. }`, `:432-435`), `:489` (`Some(named)` arm at `:489-500`), `abi/src/lib.rs:1061` (`TaskId::node()`), `tasks.rs:45` (`task_attach`), `nodes.rs:942` (`r0`), `check/machine.rs:225` (`CREDIT`).

### Reproduction
In the temporary copy, detaching node 1's start-up thread (`TaskAttach` with `SlotAddr::NONE`) and calling `node_send` to node 0 followed by `settle(100_000)` printed:

```text
F1: refused 0=1, 1=0; wait=Node { peer: 0, credit: 16 }; check=Err("CREDIT: a credit in use with neither its request nor its answer in flight")
```

An asymmetric run with node 0 detached sending to node 1 passed (`0.node() == 0`), waking with `Err(Error::WouldWait)`.

### Answers to Q1
1. **Model-only or contract defect too?** **Both are at fault.**
   - *Stamp* (`kernel-interface.md:1083`, `:1061`, `:970`): a detached or newly retyped thread carries no task and is explicitly stamped with task identifier `0`; `node_send` (`:970`) imposes no requirement that the caller be attached to a task.
   - *Receive check* (`kernel-interface.md:934`): states unconditionally that `"a \`Send\`'s stamp carries a task identifier of the sender's node"`, with no carve-out for `0`, while `:1061` places node IDs in bits 48–63 (so `0` decodes as node `0`).
   - *Refusal rule* (`kernel-interface.md:934`, `:940`, `:971`): a refused message changes nothing, is consumed, and is traced (sending no `SendAnswer`), while the sender's credit and wait stay open until an answer or R0. Under `:934` as written, any compliant kernel refuses every `Send` from a taskless thread on node `!= 0` without answering, breaking Rule 4 (`:14`).
2. **Contract sentence that fixes it (`kernel-interface.md:934`).**
   Because a receiver cannot observe whether the sender's thread had a task and trusts the sending kernel's stamping (`:934`), replace `"a \`Send\`'s stamp carries a task identifier of the sender's node"` with:
   > "a `Send`'s stamp carries 0 or a task identifier of the sender's node (with a non-zero counter)."
   (DeepSeek's `"a \`Send\`'s stamp carries a task identifier of the sender's node, or 0 for a sender attached to none"` resolves the `0` contradiction as well, though mentioning the non-zero counter makes `:1061` explicit for forged stamps.)
3. **Is `task.counter() != 0` safe for legitimate tasks, and is DeepSeek's code fix right?**
   - **No legitimate task has counter `0`.** `kernel-interface.md:1061` specifies counters start at `1`; `boot.rs:1096-1097` creates the start-up task with `TaskId::new(self.node, 1)` and sets `task_counter = 1`; `tasks.rs:190-193` (`next_task`) increments `self.task_counter += 1` before calling `TaskId::new`.
   - **Why DeepSeek's Rust expression is wrong:** `rings.rs:432-435` returns `Some(...)` to **refuse** a message. DeepSeek's `(task.counter() != 0 && task.node() != sender).then_some(stamp.0)` evaluates to `false` whenever `task.counter() == 0` — meaning it **accepts** a forged/corrupted non-zero stamp whose counter is `0` and whose node is *not* the sender, e.g., `TaskId::new(2, 0).raw() == 0x0002_0000_0000_0000` from sender `1` (as well as `TaskId::new(sender, 0)`). The exact refusal check for `"0 or a task identifier of the sender's node with a non-zero counter"` is:
     ```rust
     (stamp.0 != 0 && (task.counter() == 0 || task.node() != sender)).then_some(stamp.0)
     ```

---

## Finding 2 — `RESERVE` check cannot fail

**Verdict: confirmed with another correction.**

### Line and quote check
- Quote of `kernel-interface.md:943` is verbatim.
- Citations match: `check/machine.rs:196-202`, `:305` (`peers_of`), `rings.rs:205` (`Peer::new`), `abi/src/ring.rs:19-20`, `:34` (`RING_ANSWER_RESERVE = 34`), `check/node.rs:328`, `explore.rs:7`, `roles.rs:459` (`busy`).
- Diagnosis is right: `peer.iter().flatten().count()` counts credits (`<= 24`), so `owed <= 34` is a tautology.

### Why DeepSeek's proposed fix breaks valid states (reproduced)
DeepSeek proposes summing `11` (`RING_MESSAGE_ENTRIES_MAX`) for each `Completes::Report` credit and `1` for every other credit in `x`'s `peers[y]` (`owed`), and checking `free >= owed` against `ring_free` of `y -> x`.

That **double-counts answers that `y` has already written into `y -> x` before `x` drains the ring**: writing the 28-item `Report` (11 entries) into `y -> x` reduces `free` by 11, *while the `ReportAsk` credit remains in `x.peers[y]`* until `x` calls `report_received` (`roles.rs:606`) to free it.

In the temporary copy, we constructed a legal reachable state (`m.sys.check() == Ok(())`):
- Node `0` holds 24 active credits toward node `1`: 1 `ReportAsk`, 15 `Revoke`s, and 8 `Send`s.
- Ring `1 -> 0` contains 30 non-answer entries (`Ping`) plus node `1`'s 28-item `Report` answer (11 entries): `produced - consumed = 41`, so `free = 64 - 41 = 23`.
- Probe output:
  ```text
  F2 valid state: free=23, deepseek_owed=34
  F2 exact check: free=23, still_owed=23, report_asks=1
  ```
  DeepSeek's `free >= owed` (`23 >= 34`) falsely fails a valid state. DeepSeek's alternative ("check `report_asks <= 1` instead") checks only the premise of `kernel-interface.md:943`, not whether `ring_room` (`rings.rs:261`) actually kept the 34-entry reserve free of non-answers.

### Answers to Q2: The check that can fail, and the 28-item `Report` scenario
1. **The check in terms of `kernel-interface.md:943`:**
   - *Premise* ("a new holder has at most one `ReportAsk` in flight to each node"):
     ```rust
     let report_asks = peer
         .iter()
         .flatten()
         .filter(|c| matches!(c.completes, Completes::Report { .. }))
         .count();
     ensure(report_asks <= 1, "RESERVE: more than one ReportAsk in flight to a peer")?;
     ```
   - *Conclusion* ("the kernel ring *Y* → *X* keeps `REQUESTS_PER_PEER` + `SENDS_PER_PEER` + 10 entries (34) for the answers to *X*"): sum the entries **still owed** — credits in `x.peers[y]` whose answer has *not* yet been placed into kernel ring `y -> x`:
     ```rust
     let still_owed: u64 = peer
         .iter()
         .enumerate()
         .filter_map(|(i, slot)| slot.as_ref().map(|c| (i as u8, c)))
         .filter(|&(i, c)| !self.answer_in_kernel_ring(y, x, i, c.serial))
         .map(|(_, c)| match c.completes {
             Completes::Report { .. } => dodos_abi::RING_MESSAGE_ENTRIES_MAX as u64,
             _ => 1,
         })
         .sum();
     let pair = &table.rings[y as usize][x as usize];
     let consumed = table.beacons[x as usize].consumed[y as usize].0;
     let used = pair.kernel.produced.wrapping_sub(consumed);
     let free = dodos_abi::RING_KERNEL_ENTRIES.saturating_sub(used);
     ensure(still_owed <= free, "RESERVE: answers still owed exceed free ring entries")?;
     ```
     (Where `answer_in_kernel_ring(y, x, i, serial)` checks `y -> x`'s unconsumed kernel ring entries using `m.header.credit() == Some((i, serial))`, reusing the helper at `check/machine.rs:246` restricted to the kernel ring. If `x` fresh-starts, `peers` starts empty and `skip_rings` resets `consumed`, so `still_owed == 0 <= free`; if `y` fresh-starts, `y`'s old generation stops writing and `y`'s new generation still respects `ring_room`'s 34-entry reserve for non-answers.)
2. **28-item `Report` scenario that exercises it:**
   - Two nodes (plus a third if triggering two simultaneous take-overs): node `1` attaches 28 devices to an IOMMU unit (or claims 28 items total across devices/lines so `Report` carries the maximum 28 items = 85 payload words = 11 entries).
   - Saturate `0`'s credits toward `1` with 1 `ReportAsk` (for that 28-item unit) + 15 `Revoke`s + 8 `Send`s (24 credits, `still_owed = 34`), and fill the non-answer space of `1 -> 0` to `RING_KERNEL_ENTRIES - RING_ANSWER_RESERVE = 30` entries (`free = 34`).
   - *Valid boundary*: `1` answers with the 28-item `Report` (11 entries). `free` becomes `23` and `still_owed` becomes `23`, testing the exact 11-entry `Report` slack with `still_owed <= free` (`23 <= 23`).
   - *Failure trigger*: if `roles.rs:459`'s `busy` guard is weakened so a second unit rebuild on `0` sends a second `ReportAsk` to `1` (replacing one 1-entry request with a second 11-entry `ReportAsk`, `still_owed = 44 > 34`), or if `ring_room` lets `1` write 31 non-answer entries (`free = 33 < 34`), the check fails (`RESERVE: answers still owed exceed free ring entries` or `more than one ReportAsk`).

---

## Finding 3 — Fence "park request before the mark" check cannot fail

**Verdict: confirmed with another correction.**

### Line, quote, and mutation check
- Contract quotes match (`kernel-interface.md:1261`, `:1182`, `:1171`, `:1177`). Minor citation imprecision: DeepSeek line 230 cites `nodes.rs:914` (the comment `// The park request first, then the mark.`); the two statements are `nodes.rs:915` and `nodes.rs:916-917`. Also line 253 says the model's `FenceRecord` (`table.rs:165`) `"has no generation word at all"`; in fact `table::FenceRecord` omits `generation`, `reserved`, and `reserved2`, holding only `started`, `confirmed`, and `last_stop`.
- Diagnosis confirmed in the temporary copy:
  - **Mutation A**: swapped `nodes.rs:915` (`park_requests[core] += 1`) and `:916-917` (`write_core(..., word.marked())`). All **941 tests** in `dodos-model` passed (`0 failed`).

### Why DeepSeek's proposed fix ALSO fails to catch the swap (Mutation B)
DeepSeek proposes recording each core's `park_requests` count at `started` (`nodes.rs:908`) in `FenceRecord` and checking `park_requests[core] > that_count` (`check/machine.rs:77`).
- That catches a *missing* `park_requests[core] += 1` on a subsequent fence of a core (DeepSeek's first bullet, where `!= 0` stays trivially true).
- **It does NOT catch swapping `:915` and `:916-917`.** Both statements still run inside one atomic `fence_unit` event before `System::after` and `System::check()` execute, so by the time `check_cores` runs, `word.is_marked()` is `true` and `park_requests[core] == that_count + 1 > that_count` in both orders!
- **Verified in the copy (Mutation B):** keeping Mutation A's swap in `nodes.rs` and implementing DeepSeek's `park_at_start` in `FenceRecord` + `park_requests[core] > that_count` in `check/machine.rs:77`, all **319 library tests** (including every fence scenario and exploration) **still passed**.

*(Related falsified claim in Section 4, lines 365–366)*: DeepSeek claims `check/machine.rs:73` (`!stopping || word.is_marked()`) `"does fail when the order of nodes.rs:917 and :919 is swapped, which I checked in the copy"`. We ran **Mutation C** in the temporary copy moving `self.hw_out.push(HwAction::Stop { core })` before `if !word.is_marked() { ... write_core(..., word.marked()) }` and ran `cargo test -p dodos-model --lib scenarios::`: all **125 scenario tests passed** for the exact same reason (both happen inside one atomic `fence_unit` call). Only omitting/delaying the mark across events trips `:73`.

### Answers to Q3
1. **Is recording park counts in `FenceRecord` a layout change, and what does it cost?**
   **Yes.** `dodos_abi::FenceRecord` (`abi/src/machine.rs:278-285`; `kernel-interface.md:1261`) is 544 bytes: `generation: u32`, `reserved: u32`, `first_action: u64`, `confirmed: u64`, a single 8-byte `reserved2: u64` (word 3), and `last_stop: [u64; 64]` (512 bytes). Because a node may span up to `CORES_PER_KERNEL_MAX = 64` physical cores (`abi/src/machine.rs:295`) and each `park_request` is a 64-bit count (`kernel-interface.md:1177`), per-core counts at `started` require `[u64; 64]` = **512 bytes**, which cannot fit in the 8-byte word 3 (nor can a single scalar `u64` hold per-core counts, since cores of one node can have distinct counts from earlier fences/seals/retirements). Adding `park_at_start: [u64; 64]` **nearly doubles `FenceRecord` from 544 to 1,056 bytes** (`68 KB` → `132 KB` for 128 node slots in the living part) and adds up to 64 writes on fence start, for data nothing outside an invariant check reads.
2. **Can an event-trace check do without changing the layout?**
   **Yes — and it actually catches the swap.** `Table` (`table.rs:322-331`) already carries `Ephemeral` per-event write journals (`writes`, `member_writes`, `role_writes`, `gated`) cleared after `System::check()`. Adding a similar `fence_trace: Ephemeral<Vec<FenceEvent>>` that logs `ParkRaised(core)`, `CoreMarked(core)`, and `StopSent(core)` (or comparing per-core sequence indices inside the event) requires **zero bytes in `dodos_abi::FenceRecord`**, needs no contract layout change, and immediately rejects both Mutation A (`CoreMarked` before `ParkRaised`) and Mutation C (`StopSent` before `CoreMarked`). Combining it with model-only `park_at_start` in `table::FenceRecord` also catches a forgotten increment on re-fenced cores without touching `abi/`.

---

## Stated Limitation (`kernel-interface.md:880`)

**Verdict: confirmed.**

- Quote matches `kernel-interface.md:880`.
- `memory.rs:528-538` checks `grants[remote.node].get(&remote.grant)` (`Live` and matching `serial`) and returns `Err(Error::Gone)` at `:534` before any count increment; `count_leaves` (`memory.rs:119`) is only invoked later inside `record_mapping` (`:70`) and `extend_mapping` (`:638`).
- Because each kernel call/event runs atomically in `Model`/`System` without concurrent interleaving against `revoke_anchor` (`grants.rs:656`), the observable post-states of the two orders are identical; only an intra-event trace of gate accesses could test the ordering rule.

---

## Q4: Random 10-Row Audit of DeepSeek's Four Tables

We selected 10 rows across the four tables and checked every contract claim, function name, line number, and behaviour against the code:

| # | Location in review | Contract claim (abbreviated) | Code checked | Result |
|---|---|---|---|---|
| 1 | Table 1, Row 4 (`line 275`) | Producer in ring, consumer in receiver's beacon, neither goes back | `rings.rs:253` (`consumed`), `:282` (`write_message`, `:326` `ring.produced += entries`), `:512` (`set_consumed`, `:486` `consumed + length`) | **Right** (`set_consumed` starts at `:512`, assignment at `:513`). |
| 2 | Table 1, Row 11 (`line 282`) | Answers reserve 34; request full → `again`; `Release`/`Signal` pending 32/event in use-table order; non-manage `Send` capped at `SENDS_PER_PEER - 2` | `rings.rs:261` (`ring_room`), `grants.rs:618` (`revoke_anchor`), `:772` (`remote_destroyed`), `:557` (`grant_signal`), `rings.rs:625` (`send_pending`, `PENDING_STEP=32` over `BTreeMap` `table.rs:284`), `grants.rs:215-221` | **Right**. |
| 3 | Table 2, Row 4 (`line 295`) | Remote cap valid iff grant live+serial & granter's member word names use-entry generation in starting/live/sealing/sealed | `grants.rs:79-91` (`valid`) | **Right**. |
| 4 | Table 2, Row 11 (`line 302`) | `Release` frees use entry or sets *release pending*; ended granter gen sends none; `Revoke` removal sends none | `grants.rs:772-803` (`remote_destroyed`) | **Right**. |
| 5 | **Table 2, Row 17 (`line 308`)** | Grant dies with grantee's gen (pinned, freed when gen over); R2 removes dead granter roots; **a resume runs R0, R2, R3 and R4, R5 and sends no release** | `nodes.rs:1084` (R3), `:1374` (`unpin`), `:1494` (`resume_step`), `:1548` (`drop_ended`) | **WRONG** — see bug below. |
| 6 | Table 3, Row 5 (`line 328`) | TLB invalidation on non-idle cores holding space; ARM64 broadcast; x86-64/RISC-V request; kernel space includes idle cores | `cores.rs:253` (`others_hold`), `:272` (`start_request`, `:286` Aarch64, `:313` `space.is_some() && idle.mark`), `:348` (`invalidate_on`) | **Right**. |
| 7 | Table 3, Row 7 (`line 330`) | Request asking no core completes in the call | `cores.rs:331-336` (`if asked == 0 { self.complete(at); return Started::Complete; }`) | **Right**. |
| 8 | Table 4, Row 3 (`line 350`) | Confirmation only for current park request: x86-64 `parked`, ARM64/RISC-V machine answer (`stopped`) | `nodes.rs:589-599` (`park_confirmed`) | **Right**. |
| 9 | Table 4, Row 5 (`line 352`) | Stub writes `started` (0 when parked); starter retries every `START_RETRY_NS` until match or not starting | `nodes.rs:1576-1600` (`start_step`), `system.rs:503-511` (`write_parked` `:507` `started = 0`), `system.rs:649-651` (`wake` `:650` `started = request`) | **Right**. |
| 10 | Table 4, Row 14 (`line 361`) | Seal: hand unit roles, drain kernel rings/requests, write `sealed` last with last park request; return to live if alone | `nodes.rs:1407-1488` (`seal_step`) | **Right**. |

### Why Table 2, Row 17 is wrong (new model bug missed by DeepSeek)
`kernel-interface.md:885` requires that when a sealed node resumes, before it runs any thread, *"it runs R0, R2 and R3 for every node whose generation ended while it was sealed (R3 frees at once the grants it made to a generation already over), and R4 and R5 for each such node still fenced or unfenced, and sends no release for those grants"*.

In the model (`nodes.rs:1494-1539`):
1. `resume_step` calls `reclaim_step` **only** when `state` is `Fencing | Fenced | Unfenced` (`nodes.rs:1506-1510`).
2. When a peer finished dying (`Dead`) or already started fresh (`generation != seen_generation`) while the node was sealed, `resume_step` skips `reclaim_step` and calls **only `drop_ended`** (`nodes.rs:1517-1523`, `:1548-1570`).
3. **`drop_ended` omits R0**: it does not call `self.r0(node, self.seen_generation(node))`. Threads waiting on `Wait::Node { peer, .. }` remain stuck, `peers[node]` credits stay in use, pending signals/releases in `uses[me]` for that dead generation are left uncleaned, and unit requests sent to `node` stay un-requeued. Once `node` fresh-starts (or if already fresh-started when resumed), `System::check()` fails with **`CREDIT: a credit in use with neither its request nor its answer in flight`**.
4. **`drop_ended` omits unpinned R3**: `drop_ended` ends with `self.unpin(units)` (`nodes.rs:1569`), and `unpin` (`nodes.rs:1380`) only frees entries with `e.state == GrantState::Pinned`. Grants still in `GrantState::Live` or `GrantState::Revoking` whose grantee is the ended generation are **not freed at resume**.

**Reproduced in the temporary copy:** Node `0` started a `node_send` to node `1` (taking send credit 16, entering `Wait::Node { peer: 1, credit: 16 }`), node `0` sealed (`MemberState::Sealed`), node `2` killed node `1` (`MemberState::Dead`), and node `2` resumed node `0` back to `Live`:
- Output while node `1` remained `Dead`: `T2R17 after resume (peer Dead): wait=Node { peer: 1, credit: 16 }, credit_still_used=true`.
- Fresh-starting node `1` then caused `System::check()` to fail during `run(20 * MS)` with `Err("CREDIT: a credit in use with neither its request nor its answer in flight")`.

*(DeepSeek's failure mode in Section 4 prose at lines 365–366 is documented under Finding 3 above.)*

---

## Corrections to apply, in order of severity

### To the model (`dodos-kernel`)

1. **High — Fix `resume_step` / `drop_ended` when a peer reached `Dead` or fresh-started while sealed (`model/src/nodes.rs:1494-1570`, `nodes.rs:1374`)**:
   In `resume_step` (`:1517-1523`), before calling `drop_ended(node, units)` for a peer whose `state == MemberState::Dead || generation != seen_generation`:
   - Run `self.r0(node, self.seen_generation(node))` (and guard R0/drop checks so that if the peer already fresh-started to `g + 1`, `r0` clears `peers[node]`, `Wait::Node`, `unit_requests`, `unit_service`, and `uses` matching `u.generation != current_generation || !writes(node)` — note `r0` at `:967` filters `u.generation == generation`, so passing `seen_generation(node)` properly clears the ended generation's `uses`, while `self.seen` should only update to `current_generation` once `drop_ended` finishes).
   - Free **all** grants made to `node`'s ended generation (`grantee == node && self.grantee_over(entry)` regardless of `GrantState::Live | Revoking | Pinned`) — either by pinning matching ended-generation grants on entering `drop_ended` or extending `unpin` (`nodes.rs:1380`) to match `self.grantee_over(e)` for any `GrantState` when invoked for an ended generation. Add a regression test in `scenarios/reviews.rs` (node `0` waiting on `NodeSend` and holding a live grant to node `1`, sealed while `1` is killed to `Dead` and restarted fresh, then resumed).
2. **High — Accept stamp `0` and reject counter-`0` non-zero stamps in `refused` (`model/src/rings.rs:432-435`)**:
   Replace `(task.node() != sender).then_some(stamp.0)` with:
   ```rust
   Body::Send { stamp, .. } => {
       let task = dodos_abi::TaskId::from_raw(stamp.0);
       (stamp.0 != 0 && (task.counter() == 0 || task.node() != sender)).then_some(stamp.0)
   }
   ```
   Add a regression test in `scenarios/reviews.rs` covering a taskless sender on node `!= 0` (must succeed/answer `would_wait`) and a forged non-zero stamp with counter `0` (`TaskId::new(2, 0)` from node `1`, must be refused).
3. **Medium — Replace the tautological `RESERVE` check (`model/src/check/machine.rs:198-202`)**:
   Assert both `report_asks <= 1` and `still_owed <= free` against kernel ring `y -> x`, counting `11` for a `Completes::Report` credit and `1` for other credits whose answer is not already unconsumed in kernel ring `y -> x`. Add a 28-item `Report` test that fills the 30 non-answer entries and verifies both the boundary (`23 <= 23`) and failure when an extra `ReportAsk` or non-answer entry exceeds the reserve.
4. **Medium — Replace the tautological fence order check (`model/src/check/machine.rs:77-80`, `model/src/table.rs`, `model/src/nodes.rs`)**:
   Add an ephemeral intra-event trace (`fence_trace`) in `Table` recording `ParkRaised(core)`, `CoreMarked(core)`, and `StopSent(core)` in execution order, and check in `System::check()` that within each event `ParkRaised(c)` precedes `CoreMarked(c)` and `CoreMarked(c)` precedes `StopSent(c)`, plus `park_requests[core] > park_at_start` in model-only `table::FenceRecord` so missing increments on re-fences fail as well. Leave `dodos_abi::FenceRecord` unchanged.
5. **Low (optional model fidelity) — Add an intra-event gate-order check for `kernel-interface.md:880`**:
   To verify the limitation DeepSeek noted (`memory.rs:528` checking the grant entry before `count_leaves`), either reorder `memory.rs:528-571` / record an ephemeral gate-access trace when mapping under a grant so `use.leaves` increment visibly precedes the second grant read in the trace.

### To the contract (`architecture/kernel-interface.md`)

1. **High — Fix the `Send` stamp check contradiction at [`kernel-interface.md:934`](../architecture/kernel-interface.md#L934)**:
   Change:
   > `a Send's stamp carries a task identifier of the sender's node.`
   to:
   > `a Send's stamp carries 0 or a task identifier of the sender's node (with a non-zero counter).`
   *(No layout change is needed at [`kernel-interface.md:1261`](../architecture/kernel-interface.md#L1261) for Finding 3, and [`kernel-interface.md:943`](../architecture/kernel-interface.md#L943) for `RESERVE` is already accurate as written.)*
