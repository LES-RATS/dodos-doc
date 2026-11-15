# Verification of Review 7 (DeepSeek) of the DodOS Kernel Contract and Reference Model

Verifier: `gemini-4-hydrogen`. Date: 16 November 2026.

Verified against:
- Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` (Docs commit `3bc7597`)
- Reference model & ABI: `/Users/btw/Documents/repos/dodos-kernel` (branch `model`, commit `2afc901`)
- Reviewer report: `/Users/btw/Documents/repos/Docs/reviews/2026-11-16-model-review-7-deepseek.md`
- Reviewer test file: `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/review7/tests/deepseek/review7_deepseek.rs`
- Independent verification tests (preserved on disk): `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/review7/tests/verify-deepseek/verify7_deepseek.rs`

All work ran in `/tmp/review7-verify-deepseek` (at `2afc901`, with `model/src/system.rs` patched to panic if `System::deliver` delivers a message out of order on any `(from, to)` ring). Running DeepSeek's `review7_deepseek.rs` on all three page sizes (`DODOS_PAGE` unset, `16k`, `32k`) reproduced 2 passing probes (`a_map_count_that_would_pass_its_limit_within_one_call_is_busy`, `the_gate_word_of_a_chunk_holds_no_count_of_pages_not_of_class_data`) and 3 failing probes (`the_canonical_boundary_follows_the_architecture_and_not_the_user_range_end`, `a_device_leaf_is_not_counted_in_the_gate_word_of_a_chunk`, `a_partial_mapping_is_not_completed_by_a_call_of_another_page_count`). Running `verify7_deepseek.rs` on all three page sizes (12 tests: 9 asserting violated contract rules that fail on `2afc901`, 3 asserting model behavior / refutations that pass) gave identical verdicts on all three geometries.

## Summary table

| Finding | Verdict | Side | Severity | How you know |
|---|---|---|---|---|
| F1 | CONFIRMED | abi, tests | wrong result | `f1_canonical_follows_address_bits_in_abi_and_thread_write_regs` fails on 4K/16K/32K; `abi/src/lib.rs:443-449`, `model/tests/faults.rs:318, 509` |
| F2 | CONFIRMED | contract, model | wrong result | `f2_partial_aspace_map_rejects_different_page_count` fails on 4K/16K/32K; `kernel-interface.md:282, 887`, `model/src/memory.rs:196-206` |
| F3 | CONFIRMED | contract, abi | wording | Contract reading: `kernel-interface.md:139, 284, 342, 1540`, `abi/src/lib.rs:199` |
| F4 | CONFIRMED | contract | wrong result | Contract reading: `kernel-interface.md:134, 139, 284-286, 341-347`; `f4_iospace_attach_state_denied_precedes_trailing_busy_checks` passes on 4K/16K/32K |
| F5 | CONFIRMED | model, tests | wrong result | `f5_gate_word_bits_32_to_44_count_non_data_pages` fails on 4K/16K/32K (`not_data() == 0`); `abi/src/machine.rs:175-205`, `model/src/check/table.rs:287-289` |
| F6 | CONFIRMED | model | wrong result | `f6_device_and_kept_leaves_do_not_increment_chunk_gate_words` fails on 4K/16K/32K; `model/src/memory.rs:74-108` |
| F7 | CONFIRMED | model | wrong result | Inspection (`pub(crate)` internals): `model/src/table.rs:127-130`, `model/src/memory.rs:297-300, 329-348`, `model/src/caps.rs:333` |
| F8 | NOT A FAULT | contract, model, tests | - | `kernel-interface.md:284` (explicit defence); `model/src/check/tests.rs:2411` already tests all three `Denied` cases |
| F9 | CONFIRMED IN PART | contract | wording | `f9_completed_stepped_mapping_is_not_partial_and_hits_protect_fifth_clause` passes on 4K/16K/32K (refuting "always partial"), while `run <= E * chunk` + F10 make `> E` unreachable under `gate_chunks = E` |
| F10 | CONFIRMED | contract, abi | wrong result | `f10_geometry_valid_refuses_page_larger_than_e_chunks` fails on 4K/16K/32K; `abi/src/lib.rs:459-478`, `model/src/memory.rs:226-235` |
| F11 | CONFIRMED | contract, abi | wording | Contract reading: `kernel-interface.md:886`, `abi/src/machine.rs:112-114` |
| F12 | CONFIRMED | model | wording | Inspection: `model/src/recovery.rs:1023-1026` vs `kernel-interface.md:1124` |

Count per verdict (F1–F12): `CONFIRMED`: 10, `CONFIRMED IN PART`: 1, `NOT A FAULT`: 1 (plus 5 new sibling findings `N1`–`N5`).

---

## Verification of findings F1–F12

### F1 — `CONFIRMED` (`abi`, `tests` | `wrong result`)

- **Test**: `f1_canonical_follows_address_bits_in_abi_and_thread_write_regs` (fails identically on 4K, 16K, and 32K).
- **What it asserts**: On a valid geometry (`Geometry::valid()` accepts `user_end = 1 << (address_bits - 2)`, `abi/src/lib.rs:477`), both `(1 << (bits - 1)) - 0x1000` (lower half) and `u64::MAX << (bits - 1)` (upper half) must satisfy `low_geom.canonical(...)`, and `ThreadWriteRegs` with `rip = (1 << (bits - 1)) - 0x1000` must succeed.
- **Result**: Fails at `low_geom.canonical(0x7ffffffff000)` (`4K`), `0x3ffffffff000` (`16K`), and `0x3fffffffff000` (`32K`) because `Geometry::canonical` (`abi/src/lib.rs:446-449`) uses `self.user_end.next_power_of_two()` instead of `self.address_bits()`. Note that `model/tests/faults.rs:318, 509` also embeds `user_end.next_power_of_two()` (`tests` side).

### F2 — `CONFIRMED` (`contract`, `model` | `wrong result`)

- **Test**: `f2_partial_aspace_map_rejects_different_page_count` (fails identically on 4K, 16K, and 32K).
- **What it asserts**: Starting a 4-page `aspace_map` with `gate_chunks = 1` returns `Err(Error::Again)` with 1 page mapped; resuming with `count = 3` (different from the starting `count = 4`) must not complete the mapping with `Ok(Output::Done)`.
- **Result**: Fails across all three geometries (`left: Ok(Done), right: Ok(Done)`): `kernel-interface.md:282, 887` omits `count` from the resumption identity, and `model/src/memory.rs:196-206` checks `m.count < map.count` without storing the requested count. (Minor note on DeepSeek's prose: DeepSeek wrote "accepts any larger or smaller count than the number of pages still to write"; in fact `map.count <= m.count` returns `Busy`, while any `map.count > m.count` other than the original count completes with `Ok(Done)`.)

### F3 — `CONFIRMED` (`contract`, `abi` | `wording`)

- **Text passages**:
  - Passage 1 (`kernel-interface.md:1540`):
    > ``| `denied` | A right is missing |``
    (Repeated in `abi/src/lib.rs:199`: `/// A right is missing. Denied = 3`)
  - Passage 2 (`kernel-interface.md:139`):
    > ``4. the state: `busy`, `no_slot` (the destination slot is not empty), `no_memory`, `would_wait`, `budget` (only `sched_configure` returns it, and it has no other state error, D-110); and `denied` from two state checks that guard a rule of the gate rather than a right of a capability: the class check of a mapping ([Calls on address spaces](#calls-on-address-spaces)) and the owner of a device identifier for `iospace_attach` ([IOMMU](#iommu)).``
    (Also `kernel-interface.md:284` and `:342`.)
- **Which reading a kernel author would take**: A kernel author would read Passage 2 and the per-call rules (`:284`, `:342`) as authoritative for when to return `denied`, treating line `1540` as an abbreviated error-table summary.
- **Could two authors write kernels that return different results?**: **No.** Both the explicit per-call tables and line `139` unambiguously specify `denied` for those checks, and the sibling `denied` checks (`N3`) are also unambiguous in their call rows.

### F4 — `CONFIRMED` (`contract` | `wrong result`)

- **Test**: `f4_iospace_attach_state_denied_precedes_trailing_busy_checks` (passes on 4K, 16K, and 32K).
- **What it asserts**: Node 0 attaches device `1`; Node 1 fills an `iospace` with 16 devices (`2..=17`, hitting `IOSPACE_MAX_DEVICES` = `busy`, line `346`) and then calls `IoSpaceAttach` on device `1` (hitting identifier owner `denied`, line `342`). The reference model returns `Err(Error::Denied)` (`model/src/memory.rs:492` before `:504`).
- **Text passages**:
  - Passage 1 (`kernel-interface.md:134, 139`):
    > ``Every call checks in this order and returns the first failure:``
    > ``4. the state: `busy`, `no_slot` (the destination slot is not empty), `no_memory`, `would_wait`, `budget` (only `sched_configure` returns it, and it has no other state error, D-110); and `denied` from two state checks that guard a rule of the gate rather than a right of a capability: the class check of a mapping ([Calls on address spaces](#calls-on-address-spaces)) and the owner of a device identifier for `iospace_attach` ([IOMMU](#iommu)).``
  - Passage 2 (`kernel-interface.md:284-285` and `:340-347`):
    > ``- a page the mapping targets is of a class that refuses the leaf ... (`denied` ...);``
    > ``- a map count of a chunk of the frame would pass `MAP_COUNT_MAX` ... (`busy`);``
    and for `iospace_attach`:
    > ``- With an iospace, the state is judged in this order:``
    > ``  - the device is one the kernel uses (`busy`);``
    > ``  - the device's identifier word is taken by another node that is not dead, or fails its check (`denied`);``
    > ``  - the device is attached to another iospace (`busy`; detach it first);``
    > ``  - the device is already attached to this iospace (success, nothing changes);``
    > ``  - the iospace serves devices of another unit (`busy`);``
    > ``  - the iospace already serves 16 devices (`busy`);``
    > ``  - the unit has no free domain number (`busy`).``
- **Which reading a kernel author would take**: Most authors would follow the per-call `"in this order"` lists (as the model does), treating item 4's list as an inventory of state errors.
- **Could two authors write kernels that return different results?**: **Yes.** An author who reads item 4 (`:134, 139`) literally as an ordering of state errors (`busy` before `denied`) returns `busy` in `f4_iospace_attach_state_denied_precedes_trailing_busy_checks`, whereas an author following `:340-347` returns `denied`. (And because `:341` puts `kernel_devices` `busy` *before* `denied` while `:343-347` put `busy` *after* `denied`, no single global order of `busy` vs `denied` fits item 4.)

### F5 — `CONFIRMED` (`model`, `tests` | `wrong result`)

- **Test**: `f5_gate_word_bits_32_to_44_count_non_data_pages` (fails on 4K, 16K, and 32K).
- **What it asserts**: After taking a 1-chunk run, allocating an `ASpace`, and mapping 1 page using that chunk as the table untyped, `GateWord::from_raw(k.m.map_count(chunk)).unwrap().not_data()` must be `> 0` because the chunk holds table pages (`G2`/`G4`, `kernel-interface.md:886, 888`).
- **Result**: Fails across all three geometries with `got raw 0x0`: the model stores raw leaf counts in `table.maps: Arc<Vec<u64>>`, never uses `abi::GateWord`, and invariant 58 (`model/src/check/table.rs:287-289`, `model/src/system.rs:540`) pins `bits 32..45` to `0`.

### F6 — `CONFIRMED` (`model` | `wrong result`)

- **Test**: `f6_device_and_kept_leaves_do_not_increment_chunk_gate_words` (fails on 4K, 16K, and 32K).
- **What it asserts**: Mapping 1 device page (from `DEVICE`) and 1 kept/global read-only page (`START_SLOT_MACHINE_LIVING`) must leave `map_count(chunk)` unchanged because `G2` (`kernel-interface.md:886`) says `"A page of device memory or of the global read-only set lies in no chunk"`.
- **Result**: Fails on all three geometries:
  - 4K: `device chunk 1 changed 0->1 and kept chunk 0 changed 16->17`
  - 16K: `device chunk 0 changed 4->5 and kept chunk 0 changed 5->6`
  - 32K: `device chunk 0 changed 2->3 and kept chunk 0 changed 3->4`
  (Note: DeepSeek's side remark at line 364 that `mapped_block` makes G5 mean nothing for device blocks is overstated: `idle_block` at `model/src/blocks.rs:175-178` rejects live device blocks via `untyped.live != 0` before `mapped_block` is called.)

### F7 — `CONFIRMED` (`model` | `wrong result`)

- **How verified**: Inspection of `model/src/table.rs:127-130` (`pub(crate) enum PageClass { Table }`), `model/src/memory.rs:297-300` (inserts `PageClass::Table` with no level), `model/src/caps.rs:333` (aspace root inserts `PageClass::Table`; `IoSpace` root/lower tables are never tagged `IOSPACE_TABLE`), and `model/src/memory.rs:329-348` (`class_of` always returns `abi::PageClass::table(1)` regardless of level and never produces `GATE` or `IOSPACE_TABLE`). `table.classes` is `pub(crate)`, so no public `Model` API exposes the missing level or `IOSPACE_TABLE` tag directly, which matches why DeepSeek verified it by reading.

### F8 — `NOT A FAULT` (`contract`, `model`, `tests` | `-`)

- **How verified**: Contract reading and existing test inspection.
- **Contract quote** (`kernel-interface.md:284`):
  > ``(`denied`; the only `denied` judged with the state: what the frame capability grants and what the page may carry are two separate rules, and a correct kernel never reaches this one, since frames never cover table or gate pages, kept frames have no `write` and device frames no `exec`);``
  The contract explicitly documents the class check as defence-in-depth rather than a reachable user-space state, so its unreachability in normal calls is intentional, not a fault. Furthermore, DeepSeek missed `model/src/check/tests.rs:2411-2437` (`a_leaf_whose_page_class_refuses_it_is_denied_by_the_call`), which already builds synthetic `table.classes`, `kept`, and `memory` states to exercise all three `Denied` branches of `aspace_map` and `aspace_protect`.

### F9 — `CONFIRMED IN PART` (`contract` | `wording`)

- **Test**: `f9_completed_stepped_mapping_is_not_partial_and_hits_protect_fifth_clause` (passes on 4K, 16K, and 32K).
- **What it asserts**: Part A maps a 2-page frame with `gate_chunks = 1` in two steps (`Again`, then `Ok(Done)`), leaving `partial == false`, and confirms `ASpaceProtect` returns `Err(Error::Busy)` via the 5th clause (`touched > gate_chunks`). Part B confirms that with default `gate_chunks == E`, `MemoryTake` rejects runs `> E * chunk` (`Err(Invalid)`).
- **Text passages**:
  - Passage 1 (`kernel-interface.md:292`):
    > ``(`busy` if the record is empty, a binding, a partial mapping, a mapping in another space, or a mapping that touches more than *E* chunks, which only a mapping made in steps does; then `denied` if a page of the mapping is of a class that refuses the new rights, as in `aspace_map`).``
  - Passage 2 (`kernel-interface.md:288`, `887`):
    > ``A mapping whose leaves touch more than *E* chunks is written in steps (G3): each call writes the leaves whose checks fit, the record holds the pages written so far and the mark *partial*, and the call returns `again`; the last step clears the mark.``
    > ``a mapping whose leaves touch more makes progress in steps: ... and the step that writes the last leaf clears the mark and returns success.``
- **Which part is confirmed and which part falls**:
  - **Confirmed part**: With `gate_chunks == E`, `largest_page <= E * chunk` (`F10`), and `run <= E * chunk` (`G3`, `model/src/blocks.rs:40`, `model/src/caps.rs:110`), every ordinary frame lies in `<= E` physical chunks and every device frame has `<= E` pages, so no completed mapping can touch more than `E` chunks at runtime without lowering `gate_chunks` (a test knob, though the contract explicitly uses such test knobs for `map_count_max` in `G4`).
  - **Refuted part**: DeepSeek's core argument — `"a mapping made in steps is always partial and therefore always busy"` (report lines 445, 468) — is **false**: the last step clears `partial` (`:288`, `:887`). Deleting the 5th clause as DeepSeek recommends would break `f9_completed_stepped_mapping_is_not_partial_and_hits_protect_fifth_clause` and `model/tests/gate_attack.rs:514-516` (`gate_chunks = 1`), and DeepSeek's proposed sentence (`"a mapping made in steps is always partial"`) contradicts `:288` and `:887`.
- **Which reading a kernel author would take & divergence**: An author reads `"a mapping made in steps"` as a completed stepped mapping (`partial == false`, `touched > E`). **No** two reasonable authors would return different results on a legal machine (`touched <= E` always under unmodified `E`, and under a lowered `gate_chunks` knob both return `busy`).

### F10 — `CONFIRMED` (`contract`, `abi` | `wrong result`)

- **Test**: `f10_geometry_valid_refuses_page_larger_than_e_chunks` (fails on 4K, 16K, and 32K).
- **What it asserts**: A `Geometry` with `page_shift: [12, 21, 30, 39]`, `entries: 512`, `levels: 4` (where one `Large3` = 512 GiB leaf spans `2^18 > E = 512` chunks) must be rejected by `Geometry::valid()`, because `model/src/memory.rs:226-235` forces `step >= 1` per `aspace_map` call and G3 (`kernel-interface.md:887`) states `"One call of the gate checks at most E chunks"`.
- **Result**: Fails across all three geometries (`four_level_512.valid()` returns `true`).

### F11 — `CONFIRMED` (`contract`, `abi` | `wording`)

- **Text passages** (`kernel-interface.md:886`, within G2):
  - Passage 1:
    > ``The byte is `PageClass` of `abi/`: 0 *data*, 1 *gate*, 2 *global read-only*, 3 *device*, 4 *iospace table*, 16 + *k* *page table of level k* (*k* from 1, the tables whose entries are pages, to *L*); every other value fails the check, as a word with state 3 does.``
  - Passage 2 (two sentences later in the same paragraph):
    > ``A page of device memory or of the global read-only set lies in no chunk: its class is not stored but follows from where it lies (an entry of the device table, a kept range), and the gate reads it from there.``
- **Which reading a kernel author would take**: A kernel author follows Passage 2 — ordinary-RAM class arrays hold `{0, 1, 4, 16 + k}` while device/kept pages are classified from the device table and kept ranges, using `abi::PageClass::{GLOBAL_READ_ONLY, DEVICE}` (`2`, `3`) as logical class values (exactly as `model/src/memory.rs:329-348` does).
- **Could two authors write kernels that return different results?**: **No** on any legal execution, because user space cannot write raw `PageClass` bytes; a kernel bug corrupting an ordinary-RAM byte to `2` or `3` would already violate `G2`, and either reading still rejects `write`/`exec` or treats `2`/`3` as invalid.

### F12 — `CONFIRMED` (`model` | `wording`)

- **How verified**: Inspection of `model/src/recovery.rs:1023-1026` (`// CONTRACT-GAP (reported): the barrier does not say that the context entries of the node must be gone...`) against `kernel-interface.md:1124` (`"and no context entry of any IOMMU unit names X's generation ... every unit role is held, not handing, by a node that is live or sealing, and that holder has acked[X] = g"`), which closed that gap while the model comment remained stale.

---

## New sibling findings (`N1`–`N5`)

### N1 — `abi::Geometry::valid` permits `user_end == 1 << (address_bits - 1)`, leaving no entry for the reserved slot (`abi` | `wrong result`, next to F1)

- **Test**: `n1_geometry_valid_leaves_room_for_reserved_slot` (fails on 4K, 16K, and 32K).
- **What is wrong**: `abi/src/lib.rs:477` checks `self.user_end <= 1 << (self.address_bits() - 1)` instead of `<`. When `user_end == 1 << (address_bits - 1)`, the user range occupies every canonical lower-half root slot, leaving no lower-half address for the kernel's reserved slot (`kernel-interface.md:258, 1726`).
- **Also**: `model/tests/faults.rs:318, 509` repeats F1's `user_end.next_power_of_two()` error (`tests` side).

### N2 — `iospace_map` shares F2's partial-mapping `count` bug (`contract`, `model` | `wrong result`, next to F2)

- **Test**: `n2_partial_iospace_map_rejects_different_page_count` (fails on 4K, 16K, and 32K).
- **What is wrong**: `Syscall::IoSpaceMap` dispatches directly to `Model::aspace_map` (`model/src/lib.rs:1410`, `model/src/memory.rs:144, 196-206`), so starting a 4-page `iospace_map` with `gate_chunks = 1` (`Again`) and resuming with `count = 3` completes with `Ok(Output::Done)` as a 3-page IOMMU mapping.

### N3 — More `denied` sites without missing `Rights` falsify line 284's uniqueness claim, and `iospace_attach` puts `busy` both before and after `denied` (`contract` | `wording` / `wrong result`, next to F3 and F4)

- **Test**: `n3_other_state_denied_calls_and_iospace_attach_busy_before_denied` (passes on 4K, 16K, and 32K).
- **What is wrong**:
  1. Line `284` says `"denied; the only denied judged with the state"`, but `aspace_protect` (`292`), `iospace_map` (`333`), `iospace_attach(..., 0)` (`349`), `cap_derive` re-badging (`147`), and `task_exempt` (`929`) all return `denied` without a missing `Rights` bit — falsifying both `:1540` and `:284`.
  2. `iospace_attach` checks `kernel_devices` (`busy`, `:341`) *before* identifier owner (`denied`, `:342`) and four `busy` rules (`:343-347`) *after* `denied`, so `busy` and `denied` cannot simply be reordered in `"Order of checks"` (`:139`).

### N4 — `iospace_map` of a device leaf and multi-node kept mappings write `*none*` chunk gate words from both nodes (`model` | `breaks isolation between nodes`, next to F6)

- **Test**: `n4_iospace_device_leaf_and_two_node_kept_mappings_write_none_chunk_gate_word` (fails on 4K, 16K, and 32K).
- **What is wrong**:
  1. `IoSpaceMap` of a device frame increments `table.maps[dev_chunk]` (`4K`: `0->1`; `16K`: `8->9`; `32K`: `4->5`).
  2. When both Node 0 and Node 1 in `System::boot(&Machine::example())` map their kept `START_SLOT_MACHINE_LIVING` frame (which lies in `*none*` chunk `0` on all three geometries), **both nodes** mutate the gate word of chunk `0` (`4K`: `[(0, 32, 33), (1, 33, 34)]`; `16K`: `[(0, 9, 10), (1, 10, 11)]`; `32K`: `[(0, 5, 6), (1, 6, 7)]`), violating `G4`'s single-writer rule (`"so each count has one writer"`). Even before user calls, on `16K` and `32K`, boot's kept image mappings already write chunk `0`'s `*none*` gate word (`4` per node on `16K`, `2` per node on `32K`).

### N5 — `abi::Geometry::valid` permits unaligned `page_shift` steps, breaking `tables()` level arithmetic while booting `Model` (`abi` | `wrong result`, next to F10)

- **Test**: `n5_geometry_valid_forbids_unaligned_page_shifts_and_oversized_leaf` (fails on 4K, 16K, and 32K).
- **What is wrong**: `abi/src/lib.rs:459-478` never requires `page_shift[i + 1] - page_shift[i] == log2(entries)`. Geometry `page_shift: [12, 18, 28, 0], entries: 512, levels: 3` passes `Geometry::valid()`, boots `Model::boot`, and maps a `Large1` (`256 KiB`) frame while `model/src/memory.rs:39` computes `(18 - 12) / 9 + 1 == 1` (inserting a level-1 table for a `Large1` leaf) and `Large2` (`256 MiB`) exceeds `E * chunk` (`128 MiB`).

---

## Appendix: Full test file (`verify7_deepseek.rs`)

```rust
//! Independent verification tests for Review 7 (DeepSeek) and sibling findings.
//!
//! Tests that assert a violated contract rule (F1, F2, F5, F6, F10, and new
//! findings N1, N2, N4, N5) FAIL on `dodos-kernel` commit `2afc901` with a
//! message naming the contract mismatch. Tests that verify contract compliance
//! or refute a mistaken finding (F4 model ordering, F9, N3) PASS.

mod common;

use dodos_abi::ObjectKind::{ASpace, Endpoint, Frame, IoSpace, Task, Thread};
use dodos_abi::*;
use dodos_model::*;

const UNTYPED: SlotAddr = SlotAddr::own(common::UNTYPED);
const CONTROL: SlotAddr = SlotAddr::own(START_SLOT_MEMORY_CONTROL);
const LIVING: SlotAddr = SlotAddr::own(START_SLOT_MACHINE_LIVING);
const IOMMU: SlotAddr = SlotAddr::own(18);
const VADDR: u64 = 1 << 30;

const fn slot(index: u32) -> SlotAddr {
    SlotAddr::own(common::slot(index))
}

fn retype_with(
    untyped: SlotAddr,
    kind: ObjectKind,
    size: u64,
    page: PageSize,
    memory: MemoryType,
    dst: u32,
) -> Syscall {
    Syscall::UntypedRetype {
        untyped,
        kind,
        size,
        page: page as u64,
        memory: memory as u64,
        destination: slot(dst),
    }
}

fn retype_small(kind: ObjectKind, size: u64, dst: u32) -> Syscall {
    retype_with(
        UNTYPED,
        kind,
        size,
        PageSize::Page,
        MemoryType::WriteBack,
        dst,
    )
}

fn aspace_map(
    space: SlotAddr,
    frame: SlotAddr,
    untyped: SlotAddr,
    at: u64,
    count: u64,
    rights: Rights,
) -> Syscall {
    Syscall::ASpaceMap(Map {
        space,
        frame,
        untyped,
        address: at,
        first: 0,
        count,
        rights: rights.bits(),
    })
}

fn iospace_map(
    space: SlotAddr,
    frame: SlotAddr,
    untyped: SlotAddr,
    at: u64,
    count: u64,
    rights: Rights,
) -> Syscall {
    Syscall::IoSpaceMap(Map {
        space,
        frame,
        untyped,
        address: at,
        first: 0,
        count,
        rights: rights.bits(),
    })
}

struct NodeHarness {
    m: Model,
    t: ObjId,
}

impl NodeHarness {
    fn on(machine: &Machine) -> Self {
        let (m, t) = Model::boot(machine).unwrap();
        Self { m, t }
    }

    fn new() -> Self {
        Self::on(&Machine::example())
    }

    #[track_caller]
    fn call(&mut self, call: Syscall) -> Outcome {
        let out = self.m.apply(self.t, call);
        assert_eq!(self.m.check(), Ok(()));
        out
    }

    #[track_caller]
    fn ok(&mut self, call: Syscall) {
        for _ in 0..40_000 {
            match self.call(call.clone()) {
                Ok(Output::Done) => return,
                Err(Error::Again) => {}
                other => panic!("expected Done/Again, got {other:?}"),
            }
        }
        panic!("exceeded step limit");
    }

    #[track_caller]
    fn err(&mut self, call: Syscall, expected: Error) {
        assert_eq!(self.call(call), Err(expected));
    }

    fn make_aspace(&mut self, aspace_idx: u32, thread_idx: u32, table_ut: SlotAddr) -> ObjId {
        self.ok(retype_with(
            table_ut,
            ASpace,
            0,
            PageSize::Page,
            MemoryType::WriteBack,
            aspace_idx,
        ));
        self.ok(retype_small(Thread, 0, thread_idx));
        self.ok(Syscall::ThreadConfigure {
            thread: slot(thread_idx),
            cspace: SlotAddr::own(START_SLOT_CSPACE),
            aspace: slot(aspace_idx),
            fault: SlotAddr::NONE,
            page: SlotAddr::NONE,
        });
        self.m.object_at(self.t, slot(thread_idx)).unwrap()
    }
}

struct TwoNodeHarness {
    sys: System,
    t: Vec<ObjId>,
}

impl TwoNodeHarness {
    fn new() -> Self {
        let (sys, t) = System::boot(&Machine::example()).unwrap();
        Self { sys, t }
    }

    #[track_caller]
    fn call(&mut self, node: u16, call: Syscall) -> Outcome {
        let out = self.sys.apply(node, self.t[node as usize], call);
        assert_eq!(self.sys.check(), Ok(()));
        out
    }

    #[track_caller]
    fn ok(&mut self, node: u16, call: Syscall) {
        for _ in 0..40_000 {
            match self.call(node, call.clone()) {
                Ok(Output::Done) => return,
                Err(Error::Again) => {}
                other => panic!("node {node} expected Done/Again, got {other:?}"),
            }
        }
        panic!("exceeded step limit on node {node}");
    }

    #[track_caller]
    fn err(&mut self, node: u16, call: Syscall, expected: Error) {
        assert_eq!(self.call(node, call), Err(expected));
    }

    #[track_caller]
    fn settle(&mut self) {
        for _ in 0..64 {
            if self.sys.pending().is_empty() {
                return;
            }
            self.sys.deliver(0);
            assert_eq!(self.sys.check(), Ok(()));
        }
        panic!("messages did not settle");
    }
}

// ---------------------------------------------------------------------------
// F1: Canonical-address check in `abi::Geometry::canonical` and `ThreadWriteRegs`.
// Contract line 423: "the words the architecture requires to be canonical addresses
// must be canonical".
// ---------------------------------------------------------------------------

#[test]
fn f1_canonical_follows_address_bits_in_abi_and_thread_write_regs() {
    let base = Machine::example().geometry;
    let bits = base.address_bits();
    let lower_user_end = 1u64 << (bits - 2);
    let low_geom = Geometry {
        user_end: lower_user_end,
        ..base
    };
    assert!(low_geom.valid());

    // Highest canonical lower-half address of this address width, and lowest
    // canonical upper-half address of this address width.
    let high_lower = (1u64 << (bits - 1)) - 0x1000;
    let low_upper = u64::MAX << (bits - 1);

    assert!(
        low_geom.canonical(high_lower),
        "F1: lower-half address {high_lower:#x} within {bits}-bit width must be canonical even when user_end={lower_user_end:#x}"
    );
    assert!(
        low_geom.canonical(low_upper),
        "F1: upper-half address {low_upper:#x} within {bits}-bit width must be canonical even when user_end={lower_user_end:#x}"
    );

    // Same failure observed through a kernel syscall (`thread_write_regs`):
    let mut machine = Machine::example_on(low_geom);
    machine.geometry = low_geom;
    let mut k = NodeHarness::on(&machine);
    k.ok(retype_small(Thread, 0, 30));
    let Ok(Output::Regs(mut regs)) = k.call(Syscall::ThreadReadRegs(slot(30))) else {
        panic!("expected ThreadReadRegs output");
    };
    regs[0] = high_lower; // REG_RIP = 0
    k.ok(Syscall::ThreadWriteRegs {
        thread: slot(30),
        block: regs,
    });
}

// ---------------------------------------------------------------------------
// F2: Partial mapping resumed with a different page count.
// Contract lines 282 & 887: resumption identity omits `count`, allowing a
// 4-page partial mapping to finish as a 3-page mapping with `Ok(Done)`.
// ---------------------------------------------------------------------------

#[test]
fn f2_partial_aspace_map_rejects_different_page_count() {
    let mut machine = Machine::example();
    machine.gate_chunks = 1;
    let mut k = NodeHarness::on(&machine);
    let viewer = k.make_aspace(30, 31, UNTYPED);
    k.ok(retype_small(Frame, 4, 32));

    k.err(
        aspace_map(slot(30), slot(32), UNTYPED, VADDR, 4, Rights::READ),
        Error::Again,
    );
    let page = k.m.geometry().page();
    assert!(k.m.translated(viewer, VADDR).is_some());
    assert!(k.m.translated(viewer, VADDR + page).is_none());

    // Resuming with a smaller count equal to the done count (1) returns Busy,
    // but resuming with count = 3 (smaller than original 4, larger than done 1)
    // wrongly succeeds with Ok(Done) and produces a 3-page mapping.
    let mut retry_short = Err(Error::Again);
    for _ in 0..3 {
        retry_short = k.call(aspace_map(
            slot(30),
            slot(32),
            UNTYPED,
            VADDR,
            3,
            Rights::READ,
        ));
        if retry_short != Err(Error::Again) {
            break;
        }
    }
    assert_ne!(
        retry_short,
        Ok(Output::Done),
        "F2: resuming a 4-page partial aspace_map with count=3 wrongly succeeded and finalized a 3-page mapping"
    );
}

// ---------------------------------------------------------------------------
// F4: `iospace_attach` checks identifier owner (`denied`, line 342) BEFORE
// four `busy` checks (lines 343-347), whereas Order of Checks line 139 puts
// `busy` before `denied`.
// ---------------------------------------------------------------------------

#[test]
fn f4_iospace_attach_state_denied_precedes_trailing_busy_checks() {
    let mut sys = TwoNodeHarness::new();
    sys.ok(0, retype_small(IoSpace, 0, 30));
    // Node 0 claims device identifier (0, 1) (Node 1 holds the unit role).
    assert_eq!(
        sys.call(
            0,
            Syscall::IoSpaceAttach {
                iommu: IOMMU,
                iospace: slot(30),
                device: 1,
            },
        ),
        Ok(Output::Waits)
    );
    sys.settle();
    assert_eq!(sys.sys.node(0).woken(sys.t[0]), Some(&Ok(Output::Done)));

    // Node 1 fills an iospace with 16 devices (2..=17) so any further attach
    // hits the `IOSPACE_MAX_DEVICES` (`busy`, line 346) state condition too.
    sys.ok(1, retype_small(IoSpace, 0, 30));
    for dev in 2..=17u64 {
        sys.ok(
            1,
            Syscall::IoSpaceAttach {
                iommu: IOMMU,
                iospace: slot(30),
                device: dev,
            },
        );
    }

    // Both `denied` (device 1 owned by node 0) and `busy` (16 devices) hold.
    // The model follows line 342 before line 346 (`Denied`), not line 139 (`Busy`).
    sys.err(
        1,
        Syscall::IoSpaceAttach {
            iommu: IOMMU,
            iospace: slot(30),
            device: 1,
        },
        Error::Denied,
    );
}

// ---------------------------------------------------------------------------
// F5: Gate word bits 32-44 (`not_data`, G4 line 888) remain 0 after placing a
// page table into a chunk.
// ---------------------------------------------------------------------------

#[test]
fn f5_gate_word_bits_32_to_44_count_non_data_pages() {
    let mut k = NodeHarness::new();
    let chunk_shift = k.m.geometry().chunk_shift();
    let chunk_size = k.m.geometry().chunk();
    let machine = Machine::example_on(k.m.geometry());
    let base = (machine.memory[4].base + 8 * chunk_size).next_multiple_of(1 << chunk_shift);
    let chunk = base >> chunk_shift;

    common::take_run(&mut k.m, k.t, chunk_shift, common::slot(40));
    // Creating an ASpace from slot(40) turns at least 2 pages in `chunk` into
    // table pages (non-data per G2).
    k.make_aspace(30, 31, slot(40));
    k.ok(retype_small(Frame, 1, 32));
    k.ok(aspace_map(
        slot(30),
        slot(32),
        slot(40),
        VADDR,
        1,
        Rights::READ,
    ));

    let raw = k.m.map_count(chunk);
    let word = GateWord::from_raw(raw).expect("valid GateWord");
    assert!(
        word.not_data() > 0,
        "F5: chunk {chunk} holds table pages, so GateWord::not_data() (bits 32-44) must be > 0, got raw {raw:#x}"
    );
}

// ---------------------------------------------------------------------------
// F6: Device leaves and global read-only (kept) leaves are counted in
// `table.maps[chunk]`, though G2 (line 886) says both lie in no chunk.
// ---------------------------------------------------------------------------

#[test]
fn f6_device_and_kept_leaves_do_not_increment_chunk_gate_words() {
    let mut k = NodeHarness::new();
    common::take_device(&mut k.m, k.t);
    let chunk_shift = k.m.geometry().chunk_shift();
    let _viewer = k.make_aspace(30, 31, UNTYPED);

    // 1. Device leaf:
    k.ok(Syscall::UntypedRetype {
        untyped: SlotAddr::own(common::DEVICE),
        kind: Frame,
        size: 1,
        page: PageSize::Page as u64,
        memory: MemoryType::Uncached as u64,
        destination: slot(32),
    });
    let (_, _, dev_base) = k.m.frame_at(k.t, slot(32)).unwrap();
    let dev_chunk = dev_base >> chunk_shift;
    let dev_before = k.m.map_count(dev_chunk);
    k.ok(aspace_map(
        slot(30),
        slot(32),
        UNTYPED,
        VADDR,
        1,
        Rights::READ,
    ));
    let dev_after = k.m.map_count(dev_chunk);

    // 2. Global read-only (kept) leaf:
    let (_, _, kept_base) = k.m.frame_at(k.t, LIVING).unwrap();
    let kept_chunk = kept_base >> chunk_shift;
    let kept_before = k.m.map_count(kept_chunk);
    let page = k.m.geometry().page();
    k.ok(aspace_map(
        slot(30),
        LIVING,
        UNTYPED,
        VADDR + page,
        1,
        Rights::READ,
    ));
    let kept_after = k.m.map_count(kept_chunk);
    assert!(
        dev_after == dev_before && kept_after == kept_before,
        "F6: device chunk {dev_chunk} changed {dev_before}->{dev_after} and kept chunk {kept_chunk} changed {kept_before}->{kept_after}; both lie in no chunk"
    );
}

// ---------------------------------------------------------------------------
// F9: Completed multi-step mapping has `partial == false` and hits the 5th
// clause of `aspace_protect` ("touches more than E chunks, which only a
// mapping made in steps does", line 292). DeepSeek claimed this is dead.
// ---------------------------------------------------------------------------

#[test]
fn f9_completed_stepped_mapping_is_not_partial_and_hits_protect_fifth_clause() {
    // Part A (all 3 geometries with gate_chunks = 1):
    let mut machine = Machine::example();
    machine.gate_chunks = 1;
    let mut k = NodeHarness::on(&machine);
    k.make_aspace(30, 31, UNTYPED);
    k.ok(retype_small(Frame, 2, 32));
    k.err(
        aspace_map(slot(30), slot(32), UNTYPED, VADDR, 2, Rights::READ),
        Error::Again,
    );
    k.ok(aspace_map(
        slot(30),
        slot(32),
        UNTYPED,
        VADDR,
        2,
        Rights::READ,
    ));
    // Now `partial == false`: protect cannot hit the 3rd ("partial mapping")
    // clause, yet still returns `Busy` via the 5th ("more than E chunks") clause.
    k.err(
        Syscall::ASpaceProtect {
            aspace: slot(30),
            frame: slot(32),
            rights: Rights::READ.bits(),
        },
        Error::Busy,
    );

    // Part B (unmodified `gate_chunks == E`): `memory_take` forbids runs > E * chunk,
    // so a 2 * E-chunk run cannot be taken when largest_page <= E * chunk.
    let default_m = Machine::example();
    if let Some(large2) = default_m.geometry.bytes(PageSize::Large2)
        && large2 <= (1 << 30)
    {
        let mut k = NodeHarness::on(&default_m);
        let chunk = k.m.geometry().chunk();
        let ram = default_m.memory[4].base;
        let place = (ram + 8 * chunk).next_multiple_of(2 * large2);
        k.err(
            Syscall::MemoryTake {
                control: CONTROL,
                kind: 0,
                place,
                size: u64::from((2 * large2).trailing_zeros()),
                destination: slot(40),
            },
            Error::Invalid,
        );
    }
}

// ---------------------------------------------------------------------------
// F10: `Geometry::valid` accepts `largest_page > chunk * E`, breaking G3's
// "One call of the gate checks at most E chunks" given `step >= 1`.
// ---------------------------------------------------------------------------

#[test]
fn f10_geometry_valid_refuses_page_larger_than_e_chunks() {
    let four_level_512 = Geometry {
        page_shift: [12, 21, 30, 39],
        entries: 512,
        levels: 4,
        user_end: 1 << 46,
    };
    assert!(
        !four_level_512.valid(),
        "F10: 512 GiB Large3 leaf spans 2^18 > E=512 chunks, violating G3's one-call bound; Geometry::valid must reject it"
    );
}

// ---------------------------------------------------------------------------
// New sibling finding N1: `Geometry::valid` allows `user_end == 1 << (bits - 1)`,
// leaving no lower-half canonical entry for the reserved slot (line 258).
// ---------------------------------------------------------------------------

#[test]
fn n1_geometry_valid_leaves_room_for_reserved_slot() {
    let base = Machine::example().geometry;
    let bits = base.address_bits();
    let full_lower = Geometry {
        user_end: 1u64 << (bits - 1),
        ..base
    };
    assert!(
        !full_lower.valid(),
        "N1: user_end = 1 << {} fills the entire lower canonical half and leaves no lower-half entry for the reserved slot",
        bits - 1
    );
}

// ---------------------------------------------------------------------------
// New sibling finding N2: `iospace_map` shares F2's partial-count bug.
// ---------------------------------------------------------------------------

#[test]
fn n2_partial_iospace_map_rejects_different_page_count() {
    let mut machine = Machine::example();
    machine.gate_chunks = 1;
    let mut k = NodeHarness::on(&machine);
    k.ok(retype_small(IoSpace, 0, 30));
    k.ok(retype_small(Frame, 4, 31));

    k.err(
        iospace_map(slot(30), slot(31), UNTYPED, VADDR, 4, Rights::READ),
        Error::Again,
    );
    let mut retry_short = Err(Error::Again);
    for _ in 0..3 {
        retry_short = k.call(iospace_map(
            slot(30),
            slot(31),
            UNTYPED,
            VADDR,
            3,
            Rights::READ,
        ));
        if retry_short != Err(Error::Again) {
            break;
        }
    }
    assert_ne!(
        retry_short,
        Ok(Output::Done),
        "N2: resuming a 4-page partial iospace_map with count=3 wrongly succeeded and finalized a 3-page mapping"
    );
}

// ---------------------------------------------------------------------------
// New sibling finding N3: More `denied`s without a missing right (beyond F3's
// two), falsifying line 284's `"the only denied judged with the state"`, plus
// `iospace_attach` putting `busy` BEFORE `denied` as well as AFTER `denied`.
// ---------------------------------------------------------------------------

#[test]
fn n3_other_state_denied_calls_and_iospace_attach_busy_before_denied() {
    let mut sys = TwoNodeHarness::new();
    // 1. `cap_derive` re-badge returns `Denied` (line 147), not missing rights:
    sys.ok(0, retype_small(Endpoint, 0, 30));
    sys.ok(
        0,
        Syscall::CapDerive {
            source: slot(30),
            destination: slot(31),
            rights: Rights::ALL.bits(),
            badge: 7,
        },
    );
    sys.err(
        0,
        Syscall::CapDerive {
            source: slot(31),
            destination: slot(32),
            rights: Rights::ALL.bits(),
            badge: 8,
        },
        Error::Denied,
    );

    // 2. `task_exempt` returns `Denied` when the aware task is not mark-aware (line 929):
    sys.ok(0, retype_small(Task, 0, 33));
    sys.ok(0, retype_small(Task, 0, 34));
    sys.err(
        0,
        Syscall::TaskExempt {
            task: slot(33),
            aware: slot(34),
        },
        Error::Denied,
    );

    // 3. `iospace_attach(..., 0)` on another node's attached device returns `Denied` (line 349):
    sys.ok(0, retype_small(IoSpace, 0, 35));
    assert_eq!(
        sys.call(
            0,
            Syscall::IoSpaceAttach {
                iommu: IOMMU,
                iospace: slot(35),
                device: 1,
            },
        ),
        Ok(Output::Waits)
    );
    sys.settle();
    sys.err(
        1,
        Syscall::IoSpaceAttach {
            iommu: IOMMU,
            iospace: SlotAddr::NONE,
            device: 1,
        },
        Error::Denied,
    );

    // 4. `iospace_attach` puts `kernel_devices` (`busy`, line 341) BEFORE
    //    `denied` (line 342) and four `busy` checks AFTER `denied` (343-347):
    sys.ok(1, retype_small(IoSpace, 0, 35));
    sys.err(
        1,
        Syscall::IoSpaceAttach {
            iommu: IOMMU,
            iospace: slot(35),
            device: 0x00f8,
        },
        Error::Busy,
    );
}

// ---------------------------------------------------------------------------
// New sibling finding N4: `iospace_map` of a device leaf and multi-node boot
// kept-frame mappings write the gate word of `*none*` chunk 0 from BOTH nodes,
// breaking G4's single-writer rule ("so each count has one writer").
// ---------------------------------------------------------------------------

#[test]
fn n4_iospace_device_leaf_and_two_node_kept_mappings_write_none_chunk_gate_word() {
    let mut sys = TwoNodeHarness::new();
    let chunk_shift = sys.sys.node(0).geometry().chunk_shift();

    // 1. `iospace_map` of a device frame writes `table.maps[dev_chunk]`:
    let dev_delta = {
        let index = (0..sys.sys.node(0).device_count())
            .find(|&i| sys.sys.node(0).device_entry(i).base() == 2 << 20)
            .unwrap();
        sys.ok(
            0,
            Syscall::MemoryTake {
                control: CONTROL,
                kind: 1,
                place: index as u64,
                size: 0,
                destination: slot(30),
            },
        );
        sys.ok(0, retype_small(IoSpace, 0, 31));
        sys.ok(
            0,
            Syscall::UntypedRetype {
                untyped: slot(30),
                kind: Frame,
                size: 1,
                page: PageSize::Page as u64,
                memory: MemoryType::Uncached as u64,
                destination: slot(32),
            },
        );
        let (_, _, dev_base) = sys.sys.node(0).frame_at(sys.t[0], slot(32)).unwrap();
        let dev_chunk = dev_base >> chunk_shift;
        let before = sys.sys.node(0).map_count(dev_chunk);
        sys.ok(
            0,
            iospace_map(slot(31), slot(32), UNTYPED, VADDR, 1, Rights::READ),
        );
        (before, sys.sys.node(0).map_count(dev_chunk))
    };

    // 2. Both Node 0 and Node 1 mapping their kept `START_SLOT_MACHINE_LIVING`
    //    frame write the gate word of the same `*none*` chunk (chunk 0):
    let (_, _, living_base) = sys.sys.node(0).frame_at(sys.t[0], LIVING).unwrap();
    let kept_chunk = living_base >> chunk_shift;
    assert_eq!(
        Ownership::from_raw(sys.sys.node(0).ownership(kept_chunk))
            .unwrap()
            .state(),
        OwnState::None,
        "chunk {kept_chunk} holding living table has ownership state None"
    );
    let page = sys.sys.node(0).geometry().page();
    let mut kept_deltas = Vec::new();
    for node in 0..2u16 {
        let before = sys.sys.node(node).map_count(kept_chunk);
        sys.ok(node, retype_small(ASpace, 0, 40));
        sys.ok(
            node,
            aspace_map(slot(40), LIVING, UNTYPED, VADDR + 2 * page, 1, Rights::READ),
        );
        kept_deltas.push((node, before, sys.sys.node(node).map_count(kept_chunk)));
    }
    assert!(
        dev_delta.0 == dev_delta.1 && kept_deltas.iter().all(|&(_, b, a)| b == a),
        "N4: iospace device chunk changed {}->{}, and both nodes wrote kept *none* chunk {kept_chunk}: {kept_deltas:?}",
        dev_delta.0,
        dev_delta.1
    );
}

// ---------------------------------------------------------------------------
// New sibling finding N5: `Geometry::valid` allows unaligned `page_shift`
// steps, letting `Model::boot` run with `page_shift[1] != page_shift[0] + log2(E)`,
// breaking `tables()` level arithmetic and producing `Large2 > E * chunk`.
// ---------------------------------------------------------------------------

#[test]
fn n5_geometry_valid_forbids_unaligned_page_shifts_and_oversized_leaf() {
    let weird = Geometry {
        page_shift: [12, 18, 28, 0], // 4 KiB, 256 KiB (not 4 KiB * 512!), 256 MiB (1024 chunks > E=512)
        entries: 512,
        levels: 3,
        user_end: 1 << 38,
    };
    if weird.valid() {
        let machine = Machine::example_on(weird);
        // `Model::boot` accepts this geometry and allows `aspace_map` of a
        // 256 KiB `Large1` page that is not a level-2 table entry size.
        let mut k = NodeHarness::on(&machine);
        let chunk = weird.chunk();
        let ram = machine.memory[4].base;
        let place = (ram + 8 * chunk).next_multiple_of(chunk);
        k.ok(Syscall::MemoryTake {
            control: CONTROL,
            kind: 0,
            place,
            size: u64::from(chunk.trailing_zeros()),
            destination: slot(40),
        });
        k.ok(retype_with(
            slot(40),
            Frame,
            1,
            PageSize::Large1,
            MemoryType::WriteBack,
            41,
        ));
        k.make_aspace(30, 31, UNTYPED);
        k.ok(aspace_map(
            slot(30),
            slot(41),
            UNTYPED,
            VADDR,
            1,
            Rights::READ,
        ));
    }
    assert!(
        !weird.valid(),
        "N5: unaligned page_shift [12, 18, 28, 0] with E=512 boots Model, breaks table-level math for Large1, and has Large2 = 1024 > E chunks"
    );
}
```
