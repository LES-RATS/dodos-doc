# Review 5 (Mistral): the one-core model on branch `model`, with `thread_cancel` as the new attack surface

Date: 2026-11-14. Reviewer: Mistral (review sub-agent). Scope: the executable reference
model in `/Users/btw/Documents/repos/dodos-kernel/model/` (branch `model`, commits up to
`4554d26`) against the contract `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
("Call reference, one core", Rules, Objects, System calls, Rights, Errors) and
`abi/src/lib.rs`. Nothing was changed, committed or pushed; probes ran in a scratch copy
under `/tmp/dodos-review` (a verbatim copy of `abi/` + `model/` plus iteration counters);
the repository test suite was run once with the prescribed nix command.

Test run: `nix develop -c cargo test -p dodos-model` — **405 tests, 0 failed**
(104 unit + 292 in `tests/calls.rs` + 9 in `tests/property.rs`, the last in 109 s).
`git status` clean afterwards, on branch `model`. All probe observations below are from
runs of the scratch copy; "confirmed by a run" means the probe printed the stated outcome.

Severity legend: wrong behaviour / contract error / accepted limit worth knowing /
undefined / untested / minor.

---

## Findings, sorted by severity

### 1. The bounded wait of D-106 cannot be built reliably from the calls as specified — the contract's repetition rule is not implementable as written — **contract error**

- **Where**: contract line 139 ("Because a cancel that arrives before the wait is not
  remembered, the thread that cancels repeats until the other has seen it"); model
  `model/src/lib.rs:747` (`thread_cancel`), `model/src/ipc.rs:479` (`unlink`).
- **What is wrong**: "until the other has seen it" assumes the canceller can observe that
  the cancelled thread has seen the cancel. It cannot: `woken` is per-thread state only the
  thread itself reads, and `thread_cancel` returns `Ok` whether or not the target was
  waiting (probe B7a/B7b). So a watchdog that cancels once can lose the cancel, and a
  watchdog that repeats can hit the *next* call of the same thread. Both sequences are
  real in the model:
  - **Lost cancel (deadlock)**: `W: wait(N)` → woken with the timer word; `W:
    thread_cancel(C)` → `Ok` (C was runnable, nothing remembered); `C: call(EP, msg,
    range)` → `Waits`. No rule bounds this wait any more; the timer word was consumed by
    W. (Probe C-A: census `callers=1`, wait forever.)
  - **Cancel hits the next call**: `C: call#1` → `Waits`; `W: thread_cancel(C)` → C woken
    `cancelled`; `C: call#2` → `Waits`; `W: thread_cancel(C)` (the repeat) → call#2
    returns `cancelled` although its own deadline never fired. (Probe C-B, confirmed.)
- **How I know**: confirmed by runs (probes C-A, C-B); the model implements the contract
  exactly — `thread_cancel_of_a_thread_that_does_not_wait_changes_nothing_and_is_not_remembered`
  pins "not remembered". This is a gap in the contract, not in the model.
- **Suggest**: keep "not remembered" — a remembered cancel would hit an unrelated later
  call with no way for the client to tell (the contract says this itself). But correct the
  sentence at line 139: "seen" is not observable, and a repeated cancel can land on a later
  wait of the same thread. Either (a) state that explicitly and require that calls bounded
  this way be retry-tolerant (a stale cancel = an early timeout of the next call), or
  (b) add a cancel token: `thread_cancel(thread, token)` where the token is a word the
  caller supplied with the waiting call and the kernel stamps on the wait; the cancel
  succeeds only if the thread's current wait carries that token. Sequence C-B is the one
  that shows (b) is needed for exactness: with a generation number on the wait, W's repeat
  after C moved on would not match call#2's token and would be refused.

### 2. A late answer can reach the *next* call when the server reuses one reply object — the contract's protection holds only while the object is idle — **accepted limit worth knowing; untested**

- **Where**: contract line 141 (Threads, `thread_cancel`: "a later answer is dropped as for
  any reply object that is not armed") and line 154 ("a server that answers later, from
  several reply objects"); model `model/src/ipc.rs:371` (`answer`), `:479` (`unlink`).
- **What**: the drop-on-cancel protection covers only the window in which the reply object
  is idle. If the server receives again with the *same* reply object before answering the
  cancelled request, the object is re-armed with the next caller, and a stale `send` on it
  is delivered to that caller as the reply to its own, different request. Confirmed
  sequence (probe B4):
  1. `S: recv(EP, RP)` → waits; 2. `C: call(EP, req1)` → delivered at once, RP armed with C;
  3. `W: thread_cancel(C)` → C woken `cancelled`, RP idle;
  4. `S: recv(EP, RP)` again → waits with RP attached;
  5. `C: call(EP, req2)` → delivered at once, RP **re-armed** with C;
  6. `S: send(RP, answer_to_req1)` → `Ok(Sent)` and C's call#2 outcome is
     `msg(label=9)` — the late answer reached the next call.
  With a dedicated reply object per in-flight request the same stale `send` returns
  `WouldWait` and is dropped (probe B5a); with `reply_recv` (answer + receive atomically)
  the stale reply is dropped silently and the next request is taken (probe B5b).
- **How I know**: confirmed by run (B4 vs B5). The model matches the contract — `send` on
  an armed reply object answers the armed caller, whoever it is. No test covers the
  re-armed case (`send_on_the_reply_object_of_a_cancelled_caller_is_would_wait` covers
  only the idle object).
- **Suggest**: the model is right; pin the hazard. Add a contract sentence for servers:
  "never answer a request through a reply object that has been attached or armed again
  since the request was received; use one reply object per in-flight request, or answer
  with `reply_recv`". Add a test with the B4 sequence so the behaviour is documented as
  intended.

### 3. Who can cancel whom: no escalation path exists in the model; every way to obtain `manage` on a thread is a sharing decision — **accepted limit worth knowing**

- **Where**: `model/src/lib.rs` (`held`/`is`/`cap`), `model/src/caps.rs` (`cap_derive`,
  `fits`), `model/src/ipc.rs` (`listed`, `deliver`).
- **What**: confirmed by runs (probes A1–A8), the ways to obtain `manage` on a thread one
  should not control are exactly: (i) derivation from a capability that already has it —
  rights never grow, `derive(MANAGE)` from a SEND|DERIVE cap returns `Denied` (A1, F1);
  (ii) `untyped_retype` — gives ALL rights but only on a **new** object, never on an
  existing thread (A2); (iii) `cap_move`/IPC transfer — full rights travel with the
  capability, so a server that sends its own thread capability to a client lets the client
  cancel it (A6: client2 received the server's manage-copy in its receive range and
  cancelled the server, outcome `Cancelled`); (iv) a `via` address — **READ on a cspace
  capability is enough to *use* a manage-cap found in that space**, only `write` is needed
  to place one (A7: cancel through `via(33,5)` with a READ-only cspace cap succeeded;
  without READ it was `Denied`); (v) a manage-copy left in a space the other threads share —
  any thread bound to that space can cancel through the plain slot (A3: client cancelled
  the server through slot 46 of the shared boot space); (vi) the creator keeping a copy
  after giving the thread to a process — the creator can cancel the process's threads at
  any time, the process cannot cancel back (A8d/A8f). All are the contract's design
  (capability discipline is the policy); the model enforces the rights correctly in every
  case.
- Related, confirmed (A5): any holder of `recv` on an endpoint can consume any queued
  caller — message, badge and transferred capabilities (caller needs `grant`; the thief's
  empty receive range gets the caps). The badge identifies the sender but protects nothing.
- **Suggest**: nothing in the model. Worth one paragraph in the contract's Threads section:
  "read on a cspace capability means the right to use every capability in that space
  within its rights", so supervisors place manage-copies only in spaces of processes that
  must be controllable, and servers never grant their own thread capability.

### 4. Server side after a cancel: the reply is dropped silently, leftover range caps can poison the next live request, but nothing accumulates — **accepted limit worth knowing; partly untested**

- **Where**: `model/src/ipc.rs:371` (`answer`), `:390` (`deliver`); contract lines 158-159
  ("When a caller disappears while its request is being served, the reply object becomes
  idle"), 168 ("A server that answers with `reply_recv` is not told that the capabilities
  of its reply were dropped").
- **What** (all confirmed by runs):
  - `send` on the reply object of a cancelled caller returns `WouldWait` — the server **can**
    tell (B2e); `reply_recv` drops the reply with **no error and no flag** — it cannot
    (B2f). The model matches the contract.
  - A cancelled client's transferred capabilities stay in the server's receive range (D1c).
    If the server does not clean them, the next **live** client's capabilities are dropped
    with `caps_dropped` (D1e: server received the live client's request with `caps=0,
    flags=0x1`), while the live client's caps stay in its own slots (D1f). A confusion
    hazard, not a leak.
  - No resource accumulates per cancelled request in the kernel: the reply object becomes
    idle and is reused (D1g: `receivers=0`), a queued caller's parcel is discarded with
    nothing moved (B3), and the queue of callers is bounded only by the number of threads,
    each paid 1 KB by its creator (D2: 20 queued callers, one cancel). Clients cannot
    exhaust the server through cancels; the space itself bounds the leftover caps.
- **Suggest**: contract guidance for servers: clean the receive range after every received
  message (including ones whose caller vanished), and use `send` if you need to learn that
  a caller was cancelled. Add a test for the D1e sequence.

### 5. Cancel as a weapon: mostly ineffective; the two effective uses are wasted server work and the finding-2 misdelivery — **accepted limit worth knowing**

- **Where**: `model/src/lib.rs:747`, `model/src/ipc.rs:479`.
- **What** (confirmed by runs): cancelling a server's receiver does **not** starve queued
  clients — the next `recv` still serves them FIFO (B1d); a cancel on an empty queue just
  returns `cancelled` to the server (B1b/B1e). Cancelling a queued caller moves none of
  the capabilities it listed and the server receives the next caller (B3a–B3e). Cancelling
  a delivered caller wastes the server's work but corrupts nothing (B2). Cancel interleaved
  with a removal is safe in both orders — no double wake, no outcome overwrite (B6: the
  reply object's state is the guard; cancel sets Attached/Armed → Idle, so the removal's
  wake finds no waiter). Cancel does not duplicate or lose capabilities in a transfer: a
  queued caller's parcel is dropped whole (B3c), a delivered caller's caps stay in the
  server's space (D1c). What does work: cancelling each client between request and reply
  (the server's work is useless, B2), and the finding-2 misdelivery.
- **Suggest**: none for the model; the contract's "no timeout in the kernel" stays cheap
  because cancel is one unlink.

### 6. The watchdog itself can be blocked or starved — **accepted limit worth knowing**

- **Where**: `model/src/ipc.rs` (`hand_over`, `wait`), contract Notifications.
- **What** (confirmed by runs): a watchdog waiting on a notify can itself be cancelled by
  anyone holding `manage` on it — its `wait` returns `cancelled` (C-C1/C-C2), so its loop
  must retry on `cancelled`; and one `signal` wakes exactly one of several waiters on a
  notify, consuming the whole word (C-D: two waiters, one signal → one woken, one asleep),
  so a watchdog must use a private notify per outstanding call, or it can sleep through
  its own timer.
- **Suggest**: protocol guidance (see the recommended client protocol below).

### 7. Using `cancelled` or cancel timing to learn about another process — **minor**

- **Where**: `model/src/lib.rs:747`.
- **What**: `thread_cancel` returns `Ok` whether or not the target waited (B7a/B7b), so the
  return value leaks nothing; but an observer holding `recv` on the endpoint (or `poll` on
  a notify) can see that a victim's wait ended by watching the queue empty (B7c). A
  state/timing side channel. The contract already accepts this ("Known limit … timing and
  other covert channels are not covered", Tasks and provenance).
- **Suggest**: nothing; worth one line in the contract's Threads section.

### 8. Model vs contract: frame sizes are not rounded to a power of two — **undefined / minor**

- **Where**: contract line 122 ("Object sizes are rounded up to a power of two (a thread in
  the one-core reference: 1 KB)") vs `model/src/caps.rs:54` (`ObjectKind::Frame =>
  (size * page.bytes(), size > 0)`) with alignment only on the page size (`caps.rs:84`).
- **What**: a frame of 3 × 4 KB takes 12 KB at the watermark in the model; rounded to a
  power of two it would take 16 KB. Every other size is a power of two in both (child
  untyped must be one; the cspace directory is `next_power_of_two`; the other objects have
  fixed power-of-two sizes). The contract's own alignment rule for frames ("on the page
  size for a frame") suggests the rounding sentence means kernel objects, but it says
  "object sizes".
- **Suggest**: one clarifying sentence in the contract: whether a frame's size at the
  watermark is rounded up to a power of two or is exactly pages × page size.

### 9. Behaviour decided by the model alone without a CONTRACT-GAP tag — **minor**

- **Where**: `model/src/ipc.rs` `received()`: `marks: Marks::NONE, task: 0` — the comment
  says "Tasks are not modelled", but unlike the other gaps it is not tagged `CONTRACT-GAP`.
  (The boot layout, the aspace/fault-endpoint gap and the notification header are properly
  tagged in `model/src/lib.rs` and `model/src/ipc.rs`.)
- **Suggest**: add the tag or a pointer to the Tasks section being "Proposed".

### 10. Rules no test checks — **untested**

- The finding-2 sequence (stale `send` on a re-armed reply object reaching the next call).
- The finding-4 sequence (a cancelled client's leftover range caps making a live client's
  request arrive with `caps_dropped`).
- The bound "a call makes at most 32 walks, so it wakes at most 64 threads" (contract,
  Removal ends): the step counting is tested
  (`waking_a_thread_counts_as_one_step_of_removal`,
  `wake_of_the_step_that_marks_a_reply_object_is_not_counted`), but no test drives one call
  to the 64-wake maximum.
- "`busy`, before anything is received: a pending notification stays pending" — the
  `recv`-busy tests have no pending word on the bound notify.
- Cancel interleaved between the steps of a running removal — covered only randomly by the
  property tests (invariants hold after every call); I verified by reading that an outcome
  overwrite is impossible (finding 5), but a targeted test would pin it.

### 11. Measured costs (method (b), sizes varied, counters in the scratch copy) — **accepted limit worth knowing**

- `thread_cancel` on a queue of length N: the model's `unlink` scans the queue (1→1, 5→5,
  … 80→80 retain comparisons, probe E1). The contract's doubly-linked unlink is one step
  (`model/src/ipc.rs:475-478` says so); the scan is a property of the model, and the queue
  length is bounded only by the number of threads. Rule 4 (every call bounded) holds.
- Removal of a full space: `cap_delete` calls scale as slots/32 + slots/128 — measured 4, 8,
  32, 128 calls for 128, 256, 1024, 4096 slots (probe E2) — extrapolating to the contract's
  own 40,960 calls for a full 2^20-slot space. Max walk inside one call measured 64; the
  property runs measured `longest_walk` up to 122 (≤ `LONGEST_WALK` = 191, invariant 24).
  A depth-64 chain was removed in 2 calls with 1488 walk iterations in the first — under the
  32 × 191 bound (probe E3). `depth()` (used by every `fits` check) is O(depth) ≤ 64.
- No unbounded loop found: every loop in the model is bounded by `REMOVAL_STEP` ×
  `LONGEST_WALK` + `REMOVAL_SLOTS`, by the queue length, or by the table size. Rule 3 (no
  kernel heap) is structural.
- The hostile child (contract's accepted limit): during `cap_revoke` (not `cap_delete`)
  new derivations under the revoked capability are still accepted, and deriving 33 per
  step prolonged the removal of 200 copies from 6 to 31 `again`-calls on a 1024-slot space
  (probe F5) — it ends only when the space's slots run out, scaling with the slot budget
  (2^20 ⇒ ~31,000 calls). Exactly the limit the contract acknowledges in "Removal ends".

---

## The client protocol I recommend for bounding a `call` in time

Per outstanding call, one watchdog thread W (holds only `manage` on the client thread C),
one private notify N, one ack notify A:

```
C: 1. signal(A) = 0                       # ack cleared before the call
C: 2. timer_set(T, deadline, tol)         # T signals N when it fires
                                       # (timer is outside the one-core model; the probe used signal(N))
C: 3. call(EP, request, range)            # -> Waits
C: 4. when C runs again, the outcome of the wait:
         Ok(Message(reply)) -> done
         Err(Cancelled)     -> this wait was ended by the watchdog: treat as timeout
         Err(Gone)          -> endpoint or reply object destroyed
     then: signal(A) = 1                 # ack, before any next call

W: 1. wait(N)                             # retry the wait if it returns Cancelled (finding 6)
W: 2. loop { thread_cancel(C); poll(A); if A == 1 then stop }   # repeat: a cancel before the
                                       # wait is not remembered (finding 1, sequence C-A)
```

Rules that make it as safe as the contract allows: one notify per outstanding call (one
signal wakes one waiter and consumes the word, C-D); the watchdog's `manage` capability is
held only by the supervisor; every call bounded this way must be retry-tolerant, because a
stale repeat can land on its next wait (sequence C-B). The residual race between W's
`poll(A)` and `thread_cancel(C)` cannot be closed from user space with "not remembered" —
if exactness is needed, the kernel should take a cancel token per wait (finding 1).

Verdict on "not remembered": **the right choice**. A remembered cancel would make the
thread's very next wait fail for an unrelated reason with no client-side way to distinguish
it; "not remembered" moves the residual race to the watchdog, where it is visible in the
protocol. But the contract's "repeats until the other has seen it" should be reworded (finding 1).

Server protocol: one reply object per in-flight request, answer with `send` on that object
(or atomically with `reply_recv`); never answer through a reply object re-armed since the
request arrived (finding 2); clean the receive range after every message, cancelled caller
or not (finding 4); use `send`, not `reply_recv`, when you need to learn the caller vanished.

---

## What I checked and found correct

- `thread_cancel` implements the contract exactly: all four wait kinds end with `cancelled`
  (12 targeted tests + property coverage `waits_of_every_sort_are_cancelled`), the attached
  or armed reply object becomes idle, nothing is remembered for a next wait, a finished wait
  keeps its result, a suspended cancelled thread stays suspended, `manage` is required, and
  a thread in a dying space gets `gone`. All pass.
- The recent change (commits `b45b29e`, `4554d26`) touches only `abi/src/lib.rs`,
  `model/src/lib.rs` (the new call reusing the already-tested `unlink` + `wake`) and
  invariant 30; it does not interact with removal, transfer or depth code — the earlier
  attacks re-run clean: rights never grow (F1), a capability does not outlive its parent and
  a dead slot is not free (F2), the watermark returns to the start only when the last object
  from the untyped dies — deleting a copy frees nothing, deleting the root does (F3), D-103
  refuses two spaces holding each other's root (F4), and the hostile-child limit behaves as
  the contract states (F5, finding 11).
- Clause-by-clause, the model matches the contract on: order of checks (steps 1-4, header
  right after the acted-on capability), slot/via/dead-slot rules, badge rules, derivation
  subset and depth-64, D-103 placement rule, removal steps (32 removed-or-woken, 128 swept
  slots, `again`, last step succeeds), dying-space rules (gone from every call but
  `cap_delete` on own slots, deliveries drop caps, dying space only shrinks), reply object
  attach/arm/idle, `call`/`recv`/`reply_recv`/`send` semantics, transfer checked at call and
  at delivery with `caps_dropped`, notifications (bind, one-woken-per-signal, bound-notify
  precedence). 405 tests pass; invariants 1-30 hold after every call of 24 seeds × 5000
  random steps.
- Cancel does not corrupt capability transfer: a queued caller's listed capabilities never
  move (B3), a delivered caller's already-moved capabilities stay put (D1c), and cancel
  interleaves safely with removals in both orders (B6).
- The model's `Model::boot` simplifications and the notification header's label/words are
  tagged `CONTRACT-GAP`; `Census` and `longest_walk` are documented as harness-only.

## Notes on method

- Probes lived only in `/tmp/dodos-review` (scratch copy with iteration counters added to
  `unlink`, `remove`, `next_removed`, `swept`, `depth`); the repository was not modified.
- The full D-106 recipe (timer → notify) cannot be built inside the one-core model because
  `timer` is one of the kinds not yet specified (`unsupported`); the probes used `signal`
  on a notify, which is the primitive the timer drives.
- I did not read the earlier reviews in this folder.
