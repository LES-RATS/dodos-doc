# Model review 4 (Gemini Hydrogen): one-core reference model vs contract

Reviewed `/Users/btw/Documents/repos/dodos-kernel` on branch `model` (`abi/src/lib.rs`, `model/src/lib.rs`, `model/src/caps.rs`, `model/src/ipc.rs`, `model/src/check.rs`, `model/src/check/tests.rs`, `model/tests/calls.rs`, `model/tests/property.rs`) against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`.

All existing `dodos-model` tests pass (`95` unit tests in `model/src/check/tests.rs`, `244` integration tests in `model/tests/calls.rs`, `8` property tests in `model/tests/property.rs`). Twenty-one additional interleaving and state-transition probes were written and executed in a scratch crate outside the repository; all `21` passed and satisfied `Model::check()` after every step.

No `wrong behaviour` or `contract error` was found in the one-core state machine logic. Below are the remaining ambiguities, untested combinations, and minor discrepancies, sorted by severity.

---

## Findings

### 1. `undefined` — `thread_resume` on an already-runnable thread whose capability space was destroyed

- **Where**:
  - Contract: `Docs/architecture/kernel-interface.md`, "Threads" table (`thread_resume`, `thread_suspend`, line 132).
  - Model: `dodos-kernel/model/src/lib.rs`, `Model::thread_resume` (lines 715–720); `dodos-kernel/model/tests/calls.rs` (lines 2431–2440).
- **What is wrong**:
  - Contract: *"Both succeed when the thread is already in the state asked for. `thread_resume` is `busy` if the thread is bound to no capability space, or to one that is destroyed; a thread bound to a dying space can be resumed"*.
  - Model:
    ```rust
    fn thread_resume(&mut self, thread: ObjId, target: SlotAddr) -> Outcome {
        let target = self.object(thread, target, ObjectKind::Thread, Rights::MANAGE)?;
        self.own(target).or(Err(Error::Busy))?;
        live(&mut self.threads, target).suspended = false;
        Ok(Output::Done)
    }
    ```
  - If a thread `T` is resumed while bound to `cspace` `C`, and `C` is later destroyed while `T` is still runnable (`suspended == false`), a subsequent `thread_resume(T)` hits both rules: `T` is already in the state asked for (`!suspended`), yet `T` is bound to a destroyed `cspace`. Two kernel authors can observably disagree: one checks `self.own(target)` first and returns `Busy` (as the model does); the other checks `if !target.suspended { return Ok(Output::Done); }` first.
- **How you know**:
  - Read in contract and code; confirmed in scratch crate (`thread_resume_on_already_runnable_thread_with_destroyed_cspace_is_busy`: `UntypedRetype(CSpace, 30)` → `UntypedRetype(Thread, 40)` → `ThreadConfigure(40, 30, 0, 0)` → `ThreadResume(40)` → `CapDelete(30)` → `ThreadResume(40)` returns `Err(Error::Busy)`). Also untested in `calls.rs`, where `thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed` (line 2431) only tests a suspended thread.
- **What you suggest**:
  - State explicitly in `kernel-interface.md` whether `thread_resume` checks the capability space before "already resumed" (`busy` wins, matching the model) or vice versa, and add the already-runnable case to `calls.rs`.

---

### 2. `undefined` — Precedence between unknown `Rights` bits, subset/missing-right `denied`, and unused/invalid raw enums

- **Where**:
  - Contract: `Docs/architecture/kernel-interface.md`, "Order of checks" (lines 100–105), `cap_derive` / `untyped_retype` (lines 111, 116), "Transfer of capabilities" (lines 160–163), "Registers" (line 181).
  - ABI & Model: `dodos-kernel/abi/src/lib.rs` (`Rights` lines 111–162, `ObjectKind` lines 199–216, `PageSize` lines 220–234); `dodos-kernel/model/src/lib.rs` (lines 50, 92, 102–110); `dodos-kernel/model/src/caps.rs` (`cap_derive` lines 80–118, `footprint` lines 41–77, `untyped_retype` lines 173–208); `dodos-kernel/model/src/ipc.rs` (`listed` lines 278–303).
- **What is wrong**:
  - **Unknown rights bits vs `denied`**: Contract line 111 states *"The new rights must be a subset of the source's (`denied` otherwise, checked with the plain arguments, so after the destination); a rights word with a bit that names no right is `invalid`, here and in a message."* If `source` has `DERIVE | READ` (no `WRITE`), `destination` is valid, and `rights` has word `0x102` (both unknown bit `0x100` and unheld `WRITE`), the contract does not say whether the kernel validates the `rights` word first (`invalid`) or checks the subset first (`denied`). Likewise, in a message `Transfer::Derive(slot, raw_rights)`, the contract does not say whether an unknown bit in `raw_rights` returns `invalid` when decoding the transfer entry or only after checking `derive` and the capability's rights (`denied`).
  - **Non-frame `untyped_retype` raw `page` / `kind`**: Contract line 104 specifies `"for untyped_retype the kind is judged before the size argument"`, and line 116 defines the size argument per kind, while `model/src/lib.rs:103` states *"for a frame it is the number of pages of size `page`, which no other kind reads"*. In the binary ABI, if `page` and `size` are distinct or packed and a caller passes an invalid raw `page` encoding with `kind != Frame`, one author may validate `page` as `invalid` while another ignores it as the model implies. Similarly, on a device untyped, whether an unknown raw `kind` discriminant is checked before or with the device rule returns `invalid` either way, though for `ObjectKind::Timer` on device memory, `calls.rs` didn't check `Invalid` vs `Unsupported` (covered in Finding 4).
  - **Model gap**: `Syscall::CapDerive`, `Transfer::Derive`, and `Syscall::UntypedRetype` take typed `Rights`, `ObjectKind`, and `PageSize` instead of raw integers, so invalid bit patterns cannot be passed through `Model::apply`.
- **How you know**:
  - Read in `kernel-interface.md`, `abi/src/lib.rs`, `model/src/lib.rs`, `caps.rs`, and `ipc.rs`.
- **What you suggest**:
  - Fix in `kernel-interface.md` whether unknown `Rights` bits (`invalid`) are checked before or after `denied` in `cap_derive` and in message transfer entries, and whether `page` in `untyped_retype` is ignored for non-`frame` kinds. If `Model` keeps typed enums/bitflags, mark the raw-decoding omission with `CONTRACT-GAP` (or take raw `u32`/`u64` words at the `Syscall` boundary).

---

### 3. `undefined` — `signal` and `notify_bind` interaction with a *dying* `endpoint`

- **Where**:
  - Contract: `Docs/architecture/kernel-interface.md`, "Removal ends" (line 93), "Notifications" (lines 173, 175).
  - Model: `dodos-kernel/model/src/ipc.rs`, `Model::signal` (lines 190–197), `Model::hand_over` (lines 202–219), `Model::notify_bind` (lines 237–272).
- **What is wrong**:
  - Suppose `EP` is bound to live `notify` `NT`, `Server` is waiting in `recv(EP, RP, ...)`, and `cap_delete(EP)` returns `Again` (so `EP` is dying, and every direct call on `EP` returns `Gone`).
  - In the model:
    1. `signal(NT)` succeeds and delivers `FLAG_NOTIFICATION` to `Server` on the dying `EP`, waking `Server` and clearing `NT.word` and `RP = Idle`.
    2. `notify_bind(NT, 0)` succeeds and unbinds `NT` from the dying `EP` (even with a non-zero `NT.word`), allowing `NT` to be re-bound to another live endpoint `EP2` and immediately deliver the word.
  - Contract line 93 states *"every call on it, through any capability, returns gone, so its queues only shrink"*. While `signal(NT)` is a call on `NT` (not `EP`) and shrinks `EP`'s queue, the contract never explicitly addresses bound notifications while an endpoint is dying. A kernel author who checks `!endpoint.dying` inside `hand_over` would refuse delivery from `NT` to `EP`, leaving `Server` blocked until `EP` finishes dying (waking `Server` with `Gone` instead of a notification, and leaving `NT.word != 0`).
- **How you know**:
  - Read in contract and `ipc.rs`; confirmed in scratch runs (`signal_on_bound_notify_wakes_receiver_on_dying_endpoint` and `unbind_notify_from_dying_endpoint_with_pending_word`).
- **What you suggest**:
  - State in `kernel-interface.md` under "Removal ends" or "Notifications" whether a `signal` on a live `notify` bound to a dying `endpoint` still wakes a waiting receiver on that endpoint (matching the model) or not, and add both cases to `calls.rs`.

---

### 4. `untested` — Multi-object interleavings and edge cases absent from `model/tests/`

- **Where**:
  - Tests: `dodos-kernel/model/tests/calls.rs` and `dodos-kernel/model/tests/property.rs`.
- **What is wrong**:
  - The test suite (`244` call tests, `8` property tests) misses several multi-object interleavings and `(state, call)` boundary pairs that are important when testing the real kernel against the model:
    1. **`signal` / `notify_bind(nt, 0)` on a dying endpoint** (see Finding 3).
    2. **`thread_resume` on an already-runnable thread with a destroyed `cspace`** (see Finding 1; `calls.rs:2431` tests only a suspended thread).
    3. **A dying `Thread` continuing execution and arming a `Reply` before destruction**: `Server` waits in `recv(EP, RP, ...)`; `cap_delete(Server)` returns `Again` (33+ copies); `Caller` calls `call(EP)` -> `Server` wakes with the message and `RP` becomes `Armed(Caller)`; `cap_delete(Server)` finishes -> `Caller` remains in `Wait::Reply(RP)` until answered via `send(RP)`.
    4. **`cap_delete` vs `cap_revoke` on a copy of a *dying* object**: When `EP` is dying (`cap_delete(ep_root)` returned `Again`), `cap_revoke(copy)` returns `Gone`, whereas `cap_delete(copy)` succeeds and removes the copy (`kernel-interface.md:93`: *"`cap_delete` on a capability whose object is dying works as on any other"*).
    5. **Device `untyped` with an unsupported `ObjectKind`** (`untyped_retype(DEV, Timer, 5, ...)`): must return `Invalid` (device rule) before `Unsupported` (`calls.rs:1354` tests only `Endpoint`/`CSpace` on `DEV`; `calls.rs:3302` tests `Timer` only on ordinary `untyped`).
    6. **`reply_recv` with `ReplyState::Attached` while bound `notify` has a pending word**: returns `Busy` without consuming `notify.word` (`calls.rs:3241` tests this for `recv`, not `reply_recv`).
    7. **`thread_configure` returning `Busy` in `Wait::Call`, `Wait::Reply`, and `Wait::Recv`** (`calls.rs:2404` tests only `Wait::Notify`; `calls.rs:1591` + `2404` show the woken-while-suspended case only for `Wait::Notify`).
    8. **Overlapping/crossing removals across `CSpace`s**: two `cap_delete` calls whose sweeps cross via shared derivation subtrees, `cap_delete(cspace)` interleaved with `cap_revoke` on a held capability, and a thread inside a dying `cspace` calling `cap_delete` on a slot ahead of the space's `sweep.next` (`Again`) that an outer `cap_delete` on the `cspace` finishes.
- **How you know**:
  - Inspected `model/tests/calls.rs` and `model/tests/property.rs`; confirmed all 8 scenarios in the scratch crate (`signal_on_bound_notify_wakes_receiver_on_dying_endpoint`, `unbind_notify_from_dying_endpoint_with_pending_word`, `thread_resume_on_already_runnable_thread_with_destroyed_cspace_is_busy`, `dying_server_thread_can_still_receive_and_arm_reply_before_destruction`, `cap_delete_on_copy_of_dying_object_succeeds_while_cap_revoke_is_gone`, `device_untyped_unsupported_kind_returns_invalid`, `reply_recv_attached_is_busy_without_consuming_pending_notification`, `thread_configure_busy_in_all_four_wait_states_and_allowed_when_woken_suspended`, `overlapping_cap_delete_and_cap_revoke_on_subtrees_and_cspaces`, `two_crossing_cap_deletes_on_disjoint_cspaces_with_shared_subtree`, `thread_in_dying_space_can_cap_delete_ahead_of_sweep_and_own_root`).
- **What you suggest**:
  - Add regression tests for these 8 scenarios to `model/tests/calls.rs` so both the model and the future kernel conformance suite cover them.

---

### 5. `minor` — Off-by-one (`<= 192` vs `< 192`) in `Model::check` invariant 24 for `longest_walk`

- **Where**:
  - Contract: `Docs/architecture/kernel-interface.md`, "The derivation tree" (line 87).
  - Model: `dodos-kernel/model/src/lib.rs` (lines 350, 356, 455), `dodos-kernel/model/src/check.rs` (lines 87, 236), `dodos-kernel/model/src/check/tests.rs` (line 654).
- **What is wrong**:
  - Contract line 87: *"So no capability can depend on itself, and the walk is shorter than 192 capabilities (the longest one that can be built has 191)."*
  - Model: `check.rs:236` checks `ensure(self.longest_walk <= LONGEST_WALK, "24: walk of a removal")` where `LONGEST_WALK = 192`, and comments at `lib.rs:350, 455` and `check.rs:87` say *"bounds it by 192"* / *"never longer than 192"*. (Notably, `calls.rs:2955` asserts `< LONGEST_WALK`.) While no valid state reachable via `Model::apply` exceeds 191 capabilities, `Model::check` accepts a constructed/mutated state with `longest_walk == 192`.
- **How you know**:
  - Read in contract, `lib.rs`, `check.rs`, `check/tests.rs`, and `calls.rs:2955`; verified the exact 191-capability maximum walk in scratch test `longest_walk_can_reach_exact_191_capabilities`.
- **What you suggest**:
  - Tighten `check.rs:236` to `self.longest_walk < LONGEST_WALK` (or define `LONGEST_WALK = 3 * TREE_DEPTH - 1 = 191` and update the comments and `check/tests.rs:654`).

---

### 6. `minor` — `Header::from_raw` doc comment in `abi` omits sender flag prohibition

- **Where**:
  - Contract: `Docs/architecture/kernel-interface.md`, "Order of checks" (line 103).
  - ABI & Model: `dodos-kernel/abi/src/lib.rs` (`Header::from_raw`, lines 311–318); `dodos-kernel/model/src/ipc.rs` (`Message::check`, lines 22–28).
- **What is wrong**:
  - `Header::from_raw` is documented as *"Checks a raw word received from an untrusted caller"*, yet it only checks `words() <= MAX_WORDS && caps() <= MAX_CAPS` and accepts arbitrary 22-bit `flags`. In the model, `Message::check` separately rejects `header.flags() != 0`, but a kernel author using `Header::from_raw` for untrusted caller headers based on its doc comment could miss the `flags() != 0` check (whereas receiver-side headers legitimately carry `FLAG_CAPS_DROPPED` / `FLAG_NOTIFICATION`).
- **How you know**:
  - Read in `abi/src/lib.rs` and `model/src/ipc.rs`.
- **What you suggest**:
  - Clarify `Header::from_raw`'s doc comment (noting it checks layout bounds only and that caller-supplied headers must also have `flags() == 0`), or provide a dedicated constructor/helper for caller message headers.

---

### 7. `minor` — Unmarked `CONTRACT-GAP` choices in `Model`

- **Where**:
  - Model: `dodos-kernel/model/src/lib.rs` (lines 14, 50, 92, 102–108, 527–530).
- **What is wrong**:
  - `lib.rs:14` states *"`CONTRACT-GAP` marks a behaviour that the contract does not fix."* Two model choices lack a `CONTRACT-GAP` comment:
    1. Representing `rights`, `kind`, and `page` in `Syscall` / `Transfer` as already-valid `Rights`, `ObjectKind`, and `PageSize` types (and ignoring `page` for non-`Frame` kinds in `UntypedRetype`).
    2. In `Syscall::Other(call)` (including `ThreadReadRegs` / `ThreadWriteRegs`), checking `self.space(thread, SlotAddr::NONE, Access::Read)?` (`Gone` if the caller's own `cspace` is destroyed or dying) before returning `Error::Unsupported`, without specifying whether a real kernel checks `Unsupported` before or after `space` (or before checking `ThreadReadRegs` / `ThreadWriteRegs` arguments).
- **How you know**:
  - Read in `model/src/lib.rs` and verified all `CONTRACT-GAP` markers in `model/src/`.
- **What you suggest**:
  - Add brief `CONTRACT-GAP` notes in `model/src/lib.rs` (or fix the precedence in `kernel-interface.md`).

---

## What I checked and found correct

- **Slot addresses and slot lifecycle (`Empty` / `Full` / `Dead`)**: `via` one-level indirection, slot 0 reserved (`Invalid`), dead slot retention (`Gone` on use, `NoSlot` as destination, cleared to `Empty` only by `cap_delete` with `Write`), and `Read` vs `Write` on `via` across all 19 calls match the contract (`lib.rs`, `caps.rs`, `ipc.rs`).
- **CSpace creation, growth, and destruction**: 0 initial slots, directory size `((max/128)*8).next_power_of_two()`, alignment, start-up space non-growability, `cspace_grow` accepting any `WRITE` cap for the same `untyped` (`Invalid` if wrong untyped before `NoSlot` at maximum before `NoMemory`), and `live` count release for base object + every segment match the contract (`caps.rs`).
- **Derivation tree, cycle prevention, and depth rules**: depth limit 64 (`checked with the plain arguments`), `CSpace` root > parent space depth, `Untyped` >= parent space depth, self-holding `CSpace` allowed and deleted last, `cap_derive` keeping existing badge and rejecting non-endpoint/non-notify badges, and IPC capability transfer re-checking `fits` at delivery and dropping all capabilities (`FLAG_CAPS_DROPPED`) on failure all match the contract (`caps.rs`, `ipc.rs`).
- **Bounded removal (`32` steps, `128` slots, `< 192` walk)**: LIFO child order, post-order removal after descendants and waiters, FIFO waiter waking (`32` total removals + wakes per call, returning `Done` on the last removal rather than `Again`), `sweep.next` monotonically advancing, full slots not consuming slot budget while removed, dying capabilities returning `Gone` for all calls except `cap_delete`, dying objects returning `Gone` on all calls while `cap_delete` on a copy still operates on the slot, dying `cspace` restricting the owner thread to `cap_delete` on `via == 0` slots only, and dying `Reply` objects immediately waking their `Attached`/`Armed` waiter (uncounted in the 32-step budget) all match the contract (`caps.rs`, confirmed across all 21 scratch tests).
- **Untyped memory and watermark**: device untyped restricted to `Frame` and child `Untyped` without `EXEC`, `EXEC` propagation from untyped capability, object sizes and alignments (including `1 KB` thread, `64 B` endpoint/reply/notify, `128 B` sched, `4 KB` aspace, `<= 4 KB` alignment cap for objects other than `Untyped`/`Frame`), overflow-safe watermark rounding (`checked_next_multiple_of` / `checked_add`), and watermark reset to `0` only when `live` hits `0` (including ungrown `CSpace`s) match the contract (`caps.rs`).
- **Thread state machine**: independent `suspended` flag and `Wait::{None, Call, Reply, Recv, Notify}`, `outcome` retention until next call, `thread_configure` requiring `suspended && Wait::None` (`Busy` otherwise, keeping `outcome` if woken while suspended), `thread_suspend`/`thread_resume` preserving queues and deliveries, and `Wait`/`Thread` destruction cleanup (`unlink`) match the contract (`lib.rs`, `ipc.rs`).
- **IPC and Reply state machine (`Idle` / `Attached` / `Armed`)**: `call` fast-deliver vs FIFO queueing, `recv` checking `Idle` reply before pending notification before waiting caller before queueing, `reply_recv` answering or silently dropping if `Idle` (`Busy` only if `Attached`) then receiving, `send` never queueing (`WouldWait` on endpoint with no receiver or on `Idle`/`Attached` reply), badge 0 on reply, `FLAG_CAPS_DROPPED` propagation from request to reply header, `ReplyRecv` moving its own `reply`/`endpoint`/`cspace` cap cleanly before receiving, `Call`/`Recv` receive-window aliasing/overlap handling, and `Caller` disappearing leaving `Reply` `Idle` while `Server` disappearing leaves `Caller` waiting on `Reply` all match the contract (`ipc.rs`).
- **Notifications**: `signal` setting badge bits (or bit 0 when badge is 0), preference for direct `Notify` waiters over bound-endpoint `Recv` waiters, clearing the word and making the woken receiver's `Reply` `Idle`, `wait`/`poll` clearing non-zero word and returning `Waits`/`WouldWait` when zero, and `notify_bind` 1:1 enforcement (`Busy` if either side bound, including to each other), unbind via `SlotAddr::NONE`, and immediate pending-word delivery on bind all match the contract (`ipc.rs`).
- **Order of checks**: step 1 (`target` slot -> kind -> rights including `GRANT` with header cap count) -> message header limits/flags (`Invalid`) -> remaining capability arguments in table order -> plain arguments (`device` -> `kind` -> `size`, depth checks last) -> state (`Busy`, `NoSlot`, `NoMemory`, `WouldWait`) holds across all 19 calls (`caps.rs`, `ipc.rs`, `lib.rs`).
- **State invariants (`Model::check`)**: all 30 numbered invariants in `check.rs` are consistent with the contract (aside from `<= 192` in invariant 24, Finding 5) and hold after every step in both the property tests and all 21 scratch interleaving tests.
