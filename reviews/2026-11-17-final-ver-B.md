# Verification of two reviews of lot B

Reviewed against:
- Contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` (`main`) and `/Users/btw/Documents/repos/Docs/decisions/README.md` (`D-128` to `D-140`).
- Read-only clone: `/private/tmp/dodos-pr3-final` (`dodos-kernel` PR 3, head `6312868`).
- Experimental copy: `/private/tmp/dodos-pr3-ver-B`.
- Source reports: Opus (`v1-B-opus.md`, findings `O1`–`O24`) and DeepSeek (`v1-B-deepseek.md`, findings `D1`–`D13`).

Shared findings between the two reports (`O3`/`D6`+`D7`, `O4`/`D3`, `O6`/`D8`, `O10`/`D10`, `O13`/`D13`, `O16`/`D1`) are judged once under their combined heading. Reproductions were executed via temporary tests in `model/src/scenarios/ver_b_check.rs` and temporary fix mutations in `/private/tmp/dodos-pr3-ver-B` (`nix develop -c cargo test ...`), then cleaned with `git checkout -- .`.

---

## Findings judged once (shared between Opus and DeepSeek)

### O3 / D6 + D7 — `blocks.rs`: duplicated chunk-range arithmetic (`run`, `mapped_block`, `FreedRun::chunks`), unchecked overflow in `run`, and `remove_block_cap` wrapper
- **Lines**: `model/src/blocks.rs:18-21, 46-49, 327-338, 403-407, 431-433`, `model/src/caps.rs:1061`.
- **What we ran**: `repro_o3_d6_memory_take_overflow_checked` passed (`MemoryTake` with `place = u64::MAX - (1 << shift) + 1` and `size = shift` returned `Err(Error::Invalid)`). `memory_take` at `blocks.rs:46` checks `place.checked_add(1u64 << size)` before calling `self.run` (`blocks.rs:76`), and `run` has no other callers. However, `blocks.rs:431-433` duplicates the two-line `shift` / `chunks` range also written at `blocks.rs:331-332` and `FreedRun::chunks` (`blocks.rs:18-21`), and `remove_block_cap` (`blocks.rs:403-407`) is a two-caller one-line alias of `remove_leaf` (`caps.rs:1061`), against `.claude/skills/dodos-rust/SKILL.md` ("One small function per operation; a check that several operations share is written once").
- **Verdict**:
  - `D6` overflow-safety claim: **refuted** (`memory_take` checks overflow at `blocks.rs:46`).
  - `O3` / `D7` wrapper and `D6` chunk-range duplication: **real**, severity **minor**.
- **Correction**: In `model/src/blocks.rs`, delete `remove_block_cap` (`blocks.rs:405-407`) and call `self.remove_leaf(cap)` directly at `blocks.rs:226` and `321`; extract a small helper (e.g., `chunk_range(base, bytes, shift) -> Range<u64>`) shared by `FreedRun::chunks`, `mapped_block`, and `run`. Test: existing `blocks` and `ver_b_check::repro_o3_d6_memory_take_overflow_checked` pass.

### O4 / D3 — `lib.rs` & `model/Cargo.toml`: stale front-page docs and package description claiming one core and `unsupported` groups
- **Lines**: `model/src/lib.rs:1, 15-21`, `model/Cargo.toml:6`, `model/src/debug.rs:319-486`.
- **What we ran**: `repro_o4_d3_doc_claimed_unsupported_features_work` booted a 2-core node (`machine(Arch::X86_64, 2, &[&[0, 1]])`) and called `Syscall::IoportIn` (`Ok(Output::Value(0))`) and `Syscall::DebugWrite` (`Ok(Output::Done)`), directly contradicting `lib.rs:1, 15-21` and `Cargo.toml:6`. `blocks.rs:235-236` also returns `Output::Waits` for multi-core invalidations, and `Wait::Cores` (`lib.rs:787`) is entered (`cores.rs:359`).
- **Verdict**: **real**, severity **minor**.
- **Correction**: Rewrite the crate-level doc in `model/src/lib.rs:1-21` and `description` in `model/Cargo.toml:6` to match the multi-node, multi-core, asynchronous-invalidation model (`N` cores, `System`, `cores`/`debug`/`ioports` implemented). Test: `repro_o4_d3_doc_claimed_unsupported_features_work` (plus `cargo doc --no-deps`).

### O6 / D8 — `caps.rs`: duplicated pending-detach check in `undo`
- **Lines**: `model/src/caps.rs:1018-1027` and `1041-1050`.
- **What we inspected**: Both `(None, Some(cap))` and `(None, None)` arms of the `ObjectKind::IoSpace` match in `undo` begin with identical 9-line checks scanning `self.unit_requests` for `UnitOp::Detach` on `self.aspaces[&object].units`. Against `dodos-rust` ("a check that several operations share is written once").
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `Model::undo` (`model/src/caps.rs:1012-1053`), factor the pending-detach check into a helper or run it once when `device.is_none()` before branching on `records.last()`. Test: existing `units` / `pass19` / `pass20` iospace destruction tests pass (would fail if the guard is omitted or inverted).

### O10 / D10 — `debug.rs`: `range_of` falls back to `IoPortRange::ALL` on a malformed badge
- **Lines**: `model/src/debug.rs:523-525`, `boot.rs:1143`, `caps.rs:157, 200`, `debug.rs:476`.
- **What we ran**: `repro_o10_d10_range_of_malformed_badge_and_unreachable_via_derive` verified `debug::range_of(1 | (0 << 16)) == IoPortRange::ALL`, and confirmed `CapDerive` with non-zero badge on `START_SLOT_IOPORTS` returns `Err(Error::Invalid)` (`caps.rs:198-200`). Every constructor (`boot.rs:1143`, `ioports_issue` at `debug.rs:476`) stores a valid `IoPortRange`, so no syscall produces a malformed badge today. Still, falling back to `IoPortRange::ALL` fails open on an invariant violation instead of panicking like `Table::gate_word` (`table.rs:488`).
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `debug::range_of` (`model/src/debug.rs:524`), replace `.unwrap_or(IoPortRange::ALL)` with `.expect("an ioport range")`. Test: `repro_o10_d10_range_of_malformed_badge_and_unreachable_via_derive` fails if changed to `expect` unless testing valid round-trips (or add a `#[should_panic]` test on malformed badge).

### O13 / D13 — `faults.rs`: `raise` puts `endpoint` in `Window::cspace` when a faulting thread has no `cspace`
- **Lines**: `model/src/faults.rs:99-104`, `model/src/ipc.rs:524-553`, `model/src/check.rs:713-721`.
- **What we ran**: `repro_o13_d13_fault_with_endpoint_and_no_cspace` configured a thread with a fault endpoint, deleted its `cspace` (`cspace == None`), injected `FaultKind::Undefined`, asserted `k.m.check() == Ok(())`, observed `Wait::Call { window: Window { cspace: ep, first: 0, count: 0 }, .. }`, and received the fault cleanly via `Syscall::Recv`.
- **Contract**: `kernel-interface.md` ("Faults", ~line 190): fault delivery is a `call` with an empty receive range (`count == 0`); an empty receive range receives no capabilities and names no slot (`check.rs:720` checks `window.count == 0 || ...`, `ipc.rs:524-553` does not look up any slot when `caps.is_empty()` and `count == 0`).
- **Verdict**: **intended**, severity **note**.

### O16 / D1 — `memory.rs`: `plan_tables` counts `unhooked` tables as free, panicking in `rehook_by`
- **Lines**: `model/src/memory.rs:531, 190`, `model/src/boot.rs:1310`, `model/src/check/table.rs:479-480`.
- **What we ran**:
  1. `repro_o16_d1_iospace_map_panics_when_unhooked_non_empty` mapped a frame in `three()`, ran `CapDelete(s(201))` (`Err(Error::Again)`, leaving tables in `unhooked` and `free` empty), then called `IoSpaceMap` at `1 << 30` with `untyped: SlotAddr::NONE`: panicked at `model/src/memory.rs:190:42: a table on the free list`.
  2. `repro_o16_d1_aspace_map_panics_when_unhooked_non_empty` mapped a frame in a created `ASpace` on a 2-core node, cached it on core 1, ran `ASpaceUnmap` from core 0 (`Ok(Output::Waits)`), then had the thread on core 1 call `ASpaceMap` with `untyped: SlotAddr::NONE`: panicked with the same `a table on the free list`.
  3. Testing proposed fixes revealed a crucial trap: Opus's suggested `let free = aspace.free.len() as u64;` broke `scenarios::cores::two_threads` (`cores.rs:42` returned `Err(Error::NoMemory)` when mapping into `START_SLOT_ASPACE` with `untyped: SlotAddr::NONE`), because `boot.rs:1310` sets `tables = hooked + machine.reserve_tables` while `free` remains empty (`rehook_by` returns early at `memory.rs:160` for `from.is_none()`). DeepSeek's fix `let free = aspace.tables - hooked.len() as u64 - aspace.unhooked.len() as u64;` fixed both `ASpaceMap` and `IoSpaceMap` (`Err(Error::NoMemory)` instead of panic) and preserved `two_threads`.
- **Verdict**: **real**, severity **stop**.
- **Correction**: In `Model::plan_tables` (`model/src/memory.rs:531`), change `let free = aspace.tables - hooked.len() as u64;` to `let free = aspace.tables - hooked.len() as u64 - aspace.unhooked.len() as u64;`. Test: `repro_o16_d1_iospace_map_panics_when_unhooked_non_empty` and `repro_o16_d1_aspace_map_panics_when_unhooked_non_empty` (expecting `Err(Error::NoMemory)`, panics without the fix).

---

## Remaining findings of Opus (`v1-B-opus.md`)

### O1 — `blocks.rs`: `memory_split` does not check `mapped_block` (`device_leaves != 0`)
- **Lines**: `model/src/blocks.rs:296-297`, `model/src/blocks.rs:327-338`, `model/src/blocks.rs:126`.
- **What we ran**: `repro_o1_memory_split_with_frozen_device_leaves` took device entry `dev_idx` (`base = 2 << 20`), mapped a device frame into `IoSpace`, broke `IOMMU_ROLE`, deleted `IoSpace` and frame (`device_leaves[dev_idx] > 0` frozen), then called `MemorySplit`: it succeeded (`Ok(Output::Index(spare))`), and `sys.check()` passed. Taking `spare` (`device_leaves[spare] == 0`) also passed `sys.check()` even though its physical range came from a frozen entry. Subsequent `MemoryTake` on `dev_idx` succeeded and reset `device_leaves[dev_idx] = 0` (`blocks.rs:126`), after which `sys.check()` failed (`Err("node 0: 58: map count")`). Notice the contract itself omits `memory_split` from both the state rule and G5:
  - `kernel-interface.md:885`: "`memory_split`: the state, in order: `busy` if the untyped has a descendant or if a piece lives; `again` with nothing changed while its watermark is ready to return, as for `memory_give`; `busy` if no entry is unused and unclaimed."
  - `kernel-interface.md:1078` (G5): "`memory_give`, the destruction of a block and a change of page class require: map count 0 (for a block of a device entry, the entry's leaf count 0)".
- **Verdict**: **the contract's fault** (serious / **stop** in impact once fixed in contract + model).
- **Correction** (contract + model): Add the leaf-count check (`busy` if `device_leaves != 0`) to `memory_split` and G5 in `kernel-interface.md:885, 1078`, and in `Model::memory_split` (`model/src/blocks.rs:296`) check `if self.mapped_block(object) { return Err(Error::Busy); }`. Test: `repro_o1_memory_split_with_frozen_device_leaves` fails on `MemorySplit` returning `Ok(Index(_))` once guarded.

### O2 — `blocks.rs`: `taken_here` returns `false` for `Owner::Reserve(_)`, allowing double-take of a reserve chunk
- **Lines**: `model/src/blocks.rs:83, 159-172`, `abi/src/machine.rs:619`.
- **What we ran**: `repro_o2_reserve_chunk_taken_twice` claimed a `RoleKind::Reserve` role, took a reserve chunk via `MemoryTake`, then called `MemoryTake` a second time on the same `place` and `size`: both returned `Ok(Output::Done)`, and `k.m.check()` failed with `Err("53: two blocks on a chunk")`. Applying the fix (checking `self.kernel_runs.contains(&index)` or an in-flight `Completes::Run` covering `index` when `Owner::Reserve(_)` in `taken_here`) turned the second `MemoryTake` into `Err(Error::Busy)` with `k.m.check() == Ok(())`.
- **Verdict**: **real**, severity **stop**.
- **Correction**: In `Model::taken_here` (`model/src/blocks.rs:161-172`, called from `blocks.rs:83`), pass `(kind, index, word)` and for `Owner::Reserve(_)` check whether `kind == 0 && (self.kernel_runs.contains(&index) || ...)` (covering `self.kernel_runs` and any pending `Completes::Run` in `self.cores[..].request`). Test: `repro_o2_reserve_chunk_taken_twice` (second `MemoryTake` succeeds and fails invariant 53 without the fix).

### O5 — `lib.rs`: `chunked_or_kept` returns `true` for addresses beyond `table.owners`
- **Lines**: `model/src/lib.rs:1337-1343`, `model/tests/boot.rs:655-658`.
- **What we ran**: `repro_o5_chunked_or_kept_past_owners` called `m.chunked_or_kept(beyond)` (at `owners.len() << chunk_shift`) and `m.chunked_or_kept(u64::MAX)`: both returned `true` because `None != Some(&raw)`. With `.is_some_and(|&w| w != Ownership::none().raw())`, both returned `false`.
- **Verdict**: **real**, severity **fix** (test helper does less than its doc and `boot.rs:656` assert).
- **Correction**: In `Model::chunked_or_kept` (`model/src/lib.rs:1340`), replace `!= Some(...)` with `.is_some_and(|&w| w != dodos_abi::Ownership::none().raw())`. Test: `repro_o5_chunked_or_kept_past_owners` (returns `true` past `owners.len()` without the fix).

### O7 — `caps.rs`: stale/misplaced doc comments in `undo`
- **Lines**: `model/src/caps.rs:973-991`.
- **What we inspected**: Line 974 (`ObjectKind::Sched`) ends with "; destroying a notify disarms its armed timers", lines 977-979 (`ObjectKind::Notify`) place task detachment before "Then its watch slots" and omit `undoorbell_one`, and the `IoSpace` comment precedes `ObjectKind::Irq` (`caps.rs:989-991`).
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `Model::undo` (`model/src/caps.rs:973-991`), move each arm's doc comment to sit on its own match arm and list `undoorbell_one` on `Notify`. (Comment-only fix.)

### O8 — `caps.rs`: a block whose run keeps frozen leaf counts returns `again` forever on `cap_delete`
- **Lines**: `model/src/caps.rs:959-962`, `model/src/blocks.rs:327-338`, `model/src/memory.rs:276-296`.
- **What we ran**: `repro_o8_frozen_block_cap_delete_returns_again_forever` mapped a normal-memory frame into an `IoSpace` on `three()`, broke `IOMMU_ROLE`, removed `IoSpace` and frame (leaving `frozen` > 0), and called `CapDelete` on the block untyped 10 times with `m.run(30 * MS)` between calls: every call returned `Err(Error::Again)`.
- **Contract**: `kernel-interface.md:1078` (G5): "`memory_give`, the destruction of a block and a change of page class require: map count 0... A cleared leaf whose unit failed keeps its count for ever ([IOMMU](#iommu))." Thus a block covering a frozen leaf intentionally stays unremovable until restart (`caps.rs:959-962` comment + test would clarify, no behavior bug).
- **Verdict**: **intended**, severity **note**.

### O9 — `debug.rs`: `ports_of` demands `Rights::WRITE` on the indirection `cspace` capability
- **Lines**: `model/src/debug.rs:410-413`, `model/src/lib.rs:1681-1682, 1787`.
- **What we ran**: `repro_o9_ioport_out_through_read_only_cspace` grew a new `CSpace` (slot `200`), moved `START_SLOT_IOPORTS` into `SlotAddr::through(200, 1)`, derived a read-only `CSpace` cap in slot `201`, and called `IoportIn` (returned `Ok(Value(0))`) and `IoportOut` (returned `Err(Error::Denied)`) through `SlotAddr::through(201, 1)`. Changing `self.cap(thread, slot, right)?` to `self.cap(thread, slot, Rights::READ)?` made `IoportOut` return `Ok(Output::Done)`.
- **Contract**: `kernel-interface.md:110`: "Through a `cspace` capability, reading a slot (as the source of `cap_derive` or `cap_inspect`, or as the target of a call) needs `read`, and changing a slot (placing, moving out, deleting, revoking) needs `write`."
- **Verdict**: **real**, severity **fix**.
- **Correction**: In `Model::ports_of` (`model/src/debug.rs:411`), change `self.cap(thread, slot, right)?` to `self.cap(thread, slot, Rights::READ)?`. Test: `repro_o9_ioport_out_through_read_only_cspace` (`IoportOut` fails with `Err(Denied)` without the fix).

### O11 — `debug.rs` & `check/debug.rs`: stale docs say rate limit / debug area is per node block instead of per physical core
- **Lines**: `model/src/debug.rs:1-3, 50, 136`, `model/src/check/debug.rs:38-39`.
- **What we ran**: `repro_o11_rate_limit_is_per_core_not_per_node` flooded core 0 with 20 `TraceCode::FaultRecorded` events (`areas[0].suppressed == 4`) and then emitted 1 on core 1 (`areas[1].suppressed == 0`, 1 entry written), proving the rate limit is per physical core (`CorePart::limits`) per `kernel-interface.md:1574` ("Windows are counted per physical core... The counters sit in the core's part of the node block"). The docs at `debug.rs:50` ("debug area of each node"), `debug.rs:136` ("in the node block"), and `check/debug.rs:39` ("in the node block") were left behind when `D-129` moved `DebugArea` and rate limits per core.
- **Verdict**: **real**, severity **minor**.
- **Correction**: Update the three stale comments (`model/src/debug.rs:50`, `model/src/debug.rs:136`, `model/src/check/debug.rs:39`) to say per physical core / the core's part of the node block. Test: `repro_o11_rate_limit_is_per_core_not_per_node` pins per-core behavior.

### O12 — `faults.rs`: `raise`'s doc says an undeliverable fault is "dropped", whereas it calls `record`
- **Lines**: `model/src/faults.rs:55-58, 75-77, 110-118`.
- **What we ran**: `repro_o12_fault_without_endpoint_records_instead_of_dropping` injected `FaultKind::Undefined` on a thread without a fault endpoint; `k.m.check()` passed, `threads[&other].suspended == true`, and `threads[&other].recorded.is_some()`, matching `kernel-interface.md:482` ("A fault is recorded when it is not delivered"). Only `faults.rs:58` uses the wrong word ("dropped").
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `Model::raise`'s doc (`model/src/faults.rs:58`), replace "the fault dropped" with "the fault recorded in the thread". Test: `repro_o12_fault_without_endpoint_records_instead_of_dropping` verifies `record` behavior.

### O14 — `ipc.rs`: `Message::check_header` is a one-line wrapper around private `check`
- **Lines**: `model/src/ipc.rs:42-46`, `model/src/grants.rs:185`.
- **What we inspected**: `check_header` calls `self.check(page)` with the exact signature and one external caller (`grants.rs:185`). Making `check` `pub(crate)` removes the alias.
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `model/src/ipc.rs:42-46`, make `check` `pub(crate)` (renamed to `check_header`) and remove the forwarding method.

### O15 — `locks.rs`: `Step::Spin` is never pushed by `Model`
- **Lines**: `model/src/locks.rs:80-81`, `model/src/check/node.rs:284`, `model/src/scenarios/cores.rs:536`, `model/src/scenarios/checker.rs:219`.
- **What we inspected**: `scenarios/cores.rs:536` and `scenarios/checker.rs:219` explicitly plant `Step::Spin` traces to verify that `Model::check_locks` (`check/node.rs:284`) catches `"no lock is held across a wait for another core or for a unit"`, following `model/README.md` (`checker.rs` feeds bad states for every multi-core invariant, one test per invariant). Unlike sequence words (whose invariant is wholly uncheckable in the model), keeping `Step::Spin` as a checker variant is required to unit-test the `check_locks` spin rule and documents invariant coverage.
- **Verdict**: **intended**, severity **note**.

### O17 — `memory.rs`: stale docs on `detach` and `detach_local`, plus unused return value `u16`
- **Lines**: `model/src/memory.rs:907-910, 921, 1056, 1067, 1113-1128`.
- **What we inspected**: Since `D-139`, `detach` sends a unit request and only `detach_answered` (`memory.rs:1056`) frees the identifier word (`table.identifiers`) and removes the device from the iospace header; on a failed unit (`memory.rs:918-922`), `detach_local` does neither, keeping the identifier word as-is. Both callers of `detach_local` (`921`, `1067`) discard its `u16` domain return value.
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `model/src/memory.rs:907-910` and `1113-1128`, update the doc comments of `detach` and `detach_local` to match `D-139` (`detach_answered` writes the identifier word) and drop the unused `-> u16` return type of `detach_local`.

### O18 — `memory.rs`: `clear_mapping_pub` wrapper
- **Lines**: `model/src/memory.rs:249-252`, `model/src/scenarios/pass20.rs:797-798`, `model/src/caps.rs:1031`.
- **What we inspected**: `clear_mapping_pub` is a 1-line `pub(crate)` wrapper over private `clear_mapping` used at `scenarios/pass20.rs:798` (`caps.rs:1031` also calls it directly via the wrapper). Making `clear_mapping` `pub(crate)` eliminates the wrapper.
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `model/src/memory.rs:233, 249-252`, make `clear_mapping` `pub(crate)`, delete `clear_mapping_pub`, and call `clear_mapping` at `caps.rs:1031` and `scenarios/pass20.rs:798`.

### O19 — `sched.rs`: `hardware` doc attached to `request_due` and omits `reserve_due`
- **Lines**: `model/src/sched.rs:595-613, 635`.
- **What we inspected**: Lines 595-601 ("Due events and the hardware timer of a core...") describe `hardware` (line 613) and omit `self.reserve_due()` (line 635), while rustdoc attaches all of lines 595-605 to `request_due` (line 606), leaving `hardware` undocumented.
- **Verdict**: **real**, severity **minor**.
- **Correction**: Split the doc comment in `model/src/sched.rs:595-613` so lines 595-601 (updated to include `reserve_due` on core 0) sit on `hardware`, and lines 602-605 stay on `request_due`.

### O20 — `table.rs`: `write_member` doc claims compare-and-swap while writing unconditionally
- **Lines**: `model/src/table.rs:472-477`, `kernel-interface.md:897`.
- **What we inspected**: `write_member` overwrites `self.members[node as usize] = to` unconditionally without taking an expected `before` value, unlike `write_owner`, `write_core`, and `swap_attach`. (Similarly `write_role` at `table.rs:480` takes no `before`, though its doc does not claim CAS.) In `Model` (one event at a time under the node lock), no concurrent member-word mutation can race mid-call, so the doc claim "by compare-and-swap" misstates what the helper enforces.
- **Verdict**: **real**, severity **minor**.
- **Correction**: Either remove "by compare-and-swap" from `write_member`'s doc (`model/src/table.rs:472`) with a note that single-event execution has no concurrent writer, or pass `before` and return `bool` checked by callers.

### O21 — `table.rs`: `write_identifier` and `write_line` omit the `self.member(writer).writes()` gate check
- **Lines**: `model/src/table.rs:628, 657, 670-680, 728-738`, `model/src/nodes.rs:1450`, `model/src/check/table.rs:19-90`, `kernel-interface.md:900`.
- **What we ran**: `repro_o21_d11_fenced_node_write_line_unchecked_by_gate_and_checker` set node 0's member word to `MemberState::Fenced`: `write_owner` and `write_entry` returned `false`, whereas `write_line` wrote `Ownership::taken(Owner::Node(0), g)` unconditionally. (Note: `nodes.rs:1450` calls `write_line` during R6, where `self.node` is a **live** clearing node removing a dead node's line, so `self.member(writer).writes()` IS `true` for R6 as well.)
- **Contract**: `kernel-interface.md:900`: "Every write through a node's gate first reads that node's member word, and refuses unless the node is starting, live or sealing with its current generation ([Cores](#cores)); the kernel then parks itself."
- **Verdict**: **real**, severity **fix**.
- **Correction**: In `Table::write_identifier` (`model/src/table.rs:670`) and `Table::write_line` (`model/src/table.rs:728`), check `if !self.member(writer).writes() { return false; }`, return `bool`, and `assert!` at callers (`memory.rs:886, 1004, 1056`, `irq.rs:151, 611`, `nodes.rs:1450`); also have `judge_write` (`check/table.rs:19`) reject writes where the writer is not in a writable member state. Test: `repro_o21_d11_fenced_node_write_line_unchecked_by_gate_and_checker` (`write_line` and `write_identifier` succeed when fenced without the fix).

### O22 — `table.rs`: `started_node` decodes `NodeGen` manually instead of calling `NodeGen` methods
- **Lines**: `model/src/table.rs:455-461`, `abi/src/lib.rs:1076-1094`.
- **What we inspected**: `abi::NodeGen` (`abi/src/lib.rs:1076-1094`) has only `new`, `raw`, `node`, and `generation` — no `from_raw(u64)` constructor, and its inner `u64` field is private (`pub struct NodeGen(u64)`). Because `start_request` sets bit 63 (`1 << 63 | NodeGen::new(node, generation).raw()`), `started_node` cannot construct a `NodeGen` from `(raw & !(1 << 63))` without changing `abi/`.
- **Verdict**: **refuted**, severity **note** (impossible with `abi::NodeGen`'s current API; adding `NodeGen::from_raw` in `abi/` is optional).

### O23 — `tasks.rs`: `stop`'s comment lists three bounded waits while `Thread::bounded` has four
- **Lines**: `model/src/tasks.rs:175-178`, `model/src/lib.rs:750-755`, `model/src/threads.rs:147-149`.
- **What we inspected**: `tasks.rs:175` names "another node, a unit or its node's cores", omitting `Wait::Hand` (whereas `threads.rs:147-149` explicitly includes "nor the wait of a hand-over").
- **Verdict**: **real**, severity **minor**.
- **Correction**: In `model/src/tasks.rs:175-176`, add "or a hand-over" (`Wait::Hand`) to the comment on `Model::stop`.

### O24 — `threads.rs`: `thread_set_features` succeeds on a thread marked *leaving its core*
- **Lines**: `model/src/threads.rs:171-174`, `model/src/threads.rs:44-50`, `model/src/faults.rs:164, 211`, `kernel-interface.md:692, 725`.
- **What we ran**: `repro_o24_thread_set_features_succeeds_while_leaving` set up `two_threads(Arch::X86_64, 2)`, called `ThreadSuspend(s(300))` (`Err(Error::Again)`, leaving `other.leaving && other.suspended`), and called `ThreadSetFeatures { thread: s(300), mask: 0 }`: it returned `Ok(Output::Done)`. Adding `|| changed.leaving` to `threads.rs:172` made it return `Err(Error::Busy)`.
- **Contract**: `kernel-interface.md:692` ("whose state is partly in *b* (its registers, *b*'s pointer to it)... No call reads or writes its registers") and `kernel-interface.md:725` (`thread_set_features` "the whole vector state is set to its initial state"). While `leaving` is set, the thread's vector state is still active on the other core and cannot be reset (`threads.rs:44` and `faults.rs:164, 211` already check `leaving`).
- **Verdict**: **real**, severity **fix**.
- **Correction**: In `Model::thread_set_features` (`model/src/threads.rs:172`), change `if !changed.suspended || changed.wait != Wait::None` to `if !changed.suspended || changed.wait != Wait::None || changed.leaving`. Test: `repro_o24_thread_set_features_succeeds_while_leaving` (returns `Ok(Done)` without the fix).

---

## Remaining findings of DeepSeek (`v1-B-deepseek.md`)

### D2 — `debug.rs`: module doc claims code 4 (`UnitTimeout`) has no source and omits code 11 (`Refused`) and user codes `16`/`17`
- **Lines**: `model/src/debug.rs:6-11`, `model/src/units.rs:791`, `model/src/rings.rs:496, 522, 530`, `model/src/units.rs:532`, `kernel-interface.md:394, 1570-1572`.
- **What we inspected**: `units.rs:791` calls `self.trace(TraceCode::UnitTimeout, None, [unit, 0, 0])` (code 4), and `rings.rs:496, 522, 530` plus `units.rs:532` emit `TraceCode::Refused` (code 11), while `debug_write` and `trace_emit` emit codes 16 (`UserText`) and 17 (`UserEmit`) into the user ring.
- **Verdict**: **real**, severity **minor**.
- **Correction**: Update the module doc in `model/src/debug.rs:6-11` to list codes 4 (`UnitTimeout`) and 11 (`Refused`) among kernel-ring sources and note codes 16–17 in the user ring, leaving only codes 2, 7, and 8 as unsourced.

### D4 — `sched.rs` vs `lib.rs`: `timer_set` returns `WasArmed(0)` when an armed timer's `instant <= now`
- **Lines**: `model/src/sched.rs:1090-1104`, `model/src/lib.rs:452-454`, `model/src/check/sched.rs:185`.
- **What we ran**: `repro_d4_timer_set_on_expired_armed_timer_returns_0` armed 17 timers at `due = k.m.now + 1000`, advanced `k.m.now = due`, ran `k.m.timer_interrupt(0)` (which processes at most 16 due timers, leaving the 17th armed with `instant == now`), and called `Syscall::TimerSet` on that remaining timer with `deadline = due + 5000`: `TimerSet` returned `Ok(Output::WasArmed(0))` and set bit 0 of `notify` (and `k.m.check()` passed afterwards).
- **Contract**: `kernel-interface.md:635`: "`timer_set`, in order: if the timer is armed and its firing instant is not after now, it fires first (this is how one call sees its own timer exactly); then the result is 1 if the timer is still armed, and that arming is cancelled; 0 otherwise". (Note `lib.rs:453` doc could say "still armed" to match `sched.rs:1092`, and `check_timers` at `check/sched.rs:185` enforces `armed.instant > self.now` between idle points in the model.)
- **Verdict**: **intended**, severity **note**.

### D5 — `memory.rs`: `class_of` doc vs `bytes < chunk` vs `bytes >= chunk`
- **Lines**: `model/src/memory.rs:593-626`, `abi/src/lib.rs:495-521`, `kernel-interface.md:1076` (G3).
- **What we ran**: `repro_d5_class_of_geometry_has_no_size_between_page_and_chunk` confirmed `geometry.bytes(PageSize::Page) == Some(page)` and `geometry.bytes(PageSize::Large1) == Some(chunk)`. By `abi::Geometry::valid` (`abi/src/lib.rs:499`), `s[1] == s[0] + per_level` (`Large1` equals `chunk`), so no page size exists strictly between 1 page and 1 chunk. For `bytes >= chunk`, `not_data() != 0` falls through to `classes.range(...)` (`memory.rs:622`), which returns the first stored non-`DATA` class (which `PageClass::permits` rejects). Matches `kernel-interface.md:1076` verbatim ("that page's class byte" for one page; "the chunk's count" for whole chunks).
- **Verdict**: **refuted**.

### D9 — `caps.rs`: `fits` doc "holds only what is deeper than itself" vs `>=` for `Untyped`
- **Lines**: `model/src/caps.rs:391-413`, `kernel-interface.md:122`.
- **What we inspected**: `kernel-interface.md:122` states the exact rule under the bold heading "**A capability space holds only what is deeper than itself (design choice, D-103).** The root capability of another capability space can be placed in a capability space only if its depth is greater than the depth of the root capability of that space. An `untyped` capability (a root or a copy) can be placed there only if its depth is not smaller." `caps.rs:391-395` and `406-410` follow that exact wording and rule.
- **Verdict**: **refuted**.

### D11 — `table.rs`: `write_entry` reads `before` locally instead of taking `before` for compare-and-swap like `write_owner`
- **Lines**: `model/src/table.rs:621-635, 656-665`, `model/src/locks.rs:6-7`, `kernel-interface.md:897`.
- **What we inspected**: `kernel-interface.md:897` specifies that the real kernel gate "reads and checks each word just before it writes it, by compare-and-swap". In the executable `Model`, events of a node execute one at a time (`locks.rs:6-7`), so `write_entry` (like `write_member`, `write_role`, `write_identifier`, and `write_line`) reads `before = self.devices[index].owner.raw()` at the gate write instead of forcing callers to pass `before`. Only `write_owner`, `write_core`, and `swap_attach` take `before` where callers already hold or test against a stale snapshot. `write_entry`'s doc (`table.rs:655`) makes no false CAS claim (unlike `write_member` in O20).
- **Verdict**: **intended**, severity **note**.

### D12 — `locks.rs`: one `Lock(Gate)`/`Unlock(Gate)` pair per event instead of one per gate call
- **Lines**: `model/src/locks.rs:6-10, 117-141`, `model/src/check/node.rs:288-303`.
- **What we ran**: `repro_d12_gate_lock_emitted_once_per_event` ran a 2-chunk `MemoryTake` on a 2-core node (making 2 `write_owner` calls plus kernel mappings) and observed `steps.iter().filter(|&&s| s == Step::Lock(LockId::Gate)).count() == 1` and `Unlock(Gate) == 1`. While `end_locks` intentionally compresses gate-lock presence into one synthetic pair at the start of the event, `locks.rs:9` explicitly states "the gate lock inside it for each gate call", which disagrees with `end_locks`.
- **Verdict**: **real**, severity **minor**.
- **Correction**: Either update `model/src/locks.rs:8-10` to document that `end_locks` records one `Lock(Gate)`/`Unlock(Gate)` pair representing any gate writes in the event, or record a `Lock(Gate)`/`Unlock(Gate)` pair per gate call in `table.rs` / `memory.rs`. Test: `repro_d12_gate_lock_emitted_once_per_event` checks emitted gate lock count.

---

## What both reviewers missed in lot B

Our reproductions uncovered four gaps adjacent to the cited code that neither review noted. First, in `O1`, `check/table.rs:212-216` indexes `frozen_entries` by device-entry slot rather than by physical address range (unlike `entries` at `150, 188`), so after `memory_split` halves an entry with frozen `device_leaves > 0`, taking the new `spare` entry (`device_leaves[spare] == 0`) passes `System::check()` even though its physical pages still carry frozen DMA translations. Second, in `O16/D1`, checking `O16`'s proposed fix (`let free = aspace.free.len() as u64;`) broke `scenarios::cores::two_threads` (`cores.rs:42` failed with `Err(NoMemory)`) because `boot.rs:1310` records `hooked + machine.reserve_tables` in `START_SLOT_ASPACE.tables` without populating `free` (`root == None`, `memory.rs:160`), showing why `tables - hooked - unhooked` (with `unhooked.len()` subtracted) is needed instead of `free.len()`. Third, in `O21`, `judge_write` (`check/table.rs:19-90`) never checks `MemberState::writes()` on `write.writer`, so invariant 52 cannot catch gate writes from a fenced or dead writer, and `Table::write_role` (`table.rs:480`) writes unconditionally without `before` just like `write_member` (`O20`). Fourth, in `D12`, `Model::check_locks` (`check/node.rs:289-302`) verifies `Step::Lock(LockId::Gate)` sits inside `LockId::Node` but ignores `Step::Unlock(LockId::Gate)` completely, so an unpaired or late gate unlock passes the lock checker.

## Validation of fixes in the copy

With the fixes for `O2`, `O5`, `O9`, `O16`/`D1` (`tables - hooked - unhooked`), `O21`, and `O24` applied in `/private/tmp/dodos-pr3-ver-B` and `ver_b_check` updated to expect the fixed outcomes, the full `dodos-model` unit test suite ran and passed (`cargo test -p dodos-model --lib`: 541 passed, 0 failed), before cleaning `/private/tmp/dodos-pr3-ver-B` with `git checkout -- .`.

---

## Summary table

| finding | verdict | severity | correction in one line |
|---|---|---|---|
| O1 | the contract's fault | stop | Add `mapped_block` (`device_leaves == 0`) check to `kernel-interface.md:885, 1078` and `blocks.rs:296` |
| O2 | real | stop | Check `kernel_runs` and pending `Completes::Run` for `Owner::Reserve(_)` in `blocks.rs:83, 161-172` |
| O3 / D6 + D7 | real (duplication/wrapper); D6 overflow refuted | minor | Delete `remove_block_cap` (`blocks.rs:403-407`), call `remove_leaf`, share chunk-range helper (`memory_take` checks overflow at `46`) |
| O4 / D3 | real | minor | Update stale one-core / `unsupported` docs in `model/src/lib.rs:1, 15-21` and `model/Cargo.toml:6` |
| O5 | real | fix | Use `.is_some_and(\|&w\| w != none)` in `Model::chunked_or_kept` (`lib.rs:1340`) |
| O6 / D8 | real | minor | Factor duplicated `UnitOp::Detach` pending scan in `caps.rs:1019-1027, 1042-1050` |
| O7 | real | minor | Move misplaced arm comments and name `undoorbell_one` in `caps.rs:973-991` |
| O8 | intended | note | Contract `kernel-interface.md:1078` (G5) keeps frozen leaf counts forever until restart |
| O9 | real | fix | Pass `Rights::READ` instead of `right` to `self.cap` in `Model::ports_of` (`debug.rs:411`) |
| O10 / D10 | real | minor | Replace `.unwrap_or(IoPortRange::ALL)` with `.expect("an ioport range")` in `debug::range_of` (`debug.rs:524`) |
| O11 | real | minor | Update stale "node block" / "each node" comments to per physical core (`debug.rs:50, 136`, `check/debug.rs:39`) |
| O12 | real | minor | Fix `Model::raise` doc (`faults.rs:58`) from "dropped" to "recorded in the thread" |
| O13 / D13 | intended | note | Empty fault receive window (`count == 0`) never names or touches a slot (`kernel-interface.md:190`, `faults.rs:100-104`) |
| O14 | real | minor | Make `Message::check` (`ipc.rs:46`) `pub(crate)` as `check_header` and remove forwarding wrapper |
| O15 | intended | note | `Step::Spin` is a checker variant tested by planted bad traces in `scenarios/cores.rs:536` and `scenarios/checker.rs:219` |
| O16 / D1 | real | stop | Subtract `aspace.unhooked.len() as u64` from `free` in `Model::plan_tables` (`memory.rs:531`) |
| O17 | real | minor | Update `detach` and `detach_local` docs for `D-139` and drop unused `u16` return (`memory.rs:907-910, 1113-1128`) |
| O18 | real | minor | Make `clear_mapping` `pub(crate)` and delete `clear_mapping_pub` (`memory.rs:249-252`) |
| O19 | real | minor | Split `hardware` doc off `request_due` and mention `reserve_due` (`sched.rs:595-613`) |
| O20 | real | minor | Remove false "by compare-and-swap" claim on `write_member` (`table.rs:472`) or pass `before` |
| O21 | real | fix | Check `self.member(writer).writes()` in `write_identifier`/`write_line` (`table.rs:670, 728`) and `judge_write` |
| O22 | refuted | note | `abi::NodeGen` (`abi/src/lib.rs:1076-1094`) has a private field and no `from_raw` constructor |
| O23 | real | minor | Add "or a hand-over" (`Wait::Hand`) to `Model::stop`'s comment (`tasks.rs:175-176`) |
| O24 | real | fix | Add `\|\| changed.leaving` to busy check in `Model::thread_set_features` (`threads.rs:172`) |
| D2 | real | minor | Update `debug.rs:6-11` doc to include codes 4 (`UnitTimeout`), 11 (`Refused`), and 16–17 (`UserText`/`UserEmit`) |
| D4 | intended | note | Contract `kernel-interface.md:635` fires an expired armed timer first so `timer_set` returns `0` |
| D5 | refuted | note | `abi::Geometry::valid` enforces `Large1 == chunk`, so no size lies between 1 page and 1 chunk |
| D9 | refuted | note | `kernel-interface.md:122` uses the exact same heading and defines `>` for `CSpace` roots and `>=` for `Untyped` |
| D11 | intended | note | Single-event `Model` executes atomically (`locks.rs:6-7`); `write_entry` makes no CAS claim (`table.rs:656`) |
| D12 | real | minor | Fix `locks.rs:8-10` doc to say one `Lock(Gate)`/`Unlock(Gate)` per gated event (or record per gate call) |
