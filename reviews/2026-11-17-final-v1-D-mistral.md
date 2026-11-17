# Review of lot D (mistral) — model/src/check.rs, model/src/scenarios/checker.rs, model/src/check/{cores,debug,machine,memory,node,sched,table,tasks}.rs, model/src/scenarios/{explore,mod}.rs, model/src/check/tests.rs

Repository: `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`. I changed nothing there; the two reproductions below were run in a copy at `/private/tmp/dodos-pr3-D-mistral`.

## Findings

### 1. Invariant 40 rejects a fault of kind 9 that waits — stops the merge

`model/src/check.rs:790-798`:

```rust
let fault = match &thread.wait {
    Wait::Call { parcel, .. } => {
        let kind = (1..=8).contains(&parcel.label);
        kind && parcel.words.len() == FAULT_WORDS && parcel.caps.is_empty()
    }
    Wait::Reply(_) => true,
    _ => false,
};
ensure(!thread.faulting || fault, "40: fault wait")?;
```

The invariant's own doc (top of `check.rs`) says "a fault message that waits has a label of a fault kind". `dodos_abi::FaultKind` has nine kinds, labels 1 to 9 (`abi/src/lib.rs:755-767`, `HardwareBreakpoint = 9`, and `FaultKind::from_raw` accepts 9). The model itself raises and delivers a kind-9 fault as a waiting call: `Model::fault` accepts `FaultKind::HardwareBreakpoint` (`model/src/faults.rs:24`), and `raise` (`faults.rs:55-107`) enters the thread on its fault endpoint as a caller with `parcel.label = 9` and `faulting = true`. So the range `(1..=8)` excludes exactly one legal fault kind, and the check fails on a state the model produces. Related: the census at `check.rs:128-136` allocates `fault_kinds: [usize; 9]` and clamps with `.min(8)`, which only makes sense if label 9 can wait.

How I know: in the copy I appended to `model/tests/faults.rs` a test that configures a thread with fault endpoint `EP`, enables a breakpoint (`DR7 = 1`), resumes it, and calls `k.m.fault(thread, FaultKind::HardwareBreakpoint, ...)` with no receiver waiting, so the faulted thread waits as a caller. Then:

```
/nix/var/nix/profiles/default/bin/nix develop -c cargo test -p dodos-model --test faults zz_repro
test zz_repro_kind_9_fault_waiting_on_its_endpoint ... FAILED
check after a delivered kind-9 fault: Err("40: fault wait")
assertion `left == right` failed: left: Err("40: fault wait"), right: Ok(())
```

`census().faulting == 1` held, so the state is exactly "a thread waiting on a fault of kind 9", and `Model::check` returns `Err("40: fault wait")`. The fix is `(1..=9)` or `FaultKind::from_raw(parcel.label).is_some()`. No existing test trips this: `check/tests.rs` `fault_message_that_waits_is_accepted` uses label 8, and the random walk in `model/tests/property.rs:2113-2119` picks only kinds 1 to 6 — which is why `verify` is green today. Because the whole check runs after every step of every scenario, any future test or exploration seed that reaches a pending hardware-breakpoint fault fails the run; the invariant as coded contradicts `abi/`, so I would stop the merge on it.

### 2. The checker test for G6 passes without the G6 check ever firing — should be fixed

`model/src/scenarios/checker.rs:541-547`:

```rust
let report = m.sys.check().expect_err("spoiled");
assert!(
    report.ends_with("G6: a grant freed while its holder translates to it")
        || report.contains("58"),
    "{report}"
);
let _ = Member::new;
```

The test is named `a_grant_freed_while_its_holder_translates_to_it_is_reported`, and this file exists precisely so that every check gets a state that makes it fail. But the second disjunct lets the test pass on any report containing "58". As written it always takes that branch: `System::check` runs each running node's `Model::check` first, and the spoiled use entry (`leaves: 1` with no translation under it) is caught by the node's own invariant 58 before `check_grants` in `check/machine.rs` ever runs. How I know: in the copy I removed the `|| report.contains("58")` escape and ran

```
/nix/var/nix/profiles/default/bin/nix develop -c cargo test -p dodos-model --lib scenarios::checker::a_grant_freed
---- scenarios::checker::a_grant_freed_while_its_holder_translates_to_it_is_reported stdout ----
thread '...' panicked at model/src/scenarios/checker.rs:542:5:
node 1: 58: leaves of a use entry
test result: FAILED. 0 passed; 1 failed
```

So the shipped test always passes via "node 1: 58: leaves of a use entry", and the G6 branch in `check/machine.rs` (`"G6: a grant freed while its holder translates to it"`) has no failing test in this file — a check that cannot fail there would go unnoticed. The spoil should make the node's own 58 pass (e.g. `leaves: 0`, or a real granted translation) so that only G6 can fire, and the assertion should be `ends_with` alone, as its neighbours are. The trailing `let _ = Member::new;` is a dead statement whose only purpose is to use the import.

### 3. A check that cannot fail: `ensure(true, ...)` — question

`model/src/check/tasks.rs:55`:

```rust
ensure(true, "50: running thread of a revoked task")
```

`ensure(true, ...)` always returns `Ok`; this line can never fail and does nothing. The real invariant 50 is the loop just above it (lines 45-54), which does test the running thread of a revoked task (and `check/tests.rs` has `running_thread_of_a_revoked_task_is_reported` for it). Either the line is a leftover that should be deleted, or it was meant to guard something the loop does not — as written it is dead code carrying the invariant's name, which misleads a reader into thinking 50 is checked twice.

## Checked and not findings

- `check/table.rs` computes the chunks of a `Block::Run` with `(base + bytes) >> shift` (lines ~247, ~276) while the leaf loops use `div_ceil`; this is safe because `memory_take` with kind 0 requires `size` in `chunk_shift..=chunk_shift + entries_shift` and `place` a multiple of `1 << size` (`model/src/blocks.rs:41-46`), so base and bytes are chunk multiples and the two agree.
- `scenarios/checker.rs` `word_with_check` reproduces `CoreWord::checked` exactly (`abi/src/machine.rs:951-961`: mask `0xfff << 4`, `(v.wrapping_mul(CHECK_MUL) >> 52) << 4`), so its hand-made words pass `CoreWord::from_raw` as the tests expect.
- `check.rs` `check_identifiers` would misfire on a zero attach word, but zeroed attach words are removed from the map, not stored (`model/src/table.rs:700`, `swap_attach`), so every entry in `table.attach` is a non-zero valid word.
- `check/cores.rs` lets `optional` include large feature bits (e.g. AMX) while `baseline` excludes them; that is intended — large features are "always optional" (`abi/src/features.rs:14-16`).
- `check/machine.rs` `check_cores` calls `table.member(slot)` where `slot` is the 16-bit slot field of a core word, which would panic if `slot >= members.len()`; not reachable from an input, because core words are written only by the model with valid node slots and free words are rejected by the earlier check.
- `check/debug.rs` `ring_holds` computes `next - 2`, which would underflow for `next == 0`; `next` starts at 1 and only grows, so not reachable.

## Files read whole (the lot, in the prescribed order)

- `model/src/check.rs` (934 lines)
- `model/src/scenarios/checker.rs` (589)
- `model/src/check/cores.rs` (71)
- `model/src/check/debug.rs` (177)
- `model/src/scenarios/explore.rs` (752)
- `model/src/check/machine.rs` (419)
- `model/src/check/memory.rs` (168)
- `model/src/scenarios/mod.rs` (345)
- `model/src/check/node.rs` (383)
- `model/src/check/sched.rs` (256)
- `model/src/check/table.rs` (519)
- `model/src/check/tasks.rs` (96)
- `model/src/check/tests.rs` (2825)

Also read whole: `AGENTS.md`, `model/README.md`, `.claude/skills/dodos-rust/SKILL.md`, `.claude/skills/rust-1-100/SKILL.md`.

## Read in part (only as needed to judge the lot)

`abi/src/lib.rs` (the `FaultKind` enum and `from_raw` only), `abi/src/machine.rs` (`CoreWord`, `AttachWord` only), `abi/src/features.rs` and `abi/src/x86_64.rs` (`FeatureList`, `FEATURES`), `model/src/boot.rs` (`features`), `model/src/faults.rs` (the `fault`/`raise` path), `model/src/blocks.rs` (`memory_take`, `run`), `model/src/table.rs` (`member`, `swap_attach`, the attach map), `model/src/lib.rs` (`Thread::bounded`), and short excerpts of `model/tests/faults.rs`, `model/tests/debug.rs`, `model/tests/property.rs`. Everything else in the 79-file diff (the rest of `model/src/`, all of `abi/`, all other test and scenario files) I did not read.
