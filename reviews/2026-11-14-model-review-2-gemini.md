# Review of `dodos-model` (One Core)

Reviewed on branch `model` against [kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md), [abi/src/lib.rs](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs), [AGENTS.md](/Users/btw/Documents/repos/dodos-kernel/AGENTS.md), and [SKILL.md](/Users/btw/Documents/repos/dodos-kernel/.agents/skills/dodos-rust/SKILL.md).

Baseline test run (`cargo test -p dodos-model`): 183 unit/call tests, 4 property tests, and all `check` tests passed. Scratch tests probing edge cases were run in an external crate outside the repositories; both repositories' working trees remain unmodified aside from this report.

---

## Findings

### 1. `call` and `reply_recv` violate "Order of checks" by checking plain `message` limits before later capability arguments
- **Severity**: wrong behaviour
- **Confidence**: confirmed by a test run
- **Where**:
  - [model/src/ipc.rs:75-80](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:75-80) (`Model::call`)
  - [model/src/ipc.rs:128-134](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:128-134) (`Model::reply_recv`)
  - [kernel-interface.md:100-105](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:100-105)
- **What is wrong**:
  The contract ("Order of checks", lines 100–105) requires:
  > "Every call checks in this order and returns the first failure:
  > 1. the capability the call acts on: its slot (`invalid` if empty or out of range, `gone` if dead), its kind (`invalid`), its rights (`denied`);
  > 2. the other capability arguments, in the order of the table below, with the same three checks;
  > 3. the plain arguments (`invalid`);
  > 4. the state: `busy`, `no_slot` (the destination slot is not empty), `no_memory`, `would_wait`."

  In `Model::reply_recv`, `message.check()?` (which checks the plain header limits `words.len() <= 64` and `caps.len() <= 4`) and `self.listed(thread, &message.caps)?` (including `Transfer::Derive` rights and `TREE_DEPTH` checks) run **before** `self.object(thread, endpoint, ObjectKind::Endpoint, Rights::RECV)?` and `self.window(thread, range)?`.
  Similarly, in `Model::call`, `message.check()?` and `self.listed(...)` run **before** `self.window(thread, range)?` (which checks the `via` capability of `range.first`).
  While line 163 states that header limits are checked before the *listed slots* of the message, it does not place `words.len()` (or `Transfer::Derive` plain-argument checks) ahead of `endpoint` in `reply_recv` or `range.first.via()` in `call` and `reply_recv`.
- **How you know**:
  Confirmed by scratch tests:
  1. `Model::boot()`, `UntypedRetype(UT, Reply, 0, s(20))`, `UntypedRetype(UT, Endpoint, 0, s(21))`, `CapDerive(s(21), s(23), ALL, 0)`, `CapRevoke(s(21))` (making `s(23)` dead), `CapDerive(s(21), s(24), SEND, 0)`. Calling `ReplyRecv { reply: s(20), message: Message { words: vec![0; 65], .. }, endpoint: s(23), range: Range::NONE }` returns `Err(Error::Invalid)` instead of `Err(Error::Gone)` (and with `endpoint: s(24)`, returns `Err(Error::Invalid)` instead of `Err(Error::Denied)`).
  2. `Model::boot()`, `UntypedRetype(UT, Endpoint, 0, s(20))`, `CapDerive(s(START_SLOT_CSPACE), s(21), READ, 0)`. Calling `Call { endpoint: s(20), message: Message { words: vec![0; 65], .. }, range: Range { first: via(21, 30), count: 1 } }` returns `Err(Error::Invalid)` instead of `Err(Error::Denied)`.
- **What you suggest**:
  Check `endpoint` (in `reply_recv`) and the `via` capability of `range` (in `call` and `reply_recv`, when `range.count > 0`) in step 2 before checking `words.len() > MAX_WORDS` and other step-3 plain checks (or explicitly document table-order per-argument checking in "Order of checks" if table order was intended).

---

### 2. Unbounded work when deleting a large `cspace` with empty slots (contract gap and model scan)
- **Severity**: contract error (and model performance gap)
- **Confidence**: confirmed by a test run (and read in the code)
- **Where**:
  - [kernel-interface.md:14](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:14) (Rule 4), [92](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:92), [95](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:95), [116](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:116)
  - [model/src/caps.rs:465-471](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:465-471) (`Model::swept`)
- **What is wrong**:
  Rule 4 states:
  > "**Every call is bounded.** A long operation (revocation, deletion of a large object) runs in bounded steps and returns `again`; the caller repeats the call."
  Line 95 states:
  > "Destroying a `cspace` first removes every capability in it, in index order, by the same steps; the dying space keeps the index where the sweep stands, so that a step does not scan it again from the start."

  Even with a sweep cursor in the kernel, scanning **empty or dead slots** is not counted in the 32-step budget (`REMOVAL_STEP`). A `cspace` can have up to $2^{32}$ slots (line 116) and be grown to millions of slots via `cspace_grow`. If slots `1 .. N-1` are empty and slot `N` is full (or all `N` slots are empty), a single `cap_delete` call must scan all $O(N)$ empty slots before finding one capability or finishing.

  Separately, in the model, `CSpace` does not store a sweep cursor at all, so `Model::swept` scans from slot 0 on every single step of `Model::remove` (up to $32 \times N$ slot checks per `cap_delete` call).

  Additionally, under `untyped_retype` (lines 116, 123), creating a `cspace` with `max = 2^32` allocates and zeroes a 256 MiB directory (`8 * 2^32 / 128 = 2^28` bytes) in a single non-preemptible call without `again`.
- **How you know**:
  Confirmed by scratch test `large_empty_cspace_scans_all_empty_slots_in_one_cap_delete`: `Model::boot()`, `UntypedRetype(UT, CSpace, 1_280_000, s(20))`, 10,000 `CSpaceGrow` calls, 33 `UntypedRetype` calls into slots `1_279_967..1_280_000`, followed by `CapDelete(s(20))` scans all 1,279,967 empty slots 32 times in one call. Read in [kernel-interface.md:95,116,123](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:95).
- **What you suggest**:
  Count scanned empty/dead slots (or segments) toward the bounded step budget of `cap_delete` (allowing `again` while advancing the cursor across empty regions), keep the sweep cursor in `CSpace` in the model if step-level equivalence is desired, and consider bounding `cspace` directory zeroing or `cspace` max size.

---

### 3. Contradiction in the contract on untyped memory reclamation, and unmarked `CONTRACT-GAP` on watermark reset
- **Severity**: contract error / undefined
- **Confidence**: read in the code
- **Where**:
  - [kernel-interface.md:83](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:83), [121](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:121)
  - [model/src/caps.rs:268-276](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:268-276) (`Model::release`)
- **What is wrong**:
  Line 83 says:
  > "When the root capability is removed the object is destroyed and its memory goes back to the untyped it came from."
  Line 121 says:
  > "Memory is taken at a watermark that only moves up."

  The contract never specifies when destroyed objects' memory can be allocated again (watermark reset only on `cap_revoke` of the untyped, watermark reset when the last live object/segment from that untyped is destroyed, or a free list). In [model/src/caps.rs:268-276](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:268-276), `Model::release` resets `watermark = 0` whenever `live == 0` (even via individual `cap_delete` calls), and its doc-comment attributes this rule to `Rules of untyped_retype` even though that rule is absent from the contract.
- **How you know**:
  Read in [kernel-interface.md:83,121](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:83) and [model/src/caps.rs:268-276](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:268-276).
- **What you suggest**:
  State explicitly in `kernel-interface.md` under "Rules of `untyped_retype`" that the watermark resets to zero when the last object or `cspace` segment taken from the `untyped` is destroyed (matching `Model::release`).

---

### 4. Contradiction between "Order of checks" and "Transfer of capabilities", plus inaccurate prose in D-103 explanation
- **Severity**: contract error
- **Confidence**: read in the code (and confirmed by scratch test for the 191 bound)
- **Where**:
  - [kernel-interface.md:87](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:87), [100-105](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:100-105), [163](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:163), [285](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:285)
- **What is wrong**:
  1. **Order of checks vs message header/slots**: Lines 100–105 state that every call checks all capability arguments (step 2) before all plain arguments (step 3), whereas line 163 states that header limits (plain arguments) are checked before listed slots (capability arguments) and that `depth` and duplicate-slot checks are done with each slot before the next listed slot.
  2. **D-103 walk explanation (line 87)**: Line 87 writes:
     > "from the root of a space to an `untyped` it holds the depth does not shrink, and below an `untyped` there are only derivations."
     The clause "below an `untyped` there are only derivations" is false: `untyped_retype` creates new object roots (including `cspace` roots and child `untyped`s) as children of an `untyped` capability. What actually bounds the walk to $\le 191 < 192$ is that every edge among `cspace` roots and `untyped`s either stays in `CSpace -> Untyped` (same or greater depth, at most once per depth) or increases depth by $\ge 1$, and once a walk enters any other object kind (which can be at depth 1 inside a depth-64 `cspace`), only derivations remain (at most 64 capabilities).
  3. **Object sizes table (line 285)**: Lists `cspace` as `32 bytes per slot, grown by supplying memory`, omitting the directory (`8 bytes per 128 slots, rounded up to a power of two`) specified on line 75.
- **How you know**:
  Read in [kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md); 191-capability walk confirmed by scratch test `worst_case_walk_191_with_64_levels_and_depth1_chain` (64 levels of `CSpace` + `Untyped` spine plus a depth-1..64 `Debug` chain in `CSpace_64`, exercising D-103 and completing `cap_delete` cleanly).
- **What you suggest**:
  Align "Order of checks" with message parsing on line 163, fix the prose on line 87, and include the `cspace` directory size in the "Object sizes" table.

---

### 5. `check.rs` is missing the D-103 invariant and has weaker invariants than claimed
- **Severity**: untested (weakened oracle invariant)
- **Confidence**: read in the code
- **Where**:
  - [model/src/check.rs:24-27](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:24-27), [48-49](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:48-49), [73-75](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:73-75), [113-114](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:113-114), [134-160](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:134-160), [173-180](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:173-180), [195-225](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:195-225)
- **What is wrong**:
  1. **Missing D-103 invariant**: `Model::check` checks `depth <= 64` (Invariant 20), acyclicity of removal (Invariant 21), and `longest_walk <= 192` only on *already-executed* removals (Invariant 24). It never checks D-103 on the live state (every `Untyped` cap in `space` has `depth >= depth(space.root)`; every `CSpace` root `cap != space.root` in `space` has `depth > depth(space.root)`). A bug in `fits` or `deliver` that allows an acyclic 200-space chain at depth 2 passes `Model::check()` unless `cap_delete` is called on the outer space.
  2. **Invariant 3 (`check.rs:113-114`)**: Only checks `cap.rights.contains(Rights::ALL.without(Rights::EXEC))` on root capabilities. It does not check that a root capability has `Rights::EXEC` if and only if its parent `untyped` capability has `Rights::EXEC` and is not device memory (contract line 122).
  3. **Invariant 10 (`check.rs:195-225`)**: The reverse check verifies that every key in `untypeds`, `cspaces`, `endpoints`, `replies`, `threads`, `notifies` exists in `self.objects`, but does not check that `self.objects[id].kind` matches that map.
  4. **Invariant 23 (`check.rs:173-180`)**: Claims "no thread in it or outside it was the cause of a new capability there", but only checks `CapId(cap) < dying`. An older capability (`CapId < dying`) moved into a dying `cspace` via `cap_move` or IPC would pass Invariant 23.
  5. **Other missing state invariants**: No checks on `Window` (`count <= MAX_CAPS`, valid non-zero `first..first+count` when `cspace` is live), `Parcel` (`sender == thread`, `words.len() <= MAX_WORDS`, `caps.len() <= MAX_CAPS`), `CSpace::max` (non-zero multiple of 128, `<= 1 << 32`), or `Thread::cspace` pointing to an `ObjectKind::CSpace` when present.
- **How you know**:
  Read in [model/src/check.rs](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs).
- **What you suggest**:
  Add D-103 verification in `check_tree`, check exact `EXEC` propagation on non-startup root capabilities in Invariant 3, check `objects[id].kind` in the reverse loop of Invariant 10, and validate `Window`, `Parcel`, `CSpace::max`, and `Thread::cspace` kinds.

---

### 6. Other unmarked `CONTRACT-GAP` behaviours in the model
- **Severity**: undefined
- **Confidence**: read in the code
- **Where**:
  - [model/src/lib.rs:52-57](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:52-57) (`Message` has no `flags`) and [model/src/ipc.rs:406](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:406)
  - [model/src/caps.rs:55](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:55) (`Thread` size 1024) and [218](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:218) (`cspace_grow` alignment)
  - [model/src/caps.rs:93-107](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:93-107) and [model/src/ipc.rs:274](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:274) (step-3 order)
  - [model/src/caps.rs:481-488](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:481-488) (`waiter` wake order)
- **What is wrong**:
  Only [model/src/caps.rs:58-60](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:58-60) is marked `CONTRACT-GAP`. Additional model choices not specified in `kernel-interface.md`:
  1. **User-supplied `Header` flags**: [abi/src/lib.rs:302](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:302) allows 22 bits of `flags` in `Header::new`, and line 220 includes `flags` in the header, but the contract does not state whether user-supplied flag bits on `call`/`send`/`reply_recv` are cleared, preserved, or rejected; `model::Message` omits `flags` and passes `0`.
  2. **`cspace_grow` watermark alignment and `Thread` size**: Line 75 specifies 4 KB segments for `cspace_grow` without stating alignment (line 121 covers `untyped_retype` only); the model aligns `cspace_grow` to 4096 bytes. Line 283 defines `Thread` size as `1 KB, plus the vector state area`; the model hardcodes `1024`.
  3. **Order within step 3**: In `cap_derive`, the contract does not fix the relative order among `rights` subset (`Denied`), `badge` kind (`Invalid`), `badge` mismatch (`Denied`), and `TREE_DEPTH` (`Invalid`); nor in `Transfer::Derive` whether `rights` subset (`Denied`) is checked before the next listed slot.
  4. **Wake order during `cap_delete`/`cap_revoke`**: Line 95 does not specify whether queued waiters on a deleted `endpoint`/`notify` are woken in FIFO order across `Again` steps; the model wakes from `front()`.
- **How you know**:
  Read in [model/src/lib.rs](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs), [model/src/caps.rs](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs), [model/src/ipc.rs](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs), and [kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **What you suggest**:
  Mark these as `CONTRACT-GAP` in the model or clarify them in `kernel-interface.md` before writing the kernel oracle harness.

---

### 7. Contract rules without unit tests or weakly guarded tests
- **Severity**: untested
- **Confidence**: confirmed by a test run (for `thread_resume` on dying `cspace`) and read in [model/tests/calls.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs)
- **Where**:
  - [model/tests/calls.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs)
- **What is wrong**:
  Several explicit rules in `kernel-interface.md` have no dedicated unit test in `calls.rs` (or have tests that pass even if a rule is broken):
  1. **`thread_resume` on a thread bound to a dying `cspace`** (line 132): `calls.rs` tests `None` (line 1458) and destroyed (line 2389), not dying. (Confirmed to work via scratch test `thread_resume_succeeds_when_bound_to_dying_cspace`.)
  2. **`reply_recv` with both a pending notification and a queued caller or armed reply** (lines 147, 175): `calls.rs:2141` tests `reply_recv` notification delivery only when `reply` is idle and no caller is queued.
  3. **`deliver` into a dying `cspace` when the message carries 0 capabilities** (line 93): should deliver words without `FLAG_CAPS_DROPPED`.
  4. **`deliver` when the sender's `cspace` becomes dying while the sender waits in `Wait::Call`** (line 161): capabilities should be dropped.
  5. **IPC move of a `CSpace` root capability refused/accepted by D-103, and IPC derive of a `CSpace` capability into a deeper space** (line 86): `calls.rs:1175-1212` unit-tests `Untyped` only (though `property.rs` exercises `CSpace` moves).
  6. **Order-of-checks gaps in `calls.rs`**: No tests for `reply_recv` (`reply` vs `message` vs `endpoint` vs `range` vs `Busy`), `cspace_grow` (`Invalid` wrong untyped before `NoSlot` max reached before `NoMemory`), `thread_configure` (all 4 caps checked before `Busy`), `recv` (`range` checked before `Busy`), `notify_bind` (`endpoint` checked before `Busy`), or `cap_delete(via(dying_cspace, slot))` returning `Gone`.
  7. **`PageSize::Size1G`** (`abi/src/lib.rs:223`): never exercised in `calls.rs` or `property.rs`.
- **How you know**:
  Read all of [model/tests/calls.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs) and [model/tests/property.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs), plus scratch test run.
- **What you suggest**:
  Add unit tests in `calls.rs` for each of these behaviours.

---

## Checked and Found Correct

- **D-103 cycle prevention and 192-walk bound**: Checked [model/src/caps.rs:235-253](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:235-253) (`fits`) and [437-460](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:437-460) (`next_removed`) across `cap_move`, `cap_derive`, `untyped_retype`, and IPC `deliver`. `Untyped` requires `depth >= depth(own)`, other `CSpace` roots require `depth > depth(own)`, a space may hold its own root (skipped by `swept`), and derived `CSpace` copies have no `swept` edges; removal cannot cycle and any walk is at most 191 capabilities (confirmed by scratch test).
- **Dying capabilities, objects, and `Reply` wake-up**: Checked [model/src/lib.rs:469-526](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:469-526) and [model/src/caps.rs:127-147](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:127-147), [437-452](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:437-452). Dying capabilities accept only `cap_delete`, dying objects fail all calls with `Gone`, `Reply` waiters wake uncounted when the `Reply` root is reached, and `cap_revoke` on a `CSpace` root does not sweep the space.
- **Slot addresses, `via` rights, dead slots, and `cspace_grow`**: Checked [model/src/lib.rs:490-575](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:490-575) and [model/src/caps.rs:199-223](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:199-223). `Read`/`Write` access through `via`, slot 0 rejection, `Dead` vs `Empty` vs `NoSlot`, and `cspace_grow` from the creating `untyped` match the contract.
- **IPC semantics, capability transfer, and notifications**: Checked [model/src/ipc.rs](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs) (`call`, `recv`, `reply_recv`, `send`, `signal`, `wait`, `poll`, `notify_bind`, `deliver`, `unlink`). FIFO queueing, badge stamping, badge-0 replies, `FLAG_CAPS_DROPPED`, `FLAG_NOTIFICATION`, `notify_bind` 1-to-1 and immediate delivery, and `Reply` idle/attached/armed transitions match the contract.
- **Threads**: Checked [model/src/lib.rs:609-654](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:609-654) (`thread_configure`, `thread_resume`, `thread_suspend`) against the contract.
