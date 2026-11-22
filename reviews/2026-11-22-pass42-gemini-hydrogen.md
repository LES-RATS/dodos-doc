# Review of Pass 42 (`18ce687..43e5f07`)

**Verdict:** No findings (0 major, 0 minor) in `18ce687..43e5f07` (`6077e4c`, `a6c7ee2`, `bd8085c`, `43e5f07`). Every change matches the contract in `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` and `/Users/btw/Documents/repos/Docs/decisions/README.md` (D-168, D-169, D-170), resolves the prior review findings, and is backed by non-vacuous tests and mutation checks.

---

## Checked and Found Correct

### 1. D-170 against the contract
- **Rule & semantics (`kernel-interface.md:1883, 2206`; `decisions/README.md:180`):**
  - `Peer::last_report: Option<u64>` (`model/src/rings.rs:238`) is updated in `Model::report_received` (`model/src/roles.rs:1177`) to `Some(self.membership_now())` immediately after `take_credit` and matching `Completes::Report { role }`, and before the early return on late/non-current reports (`roles.rs:1182-1188`). Thus any consumed `Report` (taken by the active cursor or dropped as late) refreshes `last_report`.
  - `Model::rebuild_wait_since` (`model/src/roles.rs:519-526`) returns `rebuild.asked_at.map(|at| last.map_or(at, |report| at.max(report)))`. Because `asked_at` is `None` when the rebuild is not waiting, `last_report` never fabricates a wait start.
  - All three cut checks in `Model::rebuild_step` — `asked` (`roles.rs:586-588`), `blocking` (`roles.rs:662-664`), and `Err(Full::Credit | Full::Ring)` (`roles.rs:703-705`) — as well as `Model::reserve_due` (`model/src/nodes.rs:2314`) and `System::check_units` (`model/src/check/machine.rs:610-615`) use `rebuild_wait_since`.
  - In the `blocking` and `Full::Credit | Full::Ring` branches (`roles.rs:662, 703`), `rebuild.asked_at.get_or_insert(now)` preserves the instant the cursor reached the peer rather than resetting it on later polls when no `Report` was consumed.
- **Faulty-node delay bound:** A faulty peer cannot abuse `last_report` to prolong a rebuild indefinitely because `last_report` advances only when consuming a `Report` matching an in-use `ReportAsk` credit (`rings.rs:574-582`, `roles.rs:1169-1174`). The holder maintains at most one `ReportAsk` in flight per peer (`roles.rs:650-661`), and each rebuild sends at most `⌈items / 28⌉ + 1` asks before completing, refusing a malformed/bad-item `Report`, or cutting at `STUCK_NS` (the active ask is cut within `STUCK_NS`, and a waiting rebuild at most `STUCK_NS` after the last consumed `Report`).
- **Healthy-node safety:** A healthy peer serving its kernel ring within `RECOVERY_PERIOD_NS` (< `STUCK_NS`) refreshes `last_report` on each consumed page, preventing spurious deadline cuts on concurrent waiting rebuilds.
- **Resets of `last_report`:** `Peer::new()` (`model/src/rings.rs:246`) initializes `last_report: None`. This runs on fresh start (`model/src/boot.rs:1790`) and inside `Model::r0_effects` (`model/src/nodes.rs:1192`), which is invoked on every peer death (`observe_watched` at `nodes.rs:626`, `reclaim_step` at `nodes.rs:1427`, and `resume_step` at `nodes.rs:2050, 2055`, including `ended_while_sealed`). Because `dodos_abi::barrier` (`abi/src/machine.rs:1605`) prevents a dying node from reaching `Dead` and restarting until all `Starting | Live | Sealing` peers finish R0/R5, a new generation of a peer always begins with `last_report == None`.

### 2. Gate race model's seal park (`model/src/gate/race.rs`)
- **Contract faithfulness (D-168 (3), `kernel-interface.md:2207`):**
  - `State::sealing(other)` (`race.rs:144-149`) starts core 0 at `Pc::SealPark(0)` while `Member::Sealing`.
  - First access (`Pc::SealPark(0)`, `race.rs:172-177, 227-236`) acquires `self.lock` if not held by the other core (`blocked` prevents concurrent entry under `Variant { lock: true }`).
  - Second access (`Pc::SealPark(1)`, `race.rs:294-299`) sets `self.seal_parked[c] = true` while `self.member == Member::Sealing`, then calls `end(self, Pc::Parked)` which releases `self.lock` and stops the core without returning.
  - `check` checks `LOCK` across both `Member::Live | Member::Sealing` (`race.rs:430-439`), and `Step::Resume` (`race.rs:190-198, 337-344`) transitions to `Member::Live` once core 0 is `Pc::Parked` with `seal_parked[0]` and core 1 is `Pc::Done`, letting core 1 run a post-resume call (`Pc::Attach(0)`).
- **Non-vacuous exploration (`race.rs:547-568`):** `seal_park_releases_the_gate_lock_before_stopping_the_core` explores all reachable interleavings from both `State::sealing(Pc::Done)` (quiet) and `State::sealing(Pc::Attach(0))` (racing with a live gate call during sealing), asserting `broken == None`, `wedge == None`, `resumed == true`, and state-space sizes (`> 20` and `> 100`).

### 3. Minors (prior findings 3, 4.1, 4.2, 4.3)
- **Narrowed `cleared_faulty` & stale `ReportAsk` (`check/tasks.rs:103-113`, `roles.rs:604, 674, 715, 780-782, 847, 490, 1068-1100`, `nodes.rs:1248`, `units.rs:596`):**
  - `cleared_faulty` exempts a missing `lines` entry only when `(irq.source.id(), self.node, self.table.generation(self.node))` is in that specific line's `ioapic_role`'s `UnitState::cut_lines` (populated only when that role's rebuild cleared the line because `rebuild.cut.contains(&(node, g))`, and cleared on rewrite, `UnitOp::Redirection`, `r1`, or `after_take` on peer death). Other roles, newly claimed lines, and later generations are no longer exempted.
  - In `Model::report_asked` (`roles.rs:1068-1100`), `!current` is checked before `FaultyReport::Silent`, so a stale `ReportAsk` is answered empty (`REPORT_END`) to free the credit instead of being swallowed or polluting `swallowed_asks`.
- **Per-ask cut judgement (`units.rs:126-145`, `table.rs:544-545`, `roles.rs:1087-1114`, `scenarios/explore.rs:158-211`):**
  - `FaultyReport::Silent | BadItems` records `(ReportAskId -> FaultyReport)` in `Table::faulty_asks` (keyed by `peer`, `peer_gen`, `holder`, `holder_gen`, `index`, `serial`), and cuts record `RebuildCutRecord` with `credit: Some((index, serial))` (or `None` for `Full::Credit | Full::Ring`).
  - `assert_cut_explained` (`explore.rs:166-193`) looks up the exact `ReportAskId`. Cycling `FaultyReport` back to `Normal` in the same generation cannot excuse a later cut on a different ask.
- **Generation reset of `cuts_checked` (`scenarios/combinations.rs:575, 647, 715-748`):**
  - Keying `cuts_checked` by `(holder_gen, count)` (and resetting to `(0, 0)` when `!sys.has(holder)`) prevents a restarted holder whose cut count matches its prior generation from skipping cut verification.
- **Sealing holders in `REBUILD` invariant (`check/machine.rs:603-616`):**
  - Checking `MemberState::Live | MemberState::Sealing` enforces the `STUCK_NS + RECOVERY_PERIOD_NS` bound on sealing holders waiting for active rebuilds before role handoff (D-159).

### 4. Exploration seeds (`scenarios/combinations.rs`)
- **`multi_page_seed` (`combinations.rs:590-592`):** Selects 14 x86-64 seeds (`17, 37, ..., 277`, disjoint from the 27 verify seeds and named regression seeds). Gives node 0 170 MSI remapping handles plus line 6 (171 IOMMU items = 7 pages at 28 items/page + 1 IOAPIC line), co-locates `IOMMU_ROLE` and `IOAPIC_ROLE` on node 1, and sets `stuck_ms = 30`.
- **`pace_multi_page` & `advance_paced` (`combinations.rs:1113-1278`):**
  - Active only on those 14 `multi_page_seed` runs when node 0 is healthy, idle of rebuilds/fences, and a holder has `>= 2` concurrent rebuilds with an ask in flight to node 0; defers node 0's `Timer`/`Ipi`/`Ring` events in `7 ms` (`< RECOVERY_PERIOD_NS = 10 ms`) increments so 7 pages span `~49 ms > stuck_ms`.
  - Because `seed < 286` runs exclusively on `Arch::X86_64`, `Hardware::Suspending`/`Hardware::Asleep` never occur (`system.rs:367`), and `Model::next_timer()` skips silent cores (`sched.rs:126-131`), so `advance_paced` advances faithfully without missing events or spinning (`guard < 20_000` verified on `seed_277`, and all recovery state combinations remain reached).
  - The remaining 844 seeds are completely untouched.

### 5. Vacuity checks & redone mutations
All checks and mutations were run independently in an isolated scratch copy (`/private/tmp/review-42/scratch/dodos-kernel`, clean at `43e5f07`, reverted after each mutation):

- **Baseline verification in scratch (all passed):**
  - `scenarios::pass40::` (8 passed, 0 failed)
  - `scenarios::pass41::` (8 passed, 0 failed)
  - `scenarios::pass42::` (8 passed, 0 failed)
  - `gate::race::tests::` (4 passed, 0 failed)
  - `check::tests::` (242 passed, 0 failed)
  - `scenarios::verify13::` (17 passed, 0 failed)
  - `scenarios::combinations::seed_277_of_pass_42_multi_page_rebuild_does_not_cut_healthy_node` (passed; also verified `guard < 19_999` in `advance_paced`)
  - `scenarios::combinations::judge_rebuild_cuts_resets_when_holder_restarts_with_same_cut_count` (passed)

- **Redone mutations (7/7 failed as expected):**
  1. **Seal park lock release (`model/src/gate/race.rs:298`):**
     - Mutation: Replace `end(self, Pc::Parked);` with `self.cores[c] = Pc::Parked;`.
     - Result: `gate::race::tests::seal_park_releases_the_gate_lock_before_stopping_the_core` **FAILED (`RC=101`)** at `model/src/gate/race.rs:556:9` with `wedge: Some([X(0), X(0), Resume])`.
  2. **D-170 `last_report` refresh (`model/src/roles.rs:519-526`):**
     - Mutation: Return `rebuild.asked_at` in `Model::rebuild_wait_since`.
     - Result: **FAILED (`RC=101`)** on all 4 tests:
       - `scenarios::pass42::a_healthy_node_answering_multi_page_report_is_not_cut_by_concurrent_rebuild` (`pass42.rs:303:5`: `expected 7 IOMMU pages + 1 IOAPIC page, got 7`)
       - `scenarios::pass42::a_late_report_restarts_a_waiting_rebuilds_stuck_ns_wait` (`pass42.rs:454:5`: `left: Some(22000000), right: Some(52000000)`) *(note: this test verifies `rebuild_wait_since` directly on a synthetic `Rebuild` value after consuming the late `Report`; the full `rebuild_step` and `check()` paths are exercised end-to-end by the other two `pass42` tests and `seed_277`)*
       - `scenarios::pass42::checker_uses_last_report_for_rebuild_deadline_invariant` (`pass42.rs:483:5`: `left: Err("REBUILD: a holder waited past STUCK_NS for a rebuild Report"), right: Ok(())`)
       - `scenarios::combinations::seed_277_of_pass_42_multi_page_rebuild_does_not_cut_healthy_node` (`combinations.rs:729:30`: healthy node `(0, gen 1)` cut on role 1 by holder 2 (`Deadline`)).
  3. **Preserve `asked_at` when blocked (`model/src/roles.rs:662`):**
     - Mutation: Replace `rebuild.asked_at.get_or_insert(now);` with `rebuild.asked_at = Some(now);` in the `blocking` branch.
     - Result: `scenarios::pass42::a_silent_node_with_two_concurrent_rebuilds_is_cut_by_both_within_stuck_ns` **FAILED (`RC=101`)** at `pass42.rs:353:5` (`left: 1, right: 2`).
  4. **Narrowed `cleared_faulty` (`model/src/check/tasks.rs:103-113`):**
     - Mutation: Broaden `cleared_faulty` back to `!self.swallowed_asks.is_empty()`.
     - Result: `scenarios::pass42::cleared_faulty_exempts_only_lines_cleared_by_a_cut_on_that_role` **FAILED (`RC=101`)** at `pass42.rs:617:10` (`cut on IOMMU_ROLE must not exempt IOAPIC_ROLE lines`).
  5. **Sealing holders in `REBUILD` check (`model/src/check/machine.rs:603-606`):**
     - Mutation: Restrict `MemberState::Live | MemberState::Sealing` back to `MemberState::Live`.
     - Result: `scenarios::pass42::checker_rejects_a_sealing_holder_waiting_past_stuck_ns` **FAILED (`RC=101`)** at `pass42.rs:696:5` (`left: Ok(()), right: Err("REBUILD: a holder waited past STUCK_NS for a rebuild Report")`).
  6. **Generation reset of `cuts_checked` (`model/src/scenarios/combinations.rs:723-725`):**
     - Mutation: Reset `entry.1 = 0` only when `cuts.len() < entry.1`.
     - Result: `scenarios::combinations::judge_rebuild_cuts_resets_when_holder_restarts_with_same_cut_count` **FAILED (`RC=101`)**.
  7. **Per-ask faulty judgement (`model/src/scenarios/explore.rs:166-180`):**
     - Mutation: Match any entry in `faulty_asks.0` with `(k.peer, k.peer_gen)` instead of exact `ReportAskId`.
     - Result: `scenarios::pass42::cut_after_peer_returns_to_normal_is_not_excused_by_earlier_faulty_ask` **FAILED (`RC=101`)** at `pass42.rs:745:9`.
