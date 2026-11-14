# Review of the executable reference model (branch `model`), 2026-11-14, Mistral

Reviewer: Mistral Vibe, as the review sub-agent. Review only: nothing in
`dodos-kernel` was changed, committed or pushed; scratch probes lived in
`/tmp/attack` (a crate outside the repository, path-depending on
`dodos-model`), and `git status` in `dodos-kernel` is clean at the end.

Read completely: `Docs/architecture/kernel-interface.md`,
`dodos-kernel/AGENTS.md`, `.agents/skills/dodos-rust/SKILL.md`,
`abi/src/lib.rs`, and all of `model/` (`src/lib.rs`, `src/caps.rs`,
`src/ipc.rs`, `src/check.rs`, `src/check/tests.rs`, `tests/calls.rs`,
`tests/property.rs`).

Ran: `nix develop -c cargo test -p dodos-model` — 159 unit tests + 4 property
tests (24 seeds x 5000 steps) pass. Wrote 7 scratch attack probes
(`/tmp/attack/src/main.rs`) against the model to confirm or refute
suspicions; the outcomes are cited below.

Severity scale used below: **wrong behaviour** (the model contradicts the
contract, or an attack succeeds), **undefined** (the contract does not fix
the behaviour), **untested** (a contract rule no test pins), **contract
error** (the contract contradicts itself or a number), **minor**.

Headline: I found **no wrong-behaviour finding and no working attack** on the
capability system. The creation-number rule, the depth limit, the
dying/removal protocol and the IPC transfer re-checks all held under both the
test suite and my probes. The findings below are undefined behaviours,
untested rules and small contract errors, sorted by severity.

---

## Findings

### 1. Rebinding a suspended, waiting thread keeps its old wait and receive window — deliveries then land in a space the thread no longer uses (undefined, low)

- Where: `model/src/lib.rs:565-580` (`thread_configure` sets `target.cspace`
  without touching `target.wait`), `model/src/ipc.rs:291-312` (`receive`
  stores the resolved `Window` in `Wait::Recv`), `model/src/ipc.rs:356-408`
  (`deliver` places capabilities into the stored window).
- Contract: "Suspension and waiting are independent (design choice).
  Suspending a thread that waits cancels nothing: the thread keeps its place
  in its queue, a message can still be delivered to it" (kernel-interface.md:135)
  and "`thread_configure` … The thread must be suspended (`busy` otherwise)"
  (kernel-interface.md:130). The contract never says what happens to the
  wait and the receive range when a *waiting* thread is reconfigured to
  another cspace. This is an **unmarked CONTRACT-GAP**.
- What is wrong: the model allows suspend -> `thread_configure` to a new
  cspace -> resume on a thread that is queued in `Wait::Recv`/`Wait::Call`.
  A later delivery places the transferred capabilities into the *old* space's
  window (fixed at `recv` time), while the thread now runs in the new space
  and cannot see them through its own slots.
- How I know: **confirmed by a scratch probe** (`probe_rebind_waiting_thread`
  in `/tmp/attack/src/main.rs`): thread T waiting in space S1, rebound to S2;
  a `send` with `Transfer::Move(NT)` delivered the notify capability into
  S1 slot 9 (`caps=1`), T was woken, and T's own inspect of S2 slot 9 returned
  `Invalid`. `Model::check()` stayed `Ok(())`, so no invariant catches it.
- Suggest: decide in the contract. Either forbid `thread_configure` on a
  thread that waits (make it `busy`), or say the receive range is
  re-resolved in the new space, or say the wait is dropped with `gone`.
  Any of the three is implementable in the model in a few lines; today the
  model silently picks "old window wins".

### 2. Delivery to a receiver whose receive-range space is *destroyed* (not just dying) — words delivered, capabilities dropped (undefined, low)

- Where: `model/src/ipc.rs:359-367` (`empty` closure: `self.cspaces.get(&window.cspace)`
  returns `None` for a destroyed space, so every slot check fails and the
  capabilities are dropped; the words are still delivered with
  `FLAG_CAPS_DROPPED`).
- Contract: the marked CONTRACT-GAP at `ipc.rs:359-363` covers a *dying*
  space ("a delivery to a receiver whose receive range is in a dying space
  drops the capabilities", kernel-interface.md:93). The *destroyed* case is
  the same code path but is not mentioned anywhere.
- How I know: **confirmed by scratch probes** `probe_deliver_into_destroyed_space`
  and `probe_caller_space_destroyed`: after the receiver's/caller's cspace is
  destroyed (thread object alive because its root cap is elsewhere), a `call`
  is still served to the queued receiver, the words arrive (`caps=0 flags=1`),
  and the woken thread gets `gone` on its next call. No panic, all
  invariants hold.
- Suggest: extend the CONTRACT-GAP comment (and the contract) to destroyed
  spaces, or state that a queued receiver whose space is destroyed is woken
  with `gone` instead. The current behaviour is coherent (the range slots no
  longer exist, so nothing can be placed there), it is just unfixed.

### 3. "At most one new capability per competing call" — IPC can add four (contract error, minor)

- Where: contract kernel-interface.md:94: "Each call removes 32 capabilities
  against at most one new capability per competing call". The model: a
  message lists up to `MAX_CAPS` = 4 transfers (`abi/src/lib.rs:17`), each
  `Derive` creates one new capability (`model/src/ipc.rs:261-285`,
  `deliver` at `ipc.rs:391-397`), so one `call`/`send` can add 4
  capabilities under a subtree that is being revoked.
- How I know: **read in the code**; `MAX_CAPS` is 4 and `listed` loops over
  all transfers. The conclusion of the sentence still holds (32 removed per
  call against at most 4 added), so this is a wording error, not a hole.
- Suggest: change "one" to "four" (or "`MAX_CAPS`").

### 4. `send` "never queues … a queue would need kernel memory" vs the FIFO queue of `call` — where the queue lives is unspecified (contract error / open point, minor)

- Where: contract kernel-interface.md:151 ("`send` never queues (design
  choice). A queue would need kernel memory.") vs kernel-interface.md:145
  ("the caller joins the queue of the endpoint, first in, first out"). In the
  model the queue is a `VecDeque` in the endpoint state
  (`model/src/lib.rs:246-249`, `Endpoint.queue`). Rule 3 of the contract ("No
  kernel heap") makes an unbounded in-endpoint queue impossible in the real
  kernel; the contract does not say the queued callers are linked through the
  caller's own thread object.
- How I know: **read in the contract**; the model itself is fine (it is a
  model, memory is not its concern).
- Suggest: one sentence in the contract saying the queue nodes are the caller
  threads themselves (linked list through thread objects), which also bounds
  the queue by the number of threads.

### 5. Rules the model cannot check: memory clearing, marks and task stamping (untested, minor)

- Where: contract kernel-interface.md:123 ("The kernel clears the memory of
  kernel objects. It does not clear frames") and kernel-interface.md:172-176
  (the receiver gets the badge, the marks and the task identifier "the sender
  cannot forge"). `model/src/lib.rs:10-13` declares "Not modelled: … the
  contents of memory, tasks and marks"; `ipc.rs:44-49` hard-codes
  `marks: Marks::NONE, task: 0`.
- What is wrong: nothing in the model — but it means the oracle will never
  catch a kernel that forgets to clear a kernel object, or stamps forgeable
  marks. The frame rule ("does not clear frames") is a deliberate contract
  choice, so the risk is only on the "clears kernel objects" half.
- Suggest: state in the contract (or in the oracle harness plan) that
  clearing is checked by inspection/Kani on the kernel, not by the model;
  otherwise add a "memory contents" abstraction to the model later.

### 6. The uncounted reply wakes ("at most 64 per step") are not counted by any test (untested, minor)

- Where: contract kernel-interface.md:93: "These wakes are not counted in the
  32 of a step: a step marks at most one object per level of the tree, so at
  most 64." Model: `next_removed` (`model/src/caps.rs:414-438`) wakes the
  attached receiver / armed caller of every reply root on the walked path
  without decrementing the step counter in `remove` (`caps.rs:371-412`).
- How I know: **read in the code**; the per-step bound follows from the path
  visiting one capability per level, but no test counts wakes per step. The
  tests check the counted wakes (`waking_a_thread_counts_as_one_step_of_removal`,
  calls.rs) and invariant 22, not the 64.
- Suggest: a test that arms/waits on 64 reply objects under one removal and
  asserts one `cap_delete` returns `again` after exactly the counted work,
  or simply accept it as covered by invariant 21/22 plus the property run.

### 7. `cap_revoke` on the root of a cspace does not sweep the space's contents — only `cap_delete` does (untested / contract ambiguity, minor)

- Where: model `model/src/caps.rs:371-412` (`remove` with
  `Removal::Descendants` starts at `children.last()`, so the target root
  itself is never on the walked path and `swept` (`caps.rs:440-446`) never
  runs for it) vs contract kernel-interface.md:87 ("removing a capability
  removes first what was derived from it and, for the root of a space, what
  the space holds") and :95 ("Destroying a `cspace` first removes every
  capability in it").
- What is wrong: nothing observable wrong — revoke "keeps the capability"
  (kernel-interface.md:82), so keeping the space's contents is the
  consistent reading. But the contract sentence at :87 uses "removing",
  which a reader could apply to `cap_revoke` too, and **no test pins
  revoke-on-a-space-root** (the tests use `cap_delete` for the sweep:
  `destroying_a_cspace_removes_its_capabilities_in_index_order`).
- Suggest: one contract clause ("`cap_revoke` on the root of a space removes
  only its derivation descendants, not what the space holds") and one test.

### 8. Order of checks among several capability arguments is untested pairwise (untested, minor)

- Where: contract "Order of checks" (kernel-interface.md:99-105): step 2 is
  "the other capability arguments, in the order of the table below". The
  tests check each argument individually (`thread_configure_needs_manage_on_the_thread_the_cspace_and_the_aspace`,
  `recv_needs_recv_on_the_endpoint_and_on_the_reply_object`, …) and step 1
  before step 2 (`first_capability_is_checked_before_the_others`), but no
  test makes two capability arguments fail at once in the table order (e.g.
  fault endpoint without `send` *and* aspace without `manage` in
  `thread_configure`: which `denied` wins is unpinned).
- How I know: **read of `tests/calls.rs`**; the model does implement the
  table order (`lib.rs:565-580` checks thread, cspace, aspace, fault in
  order).
- Suggest: one test per call with two failing capability arguments.

### 9. `cspace_grow` accepts any capability for the same untyped object, not the literal capability the space was created from (minor, reading of the contract)

- Where: contract kernel-interface.md:117: "`write` on the untyped, which
  must be the one the cspace was created from (`invalid`)". Model
  `model/src/caps.rs:196-199`: compares `self.objects[&space].from !=
  Some(untyped)` — the untyped *object*, so any capability for it works;
  the test `cspace_grow_takes_only_the_untyped_the_cspace_was_created_from`
  asserts this deliberately ("Any capability for that untyped will do"),
  and my probe 5 confirmed: grow from a derived copy of the right untyped
  succeeds, from a child untyped fails with `invalid`.
- How I know: **confirmed by probe**; the model and the test agree with each
  other, the contract sentence is ambiguous between "the untyped" (object)
  and "the capability".
- Suggest: reword the contract to "the untyped it was created from (any
  capability for that untyped)".

---

## What I checked and found correct

- **The creation-number rule** ("A capability space holds authority only over
  what is younger than itself", kernel-interface.md:86): `movable`
  (`caps.rs:223-233`) binds exactly untyped capabilities and cspace *root*
  capabilities, compares one creation number, and is applied both at
  `cap_move` and at IPC delivery (`ipc.rs:383-385`). Probes: the start-up
  untyped root is refused into a younger space by `cap_move` (`invalid`)
  and by IPC (dropped, `caps_dropped` set, word still delivered); a *late
  copy* of that untyped root is accepted into the space created from it and
  the space can then grow from it (probe 6/7: `Ok(Slots(256))`), exactly the
  contract's documented consequence (kernel-interface.md:88); cross-held
  *copies* of two cspaces' roots do not make removal loop (probe 4:
  `cap_delete` finished, invariant 21 held, `check()` Ok). The property test
  counts accepted and refused moves of both kinds, both ways (≥50 each).
- **No cycles / "removal ends"**: invariant 21 (`check.rs:118-142`) is a
  real topological cycle check over parent + holder relations, is asserted
  after every one of 24×5000 random steps, and has its own spoil test
  (`capability_held_in_a_capability_space_that_descends_from_it_is_reported`).
- **Depth limit 64**: `shallow` (`caps.rs:210-221`) counts the parent chain;
  tested for `cap_derive`, `untyped_retype` and IPC derive, at call time and
  again at delivery (`listed`, `ipc.rs:261-285`).
- **Rights can only shrink** through `cap_derive` (`Rights::derive`, abi), the
  badge rules (only endpoint/notify, kept badge, same badge accepted, other
  denied) are all tested; `untyped_retype` gives all rights except `exec`
  unless the untyped capability has it, and never `exec` on device memory
  (device flag inherited by child untypeds, `caps.rs:272-279`) — all tested.
- **Slots**: slot 0 never used, empty→`invalid`, dead→`gone`, dead not free,
  `cap_delete` on dead makes it empty; `via` is one level, needs `read` to
  read a slot and `write` to change one — every branch tested
  (`via_reaches_a_slot_of_another_capability_space`,
  `reading_a_slot_through_a_cspace_capability_needs_read`, …).
- **Dying/removal protocol**: a `cap_delete` target is dying from the first
  step; an object is dying when a removal path reaches its root even if the
  step only removes a copy (while a non-root copy on the path keeps working);
  a dying own space gives `gone` from every call except `cap_delete`;
  delivery into a dying space drops the caps; the reply attached/armed wake
  happens exactly when the reply root is marked; destroying an object wakes
  its waiters with `gone` in bounded steps; the caller is not woken when
  only the server thread dies; a waiting thread is not disturbed by
  revocation of the cap it used. Each of these has a dedicated test in
  `tests/calls.rs`, and my probes 2-3 exercised the destroyed-space edge
  without breaking any invariant.
- **Bounded removal**: 32 steps per call, most-recent-child-first order,
  cspace contents swept in index order with the own root last, counted
  wakes — all tested (`cap_revoke_removes_32_capabilities_then_returns_again`,
  `destroying_a_cspace_removes_its_capabilities_in_index_order`,
  `waking_a_thread_counts_as_one_step_of_removal`).
- **IPC transfer**: re-checked at delivery against what the sender's listed
  slots hold *then* (the contract explicitly accepts that a shared cspace
  can swap the content, kernel-interface.md:161 — tested by
  `delivery_transfers_what_the_listed_slot_holds_then`), all-or-nothing,
  `caps_dropped` + count 0 on the receiver side, flag returned at once by
  `send` and set in the reply header for `call`, slot listed twice
  `invalid`, empty range refuses and its address is not looked at, range
  ≤ 4, message ≤ 64 words / 4 caps, derived transfers keep the badge and
  stay children of the sender's capability (revocable by the sender —
  tested). No confused deputy found: every action is taken on the same
  resolved object that was checked, and the delivery-time checks run against
  the state at delivery.
- **IPC state machine**: `call`/`recv`/`reply_recv`/`send` rights, idle/
  attached/armed reply rules, `busy` cases, dropped reply without error when
  not armed, reply carries badge 0, notification-before-caller order in
  `recv`/`reply_recv`, bound-notify signal waking one thread (notify waiter
  preferred), `notify_bind` busy/0-endpoint rules, one thread woken per
  signal with the word cleared — each has tests.
- **Threads**: configure rights and kinds, `busy` unless suspended,
  resume-`busy` when unbound, suspend/resume idempotent, suspension does not
  cancel a wait and the message is still delivered (tested).
- **Order of checks**: slot/kind/rights, then capability arguments, then
  plain arguments, then state (`no_slot` before `no_memory`) — tested
  (`no_slot_is_reported_before_no_memory`, …).
- **Untyped memory**: watermark-only-up with the contract's alignments
  (child untyped on its size, frame on its page size, others on min(size,
  4 KB)), directory rounded to a power of two, `no_memory`, watermark back
  to zero only when the last live object/segment is released, device memory
  only to frame or child untyped — all tested.
- **check.rs**: invariants 1-23 each have a spoil test in `check/tests.rs`
  that breaks exactly that invariant and asserts the reported name; the
  property suite re-checks all of them after every random call.
- **Badge as ambient authority**: a holder of a badged endpoint/notify
  capability can mint further capabilities with the *same* badge (contract:
  "asking for the same one is accepted"). That is inherent to the badge
  design (the badge identifies the capability, not the thread), the contract
  states it, and the reply path always carries badge 0 — noted, not a
  finding.

## Method notes

- Test run: `nix develop -c cargo test -p dodos-model` → 159 + 4 passed, 0
  failed (log at `/tmp/model-test.log`).
- Attack probes: `/tmp/attack/` (outside the repo), 7 scenarios: rebind of a
  waiting thread; delivery into a destroyed receive-range space; caller with
  destroyed space; cross-held cspace copies + root delete; grow paths;
  self-grow by cap_move and by IPC. Outcomes cited above; all ended with
  `Model::check() == Ok(())`.
- `git status` in `/Users/btw/Documents/repos/dodos-kernel`: clean, on branch
  `model`, nothing added, changed or deleted.
