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

## Note on the resumed run

The run that wrote M1 to D3 was interrupted. I deleted the work copy, copied
`/private/tmp/dodos-pr3-final` again to `/private/tmp/dodos-pr3-ver-D` (head
`6312868`, clean), and used a second fresh copy, `/private/tmp/dodos-pr3-ver-D-b`,
for experiments that ran while a long mutation run held the first. The patches of
M1, D1 and D3 named above are still in the earlier folder. Everything below, and
the final run of all corrections, is in
`/private/tmp/claude-501/-Users-btw-Documents-repos/19f11afb-76c0-46f6-85fd-d831d905703a/scratchpad/`:
`mut.py` and `mut-all.txt` (the mutations of D4), `mut-b.py` and `mut-b.txt`
(D9 and the extra mutations), `fix-waiter.patch` (D10), `ver-d-tests.patch` and
`copy-b-tests.patch` (the new tests), `all-corrections.patch` (every correction of
this report and every new test, together), and `verify-all.log`.

## D4. Rules of the lot that no test feeds a bad state (DeepSeek 4)

**Method.** For each of the eleven rules DeepSeek lists, I turned the condition
off (`true || ...` in front of it; for 54, `.expect(...)` instead of the error;
for the attach word of 88, the `return Err(...)` replaced by a no-op) and ran
the whole `cargo test -p dodos-model --no-fail-fast`, one mutation at a time,
with the unmutated run as a baseline (0 failed). Then, for each rule, I wrote a
spoiled state that makes it fail and checked that the same mutation makes that
new test fail.

| Rule (file:line) | Existing tests that fail when it is off | New test, reports the rule, fails when it is off |
|---|---|---|
| TLB: the state word of a request (`check/node.rs:163`) | 0 | `ver_d_a_state_word_in_use_with_no_request_is_reported` |
| TLB: a barrier that invalidates (`node.rs:173`) | 0 | `ver_d_a_barrier_that_invalidates_is_reported` |
| epoch: a barrier beyond the kernel epoch (`node.rs:182`) | 0 | `ver_d_a_barrier_beyond_the_kernel_epoch_is_reported` |
| epoch: raised by more than one at a time (`node.rs:319`) | 0 | `ver_d_an_epoch_raised_by_two_is_reported` |
| epoch: not the last raise (`node.rs:329`) | 0 | `ver_d_an_epoch_that_is_not_the_last_raise_is_reported` |
| epoch: word 6 (`node.rs:340`) | 0 | `ver_d_a_word_6_beyond_the_kernel_epoch_is_reported` |
| credits: more sends than SENDS_PER_PEER (`node.rs:360`) | 0 | none possible (below) |
| G4: a leaf count below its leaves (`check/machine.rs:152`) | 0 | none built (below) |
| 54: block of no entry (`check/table.rs:331`) | 0 | `ver_d_a_block_of_no_entry_is_reported` |
| 88: an attach word with no identifier word (`check.rs:344`) | 0 | `ver_d_an_attach_word_with_no_identifier_word_is_reported` |
| 18: a watermark ready under a live object (`check.rs:827`) | 0 | `ver_d_a_ready_watermark_under_a_live_object_is_reported` |

So DeepSeek's list is exact: every one of the eleven can be switched off with the
whole suite green. With 18 and word 6 both off, the two new tests fail and no
existing one does.

Two of the eleven cannot be made to fail alone, and that is a finding of its own:

- **credits.** `check_credits` first requires
  `credits.len() == REQUESTS_PER_PEER + SENDS_PER_PEER` (`node.rs:353-356`),
  then counts the `Some` among `credits[REQUESTS_PER_PEER..]`
  (`model/src/rings.rs:249-257`), a slice of exactly `SENDS_PER_PEER` entries.
  The count can never exceed it. A probe that adds a 25th credit gets
  `"credits: the credits of a peer"`, the line before. The rule is implied by its
  neighbour, like the two lines of D3.
- **G4, leaf count of a device entry.** Each running node's own 58
  (`check/table.rs:420-430`) already requires its leaves of each device entry to be
  at most the entry's count (equal on an unshared node). G4 adds only the sum over
  running nodes, which exceeds a count only if two running nodes both hold leaves
  of one entry, and an entry is taken by one node at a time
  (`model/src/blocks.rs:120-126`, the owner word). My probe (node 0 maps a page of
  a device entry, then the count is set to 0) gets `"node 0: 58: map count"`, as
  expected. I did not build a two-node state that gets past every node check, so
  I cannot say G4's sum is unreachable. What I can say is that no single-node
  spoil reaches it.

**Verdict.** Real, medium as a group: eleven rules that a mutation turns off
without any test noticing, in a file (`scenarios/checker.rs:1-5`) whose stated
purpose is to catch exactly that, and two of them claimed for D-135 and D-138.
For credits the verdict is stronger: the line cannot fail at all.

**Correction.** Add the nine tests in the table (they are in
`all-corrections.patch`; each fails under its mutation, all pass on the model as
it is). Delete the credits line in `Model::check_credits`, or keep it and say in
a comment that the length check above implies it. For G4's device part, either a
two-node spoil that gets past both nodes' 58 (the `pass18.rs` way, with one node
unfenced, does not apply, since G4 counts only running nodes) or a comment saying
that the node's 58 shadows it in every state a node check accepts.

## D5. Rule 37 re-implements `memory::tables` (DeepSeek 5)

**Lines.** `model/src/check/memory.rs:110-123` (the check's own formula:
`span(k) > bytes(size)`, levels of an iospace from `io_width`) against
`model/src/memory.rs:30-45` (`tables`, from the page shifts) and
`model/src/memory.rs:375-378` (`io_levels`).

**Reproduction.** DeepSeek checked three geometries by hand. I wrote
`ver_d_rule_37_agrees_with_memory_tables_on_every_valid_geometry` in
`model/src/check/tests.rs`: it builds every `Geometry` that `Geometry::valid`
accepts (page shift 12 to 32, 1 to 8 levels, 2 or 3 page sizes; 24 of them pass
`valid`), and for each page size and five addresses (0, one page, three pages,
just below half and just below the top of the address bits) compares the set the
check computes with `memory::tables`, and for every width above the page the
check's iospace levels with `memory::io_levels`. It passes. A mutation of the
test's copy of the formula (`>` to `>=`) makes it fail, so it has the power to
see a disagreement. The reason they agree is a rule, not luck:
`Geometry::valid` (`abi/src/lib.rs:493-520`) requires each page size to be one
level above the one before (`s[i] == s[i - 1] + per_level`), and with aligned
sizes `P × E^k > P × E^s` is exactly `k ≥ s + 1`, the `leaf` of `tables`.

**Verdict.** Refuted as a defect: the two cannot disagree on any geometry the
model accepts. On the style point, I would keep the check independent. A check
that calls the helper it is meant to judge stops being a second opinion; the
check of leaves in `model/src/check/table.rs:144-146` says the same thing in
its own comment ("read from the tables, not from the gate's helpers"). The
`dodos-rust` rule DeepSeek cites is about operations sharing a check, not about
the checker reusing the code it checks. Severity: none.

**Correction.** None needed. If the pair should stay in step on purpose, the
test above is the guard; it costs nothing and fails the day a geometry with
unaligned sizes is admitted.

## D6. The doc of 35 says "1 to 512 pages", the contract says 1 to *E* (DeepSeek 6)

**Lines.** `model/src/check/memory.rs:14-15` (doc) against `:68-71` (code:
`count >= 1 && first + count <= frame.pages`), and `frame.pages ≤ E` held at
`model/src/check.rs:850`.

**Contract.** `kernel-interface.md` line 27 ("A run of 1 to *E* physical pages")
and line 243 ("a **number of pages** from 1 to *E*"); `aspace_map`, line 285:
"the page count is at least 1, and first page + page count does not exceed the
number of pages".

**Reproduction.** Not run, for a reason: the finding is in a doc comment, which
no command executes. The code follows the contract (through `frame.pages ≤ E`),
and 512 is *E* only on the 4 KB geometry; `verify` runs these tests on 16 KB
(*E* = 2,048) and 32 KB (*E* = 4,096) too. The doc of 37 a few lines lower has
the same reference-machine numbers ("one per 512 GB ... one per 2 MB that holds
a 4 KB page"), which is acceptable only if it says it is the reference machine.

**Verdict.** Real, low (a sentence that contradicts the contract it cites; no
behaviour is wrong).

**Correction.** In the doc of `Model::check_spaces`: "a record maps 1 to *E*
pages"; in 37: "on the reference machine (four levels, *E* = 512) one per
512 GB ...", or the general form *P* × *E*^*k*. No test can fail for a doc.

## D7. The test named after an attached device builds a device that is not attached (DeepSeek 7)

**Lines.** `model/src/check/tests.rs:2567-2578`, and `check_identifiers`,
`model/src/check.rs:315-354`: `held` (identifier words taken by this node) must
equal `attached` (devices attached through this node's units, plus attach
words). The test inserts identifier 7 taken by node 0 with nothing attached,
so `held = {7}`, `attached = {}`: the *held, not attached* direction.

**Reproduction.** I mutated the comparison to `held.is_subset(&attached)`, which
keeps the direction the test builds and drops the one its name and comment
describe (*attached, but the word is not the node's*). The whole
`cargo test -p dodos-model` passes: 18 binaries, 1,145 tests, 0 failed. So the
direction the test is named after has no test anywhere. I wrote
`ver_d_an_attached_device_whose_identifier_word_is_another_nodes_is_reported`:
on `state()`, an iospace in slot 60, `IoSpaceAttach` of device 0x10 through
`apply_settled`, `check() == Ok(())`, then the device's identifier word
rewritten as taken by node 1. It reports
`"88: identifier words and attached devices"` on the original code and fails
under the mutation. DeepSeek is also right that `insert(4, free)` is inert.

**Verdict.** Real, low (a test that guards half the rule its name states).

**Correction.** Rename the existing test
`an_identifier_word_taken_with_no_device_attached_is_reported` (what it builds),
drop the inert `insert(4, ...)`, and add the test above, named
`an_attached_device_whose_identifier_word_is_not_its_nodes_is_reported`. It fails
with `held.is_subset(&attached)` in place of `held == attached`.

## D9. R0 and the bound of the line words live in `check_lines` (DeepSeek 9)

**Lines.** `model/src/check.rs:356-374`.

**Reproduction.** Both rules have a test: `model/src/scenarios/pass19.rs:272`
(96, the bound) and `:284` (R0). I ran the two mutations (`false &&` in front
of each condition) over the whole `cargo test -p dodos-model`: without the bound,
`pass19::a_line_at_irq_lines_max_is_unsupported_and_the_last_word_is_claimable`
fails; without R0, `pass19::r0_run_twice_for_one_generation_is_reported` fails.
Nothing else fails in either run.

**Verdict.** Half refuted, half real. The bound of the table of line words is a
rule about line words, the subject of 96, and sits where it belongs. R0 (reclaim
runs once per generation) has nothing to do with lines; its doc is a one-line
code comment inside the interrupt check, and `check()`'s list of calls
(`model/src/check.rs:287-306`) does not show it. Severity: very low (a reader's
cost; the rule is checked and tested).

**Correction.** Move the R0 test into its own `fn check_reclaim(&self) -> Check`
with a doc that names R0 and its section, called from `Model::check`; or at
least name R0 in the doc of `check_lines`. The test at `pass19.rs:284` is the
one that fails without it; no new test is needed.

## D10. `check_requests` accepts a request whose thread waits for nothing (DeepSeek 10)

**Lines.** `model/src/check/node.rs:200-205`: the waiter must wait as
`Wait::Cores(requester)` *or* `Wait::None`, and the rule is skipped when the
waiter is not a live thread. The doc at `:153` says "its waiting thread waits
for it".

**Contract.** Line 329, the request holds "the thread that waits for it, if any";
line 136 (removal of a thread): "a wait ... for its node's cores ends, and ...
the completion of the request, when it comes, finds no thread to wake".

**What the model does.** `Model::unlink` (`model/src/ipc.rs:639-665`), the path
of every cancelled wait (suspend, cancel, removal), calls `forget_waiter`
(`model/src/cores.rs:488-496`), which sets `request.waiter = None` in the same
step. `Model::complete` takes the request before it wakes the thread. So the
model never leaves `waiter = Some(t)` with `t` not waiting for that request, nor
with `t` gone. DeepSeek could not find such a path; there is none.

**Reproduction.** I made the check strict:
`request.waiter.is_none_or(|thread| self.threads.get(&thread).is_some_and(|t| t.wait == Wait::Cores(requester)))`.
The whole `cargo test -p dodos-model` passes (18 binaries, 1,149 tests, 0 failed; the count includes the
two new tests below and the two tests of D7), so nothing needs the
loophole. Two new tests in `model/src/scenarios/checker.rs`,
`ver_d_a_request_whose_thread_waits_for_nothing_is_reported` (an idle thread
named as waiter) and `ver_d_a_request_whose_thread_is_gone_is_reported`
(a waiter that is no thread), both fail on the original code with
`left: Ok(())` and pass with the strict check (patch `fix-waiter.patch`).

**Verdict.** Real, low: the check does less than its doc. The contract allows
the completion to find no thread, but the model chose to clear the waiter, and
the check should hold the model to that choice.

**Correction.** In `Model::check_requests`, the strict form above, keeping the
message (or "TLB: the thread of a request does not wait for it"); the two tests
above fail without it.

## D-a to D-e. DeepSeek's "also seen" items

- **D-a. `let other = ...; let _ = other;` (`scenarios/explore.rs:682,722`).**
  Read: `other` appears only in those two lines, so it is kept only to silence
  the lint. Real, trivial. Correction: `let _ = m.thread_on(1, 300, 2);` (the call
  matters, the name does not). Nothing runs differently, so no test.
- **D-b. `let _ = context;` (`check/tests.rs:1766-1770`).** Read: in the second
  half of `home_that_its_context_does_not_name_is_reported` the context is
  computed and thrown away, and the test checks two rules (41, then 44) under one
  name. Real, trivial. Correction: drop the unused line and split the test into
  one for 41 and one for 44 (one behaviour per test, `dodos-rust`).
- **D-c. The two `assert_ne!` of the fault test (`check/tests.rs:480-495`).**
  Run: a probe prints the report for kinds 7 and 8 at the address after the call:
  `"30: outcome of a wait"` for both. The mutation that makes 16 refuse those
  kinds (`let raised = false && ...`) makes the test fail (with seventeen other existing
  tests). So the test does what its comment says: 16 lets these states through.
  Refuted as a weakness. Naming 30 in the comment would help a reader. Severity:
  none.
- **D-d. The shadowed `zero` (`check.rs:823,837`).** Read: the first is a `bool`
  for "18: watermark is zero", the second the cleared ranges four lines below, in
  the same loop body. It compiles and clippy accepts it. Real, trivial.
  Correction: rename the second `cleared`.
- **D-e. `slots_of(...)[0]` (`scenarios/explore.rs:289,306` and others).** Read.
  In a test, an index that panics is a failure with a line number, which is what
  a forgotten setup should produce. Refuted. Severity: none.

## Mistral's "checked and not findings"

These are not findings, so I do not judge them one by one. I ran the one that
overlaps a finding (the ring, D1) and judged it there. In the others I saw nothing
that contradicts Mistral's reasons. One of them has the same shape as D1:
`check_cores` calls `table.member(slot)` on the slot field of a core word,
which panics when the slot is out of range. That is a checker that dies on a
bad state instead of reporting it. I did not run it.

## What both reviewers missed

My reproductions showed three things neither report names. First, the helper
`with_device` (`model/src/check/tests.rs:1604-1635`), used by the four tests of
rule 39, builds a state that already fails the check before any spoil: it
answers the attach by calling `Model::unit_step` directly, outside the event
that would requeue the woken thread, and `check()` then reports
`"41: queue of a context"`. Those four tests pass only because rule 39 runs
before 41 in `Model::check`, so any change to that order breaks them for a reason
that has nothing to do with 39. With `apply_settled` in place of the loop (what
`model/tests/memory.rs:48-55` does) and `assert_eq!(m.check(), Ok(()))` at the
end of the helper, all four still report their 39 and the base state is valid.
Second, two of DeepSeek's "unguarded" rules are not just untested but
unreachable by any single spoil: the credits line cannot fail at all, and G4's
device part is shadowed by every node's 58. The same is true of the
`untyped.live == 0` conjunct of the word-6 rule, which 18 always reports first.
"One spoiled state per invariant" is therefore not only a missing test: some of
these lines are dead, and dead lines should be removed or labelled, not tested.
Third, a test that tells a fault of kind 9 from the census bucket of *no
context* (M1) exists nowhere because no test or walk ever delivers a kind-9
fault; the walk's kinds stop at 6. With every correction of this report applied
together (M1, D1, D2, D3, D4's nine tests, D7, D10, the `with_device` fix), the
whole `nix develop -c ./verify` passes: format, clippy with warnings denied, and
3,380 tests over 47 test binaries, the page-dependent ones on all three
geometries, 0 failed (`verify-all.log`).

## Table

| Finding | Verdict | Severity | Correction in one line |
|---|---|---|---|
| M1 (Mistral 1; DeepSeek 8 with it) | Real | High | `check_waits`: label by `FaultKind::from_raw(..).is_some()`; census `[usize; 10]` indexed by label; test of a waiting kind-9 fault |
| DeepSeek 8 | Real, tied to M1 | Low | The census change of M1; assert `fault_kinds[8] == 0` after a kind-9 fault |
| D1 (DeepSeek 1; Mistral non-finding) | Real | Low | `ring_holds`: test `next >= 1` before `next - 2`; test with `next_user = 0` |
| D2 = M2 | Real (test does less than its name) | Low | Rename to what it checks, `assert_eq!` the 58 report, drop `Member`; G6 stays guarded by `pass18.rs` |
| D3 = M3 | Real (two lines that cannot fail) | Low | Delete both lines of `check_tasks`, end with `Ok(())` |
| D4 | Real | Medium | Nine new spoiled-state tests; delete or label the credits line; label G4's device part as shadowed by 58 |
| D5 | Refuted | None | None; the check agrees with `memory::tables` on all 24 valid geometries (test kept as a guard) |
| D6 | Real (doc against contract) | Low | Doc of 35: "1 to *E* pages"; doc of 37: say "reference machine" or use *P* × *E*^*k* |
| D7 | Real | Low | Rename the test after the direction it builds; add a test for an attached device whose word is another node's |
| D9 | Half refuted, half real | Very low | Move R0 to its own `check_reclaim` with a doc; the line-word bound stays |
| D10 | Real (check weaker than its doc) | Low | `check_requests`: waiter must exist and wait `Cores(requester)`; two tests |
| D-a | Real | Trivial | `let _ = m.thread_on(...)` |
| D-b | Real | Trivial | Drop `let _ = context`; split the test into 41 and 44 |
| D-c | Refuted | None | None (optionally name 30 in the comment) |
| D-d | Real | Trivial | Rename the second `zero` to `cleared` |
| D-e | Refuted | None | None |
| Missed: `with_device` | Real | Low | `apply_settled` and a check of the base state in the helper |
