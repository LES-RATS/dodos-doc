# Review of pass 45 (`05c1313..26a3c37`, branch `model`, head `26a3c37`)

Reviewer: DeepSeek V4.1 Flash (Mistral Vibe), thinking `high`, 23 November 2026. The assistant checked every finding: finding 1 reproduced independently (an assertion in `System::apply` fires at 104 ms on `DODOS_SEED=181`); all seven accepted, finding 2 by settling the reading (actions stay offered on a draining core). Answered by pass 46.

I read the six commits, the pass-45 brief and report, the pass-44 review and the
clauses of `Docs/architecture/kernel-interface.md` they turn on (line 600/602
"Due events and the hardware timer", 697 and 2207 D-171, 829 "a line word also
by the gate of its controller's role holder", 1356 the line-word transition
rows, 1358 "R6 frees no line word", 1702 R1). Everything below was checked
against a scratch copy of the tree (`/private/tmp/review-45/scratch/base`,
a `cp -a` of `26a3c37`); the reproducers are
`/private/tmp/review-45/scratch/base/model/src/scenarios/review45.rs`
(registered as `mod review45;` in the scratch `scenarios/mod.rs`) and the
mutation driver `/private/tmp/review-45/scratch/run_mut.sh`. Nothing in
`tree/`, `dodos-kernel` or `Docs` was modified; no cargo command was run in the
reviewed tree.

Line numbers below are those of `26a3c37`.

---

## Findings

### 1. A call still runs on a core whose capped timer interrupt left due events at `now` (major)

`model/src/system.rs:331` (`System::apply`). Contract line 600 ("the next
interrupt comes at once and processes the next 16 before anything else runs")
and line 602 ("Determinism: the reference model processes every due event at
its instant before any call at that instant").

The pass-45 fix put the guard in `System::events` only (`system.rs:349`,
`system.rs:367`, both `!model.timer_draining(position)`). A call does not go
through `events`: `System::apply` calls `Model::apply` at once, so a thread on a
draining core can run a call before the remaining due events are processed. The
model therefore does not implement the reading the pass-45 brief settles ("on
that core, nothing else is taken (no other interrupt, no call, no thread runs)
until no due event remains at `now`"), and no check refuses it.

Reproducer, `review45::review45_call_runs_on_a_draining_core`
(`review45.rs:28`): 17 timers armed at one instant on node 0's core 0, one
`Event::Timer` fired (`timer_draining(0)` true, one due event left,
`hw_timer == Some(deadline)`), then `TimerSet` for an old timer: the call
succeeds, the timer is re-armed, the due event is still there, and
`System::check()` returns `Ok(())`.

Reached in the runs as they stand: with a two-line `eprintln!` in
`System::apply` (scratch only), `DODOS_SEED=181` of
`every_combination_of_recovery_states_is_reached` prints
`CALL-WHILE-DRAINING at 104000000 cores [0] call on Some(0)` — node 0's core 0
is draining and the call runs on that very core — and the run passes.
(`DODOS_SEED=181 cargo test -p dodos-model --lib
every_combination_of_recovery_states_is_reached -- --ignored --nocapture`,
5.3 s in debug.) So this is not a knife-edge only a hand-written test can
reach; the seeded evidence contains it.

### 2. `events()` still offers actions for the draining core (minor)

`model/src/system.rs:377-381` (`events`, the `Event::Action` block) with
`model/src/system.rs:656` (`System::step` chooses uniformly at random among
`events()`) and `model/src/system.rs:1038` (`act` → `park`).

The suppression added in this pass covers `Event::Ipi` and `Event::Sleep`
only. `Event::Action` is still listed for a draining core, so `HwAction::Park
{ core }` (a self-park from `park_all`, or a seal's park) and `HwAction::Stop
{ core }` (the fence) still run on that core before the next 16 due events, and
`System::step` / `S::shuffle` pick one event out of `events()` at random, so
they can pick the action first. Whether a stop or a park is "something else
that runs" is a modelling decision the pass did not take; if the reading is that
the fence's stop is exempt, it should be named, and `EntryStep`, `StubHalt`,
`CpuOff` and `Wake` should be looked at the same way.

Reproducer, `review45::review45_action_offered_on_a_draining_core`
(`review45.rs:93`): after the capped `Event::Timer` of finding 1, a
`HwAction::Park { core: 0 }` is queued for that core and `events()` returns both
`Timer { node: 0, position: 0 }` and `Action(0)`. The pass-45 test
`capped_timer_interrupt_offers_only_timer_on_draining_core`
(`pass45.rs:233`) asserts nothing about actions (its failure message says
"draining core must offer only `Event::Timer`", but it only tests `Ipi`).

### 3. `line_r1` cannot tell R1's free from an earlier free by the controller holder (minor)

`model/src/check/table.rs:84-97` (`judge_write`, the `line_r1` clause), with
`model/src/table.rs:906` (`holds_line_controller`) and `model/src/table.rs:941`
(`journal`, `acked`). Contract line 1356: the word goes *taken* → *free,
unclaimed* by "the controller holder's, the call that writes the masked entry
with *release* (a removal), or R1 for *X* accused".

`state == 2 && after_owner == 0xFFFF && write.holds && !write.acked &&` owner
fencing/fenced/unfenced is satisfied by *any* free the holder journals before it
acknowledges *X*, whether or not its R1 has begun. A faulty controller holder
may therefore free a fenced node's line word early — with the IOAPIC's
redirection entry still naming *X*, which D-150's R1 exists to avoid — and the
check accepts it.

Reproducer, `review45::review45_checker_accepts_early_free_by_holder`
(`review45.rs:242`): node 0 claims GSI 5 (on node 1's IOAPIC), node 0's member
word is made *fencing*, the holder has **no** reclaim record for node 0 at all
(`reclaims.get(&0).is_none()`) and `acked[0] == 0`; journaling
`Word::Line(5)` from the holder with `taken → free, unclaimed` gives
`node(1).check() == Ok(())`.

For the model's own flow the discriminator does work — R6 runs only under the
barrier, i.e. after the writer's own ack (`nodes.rs:1611`, `clear_step` at
`nodes.rs:1742` needs all acks), and `after_take` withdraws the ack before it
re-runs R1 (`roles.rs:514-525`) — so this is a limit of the checker, not a
wrong claim about the model. The contract's own check for that write ("*X*'s
member word in R1") is no stronger, so closing it needs the reclaim state
(the writer's R1 for that role) in the journal.

### 4. Three pass-45 tests survive a wrong model they exist to pin (minor)

Mutations applied to the scratch copy, one at a time, reverted after each
(`run_mut.sh`); each is a change the contract forbids.

- `r1_controller_holder_frees_line_word_on_holder_death_and_takeover`
  (`pass45.rs:116`) says "the successor … runs R1 in `after_take`, frees the
  line word". Deleting `self.r1(node, g);` from `Model::after_take`
  (`roles.rs:525`) — the exact call the test is named for — leaves the test
  green (`m2`, passed); removing `r1_done`'s `r1` call (`nodes.rs:1353`) as
  well is what fails it (`m11`, `left: Fenced, right: Dead`). The free in that
  test comes from the successor's `r1_done` at R5, so the test does not test
  `after_take`.
- `harm_accepts_coresilent_only_for_d171_orphaned_fresh_start` (`pass45.rs:372`)
  does not exercise `awaiting_entry` (`nodes.rs:620`) or `width() > 1`
  (`nodes.rs:619`): dropping either from `accuse_self`'s
  `d171_start_timeout` leaves the test green (`m6`, `m7`, passed). Part B is
  rejected by `member.state() == Starting` and Part D keeps an un-entered core,
  so neither condition is ever the one that decides.
- `checker_rejects_r6_write_of_line_word` (`pass45.rs:43`) says "nor can a
  non-holder", but both cases are rejected by `!write.acked` alone: dropping
  `&& write.holds` from `line_r1` leaves it green (`m1`, passed). Nothing in
  the suite covers `journal`'s `holds` for line words.

### 5. The `Sleep` half of the new guard is untested (minor)

`model/src/system.rs:367`. Removing that one `&& !model.timer_draining(position)`
leaves all ten `scenarios::pass45::` tests green (`m10`). The
`capped_timer_interrupt_offers_only_timer_on_draining_core` test arms nothing
that would sleep, so half of the delivered guard is only exercised by the long
runs, which do not fail on it.

### 6. Line words are only ever freed on `Governs::IoApic` controllers (minor, latent)

`model/src/nodes.rs:1317` (`Model::r1`, the `governs == IoApic` gate) and
`model/src/table.rs:906` (`holds_line_controller`). Contract line 1356 and
"R1 of the controller's holder" (line 1702, 829) name the *controller role
holder*, whatever the controller is; D-150 lists the ARM64 distributor
(`GICD_ICACTIVER`) and the RISC-V APLIC.

`Machine::boot_table` builds role records from `self.ioapics` alone
(`boot.rs:1196`); no `Governs::GicDistributor` or `Governs::Aplic` role exists
anywhere in the model (`grep GicDistributor\|Governs::Aplic model/src` is
empty). On an ARM64 or RISC-V machine the model frees a dying node's line words
only because the harness keeps the example's x86 IOAPIC role
(`machine(Arch::Aarch64, …)` leaves `Machine::example().ioapics` in place,
`scenarios/mod.rs:75`). A machine without an IOAPIC role, or with a GIC/APLIC
controller role, would have no writer for R1's line free: `holds_line_controller`
returns `false`, `judge_write` rejects it, and `r6_held_back`'s `lined`
(`nodes.rs:1448`) stops R6 for good. Latent today, wrong as soon as the
controller roles of D-150 are modelled.

### 7. A stalled R6 is invisible to `System::check` (minor)

`model/src/check/machine.rs:686-708` (`check_r6_proof` judges only nodes that
already read `Dead`) and `scenarios/explore.rs:118` (`assert_live` judges live
nodes and accusations, not a node stuck in `Fenced`).

A node that stays `Fenced` because its generation's line word is never freed
passes every check for ever. Mutation `m11` (both `r1` calls that can free it
removed: `roles.rs:525` and `nodes.rs:1353`) leaves the holder `Fenced` and
`m.run(60 * MS)` — i.e. `assert_eq!(self.sys.check(), Ok(()))` after every
advance — green; only the test's own `assert_eq!(m.state(holder), MemberState::Dead)`
(`pass45.rs:133`) fails. D-150 gives the freeing writer
(`taken → free` by the controller holder at R1, line 1356), and nothing checks
that it happens.

---

## What I checked and found correct

**Line words (D-150).** No state was found in which a line word naming a dead
generation is left taken with nobody to free it, and R6 stalled:

- `review45_line_of_a_non_holder_dies` (`review45.rs:149`): a level line
  claimed by node 0, which does not hold the IOAPIC (node 1 does); node 0
  killed. Node 0 reaches `Dead` and the word is gone — the holder's `r0`/`r1`
  frees it (`r0_effects` → `r1`).
- `review45_line_claimed_in_flight_then_death` (`review45.rs:170`): the same
  with the claim still in flight (`Waits`). Same result.
- `review45_holder_killed_with_another_nodes_line_taken` (`review45.rs:186`):
  the *holder* is killed while another node holds line 5. The holder reaches
  `Dead` and the claimant's word stays exactly
  `taken(Node(claimant), g)` — the role take-over does not touch a live
  claimant's line.
- The dying holder's *own* line is freed both by the successor's `after_take`
  and, independently, by `r1_done` at R5 (mutation `m2`: deleting the
  `after_take` call still reaches `Dead`); the successor's `take_step` always
  runs, because a unit role is never vacant (`role_hand` refuses
  `RoleKind::Unit` with no target, `roles.rs:128`; boot gives every unit role a
  holder, `boot.rs:1263`) and `unit_successor` finds the live node. A node that
  dies while it holds the controller keeps its word only while no node is live,
  and then no node runs R6 either.
- `check_r6_proof`'s new line (`check/machine.rs:707`) does fire:
  `review45::review45_check_r6_proof_line_fires` (`review45.rs:288`) inserts a
  line word naming a dead generation and `System::check()` returns
  `"R6: a dead generation's line word still taken"`.
- `Model::r1` cannot free a line after the writer acknowledged: `after_take`
  zeroes `acked` before re-running R1 (`roles.rs:514`), and `r1_done` calls
  `r1` before writing `acked` (`nodes.rs:1611`), so no lawful R1 write lands
  after the ack in the model. `Table::holds_line_controller` agrees with
  `Model::ioapic_role` for every layout the model can build (one role record per
  entry of `machine.ioapics`, same `position`/`object` test).

**Timer draining.** `timer_draining` (`sched.rs:708`) implies
`Model::due_now`, so `Event::Timer` is always offered while a core drains (when
it is awake and not silent), and `Event::Wake`'s loop (`system.rs:599-630`)
does end: `program_timers` re-arms the hardware timer at `now` only while
`event.due_remaining`, and no due processing creates a new due event at `now`
(`replenish` sets `throttled = None` and a deadline after `now`, `sched.rs:600`;
`fire` only wakes a thread). No starvation was found: a suppressed `Ipi` stays
pending in `pending_ipis` and is offered again once nothing is due. Other cores
are untouched (`system.rs:349` is per `position`, `system.rs:367` per core).

**New checks.** The due-step check (`check/sched.rs:345-374`) fires on a wrong
model: mutation `m5` (`due_remaining` forced false and `due_total` set to the
taken count, so the 17th timer silently stays) fails
`timer_interrupt_due_step_checked_by_event_log` with
`"node 0: 47: armed timer"`. The `SILENT` cross-check
(`check/machine.rs:284-313`) fires: mutation `m4` (exemption forced true) fails
`silent_running_owned_core_rejected_by_check` with the check's own message. The
`Park` exemption is no wider than the state it covers: the only sites that set
`cores[p].silent = true` on a `Running` core are `park_all` (`nodes.rs:646`) and
`seal_step` (`nodes.rs:2074`, `nodes.rs:2119`), both of which have just pushed
`HwAction::Park { core }`, and a park in flight is either executed (`act`,
`system.rs:855`) or waits for a core that is asleep, where
`hardware != Running`.

**`Harm::accepts` and `start_timeout_accusations`.** The record
(`nodes.rs:615-628`, `table.rs:556`) is written exactly when D-171 (lines 697,
2207) explains the accusation: `CoreSilent`, `Starting`, not resuming, more than
one core, a core still awaiting entry, at or after `START_NS` from
`start_entered` on membership time. It is written at the instant of the
accusation, from the accusing node's own state, not by sampling. A real fault
cannot hide behind it in a way the model decides: at any instant the record is
written, D-171 itself licenses the self-accusation (an un-entered core at
`START_NS`), so there is no state in which the record explains something D-171
does not. `Harm::accepts` (`scenarios/mod.rs:399-408`) requires, besides the
record, a multi-core fresh start, an orphaned starter, self-reported evidence
and a matching panic generation, and it rejects the four cases of the pass-45
test (that test is green unmutated).

**Recovery counters.** `core0_recovery_due_now` (`nodes.rs:2526`) no longer
consults `sweep_due`, and `recovery_in_progress` (`lib.rs:2111`) no longer
consults `handing`: mutation `m9` (`recovery_coincides` forced true) fails
`healthy_sweep_does_not_set_time_event_step_16_in_recovery`, so the test does
distinguish the two. `Model::due` samples the recovery before and after
`reserve_step` (`sched.rs:784-791`), so a start or fence begun inside the step
counts. Seed 181's coincidence B (`combinations.rs:2601-2712`) asserts a real
fence round (`fence_due`), not a sweep: `core0_recovery_due_now()` is asserted
at `fence_at` with node 1 fencing, and the cap, `due_taken == 16`,
`hw_timer == Some(fence_at)` and the armed-timer arithmetic are all asserted
there, so the "reached during a recovery" row for `TIME_EVENT_STEP` rests on a
genuine recovery. What I could not do is rerun the long run: the report's
"every row reads yes" is unverified here (see below).

**Mutation table** (all on a scratch copy of `26a3c37`, `cargo test -p
dodos-model --lib`, debug, one mutation at a time, reverted after each):

| # | Mutation | Test | Result |
|---|---|---|---|
| m1 | `check/table.rs`: drop `&& write.holds` from `line_r1` | `checker_rejects_r6_write_of_line_word` | passed — finding 4 |
| m2 | `roles.rs`: drop `self.r1(node, g)` from `after_take` | `r1_controller_holder_frees_line_word_…` | passed — finding 4 |
| m3 | `system.rs`: `if false` on the `Wake`/`ShallowReturn` follow-up | `wake_drains_due_events_at_now_before_ipi` | failed, `left: 17, right: 0` |
| m4 | `check/machine.rs`: `let parking = true;` | `silent_running_owned_core_rejected_by_check` | failed, `left: Ok(()), right: Err("SILENT: …")` |
| m5 | `sched.rs`: `due_remaining` false, `due_total` = taken | `timer_interrupt_due_step_checked_by_event_log` | failed, `Err("node 0: 47: armed timer")` |
| m6 | `nodes.rs`: drop `&& … any(|c| c.awaiting_entry)` | `harm_accepts_coresilent_…` | passed — finding 4 |
| m7 | `nodes.rs`: drop `&& self.width() > 1` | `harm_accepts_coresilent_…` | passed — finding 4 (condition redundant) |
| m9 | `sched.rs`: `let recovery_coincides = true;` | `healthy_sweep_does_not_set_time_event_step_16_in_recovery` | failed, `assertion failed: !m.bounds.time_event_step_16_in_recovery` |
| m10 | `system.rs`: drop the `Sleep` guard only | all `scenarios::pass45::` (10 tests) | all passed — finding 5 |
| m11 | `roles.rs` and `nodes.rs`: drop both `after_take`'s and `r1_done`'s `self.r1(…)` | `r1_controller_holder_frees_line_word_…` | failed, `left: Fenced, right: Dead`; every `check()` in `run` passed — finding 7 |

## Not verified

I did not run `./verify` or the three long runs (`every_combination_…`,
`directed_combinations_reach_all_74`, `many_seeds`) on `26a3c37`; my runs were
one seed of the first (`DODOS_SEED=181`) and the ten unit tests of `pass45.rs`,
in a scratch copy, in debug. The report's durations, its bounds table, and
"zero R6 stalls across all three runs" are therefore unconfirmed by me — nothing
I read contradicts them, but I did not reproduce them.
