# Review of the DodOS one-core executable model

Reviewed against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` and `/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs` on branch `model` (`dodos-kernel` working tree clean; `cargo test -p dodos-model` passes: 159 unit/call tests and 4 property tests).

Findings are sorted by severity (`contract error`, `wrong behaviour`, `undefined`, `untested`, `minor`).

---

## 1. Unbounded removal walk and object marking through nested capability spaces

- **Severity**: contract error
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:14` ("**Every call is bounded.** A long operation (revocation, deletion of a large object) runs in bounded steps and returns `again`; the caller repeats the call."), `:85` ("**The tree is at most 64 deep** (provisional): a start-up capability is at depth 1, and a derivation or a creation that would go deeper is `invalid` (checked with the plain arguments). The limit bounds the walk that finds the next capability to remove."), `:93` ("These wakes are not counted in the 32 of a step: a step marks at most one object per level of the tree, so at most 64."), `:95` ("Destroying a `cspace` first removes every capability in it, in index order, by the same steps.")
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:414-446` (`next_removed` and `swept`)
- **What is wrong**:
  - `TREE_DEPTH = 64` only bounds the derivation tree (`parent` edges), not `cspace` containment (`place.0` / `swept` edges).
  - Any number of `cspace` objects `S_0, S_1, ..., S_{n-1}` created from the boot `untyped` are all at derivation depth 2, and each `S_i` is younger than `S_{i-1}` (`S_i.root > S_{i-1}.root`). Under the creation-number rule, `cap_move` permits placing `S_i`'s root inside `S_{i-1}` for arbitrary `n` (e.g., `n = 200` or `n = 1000`).
  - Calling `cap_delete` on `S_0` causes `next_removed` to walk `S_0 -> S_1 -> ... -> S_{n-1}` in a **single step**, marking all `n` `cspace` objects as `dying` before removing `S_{n-1}`, and repeating an `O(n)` walk on every subsequent step of `remove`. This violates rule 4 ("Every call is bounded") and contradicts the claim that "a step marks at most one object per level of the tree, so at most 64".
  - Additionally, `swept` scans slots from index 0 on every step; for a `cspace` with up to `u32::MAX` slots, a real kernel needs a sweep cursor/bitmap to keep single-`cspace` scanning bounded, and even with a cursor, the cross-`cspace` walk in `next_removed` remains unbounded in `n`.
- **How you know**: Read in the contract and code, and **confirmed by a test run** (a scratch test built a chain of 200 nested `CSpace`s at derivation depth 2 and called `cap_delete` on `S_0`; the first call walked all 200 `CSpace`s and returned `Err(Error::Again)`, completing in 7 calls total).
- **What you suggest**: Account for `cspace` nesting in the step bound (or keep an explicit iterative removal cursor/stack across `again` calls so a single step descends at most one `cspace` edge or a bounded number of edges, deferring the `dying` mark of nested spaces until a step reaches them), and update `kernel-interface.md` so it does not claim `TREE_DEPTH = 64` bounds the walk.

---

## 2. `cap_derive` checks the plain argument `rights` before the `destination` capability argument

- **Severity**: wrong behaviour
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:100-105` ("Every call checks in this order and returns the first failure: 1. the capability the call acts on: its slot (`invalid` if empty or out of range, `gone` if dead), its kind (`invalid`), its rights (`denied`); 2. the other capability arguments, in the order of the table below, with the same three checks; 3. the plain arguments (`invalid`); 4. the state..."), `:111` ("`cap_derive` | source, destination, rights, badge | | `derive` on the source. The new rights must be a subset of the source's (`denied` otherwise)... A capability that already has a badge keeps it: asking for another one is `denied` (checked with the plain arguments)")
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:77-78`
- **What is wrong**:
  - Line 77 calls `source.rights.derive(rights)?` before line 78 calls `self.destination(thread, destination)?`.
  - `Rights::derive` checks both whether `source` holds `Rights::DERIVE` (step 1) and whether the plain argument `rights` is a subset of `source.rights` (step 3). When `source` has `Rights::DERIVE`, `rights` asks for an unheld right, and `destination` fails step 2 (e.g., `SlotAddr::own(0)` -> `Invalid`, or `via(dead_cspace, 1)` -> `Gone`), the model returns `Err(Error::Denied)` instead of `Err(Error::Invalid)` / `Err(Error::Gone)`.
  - Note also a `dodos-rust` style link: reusing `Rights::derive` here hid the distinction between checking the capability's `DERIVE` right (step 1) and validating the plain argument `rights` (step 3).
- **How you know**: Read in the code and **confirmed by a test run** (`cap_derive` with a `SEND | DERIVE` source, `destination = SlotAddr::own(0)`, `rights = Rights::ALL`, `badge = 0` returned `Err(Error::Denied)` instead of `Err(Error::Invalid)`).
- **What you suggest**: Check `source.rights.contains(Rights::DERIVE)` in step 1 (`Denied`), resolve `destination` in step 2, and check `source.rights.contains(rights)` (`Denied`) in step 3 alongside the `badge` checks; also clarify in `kernel-interface.md:111` that the `rights` subset check happens with the plain arguments, just as it already states for the `badge` check.

---

## 3. `call`, `reply_recv`, and `send` iterate `message.caps` beyond `MAX_CAPS` (4) before checking the message limits

- **Severity**: wrong behaviour
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:223` ("Capabilities | Up to 4 per message") and `/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:314` (`Header::from_raw`: `if h.words() > MAX_WORDS || h.caps() > MAX_CAPS { return Err(Error::Invalid); }`)
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:75-77` (`call`), `:130-133` (`reply_recv`), `:155-156` (`send`), `:261-286` (`listed`)
- **What is wrong**:
  - `self.listed(thread, &message.caps)?` loops over every entry of `message.caps` before `message.check()?` checks `caps.len() <= MAX_CAPS`.
  - If a caller passes 5+ entries in `message.caps` and entry 5 is empty/dead/unwritable, the model returns the slot error (`Invalid`/`Gone`/`Denied`) for entry 5 instead of `Invalid` for exceeding `MAX_CAPS` (and takes work proportional to `message.caps.len()`). In the real kernel, `Header::from_raw` rejects `caps > 4` and the message page has no 5th capability slot to read.
- **How you know**: Read in `ipc.rs` and `abi/src/lib.rs`.
- **What you suggest**: Check `message.check()?` (or at least `message.caps.len() <= MAX_CAPS`) before iterating `message.caps` in `listed`, or state in the contract whether header limits are validated before capability arguments.

---

## 4. Re-configuring a waiting thread with `thread_configure` and asymmetric `cspace` resolution in `Parcel` vs `Window`

- **Severity**: undefined
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:131` (`thread_configure`: "The thread must be suspended (`busy` otherwise)"), `:135` ("Suspension and waiting are independent"), `:161` ("Checked again at delivery, against what the listed slots hold at that moment")
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:266-280, 606-610, 636-642`, `/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:378-379`
- **What is wrong**:
  - The contract does not say whether `thread_configure` is allowed when the target thread is suspended *and* waiting, or which `cspace` applies if its `cspace` is changed while waiting.
  - The model allows `thread_configure` on a suspended+waiting thread and resolves `Window.cspace` at **call time** (`lib.rs:607`), while `Parcel` stores only `sender: ObjId` and looks up `sender.cspace` at **delivery time** (`ipc.rs:379`). If a waiting caller is suspended and re-configured from `cspace` `S1` to `S2`, its outgoing `call` capabilities are read from `S2` while its incoming reply capabilities are written to `S1`.
- **How you know**: Read in the contract and code.
- **What you suggest**: Specify in the contract whether `thread_configure` returns `busy` if the thread is waiting (or whether `Parcel` binds the caller's `cspace` at call time like `Window`), and mark any remaining model choice.

---

## 5. `thread_resume` succeeds when the thread's bound `cspace` has been destroyed

- **Severity**: undefined
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:132` ("`thread_resume` is `busy` if the thread is bound to no capability space"), `:95` ("once the space is destroyed, from every call")
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:231-233, 647-653`
- **What is wrong**:
  - When a suspended thread's bound `cspace` is destroyed, `target.cspace` remains `Some(destroyed_id)`. `thread_resume` checks only `target.cspace.ok_or(Error::Busy)?` and succeeds (`Done`), making the thread runnable (its next call then fails with `Gone`). The contract does not specify whether a destroyed `cspace` leaves the thread "bound to no capability space" (`Busy`) or still bound (`Done`).
- **How you know**: Read in the code and contract.
- **What you suggest**: Clarify in `kernel-interface.md:132` (or mark `CONTRACT-GAP` in `lib.rs:650`).

---

## 6. `cap_delete` from a dying `cspace` via `via`, and `cap_delete` on a capability of a dying object

- **Severity**: undefined
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:93` ("An object is dying from the first step of a removal that reaches its root capability, even when that step only removes a copy: every call on it, through any capability, returns `gone`... A thread whose capability space is dying gets `gone` from every call except `cap_delete`")
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:110-130`
- **What is wrong**:
  - `cap_delete` uses `self.through(self.own(thread)?, slot, Access::Write)?`, so a thread in a dying `cspace` can still call `cap_delete(via(other_cspace, idx))` to delete capabilities in another live `cspace`. The contract does not state whether `cap_delete` in a dying `cspace` is restricted to `via == 0`.
  - `cap_delete` also succeeds on a non-dying derived capability whose object is already dying (`calls.rs:746-748` tests this), which is reasonable for slot cleanup but not explicitly excepted by the sentence "every call on it, through any capability, returns `gone`".
- **How you know**: Read in the code, tests, and contract.
- **What you suggest**: Clarify both points in `kernel-interface.md`.

---

## 7. Other unmarked model decisions (`Frame` size overflow, `CSpace` max `1 << 32`, `cap_delete`/`cap_revoke` rights, receive range vs "destination")

- **Severity**: undefined
- **Where**:
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:75, 77, 113-116, 161, 164`
  - Model: `/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:32, 37, 110-135`, `/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:478, 598-611`
- **What is wrong**:
  - `caps.rs:32`: `Frame` size calculation uses `size.saturating_mul(page.bytes())`, turning 64-bit overflow into `NoMemory` (tested in `calls.rs:1137`) instead of `Invalid`.
  - `caps.rs:37`: `CSpace` `size` requires `size <= u32::MAX.into()`, rejecting `1 << 32` (`4_294_967_296`, a multiple of 128 whose slot indexes `0..=u32::MAX` fit in 32 bits, tested in `calls.rs:1143`).
  - `caps.rs:110-135`: `cap_delete` and `cap_revoke` require no right on the capability itself; contract lines 113–114 omit "No right on the capability itself" (unlike `cap_move` and `cap_inspect`), though line 74 treats them as slot operations.
  - `lib.rs:598-611`: For a non-empty receive range whose `first` is slot 0 or beyond the table, `window` does not return `Invalid` (contrast line 77: "A destination that is slot 0 or beyond the table is `invalid`"); instead, delivery drops capabilities (`caps_dropped`, tested in `calls.rs:1828`).
  - (Also note: the existing `CONTRACT-GAP` comment at `lib.rs:478` is actually covered by `kernel-interface.md:95`: "once the space is destroyed, from every call.")
- **How you know**: Read in the code, tests, and contract.
- **What you suggest**: Document these choices in `kernel-interface.md` (and update the `CONTRACT-GAP` comment at `lib.rs:478`).

---

## 8. Weak or missing invariants in `check.rs` (and `check/tests.rs` gaps)

- **Severity**: minor
- **Where**: `/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:66-68, 97-100, 156-163, 188-193, 205-288`, `/Users/btw/Documents/repos/dodos-kernel/model/src/check/tests.rs:434, 483`
- **What is wrong**:
  - **Invariant 23 (`check.rs:156-163`)** claims "a dying capability space only shrinks", but only checks `CapId < dying`; an older capability (`CapId < dying`) wrongly moved into a dying `cspace` would not be caught.
  - **Invariant 11 (`check.rs:188-193`)** checks `from == Some(ut)` implies `root.parent` belongs to `ut`, but does not check the converse (`from.is_none()` implies `root.parent.is_none()`).
  - **Invariant 3 (`check.rs:24-26, 97-100`)** comments that a root capability has every right (except `exec`), but does not check root rights or `badge == 0` on roots / non-endpoint / non-notify capabilities.
  - **Device / `Exec` invariants missing**: `check.rs` does not verify that a child `untyped` of a `device` untyped has `device == true`, that objects from a `device` untyped are only `Frame` or `Untyped`, or that no capability from/for a `device` untyped carries `Rights::EXEC`.
  - **Waiting payload & `ReplyState::Armed` invariants missing**: `check_waits` does not validate `Wait::Call` (`parcel.sender == thread`, `words.len() <= MAX_WORDS`, `caps.len() <= MAX_CAPS`, `window.count <= MAX_CAPS`), `Wait::Recv` (`window.count <= MAX_CAPS`), `ReplyState::Armed` (`window.count <= MAX_CAPS`, `flags & !FLAG_CAPS_DROPPED == 0`), or `thread.cspace` referencing a live non-`CSpace` object.
  - **Monotonic ID invariant missing**: `check.rs` does not check `ObjId < next_id`, `CapId < next_id`, or `dying <= next_id`.
  - **`check/tests.rs`**: Invariant 22 is only tested for `ReplyState::Attached`, not `ReplyState::Armed`; Invariant 18 (`watermark == 0` iff `live == 0`) is only tested for `watermark == 0 && live > 0`, not `watermark > 0 && live == 0`.
- **How you know**: Read in `check.rs` and `check/tests.rs`.
- **What you suggest**: Add these checks to `check.rs` and add the corresponding `spoiled` tests to `check/tests.rs`.

---

## 9. Contract rules missing unit tests in `tests/calls.rs`

- **Severity**: untested
- **Where**: `/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs`
- **What is wrong**:
  1. **`reply_recv` capability transfer**: The helper `reply_recv` (`calls.rs:103-110`) hardcodes `Range::NONE`, and no test in `calls.rs` transfers capabilities on either the reply half or the receive half of `reply_recv` (nor verifies that `reply_recv` silently drops reply capabilities without informing the server).
  2. **Non-root capability on removal path / derivation during `cap_revoke`**: No test checks that an intermediate capability on the path of `cap_revoke` (`EP -> C1 -> 40 copies`) keeps working after step 1 returns `Again`, or that unremoved descendants can still derive new capabilities between `Again` steps.
  3. **`cap_delete` and `cap_revoke` with `Rights::NONE`, and `cap_revoke` with 0 descendants**: Not tested in `calls.rs`.
  4. **`Order of checks` precedence in `cap_derive` and IPC calls**:
     - `cap_derive` `rights` subset vs `destination` (this gap hid Finding 2).
     - `call` / `reply_recv` / `recv` argument-order precedence across steps 1–4 (`endpoint` before `message.caps`, `message.caps` before `range.via`, `range.via` before `range.count > 4`, duplicate slot / depth > 64 before later bad slots in `message.caps`).
  5. **Combined `FLAG_CAPS_DROPPED` on request + successful capability transfer on reply**: Not tested that the caller receives `caps == 1` and `flags == FLAG_CAPS_DROPPED`.
  6. **`send` on an idle `Reply` with capabilities**: Not tested that it returns `WouldWait` and leaves the listed capabilities untouched.
  7. **`Frame` `Size2M` / `Size1G` alignment**, **`thread_configure` re-binding a suspended thread to another `CSpace`**, and **`notify_bind` with a pending word when callers (not receivers) are queued**.
- **How you know**: Read in `tests/calls.rs`.
- **What you suggest**: Add unit tests in `tests/calls.rs` covering each of these behaviours.

---

## Checked and found correct

- `abi/src/lib.rs`: `SlotAddr`, `Rights::derive`, `Marks`, `Header::new` / `Header::from_raw`, `Error` codes, and layout assertions match the contract.
- `model/src/lib.rs`: `Model::boot`, `runnable`, `woken`, `own`/`space`/`through`/`full`/`dying`, and `thread_suspend` match the contract (modulo Findings 4 and 5).
- `model/src/caps.rs`: `cap_move`, `cap_inspect`, `cspace_grow`, `untyped_retype` rights/`exec`/device rules and watermark release, `shallow` depth-64 check, `movable` creation-number check, most-recent-child-first removal, `Slot::Dead` vs `Slot::Empty`, and `Reply` wake on marking `dying` match the contract (modulo Findings 1, 2, 6, 7).
- `model/src/ipc.rs`: `call`/`recv`/`reply_recv`/`send` fast/slow queue semantics, `badge` stamping, `signal`/`wait`/`poll`/`notify_bind` bit-OR and wake priority (`notify` waiters before bound `endpoint` receivers), `deliver` all-or-nothing capability transfer and `FLAG_CAPS_DROPPED` propagation, and `unlink` on thread destruction match the contract (modulo Findings 3 and 4).
- `model/src/check.rs`: Core structural checks (invariants 1–20, 21 acyclicity, 22 reply dying) accurately check their stated properties (modulo Finding 8).
- `model/tests/property.rs`: Deterministic PRNG, per-step `Model::check()`, and coverage assertions for all modelled calls, error codes, and creation-number refusals are sound.
