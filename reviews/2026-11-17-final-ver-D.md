# Verification of the two reviews of lot D (DeepSeek, Mistral)

Repository: `dodos-kernel`, pull request 3, head `6312868`, copied to
`/private/tmp/dodos-pr3-ver-D`. Contract: `Docs/architecture/kernel-interface.md`
on `main`. Every command ran through
`/nix/var/nix/profiles/default/bin/nix develop -c ...` in the copy, and the copy
was reset with `git checkout -- .` after each experiment. The patches I name are
kept in
`/private/tmp/claude-501/-Users-btw-Documents-repos/77e1d0e5-4c09-401e-80b5-d6fb20678a8d/scratchpad/verD/`.

Report written as I go; the table at the end is the summary.

## M1. Invariant 40 refuses a waiting fault of kind 9 (Mistral 1; DeepSeek 8 is the same defect seen from the census)

**Lines.** `model/src/check.rs:790-798`: `let kind = (1..=8).contains(&parcel.label);`.
The census at `model/src/check.rs:49` and `:128-136` keeps `fault_kinds: [usize; 9]`
indexed by label and clamps with `.min(8)`.

**Contract.** `kernel-interface.md`, the table of fault kinds (line 455) has
"hardware breakpoint | 9", and Debugging a component (line 1666): "A hit is a
fault of kind 9, *hardware breakpoint*, delivered like every fault". `abi/`
has `FaultKind::HardwareBreakpoint = 9` and `from_raw(9)` returns it.
`Model::fault` (`model/src/faults.rs:22-26`) accepts kind 9 and `raise` makes the
thread wait as a caller with `parcel.label = 9`, `faulting = true`.

**Reproduction.** I added to `model/tests/faults.rs` a test that makes a running
thread with fault endpoint `EP`, suspends it, writes `DR0 = 0x1000`, `DR7 = 1`,
resumes it and calls `k.m.fault(thread, FaultKind::HardwareBreakpoint, ...)` with no
receiver waiting:

```
test ver_d_kind_9_fault_waiting_on_its_endpoint ... FAILED
  left: Err("40: fault wait")
 right: Ok(())
```

`census().faulting == 1` held just before, so the state is exactly "a thread that
waits on a fault of kind 9". The existing test
`a_breakpoint_hit_is_a_fault_of_kind_9` (`model/tests/debug.rs:327`) passes only
because its thread has no fault endpoint, so the fault is recorded, not delivered;
the property walk (`model/tests/property.rs:2112-2119`) draws kinds 1 to 6 only.
So no test ever delivered a kind-9 fault.

With invariant 40 fixed, the census then counts the kind-9 fault in bucket 8,
which `model/tests/property.rs:1749` and `model/tests/sched.rs:647,659,918,923`
read as *no context*. I asserted `census().fault_kinds[8] == 0` after the kind-9
fault: `left: 1, right: 0`. So DeepSeek's finding 8 ("a clamp that hides") is not a
hypothetical relaxation of 40: it fires as soon as 40 follows the contract.

**Verdict.** Real. Severity: high for the model (the check that runs after every
step refuses a state the contract requires and the model produces; an oracle or a
future scenario that delivers a breakpoint fails). DeepSeek 8: real, low, and it
must be fixed together with 40.

**Correction.** In `Model::check_waits` (the loop of `model/src/check.rs:790`):
`let kind = FaultKind::from_raw(parcel.label).is_some();`. In `census`:
`fault_kinds: [usize; 10]`, `let mut kinds = [0; 10];`,
`kinds[parcel.label as usize] += 1;` (invariant 40 bounds the label), and the doc
of the field saying it is indexed by label. Test: the one above, kept as
`fault_of_kind_9_waits_on_its_endpoint` in `model/tests/faults.rs`, asserting
`check() == Ok(())` and `fault_kinds[9] == 1`, `fault_kinds[8] == 0`; it fails
without either change. Adding `FaultKind::HardwareBreakpoint` to the walk's kinds
(with a thread whose `DR7` enables a breakpoint) would make the walk reach it too.
With both changes the whole `cargo test -p dodos-model` passes (every binary `ok`;
patch `fix-40.patch`).

## D1. `ring_holds` panics on a next sequence of 0 (DeepSeek 1; Mistral lists it under "checked and not findings")

**Lines.** `model/src/check/debug.rs:16-25`: `last` computes `next - 2` before the
`next >= 1` guard is read.

**Reproduction.** In `model/src/scenarios/checker.rs`, on `node2()`, I set
`Arc::make_mut(&mut k.m.table.crash).areas[n].next_user = 0` and called
`k.m.check()` under `catch_unwind`: `panicked at model/src/check/debug.rs:23:35`
(subtract with overflow). Both reviewers are right that no run of the model writes
0 (`DebugArea::new` starts at 1, `write` only adds).

**Verdict.** Real, low: the checker must report a bad state, not die on it, and
the file `scenarios/checker.rs` exists to feed it bad states. Mistral's reason
for dismissing it (unreachable) is the reason it is low, not a reason it is
correct.

**Correction.** `ring_holds`:
`next >= 1 && placed && (next == 1 || ring[((next - 2) % entries) as usize].seq == next - 1)`.
Test: `a_ring_whose_next_sequence_is_0_is_reported` in `scenarios/checker.rs`,
asserting `reported(&k, "88: user ring")`; it panics without the change and passes
with it (patch `fix-ring.patch`).

## D2 = M2. The G6 scenario of `checker.rs` never reaches G6 (DeepSeek 2, Mistral 2)

**Lines.** `model/src/scenarios/checker.rs:520-548`, the assertion
`ends_with("G6: ...") || report.contains("58")`.

**Reproduction.** Both reviewers ran it and got `node 1: 58: leaves of a use entry`;
I agree with that. I went further, with a mutation of G6 itself:
`ensure(true || held, "G6: ...")` in `check_grants` (`model/src/check/machine.rs:178`).
Result: the `checker.rs` test still passes, and exactly one test fails,
`scenarios::pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6`.
So G6 is guarded, by `pass18.rs:557`, but not by the test that bears its name.
I also tried the natural repair, a real granted translation in node 1 and node 0's
grant cleared while node 1 runs: the report is
`node 1: 58: translation under no grant`. G6 is reachable only when the holder's
own check no longer runs (an unfenced node), which is what `pass18.rs` builds.

**Verdict.** Real (a test that does less than its name), low, because G6 has a
failing test elsewhere. Both reviewers' wording "G6 is guarded by nothing" is too
strong: it is guarded by `pass18.rs`.

**Correction.** Turn the test into what it checks: rename it
`a_use_entry_with_leaves_and_no_grant_is_reported_by_the_holders_58`, assert
`assert_eq!(report, "node 1: 58: leaves of a use entry")`, and drop
`let _ = Member::new;` and the `Member` import. Its comment points at
`pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6`
for G6. The mutation above is the check that the pair guards both rules.

## D3 = M3. Two checks of `check_tasks` that cannot fail (DeepSeek 3, Mistral 3 for the first line)

**Lines.** `model/src/check/tasks.rs:55` `ensure(true, "50: ...")` and
`:32` `ensure(!ids.contains(&TaskId::NONE.raw()), "49: task identifier")`.

**Reproduction.** Line 55 cannot fail by its text. For line 32: `ids` receives a
raw identifier only when `(1..=self.task_counter).contains(&task.id.counter())`
held (the `&&` chain of `:20-22`), and `TaskId::raw` is `node << 48 | counter`
(`abi/src/lib.rs:1049-1051`), so a counter of at least 1 gives a raw value that is
never 0 = `TaskId::NONE.raw()`. I deleted both lines (ending the function with
`Ok(())` and dropping the `TaskId` import): every test binary of
`cargo test -p dodos-model` passes and clippy with `-D warnings` is clean (patch
`fix-tasks.patch`). `git log -S` shows line 55 is the remnant of commit
`2553463`, which replaced the old single-core rule 50 with the loop above it.

**Verdict.** Real, low (dead code carrying invariant numbers, in a file whose
header promises that "a check that cannot fail is caught").

**Correction.** Delete both lines in `Model::check_tasks`, end with `Ok(())`. No
test can fail without a line that cannot fail; the deletion is the correction.

