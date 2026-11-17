# Verification of two reviews of lot A (`abi/`)

Verified by the sub-agent of the review task, against the contract
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` (branch
`main`, head `1d83b8d`) and its decisions `D-128` to `D-140`. The lot is
`abi/` of pull request 3 of `dodos-kernel`, head `6312868`. Work was done in
`/private/tmp/dodos-pr3-ver-A` (`cp -R` of `/private/tmp/dodos-pr3-final`);
nothing was changed outside it and nothing was committed.

## What I ran, and the baseline

`PATH` with `/nix/var/nix/profiles/default/bin`; every command is absolute.

- `nix develop -c ./verify` in the copy, at head, **exit 0** in 3 min 46 s:
  `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D
  warnings`, `cargo test --workspace` (74 + 2 in `dodos-abi`, 523 in the model
  library and every integration target), then the same page-dependent tests
  on 16 KB and 32 KB pages. So the lot is green as shipped, with every defect
  below in it.
- The probes are two files I added to the copy only, untracked:
  `/private/tmp/dodos-pr3-ver-A/abi/tests/ver_a.rs` (17 tests: 11 pass, 6
  fail — the six are the defects of H1, H4, M1 and M5) and
  `/private/tmp/dodos-pr3-ver-A/model/tests/ver_a.rs` (2 tests, 1 fails).
  Each test states the behaviour the contract or the doc comment demands, so a
  failure is the defect; the tests that show today's behaviour without
  complaining have "today" in a name.
- Three mutations of the copy, each reverted with `git checkout -- .`:
  A: `aarch64::abort_use`, `0x35` moved from `Fault(Protection)` to
  `NotThread` → all 74 `dodos-abi` library tests pass.
  B: `DeviceEntry`'s two fields swapped → all 74 pass.
  C: `machine::barrier`, the arm `Sealed | Fencing | Unfenced => !y.maps`
  replaced by `=> true` → 73 pass, 1 fails
  (`the_barrier_waits_for_every_node_that_could_reach_the_memory`).
- `kani`, Miri and the sanitizer are not in the flake (the skill `dodos-rust`
  says so), so no Kani proof was run; what I say about them is read from the
  code and from `abi/src/tests.rs`, and is marked as read.

Two findings are the same finding in both reports, and are judged once: the
`ExceptionUse` doc comment naming two functions that do not exist (H2 = M4),
`trace_index` with sequence 0 (H7 = M6), and the fault-status-code table being
pinned for a handful of values (the second half of M5 = the last two items of
H6). Where a reviewer's claim is wrong in detail I say so in place.

---

## H1 — `EC_SME` ignores the ISS bits. Real, high.

`abi/src/aarch64.rs:76-77` and `:197` (`EC_SME => Feature(SME)` inside
`class_use`), reached through `exception_use` at `:177-183`. The doc comment of
`EC_SME` itself says the class covers both "SME trapped by `CPACR_EL1.SMEN` (or
`CPTR_EL2`, `CPTR_EL3`)" and "an instruction illegal for `PSTATE.SM` or
`PSTATE.ZA`", and the ISS bits 2:0 name which: `0b000` the `SMEN` trap,
`0b001` illegal for `PSTATE.SM`, `0b010` illegal for `PSTATE.ZA`, `0b100` a
`ZT0` trap (`SMCR_ELx.EZT0` 0). The code folds all four into `Feature(SME)`.

Reproduced. `abi/tests/ver_a.rs`, test `h1_the_iss_bits_of_ec_sme_are_ignored_today`
passes: all 64 values of ISS give the same answer, `Some(Feature(SME))`. The
two tests that state what the contract needs:

```
h1_a_zt0_trap_is_the_feature_of_zt0 ... FAILED
  left: Some(Feature(1))   right: Some(Feature(2))
h1_an_instruction_illegal_for_the_streaming_state_is_undefined ... FAILED
  left: Some(Feature(1))   right: Some(Fault(Undefined))
```

(`Feature(1)` is SME, `Feature(2)` is `SME2_ZT0`; `abi/src/aarch64.rs:8-13`
lists `SME2_ZT0` as a state feature, "ZT0 of SME2".)

Why it is real and not the contract's fault: the contract gives the answer for
a trap that names a feature the mask lacks, and it is not the bit of SME.
`kernel-interface.md:728`: "**Using a feature that is not enabled for the
thread raises the fault *undefined instruction*** (kind 2), with word 4 = 1 +
the feature's bit when the trap names the feature, and 0 when the core does
not have the instruction at all." A `ZT0` trap on a thread whose mask holds
SME but not `SME2_ZT0` names `SME2_ZT0`; `Feature(SME)` answers SME, and
`ExceptionUse::Feature` (`abi/src/lib.rs:796-800`) says that when the mask
holds the feature the kernel "loads the state and the thread resumes" — the
`ZT0` instruction is still refused, so the thread traps with `EC_SME` again
and the same answer, for ever. Only the ISS `0b000` case is SME itself.

Severity high: an infinite trap loop in the kernel, and a wrong word 4. The
model cannot show the loop because it never calls `exception_use` (see the
last section).

Correction. `aarch64::exception_use`: split `EC_SME` out of `class_use` and
read the reason, e.g.

```rust
if ec == EC_SME {
    return sme_use((syndrome & 0x7) as u8);
}
...
const fn sme_use(iss: u8) -> Option<ExceptionUse> {
    Some(match iss {
        0b100 => ExceptionUse::Feature(SME2_ZT0),
        0b001 => ExceptionUse::Fault(FaultKind::Undefined),
        _ => ExceptionUse::Feature(SME),
    })
}
```

(`0b010`, illegal for `PSTATE.ZA`, stays `Feature(SME)`: it is the first use
of ZA, which is SME state the kernel activates.) The contract needs one
sentence for `0b001` and `0b010`, since the kind row and the sentence above
speak only of "when the thread's mask lacks them"; the ISS bits 2:0 of
`ESR_ELx` are the place to name them. Test that fails without the change:
mine `h1_a_zt0_trap_is_the_feature_of_zt0`; in the pull request add rows to
`arm64_and_riscv_exceptions_map_to_the_kinds_of_faults`
(`abi/src/tests.rs:2235`), which today pins only `esr(EC_SME, 0)`:
`(esr(a::EC_SME, 0b100), Feature(a::SME2_ZT0))` and
`(esr(a::EC_SME, 0b001), Fault(Undefined))`.

## H2 = M4 — the doc comment names `aarch64::ec_use` and `riscv64::cause_use`. Real, trivial.

`abi/src/lib.rs:787-789`. `grep -rn "ec_use\|cause_use" abi model` matches
`abi/src/lib.rs:788` and nothing else; the functions are
`aarch64::exception_use` (`abi/src/aarch64.rs:177`) and
`riscv64::exception_use` (`abi/src/riscv64.rs:87`), and the contract names
them that way too (`kernel-interface.md:457`: "`abi/` gives both tables
(`aarch64::exception_use`, `riscv64::exception_use`)"). Correction: write the
two real names; no test.

## H3 — `firing_instant` has an unwritten precondition. Real, low.

`abi/src/lib.rs:883-898`. Reproduced, `abi/tests/ver_a.rs`:
`h3_firing_instant_refuses_a_deadline_at_the_limit` passes, i.e.
`firing_instant(TIME_LIMIT, 0)` panics — `x` is clamped to `TIME_LIMIT - 1`,
`differ == 0`, `63 - 64` underflows — and
`h3_firing_instant_above_the_limit_is_zero_today` passes, i.e.
`firing_instant(TIME_LIMIT + 1, 0) == 0` and `firing_instant(u64::MAX, 7) == 0`,
which the comment "they differ, since x ≥ deadline" rules out.

Reachability: none from the model. `model/src/sched.rs:1061-1063` refuses
`deadline >= TIME_LIMIT` with `Error::Invalid` before the call, and the
contract fixes it (`kernel-interface.md:498`): "Every instant and every duration given to a
call is in nanoseconds and must be below 2^63 (`invalid` otherwise, judged with
the plain arguments), with one exception: the tolerance of `timer_set`, which
is any word". So the model does what the contract
says and the defect is the missing check on an input the contract forbids —
the same shape as `bandwidth`, which does assert (`abi/src/lib.rs:868`) and
whose assert `firing_instant` lacks. The Kani proof masks it:
`kani::assume(deadline < TIME_LIMIT)` at `abi/src/lib.rs:1196`.

Correction: `assert!(deadline < TIME_LIMIT);` after the `deadline == 0` return
in `firing_instant`, and the comment corrected to "they differ, since
`deadline ≤ x`". Test that fails without it: a new
`#[should_panic] fn a_deadline_at_the_limit_is_refused()` next to
`firing_instant_has_the_most_trailing_zeros_in_its_window`
(`abi/src/tests.rs:591`).

## H4 — `DeviceEntry::used` accepts a size below one page. Real, low.

`abi/src/machine.rs:638-644, 662-664`: `assert!(log2 < 64 && base & ((1 <<
log2) - 1) == 0)`, while the entry's first word holds `log2` in bits 0-5,
`USED` in bit 6, and `base()` masks bits 0-6 off. Reproduced:
`h4_a_device_entry_of_sixty_four_bytes_keeps_its_base` fails with `left: 0,
right: 64` — `DeviceEntry::used(64, 6).base() == 0` and `.log2() == 6`.

The contract fixes the encoding and the floor: `kernel-interface.md:858`: "An
entry is 16 bytes: a word with the base (aligned on the size, at least one
page), the log2 of the size in bits 0-5, and bit 6 set when the entry is
used; then an ownership word". So the assert does less than the sentence it
implements, and less than the struct's own doc ("the base (aligned on the
size, at least one page)"). No live caller can pass `log2 < 12`
(`model/src/boot.rs:818-823` filters `len >= page`, so `trailing_zeros() >=
12`), which is why it is low.

Correction: `assert!((12..64).contains(&log2) && base & ((1 << log2) - 1) == 0);`
Test that fails without it: `for log2 in 12..64 { assert_eq!(DeviceEntry::used(1
<< log2, log2).base(), 1 << log2) }` plus
`#[should_panic] fn an_entry_below_a_page_is_refused()`.

## H5 — stale doc comment on `size_at`. Real, trivial.

`abi/src/machine.rs:1317-1319` says "The largest supported size that suits
position `offset` with `left` bytes left, and that is above `above` if given",
and the function is `fn size_at(&self, offset: u64, left: u64) -> PageSize`.
There is no `above` parameter and no caller with one
(`Iterator::next`, `abi/src/machine.rs:1345`, is the only call). Correction:
drop "and that is above `above` if given"; no test.

## H6 — the Kani rule of `AGENTS.md` and four test gaps. Real, medium; two of its parts refuted.

Read, not run (Kani is CI only). `AGENTS.md:52`: "A pure function of abi/ has
a Kani proof (`#[cfg(kani)]`)." The proofs that exist are
`abi/src/lib.rs:1097-1251`, `abi/src/features.rs:130`, `abi/src/ring.rs:288`,
`abi/src/debug.rs:243` and `abi/src/machine.rs:1458, 1480, 1513`. What they
cover, from the function names: `Header`, `SlotAddr`, `mapping_range`,
`firing_instant`, `bandwidth`, `IrqSource`, `NodeMessage`, `trace_index`,
`FeatureMask`, `AttachWord`, `PageClass`, `Ownership`, `Member`, the ring
indices, and the two architecture class tables. So these pure functions of `abi/` have none, which
I checked one by one: `Geometry::bytes, page, chunk_shift, chunk, sizes,
address_bits, root_entry, canonical, valid` (`abi/src/lib.rs:425-521`),
`Rights`, `Marks`, `PageSize::from_raw`, `MemoryType::for_memory`,
`mapping_rights`, `io_mapping_rights`, `FaultKind::from_raw`,
`ClockPage::nanoseconds`, `TaskId`, `NodeGen`, and all of
`abi/src/x86_64.rs` — `dr7_valid`, `canonical`, `msi_remapped`, `msi_direct`,
`rflags` (no `#[cfg(kani)]` in that file at all). The finding holds as
written in substance, with two corrections of detail: the list of
`#[repr(C)]` structs is 38, not 34, and 21 of them have `offset_of!` checks,
not 20 (`grep` of `#\[repr(C)\]` against `grep offset_of!` in `tests.rs`).

Its test-coverage parts, each reproduced by mutation or by count:

- `abort_use` is proved only at fault status 0. `abi/src/lib.rs:1116-1123`
  builds `syndrome = (ec as u64) << ESR_EC_SHIFT`, so bits 25:0 are 0 and the
  abort arm calls `abort_use(0)`. Read.
- The fault-status table is pinned for 8 of 64 values. `abi/src/tests.rs:2235-2270`
  pins 0x07, 0x2B, 0x0F (page), 0x21, 0x10 (protection), 0x09, 0x18
  (not the thread) and 0x3F (reserved). Mutation A moves 0x35 from
  `Fault(Protection)` to `NotThread` and **all 74 tests still pass**, which is
  the claim, run.
- The field offsets of every `#[repr(C)]` struct are not pinned. Mutation B
  swaps `DeviceEntry`'s two fields — the contract's "a word with the base …
  then an ownership word" (`kernel-interface.md:858`) is broken — and **all
  74 tests still pass**, because `DeviceEntry` has a `size_of!` check and no
  `offset_of!` check. Run.
- `CRASH_AREA_MAGIC` (`abi/src/debug.rs:36`) is never asserted: it appears in
  `abi/` only in its definition and the re-export. Read.
- **Refuted:** the sub-claim about `barrier`
  (`abi/src/tests.rs:1438-1458`). The states it says are untested —
  `Starting`, `Sealing`, `Fencing` — share one arm with `Sealed` and
  `Unfenced`, `MemberState::Sealed | MemberState::Fencing |
  MemberState::Unfenced => !y.maps` (`abi/src/machine.rs:909`), and the
  test pins that expression both ways (`Sealed` with `!maps` accepted,
  `Unfenced` with `maps` refused). Mutation C replaces the expression by
  `true` and the test fails, so nothing is lost; testing a fourth state of the
  same `or` would add no coverage.

Correction, in the pull request's terms: proofs for at least
`Geometry::{valid, page, chunk, address_bits, root_entry, canonical}`,
`TaskId`, `NodeGen`, `Rights` and `x86_64::{dr7_valid, canonical, rflags,
msi_remapped, msi_direct}`; the arm64 proof takes the low bits of the
syndrome as `let iss: u64 = kani::any(); let syndrome = (ec as u64) <<
ESR_EC_SHIFT | iss & 0xFFF;` so that `abort_use` is proved over its 64 codes;
a test with a table of all 64 fault status codes (it fails on mutation A); an
`offset_of!` row for each of the 17 unchecked `#[repr(C)]` structs, `DeviceEntry`
first (it fails on mutation B); `assert_eq!(CRASH_AREA_MAGIC, …)` in
`layouts_are_fixed`. Note that a proof of `Geometry::valid` is exactly the
check that would have found M1.

## H7 = M6 — `trace_index(0, _)`. Intended, no severity.

`abi/src/debug.rs:78-80` is `(seq - 1) % entries`, documented "The entry of
sequence `seq` (at least 1)" at `:76-77`, and the `seq` field says "at least 1;
0 while the entry is being written" at `:86`. Reproduced:
`h7_trace_index_of_sequence_zero` passes, i.e. `trace_index(0, 256)` and
`trace_index(1, 0)` panic. Intended: the precondition is written at the
function, the Kani proof assumes it (`kani::assume(seq >= 1)`,
`abi/src/debug.rs:257`) and the only caller in the repository cannot break it
— `model/src/debug.rs:93` passes `next_user`/`next_kernel`, which start at 1
in `DebugArea::new` (`model/src/debug.rs:60-75`). Nothing to correct; an
`assert!` would be a courtesy, not a fix.

## H8 — `dr7_valid` accepts a length on an execution breakpoint. The contract's fault, low.

`abi/src/x86_64.rs:98-110`. Reproduced:
`h8_dr7_valid_accepts_a_length_on_an_execution_breakpoint` passes —
`dr7_valid(1 | 0b11 << 16)` is `true`, i.e. `L0` set with `R/W0 = 0b00`
(execute) and `LEN0 = 0b11` (four bytes); the fields are inside
`DR7_USER_MASK = 0xFFFF_0055` (`abi/src/x86_64.rs:94`), so nothing refuses
them. The contract asks for nothing more: `kernel-interface.md:1666`: "An
address word must lie in the user range (`invalid`, judged word by word with
the block); a control word with a bit outside the architecture's user mask
(in `abi/`) is `invalid`, so a thread can never watch a kernel address or an
I/O port." The model does exactly that and the contract is silent on the
length of an execution breakpoint, which Intel requires to be 0 (SDM volume 3,
18.2.4, the section the constant cites). So: the contract's fault, and the
risk is on the kernel's own side — a processor that refuses such a `DR7` write
turns a user write into a `#GP` the kernel must accuse itself of, not the
thread.

Correction: one clause in that paragraph — "on x86-64 a `LEN` field that is
not 0 with a `R/W` field of `0b00` is `invalid`" — and, in `dr7_valid`, a third
loop refusing `word >> (18 + 4 * n) & 0b11 == 0 && word >> (16 + 4 * n) & 0b11
!= 0` (R/W zero, `LEN` not zero). Test that fails without it: a row in
`x86_64_values_have_their_numbers` with `assert!(!dr7_valid(1 | 0b11 << 16))`.

## H9 — `CoreWord::from_raw` and `RoleWord::from_raw`. Intended, no severity.

`abi/src/machine.rs:1000-1003` and `:1136-1145`. For the core word the
contract fixes the reading rule and only that rule:
`kernel-interface.md:1209`: "Every read checks the check field; a word that
fails it counts as held by another live node, and the reader traces it (code
10)." `*Leaving*` is "reserved: no rule of this contract writes it"
(`:1202`), so a word in that state cannot exist. The rest is checked where the
contract puts it, in the invariants: `model/src/check/machine.rs:54-69`
("a core word never reads *leaving* (no rule writes it) nor fails its check; a
free word names no node"). For the role word the doc comment of `from_raw`
lists its three refusals and a held word naming nobody is not one of them;
`RoleWord::from_raw` has no caller in `model/` at all (`grep`), so nothing
depends on the choice. Nothing to correct; if the authors want the stricter
reading, it belongs in the invariants, not in the parser.

## H10 — `StartMachine`'s doc stops at D-137. Refuted.

`abi/src/start.rs:339-340` says "its sizes (96 bytes since D-137, 88 since
D-135, 80 since D-129)", and the claim is that D-140 made the struct 96 and the
comment does not say so. The premise is wrong: the struct was already 96 bytes
at layout 4. The fields are 8 × `u32`, then `chunks: u64`, then 9 × `u32`,
then `fence_records, lines, line_count, attach_words` — 92 bytes — and the
alignment of the `u64` rounds the struct to 96, so `retired_words` filled
padding and changed no size. Reproduced:
`h10_start_machine_was_already_ninety_six_bytes_before_the_retired_words`
passes, asserting `size_of::<StartMachine>() == 96`, that the fields without
the last are 92, and that `92.next_multiple_of(8) == 96`. The other two
numbers are right by the same arithmetic — 88 at layout 3 and 80 at layout 1,
as the `START_MACHINE_LAYOUT` history says (`abi/src/start.rs:384-387`). The comment is about sizes and its sizes are
correct; nothing to correct.

## M1 — `Geometry::valid` panics instead of refusing, and `Model::boot` reaches it. Real, high.

`abi/src/lib.rs:504`: `if s[i] != 0 && (s[i - 1] == 0 || s[i] != s[i - 1] + per_level || i > 2)`,
where `s: [u8; 4]` and `per_level: u8`. Reproduced twice:

- `abi/tests/ver_a.rs`, `m1_valid_refuses_a_crafted_geometry_instead_of_panicking`:
  `Geometry { page_shift: [12, 255, 1, 0], entries: 512, levels: 4, user_end: 1 << 30 }.valid()`
  panics at `abi/src/lib.rs:504:55`, "attempt to add with overflow"
  (`255 + 9`). The guard at `:495` bounds `s[0]` only; `s[1]` is free, and the
  loop adds to it as soon as a later size is present.
- `model/tests/ver_a.rs`, `m1_a_geometry_valid_is_a_refusal_not_a_panic`: a
  `Machine::example_on(GEOMETRY)` with `machine.geometry` set to that value and
  `Model::boot(&machine)` **panics at `abi/src/lib.rs:504`** instead of
  returning `Err(Refusal::MachineValues)` — `Machine::layout` validates first
  (`model/src/boot.rs:631-637`) in order to refuse it.

What my reproduction adds to the reviewer's finding is the reach it asserted
and did not show: M1 wrote that the model "calls it first on the boot geometry
(`model/src/boot.rs:631`), so the input reaches it unvalidated", and it does. A validator that panics on an
input it exists to refuse is the defect; in a release build the add wraps and
`sizes` comes out false, so the damage is to the build `verify` runs.

Correction: `Geometry::valid`, widen the additions —
`if s[i] as u16 != s[i - 1] as u16 + u16::from(per_level)` and the same at
`:498` (`sizes`) — or refuse `s[1..4]` above `63` before the loop. Test that
fails without it: mine `m1_valid_refuses_a_crafted_geometry_instead_of_panicking`,
which belongs in `abi/tests/review6.rs` (it is the file of the geometry
refusals) and, for the boot path, a model test that a machine with that
geometry gives `Refusal::MachineValues`.

## M2 — `module_frames` overflows on a huge length. Real, low; the reachability it claims is refuted.

`abi/src/machine.rs:1311`, `end: len.div_ceil(page) * page`. Reproduced:
`abi/tests/ver_a.rs`, `m2_module_frames_of_a_length_beyond_the_address_space`
passes — `module_frames(0, None, u64::MAX, x86_64::GEOMETRY)` and `u64::MAX -
1000` panic in `const fn module_frames` itself, before the iterator is read.

What is refuted is that the model can hand it such a length. "The length of a
boot module, taken from the start-up page and fed to `module_frames` by the
model (`model/src/boot.rs:1244,1267`)" is right about the call sites and wrong
about the value: `Machine::layout` refuses first. `model/tests/ver_a.rs`,
`m2_a_segment_of_the_largest_length_is_refused_before_module_frames` passes
with `Err(SegmentPlace)` for both lengths, from
`model/src/boot.rs:669-675`: "if segment.vaddr < chunk || end.is_none_or(|end|
end > geometry.user_end) { return Err(Refusal::SegmentPlace); }". A length
above the user range never reaches the layout or the iterator, and one below
it cannot make the product overflow. So the model does what the contract says
(`kernel-interface.md:1994`: "The first stage lays out the modules in order,
each on a page boundary"; the length is the start-up page's, `StartModule`) and the function is only unguarded on inputs no caller can
pass: the same class as H3, one step weaker, since nothing writes the
precondition at all.

Correction: `end: len.div_ceil(page).saturating_mul(page)` in `module_frames`
(the iterator's `next` also adds `self.phys + offset` at `:1325` and `at +
bytes` at `:1350`, which want the same treatment), and the sentence "The
frames of a module that fits the address space" on the function. Test that
fails without it: mine; it belongs in a new `abi/tests/` file with H3's, or in
`abi/src/tests.rs`.

## M3 — the `Geometry` accessors panic on a geometry `valid()` refuses. Real, low.

`abi/src/lib.rs:433` (`page`, `1 << page_shift[0]`), `:438` and `:442`
(`chunk_shift`, `chunk`, `1 << chunk_shift()`), `:467` (`root_entry`, `levels -
1`), `:476` (`canonical`, `address_bits() - 1`). Reproduced: `m3_the_accessors_panic_on_a_geometry_valid_refuses`
passes with four `catch_unwind`s — `page_shift[0] = 64` for `page`,
`page_shift[1] = 64` for `chunk`, the default geometry for `root_entry` and
for `canonical`. One correction of detail to the reviewer's text:
`page()` does not panic on the default geometry (`1 << 0` is 1); it panics on a
crafted shift, and `root_entry`/`canonical` are the two that panic on the
all-zero default the struct's doc names ("The default is all zero, which
[`Geometry::valid`] refuses", `abi/src/lib.rs:410`).

Not reachable through the model as written (a real machine's geometry is
validated at `model/src/boot.rs:631` before any use), and the crate's own
convention elsewhere is to write the precondition (`bandwidth`,
`TaskId::new`, `IrqSource::msi`, `RemoteRef::new`, `DeviceEntry::used` all
assert). The defect is that these six accessors, on the contract crate's
public type for a machine's values, promise a value and give a panic.

Correction: the precondition on `page`, `chunk_shift`, `chunk`, `address_bits`,
`root_entry` and `canonical` — `/// Only on a geometry [`Geometry::valid`]
accepts.` — and one Kani proof in `abi/src/lib.rs`'s proofs module,
`kani::assume(g.valid());` then `assert!(g.page() >= 4096)` and
`assert!(g.root_entry() * 2 <= 1 << (g.address_bits() - 1))`, which fails
today — with no assumption it meets the panic of M1 at once, and with the
assumption it pins the two facts. Test that fails without the change: that
proof; the four `catch_unwind`s of my probe stay as documentation.

## M5 — `abort_use` drops the two permission faults of levels −1 and −2. Real, medium.

`abi/src/aarch64.rs:231-241`: `0x04..=0x07 | 0x2A | 0x2B | 0x0C..=0x0F =>
Fault(Page)` and nothing for `0x2D`/`0x2E`, which fall to `_ => return None`
("reserved"). Reproduced:
`m5_a_permission_fault_at_level_minus_one_is_a_page_fault` and the level −2
test fail with `left: None`, and `m5_the_fault_status_codes_of_today` passes,
i.e. both are `None` today.

Why it is real, from inside the repository: the same arm classifies the
numbering of levels −1 and −2 for every other fault — `0x29` (address size,
level −1) and `0x2C` (access flag, level −1) as `NotThread`, `0x2A` and
`0x2B` (translation, levels −1 and −2) as `Page` — and then stops exactly at
`0x2C`, the last non-permission code of that numbering. Its own doc comment
says so: "A translation fault, at any level (−2 and −1 with FEAT_D128 and
FEAT_LPA2), and a permission fault are page faults (a permission fault has the
address translated: word 3 bit 3, *present*)" (`abi/src/aarch64.rs:217-230`),
with no level limit on the second clause, and `None` is documented as "for a
reserved value". The contract is wrong in the same line and has to move with
it: `kernel-interface.md:447` gives the page fault as "a translation fault
(0x04-0x07; 0x2B and 0x2A, levels −1 and −2) or a permission fault
(0x0C-0x0F, *present*)", listing levels −1 and −2 for the translation fault
and forgetting them for the permission fault.

Severity medium: a user thread whose table refuses a write with
`FEAT_LPA2`/`FEAT_D128` at level −1 or −2 is not a page fault in the model, so
whatever the kernel does with `None` happens to it instead of a delivery to
the memory service; and both the code and the contract are silent about it.

Correction: `0x04..=0x07 | 0x2A | 0x2B | 0x2D | 0x2E | 0x0C..=0x0F => Fault(Page)`
in `abort_use`, and "(0x0C-0x0F, and 0x2D and 0x2E at levels −1 and −2,
*present*)" in the contract's page-fault row. Tests that fail without it: my
two probes, plus the 64-value table H6 asks for, which would then pin every
one of these codes.

---

## What both reviewers missed, as my reproductions showed it

Neither report asked who consumes the architecture tables, and the answer is
nobody: `grep -rn "exception_use" model/` gives no match, and `ExceptionUse`,
`FaultKind::from_raw` and `abort_use` are not named anywhere in the model
either. The model raises a fault with a kind its caller chose
(`model/src/faults.rs:21`, `fn fault(&mut self, thread: ObjId, kind: FaultKind,
exception: [u64; 3])`), so the whole of the contract's `Faults` section that
maps `ESR_ELx` and `scause` onto the kinds — `abi/src/aarch64.rs`,
`abi/src/riscv64.rs`, and with them H1's `EC_SME` and M5's fault status codes
— is executed by nothing but the hand-written rows of
`arm64_and_riscv_exceptions_map_to_the_kinds_of_faults`. The executable model
of the contract does not model this part of it: no scenario can raise an
undefined instruction from a syndrome, so the trap loop H1 predicts cannot
appear in a run, and the misclassification M5 finds cannot fail an invariant.
Both reviewers wrote as though the model used these tables (H1 argues the
kernel "loads the state and resumes the thread", M5 argues about what a
handler sees), which is true of the contract and false of the code in front of
them. The second thing both missed is which of the two overflow findings is
reachable: M1's is, through `Model::boot` → `Machine::layout` →
`Geometry::valid`, and M2's is not, because `Refusal::SegmentPlace` refuses a
length above the user range first — the same reviewer graded both "should be
fixed" and neither report ran either, while running one tells the two apart.
And a third: every defect of this lot survives the whole verification
command. `nix develop -c ./verify` is green at head, and every one of my
probes fails beside it; no test in `abi/tests/review6.rs` or `abi/src/tests.rs`
builds a geometry or a length that the contract's own refusals name. A lot
whose tests exercise only the inputs that work reads green and is green on
nothing else.

## Findings, verdicts, corrections

| Finding | Verdict | Severity | Correction in one line |
|---|---|---|---|
| H1: `EC_SME` ignores ISS 2:0, so a `ZT0` trap answers SME and loops | real | high | `aarch64::exception_use`: split `EC_SME` into `sme_use(iss)`, `0b100 → Feature(SME2_ZT0)`, `0b001 → Fault(Undefined)`, else `Feature(SME)`; test rows in `arm64_and_riscv_exceptions_map_to_the_kinds_of_faults` (`esr(EC_SME, 0b100)`) |
| H2 = M4: doc names `aarch64::ec_use`, `riscv64::cause_use` | real | trivial | write `exception_use` twice in `abi/src/lib.rs:788`; no test |
| H3: `firing_instant` panics at `deadline == TIME_LIMIT`, 0 above it | real | low | `assert!(deadline < TIME_LIMIT)` and the comment fixed; `#[should_panic] a_deadline_at_the_limit_is_refused` |
| H4: `DeviceEntry::used` accepts `log2 < 12`, `base()` loses the base | real | low | `assert!((12..64).contains(&log2) && base & ((1 << log2) - 1) == 0)`; a round-trip test for `log2` in 12..64 and a `#[should_panic]` for 6 |
| H5: `size_at`'s doc names an `above` parameter that does not exist | real | trivial | delete "and that is above `above` if given" from `machine.rs:1317`; no test |
| H6: `AGENTS.md:52` unmet for `Geometry`, `Rights`, `TaskId`, `NodeGen`, all of `x86_64.rs`; `abort_use` proved only at code 0; 8 of 64 codes pinned; 17 `#[repr(C)]` structs without `offset_of!`; `CRASH_AREA_MAGIC` unasserted | real | medium | proofs for the listed pure functions, the arm64 proof given real ISS bits, a 64-code table, `offset_of!` for the 17 (`DeviceEntry` first), `assert_eq!(CRASH_AREA_MAGIC, …)`; the `barrier` half of the finding is refuted (mutation C fails) |
| H7 = M6: `trace_index(0, _)` panics | intended | none | none: the precondition is written, the proof assumes it, `model/src/debug.rs:93` cannot pass 0 |
| H8: `dr7_valid` accepts `LEN ≠ 0` with `R/W = 0b00` | contract's fault | low | contract sentence "a `LEN` that is not 0 with a `R/W` of `0b00` is `invalid`", then a third loop in `dr7_valid`; `assert!(!dr7_valid(1 \| 0b11 << 16))` |
| H9: `CoreWord::from_raw` accepts *leaving*, `RoleWord::from_raw` accepts a held word naming nobody | intended | none | none: the contract's read rule is the check field, the rest lives in `model/src/check/machine.rs:54-69`, and nothing calls `RoleWord::from_raw` |
| H10: `StartMachine`'s doc stops at D-137 | refuted | none | none: 92 bytes of fields round to 96 at layout 4, so the size is 96 from D-137 and `retired_words` filled padding (my probe asserts it) |
| M1: `Geometry::valid` overflows `s[i - 1] + per_level` | real | high | widen the two additions to `u16` (or bound `s[1..4]` first) in `Geometry::valid`; a `review6.rs` test for `page_shift: [12, 255, 1, 0]` and a model test that the boot gives `Refusal::MachineValues` |
| M2: `module_frames` overflows `div_ceil(page) * page` | real | low | `len.div_ceil(page).saturating_mul(page)` (and `phys + offset`, `at + bytes`); a test at `u64::MAX`; the reachability through the model is refuted by `Refusal::SegmentPlace` |
| M3: the six `Geometry` accessors panic on a geometry `valid()` refuses | real | low | write the precondition on `page`, `chunk_shift`, `chunk`, `address_bits`, `root_entry`, `canonical` and add a Kani proof under `kani::assume(g.valid())` |
| M5: `abort_use` drops `0x2D`/`0x2E`, the permission faults of levels −1 and −2 | real | medium | add both to the page-fault arm and to the contract's row (0x0C-0x0F, 0x2D, 0x2E *present*); a test per code, and the 64-code table of H6 |
