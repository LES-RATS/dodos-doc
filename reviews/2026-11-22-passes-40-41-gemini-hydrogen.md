# Review of Passes 40 and 41 of `dodos-kernel` (`47fda8e..18ce687`)

Reviewed `/Users/btw/Documents/repos/dodos-kernel` (`model`, `47fda8e..18ce687`, HEAD `18ce687`) against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` and `/Users/btw/Documents/repos/Docs/decisions/README.md` (D-168, D-169), `/private/tmp/pass40-report.md`, `/private/tmp/pass41-report.md`, and `/private/tmp/final-review/reports/` (`v1-*`, `v2-*`).

---

## Findings

### 1. [Major] D-168 (3) is not implemented in the gate model; its test cannot fail against gate code and its reported revert proof is false

- **Location:** `model/src/gate/parks.rs:149-184`, `model/src/gate/race.rs:93-104, 456-515` (commit `2bf3e77`)
- **Contract:** `Docs/architecture/kernel-interface.md:1414, 2206` ("the core's own park call, which releases the gate lock after this write and then stops the core without returning (D-168: nothing said the lock was released, and a lock left held would stop the resume's first gate call)").
- **What is wrong:**
  1. `2bf3e77` updated only the doc comments on `Machine::park_call` (`gate/parks.rs:149-159`) and `Machine::sealed_call` (`gate/parks.rs:161-184`). Neither `gate/parks.rs` nor `gate/race.rs` models the gate lock around seal's park or `park_for_seal`: `gate/race.rs:93-104` `Step` has only `X, Accept, Complete, Answer, Fence, R1, R6, Fill`, and `Member` (`gate/race.rs`) has no `Sealing`/`Sealed` or `SealPark` transition.
  2. `seal_park_releases_the_gate_lock_before_stopping_the_core` (`gate/race.rs:457-515`) defines a closure `run(release_on_park: bool)` that manually sets `start.lock = if release_on_park { None } else { Some(0) }` (`gate/race.rs:465`) with `start.cores = [Pc::Done, Pc::Attach(0)]` and asserts `ok.wedge == None` vs `wedged.wedge.is_some()`. That tests whether setting `State::lock = Some(0)` in the test harness blocks `Step::X(1)`, not any transition in the gate model.
  3. `/private/tmp/pass40-report.md` (item #3 under Revert-Verification Proofs) inaccurately states that `seal_park_releases_the_gate_lock_before_stopping_the_core` "failed without lock release in `Step::SealPark`", even though `git show 2bf3e77` contains no `Step::SealPark` and no non-test gate code changes in `gate/parks.rs` or `gate/race.rs`.
- **Scenario / Mutation:** `git show 2bf3e77 -- model/src/gate/parks.rs model/src/gate/race.rs` shows only doc-comment changes in `parks.rs` and the self-contained test in `race.rs`. Mutating or removing all seal-park code in `gate/parks.rs` (`park_call`, `sealed_call`) cannot fail `seal_park_releases_the_gate_lock_before_stopping_the_core` because the test never calls `gate/parks.rs` or any seal transition.

---

### 2. [Major] Concurrent multi-unit rebuilds cut a healthy multi-page node via the shared per-peer `ReportAsk` credit lock-out

- **Location:** `model/src/roles.rs:633-658, 668, 1165-1166`, `model/src/check/machine.rs:607-613`
- **Contract:** `Docs/architecture/kernel-interface.md:1883` ("it has at most one `ReportAsk` in flight to each node, whatever the number of units it rebuilds... a node from which no `Report` has come within `STUCK_NS` of the ask, or of the instant the cursor reached it while no credit was free, has its report ended as a malformed one (traced, code 11, what it would have claimed cleared), since a healthy kernel serves its kernel ring within the period of the recovery reserve, which the machine start-up puts below `STUCK_NS`").
- **What is wrong:** When a single holder concurrently rebuilds two or more unit roles (e.g., `IOMMU_ROLE` = 0 and `IOAPIC_ROLE` = 1) and healthy peer `z` has a multi-page report on role 0 (e.g., 171 MSI remapping handles = 7 pages at 28 items/page), role 0 holds the sole in-flight `ReportAsk` slot to `z` across 7 sequential ask/answer round trips. Meanwhile, role 1's `rebuild_step` reaches `z`, sees `busy == true` (`roles.rs:633-637`), sets `rebuild.asked_at = Some(now)` once (`roles.rs:640`), and never clears or refreshes `asked_at` when `z` actively answers role 0's `ReportAsk`s (`report_received` at `roles.rs:1165-1166` only clears `asked_at` on the role whose `Report` arrived). Once role 0's multi-page exchange spans `>= STUCK_NS` — even with `z` answering every single ask within `< RECOVERY_PERIOD_NS` (10 ms) — role 1 hits `roles.rs:641`, falsely cuts healthy node `z` with `RebuildCut::Deadline`, emits trace code 11 (`Refused`), and clears all of `z`'s claims on role 1 (`IOAPIC_ROLE`). Additionally, `System::check` (`check/machine.rs:607-613`) enforces `membership_now() <= at + stuck_ns + RECOVERY_PERIOD_NS` without allowing `busy` progress on another unit role, so fixing `roles.rs` alone without adjusting `check/machine.rs` would trip `check()`.
- **Concrete Reproducer (verified in scratch `pass41.rs`):**
  - 3-node x86-64 machine (`stuck_ms = 40`), node 1 holding both `IOMMU_ROLE` (role 0) and `IOAPIC_ROLE` (role 1).
  - Healthy node 0 claims 170 MSI handles (7 IOMMU report pages) and IOAPIC line 5.
  - Node 1 is killed; node 2 rebuilds roles 0 and 1 concurrently while node 0 answers every `ReportAsk` in 8 ms (5x faster than `stuck_ms = 40`, never hung, never harmed).
  - Observed result (test exit `0`): `node 2 rebuild_cuts: [(1, 0, 1, Deadline)]`, `iommu remap len: 171` (role 0 completed cleanly with all 7 pages), `ioapic line 5 kept? false` (healthy node 0's IOAPIC line 5 was permanently dropped by `RebuildCut::Deadline`).

---

### 3. [Minor] `faulty_report_used` is latched prematurely (even on stale asks) and grants a node-wide, cross-unit/cross-role line-check exemption

- **Location:** `model/src/roles.rs:1033-1039, 1055-1056`, `model/src/check/tasks.rs:104-155`
- **What is wrong:**
  1. In `Model::report_asked` (`roles.rs:1033-1039`), `self.faulty_report_used = true` is set for `FaultyReport::Silent` *before* checking `if !current` (`roles.rs:1041-1054`). A stale `ReportAsk` from an old epoch/non-holder triggers `faulty_report_used = true` even when no rebuild cut happens.
  2. `faulty_report_used` is a single `bool` per `Model` (cleared only on fresh start), and `cleared_faulty` (`check/tasks.rs:104-111`) exempts *every* claimed line on *every* IOAPIC/APLIC role whose `u.lines` lacks that GSI from `SETIPNUM`, `SOURCECFG`, and `LINE MASK` (`check/tasks.rs:115, 130, 152`). If a node used `FaultyReport::Silent`/`BadItems` on an IOMMU role (or before a later unrelated IOAPIC/APLIC `IrqClaim`), `cleared_faulty` disables all three line-controller checks for that node's lines for the rest of its generation, letting a real line-clearing/masking bug on IOAPIC/APLIC go unreported by `System::check()`.

---

### 4. [Minor] Exploration cut accounting misses normal-mode cuts after fault cycling and can skip post-restart cuts

- **Location:** `model/src/scenarios/combinations.rs:715-720, 1889-1900`, `model/src/check/machine.rs:603-605`
- **What is wrong:**
  1. `combinations.rs:1889-1900` (`faulty_acts % 10 == 0`) cycles `faulty_report` through `Normal -> Silent -> BadItems -> Normal` within the same generation `(f, fg)`, inserting `(f, fg)` into `self.faulty_silent` / `self.faulty_bad_items` (`combinations.rs:1891, 1895`) and never removing it when cycling back to `Normal`. Any subsequent `Deadline`/`BadItem` cut of `(f, fg)` while `faulty_report == Normal` is accepted as explained by `assert_cut_explained` (`explore.rs:198-204`).
  2. `judge_rebuild_cuts` (`combinations.rs:715-720`) resets `self.cuts_checked[holder]` only when `cuts.len() < self.cuts_checked[holder]`. If a holder dies, starts a fresh generation (`rebuild_cuts` reset to empty), and records `>= cuts_checked` new cuts before `judge_rebuild_cuts()` runs (or dies again before `note()`), the early cuts in `cuts[0..cuts_checked]` are never passed to `assert_cut_explained`.
  3. `check/machine.rs:603-605` skips the `REBUILD` deadline bound whenever `table.member(x).state() != MemberState::Live` (ignoring `MemberState::Sealing` holders that still execute `rebuild_step` until hand-over/seal finishes) or `Hardware != Running` (e.g., `Asleep` if `reserve_due` omitted waking for a deadline).

---

### 5. [Minor] `begin_resume` does not reset `seal_cursor` to `self.node`

- **Location:** `model/src/cores.rs:980-991`, `model/src/boot.rs:1458`
- **Contract:** `Docs/architecture/kernel-interface.md:1675` ("at its own index after a start").
- **What is wrong:** `Model::boot` / `Model::start` initialize `seal_cursor: node` (`boot.rs:1458`), but `Model::begin_resume` (`cores.rs:980-991`) leaves `seal_cursor` at whatever index it held before the seal. (`/private/tmp/pass40-report.md` also states it is reset on "boot / fresh start / resume".) The cyclic sweep bound of `⌈s / 2⌉` sweeps still holds from any starting index, so the protocol effect is benign unless another rule expects `seal_cursor == self.node` immediately after resume.

---

### 6. [Minor] Minor inaccuracy in `pass40-report.md` on `v2-C` #6 and `v2-C` #5

- **Location:** `/private/tmp/pass40-report.md` (`Part B`, `v2-C` #5 and #6); `model/src/system.rs:1256`, `model/src/nodes.rs:515`
- **What is wrong:**
  1. `pass40-report.md` lists `v2-C` #6 (`System::enter` resume precondition) as **Refuted**, whereas commit `dc2ea00` actually **fixed** it at `model/src/system.rs:1256` by adding `self.table().member(node).resuming() &&` before calling `begin_resume`.
  2. `pass40-report.md` correctly refutes `v2-C` #5 (`node_watch` with `Notify = 0`) using `kernel-interface.md:1823`, but writes "requiring only `write` on the node capability"; both the contract (`kernel-interface.md:1823`) and code (`nodes.rs:515`) require `Rights::READ`.

---

## Pass 40 Refutations Check

1. **`v2-C` #5 (`node_watch` clear without notify):** **Agree with refutation.** `kernel-interface.md:1823` explicitly specifies: *"Notify 0 unbinds, and succeeds if the index is unbound."* `nodes.rs:515-527` checks `Rights::READ` on the node cap, skips notify checks when `SlotAddr::NONE`, and clears the slot.
2. **`v2-C` #6 (`System::enter` resume precondition):** **Report mislabeled it as Refuted; actually Fixed in `dc2ea00`.** `system.rs:1256` now gates `begin_resume` on `self.table().member(node).resuming() &&`.
3. **`v1-D` #8 (`gate/race.rs` `LOCK` invariant):** **Agree with keeping as defense-in-depth.** `take_lock` enforces exclusivity on transitions, and keeping the explicit `LOCK` state check is valid defensive modeling.
4. **`v2-D` #1 (`unit_fails`), #2 (`sealing`):** **Agree** with the documentation fixes in `75a48b6` (`gate/faulty.rs`, `gate/events.rs`).
5. **`v1-G` #1 (`model/tests/verify7_deepseek.rs:532`, F10):** **Agree with refutation.** Under `page_shift = [12, 21, 30, 0]`, `E = 512`, chunk size is `2^21` (2 MiB), so a `Large2` leaf (`2^30` = 1 GiB) spans `2^30 / 2^21 = 512 = E` chunks (not `E^2`), whereas level 3 (`2^39`) spans `2^18 > E` chunks; `abi/src/lib.rs:542` enforces `<= E` chunks via `i > 2`.

---

## Checker & Exploration Assessment

- **Can a healthy node be cut without the checker noticing?** **Yes**, in the multi-unit concurrent-rebuild scenario of **Finding #2** (`roles.rs:633-658`, `check/machine.rs:607-613`): `System::check` sees `asked_at` advance past `stuck_ns` and permits (indeed demands) the deadline cut, and `combinations.rs`/`explore.rs` do not reach the >140-item single-peer multi-page threshold needed to trigger it during 7-page + dual-unit rebuilds. Also see **Finding #4** (`faulty_report_used` cycling back to `Normal`, `cuts_checked` on fast holder restart, `Sealing` holder skipped in `check/machine.rs:603`).
- **Can `⌈items / 28⌉ + 1` asks per node be exceeded without `System::check` noticing?** `System::check` is stateless and has no per-peer ask counter, so it cannot catch ask-count violations directly across steps. Within the transition logic itself (`roles.rs:1135-1152`), the bound is enforced for single-unit rebuilds: `advances` (`roles.rs:1145-1146`) requires `next == REPORT_END || (items.len() == REPORT_ITEMS && last.is_some_and(|l| next > l))`, `rising` (`roles.rs:1135-1140`) enforces strictly increasing item keys from `asked`, and `item_allowed` (`roles.rs:907-932, 1149-1151`) accepts only real items belonging to `from` (different item kinds occupy distinct high key bits, preventing key collisions, and any bad/malformed/late `Report` sets `rebuild.node = from + 1`).
- **Existing tests checked for vacuity:** Except for `gate::race::tests::seal_park_releases_the_gate_lock_before_stopping_the_core` (Finding #1), all new tests in `pass40.rs`, `pass41.rs`, `verify13.rs`, and `check/tests.rs` exercise real model/checker transitions with non-vacuous assertions (baseline tests ran and passed at `18ce687`: `pass40::` 8/8, `pass41::` 8/8, `verify13::a_report_that_is_not_the_last*` 2/2).

---

## Checked and Found Correct (with Redone Revert Proofs)

### Contract & Implementation Checks
- **D-168 (1) (`nodes.rs:806-821`, `boot.rs:1458`):** `sweep_sealed` walks `(1..=n).map(|step| (start + step) % n)` from `seal_cursor % n`, picks up to 2 sealed peers, and advances `seal_cursor = last`, guaranteeing every sealed node is read within `⌈s / 2⌉` sweeps.
- **D-168 (2) (`gate/grants.rs:184-194`):** `pin_revoking` moves `Revoking -> Pinned` iff the granter writes, `grant.state == GrantState::Revoking`, and `!self.use_released(...)` (`count > 0` on matching use entry), matching `kernel-interface.md:1389`.
- **D-169 (1) Ask deadline & ring watch (`roles.rs:573-595, 672-691`, `nodes.rs:872, 2311-2333`, `rings.rs:960-966`):**
  - `asked_at` records `membership_now()` (clock less stopped time), `reserve_due` schedules `asked_at + stuck_ns + stopped_time`, and `report_asked` does not alter `asked_at`.
  - Unconsumed `ReportAsk` opens `Watched::Ring { user: false, consumed }` in `observe_needed`.
  - Waiting with no credit/ring room (`Full::Credit | Full::Ring`) sets `asked_at` when cursor reaches `z` and cuts at `STUCK_NS`.
  - Late `Report` (`roles.rs:1111-1127`) frees the credit via `take_credit` and returns without modifying `rebuild.items` or unit state.
- **D-169 (2) Item checks (`roles.rs:907-932, 1149-1160`):** Validates `Device` (`rebuilt_attach_ok`: attach word *attached* with `root` + identifier word `(from, gen)`), `Handle` (`operands_allowed` with `InterruptCache { handle }`), and `Line` (`ioapic_role(gsi) == Some(role)` + `operands_allowed` with `Redirection`); any failure traces code 11 and cuts with `RebuildCut::BadItem`.
- **D-169 (3) 28-item rule (`roles.rs:1145-1148`, `verify13.rs:397-431`):** Non-final `Report` (`next != REPORT_END`) requires `items.len() == REPORT_ITEMS` (28) and `last.is_some_and(|l| next > l)`.

### Redone Revert Proofs (Executed in `/private/tmp/review-40-41/scratch/dodos-kernel`)

1. **`pass40::sweep_cursor_accuses_third_sealed_node_with_evidence_seal`**
   - Mutation: `model/src/nodes.rs:811` changed `let start = self.seal_cursor % n;` to `let start = 0;`.
   - Result: **FAILED (`RC=101`)** — `panicked at model/src/scenarios/pass40.rs:50:5: assertion left == right failed: left: None, right: Seal`.
2. **`pass41::the_rebuild_deadline_judges_on_the_clock_less_the_stopped_time`**
   - Mutation: `model/src/roles.rs:574` changed `self.membership_now() >= at + self.table.stuck_ns` to `self.now >= at + self.table.stuck_ns`.
   - Result: **FAILED (`RC=101`)** — `panicked at model/src/scenarios/pass41.rs:253:5: node 0 was cut during stopped time`.
3. **`pass41::a_report_with_one_bad_item_among_good_ones_ends_the_report_and_clears_its_claims`**
   - Mutation: `model/src/roles.rs:1152` changed `let good = structural && allowed;` to `let good = structural;`.
   - Result: **FAILED (`RC=101`)** — `panicked at model/src/scenarios/pass41.rs:526:9: assertion failed: m.sys.node(2).rebuild_cuts.0.iter().any(|&(r, p, _, reason)| r == IOMMU_ROLE && p == 0 && reason == RebuildCut::BadItem)`.
4. **`verify13::a_report_that_is_not_the_last_with_one_item_is_refused` & `with_no_item_is_refused`**
   - Mutation: `model/src/roles.rs:1145-1146` reverted `advances` to `next == REPORT_END || last.map_or(next > asked, |l| next > l);`.
   - Result: **FAILED (`RC=101`, both tests)** — `panicked at model/src/scenarios/verify13.rs:430:5` and `409:5` (`assertion left == right failed: left: 0, right: 1`).
5. **`check::tests::aspace_table_page_with_pinned_its_class_is_reported`**
   - Mutation: `model/src/check/table.rs:580` changed `c.class() > 16` to `c.raw() > 16`.
   - Result: **FAILED (`RC=101`)** — `panicked at model/src/check/tests.rs:3398:5: assertion left == right failed: left: Ok(()), right: Err("59: page classes")`.
