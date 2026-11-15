# Review 7: verification of the gemini-hydrogen report, by Opus

Report verified: `Docs/reviews/2026-11-16-model-review-7-gemini-hydrogen.md` (F1 to F11, protocols between nodes).
Contract: `Docs/architecture/kernel-interface.md` at Docs `3bc7597`. Model: `dodos-kernel` branch `model` at `2afc901`.

## What I did

- Ran the reviewer's 18 tests and 2 unit tests in a copy at `2afc901` (`/tmp/opus-r7v/k`): all pass, as reported.
- Made a second copy (`/tmp/opus-r7v/e`, then a clean one, `/tmp/opus-r7v/c`) where `System::deliver(index)` panics when an older message with the same `from` and `to` is still in flight: one ring per ordered pair of nodes, so the messages of one ring arrive in the order they were sent. With it, 6 of the reviewer's 18 tests stop (f1b, f1c, f5a, f5b, f6, f7), as you said.
- Wrote my own tests from the contract, every one run with ring order enforced: 22 integration tests (`model/tests/verify_hydrogen_opus.rs`) and 2 unit tests inside the crate (`model/src/verify_hydrogen_opus_unit.rs`, a child of `system`, to read the unit's context entries and a node's requests). All 24 pass at the default page size, `DODOS_PAGE=16k` and `32k`. For each of the 6 tests that break ring order, I looked for a legal order (a third node, a revocation by the granter, a second thread) before calling a finding impossible: for f1b, f5a, f5b, f6 and f7 I found one (the fault is real); for f1c I did not, and I explain why it cannot happen.
- Ran the whole model suite with ring order enforced: besides the reviewer's 6, three tests of the repository break ring order (new finding N3).
- Files: `scratchpad/review7/tests/verify-hydrogen-opus/` (the two test files, `ring_order_and_unit_include.patch`, a README).

"Side" says where the fault is: contract, model or tests. A test name below is in `verify_hydrogen_opus.rs` unless I write "unit".

## Verdicts

| Finding | Verdict | Side | Severity (mine) | How I know |
|---|---|---|---|---|
| F1 stale `RevokeStep` / `Revoke` | CONFIRMED IN PART: (1) and (2) hold in ring order; (3) impossible; (4) not a fault | contract and model | breaks isolation between nodes (1); blocks for ever (2) | run: `f1_revoke_step_frees_a_reused_grant_in_ring_order`, `f1_revoke_step_refused_after_reuse_for_a_third_node_strands_the_revoker`, `f1_late_revoke_arrives_before_any_regrant_on_its_ring`, `f1_release_after_an_immediate_free_is_traced_as_the_contract_asks` |
| F2 `core_place` + `core_stop`, retire of a parked node | CONFIRMED IN PART: wording of the contract only; the claimed faults of the model are not faults | contract | wording | run: `f2_core_place_moves_a_live_node_at_once_and_leaves_its_old_core_running`, `f2_retire_of_a_parked_node_marks_its_placed_core_and_stops_nothing`; read: contract 1077, 1182, 1194 |
| F3 `Move` / `Request` without serial; `TransferGrant` after a revocation | CONFIRMED IN PART: (1) and (2) hold in ring order by another route; (3) not a fault | contract and model | breaks isolation between nodes (2); wrong result and panic of the model (1) | run: `f3_stale_move_lands_in_a_thread_granted_after_its_destination_was_revoked`, `f3_stale_move_onto_a_reused_grant_of_another_kind_panics_the_model`, `f3_stale_request_signals_an_object_granted_to_a_third_node`, `f3_a_grant_revoked_in_flight_lands_invalid_and_its_use_is_gone` |
| F4 sealed, resumed, co-hosted nodes | CONFIRMED IN PART: (1) holds; (2) not reproduced; (3) not a fault; (4c) true but unreachable; (4a, 4b) not verified | contract (1), model (4c) | blocks for ever (1) | run: `f4_a_resumed_node_never_ends_a_wait_on_a_node_that_died_while_it_was_sealed`, `f4_kill_after_a_cohosted_resume_seals_the_other_node_not_host`, `f4_a_sealing_node_cannot_accuse_the_last_live_node_as_the_contract_says`, `f4_a_start_completes_in_one_event_so_starting_is_never_observed` |
| F5 `unlink`, `asked(None)`, role index | CONFIRMED IN PART: (1) holds; (2) and (3) impossible (they need a message no correct node sends) | model | wrong result (1) | run: `f5_a_send_whose_thread_is_destroyed_drops_its_capabilities`; unit `an_answer_to_a_forgotten_request_keeps_the_proxy_count_right` |
| F6 refused moves | CONFIRMED IN PART: "answer before refusal" is impossible, but the same loss happens in ring order; (2) holds in ring order | model (contract wording for (2)) | wrong result: a capability lost for ever, then a model invariant broken | run: `f6_a_refused_move_whose_slot_was_refilled_strands_the_capability`, `f6_a_refusal_naming_one_freed_grant_strands_the_other_moved_capability` |
| F7 remote `CSpace` destination, remote secondary arguments | CONFIRMED (one call of the list falls: `task_attach` with the remote thread first answers `invalid`) | model | panic of the model | run: `f7_a_destination_in_a_remote_cspace_panics_the_model`, `f7_a_remote_secondary_argument_of_a_local_call_panics_or_not` |
| F8 unit request lost when the role comes back | CONFIRMED | model | blocks for ever | run: `f8_a_unit_request_is_lost_when_the_role_comes_back_to_the_node_asked` |
| F9 `thread_resume` during `thread_move`, missing freezes | NOT A FAULT (contract 675 and 669 ask for it); the `task_attach` and `task_revoke` part is a wording conflict, not tested | (contract wording) | wording | run: `f9_resume_during_a_successful_move_is_what_the_contract_says`; read: contract 669, 675 |
| F10 late `Handed`, shared rate limit, `core_start`, `needed()` | CONFIRMED IN PART: (1) and (2) are what the contract asks; (3b) holds by reading; (3a) cannot be expressed in the model; (3c) is F1 | model (3b), contract wording (1) | wording; slower detection (3b) | run: `f10_a_late_handed_message_is_traced_as_the_contract_is_written`; read: contract 855, 1069, 1295, `recovery.rs:465` |
| F11 coverage of `liveness.rs`, `way_out` | CONFIRMED | tests | wording (a test gap) | read `liveness.rs:271`; run: the reviewer's coverage probe (`RUNS=136`, same state sets) |

Count per verdict: CONFIRMED 3 (F7, F8, F11); CONFIRMED IN PART 7 (F1, F2, F3, F4, F5, F6, F10); NOT A FAULT 1 (F9); IMPOSSIBLE SCENARIO 0 and NOT REPRODUCED 0 as whole verdicts (parts of F1, F4, F5 and F6 are impossible or not reproduced, said in their sections). New findings: 4 (N1 to N4).

## F1: stale revocation messages

**Claim.** `Request::Revoke` keeps no serial, `Body::RevokeStep { id, done }` names no grant, and `asked(id)` checks only the grantee and generation of whatever entry sits at that index now; a release can free a revoking entry while a step is still to come.

**The contract.** Line 842: "*Y* removes it in steps of at most 32 units ... and answers after each step; the removal step on *X* returns `again` after each answer until *Y* reports the root removed, and then frees the entry." Line 844: "When *Y* removes the root remote capability of a grant (by any removal), it frees its use entry and sends *X* a message that names the grant and its serial ... it then frees the entry if its anchor has no descendant". Line 855: "the answer of a revocation step come[s] only from the grantee the entry names, with the generation the entry records". So two messages of the same holder may free the same entry, and the second is checked against "the entry", with no serial. On a normal revocation the holder's removal of its root sends the release first, then the step, on the same ring (`remote.rs:1340`, `remote_destroyed` then `RevokeStep`): the entry is free between the two, and the contract lets the step free whatever the entry has become. Both texts are at fault, not only the model.

**(1) Isolation, in ring order: CONFIRMED.** The reviewer's f1b delivers the step before the ask of node 1 that precedes it. A legal order exists: node 0 sends the transfer of a second frame *before* it revokes the first, so on ring 0→1 the request comes before the revocation, and on ring 1→0 the release (node 1 deleted its remote capability), then the ask for grants, then the step follow each other. `f1_revoke_step_frees_a_reused_grant_in_ring_order`: the release frees entry 0, the ask reuses it (serial 1) for the second frame, node 1 maps it, and the late step frees that live, mapped entry. `check()` returns `node 1: 58: translation under no grant`; node 0 then deletes the second frame (`cap_delete` returns `done`: its anchor has no entry, so `revoke_anchor` lets it go) while node 1 still translates the address. Severity: breaks isolation between nodes.

**(2) Waiter stuck, third node: CONFIRMED, and in a simpler form than reported.** No deletion by the holder is needed: on a normal revocation, between the release and the step on ring 1→0, an ask from node 2 (another ring) reuses the freed entry, and the step is refused. `f1_revoke_step_refused_after_reuse_for_a_third_node_strands_the_revoker`: one trace of code 11, and the revoking thread is not woken after 2 s, node 1 still live. Severity: blocks for ever (no message will come for it; I did not test what a later death of node 1 or node 2 does to that wait).

**(3) Late `Revoke` refused on the same holder: IMPOSSIBLE SCENARIO.** Node 1 can hold (grant 0, serial 1) only through a `TransferGrant` that node 0 sent after it reused entry 0, so after the `Revoke` of serial 0, on the same ring 0→1: the `Revoke` always arrives first, finds nothing and answers `done`. `f1_late_revoke_arrives_before_any_regrant_on_its_ring` shows that delivering the re-grant first breaks ring order, and that in order the `Revoke` is not refused (its step then frees the reused entry: that is (1) again).

**(4) Trace on a release that crosses an immediate free: NOT A FAULT.** Line 855 asks for it: "a release ... only from the grantee the entry names" and "A message that fails its check changes nothing and is traced". `f1_release_after_an_immediate_free_is_traced_as_the_contract_asks` shows one entry of code 11 and every invariant holding. It is noise on a benign race, a wording point at most.

## F2: `core_place`, `core_stop`, retire

**Claim.** The fence aims at `placed[node]` while the node still runs on its old core; retire of a parked node marks a live node's core unusable.

**The model.** `core_place` writes `placed` at once (`recovery.rs:401`), and `System` runs a node wherever `placed` says (`System::runs`): the model has no window between the call and the move. `f2_core_place_moves_a_live_node_at_once_and_leaves_its_old_core_running`: node 1 runs on core 2 right after the call; after the kill, node 1 is dead and node 2, which shares core 2 and holds unit role 1, is accused with host. That is the rule of line 1089 ("A *Z* that a unit role names is accused"), not a fault. The old core stays `Running` with no node placed on it, which nothing reads: no dead node runs there in the model.

**Retire.** `f2_retire_of_a_parked_node_marks_its_placed_core_and_stops_nothing`: retire of sealed node 1, placed on core 2, marks core 2 unusable (`core_status` bit 33); node 2 stays live and running. Marking a core unusable stops nothing; it only refuses later starts and placements there (lines 1173, 1194).

**What remains, wording of the contract.** Line 1194: "the node is bound to that core in the machine table; a live node moves at its next event boundary". Line 1077: "Let *p* be the physical core that runs *X*." Line 1182: "Mode 2 also marks the physical core that runs the node as unusable". Nothing says how the driver finds *p* in the window line 1194 opens (`placed` already names the new core), nor what "the core that runs the node" is for a sealed node that runs nowhere. A kernel author who reads *p* from `placed` fences the wrong core in that window. CONFIRMED IN PART, contract, wording.

## F3: grants named without their serial

**Claim.** `Body::Move` and the capability arguments of `Body::Request` name grants by index only; the receiving node acts on whatever the entry holds now.

**The contract.** Line 855: "a move names grants whose grantee is the sender"; nothing binds a move or a request to the serial, while a release is bound to it (line 844). Line 842: "the grant becomes *revoking*, so every remote capability of it is invalid from that moment" says nothing of a request already in flight. The model follows: `misdirected` checks only grantee and generation for a move (`remote.rs:640`) and does not check requests; `forward` sends `anchor_index(grant)` (`remote.rs:414`).

**(1) `Move`: CONFIRMED in ring order, by another route.** The reviewer's f5a needs the holder's releases to overtake the move on their ring. The granter can free the entry itself: a revocation of a grant that nothing maps frees it at once, with no message. `f3_stale_move_lands_in_a_thread_granted_after_its_destination_was_revoked`: node 1 sends the move behind an ask on ring 1→0; node 0 revokes the destination thread's grant; the ask reuses entry 0 for another thread granted to node 1; the move lands there (that thread's RAX becomes 0xABCD), and the caller gets `done`. Wrong result. If the entry is reused for an object of another kind, `place_move` panics at `moves.rs:165` (`self.threads[&target]`): `f3_stale_move_onto_a_reused_grant_of_another_kind_panics_the_model` (new finding N2).

**(2) `Request`: CONFIRMED in ring order.** `f3_stale_request_signals_an_object_granted_to_a_third_node`: node 1's signal on its remote notify is in flight; node 0 revokes that grant (freed at once) and an ask from node 2 reuses entry 0 for another notify; the request signals node 2's notify (`poll` on it reads 1, the first notify reads nothing). Node 1 acted on an object it was never given. Severity: breaks isolation between nodes (authority, not memory).

**(3) `TransferGrant` after a revocation: NOT A FAULT.** A grant revoked while its `TransferGrant` is in flight lands as a remote capability that is invalid from the start (line 835: valid "when the grant entry is live with that serial"), as after any revocation that follows a delivery. `f3_a_grant_revoked_in_flight_lands_invalid_and_its_use_is_gone`: the first use is `gone`, every invariant holds. `caps_dropped` is for full tables and refusals (line 836), not for a later revocation.

## F4: sealed, resumed and co-hosted nodes

**(1) Resume runs only R2: CONFIRMED; the contract is at fault.** Line 845: "when it resumes (`core_start` mode 1), before it runs any thread, it removes its remote capabilities whose use entry records a generation of their granting node that is over, by the steps of R2". R0 (line 1098, "It ends with `gone` every wait of its threads on *X*") and R3 (line 1104, its grants to *X*'s generation) are run "when a live node *Y* sees *X* in fencing" or fenced; a sealed node sees nothing, and nothing makes it run them at resume. The model does what line 845 says (`started`, `recovery.rs:1167`). `f4_a_resumed_node_never_ends_a_wait_on_a_node_that_died_while_it_was_sealed`: node 1 waits on node 0's notify and has granted node 0 a frame; node 1 is sealed; node 0 is killed and becomes dead; node 1 is resumed; after 2 s the wait has not ended and the grant still names node 0's dead generation. The control (the same kill with node 1 live) ends the wait with `gone` and frees the grant. Blocks for ever.

**(2) Host kill after a co-hosted resume: NOT REPRODUCED.** The reviewer's f3b kills node 2 with host because node 2 holds unit roles 0 and 1 (I printed the role words), which line 1089 asks for. The save seal is set: every event of a node on a shared core calls `load_block` (`sched.rs:104`, `recovery.rs:94`), the start included (`started` calls `begin`). `f4_kill_after_a_cohosted_resume_seals_the_other_node_not_host`: the same scenario on node 0's core, node 0 holding no unit role: node 0 becomes sealed, evidence none.

**(3) Two nodes, the last live node hangs while the other seals: NOT A FAULT.** Line 1037: the transition to fencing is made by "any live node"; a sealing node is not live. Line 1138: "`core_stop` refuses to kill or seal the last live node (`busy`), so the last node is lost only by its own failure, and then the machine is lost." `f4_a_sealing_node_cannot_accuse_the_last_live_node_as_the_contract_says` shows the state the contract describes.

**(4c) Stale before `START_NS`: true by reading, unreachable.** `evidence` (`recovery.rs:437`) gives stale to any node after `stale_ns`, starting included. But in the model a start completes in the event that makes it (`start_node` calls `started`): `f4_a_start_completes_in_one_event_so_starting_is_never_observed`. A latent fault of the model. (4a) and (4b) I did not test.

## F5: a destroyed thread's request, `asked(None)`, the role index

**(1) CONFIRMED.** Line 854: "A request that holds no wait there completes without the thread, so nothing is left half done: its answer changes what it would have changed except the thread's own state". `unlink` forgets a `Request::Call` that holds no wait (`ipc.rs:709`), and `grant_transfer` then answers `None`. `f5_a_send_whose_thread_is_destroyed_drops_its_capabilities` (ring order): the receiver gets 0 capabilities and `caps_dropped`. Wrong result. The unit request part of the claim is real but the reviewer's test does not show it (it asserts only the new holder of the role); I show a worse case of the same code as new finding N1.

**(2) Spurious `Answer`, and (3) role out of range: IMPOSSIBLE SCENARIO.** Both tests inject with `receive_packet` a message that no correct node sends: an answer to an id the peer never received (ids are `node << 48 | counter`, unique), and `Handed` with role 999. On the legal path the count stays right: unit `an_answer_to_a_forgotten_request_keeps_the_proxy_count_right` destroys a thread whose signal is in flight; the late answer passes `asked` (`None => true`) and gives back the proxy, `outstanding` returns to 0. Robustness against a faulty kernel is not what line 855 protects against (stale messages across generations).

## F6: refused moved capabilities

**(1) CONFIRMED IN PART.** The refusal and the answer leave the receiver on the same ring, refusal first (`place_transfer`, `remote.rs:963`), so the answer cannot overtake it; the test checks this order. But the moved capability sits in the anchor from the ask on, and its slot is empty to every thread of the sender's space, not only after the answer. `f6_a_refused_move_whose_slot_was_refilled_strands_the_capability` (ring order): a second thread of node 0 fills the slot; the refusal frees the grant and leaves the capability in the kernel's own space (`refused`, `remote.rs:1208`, the `Some(_) => {}` arm), reachable by no one; `check()` still passes. The next grant of entry 0 then writes into that anchor slot, and `check()` returns `node 0: 6: slot of a capability`. Wrong result, then a broken invariant of the model.

**(2) CONFIRMED in ring order.** `f6_a_refusal_naming_one_freed_grant_strands_the_other_moved_capability`: two moved capabilities, refused; before the refusal arrives node 0 revokes the parent of the first (its grant, held by nobody, is freed at once); `misdirected` requires all grants to match (`remote.rs:632`) and refuses the whole message: the second capability stays in its anchor, its grant live, after 1 s. Line 855 speaks of "the entry", in the singular, for a refusal that names several: the model's `all` is one reading of it.

## F7: calls the model does not handle

**CONFIRMED.** `f7_a_destination_in_a_remote_cspace_panics_the_model`: `cap_derive` and `untyped_retype` into a slot through a remote `CSpace` (line 836: they make a grant) panic at `lib.rs:1635`. `f7_a_remote_secondary_argument_of_a_local_call_panics_or_not` (line 851: such an argument is `invalid`): `sched_bind` panics (`sched.rs:620`), `notify_bind` (`ipc.rs:337`), `timer_set` (`lib.rs:1042`) and `task_attach` with a local thread and a remote task (`lib.rs:1042`). `task_attach` with the remote thread first is forwarded (the thread is the target) and returns `invalid` as it should: that call, which the reviewer listed by reading, holds in one order of its arguments only.

## F8: a unit request that is never sent again

**CONFIRMED.** `f8_a_unit_request_is_lost_when_the_role_comes_back_to_the_node_asked` (ring order): node 0's attach goes to node 1; node 1 hands the role to node 2 and refuses the request; node 0 reads a handing word and keeps `sent_to` = 1 (`roles.rs:239`); node 2 takes the role and hands it back to node 1 before node 0's recovery runs; `roles_unit` sees the holder it already asked (`roles.rs:393`) and never sends the request again. After 2 s the attaching thread still waits. Line 1212: "the requester reads the role word again and sends it to the holder it names". Blocks for ever.

## F9: `thread_resume` during a move

**NOT A FAULT.** Line 675: "`thread_resume` clears its suspension but not its wait, so it runs only after the answer, and only if the move was refused", and on success "the thread keeps its bindings, stays suspended (unless `thread_resume` cleared it meanwhile), and its own context is unbound, made not configured ... so it cannot run". `f9_resume_during_a_successful_move_is_what_the_contract_says`: after success the source is not suspended, its context reads not configured (`SCHED_STATE_CONFIGURED` clear), the destination has the registers. `runnable()` lists threads that are not suspended and not waiting, whether or not a context can run them; that is the model's list for tests, not a run. `sched_count` during the move succeeds, as line 669 says ("No state error"). Line 675 also says "from the sending of its state to the answer, nothing changes it on the source" while it names only four calls as `busy`: `task_attach` and `task_revoke` on the source are not covered either way. That is a wording conflict of the contract; I did not test it.

## F10: traces, rate limit, `core_start`, `needed()`

- (1) Late `Handed`: what the contract asks (line 855, "the message of step 4 of a hand-over only from the node the handing word names as holder"). `f10_a_late_handed_message_is_traced_as_the_contract_is_written`: the target takes the role in its recovery, and the late message adds one trace of code 11. Noise on a normal path, wording.
- (2) One rate limit per code and node: line 1295, "Windows are counted per node". Not a fault.
- (3a) `core_start` does not check the first-service flag (line 1172): the model has no list of modules (`modules` is the number of segments of the first service, `recovery.rs:124`), so it cannot express the check. Model gap; not tested.
- (3b) `needed()` (`recovery.rs:465`) observes only the peers of `Request::Call`. Line 1069: "A thread that waits for *X* (a call to an object of *X*, an acknowledgement of a core group, a request to a role *X* holds) makes its kernel observe *X*". A waiting unit request (and a move, a revocation step, a transfer, a carried call) is left to the sweep of the two successors. Confirmed by reading; detection is slower, not lost (every node is somebody's successor).
- (3c) is F1.

## F11: what `liveness.rs` checks

**CONFIRMED.** `way_out` (`liveness.rs:271`) checks member words, role words and grant entries, and `explore` checks the one waiting thread of a scenario; a thread left in *waiting for another node* elsewhere, a request or a proxy count left over, or a capability stranded in the kernel space passes. I re-ran the reviewer's probe: `RUNS=136 WAY_OUT=136`, the same sets of states (no starting, no evidence self, retire or host, no revoking grant, no `Off`, `InitPending` or `Hung { nmi: false }`). The probe samples between steps and every 1 ms, so a state that lasts less than that (a revoking entry, for example) can be missed; and `MAX_DEAD=2`, so two deaths in one run are reached. Faults F1 (2), F4 (1), F6 and F8 are all states `way_out` would pass.

## New findings

**N1 (next to F5 (1)): a detach whose thread is destroyed leaves the context entry on the unit.** Model, `ipc.rs:709` with `roles.rs:231`. Node 0 detaches a device (`iospace_attach` with iospace 0) while the unit's role is handing, so the request waits on node 0 (`send_unit_request` returns while the word is not usable); the thread is destroyed and `unlink` forgets the request. Unit test `a_detach_whose_thread_is_destroyed_leaves_the_context_entry_on_the_unit`: after the hand-over completes, the unit's entry for the device still names node 0, and stays after node 0 destroys the iospace it served; `check()` passes. The control (thread kept) clears the entry. Line 854 asks the request to complete without the thread. Severity: breaks isolation between nodes once the iospace's memory is reused or given away (the device keeps a context entry whose tables are gone); shown up to the stale entry.

**N2 (next to F3 (1)): a stale move onto a reused grant of another kind panics the model.** Model, `moves.rs:165`. `f3_stale_move_onto_a_reused_grant_of_another_kind_panics_the_model`, ring order. Panic of the model.

**N3 (next to F1): three tests of the repository deliver out of ring order.** Tests. With ring order enforced, `nodes.rs` `revoking_a_mapped_grant_waits_for_the_holder_then_returns_again` and `a_stale_remote_capability_sent_home_is_dropped`, and `recovery.rs` `a_holder_refuses_a_request_of_another_epoch_even_when_it_holds_the_role_again`, stop with "an older message from 1 to 0 is still in flight". The first delivers the revocation step before the release that precedes it on ring 1→0: the model's own test of revocation skips the order in which F1's window opens. Every other test of the model crate keeps ring order.

**N4 (next to F4 (2)): resume on a core that runs a live node contradicts the table of transitions.** Contract. Line 1032: "sealed (*g*) → starting (*g*) ... The core it is placed on is confirmed parked or runs no node", and line 1173: "mode 1: `busy` if the node is not sealed or its core is not confirmed parked". Line 1194 lets a sealed node be placed on a core that runs a live node ("`busy` if the core runs a node that is not live") and says "a sealed node is resumed there by `core_start` mode 1"; line 1090 has a core run the blocks of its nodes in turn. The model takes "confirmed parked" for the node, not the core (`recovery.rs`, `core_start`: `running != node || parked_core`), and resumes it (`f4_kill_after_a_cohosted_resume_seals_the_other_node_not_host`, `core_start` returns `done` on node 0's core). Wording; a kernel author who reads line 1173 refuses every co-hosted resume.

## Appendix A: `model/tests/verify_hydrogen_opus.rs`

```rust
//! Verification of review 7 (gemini-hydrogen), by an independent verifier.
//!
//! Run in a copy of the model whose `System::deliver` panics when an older
//! message with the same `from` and `to` is still in flight: every message
//! between two nodes travels through one ring per ordered pair, so it
//! arrives in the order it was sent. Every scenario below keeps that order;
//! a test that broke it would panic in `deliver`.

use dodos_abi::ObjectKind::{CSpace, Frame, IoSpace, Notify, Reply, Sched, Thread};
use dodos_abi::*;
use dodos_model::*;
use std::panic::{AssertUnwindSafe, catch_unwind};

const DONE: Outcome = Ok(Output::Done);
const WAITS: Outcome = Ok(Output::Waits);
const UT: SlotAddr = SlotAddr::own(25);
const MAILBOX: SlotAddr = SlotAddr::own(START_SLOT_MAILBOX);
const ASPACE: SlotAddr = SlotAddr::own(START_SLOT_ASPACE);
const MS: u64 = 1_000_000;
/// The capability of role 0 (the unit role of IOMMU unit 0) and of the
/// IOMMU object in every start-up space.
const ROLE_0: u32 = 20;
const IOMMU: u32 = 19;
const AT: u64 = 1 << 30;
const AT2: u64 = 2 << 30;

const fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

const fn core(n: u32) -> SlotAddr {
    SlotAddr::own(16 + n)
}

fn retype(kind: ObjectKind, size: u64, destination: u32) -> Syscall {
    Syscall::UntypedRetype {
        untyped: UT,
        kind,
        size,
        page: PageSize::Page as u64,
        memory: 0,
        destination: s(destination),
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

fn recv_into(first: u32) -> Syscall {
    Syscall::Recv {
        endpoint: MAILBOX,
        reply: s(99),
        range: Range {
            first: s(first),
            count: 1,
        },
        wait: 0,
    }
}

fn map(frame: u32, address: u64) -> Syscall {
    Syscall::ASpaceMap(Map {
        space: ASPACE,
        frame: s(frame),
        untyped: SlotAddr::NONE,
        address,
        first: 0,
        count: 1,
        rights: Rights::READ.bits(),
    })
}

fn send(to: u32, caps: Vec<Transfer>) -> Syscall {
    Syscall::Send {
        target: core(to),
        message: msg(caps),
    }
}

fn machine(nodes: usize) -> Machine {
    let mut machine = Machine::example();
    if nodes == 3 {
        let mut third = machine.cores[1];
        third.hw_id = 4;
        machine.cores.push(third);
    }
    machine.membership.stale_ms = 10;
    machine.membership.stuck_ms = 10;
    machine.membership.sweep_ms = 100;
    machine
}

/// `nodes` nodes, the first thread of each with a small budget, and a reply
/// object in slot 99 of each start-up space.
fn boot(nodes: usize) -> (System, Vec<ObjId>) {
    let (mut sys, t) = System::boot(&machine(nodes)).unwrap();
    for node in 0..nodes as u16 {
        let call = Syscall::SchedConfigure {
            sched: s(START_SLOT_SCHED),
            core: core(node.into()),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        };
        assert_eq!(sys.apply(node, t[node as usize], call), DONE);
        assert_eq!(sys.apply(node, t[node as usize], retype(Reply, 0, 99)), DONE);
    }
    (sys, t)
}

/// A second thread on `node`, in the start-up spaces, runnable, with its own
/// context; its objects take slots `slot`, `spare` and `spare - 1`.
fn thread(sys: &mut System, t: &[ObjId], node: u16, slot: u32, spare: u32) -> ObjId {
    let first = t[node as usize];
    let calls = [
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
        Syscall::SchedBind {
            sched: s(spare - 1),
            thread: s(slot),
        },
        Syscall::ThreadResume(s(slot)),
    ];
    for call in calls {
        assert_eq!(sys.apply(node, first, call), DONE);
    }
    sys.node(node).object_at(first, s(slot)).unwrap()
}

/// Delivers the oldest message in flight that `wanted` matches. Ring order
/// is enforced by `deliver`.
fn deliver(sys: &mut System, wanted: impl Fn(&Body) -> bool) {
    let index = sys.find(wanted).expect("a message in flight");
    sys.deliver(index);
}

fn refused(sys: &System, node: u16) -> usize {
    sys.node(node)
        .ring(false)
        .iter()
        .filter(|e| e.code() == TraceCode::Refused as u16)
        .count()
}

/// Node 0 makes a frame in `parent`, derives it into `parent + 1`, and
/// moves that child to node 1's slot `got` by the first thread of node 0;
/// node 1 maps it at `address`. The anchor of the grant is a child of
/// `parent`.
fn grant_mapped(sys: &mut System, t: &[ObjId], to: u16, parent: u32, got: u32, address: u64) {
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, parent)), DONE);
    let derive = Syscall::CapDerive {
        source: s(parent),
        destination: s(parent + 1),
        rights: Rights::READ.bits(),
        badge: 0,
    };
    assert_eq!(sys.apply(0, t[0], derive), DONE);
    assert_eq!(sys.apply(to, t[to as usize], recv_into(got)), WAITS);
    assert_eq!(
        sys.apply(0, t[0], send(to.into(), vec![Transfer::Move(s(parent + 1))])),
        WAITS
    );
    sys.settle(32);
    assert_eq!(sys.check(), Ok(()));
    assert_eq!(sys.apply(to, t[to as usize], map(got, address)), DONE);
}

// F1 -------------------------------------------------------------------

/// F1 (1), in ring order. Node 0 revokes a frame node 1 maps (grant 0,
/// serial 0); node 1 deletes its remote capability first; a transfer that
/// node 0 sent before the revocation reaches node 1 before the request to
/// remove, so on ring 1 -> 0 the release, the ask for grants and the
/// revocation step follow each other. The release frees grant 0, the ask
/// reuses it (serial 1) for a new frame that node 1 maps, and the old
/// revocation step frees that live, mapped grant. Node 0 then destroys the
/// frame while node 1 still translates it.
#[test]
fn f1_revoke_step_frees_a_reused_grant_in_ring_order() {
    let (mut sys, t) = boot(2);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    let revoker = thread(&mut sys, &t, 0, 201, 3998);
    let deleter = thread(&mut sys, &t, 1, 200, 4000);
    grant_mapped(&mut sys, &t, 1, 100, 110, AT);
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 0)));

    // A second frame, whose derived child the sender moves to node 1.
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 120)), DONE);
    let derive = Syscall::CapDerive {
        source: s(120),
        destination: s(121),
        rights: Rights::READ.bits(),
        badge: 0,
    };
    assert_eq!(sys.apply(0, t[0], derive), DONE);
    assert_eq!(sys.apply(1, t[1], recv_into(111)), WAITS);
    assert_eq!(
        sys.apply(0, sender, send(1, vec![Transfer::Move(s(121))])),
        WAITS
    );
    // Then the revocation of the first frame: ring 0 -> 1 holds the
    // request, then the revocation.
    assert_eq!(sys.apply(0, revoker, Syscall::CapRevoke(s(100))), WAITS);
    // Node 1 deletes its remote capability: ring 1 -> 0 holds the release.
    assert_eq!(sys.apply(1, deleter, Syscall::CapDelete(s(110))), DONE);

    deliver(&mut sys, |b| matches!(b, Body::Request { .. })); // ask queued
    deliver(&mut sys, |b| matches!(b, Body::Revoke { .. })); // step queued
    deliver(&mut sys, |b| matches!(b, Body::Release { .. }));
    assert_eq!(sys.node(0).grant_entry(0), None);
    deliver(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 1)));
    deliver(&mut sys, |b| matches!(b, Body::TransferGrant { .. }));
    assert_eq!(sys.apply(1, deleter, map(111, AT2)), DONE);
    assert_eq!(sys.check(), Ok(()));

    // The revocation step of the first grant arrives last on its ring.
    deliver(&mut sys, |b| matches!(b, Body::RevokeStep { .. }));
    assert_eq!(sys.node(0).grant_entry(0), None, "a live, mapped grant freed");
    assert_eq!(sys.check(), Err("node 1: 58: translation under no grant".into()));
    // Node 0 destroys the second frame: its anchor has no entry any more.
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(120))), DONE);
    assert_eq!(sys.node(0).object_at(t[0], s(120)), None);
    assert_eq!(
        sys.node(1).translated(deleter, AT2),
        Some(Rights::READ),
        "node 1 still translates a frame node 0 destroyed"
    );
}

/// F1 (2), in ring order, with no deletion by the holder: the holder
/// answers the request to remove with its release and its step on the same
/// ring; between the two, an ask of a third node reuses the freed entry, and
/// the step is refused. The revoking thread never wakes.
#[test]
fn f1_revoke_step_refused_after_reuse_for_a_third_node_strands_the_revoker() {
    let (mut sys, t) = boot(3);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    let revoker = thread(&mut sys, &t, 0, 201, 3998);
    grant_mapped(&mut sys, &t, 1, 100, 110, AT);
    // A notify for node 2: its ask waits on ring 2 -> 0.
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 130)), DONE);
    assert_eq!(sys.apply(2, t[2], recv_into(110)), WAITS);
    assert_eq!(
        sys.apply(0, sender, send(2, vec![Transfer::Derive(s(130), Rights::ALL.bits())])),
        WAITS
    );
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    assert!(sys.find(|b| matches!(b, Body::TransferAsk { .. })).is_some());

    assert_eq!(sys.apply(0, revoker, Syscall::CapRevoke(s(100))), WAITS);
    deliver(&mut sys, |b| matches!(b, Body::Revoke { .. }));
    // Ring 1 -> 0: release, then step (done).
    deliver(&mut sys, |b| matches!(b, Body::Release { .. }));
    deliver(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((2, 1)));
    let before = refused(&sys, 0);
    deliver(&mut sys, |b| matches!(b, Body::RevokeStep { .. }));
    assert_eq!(refused(&sys, 0), before + 1);
    sys.run(sys.now() + 2_000 * MS, MS);
    assert_eq!(sys.node(0).woken(revoker), None, "the revoker waits for ever");
    assert_eq!(sys.member(1).state(), MemberState::Live);
}

/// F1 (3): the late request to remove cannot meet a reused grant on its
/// holder. A re-grant of the same entry to the same holder is a
/// `TransferGrant` sent after the `Revoke`, on the same ring, so the
/// `Revoke` arrives first, finds nothing and answers `done`. (Here the step
/// then frees the reused entry, which is F1 (1) again.)
#[test]
fn f1_late_revoke_arrives_before_any_regrant_on_its_ring() {
    let (mut sys, t) = boot(2);
    let revoker = thread(&mut sys, &t, 0, 201, 3998);
    let deleter = thread(&mut sys, &t, 1, 200, 4000);
    grant_mapped(&mut sys, &t, 1, 100, 110, AT);
    assert_eq!(sys.apply(0, revoker, Syscall::CapRevoke(s(100))), WAITS);
    assert_eq!(sys.apply(1, deleter, Syscall::CapDelete(s(110))), DONE);
    deliver(&mut sys, |b| matches!(b, Body::Release { .. }));
    assert_eq!(sys.node(0).grant_entry(0), None);
    // The re-grant of entry 0 to node 1 is sent after the Revoke.
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 120)), DONE);
    assert_eq!(sys.apply(1, t[1], recv_into(111)), WAITS);
    assert_eq!(sys.apply(0, t[0], send(1, vec![Transfer::Move(s(120))])), WAITS);
    // Delivering the Request first would break ring order.
    let early = catch_unwind(AssertUnwindSafe(|| {
        let mut copy = sys.clone();
        deliver(&mut copy, |b| matches!(b, Body::Request { .. }));
    }));
    assert!(early.is_err(), "the request is behind the revocation");
    let before = refused(&sys, 1);
    deliver(&mut sys, |b| matches!(b, Body::Revoke { .. }));
    assert_eq!(refused(&sys, 1), before, "the Revoke is not refused");
    assert!(sys.find(|b| matches!(b, Body::RevokeStep { done: true, .. })).is_some());
}

/// F1 (4): a release that crosses an immediate free is traced as refused;
/// the contract asks for it (a release only from the grantee the entry
/// names, with that serial; a message that fails its check is traced).
#[test]
fn f1_release_after_an_immediate_free_is_traced_as_the_contract_asks() {
    let (mut sys, t) = boot(2);
    let deleter = thread(&mut sys, &t, 1, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    assert_eq!(sys.apply(1, t[1], recv_into(110)), WAITS);
    assert_eq!(
        sys.apply(0, t[0], send(1, vec![Transfer::Derive(s(100), Rights::ALL.bits())])),
        WAITS
    );
    sys.settle(32);
    // Not mapped: the revocation frees the entry at once.
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(100))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);
    assert_eq!(sys.apply(1, deleter, Syscall::CapDelete(s(110))), DONE);
    let before = refused(&sys, 0);
    deliver(&mut sys, |b| matches!(b, Body::Release { .. }));
    assert_eq!(refused(&sys, 0), before + 1);
    assert_eq!(sys.check(), Ok(()));
}

// F2 -------------------------------------------------------------------

/// F2 (1): the model has no window between `core_place` and the move of a
/// live node: the node runs on its new core at its next event, and its old
/// core is left running with no node placed on it, never parked. The fence
/// of a later kill aims at the new core, where the node runs in the model.
#[test]
fn f2_core_place_moves_a_live_node_at_once_and_leaves_its_old_core_running() {
    let (mut sys, t) = boot(3);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace { core: core(1), physical: 2 }),
        DONE
    );
    assert!(sys.runs(1));
    assert_eq!(sys.core(1), CoreState::Running);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_KILL }),
        DONE
    );
    sys.run(sys.now() + 100 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Dead);
    // Node 2 shared core 2 and holds unit role 1: accused with host, as
    // the rule after a confirmed stop says.
    assert_eq!(sys.member(2).evidence(), Evidence::Host);
    assert_eq!(sys.core(1), CoreState::Running, "a core with no node, never parked");
}

/// F2 (2): `core_stop` retire of a sealed node placed on a core that runs
/// another node marks that core unusable and changes nothing else: the
/// other node stays live and running.
#[test]
fn f2_retire_of_a_parked_node_marks_its_placed_core_and_stops_nothing() {
    let (mut sys, t) = boot(3);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_SEAL }),
        DONE
    );
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Sealed);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace { core: core(1), physical: 2 }),
        DONE
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop { core: core(1), mode: CORE_STOP_RETIRE }),
        DONE
    );
    sys.run(sys.now() + 100 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Dead);
    assert_eq!(sys.member(2).state(), MemberState::Live);
    assert!(sys.runs(2));
    let Ok(Output::Status(words)) = sys.apply(0, t[0], Syscall::CoreStatus(core(2))) else {
        panic!("a status");
    };
    assert_ne!(words[1] & CORE_STATUS_UNUSABLE, 0, "core 2 is marked unusable");
}

// F3 -------------------------------------------------------------------

/// Node 0's objects granted to node 1 with every right, one transfer each,
/// into node 1's slots `first`, `first + 1`...: grants 0, 1... in order.
fn grant_all(sys: &mut System, t: &[ObjId], to: u16, sources: &[u32], first: u32) {
    for (i, &source) in sources.iter().enumerate() {
        assert_eq!(sys.apply(to, t[to as usize], recv_into(first + i as u32)), WAITS);
        let caps = vec![Transfer::Derive(s(source), Rights::ALL.bits())];
        assert_eq!(sys.apply(0, t[0], send(to.into(), caps)), WAITS);
        sys.settle(32);
    }
}

/// Node 1's thread to move, in slot 140, suspended, with its own context in
/// slot 142 configured for cores 0 and 1, and RAX = 0xABCD.
fn mover(sys: &mut System, t: &[ObjId]) {
    let calls = [
        retype(Thread, 0, 140),
        retype(Frame, 1, 141),
        Syscall::ThreadConfigure {
            thread: s(140),
            cspace: s(START_SLOT_CSPACE),
            aspace: ASPACE,
            fault: SlotAddr::NONE,
            page: s(141),
        },
        retype(Sched, 0, 142),
        Syscall::SchedConfigure {
            sched: s(142),
            core: core(1),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        },
        Syscall::SchedSetCores {
            sched: s(142),
            core: core(1),
            window: 0,
            mask: 0b11,
        },
        Syscall::SchedBind {
            sched: s(142),
            thread: s(140),
        },
    ];
    for call in calls {
        assert_eq!(sys.apply(1, t[1], call), DONE);
    }
    let mut block = vec![0; x86_64::REGS_WORDS];
    block[x86_64::REG_RFLAGS] = x86_64::RFLAGS_FIXED;
    block[x86_64::REG_RAX] = 0xABCD;
    let write = Syscall::ThreadWriteRegs {
        thread: s(140),
        block,
    };
    assert_eq!(sys.apply(1, t[1], write), DONE);
}

fn rax(sys: &mut System, t: &[ObjId], slot: u32) -> u64 {
    let Ok(Output::Regs(block)) = sys.apply(0, t[0], Syscall::ThreadReadRegs(s(slot))) else {
        panic!("registers");
    };
    block[x86_64::REG_RAX]
}

/// The common start of the two F3 (1) tests: node 0's thread 150 and sched
/// 151 granted to node 1 (grants 0 and 1, slots 110 and 111); an object of
/// `kind` in node 0's slot 152 on its way to node 1 (its ask waits on ring
/// 1 -> 0); then node 1's move, behind the ask on the same ring; then node
/// 0 revokes the destination thread's grant, which nobody maps: freed at
/// once. Returns node 1's calling thread.
fn stale_move(sys: &mut System, t: &[ObjId], kind: ObjectKind) -> ObjId {
    let sender = thread(sys, t, 0, 200, 4000);
    let caller = thread(sys, t, 1, 200, 4000);
    mover(sys, t);
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 150)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 151)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(kind, 0, 152)), DONE);
    grant_all(sys, t, 1, &[150, 151], 110);
    assert_eq!(sys.node(0).grant_entry(0).map(|e| e.2), Some(0));
    assert_eq!(sys.apply(1, t[1], recv_into(112)), WAITS);
    let caps = vec![Transfer::Derive(s(152), Rights::ALL.bits())];
    assert_eq!(sys.apply(0, sender, send(1, caps)), WAITS);
    deliver(sys, |b| matches!(b, Body::Request { .. }));
    let call = Syscall::ThreadMove {
        thread: s(140),
        destination: s(110),
        sched: s(111),
        core: core(0),
        budget: 0,
        period: 0,
        class: 0,
    };
    assert_eq!(sys.apply(1, caller, call), WAITS);
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(150))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);
    deliver(sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 1)));
    caller
}

/// F3 (1), in ring order: the move names grant 0 without its serial; the
/// grant was revoked (freed at once, nothing mapped it) and reused for
/// another thread granted to the same node; the move lands in that thread.
#[test]
fn f3_stale_move_lands_in_a_thread_granted_after_its_destination_was_revoked() {
    let (mut sys, t) = boot(2);
    let caller = stale_move(&mut sys, &t, Thread);
    deliver(&mut sys, |b| matches!(b, Body::Move { .. }));
    sys.settle(32);
    assert_eq!(sys.node(1).woken(caller), Some(&DONE));
    assert_eq!(rax(&mut sys, &t, 152), 0xABCD, "the state went into thread 152");
    assert_ne!(rax(&mut sys, &t, 150), 0xABCD);
    assert_eq!(sys.check(), Ok(()));
}

/// F3 (1), sibling: reused for an object of another kind, the stale move
/// panics the model (`threads[&target]` in `place_move`).
#[test]
fn f3_stale_move_onto_a_reused_grant_of_another_kind_panics_the_model() {
    let (mut sys, t) = boot(2);
    stale_move(&mut sys, &t, Notify);
    let result = catch_unwind(AssertUnwindSafe(|| {
        deliver(&mut sys, |b| matches!(b, Body::Move { .. }));
    }));
    assert!(result.is_err(), "place_move panics on a notify");
}

/// F3 (2), in ring order: a call on a remote notify carries the anchor's
/// index without the serial. While it is in flight, node 0 revokes that
/// grant (freed at once) and reuses the entry for another notify granted to
/// node 2; the call signals node 2's notify, which node 1 was never given.
#[test]
fn f3_stale_request_signals_an_object_granted_to_a_third_node() {
    let (mut sys, t) = boot(3);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 160)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 161)), DONE);
    grant_all(&mut sys, &t, 1, &[160], 110);
    assert_eq!(sys.apply(2, t[2], recv_into(110)), WAITS);
    let caps = vec![Transfer::Derive(s(161), Rights::ALL.bits())];
    assert_eq!(sys.apply(0, sender, send(2, caps)), WAITS);
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    // Node 1 signals its remote notify: a request on ring 1 -> 0.
    assert_eq!(sys.apply(1, t[1], Syscall::Signal(s(110))), WAITS);
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(160))), DONE);
    deliver(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((2, 1)));
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    sys.settle(32);
    assert_eq!(sys.node(1).woken(t[1]), Some(&DONE));
    assert_eq!(sys.apply(0, t[0], Syscall::Poll(s(160))), Err(Error::WouldWait));
    assert_eq!(
        sys.apply(0, t[0], Syscall::Poll(s(161))),
        Ok(Output::Word(1)),
        "node 2's notify was signalled by node 1"
    );
}

/// F3 (3): a grant revoked while its `TransferGrant` is in flight lands as
/// a remote capability that is invalid from the start: its first use is
/// `gone`, as after any revocation; every invariant holds.
#[test]
fn f3_a_grant_revoked_in_flight_lands_invalid_and_its_use_is_gone() {
    let (mut sys, t) = boot(2);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 170)), DONE);
    assert_eq!(sys.apply(1, t[1], recv_into(110)), WAITS);
    let caps = vec![Transfer::Derive(s(170), Rights::ALL.bits())];
    assert_eq!(sys.apply(0, sender, send(1, caps)), WAITS);
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    deliver(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(170))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);
    deliver(&mut sys, |b| matches!(b, Body::TransferGrant { .. }));
    assert_eq!(sys.check(), Ok(()));
    assert_eq!(sys.apply(1, t[1], Syscall::Signal(s(110))), Err(Error::Gone));
    sys.settle(32);
    assert_eq!(sys.check(), Ok(()));
}

// F4 -------------------------------------------------------------------

fn stop(sys: &mut System, t: &[ObjId], by: u16, node: u32, mode: u64) -> Outcome {
    sys.apply(by, t[by as usize], Syscall::CoreStop { core: core(node), mode })
}

fn resume(sys: &mut System, t: &[ObjId], by: u16, node: u32) -> Outcome {
    let call = Syscall::CoreStart {
        core: core(node),
        mode: CORE_START_RESUME,
        image: 0,
        module: 0,
    };
    sys.apply(by, t[by as usize], call)
}

/// F4 (1): node 1 waits on a notify of node 0 and has granted node 0 a
/// frame; node 1 is sealed; node 0 is killed and becomes dead; node 1 is
/// resumed. Resume runs only R2 (contract: "removes its remote capabilities
/// whose use entry records a generation ... that is over"), so the wait on
/// node 0 never ends and the grant to node 0's dead generation stays live.
/// The same wait on a live node 1 ends with `gone` (control).
#[test]
fn f4_a_resumed_node_never_ends_a_wait_on_a_node_that_died_while_it_was_sealed() {
    let (mut sys, t) = boot(3);
    let waiter = thread(&mut sys, &t, 1, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 160)), DONE);
    grant_all(&mut sys, &t, 1, &[160], 110);
    // Node 1 grants node 0 a frame.
    assert_eq!(sys.apply(1, t[1], retype(Frame, 1, 120)), DONE);
    assert_eq!(sys.apply(0, t[0], recv_into(130)), WAITS);
    assert_eq!(sys.apply(1, t[1], send(0, vec![Transfer::Move(s(120))])), WAITS);
    sys.settle(32);
    assert_eq!(sys.node(1).grant_entry(0).map(|e| e.0), Some(0));
    assert_eq!(sys.apply(1, waiter, Syscall::Wait(s(110), 0)), WAITS);
    sys.settle(32);
    let mut control = sys.clone();

    assert_eq!(stop(&mut sys, &t, 2, 1, CORE_STOP_SEAL), DONE);
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Sealed);
    assert_eq!(stop(&mut sys, &t, 2, 0, CORE_STOP_KILL), DONE);
    sys.run(sys.now() + 200 * MS, MS / 10);
    assert_eq!(sys.member(0).state(), MemberState::Dead);
    assert_eq!(resume(&mut sys, &t, 2, 1), DONE);
    sys.run(sys.now() + 2_000 * MS, MS);
    assert_eq!(sys.member(1).state(), MemberState::Live);
    assert_eq!(sys.node(1).woken(waiter), None, "the wait on dead node 0 never ends");
    let entry = sys.node(1).grant_entry(0).expect("still used");
    assert_eq!(entry.0, 0, "a grant to node 0's dead generation stays");
    assert_eq!(sys.check(), Ok(()));

    assert_eq!(stop(&mut control, &t, 2, 0, CORE_STOP_KILL), DONE);
    control.run(control.now() + 200 * MS, MS / 10);
    assert_eq!(control.node(1).woken(waiter), Some(&Err(Error::Gone)));
    assert_eq!(control.node(1).grant_entry(0), None);
}

/// F4 (2): a sealed node resumed on a core that runs a node holding no
/// unit role, then killed: the stop of that core seals the other node, its
/// save seal valid (each event of a node on a shared core loads its block
/// and keeps the others' seals valid). The review's host kill came from the
/// unit roles node 2 held, which the contract asks for.
#[test]
fn f4_kill_after_a_cohosted_resume_seals_the_other_node_not_host() {
    let (mut sys, t) = boot(3);
    assert_eq!(stop(&mut sys, &t, 0, 1, CORE_STOP_SEAL), DONE);
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Sealed);
    // Node 0 holds no unit role.
    for role in 0..sys.node_count_roles() {
        let word = sys.role(role);
        assert!(word.state() == RoleState::Vacant || word.holder() != 0);
    }
    assert_eq!(
        sys.apply(2, t[2], Syscall::CorePlace { core: core(1), physical: 0 }),
        DONE
    );
    assert_eq!(resume(&mut sys, &t, 2, 1), DONE);
    assert_eq!(sys.member(1).state(), MemberState::Live);
    assert_eq!(stop(&mut sys, &t, 2, 1, CORE_STOP_KILL), DONE);
    sys.run(sys.now() + 200 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Dead);
    assert_eq!(sys.member(0).state(), MemberState::Sealed);
    assert_eq!(sys.member(0).evidence(), Evidence::None);
}

/// F4 (3): two nodes; the holder of a unit role is sealed and hands it to
/// the other, which hangs before step 5. Nobody accuses it: the sealing
/// node is not live, and the transition to fencing is made by "any live
/// node". The contract states this loss ("the last node is lost only by its
/// own failure, and then the machine is lost").
#[test]
fn f4_a_sealing_node_cannot_accuse_the_last_live_node_as_the_contract_says() {
    let (mut sys, t) = boot(2);
    let holder = sys.role(0).holder();
    let other = 1 - holder;
    assert_eq!(stop(&mut sys, &t, other, holder.into(), CORE_STOP_SEAL), DONE);
    sys.hang(other, true);
    sys.run(sys.now() + 2_000 * MS, MS);
    assert_eq!(sys.member(other).state(), MemberState::Live);
    assert_eq!(sys.member(holder).state(), MemberState::Sealing);
}

/// F4 (4c): `evidence` accuses a starting node with stale after
/// `STALE_NS`, not `START_NS`; but in the model a start completes in the
/// event that makes it, so no node is ever seen starting.
#[test]
fn f4_a_start_completes_in_one_event_so_starting_is_never_observed() {
    let (mut sys, t) = boot(3);
    assert_eq!(stop(&mut sys, &t, 0, 1, CORE_STOP_KILL), DONE);
    sys.run(sys.now() + 200 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Dead);
    let call = Syscall::CoreStart {
        core: core(1),
        mode: CORE_START_FRESH,
        image: 0,
        module: 0,
    };
    assert_eq!(sys.apply(0, t[0], call), DONE);
    assert_eq!(sys.member(1).state(), MemberState::Live);
}

/// The text of a caught panic.
fn panic_text(result: std::thread::Result<()>) -> String {
    let error = result.expect_err("a panic");
    error
        .downcast_ref::<String>()
        .cloned()
        .or_else(|| error.downcast_ref::<&str>().map(|s| s.to_string()))
        .unwrap_or_default()
}

// F5 -------------------------------------------------------------------

/// F5 (1), in ring order: a `send` that lists a capability holds no wait on
/// the receiving node; its thread is destroyed after the request arrived
/// and before the ask for grants comes back. The contract: "A request that
/// holds no wait there completes without the thread ... its answer changes
/// what it would have changed except the thread's own state". The model
/// forgets the request and the receiver gets `caps_dropped`.
#[test]
fn f5_a_send_whose_thread_is_destroyed_drops_its_capabilities() {
    let (mut sys, t) = boot(2);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    assert_eq!(sys.apply(1, t[1], recv_into(110)), WAITS);
    let caps = vec![Transfer::Derive(s(100), Rights::ALL.bits())];
    assert_eq!(sys.apply(0, sender, send(1, caps)), WAITS);
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(200))), DONE);
    sys.settle(32);
    let Some(Ok(Output::Message(delivery))) = sys.node(1).woken(t[1]) else {
        panic!("a delivery");
    };
    let header = delivery.received.header;
    assert_eq!(header.caps(), 0);
    assert_ne!(header.flags() & Header::FLAG_CAPS_DROPPED, 0);
    assert_eq!(sys.node(0).grant_entry(0), None);
}

// F6 -------------------------------------------------------------------

/// F6 (1): the answer and the refusal of a transfer leave the receiver on
/// the same ring, refusal first, so the answer cannot overtake it (shown by
/// ring order). The same loss is reached in ring order by another thread of
/// the sender's space: from the ask on, the moved capability is in the
/// anchor and its slot is empty; a second thread fills the slot; the
/// refusal then frees the grant and leaves the capability in the kernel's
/// own space, reachable by no one.
#[test]
fn f6_a_refused_move_whose_slot_was_refilled_strands_the_capability() {
    let (mut sys, t) = boot(2);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    let moved = sys.node(0).object_at(t[0], s(100)).unwrap();
    let recv = Syscall::Recv {
        endpoint: MAILBOX,
        reply: s(99),
        range: Range::NONE,
        wait: 0,
    };
    assert_eq!(sys.apply(1, t[1], recv), WAITS);
    assert_eq!(sys.apply(0, sender, send(1, vec![Transfer::Move(s(100))])), WAITS);
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    deliver(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.node(0).object_at(t[0], s(100)), None, "the slot is empty");
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    deliver(&mut sys, |b| matches!(b, Body::TransferGrant { .. }));
    // Ring 1 -> 0: the refusal, then the answer.
    let order: Vec<bool> = sys
        .pending()
        .iter()
        .filter(|p| p.from == 1 && p.to == 0)
        .map(|p| matches!(p.body, Body::Refused { .. }))
        .collect();
    assert_eq!(order, [true, false]);
    sys.settle(32);
    assert_eq!(
        sys.node(0).woken(sender),
        Some(&Ok(Output::Sent { flags: Header::FLAG_CAPS_DROPPED }))
    );
    assert_eq!(sys.node(0).grant_entry(0), None);
    assert_ne!(sys.node(0).object_at(t[0], s(100)), Some(moved));
    assert_eq!(sys.check(), Ok(()), "no invariant sees the stranded capability");
    // The next grant takes entry 0, whose anchor slot still holds it.
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 101)), DONE);
    let recv = recv_into(110);
    assert_eq!(sys.apply(1, t[1], recv), WAITS);
    let caps = vec![Transfer::Derive(s(101), Rights::ALL.bits())];
    assert_eq!(sys.apply(0, sender, send(1, caps)), WAITS);
    sys.settle(32);
    assert_eq!(sys.check(), Err("node 0: 6: slot of a capability".into()));
}

/// F6 (2), in ring order: two moved capabilities refused at delivery;
/// before the refusal arrives, the sender revokes the parent of the first
/// (its grant, held by nobody, is freed at once). The refusal names both
/// grants; `misdirected` requires all to match and refuses the whole
/// message, so the second capability stays in its anchor, its grant live,
/// for ever.
#[test]
fn f6_a_refusal_naming_one_freed_grant_strands_the_other_moved_capability() {
    let (mut sys, t) = boot(2);
    let sender = thread(&mut sys, &t, 0, 200, 4000);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    let derive = Syscall::CapDerive {
        source: s(100),
        destination: s(101),
        rights: Rights::ALL.bits(),
        badge: 0,
    };
    assert_eq!(sys.apply(0, t[0], derive), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 102)), DONE);
    let recv = Syscall::Recv {
        endpoint: MAILBOX,
        reply: s(99),
        range: Range::NONE,
        wait: 0,
    };
    assert_eq!(sys.apply(1, t[1], recv), WAITS);
    let caps = vec![Transfer::Move(s(101)), Transfer::Move(s(102))];
    assert_eq!(sys.apply(0, sender, send(1, caps)), WAITS);
    deliver(&mut sys, |b| matches!(b, Body::Request { .. }));
    deliver(&mut sys, |b| matches!(b, Body::TransferAsk { .. }));
    assert_eq!(sys.apply(0, t[0], Syscall::CapRevoke(s(100))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);
    let before = refused(&sys, 0);
    sys.settle(32);
    assert_eq!(refused(&sys, 0), before + 1);
    assert_eq!(sys.node(0).grant_entry(1).map(|e| (e.0, e.3)), Some((1, 0)));
    assert_eq!(sys.node(0).object_at(t[0], s(102)), None);
    sys.run(sys.now() + 1_000 * MS, MS);
    assert_eq!(sys.node(0).grant_entry(1).map(|e| (e.0, e.3)), Some((1, 0)));
    assert_eq!(sys.check(), Ok(()));
}

// F7 -------------------------------------------------------------------

/// Node 1 gets node 0's object of `kind` (made in node 0's slot 100) in its
/// slot 110, with every right.
fn remote_of(kind: ObjectKind, size: u64) -> (System, Vec<ObjId>) {
    let (mut sys, t) = boot(2);
    assert_eq!(sys.apply(0, t[0], retype(kind, size, 100)), DONE);
    grant_all(&mut sys, &t, 1, &[100], 110);
    (sys, t)
}

/// F7 (1): `cap_derive` and `untyped_retype` whose destination is in a
/// capability space of another node (contract: they make a grant) panic the
/// model.
#[test]
fn f7_a_destination_in_a_remote_cspace_panics_the_model() {
    let size = u64::from(CSPACE_SEGMENT_SLOTS);
    let derive = catch_unwind(AssertUnwindSafe(|| {
        let (mut sys, t) = remote_of(CSpace, size);
        assert_eq!(sys.apply(1, t[1], retype(Notify, 0, 120)), DONE);
        let call = Syscall::CapDerive {
            source: s(120),
            destination: SlotAddr::through(110, 1),
            rights: Rights::ALL.bits(),
            badge: 0,
        };
        let _ = sys.apply(1, t[1], call);
    }));
    let text = panic_text(derive);
    assert!(!text.contains("ring order"), "{text}");
    let made = catch_unwind(AssertUnwindSafe(|| {
        let (mut sys, t) = remote_of(CSpace, size);
        let call = Syscall::UntypedRetype {
            untyped: UT,
            kind: Notify,
            size: 0,
            page: PageSize::Page as u64,
            memory: 0,
            destination: SlotAddr::through(110, 1),
        };
        let _ = sys.apply(1, t[1], call);
    }));
    let text = panic_text(made);
    assert!(!text.contains("ring order"), "{text}");
}

/// F7 (2): a call on a local object whose other capability argument is a
/// remote capability (an object of another node): `invalid` by the
/// contract. Each call below is tried on a fresh machine; the test prints
/// which of them panic and asserts that `sched_bind` does.
#[test]
fn f7_a_remote_secondary_argument_of_a_local_call_panics_or_not() {
    type Case = (&'static str, ObjectKind, fn() -> Vec<Syscall>);
    let cases: [Case; 5] = [
        ("task_attach, remote task", ObjectKind::Task, || {
            vec![
                retype(Thread, 0, 120),
                Syscall::TaskAttach {
                    thread: s(120),
                    task: s(110),
                },
            ]
        }),
        ("sched_bind", Thread, || {
            vec![
                retype(Sched, 0, 120),
                Syscall::SchedBind {
                    sched: s(120),
                    thread: s(110),
                },
            ]
        }),
        ("notify_bind", ObjectKind::Endpoint, || {
            vec![
                retype(Notify, 0, 120),
                Syscall::NotifyBind {
                    notify: s(120),
                    endpoint: s(110),
                },
            ]
        }),
        ("task_attach, remote thread", Thread, || {
            vec![
                retype(ObjectKind::Task, 0, 120),
                Syscall::TaskAttach {
                    thread: s(110),
                    task: s(120),
                },
            ]
        }),
        ("timer_set", Notify, || {
            vec![
                retype(ObjectKind::Timer, 0, 120),
                Syscall::TimerSet {
                    timer: s(120),
                    notify: s(110),
                    deadline: 1,
                    tolerance: 0,
                },
            ]
        }),
    ];
    let mut panics = Vec::new();
    for (name, kind, calls) in cases {
        let result = catch_unwind(AssertUnwindSafe(|| {
            let (mut sys, t) = remote_of(kind, 0);
            let mut last = DONE;
            for call in calls() {
                last = sys.apply(1, t[1], call);
            }
            last
        }));
        match result {
            Ok(outcome) => eprintln!("F7 {name}: {outcome:?}"),
            Err(_) => {
                eprintln!("F7 {name}: panic");
                panics.push(name);
            }
        }
    }
    assert!(panics.contains(&"sched_bind"));
}

// F8 -------------------------------------------------------------------

/// F8, in ring order: node 0's attach goes to node 1, the unit's holder,
/// which hands the role to node 2 before the request arrives and refuses
/// it; node 0 reads a handing word and keeps `sent_to` = node 1; node 2
/// takes the role and hands it back to node 1 before node 0's recovery
/// runs; the role word names node 1 again, which `roles_unit` takes for the
/// holder it already asked: the request is never sent again.
#[test]
fn f8_a_unit_request_is_lost_when_the_role_comes_back_to_the_node_asked() {
    let (mut sys, t) = boot(3);
    let attacher = thread(&mut sys, &t, 0, 200, 4000);
    assert_eq!(sys.role(0).holder(), 1);
    // An iospace may take several steps (`again`) on larger pages.
    let made = (0..64).map(|_| sys.apply(0, t[0], retype(IoSpace, 0, 100))).find(|o| *o != Err(Error::Again));
    assert_eq!(made, Some(DONE));
    let attach = Syscall::IoSpaceAttach {
        iommu: s(IOMMU),
        iospace: s(100),
        device: 0x22,
    };
    assert_eq!(sys.apply(0, attacher, attach), WAITS);
    let hand = |to: u32| Syscall::RoleHand {
        role: s(ROLE_0),
        core: core(to),
    };
    assert!(matches!(sys.apply(1, t[1], hand(2)), Ok(Output::Epoch(_))));
    deliver(&mut sys, |b| matches!(b, Body::UnitRequest { .. }));
    deliver(&mut sys, |b| matches!(b, Body::UnitAnswer { done: false, .. }));
    deliver(&mut sys, |b| matches!(b, Body::Handed { .. }));
    assert_eq!(sys.role(0).holder(), 2);
    assert_eq!(sys.role(0).state(), RoleState::Held);
    assert!(matches!(sys.apply(2, t[2], hand(1)), Ok(Output::Epoch(_))));
    deliver(&mut sys, |b| matches!(b, Body::Handed { .. }));
    assert_eq!(sys.role(0).holder(), 1);
    assert_eq!(sys.role(0).state(), RoleState::Held);
    sys.run(sys.now() + 2_000 * MS, MS);
    assert_eq!(sys.node(0).woken(attacher), None, "the attach waits for ever");
    assert!(sys.find(|b| matches!(b, Body::UnitRequest { .. })).is_none());
}

// F9 -------------------------------------------------------------------

/// F9: `thread_resume` of the source during a move that succeeds leaves it
/// not suspended, its own context unbound and not configured: what the
/// contract says ("stays suspended (unless thread_resume cleared it
/// meanwhile), and its own context is unbound, made not configured ... so
/// it cannot run"). `sched_count` on its context during the move succeeds,
/// as the contract says ("No state error").
#[test]
fn f9_resume_during_a_successful_move_is_what_the_contract_says() {
    let (mut sys, t) = boot(2);
    let caller = thread(&mut sys, &t, 1, 200, 4000);
    mover(&mut sys, &t);
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 150)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 151)), DONE);
    grant_all(&mut sys, &t, 1, &[150, 151], 110);
    let call = Syscall::ThreadMove {
        thread: s(140),
        destination: s(110),
        sched: s(111),
        core: core(0),
        budget: 0,
        period: 0,
        class: 0,
    };
    assert_eq!(sys.apply(1, caller, call), WAITS);
    assert_eq!(sys.apply(1, t[1], Syscall::ThreadResume(s(140))), DONE);
    let count = Syscall::SchedCount {
        sched: s(142),
        core: core(1),
        mode: 1,
    };
    assert_eq!(sys.apply(1, t[1], count), DONE);
    sys.settle(32);
    assert_eq!(sys.node(1).woken(caller), Some(&DONE));
    let source = sys.node(1).object_at(t[1], s(140)).unwrap();
    assert!(sys.node(1).runnable().contains(&source), "not suspended");
    let Ok(Output::SchedRead { state, .. }) = sys.apply(1, t[1], Syscall::SchedRead(s(142)))
    else {
        panic!("sched_read");
    };
    assert_eq!(state & SCHED_STATE_CONFIGURED, 0, "its context is not configured");
    assert_eq!(rax(&mut sys, &t, 150), 0xABCD);
    assert_eq!(sys.check(), Ok(()));
}

// F10 ------------------------------------------------------------------

/// F10 (1): the target of a hand-over may take the role (step 5) in its
/// recovery before the message of step 4 arrives; the late message then
/// fails the check the contract gives it ("only from the node the handing
/// word names as holder") and is traced: noise on a normal hand-over, as
/// the contract is written.
#[test]
fn f10_a_late_handed_message_is_traced_as_the_contract_is_written() {
    let (mut sys, t) = boot(3);
    let hand = Syscall::RoleHand {
        role: s(ROLE_0),
        core: core(2),
    };
    assert!(matches!(sys.apply(1, t[1], hand), Ok(Output::Epoch(_))));
    assert_eq!(sys.recover(64) > 0, true);
    assert_eq!(sys.role(0).holder(), 2);
    assert_eq!(sys.role(0).state(), RoleState::Held);
    let before = refused(&sys, 2);
    deliver(&mut sys, |b| matches!(b, Body::Handed { .. }));
    assert_eq!(refused(&sys, 2), before + 1);
}
```

## Appendix B: `model/src/verify_hydrogen_opus_unit.rs`

```rust
//! Verification of review 7 (gemini-hydrogen): what an integration test
//! cannot read (the context entries of a unit, the requests of a node).
//! A child of `system`, included by one line at the end of `system.rs`.

use super::*;
use crate::{Output, Range, Syscall};
use dodos_abi::{ObjectKind, PageSize, Rights, SlotAddr, START_SLOT_MAILBOX};

const DONE: Outcome = Ok(Output::Done);
const WAITS: Outcome = Ok(Output::Waits);

fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

fn retype(kind: ObjectKind, size: u64, destination: u32) -> Syscall {
    Syscall::UntypedRetype {
        untyped: s(25),
        kind,
        size,
        page: PageSize::Page as u64,
        memory: 0,
        destination: s(destination),
    }
}

fn three() -> (System, Vec<ObjId>) {
    let mut machine = Machine::example();
    let mut third = machine.cores[1];
    third.hw_id = 4;
    machine.cores.push(third);
    machine.membership.stale_ms = 10;
    machine.membership.stuck_ms = 10;
    machine.membership.sweep_ms = 100;
    let (mut sys, t) = System::boot(&machine).unwrap();
    for node in 0..3u16 {
        let call = Syscall::SchedConfigure {
            sched: s(dodos_abi::START_SLOT_SCHED),
            core: s(16 + u32::from(node)),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        };
        assert_eq!(sys.apply(node, t[node as usize], call), DONE);
    }
    (sys, t)
}

/// A second thread of node 0 in slot 200, runnable, with its own context.
fn helper(sys: &mut System, t: &[ObjId]) -> ObjId {
    let calls = [
        retype(ObjectKind::Thread, 0, 200),
        retype(ObjectKind::Frame, 1, 4000),
        Syscall::ThreadConfigure {
            thread: s(200),
            cspace: s(dodos_abi::START_SLOT_CSPACE),
            aspace: s(dodos_abi::START_SLOT_ASPACE),
            fault: SlotAddr::NONE,
            page: s(4000),
        },
        retype(ObjectKind::Sched, 0, 3999),
        Syscall::SchedConfigure {
            sched: s(3999),
            core: s(16),
            budget: 500_000,
            period: 10_000_000,
            class: 1,
        },
        Syscall::SchedBind {
            sched: s(3999),
            thread: s(200),
        },
        Syscall::ThreadResume(s(200)),
    ];
    for call in calls {
        assert_eq!(sys.apply(0, t[0], call), DONE);
    }
    sys.node(0).object_at(t[0], s(200)).unwrap()
}

/// The context entry of `device` on the unit of IOMMU object `iommu` of
/// node 0, as the machine table holds it.
fn entry(sys: &System, t: &[ObjId], device: u16) -> Option<(u16, u32)> {
    let model = sys.node(0);
    let iommu = model.object_at(t[0], s(19)).unwrap();
    let unit = model.iommus[&iommu].unit;
    let role = model.unit_role(unit).unwrap();
    let units = &model.table.units;
    units.get(&role).and_then(|u| u.entries.get(&device).copied())
}

/// New finding next to F5 (1): node 0 detaches a device while the unit's
/// role is handing, so its request waits on node 0; the thread is
/// destroyed, `unlink` forgets the request, and the context entry stays on
/// the unit, naming node 0, after the iospace it served is destroyed. The
/// contract: "A request that holds no wait there completes without the
/// thread". The control, with the thread kept, clears the entry.
#[test]
fn a_detach_whose_thread_is_destroyed_leaves_the_context_entry_on_the_unit() {
    let (mut sys, t) = three();
    let attacher = helper(&mut sys, &t);
    // An iospace may take several steps (`again`) on larger pages.
    let made = (0..64)
        .map(|_| sys.apply(0, t[0], retype(ObjectKind::IoSpace, 0, 100)))
        .find(|o| *o != Err(dodos_abi::Error::Again));
    assert_eq!(made, Some(DONE));
    let attach = Syscall::IoSpaceAttach {
        iommu: s(19),
        iospace: s(100),
        device: 0x22,
    };
    assert_eq!(sys.apply(0, attacher, attach), WAITS);
    sys.settle(32);
    assert_eq!(sys.node(0).woken(attacher), Some(&DONE));
    let g0 = sys.member(0).generation();
    assert_eq!(entry(&sys, &t, 0x22), Some((0, g0)));
    let role = sys.node(0).unit_role(0).unwrap();
    let holder = sys.role(role).holder();
    assert_ne!(holder, 0);
    let target = 3 - holder;
    let hand = Syscall::RoleHand {
        role: s(20 + role as u32),
        core: s(16 + u32::from(target)),
    };
    assert!(matches!(sys.apply(holder, t[holder as usize], hand), Ok(Output::Epoch(_))));
    assert_eq!(sys.role(role).state(), RoleState::Handing);
    let detach = Syscall::IoSpaceAttach {
        iommu: s(19),
        iospace: SlotAddr::NONE,
        device: 0x22,
    };
    assert_eq!(sys.apply(0, attacher, detach), WAITS);
    let mut control = sys.clone();

    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(200))), DONE);
    sys.run(sys.now() + 100 * 1_000_000, 100_000);
    assert_eq!(sys.role(role).state(), RoleState::Held);
    assert_eq!(sys.role(role).holder(), target);
    assert!(sys.node(0).requests.is_empty());
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(100))), DONE);
    assert_eq!(entry(&sys, &t, 0x22), Some((0, g0)), "a stale context entry");
    assert_eq!(sys.check(), Ok(()));

    control.run(control.now() + 100 * 1_000_000, 100_000);
    assert_eq!(control.node(0).woken(attacher), Some(&DONE));
    assert_eq!(entry(&control, &t, 0x22), None);
}

/// F5 (2), the legal path: a request that holds no wait (a signal on a
/// remote notify) whose thread is destroyed is forgotten; its answer comes
/// later from the node it was sent to, passes `asked` (`None => true`) and
/// gives back the proxy it used: `outstanding` returns to 0. Only a message
/// that no correct node sends (an answer to an id it never received) could
/// make the count wrong.
#[test]
fn an_answer_to_a_forgotten_request_keeps_the_proxy_count_right() {
    let (mut sys, t) = three();
    let signaller = helper(&mut sys, &t);
    for node in 0..2u16 {
        assert_eq!(sys.apply(node, t[node as usize], retype(ObjectKind::Reply, 0, 99)), DONE);
    }
    assert_eq!(sys.apply(1, t[1], retype(ObjectKind::Notify, 0, 100)), DONE);
    let recv = Syscall::Recv {
        endpoint: s(START_SLOT_MAILBOX),
        reply: s(99),
        range: Range {
            first: s(110),
            count: 1,
        },
        wait: 0,
    };
    assert_eq!(sys.apply(0, t[0], recv), WAITS);
    let message = crate::Message {
        label: 1,
        flags: 0,
        words: vec![1],
        caps: vec![crate::Transfer::Derive(s(100), Rights::ALL.bits())],
        marks: 0,
    };
    let send = Syscall::Send {
        target: s(16),
        message,
    };
    assert_eq!(sys.apply(1, t[1], send), WAITS);
    sys.settle(32);
    assert_eq!(sys.apply(0, signaller, Syscall::Signal(s(110))), WAITS);
    assert_eq!(sys.node(0).outstanding.get(&1), Some(&1));
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(200))), DONE);
    assert!(sys.node(0).requests.is_empty());
    sys.settle(32);
    assert_eq!(sys.node(0).outstanding.get(&1), Some(&0));
    assert_eq!(sys.check(), Ok(()));
}
```

## Appendix C: `ring_order_and_unit_include.patch`

```diff
diff --git a/model/src/system.rs b/model/src/system.rs
index adde7bc..9c7a2ee 100644
--- a/model/src/system.rs
+++ b/model/src/system.rs
@@ -163,6 +163,11 @@ impl System {
     /// The message in flight at `index` arrives at its node, which runs.
     pub fn deliver(&mut self, index: usize) {
         let to = self.in_flight[index].to;
+        let from_ = self.in_flight[index].from;
+        assert!(
+            !self.in_flight[..index].iter().any(|p| p.from == from_ && p.to == to),
+            "ring order: an older message from {from_} to {to} is still in flight"
+        );
         assert!(self.runs(to), "node {to} does not run");
         let packet = self.in_flight.remove(index);
         let from = packet.from as usize;
@@ -1170,3 +1175,7 @@ mod tests {
         assert_eq!(sys.check(), Err("86: no live node".into()));
     }
 }
+
+#[cfg(test)]
+#[path = "verify_hydrogen_opus_unit.rs"]
+mod verify_hydrogen_opus_unit;
```
