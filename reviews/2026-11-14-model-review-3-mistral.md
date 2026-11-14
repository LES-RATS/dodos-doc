# Review of the one-core executable model (branch `model`) — Mistral, 2026-11-14

Reviewer: Mistral Large 4 (as review sub-agent). Scope: the executable reference
model in `/Users/btw/Documents/repos/dodos-kernel/model/` against the contract
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` ("Call
reference, one core", Rules, Objects, System calls, Rights, Errors), the
interface in code `/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs`,
reviewed read-only. I did not read the other files in this directory. Nothing
was changed, committed or pushed; `git status` in the kernel repo is clean.
Probes ran from a scratch copy outside the repository (`/tmp/dodos-probes`).

Test run (as instructed):
`cd /Users/btw/Documents/repos/dodos-kernel && nix develop -c cargo test -p dodos-model`
→ **211 passed, 0 failed** (207 in `tests/calls.rs` + `src/check/tests.rs`, 4
property tests over 24 seeds × 5000 steps, each step followed by `Model::check`).

Method: full read of the contract, `abi/src/lib.rs`, and all six model files;
then attack probes on a scratch copy (`/tmp/dodos-probes`), including an
instrumented copy of the model with counters for loop iterations of one call.
Sizes probed: 1, the limits, limit+1, and the largest the types allow
(2^20-slot space, 64 levels, 4 capabilities, 64 words, ~10^3 waiting threads,
~5·10^5 objects from one untyped, `u64::MAX` arguments).

## Findings

Sorted by severity. There is **no finding of wrong behaviour and no contract
error**: on every attack I could construct, the model does what the contract
says. The findings below are coverage, documentation and model-cost issues.

### 1. Delivery into a *destroyed* (not only dying) receive-range space is untested — severity: untested (low)

- Where: `model/src/ipc.rs` `deliver` (the `empty` closure, ~line 380);
  contract "The derivation tree / Removal ends": "a delivery to a receiver
  whose receive range is in a **dying or destroyed** space drops the
  capabilities (the words are still delivered)".
- What is wrong: only the *dying* case has tests
  (`delivery_into_a_dying_capability_space_drops_the_capabilities`,
  `capabilities_of_a_caller_whose_space_began_to_die_are_dropped_at_delivery`,
  `message_without_capabilities_reaches_a_dying_space_without_the_dropped_flag`
  in `model/tests/calls.rs`). The *destroyed* case — receiver still queued
  while its receive-range space is fully destroyed — has no test.
- How I know: **confirmed by a run** (my probe, scratch copy): server waits
  with range `via(30,5)`; `cap_delete(s(30))` until `Done`; a caller then
  does `call` listing `Transfer::Move(s(22))`; the server is woken with the
  words, `caps() == 0`, `FLAG_CAPS_DROPPED` set, the sender keeps its
  capability, `Model::check()` holds. The model is correct; the behaviour is
  simply not pinned by a regression test. Same for the reply direction
  (caller's own space destroyed while it waits for the reply; the reply
  object lives elsewhere): `send` on the reply returns
  `Sent { flags: FLAG_CAPS_DROPPED }`, the caller is woken with the words and
  badge 0, its caps dropped, `check()` holds.
- Suggest: add a test mirroring the probe above (destroyed range space, both
  directions), so a future change cannot regress it silently.

### 2. The oracle's per-call work is not bounded by the contract's constants (queue scans) — severity: minor (model-only cost)

- Where: `model/src/ipc.rs:457,462,465` (`unlink` does `queue.retain` /
  `waiters.retain` over the *whole* wait queue), `model/src/caps.rs:557`
  (`remove_cap` scans the parent's whole `children` vec), `model/src/caps.rs:476`
  (`Sweep.held` collects all capabilities of a dying space, O(space), once).
- What is wrong: the size of an endpoint/notify wait queue is user-controlled
  (bounded only by supplied memory — I probed 1000 waiting threads; the 64 MB
  boot untyped allows ~65 000). Which rule bounds it? None fixes a constant:
  rule 4 bounds *the kernel's* work, and the contract achieves that by linking
  each waiting thread through its own thread object ("The queue of callers
  needs none: each waiting thread is linked through its own thread object"),
  i.e. O(1) unlink. The model's `VecDeque::retain` makes one call
  O(queue): a removal call that wakes 32 waiters does 32 full queue scans.
- How I know: **confirmed by a run** on the instrumented scratch copy — 1000
  threads waiting on one notify, `cap_delete` took 32 calls (32 wakes per
  call, FIFO, all `gone`), each wake scanning the ~1000-long queue; teardown
  of a 2^20-slot space with 523 264 full slots took 20 456 calls, worst call
  `steps=32, removed=32, slots=31, walk=64` (all within the contract's 32/128
  budgets — the *walk/slot* part is bounded; the queue scan is the unbounded
  part, and it is a representation artifact).
- Suggest: none for correctness; note in the model's docs that its queues are
  vectors, so its own runtime is O(queue) per unlink, and the kernel must keep
  the O(1) linked unlink the contract describes. The oracle cannot be used to
  *measure* the kernel's per-call bound for queue operations.

### 3. Wrong CONTRACT-GAP tag on the sweep start — severity: minor (documentation)

- Where: `model/src/caps.rs:469-471`: "CONTRACT-GAP (The derivation tree): the
  contract does not say where the sweep starts … the sweep starts at slot 1."
- What is wrong: the contract **does** say it — "The sweep of a space starts
  at slot 1" (`kernel-interface.md`, The derivation tree). The model's behaviour
  (sweep starts at slot 1, slot 0 never examined, invariant 27) matches the
  contract; only the gap tag is wrong, and it hides a decided point.
- How I know: **read in code and contract**; test
  `removal_examines_at_most_128_slots_of_dying_spaces_per_call` pins the
  behaviour.
- Suggest: drop the CONTRACT-GAP tag, cite the contract sentence instead.

### 4. Task marks and task id are hard-coded, not tagged CONTRACT-GAP at the decision — severity: minor

- Where: `model/src/ipc.rs:54-59` `received()`: every delivery carries
  `marks: Marks::NONE, task: 0`. Contract (Messages): "The receiver gets … the
  **marks** of the sender's task … the **task identifier**, for the log … the
  sender cannot forge any of it."
- What is wrong: a behaviour decided by the model alone (tasks are not
  modelled — said in the `lib.rs` module doc, but the decision point carries no
  CONTRACT-GAP tag). If the kernel is ever tested against this oracle on
  stamping, the oracle always answers `NONE`/`0`.
- How I know: **read in code**; spot-probed (`receiver_gets_the_badge…` asserts
  `marks == Marks::NONE, task == 0`).
- Suggest: add a `CONTRACT-GAP` comment at `received()` naming the Messages
  section.

### 5. One removal call can wake up to ~64 threads, not 32 — severity: minor (observation, within the contract)

- Where: `model/src/caps.rs` `remove` / `next_removed` (the reply-object wake
  inside `next_removed` is not counted, per contract).
- What: each of the ≤32 steps of one call re-walks from the start and may mark
  a *different* reply object dying, each triggering one uncounted wake; so a
  call can do 32 counted removals/wakes **plus** up to 32 uncounted reply
  wakes. The contract sanctions the uncounted wake *per step* ("This wake is
  not counted in the 32 of a step: a walk passes through at most one reply
  object"), so this is not a violation — I verified a single walk cannot pass
  two reply roots (below a reply root there are only copies, which are roots of
  nothing) — but the top-level sentence "at most 32 capabilities are removed or
  threads woken" per call reads stricter than the implementation.
- How I know: **read in code**; the bound stays a constant, so rule 4 holds.
- Suggest: optionally reword the contract sentence to "per step".

### 6. The accepted revoke-starvation limit is untested in its multi-thread form — severity: untested (accepted by the contract)

- Where: contract "The derivation tree": "while `cap_revoke` runs, threads that
  hold capabilities under it can still derive new ones. Each call removes 32
  capabilities against at most four new capabilities per competing call … a
  supervisor that wants a certain end suspends those threads first."
- What: a single thread deriving during a revoke is tested
  (`capability_on_the_path_of_a_removal_keeps_working_until_it_is_removed`);
  the starvation variant — more than 8 cooperating attacker threads each
  deriving one capability between revoke calls, so the revoke never ends — is
  not exercised. The contract declares the limit accepted.
- How I know: **read in code and contract**; invariant 21 ("removal ends") is
  checked after every call in both suites and held in all runs, so the *state*
  is always well formed; only the live-attacker interleaving is untested.
- Suggest: none required (contract-accepted); optionally a test documenting the
  accepted limit.

## What I checked and found correct

- **Test suite**: 211/211 pass via the instructed nix command.
- **Removal walk bound (rule 4)**: adversarial construction (a space at every
  depth 2..64, each holding an untyped copy at its own depth, plus a depth-1
  ordinary capability with a 64-deep copy chain inside the deepest space),
  then `cap_delete` of the outer space and `cap_revoke` of the boot untyped:
  `longest_walk = 189 ≤ 192` (`LONGEST_WALK`, `model/src/lib.rs:353`), 64 calls
  each, `check()` clean — **confirmed by a run**. The bound holds because
  `fits` is enforced at *every* placement (`cap_move`, `cap_derive`,
  `untyped_retype`, IPC delivery), which is what makes the contract's
  128-restricted + 64-ordinary argument true; invariant 24 checks it after
  every call in both suites.
- **Per-call bounds**: instrumented scratch copy — worst call measured
  `steps=32`, slot budget ≤ 128, removed ≤ 32, wakes ≤ 32 (87 waiters on one
  notify drained in 3 calls; 1000 waiters in 32 calls, all `gone`, FIFO).
- **Watermark / object reuse (the watermark attack)**: destroy-last-object
  resets the watermark (invariants 18/19 after every call); the new object gets
  a **new `ObjId`**, every capability of the old one is `gone` (dead slot), the
  deleted root's slot is empty — no use-after-free is reachable, `CapId`/`ObjId`
  are never reused. Deleting a *copy* does not free memory; deleting the root
  wherever it was moved does; deleting an untyped removes its objects first.
  **Confirmed by runs** (probe 3).
- **Rights that grow**: `cap_derive` subset enforced (invariant 3 + the Kani
  proof `derive_never_adds_a_right` in `abi`); IPC `derive` uses the same
  `Rights::derive`; `untyped_retype` grants all rights except `exec`
  propagation, never `exec` on device memory (invariants 3/25, tested).
- **Badges**: only on endpoint/notify, kept on derivation, same accepted /
  different `denied`; `u64::MAX` badge → notify word `u64::MAX` (probed);
  reply carries badge 0; receiver sees the badge of the capability the sender
  used (probed).
- **`via` addresses**: one level only, `read` to read a slot through a cspace
  capability, `write` to change one — all tested; raw `u64::MAX` / `via =
  u32::MAX` addresses give fixed errors, no panic (probed).
- **Confused deputy (check at call vs delivery)**: listed slots are re-resolved
  and re-checked at delivery; a slot whose content was replaced between call
  and delivery moves the *new* occupant — exactly what the contract says
  ("against what the listed slots hold at that moment"); a failing check drops
  all-or-nothing with `caps_dropped`, words still delivered, sender keeps its
  caps (probed both). Duplicate listing and derive-depth checked per slot.
- **Dying / destroyed spaces**: a thread in a dying space gets `gone` from
  every call except `cap_delete` on its own slots; a destroyed space, from
  every call including `cap_delete` (tested). Deliveries into dying **and**
  destroyed range spaces drop caps, words delivered (probed). Marking a reply
  object dying wakes the attached receiver / armed caller, uncounted in the 32
  (tested). A waiting thread is not disturbed by revocation of the capability
  it used; it is woken `gone` only when the object it waits on is destroyed
  (tested + probed).
- **Denial of service**: `send` never queues (`would_wait`); queues are FIFO
  and homogeneous (invariant 12); one thread woken per `signal`; exhausting
  another party's untyped gives `no_memory`, its slots `no_slot`/`invalid` —
  all fixed errors, probed at the type limits (sizes `u64::MAX`, `1<<63`,
  `2^32`, `2^20+128`; ranges `(u32::MAX,4)`, `(0,1)`, `(128,1)`, `(127,2)`,
  `(126,3)`, `(40,5)`; 65 words; 5 caps; sender-set flags `1`, `2`, `1<<21`,
  `1<<22`, `u32::MAX`) — no panic, `check()` clean after each.
- **Order of checks**: extensively tested in `model/tests/calls.rs` (last
  section): header right after the acting capability, capability arguments in
  table order, plain arguments before state, `no_slot` before `no_memory`,
  depth checks last, destination before plain arguments. I found no
  divergence on re-reading.
- **IPC semantics**: `call`/`recv`/`reply_recv`/`send` states, reply object
  idle/attached/armed, caller disappears → reply idle, server thread
  destroyed → caller not woken, `reply_recv` not told of its reply's dropped
  caps, `caps_dropped` in the reply header combining request and reply drops,
  notifications before callers, `notify_bind` exclusivity — all tested and
  spot-probed.
- **Working tree**: `git status` clean; all probes and the instrumented copy
  live in `/tmp/dodos-probes`, outside the repository.
