# Review of the one-core executable model (`dodos-kernel/model`, branch `model`)

Reviewer: Mistral Large 4 (review sub-agent). Date: 2026-11-14.
Scope: the model against `Docs/architecture/kernel-interface.md` ("Call reference, one core", Rules, Objects, System calls, Rights, Errors) and `abi/src/lib.rs`, with a security angle on the capability system. Review only: nothing in the repositories was changed; scratch probes live in `/tmp/model-probes` (outside the repo). The test suite was run: `cargo test -p dodos-model` — 183 unit/integration tests + 4 property tests, all pass.

I did not read the earlier reviews in this folder.

## Summary

I found **no wrong behaviour and no contract error that I could confirm**. The capability-security core — rights monotonicity, the depth/placement rule at every placement point, the 64-level limit, the dying/destroyed semantics, the all-or-nothing transfer re-checked at delivery, and the claimed bound of 192 on the removal walk — is implemented as the contract says, and my directed attack probes could not break any of them. The findings below are minor: one untested bound, one missing state invariant, one oracle-versus-kernel performance gap, two undefined corners, and three untested contract rules.

## Findings, by severity

### 1. The 192-capability bound on the removal walk is only fuzz-tested, never directed-tested — severity: untested

- **Where**: `model/src/caps.rs:439` (`next_removed` records `longest_walk`), `model/src/check.rs:159` (invariant 24: `longest_walk <= 3 * TREE_DEPTH`), contract "The derivation tree" ("the walk that finds the next capability to remove is at most 192 capabilities long").
- **What**: the only tests that touch invariant 24 are the random property runs (24 seeds x 5000 steps) and two unit tests in `check/tests.rs` that set/measure the field on a tiny state (walk = 2). No test constructs a long walk on purpose.
- **How I know**: I built a directed maximal attack in `/tmp/model-probes` (probe 1): 48 nested capability spaces (roots at depths 2..49), each space holding an untyped copy at the same depth whose last child is the next space's root, plus an ordinary capability in the innermost space with a derivation chain down to depth 64 — the shape that maximizes the walk (two structural capabilities per depth level, then a 64-deep derivation tail, which my analysis bounds at ~191 <= 192). Deleting the outermost root removed everything in 7 calls, `check()` stayed `Ok(())`, and the depth rule refused every illegal placement I tried (space root into a deeper-descended space, shallow untyped into a deeper space, boot untyped root into a child space — all `Invalid` as required). So the bound holds under a directed attack, but nothing in the test suite would notice a regression that allowed, say, 193.
- **Suggest**: add a directed test that builds the maximal chain (as in `spaces_nest_no_deeper_than_the_tree`, but with the innermost space holding an ordinary cap and a depth-64 chain) and asserts that `cap_delete` terminates and `check()` passes throughout.

### 2. `swept()` rescans the dying space from index 0 on every removal step — the model does not have the saved sweep index the contract gives the kernel — severity: minor (oracle fidelity, not behaviour)

- **Where**: `model/src/caps.rs` `Model::swept` (`space.slots.iter().find_map(...)` from index 0); contract "The derivation tree": "the dying space keeps the index where the sweep stands, so that a step does not scan it again from the start".
- **What**: in the model, one `cap_delete`/`cap_revoke` call does up to 32 steps, each rescanning the slot vector from index 0, so one call costs O(32 x slots). The contract's rule 4 ("every call is bounded") is met by the kernel only because the kernel keeps the index; the oracle does not, so the oracle's per-call work grows with the number of slots of the space being destroyed.
- **How I know**: probe 2 in `/tmp/model-probes` — destroying a cspace of 2000 segments (256,000 slots) holding 2000 endpoints: 124 calls, ~2.1 s at high slot indexes vs ~0.83 s at low indexes (debug build). The sequence of `again`/`done` results is identical either way, so no observable behaviour differs; this is cost only.
- **Suggest**: either accept it (the model is an oracle, the kernel keeps the index as the contract says), or keep a sweep cursor in the model's dying spaces so the oracle's cost matches the contract's claim.

### 3. `check.rs` does not verify the depth-placement rule as a state invariant — severity: minor (invariant weaker than the file claims)

- **Where**: `model/src/check.rs` (invariants 1-26); the rule itself is only enforced procedurally in `Model::fits` (`model/src/caps.rs`).
- **What**: the contract's central anti-cycle/anti-DoS rule — "a capability space holds only what is deeper than itself" — is checked at every placement (`cap_move`, `cap_derive`, `untyped_retype`, IPC delivery all call `fits`), but `Model::check` never re-verifies it on the state. The invariants cover its consequences (depth <= 64 as invariant 20, acyclicity of the removal order as invariant 21, walk <= 192 as 24), but a non-cyclic violation (e.g. an untyped root at depth 1 held by a space whose root is at depth 5) would not be reported by `check()`.
- **How I know**: read of `check.rs` (no invariant compares the depth of a held untyped/cspace-root capability with the depth of the space's root); the spoil-tests in `check/tests.rs` break the rule only through a cycle (invariant 21).
- **Suggest**: add an invariant: for every full slot, if the held capability is an untyped capability, its depth >= depth of the space's root; if it is the root of another space, strictly greater (unless it is the space's own root).

### 4. `cap_delete` through a `via` that names a dying space returns `gone`, while `cap_delete` on one's own dying space (via = 0) works — severity: undefined (contract ambiguous)

- **Where**: `model/src/caps.rs` `cap_delete` (uses `through(own, slot, Write)`; `full` returns `gone` when the via capability's object is dying) vs `model/src/lib.rs` `space()` (the own-space dying check that `cap_delete` bypasses). Contract: "a thread whose capability space is dying gets `gone` from every call except `cap_delete`" and "every call on it, through any capability, returns `gone`" / "`cap_delete` on a capability whose object is dying works as on any other: it acts on the slot, not on the object".
- **What**: the contract's exception is worded for the thread's own space. The model extends `gone` to via capabilities of a dying space (probe 6: `cap_delete` through a copy of a dying space's root cap -> `Err(Gone)`), while `cap_delete` on a slot of the thread's own dying space succeeds (probe 6: `Ok(Done)`). Both readings are defensible; the contract does not settle the via case.
- **How I know**: probe 6 in `/tmp/model-probes`; code read.
- **Suggest**: one sentence in the contract: whether the `cap_delete` exception applies through a `via` that names a dying space.

### 5. Error code and check-order for `untyped_retype` of kinds outside the one-core model — severity: undefined (unmarked contract gap)

- **Where**: `model/src/caps.rs` `footprint` returns `Err(Unsupported)` for kinds outside the model; the `CONTRACT-GAP` comment covers which kinds are made, but not this. Contract "Order of checks" names only `invalid` for plain arguments; `unsupported` is in the error table without a position.
- **What**: the model returns `unsupported` from `footprint`, i.e. after the destination check but before the device-memory check, `fits`, `no_slot` and `no_memory`. So `untyped_retype(DEV, Timer, ...)` is `unsupported`, not `invalid`, and a bad destination wins over an unsupported kind in some orders. The contract does not define either.
- **How I know**: code read (`untyped_retype` calls `footprint` before the device check and before `vacant`/`take`); test `kinds_outside_the_one_core_model_are_unsupported` only checks the code, not the order.
- **Suggest**: state in the contract that unsupported kinds are refused with `unsupported` as a plain-argument check (or fold them into the marked CONTRACT-GAP).

### 6. Three contract rules have no test — severity: untested

- **Where / what**:
  1. "`thread_resume` ... a thread bound to a dying space can be resumed" — only the destroyed-space case (`busy`) is tested (`thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed`); the dying case is untested.
  2. `cap_move` on a dead slot returns `gone` — only `cap_inspect` on a dead slot is tested.
  3. A suspended thread that waits to receive still gets a notification of the bound `notify` (suspension keeps the queue place) — tested for messages, not for notifications.
- **How I know**: read of `model/tests/calls.rs` (grep for the behaviours); all three follow from code paths that are otherwise exercised (`thread_resume` uses `own()` which only fails for a destroyed space; `full()` returns `gone` for dead slots; `hand_over` does not look at `suspended`).
- **Suggest**: three small tests.

### 7. Contract-internal note: "32 per call" vs the uncounted reply wake — severity: minor (contract clarity, model matches the carve-out)

- **Where**: contract "The derivation tree": "at most 32 capabilities are removed or threads woken per call" vs "This wake is not counted in the 32 of a step: a walk passes through at most one reply object".
- **What**: the model wakes at most one reply-object waiter per walk, uncounted, and up to 32 counted removals/wakes per call — so a single call can wake up to 64 threads in the worst case. The contract's carve-out is per step/walk, so the model is within the contract, but "32 per call" reads stricter than what is specified.
- **How I know**: code read of `remove`/`next_removed` (`model/src/caps.rs`); test `wake_of_the_step_that_marks_a_reply_object_is_not_counted`.
- **Suggest**: reword to "at most 32 counted per call, plus one uncounted reply wake per step".

## What I checked and found correct

- Rights never grow: `cap_derive` subset + `derive` right enforced at call time; IPC `Derive` re-checked at call and again at delivery (probe 3: asking for more rights -> `Denied` at the call, `caps_dropped` at delivery). `exec` only from an `exec` untyped capability, never on device memory (probe 3: all attempts refused, frames from device get `ALL \ EXEC`).
- Badge rules: only on endpoint/notify, kept on derivation, different badge `denied`, IPC-derived caps keep the badge (probe 3 + tests).
- The depth/placement rule (`fits`) is applied at all four placement points (move, derive, retype, IPC delivery) and refused every illegal placement in probe 1; the 64-level limit is enforced for derivations, creations and IPC derives (`listed` checks depth, `fits` re-checks at delivery).
- The removal walk bound of 192: directed maximal construction (probe 1) stayed within it and removal always ended; invariant 21 (acyclicity) and 24 hold after every call in 24 fuzzed seeds.
- Dying/destroyed semantics: an object is `gone` from every call through any capability from the first step that reaches its root; a capability under `cap_delete` is `gone` except for `cap_delete` itself; a dying space refuses every placement by every route (probe 6: move/derive/retype/grow via its caps all `gone`; IPC delivery into a dying or destroyed range drops the capabilities and still delivers the words — probe 4), and a thread in it gets `gone` from everything except `cap_delete`, and from everything once destroyed (probes 4 and 6).
- Transfer of capabilities: all-or-nothing, re-checked at delivery against what the listed slots hold then (probe 7: a slot swapped between call and delivery moves the *new* occupant — exactly what the contract specifies), duplicate slot `invalid`, header limits before listed slots, empty range refuses all, `caps_dropped` flag on both sides where the contract says, `reply_recv` not told of its reply's drop.
- Object lifetime: the object lives exactly as long as its root capability wherever moved; memory returns to the untyped on destruction (probe 5: after revoking the boot untyped's descendants, a full 64 MB child could be retyped again); dead slots are not free but `cap_delete` empties them.
- IPC queues: callers and receivers never mix (invariant 12 holds through fuzzing), FIFO, `send` never queues, notification precedence over callers, one thread woken per `signal`, bound-notify delivery on `notify_bind`, reply attach/armed wake rules with the uncounted wake.
- Order of checks matches the contract's four steps in every call I traced (endpoint, other capability arguments in table order, plain arguments, then state), including the contract's explicit exceptions (header limits before listed slots; subset/badge/depth checks after the destination).
- Watermark/alignment rules of `untyped_retype` (child untyped on its size, frame on page size, others on size or 4 KB, directory rounded to a power of two) and the live-count accounting are tested and consistent.
- `git status` in `dodos-kernel` is clean; all scratch work is in `/tmp/model-probes`.
