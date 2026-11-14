# Review of the One-Core Reference Model Tests and Invariants (`dodos-model`)

**Reviewer:** `gemini-4-argon`  
**Date:** 14 November 2026  
**Scope:** Independent review of the test suite ([`model/src/check/tests.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check/tests.rs), [`model/tests/calls.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs), [`model/tests/property.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs)) and state invariants ([`model/src/check.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs)) against the contract ([`Docs/architecture/kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)) and ABI ([`abi/src/lib.rs`](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs)).

---

## 1. Findings (Sorted by Importance)

### Finding 1: 18 mutations of contract rules in the model survive the entire test suite (`calls.rs`, `property.rs`, and `check.rs`)
- **Where:** [`model/tests/calls.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs), [`model/tests/property.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs), [`model/src/caps.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs), [`model/src/ipc.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs), [`model/src/lib.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs).
- **What is wrong:** Breaking 18 distinct rules of the contract in a scratch copy of `dodos-model` leaves all 211 tests (`check::tests`, `calls`, and `property`) passing:
  1. **Multi-capability IPC transfer (`deliver`, `ipc.rs:401-409`) is completely untested for `>= 2` delivered capabilities (`Mutant M43` and `Mutant M44` survive):**
     - **Mutant M43:** Replacing `let place = (window.cspace, index(i) as u32)` with `let place = (window.cspace, index(0) as u32)` (placing every transferred capability into the first slot of the receive range instead of `first + i`) **survives the entire test suite**, including `tests/property.rs`! Not a single test in `calls.rs` successfully delivers a message with 2, 3, or 4 capabilities (`transfer_is_all_or_nothing` and `transfer_is_dropped_when_the_range_is_shorter_than_the_list` both drop the 2 capabilities), and in `property.rs` whenever 2 capabilities happen to be delivered at once they are derived copies (`Transfer::Derive`) whose overwrite at `index(0)` happens before `new_cap` or in a way that never triggers across the 24 seeds.
     - **Mutant M44:** Replacing `caps.iter().all(fits)` with `caps.first().is_none_or(fits)` in `deliver` ([`ipc.rs:401`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L401)) **survives**: no test transfers 2 capabilities where the first capability passes `fits()` and the second violates `fits()`.
  2. **`reply_recv` badge 0 rule (`ipc.rs:150`) is untested (`Mutant M41` survives):**
     - Contract ([`kernel-interface.md:152`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L152)): *"A reply carries badge 0."* `send_on_a_reply_object_answers_the_caller_with_badge_0` ([`calls.rs:1645`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L1645)) tests `send` on a reply object, where the reply capability itself always has badge 0. In `reply_recv`, the call also takes an `endpoint` capability (which can be badged). Mutating `reply_recv` to pass the `endpoint` capability's badge instead of `0` into `Parcel::new(thread, message, ep_badge)` **survives all tests**, because every `reply_recv` test in `calls.rs` passes `EP` (whose badge is 0), and `property.rs` does not check the badge of replies received by callers!
  3. **`reply_recv` ordering between `answer` and `receive` (`ipc.rs:150-151`) is untested (`Mutant M42` survives):**
     - Contract ([`kernel-interface.md:147`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L147)): *"As `send` on the reply object, then as `recv` with the same reply object."* Mutating `reply_recv` to perform the `receive` delivery before the `answer` delivery **survives**, because no test in `calls.rs` moves a capability out of slot `X` in the reply of `reply_recv` while simultaneously using slot `X` as the receive range for the next incoming request.
  4. **`cap_delete` through another `CSpace` (`via != 0`) leaving an empty slot (`caps.rs:440`) is not verified (`Mutant M49` survives):**
     - Contract ([`kernel-interface.md:73, 93`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L73)): `cap_delete` makes the slot it acts on `Empty` (whereas capabilities removed as descendants become `Dead`). Mutating `remove` so that `cap_delete` via a `CSpace` capability (`via != 0` on a space with no bound thread) leaves `Slot::Dead` instead of `Slot::Empty` **survives all tests**, because `thread_whose_capability_space_is_dying_deletes_its_own_slots_only` ([`calls.rs:916`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L916)) only asserts `DONE` on `CapDelete(via(25, NT))` without checking whether slot `NT` became `Empty` (reusable) rather than `Dead`!
  5. **`cap_delete` on a `Slot::Dead` through a `CSpace` capability without `Rights::WRITE` (`caps.rs:144`) is untested (`Mutant M02` survives):**
     - `changing_a_slot_through_a_cspace_capability_needs_write` ([`calls.rs:354`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L354)) only tests `CapDelete` through a read-only `CSpace` capability on a *full* slot (`via(31, 5)`), never on a *dead* slot.
  6. **Multi-step `cap_delete` by a thread whose own `CSpace` is dying (`caps.rs:142`) is untested (`Mutant M39` survives):**
     - `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` ([`calls.rs:899`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L899)) only calls `cap_delete` on a slot in a dying `CSpace` that finishes in 1 step (1 child). If the slot has `>= 32` descendants so the first `cap_delete` sets `cap.dying = true` and returns `Error::Again`, refusing the second `cap_delete` call when `self.dying(own) && cap.dying` survives.
  7. **Counting the slot holding a dying `CSpace`'s own root capability in `REMOVAL_SLOTS` (`caps.rs:522`) is untested (`Mutant M30` survives):**
     - In `swept()`, not decrementing `slots` when skipping over `Slot::Full(held)` where `held == cap` (the dying `CSpace`'s own root capability) survives.
  8. **Order of checks in `reply_recv`, `listed`, and `cap_derive` (`Mutants M24, M07, M03, M06` survive):**
     - **Mutant M24 (`ipc.rs:139`):** In `reply_recv`, checking `endpoint` before `self.listed(thread, &message.caps)` survives because `calls.rs:2610` only tests an invalid *header* against a dead `endpoint`, never a bad *listed capability slot* in `message.caps` against a bad `endpoint` in `reply_recv`.
     - **Mutant M07 (`ipc.rs:285`):** In `listed()`, for `Transfer::Derive(slot, rights)`, checking `self.depth(cap) >= TREE_DEPTH` (`Invalid`) before `self.caps[&cap].rights.derive(rights)` (`Denied`) survives.
     - **Mutants M03 (`caps.rs:106`) and M06 (`ipc.rs:286`):** Swapping the two badge checks in `cap_derive` (unobservable on valid states because only `Endpoint`/`Notify` can have `kept != 0`) and swapping duplicate-slot vs depth check in `listed` (both return `Error::Invalid`) survive.
  9. **Object sizes and alignments in `untyped_retype` (`caps.rs:41-77`) (`Mutants M11, M12, M13, M21, M22, M47, M48` survive):**
     - `Thread` size (`1024` → `512`, **M11**) and alignment (`1024` → `64`, **M47**) survive.
     - `Sched` size (`128` → `64`, **M12**) survives.
     - `Endpoint | Reply | Notify` size (`64` → `128`, **M13**) survives (every test in `calls.rs` follows a single `Endpoint` with a 4 KB-aligned `ASpace` or `Frame`, which pads the watermark to `4096` regardless of whether `Endpoint` took 64 or 128 bytes).
     - `CSpace` directory minimum size (`8` → `16` bytes for 1 segment, **M21**) and directory alignment (`bytes.min(PAGE)` → `PAGE` (**M22**) or `8` (**M48**)) survive.
- **How you know:** Confirmed by running all 50 mutants in the scratch copy (`task-75`, `task-82`, `task-93`).
- **Suggested tests:** Add deterministic tests in [`model/tests/calls.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs) for each of the 16 observable surviving mutants (listed in the Mutation Log table in Section 2).

---

### Finding 2: Property test generator never marks any non-`Untyped`, non-`CSpace` object or any copy capability as `dying`
- **Where:** [`model/tests/property.rs:235-242`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L235-L242) (`Generator::call`) and [`model/tests/property.rs:531-539`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L531-L539) (`run`).
- **What is wrong:**
  1. Because `REMOVAL_STEP` is 32 and `REMOVAL_SLOTS` is 128, a `cap_delete` or `cap_revoke` call only returns `Error::Again` (leaving a capability or object `dying` across steps) if the subtree has more than 32 capabilities/waiters to remove or sweeps a `CSpace` with more than 128 slots examined.
  2. In `Generator`, objects of kinds `Endpoint`, `Reply`, `Notify`, `Thread`, `Frame`, `ASpace`, and `Sched` never accumulate 32 derived children or 32 waiters, and when a `CSpace` with 2 segments (256 slots) is swept, any non-`CSpace` root capability inside it has `< 32` children and is completely removed in the same `cap_delete` call that first reaches it.
  3. Consequently, across all 24 seeds × 5,000 steps (120,000 calls):
     - **0 steps** ever have a dying `Endpoint`, `Reply`, `Notify`, `Thread`, `Frame`, `ASpace`, or `Sched` (`dying_by_kind` is `[4754, 20999, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]`, i.e. only `Untyped` and `CSpace`).
     - **0 steps** ever have a dying non-root capability (a copy under `cap_delete` whose object is not dying).
     - Invariant 22 (`"22: thread of a dying reply object"`) is never exercised on an actual dying reply object during the property test.
- **How you know:** Confirmed by a run in a scratch copy after adding per-step counters (`debug_stats` and `debug_extra2`) to [`model/src/lib.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs) and [`model/tests/property.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs).
- **Suggested test or change:** In [`model/tests/property.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs), add a generator action (or burst mode) that occasionally derives 33 copies of an existing `Reply`, `Endpoint`, or `Notify` capability (or a copy capability) into a grown `CSpace` and invokes `CapDelete` or `CapRevoke` on it.

---

### Finding 3: Property test generator reaches a maximum tree depth of 7 (out of 64) and a maximum removal walk of 5 (out of 192), and only 2.2% of non-boot-CSpace thread calls succeed
- **Where:** [`model/tests/property.rs:95-178`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L95-L178) (`Generator`) and [`model/tests/property.rs:480-543`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L480-L543) (`run`).
- **What is wrong:**
  1. **Shallow trees and walks:** `Generator::held` picks a start-up capability at depth 1 with 40% probability (for `UNTYPED` and `CSPACE`), and `Generator::slot` picks uniformly among 8 slots per class (`18 + 8 * n + c`), frequently overwriting or deleting slots. Across all 120,000 steps:
     - Maximum capability tree depth reached (`max_depth`) is **7** (limit `TREE_DEPTH = 64`).
     - Maximum `CSpace` root depth (`max_space_depth`) is **5**.
     - Maximum removal walk (`model.longest_walk()`) is **5** (limit `LONGEST_WALK = 192`).
     - Depth-64 refusal in `fits()` and `listed()` is **never** reached by `tests/property.rs`.
  2. **Threads in other capability spaces almost always fail:** `of_use` in [`model/tests/property.rs:489`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L489) checks `model.object_at(*thread, SlotAddr::own(START_SLOT_CSPACE)).is_some()` (slot 1), which is empty in newly created `CSpace`s unless a capability happens to be placed in slot 1. Even when a thread bound to a non-boot `CSpace` is picked (4,252 steps across 120,000 calls), `Generator` still biases `held()` and `memory()` toward `START_SLOT_CSPACE` (slot 1) and `START_SLOT_FIRST` (slot 16), which only exist in the boot `CSpace`. Thus only **96 out of 4,252 calls (2.25%)** made by threads in non-boot capability spaces succeed.
  3. **Call and argument shapes never produced by `Generator`:**
     - `PageSize::Size2M` and `PageSize::Size1G` in `UntypedRetype` (hardcoded to `PageSize::Size4K` at [`model/tests/property.rs:252`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L252)).
     - `ObjectKind::Irq`, `IoPorts`, `IoSpace`, `Task`, `Core`, `Debug` in `UntypedRetype` (`KINDS` only includes `Timer` among unsupported kinds).
     - `CapDerive` with `badge >= 8` (`self.rng.below(8)`).
     - `Message` with `words.len()` between `4` and `64` (`words` is either `0..4` or `65`, never testing `4..=64` or the `REG_WORDS = 6` boundary).
     - `Syscall::Call` or `Syscall::ReplyRecv` in the `at_risk` depth-refusal tracking (`at_risk` only inspects `CapMove` and `Send`, never `Call`, `ReplyRecv`, `CapDerive`, or `UntypedRetype`).
- **How you know:** Confirmed by running the instrumented property test in the scratch copy and reading [`model/tests/property.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs).
- **Suggested test or change:**
  - In `Generator`, avoid hardcoding `START_SLOT_FIRST` and `START_SLOT_CSPACE` when the running thread's `CSpace` is not the boot `CSpace`.
  - Include `PageSize::Size2M` and `PageSize::Size1G` in `Generator::call` for `UntypedRetype`, message lengths in `4..=64`, and badges with high bits (`1 << 63`).
  - Assert a minimum reached `longest_walk` and `max_depth` in `invariants_hold_after_every_call_of_random_sequences`.

---

### Finding 4: Coverage counters in `tests/property.rs` double-count woken outcomes across multiple steps
- **Where:** [`model/tests/property.rs:531-540`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs#L531-L540) (`run`).
- **What is wrong:** As noted by the comment `// Counted at every step until the woken thread makes its next call`, at the end of every step the loop iterates over all runnable threads and calls `reached.note(woken)` and `reached.woken_gone += (*woken == Err(Error::Gone)) as u32`.
  - If a woken thread is not immediately chosen to run on the next step, its `woken(thread)` outcome remains `Some(...)` and is counted again on every subsequent step until that thread runs.
  - Across the 24 seeds, our instrumentation shows:
    - `woken_gone` is reported as `70`, whereas actual transitions to `Some(Err(Error::Gone))` occur **33** times.
    - `with_caps` is reported as `96`, whereas actual deliveries with capabilities are **48** (1 synchronous + 47 woken transitions).
    - `dropped` is reported as `107`, whereas actual deliveries with `FLAG_CAPS_DROPPED` are **51** (3 synchronous + 48 woken transitions).
    - `notifications` is reported as `59`, whereas actual notification deliveries via `recv`/`reply_recv` are **47** (36 synchronous + 11 woken transitions).
- **How you know:** Confirmed by comparing the original `Reached` counters against transition-only counters in the scratch copy. (All four underlying events are still genuinely > 0, so the coverage assertions do not pass on zero occurrences, though they overstate the count by ~2×.)
- **Suggested test or change:** Count woken outcomes only when a thread transitions from waiting (`!runnable` before `apply`) to woken (`woken(thread).is_some()` after `apply`).

---

### Finding 5: Five tests in `calls.rs` have assertions weaker than their names or pass for the wrong reason
- **Where:** [`model/tests/calls.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs) at lines 425, 1483, 2225, 2493, and 2685.
- **What is wrong:**
  1. [`segment_is_aligned_on_4_kb`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L2685-L2694): Creates a 16 KB untyped (`s(31)`), creates a `CSpace` from it (taking 8 bytes for the directory, watermark = 8), calls `cspace_grow` (which aligns to 4 KB and takes 4 KB, watermark = 8,192), and then creates two `ASpace`s (4 KB each, aligned on 4 KB) before asserting `NoMemory`. **Bug in the test:** Even if `cspace_grow` did *not* align the 4 KB segment on 4 KB (so the segment occupied `8..4104`), the subsequent `ASpace` creation in `s(32)` aligns the watermark to 4 KB anyway (`8,192..12,288`)! Thus `segment_is_aligned_on_4_kb` passes even if `cspace_grow` has alignment `8` instead of `4096` (confirmed by **Mutant M45**, which was killed only by `segments_go_back_to_the_untyped_when_the_cspace_is_destroyed`, not by `segment_is_aligned_on_4_kb`!).
  2. [`cspace_grow_takes_only_the_untyped_the_cspace_was_created_from`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L425-L438): Includes `k.no(from(s(30)), Error::Invalid)` and `k.no(grow(START_SLOT_FIRST), Error::Invalid)` (passing wrong object kinds for `untyped` and `cspace`), which fail in `self.object(...)` kind check before reaching `self.objects[&space].from != Some(untyped)` (though `s(31)` and `DEV` in the same test do reach the actual rule).
  3. [`thread_configure_binds_the_capability_space`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L1483-L1493) and [`notify_bind_with_endpoint_0_removes_the_binding`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L2225-L2236): Use `.map(drop)` (`assert_eq!(k.on(other, Syscall::CapInspect(s(31))).map(drop), Ok(()))` and `assert_eq!(k.go(recv(EP, RP, Range::NONE)).map(drop), Ok(()))`), discarding the `Output` variant instead of asserting `Ok(Output::Inspect { ... })` and `WAITS` (`Ok(Output::Waits)`).
  4. [`reply_recv_transfers_capabilities_both_ways_and_is_not_told_of_a_drop`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L2493): Uses `assert!(k.on(second, Syscall::CapInspect(s(50))).is_ok())` instead of checking the inspected capability.
- **How you know:** Confirmed by reading [`model/tests/calls.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs) and running **Mutant M45** (where `segment_is_aligned_on_4_kb` passed even with `cspace_grow` alignment set to 8 bytes).
- **Suggested change:** In `segment_is_aligned_on_4_kb`, allocate a 64-byte `Endpoint` (`retype(s(31), Endpoint, 0, s(34))`) right after `cspace_grow` and one `ASpace` so that `segment_is_aligned_on_4_kb` itself fails if `cspace_grow` does not align on 4 KB; replace `.map(drop)` and `.is_ok()` with exact `Output` assertions.

---

### Finding 6: One test in `check/tests.rs` fails for the wrong invariant (`6` instead of `27`), and 15 sub-conditions in `check.rs` are not guarded by any test in `check/tests.rs`
- **Where:** [`model/src/check/tests.rs:563-577`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check/tests.rs#L563-L577) (`sweep_that_stands_beyond_the_table_is_reported`) and [`model/src/check.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs).
- **What is wrong:**
  1. **Test that passes for the wrong reason:** In [`sweep_that_stands_beyond_the_table_is_reported`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check/tests.rs#L563-L577), the test intends to spoil invariant `"27: index of the sweep"` (`(1..=slots.max(1)).contains(&sweep.next)`) by setting `next = 129`. To avoid triggering `"27: full slot behind the sweep"` first, the test overwrites all non-root slots in `at.space` with `Slot::Dead`, **without removing those capabilities from `m.caps`**. Because `check_tree()` runs *before* `check_slots()`, `check_tree()` immediately fails with `"6: slot of a capability"`! The author of the test wrote `assert_eq!(broken, "6: slot of a capability")` at line 576, so the test never reaches `check_slots()` and never tests `"27: index of the sweep"` for `sweep.next > slots`!
  2. **15 sub-conditions in `check.rs` whose removal is not caught by `check/tests.rs`:**
     - **Invariant 1 (`check.rs:118`):** `ensure(listed == 1, "1: parent lists its child once")` — only tested for `listed == 0` (`.clear()`), never for `listed == 2` (a child listed twice in `parent.children`). Mutating `listed == 1` to `listed >= 1` survives (**Mutant C9**).
     - **Invariant 7 (`check.rs:214-215`):** `let max = space.max != 0 && space.max.is_multiple_of(CSPACE_SEGMENT_SLOTS); ensure(max && space.max <= 1 << 20, "7: maximum")` — only tested for `space.max = 200` (not a multiple of 128). Neither `space.max == 0` (when `slots` is empty) nor `space.max > 1 << 20` (e.g. `(1 << 20) + 128`) is tested in `check/tests.rs` (**Mutants C2, C3** survive).
     - **Invariant 10 (`check.rs:187` and `228-235`):**
       - Line 187 (`let object = self.objects.get(&id).ok_or("10: state without an object")?` in `check_slots`) is only reached for a `CSpace` without an entry in `self.objects`, which is never tested in `check/tests.rs` (**Mutant C10** survives).
       - Lines 228–235 (`has_state` in `check_objects`) is only tested by removing `m.replies.remove(&at.reply)`; removing the `Untyped`, `CSpace`, `Thread`, `Endpoint`, or `Notify` branches of `has_state` survives (**Mutants C12–C16**).
     - **Invariant 25 (`check.rs:244-245`):** `let inherits = self.untypeds.get(&id).is_none_or(|child| child.device); ensure(!device || plain && inherits, "25: kind on device memory")` — `check/tests.rs` only tests creating a `Notify` on device memory (`!plain`), never a child `Untyped` of device memory with `child.device == false` (`!inherits`). Mutating `plain && inherits` to `plain` survives (**Mutant C8**).
     - **Invariant 26 (`check.rs:141`):** `ensure(id.0.max(cap.object.0) < self.next_id, "26: identity")` — `check/tests.rs` sets `m.next_id = 3`, which violates both `id.0 < self.next_id` and `cap.object.0 < self.next_id`. Because `CapId` is allocated *after* `ObjId` in `Model::create`, `id.0 > cap.object.0` always holds unless `cap.object.0` is specifically spoiled to `>= self.next_id`. Mutating `id.0.max(cap.object.0) < self.next_id` to `id.0 < self.next_id` survives (**Mutant C1**).
     - **Invariant 27 (`check.rs:210`):** `let within = |sweep: &crate::Sweep| (1..=slots.max(1)).contains(&sweep.next)` — because of item 1 above, mutating the upper bound `=slots.max(1)` to unbounded `(1..)` survives (**Mutant C11**).
     - **Invariant 29 (`check.rs:323, 336, 371, 374`):**
       - `within(window)` on `ReplyState::Armed` (`check.rs:336`) is never tested in `check/tests.rs` (**Mutant C4** survives).
       - `within(window)` on `Wait::Recv` (`check.rs:374`) is never tested in `check/tests.rs` (**Mutant C5** survives).
       - `parcel.words.len() <= MAX_WORDS && parcel.caps.len() <= MAX_CAPS` on `Wait::Call` (`check.rs:371`) is never tested in `check/tests.rs` (**Mutants C6, C17, C18** survive).
       - `window.first != 0` inside `within(window)` (`check.rs:323`) is never tested with `window.count > 0 && window.first == 0` in `check/tests.rs` (**Mutant C7** survives).
- **How you know:** Confirmed by running all 18 `check.rs` sub-condition mutants (`C1`–`C18`) and all 54 invariant tag mutants (`task-58`, `task-64`, `task-70`) in the scratch copy.
- **Suggested fix and tests:**
  - In `sweep_that_stands_beyond_the_table_is_reported` ([`model/src/check/tests.rs:563-577`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check/tests.rs#L563-L577)), properly remove the non-root capabilities (or call `Syscall::CapDelete` on all non-CSpace slots of a fresh `Model::boot()`) before calling `dying_space(m, at, 129)`, and assert `"27: index of the sweep"`.
  - Add unit tests in `check/tests.rs` for each of the unguarded sub-conditions listed above (`space.max > 1 << 20`, `child.device = false` on a child untyped of device memory, `parcel.words` / `parcel.caps` over limits in `Wait::Call`, invalid `window` in `Wait::Recv` and `ReplyState::Armed`, and `window.first = 0, window.count = 1`).

---

### Finding 7: Contract properties that hold in every reachable state but are not checked in `Model::check`
- **Where:** [`model/src/check.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs).
- **What is wrong:** Comparing the contract ([`Docs/architecture/kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)) against `Model::check` identifies 6 state properties guaranteed by the contract that are not checked by any invariant in `check.rs`:
  1. **Start-up capability space is never from an untyped and its size is fixed (`kernel-interface.md:90`):** Any `CSpace` with `object.from.is_none()` (the start-up `CSpace`) has `space.slots.len() == space.max as usize` (`CSPACE_SEGMENT_SLOTS = 128` slots).
  2. **Watermark lower bound and alignment (`kernel-interface.md:121`, `caps.rs:41-79`):** Invariant 18 checks `untyped.watermark <= untyped.bytes` and `(untyped.watermark == 0) == (untyped.live == 0)`, but does not check that `untyped.watermark` is at least the sum of the footprints of all currently live objects and `CSpace` segments created from that `untyped` (`untyped.watermark >= sum_of_live_bytes`), nor that `untyped.watermark` is a multiple of 8 (the smallest object/directory size).
  3. **Waiting or woken threads are always bound to a capability space (or a destroyed one) (`kernel-interface.md:131-135`):** Invariant 16 checks `let bound = thread.suspended || thread.cspace.is_some()`, which allows a *suspended* thread with `thread.cspace == None` to be in a wait queue (`thread.wait != Wait::None`) or have `thread.outcome.is_some()`. Under the contract, a thread can only make a call while running (which requires `thread.cspace.is_some()`), and `thread_configure` never sets `cspace` back to `None`. Therefore, `(thread.wait == Wait::None && thread.outcome.is_none()) || thread.cspace.is_some()` holds in every reachable state.
  4. **Woken outcome validity (`lib.rs:175-177`):** If `thread.outcome` is `Some(outcome)`:
     - `outcome != Err(Error::Ok)` (documented at `lib.rs:176`: "`Err(Error::Ok)` never occurs") and `outcome != Ok(Output::Waits)`.
     - Specifically, a woken outcome is *only* ever `Err(Error::Gone)`, `Ok(Output::Word(w))` with `w != 0`, or `Ok(Output::Message(delivery))` where `delivery.words.len() == delivery.received.header.words()`.
  5. **Waiting `Parcel` capability list validity (`kernel-interface.md:160, 163`):** Invariant 29 checks `parcel.words.len() <= MAX_WORDS && parcel.caps.len() <= MAX_CAPS` and `parcel.sender == id` for `Wait::Call { parcel, .. }`, but does not check that every `Transfer::Derive(_, rights)` in `parcel.caps` has valid `Rights` bits (`Rights::from_bits(rights.bits()).is_some()`).
  6. **Object creation order (`lib.rs:35, 38`, `caps.rs:308, 361`):** Invariant 1 checks `parent < id` for `CapId`s, and Invariant 26 checks `id.0.max(cap.object.0) < self.next_id`, but `check.rs` does not check that for every object with `Some(from) = object.from`, `from < id` (an object is always younger than the `Untyped` it was created from) and `id.0 < object.root.0`.
- **How you know:** Confirmed by reading [`model/src/check.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs) and [`Docs/architecture/kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **Suggested invariants:** Add to `check_waits` and `check_memory`:
  - `(thread.wait == Wait::None && thread.outcome.is_none()) || thread.cspace.is_some()`;
  - `thread.outcome` is only `Err(Error::Gone)`, `Ok(Output::Word(w))` with `w != 0`, or `Ok(Output::Message(_))`;
  - `untyped.watermark >= live_bytes_sum` and `untyped.watermark.is_multiple_of(8)` in `check_memory()`.

---

## 2. Mutation Log

We tested **50 mutations** of the model's rules in [`model/src/lib.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs), [`model/src/caps.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs), and [`model/src/ipc.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs) (plus **18 sub-condition mutations** and **54 invariant-tag mutations** in [`model/src/check.rs`](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs), logged in Finding 6) in the isolated scratch copy.

### 2.1 Model Rule Mutations (`lib.rs`, `caps.rs`, `ipc.rs`) — 50 Mutants (32 Killed, 18 Survived)

| # | Mutant ID & File | Rule Broken / Mutation | Result | Killed By (or Missing Test if Survived) |
|---|---|---|---|---|
| 1 | `M01` (`caps.rs:144`) | `cap_delete` uses `Access::Read` instead of `Access::Write` for all slots | **KILLED** | `changing_a_slot_through_a_cspace_capability_needs_write` |
| 2 | `M02` (`caps.rs:144`) | `cap_delete` uses `Access::Read` when target slot is `Slot::Dead` | **SURVIVED** | Missing test: `cap_delete` on a `Slot::Dead` via a `CSpace` cap without `WRITE` right |
| 3 | `M03` (`caps.rs:106`) | `cap_derive` checks `badge != kept` (`Denied`) before `kind != Endpoint/Notify` (`Invalid`) | **SURVIVED** | Unobservable on valid states (`kept != 0` only holds on `Endpoint`/`Notify`) |
| 4 | `M04` (`caps.rs:106`) | `cap_derive` checks `fits` (depth) before badge kind/value checks | **KILLED** | `plain_arguments_of_cap_derive_are_judged_in_the_order_of_the_table` |
| 5 | `M05` (`lib.rs:621`) | `window` checks `count > MAX_CAPS` (`Invalid`) before `space(Access::Write)` (`Denied`) | **KILLED** | `arguments_of_call_are_checked_in_the_order_of_the_table` |
| 6 | `M06` (`ipc.rs:286`) | `listed` checks duplicate slot (`Invalid`) before `depth >= TREE_DEPTH` (`Invalid`) | **SURVIVED** | Unobservable because both return `Error::Invalid` |
| 7 | `M07` (`ipc.rs:285`) | `listed` checks `depth >= TREE_DEPTH` (`Invalid`) before `rights.derive` (`Denied`) | **SURVIVED** | Missing test: IPC `Transfer::Derive` at depth 64 with excessive rights |
| 8 | `M08` (`caps.rs:54`) | `CSpace` directory bytes not rounded up to power of two | **KILLED** | `cspace_directory_is_rounded_up_to_a_power_of_two` |
| 9 | `M09` (`caps.rs:55`) | Off-by-one on `CSpace` max slots: `size < 1 << 20` instead of `size <= 1 << 20` | **KILLED** | `cspace_maximum_is_a_whole_number_of_segments_up_to_2_to_the_20` (+2 more) |
| 10 | `M10` (`caps.rs:44`) | Off-by-one on `Untyped` min size: `size > PAGE` (4096) instead of `size >= PAGE` | **KILLED** | `child_untyped_is_a_power_of_two_of_at_least_4_kb` (+11 more) |
| 11 | `M11` (`caps.rs:60`) | `Thread` object footprint changed from `1024` to `512` bytes | **SURVIVED** | Missing test: `Thread` 1 KB size in `untyped_retype` |
| 12 | `M12` (`caps.rs:61`) | `Sched` object footprint changed from `128` to `64` bytes | **SURVIVED** | Missing test: `Sched` 128 B size in `untyped_retype` |
| 13 | `M13` (`caps.rs:62`) | `Endpoint \| Reply \| Notify` footprint changed from `64` to `128` bytes | **SURVIVED** | Missing test: 64 B footprint of `Endpoint`/`Reply`/`Notify` |
| 14 | `M14` (`caps.rs:18`) | Off-by-one on `REMOVAL_SLOTS`: `127` instead of `128` | **KILLED** | `removal_examines_at_most_128_slots_of_dying_spaces_per_call` |
| 15 | `M15` (`caps.rs:18`) | Off-by-one on `REMOVAL_SLOTS`: `129` instead of `128` | **KILLED** | `removal_examines_at_most_128_slots_of_dying_spaces_per_call` |
| 16 | `M16` (`caps.rs:415`) | Off-by-one on `REMOVAL_STEP`: `31` instead of `32` | **KILLED** | `cap_revoke_of_32_descendants_is_one_call` (+5 more) |
| 17 | `M17` (`caps.rs:415`) | Off-by-one on `REMOVAL_STEP`: `33` instead of `32` | **KILLED** | `cap_delete_returns_again_while_descendants_remain` (+8 more) |
| 18 | `M18` (`caps.rs:268`) | Off-by-one on `TREE_DEPTH`: `depth < 64` instead of `depth <= 64` | **KILLED** | `creation_deeper_than_64_is_invalid`, `derivation_deeper_than_64_is_invalid` (+3 more) |
| 19 | `M19` (`caps.rs:264`) | Off-by-one on `Untyped` depth rule: `depth > self.depth(own)` instead of `>=` | **KILLED** | `capability_derived_by_ipc_lands_in_a_space_that_is_not_deeper` (+5 more) |
| 20 | `M20` (`caps.rs:265`) | Off-by-one on `CSpace` root depth rule: `depth >= self.depth(own)` instead of `>` | **KILLED** | `root_capability_of_a_space_is_placed_only_in_a_space_less_deep` (+3 more) |
| 21 | `M21` (`caps.rs:54`) | `CSpace` directory minimum size `16` bytes instead of `8` bytes | **SURVIVED** | Missing test: 8-byte directory footprint of a 1-segment `CSpace` |
| 22 | `M22` (`caps.rs:75`) | `CSpace` directory alignment `PAGE` (4096) instead of `bytes.min(PAGE)` | **SURVIVED** | Missing test: sub-page alignment of a small `CSpace` directory |
| 23 | `M23` (`ipc.rs:119`) | `recv` checks `reply != Idle` (`Busy`) before `window` (`Invalid`/`Denied`) | **KILLED** | `state_is_checked_after_every_argument` |
| 24 | `M24` (`ipc.rs:139`) | `reply_recv` checks `endpoint` before `listed(thread, &message.caps)` | **SURVIVED** | Missing test: `reply_recv` with invalid/dead listed cap and invalid/dead `endpoint` |
| 25 | `M25` (`lib.rs:660`) | `thread_configure` checks `fault` endpoint before `aspace` | **KILLED** | `capability_arguments_are_checked_in_the_order_of_the_table` |
| 26 | `M26` (`lib.rs:668`) | `thread_configure` on a waiting thread returns `Invalid` instead of `Busy` | **KILLED** | `thread_configure_is_busy_on_a_thread_that_waits` |
| 27 | `M27` (`caps.rs:133`) | `cap_move` checks `vacant` (`NoSlot`) before `fits` (`Invalid`) | **KILLED** | `refused_move_is_invalid_before_no_slot` |
| 28 | `M28` (`caps.rs:198`) | `untyped_retype` checks `vacant` (`NoSlot`) before `fits` (`Invalid`) | **KILLED** | `refused_derivation_or_creation_is_invalid_before_no_slot` |
| 29 | `M29` (`caps.rs:199`) | `untyped_retype` checks `take` (`NoMemory`) before `vacant` (`NoSlot`) | **KILLED** | `no_slot_is_reported_before_no_memory` (+3 more) |
| 30 | `M30` (`caps.rs:522`) | `swept` does not count slot holding the dying `CSpace`'s own root cap in `128` budget | **SURVIVED** | Missing test: `CSpace` holding its own root cap at slot `< 128` during multi-step sweep |
| 31 | `M31` (`caps.rs:428`) | Waking the thread on a dying `Reply` object counts toward `REMOVAL_STEP` (32) | **KILLED** | `wake_of_the_step_that_marks_a_reply_object_is_not_counted` |
| 32 | `M32` (`ipc.rs:190`) | `signal` overwrites `notify.word` (`=`) instead of bitwise-OR (`\|=`) | **KILLED** | `signal_sets_bit_0_or_the_bits_of_the_badge` (+1 more) |
| 33 | `M33` (`ipc.rs:204`) | `hand_over` wakes bound `endpoint` receiver before `notify` waiter | **KILLED** | `signal_on_a_bound_notify_prefers_a_thread_that_waits_on_the_notify` |
| 34 | `M34` (`ipc.rs:307`) | `receive` serves queued `endpoint` caller before pending bound `notify` word | **KILLED** | `recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller` (+1 more) |
| 35 | `M35` (`ipc.rs:417`) | `deliver` overwrites `flags` with `dropped` instead of `flags \| dropped` | **KILLED** | `reply_header_has_the_dropped_flag_of_the_request_with_the_capabilities_of_the_reply` |
| 36 | `M36` (`ipc.rs:400`) | `deliver` checks first slot of receiver's range even when `caps` is empty | **KILLED** | `message_without_capabilities_reaches_a_dying_space_without_the_dropped_flag` |
| 37 | `M37` (`caps.rs:149`) | Thread in dying `CSpace` cannot `cap_delete` a `Slot::Dead` in its own space | **KILLED** | `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` |
| 38 | `M38` (`caps.rs:155`) | `cap_delete` refuses a non-dying copy capability when its object is dying | **KILLED** | `every_call_on_a_dying_object_is_gone` |
| 39 | `M39` (`caps.rs:142`) | Thread in dying `CSpace` refused on 2nd step of `cap_delete` (`cap.dying == true`) | **SURVIVED** | Missing test: multi-step `cap_delete` by a thread whose own `CSpace` is dying |
| 40 | `M40` (`ipc.rs:249`) | `notify_bind(notify, NONE)` fails with `Invalid` when `notify` is not bound | **KILLED** | `notify_bind_with_endpoint_0_removes_the_binding` |
| 41 | `M41` (`ipc.rs:150`) | `reply_recv` stamps the `endpoint` capability's badge on the reply instead of `0` | **SURVIVED** | Missing test: `reply_recv` with a badged `endpoint` capability asserting caller gets badge `0` |
| 42 | `M42` (`ipc.rs:150`) | `reply_recv` performs `receive` before `answer` (delivering reply after receiving) | **SURVIVED** | Missing test: `reply_recv` moving a cap from slot `X` while receiving into slot `X` |
| 43 | `M43` (`ipc.rs:404`) | `deliver` places all transferred caps at `index(0)` instead of `index(i)` | **SURVIVED** | Missing test: successful transfer of `>= 2` capabilities verifying slots `first..first+n` |
| 44 | `M44` (`ipc.rs:401`) | `deliver` checks `fits` only on the first transferred capability (`caps.first()`) | **SURVIVED** | Missing test: 2-cap IPC transfer where 1st cap fits and 2nd cap fails depth check |
| 45 | `M45` (`caps.rs:236`) | `cspace_grow` segment aligned on `8` bytes instead of `4096` bytes | **KILLED** | `segments_go_back_to_the_untyped_when_the_cspace_is_destroyed` (`segment_is_aligned_on_4_kb` passed!) |
| 46 | `M46` (`caps.rs:75`) | `ASpace` alignment changed from `4096` (`PAGE`) to `64` bytes | **KILLED** | `memory_is_aligned_on_the_size_of_the_object` |
| 47 | `M47` (`caps.rs:75`) | `Thread` alignment changed from `1024` to `64` bytes | **SURVIVED** | Missing test: `Thread` 1 KB alignment in `untyped_retype` |
| 48 | `M48` (`caps.rs:75`) | `CSpace` directory alignment changed from `bytes.min(PAGE)` to `8` bytes | **SURVIVED** | Missing test: `CSpace` directory alignment (e.g. 4 KB alignment for `>= 512` segments) |
| 49 | `M49` (`caps.rs:440`) | `cap_delete` via another `CSpace` (`via != 0`) leaves `Slot::Dead` instead of `Slot::Empty` | **SURVIVED** | Missing test: reusing or inspecting a slot deleted via a `CSpace` capability (`via != 0`) |
| 50 | `M50` (`caps.rs:481`) | Marking a `Reply` object dying does not wake an `Armed` caller until destruction | **KILLED** | `marking_a_reply_object_as_dying_wakes_the_caller_it_is_armed_with` (+1 more) |

---

## 3. What Was Checked and Found Sound

1. **Test determinism (`tests/property.rs` and `tests/calls.rs`):** Hand-written `xorshift64*` RNG with fixed seeds (`0..24`), `BTreeMap` collections throughout `Model`, and `same_seed_gives_the_same_state` / `different_seeds_give_different_states` are completely deterministic and reproducible.
2. **Helper integrity in `tests/calls.rs`:** `K::on` checks `assert_eq!(self.m.check(), Ok(()))` after every single system call across all 153 tests in `calls.rs`, and `got()` verifies that `delivery.words` matches the header's word count and label.
3. **Invariants 1–29 in `model/src/check.rs` match their comments:** Every numbered invariant comment in `Model::check` accurately describes the check performed in code, including Kahn's topological sort for cycle detection in Invariant 21 (`check_removal`) and the `LONGEST_WALK = 192` bound in Invariant 24.
4. **Core capability tree, revocation step bounds (32 caps / 128 slots), and depth placement rules (D-103):** Well-tested in `calls.rs` (`longest_walk_that_the_depth_rule_allows_is_within_the_bound` reaches the exact theoretical maximum of `1 + 63 + 62 + 64 = 190 <= 192` capabilities; `spaces_nest_no_deeper_than_the_tree` reaches depth 64; `removal_examines_at_most_128_slots_of_dying_spaces_per_call` kills both `127` and `129` off-by-one mutants).
