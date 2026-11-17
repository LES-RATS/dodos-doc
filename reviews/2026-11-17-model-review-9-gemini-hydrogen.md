# Model review 9: pass 17 (`633f6f3..c7951d8`)

Review of `/Users/btw/Documents/repos/dodos-kernel` (branch `model`, head `c7951d8`, commits `facf340`, `ecf5bba`, `c7951d8`) against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` (branch `main`, decisions D-128 to D-134).

Summary: 21 findings (9 Major, 12 Minor, including 6 surviving pass-17 mutations out of 32 run under full `./verify` in `/private/tmp/dodos-kernel-review9`).

## Findings

### Item 1: Model against pass 17 contract rules

1. **Major — RISC-V `stop()` stops and parks without checking the fence mark (`model/src/system.rs:640-644` vs `kernel-interface.md:1204`).**
   - **Contract (`kernel-interface.md:1204`):** "The node kernel's handler of the fence signal parks its core only if the core's word carries the fence mark; otherwise it returns (by `IRET` on x86-64) and changes nothing ... the gate sends an NMI, SDEI event 0 or the RISC-V stop only to a marked word, or for a start (G10)".
   - **Code (`model/src/system.rs:640-644`):**
     ```rust
     // RISC-V: the stop extension stops the hart whatever it does.
     (Arch::Riscv64, _) => {
         self.write_parked(core, true);
         self.hardware[core] = Hardware::Off;
     }
     ```
   - **State where they differ:** Call `System::late_wake(core)` (`model/src/system.rs:421-426`) on a running RISC-V hart whose core word is not marked (`Hardware::Running`). `late_wake` invokes `self.stop(core)` (`424`), which unconditionally writes `parked`, zeros `started`, sets `stopped[core]`, silences the core, and moves it to `Hardware::Off`. On x86-64 (`578-583`) and ARM64 (`625-626`), an unmarked running core ignores `stop(core)`. (In addition, if `Hardware::Off` on RISC-V receives `HwAction::Stop` when unmarked, `(Arch::Riscv64, _)` overwrites `parked` and sets `started = 0`.)
   - **Smallest correction:** On RISC-V, return early when `!self.marked(core)` (or guard `(Arch::Riscv64, hw)` with `if !self.marked(core)` for non-`Off` states, matching x86-64 and ARM64).

2. **Major — ARM64 `stop()` silently drops a stop on `Hardware::Entering` (`model/src/system.rs:625-639` vs `kernel-interface.md:1291`).**
   - **Contract (`kernel-interface.md:1291`):** "(1) Signal *p* with SDEI event 0 (`SDEI_EVENT_SIGNAL`), every core having registered the kernel's handler for event 0, enabled it and unmasked itself when it entered its node (the entry stub does the three before it reads its core word) ... (2) The handler writes what it can of the crash record and the park request it reads into `parked`, and completes the event with `SDEI_EVENT_COMPLETE_AND_RESUME` (0xC4000026) to the park routine of the kept image, which calls PSCI `CPU_OFF` outside any event".
   - **Code (`model/src/system.rs:625-639, 744-759`):** In `enter_if_named` (`744`), after reading the core word and passing the entry-stub checks, ARM64 sets `self.hardware[core] = Hardware::Entering`. If core >0 of a fresh multi-core node enters first, `enter()` (`757-758`) returns while waiting for core 0, leaving `hardware[core] == Hardware::Entering`. In `stop()`, ARM64 matches only `Hardware::Running | Hardware::Hung { nmi: true }` (`625-631`) and `Hardware::Off` (`634-638`), so `(Arch::Aarch64, Hardware::Entering)` falls through to `_ => {}` (`639`).
   - **State where they differ:** A fresh multi-core ARM64 node where core 1 takes `HwAction::Start` before core 0 (`hardware[1] == Hardware::Entering`), and another node accuses the starting node and sends `HwAction::Stop { core: 1 }` while core 1 is in `Entering`. Even though core 1 already passed the entry stub (where SDEI event 0 is registered and unmasked) and has a marked word, `stop(1)` does nothing.
   - **Smallest correction:** Include `Hardware::Entering` alongside `Hardware::Running | Hardware::Hung { nmi: true }` in the ARM64 arms at `model/src/system.rs:625-627` (and `fence_record` if appropriate).

3. **Major — x86-64 `stop()` treats `Hardware::Entering` as INIT (blocked on BSP / VMX) instead of NMI, and `fence_record()` skips `EntryStub { installed: true }` (`model/src/system.rs:547-550, 588-616` vs `kernel-interface.md:1204, 1285, 1288`).**
   - **Contract (`kernel-interface.md:1204, 1285, 1288`):** "The core enters the kept image's entry stub, which arms the fence's signal first (x86-64: it installs the node kernel's NMI handler ...), then reads its core word ... If *X*'s kernel can still run its NMI handler, the handler reads its core's word and finds the fence mark ... writes what it can of its core's crash record ... leaves VMX root operation if it is in it, **writes the park request it reads into `parked`**, and returns by `IRET` into the park stub".
   - **Code (`model/src/system.rs:546-552, 607-616`):**
     - `Hardware::Entering` (`611`) is placed in the INIT arm (`607-616`) instead of the NMI arm (`588-599`), even though `enter_if_named` (`744`) is reached only from `EntryStub { installed: true }` (`701-705`), where the node kernel's NMI handler is already installed. On a bootstrap core (`booted == true`) or in VMX root operation (`vmx == true`), `(Arch::X86_64, Hardware::Entering)` therefore ignores `stop()` (`613`, `617`) instead of parking by NMI.
     - `fence_record(core)` (`547-552`) returns early unless `matches!(self.hardware[core], Hardware::Running | Hardware::Hung { nmi: true })`, so calling `self.fence_record(core)` at `595` writes no crash record for `Hardware::EntryStub { installed: true }` (nor `Entering` once moved to the NMI arm).
   - **Smallest correction:** Move `Hardware::Entering` from the INIT arm (`611`) to the NMI arm (`588-592`), and allow `Hardware::EntryStub { installed: true } | Hardware::Entering` in `fence_record()` (`547-550`).

4. **Minor — x86-64 `wake()` with no start request leaves `parked` stale (`model/src/system.rs:676-680` vs `kernel-interface.md:1288`).**
   - **Contract (`kernel-interface.md:1288`):** "the stub's NMI handler, if it interrupted the stub's loop (from the stub's write of `parked` to its halt), writes the park request it reads into `parked` and reads the start request; it then returns by `IRET`."
   - **Code (`model/src/system.rs:676-680`):** When `start_requests[core]` parses as `None`, `wake()` has the comment `// The stub writes parked, finds no request, and halts again.` (`677`) and sets `self.hardware[core] = Hardware::Stub { window: true };`, without calling `write_parked(core, false)`.
   - **State where they differ:** If a park request was raised while the core was halted in `Hardware::Stub { window: false }`, and a stale `HwAction::Start` wakes it before `HwAction::Stop`, `parked` does not update to the new `park_requests[core]` as the contract and comment say.
   - **Smallest correction:** Call `self.write_parked(core, false);` in `wake()` when `Arch::X86_64` finds no start request at `676-680`.

5. **Major — `FenceRecord` is cleared at `accuse()` instead of first fence action, omits `generation`, and indexes `last_stop` by unreduced `core` instead of `core % 64` (`model/src/table.rs:167-171`, `model/src/nodes.rs:485, 910, 924, 1333-1335` vs `kernel-interface.md:1282`).**
   - **Contract (`kernel-interface.md:1282`):** "word 0, the generation the record concerns (bits 0-31, the other bits 0); word 1, the instant of the first fence action; word 2, the instant the fence was confirmed; word 3, reserved, 0; words 4 to 67, for each core of *X*, at index 4 + (its core number mod 64), the instant of the last stop sent to that core ... The first fence action of a generation writes the record anew (that generation, its instant, every other word 0)".
   - **Code:**
     - `model/src/table.rs:167-171` defines `FenceRecord` with `{ started, confirmed, last_stop: BTreeMap<usize, u64> }`: there is no `generation` field, and `last_stop` is keyed by `core: usize` (`nodes.rs:924`, `1335`) rather than `dodos_abi::FenceRecord::stop_index(core)` (`core % 64`).
     - `model/src/nodes.rs:485` resets `self.table.fences[node as usize] = FenceRecord::default();` in `accuse()`, *before* the first fence action (`nodes.rs:909-911`), rather than writing the record anew at the first fence action.
   - **State where they differ:** Between `accuse()` and the first `fence_unit()` step (when an accusation occurs and before the driver's reserve runs), the model already erased the prior generation's `FenceRecord` in `table.fences[node]`. Because `table::FenceRecord` lacks `generation` and uses full `core` instead of `core % 64`, `System` also never checks single-window uniqueness in `last_stop` or generation matching on `FenceRecord`.
   - **Smallest correction:** Store `generation: u32` in `table::FenceRecord`, index `last_stop` by `dodos_abi::FenceRecord::stop_index(core)` (`[u64; 64]` or map key `core % 64`), and reset the record inside `fence_unit` when `started.is_none()` (`nodes.rs:909-911`) rather than in `accuse()`.

6. **Major — `UnitOp::Attach` omits G9 (`iospace` root ownership/class check) and `UnitOp::Redirection` with `claimed: false` accepts nonzero operand 2 (`model/src/units.rs:265-291` vs `kernel-interface.md:1013, 1017, 1060`).**
   - **Contract (`kernel-interface.md:1013, 1017, 1060`):**
     - Op 1 attach (`1013`): gate checks "G9; the identifier word names the requester; the domain number is in the requester's range on the unit", where G9 (`1060`) requires: "The gate of a unit's role holder writes a context entry only if the root it names is a top-level iospace table owned by the node that owns the device".
     - Op 5 redirection entry (`1017`): operand 2 for `0 masked` is "`masked: 0`".
   - **Code (`model/src/units.rs:265-281`):**
     - `UnitOp::Attach { device, domain, root }` (`265-269`) checks only `held(device) && in_range(domain) && root != 0`: it never checks that `root` is a page of `PageClass::IOSPACE_TABLE` owned by `(node, generation)` (or a floor/live chunk owned by `node`).
     - `UnitOp::Redirection { claimed: false, gsi, .. }` (`276-280`) ignores `target`, `level`, and `low`, accepting `claimed: false` even when operand 2 (`target`) is `Target::Remapped` or `Target::Direct` instead of `Target::Masked` (operand 2 = 0).
     - In addition, `units.rs:240-245` passes `handle_core(handle)` (`usize::from(handle) / 192`, up to `341`) directly to `self.table.core_word(core)`, which indexes `self.core_words[core]` (`model/src/table.rs:358-360`) without bounds checking and panics instead of returning `false` (tracing code 11 and answering done per `1018`) on a forged out-of-range `handle: u16` on any machine with `< 342` cores.
   - **State where they differ:** A forged `Body::UnitRequest` injected into the holder's ring with `UnitOp::Attach { root: 4096, .. }` (a page not owned or not an iospace table) passes `operands_allowed` and attaches the device; a forged `UnitOp::Redirection { claimed: false, target: Target::Remapped { .. }, .. }` passes `operands_allowed`; and a forged `UnitOp::InterruptCache { handle: 65000 }` panics out-of-bounds in `core_word` instead of rejecting operand 1 and answering done.
   - **Smallest correction:** Check in `operands_allowed` that `root` is a valid aligned `PageClass::IOSPACE_TABLE` page owned by `(node, generation)` (in its floor or a `Taken(node, generation)` chunk), require `matches!(target, Target::Masked)` when `claimed == false`, and use `self.core_words.get(core)` in `Table::core_word`.

7. **Major — `irq_claim` skips later IOMMU units and IOAPIC redirection if unit 0 is held locally and already failed (`model/src/irq.rs:170-177`, `model/src/units.rs:174, 191-217, 324-340` vs `kernel-interface.md:1019`).**
   - **Contract (`kernel-interface.md:1019`):** "A unit found failed is passed over and the later units are still asked; after the last one, the claim of a line sends its redirection entry (operation 5) to the holder of the IOAPIC's role in the same entry".
   - **Code (`model/src/irq.rs:170-177`):**
     ```rust
     let entry = self.unit_request_with(role, op, waiter, None, Some((address, data)))?;
     if !units.is_empty()
         && let Some(e) = self.unit_requests[entry].as_mut()
     {
         e.segment = Some(segment);
         e.then = redirection;
     }
     Ok(Output::Waits)
     ```
     `unit_request_with` calls `self.unit_send_queued()` (`model/src/units.rs:174`) *before* `irq_claim` sets `e.segment = Some(segment)` and `e.then = redirection` (`irq.rs:174-175`). If the caller's node holds unit 0 (`holder == self.node && self.serves_role(role)`) and unit 0 is failed (`self.unit_failed(entry.role)` at `units.rs:324-326`), `unit_send_queued` calls `self.unit_complete(index, UnitResult::Failed)` immediately (`units.rs:325`). Inside `unit_complete`, `next_unit` sees `(segment: None, then: None) => return false` (`units.rs:202`), wakes the calling thread immediately with `Err(Error::Busy)` (`531-536`), skips all subsequent IOMMU units on `segment` and the IOAPIC `Redirection` entry, and `irq_claim` (`177`) returns `Ok(Output::Waits)` for a thread that is no longer waiting! (For a local IOAPIC line without remapping, `units.is_empty()` is true, `Redirection` completes synchronously inside `unit_send_queued` at `units.rs:338-340`, waking the thread with `Ok(Output::Msi { address: 0, data: 0 })`, and `irq_claim` likewise returns `Ok(Output::Waits)` instead of `Ok(Output::Msi { .. })` / already completed.)
   - **State where they differ:** Two IOMMU units on segment 0 (both held locally by node 0, unit 0 failed, unit 1 healthy) and an MSI or line `irq_claim` on node 0. Unit 1's interrupt entry cache is never invalidated, a line's IOAPIC redirection entry is never written, and `irq_claim` returns `Ok(Output::Waits)` while `thread.wait == Wait::None`.
   - **Smallest correction:** Pass `(segment, then)` directly into `unit_request_with` so `e.segment` and `e.then` are populated *before* `unit_send_queued()`, and return the thread's completed outcome (or avoid waking inside the syscall) if `unit_send_queued()` completes the entry synchronously.

8. **Major — Machine start-up does not refuse `BootNodes` when the core firmware booted is in no node (`model/src/boot.rs:624-653` vs `kernel-interface.md:1969`).**
   - **Contract (`kernel-interface.md:1969`):** "The kernel refuses to start, with a stop record ... if: ... `BootNodes` names a core twice, a core that is not usable, more cores in one node than the image supports, or two cores of different state features or vector lengths in one node, or leaves the core firmware booted in no node".
   - **Code (`model/src/boot.rs:633-653`):** `layout()` checks `slots_ok`, `domains_ok`, `nodes.len() <= n`, and `fits` (every node non-empty, `<= cores_supported`, alike features, cores in range and distinct in `named`). It never checks that the core with `c.booted == true` is in `named`.
   - **State where they differ:** A 2-core machine (`self.single() == false`) with core 0 (`booted: true`) and core 1 (`booted: false`), and `boot_nodes = Some((1, vec![(0, 0b10)]))`. `Machine::layout()` returns `Ok(...)` and leaves the bootstrap core out of every node instead of returning `Err(Refusal::Nodes)`. (Note also that when `self.single()` is `true`, `boot.rs:389-394, 404-416` ignores `self.boot_nodes` and uses `.position(|c| c.booted).unwrap_or(0)` at `414`, silently picking core 0 if no core is marked `booted`.)
   - **Smallest correction:** In `Machine::layout()` (`boot.rs:644-653`), when `!self.single()`, verify that the core firmware booted (or each `c` with `c.booted`) is contained in `named`, returning `Err(Refusal::Nodes)` otherwise.

9. **Major — `resume_step()` hangs forever when any peer is `Unfenced`, and `r0(node, old)` resets active reclaim progress for a restarted peer (`model/src/nodes.rs:1499-1591` vs `kernel-interface.md:1306, 1311, 1388`).**
   - **Contract (`kernel-interface.md:1306, 1311, 1388`):**
     - `1306, 1311`: "When *Y* sees *X* in **fenced** (or unfenced, for R2 to R5 only as far as they touch *Y*'s own memory), it finishes, in steps of its recovery reserve: ... **R5.** It clears `maps_of` bit *X* and writes `acked[X]` = *g* in its node beacon".
     - `1388`: "`node_start` Effect, mode 1: ... runs R0, R2 and R3 for every node whose generation ended while it was sealed and R4 and R5 for those still fenced or unfenced (`Grants`, "Generations"), in steps of its recovery reserve, then consumes what waited in its rings under the check, and the node becomes live with the same generation".
   - **Code (`model/src/nodes.rs:1509-1531` and `1134-1142`):**
     1. `resume_step()` (`1511-1521`) matches `MemberState::Fencing | MemberState::Fenced | MemberState::Unfenced` and returns `any` early whenever `state != MemberState::Fencing && !self.reclaims.get(&node).is_some_and(|r| r.acked)`. Because `reclaim_step()` (`1137`) sets `acked = true` *only* when `state == MemberState::Fenced` (not for `Unfenced`), `r.acked` remains `false` for any `Unfenced` peer (`1137` omits `Unfenced`, and R5 is not written for `Unfenced` or `resume_step` blocks on `acked` for `Unfenced`). Thus `resume_step` returns early at `1519` on every step, `self.ready` never becomes `true`, and the resuming node never leaves `Starting`.
     2. In `nodes.rs:1528-1530`, if a peer `node` was live/fencing (`old.generation() == g1`) when *Y* sealed, died (`Dead`), was restarted (`g2`), and entered `Fencing(g2)` before *Y* finished resuming, `ended_while_sealed(node)` returns `Some(g1)` on every call of `resume_step` (`sealed_view` is only cleared at `1536` when `ready` flips to `true`). Calling `self.r0(node, g1)` (`1529`) calls `self.reclaims.insert(node, Reclaim { generation: g1, isolated: true, .. })`, overwriting `reclaims[node]` for `g2` (`reclaim_step` at `1515` then sees `generation != g2` and restarts `r0`/`r1` every step!).
   - **Smallest correction:** Either do R5 (clear `maps_of` and set `acked = true`) for `Unfenced` peers in `reclaim_step` / wait on `r.audited` rather than `r.acked` for `Unfenced` in `resume_step`, and track per-sealed-generation `ended` completion (or only run `r0(node, old)` once per `ended_while_sealed(node)` when `sealed_ended_done` does not yet contain `(node, old)`).

---

### Item 2: Check of L2 lock order (`model/src/locks.rs` and `model/src/check/node.rs`)

10. **Major — Under L2, `end_locks()` tautologically passes `check_locks` for almost any wrong object lock order, and seven parts of the L2 contract rule are unreachable.**
    - **What no test can reach under the serial model:** Because `System` / `Model` execute one event at a time without concurrent threads holding locks (`locks.rs:286` emits `Step::Try(lock)` unconditionally whenever `lock < top`), no test can reach:
      1. a failing `Step::Try(lock)` (`kernel-interface.md:650`);
      2. releasing all held locks unchanged (`650`);
      3. round-2 acquisition of the discovered locks in canonical kind+address order by waiting (`Step::Lock`) (`650`);
      4. re-checking that every object read in round 1 still links to the same target (same head of queue, same neighbour in derivation/space/task list, same binding, not dying) (`650`);
      5. returning `Err(Error::Again)` from a changed link or a round-2 try failure (`650`, including the 14 syscalls at `653` for which `again` is newly L2-only);
      6. the non-syscall recovery paths at `652` (interrupt arrival or due timer failing a try on `Notify`, releasing `Core`, taking `Notify -> Core` or `Notify`/`Endpoint`, or firing a timer after releasing `Core` -> `Timer -> Core`, or a recovery reserve step ending early on a failed try);
      7. delaying `untyped_retype` watermark reuse until every other core finishes its current event (`654`).
    - **Can `check_locks` pass on a model that takes locks in a wrong order? Yes:**
      - In `model/src/locks.rs:266-297`, `end_locks()` builds `steps` *after* the event finishes from `self.locks.touched` plus `before.changed(self)` (deduplicated, with `LockId::Gate` forced last at `278-281`), emitting `Step::Try(lock)` whenever `lock < top` and `Step::Lock(lock)` otherwise (`283-292`), then unlocking in reverse order (`294-296`).
      - In `model/src/check/node.rs:296-339`, `check_locks()` checks only: every `Step::Lock(lock)` is strictly greater than all currently held locks (`306`), every `Step::Try(lock)` has *at least one* held lock `h > lock` and is not already held (`313`), `LockId::Gate` is last (`324`), `locks.len() <= bound` (`329`), and `paid == locks.len()` (`335`).
      - Because `found` has no duplicates and `top` is `max(held)`, `lock < top` guarantees `held.iter().any(|&h| lock < h) && !held.contains(&lock)` (`313`), and `lock >= top` guarantees `held.iter().all(|&h| h < lock)` (`306`). Therefore **any arbitrary permutation** of distinct non-`Gate` `LockId`s in `touched` + `before.changed()` satisfies `check_locks()` — including a model that *waits* (`Lock`) on a lower lock instead of taking locks in canonical order, or tries a lock that the contract (`650`, `653`) forbids trying (not reached via a link of an already-held object). The only errors `end_locks()` + `check_locks()` can catch are exceeding `bound` (`k`), `Gate` not last (impossible via `end_locks` unless `LockId::Gate` ordering changes), or manual test injection into `locks.steps`.
    - **Smallest correction:** Record explicit `Lock`/`Try` intentions at the lock-acquisition sites in syscall/interrupt handlers (including distinguishing true canonical waits from link-discovered tries against `kernel-interface.md:650, 653`) rather than synthesising `Try` vs `Lock` post-hoc from `touched` in `end_locks()`.

---

### Item 4: Bad-state tests of the checker (`scenarios/checker.rs` and `check/tests.rs`)

11. **Minor — Count discrepancy and three shadowed / defective G4 & G6 bad-state checks.**
    - **Test count:** Pass 17 has **62** bad-state checker tests, not 66: **45** `#[test]` functions in `model/src/scenarios/checker.rs` plus **17** new tests added at the end of `model/src/check/tests.rs:2598-2832` (total 208 tests in `check/tests.rs`).
    - **Random sample of 15 tests (`random.Random(17)`):** All 15 pass under `cargo test -p dodos-model --lib` (15 passed, 0 failed). Inspecting each test's mutation and assertion: 14 of the 15 fail directly at the invariant named in their title/assertion; #11 (`scenarios::checker::a_map_count_that_is_not_the_leaves_of_its_chunk_is_reported`) does *not* hit machine-level `G4` in `check/machine.rs:133` — it asserts `"node 0: 58: map count"` from `check/table.rs:412`.
      1. `scenarios::checker::a_core_that_runs_a_generation_that_is_over_is_reported` -> `P3: a core executes a dead node or a generation that is over`
      2. `scenarios::checker::a_message_applied_to_another_generation_of_its_receiver_is_reported` -> `apply: a message applied to a generation not in its member word`
      3. `check::tests::thread_whose_home_does_not_name_it_is_reported` -> `44: context of a home`
      4. `scenarios::checker::under_l2_more_than_k_locks_is_reported` -> `node 0: L2: more than k locks in one call`
      5. `scenarios::checker::a_thread_waiting_for_an_answer_no_credit_expects_is_reported` -> `node 0: CREDIT: a thread waits for an answer no credit expects`
      6. `scenarios::checker::under_l2_the_gate_lock_before_another_is_reported` -> `node 0: L2: the gate lock is not the last of the order`
      7. `scenarios::checker::a_marked_thread_with_no_leave_interrupt_is_reported` -> `node 0: 65: thread leaving its core without the leave interrupt`
      8. `check::tests::context_placed_on_a_core_the_node_does_not_have_is_reported` -> `42: core of a context`
      9. `check::tests::block_whose_parent_is_not_a_memory_control_is_reported` -> `51: block without its control`
      10. `check::tests::notify_that_lists_an_irq_not_bound_to_it_is_reported` -> `48: irq listed by a notify`
      11. `scenarios::checker::a_map_count_that_is_not_the_leaves_of_its_chunk_is_reported` -> `node 0: 58: map count` (shadows `G4`, see below)
      12. `scenarios::checker::a_thread_on_two_cores_is_reported` -> `node 0: 46: a thread on two cores`
      13. `scenarios::checker::under_l1_a_lock_of_an_object_is_reported` -> `node 0: L1: a lock of L2 under L1`
      14. `scenarios::checker::a_request_older_than_core_answer_ns_on_a_node_that_did_not_accuse_itself_is_reported` -> `node 0: 67: core did not answer within CORE_ANSWER_NS`
      15. `scenarios::checker::a_run_of_the_kernels_space_a_core_still_translates_after_it_was_given_is_reported` -> `G1: a core translates a run after it was given`
    - **The three shadowed checks:**
      1. **`G4` (`scenarios::checker::a_map_count_that_is_not_the_leaves_of_its_chunk_is_reported`, `checker.rs:440-468` vs `check/machine.rs:125-134`):** The test decrements `gate_words[chunk] -= 1`, which triggers per-node invariant `"node 0: 58: map count"` (`check/table.rs:405, 412`), never reaching `G4`. **Worse, there are two real bugs in `G4` (`check/machine.rs:125-133`) and the test's comment (`checker.rs:461-465`):**
         - First, in `checker.rs:442`, `frame` is allocated from node 0's **floor**, whose chunk has `table.owners[chunk] == 0` (`OwnState::None`, `Owner::Node(0)`, `generation: 0`). When probed by changing `gate_words[chunk] -= 1` to `+= 1`, `System::check()` returned **`Ok(())`** (`panicked at checker.rs:466: spoiled: ()`)! Why: `check/machine.rs:125-131` calls `Ownership::from_raw(0)` -> `Some(Ownership(0))` with `Owner::Node(0)` and `generation() == 0` without checking `w.state() == OwnState::Taken`, so `self.has_generation(0, 0)` is `false` and `alive` is `false`. Thus `G4` allows *any* over-counted `gate_words[floor_chunk]` (`held <= count`), and `check/table.rs:405` (`self.shared == true`) also checks only `l <= m`.
         - Second, contrary to the comment at `checker.rs:461-465`, per-node check `58` (`l <= m`) and machine `G4` (`held == count`) are *not* the same rule on a running node: for a `Taken` chunk, `+= 1` passes `58` and hits `G4` directly; for a floor chunk, `+= 1` slips past *both* `58` and `G4`.
      2. **`G6` (`scenarios::checker::a_grant_freed_while_its_holder_translates_to_it_is_reported`, `checker.rs:557-584`):** Running this test reports `"node 1: 58: leaves of a use entry"` (from `check/table.rs:413-415` on `used.leaves == 1` vs `granted == 0`). The `assert!(report.ends_with("G6: ...") || report.contains("58"))` succeeds only via the `"58"` fallback; `check_grants()` (`G6`, `check/machine.rs:163`) is shadowed whenever node 1 is running because `check_table()` runs first for every live/sealing/starting model in `System::check()`, checking both `table.grants[remote.node].get(&remote.grant)` (`check/table.rs:245-249`, `"58: translation under no grant"`) and `used.leaves == counted` (`check/table.rs:413-416`, `"58: leaves of a use entry"`). Thus `G6` in `check/machine.rs:163` only fires independently when node 1 has a valid local `uses[1]` entry whose leaves match `granted` (or is no longer running `check_table()`, i.e. `Fencing`/`Unfenced`).
      3. **`a_translation_under_no_grant_is_reported` (`checker.rs:608-625`):** Asserts `report == "node 1: 58: translation under no grant"`, explicitly expecting the per-node `58` check rather than `G6`.

---

### Item 5: Exploration assertions (`scenarios/explore.rs`) and `model/tests/property.rs` floors

12. **Minor — `reached("a full ring", full)` in `explore.rs` counts non-full writes leaving 1 entry free and uses a wrong entry count comment (`model/src/scenarios/explore.rs:621-637`).**
    - **Four exploration assertions checked:**
      - `crossed` (`explore.rs:150-168`): Genuine (count `10` measured previously). Checks `release_pending` or a `NodeMessage::Release` in flight matching a `GrantState::Revoking` entry on the same granter->grantee pair. Note: `crossed()` checks granter, grantee, and `Revoking` without matching the `grant` ID inside `Body::Release`, which is valid only because this test creates a single grant per seed.
      - `applied_handed` (`explore.rs:332, 336, 350-356`): Genuine (`38` measured). Incremented solely in `model/src/rings.rs:623` when `Body::Handed` passes `refused()` and is applied.
      - `stopped_in_request` (`explore.rs:704-714`): Genuine (`9` measured). Node 1 has physical cores 1 (position 0) and 2 (position 1, bit `0b10`); `stopped_in_request` increments only when `req.asked & 0b10 != 0 && req.acked & 0b10 == 0` right before calling `m.sys.hang(2, true)` inside an in-flight invalidation request.
      - **`full` (`explore.rs:621-637`, **defective assertion**):** The comment (`621-623`) states 60-word `NodeSend` messages take `"8 entries each, so the 64 entries of the ring fill before the 8 sends in flight are used."` In fact, `Body::Send::entries()` (`rings.rs:169, 175`, `abi/src/ring.rs:149`) is `ceil((16 + 8*(3 + 0 + 60)) / 64) = ceil(520 / 64) = 9` entries (so 7 sends = 63 entries, leaving 1 entry free; 8 sends would need 72 entries). Furthermore, line `634` checks `!m.sys.node(0).ring_room(1, NodeMessage::Send, 8)` **after** `m.call_by(0, thread, send)` *regardless of `outcome`* (`Ok(Output::Waits)` or `Err(Error::Gone)` vs `Err(Error::Busy)`). Thus the 7th *successful* `NodeSend` (`Ok(Output::Waits)`, `63` entries used, `1` free, `< 8`) already increments `full` even if no `NodeSend` ever fails with `Error::Busy`! (Probing this run showed `Err(Error::Busy)` did trigger 9 times across the seeds (`REAL_BUSY_FULL` x9), so the scenario *does* hit a real `Busy`, but `full` itself measures `!ring_room(_, _, 8)` post-call rather than `outcome == Err(Error::Busy)` and passes even if `Busy` drops to 0.)
    - **Smallest correction:** Check `outcome == Err(Error::Busy)` (and fix the comment `8 entries` -> `9 entries` and `ring_room(..., 9)` if keeping a room check).
    - **Floors in `model/tests/property.rs:2456-2625`:** Running `DODOS_COUNTS=1 cargo test -p dodos-model --test property -- --nocapture` across 4 KB, 16 KB, and 32 KB geometries gave identical minima for `objects_of_every_kind_are_seen_dying`, `scheduling_states_are_reached`, and `interrupts_and_marks_are_reached` (noting `no_context` = `448` in 32 KB vs `973` in 4 KB / 16 KB; `marked` = `3` in 32 KB vs `4` in 4 KB / 16 KB). Taking `ceil(0.75 * min)` across the three geometries reproduces every floor in the file verbatim:
      - `objects_of_every_kind_are_seen_dying` (`2468-2479`): `min = [27, 9438, 39, 9509, 141, 13, 13, 920, 472]` and `dying_copies = 32` -> `ceil(0.75 * min) = [21, 7079, 30, 7132, 106, 10, 10, 690, 354]` and `24`. Matches `[21, 7079, 30, 7132, 106, 10, 10, 690, 354]` and `[24]`.
      - `scheduling_states_are_reached` (`2575-2594`): `min = [80347, 5518, 270, 3277, 12964, 67910, 5887, 448]` and `[4771, 9]` -> `ceil(0.75 * min) = [60261, 4139, 203, 2458, 9723, 50933, 4416, 336]` and `[3579, 7]`. Matches verbatim.
      - `interrupts_and_marks_are_reached` (`2597-2610`): `min = [1234, 3, 81208, 2425, 3851]` -> `ceil(0.75 * min) = [926, 3, 60906, 1819, 2889]`. Matches verbatim.

---

### Item 6: Kani proofs (`abi/src/machine.rs` and `abi/src/ring.rs`)

13. **Minor — The three full-width `CoreWord` proofs omit `CORE_UNUSABLE` on `Joining`/`Owned`, omit `is_marked()`/`is_unusable()` readbacks, and never invoke `CoreWord::from_raw` at full widths (`abi/src/machine.rs:1587-1665`).**
    - **Coverage gaps in the three full-width proofs (`abi/src/machine.rs:1587-1647`):**
      1. `any_named_word()` (`1587-1595`) calls `marked()` conditionally but **never calls `.unusable()`**, so bit 3 (`CORE_UNUSABLE`) is pinned to `0` on `Joining` and `Owned` across all three full-width proofs (`core_words_read_back`, `core_words_keep_their_base`, `core_words_with_a_check_bit_flipped_are_refused`). (It is also omitted in `core_words_read_back_end_to_end` at `1660`.)
      2. `core_words_read_back()` (`1611-1620`) does **not** assert `word.is_marked()` (comparing to the coin flip) or `word.is_unusable()` on `word`, and does **not** assert `free.is_unusable() == u` on `CoreWord::free(u)` (`1617-1619`).
      3. Neither `core_words_read_back()`, `core_words_keep_their_base()`, nor `core_words_with_a_check_bit_flipped_are_refused()` actually invokes `CoreWord::from_raw` at the full 16-bit slot / 32-bit generation widths: the `from_raw(word.raw()) == Some(word)` and `from_raw(flipped).is_none()` claims rest on the prose argument in lines `1599-1608`, while `core_words_read_back_end_to_end` (`1652-1665`) runs `from_raw` only with 4-bit slot and 4-bit generation masks (`& 0xF`), and `core_words_keep_their_base` (`1627-1632`) copies `word.raw() & 0b11` and `word.raw() & (CORE_MARK | CORE_UNUSABLE)` directly from `word.raw()` rather than from the inputs chosen by `any_named_word`.
    - **Smallest correction:** Pass `(marked, unusable)` flags in `any_named_word()` (calling `.unusable()` as well as `.marked()`), assert `is_marked()` and `is_unusable()` on both `word` and `free` in `core_words_read_back`, and check `built` in `core_words_keep_their_base` from the chosen state/flags rather than `word.raw()`.
    - **Ring proof (`abi/src/ring.rs:291-332`):** The comment (`296-308`) matches what the proof proves: `sane` (`produced.wrapping_sub(consumed) <= entries`) is assumed for `ring_fits` (`321-326`), because when an overflowed ring calls `ring_fits` with `length == 0`, `ring_fits` returns `true` while `after - consumed > entries`; and `ring_resync` (`327-331`) is proven unconditionally without `sane`.

---

### Item 7: Unasked changes

14. **Minor — Checker `P2` silently ignores a running core when all claiming models mark it silent, and stops at the first non-silent match (`model/src/check/machine.rs:89-96` vs `kernel-interface.md:1185`).**
    - **Contract (`kernel-interface.md:1185`):** "no node holds the core, and it executes no kernel: it is parked ... *Owned* (*N*, *g*): the core runs *N*."
    - **Code (`model/src/check/machine.rs:89-96`):**
      ```rust
      let runner = self
          .models()
          .find(|(_, m)| m.position(core as u64).is_some_and(|p| !m.is_silent(p)))
          .map(|(n, _)| n);
      ensure(
          named && runner.is_none_or(|n| n == slot),
          "P2: a core executes a node its word does not name",
      )?;
      ```
    - **Flaws:** (a) When `hardware[core] == Hardware::Running` (`82`), `.find(...)` stops at the first non-silent model claiming `core`; if a second model *also* claims `core` non-silently and the first one happens to match `slot`, the duplicate runner is ignored. (b) If `hardware[core] == Hardware::Running` yet every model covering `core` has `is_silent(p) == true`, `runner` is `None` and `runner.is_none_or(|n| n == slot)` passes erroneously instead of flagging the mismatch between `Hardware::Running` and silent models.
    - **Smallest correction:** Collect all `(n, m)` with `m.position(core as u64).is_some_and(|p| !m.is_silent(p))` and require `named && runners == vec![slot]` (or `runners.is_empty()` only when `hardware[core] != Hardware::Running`).

15. **Minor — Invariant 43's silent-core exemption fails immediately on a clean resume if a throttled context's replenishment instant passed while sealed (`model/src/check/sched.rs:77-78`, `model/src/cores.rs:722` vs `kernel-interface.md:599`).**
    - **Code (`model/src/check/sched.rs:77-78`):**
      ```rust
      let silent = self.cores.get(sched.core).is_some_and(|c| c.silent);
      let throttled = silent || sched.throttled.is_some_and(|(at, _)| at > self.now);
      ```
    - While a core is hung or sealed (`c.silent == true`), no `timer_interrupt` runs on it, so exempting `c.silent` lets a multi-core node run on its other cores until `CORE_ANSWER_NS`, and lets a sealed node hold state until resumed. However, at a resume (`model/src/cores.rs:722`), `core_entered()` clears `part.silent = false` *before* `System::after(node)` and without taking a timer event; if a context was throttled with `at` earlier than `self.now` at resume (within `SEAL_NS`), `silent` becomes `false` while `at <= self.now`, breaking invariant 43 immediately after `core_entered`. Conversely, while `c.silent == true`, `78` bypasses `at > self.now` unconditionally without checking whether the node is within `CORE_ANSWER_NS` or sealed.

---

## Item 3: F2 equivalence and mutation campaign

### Equivalence check of F2 (`model/src/nodes.rs:879-885`)
The author's claim — *"the round loop already cancels, and no request can be written after an accusation"* — is **true** for lines `879-885` of `model/src/nodes.rs`:
1. When a node `node` at generation `g` is accused (`accuse()` at `model/src/nodes.rs:484-485`), `table.member(node)` becomes `MemberState::Fencing` and `table.fences[node as usize]` is reset so `started == None`.
2. At `fence_unit()` (`nodes.rs:878`), the `Fenced` arm requires `unconfirmed.is_empty() && started.is_some()`. It cannot be entered before line `910` sets `started = Some(now)` inside the first round loop.
3. On that very round where `started` becomes `Some(now)`, lines `926-931` execute and clear `self.table.start_requests[core] = 0` for every core whose `started_node` equals `(node, g)`.
4. Meanwhile, the only writer of nonzero `start_requests` (`start_step()` at `nodes.rs:1603-1615`) checks `member.state() == MemberState::Starting && member.generation() == start.generation` before writing `table.start_requests[core] = start.request`. Because `MemberState::Fencing | Unfenced | Fenced` never returns to `Starting` for generation `g` (`kernel-interface.md:1248`), no new start request for `(node, g)` can ever be written after `accuse()`.
5. Therefore `nodes.rs:879-885` is genuinely redundant (equivalent under all reachable executions), while `nodes.rs:926-931` is the active start-request cancellation loop (guarded by `scenarios::mistral::f2_the_first_round_of_a_fence_cancels_the_start_requests_aimed_at_the_node`).

### Pass-17 mutations

Full `./verify` (`cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`, and `DODOS_PAGE=16k` / `32k` runs) was run in `/private/tmp/dodos-kernel-review9` on each single-change pass-17 mutation and reverted immediately after each run.

16. **Minor (Surviving mutant `M5`) — No test covers an IOAPIC on a non-zero PCI segment (`model/src/irq.rs:86-92` vs `kernel-interface.md:1019`).**
    - **Contract (`kernel-interface.md:1019`):** "asks each unit that serves the source's PCI segment (an MSI's requester, or the IOAPIC of a line, whose segment the DMAR gives)".
    - **Surviving mutation (`M5`, `model/src/irq.rs:92`):**
      ```diff
      --- a/model/src/irq.rs
      +++ b/model/src/irq.rs
      @@ -90,5 +90,5 @@ impl Model {
                       .iter()
                       .find(|io| (io.first_gsi..io.first_gsi + io.inputs).contains(&source.id()))
      -                .map_or(0, |io| io.segment),
      +                .map_or(0, |_io| 0),
                   false => source.segment(),
               };
      ```
    - **Command & Result:** `./verify` exited `0` (all tests passed across default, `16k`, and `32k`). Because every test places its IOAPIC on segment `0`, hardcoding an IOAPIC line's segment to `0` goes undetected.
    - **Smallest correction:** Add a test with an IOMMU unit and IOAPIC on segment `1` (plus an IOMMU unit on segment `0`), verifying `irq_claim` of a line asks only the segment-1 IOMMU before programming the IOAPIC redirection entry.

17. **Minor (Surviving mutant `M3`) — No test checks the 64-core single-window bound on the one-node class-0 fallback (`model/src/boot.rs:409-415` vs `kernel-interface.md:1972`).**
    - **Contract (`kernel-interface.md:1972`):** "the machine then runs one node, on every usable core if they lie in one window of 64 core numbers, have the same state features and vector lengths, and are no more than the image supports, and on the core firmware booted otherwise".
    - **Surviving mutation (`M3`, `model/src/boot.rs:409-411`):**
      ```diff
      --- a/model/src/boot.rs
      +++ b/model/src/boot.rs
      @@ -407,7 +407,6 @@ impl Machine {
                   // are no more than the image supports; the core firmware booted
                   // otherwise (Start-up state, D-134).
      -            let one_window = count <= dodos_abi::CORE_WINDOW_BITS as usize;
                   let alike = (0..count).all(|c| self.state_kind(c) == self.state_kind(0));
      -            if count <= self.cores_supported as usize && one_window && alike {
      +            if count <= self.cores_supported as usize && alike {
                       return vec![(0..count).collect()];
                   }
      ```
    - **Command & Result:** `./verify` exited `0` (all tests passed across default, `16k`, and `32k`). Note also that `one_window` (`409`) checks only `count <= 64`, not whether the usable cores have `hw_id`/positions in one 64-core window, and no test constructs a `single()` machine with `> 64` alike cores and `cores_supported > 64`.
    - **Smallest correction:** Add a `boot` unit test with `65` cores (`cores[0].fence = 0`, `cores_supported = 128`, alike kinds, `cores[0].booted = true`), asserting `machine.initial_nodes() == vec![vec![0]]`.

18. **Minor (Surviving mutant `M20`) — No test checks that ARM64 SDEI event 0 respects the fence mark (`model/src/system.rs:625-626` vs `kernel-interface.md:1204`).**
    - **Contract (`kernel-interface.md:1204`):** "The node kernel's handler of the fence signal parks its core only if the core's word carries the fence mark; otherwise it returns (by `IRET` on x86-64) and changes nothing ... the gate sends an NMI, SDEI event 0 or the RISC-V stop only to a marked word, or for a start (G10)".
    - **Surviving mutation (`M20`, `model/src/system.rs:625-626`):**
      ```diff
      --- a/model/src/system.rs
      +++ b/model/src/system.rs
      @@ -623,6 +623,4 @@ impl System {
                   // The fence is confirmed by OFF after the request, never by the
                   // handler's own write.
      -            (Arch::Aarch64, Hardware::Running | Hardware::Hung { nmi: true })
      -                if !self.marked(core) => {}
                   (Arch::Aarch64, Hardware::Running | Hardware::Hung { nmi: true }) => {
                       self.fence_record(core);
      ```
    - **Command & Result:** `./verify` exited `0` (all tests passed across default, `16k`, and `32k`). `a_start_wake_that_reaches_a_core_already_running_changes_nothing` (`model/src/scenarios/pass17.rs:158-170`) tests `late_wake` only on `Arch::X86_64`, so removing the `!self.marked(core)` guard on ARM64 is undetected.
    - **Smallest correction:** Parameterize `a_start_wake_that_reaches_a_core_already_running_changes_nothing` (or add a sibling test) over `Arch::Aarch64` (and `Arch::Riscv64`).

19. **Minor (Surviving mutant `M23`) — No test has an earlier failed unit followed by a later healthy unit before the last step of `irq_claim` (`model/src/units.rs:192` vs `kernel-interface.md:1019`).**
    - **Contract (`kernel-interface.md:1019`):** "A unit found failed is passed over and the later units are still asked; after the last one, the claim of a line sends its redirection entry (operation 5) to the holder of the IOAPIC's role in the same entry ... then the call ends, `busy` if any unit was found failed."
    - **Surviving mutation (`M23`, `model/src/units.rs:192`):**
      ```diff
      --- a/model/src/units.rs
      +++ b/model/src/units.rs
      @@ -190,5 +190,4 @@ impl Model {
           /// used again.
           fn next_unit(&mut self, index: usize, entry: UnitEntry, failed: bool) -> bool {
      -        let failed = entry.failed || failed;
               let next = entry.segment.and_then(|segment| {
                   let roles = self.segment_roles(segment);
      ```
    - **Command & Result:** `./verify` exited `0` (all tests passed across default, `16k`, and `32k`). Because `pass17::a_claim_passes_a_failed_unit_asks_the_later_ones_and_ends_busy_keeping_the_irq` (`pass17.rs:414-431`) breaks the second of 3 units (so the final transition sees `entry.failed == true` directly from unit 1's failure without passing through an intermediate healthy unit), `entry.failed || failed` is never needed unless an earlier unit failed before a *non-final* healthy unit succeeds (e.g., failing unit 0 in a 3-unit MSI, or failing any IOMMU unit before a line's IOAPIC redirection step!).
    - **Smallest correction:** Break unit 0 (or any unit in a remapped line claim across a working later unit + IOAPIC) in `pass17::a_claim_passes_a_failed_unit_asks_the_later_ones_and_ends_busy_keeping_the_irq`, asserting `Err(Error::Busy)` at the end.

20. **Minor (Surviving mutant `M26`) — No test checks that `UnitOp::Detach` verifies the domain number (`model/src/units.rs:270-273` vs `kernel-interface.md:1014`).**
    - **Contract (`kernel-interface.md:1014`):** Op 2 detach checks "the context entry names the requester's generation and that domain number (or none is left: a detach is idempotent)".
    - **Surviving mutation (`M26`, `model/src/units.rs:270-273`):**
      ```diff
      --- a/model/src/units.rs
      +++ b/model/src/units.rs
      @@ -269,6 +269,6 @@ impl Model {
                   } => held(device) && in_range(domain) && root != 0,
                   UnitOp::Detach { device, domain } => state.is_none_or(|u| {
      +                let _ = domain;
                       u.entries.get(&device).is_none_or(|&owner| owner == from)
      -                    && u.domains.get(&device).is_none_or(|&d| d == domain)
                   }),
                   UnitOp::Invalidate { domain } => domain.is_some_and(in_range),
      ```
    - **Command & Result:** `./verify` exited `0` (all tests passed across default, `16k`, and `32k`). `the_holder_refuses_a_detach_of_a_context_entry_of_another_node` (`pass17.rs:587-607`) tests detaching another node's device, never detaching the requester's own device under a wrong domain number.
    - **Smallest correction:** In `the_holder_refuses_a_detach_of_a_context_entry_of_another_node` (or a sibling test), attach a device for `requester` under domain `own`, then inject `UnitOp::Detach { device: 0x10, domain: own + 1 }` and assert `judged(...) == true` and the context entry remains attached.

21. **Minor (Surviving mutant `M31`) — No test checks `UnitOp::Attach`'s `root` operand at all (`model/src/units.rs:269` vs `kernel-interface.md:1013, 1060`).**
    - **Contract (`kernel-interface.md:1013, 1060`):** Op 1 attach checks "G9; the identifier word names the requester; the domain number is in the requester's range on the unit", where G9 requires `root` to be a top-level iospace table owned by the requester.
    - **Surviving mutation (`M31`, `model/src/units.rs:265-269`):**
      ```diff
      --- a/model/src/units.rs
      +++ b/model/src/units.rs
      @@ -267,5 +267,8 @@ impl Model {
                       domain,
                       root,
      -            } => held(device) && in_range(domain) && root != 0,
      +            } => {
      +                let _ = root;
      +                held(device) && in_range(domain)
      +            }
                   UnitOp::Detach { device, domain } => state.is_none_or(|u| {
      ```
    - **Command & Result:** `./verify` exited `0` (all tests passed across default, `16k`, and `32k`). No test supplies a `root` of `0` (nor a non-iospace / foreign-owned root; see also Finding 6).
    - **Smallest correction:** Enforce full G9 ownership + `PageClass::IOSPACE_TABLE` check in `operands_allowed` (Finding 6) and add a forged `UnitOp::Attach` test with `root: 0` and with another node's / non-`IOSPACE_TABLE` page.

| ID | Target | Contract sentence violated | Command | Result |
|---|---|---|---|---|
| `M1` | `abi/src/machine.rs:295` (`core % 32`) | `kernel-interface.md:1282` (`at index 4 + (its core number mod 64)`) | `./verify` | Killed (`dodos-abi`: `tests::a_fence_record_indexes_its_last_stops_by_core_number_modulo_64`) |
| `M2` | `model/src/boot.rs:384` (drop `&& !self.accept_unfenced`) | `kernel-interface.md:1293` (`or declares that it accepts an unfenced core`) | `./verify` | Killed (`boot`: `a_machine_with_a_core_of_fence_class_0_runs_one_node_unless_declared`) |
| `M3` | `model/src/boot.rs:409-411` (drop `one_window`) | `kernel-interface.md:1972` (`if they lie in one window of 64 core numbers`) | `./verify` | **SURVIVED** (`./verify` rc=0) |
| `M4` | `model/src/boot.rs:650` (`u.domains` without `.saturating_sub(2)`) | `kernel-interface.md:1008, 1969` (`d = floor((D - 2) / n)`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::the_start_up_refuses_a_unit_with_fewer_domain_numbers_than_node_slots`) |
| `M5` | `model/src/irq.rs:92` (`.map_or(0, |_io| 0)`) | `kernel-interface.md:1019` (`the IOAPIC of a line, whose segment the DMAR gives`) | `./verify` | **SURVIVED** (`./verify` rc=0) |
| `M6` | `model/src/irq.rs:174` (`e.segment = None`) | `kernel-interface.md:1019` (`asks every unit that serves the source's PCI segment`) | `./verify` | Killed (`dodos-model`: 5 tests incl. `scenarios::units::the_claim_of_an_msi_asks_each_remapping_unit_of_its_segment_one_after_another`) |
| `M7` | `model/src/irq.rs:175` (`e.then = None`) | `kernel-interface.md:1019` (`after the last one, the claim of a line sends its redirection entry`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_claim_of_a_remapped_line_invalidates_the_interrupt_entry_cache_before_the_redirection_entry`) |
| `M8` | `model/src/locks.rs:286` (`Step::Lock(lock)` instead of `Step::Try(lock)`) | `kernel-interface.md:650` (`A core waits for a lock only in the order by kind`) | `./verify` | Killed (`dodos-model`: 7 tests incl. `scenarios::pass17::under_l2_a_call_records_its_locks_in_the_order_it_took_them_with_tries_apart`) |
| `M9` | `model/src/locks.rs:280` (`found.insert(0, LockId::Gate)`) | `kernel-interface.md:646` (`The gate lock is the last lock of every order`) | `./verify` | Killed (`dodos-model`: 7 tests incl. `scenarios::cores::under_l2_a_call_takes_its_locks_in_the_order_of_their_kind_the_gate_lock_last`) |
| `M10` | `model/src/memory.rs:824-827` (omit domain reuse on second attach) | `kernel-interface.md:1008` (`takes the number of an iospace ... at its first device`) | `./verify` | Killed (`memory`: `unit_without_a_free_domain_number_is_busy`) |
| `M11` | `model/src/memory.rs:928-930` (omit `self.domains.remove(&iospace)`) | `kernel-interface.md:1008` (`and frees it with the last`) | `./verify` | Killed (`memory`: `unit_without_a_free_domain_number_is_busy`) |
| `M12` | `model/src/nodes.rs:926-931` (drop round-loop `start_requests` clear) | `kernel-interface.md:1204` (`A fence cancels the start requests of the cores whose words name the fenced node`) | `./verify` | Killed (`dodos-model`: `scenarios::mistral::f2_the_first_round_of_a_fence_cancels_the_start_requests_aimed_at_the_node`) |
| `M13` | `model/src/nodes.rs:1529` (omit `self.r0(node, old)`) | `kernel-interface.md:1388` (`runs R0, R2 and R3 for every node whose generation ended while it was sealed`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_resume_after_a_peer_died_and_started_fresh_runs_r0_and_frees_the_grants_to_it`) |
| `M14` | `model/src/nodes.rs:1567` (omit `GrantState::Pinned` in `drop_ended`) | `kernel-interface.md:1309, 1388` (`R3 marks pinned the grants made to X's generation`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_resume_after_a_peer_died_and_started_fresh_runs_r0_and_frees_the_grants_to_it`) |
| `M15` | `model/src/nodes.rs:1757-1758` (run `roles_step` before `serve_kernel_rings`) | `kernel-interface.md:949-960` (`Handed` applied before target reads role word) | `./verify` | Killed (`dodos-model`: `scenarios::explore::unit_a_request_across_a_hand_over_and_the_deaths_of_its_parties`) |
| `M16` | `model/src/rings.rs:456` (accept `stamp.0 != 0` bypassed via omitting `stamp.0 != 0`) | `kernel-interface.md:1169` (`the sender's stamp ... is 0 for a sender attached to no task`) | `./verify` | Killed (`dodos-model`: 5 tests incl. `scenarios::pass17::a_send_whose_stamp_is_0_is_accepted_from_any_node`) |
| `M17` | `model/src/rings.rs:456` (accept `task.counter() == 0` when `stamp.0 != 0`) | `kernel-interface.md:1082` (`counter starts at 1; identifier 0 means no task`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_send_whose_stamp_has_a_counter_of_0_is_refused`) |
| `M18` | `model/src/system.rs:578-583` (remove x86-64 `!self.marked(core)` guard) | `kernel-interface.md:1204` (`The node kernel's handler parks its core only if the core's word carries the fence mark`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_start_wake_that_reaches_a_core_already_running_changes_nothing`) |
| `M19` | `model/src/system.rs:595-611` (move `EntryStub { installed: false }` from INIT to NMI arm) | `kernel-interface.md:1288` (`An NMI that interrupts the entry stub before it has installed the handler only returns`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_fence_nmi_that_lands_in_the_entry_stub_gives_no_false_confirmation`) |
| `M20` | `model/src/system.rs:625-626` (remove ARM64 `!self.marked(core)` guard) | `kernel-interface.md:1204` (`parks its core only if the core's word carries the fence mark`) | `./verify` | **SURVIVED** (`./verify` rc=0) |
| `M21` | `model/src/system.rs:681-690` (skip `EntryStub { installed: false }` on x86-64 wake) | `kernel-interface.md:1204` (`The core enters the kept image's entry stub, which arms the fence's signal first`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_fence_nmi_that_lands_in_the_entry_stub_gives_no_false_confirmation`) |
| `M22` | `model/src/system.rs:731` (omit `self.park(core)` when x86-64 entry stub rejects) | `kernel-interface.md:1288` (`the park stub writes the park request it reads into parked`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_fence_nmi_that_lands_in_the_entry_stub_gives_no_false_confirmation`) |
| `M23` | `model/src/units.rs:192` (omit `let failed = entry.failed || failed;`) | `kernel-interface.md:1019` (`then the call ends, busy if any unit was found failed`) | `./verify` | **SURVIVED** (`./verify` rc=0) |
| `M24` | `model/src/units.rs:227` (`let first = u32::from(slot) * per;`) | `kernel-interface.md:1008` (`number 0 is never used; slot s owns 1 + s*d to (s+1)*d`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::each_node_slot_takes_its_domain_numbers_from_its_own_range` & `the_holder_refuses_an_attach_under_a_domain_number_of_another_node`) |
| `M25` | `model/src/units.rs:269` (omit `in_range(domain)` in `UnitOp::Attach`) | `kernel-interface.md:1013` (`the domain number is in the requester's range on the unit`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::the_holder_refuses_an_attach_under_a_domain_number_of_another_node`) |
| `M26` | `model/src/units.rs:270-273` (omit domain match in `UnitOp::Detach`) | `kernel-interface.md:1014` (`the context entry names the requester's generation and that domain number`) | `./verify` | **SURVIVED** (`./verify` rc=0) |
| `M27` | `model/src/units.rs:274` (omit `in_range` check in `UnitOp::Invalidate`) | `kernel-interface.md:1015` (`the domain number is in the requester's range`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::the_holder_refuses_an_invalidation_of_a_domain_number_of_another_node`) |
| `M28` | `model/src/units.rs:275` (omit `names(handle_core(handle))` in `UnitOp::InterruptCache`) | `kernel-interface.md:1016` (`the handle lies in the range of a core whose word names the requester`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::the_holder_refuses_an_interrupt_entry_cache_invalidation_of_a_handle_of_another_nodes_core`) |
| `M29` | `model/src/units.rs:283-288` (omit requester core check for `Target::Direct` in `UnitOp::Redirection`) | `kernel-interface.md:1017` (`claimed: the handle, or the APIC ID, names a core whose word names the requester`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::the_holder_of_an_ioapic_refuses_a_redirection_entry_aimed_at_another_nodes_core`) |
| `M30` | `model/src/units.rs:511` (`if result == UnitResult::Done && self.next_unit(...)`) | `kernel-interface.md:1019` (`A unit found failed is passed over and the later units are still asked`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::a_claim_passes_a_failed_unit_asks_the_later_ones_and_ends_busy_keeping_the_irq`) |
| `M31` | `model/src/units.rs:269` (omit `root != 0` in `UnitOp::Attach`) | `kernel-interface.md:1013, 1060` (`G9: root names top-level iospace table owned by requester`) | `./verify` | **SURVIVED** (`./verify` rc=0) |
| `M32` | `model/src/units.rs:289` (`Target::Masked => true` on claimed `UnitOp::Redirection`) | `kernel-interface.md:1017` (`claimed redirection operand 2 is remapped or direct, not masked: 0`) | `./verify` | Killed (`dodos-model`: `scenarios::pass17::the_holder_of_an_ioapic_refuses_a_redirection_entry_aimed_at_another_nodes_core`) |


---

## Checked and found correct

- **Stamp of a sender attached to no task (`model/src/grants.rs:261-269, 292-297`, `model/src/rings.rs:454-457` vs `kernel-interface.md:1104-1105, 1169`):** Checked `stamp_of()` and `Body::Send` validation. When `thread.task == None`, `stamp_of` puts `0` in `stamp.0` and uses `self.marks(thread)` for `stamp.1` (`kernel-interface.md:1104-1105, 1169`); `rings.rs:454-457` accepts `stamp.0 == 0` or `(task.counter() != 0 && task.node() == sender)` (`pass17::a_thread_attached_to_no_task_sends_to_another_node_and_gets_its_answer` tests this path).
- **`UnitOp::Detach` idempotency (`model/src/units.rs:270-273` vs `kernel-interface.md:1014`):** Matches the rule `"the context entry names the requester's generation and that domain number (or none is left: a detach is idempotent)"`.
- **Unasked change — `reserve_step` ordering (`model/src/nodes.rs:1753-1758`):** `unit_step(); serve_kernel_rings(&mut units); roles_step(&mut units);` lets a `Handed` unit role delivered in `serve_kernel_rings` take effect before `roles_step` reads the handing word in the same reserve step (both take step 5).
- **Unasked change — `IoApic.segment` (`model/src/boot.rs:68-74`, `model/src/irq.rs:86-94`):** Uses the IOAPIC's DMAR segment rather than hardcoding 0 (`kernel-interface.md:1019`: `"the IOAPIC of a line, whose segment the DMAR gives"`).
- **Unasked change — `#[cfg(test)] System` test helpers (`model/src/system.rs:792-810`):** `node_mut`, `push_action`, and `edit_table` exist under `#[cfg(test)]` only, for bad-state checker and regression scenarios (`scenarios/checker.rs`, `scenarios/mistral.rs`).

## Not checked or could not run

- `kani` (bounded model checker) and Miri/ASan: not available in the local Nix shell (`AGENTS.md` / `dodos-rust`), so Kani harnesses (`abi/src/machine.rs`, `abi/src/ring.rs`) were reviewed by code inspection rather than executed with `cargo kani`.
