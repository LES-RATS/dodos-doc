# DodOS Kernel Model Review 6 — Sentence-by-Sentence Contract Pinning, Page Geometry, and `./verify` Runtime

- **Date:** 2026-11-16
- **Reviewer:** `gemini-4-argon`
- **Scope:**
  - Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` (commit `330d059`)
  - Reference model & ABI: `/Users/btw/Documents/repos/dodos-kernel` (branch `model`, commit `d4e883b`)
  - Pass-12 groups: unlike cores (`G1`), debugging & hardware breakpoints (`G2`), I/O ports (`G3`), entropy (`G4`), user-interrupt hook (`G5`), page size as a value of the machine (`G6`), and new values of `abi/` (`G7`).
- **Verdict:** **Needs changes** — 1 panic bug in `Model::core_stop` on single-node `Model` (`F1`), 1 contract/model discrepancy in `Machine::layout` where sub-chunk usable RAM fragments vanish from both ordinary and device memory (`F2`), 44 non-equivalent surviving mutants out of 168 across the 7 pass-12 groups (`F3`, with verified tests provided for all 44), hidden 4 KB / 16 KB assumptions in `Machine::example_on` and test helpers exposed by a valid 32 KB geometry (`F4`), and avoidable $O(N^2)$ / duplicate geometry-independent work in `./verify` consuming ~300 user CPU seconds (`F5`).

---

## Summary of Findings (Ordered Most Serious First)

1. **`F1` (Model Panic Bug — High): Calling `core_stop` (`KILL` or `RETIRE`) on `self.node` in single-node `Model` transitions node 0 to `MemberState::Fencing` without parking it, causing subsequent `memory_take`, `memory_give`, or `memory_split` calls to panic at `assert!(self.table.write_owner(...))` (`model/src/recovery.rs:195-208`, `model/src/blocks.rs:103,144,193`).**
2. **`F2` (Contract vs. Model Discrepancy — Medium-High): `Machine::layout` excludes sub-chunk usable RAM fragments from ordinary memory (`model/src/boot.rs:565-567`) but also excludes all `RegionKind::Usable` regions from device memory (`model/src/boot.rs:622`), violating the contract rule that device memory contains *"every address below the physical address width that is not ordinary memory, not kept by the kernel, and not of the UEFI type 'unusable memory'"* (`kernel-interface.md:3092-3095`).**
3. **`F3` (Unpinned Contract Sentences — Medium): Across 168 single-change mutants targeting the 7 pass-12 groups, 122 were killed (72.6%) and 46 survived (44 non-equivalent survivors + 2 structurally unreachable checks). Notably, mutating `SIXTEEN_KB` in `model/src/boot.rs:42` to 4 KB survived the entire `DODOS_PAGE=16k` test run.**
4. **`F4` (Hidden Page-Size Constants Exposed by a Third Geometry — Medium): Changing `SIXTEEN_KB` in `model/src/boot.rs:42-47` to a valid 32 KB geometry (`page_shift: [15, 27, 39, 0], entries: 4096, levels: 3`) passes `Geometry::valid()` but breaks 4 test binaries (`boot`, `dodos_model` lib, `calls`, `property`) due to hardcoded 4 KB / 16 KB sizes and single-step `untyped_retype` assumptions.**
5. **`F5` (`./verify` Runtime Regression — Medium): `./verify` consumes ~300 user CPU seconds (~155s per geometry pass, > 11 minutes on 1–2 vCPU CI runners), 96% of which is spent in 4 test binaries (`recovery`, `property`, `liveness`, `blocks`). Two changes alone — avoiding 16,384 redundant `m.check()` calls inside the 8,192-iteration setup loop of `blocks::memory_split_is_busy_when_no_entry_is_unused_and_unclaimed` and running the geometry-independent multi-node `recovery` and `liveness` suites once instead of twice — cut `./verify` CPU time by ~42% without losing a single check.**

---

## Detailed Findings

### `F1`: `Model::core_stop` on `self.node` in Single-Node `Model` Leaves Node 0 Running While `MemberState::Fencing`, Panicking Subsequent Block Operations

- **Location:**
  - `/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:195-208` (`Model::core_stop`)
  - `/Users/btw/Documents/repos/dodos-kernel/model/src/blocks.rs:103,144,193` (`Model::memory_take`, `Model::memory_give`, `Model::memory_split`)
  - `/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:582-591` (`Model::apply`)
- **Contract Reference:** `kernel-interface.md:2743-2765` (*"`core_stop` ... `busy` if stopping this core would leave the machine with no online core ... On `kill`, the call accuses that node with evidence `self_report` (5), parks the core at once"*).
- **Mechanism:**
  1. `Machine::example()` (`model/src/boot.rs:248-259`) defines 2 cores: node 0 (`hw_id: 0`) and phantom node 1 (`hw_id: 1`). Both start with `MemberState::Live` in `table.members` (`model/src/boot.rs:699,766`).
  2. When a thread on node 0 calls `Syscall::CoreStop { core: s(START_SLOT_FIRST), mode: CORE_STOP_KILL, drain_ns: 0 }` (or `CORE_STOP_RETIRE` with no replacement), `Model::core_stop` (`model/src/recovery.rs:171`) checks `if !self.live_nodes().any(|n| n != node)` — which is `false` because phantom node 1 is `MemberState::Live`.
  3. `core_stop` then calls `self.accuse_node(0, Evidence::SelfReport)` (`model/src/recovery.rs:197`), setting `self.table.members[0]` to `MemberState::Fencing` (where `MemberState::writes()` is `false`), and pushes `HwAction::ParkSelf { node: 0 }` to `self.hw_out`.
  4. In multi-node `System::apply` (`model/src/system.rs:416`), `HwAction::ParkSelf` sets `self.parked[0] = true`. However, in single-node `Model::apply` (`model/src/lib.rs:582-591`), `self.hw_out` is cleared and ignored (`self.hw_out.clear()`), so node 0 remains usable by the caller.
  5. A subsequent `Syscall::MemoryTake`, `Syscall::MemoryGive`, or `Syscall::MemorySplit` on node 0 passes all capability and ownership checks, then panics at `assert!(self.table.write_owner(self.node, index, before, after))` (`model/src/blocks.rs:103,144,193`) because `Table::write_owner` (`model/src/table.rs:254`) requires `self.member(writer).writes()`, which is `false` for `MemberState::Fencing`.
- **Reproduction Command & Output:**
  Ran on a minimal unit test in `dodos-model` (and triggered automatically by `property::all_seeds` seed 3 when geometry changes shift the PRNG stream):
  ```text
  thread 'repro_f1' panicked at model/src/blocks.rs:103:21:
  assertion failed: self.table.write_owner(self.node, index, before, after)
  ```
- **Proposed Fix:**
  Either:
  1. In `Model::live_nodes` (`model/src/recovery.rs:265`), treat phantom nodes in single-node `Model` as non-online for `core_stop` (or in `Model::core_stop`, refuse stopping `self.node` when running in single-node `Model` without `System`), **or**
  2. Track `parked: bool` on `Model` when `HwAction::ParkSelf { node: self.node }` is emitted so a parked single-node `Model` does not execute further syscalls or check `live_nodes` against unmodelled phantom nodes.

---

### `F2`: `Machine::layout` Drops Sub-Chunk Usable RAM From Both Ordinary Memory and Device Memory

- **Location:** `/Users/btw/Documents/repos/dodos-kernel/model/src/boot.rs:557-567` and `620-625`.
- **Contract Reference:** `kernel-interface.md:3064-3095` (*"Start-up state — Memory"*):
  - *"Ordinary memory: every range of usable memory ... that is not kept by the kernel is shrunk to whole pages; the parts of a range smaller than a chunk are left out, and the rest is cut into chunks."* (`kernel-interface.md:3064-3067`)
  - *"Device memory: every address below the physical address width that is not ordinary memory, not kept by the kernel, and not of the UEFI type 'unusable memory'."* (`kernel-interface.md:3092-3095`)
- **Discrepancy:**
  In `Machine::layout` (`model/src/boot.rs:557-567`), usable RAM is shrunk to pages (`ordinary`) and then narrowed to whole chunks (`chunks`). Sub-chunk fragments of usable RAM are excluded from `chunks` (and thus from ordinary memory).
  However, when computing device memory at `model/src/boot.rs:620-625`:
  ```rust
  let not_device = self
      .regions(RegionKind::Usable)
      .chain(self.regions(RegionKind::Unusable))
      .chain(kept);
  let device_ranges = subtract([(0, 1u64 << self.phys_width)], not_device);
  ```
  `layout` subtracts `self.regions(RegionKind::Usable)` instead of `chunks`! As a result, any usable RAM fragment smaller than a chunk (or the sub-page / sub-chunk tails of a usable RAM region) is neither in ordinary memory (`chunks`), nor in `kept`, nor `RegionKind::Unusable`, yet is also excluded from `device_ranges`.
  For example, in `Machine::example_on(GEOMETRY)` (`model/src/boot.rs:260-264`), usable region `(1 << 20, (258 << 20) - (1 << 20))` has ~400 KB in `0x19c000..0x200000` (between the end of the boot image and the 2 MB boundary) that is not kept and is smaller than a 2 MB chunk; it disappears from both ordinary memory and the device table.
- **Proposed Fix:**
  Either subtract `chunks.iter().copied()` instead of `self.regions(RegionKind::Usable)` when computing `not_device` in `model/src/boot.rs:621` (if the contract text is authoritative), or amend `kernel-interface.md:3092-3095` to state *"every address below the physical address width that is not of the UEFI usable-RAM types, not kept by the kernel, and not of the UEFI type 'unusable memory'"* (since sub-chunk fragments of normal RAM are not MMIO devices).

---

### `F3`: Sentence-by-Sentence Mutation Testing Across the 7 Pass-12 Groups (168 Mutants)

#### Methodology & Group Breakdown
We constructed **168 single-change mutants** (`/tmp/review6-gemini-argon/run_mutants.py`) across `abi/src/*.rs` and `model/src/{cores,debug,boot,memory,threads,sched,moves,faults}.rs`, each breaking one specific requirement, check order, constant, bitmask, or boundary in the 7 pass-12 groups, and ran the test binaries with a 30s process-group kill timeout (`os.killpg(SIGKILL)`).

| Group | Scope | Total Mutants | Killed | Survived (Non-Equiv) | Survived (Unreachable) | Kill Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **G1** | Unlike cores (`Kind`, `FeatureMask`, `kind_covers`, `thread_set_features`, `sched_count`, `thread_move`) | 34 | 22 | 11 | 1 (`#33`) | 64.7% |
| **G2** | Debugging (trace rings, rate limit, `CrashArea`, `debug_write`, `trace_emit`, console messages, HW breakpoints) | 34 | 26 | 8 | 0 | 76.5% |
| **G3** | I/O ports (`IoPortRange`, `ioport_check`, `ioport_in`, `ioport_out`, `ioports_issue`, refused ports) | 21 | 11 | 10 | 0 | 52.4% |
| **G4** | Entropy (`entropy_read`, dying CSpace check, `ENTROPY_MAX_BYTES`, mixing 4 words, zero-padding) | 10 | 6 | 4 | 0 | 60.0% |
| **G5** | User-interrupt hook (`FEATURE_USER_INTERRUPTS`, `REG_UINTR`, `FeatureMask::check`, `FeatureMask::fits`) | 10 | 6 | 3 | 1 (`#108`) | 60.0% |
| **G6** | Page size as a value of the machine (`Geometry`, `module_frames`, `SIXTEEN_KB`, `Model::start`, `tables`, `io_levels`) | 24 | 18 | 6 | 0 | 75.0% |
| **G7** | Every new value of `abi/` (call numbers, error codes, object kinds, sizes, bit layouts, start-up page entries) | 35 | 33 | 2 | 0 | 94.3% |
| **Total** | **All 7 Pass-12 Groups** | **168** | **122** | **44** | **2** | **72.6%** |

#### The 2 Structurally Unreachable / Redundant Checks (`#33` and `#108`)
- **Mutant `#33` (`G1`, `model/src/moves.rs:94`):** Removing `if !state.mask.fits(kind) { return Err(Error::Unsupported); }` in `Model::place_move`.
  - *Why unreachable:* Lines 90–92 of `place_move` already check `if dest.mask != state.mask { return Err(Error::Invalid); }` first, and `dest` is a thread on `dest_node` whose `dest.mask` is invariant-guaranteed to satisfy `dest.mask.fits(kind)` (verified at thread creation as `FeatureMask::NONE` and at every `thread_set_features` on `dest_node`). Thus whenever line 94 is reached, `state.mask == dest.mask`, which always fits `kind`.
- **Mutant `#108` (`G5`, `model/src/threads.rs:172`):** Removing `if mask.features() & (1 << FEATURE_USER_INTERRUPTS) != 0 { return Err(Error::Unsupported); }` in `Model::thread_set_features`.
  - *Why unreachable:* Two lines later (`model/src/threads.rs:175`), `self.thread_size(mask)` calls `mask.check(self.machine.features, kind)` (`model/src/cores.rs:19`), and `FeatureMask::check` (`abi/src/features.rs:102-104`) already returns `Err(Error::Unsupported)` whenever bit 31 (`FEATURE_USER_INTERRUPTS`) is set.

#### All 44 Non-Equivalent Surviving Mutants
| ID | Group | File & Line | Mutation (Contract Rule Broken) | Why It Survived |
| ---: | :--- | :--- | :--- | :--- |
| `#3` | G1 | `abi/src/features.rs:36` | `Kind::baseline`: omit `& !(1 << FEATURE_USER_INTERRUPTS)` | `x86_64::FEATURES.state` and `aarch64::FEATURES.state` do not set bit 31; no unit test called `Kind::baseline` with bit 31 in `list.state`. |
| `#4` | G1 | `abi/src/features.rs:36` | `Kind::baseline`: omit `& list.state` | Every test `Kind` only set bits in `features` that were already in `list.state` (or instruction bits $\ge 32$). |
| `#5` | G1 | `abi/src/features.rs:64` | `FeatureMask::vector_bytes`: mask `0xFF` instead of `0xFFFF` | Tests only used vector lengths 16, 32, and 64 ($< 256$), never testing the upper byte of the 16-bit field (e.g., 256 bytes / 2048-bit SVE). |
| `#13` | G1 | `abi/src/features.rs:124` | `FeatureMask::fits`: omit `self.vector_bytes() == kind.vector_bytes` | `FeatureMask::fits` is only called in `place_move` after `dest.mask == state.mask` (`#33`), and no unit test in `abi` called `FeatureMask::fits` directly with mismatched `vector_bytes`. |
| `#14` | G1 | `abi/src/features.rs:124` | `FeatureMask::fits`: require `self.vector_bytes() == kind.vector_bytes` even when `self.vector_bytes() == 0` | Same as `#13`: no unit test called `FeatureMask::fits` directly with `vector_bytes == 0` on a kind with `vector_bytes > 0`. |
| `#18` | G1 | `abi/src/features.rs:152` | `kind_covers`: compare `(node.features as u32) & !(host.features as u32)` (ignoring instruction bits 32..63) | No test passed a `Kind` with instruction features in bits 32..63 to `kind_covers` or `Machine::layout`. |
| `#20` | G1 | `model/src/threads.rs:167` | `thread_set_features`: check `thread_size(mask)` before `object(thread, target, Thread, WRITE)` | All invalid-mask tests passed a valid `Thread` capability with `WRITE` rights. |
| `#21` | G1 | `model/src/threads.rs:180` | `thread_set_features`: check `NoMemory` (`needed > changed.area`) before `Busy` (`!suspended \|\| wait != None`) | The `Busy` test used mask `0` (where `needed <= changed.area`), and the `NoMemory` test used a suspended thread. |
| `#24` | G1 | `model/src/sched.rs:692` | `sched_count`: swap `sched` and `core` capability checks | Tests never passed both an invalid/read-only `sched` and an invalid `core` with distinct errors (`Denied` vs `Invalid`). |
| `#26` | G1 | `model/src/sched.rs:700` | `sched_count`: zero `instructions` and `hw_class` on `SCHED_COUNT_ON` as well as `SCHED_COUNT_OFF` | `sched_count(SCHED_COUNT_ON)` was only called when `instructions == 0`. |
| `#31` | G1 | `model/src/moves.rs:74` | `thread_move`: omit `!held.chain.is_empty()` check on source thread's home context | The lend-chain test left the caller blocked in `Wait::Replying`, which was already caught by `state.wait != Wait::None`; no test suspended and cancelled the caller while its context remained lent. |
| `#49` | G2 | `model/src/debug.rs:100` | `CrashArea::new`: `sequence: previous` instead of `previous + 1` | `Machine::example()` has `previous_crash: None` (`previous = 0`), and no test inspected `table.crash.sequence`. |
| `#50` | G2 | `model/src/debug.rs:112` | `CrashArea::accepted`: omit `r.commit == self.boot_id` check | The model always writes `commit: self.boot_id`; no unit test injected an uncommitted record (`commit != boot_id`). |
| `#52` | G2 | `model/src/debug.rs:124` | `CrashArea::write_record`: block all overwrites when `self.held`, instead of only blocking `reason == 5` | Contract (`kernel-interface.md:2924-2928`) says only a fence (`reason == 5`) will not overwrite an existing record, while a self-reported failure updates it. No test wrote two records with `reason != 5`. |
| `#54` | G2 | `model/src/debug.rs:184` | `Model::trace`: rate-limit window `now.saturating_sub(at) > TRACE_BURST_NS` instead of `>=` | Tests advanced time by `TRACE_BURST_NS + 1` or `2 * TRACE_BURST_NS`, never testing the exact boundary `t0 + TRACE_BURST_NS`. |
| `#59` | G2 | `model/src/debug.rs:302` | `Model::debug_write`: check `length > DEBUG_WRITE_MAX` before `debug` capability | The `length > DEBUG_WRITE_MAX` test passed a valid `DEBUG` capability. |
| `#63` | G2 | `model/src/debug.rs:345` | `Model::trace_emit`: require `Rights::READ` instead of `Rights::WRITE` on `debug` capability | `trace_emit` was only tested with `START_SLOT_DEBUG` (which has both `READ` and `WRITE`) or with a wrong-kind capability; never with a `READ`-only `debug` capability. |
| `#66` | G2 | `model/src/faults.rs:183` | `Model::thread_write_regs`: check `(REG_DR0..REG_DR3).contains(&i)` (omitting `REG_DR3`) | Tests only put a non-canonical/kernel address in `REG_DR0`, never in `REG_DR3`. |
| `#68` | G2 | `model/src/faults.rs:195` | `Model::thread_write_regs`: check `Busy` before register word validation (`Invalid`) | Running-thread (`Busy`) tests passed valid register blocks, and invalid-register tests used a suspended thread. |
| `#69` | G3 | `abi/src/ioport.rs:28` | `IoPortRange::new`: `first < last` instead of `first <= last` | All `ioports_issue` tests used `first < last` (e.g., `0x3F8..=0x3FF`), never a 1-port range `first == last`. |
| `#70` | G3 | `abi/src/ioport.rs:28` | `IoPortRange::new`: `last < 0xFFFF` instead of `last <= 0xFFFF` | `IoPortRange::ALL` is constructed as a struct literal, and no `ioports_issue` test issued a range ending at `0xFFFF`. |
| `#73` | G3 | `abi/src/ioport.rs:58` | `ioport_check`: accept `width == 8` (`matches!(width, 1 \| 2 \| 4 \| 8)`) | Invalid-width tests only tried `width = 0` and `width = 3`, never `width = 8`. |
| `#79` | G3 | `model/src/debug.rs:401` | `Model::ioport`: check `Arch::X86_64` before `addressed_space(thread)` (dying CSpace `Gone`) | No test called `ioport_in`/`ioport_out` from a thread with a dying CSpace on `Arch::X86_64` (or `Arch::Other`). |
| `#80` | G3 | `model/src/debug.rs:405` | `Model::ioport`: require `Rights::READ` instead of `Rights::WRITE` for `ioport_out` | `ioport_out` was only tested with `START_SLOT_IOPORTS` (`READ \| WRITE \| DERIVE`) or a `READ`-only capability on `ioport_in`, never a `READ`-only capability on `ioport_out`! |
| `#81` | G3 | `model/src/debug.rs:412` | `Model::ioport`: check `ports_refused` (`Busy`) before `ioport_check` (`Invalid`) | Refused-port tests always used a valid width and in-range port. |
| `#82` | G3 | `model/src/debug.rs:360` | `Model::ports_refused`: omit `self.machine.console_port` | `Machine::example()` sets `console_port: None`, and no test ever set `console_port: Some(...)`! |
| `#84` | G3 | `model/src/debug.rs:449` | `Model::ioports_issue`: require `Rights::WRITE` instead of `Rights::DERIVE` | The `Denied` test derived a capability with `Rights::READ` only (lacking both `WRITE` and `DERIVE`). |
| `#85` | G3 | `model/src/debug.rs:451` | `Model::ioports_issue`: check `IoPortRange::new` before `destination` slot | Invalid-range tests always passed a valid `destination` slot. |
| `#87` | G3 | `model/src/debug.rs:455` | `Model::ioports_issue`: check `vacant(place)` (`NoSlot`) before `fits(..., Placing::Derived)` (`Invalid`) | Depth-limit tests always targeted an empty destination slot. |
| `#92` | G4 | `model/src/debug.rs:465` | `Model::entropy_read`: check `length > ENTROPY_MAX_BYTES` before `addressed_space(thread)` (`Gone`) | No test called `entropy_read` with `length > 64` from a thread whose CSpace was dying. |
| `#96` | G4 | `model/src/debug.rs:474` | `Model::entropy_read`: do not mix caller's `mix` words into PRNG state | Tests only passed `mix: [0; 4]` or compared two calls on the same `Model` (where `entropy_calls` already advances), never comparing two fresh models with different `mix` arrays. |
| `#97` | G4 | `model/src/debug.rs:474` | `Model::entropy_read`: mix only `mix[0..3]` instead of all 4 words | Same as `#96`: no test varied `mix[3]` on identical state. |
| `#99` | G4 | `model/src/debug.rs:489` | `Model::entropy_read`: mask partial final word with `(1 << (8 * (left - 1))) - 1` instead of `8 * left` | Tests only checked that bytes above `length` were zero (`word >> (8 * left) == 0`), never asserting that the highest valid byte was non-zero! |
| `#101` | G5 | `abi/src/features.rs:102` | `FeatureMask::check`: omit `self.features() & user != 0` check (relying only on `features & !kind == 0`) | If a `Kind` has bit 31 set in `kind.features`, `FeatureMask::check` without the `user` mask accepts bit 31 instead of returning `Err(Error::Unsupported)`. |
| `#107` | G5 | `model/src/faults.rs:189` | `Model::thread_write_regs`: check `REG_UINTR != 0` (`Unsupported`) after `Busy` check | `REG_UINTR != 0` was only tested on a suspended thread, not on a running (`Busy`) thread. |
| `#109` | G5 | `abi/src/features.rs:122` | `FeatureMask::fits`: omit `& !(1 << FEATURE_USER_INTERRUPTS)` | No unit test called `FeatureMask::fits` with bit 31 set. |
| `#118` | G6 | `abi/src/machine.rs:848` | `module_frames`: cap `PageSize::Page` run at `512` instead of `self.geometry.entries` | No test called `module_frames` on `SIXTEEN_KB` (`entries = 2048`) with a run of $> 512$ pages. |
| `#119` | G6 | `model/src/boot.rs:42` | `SIXTEEN_KB`: change `page_shift: [14, 25, 36, 0], entries: 2048, levels: 3` to 4 KB (`[12, 21, 30, 0], 512, 4`) | Every test in `model/tests/` computes `Machine::example().geometry.page()` dynamically; **not a single test asserted that `DODOS_PAGE=16k` actually gives a 16,384-byte page!** |
| `#122` | G6 | `model/src/boot.rs:813` | `Model::start`: `start_pages >= START_PAGE_MAX_PAGES` instead of `>` | `boot::kernel_refuses_a_start_up_page_of_more_than_63_pages` (`model/tests/boot.rs:516`) tested 62 pages (`61 * page`) and 64 pages (`63 * page`), skipping 63 pages (`62 * page`)! |
| `#129` | G6 | `model/src/memory.rs:36` | `tables`: hardcode `per_level = 9` instead of `geometry.entries.trailing_zeros()` | On `SIXTEEN_KB`, no test mapped two pages $2^{23}$ bytes apart (which share a 16 KB level-1 table covering $2^{25}$ bytes, but sit in different 4 KB level-1 tables covering $2^{21}$ or $2^{23}$ bytes). |
| `#130` | G6 | `model/src/memory.rs:35` | `tables`: hardcode `page = 12` instead of `u32::from(geometry.page_shift[0])` | Same as `#129`. |
| `#131` | G6 | `model/src/memory.rs:126` | `io_levels`: hardcode `9` instead of `geometry.entries.trailing_zeros()` | `Machine::example()` has `io_width: 39`, where `(39 - 14).div_ceil(11) == 3 == (39 - 14).div_ceil(9)`! Only `io_width: 47` (or `48`) on `SIXTEEN_KB` distinguishes `div_ceil(11) == 3` from `div_ceil(9) == 4`. |
| `#160` | G7 | `abi/src/arch.rs:124` | `aarch64::FEATURES`: omit `1 << SME` from `with_length` | No test checked `aarch64::FEATURES.with_length & (1 << aarch64::SME)`. |
| `#168` | G7 | `abi/src/debug.rs:11` | `DEBUG_AREA_MAGIC`: `0x6244_6F44` (`"DoDb"`) $\to$ `0x6344_6F44` (`"DoDc"`) | Model tests compared `DEBUG_AREA_MAGIC` against itself. |

#### Verified Missing Tests That Kill All 44 Non-Equivalent Survivors
We wrote 6 compact test functions (one each in `abi/src/tests.rs`, `model/tests/cores.rs`, `model/tests/debug.rs`, `model/src/debug.rs`, `model/tests/boot.rs`, and `model/tests/memory.rs`) and verified against both the unmutated codebase and all 44 mutants (`Killed 44/44 non-equivalent survivors`):

1. **`abi/src/tests.rs` (`review6_missing_abi_pins` — kills `#3, #4, #5, #13, #14, #18, #69, #70, #73, #101, #109, #118, #160, #168`):**
```rust
#[test]
fn review6_missing_abi_pins() {
    use crate::{
        DEBUG_AREA_MAGIC, FEATURE_USER_INTERRUPTS, FeatureList, FeatureMask, IoPortRange, Kind,
        aarch64, ioport_check, kind_covers,
    };

    // #3, #4: Kind::baseline excludes bit 31 and bits not in list.state
    let list = FeatureList {
        state: 0b0011 | (1 << FEATURE_USER_INTERRUPTS),
        with_length: 0,
        large: 0,
    };
    let kind = Kind {
        features: 0b0111 | (1 << FEATURE_USER_INTERRUPTS),
        vector_bytes: 0,
        baseline_bytes: 64,
        feature_bytes: [0; 32],
    };
    assert_eq!(kind.baseline(list), 0b0011);

    // #5: FeatureMask::vector_bytes reads all 16 bits (bits 32..47)
    let m256 = FeatureMask::new(1 << aarch64::SVE, 256);
    assert_eq!(m256.vector_bytes(), 256);

    // #13, #14, #109: FeatureMask::fits checks vector_bytes when non-zero, allows 0, and ignores bit 31
    let k32 = Kind {
        features: 1 << aarch64::SVE,
        vector_bytes: 32,
        baseline_bytes: 64,
        feature_bytes: [0; 32],
    };
    assert!(!FeatureMask::new(1 << aarch64::SVE, 64).fits(&k32));
    assert!(FeatureMask::new(0, 0).fits(&k32));
    assert!(FeatureMask::new(1 << FEATURE_USER_INTERRUPTS, 0).fits(&k32));

    // #101: FeatureMask::check rejects bit 31 with Unsupported even if kind.features has bit 31 set
    assert_eq!(
        FeatureMask::new(1 << FEATURE_USER_INTERRUPTS, 0).check(list, &kind),
        Err(crate::Error::Unsupported)
    );

    // #18: kind_covers checks instruction features in bits 32..63
    let host_no_inst = Kind { features: 1, ..k32 };
    let node_with_inst = Kind { features: 1 | (1u64 << 32), ..k32 };
    assert!(!kind_covers(&host_no_inst, &node_with_inst));

    // #69, #70, #73: IoPortRange::new boundary values and ioport_check width=8
    assert!(IoPortRange::new(0x3F8, 0x3F8).is_some());
    assert!(IoPortRange::new(0, 0xFFFF).is_some());
    assert_eq!(
        ioport_check(IoPortRange::ALL, 0x3F8, 8, None),
        Err(crate::Error::Invalid)
    );

    // #118: module_frames allows up to geometry.entries (> 512) pages in one frame on 16 KB geometry
    let geo16k = crate::Geometry {
        page_shift: [14, 25, 36, 0],
        entries: 2048,
        levels: 3,
        user_end: (1 << 47) - (1 << 36),
    };
    let frames: Vec<_> = crate::module_frames(1 << 14, None, 600 * (1 << 14), geo16k).collect();
    assert_eq!(frames.len(), 1);
    assert_eq!(frames[0].pages, 600);

    // #160: aarch64::FEATURES includes SME in with_length
    assert_ne!(aarch64::FEATURES.with_length & (1 << aarch64::SME), 0);

    // #168: DEBUG_AREA_MAGIC is b"DoDb"
    assert_eq!(DEBUG_AREA_MAGIC, 0x6244_6F44);
}
```

2. **`model/tests/cores.rs` (`review6_missing_cores_pins` — kills `#20, #21, #24, #26, #31`):**
```rust
#[test]
fn review6_missing_cores_pins() {
    // #20: thread_set_features checks target capability before mask
    let mut k = K::new();
    k.no(features(999, 1u64 << 63), Error::Invalid);
    k.ok(Syscall::CapDerive {
        source: s(START_SLOT_THREAD),
        destination: s(200),
        rights: Rights::READ.bits(),
        badge: 0,
    });
    k.no(features(200, 1u64 << 63), Error::Denied);

    // #21: thread_set_features checks Busy (running/waiting) before NoMemory (needed > area)
    k.no(features(START_SLOT_THREAD, 1 << AMX), Error::Busy);

    // #24: sched_count checks sched capability before core capability
    k.ok(Syscall::CapDerive {
        source: SCHED,
        destination: s(201),
        rights: Rights::READ.bits(),
        badge: 0,
    });
    k.no(
        Syscall::SchedCount {
            sched: s(201),
            core: s(START_SLOT_CSPACE),
            mode: SCHED_COUNT_ON,
        },
        Error::Denied,
    );

    // #26: sched_count(SCHED_COUNT_ON) on an already counted context preserves count and hw_class
    k.ok(count(SCHED, SCHED_COUNT_ON));
    k.m.advance(k.m.now() + 100);
    assert_eq!(k.m.check(), Ok(()));
    let (_, _, before) = read(&mut k.m, k.t, SCHED);
    assert!(before >= 100);
    k.ok(count(SCHED, SCHED_COUNT_ON));
    let (_, _, after) = read(&mut k.m, k.t, SCHED);
    assert_eq!(after, before);

    // #31: thread_move rejects a suspended source thread whose context is still lent out
    let mut m = S::new();
    m.ok(0, retype(ObjectKind::Endpoint, 0, 150));
    m.ok(0, retype(Thread, 0, 151));
    m.ok(0, retype(Frame, 1, 152));
    m.ok(
        0,
        Syscall::ThreadConfigure {
            thread: s(151),
            cspace: s(START_SLOT_CSPACE),
            aspace: s(START_SLOT_ASPACE),
            fault: SlotAddr::NONE,
            page: s(152),
        },
    );
    m.ok(0, Syscall::ThreadResume(s(151)));
    let passive = m.sys.node(0).object_at(m.t[0], s(151)).unwrap();
    let recv_ep = Syscall::Recv {
        endpoint: s(150),
        reply: s(99),
        range: Range::NONE,
        wait: 0,
    };
    assert_eq!(m.sys.apply(0, passive, recv_ep), WAITS);
    m.ok(0, Syscall::ThreadResume(s(A)));
    let src = m.sys.node(0).object_at(m.t[0], s(A)).unwrap();
    let call_ep = Syscall::Call {
        endpoint: s(150),
        message: Message::default(),
        range: Range::NONE,
        wait: 1,
    };
    assert_eq!(m.sys.apply(0, src, call_ep), WAITS);
    m.ok(0, Syscall::ThreadSuspend(s(A)));
    m.ok(0, Syscall::ThreadCancel(s(A), 1));
    assert_eq!(m.moving((0, 0, 0)), Err(Error::Busy));
}
```

3. **`model/tests/debug.rs` (`review6_missing_debug_ioport_entropy_pins` — kills `#54, #59, #63, #66, #68, #80, #81, #82, #84, #85, #87, #96, #97, #99, #107`):**
```rust
#[test]
fn review6_missing_debug_ioport_entropy_pins() {
    use dodos_abi::x86_64::REG_DR3;

    let mut k = K::new();

    // #54: rate limit window rolls over at exactly at + TRACE_BURST_NS
    let b = k.spawn();
    let t0 = k.m.now();
    for _ in 0..17 {
        k.m.fault(b, FaultKind::Page, [14, 2, 0x1000]);
        k.ok(Syscall::ThreadResume(s(101)));
    }
    assert_eq!(k.m.suppressed(), 1);
    k.m.advance(t0 + TRACE_BURST_NS);
    k.m.fault(b, FaultKind::Page, [14, 2, 0x1000]);
    let ring = k.kernel();
    assert_eq!(ring[ring.len() - 2].code(), 3);

    // #59: debug_write checks debug capability before length > DEBUG_WRITE_MAX
    k.ok(Syscall::CapDerive {
        source: DEBUG,
        destination: s(200),
        rights: Rights::READ.bits(),
        badge: 0,
    });
    k.no(
        Syscall::DebugWrite {
            debug: s(200),
            length: DEBUG_WRITE_MAX + 1,
            words: vec![],
        },
        Error::Denied,
    );

    // #63: trace_emit requires WRITE on debug capability
    k.no(
        Syscall::TraceEmit {
            debug: s(200),
            words: [0; 3],
        },
        Error::Denied,
    );

    // #66, #68, #107: thread_write_regs checks REG_DR3 < user_end, and checks words (Invalid / Unsupported) before Busy
    let mut bad_dr3 = block();
    bad_dr3[REG_DR3] = Machine::example().geometry.user_end;
    k.no(
        Syscall::ThreadWriteRegs {
            thread: s(START_SLOT_THREAD),
            block: bad_dr3,
        },
        Error::Invalid,
    );
    let mut bad_uintr = block();
    bad_uintr[REG_UINTR] = 1;
    k.no(
        Syscall::ThreadWriteRegs {
            thread: s(START_SLOT_THREAD),
            block: bad_uintr,
        },
        Error::Unsupported,
    );

    // #80, #81, #82: ioport_out requires WRITE; ioport checks Invalid before Busy (ports_refused); console_port is refused
    k.ok(Syscall::CapDerive {
        source: PORTS,
        destination: s(201),
        rights: Rights::READ.bits(),
        badge: 0,
    });
    k.no(port_out(s(201), 0x80, 1, 0), Error::Denied);
    k.no(port_in(PORTS, 0x20, 3), Error::Invalid);
    let mut mach_uart = Machine::example();
    mach_uart.console_port = Some(0x3F8);
    let mut ku = K::on(&mach_uart);
    ku.no(port_in(PORTS, 0x3F8, 1), Error::Busy);
    ku.no(port_in(PORTS, 0x3FF, 1), Error::Busy);
    assert_eq!(ku.go(port_in(PORTS, 0x400, 1)), Ok(Output::Value(0)));

    // #84, #85, #87: ioports_issue requires DERIVE (even with WRITE), checks destination before range, and checks fits before vacant
    k.ok(Syscall::CapDerive {
        source: PORTS,
        destination: s(202),
        rights: Rights::READ.union(Rights::WRITE).bits(),
        badge: 0,
    });
    k.no(
        Syscall::IoportsIssue {
            ioports: s(202),
            destination: s(203),
            first: 0x80,
            last: 0x80,
        },
        Error::Denied,
    );
    k.ok(Syscall::CapDerive {
        source: s(START_SLOT_CSPACE),
        destination: s(204),
        rights: Rights::READ.bits(),
        badge: 0,
    });
    k.no(
        Syscall::IoportsIssue {
            ioports: PORTS,
            destination: SlotAddr::through(204, 0),
            first: 10,
            last: 5,
        },
        Error::Denied,
    );
    let mut cur = PORTS;
    for slot in 300..363 {
        k.ok(Syscall::CapDerive {
            source: cur,
            destination: s(slot),
            rights: Rights::READ.union(Rights::DERIVE).bits(),
            badge: 0,
        });
        cur = s(slot);
    }
    k.no(
        Syscall::IoportsIssue {
            ioports: cur,
            destination: s(START_SLOT_CSPACE),
            first: 0x80,
            last: 0x80,
        },
        Error::Invalid,
    );

    // #96, #97, #99: entropy_read mixes all 4 words and keeps all 8 * left bits in the last word
    let mut k1 = K::new();
    let mut k2 = K::new();
    let Ok(Output::Bytes(w1)) = k1.go(Syscall::EntropyRead {
        length: 13,
        mix: [0, 0, 0, 1],
    }) else {
        panic!();
    };
    let Ok(Output::Bytes(w2)) = k2.go(Syscall::EntropyRead {
        length: 13,
        mix: [0, 0, 0, 2],
    }) else {
        panic!();
    };
    assert_ne!(w1, w2);
    assert!(w1[1] >> 32 != 0 || w2[1] >> 32 != 0);
}
```

4. **`model/src/debug.rs` (`review6_missing_crash_and_dying_space_pins` — kills `#49, #50, #52, #79, #92`):**
```rust
#[test]
fn review6_missing_crash_and_dying_space_pins() {
    use crate::boot::Arch;
    use dodos_abi::{
        Error, ObjectKind, PageSize, Rights, START_SLOT_ASPACE, START_SLOT_IOPORTS,
        START_SLOT_SCHED, SlotAddr,
    };

    // #49, #50, #52: CrashArea::new sequence = previous + 1, accepted checks commit == boot_id, and non-fence reasons overwrite held record
    let mut mach = Machine::example();
    let (mut m0, _) = Model::boot(&mach).unwrap();
    assert_eq!(m0.table.crash.sequence, 1);
    m0.table.crash.areas[0].record = Some(super::Record {
        commit: m0.table.crash.boot_id ^ 1,
        node: 0,
        reason: 1,
        fault_RIP: 0,
        fault_addr: 0,
        fault_extra: 0,
        code: 0,
    });
    assert!(m0.table.crash.accepted().is_none());
    m0.table.crash.write_record(0, 1, [10, 20, 30], 0);
    m0.table.crash.write_record(0, 2, [40, 50, 60], 0);
    assert_eq!(m0.table.crash.accepted().unwrap().reason, 2);

    // #79, #92: ioport and entropy_read check addressed_space (Gone on dying CSpace) first
    mach.arch = Arch::Other;
    let (mut ma, boota) = Model::boot(&mach).unwrap();
    let ut = SlotAddr::own(25);
    for (kind, page, dst) in [
        (ObjectKind::CSpace, 0, 100),
        (ObjectKind::Thread, 0, 101),
        (ObjectKind::Sched, 0, 102),
        (ObjectKind::Frame, PageSize::Page as u64, 103),
    ] {
        let size = if kind == ObjectKind::Frame { 1 } else { 0 };
        let _ = ma.apply(
            boota,
            crate::Syscall::UntypedRetype {
                untyped: ut,
                kind,
                size,
                page,
                memory: 0,
                destination: SlotAddr::own(dst),
            },
        );
    }
    let _ = ma.apply(
        boota,
        crate::Syscall::CapCopy {
            source: SlotAddr::own(START_SLOT_IOPORTS),
            destination: SlotAddr::through(100, START_SLOT_IOPORTS),
            rights: Rights::ALL.bits(),
        },
    );
    let _ = ma.apply(
        boota,
        crate::Syscall::ThreadConfigure {
            thread: SlotAddr::own(101),
            cspace: SlotAddr::own(100),
            aspace: SlotAddr::own(START_SLOT_ASPACE),
            fault: SlotAddr::NONE,
            page: SlotAddr::own(103),
        },
    );
    let _ = ma.apply(
        boota,
        crate::Syscall::SchedControl {
            sched: SlotAddr::own(102),
            core: SlotAddr::own(START_SLOT_SCHED),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        },
    );
    let _ = ma.apply(
        boota,
        crate::Syscall::SchedBind {
            sched: SlotAddr::own(102),
            thread: SlotAddr::own(101),
        },
    );
    let _ = ma.apply(boota, crate::Syscall::ThreadResume(SlotAddr::own(101)));
    let child_t = ma.object_at(boota, SlotAddr::own(101)).unwrap();
    assert_eq!(
        ma.apply(boota, crate::Syscall::CapDelete(SlotAddr::own(100))),
        Err(Error::Again)
    );
    assert_eq!(
        ma.apply(
            child_t,
            crate::Syscall::IoportIn {
                ioports: SlotAddr::own(START_SLOT_IOPORTS),
                port: 0x80,
                width: 1,
            },
        ),
        Err(Error::Gone)
    );
    assert_eq!(
        ma.apply(
            child_t,
            crate::Syscall::EntropyRead {
                length: 100,
                mix: [0; 4],
            },
        ),
        Err(Error::Gone)
    );
}
```

5. **`model/tests/boot.rs` (`review6_missing_boot_pins` — kills `#119, #122`):**
```rust
#[test]
fn review6_missing_boot_pins() {
    // #119: when DODOS_PAGE=16k, Machine::example() uses 16 KB pages
    if std::env::var("DODOS_PAGE").as_deref() == Ok("16k") {
        assert_eq!(Machine::example().geometry.page(), 16_384);
    }
    // #122: start-up page of exactly 63 pages (START_PAGE_MAX_PAGES) is accepted
    let page = Machine::example().geometry.page() as u32;
    let fits63 = with(|m| m.files[0].name = 62 * page);
    let (m, t) = boot(&fits63);
    let at = |n: u64| 2 * page as u64 + n * page as u64;
    assert!(m.translated(t, at(62)).is_some());
    assert!(m.translated(t, at(63)).is_none());
}
```

6. **`model/tests/memory.rs` (`review6_missing_16k_table_pins` — kills `#129, #130, #131`):**
```rust
#[test]
fn review6_missing_16k_table_pins() {
    use dodos_model::{Map, SIXTEEN_KB};
    // #129, #130, #131: tables() and io_levels() use geometry.page_shift[0] and geometry.entries on 16 KB geometry
    let mut mach = Machine::example_on(SIXTEEN_KB);
    mach.io_width = 47;
    let (mut m, t) = Model::boot(&mach).unwrap();
    let page = m.geometry().page();
    let chunk = m.geometry().chunk();
    let ut = SlotAddr::own(25);
    assert_eq!(
        m.apply(
            t,
            Syscall::UntypedRetype {
                untyped: ut,
                kind: ObjectKind::ASpace,
                size: 0,
                page: 0,
                memory: 0,
                destination: SlotAddr::own(100),
            },
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::UntypedRetype {
                untyped: ut,
                kind: ObjectKind::Frame,
                size: 2,
                page: PageSize::Page as u64,
                memory: 0,
                destination: SlotAddr::own(101),
            },
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::CapDerive {
                source: SlotAddr::own(101),
                destination: SlotAddr::own(102),
                rights: Rights::READ.bits(),
                badge: 0,
            },
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::ASpaceMap(Map {
                space: SlotAddr::own(100),
                frame: SlotAddr::own(101),
                untyped: ut,
                address: chunk,
                first: 0,
                count: 1,
                rights: Rights::READ.bits(),
            }),
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::ASpaceMap(Map {
                space: SlotAddr::own(100),
                frame: SlotAddr::own(102),
                untyped: SlotAddr::NONE,
                address: chunk + (1 << 23),
                first: 1,
                count: 1,
                rights: Rights::READ.bits(),
            }),
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::CapDerive {
                source: SlotAddr::own(101),
                destination: SlotAddr::own(104),
                rights: Rights::READ.bits(),
                badge: 0,
            },
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::UntypedRetype {
                untyped: ut,
                kind: ObjectKind::Untyped,
                size: 4 * page,
                page: 0,
                memory: 0,
                destination: SlotAddr::own(105),
            },
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::UntypedRetype {
                untyped: SlotAddr::own(105),
                kind: ObjectKind::IoSpace,
                size: 0,
                page: 0,
                memory: 0,
                destination: SlotAddr::own(106),
            },
        ),
        Ok(Output::Done)
    );
    assert_eq!(
        m.apply(
            t,
            Syscall::IoSpaceMap(Map {
                space: SlotAddr::own(106),
                frame: SlotAddr::own(104),
                untyped: SlotAddr::own(105),
                address: chunk,
                first: 0,
                count: 1,
                rights: Rights::READ.bits(),
            }),
        ),
        Ok(Output::Done)
    );
}
```

---

### `F4`: Third Page-Size Geometry Check (`8 KB` and `32 KB`)

#### 1. Does `./verify` Really Run the Suite With Two Page Sizes?
Yes: `/Users/btw/Documents/repos/dodos-kernel/verify:17-22` runs `cargo test --workspace` (where `Machine::example()` uses `dodos_abi::x86_64::GEOMETRY`, 4 KB pages / 2 MB chunks) and then `DODOS_PAGE=16k cargo test -p dodos-model` (where `Machine::example()` selects `SIXTEEN_KB` in `model/src/boot.rs:42-47`, 16 KB pages / 32 MB chunks). However, as Mutant `#119` showed, no test asserted that `DODOS_PAGE=16k` actually produces a 16 KB page in `Machine::example()`.

#### 2. Changing `SIXTEEN_KB` to a Third Value (`8 KB` vs. `32 KB`)
We tested two valid alternative geometries in place of `SIXTEEN_KB` (`model/src/boot.rs:42-47`):
- **8 KB (`page_shift: [13, 23, 33, 0], entries: 1024, levels: 3, user_end: (1 << 43) - (1 << 33)`):**
  Passed all test binaries, because $8\text{ KB} \le 16\text{ KB}$ and $\text{chunk} = 8\text{ MB} \le 32\text{ MB}$, so every hardcoded 16 KB or 64 KB constant in `Machine::example_on` and `model/tests/` remained $\ge P$ and $\le \text{CLEAR\_STEP\_BYTES}$.
- **32 KB (`page_shift: [15, 27, 39, 0], entries: 4096, levels: 3, user_end: (1 << 51) - (1 << 39)`):**
  Satisfies `Geometry::valid() == true` ($P = 32\text{ KB}, E = 4096, \text{chunk} = 128\text{ MB}, \text{Large2} = 512\text{ GB}$), and exposed **hidden 4 KB / 16 KB constants across 4 test binaries**:
  1. **`model/src/boot.rs:267-278` and `model/tests/boot.rs:269,483` (`boot` binary — 2 failures):**
     - `Machine::example_on` (`model/src/boot.rs:267,273`) hardcodes segment lengths `len: 0x1_0000` (64 KB) at `vaddr: chunk` and `len: 0x4000` (16 KB) at `vaddr: chunk + 0x1_0000`. On 4 KB and 16 KB geometries, `0x4000` is a whole number of pages (4 pages or 1 page), so the second segment ends at `chunk + 0x1_4000`. On 32 KB, `0x4000` rounds up to 1 page of 32 KB (`0x8000`), so `chunk + 0x1_4000` is still inside segment 1, failing `assert!(m.translated(t, chunk + 0x1_4000).is_none())` at `model/tests/boot.rs:269`!
     - `kernel_refuses_a_segment_outside_the_lower_half` (`model/tests/boot.rs:483`) places a segment of `0x4000` bytes at `end - 0x4000`. On 32 KB, `end - 0x4000` is not page-aligned (`Refusal::SegmentOverlap`), instead of reaching `end`.
  2. **`model/src/check/tests.rs:1604` (`dodos_model` lib test `check::tests::iospace` — 1 failure):**
     - `with_device` (`model/src/check/tests.rs:1604`) calls `m.apply(t, retype(25, ObjectKind::IoSpace, 0))` once and expects `Ok(Output::Done)`. An `IoSpace` takes $2 \times P$ bytes (`abi/src/lib.rs:582`). For $P \le 16\text{ KB}$, $2P \le 32\text{ KB}$, which fits in a single `CLEAR_STEP_BYTES` (64 KB) step alongside the prior `Untyped` retype (`watermark = 4 KB`). For $P = 32\text{ KB}$, $2P = 64\text{ KB}$, so `watermark + 64 KB = 68 KB > CLEAR_STEP_BYTES` (64 KB), returning `Err(Error::Again)`!
  3. **`model/tests/calls.rs:293,617,1367,1744,3618` (`calls` binary — 10 failures):**
     - `K::make` (`model/tests/calls.rs:293`) calls `self.ok(Syscall::UntypedRetype { ... })` once without looping on `Err(Error::Again)`. Creating an `IoSpace` ($2P = 64\text{ KB}$) or multiple objects after a dirty untyped exceeds `CLEAR_STEP_BYTES` (64 KB) when $P = 32\text{ KB}$.
     - `model/tests/calls.rs:617,1367,1744` hardcode child untyped sizes `1 << 14` (16 KB) and `1 << 13` (8 KB), which are smaller than $P = 32\text{ KB}$ (`Error::Invalid`).
     - `frame_of_the_second_large_page_is_aligned_on_its_size` (`model/tests/calls.rs:3618`) calls `k.take_run(slot, shift + 11, 28)` where `shift = page_shift[2] = 39` ($\text{Large2} = 512\text{ GB}$). Requesting `shift + 11 = 50` ($1\text{ PB} = 8192$ chunks) exceeds `MEMORY_TAKE_MAX_CHUNKS` ($4096$).
  4. **`model/tests/property.rs:114,1825` (`property` binary — 2 failures):**
     - `same_seed_gives_the_same_state` (`model/tests/property.rs:1825`) constructs a fresh `Runner` via `Model::boot(&Machine::example_on(GEOMETRY))` (hardcoding 4 KB `GEOMETRY`) and compares it against `run(0)`, which uses `Machine::example()` (respecting `DODOS_PAGE=16k`). It only passed under `DODOS_PAGE=16k` because few actions depended on `page()` before step 5,000, whereas under 32 KB `K::new()` in `property.rs` also hit `F1` (`core_stop` on `self.node` followed by `memory_take` in seed 3).

---

### `F5`: Where the Time of `./verify` Goes and What Can Be Cut Without Losing a Check

#### 1. Measured Per-Binary Timing Across Both Passes of `./verify`
`./verify` runs:
1. `cargo fmt --all -- --check` (0.2s)
2. `cargo clippy --workspace --all-targets -- -D warnings` (1.1s warm)
3. `cargo test --workspace` (4 KB geometry)
4. `DODOS_PAGE=16k cargo test -p dodos-model` (16 KB geometry)

Measured wall-clock and user CPU time per test binary on this machine (and why CI takes $> 11$ minutes on 2-core runners: total user CPU across both passes is **304.5 seconds** = 5.1 CPU-minutes on fast local silicon, which scales to **11–13 minutes** on 1–2 vCPU CI VMs):

| Test Binary | 4 KB Wall (s) | 4 KB User CPU (s) | 16 KB Wall (s) | 16 KB User CPU (s) | Combined User CPU (s) | % of Total CPU | Depends on `DODOS_PAGE`? |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| `recovery` | 24.48 | 92.60 | 24.30 | 92.34 | **184.94** | **60.7%** | **No** (hardcodes `x86_64::GEOMETRY`) |
| `property` | 25.92 | 27.32 | 25.30 | 26.25 | **53.57** | **17.6%** | Yes (`Machine::example()`) |
| `liveness` | 20.11 | 19.72 | 19.86 | 17.90 | **37.62** | **12.4%** | **No** (`System::with_nodes` uses `x86_64::GEOMETRY`) |
| `blocks` | 6.95 | 6.08 | 6.53 | 5.79 | **11.87** | **3.9%** | Yes |
| `dodos-model` (lib) | 0.90 | 5.71 | 0.87 | 5.47 | **11.18** | **3.7%** | Partially (1 test uses `Machine::example()`) |
| `calls` | 0.29 | 1.66 | 0.25 | 1.24 | **2.90** | **1.0%** | Yes |
| `multi` | 0.37 | 0.77 | 0.36 | 0.72 | **1.49** | **0.5%** | **No** (`System::with_nodes`) |
| `scheduler`, `ipc`, `cores`, `debug`, `memory`, `boot`, `abi` | 0.65 | 0.56 | 0.53 | 0.38 | **0.94** | **0.3%** | Partially |
| **Total** | **79.67s** | **154.42s** | **78.00s** | **150.09s** | **304.51s** | **100.0%** | — |

#### 2. Which Individual Tests Take the Time, and What Can Be Cut Without Losing a Check

1. **Duplicate `DODOS_PAGE=16k` execution of geometry-independent multi-node binaries (`recovery`, `liveness`, `multi`) — saves ~111 user CPU seconds (~36% of total CPU) with zero checks lost:**
   - `System::with_nodes` (`model/src/system.rs:78`) constructs `Machine::example_on(dodos_abi::x86_64::GEOMETRY)`, which **ignores `DODOS_PAGE` completely**!
   - Yet `DODOS_PAGE=16k cargo test -p dodos-model` re-runs `recovery` (92.34s user CPU), `liveness` (17.90s user CPU), and `multi` (0.72s user CPU) identically a second time.
   - **Fix in `./verify`:** Restrict the second pass to the binaries that actually read `DODOS_PAGE` (`--test boot --test memory --test calls --test blocks --test cores --test debug --test ipc --test scheduler --test property`), or pass `--skip` for geometry-independent binaries.

2. **`model/tests/blocks.rs:424` (`memory_split_is_busy_when_no_entry_is_unused_and_unclaimed`) — takes 6.72s wall (99% of `blocks`), reducible to 0.05s with zero checks lost:**
   - To fill all 8,192 spare device-table entries (`DEVICE_TABLE_SPARE = 8192`), the test loops 8,192 times calling `k.go(Syscall::MemorySplit { ... })` (`model/tests/blocks.rs:431`).
   - `K::go` (`model/tests/blocks.rs:47-51`) calls `self.m.check()` **before and after every single `apply`** — executing **16,384 full `Model::check()` passes**, each scanning the growing `devices` vector ($O(N^2)$ over 8,192 entries $\approx 6.7 \times 10^7$ iterations).
   - **Fix:** Call `k.m.apply(k.t, Syscall::MemorySplit { ... })` directly for the first 8,191 setup splits and `k.ok(...)` (which runs `m.check()` before and after) on the 8,192nd split and the failing 8,193rd split. We verified this reduces `blocks` from **6.95s to 0.05s** while checking the exact same boundary states.

3. **`model/tests/recovery.rs` (`nodes_that_beat_and_consume_their_rings_are_never_accused` [15.1s] and `a_firmware_stall_shorter_than_stale_ns_accuses_nobody` [10.1s]):**
   - `System::step()` (`model/src/system.rs:212`) calls `self.check()` on every 100 µs (`TICK_NS`) step. Simulating 2 seconds (`20,000` ticks) in `a_firmware_stall_shorter_than_stale_ns_accuses_nobody` (`model/tests/recovery.rs:584`) and 3 seconds (`30,000` ticks) in `nodes_that_beat_and_consume_their_rings_are_never_accused` (`model/tests/recovery.rs:607`) runs **50,000 full 4-node `System::check()` passes** during pure time advancement when no syscalls occur between 1 ms (`BEAT_NS`) heartbeats.
   - **Fix:** In those two heartbeat-steady-state loops, checking `sys.check()` every `BEAT_NS` (1 ms = every 10 ticks) instead of every `TICK_NS` (100 µs), or only when `step()` performs a heartbeat/action, cuts `recovery` CPU time by **~75% (from 92.6s to ~22s)** while still checking invariants at every heartbeat, ring consumption, and accusation boundary.

4. **`model/tests/property.rs:1820-1834` (`same_seed_gives_the_same_state` [3.5s] and `different_seeds_give_different_states` [1.9s]):**
   - `all_seeds` (`model/tests/property.rs:1839`) already runs seeds `0..24` for 5,000 steps each. `same_seed_gives_the_same_state` and `different_seeds_give_different_states` re-run seeds 0, 1, and 2 six more times for a full 5,000 steps each (30,000 extra steps per pass = 60,000 extra steps across `./verify`), when 200 steps already exercises every generator branch and proves determinism/divergence.

---

## Appendix: Complete List of 168 Mutants Executed

- **G1 (34 mutants, `#1`–`#34`):**
  - Killed (22): `#1, #2, #6, #7, #8, #9, #10, #11, #12, #15, #16, #17, #19, #22, #23, #25, #27, #28, #29, #30, #32, #34`
  - Survived non-equivalent (11): `#3, #4, #5, #13, #14, #18, #20, #21, #24, #26, #31`
  - Survived unreachable (1): `#33`
- **G2 (34 mutants, `#35`–`#68`):**
  - Killed (26): `#35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #51, #53, #55, #56, #57, #58, #60, #61, #62, #64, #65, #67`
  - Survived non-equivalent (8): `#49, #50, #52, #54, #59, #63, #66, #68`
- **G3 (21 mutants, `#69`–`#89`):**
  - Killed (11): `#71, #72, #74, #75, #76, #77, #78, #83, #86, #88, #89`
  - Survived non-equivalent (10): `#69, #70, #73, #79, #80, #81, #82, #84, #85, #87`
- **G4 (10 mutants, `#90`–`#99`):**
  - Killed (6): `#90, #91, #93, #94, #95, #98`
  - Survived non-equivalent (4): `#92, #96, #97, #99`
- **G5 (10 mutants, `#100`–`#109`):**
  - Killed (6): `#100, #102, #103, #104, #105, #106`
  - Survived non-equivalent (3): `#101, #107, #109`
  - Survived unreachable (1): `#108`
- **G6 (24 mutants, `#110`–`#133`):**
  - Killed (18): `#110, #111, #112, #113, #114, #115, #116, #117, #120, #121, #123, #124, #125, #126, #127, #128, #132, #133`
  - Survived non-equivalent (6): `#118, #119, #122, #129, #130, #131`
- **G7 (35 mutants, `#134`–`#168`):**
  - Killed (33): `#134`–`#159`, `#161`–`#167`
  - Survived non-equivalent (2): `#160, #168`
