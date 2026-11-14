# Review of the One-Core Model Tests and Invariants (`dodos-model` & `dodos-abi`)

**Reviewer:** `gemini-4-argon` (independent review of the tests and invariants)  
**Date:** 14 November 2026  
**Target:** `/Users/btw/Documents/repos/dodos-kernel` (branch `model`) against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`

---

## Executive Summary

We audited the test suite (`abi/src/lib.rs`, `model/src/check.rs`, `model/src/check/tests.rs`, `model/tests/calls.rs`, and `model/tests/property.rs`) across five angles:
1. **Mutation testing:** 180 single-change mutants across `abi/src/lib.rs`, `model/src/lib.rs`, `model/src/caps.rs`, and `model/src/ipc.rs` (including 65 mutants on the newest code: `thread_cancel` / `Error::Cancelled`, the 128-slot removal budget, constants moved to `abi/`, and the shared helpers `depth` and `dying`), run against the full suite including `tests/property.rs` with timeouts. **161 mutants were killed, 1 timed out (infinite loop), and 18 survived** (17 observable through the public API/ABI, 1 equivalent).
2. **Shared helpers in `check.rs` (`Model::depth` and `Model::dying`):** Invariants 20, 22, and 28 rely on the model's own `depth` and `dying` helpers without an independent check, making those invariants blind to bugs in the shared helpers during `calls.rs` and `property.rs`.
3. **Property test (`tests/property.rs`):** Instrumented with counters and tested by removing 22 generator arms/branches one at a time. Three generator arms (`four()` in `message()`, `kill()`, and `tidy()`) can be disabled without tripping any coverage assertion when RNG alignment is preserved; and the 128-slot removal budget ending a step with 0 capabilities removed occurs only **2 times** across all 120,000 steps without any coverage floor.
4. **Test name vs. assertion audit (`tests/calls.rs`):** Sampled 95 tests (including all newest tests and all `cancel` tests). Found 1 test whose setup tests an unrelated object instead of what its name states, 1 test with dead setup and incomplete wait coverage vs. its name, and 2 order-of-checks gaps where adjacent checks return the same `Error::Invalid` code.
5. **Untested contract rules:** Identified specific rules in `kernel-interface.md` and `abi/` that have no test in the suite.

---

## Findings (Sorted by Importance)

### Finding 1 — Invariants 20, 22, and 28 share `Model::depth` and `Model::dying` with the model and fail to catch bugs in those helpers

- **Where:** `model/src/check.rs:207` (Invariant 20), `model/src/check.rs:248,266-267` (Invariant 28), `model/src/check.rs:277` (Invariant 27), `model/src/check.rs:405` (Invariant 22), `model/src/caps.rs:254-256` (`Model::depth`), `model/src/lib.rs:591-594` (`Model::dying`).
- **What is wrong:**  
  `check.rs` calls the model's own `self.depth(cap)` and `self.dying(id)` instead of computing depth and dying state independently:
  1. **`Model::depth` in Invariants 20 and 28:** Both `Model::fits` (`caps.rs:269-275`), `Model::listed` (`ipc.rs:312`), Invariant 20 (`self.depth(id) <= TREE_DEPTH`), and Invariant 28 (`depth(cap) >= depth(root)` / `depth(cap) > depth(root)`) call `self.depth()`.
     - When `self.depth()` has an off-by-one bug (`M061`: starting the walk from `self.caps[&cap].parent` so root depth is 0 instead of 1), `fits()` and `listed()` allow capability chains of 65 capabilities (real depth 65), and **Invariant 20 does not catch it** because `self.depth(id)` returns 64! `M061` was killed only by unit tests that hardcode 64 derivations, never by `model.check()` in `calls.rs` or `property.rs`.
     - When `self.depth()` returns a constant (`M062`: returning `1`), **Invariant 20 (`1 <= 64`) is completely blind** to arbitrary tree depths, and **Invariant 28 (`1 >= 1`) is completely blind** to `Untyped` capabilities placed in deeper `CSpace`s. While Invariant 21 (`check_removal` topological sort) catches actual dependency cycles, non-cyclic violations of Invariant 28 (such as placing a depth-1 `Untyped` into a depth-2 `CSpace` when no child of that `Untyped` holds the `CSpace`) are not cycles and are missed by both Invariant 28 and Invariant 21.
  2. **`Model::dying` in Invariants 22 and 27:**
     - **Invariant 27** (`self.dying(id) == sweep.is_some()` at `check.rs:277`) compares `self.dying(id)` against `cspace.sweep.is_some()`, so it catches `self.dying(id)` returning `false` *only* for a `CSpace` that already has `sweep: Some(_)`. If `cap_delete` on a `CSpace` marks `root.dying = true` without initializing `sweep` (or if `self.dying(id)` returns `false` while `root.dying` is `false`), Invariant 27 is blind if both sides are `false`.
     - **Invariant 22** (`let idle = *state == ReplyState::Idle || !self.dying(id);` at `check.rs:405`) has **no independent anchor at all**: a `Reply` object has no `sweep` field. If `self.dying(id)` is buggy (e.g. `M057`, returning `false`), Invariant 22 never notices a thread remaining `Attached` or `Armed` on a reply object whose root capability has `dying == true`.
     - Furthermore, `check.rs` has **no invariant** verifying which capabilities may have `cap.dying == true` (e.g. if `cap_revoke` accidentally marks the revoked capability itself as `dying = true`, no invariant in `check.rs` reports it).
- **How we know:** Confirmed both by reading `model/src/check.rs` and by running mutants `M057`, `M061`, and `M062`.
- **Suggested invariant / test:**
  - In `check_tree` (`model/src/check.rs:176-210`), compute a local `depths: BTreeMap<CapId, usize>` top-down using the topological order of `CapId` (already guaranteed by Invariant 1 `parent < id`):
    ```rust
    let depth = match cap.parent {
        None => 1,
        Some(parent) => depths[&parent] + 1,
    };
    ensure(depth <= TREE_DEPTH && self.depth(id) == depth, "20: depth of the tree")?;
    depths.insert(id, depth);
    ```
    and pass `depths` into `check_slots` for Invariant 28.
  - In `check_objects` or `check_slots` (`check.rs:277`) and `check_waits` (`check.rs:405`), check `self.caps[&self.objects[&id].root].dying` directly and assert `self.dying(id) == self.caps[&self.objects[&id].root].dying`.

---

### Finding 2 — `thread_cancel` on an unconfigured thread or a thread whose `CSpace` is destroyed is untested (`M173` survived)

- **Where:** `model/src/lib.rs:747-758` (`Model::thread_cancel`), `model/tests/calls.rs:4027-4214`.
- **What is wrong:**  
  In the contract ("Threads" table, line 134):
  - `thread_resume` is `busy` if the target thread is bound to no capability space, or to one that is destroyed (`self.bound_space(target).or(Err(Error::Busy))?` at `lib.rs:728`).
  - `thread_suspend` succeeds on a thread bound to no capability space (explicitly tested in `thread_suspend_succeeds_on_a_thread_bound_to_no_capability_space` at `calls.rs:3729`).
  - `thread_cancel` also succeeds regardless of whether the target thread is bound to a capability space or whether the target thread's capability space was destroyed (for example, a waiting thread whose bound `CSpace` was destroyed while it waited on an endpoint/notify in the parent space, or a newly created unconfigured thread).
  However, **no test in `calls.rs` or `property.rs` ever calls `thread_cancel` on a target thread that is bound to no `CSpace` or whose `CSpace` is destroyed**. Inserting `self.bound_space(target).or(Err(Error::Busy))?;` into `Model::thread_cancel` (`M173`) survives the entire test suite (`calls.rs`, `check::tests`, and all 24 seeds of `property.rs`)!
- **How we know:** Confirmed by running mutant `M173` against `cargo test -p dodos-model` (including `tests/property.rs`); all tests pass.
- **Suggested test:** Add to `model/tests/calls.rs`:
  ```rust
  #[test]
  fn thread_cancel_succeeds_on_a_thread_bound_to_no_space_or_a_destroyed_space() {
      let mut k = K::with_ipc();
      k.make(Thread, 30);
      k.ok(cancel(30));
      k.make(CSpace, 31);
      k.make(Thread, 32);
      k.ok(configure(32, s(31), SlotAddr::NONE, SlotAddr::NONE));
      k.ok(Syscall::ThreadResume(s(32)));
      let waiter = k.m.object_at(k.t, s(32)).unwrap();
      k.ok(Syscall::ThreadSuspend(s(32)));
      k.ok(configure(32, SPACE, SlotAddr::NONE, SlotAddr::NONE));
      k.ok(Syscall::ThreadResume(s(32)));
      assert_eq!(k.on(waiter, Syscall::Wait(s(NT))), WAITS);
      k.ok(Syscall::ThreadSuspend(s(32)));
      k.ok(Syscall::CapDelete(s(31)));
      k.ok(cancel(32));
      assert_eq!(k.woken(waiter), CANCELLED);
  }
  ```

---

### Finding 3 — `Model::object_at` does not have a test for its `Rights::READ` requirement through a `CSpace` capability (`M169` survived)

- **Where:** `model/src/lib.rs:457-461` (`pub fn object_at(&self, thread: ObjId, slot: SlotAddr) -> Option<ObjId>`).
- **What is wrong:**  
  `Model::object_at` is a public method on `Model` that resolves `slot: SlotAddr` for `thread` by calling `self.cap(thread, slot, Rights::READ).ok()?`. By contract ("Slots and addresses", line 74: *"Through a `cspace` capability, reading a slot ... needs `read`"*), resolving a slot address with `via != 0` through a `CSpace` capability that lacks `Rights::READ` must fail (`None`), and resolving through a dying `CSpace` must also fail (`None`).  
  Every call to `object_at` in `calls.rs`, `check/tests.rs`, and `property.rs` either uses `via == 0` (`SlotAddr::own(...)`) or uses a `CSpace` capability that has `Rights::ALL`. Mutating `Rights::READ` to `Rights::NONE` in `Model::object_at` (`M169`) survives the entire test suite including `tests/property.rs`.
- **How we know:** Confirmed by running mutant `M169` against the full test suite (`abi`, `lib`, `calls`, `property`).
- **Suggested test:** In `calls.rs` (e.g. in `reading_a_slot_through_a_cspace_capability_needs_read` at `calls.rs:342`):
  ```rust
  assert_eq!(k.m.object_at(k.t, via(30, 5)), k.m.object_at(k.t, via(31, 5)).or_else(|| k.m.object_at(k.t, via(30, 5))));
  assert_eq!(k.m.object_at(k.t, via(31, 5)), None);
  assert!(k.m.object_at(k.t, via(30, 5)).is_some());
  ```

---

### Finding 4 — No test verifies that waking a thread when marking a `Reply` object as dying does not consume the 128-slot `REMOVAL_SLOTS` budget (`M170` survived)

- **Where:** `model/src/caps.rs:501-511` (`Model::next_removed`), `model/tests/calls.rs:2483-2493`, `model/tests/calls.rs:3511-3530`.
- **What is wrong:**  
  Contract ("Removal ends", line 93): *"The step that marks a reply object as dying also wakes, with `gone`, the receiver attached to it or the caller that waits for an answer through it ... This wake is not counted in the 32 of a step"*, nor is it an examined slot of a dying `CSpace` (which has a budget of `REMOVAL_SLOTS = 128`).  
  In `calls.rs`, `wake_of_the_step_that_marks_a_reply_object_is_not_counted` (`calls.rs:2483`) and `one_call_wakes_a_thread_of_a_reply_object_at_each_of_its_32_steps` (`calls.rs:3511`) test that waking the thread of a dying reply object does not decrement `steps` (the 32-step budget). However, in `calls.rs:3511`, only 32 slots of the `CSpace` are swept (consuming 64 of the 128 `REMOVAL_SLOTS` budget if the reply wake also decremented `slots`). If a kernel author accidentally charges the reply-object wake against `slots` (`*slots = slots.saturating_sub(1)`, mutant `M170`), **every test in `calls.rs` and `property.rs` still passes**!
- **How we know:** Confirmed by running mutant `M170` against the entire test suite (`calls.rs` and `property.rs`).
- **Suggested test:** Add a test in `calls.rs` where a dying `CSpace` has 127 empty slots (`1..128`) followed by a `Reply` object in slot 128 with a waiting thread attached: a single `CapDelete` call must examine the 127 empty slots, remove the `Reply` object in slot 128, wake its attached server, examine no more slots, and finish destroying the 1-segment `CSpace` in that single call (`Ok(Output::Done)`). If waking the reply waiter consumed `slots`, `slots` would hit 0 before finishing the `CSpace`.

---

### Finding 5 — 14 ABI constants, discriminants, header flag bits, and `#[repr(C)]` struct field offsets in `abi/src/lib.rs` are not pinned by any test (`M027`–`M030`, `M032`–`M036`, `M040`–`M042`, `M160`, `M161` survived)

- **Where:** `abi/src/lib.rs` and `model/tests/calls.rs:3541-3597`.
- **What is wrong:**  
  The contract states under "Open points" (line 17): *"Numbers (error codes, bits of the rights, kinds, calls, layout of the header) are defined in `abi/`, which is the reference for values; this document names them."*  
  While `Error` codes (`abi/src/lib.rs:514`, `calls.rs:3561`) and `Rights` bits (`calls.rs:3582`) are exhaustively pinned, the following values in `abi/src/lib.rs` have **no test pinning them**, and mutating them survives the entire test suite (`cargo test --workspace`):
  1. **`ObjectKind` discriminants (`0..=15`, `#[repr(u8)]`, `abi/src/lib.rs:146-164`):** Swapping `Untyped = 0` and `CSpace = 1` (`M027`), `Endpoint = 6` and `Reply = 7` (`M028`), or `Timer = 9` and `Irq = 10` (`M029`) survives all tests because every test uses symbolic variants (`ObjectKind::Untyped`, etc.).
  2. **`PageSize` discriminants (`0..=2`, `#[repr(u8)]`, `abi/src/lib.rs:168-174`):** Swapping `Size4K = 0` and `Size2M = 1` (`M030`) survives all tests.
  3. **`Call` discriminants (`0..=43`, `#[repr(u32)]`, `abi/src/lib.rs:193-242`):** `abi::tests::thread_cancel_comes_after_the_calls_that_were_there_before` (`abi/src/lib.rs:521-525`) asserts `Call::TraceEmit as u32 == 44` and `Call::ThreadCancel as u32 == 45` with the comment *"so that the calls that were there before keep their place"*, but **never checks the positions of the first 44 calls (`0..=43`)**! Swapping `CapDerive` and `CapMove` (`M032`) or `TimerSet` and `TimerCancel` (`M033`) leaves `TraceEmit == 44` and `ThreadCancel == 45` and survives!
  4. **`Header::FLAG_CAPS_DROPPED` (`1 << 0`) and `Header::FLAG_NOTIFICATION` (`1 << 1`) (`abi/src/lib.rs:321-323`):** Every test in `abi/` and `model/` compares flags against the symbolic constants `Header::FLAG_CAPS_DROPPED` and `Header::FLAG_NOTIFICATION`. Changing `FLAG_CAPS_DROPPED` to `1 << 2` (`M034`) or `FLAG_NOTIFICATION` to `1 << 2` (`M035`) survives the entire test suite!
  5. **`Header::FLAG_BITS = 22` (`abi/src/lib.rs:331`):** `header_rejects_oversized_messages` (`abi/src/lib.rs:559`) tests that `flags = 1 << 22` is rejected (`None`), while `header_round_trips_at_the_limits` (`abi/src/lib.rs:542`) only passes `flags = Header::FLAG_CAPS_DROPPED` (`1 << 0`), never testing bit 21 (`1 << 21` or `(1 << 22) - 1`). Mutating `FLAG_BITS` from `22` to `21` (`M036`) survives!
  6. **`START_MAGIC` (`u64::from_le_bytes(*b"DodOSst\0")`) and `StartKind` discriminants (`0..=8`, `#[repr(u32)]`) (`abi/src/lib.rs:451-471`):** Neither `START_MAGIC` (`M040`) nor `StartKind` (`M041`) is referenced in any test in `abi/` or `model/`.
  7. **`#[repr(C)]` struct field offsets (`Received`, `StartHeader`, `StartEntry`, `abi/src/lib.rs:429-496`):** `layouts_are_fixed` (`abi/src/lib.rs:584-589`) checks `size_of::<Received>() == 32`, `size_of::<StartHeader>() == 24`, and `size_of::<StartEntry>() == 16`, but checks neither `align_of` nor field offsets (`core::mem::offset_of!`). Swapping `header` and `badge` in `Received` (`M042`), `version` and `entries` in `StartHeader` (`M160`), or `offset` and `len` in `StartEntry` (`M161`) preserves `size_of` and survives!
- **How we know:** Confirmed by running mutants `M027`–`M030`, `M032`–`M036`, `M040`–`M042`, `M160`, and `M161` against `cargo test -p dodos-abi` and `cargo test -p dodos-model`.
- **Suggested test:**
  - In `abi/src/lib.rs` (or `calls.rs:3541`), pin all 16 `ObjectKind` discriminants (`0..=15`), all 3 `PageSize` discriminants (`0..=2`) and their `.bytes()`, all 46 `Call` discriminants (`0..=45`), `Header::FLAG_CAPS_DROPPED == 1`, `Header::FLAG_NOTIFICATION == 2`, `START_MAGIC == 0x0074_7353_4f64_6f44`, all 9 `StartKind` discriminants (`0..=8`), and `offset_of!` / `align_of` for `Received`, `StartHeader`, and `StartEntry`.
  - In `header_round_trips_at_the_limits` (`abi/src/lib.rs:542`), pass `(1 << 22) - 1` for `flags` (and verify `(Header::new(0xdead_beef, 64, 4, 1 << 21).unwrap().raw() >> 63) == 1`).

---

### Finding 6 — `thread_cancel_of_a_waiter_on_a_notify_leaves_the_word_and_the_binding` tests a pending word on an unrelated `Notify` object instead of the one being cancelled

- **Where:** `model/tests/calls.rs:4076-4094`.
- **What is wrong:**  
  Look at lines 4076–4088 of `calls.rs`:
  ```rust
  #[test]
  fn thread_cancel_of_a_waiter_on_a_notify_leaves_the_word_and_the_binding() {
      let mut k = K::with_ipc();
      k.ok(bind(NT, s(EP)));
      let (first, second) = (k.spawn(40), k.spawn(41));
      assert_eq!(k.on(first, Syscall::Wait(s(NT))), WAITS);
      assert_eq!(k.on(second, Syscall::Wait(s(NT))), WAITS);
      // A word that is pending on another notify.
      k.make(Notify, 30);
      k.ok(Syscall::Signal(s(30)));
      k.ok(cancel(40));
      assert_eq!(k.woken(first), CANCELLED);
      assert_eq!(k.go(Syscall::Poll(s(30))), Ok(Output::Word(1)));
  ```
  The test is named `thread_cancel_of_a_waiter_on_a_notify_leaves_the_word_and_the_binding`. By Invariant 13 (`check.rs:344`), a `Notify` (`NT`, slot 22) that has waiting threads (`first`, `second`) *cannot* have a non-zero `word` (`word == 0 || waiters.is_empty()`). Instead of checking that `NT`'s word remains `0` after `cancel(40)` (e.g. `k.no(Syscall::Poll(s(NT)), Error::WouldWait)`), the test creates a **second, completely unrelated `Notify` in slot 30**, signals slot 30, cancels `first` (which is waiting on `NT`, slot 22), and then polls slot 30!  
  A bug in `unlink(Wait::Notify(notify))` that corrupted `self.notifies[&notify].word` (for instance, setting `notify.word = 1` when a waiter is cancelled on `NT`) would not be caught by `Poll(s(30))`, and because `Signal(s(NT))` on line 4090 sets bit 0 (`|= 1`), `woken(second)` on line 4091 would still be `Some(Ok(Output::Word(1)))` even if `cancel(40)` had set `NT`'s word to `1`!
- **How we know:** Read in `model/tests/calls.rs:4076-4094`.
- **Suggested test:** Before `k.ok(Syscall::Signal(s(NT)))` on line 4090, assert `k.no(Syscall::Poll(s(NT)), Error::WouldWait);` to prove `NT`'s own word is still 0 after `cancel(40)`.

---

### Finding 7 — Property test (`tests/property.rs`): 3 generator arms are unguarded by coverage assertions, and the 128-slot budget ending a step with 0 removals is almost never reached (2 times in 120,000 steps)

- **Where:** `model/tests/property.rs:349-362` (`Generator::four`), `783-798` (`Generator::tidy`), `845-848` (`Generator::kill`), `1135-1142` (`run`), `1194-1301` (coverage tests).
- **What is wrong:**
  1. **Three generator arms can be removed without failing any coverage assertion:**
     - **Arm `A09` (`if self.rng.chance(12) { caps = self.four(); }` in `Generator::message`, `property.rs:378-380`):** Removing this arm completely **passes all 9 tests in `tests/property.rs`**! Why? Because `Reached::with_four` has a floor of `>= 4` (`property.rs:1270`, measured 11), and the `listen`/`speak` script pair (`property.rs:820-841`) independently sends 4 capabilities and reaches `with_four = 4` on its own. Thus the `four()` branch inside `Generator::message` is not guarded by the `with_four >= 4` floor.
     - **Arm `A26` (`80..84 => self.kill()` in `Generator::script`, `property.rs:856`) and Arm `A27` (`_ => self.tidy(plan)` in `Generator::script`, `property.rs:858`):** When `self.kill()` or `self.tidy(plan)` is replaced with `Vec::new()` (preserving the single RNG call in `kill()`), **all 9 tests in `tests/property.rs` pass**! Specifically, without `kill()`, `destroyed` drops from `123` to `20`, which still passes `assert!(reached.destroyed >= 4)` (`property.rs:1271`); without `tidy()`, all coverage assertions also pass (`dropped: 39`, `with_four: 12`, `longest_walk: 126`).
     - *(Note on RNG coupling in arm-removal checks)*: Several other arms (`A10` `four_free` in `range()`, `A20` `NOT_MADE` in `UntypedRetype`) only caused unrelated coverage tests (such as `waits_of_every_sort_are_cancelled`) to fail when removed because deleting their `self.rng` call shifted the PRNG stream for subsequent steps. For example, if `NOT_MADE` in `UntypedRetype` (`property.rs:456-458`) is replaced with a no-op that consumes the same RNG draw (`if self.rng.chance(3) { let _ = self.rng.pick(&NOT_MADE); }`), `invariants_hold_after_every_call_of_random_sequences` **still passes** because `Syscall::Other` already generates 422 `Error::Unsupported` calls (`property.rs:1200-1204` only checks total `reached.errors[Unsupported] > 0`, never checking that `UntypedRetype` itself ever returned `Error::Unsupported`!).
  2. **States rarely or never reached by `tests/property.rs` (confirmed by instrumentation across all 24 seeds = 120,000 steps):**
     - **A removal step ending on the 128-slot budget alone having removed 0 capabilities** (Contract line 92: *"A step may end on the slot budget alone, having only moved the sweep"*): Across all 120,000 steps (1,551 `CapDelete -> Again` calls), the 128-slot budget stops a step early 1,399 times, of which 1,299 remove 2 capabilities (`steps_done = 2`, because `CHILD_SLOTS = 256` in `spawn` has capabilities in slots 1, 16, 18..42, so the second `CapDelete` call removes the last 2 capabilities around slot 40 and then sweeps ~128 empty slots). A step that removes **0 capabilities** and ends solely on the 128-slot sweep budget happens only **2 times** across all 120,000 steps, and **no counter in `Reached` tracks `REMOVAL_SLOTS` budget terminations at all**!
     - **`CapInspect` returning `Error::Denied`:** **0 times** in 120,000 steps (`call_errors[4][3] == 0`), because `Generator::call` arm `6 => Syscall::CapInspect(self.held(class))` uses `self.held(class)`, and `CSpace` capabilities in the generator almost always have `Rights::ALL` (75% of derivations use `Rights::ALL`).
     - **`UntypedRetype` on device memory succeeding:** Only **24 times** in 120,000 steps (out of 5,800 successful `UntypedRetype` calls = 0.4%), because `spawn` and `nest` hardcode `MEMORY` (slot 16, ordinary untyped) and `Generator::memory()` picks slot 17 (device untyped) with only $40\% \times 40\% \times 10\% = 1.6\%$ probability, most of which fail with `Invalid` because `kind` is a kernel object rather than `Frame` or `Untyped`.
     - **`NotifyBind` delivering a pending word immediately to a waiting receiver:** Only **3 times** in 120,000 steps.
     - **`ThreadCancel` cancelling a thread that is both suspended and waiting:** Only **4 times** in 120,000 steps.
     - **`CSpace` with more than 2 segments (256 slots):** **0 times** in 120,000 steps (`KINDS` and `spawn` always create `CSpace`s of max 256 slots, and `nest` creates 128-slot `CSpace`s).
  3. **Floor vs. measured comparison (`property.rs:1212-1301`):**
     | Metric | Measured (24 seeds) | Floor in `property.rs` | Ratio (Measured / Floor) | Assessment |
     |---|---|---|---|---|
     | `deepest` | 64 | `== 64` | 1.0x | Tight |
     | `longest_walk` | 122 | `>= 100` | 1.22x | Tight (though max theoretical is 191; generator `nest` only builds ~24-45 deep) |
     | `seeds_walked` | 24 | `== 24` | 1.0x | Tight |
     | `dying[kind]` | 19 (`Thread`) to 13,567 (`CSpace`) | `> 0` (`>= 1`) | up to 13,567x | Very loose for all kinds except `Thread` (19) |
     | `dying_copies` | 2,991 | `>= 300` | 10.0x | Reasonable |
     | `outside` | 32,745 | `>= 15,000` | 2.18x | Tight |
     | `waits` (`callers`, `served`, `receivers`, `waiters`, `bound`) | 12,963 – 38,311 | `>= 2,000` | 6.5x – 19.2x | Moderate |
     | `ends` (`with_caps`, `dropped`, `notifications`, `woken_gone`) | 34, 28, 33, 24 | `>= 10` | 2.4x – 3.4x | Tight |
     | `with_four` | 11 | `>= 4` | 2.75x | **Too low to guard `Generator::message`'s `self.four()` arm** (which leaves `with_four = 4` when removed!) |
     | `destroyed` | 123 | `>= 4` | **30.75x** | **So low that removing `Generator::kill()` (`destroyed = 20`) still passes!** |
     | `moved` (`[1754, 195]`) & `refused` (`[104, 21]`) | 21 – 1,754 | `>= 10` | 2.1x – 175x | Loose on `moved[0]` (1,754 vs 10), tight on `refused[1]` (21 vs 10) |
     | `sent` / `sent_refused` | 10 / 2 | `>= 5` / `>= 1` | 2.0x | Tight |
     | `called` / `answered` | 31 / 16 | `>= 5` / `>= 5` | 6.2x / 3.2x | Reasonable |
     | `cancelled` (`[22, 8, 26, 12]`) | 8 – 26 | `>= 3` | 2.67x – 8.67x | Tight |
  4. **Replayability of a failing seed:**  
     When `model.check()` fails inside `run(seed, ...)`, line 1141 panics with `panic!("seed {seed}, step {step}, {shown}: {broken}")`. Because `run(seed, &mut Reached::default())` is deterministic and independent of other seeds, knowing `seed` and `step` is sufficient to replay the exact sequence from `Model::boot()` up to `step`. However, **`run` is private** and there is no helper test or environment variable to replay a single seed or print the trace of steps `0..=step`, and if a coverage assertion fails in `all_seeds()`, it fails on the aggregate of all 24 seeds without printing which seed contributed what.
- **How we know:** Confirmed by running `test_prop_arms.py`, `test_extra_arms.py`, `run_prop_counters.py`, and `check_slot_budget.py`.
- **Suggested test / improvement:**
  - Raise the `with_four` floor from `>= 4` to `>= 7` (so losing either `listen`/`speak` or `message`'s `four()` fails it) and raise the `destroyed` floor from `>= 4` to `>= 40` (so losing `kill()` fails it).
  - Add a counter in `Reached` for `UntypedRetype` returning `Error::Unsupported` (to guard the `NOT_MADE` branch in `UntypedRetype` independently of `Syscall::Other`) and a counter for removal steps terminated by the 128-slot `REMOVAL_SLOTS` budget.

---

### Finding 8 — `thread_configure_is_busy_in_every_wait` has dead setup code and omits `Wait::Notify`

- **Where:** `model/tests/calls.rs:3830-3852`.
- **What is wrong:**
  1. Lines 3836–3839:
     ```rust
     for slot in [40, 41] {
         k.ok(Syscall::ThreadSuspend(s(slot)));
         k.ok(Syscall::ThreadResume(s(slot)));
     }
     ```
     Threads 40 and 41 were just created by `k.spawn(40)` and `k.spawn(41)` (which already configured and resumed them). Suspending and immediately resuming them before they enter any wait is dead no-op code.
  2. The test is named `thread_configure_is_busy_in_every_wait`, but it only tests 3 of the 4 wait states (`Wait::Call`, `Wait::Recv`, and `Wait::Reply`); `Wait::Notify` is tested in an earlier test (`thread_configure_is_busy_on_a_thread_that_waits`, `calls.rs:2406`).
- **How we know:** Read in `model/tests/calls.rs:3830-3852`.
- **Suggested fix:** Remove the dead `ThreadSuspend`/`ThreadResume` loop at lines 3836–3839, and either include `Wait::Notify` in `thread_configure_is_busy_in_every_wait` or rename it to reflect that it checks the three IPC waits (`Call`, `Recv`, `Reply`).

---

### Finding 9 — Two order-of-checks rules in the contract cannot be distinguished by the existing tests (or return the same `Error::Invalid` code)

- **Where:**
  1. `model/src/lib.rs:670-675` (`Model::window`) and `model/tests/calls.rs:2025-2034`, `2681-2685`.
  2. `model/src/caps.rs:124-129` (`Model::cap_derive`) and `model/tests/calls.rs:2756-2769`.
  3. `model/src/ipc.rs:338-341` (`Model::deliver`) and `model/tests/calls.rs:2003-2022`.
- **What is wrong:**
  1. **Receive range slot bounds (step 2) vs. `count > MAX_CAPS` (step 3):**  
     Contract ("Order of checks" line 104 & "Transfer of capabilities" line 168): *"A destination or any other slot address is a capability argument: its `via` capability and its range are judged here"* (step 2), whereas *"the plain arguments, in the order of the table (`invalid`)"* (`count > 4`, step 3). Because both `beyond` (`first == 0 || end > slots.len()`) and `count as usize > MAX_CAPS` return `Error::Invalid` (`lib.rs:673-674`), both conditions produce the identical error code `Error::Invalid` and no test can distinguish their order.
  2. **`cap_derive` badge on non-`Endpoint`/`Notify` (`Invalid`) vs. depth 64 (`Invalid`):**  
     In `plain_arguments_of_cap_derive_are_judged_in_the_order_of_the_table` (`calls.rs:2756-2769`), the test checks `rights` (`Denied`) before `badge` (`Invalid`), and `badge != kept` (`Denied`) before `depth > 64` (`Invalid`). Because `badge != 0` on a non-`Endpoint`/`Notify` and `depth > 64` both return `Error::Invalid`, their relative order is unobservable.
  3. **Order of checks between capability arguments of `call` (`endpoint` vs. `range`'s `via` capability) when the message header is valid:**  
     In `arguments_of_call_are_checked_in_the_order_of_the_table` (`calls.rs:2345-2361`), line 2357 checks `call(no_send, dead(), denied)` -> `Error::Denied`. Wait: both `no_send` (the endpoint without `SEND`) and `denied` (the receive range through a `read_only` `CSpace` without `WRITE`) fail with **`Error::Denied`**! Thus line 2357 (`k.no(call(no_send, dead(), denied), Error::Denied)`) compares two identical error codes (`Error::Denied` from `endpoint` vs. `Error::Denied` from `range`)! While `dead()` in the middle returns `Error::Gone` on line 2358 (which indirectly proves `endpoint` -> `dead()` -> `denied` by transitivity), line 2357 itself uses `Error::Denied` for both `no_send` and `denied`.
- **How we know:** Read in `model/src/lib.rs:670-675`, `model/src/caps.rs:124-129`, and `model/tests/calls.rs:2345-2361`.
- **Suggested test:** In `arguments_of_call_are_checked_in_the_order_of_the_table` (`calls.rs:2345`), use an invalid or dead slot for `endpoint` (or for `range`'s `via`) so the three failure codes are all distinct, and add a direct check that `call` checks `endpoint` (`Denied`) before `message` header limits (`Invalid`) when `caps` is empty (complementing `grant_is_judged_before_the_limits_of_the_header` at `calls.rs:3265`).

---

### Finding 10 — Contract rules with no test at all

- **Where:** `Docs/architecture/kernel-interface.md` vs. `abi/src/lib.rs` and `model/tests/calls.rs`.
- **What is wrong (rules in the contract with no test in the suite):**
  1. **Start-up page layout and constants (`kernel-interface.md:306-315`, `abi/src/lib.rs:451-496`):**  
     The contract specifies the versioned start-up page with entries `(kind, offset, length)` for object sizes, untyped ranges, core list, firmware tables, entropy seed, boot timestamps, and crash record. `abi/src/lib.rs` defines `START_MAGIC`, `StartKind` (`ObjectSizes`..`CrashRecord`), `StartHeader`, and `StartEntry`, but **no test in `abi/` or `model/` tests `START_MAGIC`, `StartKind` discriminants, or the field layouts of `StartHeader` and `StartEntry`** (confirmed by survivors `M040`, `M041`, `M160`, `M161`).
  2. **Object sizes of `timer` (64 B), `irq` (64 B), and `task` (256 B) (`kernel-interface.md:285-287`):**  
     The "Object sizes" table in the contract specifies `timer` = 64 bytes, `irq` = 64 bytes, and `task` = 256 bytes (and `iospace` = 4 KB). Unlike `ENDPOINT_BYTES`, `REPLY_BYTES`, `NOTIFY_BYTES`, `SCHED_BYTES`, `THREAD_BYTES`, and `ASPACE_BYTES`, these constants are neither defined in `abi/src/lib.rs` nor tested in `numbers_of_the_contract_are_those_of_the_interface` (`calls.rs:3541`).
  3. **`thread_cancel` on a thread bound to no `CSpace` or a destroyed `CSpace` (`kernel-interface.md:134`):**  
     Untested (see Finding 2, confirmed by survivor `M173`).
  4. **Reading a slot via `Model::object_at` through a `CSpace` capability without `Rights::READ` (`kernel-interface.md:74`, `model/src/lib.rs:457`):**  
     Untested (see Finding 3, confirmed by survivor `M169`).
  5. **Waking a thread on a dying `Reply` object does not consume the 128-slot `REMOVAL_SLOTS` budget (`kernel-interface.md:93`):**  
     Only tested against the 32-step `REMOVAL_STEP` budget, not the 128-slot `REMOVAL_SLOTS` budget (see Finding 4, confirmed by survivor `M170`).
  6. **All 46 `Call` numbers, all 16 `ObjectKind` numbers, all 3 `PageSize` numbers, and `Header` flag bit values (`kernel-interface.md` Open Points line 17):**  
     Untested in `abi/` and `model/` (see Finding 5, confirmed by survivors `M027`–`M030`, `M032`–`M036`).

---

## Detailed Review of Invariants in `model/src/check.rs` (Angle 2)

Every invariant in `model/src/check.rs` (Invariants 1–28) is unit-tested with a dedicated negative test in `model/src/check/tests.rs` (61 unit tests in `check::tests`, all verified to fail when their respective invariant check is removed).

For the invariants and census helpers that call the model's shared helpers `self.depth(cap)` (`caps.rs:254`) and `self.dying(id)` (`lib.rs:591`):

| Invariant / Helper | Location in `check.rs` | Shared Helper Used | Would it still catch an error in the shared helper? | Missing Independent Check |
|---|---|---|---|---|
| **Invariant 20** ("depth of the tree <= 64") | `check.rs:207` | `self.depth(id)` | **No.** If `self.depth` undercounts (e.g. `M061` off-by-one, or `M062` returning `1`), `Model::fits` and `Model::listed` allow chains > 64 deep and Invariant 20 uses the same broken `self.depth(id)` and reports `Ok(())`. | Compute depth independently in `check_tree` from `cap.parent` (`None => 1`, `Some(p) => depth[p] + 1`) and assert both `depth <= TREE_DEPTH` and `self.depth(id) == depth`. |
| **Invariant 28** ("depth of an untyped capability" & "depth of the root capability of a space") | `check.rs:248, 266-267` | `self.depth(cap)`, `self.depth(root)` | **Partially no.** If `self.depth` is shifted by a constant offset (`M061`), relative comparisons `depth(a) >= depth(b)` still hold. If `self.depth` returns a constant (`M062`) or miscalculates non-linearly, Invariant 28 fails to catch non-cyclic depth violations (Invariant 21 only catches cycles or walks > 191). | Use the independent `depths` map computed in `check_tree` rather than `self.depth()`. |
| **Invariant 22** ("reply object of a waiting thread" & "dying reply object") | `check.rs:405` | `self.dying(id)` | **No.** A `Reply` object has no `sweep` field, so if `self.dying(id)` returns `false` (`M057`), Invariant 22 never detects an `Attached` or `Armed` thread on a dying `Reply` object. | Check `!self.caps[&self.objects[&id].root].dying` directly in `check_waits`. |
| **Invariant 27** ("sweep of a dying space") | `check.rs:277` | `self.dying(id)` | **Partially yes (for `CSpace`s with `sweep.is_some()`), no if both are false.** Because it checks `self.dying(id) == sweep.is_some()`, any discrepancy between `self.dying(id)` and `sweep.is_some()` is caught, *unless* `cap_delete` failed to set `sweep` when `self.dying(id)` also returned `false`. | Check `self.caps[&self.objects[&id].root].dying == sweep.is_some()` and `self.dying(id) == self.caps[&self.objects[&id].root].dying` for every object in `check_objects`. |
| **`Census`** (`deepest`, `dying`, `dying_copies`) | `check.rs:43-55` | `self.depth(id)`, `self.dying(cap.object)` | **Yes** — `check::tests::census_counts_what_the_state_holds` (`check/tests.rs:1305`) pins exact numbers on a known state and killed `M057`, `M061`, and `M062`. | None needed in `Census` once Invariants 20, 22, 27, 28 check the underlying fields directly. |

---

## Mutation Log (180 Mutants)

- **Total mutants run:** 180 single-change mutants across `abi/src/lib.rs` (50), `model/src/lib.rs` (49), `model/src/caps.rs` (53), and `model/src/ipc.rs` (28).
- **Mutants on newest code (`abi/new`, `new/cancel`, `new/helper`, `new/budget`):** 65 of 180 (36.1%).
- **Killed:** 161 (10 in `dodos-abi` unit tests, 151 in `dodos-model` unit + `calls.rs` + `property.rs`).
- **Timeout (infinite loop killed by timeout):** 1 (`M074`).
- **Survived:** 18 (17 observable through the public API/ABI, 1 equivalent mutant `M115`).

### Summary of Survivors and Timeouts

| ID | File | Mutant | Classification | Missing Test / Explanation |
|---|---|---|---|---|
| `M027` | `abi/src/lib.rs` | `ObjectKind::Untyped = 0, CSpace = 1` -> `1, 0` | **Observable (ABI)** | Pin `ObjectKind` discriminant values `0..=15` (Finding 5). |
| `M028` | `abi/src/lib.rs` | `ObjectKind::Endpoint = 6, Reply = 7` -> `7, 6` | **Observable (ABI)** | Pin `ObjectKind` discriminant values `0..=15` (Finding 5). |
| `M029` | `abi/src/lib.rs` | `ObjectKind::Timer = 9, Irq = 10` -> `10, 9` | **Observable (ABI)** | Pin `ObjectKind` discriminant values `0..=15` (Finding 5). |
| `M030` | `abi/src/lib.rs` | `PageSize::Size4K = 0, Size2M = 1` -> `1, 0` | **Observable (ABI)** | Pin `PageSize` discriminant values `0..=2` (Finding 5). |
| `M032` | `abi/src/lib.rs` | Swap `Call::CapDerive` and `Call::CapMove` | **Observable (ABI)** | Pin all 46 `Call` discriminant values `0..=45` (Finding 5). |
| `M033` | `abi/src/lib.rs` | Swap `Call::TimerSet` and `Call::TimerCancel` | **Observable (ABI)** | Pin all 46 `Call` discriminant values `0..=45` (Finding 5). |
| `M034` | `abi/src/lib.rs` | `Header::FLAG_CAPS_DROPPED = 1 << 0` -> `1 << 2` | **Observable (ABI)** | Pin `Header::FLAG_CAPS_DROPPED == 1` (Finding 5). |
| `M035` | `abi/src/lib.rs` | `Header::FLAG_NOTIFICATION = 1 << 1` -> `1 << 2` | **Observable (ABI)** | Pin `Header::FLAG_NOTIFICATION == 2` (Finding 5). |
| `M036` | `abi/src/lib.rs` | `Header::FLAG_BITS = 22` -> `21` | **Observable (ABI)** | Test `Header::new(..., flags: (1 << 22) - 1)` is `Some` (Finding 5). |
| `M040` | `abi/src/lib.rs` | `START_MAGIC` changed to `DodOSst\x01` | **Observable (ABI)** | Pin `START_MAGIC` bytes (Finding 5). |
| `M041` | `abi/src/lib.rs` | `StartKind::ObjectSizes = 0, Untyped = 1` -> `1, 0` | **Observable (ABI)** | Pin `StartKind` discriminant values `0..=8` (Finding 5). |
| `M042` | `abi/src/lib.rs` | Swap `header` and `badge` fields in `#[repr(C)] struct Received` | **Observable (ABI)** | Pin `offset_of!(Received, header, badge, marks, task)` (Finding 5). |
| `M074` | `model/src/caps.rs` | `swept()` resets `space.sweep = Some(1)` on every `next_removed` walk | **Timeout (Infinite Loop)** | Killed by 20s timeout when a dying `CSpace` has >32 capabilities. |
| `M115` | `model/src/caps.rs` | `let badge = if kept != 0 { kept } else { badge }` -> `if badge != 0 { badge } else { kept }` | **Equivalent** | Line 124 already rejected `badge != 0 && kept != 0 && badge != kept`, so `kept` and `badge` cannot both be non-zero and distinct here. |
| `M160` | `abi/src/lib.rs` | Swap `version` and `entries` in `#[repr(C)] struct StartHeader` | **Observable (ABI)** | Pin `offset_of!(StartHeader, magic, version, entries, _reserved)` (Finding 5). |
| `M161` | `abi/src/lib.rs` | Swap `offset` and `len` in `#[repr(C)] struct StartEntry` | **Observable (ABI)** | Pin `offset_of!(StartEntry, kind, _reserved, offset, len)` (Finding 5). |
| `M169` | `model/src/lib.rs` | `object_at` passes `Rights::NONE` instead of `Rights::READ` | **Observable (Public API)** | Test `Model::object_at` with `SlotAddr::through(via, index)` where `via` has no `READ` right (Finding 3). |
| `M170` | `model/src/caps.rs` | `next_removed` decrements `slots` when waking a dying reply object's thread | **Observable (Public API)** | Test a 128-slot sweep that also marks a `Reply` object as dying and wakes its thread in one call (Finding 4). |
| `M173` | `model/src/lib.rs` | `thread_cancel` checks `self.bound_space(target).or(Err(Error::Busy))?` | **Observable (Public API)** | Test `thread_cancel` on an unconfigured thread and a thread whose `CSpace` is destroyed (Finding 2). |

### Full Log of All 180 Mutants

| ID | Category | File | Mutant Description | Outcome |
|---|---|---|---|---|
| M001 | `abi/new` | `abi/src/lib.rs` | REMOVAL_SLOTS = 128 -> 127 | Killed (`numbers_of_the_contract_are_those_of_the_interface`, `removal_examines_at_most_128_slots_of_dying_spaces_per_call`) |
| M002 | `abi/new` | `abi/src/lib.rs` | REMOVAL_SLOTS = 128 -> 129 | Killed (`numbers_of_the_contract_are_those_of_the_interface`, `slot_of_the_root_capability_of_a_dying_space_counts_as_examined`, `removal_examines_at_most_128_slots_of_dying_spaces_per_call`) |
| M003 | `abi/new` | `abi/src/lib.rs` | LONGEST_WALK = 2 * TREE_DEPTH - 1 + TREE_DEPTH -> 2 * TREE_DEPTH + TREE_DEPTH | Killed (`numbers_of_the_contract_are_those_of_the_interface`, `longest_walk_that_the_depth_rule_allows_is_within_the_bound`) |
| M004 | `abi/new` | `abi/src/lib.rs` | CSPACE_MAX_SLOTS = 1 << 20 -> 1 << 19 | Killed (`cspace_maximum_is_a_whole_number_of_segments_up_to_2_to_the_20`, `numbers_of_the_contract_are_those_of_the_interface`, `removal_examines_at_most_128_slots_of_dying_spaces_per_call` (+1 more)) |
| M005 | `abi/new` | `abi/src/lib.rs` | CSPACE_DIRECTORY_BYTES = 8 -> 16 | Killed (`cspace_directory_is_rounded_up_to_a_power_of_two`, `directory_is_aligned_on_its_size`, `kernel_object_larger_than_4_kb_is_aligned_on_4_kb` (+2 more)) |
| M006 | `abi/new` | `abi/src/lib.rs` | ENDPOINT_BYTES = 64 -> 128 | Killed (`directory_of_one_segment_takes_8_bytes`, `endpoint_reply_and_notify_take_64_bytes`, `numbers_of_the_contract_are_those_of_the_interface`) |
| M007 | `abi/new` | `abi/src/lib.rs` | REPLY_BYTES = 64 -> 128 | Killed (`endpoint_reply_and_notify_take_64_bytes`, `numbers_of_the_contract_are_those_of_the_interface`) |
| M008 | `abi/new` | `abi/src/lib.rs` | NOTIFY_BYTES = 64 -> 128 | Killed (`endpoint_reply_and_notify_take_64_bytes`, `numbers_of_the_contract_are_those_of_the_interface`) |
| M009 | `abi/new` | `abi/src/lib.rs` | SCHED_BYTES = 128 -> 256 | Killed (`numbers_of_the_contract_are_those_of_the_interface`, `sched_is_aligned_on_128_bytes`, `sched_takes_128_bytes`) |
| M010 | `abi/new` | `abi/src/lib.rs` | THREAD_BYTES = 1024 -> 2048 | Killed (`numbers_of_the_contract_are_those_of_the_interface`, `thread_is_aligned_on_1_kb`, `thread_takes_1_kb`) |
| M011 | `abi/new` | `abi/src/lib.rs` | ASPACE_BYTES = 4096 -> 8192 | Killed (`kernel_object_larger_than_4_kb_is_aligned_on_4_kb`, `memory_is_aligned_on_the_size_of_the_object`, `numbers_of_the_contract_are_those_of_the_interface` (+5 more)) |
| M012 | `abi/new` | `abi/src/lib.rs` | Error::Cancelled = 11 -> 12 | Killed (`abi::tests::error_codes_are_stable`) |
| M013 | `abi/new` | `abi/src/lib.rs` | Swap Call::TraceEmit and Call::ThreadCancel order | Killed (`abi::tests::thread_cancel_comes_after_the_calls_that_were_there_before`) |
| M014 | `abi` | `abi/src/lib.rs` | REG_WORDS = 6 -> 5 | Killed (`numbers_of_the_contract_are_those_of_the_interface`) |
| M015 | `abi` | `abi/src/lib.rs` | MAX_WORDS = 64 -> 63 | Killed (`numbers_of_the_contract_are_those_of_the_interface`) |
| M016 | `abi` | `abi/src/lib.rs` | MAX_CAPS = 4 -> 3 | Killed (`capabilities_of_one_message_each_land_in_their_own_slot`, `numbers_of_the_contract_are_those_of_the_interface`) |
| M017 | `abi` | `abi/src/lib.rs` | SLOT_BYTES = 32 -> 64 | Killed (`cspace_grow_checks_the_untyped_then_the_maximum_then_the_memory`, `cspace_grow_is_no_memory_when_the_untyped_is_exhausted`, `numbers_of_the_contract_are_those_of_the_interface` (+2 more)) |
| M018 | `abi` | `abi/src/lib.rs` | CSPACE_SEGMENT_SLOTS = 128 -> 64 | Killed (`check::tests::badge_on_a_capability_that_is_not_for_an_endpoint_or_a_notify_is_reported`, `check::tests::capability_that_a_dying_space_did_not_hold_when_it_began_to_die_is_reported`, `check::tests::census_counts_what_the_state_holds` (+10 more)) |
| M019 | `abi` | `abi/src/lib.rs` | REMOVAL_STEP = 32 -> 31 | Killed (`cap_revoke_of_32_descendants_is_one_call`, `cap_revoke_removes_32_capabilities_then_returns_again`, `capability_is_removed_after_its_descendants_the_most_recent_first` (+6 more)) |
| M020 | `abi` | `abi/src/lib.rs` | TREE_DEPTH = 64 -> 63 | Killed (`capability_at_depth_64_is_moved_by_ipc`, `derivation_deeper_than_64_is_invalid`, `depth_of_a_capability_to_derive_is_judged_before_the_next_listed_slot` (+7 more)) |
| M021 | `abi` | `abi/src/lib.rs` | START_SLOT_CSPACE = 1 -> 2, START_SLOT_ASPACE = 2 -> 1 | Killed (`numbers_of_the_contract_are_those_of_the_interface`) |
| M022 | `abi` | `abi/src/lib.rs` | START_SLOT_FIRST = 16 -> 15 | Killed (`numbers_of_the_contract_are_those_of_the_interface`) |
| M023 | `abi` | `abi/src/lib.rs` | Error::Denied = 3, Invalid = 4 swapped | Killed (`numbers_of_the_errors_are_those_of_the_interface`) |
| M024 | `abi` | `abi/src/lib.rs` | Rights::EXEC = 1 << 2, SEND = 1 << 3 swapped | Killed (`bits_of_the_rights_are_those_of_the_interface`) |
| M025 | `abi` | `abi/src/lib.rs` | Rights::derive omits contains(Self::DERIVE) | Killed (`abi::tests::derive_only_removes_rights`) |
| M026 | `abi` | `abi/src/lib.rs` | Marks::PRIVATE = 1 << 0 -> 1 << 2 | Killed (`abi::tests::marks_reject_reserved_bits`) |
| M027 | `abi` | `abi/src/lib.rs` | ObjectKind::Untyped = 0, CSpace = 1 -> 1, 0 | **SURVIVED** |
| M028 | `abi` | `abi/src/lib.rs` | ObjectKind::Endpoint = 6, Reply = 7 -> 7, 6 | **SURVIVED** |
| M029 | `abi` | `abi/src/lib.rs` | ObjectKind::Timer = 9, Irq = 10 -> 10, 9 | **SURVIVED** |
| M030 | `abi` | `abi/src/lib.rs` | PageSize::Size4K = 0, Size2M = 1 -> 1, 0 | **SURVIVED** |
| M031 | `abi` | `abi/src/lib.rs` | PageSize::Size1G bytes 1 << 30 -> 1 << 29 | Killed (`frame_of_1_gb_pages_is_aligned_on_1_gb`) |
| M032 | `abi` | `abi/src/lib.rs` | Swap Call::CapDerive and Call::CapMove order | **SURVIVED** |
| M033 | `abi` | `abi/src/lib.rs` | Swap Call::TimerSet and Call::TimerCancel order | **SURVIVED** |
| M034 | `abi` | `abi/src/lib.rs` | Header::FLAG_CAPS_DROPPED = 1 << 0 -> 1 << 2 | **SURVIVED** |
| M035 | `abi` | `abi/src/lib.rs` | Header::FLAG_NOTIFICATION = 1 << 1 -> 1 << 2 | **SURVIVED** |
| M036 | `abi` | `abi/src/lib.rs` | Header::FLAG_BITS = 22 -> 21 | **SURVIVED** |
| M037 | `abi` | `abi/src/lib.rs` | Header::words mask 0x7f -> 0x3f | Killed (`abi::tests::header_rejects_oversized_messages`, `abi::tests::header_round_trips_at_the_limits`) |
| M038 | `abi` | `abi/src/lib.rs` | Header::caps mask 0x7 -> 0x3 | Killed (`abi::tests::header_rejects_oversized_messages`, `abi::tests::header_round_trips_at_the_limits`) |
| M039 | `abi` | `abi/src/lib.rs` | Header::is_fast words() <= REG_WORDS -> words() < REG_WORDS | Killed (`abi::tests::fast_path_is_registers_without_capabilities`) |
| M040 | `abi` | `abi/src/lib.rs` | START_MAGIC changed | **SURVIVED** |
| M041 | `abi` | `abi/src/lib.rs` | StartKind::ObjectSizes = 0, Untyped = 1 -> 1, 0 | **SURVIVED** |
| M042 | `abi` | `abi/src/lib.rs` | Received field order badge and header swapped | **SURVIVED** |
| M043 | `new/cancel` | `model/src/lib.rs` | modelled(call) omits ThreadCancel | Killed (`thread_cancel_is_not_one_of_the_calls_that_are_not_modelled`) |
| M044 | `new/cancel` | `model/src/lib.rs` | thread_cancel requires Rights::WRITE instead of Rights::MANAGE | Killed (`thread_cancel_needs_manage_on_a_thread`) |
| M045 | `new/cancel` | `model/src/lib.rs` | thread_cancel wakes with Error::Gone instead of Error::Cancelled | Killed (`client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped`, `reply_recv_on_the_reply_object_of_a_cancelled_caller_drops_the_reply`, `send_on_the_reply_object_of_a_cancelled_caller_is_would_wait` (+5 more)) |
| M046 | `new/cancel` | `model/src/lib.rs` | thread_cancel does not call self.unlink(target) | Killed (`client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped`, `outcome_of_a_cancelled_wait_is_cleared_by_the_next_call_of_the_thread`, `reply_recv_on_the_reply_object_of_a_cancelled_caller_drops_the_reply` (+6 more)) |
| M047 | `new/cancel` | `model/src/lib.rs` | thread_cancel does not call self.wake(target, Err(Error::Cancelled)) | Killed (`client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped`, `reply_recv_on_the_reply_object_of_a_cancelled_caller_drops_the_reply`, `send_on_the_reply_object_of_a_cancelled_caller_is_would_wait` (+5 more)) |
| M048 | `new/cancel` | `model/src/lib.rs` | thread_cancel unconditionally wakes with Cancelled even when not waiting | Killed (`thread_cancel_leaves_the_outcome_of_a_wait_that_is_already_over`, `thread_cancel_of_a_thread_that_does_not_wait_changes_nothing_and_is_not_remembered`, `thread_that_cancels_itself_does_not_wait_and_nothing_changes`) |
| M049 | `new/cancel` | `model/src/lib.rs` | thread_cancel resumes a suspended thread | Killed (`suspended_thread_that_is_cancelled_stays_suspended_and_finds_cancelled`) |
| M050 | `new/cancel` | `model/src/lib.rs` | thread_cancel ignores Wait::Reply | Killed (`client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped`, `reply_recv_on_the_reply_object_of_a_cancelled_caller_drops_the_reply`, `send_on_the_reply_object_of_a_cancelled_caller_is_would_wait`) |
| M051 | `new/cancel` | `model/src/lib.rs` | thread_cancel ignores Wait::Recv | Killed (`thread_cancel_of_a_receiver_makes_its_reply_object_idle`) |
| M052 | `new/cancel` | `model/src/lib.rs` | thread_cancel ignores Wait::Notify | Killed (`outcome_of_a_cancelled_wait_is_cleared_by_the_next_call_of_the_thread`, `suspended_thread_that_is_cancelled_stays_suspended_and_finds_cancelled`, `thread_cancel_of_a_waiter_on_a_notify_leaves_the_word_and_the_binding`) |
| M053 | `new/cancel` | `model/src/lib.rs` | thread_cancel ignores Wait::Call | Killed (`thread_cancel_of_a_caller_moves_none_of_the_capabilities_it_listed`, `thread_cancel_takes_a_queued_caller_out_of_the_queue`) |
| M054 | `new/cancel` | `model/src/ipc.rs` | unlink on Wait::Reply does not idle reply | Killed (`call_is_delivered_to_a_suspended_receiver_which_does_not_run`, `caller_is_not_woken_when_the_server_thread_alone_is_destroyed`, `client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped` (+15 more)) |
| M055 | `new/cancel` | `model/src/ipc.rs` | unlink on Wait::Recv does not idle reply | Killed (`binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive`, `binding_to_a_dying_endpoint_is_removed_and_the_word_goes_elsewhere`, `delivery_into_a_destroyed_capability_space_drops_the_capabilities` (+12 more)) |
| M056 | `new/cancel` | `model/src/ipc.rs` | unlink on Wait::Recv does not remove from endpoint queue | Killed (`binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive`, `call_is_delivered_to_a_suspended_receiver_which_does_not_run`, `call_is_delivered_at_once_to_a_thread_that_waits_to_receive` (+19 more)) |
| M057 | `new/helper` | `model/src/lib.rs` | dying() always returns false | Killed (`check::tests::caller_of_a_dying_reply_object_is_reported`, `check::tests::dying_space_without_a_sweep_is_reported`, `check::tests::census_counts_what_the_state_holds` (+3 more)) |
| M058 | `new/helper` | `model/src/lib.rs` | full() ignores held.dying | Killed (`copy_under_cap_delete_is_dying_and_its_object_is_not`) |
| M059 | `new/helper` | `model/src/lib.rs` | full() ignores self.dying(held.object) | Killed (`copy_of_a_dying_object_is_deleted_and_not_revoked`, `every_call_on_a_dying_object_is_gone`, `object_is_dying_as_soon_as_a_removal_reaches_its_root_capability` (+2 more)) |
| M060 | `new/helper` | `model/src/lib.rs` | addressed_space() ignores self.dying(own) | Killed (`thread_cancel_by_a_thread_whose_capability_space_is_dying_is_gone`, `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete`) |
| M061 | `new/helper` | `model/src/caps.rs` | depth() starts at 0 instead of 1 (skips self) | Killed (`check::tests::census_counts_what_the_state_holds`, `check::tests::tree_of_depth_65_is_reported`, `check::tests::tree_of_depth_64_is_accepted`) |
| M062 | `new/helper` | `model/src/caps.rs` | depth() always returns 1 | Killed (`check::tests::capability_space_without_its_state_is_reported`, `check::tests::census_counts_what_the_state_holds`, `check::tests::maximum_of_no_slot_is_reported` (+3 more)) |
| M063 | `new/helper` | `model/src/caps.rs` | fits() Derived uses depth(source) instead of depth(source) + 1 | Killed (`capability_derived_by_ipc_lands_in_a_space_that_is_not_deeper`, `creation_deeper_than_64_is_invalid`, `derivation_deeper_than_64_is_invalid` (+4 more)) |
| M064 | `new/helper` | `model/src/caps.rs` | fits() Retyped uses depth(source) instead of depth(source) + 1 | Killed (`caller_is_woken_with_gone_when_a_sweep_destroys_its_reply_object`, `cap_delete_on_an_empty_slot_of_an_own_dying_space_is_invalid`, `cap_delete_through_a_cspace_capability_leaves_the_slot_empty` (+62 more)) |
| M065 | `new/helper` | `model/src/caps.rs` | fits() Untyped uses > instead of >= | Killed (`capability_derived_by_ipc_lands_in_a_space_that_is_not_deeper`, `longest_walk_that_the_depth_rule_allows_is_within_the_bound`, `spaces_nest_no_deeper_than_the_tree` (+4 more)) |
| M066 | `new/helper` | `model/src/caps.rs` | fits() CSpace root uses >= instead of > | Killed (`root_capability_of_a_space_is_placed_only_in_a_space_less_deep`, `root_capability_of_a_space_moved_by_ipc_follows_the_depth_rule`, `space_is_created_only_in_a_space_less_deep` (+1 more)) |
| M067 | `new/helper` | `model/src/caps.rs` | fits() CSpace ignores if root | Killed (`capability_of_another_kind_moves_into_any_capability_space`, `copy_of_a_space_capability_is_derived_into_any_space`, `cspace_that_holds_its_own_root_capability_can_be_deleted` (+4 more)) |
| M068 | `new/helper` | `model/src/caps.rs` | fits() depth < TREE_DEPTH instead of <= | Killed (`capability_at_depth_64_is_moved_by_ipc`, `derivation_deeper_than_64_is_invalid`, `depth_of_a_capability_to_derive_is_judged_before_the_next_listed_slot` (+6 more)) |
| M069 | `new/budget` | `model/src/caps.rs` | swept() starts at slot 0 instead of slot 1 | Killed (`slot_through_a_capability_for_a_dying_space_is_gone`, `three_layers_of_spaces_create_spaces_and_hand_memory_down`, `longest_walk_that_the_depth_rule_allows_is_within_the_bound` (+1 more)) |
| M070 | `new/budget` | `model/src/caps.rs` | swept() does not decrement slots budget on empty/dead slots | Killed (`removal_examines_at_most_128_slots_of_dying_spaces_per_call`, `root_capability_of_a_space_is_placed_only_in_a_space_less_deep`, `slot_of_the_root_capability_of_a_dying_space_counts_as_examined` (+2 more)) |
| M071 | `new/budget` | `model/src/caps.rs` | swept() decrements slots budget by 2 instead of 1 | Killed (`caller_is_woken_with_gone_when_a_sweep_destroys_its_reply_object`, `cspace_that_holds_its_own_root_capability_can_be_deleted`, `deleting_the_first_capability_space_destroys_everything_in_it` (+17 more)) |
| M072 | `new/budget` | `model/src/caps.rs` | swept() decrements slots budget even when returning Swept::Holds(held) | Killed (`deleting_the_first_capability_space_destroys_everything_in_it`, `destroying_a_cspace_destroys_the_objects_whose_root_it_holds`, `root_capability_of_a_space_is_placed_only_in_a_space_less_deep` (+2 more)) |
| M073 | `new/budget` | `model/src/caps.rs` | swept() does not skip held == cap (root of space) | Killed (`cspace_that_holds_its_own_root_capability_can_be_deleted`, `deleting_the_first_capability_space_destroys_everything_in_it`, `slot_of_the_root_capability_of_a_dying_space_counts_as_examined` (+2 more)) |
| M074 | `new/budget` | `model/src/caps.rs` | swept() resets sweep.next to 1 on each next_removed call | **TIMEOUT** (infinite loop) |
| M075 | `new/budget` | `model/src/caps.rs` | remove() resets slots budget on every step of the loop instead of per call | Killed (`root_capability_of_a_space_is_placed_only_in_a_space_less_deep`) |
| M076 | `new/budget` | `model/src/caps.rs` | next_removed does not mark root cap as dying when reached | Killed (`object_is_dying_as_soon_as_a_removal_reaches_its_root_capability`, `three_layers_of_spaces_create_spaces_and_hand_memory_down`, `longest_walk_that_the_depth_rule_allows_is_within_the_bound` (+1 more)) |
| M077 | `new/budget` | `model/src/caps.rs` | next_removed does not wake waiter on dying reply object | Killed (`caller_is_woken_with_gone_when_a_sweep_destroys_its_reply_object`, `destroying_a_reply_object_wakes_its_caller_and_its_receiver_with_gone`, `marking_a_reply_object_as_dying_wakes_the_caller_it_is_armed_with` (+3 more)) |
| M078 | `new/budget` | `model/src/caps.rs` | next_removed only wakes Attached on dying reply, not Armed | Killed (`caller_is_woken_with_gone_when_a_sweep_destroys_its_reply_object`, `destroying_a_reply_object_wakes_its_caller_and_its_receiver_with_gone`, `marking_a_reply_object_as_dying_wakes_the_caller_it_is_armed_with`) |
| M079 | `new/budget` | `model/src/caps.rs` | next_removed only wakes Armed on dying reply, not Attached | Killed (`destroying_a_reply_object_wakes_its_caller_and_its_receiver_with_gone`, `marking_a_reply_object_as_dying_wakes_the_receiver_attached_to_it`, `wake_of_the_step_that_marks_a_reply_object_is_not_counted` (+1 more)) |
| M080 | `new/budget` | `model/src/caps.rs` | longest_walk is not updated in next_removed | Killed (`check::tests::walk_of_a_removal_is_measured`) |
| M081 | `lib` | `model/src/lib.rs` | BOOT_UNTYPED_BYTES = 4 << 30 -> 2 << 30 | Killed (`frame_of_1_gb_pages_is_aligned_on_1_gb`, `start_up_untypeds_have_the_sizes_that_the_model_states`) |
| M082 | `lib` | `model/src/lib.rs` | BOOT_DEVICE_BYTES = 1 << 20 -> 2 << 20 | Killed (`start_up_untypeds_have_the_sizes_that_the_model_states`) |
| M083 | `lib` | `model/src/lib.rs` | boot() gives device untyped Rights::ALL (with EXEC) | Killed (`check::tests::attached_reply_object_whose_thread_does_not_wait_with_it_is_reported`, `check::tests::capability_space_state_of_an_object_of_another_kind_is_reported`, `check::tests::capability_space_over_its_maximum_is_reported` (+99 more)) |
| M084 | `lib` | `model/src/lib.rs` | boot() does not mark device untyped as device = true | Killed (`check::tests::child_untyped_of_device_memory_that_is_not_device_memory_is_reported`, `check::tests::exec_on_device_memory_is_reported`, `check::tests::kernel_object_on_device_memory_is_reported`) |
| M085 | `lib` | `model/src/lib.rs` | apply() does not clear thread.outcome = None | Killed (`client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped`, `destroying_an_object_wakes_the_threads_that_wait_on_it_with_gone`, `marking_a_reply_object_as_dying_wakes_the_receiver_attached_to_it` (+4 more)) |
| M086 | `lib` | `model/src/lib.rs` | Syscall::Other skips addressed_space check (dying/destroyed space) | Killed (`thread_whose_capability_space_is_destroyed_gets_gone_from_every_call`, `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete`) |
| M087 | `lib` | `model/src/lib.rs` | through() does not check ObjectKind::CSpace | Killed (`via_must_name_a_live_cspace_capability`) |
| M088 | `lib` | `model/src/lib.rs` | through() always checks Rights::READ instead of right | Killed (`arguments_of_call_are_checked_in_the_order_of_the_table`, `arguments_of_reply_recv_are_checked_in_the_order_of_the_table`, `cap_delete_on_a_dead_slot_through_a_cspace_capability_needs_write` (+7 more)) |
| M089 | `lib` | `model/src/lib.rs` | full() returns Invalid on Slot::Dead instead of Gone | Killed (`arguments_of_call_are_checked_in_the_order_of_the_table`, `arguments_of_reply_recv_are_checked_in_the_order_of_the_table`, `cap_delete_removes_the_descendants_instead_of_handing_them_up` (+35 more)) |
| M090 | `lib` | `model/src/lib.rs` | is() checks rights before kind | Killed (`kind_is_checked_before_rights`) |
| M091 | `lib` | `model/src/lib.rs` | destination() allows index == 0 | Killed (`cap_derive_checks_the_destination_before_the_rights_asked_for`, `cap_move_checks_the_source_before_the_destination`, `slot_zero_is_never_used` (+2 more)) |
| M092 | `lib` | `model/src/lib.rs` | destination() uses > instead of >= for slots.len() | Killed (`cap_derive_takes_a_full_source_and_an_empty_destination`, `cspace_is_created_with_no_slot_and_grows_by_one_segment`, `empty_or_out_of_range_slot_is_invalid`) |
| M093 | `lib` | `model/src/lib.rs` | vacant() treats Slot::Dead as Ok(()) | Killed (`dead_slot_is_not_free`) |
| M094 | `lib` | `model/src/lib.rs` | window() does not ignore range.first when range.count == 0 | Killed (`address_of_an_empty_receive_range_is_not_looked_at`) |
| M095 | `lib` | `model/src/lib.rs` | window() checks Rights::READ instead of Rights::WRITE on cspace | Killed (`arguments_of_call_are_checked_in_the_order_of_the_table`, `arguments_of_reply_recv_are_checked_in_the_order_of_the_table`, `receive_range_through_a_cspace_capability_needs_write` (+1 more)) |
| M096 | `lib` | `model/src/lib.rs` | window() allows first == 0 when count > 0 | Killed (`receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid`) |
| M097 | `lib` | `model/src/lib.rs` | window() uses >= instead of > for end > slots.len() | Killed (`receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid`) |
| M098 | `lib` | `model/src/lib.rs` | thread_configure requires Rights::WRITE instead of Rights::MANAGE on cspace | Killed (`capability_arguments_are_checked_in_the_order_of_the_table`, `thread_configure_needs_manage_on_the_thread_the_cspace_and_the_aspace`) |
| M099 | `lib` | `model/src/lib.rs` | thread_configure requires Rights::WRITE instead of Rights::MANAGE on aspace | Killed (`capability_arguments_are_checked_in_the_order_of_the_table`, `thread_configure_needs_manage_on_the_thread_the_cspace_and_the_aspace`) |
| M100 | `lib` | `model/src/lib.rs` | thread_configure requires Rights::MANAGE instead of Rights::SEND on fault endpoint | Killed (`thread_configure_needs_send_on_the_fault_endpoint`) |
| M101 | `lib` | `model/src/lib.rs` | thread_configure allows configuring a running thread (!target.suspended omitted) | Killed (`thread_configure_is_busy_unless_the_thread_is_suspended`) |
| M102 | `lib` | `model/src/lib.rs` | thread_configure allows configuring a waiting thread (target.wait != Wait::None omitted) | Killed (`thread_configure_is_busy_on_a_thread_that_waits`, `thread_configure_is_busy_in_every_wait`) |
| M103 | `lib` | `model/src/lib.rs` | thread_resume refuses a thread bound to a dying space | Killed (`thread_bound_to_a_dying_space_can_be_resumed`) |
| M104 | `lib` | `model/src/lib.rs` | thread_resume succeeds if already running even when space is destroyed | Killed (`thread_resume_is_busy_for_a_thread_that_runs_in_a_destroyed_space`) |
| M105 | `lib` | `model/src/lib.rs` | thread_suspend refuses a thread bound to no space | Killed (`thread_suspend_succeeds_on_a_thread_bound_to_no_capability_space`) |
| M106 | `caps` | `model/src/caps.rs` | footprint Untyped allows size < PAGE (e.g. >= 2048) | Killed (`child_untyped_is_a_power_of_two_of_at_least_4_kb`) |
| M107 | `caps` | `model/src/caps.rs` | footprint Untyped does not check is_power_of_two | Killed (`child_untyped_is_a_power_of_two_of_at_least_4_kb`) |
| M108 | `caps` | `model/src/caps.rs` | footprint CSpace does not round directory size up to power of two | Killed (`cspace_directory_is_rounded_up_to_a_power_of_two`) |
| M109 | `caps` | `model/src/caps.rs` | footprint CSpace allows size < CSPACE_MAX_SLOTS instead of <= | Killed (`cspace_maximum_is_a_whole_number_of_segments_up_to_2_to_the_20`, `removal_examines_at_most_128_slots_of_dying_spaces_per_call`, `segments_that_were_never_added_are_not_examined`) |
| M110 | `caps` | `model/src/caps.rs` | footprint align for CSpace/other objects does not cap at PAGE (4 KB) | Killed (`kernel_object_larger_than_4_kb_is_aligned_on_4_kb`) |
| M111 | `caps` | `model/src/caps.rs` | footprint align for Frame uses PAGE instead of page.bytes() | Killed (`frame_of_1_gb_pages_is_aligned_on_1_gb`, `large_frame_is_aligned_on_its_page_size`) |
| M112 | `caps` | `model/src/caps.rs` | cap_derive checks destination before DERIVE right on source | Killed (`cap_derive_checks_the_destination_before_the_rights_asked_for`) |
| M113 | `caps` | `model/src/caps.rs` | cap_derive checks badge before rights subset | Killed (`plain_arguments_of_cap_derive_are_judged_in_the_order_of_the_table`) |
| M114 | `caps` | `model/src/caps.rs` | cap_derive refuses badge == kept on already-badged capability | Killed (`badged_capability_keeps_its_badge_and_refuses_another`, `plain_arguments_of_cap_derive_are_judged_in_the_order_of_the_table`) |
| M115 | `caps` | `model/src/caps.rs` | cap_derive overwrites kept badge when badge == 0 | **SURVIVED** (Equivalent) |
| M116 | `caps` | `model/src/caps.rs` | cap_derive checks vacant(place) before fits() | Killed (`refused_derivation_or_creation_is_invalid_before_no_slot`) |
| M117 | `caps` | `model/src/caps.rs` | cap_move requires Rights::READ instead of Rights::WRITE on source | Killed (`changing_a_slot_through_a_cspace_capability_needs_write`, `reading_a_slot_through_a_cspace_capability_needs_read`) |
| M118 | `caps` | `model/src/caps.rs` | cap_move checks vacant(place) before fits() | Killed (`refused_move_is_invalid_before_no_slot`) |
| M119 | `caps` | `model/src/caps.rs` | cap_delete allows via != 0 when caller's space is dying | Killed (`thread_whose_capability_space_is_dying_deletes_its_own_slots_only`) |
| M120 | `caps` | `model/src/caps.rs` | cap_delete refuses all calls when caller's space is dying | Killed (`cap_delete_on_an_empty_slot_of_an_own_dying_space_is_invalid`, `removal_begun_inside_a_dying_space_is_finished_by_the_sweep`, `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` (+1 more)) |
| M121 | `caps` | `model/src/caps.rs` | cap_delete requires Rights::READ instead of Rights::WRITE on through() | Killed (`cap_delete_on_a_dead_slot_through_a_cspace_capability_needs_write`, `changing_a_slot_through_a_cspace_capability_needs_write`) |
| M122 | `caps` | `model/src/caps.rs` | cap_delete does not mark cap.dying = true on first step | Killed (`check::tests::census_counts_what_the_state_holds`) |
| M123 | `caps` | `model/src/caps.rs` | cap_revoke requires Rights::READ instead of Rights::WRITE on slot | Killed (`changing_a_slot_through_a_cspace_capability_needs_write`) |
| M124 | `caps` | `model/src/caps.rs` | untyped_retype checks footprint before device memory rule | Killed (`device_memory_refuses_a_kind_that_is_not_made_as_invalid_whatever_the_size`, `untyped_retype_judges_the_kind_before_the_size`) |
| M125 | `caps` | `model/src/caps.rs` | untyped_retype checks take() before vacant() | Killed (`dead_slot_is_not_free`, `no_slot_is_reported_before_no_memory`, `refused_derivation_or_creation_is_invalid_before_no_slot` (+2 more)) |
| M126 | `caps` | `model/src/caps.rs` | untyped_retype always gives Rights::ALL regardless of untyped's EXEC right | Killed (`child_untyped_has_exec_only_if_the_untyped_capability_has_it`, `device_memory_becomes_only_a_frame_or_a_child_untyped`, `new_capability_has_every_right` (+3 more)) |
| M127 | `caps` | `model/src/caps.rs` | cspace_grow checks slots.len() > *max instead of >= | Killed (`cspace_grow_checks_the_untyped_then_the_maximum_then_the_memory`, `cspace_grow_is_no_slot_at_the_maximum`) |
| M128 | `caps` | `model/src/caps.rs` | cspace_grow aligns segment on 8 bytes instead of SEGMENT_BYTES (4 KB) | Killed (`segment_is_aligned_on_4_kb`, `segments_go_back_to_the_untyped_when_the_cspace_is_destroyed`) |
| M129 | `caps` | `model/src/caps.rs` | release() resets watermark when live <= 1 instead of live == 0 | Killed (`destroying_a_cspace_removes_its_capabilities_in_index_order`, `removal_begun_inside_a_dying_space_is_finished_by_the_sweep`, `thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed` (+4 more)) |
| M130 | `caps` | `model/src/caps.rs` | remove() leaves Slot::Dead instead of Slot::Empty on target slot | Killed (`cap_delete_and_cap_revoke_need_no_right_on_the_capability`, `cap_delete_through_a_cspace_capability_leaves_the_slot_empty`, `cap_delete_removes_the_descendants_instead_of_handing_them_up` (+11 more)) |
| M131 | `caps` | `model/src/caps.rs` | remove() leaves Slot::Empty instead of Slot::Dead on descendant slots | Killed (`arguments_of_call_are_checked_in_the_order_of_the_table`, `arguments_of_reply_recv_are_checked_in_the_order_of_the_table`, `cap_delete_on_a_dead_slot_makes_it_empty` (+37 more)) |
| M132 | `caps` | `model/src/caps.rs` | remove() takes first child instead of last (oldest instead of most recent) | Killed (`cap_revoke_removes_32_capabilities_then_returns_again`) |
| M133 | `caps` | `model/src/caps.rs` | next_removed() takes first child instead of last | Killed (`capability_is_removed_after_its_descendants_the_most_recent_first`, `copy_under_cap_delete_is_dying_and_its_object_is_not`, `removal_does_not_end_while_another_thread_derives_33_capabilities_per_step` (+1 more)) |
| M134 | `caps` | `model/src/caps.rs` | waiter() pops from back instead of front (LIFO instead of FIFO) | Killed (`destroying_an_object_wakes_its_waiters_first_in_first_out`, `destroying_an_endpoint_wakes_its_callers_32_per_call`) |
| M135 | `caps` | `model/src/caps.rs` | destroy() CSpace does not release segments back to untyped | Killed (`caller_is_woken_with_gone_when_a_sweep_destroys_its_reply_object`, `cspace_that_holds_its_own_root_capability_can_be_deleted`, `delivery_into_a_destroyed_capability_space_drops_the_capabilities` (+17 more)) |
| M136 | `ipc` | `model/src/ipc.rs` | Message::check() allows non-zero flags from sender | Killed (`grant_is_judged_before_the_limits_of_the_header`, `header_with_a_flag_set_by_the_sender_is_invalid`) |
| M137 | `ipc` | `model/src/ipc.rs` | Message::rights() does not require GRANT when caps are present | Killed (`grant_is_judged_before_the_limits_of_the_header`, `message_with_capabilities_needs_grant`) |
| M138 | `ipc` | `model/src/ipc.rs` | call() checks listed() before message.check() | Killed (`header_is_read_right_after_the_capability_the_call_acts_on`, `header_limits_are_checked_before_the_listed_slots`) |
| M139 | `ipc` | `model/src/ipc.rs` | call() checks window() before listed() | Killed (`arguments_of_call_are_checked_in_the_order_of_the_table`) |
| M140 | `ipc` | `model/src/ipc.rs` | recv() checks ReplyState::Idle before window() | Killed (`state_is_checked_after_every_argument`) |
| M141 | `ipc` | `model/src/ipc.rs` | reply_recv() checks endpoint before message.check() and listed() | Killed (`header_is_read_right_after_the_capability_the_call_acts_on`, `reply_recv_checks_the_listed_slots_before_the_endpoint`) |
| M142 | `ipc` | `model/src/ipc.rs` | reply_recv() uses badge of endpoint instead of 0 for reply parcel | Killed (`reply_of_reply_recv_carries_badge_0`, `reply_recv_answers_and_returns_a_pending_notification_before_a_caller`, `reply_recv_answers_before_it_receives` (+2 more)) |
| M143 | `ipc` | `model/src/ipc.rs` | send() checks listed() before message.check() | Killed (`header_limits_are_checked_before_the_listed_slots`, `header_is_read_right_after_the_capability_the_call_acts_on`) |
| M144 | `ipc` | `model/src/ipc.rs` | signal() overwrites notify.word (=) instead of bitwise OR (\|=) | Killed (`recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller`, `signal_sets_bit_0_or_the_bits_of_the_badge`) |
| M145 | `ipc` | `model/src/ipc.rs` | signal() with badge == 0 sets 0 instead of bit 0 (1) | Killed (`binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive`, `binding_delivers_nothing_to_a_caller_in_the_queue`, `binding_to_a_dying_endpoint_is_removed_and_the_word_goes_elsewhere` (+21 more)) |
| M146 | `ipc` | `model/src/ipc.rs` | hand_over() serves bound endpoint receiver before notify waiter | Killed (`signal_on_a_bound_notify_prefers_a_thread_that_waits_on_the_notify`, `thread_that_waits_on_the_notify_is_served_before_a_receiver_of_the_endpoint`) |
| M147 | `ipc` | `model/src/ipc.rs` | notify_bind() does not call hand_over(notify) after binding | Killed (`binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive`, `binding_to_a_dying_endpoint_is_removed_and_the_word_goes_elsewhere`) |
| M148 | `ipc` | `model/src/ipc.rs` | notify_bind() allows binding when endpoint already has a notify | Killed (`notify_bind_is_busy_when_either_side_is_already_bound`) |
| M149 | `ipc` | `model/src/ipc.rs` | notify_bind() allows binding when notify already has an endpoint | Killed (`notify_bind_is_busy_when_either_side_is_already_bound`) |
| M150 | `ipc` | `model/src/ipc.rs` | listed() checks depth > TREE_DEPTH instead of >= TREE_DEPTH | Killed (`derivation_deeper_than_64_is_invalid`, `depth_of_a_capability_to_derive_is_judged_before_the_next_listed_slot`, `capability_at_depth_64_is_moved_by_ipc` (+1 more)) |
| M151 | `ipc` | `model/src/ipc.rs` | listed() checks depth for Listed::Move as well as Listed::Derive | Killed (`capability_at_depth_64_is_moved_by_ipc`) |
| M152 | `ipc` | `model/src/ipc.rs` | receive() checks callers before pending notification on bound notify | Killed (`binding_delivers_nothing_to_a_caller_in_the_queue`, `recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller`, `reply_recv_answers_and_returns_a_pending_notification_before_a_caller`) |
| M153 | `ipc` | `model/src/ipc.rs` | answer() drops flags from request when delivering reply | Killed (`empty_range_refuses_every_capability_and_the_words_still_arrive`, `reply_header_has_the_dropped_flag_of_the_request_with_the_capabilities_of_the_reply`) |
| M154 | `ipc` | `model/src/ipc.rs` | deliver() allows delivering capabilities into a dying cspace | Killed (`delivery_into_a_dying_capability_space_drops_the_capabilities`) |
| M155 | `ipc` | `model/src/ipc.rs` | deliver() does not check fits() at delivery | Killed (`capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped`, `capability_moved_by_ipc_into_a_space_that_cannot_hold_it_is_dropped`, `depth_rule_is_judged_on_each_capability_of_a_message` (+1 more)) |
| M156 | `ipc` | `model/src/ipc.rs` | deliver() loses badge on Derived capability | Killed (`derived_capability_is_a_child_of_the_sender_s_and_keeps_its_badge`) |
| M157 | `ipc` | `model/src/ipc.rs` | deliver() places all capabilities into window.first instead of window.first + i | Killed (`capabilities_of_one_message_each_land_in_their_own_slot`, `transfer_is_all_or_nothing`, `two_slots_for_one_object_are_listed_in_one_message`) |
| M158 | `ipc` | `model/src/ipc.rs` | receiver() pops from back instead of front (LIFO receivers) | Killed (`receivers_are_served_first_in_first_out`) |
| M159 | `ipc` | `model/src/ipc.rs` | take_caller() pops from back instead of front (LIFO callers) | Killed (`call_joins_the_queue_and_recv_takes_the_first_caller`, `reply_recv_answers_the_caller_then_receives`, `reply_recv_answers_before_it_receives` (+2 more)) |
| M160 | `abi` | `abi/src/lib.rs` | StartHeader field order version and entries swapped | **SURVIVED** |
| M161 | `abi` | `abi/src/lib.rs` | StartEntry field order offset and len swapped | **SURVIVED** |
| M162 | `new/helper` | `model/src/caps.rs` | fits() moved_root ignores source != own (space holding own root treated as moved_root) | Killed (`cspace_that_holds_its_own_root_capability_can_be_deleted`, `slot_of_the_root_capability_of_a_dying_space_counts_as_examined`, `sweep_goes_on_past_the_root_capability_of_the_space`) |
| M163 | `new/helper` | `model/src/caps.rs` | fits() moved_root is always false (moved cspace roots never checked for depth) | Killed (`root_capability_of_a_space_is_placed_only_in_a_space_less_deep`, `root_capability_of_a_space_moved_by_ipc_follows_the_depth_rule`, `spaces_nested_at_the_same_depth_are_refused`) |
| M164 | `new/budget` | `model/src/caps.rs` | next_removed assert walk <= 2 * LONGEST_WALK -> walk < LONGEST_WALK | Killed (`longest_walk_that_the_depth_rule_allows_is_within_the_bound`) |
| M165 | `new/budget` | `model/src/caps.rs` | swept() only counts Full(_) and Empty slots against budget, not Dead slots | Killed (`supervisor_kills_a_process_by_deleting_its_space_then_its_untyped`) |
| M166 | `new/budget` | `model/src/caps.rs` | swept() only counts Dead and Full(_) slots against budget, not Empty slots | Killed (`removal_examines_at_most_128_slots_of_dying_spaces_per_call`, `root_capability_of_a_space_is_placed_only_in_a_space_less_deep`, `slot_of_the_root_capability_of_a_dying_space_counts_as_examined` (+1 more)) |
| M167 | `new/cancel` | `model/src/ipc.rs` | unlink on Wait::Call does not remove thread from endpoint queue | Killed (`check::tests::walk_of_a_removal_is_measured`) |
| M168 | `new/cancel` | `model/src/ipc.rs` | unlink on Wait::Notify does not remove thread from notify waiters | Killed (`destroying_an_object_wakes_the_threads_that_wait_on_it_with_gone`, `destroying_an_object_wakes_its_waiters_first_in_first_out`, `outcome_of_a_cancelled_wait_is_cleared_by_the_next_call_of_the_thread` (+11 more)) |
| M169 | `new/helper` | `model/src/lib.rs` | object_at() does not check Rights::READ | **SURVIVED** |
| M170 | `new/budget` | `model/src/caps.rs` | next_removed counts reply wake against slots budget | **SURVIVED** |
| M171 | `new/budget` | `model/src/caps.rs` | next_removed counts waking a reply object's thread against steps budget | Killed (`one_call_wakes_a_thread_of_a_reply_object_at_each_of_its_32_steps`, `wake_of_the_step_that_marks_a_reply_object_is_not_counted`) |
| M172 | `new/budget` | `model/src/caps.rs` | swept() does not count root capability slot of dying space against slots budget when skipping it | Killed (`slot_of_the_root_capability_of_a_dying_space_counts_as_examined`) |
| M173 | `new/cancel` | `model/src/lib.rs` | thread_cancel checks bound_space of target thread (returns Busy if unconfigured or space destroyed) | **SURVIVED** |
| M174 | `new/cancel` | `model/src/lib.rs` | thread_cancel clears existing outcome when target thread is not waiting | Killed (`thread_cancel_leaves_the_outcome_of_a_wait_that_is_already_over`) |
| M175 | `new/helper` | `model/src/lib.rs` | dying() returns true for any object whose root has children | Killed (`check::tests::caller_and_receiver_in_one_queue_are_reported`, `check::tests::binding_that_only_the_endpoint_names_is_reported`, `check::tests::caller_of_a_dying_reply_object_is_reported` (+101 more)) |
| M176 | `ipc` | `model/src/ipc.rs` | deliver() does not check window.cspace existence when checking empty() | Killed (`delivery_into_a_dying_capability_space_drops_the_capabilities`) |
| M177 | `ipc` | `model/src/ipc.rs` | reply_recv() checks ReplyState::Attached before endpoint and window | Killed (`arguments_of_reply_recv_are_checked_in_the_order_of_the_table`) |
| M178 | `abi` | `abi/src/lib.rs` | Header::new shift for caps 39 -> 38 | Killed (`abi::tests::header_round_trips_at_the_limits`) |
| M179 | `abi` | `abi/src/lib.rs` | Header::new shift for flags 42 -> 43 | Killed (`abi::tests::header_round_trips_at_the_limits`) |
| M180 | `abi` | `abi/src/lib.rs` | SlotAddr::through shift 32 -> 31 | Killed (`abi::tests::slot_address_splits_into_via_and_index`) |

---

## What Was Checked and Found Sound

1. **`model/src/check/tests.rs` (61 unit tests for Invariants 1–28):** Sound — every single invariant numbered 1 through 28 in `check.rs` has a targeted negative unit test that constructs a minimal invalid state and asserts the exact invariant number and message.
2. **Core `thread_cancel` and `Error::Cancelled` semantics (`calls.rs:4027-4214`, `property.rs:1294`):** Sound — cancelling all 4 wait sorts (`Call`, `Reply`, `Recv`, `Notify`), dropping late replies (`send` -> `WouldWait`, `reply_recv` -> dropped), preserving suspended state, not remembering a cancel before a wait, preserving an already-completed wait outcome, clearing `outcome` on the next call, and requiring `Rights::MANAGE` are all thoroughly tested and killed 17 of 18 `new/cancel` mutants.
3. **128-slot examination budget (`REMOVAL_SLOTS`) and `CSpace` sweep (`calls.rs:2594-2624, 3115-3143, 3926-3963`):** Sound on empty, dead, and root-capability slots — `M001`, `M002`, `M069`–`M075`, `M165`, `M166`, and `M172` were all killed (only the interaction with waking a dying reply object's thread, `M170`, survived).
4. **Constants moved to `abi/` (`REMOVAL_SLOTS`, `LONGEST_WALK`, `CSPACE_MAX_SLOTS`, `CSPACE_DIRECTORY_BYTES`, object sizes):** Sound — all 13 `abi/new` mutants (`M001`–`M013`) were killed by `numbers_of_the_contract_are_those_of_the_interface` and behavioral tests in `calls.rs`.
5. **93 of the 95 sampled tests in `model/tests/calls.rs`:** Sound — they test what their names claim with distinct error codes and non-vacuous assertions.
