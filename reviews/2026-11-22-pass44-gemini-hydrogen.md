# Pass 44 Review — DodOS Reference Model (`6b657e4..05c1313`)

Reviewed `dodos-kernel` branch `model` (`6b657e4..05c1313`) against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` and `/Users/btw/Documents/repos/Docs/decisions/README.md`. All reproducer tests and mutations were run in `/private/tmp/review-44/scratch/dodos-kernel` (`CARGO_TARGET_DIR=/private/tmp/review-44/scratch/target`); both `/Users/btw/Documents/repos/dodos-kernel` and `/Users/btw/Documents/repos/Docs` remain clean.

---

## Findings

### 1. Follow-up timer interrupts after `TIME_EVENT_STEP` (16) and `Event::Wake` do not run "before anything else runs" (Major)

- **Location:** `model/src/system.rs:342-398`, `model/src/system.rs:578-581`, `model/src/system.rs:613-628`; `model/src/sched.rs:707-721`
- **Contract:** `Docs/architecture/kernel-interface.md:600` (*Due events and the hardware timer*): *"A timer interrupt processes at most 16 due events (provisional) ... If due events remain, the hardware timer is set to now, so the next interrupt comes at once and processes the next 16 before anything else runs."*
- **What is wrong:** Three related defects break "before anything else runs":
  1. **`Event::Wake | Event::ShallowReturn` loops on `has_due_past` (`instant < now`), not `has_due_at` (`instant <= now`):** At `system.rs:623`, the follow-up loop terminates as soon as `self.node(node).has_due_past(position)` is false. If a waking core has `<= 16` strictly-past due events plus at least one due event at `instant == now` (including a shallow return or latency-0 wake where `now == instant`), the loop exits after one iteration leaving `hw_timer == Some(now)` and a remaining due event at `now`.
  2. **`Event::Timer` processes 16 events and returns without draining follow-up interrupts at `now`:** At `system.rs:578-581`, `Event::Timer` calls `timer_interrupt` once (`TIME_EVENT_STEP = 16`) and returns control to the scheduler/caller (`System::events()` / `System::advance` / syscalls).
  3. **`System::events()` puts `Event::Ipi` ahead of `Event::Timer` and leaves other events/syscalls enabled while `hw_timer == Some(now)`:** In `System::events()` (`system.rs:342-398`), `Event::Ipi` is pushed at lines `342-353` before `Event::Timer` at lines `354-363`, followed by `Event::Sleep`, `Event::Action`, etc. `System::advance` picks `self.events().first()`, so when `hw_timer == Some(now)` remains after `Event::Wake` or `Event::Timer`, `Event::Ipi` (even on the same core/node) runs before the follow-up `Event::Timer`, and callers/`shuffle` can interleave syscalls or unrelated events before the remaining due events at `now` are drained.
- **Scenario proving it:**
  - `scenarios::pass44::review44_repro_1a_wake_leaves_due_at_now_behind_ipi` (in `/private/tmp/review-44/scratch/dodos-kernel`): on an ARM64 2-node system with a pending IPI on node 1 and two timers due at `wake_at` (`T1 = wake_at - 1`, `T2 = wake_at`), `Event::Wake` with 0 exit latency fires `T1`, stops on `!has_due_past(0)` while `hw_timer == Some(wake_at)` and `T2` is still armed at `now`, and `System::events().first()` returns `Event::Ipi { node: 1, position: 0 }` ahead of `Event::Timer { node: 1, position: 0 }`.
  - `scenarios::pass44::review44_repro_1b_timer_returns_after_16_and_runs_other_events_before_followup`: firing `Event::Timer` on node 1 with 17 timers at `now` and a pending IPI returns with 1 timer still armed (`hw_timer == Some(now)`), and `System::events().first()` fires `Event::Ipi { node: 1, position: 0 }` before the follow-up `Event::Timer`.

---

### 2. Checks 43 and 47 can still miss an un-taken due event on a silent-flagged running core or when `hw_timer <= Some(now)` (Major)

- **Location:** `model/src/check/sched.rs:84`, `model/src/check/sched.rs:92-108`, `model/src/check/sched.rs:255`, `model/src/check/sched.rs:257-266`; `model/src/check/machine.rs:275-281`
- **Contract:** `Docs/architecture/kernel-interface.md:600`: *"A due event is a replenishment whose instant is not after now, or a timer whose firing instant is not after now. ... Determinism: the reference model processes every due event at its instant before any call at that instant."*
- **What is wrong:**
  1. **Unconditional `silent` exemption on a `Hardware::Running` core:** `check_sched` (`sched.rs:84, 102-103`) and `check_timers` (`sched.rs:255, 262-265`) accept arbitrarily overdue throttled replenishments and armed timers whenever `core.silent` is `true`, without verifying that the core is not `Hardware::Running`. Meanwhile `check_machine` (`machine.rs:275-281`) filters `runners` with `!m.is_silent(p)`, so `.all(|(n, _)| n == slot)` passes vacuously if a core is `Hardware::Running` with its `CoreWord` still `Owned` while `core.silent == true`. A model bug that leaves `core.silent = true` on a running core freezes overdue timers and replenishments forever with `System::check() == Ok(())`.
  2. **No verification that `Event::Timer` actually processed due events when `hw_timer <= Some(now)`:** When `timer_due` (`hw_timer <= Some(self.now)`) holds—for instance when `> 16` due events keep `hw_timer == Some(now)` or before `Event::Timer` runs—Checks 43 and 47 accept every throttled context and armed timer at `<= now` (`sched.rs:99, 264`). Neither the checker nor `program_timers` detects if `Event::Timer` took fewer than `min(due, 16)` events (or took 0 events while keeping `hw_timer = Some(now)`).
- **Scenario / mutation proving it:**
  - `scenarios::pass44::review44_repro_2a_silent_running_core_passes_check_with_overdue_timer`: on a running core (`Hardware::Running`, `CoreState::Owned`) with `cores[0].silent = true`, an armed timer at `deadline` remains un-taken at `deadline + 100 * MS` and `System::check()` still returns `Ok(())`.
  - **Mutation on `model/src/sched.rs:829`:** changing `due.into_iter().take(TIME_EVENT_STEP)` to `due.into_iter().take(1)` on a node with 17 timers armed at `now` and firing `Event::Timer` leaves 16 due timers un-taken at `now`, yet `System::check()` returns `Ok(())`.

---

### 3. `Harm::accepts` accepts `CrashReason::CoreSilent` self-accusations wider than D-171 allows (Major)

- **Location:** `model/src/scenarios/mod.rs:362-407`, `model/src/scenarios/mod.rs:426-434`, `model/src/scenarios/mod.rs:475-478`, `model/src/scenarios/mod.rs:583-586`
- **Contract:** `Docs/architecture/kernel-interface.md:2207` and `Docs/decisions/README.md:181` (D-171): only an orphaned *multi-core* fresh start whose un-entered core never enters before `START_NS` after the first core's entry (`start_entered`) should self-accuse `CrashReason::CoreSilent` while still starting (before reaching `MemberState::Live`).
- **What is wrong:** `Harm::accepts` (`mod.rs:390-398`) accepts `Evidence::SelfReported` with `CrashReason::CoreSilent` whenever `orphan && !self.ever_live.contains(&at)`:
  1. **`Harm::starts` records 1-core starts and resumes too:** `call_by` (`mod.rs:461-478`) inserts every successful `Syscall::NodeStart` (mode fresh or resume, 1-core or multi-core) into `self.harm.starts`. A 1-core node never runs `watch_own_cores` (`cores.rs:713`: `if self.width() == 1 ... { return; }`), and a resume never sets `awaiting_entry`, so neither can legitimately self-accuse `CoreSilent` under D-171. Yet if a bug causes an orphaned 1-core start or orphaned resume to self-accuse `CoreSilent`, `Harm::accepts` accepts it.
  2. **`ever_live` is sampled only at `S::sample_bounds()` boundaries:** `self.harm.ever_live` is updated in `S::sample_bounds()` (`mod.rs:428-431`) after `System::advance(at)` returns (`run` / `run_by` step windows of `100 µs`–`1 ms` at `mod.rs:573-585`). An orphaned multi-core fresh start that transitions to `MemberState::Live` inside `advance` and then falsely self-accuses `CoreSilent` within the same `advance` window is never recorded in `ever_live`, so `Harm::accepts` still accepts the false self-accusation of a once-`Live` node.
- **Scenario proving it:**
  - `scenarios::pass44::review44_repro_3a_harm_accepts_coresilent_on_1core_orphan_and_live_orphan`: Part A kills and fresh-starts 1-core node 1 then hangs starter node 0; `harm.accepts(1, Member::new(Fencing, SelfReported, ...), Some((CrashReason::CoreSilent as u64, g1, 1)))` returns `true`. Part B fresh-starts 2-core node 1 on `[1, 2]`, hangs starter node 0 once starts are in flight, calls `m2.sys.advance(now + 10 * MS)` reaching `MemberState::Live` (before `sample_bounds()`), and shows `harm.accepts` still accepts a `CoreSilent` self-accusation because `ever_live` does not contain `(1, g2)`.

---

### 4. `time_event_step_16_in_recovery` and pressure seed 181 count routine `SWEEP_NS` ticks on a healthy cluster as "during a recovery" (Major)

- **Location:** `model/src/nodes.rs:2478-2491`, `model/src/sched.rs:795, 847-849`, `model/src/scenarios/bounds.rs:121-122`, `model/src/scenarios/combinations.rs:2559-2648`
- **What is wrong:**
  1. **`core0_recovery_due_now()` includes `sweep_due`:** In `nodes.rs:2480, 2490`, `core0_recovery_due_now()` returns `true` whenever `self.now >= self.next_sweep && self.others_exist()`. On a completely healthy cluster (`recovery_in_progress(None) == false`, all nodes `Live`, no fence/seal/rebuild/start), a routine periodic `SWEEP_NS` tick on core 0 sets `recovery_coincides = true` (`sched.rs:795`) and latches `time_event_step_16_in_recovery = true` (`sched.rs:848`), violating the counter specification (`bounds.rs:121-122`: *"Reached while a recovery (death, fence, seal, fresh start, or rebuild) involving a node concerned was in progress at the exact instant of the hit"*).
  2. **Pressure seed 181 (`combinations.rs:2559-2648`) passes with zero recovery via Coincidence A, and misses `TIME_EVENT_STEP = 17`:** Coincidence A (`combinations.rs:2559-2608`) arms 20 timers at `next_sweep` on a healthy node 0 and asserts `time_event_step_16_in_recovery` at line `2608`. Coincidence B (`2611-2648`, where `kill(1)` is actually fencing) has no `time_event_step_16*` or `armed_after` assertions and silently skips if `fence_at <= self.m.sys.now() + 1`. Consequently:
     - Removing Coincidence B (`2611-2648`) still passes `DODOS_SEED=181 every_combination_of_recovery_states_is_reached -- --ignored` (`rc=0`) with zero recovery during any `TIME_EVENT_STEP` hit.
     - Raising `TIME_EVENT_STEP` from `16` to `17` (`sched.rs:828-829`) still passes `DODOS_SEED=181` (`rc=0`): at `sweep_at`, 21 events are due (1 replenishment + 20 timers), so `take(17)` leaves 4 timers (`armed_after >= 20 - 16 = 4` still passes, and `total_due = 21 > 17` still sets `time_event_step_16`), and Coincidence B (20 due timers, leaving 3) has no assertion on `armed_after`. (Raising `TIME_EVENT_STEP` to `25` is caught at `combinations.rs:2602:13`.)
- **Scenario / mutations proving it:**
  - `scenarios::pass44::review44_repro_4_healthy_sweep_sets_time_event_step_16_in_recovery`: arms 17 timers at `next_sweep` on healthy node 0 (`!m.sys.node(0).recovery_in_progress(None)`), fires `Event::Timer { node: 0, position: 0 }`, and observes `m.bounds.time_event_step_16_in_recovery == true`.
  - Mutations on `DODOS_SEED=181` in scratch (`cargo test --release -p dodos-model --lib every_combination_of_recovery_states_is_reached -- --ignored`): deleting Coincidence B passed (`rc=0`); changing `TIME_EVENT_STEP` to `17` passed (`rc=0`).

---

### 5. Two additional `"Reached during a recovery"` counter inaccuracies (Minor)

- **Location:** `model/src/lib.rs:2121-2124`, `model/src/lib.rs:2132`, `model/src/rings.rs:929-1022`, `model/src/scenarios/bounds.rs:121-122`
- **What is wrong:**
  1. **Planned `RoleHand` counted as a recovery:** `Model::recovery_in_progress` (`lib.rs:2121-2124, 2132`) returns `true` whenever `!self.handing.is_empty()` or any role word has `RoleState::Handing` involving `self.node` or `peer`. A planned `Syscall::RoleHand` of a unit role between healthy `Live` nodes is not a recovery (death, fence, seal, fresh start, or rebuild).
  2. **`pending_step_capped` persists across steps into a later recovery:** `self.bound_hits.0.pending_step_capped` (`rings.rs:929`) is only cleared (`1022`) when a subsequent `send_pending()` finishes without hitting `PENDING_STEP`. If an earlier non-recovery flush hits `PENDING_STEP` (setting `pending_step_capped = true` and `pending_step_32_in_recovery = false`), and a later `send_pending()` runs while a target is recovering (`sealing`/`sealed`/`fencing`) with as few as **1** pending message (`sent < 32`), lines `961-965`, `993-995`, or `1003-1007` latch `pending_step_32_in_recovery = true` even though `PENDING_STEP` was never hit during recovery.
- **Scenario proving it:**
  - `scenarios::pass44::review44_repro_5_role_hand_and_stale_pending_step_in_recovery`: Part A calls `Syscall::RoleHand` for `IOMMU_ROLE` between healthy `Live` nodes 1 and 2 (`!m.sys.node(1).recovery_in_progress(None)` before the call) and shows both `node(1).recovery_in_progress(None)` and `node(2).recovery_in_progress(Some(1))` become `true`. Part B saturates user ring `1 -> 0` with `64` signals plus `33` `signal_pending` while all nodes are `Live`, drains ring `1 -> 0`, runs one reserve step on node 1 (`pending_step_32 = true`, `pending_step_32_in_recovery = false`, 1 `signal_pending` left), then seals node 0 (`seal(0)`) and runs `12 * MS`: the single-entry recovery flush sets `pending_step_32_in_recovery == true`.

---

### 6. `Model::clear_step` clears a line word still naming the dead generation instead of stopping the R6 walk (Minor)

- **Location:** `model/src/nodes.rs:1397-1408`, `model/src/nodes.rs:1761-1767`; `model/src/check/table.rs:83-91`
- **Contract:** `Docs/architecture/kernel-interface.md:1715` (*R6. Clear*): *"every line word, which must no longer name X's generation, since the holder's gate of its controller wrote it free in the call that masked it (R1); one that still names it stops the walk, as an attach word does (D-150: R6 freed it on the holder's `acked`, a signal; D-135)"*.
- **What is wrong:** D-172 (`clear_step` phases `0..=5`) correctly walks grants, uses, lines, attach words, and `irq_tables` before clearing chunks (`phase 2`) and `device_leaves` (`phase 3`), preventing any half-cleared page classes or device entries when R6 stops on a grant or attach word. However, `clear_step` still overwrites any `table.lines` entry equal to `taken` with `None` (`nodes.rs:1761-1767`) instead of stopping the walk, `r6_held_back` (`1397-1408`) ignores `table.lines`, and `check/table.rs:83-91` explicitly allows R6 (`state == 2`) to clear a line word belonging to a `Fenced` or `Dead` owner.
- **Scenario proving it:**
  - `scenarios::pass44::review44_repro_6_clear_step_clears_line_word_instead_of_stopping`: kills node 1, inserts a line word in `table.lines` owned by node 1's dying generation `g1`, verifies `r6_held_back(1, g1)` is `false`, runs `40 * MS`, and observes that R6 clears `table.lines[&9]` and transitions node 1 to `MemberState::Dead` instead of stopping the walk.

---

## Checked and Found Correct

- **D-171 core watching and checker rule (`cores.rs:719-744`, `cores.rs:902-908`, `check/node.rs:414-441`):**
  - `start_entered` is recorded only on the first `core_entered` of a fresh start (`!self.resuming && self.start_entered.is_none()` at `cores.rs:902-905`), `awaiting_entry` is initialized for cores of a fresh start (`nodes.rs`) and cleared on `core_entered` (`cores.rs:908`), and `watch_own_cores` (`cores.rs:720-734`) skips `watched.0` comparison for `awaiting_entry` cores while accusing at `now >= since.saturating_add(START_NS)` (setting `bound_hits.0.start_timeout`).
  - `check/node.rs:414-441` enforces D-171 when `self.cores.iter().any(|c| c.awaiting_entry)` before `since + START_NS`, allowing `CoreSilent` self-accusation only if another legitimate `CoreSilent` cause (`late_request` or `stale_entered` on an already-entered core) holds.
- **Resume stale-beacon safety (`cores.rs:902-963`, `nodes.rs:2212-2228`):** During a resume (`self.resuming == true`), `nodes.rs:2212-2213` keeps `self.ready = false` until `self.table.owned_unmarked(me, member.generation())` is true (meaning all cores have already entered `core_entered`), and `core_entered` (`cores.rs:949-963`) updates `beat_on(position)` / replenishes or refreshes `idle` and `hw_timer` before leaving. A core cannot run `watch_own_cores` against a pre-seal stale beacon on resume.
- **D-172 walk ordering in `Model::clear_step` (`nodes.rs:1718-1940`):** Every modeled stopping or page-naming entry (`grants` in phase `0`; `uses`, `lines`, `attach`, `irq_tables` in phase `1`) is walked before `owners` / `gate_words` / `classes` (phase `2`), `device_leaves` (phase `3`), `core_words` (phase `4`), and `MemberState::Dead` / non-unit roles (phase `5`). (Domain words live in per-IOMMU unit state rather than `Table`, and ITS words are not separately modeled in `Table`.)
- **`core.asleep` sync & Check (`system.rs:637-656`, `nodes.rs:2309-2311`, `check/machine.rs:249-260`):** `sync_sleep()` updates every core's `asleep` latency across `hang`, `wake_from_sleep`, `ShallowReturn`, and `gate_park_self`, and `check/machine.rs:249-260` verifies `core.asleep == expected_asleep` against `Hardware::Suspending` / `Hardware::Asleep` on every `System::check()`.
- **`held_after_step`, `assert_live`, `assert_cut_explained`, and `BoundHits` branches:**
  - `nodes.rs:2525-2527` properly guards `held_after_step = !capped && self.held_sendable()` so `check_node` does not falsely fail when `PENDING_STEP` (32) caps `send_pending()`.
  - `explore.rs:118-137` (`assert_live` / `assert_cut_explained`) only permits explained D-169 rebuild cuts.
  - Spot-checked `BoundHits` branches for `cspace_over_max_refused`, `tree_depth_65_refused`, `irq_193rd_refused`, `recovery_period_waited`, `sweep_2_sealed_capped`, `start_timeout`, `clear_step_again`: each fires only at its exact limit/branch.
- **Pressure offsets `71`, `104`, `148`, `225` (`combinations.rs`):** Offsets `71` (kernel ring reserve / 17th req credit during kill/rebuild/seal), `104` (grants/uses full during kill/rebuild), `148` Part B (36 `release_pending` flushed via `PENDING_STEP` while 2 grants/grantees are being killed/fenced — note Part A runs `seal`/`resume` after draining the 4 leftovers), and `225` (65th unit request refused during kill/fence/IOMMU teardown) genuinely overlap the bound with active recovery.

---

## Mutations & Tests Executed in Scratch (`/private/tmp/review-44/scratch/dodos-kernel`)

### Reproducer suite (`review44_repro_*`, unmodified `05c1313` + 7 reproducer tests in `model/src/scenarios/pass44.rs`)
Ran `CARGO_TARGET_DIR=/private/tmp/review-44/scratch/target cargo test -p dodos-model --lib review44_repro_`:
- **Result:** `test result: ok. 7 passed; 0 failed; 0 ignored` (`5.10s`):
  - `review44_repro_1a_wake_leaves_due_at_now_behind_ipi` ... ok
  - `review44_repro_1b_timer_returns_after_16_and_runs_other_events_before_followup` ... ok
  - `review44_repro_2a_silent_running_core_passes_check_with_overdue_timer` ... ok
  - `review44_repro_3a_harm_accepts_coresilent_on_1core_orphan_and_live_orphan` ... ok
  - `review44_repro_4_healthy_sweep_sets_time_event_step_16_in_recovery` ... ok
  - `review44_repro_5_role_hand_and_stale_pending_step_in_recovery` ... ok
  - `review44_repro_6_clear_step_clears_line_word_instead_of_stopping` ... ok

### Model/checker mutation proving Finding 2(b)
- `model/src/sched.rs:829`: mutated `due.into_iter().take(TIME_EVENT_STEP)` to `due.into_iter().take(1)` and ran `review44_repro_2b` (17 timers due at `now`, firing `Event::Timer`): **PASSED (`rc=0`)** (`System::check()` missed the 16 un-taken timers at `now`). Reverted afterwards.

### Unit-test fault-injection mutations (brief item 6 — 7 pass-44 tests sampled)
1. Disable `if self.cores[position].awaiting_entry` timeout wait in `cores.rs:720` -> `exp_2b_staggered_fresh_start_does_not_falsely_self_accuse_before_start_ns` **FAILED (`pass44.rs:111:13`)**.
2. Disable `start_entered + START_NS` self-accusation in `cores.rs:724-725` -> `unentered_core_at_fresh_start_self_accuses_at_start_ns` **FAILED (`pass44.rs:184:33`)**.
3. Disable D-171 check in `check/node.rs:414-415` -> `d171_checker_rejects_early_core_silent_self_accusation_for_unentered_core` **FAILED (`pass44.rs:211:10`)**.
4. Revert `armed.instant == self.now && timer_due` to `true` in `check/sched.rs:264` -> `checks_43_and_47_reject_at_now_without_hardware_timer_due_at_now` **FAILED (`pass44.rs:264:5`)**.
5. Remove `self.sync_sleep()` in `system.rs:741` (`hang`) -> `hang_sleeping_core_clears_asleep_and_passes_check` **FAILED (`pass44.rs:667:7`)**.
6. Clear chunks (phase 2) before attach words (phase 1) and disable `r6_held_back` in `nodes.rs` -> `r6_clear_step_removes_attach_words_before_clearing_page_classes` **FAILED (`rc=101`, `pass44.rs:731` / Check 88)**.
7. Disable `recovery_period_waited = true` in `sched.rs` -> `recovery_period_waited_after_full_10ms_stall_on_arm64_fence` **FAILED (`rc=101`)**.

### Pressure-seed mutations (`every_combination_of_recovery_states_is_reached -- --ignored`, brief item 5)
- `DODOS_SEED=71`, remove `RING_ANSWER_RESERVE` (`rings.rs:302` -> `(RING_KERNEL_ENTRIES, 0)`): **CAUGHT (`rc=101`, `combinations.rs:2092:13`)**.
- `DODOS_SEED=71`, let 17th request credit into send slot (`rings.rs:253` -> `0..REQUESTS_PER_PEER + 1`): **CAUGHT (`rc=101`, `combinations.rs:2102:28`)**.
- `DODOS_SEED=71`, resize `Peer::credits` by `+1` (`rings.rs:244,253`): **CAUGHT (`rc=101`, `scenarios/mod.rs:421:9`, `node 0: credits`)**.
- `DODOS_SEED=148`, raise `PENDING_STEP` (`rings.rs:921` -> `>= 33`): **CAUGHT (`rc=101`, `combinations.rs:2471:13`)**.
- `DODOS_SEED=181`, delete Coincidence B (`combinations.rs:2611-2648`): **PASSED (`rc=0`)** with zero recovery in progress.
- `DODOS_SEED=181`, raise `TIME_EVENT_STEP` to `17` (`sched.rs:828-829`): **MISSED (`rc=0`)**.
- `DODOS_SEED=181`, raise `TIME_EVENT_STEP` to `25` (`sched.rs:828-829`): **CAUGHT (`rc=101`, `combinations.rs:2602:13`)**.
