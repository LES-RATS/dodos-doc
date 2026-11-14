# DodOS one-core model review 3 (bounded work, termination, and contract consistency)

Reviewed against:
- Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
- ABI: `/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs`
- Model (branch `model`): `/Users/btw/Documents/repos/dodos-kernel/model/src/{lib.rs,caps.rs,ipc.rs,check.rs,check/tests.rs}` and `/Users/btw/Documents/repos/dodos-kernel/model/tests/{calls.rs,property.rs}`

Baseline suite (`cargo test -p dodos-model`) passed (unit tests, 207 `calls` tests, 4 `property` tests). Six additional behaviours were confirmed with an external scratch crate (`review_checks`, outside both repositories).

---

## Bounded-work and termination analysis (Rule 4)

Under a real no-heap kernel with fixed-size objects and intrusive wait-queue / derivation-tree links:

| Operation | Real-kernel work bound | Worst case |
|---|---|---|
| `cap_derive`, `cap_move`, `cap_inspect` | $O(1)$ | Depth lookup along `TREE_DEPTH <= 64` (or cached `u8` depth) + 1 slot write + intrusive list insert/move. |
| `untyped_retype` | Bounded $O(1)$ object clear | Creating a max-size `cspace` (`2^20` slots): clears **64 KB** directory (`8 bytes * 8192`, rounded to power of two). Next largest: `aspace` (**4 KB**), `thread` (**1 KB + processor vector state**), `sched` (**128 B**), `endpoint`/`reply`/`notify` (**64 B**). `frame` and `untyped` are **not** cleared. |
| `cspace_grow` | Bounded $O(1)$ | Clears one **4 KB** segment (`128 * 32 B`) and updates the directory entry. |
| `cap_delete`, `cap_revoke` | $O(1)$ bounded per call | Budget: at most **32** capability removals or waiter wakes, plus **128** examined slots across dying `cspace`s, plus at most **1** reply-object wake per walk (uncounted). Each step walks at most **191** capabilities (`S1 -> U1 -> ... -> S63 -> U63 -> S64 -> O1..O64`; contract states 192). Worst case per call: `32 * 191 = 6,112` tree/slot hops + `128` slot scans + up to `32` reply wakes. Destruction of a full `2^20`-slot `cspace` is `live -= 1 + segments` (`O(1)` arithmetic; `caps.rs:578-580` loops up to `8192`). |
| `call`, `recv`, `reply_recv`, `send` | $O(1)$ | Validate at most `4` listed slots (`listed`), copy at most `64` words and `4` capabilities, unlink/enqueue `1` thread via intrusive doubly-linked list (`ipc.rs:452-468` uses `VecDeque::retain`, which is $O(n)$ in the model only). |
| `signal`, `wait`, `poll`, `notify_bind` | $O(1)$ | Bitwise `word` update, optional intrusive queue push/pop (`1` thread), and optional bound-endpoint delivery. |
| `thread_configure`, `thread_resume`, `thread_suspend` | $O(1)$ | Validate up to 4 capabilities, update thread fields. |

**Termination and user-controlled work:**
- No call's per-call work grows unboundedly with user-controlled state in a real kernel: the largest memory clear is capped at 64 KB (`cspace` directory), message length at 64 words / 4 caps, tree depth at 64, walk length at 191, and removal work at 32 steps / 128 slots per call.
- **Unbounded multi-step termination:** While `cap_delete` or `cap_revoke` returns `Again` between steps, unreached descendant capabilities (and unreached child `cspace`s) are not yet marked `dying`, so competing threads can keep deriving new descendants between steps and prevent termination (see Finding 2 below).

---

## Findings

### 1. Header validation vs `GRANT` right ordering contradicts Step 1 / Step 2
- **Severity:** `contract error`
- **Where:** `Docs/architecture/kernel-interface.md:102-103, 145, 147, 148`; `model/src/ipc.rs:83-85, 136-138, 161-164`
- **What is wrong:** Step 1 (`kernel-interface.md:102`) checks the target capability's slot, kind, and rights (`denied`). Step 2 (`kernel-interface.md:103`) states: *"a header is read right after the capability the call acts on, because it says how many capabilities the message lists; a header beyond the limits, or with a flag bit set by the sender, is `invalid` before any other capability argument is looked at"*. However, `call`, `send`, and `reply_recv` only require `GRANT` *"if the message lists capabilities"* (`lines 145, 147, 148`). Determining whether `GRANT` is needed in Step 1 requires inspecting `header.caps() > 0` before Step 2 validates the header limits (`caps <= 4`). Two observably different implementations satisfy this text: checking `GRANT` before `message.check()` (returning `Denied` when `caps = 5` without `GRANT`, which the model does without a `CONTRACT-GAP` marker), or validating the header before checking `GRANT` (returning `Invalid`).
- **How you know:** Read in `kernel-interface.md` and `ipc.rs`; confirmed by scratch test `invalid_header_with_five_caps_checks_grant_before_header`: calling `Send`, `Call`, and `ReplyRecv` with 5 capabilities on an `Endpoint`/`Reply` lacking `Rights::GRANT` returns `Err(Error::Denied)` rather than `Err(Error::Invalid)`.
- **What you suggest:** Explicitly specify in `Order of checks` whether header validity (`invalid`) precedes the conditional `grant` right check (`denied`), or vice versa, and align `ipc.rs` (or add a `CONTRACT-GAP` if left open).

### 2. `cap_delete` also fails to terminate when competing threads act in unreached descendants
- **Severity:** `contract error`
- **Where:** `Docs/architecture/kernel-interface.md:93-94`; `model/src/caps.rs:156-158, 466-467`
- **What is wrong:** `kernel-interface.md:94` states: *"One limit is accepted: while `cap_revoke` runs, threads that hold capabilities under it can still derive new ones. Each call removes 32 capabilities against at most four new capabilities per competing call (a message), and a supervisor that wants a certain end suspends those threads first."* It does not mention `cap_delete`. However, `cap_delete` only marks the target capability (`caps.rs:157`) and reached root capabilities (`caps.rs:467`) as `dying`. Whenever `cap_delete` stops with `Again` before reaching a descendant capability `C` (or an older child `CSpace` behind a younger child subtree of >32 caps), `C` and that child `CSpace` remain live (`!dying`), so competing threads can continue deriving/creating capabilities under `C` (or inside that child `CSpace`) between steps of `cap_delete` indefinitely. Additionally, comparing "32 capabilities against at most four new capabilities per competing call (a message)" assumes interleaving of at most one competing call per `cap_revoke`/`cap_delete` step, whereas an un-suspended thread can perform arbitrary `cap_derive` calls while preempted.
- **How you know:** Confirmed by two scratch tests:
  1. `cap_delete_on_copy_allows_competing_derives_on_unreached_descendant`: `UntypedRetype(Notify -> s(20))`, `CapDerive(20 -> 21)`, `CapDerive(21 -> 22)`, 35 derives `22 -> 30..64`, `CapDelete(21)` returns `Err(Error::Again)`; slots `33..64` are cleared and re-derived from `s(22)`, and the next `CapDelete(21)` again returns `Err(Error::Again)`.
  2. `cap_delete_on_untyped_with_younger_child_leaves_older_child_cspace_alive_between_steps`: child `CSpace` `s(21)` and younger child `Untyped` `s(23)` (with 35 `Notify`s) under `s(20)`; after `CapDelete(20)` returns `Err(Error::Again)`, a thread bound to `s(21)` still succeeds in `UntypedRetype` inside `s(21)`.
- **What you suggest:** Broaden `kernel-interface.md:94` from `cap_revoke` to *any removal (`cap_delete` or `cap_revoke`)* and clarify that termination in the presence of active threads requires suspending threads that hold unreached capabilities in the subtree.

### 3. `thread` object size contradicts the power-of-two object-size rule
- **Severity:** `contract error`
- **Where:** `Docs/architecture/kernel-interface.md:121, 283`; `model/src/caps.rs:58-60`
- **What is wrong:** `kernel-interface.md:121` states *"Object sizes are powers of two."* Yet `kernel-interface.md:283` defines `thread` size as *"1 KB, plus the vector state area, whose size depends on the processor"*. On x86-64, XSAVE vector state areas are typically not a power of two (and adding them to 1 KB produces a non-power-of-two total unless rounded up to the next power of two, which would over-allocate and leave alignment ambiguous between `1024`, `4096`, or the rounded size). The model currently sidesteps this with `ObjectKind::Thread => (1024, size == 0)` (`CONTRACT-GAP` at `caps.rs:58-60`).
- **How you know:** Read in `kernel-interface.md:121, 283` and `caps.rs:58-60`.
- **What you suggest:** State explicitly in `kernel-interface.md:283` (and `121`) whether `thread` size is rounded up to a power of two (e.g., 2 KB or 4 KB) or whether `thread` (like multi-page `frame`s) is an explicit exception aligned to 4 KB / 1 KB.

### 4. Minor contract text discrepancies (`cspace` directory rounding, dying `cap_delete`, walk bound 191 vs 192)
- **Severity:** `contract error`
- **Where:** `Docs/architecture/kernel-interface.md:75, 87, 93, 95, 121, 285`
- **What is wrong:**
  1. **Directory rounding (`line 75` vs `line 285`):** `line 75` specifies *"8 bytes per 128 slots, rounded up to a power of two"*, matching `line 121` (*"Object sizes are powers of two"*) and `caps.rs:54`. The Object sizes table (`line 285`) omits *"rounded up to a power of two"*, writing only *"8 bytes per 128 slots of the maximum"*.
  2. **Dying `cspace` (`line 93` vs `line 95`):** `line 93` allows *"cap_delete on its own slots"*, while `line 95` drops the qualifier (*"except cap_delete"*). The model implements `line 93` (`caps.rs:143`: `slot.via() != 0` returns `Gone`).
  3. **Walk bound (`line 87`):** The proof at `line 87` bounds the walk to `128 + 64 = 192` capabilities. Because a walk cannot traverse *both* a depth-64 `untyped` `U64` and a depth-64 ordinary child `O1` of `U64` (`O1` would have depth 65 > `TREE_DEPTH`), the true mathematical maximum is **191** (`S1, U1, ..., S63, U63, S64, O1..O64`). As an upper bound, `192` is safe.
- **How you know:** Read in `kernel-interface.md` and `caps.rs`; `191` confirmed by scratch test `longest_walk_can_reach_191` (`m.longest_walk() == 191`).
- **What you suggest:** Add *"rounded up to a power of two"* to `line 285`, add *"on its own slots"* to `line 95`, and optionally note 191 as the exact worst case in `line 87`.

### 5. Behaviour decided by the model without `CONTRACT-GAP` (and ABI rights decoding)
- **Severity:** `undefined`
- **Where:** `model/src/lib.rs:366-400`; `model/src/ipc.rs:83-85, 136-138, 161-164, 283-297`; `abi/src/lib.rs:132`
- **What is wrong:**
  1. **`GRANT` checked before header validation (`ipc.rs:83, 137, 161`):** Discussed in Finding 1; not marked `CONTRACT-GAP`.
  2. **`Transfer::Derive` rights vs duplicate slot in `listed` (`ipc.rs:283-297`):** `kernel-interface.md:163` specifies that duplicate-slot and depth checks occur *"with the slot, before the next listed slot"*, but does not fix the relative order *within* one `Derive` entry between `Rights::derive` (`Denied`) and duplicate-slot (`Invalid`). The model checks `derive` rights -> `depth` -> `duplicate`, so `[Move(s(30)), Derive(s(30), NONE)]` on a cap without `DERIVE` returns `Denied` instead of `Invalid`. Not marked `CONTRACT-GAP`.
  3. **Start-up image layout (`lib.rs:366-400`):** `Model::boot` fixes the boot `cspace` size to `128` (`CSPACE_SEGMENT_SLOTS`), creates one 64 MiB ordinary `untyped` and one 1 MiB device `untyped`, and omits `core`, `irq`, `ioports`, `iospace`, and boot `frame`s (though `kernel-interface.md:90` leaves boot `cspace` size to the boot image and those other objects belong to unmodelled groups). Not marked `CONTRACT-GAP`.
  4. **Unknown `Rights` bits (`abi/src/lib.rs:132`):** `Marks::from_bits(u64)` returns `Result<Marks, Error>` (`Err(Error::Invalid)`), whereas `Rights::from_bits(u32)` returns `Option<Rights>`. Neither `kernel-interface.md` nor `abi` states whether an unknown right bit passed in `cap_derive` or `Transfer::Derive` yields `Invalid` or `Denied` (the model accepts typed `Rights`, avoiding raw decoding).
- **How you know:** Read in `lib.rs`, `ipc.rs`, `abi/src/lib.rs`; item 2 confirmed by scratch test `listed_duplicate_slot_checks_derive_rights_before_duplicate`.
- **What you suggest:** Document the `listed` intra-entry check order and unknown `Rights` bit error in `kernel-interface.md` (or mark `CONTRACT-GAP` in `ipc.rs`), and add a brief note on `Model::boot`'s concrete boot `cspace` size (`128`).

### 6. Contract rules and error orders not covered by existing tests
- **Severity:** `untested`
- **Where:** `model/tests/calls.rs`, `model/tests/property.rs`, `model/src/check/tests.rs`
- **What is wrong:** The following contract rules have no unit test in `calls.rs` (nor targeted coverage in `check/tests.rs`):
  1. `send` on an **attached** `Reply` object returns `WouldWait` (only `Idle` is tested at `calls.rs:2507`).
  2. `send` on an `Idle` `Reply` object with a bad listed capability checks `listed` before `WouldWait`.
  3. `recv` with a `Busy` `Reply` object on an `Endpoint` whose bound `Notify` has a pending word returns `Busy` **without consuming** the pending word (confirmed by scratch test `busy_recv_does_not_consume_bound_notification`).
  4. `call` and `reply_recv` with an empty receive range (`count == 0`) ignoring a bad `first` address (only `recv` is tested at `calls.rs:1707`).
  5. `call`, `send`, and `reply_recv` with `caps.len() > MAX_CAPS` when the target capability lacks `GRANT`.
  6. `cap_delete` on a `CSpace` that holds its own root capability in an **earlier** slot and another capability in a **later** slot (verifying the sweep skips its own root and continues past it).
  7. `cap_delete` waking >32 threads from an `Endpoint` queue (callers or receivers) returning `Again` (`calls.rs:855` only tests `Notify` waiters).
  8. `untyped_retype` from an ordinary `Untyped` lacking `EXEC` creating a child `Untyped` (verifying `EXEC` is stripped on the child `Untyped`), and `Unsupported` kind tested before `NoSlot` / depth-64.
  9. `thread_configure` checking `thread` (`MANAGE` / kind) *before* `cspace`, and `thread_suspend` on a thread waiting in `Endpoint` (`Call` or `Recv`; `calls.rs:1578` only tests `Notify`).
  10. `reply_recv` with an armed `Reply` when `endpoint` has a pending notification (answers the caller, leaves `Reply` `Idle`, and returns the notification).
  11. Delivery into a **destroyed** (not merely dying) `CSpace` dropping capabilities while delivering words (`calls.rs` only unit-tests dying spaces).
- **How you know:** Read and searched `model/tests/calls.rs`, `model/tests/property.rs`, and `model/src/check/tests.rs`.
- **What you suggest:** Add unit tests to `model/tests/calls.rs` for these cases so the kernel conformance suite exercises them directly.

### 7. Model-only inefficiencies and stale `CONTRACT-GAP` comments
- **Severity:** `minor`
- **Where:** `model/src/caps.rs:63-67, 469-477, 515-519`; `model/src/ipc.rs:452-468`
- **What is wrong:**
  1. **Eager allocation in `next_removed` (`caps.rs:472-477`):** `space.sweep.get_or_insert(Sweep { next: 1, held })` eagerly iterates the entire `space.slots` vector and collects a `Vec<CapId>` on *every* step passing through an already-dying `CSpace`, discarding the vector when `sweep` is already `Some`. For a `2^20`-slot `CSpace`, a single 32-step `cap_delete` call scans 33M slots unnecessarily.
  2. **Stale `CONTRACT-GAP` comments (`caps.rs:63-67, 469-471, 515-519`):** All three describe behaviour that `kernel-interface.md` now specifies (`line 104` places `unsupported` after device memory and before size; `line 92` states *"The sweep of a space starts at slot 1; a slot counts as examined when the sweep moves past it, so a full slot is not counted while its capability is being removed."*). Note that `caps.rs:63-67` still partially reflects that `kernel-interface.md` does not enumerate which non-one-core kinds `untyped_retype` will eventually support vs reject.
  3. **Model wait-queue unlink (`ipc.rs:452-468`):** Uses `VecDeque::retain` ($O(n)$ in queue length); acceptable for the reference model, provided the kernel implementation uses intrusive doubly-linked lists in `Thread` ($O(1)$).
- **How you know:** Read in `caps.rs`, `ipc.rs`, and `kernel-interface.md`.
- **What you suggest:** Replace `get_or_insert(...)` at `caps.rs:477` with `get_or_insert_with(|| ...)` and update or remove the three stale `CONTRACT-GAP` comments.

---

## Checked and found correct

- **Capability tree & depth rule (`caps.rs:253-271`):** `fits` cleanly enforces depth $\le 64$, `untyped` depth $\ge$ space depth, and child `cspace` root depth $>$ space depth across `cap_derive`, `cap_move`, `untyped_retype`, and IPC delivery, ruling out self-referential removal cycles.
- **Removal steps & reply-object invariant (`caps.rs:414-563`):** `remove`, `next_removed`, `swept`, and `destroy` faithfully respect the 32-step / 128-slot budgets, mark `target` and reached roots `dying` on step 1, wake waiting reply callers/receivers once per walk without counting against the 32 budget, leave `Empty` on `cap_delete` target vs `Dead` on indirect removals, and release `1 + segments` on `CSpace` destruction.
- **Untyped watermark & alignment (`caps.rs:41-79, 275-295`):** `footprint`, `take`, and `release` match `kernel-interface.md:121`, including 4 KB alignment cap on non-frame/non-untyped objects, `checked_mul` / `checked_add` overflow checks, and watermark reset only when `live == 0`.
- **IPC, reply objects, capability transfer, and notifications (`ipc.rs:76-470`):** `call`, `recv`, `reply_recv`, `send`, `signal`, `wait`, `poll`, and `notify_bind` match the contract's state transitions, FIFO queueing, `caps_dropped` propagation (including hiding reply drops from `reply_recv`), and notification delivery priority (`notify_bind` immediate wake, `recv` / `reply_recv` clearing word before caller dequeue).
- **Invariants in `check.rs` (`check.rs:1-402`):** All 29 numbered invariants accurately enforce what their doc comments claim, including Kahn's cycle check in `check_removal` (Invariant 21 correctly handles `cap.parent == holder` duplicate edges), `sweep.held` monotonicity (Invariant 23), and live-count / watermark consistency (Invariants 18–19).
