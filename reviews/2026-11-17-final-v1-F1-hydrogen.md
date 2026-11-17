# Review report: lot F1

## `model/tests/calls.rs`

### Finding 1 — should be fixed
- **File and line:** `model/tests/calls.rs:4073-4086`
- **Code:**
```rust
#[test]
fn cap_delete_on_an_empty_slot_of_an_own_dying_space_is_invalid() {
    let mut k = K::new();
    let inside = space_with_a_thread(&mut k);
    k.no(Syscall::CapDelete(s(30)), Error::Again);
    assert_eq!(
        k.on(inside, Syscall::CapDelete(s(100))),
        Err(Error::Invalid)
    );
    assert_eq!(
        k.on(inside, Syscall::CapDelete(s(128))),
        Err(Error::Invalid)
    );
    assert_eq!(k.on(inside, Syscall::CapDelete(s(0))), Err(Error::Invalid));
}
```
- **What is wrong:** `space_with_a_thread` creates a 128-slot `CSpace` (indices `0..128`) and runs `inside` inside it, so `inside`'s own slots are unshifted (`o(...)`). `s(100)` expands via `shifted(100)` (`model/tests/calls.rs:32-39`) to `SlotAddr::own(164)` and `s(128)` to `SlotAddr::own(192)`. Both `164` and `192` are out of range of the 128-slot table (`slots.get(...) == None` in `model/src/caps.rs:236,253`), not an in-range empty slot (`Some(Slot::Empty)`). As written, the test never exercises `Some(Slot::Empty)` on a dying space; it checks out-of-range twice and slot `0` once. It should use `o(100)` and `o(128)` (and `o(0)`).
- **How I know:** Inspected `shifted` (`model/tests/calls.rs:32-39`), `space_with_a_thread` (`model/tests/calls.rs:1093-1108`), and `Model::cap_delete` (`model/src/caps.rs:228-255`).

### Finding 2 — should be fixed
- **File and line:** `model/tests/calls.rs:1598-1610` (and `1636-1644`)
- **Code:**
```rust
#[test]
fn size_argument_is_zero_for_the_other_kinds() {
    // A thread's size argument is its feature mask (tests/cores.rs).
    let mut k = K::new();
    for kind in [ASpace, ObjectKind::Sched, Endpoint, Reply, Notify] {
        for size in [1, 7, 4096, u64::MAX] {
            k.no(retype(UT, kind, size, s(30)), Error::Invalid);
        }
        ...
    }
}
```
- **What is wrong:** `ObjectKind::Timer`, `ObjectKind::Task`, and `ObjectKind::IoSpace` also require `size == 0` in `footprint` (`model/src/caps.rs:138,146-147`), but they are omitted from `size_argument_is_zero_for_the_other_kinds`, and `timers_tasks_and_iospaces_are_made_from_an_untyped` (`model/tests/calls.rs:1636-1644`) only tests `size == 0`. No test in `model/tests/` passes a non-zero `size` to `UntypedRetype` for `Timer`, `Task`, or `IoSpace` on ordinary memory (only `calls.rs:4186` tests `Timer` with `size: 5` on device memory, which fails earlier on device kind check at `model/src/caps.rs:102-104`).
- **How I know:** Read `model/tests/calls.rs:1598-1644`, `model/src/caps.rs:100-148`, and searched all `UntypedRetype` / `Timer` / `Task` / `IoSpace` references across `model/tests/`.

### Finding 3 — should be fixed
- **File and line:** `model/tests/calls.rs:684-692`
- **Code:**
```rust
/// Every right but one.
/// Every right but `right`, and without `exec` but for an `exec` asked
/// for: the start-up capabilities of the tests have no `exec`.
fn caps_without(right: Rights) -> Rights {
```
- **What is wrong:** Line 684 (`/// Every right but one.`) is a leftover duplicate doc comment whose statement is false: for any `right != Rights::EXEC`, `caps_without` returns `NOT_EXEC.without(right)`, which omits two rights (`EXEC` and `right`).
- **How I know:** Read `model/tests/calls.rs:21,684-692`.

## `model/tests/common/mod.rs`

### Finding 4 — should be fixed
- **File and line:** `model/tests/common/mod.rs:1-2`
- **Code:**
```rust
//! What the test files share: the slots of the start-up space of
//! `Machine::example`, the same on both geometries of the tests.
```
- **What is wrong:** The comment says "both geometries of the tests", which is stale/false: `verify` and `model/README.md` run the tests on three geometries (`4 KB` default, `16 KB`, and `32 KB` pages).
- **How I know:** Read `model/tests/common/mod.rs:1-2`, `verify:8-24`, and `model/README.md`.

## `model/tests/property.rs`

### Finding 5 — stops the merge
- **File and line:** `model/tests/property.rs:1632, 1729-1733` (and `abi/src/lib.rs:324-351`)
- **Code:**
```rust
    /// Steps after which an object of each kind was dying, by kind.
    dying: [u32; 19],
```
```rust
        let mut kinds = census.dying;
        kinds.dedup();
        kinds
            .iter()
            .for_each(|&kind| self.dying[kind as usize] += 1);
```
- **What is wrong:** `ObjectKind` (`abi/src/lib.rs:324-351`) has 21 variants (`0..=20`), ending with `MemoryControl = 19` and `Role = 20`, whereas `Reached::dying` is `[u32; 19]` (`0..=18`). If a `MemoryControl` or `Role` object is ever marked dying in `census.dying`, `self.dying[kind as usize]` panics with index out of bounds. Currently `Generator` can `CapDelete` slots `0..26` (`property.rs:826`, which includes `START_SLOT_MEMORY_CONTROL = 12` and `common::ROLES = 19..=23`), and it only avoids the panic because `Generator` never creates 32+ copies of those capabilities, so `CapDelete` destroys them in a single step rather than leaving them dying.
- **How I know:** Read `model/tests/property.rs:826,1632,1729-1733` and `abi/src/lib.rs:324-351`.

### Finding 6 — stops the merge
- **File and line:** `model/tests/property.rs:1859-1878, 1965-1966, 2051-2053, 2482-2483, 2538`
- **Code:**
```rust
    // refused_send (run once per seed, 24 seeds):
    reached.sent += 1;
    reached.sent_refused += 1;
...
    // objects_of_every_kind_are_seen_dying:
    let dying = MADE.map(|kind| reached.dying[kind as usize]);
    at_least(dying, [21, 7107, 30, 8246, 106, 10, 10, 691, 166]);
...
    // moves_that_the_depths_rule_on_are_accepted_and_refused:
    at_least([reached.sent, reached.sent_refused], [21, 18]);
```
- **What is wrong:** `crowd` and `refused_send` run deterministically at the start of each of the 24 seeds (`run` at `2051-2052`). Across 24 seeds, `crowd` guarantees at least `24` steps with a dying `Untyped`, and `refused_send` guarantees `reached.sent >= 24` and `reached.sent_refused >= 24`. However, the coverage floors are `21` for `dying[Untyped]`, `21` for `sent`, and `18` for `sent_refused` — all below `24`. These floors therefore cannot fail even if the random generator produces 0 occurrences. In fact, running `property` shows `sent_refused: 24` (and `sent: 28`, `dying[Untyped]: 28`), meaning the random generator produced **zero** `sent_refused` events across all 24 seeds, hidden by the deterministic pre-loop addition and a floor below `24`.
- **How I know:** Read `model/tests/property.rs:1859-1878,1965-1966,2051-2053,2482-2483,2538`, and ran `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-F1-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-F1-hydrogen/Cargo.toml -p dodos-model --test property -- --nocapture`, which printed `sent: 28`, `sent_refused: 24`, and `dying: [28, ...]`.

### Finding 7 — should be fixed
- **File and line:** `model/tests/property.rs:1631, 1729-1733` (and `model/src/check.rs:98,109`)
- **Code:**
```rust
        let mut kinds = census.dying;
        kinds.dedup();
        kinds
            .iter()
            .for_each(|&kind| self.dying[kind as usize] += 1);
```
- **What is wrong:** `census.dying` (`model/src/check.rs:98,109`) iterates over `self.objects` (`BTreeMap<ObjId, Object>`), which is ordered by `ObjId` (creation order), not by `ObjectKind`. Calling `kinds.dedup()` without sorting removes only consecutive duplicates. If two dying objects of the same kind have a dying object of another kind between them in `ObjId` order, that kind is counted multiple times for a single step, contradicting `/// Steps after which an object of each kind was dying, by kind.` (`model/tests/property.rs:1631`).
- **How I know:** Read `model/tests/property.rs:1631,1729-1733` and `model/src/check.rs:97-110`.

### Finding 8 — should be fixed
- **File and line:** `model/tests/property.rs:170-181, 2472-2485`
- **Code:**
```rust
/// The kinds that the model makes, as `Census::dying` names them.
const MADE: [ObjectKind; 9] = [
    ObjectKind::Untyped,
    ObjectKind::CSpace,
    ObjectKind::ASpace,
    ObjectKind::Frame,
    ObjectKind::Thread,
    ObjectKind::Sched,
    ObjectKind::Endpoint,
    ObjectKind::Reply,
    ObjectKind::Notify,
];
```
- **What is wrong:** `MADE` omits `Timer`, `IoSpace`, and `Task` (which the model creates in `KINDS` at `145-147` and `calls.rs:1637`), as well as `Irq`. Thus `objects_of_every_kind_are_seen_dying` (`2472-2485`) does not check them even though `Timer`, `Irq`, and `IoSpace` appear in `census.dying` (`3`, `7`, and `15127` in the 4 KB run, and the comment at `2479-2480` explicitly mentions `IoSpace` destruction).
- **How I know:** Read `model/tests/property.rs:135-148,170-181,2472-2485`, and observed `dying` indices `9` (`Timer = 3`), `10` (`Irq = 7`), `12` (`IoSpace = 15127`), `13` (`Task = 0`) in the `property` run output.

### Finding 9 — should be fixed
- **File and line:** `model/tests/property.rs:59-60, 252, 491, 777, 1274, 1488`
- **Code:**
```rust
//! that a script makes is laid out as the start-up space: a capability for the
//! space itself in slot 1, an untyped in slot 20.
```
```rust
/// grants, and `node_start` a dead node (both in `tests/machine.rs`).
```
- **What is wrong:** Multiple comments in `property.rs` are false/stale:
  1. Lines `59-60`, `777`, and `1488` refer to the untyped in "slot 20", and lines `491` and `1274` refer to it in "slot 16". In fact, `MEMORY` (`133`) is `SlotAddr::own(MEMORY_SLOT)` where `MEMORY_SLOT = 107` (`85`), and `spawn` derives it into `inside(MEMORY_SLOT)` = slot `107` (`1299`). (In the start-up space, `START_SLOT_FIRST = 16` is the start-up untyped and `UNTYPED_SLOT = 25` is the chunk untyped.)
  2. Line `252` refers to `tests/machine.rs`, which does not exist in `model/tests/` (the multi-node tests live in `model/src/scenarios/`).
- **How I know:** Read `model/tests/property.rs:59-60,82,85,133,252,491,777,1274,1299,1488` and listed `model/tests/`.

### Finding 10 — should be fixed
- **File and line:** `model/tests/property.rs:1299, 1328, 1347`
- **Code:**
```rust
        calls.push(derive(MEMORY, inside(MEMORY_SLOT)));
...
        let kept = self.find_own(OTHER, Wanted::Free).map_or(inside(107), own);
```
- **What is wrong:** `MEMORY_SLOT` is `107` (`property.rs:85`), so `inside(107)` is already filled by `derive(MEMORY, inside(MEMORY_SLOT))` at line `1299`. If `self.find_own(OTHER, Wanted::Free)` returns `None`, `kept` falls back to `inside(107)` and the `Sched` creation at line `1347` collides with `MEMORY` and fails with `Error::NoSlot` (whereas the second thread uses `inside(106)` at line `1331`).
- **How I know:** Read `model/tests/property.rs:85,1299,1328-1357`.

### Finding 11 — question
- **File and line:** `model/tests/property.rs:806, 954-963, 1170-1179`
- **Code:**
```rust
        let roll = if self.rng.chance(14) {
            29 + self.rng.below(8)
        } else {
            self.rng.below(74)
        };
        match roll {
            ...
            35 | 36 => Syscall::Recv { ... },
            38 | 39 => Syscall::ThreadCancel(self.held(THREAD), self.number()),
            ...
            _ if self.rng.chance(80) => Syscall::NotifyBind { ... },
            _ => self.debug_call(),
        }
```
- **What is wrong:** `roll` ranges over `0..74`, and every integer in `0..74` except `37` has an explicit arm before `_`. As a result, only `roll == 37` (1 in 74 non-depth rolls) ever reaches `NotifyBind` (80%) or `debug_call` (20%, further split 6 ways among `DebugWrite`, `TraceEmit`, `IoportIn`, `IoportOut`, `IoportsIssue`, `EntropyRead`). Is `37` being the sole fallthrough intentional, or was a `37` arm deleted without adjusting the fallback range?
- **How I know:** Read `model/tests/property.rs:803-1180` and checked the `property` run output (`ok[60..63]` for `IoportIn`, `IoportOut`, `IoportsIssue`, `EntropyRead` were `3`, `4`, `8`, `26`, and `ok[18]`/`ok[59]` for `DebugWrite`/`TraceEmit` were `13` each).

## Files read

### Read whole
- `AGENTS.md`
- `model/README.md`
- `.claude/skills/dodos-rust/SKILL.md`
- `.claude/skills/rust-1-100/SKILL.md`
- `model/tests/calls.rs` (lines 1–5574)
- `model/tests/common/mod.rs` (lines 1–74)
- `model/tests/property.rs` (lines 1–2652)

### Read in part (only as needed to understand the lot)
- `verify`
- `abi/src/lib.rs` (`Error`, `ObjectKind`)
- `abi/src/start.rs` (`START_SLOT_*`)
- `model/src/lib.rs` (`Syscall`)
- `model/src/boot.rs` (`Machine::example_on`)
- `model/src/caps.rs` (`footprint`, `cap_delete`, `fits`, `create`, `next_removed`, `destroy`)
- `model/src/check.rs` (`Model::census`)
- `model/tests/cores.rs` (head lines 1–60)

### Not read
- All remaining files of `abi/`, `model/`, and the rest of the repository (including the other test files in `model/tests/` and `model/src/scenarios/`).

## Commands run
- In a copy `/private/tmp/dodos-pr3-F1-hydrogen` (no edits made to `/private/tmp/dodos-pr3-final`):
  - `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-F1-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-F1-hydrogen/Cargo.toml -p dodos-model --test property -- --nocapture` -> `15 passed; 0 failed`
  - `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-F1-hydrogen -c sh -c 'cargo test --manifest-path /private/tmp/dodos-pr3-F1-hydrogen/Cargo.toml -p dodos-model --test calls && DODOS_PAGE=16k cargo test --manifest-path /private/tmp/dodos-pr3-F1-hydrogen/Cargo.toml -p dodos-model --test calls && DODOS_PAGE=32k cargo test --manifest-path /private/tmp/dodos-pr3-F1-hydrogen/Cargo.toml -p dodos-model --test calls'` -> `347 passed; 0 failed` on each of the 3 geometries.
