# Review of lot E (mistral): `model/src/scenarios/{cores,crossing,membership,mistral,pass17,pass18,pass19,pass20,pass21,reviews,units}.rs`

Repository: `/private/tmp/dodos-pr3-final` (branch `model`, head `6312868`). I read
the eleven files whole, in the order the brief gives, plus the guidance
(`AGENTS.md`, `model/README.md`, `.claude/skills/dodos-rust/SKILL.md`,
`.claude/skills/rust-1-100/SKILL.md`) and the parts of the rest of the crate I
needed to check the tests' claims (`scenarios/mod.rs` whole; excerpts of
`rings.rs`, `locks.rs`, `boot.rs`, `sched.rs`, `nodes.rs`, `cores.rs`,
`system.rs`, `units.rs`, `memory.rs`, `irq.rs`, `check.rs`, `check/machine.rs`,
`check/node.rs`, `check/table.rs`, `check/memory.rs`, and constants in `abi/`).
I changed nothing in the clone; I copied it to `/private/tmp/dodos-pr3-E-mistral`
for the runs below.

Verification run (in the copy): all tests of the eleven modules pass as they
stand —

    cd /private/tmp/dodos-pr3-E-mistral && cargo test -p dodos-model --lib -- \
      scenarios::cores scenarios::crossing scenarios::membership scenarios::mistral \
      scenarios::pass17 scenarios::pass18 scenarios::pass19 scenarios::pass20 \
      scenarios::pass21 scenarios::reviews scenarios::units
    test result: ok. 264 passed; 0 failed; 0 ignored; finished in 11.85s

I also checked that the tests can fail where their names claim a guard: I
mutated `Model::freeze_unmapping` in the copy to leave the record
`Unmapping` on a failed unit (instead of emptying it), and
`scenarios::mistral::f7_an_unmap_whose_unit_failed_empties_the_record_and_keeps_the_map_count`
failed as it should (killed by the per-step check, invariant "node 0: 36: list
of the records of a space"), then restored the file. So that test's "empties
the record" half is guarded, through the check, not through a direct
assertion — not a finding, noted because the name suggests otherwise.

## Findings

### 1. The table in `reviews.rs` names four tests that do not exist — severity: should be fixed

File: `model/src/scenarios/reviews.rs`, header table, lines 31, 36 and 57.

    //! | DeepSeek 4: an interrupt entry and an untyped under L2 | `deepseek_4_*` here |
    //! | DeepSeek 10: the gate lock last and counted in *k* | `cores::under_l2_a_call_takes_its_locks_in_the_order_of_their_kind_the_gate_lock_last` |
    //! | Ninth review 6: the order of L2 | `pass17::under_l2_a_call_records_its_locks_*`, `cores::the_check_refuses_a_lock_order_the_contract_forbids` |

What is wrong: the four backticked test names — `deepseek_4_*`,
`cores::under_l2_a_call_takes_its_locks_in_the_order_of_their_kind_the_gate_lock_last`,
`pass17::under_l2_a_call_records_its_locks_*`,
`cores::the_check_refuses_a_lock_order_the_contract_forbids` — appear nowhere
else in the repository; no function with those names (or a prefix of them)
exists in any `.rs` file. All four are about the L2 locking variant, whose
model and tests left the branch with D-138 (README, "What it does not model":
"the order by kind, the tries and their two rounds, … the bound *k*, their
tests and the L2 values … left with it"). The table's own preamble (lines 7–9)
says that findings "about mechanisms the decided shape removed … have no
test: the table says so" — these four rows do not say so; they point at tests
a reader cannot open. The only test that does exist for the row is
`cores::the_check_refuses_a_lock_the_contract_forbids` (`cores.rs:513`), whose
name differs from the one the table gives.

How I know: I extracted every backticked reference in the table (84 of them)
and matched each against all `fn <name>(` in the repository. Exactly these
four (plus prose tokens like `Release`, `parked`, `r6_inflight`, which are
not test names) do not resolve; every other reference, including
`explore::crossing_*`, `explore::waiter_*`, the `kernel_shape_*` rows, the
`pass17::*` rows, `mistral::f3_*`, the `abi` test
`a_fence_record_indexes_its_last_stops_by_core_number_modulo_64`
(`abi/src/tests.rs:2477`), `model/tests/blocks.rs`, `checker.rs` and
`check/tests.rs`, does resolve. Command and result:

    grep -rn "under_l2\|the_check_refuses_a_lock_order\|deepseek_4" model abi model/tests
    → only model/src/scenarios/reviews.rs:31,36,57

### 2. A comment in `units.rs` describes the opposite `hang` flag — severity: question

File: `model/src/scenarios/units.rs`, lines 366–368, in
`a_plain_role_of_a_fenced_holder_can_be_claimed_a_reserve_role_only_once_it_is_dead`.

    // Node 1 hangs without its handler on a class-2 core: it is fenced by
    // INIT, and dead once the barrier holds.
    m.sys.hang(1, true);

What is wrong: `System::hang(core, nmi)` sets `Hardware::Hung { nmi }`, and
per `model/src/system.rs:24-26` the flag says "whether its kernel can still
run the handler of the fence's signal". In `System::stop` (`system.rs:607–641`)
a x86-64 core in `Hung { nmi: true }` is parked by the fence's NMI (the
handler runs); `Hung { nmi: false }` on a non-booted core outside VMX root is
the one stopped "by INIT". So the comment ("without its handler … fenced by
INIT") describes `hang(1, false)`, while the code passes `true`. The test
passes either way here — both arms park a class-2 core that is not the
bootstrap core and not in VMX root — so this is a false comment, not a wrong
assertion; the test ran green in the run above.

## Cross-checks that came out clean (so the next reviewer need not redo them)

- The credit arithmetic agrees across files: `REQUESTS_PER_PEER = 16`,
  `SENDS_PER_PEER = 8`, `SENDS_RESERVED_FOR_MANAGE = 2`,
  `RING_KERNEL_ENTRIES = 64`, `RING_ANSWER_RESERVE = 34` (`abi/src/ring.rs`).
  `crossing::node_send_is_busy_beyond_…` (limit 6 = 8−2, then 8 with `manage`),
  `mistral::f11` (16 request credits), `pass17::reserve_keeps_room_…`
  (30 pings → 34 free / 34 owed = 11 for the `ReportAsk` + 23×1; a 28-item
  `Report` = 85 words = 11 entries = `RING_MESSAGE_ENTRIES_MAX`, since
  `RING_HEADER_BYTES = 16`, `RING_ENTRY_BYTES = 64`) all match
  `check_reserve` in `check/machine.rs:322` and `ring_room` in `rings.rs:286`.
- The boot floor `CORE_ANSWER_NS > 2·N·H + D` (strictly; `boot.rs:745–772`,
  `Measured::healthy_wait` in `locks.rs:168`) is exactly what
  `pass20::the_start_up_refuses_a_core_answer_ns_…` (12.5 ms refused, 8.5 ms
  accepted), `pass21::deepseek12_9` (2×64×10 µs + 5 µs = 1.285 ms > 1 ms
  refused) and `pass21::deepseek12_m25` (10 ms exactly refused, "not above")
  assert; the three agree with each other and with the code.
- Handles: `handle = core × 192 + (vector − 48)` (`irq.rs:289`,
  `IRQ_VECTOR_FIRST = 48`, `IRQ_TABLE_ENTRIES = 192`), matching pass17's
  `50 − 48`, pass17/pass18's `core * 192 + k`, pass21's `a * 192`.
- `request_due = started + core_answer_ns + stopped_time` (`sched.rs:606`)
  matches `pass21::deepseek12_7`; `membership_now = now − stopped_time`
  (`nodes.rs:608`) matches the two `pass20` stopped-time tests.
- `domain_range` (`units.rs:238`: `per = (domains−2)/nodes`, first `1+slot·per`,
  inclusive end `(slot+1)·per`) matches pass17's
  `each_node_slot_takes_its_domain_numbers_…` (domains = 256 → per = 84) and
  the start-up refusal (`boot.rs:655-663`: per ≥ 1 required → domains = 4
  refused, 5 accepted for 3 slots).
- `start_barrier` asks `all_cores & !(1 << self)` (`cores.rs:405`), matching
  `pass20`'s `asked == 0b110`, pass21's `0b101` (called from core 1), and the
  give test's `0b10` including the idle core.
- Error strings asserted in the lot exist verbatim in the checks:
  "WINDOW: …" (`check/node.rs:28`), "96: a line word beyond the last" and
  "96: line words and claimed lines" (`check.rs:369,393`),
  "59: more tables unhooked …" (`check/table.rs:477`),
  "R0: run twice for one generation", "RESERVE: …" (`check/machine.rs`).
- `CrashReason::CoreSilent = 9` (`abi/src/debug.rs:156`), matching the
  "reason 9" comment in `cores.rs`.

## Files read whole

- `model/src/scenarios/cores.rs` (542 lines)
- `model/src/scenarios/crossing.rs` (837)
- `model/src/scenarios/membership.rs` (757)
- `model/src/scenarios/mistral.rs` (433)
- `model/src/scenarios/pass17.rs` (823)
- `model/src/scenarios/pass18.rs` (715)
- `model/src/scenarios/pass19.rs` (804)
- `model/src/scenarios/pass20.rs` (815)
- `model/src/scenarios/pass21.rs` (658)
- `model/src/scenarios/reviews.rs` (542)
- `model/src/scenarios/units.rs` (611)
- `model/src/scenarios/mod.rs` (345, the harness)
- `AGENTS.md`, `model/README.md`, `.claude/skills/dodos-rust/SKILL.md`,
  `.claude/skills/rust-1-100/SKILL.md`

## Not read

- `model/src/scenarios/checker.rs` and `explore.rs` (other reviewers' lots).
- The rest of the model crate beyond the excerpts cited above (full files:
  `rings.rs`, `locks.rs`, `boot.rs`, `system.rs`, `units.rs`, `cores.rs`,
  `sched.rs`, `nodes.rs`, `memory.rs`, `irq.rs`, `check*`, `lib.rs`, etc. were
  only grepped/read in the ranges named).
- `abi/` beyond the constants and items cited; `model/tests/`; the `verify`
  script beyond its head; the kernel side (none exists here — the PR is the
  two crates `abi/` and `model/`).
