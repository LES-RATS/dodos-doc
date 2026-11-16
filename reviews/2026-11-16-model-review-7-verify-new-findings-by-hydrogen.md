# Review 7: verification of new findings, verifier disagreements, and F2, by gemini-hydrogen

Reports verified:
- [`2026-11-16-model-review-7-verify-hydrogen-by-opus.md`](/Users/btw/Documents/repos/Docs/reviews/2026-11-16-model-review-7-verify-hydrogen-by-opus.md) (Opus N1–N4; F3(1), F4(2), F9, F10)
- [`2026-11-16-model-review-7-verify-hydrogen-by-deepseek.md`](/Users/btw/Documents/repos/Docs/reviews/2026-11-16-model-review-7-verify-hydrogen-by-deepseek.md) (DeepSeek N1; F3(1), F4(2), F9, F10)
- [`2026-11-16-model-review-7-gemini-hydrogen.md`](/Users/btw/Documents/repos/Docs/reviews/2026-11-16-model-review-7-gemini-hydrogen.md) (F2, F3(1), F4(2), F9, F10)

Contract: `Docs/architecture/kernel-interface.md` at Docs commit `3bc7597`.
Model: `dodos-kernel`, branch `model`, commit `2afc901`.

## What I did

- Built a clean copy of `dodos-kernel` (`2afc901`) with per-ordered-pair ring delivery enforced in `System::deliver` (`overtaking in the ring {from} -> {to}`), and `Model::needed` exposed as `pub(crate)` for unit testing (`ring_order_and_unit_include.patch`).
- Re-ran the entire `dodos-model` test suite with ring order enforced (`--no-fail-fast`) to verify Opus N3 directly.
- Copied and ran both verifiers' tests covering F3(1), F4(2), F9, and F10 with ring order enforced.
- Wrote and executed an independent test suite from the contract: 10 integration tests (`model/tests/verify_new_hydrogen.rs`) and 4 unit tests (`model/src/verify_new_hydrogen_unit.rs`), all run and passing under default (`4k`), `DODOS_PAGE=16k`, and `DODOS_PAGE=32k`.
- Files delivered in `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/review7/tests/verify-new-hydrogen/`: `verify_new_hydrogen.rs`, `verify_new_hydrogen_unit.rs`, `ring_order_and_unit_include.patch`, `README.md`.

"Side" says where the fault is: `contract`, `model`, or `tests`.

## Verdicts

| Finding | Verdict | Side | Severity | How you know |
|---|---|---|---|---|
| Opus N1: `iospace` detach whose thread is destroyed leaves IOMMU context entry | CONFIRMED | model | breaks isolation between nodes | Unit `n1_opus_detach_whose_thread_is_destroyed_leaves_unit_context_entry`; `memory.rs:480-481`, `ipc.rs:709` |
| Opus N2: late `Body::Move` onto reused grant of another kind panics | CONFIRMED | model | panic of the model | `n2_opus_stale_move_onto_reused_grant_of_another_kind_panics` (`moves.rs:165`) |
| Opus N3: three repo tests deliver out of ring order | CONFIRMED | tests | wording (broken test suite invariant) | Full `dodos-model` run (`--no-fail-fast`): exact 3 failures in `nodes.rs:643,1048` & `recovery.rs:971`, all rest pass |
| Opus N4: `core_start` mode 1 contradicts lines 1032/1173 vs 1194 | CONFIRMED | contract | wording | `n4_opus_cohosted_resume_succeeds_on_unparked_core_against_line_1173`; read contract 1032, 1173 vs 1090, 1194 |
| DeepSeek N1: `ReplyRecv` & `SchedConfigure` panic on remote cap | CONFIRMED | model | panic of the model | `n1_ds_reply_recv_and_sched_configure_remote_panic` (`ipc.rs:423`, `sched.rs:577`) |
| F3(1): `Body::Move` without serial (Opus vs DeepSeek) | CONFIRMED (Opus right, DeepSeek wrong) | model | wrong result | `f3_part1_stale_move_overwrites_reused_thread_in_ring_order` & Opus `f3_stale_move_lands_in_a_thread_granted_after_its_destination_was_revoked` |
| F4(2): co-hosted `CORE_START_RESUME` / `save_seal` / `Host` kill (Opus vs DeepSeek) | NOT REPRODUCED as claimed against `save_seal`; line 1173 breach is Opus N4 (Opus right on `save_seal`, DeepSeek wrong on cause of `Host`) | model / contract (N4) | wording (N4); not a `save_seal` fault | Unit `f4_part2_unit_save_seal_is_set_and_node2_dies_only_because_of_unit_roles` & `f4_part2_cohosted_resume_on_no_role_core_seals_cleanly` |
| F9: `thread_resume` during `thread_move`, missing freezes (Opus vs DeepSeek) | CONFIRMED IN PART (DeepSeek closer on Clause A; freezes NOT A FAULT; Opus wrong to omit Clause A contradiction) | contract | wording | `f9_resume_and_task_ops_during_move` + both verifiers' `f9` tests; read contract 669, 675 |
| F10: late `Handed`, rate limit, `core_start` module, `needed()` (Opus vs DeepSeek) | CONFIRMED IN PART: (1)(2)(3a) NOT A FAULT / wording; (3b) `needed()` CONFIRMED (Opus right, DeepSeek wrong) | model (3b); contract wording (1) | wording; slower detection (3b) | `f10_late_handed_and_rate_limit_and_core_start_modules` + unit `f10_unit_needed_skips_non_call_requests_against_line_1069` |
| F2: `core_place` + `core_stop` / fence hitting wrong core | CONFIRMED IN PART: contract window lets fence/retire hit wrong core; model moves immediately (retire NOT A FAULT against line 1090) | contract | breaks isolation between nodes (contract window); wording (retire) | Read contract 1052–1053, 1077, 1089–1090, 1182, 1186, 1194; run `f2_core_place_and_retire_on_parked_core_model_behavior` |
| New N1-S1 (sibling of Opus N1): `UnitOp::Attach` whose thread is destroyed leaves no context entry | CONFIRMED | model | wrong result | Unit `n1_opus_sibling_attach_whose_thread_is_destroyed_leaves_no_unit_context_entry` (`memory.rs:527`, `ipc.rs:709`) |
| New N2-S1 (sibling of Opus N2): stale `Body::Move` onto reused `Sched` grant panics | CONFIRMED | model | panic of the model | `n2_opus_sibling_stale_move_onto_reused_sched_grant_of_another_kind_panics` (`moves.rs:183`) |
| New DS-N1-S1 (siblings of DeepSeek N1): 7 more calls omitted from `capability_arguments()` | CONFIRMED | model | panic of the model | `n1_ds_siblings_omitted_from_capability_arguments_panic` (`remote.rs:246-270`) |

Counts across the 10 verified items + 3 new sibling findings (13 rows): `CONFIRMED`: 8 (5 asked new findings + 3 new sibling findings), `CONFIRMED IN PART`: 3 (F2, F9, F10), `NOT REPRODUCED`: 1 (F4(2) `save_seal == false`), plus F3(1) `CONFIRMED` (`CONFIRMED` total 9 if F3(1) is counted separately from sibling rows — 6 of 10 primary items `CONFIRMED`, 3 `CONFIRMED IN PART`, 1 `NOT REPRODUCED`, and 3 `CONFIRMED` new siblings).

---

## Part (a): Unverified new findings

### Opus N1: `iospace` detach whose thread is destroyed leaves IOMMU context entry

- **Verdict:** `CONFIRMED` | **Side:** `model` | **Severity:** `breaks isolation between nodes`
- **Model & contract:** `memory.rs:478-482` calls `self.detach_local(iommu, device)` and then `self.unit_request(Some(thread), unit, UnitOp::Detach(device))`. When the unit role is `Handing`, `roles.rs:239` parks the request on the caller without sending it. If the calling thread is destroyed (`CapDelete`) before the hand-over finishes, `unlink` (`ipc.rs:707-710`) falls into the catch-all arm (`self.cancel_remote(id); self.requests.remove(&id);`), deleting `Request::Unit`. Line 854 requires a request holding no wait on a peer to complete without the thread.
- **Test (`verify_new_hydrogen_unit::n1_opus_detach_whose_thread_is_destroyed_leaves_unit_context_entry`):**
  - Attaches devices `0x10` and `0x11` on node 0 (`units[&0].entries` records `(0, gen)` for both).
  - Node 1 starts `RoleHand` to node 2 (`RoleState::Handing`).
  - Threads `detacher` (`0x10`) and `keeper` (`0x11`) call `IoSpaceAttach(..., SlotAddr::NONE, dev)` (`WAITS`); both are removed from `reports[0]`.
  - Destroys `detacher` (`CapDelete`), settles & runs `recover`, then settles retries.
  - **Asserts:** `keeper` wakes with `DONE` and `units[&0].entries.get(&0x11) == None`, whereas after `CapDelete` of the `IoSpace` itself, `sys.check() == Ok(())`, `reports[0].is_empty()`, and `units[&0].entries.get(&0x10) == Some(&(0, gen))` still remains programmed on the IOMMU unit.

### Opus N2: late `Body::Move` onto reused grant of another kind panics

- **Verdict:** `CONFIRMED` | **Side:** `model` | **Severity:** `panic of the model`
- **Model:** `place_move` (`moves.rs:165`) unconditionally indexes `self.threads[&target]` without checking `ObjectKind` or serial, because `Body::Move` carries only grant indices and `misdirected` (`remote.rs:640`) checks only grantee + generation.
- **Test (`verify_new_hydrogen::n2_opus_stale_move_onto_reused_grant_of_another_kind_panics`):**
  - Node 0 grants `Thread` (grant 0) and `Sched` (grant 1) to node 1; sends a `Notify` so `TransferAsk` queues on ring `1 -> 0`.
  - Node 1 queues `Body::Move` behind `TransferAsk` on ring `1 -> 0` (ring order preserved).
  - Node 0 synchronously `CapRevoke`s grant 0 (unmapped `Thread` -> freed immediately, no message), delivers `TransferAsk` (reuses grant 0 for `Notify`, serial 1), then delivers `Body::Move`.
  - **Asserts:** `catch_unwind` catches panic at `moves.rs:165` (`no entry found for key`).

### Opus N3: three repository tests deliver out of ring order

- **Verdict:** `CONFIRMED` | **Side:** `tests` | **Severity:** `wording` (test suite breaks its own ring-order rule)
- **How known:** Ran full `cargo test -p dodos-model --no-fail-fast` with `ring_order.patch` (`System::deliver` panicking when an older packet with the same `(from, to)` is in flight). Every unit and integration test passed except these exact three tests, all panicking at `system.rs:169` (`overtaking in the ring 1 -> 0`):
  1. `nodes::revoking_a_mapped_grant_waits_for_the_holder_then_returns_again` (`model/tests/nodes.rs:643-657`): line 653 delivers `Body::RevokeStep { done: true, .. }` before the `Body::Release` queued earlier on ring `1 -> 0` when node 1 removed its root capability.
  2. `nodes::a_stale_remote_capability_sent_home_is_dropped` (`model/tests/nodes.rs:1048-1079`): line 1073 deliberately skips `Body::TransferGrant([Crossing::Home])` while delivering a later message on ring `1 -> 0`.
  3. `recovery::a_holder_refuses_a_request_of_another_epoch_even_when_it_holds_the_role_again` (`model/tests/recovery.rs:971-1010`): holds `Body::UnitRequest` on ring `1 -> 0` while delivering `Body::Handed` on ring `1 -> 0` ahead of it.

### Opus N4: `core_start` mode 1 contradicts transition table lines 1032/1173 vs 1194

- **Verdict:** `CONFIRMED` | **Side:** `contract` | **Severity:** `wording`
- **Contract quotes:**
  - Line 1032: `sealed (g) | starting (g) | the node that calls core_start mode resume | The core it is placed on is confirmed parked or runs no node`
  - Line 1173: `mode 1: busy if the node is not sealed or its core is not confirmed parked.`
  - Line 1194 (`core_place`): `State, in order: busy if the node is not live or sealed; busy if the core is marked unusable; busy if the core runs a node that is not live ... Effect: the node is bound to that core in the machine table; a live node moves at its next event boundary, by the protocol of parked nodes; a sealed node is resumed there by core_start mode 1.`
  - Line 1090: `A physical core runs the blocks of the nodes placed on it in turn`
- **Contradiction:** Lines 1194 and 1090 explicitly design placing a sealed node onto a physical core actively running a live node and resuming it there with `core_start` mode 1, whereas lines 1032 and 1173 forbid mode 1 unless that core is confirmed parked (or runs no node). The model follows line 1194 (`recovery.rs:151-155` checks `running == Some(node)` rather than requiring the core to be parked).
- **Test (`verify_new_hydrogen::n4_opus_cohosted_resume_succeeds_on_unparked_core_against_line_1173`):**
  - Seals node 1 (`MemberState::Sealed`), calls `CorePlace { core: core(1), physical: 0 }` onto core 0 while live node 0 runs there (`DONE`), then calls `CoreStart { core: core(1), mode: CORE_START_RESUME, .. }`.
  - **Asserts:** `CoreStart` returns `DONE` and both node 0 and node 1 are `MemberState::Live`.

### DeepSeek N1: `ReplyRecv` and `SchedConfigure` panic on another node's capability

- **Verdict:** `CONFIRMED` | **Side:** `model` | **Severity:** `panic of the model`
- **Contract & model:** Line 849 (Rule 7) states *"a call on an object held by another node becomes a message between kernels, and the caller sees the same result, later"*, and line 857 specifies `reply_recv` on a remote endpoint. `remote.rs:246-270` (`capability_arguments`) uses a hand-written `match` that omits `Syscall::ReplyRecv` and `Syscall::SchedConfigure`, so both run locally on the caller's tables and panic at `ipc.rs:423` (`self.endpoints[&endpoint]`) and `sched.rs:577` (`self.scheds[&context]`). Note that for `SchedConfigure` to reach line 577, `core` must name the caller's own core (pass `self.own_core` at `sched.rs:560`), where Rule 7 line 851 would reject a caller's own `core` capability if forwarded — either way it must not panic.
- **Test (`verify_new_hydrogen::n1_ds_reply_recv_and_sched_configure_remote_panic`):**
  - Grants an `Endpoint` and a `Sched` from node 1 to node 0.
  - Node 0 calls `ReplyRecv` on the remote endpoint and `SchedConfigure` on the remote `sched` (with `core(0)`).
  - **Asserts:** Both calls panic (`ipc.rs:423` and `sched.rs:577`).

---

## Part (b): Disagreements between verifiers

### F3 part 1: `Body::Move` without a serial

- **Verdict:** `CONFIRMED` | **Who is right:** **Opus is right; DeepSeek is wrong.** | **Side:** `model` | **Severity:** `wrong result`
- **Why:** Running Opus's `f3_stale_move_lands_in_a_thread_granted_after_its_destination_was_revoked` and DeepSeek's reasoning shows why DeepSeek missed it. DeepSeek (`IMPOSSIBLE SCENARIO`) checked only Hydrogen's `f5a` route (having node 1 release before its own `Move` on `1 -> 0`) and concluded no legal order exists. Opus found a 100% ring-order legal route: node 0 revokes grant 0 (`D1`, unmapped `Thread`) *synchronously* on node 0 with no message, *after* node 1 queued `Body::Move` behind a `TransferAsk` on ring `1 -> 0`. `TransferAsk` arrives first, reuses grant 0 for a new thread `D2` granted to node 1, and `Body::Move` then overwrites `D2` (`place_move`, `moves.rs:155-215`).
- **Own test (`verify_new_hydrogen::f3_part1_stale_move_overwrites_reused_thread_in_ring_order`):**
  - Queues `TransferAsk` before `Body::Move` (`RAX = 0x1337`, `SchedSetCores` mask `0b11`) on ring `1 -> 0`, revokes `D1` on node 0 (`CapRevoke` -> `DONE`), delivers `TransferAsk` (reuses grant 0 for fresh `D2`), then delivers `Body::Move`.
  - **Asserts:** `mover` wakes with `DONE` and `ThreadReadRegs` on `D2` returns `RAX == 0x1337`.

### F4 part 2: co-hosted `CORE_START_RESUME` and `save_seal` / `Host` kill

- **Verdict:** `NOT REPRODUCED` as claimed against `save_seal == false` (the separate model violation of line 1173 is **Opus N4**) | **Who is right:** **Opus is right on the `save_seal` mechanism; DeepSeek is right on the literal line 1173 violation (Opus N4) but wrong on why node 2 died with `Host`.**
- **Why:** Both Opus's `f4_kill_after_a_cohosted_resume_seals_the_other_node_not_host` and DeepSeek's `f4b_a_resume_on_a_shared_core_kills_the_node_that_was_never_saved` pass under ring order. DeepSeek observed node 2 die with `Evidence::Host` on core 2 (`started(3)`) and claimed *"nothing seals node 2, whose block is now gone"*. In fact, `load_block` (`recovery.rs:94-103`, invoked when `core_start(RESUME)` calls `started` -> `begin`) **does** set `beacons[previous_runner].save_seal = true`. In `Machine::example()`, cores 1 and 2 have `fence = 2` (core 0 has `fence = 1`), so node 2 holds unit role 1; `named == true` at `recovery.rs:791-793` forces `Evidence::Host` per contract line 1089 (*"A Z that a unit role names is accused"*), not a missing `save_seal`.
- **Own tests:**
  - **Unit (`verify_new_hydrogen_unit::f4_part2_unit_save_seal_is_set_and_node2_dies_only_because_of_unit_roles`):** Places sealed node 1 on core 2, calls `CoreStart(CORE_START_RESUME)` (`DONE`), **asserts `sys.table().beacons[2].save_seal == true`** directly before `CoreStop(KILL)`, then shows node 2 dies with `Evidence::Host`.
  - **Integration (`verify_new_hydrogen::f4_part2_cohosted_resume_on_no_role_core_seals_cleanly`):** Places sealed node 1 on core 0 (node 0 holds no unit role), resumes node 1 (`DONE`), then kills node 1 from node 2. **Asserts:** node 0 cleanly becomes `MemberState::Sealed` with `Evidence::None`.

### F9: `thread_resume` during `thread_move` and missing freezes

- **Verdict:** `CONFIRMED IN PART` (`contract`, `wording`; missing freezes `NOT A FAULT`) | **Who is right:** **DeepSeek is closer on Clause A; Opus is wrong to call the whole finding `NOT A FAULT`.**
- **Contract (line 675):** Two sentences in line 675 flatly contradict each other:
  - Sentence 3 (Clause A): *"`thread_resume` clears its suspension but not its wait, so it runs only after the answer, and only if the move was refused."*
  - Sentence 6 (Clause B): *"At that answer the thread's wait ends; the thread keeps its bindings, stays suspended (unless `thread_resume` cleared it meanwhile), and its own context is unbound, made not configured and its bandwidth taken out of the source's sum, so it cannot run; its registers are set as for a new thread"*
  - Both Opus's `f9_resume_during_a_successful_move_is_what_the_contract_says` and DeepSeek's `f9_a_resume_during_a_move_leaves_the_moved_thread_runnable` pass: `moved` (`moves.rs:236-245`) follows Sentence 6 (`!suspended`, `wait == Wait::None`, `home == None`), so `Model::runnable()` includes `source`. Opus claims `runnable()` is merely a test helper for threads that have no context; however, `Model::apply(source, Syscall::Yield)` also executes cleanly (`DONE`). Sentence 3 is wrong under the model's behaviour and must be reconciled with Sentence 6.
  - On the "missing freezes": `sched_count` (`No state error`, line 669) and `task_attach`/`task_revoke` are absent from line 675's explicit four-call freeze list (`sched_configure`, `sched_set_cores`, `sched_bind`, `sched_unbind`), so the model matches the list (`NOT A FAULT`), though `task_attach`/`task_revoke` create a wording tension with *"from the sending of its state to the answer, nothing changes it on the source"*.
- **Own test (`verify_new_hydrogen::f9_resume_and_task_ops_during_move`):**
  - Starts `ThreadMove` on suspended `src` (with `SchedSetCores` mask `0b11`) and while `Body::Move` is in flight executes `ThreadResume`, `SchedCount`, `TaskAttach`, and `TaskRevoke` (followed by `ThreadResume`), then settles.
  - **Asserts:** All four calls succeed (`DONE`) mid-move, post-move `SchedRead` clears `SCHED_STATE_CONFIGURED`, `sys.node(0).runnable().contains(&src)`, and `sys.apply(0, src, Syscall::Yield)` returns `DONE`.

### F10: late `Handed` trace, shared rate limit, `core_start`, and `needed()`

- **Verdict:** `CONFIRMED IN PART` — `(1)`, `(2)`, `(3a)` `NOT A FAULT` / contract `wording` or model module-list gap; `(3b)` `CONFIRMED` (`model`, slower detection) | **Who is right:** **Opus is right; DeepSeek is wrong to give `NOT A FAULT` while ignoring (3b).**
- **Contract & model:**
  - `(1)` Line 855 explicitly specifies code 11 tracing for a `Handed` message failing its handing-word check (`f10_a_late_handed_message...` and `f10_a_late_step_four_message...` both pass).
  - `(2)` Line 1295 explicitly states *"Windows are counted per node"* (16 entries per code/node).
  - `(3a)` Line 1172 checks `module < segments.len()` and first-service flag; in the model `Machine::segments` are the first service's segments and `files` follow them (`recovery.rs:124` has no general module table), so `module >= segments.len()` already returns `Err(Invalid)`.
  - `(3b)` **Model bug (`recovery.rs:465-473`):** Contract line 1069 states *"A thread that waits for X (a call to an object of X, an acknowledgement of a core group, a request to a role X holds) makes its kernel observe X"*. Yet `Model::needed()` only matches `Request::Call { peer, .. }` (`_ => None`), omitting `Request::Unit`, `Request::Move`, `Request::Carry`, `Request::Transfer`, and `Request::Revoke`. Thus a node waiting on a non-successor peer via `ThreadMove` or `UnitOp` does not observe it until `SWEEP_NS`.
- **Own tests:**
  - **Integration (`verify_new_hydrogen::f10_late_handed_and_rate_limit_and_core_start_modules`):** Confirms `(1)` late `Body::Handed` adds 1 Code 11 entry, `(2)` 17 refused releases from node 1 + 1 from node 2 share node 0's single window (`16` entries, `suppressed == 2`), and `(3a)` `CoreStart(CORE_START_FRESH)` with `module = segments.len()` returns `Err(Error::Invalid)`.
  - **Unit (`verify_new_hydrogen_unit::f10_unit_needed_skips_non_call_requests_against_line_1069`):** On a 4-node machine (node 0's cyclic successors are 1 and 2, **not 3**), advances past the initial `t=0` sweep (`next_sweep >= 100ms`), issues `ThreadMove` targeting node 3, and hangs node 3. **Asserts:** `!sys.node(0).needed().contains(&3)` and node 0 keeps node 3 `MemberState::Live` at `45ms` (`> 4 * stale_ms`), whereas the control using `Request::Call` (`Wait` on node 3's `Notify`) includes `3` in `needed()` and fences node 3 to `MemberState::Dead` by `45ms`.

---

## Part (c): F2 — `core_place`, `core_stop`, and the fence

- **Verdict:** `CONFIRMED IN PART` | **Side:** `contract` (fence target in the `core_place` window) | **Severity:** `breaks isolation between nodes` (in the contract; `NOT A FAULT` / `wording` in the model)

### Exact contract lines

- **Line 1052–1053** (`Beacons`):
  > "**A core beacon** is one page per physical core, written only by that core: ... `running`, the index of the node whose block it runs (0xFFFF while it switches between parked nodes); ... **A node beacon**, written only by the kernel that runs that node: ... `save_seal`, written last when a parked node is saved and cleared first when it is loaded (a node whose seal is valid was not running)"
- **Line 1077** (`The fence`):
  > "Let *p* be the physical core that runs *X*."
- **Line 1089–1090**:
  > "**After a confirmed stop**, for every node *Z* placed on *p* other than *X* that is not dead or fenced ... A *Z* that a unit role names is accused ... **Several nodes on one physical core (D-108).** `core_stop` acts on a node, never on a core ... So when *X* is not the node *p* runs (the core beacon's `running` is not *X*) and *X*'s save seal is valid, *X* cannot execute: its stop is **confirmed** at once by those two words, *X* becomes fenced, and *p* is not stopped. Only when *X* runs on *p*, or its seal is not valid, is *p* itself stopped, by the steps above, and the other nodes placed on *p* are sealed or accused by the rule after a confirmed stop."
- **Line 1182** (`core_stop`):
  > "Mode 2 also marks the physical core that runs the node as unusable until the machine restarts."
- **Line 1186** (`core_status`):
  > "Words of the result: ... 1 the physical core the node is placed on"
- **Line 1194** (`core_place`):
  > "Effect: the node is bound to that core in the machine table; a live node moves at its next event boundary, by the protocol of parked nodes; a sealed node is resumed there by `core_start` mode 1."

### Does the contract as written let `core_stop` or a fence reach the wrong physical core?

**Yes.**

1. **Wrong fence target (`core_stop` mode 0/2 or stale/stuck/self fence):** Line 1194 immediately rewrites *X*'s placement in the machine table to the new physical core *q* while a live *X* continues executing on its old physical core *p* until *X*'s next event boundary. Neither the machine table nor *X*'s node beacon has a `running_core` field publishing *p*, and line 1186 exposes only placement. A fence driver reading *p* from *X*'s placement looks at *q* instead of *p*:
   - If *X* is still executing on *p* (so *X*'s `save_seal` is cleared / invalid), line 1090 says that when *X*'s `save_seal` is not valid, the driver stops *q* itself (`NMI`/`INIT`/`SIPI` or `SDEI`/`fence_hart`), stopping *q* and accusing/sealing innocent nodes running on *q* (`Evidence::Host` if holding a unit role) while ***p* (running *X*) is never stopped** — breaking isolation and leaving *X* running past its fencing transition.
   - Even if *q* is idle, stopping *q* confirms *q* parked and leaves *X* still executing on *p*.
2. **Wrong retired core (`core_stop` mode 2):** Line 1182 says mode 2 *"marks the physical core that runs the node as unusable"*. Without a separate `running_core`, reading placement during the window of line 1194 retires *q* instead of *p*. (And for a sealed node, which runs on no physical core, line 1182's *"physical core that runs the node"* is a wording ambiguity — `f2_core_place_and_retire_on_parked_core_model_behavior` confirms the model retires `placed[node]` while node 2 keeps running on core 2.)
3. **Why the model does not show the isolation breach itself (`NOT A FAULT` in model):** In the model (`recovery.rs:401`), `core_place` updates `self.table.placed[node]` and `System` immediately executes `node` on its new core with no inter-event execution window (`f2_core_place_and_retire_on_parked_core_model_behavior`). Thus `p == q` holds instantaneously in the model, masking the contract defect.

### Smallest rule that closes it

1. Add `running_core` to each node's beacon (or shared table, written by the core's scheduler/switch path alongside `save_seal`): set to `p` while core `p` loads *X*'s block (before clearing `save_seal`), and set to `NONE` (`0xFFFF`) when *X* is saved and `save_seal` is set.
2. In `core_place(X, q)` (line 1194) on a live *X*, after binding `placed[X] = q`, read `running_core[X]`; if it names an old core `p != q`, send an IPI to `p` so *X* hits its event boundary and parks off `p`.
3. Define *"the physical core that runs X"* in lines 1077, 1089, 1090, and 1182 as: `running_core[X]` if it is not `NONE`, and `placed[X]` only when `running_core[X] == NONE` (so `core_stop` mode 2 on a sealed node cleanly marks `placed[X]` unusable, and a live *X* still running on `p` is fenced and retired on `p`).

---

## New sibling findings (discovered next to confirmed findings)

### N1-S1 (next to Opus N1): `UnitOp::Attach` whose thread is destroyed leaves no unit context entry

- **Verdict:** `CONFIRMED` | **Side:** `model` | **Severity:** `wrong result`
- **Model:** `memory.rs:518-527` records `table.identifiers` and `table.reports[node]` locally *before* calling `unit_request(Some(thread), unit, UnitOp::Attach(device))`. When the unit role is `Handing`, destroying the calling thread deletes `Request::Unit` via `ipc.rs:709`.
- **Unit test (`verify_new_hydrogen_unit::n1_opus_sibling_attach_whose_thread_is_destroyed_leaves_no_unit_context_entry`):** Destroys `attacher` while role 0 is `Handing` (`0x20`). After hand-over finishes (`role(0).holder() == 2`), **asserts** `sys.check() == Ok(())`, `reports[0].contains(&(0, 0x20))`, yet `units[&0].entries.get(&0x20) == None`.

### N2-S1 (next to Opus N2): stale `Body::Move` onto reused `Sched` grant of another kind panics

- **Verdict:** `CONFIRMED` | **Side:** `model` | **Severity:** `panic of the model`
- **Model:** Even when grant 0 (`Thread`) is untouched so `moves.rs:165` succeeds, reusing grant 1 (`Sched`) for a `Notify` passes `self.threads[&target]` (`165`) and panics at `moves.rs:183` (`self.scheds[&context]`).
- **Integration test (`verify_new_hydrogen::n2_opus_sibling_stale_move_onto_reused_sched_grant_of_another_kind_panics`):** Same ring-order setup as N2, revoking grant 1 (`Sched`) instead of grant 0 (`Thread`) and configuring `SchedSetCores` mask `0b11` so `moves.rs:180` passes. **Asserts:** panic at `moves.rs:183`.

### DS-N1-S1 (next to DeepSeek N1): 7 more syscalls omitted from `capability_arguments()`

- **Verdict:** `CONFIRMED` | **Side:** `model` | **Severity:** `panic of the model`
- **Model:** Auditing all `Syscall` arms in `lib.rs` against `capability_arguments()` (`remote.rs:246-270`) finds 7 additional object-mutating syscalls omitted from the list (plus secondary remote arguments on two local-primary calls):
  - `SchedSetCores` on remote `Sched` -> panics at `lib.rs:1042` (from `sched.rs:668`)
  - `SchedCount` on remote `Sched` -> panics at `lib.rs:1042` (from `sched.rs:716`)
  - `ThreadConfigure` on remote `Thread` -> panics at `threads.rs:43`; and on local `Thread` with remote `CSpace` -> panics at `lib.rs:1042` (from `threads.rs:190`)
  - `ThreadSetFeatures` on remote `Thread` -> panics at `threads.rs:169`
  - `TaskExempt` on remote `Task` -> panics at `lib.rs:1042` (from `tasks.rs:112`); and on local `Task` with remote `aware` -> panics at `tasks.rs:109`
  - `ASpaceMap` on remote `ASpace` -> panics at `memory.rs:211` (shared by `IoSpaceMap`)
  - `IoSpaceAttach` on remote `IoSpace` -> panics at `memory.rs:500`
  - `CSpaceGrow` on remote `CSpace` + local `Untyped` -> fails locally with `Err(Invalid)` (`caps.rs:345`) instead of forwarding via `remote.rs:246`
- **Integration test (`verify_new_hydrogen::n1_ds_siblings_omitted_from_capability_arguments_panic`):** Exercises every one of the 7 calls and secondary remote-argument combinations above and **asserts** each panic (and `Err(Invalid)` for `CSpaceGrow`).

---

## Appendix A: `model/tests/verify_new_hydrogen.rs`

```rust
//! Independent verification of Review 7 new findings and verifier disagreements.
//!
//! Written from the contract (`Docs/architecture/kernel-interface.md`, commit `3bc7597`)
//! and the reference model (`2afc901`) with ring order enforced in `System::deliver`.

use dodos_abi::ObjectKind::{
    ASpace, CSpace, Endpoint, Frame, IoSpace, Notify, Reply, Sched, Task, Thread,
};
use dodos_abi::x86_64::{REG_RAX, REGS_WORDS};
use dodos_abi::*;
use dodos_model::*;
use std::panic::{AssertUnwindSafe, catch_unwind};

const DONE: Outcome = Ok(Output::Done);
const WAITS: Outcome = Ok(Output::Waits);
const UT: SlotAddr = SlotAddr::own(25);
const MAILBOX: SlotAddr = SlotAddr::own(START_SLOT_MAILBOX);
const ASPACE: SlotAddr = SlotAddr::own(START_SLOT_ASPACE);
const MS: u64 = 1_000_000;
const IOMMU_CAP: u32 = 18;
const NO_EXEC: Rights = Rights::ALL.without(Rights::EXEC);

const fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

const fn core(n: u32) -> SlotAddr {
    SlotAddr::own(START_SLOT_FIRST + n)
}

fn retype(kind: ObjectKind, size: u64, dest: u32) -> Syscall {
    Syscall::UntypedRetype {
        untyped: UT,
        kind,
        size,
        page: PageSize::Page as u64,
        memory: 0,
        destination: s(dest),
    }
}

fn retype_done(sys: &mut System, node: u16, caller: ObjId, kind: ObjectKind, size: u64, dest: u32) {
    loop {
        match sys.apply(node, caller, retype(kind, size, dest)) {
            Ok(Output::Done) => break,
            Err(Error::Again) => continue,
            other => panic!("unexpected retype outcome: {other:?}"),
        }
    }
}

fn msg(caps: Vec<Transfer>) -> Message {
    Message {
        label: 7,
        flags: 0,
        words: vec![7],
        caps,
        marks: 0,
    }
}

fn recv_into(first: u32, count: u32) -> Syscall {
    Syscall::Recv {
        endpoint: MAILBOX,
        reply: s(99),
        range: Range {
            first: s(first),
            count,
        },
        wait: 0,
    }
}

fn send_to(to: u32, caps: Vec<Transfer>) -> Syscall {
    Syscall::Send {
        target: core(to),
        message: msg(caps),
    }
}

fn machine_n(nodes: usize) -> Machine {
    let mut machine = Machine::example();
    while machine.cores.len() < nodes {
        let mut extra = machine.cores[1];
        extra.hw_id = 2 * machine.cores.len() as u64;
        machine.cores.push(extra);
    }
    machine.membership.stale_ms = 10;
    machine.membership.stuck_ms = 10;
    machine.membership.sweep_ms = 100;
    machine
}

fn boot_n(nodes: usize) -> (System, Vec<ObjId>) {
    let (mut sys, t) = System::boot(&machine_n(nodes)).unwrap();
    for node in 0..nodes as u16 {
        let sched = Syscall::SchedConfigure {
            sched: s(START_SLOT_SCHED),
            core: core(node.into()),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        };
        assert_eq!(sys.apply(node, t[node as usize], sched), DONE);
        assert_eq!(sys.apply(node, t[node as usize], retype(Reply, 0, 99)), DONE);
    }
    (sys, t)
}

fn spawn_thread(sys: &mut System, t: &[ObjId], node: u16, slot: u32, spare: u32) -> ObjId {
    let root = t[node as usize];
    for call in [
        retype(Thread, 0, slot),
        retype(Frame, 1, spare),
        Syscall::ThreadConfigure {
            thread: s(slot),
            cspace: s(START_SLOT_CSPACE),
            aspace: ASPACE,
            fault: SlotAddr::NONE,
            page: s(spare),
        },
        retype(Sched, 0, spare - 1),
        Syscall::SchedConfigure {
            sched: s(spare - 1),
            core: core(node.into()),
            budget: 500_000,
            period: 10_000_000,
            class: 1,
        },
        Syscall::SchedSetCores {
            sched: s(spare - 1),
            core: core(node.into()),
            window: 0,
            mask: 0b11,
        },
        Syscall::SchedBind {
            sched: s(spare - 1),
            thread: s(slot),
        },
        Syscall::ThreadResume(s(slot)),
    ] {
        assert_eq!(sys.apply(node, root, call), DONE);
    }
    sys.node(node).object_at(root, s(slot)).unwrap()
}

fn grant_one(
    sys: &mut System,
    t: &[ObjId],
    from: u16,
    to: u16,
    src_slot: u32,
    dst_slot: u32,
    rights: Rights,
) {
    assert_eq!(sys.apply(to, t[to as usize], recv_into(dst_slot, 1)), WAITS);
    assert_eq!(
        sys.apply(
            from,
            t[from as usize],
            send_to(to.into(), vec![Transfer::Derive(s(src_slot), rights.bits())])
        ),
        WAITS
    );
    sys.settle(32);
    assert_eq!(sys.check(), Ok(()));
}

fn deliver_first(sys: &mut System, pred: impl Fn(&Body) -> bool) {
    let idx = sys.find(pred).expect("matching packet in flight");
    sys.deliver(idx);
}

// =========================================================================
// (a) Opus N2 (+ sibling moves.rs:183): Body::Move onto reused grant kind
// =========================================================================

#[test]
fn n2_opus_stale_move_onto_reused_grant_of_another_kind_panics() {
    let (mut sys, t) = boot_n(2);
    let ask_sender = spawn_thread(&mut sys, &t, 0, 200, 3000);
    let mover = spawn_thread(&mut sys, &t, 1, 200, 3000);
    let recv1 = spawn_thread(&mut sys, &t, 1, 202, 2994);

    // Grant 0: Thread on node 0; Grant 1: Sched on node 0.
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 100)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 101)), DONE);
    grant_one(&mut sys, &t, 0, 1, 100, 110, NO_EXEC);
    grant_one(&mut sys, &t, 0, 1, 101, 111, NO_EXEC);
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 0)));
    assert_eq!(sys.node(0).grant_entry(1).map(|e| (e.0, e.2)), Some((1, 0)));

    // Pre-existing Notify in slot 120 on node 0; send it so TransferAsk queues on ring 1 -> 0.
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 120)), DONE);
    assert_eq!(sys.apply(1, recv1, recv_into(130, 1)), WAITS);
    assert_eq!(
        sys.apply(
            0,
            ask_sender,
            send_to(1, vec![Transfer::Derive(s(120), NO_EXEC.bits())])
        ),
        WAITS
    );
    deliver_first(&mut sys, |b| matches!(b, Body::Request { .. }));
    assert!(sys.find(|b| matches!(b, Body::TransferAsk { .. })).is_some());

    // Now node 1 queues Body::Move { thread: 0, sched: 1 } BEHIND TransferAsk on ring 1 -> 0.
    let _src = spawn_thread(&mut sys, &t, 1, 201, 2997);
    assert_eq!(sys.apply(1, t[1], Syscall::ThreadSuspend(s(201))), DONE);
    assert_eq!(
        sys.apply(
            1,
            mover,
            Syscall::ThreadMove {
                thread: s(201),
                destination: s(110),
                sched: s(111),
                core: core(0),
                budget: 0,
                period: 0,
                class: 0,
            }
        ),
        WAITS
    );

    // Node 0 synchronously revokes grant 0 (Thread has no mappings -> freed at once).
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(100))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);

    // Deliver TransferAsk (in ring 1 -> 0 order!): reuses grant 0 for Notify (serial 1).
    deliver_first(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 1)));

    // Deliver Body::Move next on ring 1 -> 0: place_move indexes self.threads[&notify] -> panic!
    let res = catch_unwind(AssertUnwindSafe(|| {
        deliver_first(&mut sys, |b| matches!(b, Body::Move { .. }));
    }));
    assert!(res.is_err(), "stale Move onto Notify grant must panic at moves.rs:165");
}

#[test]
fn n2_opus_sibling_stale_move_onto_reused_sched_grant_of_another_kind_panics() {
    let (mut sys, t) = boot_n(2);
    let ask_sender = spawn_thread(&mut sys, &t, 0, 200, 3000);
    let mover = spawn_thread(&mut sys, &t, 1, 200, 3000);
    let recv1 = spawn_thread(&mut sys, &t, 1, 202, 2994);

    // Grant 0: Thread on node 0; Grant 1: Sched on node 0.
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 100)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 101)), DONE);
    grant_one(&mut sys, &t, 0, 1, 100, 110, NO_EXEC);
    grant_one(&mut sys, &t, 0, 1, 101, 111, NO_EXEC);

    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 120)), DONE);
    assert_eq!(sys.apply(1, recv1, recv_into(130, 1)), WAITS);
    assert_eq!(
        sys.apply(
            0,
            ask_sender,
            send_to(1, vec![Transfer::Derive(s(120), NO_EXEC.bits())])
        ),
        WAITS
    );
    deliver_first(&mut sys, |b| matches!(b, Body::Request { .. }));

    // Source thread must have mask=0 and core 0 in its cores set so place_move reaches line 183.
    let _src = spawn_thread(&mut sys, &t, 1, 201, 2997);
    assert_eq!(sys.apply(1, t[1], Syscall::ThreadSuspend(s(201))), DONE);
    assert_eq!(
        sys.apply(
            1,
            mover,
            Syscall::ThreadMove {
                thread: s(201),
                destination: s(110),
                sched: s(111),
                core: core(0),
                budget: 0,
                period: 0,
                class: 0,
            }
        ),
        WAITS
    );

    // Revoke grant 1 (Sched) instead of grant 0 (Thread)!
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(101))), DONE);
    assert_eq!(sys.node(0).grant_entry(1), None);

    // TransferAsk reuses grant 1 for Notify (serial 1).
    deliver_first(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(1).map(|e| (e.0, e.2)), Some((1, 1)));

    // place_move passes self.threads[&target] (165) and panics at self.scheds[&context] (183)!
    let res = catch_unwind(AssertUnwindSafe(|| {
        deliver_first(&mut sys, |b| matches!(b, Body::Move { .. }));
    }));
    assert!(res.is_err(), "stale Move onto reused sched grant must panic at moves.rs:183");
}

// =========================================================================
// (a) Opus N4: core_start(RESUME) succeeds on unparked core running live node
// =========================================================================

#[test]
fn n4_opus_cohosted_resume_succeeds_on_unparked_core_against_line_1173() {
    let (mut sys, t) = boot_n(2);
    assert_eq!(
        sys.apply(1, t[1], Syscall::CoreStop { core: core(1), mode: CORE_STOP_SEAL }),
        DONE
    );
    sys.settle(32);
    sys.recover(16);
    assert_eq!(sys.node(1).member(1).state(), MemberState::Sealed);

    // Place sealed node 1 onto core 0 (actively running live node 0).
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace { core: core(1), physical: 0 }),
        DONE
    );
    // Literal lines 1032 / 1173 say "busy if ... its core is not confirmed parked".
    // Contract lines 1194 / 1090 and model allow resuming onto core 0 running live node 0.
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CoreStart {
                core: core(1),
                mode: CORE_START_RESUME,
                image: CORE_IMAGE_BOOT,
                module: 0,
            }
        ),
        DONE
    );
    assert_eq!(sys.node(0).member(1).state(), MemberState::Live);
    assert_eq!(sys.node(0).member(0).state(), MemberState::Live);
}

// =========================================================================
// (a) DeepSeek N1 + Siblings: calls omitted from capability_arguments()
// =========================================================================

#[test]
fn n1_ds_reply_recv_and_sched_configure_remote_panic() {
    let (mut sys, t) = boot_n(2);
    assert_eq!(sys.apply(1, t[1], retype(Endpoint, 0, 100)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 101)), DONE);
    grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
    grant_one(&mut sys, &t, 1, 0, 101, 111, NO_EXEC);

    let r1 = catch_unwind(AssertUnwindSafe(|| {
        sys.apply(
            0,
            t[0],
            Syscall::ReplyRecv {
                reply: s(99),
                message: msg(vec![]),
                endpoint: s(110),
                range: Range::NONE,
                wait: 0,
            },
        )
    }));
    assert!(r1.is_err(), "ReplyRecv on remote endpoint must panic at ipc.rs:423");

    let r2 = catch_unwind(AssertUnwindSafe(|| {
        sys.apply(
            0,
            t[0],
            Syscall::SchedConfigure {
                sched: s(111),
                core: core(0),
                budget: 500_000,
                period: 10_000_000,
                class: 1,
            },
        )
    }));
    assert!(r2.is_err(), "SchedConfigure on remote sched must panic at sched.rs:577");
}

#[test]
fn n1_ds_siblings_omitted_from_capability_arguments_panic() {
    // 1) SchedSetCores, SchedCount on remote Sched -> panic (sched.rs:668, 716)
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 100)), DONE);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::SchedSetCores {
                    sched: s(110),
                    core: core(0),
                    window: 0,
                    mask: 1,
                },
            )
        }));
        assert!(r.is_err(), "SchedSetCores on remote sched must panic at sched.rs:668");
    }
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 100)), DONE);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::SchedCount {
                    sched: s(110),
                    core: core(0),
                    mode: SCHED_COUNT_ON,
                },
            )
        }));
        assert!(r.is_err(), "SchedCount on remote sched must panic at sched.rs:716");
    }

    // 2) ThreadConfigure, ThreadSetFeatures on remote Thread -> panic (threads.rs:43, 169)
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(1, t[1], retype(Thread, 0, 100)), DONE);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::ThreadConfigure {
                    thread: s(110),
                    cspace: s(START_SLOT_CSPACE),
                    aspace: ASPACE,
                    fault: SlotAddr::NONE,
                    page: SlotAddr::NONE,
                },
            )
        }));
        assert!(r.is_err(), "ThreadConfigure on remote thread must panic at threads.rs:43");
    }
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(1, t[1], retype(Thread, 0, 100)), DONE);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::ThreadSetFeatures {
                    thread: s(110),
                    mask: 0,
                },
            )
        }));
        assert!(r.is_err(), "ThreadSetFeatures on remote thread must panic at threads.rs:169");
    }

    // 3) TaskExempt on remote Task (tasks.rs:112) AND on local Task + remote aware (tasks.rs:109)
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(1, t[1], retype(Task, 0, 100)), DONE);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r1 = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::TaskExempt {
                    task: s(110),
                    aware: s(START_SLOT_TASK),
                },
            )
        }));
        assert!(r1.is_err(), "TaskExempt on remote task must panic at tasks.rs:112");
    }
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(0, t[0], retype(Task, 0, 102)), DONE);
        grant_one(&mut sys, &t, 1, 0, START_SLOT_TASK, 110, NO_EXEC);
        let r2 = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::TaskExempt {
                    task: s(102),
                    aware: s(110),
                },
            )
        }));
        assert!(r2.is_err(), "TaskExempt with remote aware must panic at tasks.rs:109");
    }

    // 4) ASpaceMap on remote ASpace (memory.rs:211)
    {
        let (mut sys, t) = boot_n(2);
        retype_done(&mut sys, 1, t[1], ASpace, 0, 100);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        retype_done(&mut sys, 0, t[0], Frame, 1, 102);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::ASpaceMap(Map {
                    space: s(110),
                    frame: s(102),
                    untyped: SlotAddr::NONE,
                    address: 1 << 30,
                    first: 0,
                    count: 1,
                    rights: Rights::READ.bits(),
                }),
            )
        }));
        assert!(r.is_err(), "ASpaceMap on remote ASpace must panic at memory.rs:211");
    }

    // 5) IoSpaceAttach on remote IoSpace (memory.rs:500)
    {
        let (mut sys, t) = boot_n(2);
        retype_done(&mut sys, 1, t[1], IoSpace, 0, 100);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::IoSpaceAttach {
                    iommu: s(IOMMU_CAP),
                    iospace: s(110),
                    device: 0x30,
                },
            )
        }));
        assert!(r.is_err(), "IoSpaceAttach on remote IoSpace must panic at memory.rs:500");
    }

    // 6) CSpaceGrow on remote CSpace + local Untyped: fails locally with Invalid instead of forwarding
    {
        let (mut sys, t) = boot_n(2);
        retype_done(&mut sys, 1, t[1], CSpace, 128, 100);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let out = sys.apply(
            0,
            t[0],
            Syscall::CSpaceGrow {
                cspace: s(110),
                untyped: UT,
            },
        );
        assert_eq!(out, Err(Error::Invalid));
    }

    // 7) ThreadConfigure on local Thread with remote CSpace -> panics at threads.rs:190
    {
        let (mut sys, t) = boot_n(2);
        assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 102)), DONE);
        retype_done(&mut sys, 1, t[1], CSpace, 128, 100);
        grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
        let r = catch_unwind(AssertUnwindSafe(|| {
            sys.apply(
                0,
                t[0],
                Syscall::ThreadConfigure {
                    thread: s(102),
                    cspace: s(110),
                    aspace: SlotAddr::NONE,
                    fault: SlotAddr::NONE,
                    page: SlotAddr::NONE,
                },
            )
        }));
        assert!(r.is_err(), "ThreadConfigure with remote cspace must panic at threads.rs:190");
    }
}

// =========================================================================
// (b) Disagreements: F3(1), F4(2), F9, F10
// =========================================================================

#[test]
fn f3_part1_stale_move_overwrites_reused_thread_in_ring_order() {
    let (mut sys, t) = boot_n(2);
    let ask_sender = spawn_thread(&mut sys, &t, 0, 200, 3000);
    let mover = spawn_thread(&mut sys, &t, 1, 200, 3000);
    let recv1 = spawn_thread(&mut sys, &t, 1, 202, 2994);

    // Grant 0: Thread D1 on node 0; Grant 1: Sched S on node 0.
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 100)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 101)), DONE);
    grant_one(&mut sys, &t, 0, 1, 100, 110, NO_EXEC);
    grant_one(&mut sys, &t, 0, 1, 101, 111, NO_EXEC);

    // Second thread D2 on node 0 (untouched, suspended, fresh RAX = 0).
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 120)), DONE);
    assert_eq!(sys.apply(1, recv1, recv_into(130, 1)), WAITS);
    assert_eq!(
        sys.apply(
            0,
            ask_sender,
            send_to(1, vec![Transfer::Derive(s(120), NO_EXEC.bits())])
        ),
        WAITS
    );
    deliver_first(&mut sys, |b| matches!(b, Body::Request { .. }));

    // Source thread on node 1 with distinct RAX = 0x1337.
    assert_eq!(sys.apply(1, t[1], retype(Thread, 0, 201)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(Frame, 1, 2997)), DONE);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::ThreadConfigure {
                thread: s(201),
                cspace: s(START_SLOT_CSPACE),
                aspace: ASPACE,
                fault: SlotAddr::NONE,
                page: s(2997),
            }
        ),
        DONE
    );
    assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 2996)), DONE);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::SchedConfigure {
                sched: s(2996),
                core: core(1),
                budget: 500_000,
                period: 10_000_000,
                class: 1,
            }
        ),
        DONE
    );
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::SchedSetCores {
                sched: s(2996),
                core: core(1),
                window: 0,
                mask: 0b11,
            }
        ),
        DONE
    );
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::SchedBind {
                sched: s(2996),
                thread: s(201),
            }
        ),
        DONE
    );
    let mut regs = vec![0u64; REGS_WORDS];
    regs[REG_RAX] = 0x1337;
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::ThreadWriteRegs {
                thread: s(201),
                block: regs,
            }
        ),
        DONE
    );

    // Queue Body::Move behind TransferAsk on ring 1 -> 0.
    assert_eq!(
        sys.apply(
            1,
            mover,
            Syscall::ThreadMove {
                thread: s(201),
                destination: s(110),
                sched: s(111),
                core: core(0),
                budget: 0,
                period: 0,
                class: 0,
            }
        ),
        WAITS
    );

    // Node 0 revokes grant 0 (D1) synchronously and delivers TransferAsk -> reuses grant 0 for D2!
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(100))), DONE);
    deliver_first(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 1)));

    // Deliver Body::Move in ring order -> lands on D2 instead of D1!
    deliver_first(&mut sys, |b| matches!(b, Body::Move { .. }));
    sys.settle(32);
    assert_eq!(sys.node(1).woken(mover), Some(&DONE));
    let Ok(Output::Regs(d1_regs)) = sys.apply(0, t[0], Syscall::ThreadReadRegs(s(100))) else {
        panic!("read D1");
    };
    let Ok(Output::Regs(d2_regs)) = sys.apply(0, t[0], Syscall::ThreadReadRegs(s(120))) else {
        panic!("read D2");
    };
    assert_eq!(d1_regs[REG_RAX], 0);
    assert_eq!(d2_regs[REG_RAX], 0x1337);
}

#[test]
fn f4_part2_cohosted_resume_on_no_role_core_seals_cleanly() {
    // 3-node machine: core 0 has fence=1 (holds NO unit role); cores 1, 2 hold unit roles.
    let (mut sys, t) = boot_n(3);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_SEAL }),
        DONE
    );
    sys.settle(32);
    sys.recover(16);
    assert_eq!(sys.node(1).member(1).state(), MemberState::Sealed);

    // Resume node 1 onto node 0's core (node 0 holds no unit role).
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace { core: core(1), physical: 0 }),
        DONE
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CoreStart {
                core: core(1),
                mode: CORE_START_RESUME,
                image: CORE_IMAGE_BOOT,
                module: 0,
            }
        ),
        DONE
    );

    // Kill node 1 from node 2: node 0 had save_seal=true and no unit role -> Sealed cleanly!
    assert_eq!(
        sys.apply(2, t[2], Syscall::CoreStop { core: core(1), mode: CORE_STOP_KILL }),
        DONE
    );
    sys.run(10 * MS, MS);
    assert_eq!(sys.node(2).member(1).state(), MemberState::Dead);
    let m0 = sys.node(2).member(0);
    assert_eq!(m0.state(), MemberState::Sealed);
    assert_eq!(m0.evidence(), Evidence::None);
}

#[test]
fn f9_resume_and_task_ops_during_move() {
    let (mut sys, t) = boot_n(2);
    let mover = spawn_thread(&mut sys, &t, 0, 200, 3000);
    assert_eq!(sys.apply(1, t[1], retype(Thread, 0, 100)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 101)), DONE);
    grant_one(&mut sys, &t, 1, 0, 100, 110, NO_EXEC);
    grant_one(&mut sys, &t, 1, 0, 101, 111, NO_EXEC);

    let src = spawn_thread(&mut sys, &t, 0, 201, 2997);
    assert_eq!(sys.apply(0, t[0], retype(Task, 0, 130)), DONE);
    assert_eq!(
        sys.apply(0, t[0], Syscall::TaskMark { task: s(130), marks: Marks::PRIVATE.bits() }),
        DONE
    );
    assert_eq!(sys.apply(0, t[0], Syscall::ThreadSuspend(s(201))), DONE);

    assert_eq!(
        sys.apply(
            0,
            mover,
            Syscall::ThreadMove {
                thread: s(201),
                destination: s(110),
                sched: s(111),
                core: core(1),
                budget: 0,
                period: 0,
                class: 0,
            }
        ),
        WAITS
    );

    // While Body::Move is in flight:
    // 1. ThreadResume succeeds.
    assert_eq!(sys.apply(0, t[0], Syscall::ThreadResume(s(201))), DONE);
    // 2. SchedCount succeeds ("No state error", line 669; not in line 675 busy list).
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::SchedCount {
                sched: s(2996),
                core: core(0),
                mode: SCHED_COUNT_ON,
            }
        ),
        DONE
    );
    // 3. TaskAttach succeeds mid-move (not in line 675 busy list).
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::TaskAttach {
                thread: s(201),
                task: s(130),
            }
        ),
        DONE
    );
    // 4. TaskRevoke on task detaches the in-move thread mid-move (`tasks.rs:148`) and suspends it.
    assert_eq!(sys.apply(0, t[0], Syscall::TaskRevoke(s(130))), DONE);
    // Resume again so we also observe the post-move state from Clause B.
    assert_eq!(sys.apply(0, t[0], Syscall::ThreadResume(s(201))), DONE);

    sys.settle(32);
    assert_eq!(sys.node(0).woken(mover), Some(&DONE));
    let Ok(Output::SchedRead { state, .. }) = sys.apply(0, t[0], Syscall::SchedRead(s(2996))) else {
        panic!("sched read");
    };
    assert_eq!(state & SCHED_STATE_CONFIGURED, 0);
    // Clause B: source stays not suspended (`runnable()`) and Model::apply executes Yield on it.
    assert!(sys.node(0).runnable().contains(&src));
    assert_eq!(sys.apply(0, src, Syscall::Yield), DONE);
}

#[test]
fn f10_late_handed_and_rate_limit_and_core_start_modules() {
    // 1) Late Body::Handed traced as Code 11 per line 855 (3 nodes: role 0 on slot 20).
    let (mut sys, t) = boot_n(3);
    let role0_3nodes = s(START_SLOT_FIRST + 3 + 1);
    let before = sys
        .node(2)
        .ring(false)
        .iter()
        .filter(|e| e.code() == TraceCode::Refused as u16)
        .count();

    assert!(matches!(
        sys.apply(
            1,
            t[1],
            Syscall::RoleHand {
                role: role0_3nodes,
                core: core(2),
            }
        ),
        Ok(Output::Epoch(_))
    ));
    // Node 2 takes role 0 via recover() BEFORE Body::Handed is delivered.
    sys.recover(16);
    assert_eq!(sys.role(0).state(), RoleState::Held);
    assert_eq!(sys.role(0).holder(), 2);
    // Now deliver late Body::Handed -> traced as Code 11 per line 855.
    deliver_first(&mut sys, |b| matches!(b, Body::Handed { .. }));
    let after = sys
        .node(2)
        .ring(false)
        .iter()
        .filter(|e| e.code() == TraceCode::Refused as u16)
        .count();
    assert_eq!(after, before + 1);

    // 2) Rate-limit window of Code 11 is per-node (max 16 per window, line 1295), shared across peers.
    for i in 0..17u32 {
        assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100 + i)), DONE);
        grant_one(&mut sys, &t, 0, 1, 100 + i, 100 + i, NO_EXEC);
    }
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 150)), DONE);
    grant_one(&mut sys, &t, 0, 2, 150, 150, NO_EXEC);
    // Node 0 revokes all 18 grants synchronously (never mapped).
    for i in 0..17u32 {
        assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(100 + i))), DONE);
    }
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(150))), DONE);
    // Node 1 sends 17 late releases + node 2 sends 1 late release in the same window.
    for i in 0..17u32 {
        assert_eq!(sys.apply(1, t[1], Syscall::CapDelete(s(100 + i))), DONE);
    }
    assert_eq!(sys.apply(2, t[2], Syscall::CapDelete(s(150))), DONE);
    sys.settle(64);
    let refused_entries = sys
        .node(0)
        .ring(false)
        .iter()
        .filter(|e| e.code() == TraceCode::Refused as u16)
        .count();
    assert_eq!(refused_entries, 16);
    assert_eq!(sys.node(0).suppressed(), 2);

    // 3a) Line 1172 check: module >= machine.segments.len() (non-first-service file) -> Invalid.
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_KILL }),
        DONE
    );
    sys.run(20 * MS, MS);
    assert_eq!(sys.node(0).member(1).state(), MemberState::Dead);
    let non_first = Machine::example().segments.len() as u64;
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CoreStart {
                core: core(1),
                mode: CORE_START_FRESH,
                image: CORE_IMAGE_BOOT,
                module: non_first,
            }
        ),
        Err(Error::Invalid)
    );
}

// =========================================================================
// (c) F2: Model behavior on core_place + core_stop(KILL) and RETIRE
// =========================================================================

#[test]
fn f2_core_place_and_retire_on_parked_core_model_behavior() {
    let (mut sys, t) = boot_n(3);
    // Live node 1 is placed on core 2 (running live node 2, which holds unit role 1).
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace { core: core(1), physical: 2 }),
        DONE
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_KILL }),
        DONE
    );
    sys.run(10 * MS, MS);
    // In the model, placed changes immediately; killing node 1 stops core 2 and kills node 2 (Host).
    assert_eq!(sys.node(0).member(1).state(), MemberState::Dead);
    assert_eq!(sys.node(0).member(2).state(), MemberState::Dead);
    assert_eq!(sys.node(0).member(2).evidence(), Evidence::Host);
    assert_eq!(sys.check(), Ok(()));

    // Also test CORE_STOP_RETIRE on a co-hosted sealed node: marks core 2 unusable while node 2 lives.
    let (mut sys2, t2) = boot_n(3);
    assert_eq!(
        sys2.apply(0, t2[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_SEAL }),
        DONE
    );
    sys2.settle(32);
    sys2.recover(16);
    assert_eq!(
        sys2.apply(0, t2[0], Syscall::CorePlace { core: core(1), physical: 2 }),
        DONE
    );
    assert_eq!(
        sys2.apply(0, t2[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_RETIRE }),
        DONE
    );
    let Ok(Output::Status(words)) = sys2.apply(0, t2[0], Syscall::CoreStatus(core(2))) else {
        panic!("core_status");
    };
    assert_ne!(words[1] & CORE_STATUS_UNUSABLE, 0);
    assert_eq!(sys2.node(0).member(2).state(), MemberState::Live);
}
```

## Appendix B: `model/src/verify_new_hydrogen_unit.rs`

```rust
use super::*;
use crate::{Message, Output, Range, Transfer};
use dodos_abi::ObjectKind::{self, Frame, IoSpace, Notify, Reply, Sched, Thread};
use dodos_abi::{
    CORE_IMAGE_BOOT, CORE_START_RESUME, CORE_STOP_SEAL, Evidence, MemberState, PageSize, Rights,
    RoleState, START_SLOT_ASPACE, START_SLOT_CSPACE, START_SLOT_FIRST, START_SLOT_MAILBOX,
    START_SLOT_SCHED, SlotAddr,
};

const DONE: crate::Outcome = Ok(crate::Output::Done);
const WAITS: crate::Outcome = Ok(crate::Output::Waits);
const MAILBOX: SlotAddr = SlotAddr::own(START_SLOT_MAILBOX);
const ASPACE: SlotAddr = SlotAddr::own(START_SLOT_ASPACE);
const MS: u64 = 1_000_000;

const fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

const fn core(n: u32) -> SlotAddr {
    SlotAddr::own(START_SLOT_FIRST + n)
}

const fn iommu_cap(nodes: usize) -> SlotAddr {
    SlotAddr::own(START_SLOT_FIRST + nodes as u32)
}

const fn role0_cap(nodes: usize) -> SlotAddr {
    SlotAddr::own(START_SLOT_FIRST + nodes as u32 + 1)
}

const fn ut_cap(nodes: usize) -> SlotAddr {
    SlotAddr::own(START_SLOT_FIRST + nodes as u32 + 6)
}

fn retype(nodes: usize, kind: ObjectKind, size: u64, dest: u32) -> Syscall {
    Syscall::UntypedRetype {
        untyped: ut_cap(nodes),
        kind,
        size,
        page: PageSize::Page as u64,
        memory: 0,
        destination: s(dest),
    }
}

fn retype_done(sys: &mut System, node: u16, caller: ObjId, nodes: usize, kind: ObjectKind, size: u64, dest: u32) {
    loop {
        match sys.apply(node, caller, retype(nodes, kind, size, dest)) {
            Ok(Output::Done) => break,
            Err(dodos_abi::Error::Again) => continue,
            other => panic!("unexpected retype outcome: {other:?}"),
        }
    }
}

fn machine_n(nodes: usize) -> Machine {
    let mut machine = Machine::example();
    while machine.cores.len() < nodes {
        let mut extra = machine.cores[1];
        extra.hw_id = 2 * machine.cores.len() as u64;
        machine.cores.push(extra);
    }
    machine.membership.stale_ms = 10;
    machine.membership.stuck_ms = 10;
    machine.membership.sweep_ms = 100;
    machine
}

fn boot_with(m: Machine) -> (System, Vec<ObjId>) {
    let nodes = m.cores.len();
    let (mut sys, t) = System::boot(&m).unwrap();
    for node in 0..nodes as u16 {
        let sched = Syscall::SchedConfigure {
            sched: s(START_SLOT_SCHED),
            core: core(node.into()),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        };
        assert_eq!(sys.apply(node, t[node as usize], sched), DONE);
        assert_eq!(sys.apply(node, t[node as usize], retype(nodes, Reply, 0, 99)), DONE);
    }
    (sys, t)
}

fn boot_n(nodes: usize) -> (System, Vec<ObjId>) {
    boot_with(machine_n(nodes))
}

fn spawn_thread(sys: &mut System, nodes: usize, t: &[ObjId], node: u16, slot: u32, spare: u32) -> ObjId {
    let root = t[node as usize];
    for call in [
        retype(nodes, Thread, 0, slot),
        retype(nodes, Frame, 1, spare),
        Syscall::ThreadConfigure {
            thread: s(slot),
            cspace: s(START_SLOT_CSPACE),
            aspace: ASPACE,
            fault: SlotAddr::NONE,
            page: s(spare),
        },
        retype(nodes, Sched, 0, spare - 1),
        Syscall::SchedConfigure {
            sched: s(spare - 1),
            core: core(node.into()),
            budget: 500_000,
            period: 10_000_000,
            class: 1,
        },
        Syscall::SchedBind {
            sched: s(spare - 1),
            thread: s(slot),
        },
        Syscall::ThreadResume(s(slot)),
    ] {
        assert_eq!(sys.apply(node, root, call), DONE);
    }
    sys.node(node).object_at(root, s(slot)).unwrap()
}

fn grant_one(
    sys: &mut System,
    t: &[ObjId],
    from: u16,
    to: u16,
    src_slot: u32,
    dst_slot: u32,
    rights: Rights,
) {
    let recv = Syscall::Recv {
        endpoint: MAILBOX,
        reply: s(99),
        range: Range {
            first: s(dst_slot),
            count: 1,
        },
        wait: 0,
    };
    assert_eq!(sys.apply(to, t[to as usize], recv), WAITS);
    let send = Syscall::Send {
        target: core(to.into()),
        message: Message {
            label: 1,
            flags: 0,
            words: vec![1],
            caps: vec![Transfer::Derive(s(src_slot), rights.bits())],
            marks: 0,
        },
    };
    assert_eq!(sys.apply(from, t[from as usize], send), WAITS);
    sys.settle(32);
    assert_eq!(sys.check(), Ok(()));
}

#[test]
fn n1_opus_detach_whose_thread_is_destroyed_leaves_unit_context_entry() {
    // 3-node machine: core 0 fence=1, core 1 & 2 fence=2 -> node 1 holds IOMMU role 0.
    let (mut sys, t) = boot_n(3);
    assert_eq!(sys.role(0).holder(), 1);

    retype_done(&mut sys, 0, t[0], 3, IoSpace, 0, 100);
    // Attach device 0x10 and control device 0x11 via node 1.
    for dev in [0x10u64, 0x11u64] {
        let attach = Syscall::IoSpaceAttach {
            iommu: iommu_cap(3),
            iospace: s(100),
            device: dev,
        };
        assert_eq!(sys.apply(0, t[0], attach), WAITS);
        sys.settle(16);
        assert_eq!(sys.node(0).woken(t[0]), Some(&DONE));
    }
    assert_eq!(
        sys.table().units[&0].entries.get(&0x10),
        Some(&(0, sys.table().generation(0)))
    );
    assert_eq!(
        sys.table().units[&0].entries.get(&0x11),
        Some(&(0, sys.table().generation(0)))
    );

    let detacher = spawn_thread(&mut sys, 3, &t, 0, 200, 3000);
    let keeper = spawn_thread(&mut sys, 3, &t, 0, 201, 2997);

    // Node 1 starts handing IOMMU role 0 to node 2 -> role is Handing.
    assert!(matches!(
        sys.apply(
            1,
            t[1],
            Syscall::RoleHand {
                role: role0_cap(3),
                core: core(2),
            }
        ),
        Ok(Output::Epoch(_))
    ));
    assert_eq!(sys.role(0).state(), RoleState::Handing);

    // Both detacher (0x10) and keeper (0x11) detach while role 0 is Handing.
    assert_eq!(
        sys.apply(
            0,
            detacher,
            Syscall::IoSpaceAttach {
                iommu: iommu_cap(3),
                iospace: SlotAddr::NONE,
                device: 0x10,
            }
        ),
        WAITS
    );
    assert_eq!(
        sys.apply(
            0,
            keeper,
            Syscall::IoSpaceAttach {
                iommu: iommu_cap(3),
                iospace: SlotAddr::NONE,
                device: 0x11,
            }
        ),
        WAITS
    );
    assert!(sys.table().reports[0].is_empty());

    // Destroy detacher: unlink deletes its Request::Unit (`ipc.rs:709`).
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(200))), DONE);

    // Finish hand-over; node 2 takes role 0 in recover(), then settle() delivers keeper's retry.
    sys.settle(32);
    sys.recover(16);
    sys.settle(32);
    assert_eq!(sys.role(0).state(), RoleState::Held);
    assert_eq!(sys.role(0).holder(), 2);

    // Control succeeded: 0x11's context entry was cleared.
    assert_eq!(sys.node(0).woken(keeper), Some(&DONE));
    assert_eq!(sys.table().units[&0].entries.get(&0x11), None);

    // Even after deleting the IoSpace, device 0x10's context entry remains on the unit.
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(100))), DONE);
    assert_eq!(sys.check(), Ok(()));
    assert!(sys.table().reports[0].is_empty());
    assert_eq!(
        sys.table().units[&0].entries.get(&0x10),
        Some(&(0, sys.table().generation(0)))
    );
}

#[test]
fn n1_opus_sibling_attach_whose_thread_is_destroyed_leaves_no_unit_context_entry() {
    let (mut sys, t) = boot_n(3);
    assert_eq!(sys.role(0).holder(), 1);
    retype_done(&mut sys, 0, t[0], 3, IoSpace, 0, 100);
    let attacher = spawn_thread(&mut sys, 3, &t, 0, 200, 3000);

    assert!(matches!(
        sys.apply(
            1,
            t[1],
            Syscall::RoleHand {
                role: role0_cap(3),
                core: core(2),
            }
        ),
        Ok(Output::Epoch(_))
    ));
    assert_eq!(sys.role(0).state(), RoleState::Handing);

    // Attacher starts IoSpaceAttach while role is Handing, then is destroyed.
    assert_eq!(
        sys.apply(
            0,
            attacher,
            Syscall::IoSpaceAttach {
                iommu: iommu_cap(3),
                iospace: s(100),
                device: 0x20,
            }
        ),
        WAITS
    );
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(200))), DONE);

    sys.settle(32);
    sys.recover(16);
    assert_eq!(sys.role(0).holder(), 2);
    assert_eq!(sys.check(), Ok(()));
    // Node 0's report & identifier table say 0x20 is attached, yet the unit entry was never written.
    assert!(sys.table().reports[0].contains(&(0, 0x20)));
    assert_eq!(sys.table().units[&0].entries.get(&0x20), None);
}

#[test]
fn f4_part2_unit_save_seal_is_set_and_node2_dies_only_because_of_unit_roles() {
    // 3-node machine: core 0 fence=1, core 1 fence=2, core 2 fence=2.
    // Unit role 0 -> node 1, unit role 1 -> node 2.
    let (mut sys, t) = boot_n(3);
    assert_eq!((sys.role(0).holder(), sys.role(1).holder()), (1, 2));

    // Seal node 1: it hands role 0 to node 2, leaving node 2 holding both unit roles.
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_SEAL }),
        DONE
    );
    sys.settle(32);
    sys.recover(16);
    assert_eq!(sys.node(1).member(1).state(), MemberState::Sealed);
    assert_eq!((sys.role(0).holder(), sys.role(1).holder()), (2, 2));

    // Place sealed node 1 on core 2 (which runs live node 2) and resume it.
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace { core: core(1), physical: 2 }),
        DONE
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CoreStart {
                core: core(1),
                mode: CORE_START_RESUME,
                image: CORE_IMAGE_BOOT,
                module: 0,
            }
        ),
        DONE
    );
    assert_eq!(sys.node(0).member(1).state(), MemberState::Live);

    // Proves load_block() DID set save_seal = true on node 2!
    assert_eq!(sys.table().core_beacons[2].running, 1);
    assert!(sys.table().beacons[2].save_seal);

    // Kill node 1: node 2 becomes Dead with Evidence::Host ONLY because it holds unit roles (1089).
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CoreStop {
                core: core(1),
                mode: dodos_abi::CORE_STOP_KILL,
            }
        ),
        DONE
    );
    sys.run(10 * MS, MS);
    assert_eq!(sys.node(0).member(1).state(), MemberState::Dead);
    let m2 = sys.node(0).member(2);
    assert_eq!(m2.state(), MemberState::Dead);
    assert_eq!(m2.evidence(), Evidence::Host);
}

#[test]
fn f10_unit_needed_skips_non_call_requests_against_line_1069() {
    // 4-node machine: node 0's two cyclic successors are 1 and 2, NOT 3.
    let (mut sys, t) = boot_n(4);

    // Part A: Request::Move targeting node 3 is omitted by needed().
    let mut all = Rights::ALL;
    all = all.without(Rights::EXEC);
    assert_eq!(sys.apply(3, t[3], retype(4, Thread, 0, 100)), DONE);
    assert_eq!(sys.apply(3, t[3], retype(4, Sched, 0, 101)), DONE);
    grant_one(&mut sys, &t, 3, 0, 100, 110, all);
    grant_one(&mut sys, &t, 3, 0, 101, 111, all);

    let src = spawn_thread(&mut sys, 4, &t, 0, 200, 3000);
    assert_eq!(sys.apply(0, t[0], Syscall::ThreadSuspend(s(200))), DONE);
    let mv = Syscall::ThreadMove {
        thread: s(200),
        destination: s(110),
        sched: s(111),
        core: core(3),
        budget: 0,
        period: 0,
        class: 0,
    };
    assert_eq!(sys.apply(0, t[0], mv), WAITS);
    assert!(!sys.node(0).needed().contains(&3));
    let _ = src;

    // Trigger initial sweep at 0..5ms while node 3 is live, setting next_sweep >= 100ms.
    sys.run(5 * MS, MS);
    // Now hang node 3 before next_sweep (100ms): node 0 has no Call on 3, so 3 stays Live at 45ms.
    sys.hang(3, true);
    sys.run(45 * MS, MS);
    assert!(!sys.node(0).needed().contains(&3));
    assert_eq!(sys.node(0).member(3).state(), MemberState::Live);

    // Part B: Control using Request::Call (Notify Wait) targeting node 3 IS in needed().
    let (mut sys2, t2) = boot_n(4);
    assert_eq!(sys2.apply(3, t2[3], retype(4, Notify, 0, 100)), DONE);
    grant_one(&mut sys2, &t2, 3, 0, 100, 110, Rights::ALL.without(Rights::EXEC));
    sys2.run(5 * MS, MS);
    assert_eq!(sys2.apply(0, t2[0], Syscall::Wait(s(110), 0)), WAITS);
    sys2.settle(16);
    assert!(sys2.node(0).needed().contains(&3));
    sys2.hang(3, true);
    sys2.run(45 * MS, MS);
    assert_eq!(sys2.node(0).member(3).state(), MemberState::Dead);
}
```

## Appendix C: `ring_order_and_unit_include.patch`

```diff
diff --git a/model/src/recovery.rs b/model/src/recovery.rs
index 743f883..f519033 100644
--- a/model/src/recovery.rs
+++ b/model/src/recovery.rs
@@ -462,7 +462,7 @@ impl Model {
 
     /// The nodes this node needs: those its threads wait for, and its two
     /// successors among the nodes that are not dead (the sweep).
-    fn needed(&self) -> Vec<u16> {
+    pub(crate) fn needed(&self) -> Vec<u16> {
         let mut needed: Vec<u16> = self
             .requests
             .values()
diff --git a/model/src/system.rs b/model/src/system.rs
index adde7bc..7a291a3 100644
--- a/model/src/system.rs
+++ b/model/src/system.rs
@@ -163,6 +163,15 @@ impl System {
     /// The message in flight at `index` arrives at its node, which runs.
     pub fn deliver(&mut self, index: usize) {
         let to = self.in_flight[index].to;
+        // One ring per ordered pair of nodes: a message never overtakes an
+        // older one of the same pair.
+        let from = self.in_flight[index].from;
+        assert!(
+            !self.in_flight[..index]
+                .iter()
+                .any(|p| p.from == from && p.to == to),
+            "overtaking in the ring {from} -> {to}"
+        );
         assert!(self.runs(to), "node {to} does not run");
         let packet = self.in_flight.remove(index);
         let from = packet.from as usize;
@@ -1170,3 +1179,7 @@ mod tests {
         assert_eq!(sys.check(), Err("86: no live node".into()));
     }
 }
+
+#[cfg(test)]
+#[path = "verify_new_hydrogen_unit.rs"]
+mod verify_new_hydrogen_unit;
```
