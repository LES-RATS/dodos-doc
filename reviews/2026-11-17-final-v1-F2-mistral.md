# Review of lot F2 (mistral) — `model/tests`, 14 files

Repository: `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
Lot read whole, in the order the brief gives: `model/tests/{blocks,boot,cores,debug,faults,gate_attack,gate_classes,gate_words,generations,irq,memory,sched,tasks,verify7_deepseek}.rs`.

## What I ran

In a copy at `/private/tmp/dodos-pr3-F2-mistral` (the shared clone untouched), with the system `rustc 1.100.0`:

- `cargo test -p dodos-model` on all 14 targets of the lot: **254 tests, 0 failed** (blocks 14, boot 33, cores 13, debug 20, faults 25, gate_attack 10, gate_classes 6, gate_words 4, generations 5, irq 16, memory 37, sched 45, tasks 20, verify7_deepseek 12).
- The page-dependent subset plus `--lib` under `DODOS_PAGE=16k` and `DODOS_PAGE=32k` (what `verify` does): all pass, 0 failed, on both geometries.
- `cargo clippy --workspace --all-targets -- -D warnings`: clean, exit 0.

So no finding below is "the suite is red"; the lot is green on all three geometries.

## Findings

### 1. Stale doc comments name `thread_move`, a call removed by D-128, and promise its coverage — should be fixed

- `model/tests/cores.rs:3` (file header) and `model/tests/cores.rs:379` (doc comment on `unlike_cores_rules_that_no_test_pinned`).

Quoted (`cores.rs:1-3`):

```rust
//! Unlike cores: feature masks and the size of a thread,
//! `thread_set_features`, what a core enables, instructions retired on
//! demand, and `thread_move` between the two nodes of `Machine::example`.
```

and (`cores.rs:379`):

```rust
/// Argon F3: the order of the checks of thread_set_features and sched_count,
/// sched_count on a counted context, and thread_move with a context still
/// lent (mutants 20, 21, 24, 26, 31).
```

What is wrong: there is no `thread_move` in this repository any more. `abi/src/lib.rs:660-662` documents `GrantSignal` as "the doorbell of a grant, at the place of `thread_move`, removed by D-128", and `model/src/lib.rs:129` (`pub enum Syscall`) has no `ThreadMove` variant. No test in `cores.rs` moves a thread between nodes, so the header promises a coverage that does not exist and both comments name a call that cannot be made. How I know: `grep -rn "thread_move" /private/tmp/dodos-pr3-final/model /private/tmp/dodos-pr3-final/abi` returns exactly `cores.rs:3`, `cores.rs:379` and a comment in `abi/src/features.rs:98` ("the condition of `thread_move` on the destination node" — that one is in `abi/`, outside my lot, but it is the same staleness).

### 2. `mod common;` declared but never used in `blocks.rs` — question

- `model/tests/blocks.rs:5`.

Quoted:

```rust
mod common;
```

What is wrong: `grep -c "common::" model/tests/blocks.rs` is 0 — nothing in the file refers to the module (`blocks.rs` uses raw slot numbers, not `common::slot`). The include is dead; it compiles only because `model/tests/common/mod.rs` starts with `#![allow(dead_code)]`, and `cargo clippy --workspace --all-targets -- -D warnings` passes, so no lint catches it. How I know: the grep above; clippy run above, exit 0.

### 3. A tautological assertion that cannot fail at the end of a `gate_words.rs` test — question

- `model/tests/gate_words.rs:119`, in `a_destroyed_block_of_a_reserve_chunk_keeps_the_reserves_code`.

Quoted (with its definition fourteen lines earlier, `gate_words.rs:104`):

```rust
let chunk = 1u64 << shift;
...
assert_eq!(chunk, 1 << shift);
```

What is wrong: `chunk` is by construction `1 << shift`, so the assertion compares a value with itself and can never fail; it guards nothing. The real checks of the test are the two `m.ownership(at >> shift)` assertions above it. How I know: read of the whole file; the definition is at `gate_words.rs:104`.

### 4. A dead statement in `debug.rs` — question

- `model/tests/debug.rs:564`, in `a_node_started_fresh_keeps_its_rings_and_goes_on_from_their_sequences`.

Quoted:

```rust
    let _ = (Endpoint, Task);
```

What is wrong: both `Endpoint` and `Task` are already used elsewhere in the same file (e.g. `debug.rs:600` `retype(Endpoint, 0, 110)`, `debug.rs:608` `retype(Task, 0, 111)`), so this line does nothing — it is not even needed to silence an unused-import warning, and clippy with `-D warnings` passes both with and without it. How I know: grep for the imports' uses in the file; clippy run above.

## Things I checked and found consistent (not findings)

- Slot maps: `common::slot` (fixed slots 0-18, 19→24, 20→25, 21→64, ≥22→+64) agrees with `boot.rs`'s slot census (slots 1-15 fixed, 16-31 the machine roots, 32 empty) and with `common/mod.rs`'s header comment.
- Constants used across the lot match the source: `TREE_DEPTH = 64` (`abi/src/lib.rs:114`) with the depth-64 chain behaviour in `blocks.rs:158-170` and `boot.rs:143-157`; `CLEAR_STEP_BYTES = 65_536` (`abi/src/lib.rs:135`) with the Again-step counts in `blocks.rs:138-146`, `boot.rs:262-274`, `gate_attack.rs:499-532`; `START_SCHED_BUDGET_NS = 9_843_750` = 63/64 of 10 ms (`abi/src/lib.rs:841`) with the `cores.rs:327` test name; `DEVICE_TABLE_SPARE = 8192` (`abi/src/machine.rs:340`); `DEBUG_WRITE_MAX = 512`, `TRACE_BURST_NS = 1 ms` (`abi/src/debug.rs:22-25`) with `debug.rs`; `REG_RIP = 0`, `REGS_WORDS = 26` (`abi/src/x86_64.rs:63-65`) with `verify7_deepseek.rs:271-276` and `faults.rs`.
- `Refusal::Floors` does cover membership times ("or a time of `BootMembership` is out of its range", `model/src/boot.rs:474-476`), so `boot.rs`'s `kernel_refuses_times_of_membership_out_of_their_ranges` asserting `Floors` is correct, not a wrong variant.
- The depth convention agrees between `blocks.rs:158-170` (control copy at depth 64 refused, 63 accepted) and `boot.rs:143-157` (`TREE_DEPTH - depth` accepted copies).
- `debug.rs:619` `destroying_a_thread_with_every_link_takes_one_step_of_at_most_8_units`: the "one step" is genuinely asserted (`k.ok(CapDelete(...))` returns `Done`, not `Again`, with all 7 links present), and `K::go` runs `m.check()` after the call, so the per-call bounds the model enforces are exercised.
- `memory.rs:808-885` (`tables_follow_the_page_and_e_of_the_sixteen_kb_geometry`): `tables()`/`io_levels()` are `pub(crate)` (`model/src/memory.rs:30,375`), so the level count cannot be asserted directly; the test pins it indirectly — the 4-page untyped suffices for the iospace's tables only if 47 bits at 16 KB pages give 3 levels, otherwise the map fails or `check()` fails. I judged this sufficient, not a "tests less than its name says" finding.
- `verify7_deepseek.rs` F9 part B is conditional (`large2 <= 1 << 30`), so it runs only on the 4 KB geometry; on that geometry `Large2` is exactly 1 GB and the `MemoryTake` refusal is exercised. Intentional, not a vacuous test.

## Files read whole

- `model/tests/blocks.rs` (444), `boot.rs` (742), `cores.rs` (422), `debug.rs` (826), `faults.rs` (622), `gate_attack.rs` (593), `gate_classes.rs` (281), `gate_words.rs` (120), `generations.rs` (247), `irq.rs` (443), `memory.rs` (993), `sched.rs` (991), `tasks.rs` (549), `verify7_deepseek.rs` (791).
- Guidance: `AGENTS.md`, `model/README.md`, `model/tests/common/mod.rs`, `.claude/skills/dodos-rust/SKILL.md`, `.claude/skills/rust-1-100/SKILL.md`.

## Read for reference only (not whole, grep/sed level)

- `model/src/lib.rs` (the `Syscall` enum at :129, `apply` at :1383, step counters at :1163-1164), `model/src/boot.rs:463-488` (`Refusal`), `model/src/locks.rs` (`Cost`), `model/src/check.rs` / `check/machine.rs` / `check/node.rs` (what `check()` covers), `model/src/units.rs`, `model/src/system.rs`, `model/src/sched.rs`, `model/src/memory.rs:30,375`, `model/src/nodes.rs:1969-1975`, `abi/src/lib.rs` (constants, `GrantSignal` note at :660), `abi/src/x86_64.rs:63-146`, `abi/src/debug.rs:22-25`, `abi/src/machine.rs:340`, `abi/src/features.rs:98`, `verify`.
- Not read at all: `model/tests/calls.rs` and `model/tests/property.rs` (not in my lot), the rest of `model/src/` (including `src/scenarios/`), the rest of `abi/`, and everything outside the repository. No web search, no other directories, per the brief.

## Bottom line

No merge-stopping finding in this lot: all 254 tests of the 14 files pass on the default, 16 KB and 32 KB geometries, and clippy with `-D warnings` is clean. The four findings above are a false/stale comment pair (`thread_move`), one dead `mod common;`, one tautological `assert_eq!`, and one dead `let _ =` statement — all small, none reachable from an input.
