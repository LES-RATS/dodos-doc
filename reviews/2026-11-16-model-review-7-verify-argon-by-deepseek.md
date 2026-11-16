# Verification of review 7 (`gemini-4-argon`)

- **Report verified:** [2026-11-16-model-review-7-gemini-argon.md](2026-11-16-model-review-7-gemini-argon.md), `2afc901` of `dodos-kernel`, `3bc7597` of `Docs` (contract)
- **Method:** I read the claim, the contract sentences and the model code it names, then wrote and ran my own test or my own mutant of `model/src`, in a copy of `dodos-kernel` at `2afc901` under `/tmp/va/kernel` (`nix develop -c ./verify`, `DODOS_PAGE=16k|32k`). Every `./verify` below is the one `AGENTS.md` names; a warm run is about 61 s.
- **Ring order:** no scenario below needs two messages of one ring reordered. `System::deliver` is not called anywhere in my tests; the one scenario that would have needed it (a surviving node taking the device *while* the dead node's last message is still in flight) is not used.
- **My tests and scripts:** `scratchpad/review7/tests/verify-argon/` of this session (full text of the test file in the appendix).

## Verdicts

| # | Finding | Verdict | Side | Severity | How I know |
|:--|:--|:--|:--|:--|:--|
| a | §1.1 a device identifier word wedged when its owner dies and starts fresh before a survivor takes over | **CONFIRMED IN PART** | contract (the model does what the contract says) | a PCI device is refused to every other node for as long as its former owner lives (`denied`); not isolation, and not for ever | my `a_identifier_word.rs`: a survivor is refused `Err(Denied)` after the owner restarts; the word is released when the owner dies again; the owner's own next generation takes it |
| b1 | §3.1 cut 2: `recovery.rs` checks once per millisecond instead of once per 100 µs, the journal cleared between checks | **CONFIRMED IN PART** | tests | one event in ten unchecked in that file; no hole in `./verify` | mutant: old check kills it in 17 tests, new check passes 44/44; but `liveness.rs`, untouched by the cut, still kills it |
| b2 | §3.1 cut 1: the 8,192-split loop of `blocks.rs` checks every 512 splits | **CONFIRMED** | tests | one event in 512 unchecked; a mutant survives the whole `./verify` | mutant: new `blocks.rs` 14/14 and `./verify` rc=0; the pre-pass-13 per-split check fails it (`52: write of an ownership word`) |
| b3 | §3.1 cut 3: `--test debug` left out of the 16k and 32k runs | **CONFIRMED** | tests | a geometry-dependent rule is checked on one geometry only | mutant `faults.rs`: `./verify` rc=0; `DODOS_PAGE=16k cargo test --test debug` fails 2 of 21 tests |
| b4 | §3.1 weakening 4: `K::ok` accepts up to 64 steps for every `UntypedRetype` | **CONFIRMED IN PART** | tests | step counts not pinned in `calls.rs`; no hole in `./verify` | mutant: `calls.rs` 347/347 at 4k, 16k, 32k; pre-pass-13 `K::ok` fails it; but `adversarial_nodes` (32k) still kills it |
| b5 | §3.1 weakening 5: `same_seed_gives_the_same_state` weakened | **NOT REPRODUCED** | tests (wording) | the report's description of both versions is wrong; one comparison is gone, no mutant of `model/src` needs it | see §B.5 |
| c | §2: 59 survivors, killed by 4 new tests | **CONFIRMED IN PART** | tests | the claims hold for the 15 I drew, with two corrections: three mutants do not build under `-D warnings`, and the new test they hang most kills on is red on clean code | 15 mutants reproduced, all survive `./verify` at `2afc901`, all 15 killed at an assertion that passes on the clean tree; 4 of the 8 "equivalent" mutants re-checked |
| d | §4: `./verify` is deterministic | **CONFIRMED** | tests | none | 3 runs: rc=0, 44 targets, 2,486 tests, 985 distinct names, identical per-target counts |

**Counts.** 8 findings, 8 verdicts: **CONFIRMED 3** (b2, b3, d), **CONFIRMED IN
PART 4** (a, b1, b4, c), **NOT REPRODUCED 1** (b5). §1.1 (a) is confirmed as a
defect of the contract, not of the model; the one finding I could not
reproduce at all is b5. Four of the eight are confirmed but with a consequence
the report states and I could not (`b1`, `b4`: the cut leaves a hole in one
test file, not in `./verify`), or with evidence it cannot use (c: its kill
test is red on clean code).

## A. §1.1 — the identifier word of a dead generation

### The claim

Node 0 attaches a PCI device (its identifier word becomes *taken* by node 0's
generation), node 0 dies, the survivors reach the barrier, and node 1 starts
node 0 fresh before any node takes the device. From then on the word reads
*taken* by a generation that is gone while its owner's member word reads
*live*, so rule 3 of taking (a **dead** owner) no longer applies, and every
other live node is refused the device.

### My test

`model/tests/a_identifier_word.rs`, five tests, three nodes (`Machine::example`
plus a third core), no `deliver`:

| Test | Asserts | On `2afc901` |
|:--|:--|:--|
| `a_word_of_a_dead_generation_is_denied_to_every_other_live_node` | after `core_start(fresh)`, node 1's `iospace_attach` of the same device is `Err(Denied)` | **passes** (the wedge is there) |
| `a_survivor_takes_the_device_the_dead_generation_left_behind` | the same call must succeed, as it does for the chunks of that generation | **fails**: `the survivor was refused the device: Err(Denied)` |
| `the_wedge_ends_when_the_owner_dies_again` | after node 0's *next* generation is dead too, node 1's attach is `Done` | **passes** (so the wedge is not for ever) |
| `node_0_alone_retakes_the_word_of_its_dead_generation` | rule 1: node 0's new generation may take its own earlier generation's word | **passes** |
| `a_device_entry_of_a_dead_generation_is_busy_to_every_other_live_node` | the same rule on the ownership word of a **device table entry** (`memory_take`, kind 1) | **passes** (new finding, §A.4) |

`sys.check()` is asserted after every step: the model's own invariants hold
throughout, including `check_identifiers` (88), which compares only the words
of the *current* generation and so cannot see the stale one.

### Where the fault is: the contract, not the model

- Contract line 342, the state of `iospace_attach`: *"the device's identifier
  word is taken by another node that is not dead, or fails its check
  (`denied`)"*. At the moment node 1 calls, the word is taken by node 0 and
  node 0 is live — so `denied` is exactly what the contract asks for, and
  [`memory.rs:539`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:539)
  (`holds_identifier`) plus
  [`abi/src/machine.rs:413`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:413)
  (`may_take`) implement it faithfully.
- Rule 3 of taking, line 773: *"a node whose member word is **dead**
  ([Cores](#cores)), whatever the state and the generation in the word"*. A
  live owner in a later generation is not dead, so nothing frees the word.
- R6, line 1110, clears *"every chunk whose ownership word reads taken by
  X's generation … every entry of X's grant table … every entry of X's use
  table"*. Identifier words and device table entries are not in that list.
- Why the word outlives its owner at all: identifier words live in the machine
  table ([`table.rs:178`](/Users/btw/Documents/repos/dodos-kernel/model/src/table.rs:178))
  and every node keeps a copy, equal after each event. When the dead node's
  model is dropped, [`system.rs:448`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs:448)
  (`drop_dead`, the model's R6) clears map counts, page classes, grants and
  uses of that generation but not its identifier words, so every survivor's
  copy still names it — and the freshly started node 0 is seeded from those
  copies.
- Line 1124 promises: *"**After dead**, every ownership word and device entry
  owned by X is free for any live node, and for X's next generation"* — but
  only through rule 3, so the promise lapses the moment X is live again.
- The contract already has the right notion elsewhere: line 1104, R3,
  *"Generation g is over when X's member word reads dead, or names a
  generation other than g: a supervisor may start X again before Y has seen
  it dead, and the pinned entry must not wait for a state that will not come
  back."* That sentence exists precisely for this race; rule 3 was not given
  it.

So the review's diagnosis of the mechanism is right, but its side is not:
this is a gap in the contract (R6's list and rule 3), and the model is
faithful. Two further corrections to §1.1:

1. **"permanently wedged", "for ever" — wrong.** The word is released when
   the owner dies again (my third test), and the owner's own next generation
   can always take it (rule 1, my fourth test). What is lost is the device
   *for the other nodes, while the owner stays live*. Severity: a device held
   hostage, not an isolation breach — the word errs on the safe side.
2. **Step 6's "even though generation g of node X died" is right, but the
   words "`Err(Error::Denied)` for every other live node" hold only for
   `iospace_attach`**: for a *device table entry* the same wedge shows as
   `Err(Error::Busy)` from `memory_take` (§A.4).

### The two corrections it proposes

**Correction 1 (preferred): free the identifier words of the dead generation
in R6, with the analogue of the invariant that forbids a block on a stale
word.** Right, and it works. I implemented it — in `System::drop_dead`, which
is the model's R6, remove every identifier word equal to *taken (X, g)* for
the generation that just died — and then:

- `a_survivor_takes_the_device_the_dead_generation_left_behind` passes (the
  other two "documents the wedge" tests flip, as they should);
- `./verify` stays green, unchanged: rc=0, 44 targets, 2,486 tests passed,
  the same counts as the clean tree (the patch is in `drop_dead`, which is the
  model's R6: `t.identifiers.retain(|_, &mut raw| raw != dying)` with `dying`
  the word taken by `(node, g)` of the generation that just died).

Three things the correction must also say, which the report does not:

- the gate's rule (line 778: it *"refuses to write a word whose owner the
  rules above do not allow"*, and check 52 in
  [`check/table.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:88)
  with `_ => dead`) must allow the *cleared* value for a node that is not the
  owner, exactly as line 1110 allows it for chunks — today identifier words
  are not even journaled (`memory.rs:518` writes the map directly), so
  invariant 52 never sees them;
- R6's sentence (line 1110) must name identifier words and device entries;
- the invariant analogue must be "no identifier word is taken by a generation
  that is over", not "by a generation that is not the current one", because
  during a reclaim the word legitimately names the dying generation until the
  walk reaches it.

**Correction 2 (`may_take` also accepts `word.generation() != generation`):
rejected, on two counts.**

- *Wrong side.* Rule 3 of taking is the contract's (line 773) and the gate
  implements it (check 52, `_ => dead`). A model-only change would make the
  model take a word the gate refuses, i.e. put the model out of the contract
  it exists to model.
- *Wrong as written, and the model says so.* For a node's word, the
  generation field is 0 when the word is *free* (contract, line 766: *"0 when
  it is free"*), and a node's generation is never 0. So `generation() !=
  generation(owner)` is true for **every free word owned by a live node**, and
  the other live node's free word becomes takeable — which is not rule 3 but
  its opposite. I applied the correction to `Table::may_take` and ran
  `./verify`: it fails at
  `blocks::a_word_given_to_another_live_node_is_refused`, `Err("52: write of
  an ownership word")` — the model's own invariant 52 refuses the write the
  changed `may_take` allowed. If this route is taken at all, the condition
  must be `state() == Taken && word.generation() != generation(owner)`, and it
  must be a change of rule 3 in the contract, not of the model.

### New finding next to (a): the same gap for device table entries

`memory_take` (kind 1) has the same rule and the same gap: R6 (line 1110)
does not clear *device entries* either, and line 1124 names them. My fifth
test takes the 2 MB device entry on node 0, kills node 0, starts it fresh, and
node 1's `memory_take` of that entry answers `Err(Busy)` — the entry, and the
device range it covers, is lost to every other node while node 0 lives. Test:
`a_device_entry_of_a_dead_generation_is_busy_to_every_other_live_node`
(passes on `2afc901`, i.e. documents the behaviour); after node 0 dies again,
node 1 takes the entry (`Done`), which is rule 3 as before. Severity: as (a);
side: contract. The review missed it although its own line-1124 quote names
device entries.

## B. §3 — what was cut to make `./verify` fast

`git diff d4e883b..2afc901 -- verify model/tests` is faithful to the report:
the geometry runs went from `DODOS_PAGE=16k cargo test -p dodos-model` to ten
named targets on 16k and 32k, `S::run` went from 100 µs to 1 ms per check, the
split loop went from a check per split to one per 512, and `K::ok` began
diverting every `UntypedRetype` to `made_in(call, 64)`.

For each cut I wrote one mutant of `model/src` that writes an ownership word
that is legal before and after an event and illegal inside it (or, for b4, one
that changes a step count), then ran it against the old check and the new one.
The scripts are `b_mutants.py` (`apply b1|b2|b3|b4`, `old-check b1|b2|b4`) and
`b5_note.md`.

| Cut | My mutant of `model/src` | Old check | New check | `./verify` at `2afc901` |
|:--|:--|:--|:--|:--|
| b1 `recovery.rs` | an illegal write of a chunk's ownership word in `recovery_step`, undone in the same step, at every step at `now % 1_000_000 == 200_000` | **kills** it: 17 of 44 tests fail, `Err("node 0: 52: write of an ownership word")` | **passes**: 44/44 | **kills** it: `liveness.rs` fails (6 tests) |
| b2 `blocks.rs` | the same write in `memory_split` at `spare == 400`, i.e. split 400 of the 8,192 | **kills** it: 13 passed, 1 failed (`52`) | **passes**: 14/14 | **passes: rc=0** |
| b3 `--test debug` | `thread_write_regs` uses `0x7F80_0000_0000`, the user end of the 4 KB geometry, on every geometry | **kills** it: `DODOS_PAGE=16k cargo test --test debug` fails 2 of 21 (`breakpoint_words_are_judged_word_by_word…`, `debug_port_and_entropy_rules_that_no_test_pinned`) | **passes** | **passes: rc=0** |
| b4 `K::ok` | a 65,536-byte object on 32 KB pages clears 32 KB per step, so a two-page `aspace`/`iospace` takes two steps where one reached its end | **kills** it: `DODOS_PAGE=32k cargo test --test calls` fails in many tests | **passes**: `calls.rs` 347/347 at 4k, 16k, 32k | **kills** it: `adversarial_nodes::f5a_step_5_of_a_hand_over_runs_r1_for_a_node_already_dying` (32k) |
| b5 `same_seed…` | none — see B.5 | — | — | — |

### B.1 The `recovery.rs` interval (CONFIRMED IN PART)

The cut is real and my mutant proves the mechanism the report describes: the
journal (`table.writes`) is cleared by `Model::begin` at every event
(`sched.rs:113`), so an illegal event at a tick the check never visits leaves
no trace. With the d4e883b `S::run` (a check after every 100 µs) the mutant
dies in 17 tests; with the 2afc901 one (a check per millisecond) all 44 tests
pass.

What does not hold is the consequence: `./verify` still kills the mutant. The
events between two of `S::run`'s millisecond checks are also seen by
`liveness.rs`, which runs every crash point of fifteen scenarios and checks
its invariants at offsets that sweep the whole millisecond
(`liveness.rs:330`). I tried both a residue-based trigger (200 µs of every
millisecond) and the 100 µs grid: both die in `liveness`. So the cut leaves a
hole in `recovery.rs`, not in the gate. A mutant that survived `./verify`
through this cut would have to be reached only by a recovery step that
`liveness` never takes; I did not find one and I cannot claim there is none.

### B.2 The `blocks.rs` loop (CONFIRMED)

This is the only cut where I have a complete demonstration: the mutant
(`spare == 400`, one split in the middle of the loop) passes the new
`blocks.rs` (14/14) *and* the whole `./verify` (`rc=0`, 44 targets, including
the 16k and 32k reruns of `blocks`), and the pre-pass-13 loop
(`k.ok(take)` / `k.go(split)`, which checks after every split) fails it with
`Err("52: write of an ownership word")`. Nothing else in the suite visits that
split.

### B.3 `--test debug` on 16k and 32k (CONFIRMED)

The report's premise holds: `debug.rs` is the only test file that pins
`REG_DR0..=REG_DR3 < user_end`. My mutant (the 4 KB `USER_RANGE_END` on every
geometry) survives `./verify` — including both geometry runs, `faults` among
them — and dies in `DODOS_PAGE=16k cargo test -p dodos-model --test debug`
(2 of 21 tests; on 32k the geometry's user end is larger and the mutant is not
caught). Adding `--test debug` to the geometry loop costs 0.02 s.

Correction to §3.3: its table of the seven omitted binaries has the wrong
count for every one of them, and the total is right only by coincidence. The
real counts, identical at 16k and 32k, all passing:

| Binary | Report | Real | Binary | Report | Real |
|:--|--:|--:|:--|--:|--:|
| `cores` | 15 | **24** | `liveness` | 16 | **6** |
| `debug` | 8 | **21** | `recovery` | 102 | **44** |
| `irq` | 9 | **16** | `sched` | 14 | **45** |
| `tasks` | 12 | **20** | total | 176 | 176 |

The same `102` appears in §3.2 ("Pass 13's `recovery.rs` passes completely
(102 passed)"), where the binary has 44 tests.

### B.4 `K::ok` and step counts (CONFIRMED IN PART)

`K::ok` does divert every `UntypedRetype` to `made_in(call, 64)`
(`calls.rs:249`), so `calls.rs` no longer pins step counts — my mutant (two
steps where one reached the end, on 32 KB pages) passes `calls.rs` at all
three geometries, and the pre-pass-13 `K::ok` (a single `DONE`) fails it in
many tests.

But here too `./verify` keeps the coverage: on 32 KB pages a two-page
`iospace` is exactly 65,536 bytes, and `adversarial_nodes`, `memory` and
`nodes` retype those objects with their own assertions. `./verify` with the
mutant fails in
`adversarial_nodes::f5a_step_5_of_a_hand_over_runs_r1_for_a_node_already_dying`.
So the weakening is real inside `calls.rs` and empty at the gate, because the
only sizes for which the step count can change are the ones every other binary
also retypes.

### B.5 `same_seed_gives_the_same_state` (NOT REPRODUCED)

I could not build a mutant of `model/src` that the old check kills and the new
one lets through, and the report's description of the two versions is wrong.
It says the old test *"ran seeds `0`, `1`, `2` twice each from scratch (`6`
independent `run_seed` executions) and compared both state hashes and `Reached`
sets for all 3 seeds"*; `git show d4e883b:model/tests/property.rs` runs seeds
`0` and `1` twice each — four runs. And the new test does not compare `Reached`
for seed 0 only against a re-run of `0, 1, 2`: it compares the state hash of
seeds 0 **and 1** against an independent run made in parallel at the start of
the suite, and compares seed 0's `Reached` between two consecutive runs. The
one thing dropped is the equality of seed 1's `Reached` between two runs.

For the old check to fail, a mutant must be non-deterministic between runs (a
deterministic one changes both runs alike). To escape the new check that
non-determinism must show in `Reached` only, not in the state hash of seeds 0
and 1, and must miss seed 0 — whose `Reached` is still compared twice in the
same process. A first-run-versus-later-run effect (a `OnceLock`, a warmed
cache) is caught by that; anything else has to be tuned to the number of
syscalls the two seeds make, which is not a mutation of a rule. `b5_note.md`
records the reasoning. So §3.1's row 5 is a real but empty weakening, and the
counts in it are wrong.

## C. §2 — the 59 survivors

### How I picked

Fifteen of the 59 ids of §2.3, by sorting the ids by `id × 2654435761 mod 2^32`
and taking the first fifteen: **89, 136, 52, 141, 120, 133, 23, 57, 146, 2, 70,
15, 138, 83, 151** (three of the six ABI ones fell in, so the draw is spread
over the groups the report's §2.3 sorts the survivors into: 2, 15, 23 from its
first group; 52, 57 from the second; 70, 83, 89 from the third; none from the
fourth; 120, 133, 136, 138, 141, 146, 151 from the fifth).

I reconstructed each mutant from the review's own `build_mutants.py` (its ids
are the index in that list) rather than from its prose, and ran the whole
`./verify` on each, then the review's four new test functions
(`r7_system_unit_survivor_tests`, `r7_abi_survivors`, and the two
`aspace_map` ones, copied unchanged into `c_apply_argon_tests.py`).

### Result

| id | file: what it weakens | `./verify` at `2afc901` | Killed by the review's tests at |
|:--|:--|:--|:--|
| 89 | `memory.rs`: `identifier_key` `segment << 16` → `<< 8` | rc=0 | `r7_system_unit_survivor_tests`, `system.rs:1384` |
| 136 | `remote.rs`: `asked` for `Body::Revoke` ignores `e.grantee == from && e.generation` | rc=0 | same, `system.rs:1239` |
| 52 | `check/table.rs`: R6 cleared word, `owner == after_owner` → `!=` | rc=0 | same, `system.rs:1412` |
| 141 | `remote.rs`: `Body::Revoke` misdirection check removed | rc=0 **only after a clippy-clean edit** (`let _ = held;`; as written `error: unused variable: held`) | same, `system.rs:1239` |
| 120 | `recovery.rs`: `isolate` wakes a `Move` source with `Err(Gone)` too | rc=0 | same, `system.rs:1565` |
| 133 | `remote.rs`: `granter` ignores `r.serial == serial` | rc=0 **only after a clippy-clean edit** (`let _ = serial;`) | same, `system.rs:1239` |
| 23 | `machine.rs`: `GLOBAL_READ_ONLY` accepts device leaves | rc=0 | `r7_abi_survivors`, `abi/src/lib.rs:1175` |
| 57 | `check/table.rs`: invariant 56 drops `zero == table.none.len()` | rc=0 **only after a clippy-clean edit** (`let _ = zero;`) | `r7_system_unit_survivor_tests`, `system.rs:1450` |
| 146 | `remote.rs`: `Body::Moved` misdirection check removed | rc=0 | same, `system.rs:1239` |
| 2 | `start.rs`: `START_MEMORY_UNFENCED_ACCEPTED` `1 << 4` → `1 << 5` | rc=0 | `r7_abi_survivors`, `abi/src/lib.rs:1160` |
| 70 | `memory.rs`: `aspace_map` partial continuation ignores `m.rights` | rc=0 | `r7_aspace_map_…`, `memory.rs:965` |
| 15 | `lib.rs`: `Geometry::valid`, `user_end <= 1 << (bits-1)` → `<` | rc=0 | `r7_abi_survivors`, `abi/src/lib.rs:1168` |
| 138 | `remote.rs`: `Body::Answer` misdirection check removed | rc=0 | `r7_system_unit_survivor_tests`, `system.rs:1239` |
| 83 | `memory.rs`: `aspace_protect` gate chunk boundary `>` → `>=` | rc=0 | `r7_aspace_map_…`, `memory.rs:954` |
| 151 | `remote.rs`: `revoke_anchor` does not free a `Pinned` grant | rc=0 | `r7_system_unit_survivor_tests`, `system.rs:1638` |

15 of 15 survive `./verify` at `2afc901` (three only after the clippy-clean
edit above; as literally written they fail `cargo clippy -D warnings`, so they
are survivors of `cargo test`, not of `./verify`). 15 of 15 are killed by the
review's new tests, at an assertion *before* the one that fails on clean code
(see the next paragraph), so the kills are real.

Rows and the panic lines are in `c-results.jsonl`; the driver is `c_run.py`,
the fifteen definitions `c_mutants_selected.json`.

### The two things that must be said about those kills

1. **`r7_system_unit_survivor_tests` fails on the clean tree**, at
   `model/src/system.rs:1716`:
   `assertion failed: n0.table.beacons[0].observations.iter().any(|o| o.node == 2)`.
   The report's claim that all four new tests pass on unmodified `2afc901`
   (`rc = 0`) is therefore false, and §2.3's evidence — "all 59 are killed
   (`rc != 0`)" — is not evidence at all for the mutants it pins on that test:
   a suite that is already red says nothing. I checked the *location* of each
   panic instead: `1239`, `1384`, `1412`, `1450`, `1565` and `1638` all sit
   before `1716` and pass on the clean tree, so the mutants are genuinely
   detected; but that is my check, not the report's. Until the assertion at
   `1716` is fixed, that test cannot be used as a kill.
2. **Three of its "survivors" do not build under `-D warnings`**, so they do
   not survive `./verify` (§B and the table above): #57, #133 and #141.

### The 8 mutants called equivalent — 4 checked

| id | equivalence claimed | My check |
|:--|:--|:--|
| 92 | `holds_identifier`'s `mine` needs no generation test, because rule 1 of taking already accepts a word taken by an earlier generation of the same node | sound: `may_take` returns true for `Owner::Node(self)` whenever `self.generation() != generation`, so `mine \|\| may_take` is unchanged; `./verify` rc=0 |
| 153 | `reserve_taken`'s generation test is unreachable because `role_claim` reaches it only when the holder is dead | argument matches the mutant (it is in `reserve_taken`, not in `check_roles` as its label in `build_mutants.py` says); `./verify` rc=0. I did not prove the call-site guarantee, so I confirm only "survives and the argument is plausible" |
| 161 | `sched_bind`'s `in_move(context)` is covered by `scheds[&context].home.is_some()`, because `thread_move` keeps `home` until `moved()` completes | sound for the code I read (`moves.rs:70`, `moves.rs:212`); `./verify` rc=0 |
| 80 | `class_of`'s `table.kept` test is covered by `frame.kept`, because `boot` makes a kept frame per kept range and no block may overlap kept memory | consistent with `boot.rs:151` and `blocks.rs:58`; `./verify` rc=0. Not proof, but no path I found breaks it |

The other four (13, 14, 27, 61) I did not check.

## D. §4 — determinism

Three full `./verify` runs on an untouched `2afc901` (`d_three_runs.sh`):

| Run | Exit | Targets | Tests | Distinct test names |
|:--|:--|--:|--:|--:|
| 1 | 0 | 44 | 2,486 | 985 |
| 2 | 0 | 44 | 2,486 | 985 |
| 3 | 0 | 44 | 2,486 | 985 |

Per-target counts identical (`diff` empty), set of test names identical after
sorting. The only differences in the three logs are durations, and the
interleaving of the harness's parallel threads on one line — which is why the
comparison sorts names before diffing. The report's §4 claim of a
deterministic `./verify` holds. Its ten-run table gives wall times of
31.2–31.7 s, about half of what I measure here (61 s warm); that is a different
machine, not a different result.

## What the review got wrong, and what it missed

1. **A broken kill test.** `r7_system_unit_survivor_tests` is red on clean
   `2afc901` (`system.rs:1716`), which voids its own §2.3 evidence and its claim
   that all four new tests pass unmodified.
2. **Three mutants that do not compile under `./verify`** (#57, #133, #141
   leave an unused binding and `cargo clippy -D warnings` refuses them).
3. **§3.3's table of the seven omitted binaries** has the wrong count for every
   one of them (section B.3), and the `102` for `recovery.rs` recurs in §3.2.
4. **§3.2's mutant for cut 2** quotes *"`let step = CLEAR_STEP_BYTES.min(bytes)`"*
   at `model/src/caps.rs:443`; no such line exists — the step is
   `(untyped.clean + CLEAR_STEP_BYTES).min(end)` in `take`, and whether an
   object takes one step or two is legal either way under the contract
   (*"at most 64 KB"*), which is why the step-count claim needs the framework
   of the old test rather than a contract rule.
5. **Two consequences it draws that do not hold**: the two interval cuts do
   not open a hole in `./verify` (B.1, B.4), because `liveness.rs` and
   `adversarial_nodes` cover the same events.
6. **Missed next to (a)**: the same wedge on device table entries
   (`memory_take`, kind 1), and the fact that identifier words are not
   journaled at all, so no invariant, old or new, can see them.

## Appendix — `model/tests/a_identifier_word.rs`, full text

Copied from `scratchpad/review7/tests/verify-argon/a_identifier_word.rs` of this
session. Run as `nix develop -c cargo test -p dodos-model --test
a_identifier_word` at `2afc901`: 4 passed, 1 failed
(`a_survivor_takes_the_device_the_dead_generation_left_behind`, `Err(Denied)`).
The failing test is the one that states what the contract's symmetry asks for;
`sys.check()` is asserted after every step, so the model's invariants hold in
every test.

```rust
//! (a) A device identifier word, taken by node 0's generation, stays taken
//! after that generation died and node 0 started fresh before any survivor
//! took the device: every other live node is refused the device.
//!
//! Contract: `Docs/architecture/kernel-interface.md` at 3bc7597.
//! - line 342 (rules of `iospace_attach`): "the device's identifier word is
//!   taken by another node that is not dead, or fails its check (`denied`)";
//! - line 1124 (the reclaim barrier): "**After dead**, every ownership word
//!   and device entry owned by *X* is free for any live node, and for *X*'s
//!   next generation";
//! - rule 3 of taking (line 773): "a node whose member word is **dead**",
//!   and rule 1: "*X* itself, if the word is free, or taken by a generation
//!   of *X* other than *g*";
//! - R6 (line 1110): the node that reclaims clears the chunks of the
//!   ownership table, the grant entries and the use entries of *X*.
//!   Identifier words are not in that list, and no invariant of the model
//!   (`check_identifiers`, 88) forbids a word taken by a generation that is
//!   not the owner's current one.
//!
//! Ring order: no step here needs two messages of one ring reordered, so
//! `System::deliver` is never called and the scenario is one a machine can
//! run.

use dodos_abi::ObjectKind::IoSpace;
use dodos_abi::*;
use dodos_model::*;

const DONE: Outcome = Ok(Output::Done);
const WAITS: Outcome = Ok(Output::Waits);
const UT: SlotAddr = SlotAddr::own(25);
const MS: u64 = 1_000_000;
/// The `iommu` root of unit 0 in every start-up space (three nodes).
const IOMMU: u32 = 19;
/// One PCI device: bus 0, device 1, function 0.
const DEVICE: u64 = 0x10;
const SPACE: u32 = 100;

const fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

const fn core(n: u32) -> SlotAddr {
    SlotAddr::own(16 + n)
}

fn retype(kind: ObjectKind, size: u64, destination: u32) -> Syscall {
    Syscall::UntypedRetype {
        untyped: UT,
        kind,
        size,
        page: PageSize::Page as u64,
        memory: 0,
        destination: s(destination),
    }
}

fn stop(n: u32, mode: u64) -> Syscall {
    Syscall::CoreStop {
        core: core(n),
        mode,
    }
}

fn start(n: u32, mode: u64) -> Syscall {
    Syscall::CoreStart {
        core: core(n),
        mode,
        image: 0,
        module: 0,
    }
}

fn attach(iospace: u32) -> Syscall {
    Syscall::IoSpaceAttach {
        iommu: s(IOMMU),
        iospace: s(iospace),
        device: DEVICE,
    }
}

fn three() -> (System, Vec<ObjId>) {
    let mut machine = Machine::example();
    let mut third = machine.cores[1];
    third.hw_id = 4;
    machine.cores.push(third);
    machine.membership.stale_ms = 10;
    machine.membership.stuck_ms = 10;
    machine.membership.sweep_ms = 100;
    System::boot(&machine).unwrap()
}

/// Node 0 attaches `DEVICE` in a fresh iospace of its own and waits for the
/// holder of the unit role (node 1) to write the context entry.
fn node_0_takes_the_device(sys: &mut System) -> u32 {
    let t0 = sys.node(0).object_at_start(START_SLOT_THREAD);
    assert_eq!(sys.apply(0, t0, retype(IoSpace, 0, SPACE)), DONE);
    assert_eq!(sys.apply(0, t0, attach(SPACE)), WAITS);
    sys.run(sys.now() + MS, MS / 10);
    assert_eq!(sys.node(0).woken(t0), Some(&DONE));
    assert_eq!(sys.check(), Ok(()));
    sys.member(0).generation()
}

/// Node 1 kills node 0 and the peers reach the barrier.
fn node_0_dies(sys: &mut System, t: &[ObjId]) {
    assert_eq!(sys.apply(1, t[1], stop(0, CORE_STOP_KILL)), DONE);
    sys.run(sys.now() + 10 * MS, MS / 10);
    assert_eq!(sys.member(0).state(), MemberState::Dead);
    assert_eq!(sys.check(), Ok(()));
}

#[test]
fn a_word_of_a_dead_generation_is_denied_to_every_other_live_node() {
    // The finding: the device is refused to node 1 while node 0's next
    // generation is live, even though generation 0 of node 0 died, its
    // iospaces are gone, and its devices were blocked by R1 and
    // acknowledged by the barrier.
    let (mut sys, t) = three();
    let first = node_0_takes_the_device(&mut sys);
    node_0_dies(&mut sys, &t);
    assert_eq!(sys.apply(1, t[1], start(0, CORE_START_FRESH)), DONE);
    assert_eq!(sys.member(0).state(), MemberState::Live);
    assert_eq!(sys.member(0).generation(), first + 1);
    assert_eq!(sys.check(), Ok(()));

    assert_eq!(sys.apply(1, t[1], retype(IoSpace, 0, SPACE)), DONE);
    assert_eq!(sys.apply(1, t[1], attach(SPACE)), Err(Error::Denied));
}

#[test]
fn a_survivor_takes_the_device_the_dead_generation_left_behind() {
    // What the contract's symmetry with memory blocks asks for: generation 0
    // of node 0 is over (dead, and started again with a later generation),
    // so its identifier word must be free for a live node, as its chunks
    // are. This fails on 2afc901: the call returns `Err(Denied)`.
    let (mut sys, t) = three();
    let _first = node_0_takes_the_device(&mut sys);
    node_0_dies(&mut sys, &t);
    assert_eq!(sys.apply(1, t[1], start(0, CORE_START_FRESH)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(IoSpace, 0, SPACE)), DONE);
    let outcome = sys.apply(1, t[1], attach(SPACE));
    assert!(
        matches!(outcome, Ok(Output::Done) | Ok(Output::Waits)),
        "the survivor was refused the device: {outcome:?}"
    );
}

#[test]
fn the_wedge_ends_when_the_owner_dies_again() {
    // "For ever" is wrong: rule 3 of taking frees the word once the owner's
    // member word reads dead, whatever the generation in the word. The
    // wedge therefore lasts as long as the owner node stays live.
    let (mut sys, t) = three();
    let first = node_0_takes_the_device(&mut sys);
    node_0_dies(&mut sys, &t);
    assert_eq!(sys.apply(1, t[1], start(0, CORE_START_FRESH)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(IoSpace, 0, SPACE)), DONE);
    assert_eq!(sys.apply(1, t[1], attach(SPACE)), Err(Error::Denied));

    assert_eq!(sys.apply(1, t[1], stop(0, CORE_STOP_KILL)), DONE);
    sys.run(sys.now() + 10 * MS, MS / 10);
    assert_eq!(sys.member(0).state(), MemberState::Dead);
    assert_eq!(sys.member(0).generation(), first + 1);
    // Node 1 holds the unit role, so the attach completes at once.
    assert_eq!(sys.apply(1, t[1], attach(SPACE)), DONE);
    assert_eq!(sys.check(), Ok(()));
}

#[test]
fn node_0_alone_retakes_the_word_of_its_dead_generation() {
    // Rule 1: the word is not lost to its owner's next generation, only to
    // the other nodes.
    let (mut sys, t) = three();
    let _first = node_0_takes_the_device(&mut sys);
    node_0_dies(&mut sys, &t);
    assert_eq!(sys.apply(1, t[1], start(0, CORE_START_FRESH)), DONE);
    let t0 = sys.node(0).object_at_start(START_SLOT_THREAD);
    assert_eq!(sys.apply(0, t0, retype(IoSpace, 0, SPACE)), DONE);
    // Node 0 does not hold the unit role, so the context entry waits.
    assert_eq!(sys.apply(0, t0, attach(SPACE)), WAITS);
    sys.run(sys.now() + MS, MS / 10);
    assert_eq!(sys.node(0).woken(t0), Some(&DONE));
    assert_eq!(sys.check(), Ok(()));
}

// ---------------------------------------------------------------------------
// The sibling the review missed: the same rule, on the ownership word of a
// device table entry (`memory_take`, kind 1), which R6 does not clear either
// (contract line 1110: chunks, grants and uses; line 1124 promises "every
// ownership word and device entry owned by X").

fn device_entry_at_2mb(sys: &System) -> u32 {
    (0..sys.node(0).device_count())
        .find(|&i| sys.node(0).device_entry(i).base() == 2 << 20)
        .expect("the 2 MB device range") as u32
}

fn take_entry(place: u32, destination: u32) -> Syscall {
    Syscall::MemoryTake {
        control: s(START_SLOT_MEMORY_CONTROL),
        kind: 1,
        place: place.into(),
        size: 0,
        destination: s(destination),
    }
}

#[test]
fn a_device_entry_of_a_dead_generation_is_busy_to_every_other_live_node() {
    let (mut sys, t) = three();
    let entry = device_entry_at_2mb(&sys);
    // Node 0's driver takes the device entry (D-113: the node where the
    // driver runs takes the entry with `memory_take`).
    assert_eq!(sys.apply(0, t[0], take_entry(entry, 100)), DONE);
    assert_eq!(sys.check(), Ok(()));
    node_0_dies(&mut sys, &t);
    assert_eq!(sys.apply(1, t[1], start(0, CORE_START_FRESH)), DONE);
    assert_eq!(sys.member(0).state(), MemberState::Live);

    // Node 1 cannot take the entry of the generation that died: the same
    // wedge as for the identifier word, reported as `busy`.
    assert_eq!(sys.apply(1, t[1], take_entry(entry, 100)), Err(Error::Busy));
    assert_eq!(sys.check(), Ok(()));

    // And it is released when node 0's next generation dies as well.
    assert_eq!(sys.apply(1, t[1], stop(0, CORE_STOP_KILL)), DONE);
    sys.run(sys.now() + 10 * MS, MS / 10);
    assert_eq!(sys.member(0).state(), MemberState::Dead);
    assert_eq!(sys.apply(1, t[1], take_entry(entry, 100)), DONE);
    assert_eq!(sys.check(), Ok(()));
}
```
