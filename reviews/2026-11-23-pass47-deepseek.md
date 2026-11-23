# Review of pass 47 (`5fc1333..a9c6762`, branch `model`, head `a9c6762`)

The assistant checked every finding (23 November 2026): all five accepted. Finding 1 rerun: with `next_sweep` removed from `reserve_instants`, `pass47::a_call_takes_the_sweep_of_another_node_first` still passes. Finding 2 read in the code: pass 46's `Model::apply` tested `asleep == 0` (`lib.rs:1565` at `5fc1333`) and pass 47 dropped it; on the `System` path, the assistant's own mutation that drops the `awake` filter of `System::due_core` also survives the whole library, so neither side of the sleep test has a test. Findings 3 and 5 are readings, unreachable today (contract line 397; `explore.rs` iterates `grants[x].values()` and so cannot compare the key). Finding 4 is a comment. Two more mutations of the assistant's own survive: the `CORE_ANSWER_NS` clause of `Model::due_cores` counted on a node that already accused itself (whole library), and the liveness exemption accepting a frozen count of any value (the `pass47` tests). All taken into pass 48.


Reviewer: DeepSeek V4.1 Flash (Mistral Vibe), 23 November 2026. Read-only on
`/private/tmp/review-47/tree`, `dodos-kernel` and `Docs`. Every mutation and
reproducer ran in a `cp -a` copy at `/private/tmp/review-47/scratch/base`
(driver `/private/tmp/review-47/scratch/mut.py`, reproducer
`/private/tmp/review-47/scratch/reproducers/review47.rs`); each file was
restored after its mutation and the copy ends identical to the tree. Cargo
through `/nix/var/nix/profiles/default/bin/nix develop -c …`.

Baseline of the copy: `cargo test -p dodos-model --lib` — **1119 passed, 0
failed, 15 ignored, 139.30 s**. The 12 tests of `pass47.rs` alone: pass, 1.5 s.
The seven `directed_*` tests (one ignored): pass, 21.5 s.

Line numbers are those of `a9c6762`. I found **no major finding**: nothing in
the range contradicts the contract, and I found no way for a check to miss a
fault that the model can reach.

---

## Findings

### 1. The new test for the sweep's due event passes with that due event deleted (minor)

`model/src/scenarios/pass47.rs:56` (`a_call_takes_the_sweep_of_another_node_first`),
`model/src/nodes.rs:2453-2455` (`reserve_instants`, the `next_sweep` arm),
`model/src/nodes.rs:2440-2449` (`reserve_timer_due`). Contract line 1675 (the
sweep is "at a due event of its first core's timer queue, which it arms every
`SWEEP_NS`") and line 602.

The test names the sweep as the due event it pins, but the state it builds has
a **second** reserve instant in `(steps_at, next_sweep]`: node 0's observation
of node 1 (`o.at + stale_ns`). So `reserve_timer_due()` is true for that
instant, the drain fires the timer, the reserve's step sees `now >= next_sweep`
and sweeps.

Mutation (`mut.py M1-sweep-not-an-instant`): guard the arm with
`if false && self.others_exist()` — the sweep is no longer an instant at all.
`a_call_takes_the_sweep_of_another_node_first` **still passes**.

Reproducer (`reproducers/review47.rs`, registered as `mod review47;` in the
copy): `S::two()`, `settle()`, `beacons[0].observations.clear()`,
`move_clock(next_sweep)`, then `assert!(due_now(0))`,
`assert!(reserve_timer_due())`, a call of node 1, `assert!(next_sweep > sweep)`.
On `a9c6762` it **passes**; with the mutation it **fails at the second
assertion** — `due_now(0)` is true (the model offers a timer:
`reserve_due` = `Some(now)` because `reserve_work` sees `now >= next_sweep`)
while `reserve_timer_due()` is false, so the drain takes nothing and check 47
says nothing. That is exactly the shape of pass 46's finding 5, at the sweep.

Not a hole in the suite: the whole library under the mutation fails four tests
(`combined_recovery_states_between_nodes`, `directed_combinations_sample`,
`pass28::a_closed_observation_frees_its_slot`,
`membership::a_node_that_does_not_consume_a_message_waiting_in_its_ring_is_accused_stuck`)
— the sweep is what observes a stuck node, so its loss shows up as a wrong
accusation elsewhere, with a message that does not name the sweep. The fault is
the test, not the model: it should clear the observations (as the reproducer
does) so that `next_sweep` is the only instant in the window.

### 2. The standalone flag lost the sleep guard, so check 47 can refuse a lawful sleeping core (minor)

`model/src/lib.rs:1569-1578` (`Model::apply`: `draining = (0..width()).any(|c|
!self.cores[c].silent && self.timer_draining(c))`), against
`model/src/system.rs:440-447` (`System::awake`) and the pass-47 brief, item 1
("the same awake test, `System::awake`, not `asleep == 0`").

Pass 46's flag had `self.cores[c].asleep == 0`; pass 47 deleted it and put
nothing in its place, so a `Model` driven outside `System` now counts a core
that is `Suspending` or `Asleep` as draining. The contract allows exactly that
state: `check/sched.rs:86-100` and `:258-268` accept a replenishment or a timer
of a sleeping core whose instant is past now within the state's exit latency
("a timer of a sleeping core is taken at its wake, up to the state's exit
latency after its instant", Idle). `program_timers`/`refresh_timer_on`
(`sched.rs:713-742`) keep `hw_timer` at `now` for such a core, so
`timer_draining` is true and `Model::apply` flags the call.

Consequence: a scenario that calls `m.sys.node_mut(n).apply(...)` directly —
`pass46::checker_rejects_a_call_while_a_core_of_its_node_drains` is one, and the
report counts more than 30 such callers — while another core of that node sleeps
with a due timer or replenishment is refused with `47: a call ran while a core
had a due event left` for a lawful state. `System::apply` is right (it filters on
`awake`); only the standalone path is wide. No current test reaches it (the suite
passes), so this is a reading with a known shape, not a demonstration; the fix is
one predicate in `Model::apply`, e.g. the same hardware state the `System` keeps,
or the core's `asleep` as before.

### 3. The liveness exemption does not cover an attach word a failed unit keeps *attached* (minor)

`model/src/scenarios/explore.rs:182-183` (`assert!(!lined && !attached && kept)`),
`model/src/nodes.rs:1413-1423` (R1 done at once on a failed unit **only** for a
node with no device behind it), `model/src/nodes.rs:1454-1458` (`r6_held_back`
counts an attach word read *attached* beside an identifier word of `(x, g)`).
Contract line 397 and line 341: "those kept counts … end at R6 once no attach
word of the generation reads *attached* (which an attached word of a failed unit
never lets happen)".

A node whose device was behind a unit that failed never has R1 done on that unit,
so its attach word stays *attached* for ever, and R6 for it is held back for a
reason the contract calls lawful until the machine restarts. The exemption
narrows the failure to `kept` (`frozen_uses`, the use-entry count) and still
treats `attached` as a fault, so such a state would fail the check when it is
the only hold-back.

I could not build it: the same failed unit keeps some live node from writing
`acked[x]` (R1 is not done there), so `barrier_holds(x)` never holds in a run —
which is exactly why the test of the exemption has to clear `maps_of` by hand.
So this is a reading, not a demonstration; it says the exemption is narrower
than line 397's sentence, in the safe direction (a false positive, unreachable
today), not wider.

### 4. The comment on the drain names `Model::due_now`, which is the predicate the drain deliberately is not (minor)

`model/src/system.rs:333-336`: "each core that takes its interrupts and has a
due instant (`Model::due_now`) takes its timer interrupts until none is due".

The code uses `System::due_core` → `Model::due_cores` (`cores.rs:856-866`), and
`due_cores` is narrower than `due_now` (`sched.rs:749-754`) by exactly the
reserve's "runnable now" that the whole departure from the brief turns on.
`Model::apply`'s own doc comment (`lib.rs:1564-1568`) is right; this one invites
the next writer to re-widen the predicate that 21 tests then fail on. Worth one
sentence, not a code change.

### 5. The check's `counted` is not an exact mirror of `grant_still_counted` (minor, reading only)

`model/src/scenarios/explore.rs:162-180` against `model/src/nodes.rs:1428-1446`.
The model counts a grant only if the use entry at the recorded index names
`u.granter == node && u.grant == grant && u.serial == entry.serial && u.leaves >
0`; the check iterates the grant entries and drops the `u.grant == grant` test
(it never knows the key). For a table where a use entry at a grant's `use_index`
names another grant, `counted` gains an entry the model does not count, so
`kept`'s `all` can excuse a hold-back the exemption does not describe, or refuse
one it does. Check G6 (`check/machine.rs:406-412`) requires the use entry a live
count names to be the grant's own, so I could not build a reachable state; the
conjunct belongs there for the same reason it is in the model's reading.

---

## Item 1: the departure from the brief is right

The brief took a core's due instant to be `due_now`. The writer drains
`Model::due_cores` instead: the timer queues (`timer_draining`), the
`CORE_ANSWER_NS` deadline of the core's request, and on core 0 the reserve's
timed instants (`reserve_timer_due`). I agree, on the contract:

- line 600 defines a due event as "a replenishment whose instant is not after
  now, or a timer whose firing instant is not after now";
- line 332 makes the request deadline one ("arms a due event of its timer
  queue"), and lines 1675 and 1682 make the sweep, a fence's timed waits and a
  start's retry due events of the first core's timer queue — all of them are in
  `reserve_instants` (`nodes.rs:2451-2503`: `next_sweep`, `fence.last +
  fence_round`, the fence records' `SETTLE_NS`/`FENCE_NS` instants,
  `start.last + START_RETRY_NS`, `start.since + START_NS`, `unit_deadline`,
  observation waits, handing waits, the `START_NS` of a wait for entry);
- line 1737 makes the rest of recovery the work of a scheduling context, "by the
  rules of What runs next": `reserve_due`'s `Some(now)` while `reserve_work()`
  is true is that context being runnable, not a replenishment due. The reserve's
  own period is never a due instant in the model (`reserve_due` returns `None`
  when it has no work and no instant, `nodes.rs:2426-2432`), which matches
  "it arms no timer" (line 1739).

Nothing more than those three is drained, and nothing of those three is missing.

**The drain cannot fail to end.** Each clause makes progress with one timer
interrupt, and the two predicates agree exactly:

- request deadline: `due_cores` reports `request_due(p) <= now`, and `due()`
  (`sched.rs:770-782`) accuses the node under the same inequality —
  `started + core_answer_ns <= membership_now()` with `membership_now = now -
  stopped_time` is `request_due = started + core_answer_ns + stopped_time <=
  now`; `request_due` is `None` while the release word is raised, so no state
  spins. After the accusation `beacons[node].panic` is set (or already named the
  generation) and `!panicked` drops the clause.
- reserve: `due()` calls `reserve_step()` on core 0, which always ends with
  `steps_at.0 = self.now` (`nodes.rs:2618-2622`), and `reserve_timer_due`
  requires an instant **strictly after** `steps_at` — false after the step.
- timer queues: `has_due_at` and `due()` see the same two sources, so each
  interrupt takes at least one of the at most 16 it takes (line 600's cap keeps
  `hw_timer` at `now`, so the next iteration drains the rest).

## Item 2: the five tests

Each of them pins its clause alone, on the states below; I ran all five under
the report's mutations and under five others (table below), and each failed only
at the clause under test. Two notes, neither a fault:

- `checker_rejects_a_line_free_journaled_as_r1_after_the_holders_acknowledgement`
  (`pass47.rs:114`) and
  `checker_rejects_a_release_free_by_a_node_that_does_not_hold_the_controller`
  (`:134`) plant the write in the journal through `free_line_5`
  (`pass47.rs:72-86`) rather than reach it; that is what makes the state differ
  from a passing one by the clause and nothing else.
- `the_holder_refuses_a_release_on_a_claimed_entry` (`:168`) judges
  `operands_allowed` directly (`units.rs:453-454`), not a check — right for a
  refusal of the gate.

## Item 3: the liveness check

- The exemption reads the grantee's `frozen_uses` (`memory.rs:277-300`), the
  count an unmapping left when the unit answered *failed*, and requires it to
  cover the use entry's whole `leaves`. That is line 397's state: the holder's
  count kept by a failed unit, the granter never free, "stays fenced". It
  requires `!lined && !attached` and does not care about the grantee's member
  state, which is the narrowing the brief asked for (a frozen grantee alone
  excuses nothing — `pass47.rs:241` pins that).
- `Fencing` nodes are judged (`explore.rs:125-138`) when the driver is live or
  sealing, writes, and has a core that takes events — the case the brief asked
  for. A `Fencing` node whose driver is gone is left alone, which the sweep's
  `SWEEP_NS` (1 s) makes lawful past a 200 ms quiet run; I agree with that
  judgement and with not judging `driver == x`.
- The node that sees the barrier is any live node whatever its core 0
  (`explore.rs:141-148`, `pass47.rs:271`).
- Can it fire on a lawful state? Only through finding 3 (an attach word), which
  the model's own barrier keeps out of reach today; and through a `Fenced` node
  whose driver is live with every core silent, where "R6 held back" is the wrong
  message for a lost machine but not a lawful outcome. Can it miss a stall? A
  `Fenced` node judged only through the first live node whose barrier holds
  (another live node could be the stuck one), and a node whose only
  barrier-holding peer is sealing and seals — the same two as pass 46, neither
  reachable in the runs I have.

## Item 4: the harness fix

`directed_combination`'s new step 2a (`combinations.rs:5090-5106`) takes a free
device entry larger than a page on node 1 and splits it. Its test
`directed_resume_with_a_hand_death_splits_an_entry` passes on `a9c6762`, and
with the step disabled (`if false && has(SPLIT)`) it fails at
`combinations.rs:5820` with `directed_combination([9, 13, 21]) did not have all
bits set at once: mask=0x403201, wanted=0x202200` — the report's message.

I checked the six the report says are still out of reach with a scratch test
(removed after the run) that ran thirteen combinations through
`directed_combination` and reported which reached:

| Wanted | Caught by |
|---|---|
| `pair + fenced + entry split`, `resume + fenced + entry split` | the final probe, `mask=0x600000`/`0x600200`, wanted `0x200040`/`0x200240` — SPLIT reached, **FENCED** not |
| `pair + grant unanswered + entry split`, `resume + …`, `death + …` | inside step 9b, `assert!(run.receive(u_pair, 0))` (`combinations.rs:5500`) |
| `death + entry split + line moving` | inside step 11, `assert_eq!(run.call(actor, kill(victim)), Some(DONE))` (`:5603`) |
| the same six with *chunk given* in place of *entry split* | the same three places, the same way |
| `death + entry split + device detached` (a control) | reached |

So the report's claim holds: the six are limited by the *fenced*, *grant
unanswered* and *death + line moving* steps, not by the new one. Leaving them
unfixed is right — they fail only if the seeds stop reaching them, which is the
fault pass 46 found and this pass fixed for *entry split*.

## What I checked and found correct

- **The drain and the flag are one predicate.** `System::apply`
  (`system.rs:331-355`) drains with `due_core` and then computes `DueAtCall`
  with the same `due_core`; the flag travels to the caller's `EventLog`
  (`lib.rs:1580-1592`) and check 47 (`check/sched.rs:374-379`) reads it. A
  mutation of the drain alone now fails a test (row 9 below), which was pass 46
  finding 1.
- **Finding 6 of pass 46 is answered on the `System` path**: `due_core` filters
  on `System::awake` (`system.rs:440-447`), the same test the drain uses, and
  `asleep == 0` is gone. (Only the standalone `Model` path is wide — finding 2.)
- **`reserve_instants` is a factoring with no change of behaviour**: the moved
  block is byte-for-byte the same pushes, and `reserve_due` keeps the
  `at > now`, `min(period)` and `Some(now)`-when-work logic (`nodes.rs:2415-2432`).
- **The unmoved `Model::apply`**: `checker_rejects_a_call_while_a_core_of_its_node_drains`
  (`pass46.rs:125`) still forces the flag through `Model::apply` and fails if
  check 47's call clause is made true — the same-node case still has a test.
- **`short_run_missed.txt`** (`scenarios/short_run_missed.txt`) is guarded by
  the `lost` assertion of `combined_recovery_states_between_nodes`
  (`combinations.rs:4856-4870`); the file's new content is consistent with it,
  since the whole suite (which runs that scenario) passes.
- The five new tests of item 2 and the four of item 3 each reach their state and
  fail under the mutation named for them (rows 2-8 and 10-13).

## Mutations I ran (each alone, file restored after each; debug build)

| # | Mutation (file: change) | Test | Result |
|---|---|---|---|
| 1 | `nodes.rs:2453` `next_sweep` not pushed into `reserve_instants` | `pass47::a_call_takes_the_sweep_of_another_node_first` | **passed** — finding 1 |
| 1b | the same, whole library (1119) | — | 4 failed: `combined_recovery_states_between_nodes`, `directed_combinations_sample`, `pass28::a_closed_observation_frees_its_slot`, `membership::a_node_that_does_not_consume_a_message_…accused_stuck` |
| 2 | `cores.rs:859` `at <= self.now` → `at < self.now` | `pass47::a_call_takes_a_core_answer_deadline_of_another_node_first` | failed, `pass47.rs:49`, `node 0: CORE_ANSWER_NS: a request older than the bound on a node that did not accuse itself` |
| 3 | `nodes.rs:1336` `let walking = self.r1_walking(…)` → `true` | `pass47::checker_rejects_an_r1_line_free_on_a_reclaim_record_of_an_older_generation` | failed, `pass47.rs:103`, `Some(R1 { walking: true })` |
| 4 | `table.rs:978` the journal's `acked` → `false` | `pass47::checker_rejects_a_line_free_journaled_as_r1_after_the_holders_acknowledgement` | failed, `pass47.rs:128`, `Ok(())` |
| 5 | `check.rs:431` `&&` → `||` in invariant 96 | `pass47::a_line_irq_not_removing_whose_word_is_free_is_reported` | failed, `pass47.rs:158`, `Ok(())` |
| 6 | `table.rs:970` the journal's `holds` for a line word → `true` | `pass47::checker_rejects_a_release_free_by_a_node_that_does_not_hold_the_controller` | failed, `pass47.rs:141`, `Ok(())` |
| 7 | `units.rs:453` refuse a *release* only when `!claimed` | `pass47::the_holder_refuses_a_release_on_a_claimed_entry` | failed, `pass47.rs:182` |
| 8 | `explore.rs:181` `kept = !counted.is_empty()` | `pass47::a_grant_counted_by_a_frozen_grantee_without_a_failed_unit_is_a_stall` | failed, "did not panic as expected" |
| 9 | `system.rs:360` the drain skips core 0 (`p != 0 && awake`) | `pass47::a_call_on_one_node_takes_the_due_events_of_another_node_first` | failed, `pass47.rs:23` |
| 10 | `nodes.rs:2457-2459` and `:2484-2493`: the fence's and the fence records' instants dropped | whole library (1119) | 2 failed: `combined_recovery_states_between_nodes`, `pass42::checker_rejects_a_sealing_holder_waiting_past_stuck_ns` (`REBUILD: a holder waited past STUCK_NS …`) — the fence waits' due events are load-bearing, though no `pass47` test names them |
| 11 | `combinations.rs:5090` step 2a disabled (`if false && has(SPLIT)`) | `directed_resume_with_a_hand_death_splits_an_entry` | failed, `combinations.rs:5820`, `mask=0x403201, wanted=0x202200` |
| 12 | the six *entry split* and six *chunk given* triples through `directed_combination` (scratch test) | — | the six of each missed, at the three places of item 4 |
| 13 | `reproducers/review47.rs` (sweep alone, observations cleared) | on `a9c6762` | passed; under mutation 1 it failed at `reserve_timer_due()` |

Rows 2-9 sample eight tests of `pass47.rs` by mutations other than the report's
table for them; seven of the eight fail as they should. Row 1 is the exception,
finding 1.

## Not verified

I did not run `./verify`, `every_combination_of_recovery_states_is_reached`,
`directed_combinations_reach_all_74` or `many_seeds` on `a9c6762` — the release
long runs do not fit this session (the report's 196-527 s each). What I ran is
the whole debug library suite three times (baseline and two mutations), the
`pass47` subset, the seven `directed_*` tests, and the scratch combinations.
The report's durations and its `never reached: []` are therefore unconfirmed by
me; nothing I read contradicts them. Finding 2 is a reading (no reproducer);
finding 3 is a reading whose state I could not reach; finding 5 is a reading
that check G6 makes unreachable. No `CONTRACT-GAP`.
