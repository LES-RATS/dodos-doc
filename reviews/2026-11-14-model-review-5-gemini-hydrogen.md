# Fifth Review of the DodOS One-Core Reference Model (`dodos-model`)

- **Reviewed commit**: `4554d26` (`model` branch of `dodos-kernel`) against [kernel-interface.md](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) and [abi/src/lib.rs](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs).
- **Test runs**:
  - Repo suite (`cargo test -p dodos-model` via `nix develop`): **301 passed, 0 failed** (292 unit/integration tests + 9 property tests).
  - Out-of-repo scratch suite (`cancel_probe/tests/interleavings.rs`): **10 passed, 0 failed**, confirming the uncovered `thread_cancel` interleavings and the D-106 race below.

No **`wrong behaviour`** bugs were found in the modelled transitions of `dodos-model`. All substantive issues below are **`contract error`** (design hazards in D-106 / `reply_recv`), **`undefined`** (two-author ambiguities / missing `CONTRACT-GAP` / unmodelled raw-rights validation), **`untested`** cases, and **`minor`** points.

---

## Findings (sorted by severity)

### 1. D-106's repeat-`thread_cancel` timeout recipe can still cancel an unrelated later call and can livelock on one core
- **Severity**: `contract error`
- **Where**: [kernel-interface.md:139](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L139) (D-106), [kernel-interface.md:134](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134) (`thread_cancel`).
- **What is wrong**:
  The contract states: *"Because a cancel that arrives before the wait is not remembered, the thread that cancels repeats until the other has seen it; a remembered cancel would hit an unrelated later call."* Two hazards remain in this design:
  1. **An in-flight cancel still hits an unrelated later call.** Checking a user-space `done` flag in the helper thread `H` and calling `thread_cancel(C)` are not atomic. If `C`'s timed call 1 completes normally right as the timer fires (or `H` reads `!done` just before `C` writes `done = true`), `C` can return from call 1 and enter an unrelated call 2 (`call`, `recv`, `wait`) before `H`'s already-decided `thread_cancel(C)` runs; the kernel then cancels call 2. A stale timer bit in the notify causes the same failure if call 2 runs before `H` drains the notify.
  2. **One-core livelock if `H` repeats without yielding.** On one core, `thread_cancel(C)` returns `Ok(Done)` immediately even when `C` already has `Cancelled` pending (`wait == Wait::None`). If `H` loops calling `thread_cancel(C)` until `C` runs and updates `done`, and `H` has scheduling priority ≥ `C` (note `yield` is neither specified nor modelled yet), `C` may never be scheduled to observe `Cancelled`, causing `H` to spin forever.
- **How you know**: Read in [kernel-interface.md:134,139](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134-L139) and **confirmed by a run** in scratch test `d106_in_flight_repeat_cancel_hits_unrelated_next_call_and_reply_recv_hides_drop`:
  1. `server` waits via `Recv(EP, RP)`.
  2. `client` issues `Call(EP, msg 1)` -> `Waits`; `server` receives `msg 1` (`RP` armed with `client`).
  3. Timer fires and wakes `helper`; before `helper` invokes `ThreadCancel`, `server` runs `ReplyRecv(RP, msg 100, EP)` -> `client` wakes with `Message(100)`.
  4. `client` marks call 1 done in user memory and enters unrelated `Call(ep2, msg 2)` -> `Waits`.
  5. `helper` now executes its in-flight `ThreadCancel(client)` -> returns `Ok(Done)` and wakes `client`'s Call 2 with `Err(Error::Cancelled)`.
- **What you suggest**:
  Document the required two-notify / badged-signal handshake in user space (detailed in the D-106 protocol section below) so `client` never enters call 2 until `helper` has acknowledged completion of call 1's timeout scope, and specify how `helper` avoids starving `client` on one core (e.g. lower helper priority, `yield`, or `timer_cancel` status + single cancel per armed epoch).

### 2. A server using `reply_recv` cannot tell that its reply was dropped due to a cancelled caller
- **Severity**: `contract error`
- **Where**: [kernel-interface.md:134,151,166](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134-L166), [ipc.rs:149-174](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L149-L174).
- **What is wrong**:
  When a caller is cancelled while `RP` is armed (`Wait::Reply(RP)`), `RP` becomes `Idle`. A server answering via `send(RP, resp)` gets `Err(Error::WouldWait)` and learns that the client did not receive `resp`. On the fast path (`reply_recv(RP, resp, EP)`), the contract specifies *"If the reply object is not armed the reply is dropped without an error and the receive goes on"*, so the server receives **no error and no flag** indicating `resp` (and any `Transfer::Move` / `Transfer::Derive` capabilities in `resp`) was not delivered. For non-idempotent requests (or deferred/worker-pool replies if `RP` is recycled prematurely), the server cannot detect the cancelled call.
- **How you know**: Read in [kernel-interface.md:151](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L151) and [ipc.rs:169-173](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L169-L173); **confirmed by a run** in [calls.rs:4052-4060](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L4052-L4060) and scratch test `reply_recv_on_cancelled_caller_does_not_move_reply_capabilities` (`ReplyRecv(RP, msg(9, [Move(NT)]), EP)` returns `Waits` with `NT` left in the server's slot).
- **What you suggest**:
  Keep the fast-path `reply_recv` behaviour if intended, but add an explicit note in the IPC / D-106 contract: servers that need delivery confirmation use `send(RP)` before `recv`, and multi-worker servers must never return `RP` to a `recv` pool before the worker has finished calling `send(RP)` (otherwise cancelling Call 1 makes `RP` idle, `recv` arms `RP` with Call 2, and the worker's late `send(RP)` answers Call 2).

### 3. Pre-model `Rights` decoding assumed by `caps.rs` contradicts `Order of checks`, and `Transfer::Derive` unknown-bit precedence is ambiguous
- **Severity**: `undefined`
- **Where**: [abi/src/lib.rs:145-195](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs#L145-L195), [model/src/lib.rs:48-51,89-94](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L48-L94), [caps.rs:107-116](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs#L107-L116), [ipc.rs:300-303](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L300-L303), [kernel-interface.md:103-112,164-167](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L103-L167).
- **What is wrong**:
  Unlike `Message.flags: u32` and `UntypedRetype.size: u64`, `Syscall::CapDerive.rights` and `Transfer::Derive(_, rights)` take pre-validated `dodos_abi::Rights`. The comment at [caps.rs:107-110](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs#L107-L110) pushes invalid-bit detection out of the model: *"whoever decodes the raw word answers `invalid` before calling the model"* (with no `CONTRACT-GAP` marker). That creates two problems:
  1. **Contradicts `Order of checks`**: decoding the raw rights word *before* calling `Model::apply` returns `Invalid` even when step 1 (`source` slot dead -> `Gone`, wrong kind, missing `DERIVE` -> `Denied`) or step 2 (`destination` `via` dead/denied, or in IPC: endpoint `SEND|GRANT`, bad message header, or an earlier listed slot) failed first.
  2. **Two-author ambiguity in `Transfer::Derive`**: the contract says *"a rights word with a bit that names no right is `invalid`, here and in a message, and is judged before the subset"* ([kernel-interface.md:112](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L112)), while [abi/src/lib.rs:189-195](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs#L189-L195) (`Rights::derive`) merges `DERIVE` and subset into a single `Denied` check. For a `Transfer::Derive` entry whose source capability lacks `DERIVE` *and* whose raw rights word has an unknown bit, one author will return `Invalid` (plain rights word invalid) and another `Denied` (capability lacks `DERIVE`, checked at the slot).
- **How you know**: Read in [caps.rs:107-116](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs#L107-L116), [ipc.rs:300-303](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L300-L303), [abi/src/lib.rs:166-195](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs#L166-L195), and [kernel-interface.md:103-112,164-167](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L103-L167).
- **What you suggest**:
  Pass raw `u32` (or a `RawRights(u32)` wrapper) in `Syscall::CapDerive` and `Transfer::Derive`, decode with `Rights::from_bits` at step 3 in `cap_derive` (before subset) and inside `listed`, and state explicitly in `Transfer of capabilities` whether an unknown rights bit in `Transfer::Derive` is checked before or after `DERIVE` on that slot.

### 4. Two-author ambiguity and missing `CONTRACT-GAP` on `Syscall::Other(ThreadReadRegs | ThreadWriteRegs)`
- **Severity**: `undefined`
- **Where**: [model/src/lib.rs:519-528](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L519-L528), [kernel-interface.md:135](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L135).
- **What is wrong**:
  The contract lists `thread_read_regs` and `thread_write_regs` in the Threads table with rights (`read`, `write`) and state (`busy` if not suspended), while adding *"these two calls are not part of the one-core reference and are `unsupported` in it."* The model takes no `thread` argument in `Syscall::Other` and returns `Err(Error::Unsupported)` after only `addressed_space` (`Gone` if caller's `cspace` is dying/destroyed), without a `CONTRACT-GAP` marker. Another kernel author reading the Threads table could reasonably check the `thread` capability (`Invalid`/`Gone`/`Denied`) and/or `suspended` (`Busy`) before returning `Unsupported`.
- **How you know**: Read in [lib.rs:519-528](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L519-L528) and [kernel-interface.md:135](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L135).
- **What you suggest**:
  Either state in [kernel-interface.md:135](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L135) that `unsupported` is returned immediately after resolving the caller's space (no argument checks), or mark [lib.rs:524](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L524) with `CONTRACT-GAP`.

### 5. `timer_set` / `timer_cancel` semantics needed by D-106 are not yet specified
- **Severity**: `undefined`
- **Where**: [kernel-interface.md:57,139](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L57-L139).
- **What is wrong**:
  D-106 relies on arming and cancelling a `timer` tied to a `notify`. Whether `timer_cancel` reports if the timer already fired (and confirms it never retracts a signal bit already merged into the notify word) is unspecified, directly affecting whether every timed call must perform a notify drain/handshake even on the fast non-timed-out path.
- **How you know**: Read in [kernel-interface.md:57,139](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L57-L139).
- **What you suggest**:
  When specifying the Time group, define whether `timer_cancel` reports if the timer had already fired and state explicitly that it cannot clear bits already ORed into the notify word.

### 6. Nine `thread_cancel` states and interleavings lack tests in `model/tests/`
- **Severity**: `untested`
- **Where**: [model/tests/calls.rs:4040-4215](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L4040-L4215).
- **What is wrong**:
  `calls.rs` pins basic `thread_cancel` semantics, `property.rs` fuzzes `ThreadCancel`, and [lib.rs:747-758](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L747-L758) handles all edge cases accurately, but nine specific combinations have no dedicated tests in `calls.rs`:
  1. `thread_cancel` on a **suspended** thread waiting in `Wait::Call`, `Wait::Reply`, or `Wait::Recv` (`calls.rs:4126` tests only `Wait::Notify`).
  2. `thread_cancel` preserving a completed `Output::Message` or `Err(Error::Gone)` outcome (`calls.rs:4168` tests only `Output::Word`).
  3. `thread_cancel` on a waiting thread bound to a **dying or destroyed** `cspace`.
  4. `thread_cancel` called by a thread whose `cspace` is **destroyed** (`calls.rs:4160` tests only dying).
  5. `thread_cancel` on a **dying thread** (`CapDelete` on root returned `Again` -> `Gone` through any cap) vs on a dying copy of a live thread (`Gone` through dying copy, `Done` through another cap).
  6. `thread_cancel` on a thread queued on a **dying endpoint/notify** mid-`cap_delete` (`Again` after waking 32 of >32 waiters).
  7. `thread_cancel` followed by `thread_configure` (fails with `Busy` while waiting; succeeds once cancelled while suspended, preserving `Cancelled`).
  8. `reply_recv` on a cancelled caller where the reply message lists capabilities (`Transfer::Move` leaves capability untouched in server's slot).
  9. `thread_cancel` of a receiver on an endpoint with a bound notify leaving a subsequent `signal` pending.
- **How you know**: Read in [calls.rs:4040-4215](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs#L4040-L4215) and **confirmed by a run** of all nine scenarios in the out-of-repo scratch suite (`cancel_probe/tests/interleavings.rs`: 9/9 passed + D-106 trace).
- **What you suggest**:
  Port these nine cases into [model/tests/calls.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs).

### 7. Notification `marks` and `task` fields have no contract rule or `CONTRACT-GAP` for notifications
- **Severity**: `minor`
- **Where**: [ipc.rs:60-82](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L60-L82), [kernel-interface.md:179](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L179).
- **What is wrong**:
  `notification(word)` uses `received(header, word)`, which documents `marks = NONE, task = 0` as *"Tasks are not modelled"*. Even once tasks are modelled, a notification returned by `recv`/`reply_recv` can aggregate signals from timers, interrupts, or multiple threads and has no single sending task; `ipc.rs:61-63` marks `label = 0, words = []` with `CONTRACT-GAP (Notifications)` but does not mention `marks` and `task`.
- **How you know**: Read in [ipc.rs:60-82](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L60-L82).
- **What you suggest**:
  Specify in [kernel-interface.md:179](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L179) (or widen the `CONTRACT-GAP` at `ipc.rs:61`) that kernel-delivered notifications stamp `marks = 0, task = 0`.

### 8. Sharing `depth` and `dying` helpers between `Model` and `check.rs` weakens invariant independence
- **Severity**: `minor`
- **Where**: [caps.rs:254-256](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs#L254-L256), [lib.rs:591-594](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L591-L594), [check.rs:43-55,248,277,405](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs#L43-L405).
- **What is wrong**:
  Commits `6ccdcd8` and `934f3a4` unified `depth` and `dying` between the model's call handlers and `Model::check`. While they preserve exact behaviour on valid states (and safely use `.get` so spoiled test states in `check/tests.rs` fail cleanly on invariants 1/8/9 rather than panicking), sharing them creates common-mode blind spots:
  - A bug in `Model::depth` (e.g. off-by-one or early stop) would affect both `fits`/`listed` and Invariants 20 (`TREE_DEPTH`) and 28 (D-103).
  - A bug in `Model::dying` would affect both `full`/`addressed_space`/`deliver` and Invariant 22 (`dying(reply) => Idle`) — though Invariant 27 (`self.dying(id) == sweep.is_some()`) still cross-checks `dying` for `CSpace`s against `next_removed`'s `sweep` field, and `check/tests.rs` explicitly tests spoiled trees and `root.dying = true`.
- **How you know**: Read in [check.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs) and `git show 6ccdcd8 934f3a4`.
- **What you suggest**:
  Keep `depth` and `dying` inline/separate inside `check.rs` if `Model::check` is meant to remain an independent oracle of `Model`.

---

## Special-Angle Audit: `thread_cancel`, `Error::Cancelled`, and D-106

### State and interleaving matrix

| Case | Contract ([kernel-interface.md:134,137](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134-L137)) | Model ([lib.rs:747-758](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L747-L758), [ipc.rs:479-494](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs#L479-L494)) | Pinned by test? |
|---|---|---|---|
| Queued on endpoint (`Wait::Call`) | Unlinked from endpoint queue; call returns `Cancelled` | `unlink` removes from `endpoints[ep].queue`, `wake` sets `Err(Cancelled)` | `calls.rs:4029`, `calls.rs:4097` |
| Waiting for reply (`Wait::Reply`, `RP` armed) | Reply object becomes idle; late answer dropped (`send` -> `WouldWait`, `reply_recv` -> dropped); caller gets `Cancelled` | `unlink` resets `replies[rp] = Idle`, `wake` sets `Err(Cancelled)` | `calls.rs:4041,4052,4189` |
| Waiting to receive (`Wait::Recv`, `RP` attached) | Unlinked from endpoint queue; `RP` becomes idle; receiver gets `Cancelled` | `unlink` removes from `endpoints[ep].queue`, resets `replies[rp] = Idle`, `wake` sets `Err(Cancelled)` | `calls.rs:4063` |
| Waiting on notify (bound or unbound, `Wait::Notify`) | Unlinked from notify waiters; notify word and endpoint binding unchanged; waiter gets `Cancelled` | `unlink` removes from `notifies[nt].waiters`, `wake` sets `Err(Cancelled)` | `calls.rs:4076` |
| Wait with message listing capabilities (`Move`/`Derive`) | Nothing moved or derived (transferred only at delivery) | `Wait::Call` drops `parcel`; no slots or tree modified | `calls.rs:4097`; scratch (`Move`+`Derive`) |
| Suspended waiting thread | Stays suspended; `Cancelled` preserved until resumed and next call | `suspended` untouched; `outcome = Some(Err(Cancelled))` cleared only on next `apply` | `calls.rs:4126` (`Notify`); scratch (`Call`, `Reply`, `Recv`) |
| Wait already over (`Message`, `Word`, `Gone`, prior `Cancelled`) | Does not wait; keeps existing outcome | `wait == Wait::None`, so `if` skipped; returns `Ok(Done)` | `calls.rs:4168` (`Word`); scratch (`Message`, `Gone`) |
| Target thread in dying or destroyed `cspace` | Target `cspace` not consulted by `thread_cancel`; wait cancelled (`Cancelled`), target's next call gets `Gone` (or `cap_delete` on own slots while dying) | `self.object` resolves caller's space only; `unlink` + `wake(Cancelled)` succeed; target gets `Gone` on next `apply` | Scratch test |
| Caller in dying or destroyed `cspace` | Caller gets `Gone` before any argument is looked at | `self.object` -> `addressed_space` -> `Gone` | `calls.rs:4160` (dying); scratch (destroyed) |
| Target thread being destroyed (`cap_delete` on root -> `Again`) | Object is dying from step 1: any call on it returns `Gone` | `dying(target) == true` -> `self.full` returns `Err(Gone)`; final `cap_delete` step runs `destroy` -> `unlink` | Scratch test |
| Target of removal on only a copy / on waited endpoint or notify | Dying copy -> `Gone`, live copy -> `Done`; waiter on dying EP/notify (`Again`) unlinked with `Cancelled` | `held.dying` -> `Gone`, root/other copy -> `Done`; dying EP/notify queue shrinks by 1 | Scratch tests |
| Caller cancelling itself | Running caller is not waiting -> succeeds, changes nothing | `wait == Wait::None` -> `Ok(Done)` | `calls.rs:4152` |
| Cancel racing with delivery (`call`/`send`/`reply_recv`/`hand_over`) | Whichever runs first wins; post-delivery cancel sees `wait == None` and keeps `Message`/`Word`; post-cancel `reply_recv` drops reply (`send` -> `WouldWait`) | Atomic single-step `apply` guarantees clean linearization | `calls.rs:4041,4052,4168`; scratch |
| Cancel racing with `signal` | Pre-cancel `signal` wakes waiter with `Word` (cancel leaves `Word`); post-cancel `signal` leaves bit pending or wakes next waiter / bound receiver | `hand_over` vs `thread_cancel` | `calls.rs:4076,4168`; scratch (`bound_endpoint`) |
| Cancel racing with `reply_recv` (incl. caps in reply) | Post-cancel `reply_recv` drops reply without moving/deriving reply caps | `answer` sees `Idle`, returns `None` without calling `deliver` | `calls.rs:4052`; scratch (with `Move`) |
| Cancel vs `thread_configure` | `thread_configure` is `Busy` while waiting; after `thread_cancel` on suspended thread, `thread_configure` succeeds and `Cancelled` survives | `target.wait` becomes `Wait::None`, freeing old range; `outcome` untouched | Scratch test |

### Soundness of D-106 (timeout built outside the kernel)

Because `thread_cancel` is stateless (neither remembered before a wait nor tagged with a wait generation), a client library can build sound per-call timeouts **only** by synchronizing `client` (`C`) and `helper` (`H`) across every timed call boundary so `H` can never still be acting on call `s` when `C` enters call `s + 1`.

**Exact sound protocol**:
Allocate two notifies (`N_timer` and `N_ack`), two distinct badged `SEND` caps to `N_timer` (`NT_TIMER` with badge `1`, given to `timer`; `NT_WAKE` with badge `2`, held by `C`), shared atomics `seq = 0`, `active = false`, `ack = 0`:
1. **Before `call` (sequence `s = seq + 1`)**: `C` writes `seq = s; active = true` (release), arms `timer` to signal `NT_TIMER` (badge `1`) at deadline, then executes `call(EP, ...)`.
2. **Helper loop (`H`)**: `loop`: `bits = wait(N_timer)`; read `s = seq`; if `bits & 1 != 0`: while `active.load(Acquire)` && `seq.load(Acquire) == s`, call `thread_cancel(C)` (must yield / run at lower priority than `C` on one core, or sleep briefly, so `C` can run to clear `active`); write `ack = s` (release) and `signal(N_ack)`.
3. **After `call` returns (whether `Ok(Message)` or `Err(Cancelled)` or `Err(Gone)`)**:
   - **After `call` returns** (whether `Ok(Message)`, `Err(Cancelled)`, or `Err(Gone)`): `C` immediately sets `active = false` (release), calls `timer_cancel(timer)`, and if `ack.load(Acquire) != s`, signals `NT_WAKE` (badge `2`) and loops `while ack.load(Acquire) != s { let _ = wait(N_ack); }` (ignoring `Err(Cancelled)` to absorb any in-flight `thread_cancel`). If the timer fired concurrently with `timer_cancel`, `H` receives `1 | 2` in one `wait(N_timer)` word, clears both bits, sets `ack = s`, and signals `N_ack` once—so both notifies are clean before call `s + 1` begins.

Evaluating the five failure modes under this protocol vs the naive D-106 recipe:
1. **Lost cancel**: Impossible under both, *provided* `H` can yield or has lower priority than `C`; otherwise `H` repeating `thread_cancel` livelocks on one core (Finding 1).
2. **Cancel hitting the wrong call**: **Happens in the naive recipe** when an in-flight `thread_cancel` or stale notify bit lands after `C` enters call `s + 1` (Finding 1). Prevented by the `ack == s` barrier before `C` starts call `s + 1`.
3. **Reply delivered to the wrong call after a cancel**: **Impossible** in the kernel. Cancelling `C` sets `RP` to `Idle`; `C`'s next `call` either waits in the endpoint queue or arms a *new* reply slot (or even the same `RP` only after the server calls `recv`/`reply_recv`), and any late `send`/`reply_recv` from call 1 either fails with `WouldWait` (if `RP` is still `Idle`) or was already `Idle` when call 2 began.
4. **Server unable to tell which request it answers**: **Unresolved for `reply_recv`** (Finding 2). On `send(RP)` the server gets `WouldWait`, whereas on `reply_recv(RP, ...)` the reply is silently dropped.
5. **Reply object stuck non-reusable**: **Impossible**. `unlink` resets `ReplyState` to `Idle` unconditionally (`Wait::Reply` and `Wait::Recv`), and deleting a `Reply` object wakes its attached/armed thread first (`next_removed`).

---

## Rest of the Model and Recent Refactorings

- **Bounded work (`32` / `128` / `191`)**: Confirmed in [caps.rs:424-551](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs#L424-L551). `remove` bounds removals/wakes at `REMOVAL_STEP = 32` and examined dying slots at `REMOVAL_SLOTS = 128` (not charging a full slot while its cap is being removed, matching [kernel-interface.md:92](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L92)), and `longest_walk` is asserted `<= LONGEST_WALK (191)` by Invariant 24. Model-only `Vec::retain`, `VecDeque::retain`, and `sweep.held` are explicitly documented as stand-ins for doubly-linked kernel lists and invariant-23 checks.
- **Nine recent refactorings (`b6584e5..ffdf336`)**:
  - `Swept` (`b6584e5`), `Listed` (`a46dfd6`), `Rights` replacing `Access` (`e7dbcdc`), `Place` (`7a2f09f`), `unlink -> ()` (`c9305b2`, `ffdf336`), `bound_space`/`addressed_space` (`f5425fa`), and `5cb1db2` (`if` for `exec`, removing `Checked`, Invariant 21 doc): none changed any observable behaviour.
  - Sharing `depth` (`6ccdcd8`) and `dying` (`934f3a4`) preserved behaviour on valid states and avoided panics on spoiled states, at the cost of weakening invariant independence (Finding 8).

---

## Checked and Found Correct

- **ABI & constants ([abi/src/lib.rs](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs))**: All constants, error codes, `Rights`, `SlotAddr`, `Header` bitfields, and `ObjectKind` match [kernel-interface.md](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **Capabilities & derivation tree ([caps.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs))**: `cap_derive`, `cap_move`, `cap_delete`, `cap_revoke`, `cap_inspect`, `untyped_retype`, `cspace_grow`, D-103 depth rules, watermark/alignment, device-memory rules, and dead-slot tracking match the contract and `Order of checks` (except raw `Rights` decoding in Finding 3).
- **IPC, capability transfer, and notifications ([ipc.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs))**: `call`, `recv`, `reply_recv`, `send`, `signal`, `wait`, `poll`, `notify_bind`, all-or-nothing delivery transfer with `caps_dropped`, badge rules, and bound-notify precedence match the contract.
- **Threads ([lib.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs))**: `thread_configure`, `thread_resume`, `thread_suspend`, `thread_cancel`, `cspace` dying/destroyed handling, and `outcome` lifecycle match the contract (apart from `Syscall::Other` in Finding 4 and already-marked `CONTRACT-GAP`s at [lib.rs:391,702](file:///Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs#L391-L702)).
- **State invariants ([check.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check.rs), [check/tests.rs](file:///Users/btw/Documents/repos/dodos-kernel/model/src/check/tests.rs))**: All 30 numbered invariants accurately formalize the contract and are guarded by unit mutation tests and property tests.
