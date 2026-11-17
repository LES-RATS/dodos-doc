# Review of pull request: lot A (`abi/`)

Repository: `/private/tmp/dodos-pr3-final` (branch `model`, head `6312868`).
Verification run in copy `/private/tmp/dodos-pr3-A-hydrogen`:
- `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-A-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-A-hydrogen/Cargo.toml -p dodos-abi`: 74 unit tests + 2 integration tests (`review6.rs`) passed.
- `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-A-hydrogen -c cargo clippy --manifest-path /private/tmp/dodos-pr3-A-hydrogen/Cargo.toml --workspace --all-targets -- -D warnings`: passed with no warnings.

## Findings

### 1. `should be fixed` — `abi/src/aarch64.rs:75-77, 177-183, 197`: `EC_SME` ignores ISS bits and risks an infinite trap loop

Quoted code (`abi/src/aarch64.rs:75-77`, `177-183`, `197`):
```rust
/// SME trapped by `CPACR_EL1.SMEN` (or `CPTR_EL2`, `CPTR_EL3`), or an
/// instruction illegal for `PSTATE.SM` or `PSTATE.ZA`.
pub const EC_SME: u8 = 0x1D;
...
pub const fn exception_use(syndrome: u64) -> Option<ExceptionUse> {
    let ec = ((syndrome & ESR_EC_MASK) >> ESR_EC_SHIFT) as u8;
    if ec == EC_IABT_LOWER || ec == EC_DABT_LOWER {
        return abort_use((syndrome & 0x3F) as u8);
    }
    class_use(ec)
}
...
        EC_SME => Feature(SME),
```

What is wrong: `exception_use` delegates `EC_SME` (`0x1D`) straight to `class_use`, ignoring the syndrome's ISS bits and unconditionally returning `ExceptionUse::Feature(SME)`. As the doc comment on lines 75-76 itself states, `EC_SME` is raised both when SME is trapped by `CPACR_EL1.SMEN` (ISS bits 2:0 = `0b000`) and when a thread executes an instruction illegal for its current `PSTATE.SM` or `PSTATE.ZA` (ISS bits 2:0 != `0`, e.g., an SVE instruction in Streaming SVE mode or an SME instruction with `PSTATE.ZA == 0`), as well as when `ZT0` is trapped by `SMCR_ELx.EZT0 == 0` (`SME2_ZT0` on line 8, ISS bits 2:0 = `0b100`). Per `ExceptionUse::Feature` (`abi/src/lib.rs:796-799`), if a thread already has `SME` in its feature mask and its SME state is already loaded, the kernel loads the state and resumes the thread at the trapping instruction — which will trap again with `EC_SME` in an infinite loop instead of delivering `Fault(Undefined)` (or checking `SME2_ZT0`).

How I know: Read `abi/src/aarch64.rs` and `abi/src/lib.rs:796-800`.

### 2. `should be fixed` — `abi/src/lib.rs:787-789`: Doc comment names nonexistent functions `aarch64::ec_use` and `riscv64::cause_use`

Quoted code (`abi/src/lib.rs:787-789`):
```rust
/// What an exception taken from a user thread is (Faults), as the tables of
/// each architecture classify it (`aarch64::ec_use`, `riscv64::cause_use`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExceptionUse {
```

What is wrong: Neither `aarch64::ec_use` nor `riscv64::cause_use` exists anywhere in the crate; both functions are named `exception_use` (`abi/src/aarch64.rs:177`, `abi/src/riscv64.rs:87`, and called as such in `abi/src/lib.rs:1122, 1130`).

How I know: Read `abi/src/lib.rs`, `abi/src/aarch64.rs`, `abi/src/riscv64.rs`, and ran `grep -rn "ec_use\|cause_use" /private/tmp/dodos-pr3-final/abi/ /private/tmp/dodos-pr3-final/model/`, which matched only `abi/src/lib.rs:788`.

### 3. `should be fixed` — `abi/src/lib.rs:883-898`: `firing_instant` panics on `deadline == TIME_LIMIT` and returns `0` for `deadline > TIME_LIMIT`

Quoted code (`abi/src/lib.rs:883-898`):
```rust
pub const fn firing_instant(deadline: u64, tolerance: u64) -> u64 {
    if deadline == 0 {
        return 0;
    }
    let sum = deadline.saturating_add(tolerance);
    let x = if sum < TIME_LIMIT - 1 {
        sum
    } else {
        TIME_LIMIT - 1
    };
    let differ = (deadline - 1) ^ x;
    // The index of the highest bit in which deadline − 1 and x differ;
    // they differ, since x ≥ deadline.
    let m = 63 - differ.leading_zeros();
    x >> m << m
}
```

What is wrong: Unlike `bandwidth` (`abi/src/lib.rs:868`) and `TaskId::new` (`abi/src/lib.rs:1050`), `firing_instant` does not assert `deadline < TIME_LIMIT`. If called with `deadline == TIME_LIMIT` (`1 << 63`), `x` is clamped to `TIME_LIMIT - 1`, so `deadline - 1 == x`, `differ == 0`, `differ.leading_zeros() == 64`, and `63 - differ.leading_zeros()` panics with integer underflow. If called with `deadline > TIME_LIMIT`, `x < deadline` (falsifying the comment `since x >= deadline`), bit 63 of `differ` is `1`, `m == 63`, and `x >> 63 << 63` silently returns `0`. The Kani proof (`abi/src/lib.rs:1196`) masks this by assuming `deadline < TIME_LIMIT`.

How I know: Traced `abi/src/lib.rs:883-898` and `1193-1207` by hand.

### 4. `should be fixed` — `abi/src/machine.rs:638-644, 662-664`: `DeviceEntry::used` accepts `log2 < 7`, corrupting `base()`

Quoted code (`abi/src/machine.rs:624-626, 638-644, 662-664`):
```rust
/// One entry of the device table, 16 bytes: the base (aligned on the size,
/// at least one page) with the log2 of the size in bits 0-5 and bit 6 when
/// the entry is used; then an ownership word.
...
    /// A used entry of `1 << log2` bytes at `base`, unclaimed.
    pub const fn used(base: u64, log2: u32) -> Self {
        assert!(log2 < 64 && base & ((1 << log2) - 1) == 0);
        Self {
            range: base | log2 as u64 | Self::USED,
            owner: Ownership::free(Owner::Unclaimed),
        }
    }
...
    pub const fn base(&self) -> u64 {
        self.range & !0x7f
    }
```

What is wrong: Bits 0..=5 hold `log2` and bit 6 holds `Self::USED` (`1 << 6`), and `base()` masks out bits 0..=6 (`!0x7f`). However, `DeviceEntry::used` only asserts `log2 < 64`, not `log2 >= 7` (or `>= 12`, as the comment "at least one page" says). Calling `DeviceEntry::used(64, 6)` passes the assertion, sets bit 6 of `base` in `range`, and `entry.base()` silently returns `0` instead of `64`.

How I know: Read `abi/src/machine.rs:624-665`.

### 5. `should be fixed` — `abi/src/machine.rs:1317-1319`: Stale doc comment on `ModuleFrames::size_at`

Quoted code (`abi/src/machine.rs:1317-1319`):
```rust
    /// The largest supported size that suits position `offset` with `left`
    /// bytes left, and that is above `above` if given.
    fn size_at(&self, offset: u64, left: u64) -> PageSize {
```

What is wrong: The doc comment refers to a parameter `above` that does not exist on `size_at`.

How I know: Read `abi/src/machine.rs:1316-1335`.

### 6. `should be fixed` — `AGENTS.md:52`, `abi/`: Pure functions and branches missing Kani proofs or unit tests

Places and quoted code:
- `AGENTS.md:52`: `- A pure function of abi/ has a Kani proof (#[cfg(kani)]).`
- `abi/src/x86_64.rs` (lines 98, 121, 129, 136, 145): none of `dr7_valid`, `canonical`, `msi_remapped`, `msi_direct`, `rflags` has a `#[cfg(kani)]` proof.
- `abi/src/lib.rs` (lines 267-286, 301-318, 397, 425-521, 537, 576-593, 771, 920, 1049-1094): `Geometry::{bytes, page, chunk_shift, chunk, sizes, address_bits, root_entry, canonical, valid}`, `Rights::*`, `Marks::*`, `PageSize::from_raw`, `MemoryType::for_memory`, `mapping_rights`, `io_mapping_rights`, `FaultKind::from_raw`, `ClockPage::nanoseconds`, `TaskId::*`, `NodeGen::*` have no `#[cfg(kani)]` proof.
- `abi/src/machine.rs` (lines 76-105, 309-335, 638-664, 1454): `RemoteRef::*`, `GateWord::*`, `DeviceEntry::*`, `ports_meet` have no `#[cfg(kani)]` proof.
- `abi/src/debug.rs` (lines 65, 98-122): `TraceCode::user` and `TraceEntry::{code, continued, generation, slot, word2_of}` have no `#[cfg(kani)]` proof.
- `abi/src/ring.rs` (lines 108-145): `NodeMessage::{from_raw, ring, is_request, is_answer, answers}` have no `#[cfg(kani)]` proof.
- `abi/src/lib.rs:1116-1123` (`an_arm64_class_is_classified_exactly_when_the_architecture_defines_it`) always sets the low 12 bits of `syndrome` to `0`, so `aarch64::abort_use` (`abi/src/aarch64.rs:231-241`) is proved only at `fsc == 0`; `abi/src/tests.rs:2240-2270` tests only 7 of the 64 fault status codes.
- `abi/src/tests.rs:1438-1458` (`the_barrier_waits_for_every_node_that_could_reach_the_memory`) tests `Live`, `Dead`, `Sealed`, `Unfenced`, and `Fenced`, but never tests `Starting`, `Sealing`, `Fencing`, or `Fenced` with `!maps && !acknowledged_by_all`.
- `abi/src/debug.rs:36`: `CRASH_AREA_MAGIC` is not asserted in `abi/src/tests.rs`, and `fields_of_the_shared_layouts_have_their_offsets` (`abi/src/tests.rs:869-1046`) checks `offset_of!` for 20 of the 34 `#[repr(C)]` structs, omitting `FenceRecord`, `DeviceEntry`, `TraceEntry`, `StopRecord`, `BootNode`, `BootNodes`, and 11 `Start*` structs (though their `size_of!` is checked in `layouts_are_fixed`).

What is wrong: Many pure functions in `abi/` lack the Kani proofs required by `AGENTS.md:52`, and `abort_use`, `barrier`, and several `#[repr(C)]` field offsets have gaps in test coverage.

How I know: Read all 11 files of `abi/` and `AGENTS.md`.

### 7. `question` — `abi/src/debug.rs:78-80`: `trace_index` underflows if `seq == 0` (which is a valid sentinel in `TraceEntry::seq`)

Quoted code (`abi/src/debug.rs:76-80, 86`):
```rust
/// The entry of sequence `seq` (at least 1) sits at index (seq − 1) mod
/// `entries` of its ring.
pub const fn trace_index(seq: u64, entries: u64) -> u64 {
    (seq - 1) % entries
}
...
    /// The sequence, at least 1; 0 while the entry is being written.
    pub seq: u64,
```

What is wrong: Calling `trace_index(0, entries)` underflows `(seq - 1)` and panics, and `entries == 0` divides by zero; the Kani proof (`abi/src/debug.rs:250-266`) only checks `1 <= seq <= u32::MAX` and `entries` in `{256, 768}`. Should `trace_index` assert `seq >= 1 && entries != 0` (or return `Option<u64>`)?

How I know: Read `abi/src/debug.rs:76-88, 249-266`.

### 8. `question` — `abi/src/x86_64.rs:98-110`: `dr7_valid` allows non-zero `LEN` on execution breakpoints (`R/W == 0b00`)

Quoted code (`abi/src/x86_64.rs:98-110`):
```rust
pub const fn dr7_valid(word: u64) -> bool {
    if word & !DR7_USER_MASK != 0 {
        return false;
    }
    let mut n = 0;
    while n < HW_BREAKPOINTS {
        if word >> (16 + 4 * n) & 0b11 == DR7_CONDITION_IO {
            return false;
        }
        n += 1;
    }
    true
}
```

What is wrong: On x86-64 (Intel SDM Vol. 3, 18.2.4), an instruction-execution breakpoint (`R/W_n == 0b00`) requires `LEN_n == 0b00` (1 byte), and non-zero `LEN_n` with `R/W_n == 0b00` is undefined. `dr7_valid` only rejects `R/W_n == 0b10` (I/O) and bits outside `DR7_USER_MASK`, accepting e.g. `0b1100 << 16`. Is accepting non-zero `LEN` on execution breakpoints intentional, or should `dr7_valid` reject it?

How I know: Read `abi/src/x86_64.rs:88-110` and `model/src/check/debug.rs:167-174`.

### 9. `question` — `abi/src/machine.rs:1000-1003, 1136-1145`: `CoreWord::from_raw` and `RoleWord::from_raw` accept semantically invalid states

Quoted code (`abi/src/machine.rs:1000-1003`, `1136-1145`):
```rust
    pub const fn from_raw(raw: u64) -> Option<Self> {
        let word = Self::checked(raw);
        if word.0 == raw { Some(word) } else { None }
    }
...
    pub const fn from_raw(raw: u64) -> Option<Self> {
        let word = Self(raw);
        let ok = match raw & 0b11 {
            0 => word.holder() == ROLE_NOBODY && word.target() == ROLE_NOBODY,
            1 => word.target() == ROLE_NOBODY,
            2 => true,
            _ => false,
        };
        if ok { Some(word) } else { None }
    }
```

What is wrong: Unlike `Ownership::from_raw` and `Member::from_raw`, `CoreWord::from_raw` accepts `CoreState::Leaving` (which `abi/src/machine.rs:925-926` says no rule writes and the gate refuses) and accepts `CoreState::Free` with `slot != CORE_NO_SLOT` or `generation != 0` (leaving `model/src/check/machine.rs:60-69` to check those separately). Similarly, `RoleWord::from_raw` accepts `RoleState::Held` with `holder == ROLE_NOBODY` and `RoleState::Handing` with `holder == ROLE_NOBODY` or `target == ROLE_NOBODY` or `holder == target`. Is this split between `from_raw` and caller checks intentional?

How I know: Read `abi/src/machine.rs:549-563, 731-736, 917-1003, 1136-1145` and `model/src/check/machine.rs:54-69`.

### 10. `question` — `abi/src/start.rs:339-340`: `StartMachine` doc comment stops at D-137

Quoted code (`abi/src/start.rs:339-340, 381-387`):
```rust
/// Where the living part lies in the frame of slot 13, and its sizes (96
/// bytes since D-137, 88 since D-135, 80 since D-129).
```

What is wrong: `StartMachine` is 96 bytes in D-140 (layout 5, with `retired_words` occupying the 4 bytes of tail padding that D-137's 92 bytes left), whereas the comment only mentions D-137, D-135, and D-129 and omits D-140 / layout 5.

How I know: Read `abi/src/start.rs:339-388` and counted field sizes.

## Files read whole

- `AGENTS.md`
- `model/README.md`
- `.claude/skills/dodos-rust/SKILL.md`
- `.claude/skills/rust-1-100/SKILL.md`
- `abi/src/aarch64.rs`
- `abi/src/debug.rs`
- `abi/src/features.rs`
- `abi/src/lib.rs`
- `abi/src/machine.rs`
- `abi/tests/review6.rs`
- `abi/src/ring.rs`
- `abi/src/riscv64.rs`
- `abi/src/start.rs`
- `abi/src/tests.rs`
- `abi/src/x86_64.rs`

## Files read in part (only as needed to understand `abi/`)

- `Cargo.toml`, `abi/Cargo.toml`, `verify`
- `model/src/blocks.rs` (lines 300-335)
- `model/src/check/debug.rs` (lines 145-177)
- `model/src/check/machine.rs` (lines 45-100)
- `model/src/debug.rs` (lines 1-110, 500-670)
- `model/src/faults.rs` (lines 1-120)
- `model/src/irq.rs` (lines 1-175)
- `model/src/nodes.rs` (matched lines around `CoreWord::from_raw`)
