# Review of lot A (PR `origin/main...HEAD`, branch `model`, head `6312868`, clone `/private/tmp/dodos-pr3-final`)

Reviewer: v1-A-mistral. Lot: the whole `abi/` crate — `abi/src/aarch64.rs`,
`abi/src/debug.rs`, `abi/src/features.rs`, `abi/src/lib.rs`,
`abi/src/machine.rs`, `abi/tests/review6.rs`, `abi/src/ring.rs`,
`abi/src/riscv64.rs`, `abi/src/start.rs`, `abi/src/tests.rs`,
`abi/src/x86_64.rs` (these eleven are all of `abi/`). All were read whole, in
the order the brief lists.

Verification runs were done in a copy, `/private/tmp/dodos-pr3-A-mistral`
(`cp -R` of the clone; the clone itself was not modified), with the machine's
rustc/cargo 1.100.0:

- `cargo test -p dodos-abi --lib` → **74 passed, 0 failed**.
- `cargo test -p dodos-abi --test review6` → the two shipped tests pass.
- Two throwaway probe test files (`abi/tests/probe.rs`, an appended probe in
  `abi/tests/review6.rs` in the copy only) reproduced the panics reported below.

## Findings

### 1. `Geometry::valid` panics with an add overflow on a crafted geometry (dev/debug builds) — should be fixed

`abi/src/lib.rs:504` (loop over the page sizes; `per_level` is line 498):

```rust
let per_level = self.entries.trailing_zeros() as u8;
let mut sizes = s[1] == s[0] + per_level && self.levels > 1;
...
    if s[i] != 0 && (s[i - 1] == 0 || s[i] != s[i - 1] + per_level || i > 2) {
```

`s[i - 1]` and `per_level` are `u8`; when `s[i - 1] + per_level > 255` the
addition overflows, which panics in a dev-profile build (the workspace
`Cargo.toml` keeps overflow checks on for `dodos-abi` in dev). Demonstrated in
the copy with:

```
Geometry { page_shift: [12, 255, 1, 0], entries: 1 << 31, levels: 4, user_end: 1 << 30 }.valid()
→ thread panicked at abi/src/lib.rs:504:55: attempt to add with overflow
```

(`cargo test -p dodos-abi --test review6` with an appended probe test; the probe
failed with exactly that panic.) `valid()` is the documented gate for the
values the start-up page publishes ("The default is all zero, which
[`Geometry::valid`] refuses", lib.rs:417), and the model calls it first on the
boot geometry (`model/src/boot.rs:631`), so the input reaches it unvalidated.
In a release build the wrap happens to be benign for this input, but the panic
is real in every dev/test build the project itself runs (`verify`). Fix by
bounding the additions (e.g. widen to `u16`/`u32`, or validate `s[1..4]`
ranges before the loop).

### 2. `module_frames` overflows on a huge module length — should be fixed

`abi/src/machine.rs:1311`:

```rust
end: len.div_ceil(page) * page,
```

With `page = 4096` and `len = u64::MAX`, `div_ceil` gives 2^52 and the product
is 2^64: overflow panic in dev, wrap in release. Demonstrated in the copy:
`module_frames(0, None, u64::MAX, x86_64::GEOMETRY).count()` panicked at
`abi/src/machine.rs:1311:14`. `len` is the length of a boot module, taken from
the start-up page and fed to `module_frames` by the model
(`model/src/boot.rs:1244,1267`), so the length should be bounded (or the
product computed with `checked_mul` / the iterator made `Option`) before it
reaches this line.

### 3. The public `Geometry` accessors panic on an unvalidated geometry — question

All four are `pub const fn` with no internal guard, and all panic in dev
builds on a geometry that `valid()` refuses (demonstrated in the copy with
`catch_unwind`):

- `page()`, `abi/src/lib.rs:434` — `1 << self.page_shift[0]`; panics at 434:9
  when `page_shift[0] >= 64`.
- `chunk()`, `abi/src/lib.rs:443` — `1 << self.chunk_shift()`; panics at 443:9
  when `page_shift[1] >= 64`.
- `root_entry()`, `abi/src/lib.rs:468` — `self.levels - 1` underflows when
  `levels == 0`; panics at 468:43 on the all-zero default geometry.
- `canonical()`, `abi/src/lib.rs:477` — `self.address_bits() - 1` underflows
  when `address_bits() == 0`; panics at 477:30 on the all-zero default — the
  very default the struct doc mentions (`lib.rs:417`).

Today the only in-repo call path validates first (`model/src/boot.rs:631` calls
`valid()` before using `page()`/`chunk()`/`canonical()`), so this is not
reachable through the model as written; but as public API of the contract
crate these panic instead of returning a value on inputs the crate itself
documents as merely "refused by `valid()`". Either mark the precondition
("only on a geometry `valid()` accepts") on each accessor, or make them total.

### 4. False doc comment: `ExceptionUse` names two functions that do not exist — should be fixed (trivial)

`abi/src/lib.rs:788`:

```rust
/// each architecture classify it (`aarch64::ec_use`, `riscv64::cause_use`).
```

Both modules export `exception_use` (`abi/src/aarch64.rs:177`,
`abi/src/riscv64.rs:87`); `ec_use` and `cause_use` exist nowhere (grep over
`abi/` and `model/`). The pointers are stale renames.

### 5. `aarch64::abort_use`: the DFSC table is pinned by tests for only 8 of 64 values, and the comment's "at any level" does not match the code for 0x2D/0x2E — question

`abi/src/aarch64.rs:231-240`:

```rust
pub const fn abort_use(fsc: u8) -> Option<ExceptionUse> {
    ...
        0x04..=0x07 | 0x2A | 0x2B | 0x0C..=0x0F => Fault(Page),
        0x10 | 0x11 | 0x21 | 0x35 => Fault(Protection),
        0x00..=0x03 | 0x29 | 0x2C | 0x08..=0x0B => NotThread,
        0x12..=0x18 | 0x1B..=0x1F | 0x22..=0x28 | 0x30 | 0x31 | 0x34 => NotThread,
        _ => return None,
```

The comment above it (lines 222-230) says: "A translation fault, at any level
(−2 and −1 with FEAT_D128 and FEAT_LPA2), and a permission fault are page
faults". The code maps translation faults at levels 0–3 plus 0x2A/0x2B to
`Page`, and permission faults only at levels 0–3 (0x0C–0x0F); the values the
LPA2/D128 numbering gives to permission faults at levels −1/−2 (0x2D/0x2E by
the same scheme that puts 0x29/0x2A/0x2B/0x2C at level −1/−2) fall through to
`None` ("reserved"). Either "at any level" attaches only to translation, or
0x2D/0x2E should be `Page`. I could not settle this from inside the repository
(the brief forbids outside documentation), so it is a question for the authors
against DDI 0487 K.a. Related: of the 64 FSC values, `abi/src/tests.rs`
(`arm64_and_riscv_exceptions_map_to_the_kinds_of_faults`) pins only 0x07, 0x2B,
0x0F (Page), 0x21, 0x10 (Protection), 0x09, 0x18 (NotThread) and 0x3F (None),
and the Kani proof in `lib.rs` checks only `is_some()`, not the `Fault` kind —
so a wrong kind on the other 56 values would not fail any test.

### 6. `trace_index` underflows on sequence 0 — question (documented precondition only)

`abi/src/debug.rs:78-80`:

```rust
pub const fn trace_index(seq: u64, entries: u64) -> u64 {
    (seq - 1) % entries
}
```

`seq = 0` underflows and panics in dev builds; "at least 1" appears only in
the doc comment, and the Kani proof `assume`s it. No in-repo caller can pass 0
(the rings are kernel-written), so this is noted for completeness, not as a
live bug.

## Checked and found consistent (no finding)

- All `repr(C)` sizes and offsets asserted in `abi/src/tests.rs`
  (`layouts_are_fixed`, `fields_of_the_shared_layouts_have_their_offsets`) were
  recomputed by hand and match: debug area 17×4,096 = 69,632 with the kernel
  ring at 4,096 and the user ring at 20,480 ending exactly at the area end;
  `CoreCrashRecord` 4,032; `CrashAreaHeader` 4,096; `FenceRecord` 544;
  `StartMachine` 96; `StartDebug` 56; `StartCore` 32; `StartNode` 24;
  `RingHeader` 16; `RETIRED_WORD_BYTES` = 192/8 = 24. The suite passes.
- Call numbering: 64 `Call` variants, `TraceEmit` = 44, `ThreadCancel` = 45,
  `IrqClaim` = 46, `SchedRead` = 47, matching `calls_keep_their_place` and the
  two dedicated tests.
- `NodeMessage`: 11 kinds with 9 reserved; `from_raw` mapping, ring split,
  request/answer pairing, `RING_ANSWER_RESERVE` = 16+8+10 = 34 = credits + one
  `Report` − 1, `message_entries` of the largest `Send` (10) and `Report` (11)
  — all verified by hand and by the passing tests.
- `bandwidth` matches the 128-bit reference on the test's 100,000 random cases
  and on hand-checked edges (1/3, full budget, 2^47−1 over 2^48−1); its `assert`
  precondition (`budget ≤ period < 2^48`) is enforced by the only model caller
  (`model/src/sched.rs:784` validates before configuring; `timer_set` refuses
  `deadline ≥ TIME_LIMIT` at `sched.rs:1061` before `firing_instant`).
- `firing_instant` hand-checked on the test's cases (1000/24 → 1024, 1000/23 →
  1008, 1025/1000 → 1536, 5/u64::MAX → 2^62, TIME_LIMIT−1/9 → TIME_LIMIT−1).
- `member_transition` rows, `may_take` rules 1–4, `successor`/`best_class`,
  `barrier`, `Ownership`/`CoreWord` check fields (top 14/12 bits of the product
  by `CHECK_MUL`), `PageClass` ranges and `permits`, `AttachWord`, `GateWord`,
  `RoleWord`, `IoPortRange`/`ioport_check`, `clear_step`/`clear_steps`,
  `floors`, `module_frames` (including the frame-splitting cases in
  `module_frames_take_the_largest_size_that_fits`), `FeatureMask::check`
  ordering Invalid-then-Unsupported, `thread_bytes`, `kind_covers` — all read
  and traced; the corresponding tests pass.
- ARM64 EC table and RISC-V `scause` table agree with the Linux copies
  transcribed in `tests.rs` (45 + 4 = 49 classes; 19 + 1 = 20 causes);
  `EXCEPTION_CLASSES`/`CAUSES` counts match their array lengths; the three
  architectures' `IRQ_TABLE_ENTRIES` are all 192.
- x86-64 values used by the tests (`IRQ_VECTOR_FIRST/LAST` 48/239 → 192
  claimable, `IRQ_MAX_CORES_REMAPPED` 341 so handles fit 16 bits,
  `DR7_USER_MASK` 0xFFFF_0055 with the I/O condition refused by `dr7_valid`,
  `msi_remapped`/`msi_direct`, `rflags`, `canonical`, `USER_RANGE_END` =
  2^47 − 2^39 = half − root_entry) all check out against `x86_64.rs`.
- `abi/` has `#![forbid(unsafe_code)]` and every `assert!` in the crate is a
  documented constructor precondition (`bandwidth`, `IrqSource::msi`,
  `TaskId::new`, `DeviceEntry::used`, `RemoteRef::new`); no `unsafe` anywhere
  in the lot.

## Files read whole

- `abi/src/aarch64.rs` (261 lines)
- `abi/src/debug.rs` (267)
- `abi/src/features.rs` (202)
- `abi/src/lib.rs` (1,251)
- `abi/src/machine.rs` (1,943)
- `abi/tests/review6.rs` (34)
- `abi/src/ring.rs` (388)
- `abi/src/riscv64.rs` (122)
- `abi/src/start.rs` (455)
- `abi/src/tests.rs` (2,482)
- `abi/src/x86_64.rs` (155)

Plus, for orientation only: `AGENTS.md`, `model/README.md`,
`.claude/skills/dodos-rust/SKILL.md`, `.claude/skills/rust-1-100/SKILL.md`,
`abi/Cargo.toml`, root `Cargo.toml`/`flake.nix`, and short excerpts of
`model/src/boot.rs`, `model/src/sched.rs`, `model/src/memory.rs` (only to
judge whether the panics above are reachable; not reviewed as findings).

## Not read

Everything else in the repository: the whole `model/` crate (beyond the
excerpts named above), `verify`, `Cargo.lock`, and all files outside
`/private/tmp/dodos-pr3-final`. No other directory of the machine and no web
sources were consulted, per the brief.
