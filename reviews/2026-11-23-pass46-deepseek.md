# Review of pass 46 (`26a3c37..5fc1333`, branch `model`, head `5fc1333`)

The assistant checked every finding (23 November 2026): all seven accepted. Finding 2 is a missing test, not a fault: `Model::r1_walking` compares the generation, so the stale-record scenario holds only under the reviewer's mutation. Findings 1 and 5 are one: the drain and check 47 must cover every due instant (`due_now`) of every node. Answered by pass 47.

Reviewer: DeepSeek V4.1 Flash (Mistral Vibe), 23 November 2026. Read-only on
`/private/tmp/review-46/tree`, `dodos-kernel` and `Docs`; every mutation and
reproducer ran in a `cp -a` copy at `/private/tmp/review-46/scratch/base`
(reproducers in `model/src/scenarios/review46.rs` of that copy, registered as
`mod review46;`, driver `/private/tmp/review-46/scratch/mut.py`). Cargo through
`/nix/var/nix/profiles/default/bin/nix develop -c …`.

Line numbers are those of `5fc1333`. The full debug library suite (1106 tests,
15 ignored) takes 132–172 s there; I ran it under most mutations below.

---

## Findings

### 1. Check 47 cannot see a call that runs while *another* node's core drains (major)

`model/src/lib.rs:1564-1567` (`Model::apply`, the flag is set from the caller's
own node only), `model/src/check/sched.rs:374-377` (check 47),
`model/src/system.rs:335-353` (the drain). Contract line 602: "*the reference
model processes every due event at its instant before any call at that
instant*" — no node is named.

The drain itself is right: `System::apply` fires the capped timer interrupts of
every node's draining cores before the call, as the pass-46 brief asked ("do it
for every node, not only the caller's"). The **check** is not: a call carries
one node's `EventLog`, and `call_while_draining` is computed in `Model::apply`
from `(0..self.width())` of the calling node. A call on node 1 that begins while
node 0's core 0 still has due events is therefore invisible to every check, and
no test in the suite reaches that shape either.

Mutation (`mut.py drain_caller_node_only`, different from the report's): keep
the drain but restrict it to the caller's node —

```rust
let draining = self.nodes.iter().enumerate()
    .filter(|(slot, _)| *slot == node as usize)     // added
    .find_map(|(slot, model)| { … });
```

`cargo test -p dodos-model --lib` (all 1106): **passes**, 0 failed. So the half
of finding 1 that the brief singled out can be deleted from the model and
neither `pass46::a_call_takes_the_due_events_left_at_its_instant_first` nor
`pass46::checker_rejects_a_call_while_a_core_of_its_node_drains` nor any other
test or check notices. The report's own mutation table only shows that removing
the drain *entirely* fails the two tests; that is the same-node case.

Fix: have `System::apply` record, before the call, whether any core of any node
was draining (a field on the call's `EventLog`), and have check 47 judge that;
or at least a test where node 1 calls while node 0 drains.

### 2. `line_r1`'s "R1 walks" evidence does not pin the generation (minor)

`model/src/nodes.rs:1355-1359` (`Model::r1_walking`),
`model/src/check/table.rs:94` and `:100` (`line_r1`). Contract line 1702 and the
R1 word at line 1335: "*the generation it concerns (32 bits), a state (0 none, 1
walking, 2 done) and a cursor*"; line 1356: the free is the holder's "*at R1 for
X accused*".

`r1_walking(role, node, generation)` reads the writer's reclaim record for
`node` and requires `r.generation == generation` before using "R1 on that role
has not been recorded yet". The journal only carries the boolean, so the checker
accepts the boolean. Drop that conjunct:

```rust
.is_some_and(|r| r.generation == generation && !r.r1.contains_key(&role))
→
.is_some_and(|r| !r.r1.contains_key(&role))
```

Full library suite: **passes**. `pass46::checker_rejects_a_holders_line_free_
before_its_r1_walks` uses a node with **no** reclaim record at all, so it pins
only the "no record" case.

Consequence (the same family as the pass-45 finding 3, narrowed but not closed):
take node 0, which died once already — its holder keeps `reclaims[0]` with
generation 1 and no `r1` entry for the IOAPIC role. Node 0 is accused again in
generation 2 and claims line 5 (word `taken(0, 2)`). A faulty IOAPIC holder
frees that word with `LineFree::R1 { walking: true }` without ever running R1
for generation 2; `judge_write` accepts it, because the stale record makes
`walking` true. `D-150`'s whole point — that the word is freed *at the walk that
masks the line* — is not enforced.

### 3. `line_r1`'s `!write.acked`, the clause that keeps R6 out of line words, has no test (minor)

`model/src/check/table.rs:100`. Contract line 1358: "*R6 frees no line word: it
stops at one that still names X's generation*"; line 829 lets the holder's gate
write a line word *free* only "in the call that masks it with *release* or at
R1".

Dropping `&& !write.acked` from `line_r1` leaves **all ten `scenarios::pass45`
tests and all eighteen `scenarios::pass46` tests green**. The pass-45 test that
is named for this (`pass45::checker_rejects_r6_write_of_line_word`) journals the
free with `line_free: None`, so it is refused by the journal clause, not by the
ack. A holder that frees a dead generation's line word in R6, after its `acked`,
is accepted by the checker as if it were R1.

### 4. Invariant 96's "a line irq that is not removing holds its word" half has no test (minor)

`model/src/check.rs:431`, `match must_hold.is_subset(&held) && held.is_subset(&may_hold)`.
Contract line 1356 and the line-word table: a *taken* word is the claim.

Replacing the condition with `held.is_subset(&may_hold) {` (dropping the
`must_hold ⊆ held` half): the whole library passes (1106). The
`held ⊆ may_hold` half is exercised by `pass46::a_removal_frees_the_line_word_
in_the_holders_masking_call`; the other half — the one that says a live line irq
must hold its word, i.e. that an unmasked redirection entry always has a word
behind it — is not exercised anywhere, although it is the half that a real
regression (a word freed while the irq is armed and not removing) would break.

### 5. The drain and check 47 key on `timer_draining`, but the due instant of a core is `due_now` (minor)

`model/src/sched.rs:708-710` (`timer_draining` = `hw_timer ≤ now && has_due_at`),
`model/src/system.rs:333-353` (the drain), `model/src/lib.rs:1564-1565` (the
flag), against `model/src/system.rs:375-382` (`events()` offers `Event::Timer`
when `due_now`, i.e. `hardware(p) ≤ now`) and `model/src/sched.rs:749-754`
(`hardware` = the min of the programmed timer, the core's `CORE_ANSWER_NS`
deadline and the recovery reserve).

`program_timers` sets `hw_timer` from `future_timer`, which never includes the
request deadline or the reserve; so on a core whose only due instant is one of
those two, `due_now` is true (the interrupt is offered) and `timer_draining` is
false (nothing is drained, and the check sets nothing). `due()` treats the
request deadline as a due event in so many words ("*the due event of the core's
invalidation request*"), and `next_instant` stops the clock at it, so this is a
due instant by the model's own reading.

Reproducer, `review46::a_call_runs_before_a_core_answer_deadline` (scratch):
node 0 of two cores, a `Completes::Barrier` request on core 0 (`asked: 0b10`,
`started: now`), `move_clock(now + core_answer_ns)`; the test asserts
`due_now(0)`, `!timer_draining(0)`, that `events()` contains
`Event::Timer { node: 0, position: 0 }`, then applies a call and asserts
`!node(0).event.call_while_draining`. **Passes** on `5fc1333`: the call ran
before a due event of the core and check 47 reported nothing.

Not a missed fault today: the same state is refused by another check
(`check_requests`, `model/src/check/node.rs:375-382`, `CORE_ANSWER_NS: a request
older than the bound on a node that did not accuse itself`) —
`review46::the_same_call_through_the_harness_fails_another_check` passes with
that message. So the failure is caught afterwards and with the wrong diagnosis,
which is why this is minor; but the drop-in fix is to use `due_now` (or
`hardware`) in both the drain and the flag, and to say so at
`check/sched.rs:374`.

### 6. The check's exemption for a sleeping core is a latency, not a state (minor)

`model/src/lib.rs:1565`: `!self.cores[c].silent && self.cores[c].asleep == 0 &&
self.timer_draining(c)`. The drain exempts a core by its hardware state
(`self.awake`, `model/src/system.rs:427-437`: `Suspending` or `Asleep`), and
`asleep` is the state's *exit latency* (`sync_sleep`, `system.rs:664-676`).

The two agree in every state the harness reaches today, because the idle tables
used in the scenarios give a losing state a latency of 200 µs. They disagree for
a context-losing state of exit latency 0, which `node_idle` accepts:
`idle_table` (`model/src/nodes.rs:2637-2672`) requires only that latencies
increase, and the contract (line 1821) sets no minimum. A core in `Suspending`
or `Asleep` with latency 0 then reads as awake to the check and as asleep to the
drain, and a call would be refused with check 47's message for a lawful state.
I could not build a reproducer (it needs a due event on a core with no thread
and no armed timer, which nothing in the harness creates), so this is a reading,
not a demonstration; the fix is to key the flag on the same predicate the drain
uses.

### 7. The liveness exemption is wider than its own comment (minor)

`model/src/scenarios/explore.rs:132-163` (`assert_no_stalled_r6`). The comment
says the only lawful hold-back is "*a grant of `(x, g)` whose grantee is itself
frozen … with a leaf count kept by a failed IOMMU unit (D-142, D-149)*". The
code accepts **any** counted use entry whose grantee is `Fencing`, `Fenced` or
`Unfenced`:

```rust
counted && matches!(table.member(entry.grantee).state(),
    MemberState::Fencing | MemberState::Fenced | MemberState::Unfenced)
```

`counted` is `grant_still_counted` itself; nothing asks whether an IOMMU unit has
failed, which is the sentence that makes the stall lawful (line 397: "*the
barrier of a node whose granted frame a record emptied so still counts in the
holder's use entry never holds … since the holder's R2 for it is never done*").
A frozen grantee whose count is stuck for a reason R2 would have cleared is
therefore excused, and the check's own message does not distinguish it: on a
counted-grant failure it prints `lined=false, attached=false` and the whole line
map, which points at nothing.

Two narrower notes on the same function: `driver` requires `!m.sys.node(n).
is_silent(0)` — a live node whose *core 0* is silent is not consulted, though
its other cores are — and `for x in 0..table.nodes` judges only `Fenced` nodes,
so a node stuck in `Fencing` is not judged at all.

---

## What I checked and found correct

**The release free (item 2).** The word is freed in exactly the holder's masking
call and nowhere else:

- `Model::submit_for` (`model/src/units.rs:618-636`) writes it *free* in the
  same call that writes the masked entry into the unit, after
  `operands_allowed` (`units.rs:434-456`) has accepted it: a `release` on a
  *claimed* op is refused (`units.rs:453-456`, bit 35 is masked only), and a
  masked op whose word names another node is refused (`units.rs:434-450`), so a
  foreign release can free only the requester's own word. The write is
  conditional on the word naming the requester *and its generation*, which is
  what the journal then records (`LineFree::Release`), so the checker's
  `line_release` clause and the gate read the same word.
- A node that holds the controller itself goes through the same path: the
  removal is still a request (`model/src/irq.rs:541-583`, and `submit_for`
  refuses nothing for a self-request), which
  `pass46::the_holders_own_removal_frees_the_line_word_in_its_masking_call`
  pins.
- `Model::irq_destroyed` (`irq.rs:733-742`) writes no line word, and nothing in
  the answer path (`answer_unit`, `unit_complete`) writes one.
- `judge_write`'s `let freed = !line && held && …`
  (`model/src/check/table.rs:109`) means an owner's free of a line word is
  never lawful except as `line_release`/`line_r1`; a node that does not hold the
  controller fails `write.holds` (`table.rs:966-971`: for a line,
  `holds_line_controller`).
- Holder dies between the masking and the answer: the word is already free, and
  the successor holder re-serving the request writes nothing (the guard at
  `units.rs:626-629`); the requester's removal ends at its own step. Requester
  dies with its removal in flight: the word stays `taken(requesters' gen)` and
  the holder's R1 frees it (`Model::r1`, `model/src/nodes.rs:1319-1342`), which
  `pass45::r1_controller_holder_frees_line_word_on_holder_death_and_takeover`
  and `pass46::the_successors_r1_at_the_take_over_frees_the_line_word_before_r5`
  cover; if nobody can free it, `assert_no_stalled_r6` now fails the run.

**Invariant 51 (item 3).** The exemption `irq.removing` is what line 775 allows:
`irq_claim` is `busy` on "*the source is a line whose word the rules of taking
refuse to this node or that this node's current generation already holds*", and
after the release the node no longer holds it, so the claim is lawful. Two
entries cannot both deliver: the free and the unit's masked state are written in
the same call (`submit_for` removes the line from `unit.lines` /
`unit.masked` before writing the word), and the new claim programs a different
vector, so `interrupt_on(position, vector)` cannot find two matches. Level lines
are additionally masked at the unit. `must_hold`/`may_hold` in invariant 96
(`check.rs:404-432`) describe the window correctly: the word may read either way
while the request asks and must be free once it is answered.

**The `Sleep` guard (item 6).** The writer's proof is right, twice over:
`timer_draining(p)` gives `hw_timer ≤ now`, and `hardware(p)` is the min of
`hw_timer` with two more instants (`sched.rs:749-754`), so `due_now(p)` holds and
`sleep_state` (`cores.rs:828-850`) returns `None` on its own; and with the
earliest instant at `now` the entry fit `e[0] + e[1] < until` is satisfied by no
entry (`until = 0`). Removing `!model.timer_draining(position)` from the sleep
arm of `System::events` is therefore sound, and `a_draining_core_does_not_sleep`
still pins the behaviour through `sleep_state`.

**Controller roles (item 5).** `Machine::boot_table` (`model/src/boot.rs:1194-1209`)
gives every line controller the architecture's kind, and
`table::governs_lines` (`table.rs:395-403`) is the only test in
`ioapic_role` (`units.rs:190-205`), `holds_line_controller` (`table.rs:929-949`),
`operands_allowed` (`units.rs:365-372`), `Model::r1` (`nodes.rs:1317`),
`Model::items` (`roles.rs:1030-1046`), the faulty report (`roles.rs:1142-1149`)
and the boot unit states (`boot.rs:1353-1357`). `grep Governs::IoApic` leaves
only `boot.rs:1195` (the x86-64 choice) and the `governs_lines` body: nothing
still assumes an IOAPIC on ARM64 or RISC-V, and `pass46::the_gic_distributor_and_
aplic_roles_free_line_words` covers both kinds end to end (removal, R1 under a
fence, a claim again).

**D-171 and the tests that read what they judge (item 7).**
`start_timeout_recorded` (`pass46.rs:488-500`) accuses node 1 and reads node 1's
own `table.start_timeout_accusations`, so Argon's defect (node 0's table after
an accusation on node 1) is gone; `harm_refuses_core_silent_of_a_fresh_start_of_
one_core` reads `m.harm.starts` for `(1, g)` and passes the canonical table to
`Harm::accepts`, which is where `edit_table` wrote the record.
`a_start_timeout_needs_more_than_one_core` is honest that it forces the state
(`cores.truncate(1)`), which is what makes its mutation possible.

**The harness fix of `5fc1333`.** `directed_combination` now excludes the node
that must hand the IOMMU role from being the liner; the `lost` assertion in
`combined_recovery_states_between_nodes` (`combinations.rs:4865-4870`) still
guards `short_run_missed.txt` (a combination reached when measured and not now
fails), and the re-measured list of `4d9a8d6` is consistent with that guard.

## Mutations I ran (each alone, on the scratch copy, file restored after each)

Debug, `cargo test -p dodos-model --lib [<filter>]`.

| # | Mutation (file: change) | Test(s) | Result |
|---|---|---|---|
| m1 | `system.rs:335` drain restricted to the caller's node | whole suite (1106) | **passed** — finding 1 |
| m2 | `nodes.rs:1358` `r1_walking` without `r.generation == generation` | whole suite (1106) | **passed** — finding 2 |
| m3 | `check/table.rs:100` `line_r1` without `&& !write.acked` | `scenarios::pass45` (10), `pass46` (18) | **passed** — finding 3 |
| m4 | `check.rs:431` invariant 96 without `must_hold.is_subset(&held)` | whole suite (1106) | **passed** — finding 4 |
| m5 | `explore.rs:129` the liveness check made inert (`if true \|\| …`) | `a_stalled_r6_fails_the_quiet_liveness_check` | failed, "did not panic as expected" — the test works |
| m6 | `irq.rs:567` `release: false` in `irq_removal`'s masking op | `a_removal_frees_the_line_word_in_the_holders_masking_call` | failed at `pass46.rs:235`, `96: line words and claimed lines` |
| m7 | `irq.rs:138` `irq_claim` busy when the node has *any* line irq on the source | `a_released_line_may_be_claimed_again_before_its_removal_ends` | failed at `pass46.rs:312` |
| m8 | `roles.rs:524-525` `after_take` records the role in `r1` before walking | `the_successors_r1_at_the_take_over_frees_the_line_word_before_r5` | failed at `pass46.rs:456`, the word still held |
| m9 | `boot.rs:1197` RISC-V boots `GicDistributor` | `the_gic_distributor_and_aplic_roles_free_line_words` | failed at `pass46.rs:613` |
| m10 | `check/table.rs:93` `line_release` accepts any `Release { .. }` | `checker_rejects_a_release_free_for_another_requester` | failed at `pass46.rs:346` |
| r1 | `review46::a_call_runs_before_a_core_answer_deadline` | scratch reproducer | passes — finding 5 |
| r2 | `review46::the_same_call_through_the_harness_fails_another_check` | scratch reproducer | passes — the state is caught by `CORE_ANSWER_NS` |

Seven tests of `pass46.rs` sampled by mutation (m5–m10 plus m1/m2 on the two item-1
tests): five of them fail as the report says they should; the two that do not are
finding 1 and finding 2.

## Not verified

I did not run `./verify` or the three long runs (`every_combination_of_recovery_
states_is_reached`, `directed_combinations_reach_all_74`, `many_seeds`) on
`5fc1333`; my runs were the whole debug library suite (eleven times, under
mutations) and the `pass45`/`pass46` subsets in the scratch copy. The report's
durations, its bounds table and its long-run claims are therefore unconfirmed by
me; nothing I read contradicts them. The report's lenient reading of contract
line 794 ("stays dying with its vector and its line word" against "no node frees
a line word on an answer") is the one the table at 1356, operation 5's bit 35 and
the brief settle, and I agree with it: `irq_destroyed` writes no line word. No
`CONTRACT-GAP` found.
