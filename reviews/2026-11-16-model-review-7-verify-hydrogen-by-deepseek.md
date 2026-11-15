# Review 7: verification of the gemini-hydrogen report, by deepseek

Report verified: `Docs/reviews/2026-11-16-model-review-7-gemini-hydrogen.md` (F1 to F11, the protocols between nodes).
Contract: `Docs/architecture/kernel-interface.md` at Docs `3bc7597`. Model: `dodos-kernel` at `2afc901`.

## What I did

- Ran the reviewer's 18 tests and its 2 unit tests in a copy at `2afc901` (`/tmp/verify7-ds/kernel`): all pass, as reported.
- Enforced the ring rule in a second copy: `System::deliver(index)` panics when an older message of the same `from` and `to` is still in flight (`ring_order.patch`, 9 lines), so the messages of one ordered pair of nodes arrive in the order they were sent. With it, 6 of the reviewer's 18 tests stop: f1b, f1c, f5a, f5b, f6, f7 — each one overtakes in ring `0 -> 1` or `1 -> 0` — as you said.
- Wrote my own tests from the contract, every one run with the ring rule enforced: 21 integration tests (`model/tests/verify_hydrogen.rs`) and 2 tests inside the crate (`model/src/system.rs`, `mod verify_hydrogen_unit`, to read a node's `outstanding` and to push a hand-made packet). All 23 pass.
- For each of the 6 tests that break the ring, I looked for a legal order — a third node, a revocation that needs no message, a second thread — before calling any part of the finding impossible. The reviewer's f1b, f5b, f6 and f7 are reachable by a legal order and the fault stands; its f1c and f5a are not, and I say why.
- From a fresh clone (`/tmp/verify7-ds/check`) the reviewer's patches, `ring_order.patch`, `system_verify_hydrogen_unit_tests.patch` and `verify_hydrogen.rs` reproduce every number below: 21 + 2 of mine pass, 12 of the reviewer's pass, and the same 6 fail.

Everything was run with `timeout 280 nix develop -c cargo test -p dodos-model ...`. Nothing in `Docs` or `dodos-kernel` was changed; my copies are under `/tmp`. Files: `scratchpad/review7/tests/verify-hydrogen/` (the test file, two patches, a README).

"Side" says where the fault is: contract, model, or the reviewer's own tests. A test name below is in `verify_hydrogen.rs` unless I write "unit".

## Verdicts

| Finding | Verdict | Side | Severity (mine) | How I know |
|---|---|---|---|---|
| F1 a stale `RevokeStep` / `Revoke` | CONFIRMED IN PART: (1) and (2) hold in a legal order, (3) impossible, (4) not a fault | model (1, 2); contract (4) | breaks isolation between nodes (1); blocks for ever (2) | run: `f1_a_stale_revoke_step_frees_a_live_mapped_grant_in_a_legal_order` (invariant 58 fails), `f1b_a_stale_revoke_step_with_a_third_node_holds_the_caller_for_ever`; read: 844, 855 |
| F2 `core_place` then `core_stop`; retire | CONFIRMED: both parts | contract (A); model (B) | breaks isolation between nodes (a live node's core stopped, an innocent node killed); wrong result | run: `f2_a_stop_after_a_place_of_a_live_node_stops_the_core_of_another_node`, `f2b_a_retire_of_a_sealed_node_retires_the_core_of_a_live_node`; `check()` stays `Ok`; read: 1090, 1182, 1194, `recovery.rs:247-250` |
| F3 grants named without their serial | CONFIRMED IN PART: (1) impossible, (2) and (3) confirmed | model | breaks isolation between nodes | run: `f3_a_stale_request_signals_the_notify_of_a_grant_of_a_third_node`, `f3b_a_transfer_installs_a_capability_of_a_grant_the_granter_freed`; read: `remote.rs:246`, `656` |
| F4 sealed, resumed, co-hosted nodes | CONFIRMED IN PART: (1) and (2) hold, (3) not a fault | contract (1); model (2) | blocks for ever (1); wrong result (2) | run: `f4_a_resume_runs_r2_only_and_leaves_a_move_and_a_grant_stuck`, `f4b_a_resume_on_a_shared_core_kills_the_node_that_was_never_saved`, `f4c_the_last_live_node_that_hangs_leaves_the_machine_lost`; read: 853, 845, 1037, 1138, 1173 |
| F5 a destroyed thread's request, `asked(None)`, the role index | CONFIRMED IN PART: (2) and (3) hold, (1) is what the contract allows | model (2, 3); contract (1) | panic of the model (2, 3); wording (1) | run: `f5_a_destroyed_sender_drops_the_capabilities_of_its_send`, unit `f5b_a_spurious_answer_frees_a_proxy_that_is_still_busy`, unit `f5c_a_message_naming_a_role_that_does_not_exist_panics`; read: `remote.rs:606`, `679`, `650`, `roles.rs:264` |
| F6 refused moved capabilities stranded | CONFIRMED: both parts, by legal orders; the reviewer's orders were not legal | model | wrong result (a capability stranded in a kernel space, invisible to `check()`) | run: `f6_a_refused_move_is_stranded_when_the_slot_is_refilled`, `f6b_a_batch_refused_with_one_stale_grant_strands_the_rest` |
| F7 calls the model does not handle | CONFIRMED | model | panic of the model | run: `f7_a_derive_into_a_capability_space_of_another_node_panics`, `f7b_a_secondary_capability_of_the_caller_s_own_node_panics` |
| F8 a unit request never sent again | CONFIRMED | model | blocks for ever | run: `f8_a_unit_request_is_never_retried_after_the_role_returns_to_its_holder`; read: `roles.rs:231-255` (no word sent, `sent_to` kept), `roles.rs:384-400` (a retry only for another holder) |
| F9 `thread_resume` during a move | CONFIRMED IN PART: the zombie is real, the contract says it two ways, the missing freezes are not a fault | contract and model | wording | run: `f9_a_resume_during_a_move_leaves_the_moved_thread_runnable`; read: 675 |
| F10 a late step-4 message traced; the window of a code | NOT A FAULT: both parts | contract | wording | run: `f10_a_late_step_four_message_is_traced_as_a_refusal`, `f10b_one_peer_fills_the_refusal_window_of_the_node_it_talks_to`; read: 855, 1295 |
| F11 what `liveness.rs` checks | CONFIRMED | the reviewer's own subject: the model's tests | wording | run: `f11_the_way_out_of_liveness_is_blind_to_a_thread_stuck_on_another_node`, the reviewer's `audit_liveness_coverage` (its numbers reproduce: `RUNS=136`, 7 member states, 4 evidences, grant states {0, 2}); read: `liveness.rs:271-300` |

**Counts.** CONFIRMED 5 (F2, F6, F7, F8, F11). CONFIRMED IN PART 5 (F1, F3, F4, F5, F9). NOT A FAULT 1 (F10). IMPOSSIBLE SCENARIO 0 as a whole finding (3 parts of findings are impossible: F1(3), F3(1), and f5a inside F3). NOT REPRODUCED 0.

## F1: stale revocation messages

The reviewer claims four things. Three are about the model's trust in the grant *index* instead of the pair `(grant, serial)`; the fourth is about a trace.

**(1) A step frees a live mapped grant: CONFIRMED, in a legal order.** The reviewer's `f1b` puts the second `TransferAsk` in front of the `Revoke` of the first grant in ring `0 -> 1`, which the ring forbids. A legal route to the same state: node 0 sends the second transfer to node 1 *before* node 0 revokes the first grant, so the ask is sent first; node 1 grants index 0 to the second receiver when it arrives (entry 0 is still `Live` under the first grant — the same index, a new serial); then node 1 revokes the first grant: `released()` frees the entry without completing `Request::Revoke`, and `revoked_step()`/`asked()` then trust the index. In the model the entry that the first revocation was about is gone, so the holder's step is applied to the *new* grant, and node 1 frees a grant that is live and mapped. `f1_a_stale_revoke_step_frees_a_live_mapped_grant_in_a_legal_order`: node 1 has mapped a frame of node 0 (grant 0, serial 0, translated); the second transfer's request of node 1's frame goes to node 0 first; node 0 revokes grant 0 (no message; the grant is freed at once); node 1 answers the second transfer with entry 0 and serial 1; the stale `RevokeStep` from node 0 then reaches node 1, which frees entry 0 — the *new* grant — and the frame that node 1 had mapped stays `translated` with no grant behind it. `check()` answers `Err("node 1: 58: translation under no grant")`: the machine's own invariant 58 shows the breach. Severity: breaks isolation between nodes; a live holder's mapping survives its grant, and the granter holds a serial it never used.

**(2) The caller waits for ever: CONFIRMED, with a third node.** `f1b_a_stale_revoke_step_with_a_third_node_holds_the_caller_for_ever`: node 0 grants node 1's frame, then (in ring order) the third node 2 asks for entry 0 and gets it after node 1 revoked the first grant, and node 0's last step is refused by `released()` in the same way; node 0's revoke never completes and its thread waits for ever, while entry 0 serves a live grant of node 2. Line 844 asks the receiving node to act only when "the entry has that serial and names *Y*"; the model asks the index. Severity: blocks for ever.

**(3) A late `Revoke` refused after the same peer reused the slot: IMPOSSIBLE SCENARIO.** `f1c`'s order is not a legal one, and no other order reaches it: for node 1 to reuse entry *k* for another grant the *same* granter made, the granter has to send the `TransferGrant` of the new grant, and that message travels in the ring `0 -> 1` *behind* the last `Revoke` step of the old one (the granter sends the steps of a revocation before it asks for anything to be granted again). If the new grant comes from another node, it is in that node's ring and the entry is not "the same peer's slot" any more, which is case (1). So a `Revoke` cannot arrive after its index serves a new grant of the same pair.

**(4) A concurrent unmapped release is traced `Refused`: NOT A FAULT.** Line 855 asks for it: "A message that fails its check changes nothing and is traced (code 11)"; line 844 sends the release for any removal of the root remote capability and lets no thread wait for it, so a release that crosses a revocation the granter made at once is *meant* to be refused, and the trace is the record of that. `f10_a_late_step_four_message_is_traced_as_a_refusal` shows the same rule from the other side.

## F2: `core_place` and `core_stop`

**CONFIRMED, both parts; the first is mostly the contract's fault, the second the model's.**

**(A) A stop after a place of a live node stops the core of another node.** Line 1194 does bind the node in the machine table at once, but "a live node moves at its next event boundary"; line 1090 identifies the core to stop by where the node **runs**: "*X* runs on *p*" and "the core beacon's `running` is not *X*". In the model `placed` is rewritten by the call at once and `core_place` has no step of the parked-node protocol, so the stop of a live node that has not moved yet is aimed at the core it was *placed* on. `f2_a_stop_after_a_place_of_a_live_node_stops_the_core_of_another_node`: three nodes on three cores; node 1 is placed on the physical core where node 2 runs live (which 1194 allows: the core runs a live node); before any event boundary node 0 stops node 1 with kill; node 1 dies, **core 1 — the core it was running on — is never stopped and stays `Running`**, and node 2 dies with evidence `Host`, killed for a stop aimed at another node. `check()` answers `Ok(())`: no invariant catches a dead node whose core still runs. Severity: breaks isolation between nodes; an innocent node is killed and a dead node's core keeps running.

**(B) A retire of a sealed node retires the core of a live node.** `f2b_a_retire_of_a_sealed_node_retires_the_core_of_a_live_node`: node 1 seals itself, is placed on the physical core where node 2 runs live, and is then retired; `core_stop(RETIRE)` marks `unusable[placed[node]]` with no test of who runs there (`recovery.rs:247-250`), so `CoreStatus` of node 2's core answers `CORE_STATUS_UNUSABLE` while node 2 is `Live` and its core `Running`. Line 1182 says "the physical core that runs the node"; line 1090 lists what a core does with the nodes placed on it. Here the model is at fault, not the contract. Severity: breaks isolation between nodes.

## F3: grants named without their serial

**(1) `Body::Move` without a serial (`f5a`): IMPOSSIBLE SCENARIO.** The reviewer's `f5a` overtakes a `Release` with a `Move` in ring `0 -> 1`. It cannot happen: the moved thread's caps are released by the source *after* it sends the state of the move, in its own ring, so the `Move` always arrives before the release; the grant it names is still live, and the reviewer's "stale move" has no legal order. (The model's `Move` message names the thread and the sched of the destination by grant index and no serial; the contract says what the call takes, not what the message carries, so the missing serial is a wording gap of the model at most, and nothing is reachable through it.)

**(2) `Body::Request` exempt from `misdirected`, judged by its anchor: CONFIRMED, in a legal order.** The reviewer's `f5b` breaks the ring with two grants of one pair; a legal route needs no message at all: a granter revokes its *own* grant synchronously (line 844 frees it at once when the anchor has no descendant), then grants the same index to a **third** node. `f3_a_stale_request_signals_the_notify_of_a_grant_of_a_third_node`: node 1 holds a remote notify of node 0 (grant 0) and has a signal of it in flight; node 0 revokes grant 0 (freed at once); node 0 grants entry 0 again to node 2's notify; node 1's request then signals node 2's notify — `poll` on node 2's notify reads 1. Line 855 lists the messages that are checked and `Request` is judged by its handler; the model's exemption leaves the anchor index, without the serial, as the only check (`remote.rs:656`: `Body::Request ... => None`). Severity: breaks isolation between nodes; node 1 acted on an object it was never given.

**(3) `place_transfer` installs a `Crossing::Grant` without the `Live` and serial check: CONFIRMED, in a legal order.** The `Home` branch of the same function checks the entry; the `Grant` branch does not. `f3b_a_transfer_installs_a_capability_of_a_grant_the_granter_freed`: the granter revokes its grant of the anchor locally (no message) after the `TransferGrant` was composed; the receiver installs the capability anyway, `caps == 1`, no `caps_dropped`, and its first use is `Gone`. Line 835: a remote capability is valid "when the grant entry is live with that serial". Severity: wrong result (a capability that is dead on arrival), found on a use that the caller counted as granted.

## F4: sealed, resumed and co-hosted nodes

**(1) Resume runs R2 only: CONFIRMED; the model follows a contract that is short.** Line 845: a node resumed by `core_start` mode 1 "removes its remote capabilities whose use entry records a generation of their granting node that is over, by the steps of R2, and sends no release". R0 (line 1098, "It ends with `gone` every wait of its threads on *X*") and R3 (its grants to *X*'s generation) are run when a live node sees another in fencing; a sealed node sees nothing, and nothing else asks for them at resume. `f4_a_resume_runs_r2_only_and_leaves_a_move_and_a_grant_stuck`: node 1 waits on node 0's notify and has granted node 0 a frame; node 1 is sealed; node 0 is killed and dies; node 1 is resumed; over the next 300 ms of machine time the wait does not end, `in_move` is unchanged and the grant still names node 0's generation. Control: the same kill with node 1 live ends the wait with `gone`. Line 853 ("Every wait on another node ends when that node is accused, whatever the request") is what the resumed node misses. Severity: blocks for ever.

**(2) A resume on a shared core: CONFIRMED, the model's fault.** Line 1173: a mode 1 start is `busy` when "the node is not sealed or its core is not confirmed parked". `f4b_a_resume_on_a_shared_core_kills_the_node_that_was_never_saved`: node 1 seals itself and is placed on the physical core where node 2 runs live, so that core is not parked; the model **accepts** the resume (`DONE`), loads node 1's block over node 2's, and nothing seals node 2, whose block is now gone. A later `core_stop(KILL)` of node 1 then leaves both nodes `Dead`, and node 2 — which never ran a bad instruction — carries evidence `Host`. Severity: wrong result (an innocent node is killed and a live node's state is lost); the state check of 1173 is skipped, not a wording matter.

**(3) Two nodes, the last live node hangs while the other seals: NOT A FAULT.** Line 1037 gives the transition to fencing to "any live node ... at least one other node is live"; line 1138: "`core_stop` refuses to kill or seal the last live node (`busy`), so the last node is lost only by its own failure, and then the machine is lost." `f4c_the_last_live_node_that_hangs_leaves_the_machine_lost` reaches exactly that state: node 0 sealed, node 1 hung, the machine lost and no node to accuse anybody. The reviewer calls it a design hole; the contract calls it the end of the machine.

## F5: a destroyed thread's request, `asked(None)`, the role index

**(1) A destroyed sender's `send` drops the capabilities: what the contract allows.** Line 854: a request that holds no wait "completes without the thread", and "grants that arrive for a destroyed receiver are refused, so the capabilities stay with their sender, whose `send` returns the flag `caps_dropped`". Line 212 then says the same for a lost message page: "If the sender's message page was unbound while it waited, the list is lost: the capabilities are dropped in the same way". `f5_a_destroyed_sender_drops_the_capabilities_of_its_send` shows both readings of the same state, and the `Request::Unit` retry case the reviewer adds has no victim (nothing is lost but a retry). Side: contract, and only its wording is at fault: two clauses describe the same loss with different words. The reviewer's severity for this part does not hold.

**(2) `asked` answers `true` for an unknown request: CONFIRMED (unit test).** `remote.rs:606`: `None => true`. A `Body::Answer` for an id the node never sent is therefore not refused, and `answered_request` (line 734) takes one away from `outstanding` — which counts the requests the *calling* node has in flight to that peer — and removes `Request` entries that are not `Call`s. Unit `f5b_a_spurious_answer_frees_a_proxy_that_is_still_busy`: sixteen threads of node 0 wait on a notify of node 1 (sixteen proxies busy, `outstanding == 16`); a hand-made `Body::Answer` with id 999 999 arrives; no entry of code 11 is written and `outstanding` is 15; the seventeenth thread's wait is sent and node 1 panics in `serve_request` at `remote.rs:679` ("the calling node counts its requests"). Severity: panic of the model, and one that a node reaches by sending a single message of the right generation.

**(3) A role word out of range: CONFIRMED (unit test).** `misdirected` indexes `self.table.roles[*role as usize]` for `Body::Handed` (`remote.rs:650`) and `serve_unit` does the same for `Body::UnitRequest` (`roles.rs:264`), which `misdirected` exempts (line 661). Unit `f5c_a_message_naming_a_role_that_does_not_exist_panics`: role 999 of 5 panics in both, `index out of bounds: the len is 5 but the index is 999`. Severity: panic of the model. (A hand-made packet is needed: no legal call of the contract names a role by index, so this is a robustness fault of the message path, not of the calls; line 855 asks for a check, not a panic.)

## F6: refused moved capabilities stranded

**CONFIRMED, both parts, but not by the reviewer's orders: both of its tests break the ring, and the fault survives without any order at all.** `Refused` of a batch and the `Answer` of the move that carries the caps are messages of different rings in the reviewer's `f7`, and it puts the answer first in ring `1 -> 0`; the fault does not need the answer.

**(1) A refused move is stranded once the sender's slot is refilled.** Line 212 is the rule the model breaks: on a refusal "no capability moves, the words are still delivered". The capability that a `Move` transfer took out of the sender's space must therefore come back to the sender's slot. `f6_a_refused_move_is_stranded_when_the_slot_is_refilled`: node 1 receives with an empty range, which "refuses every capability" (line 215), so the move of node 0's notify into slot 100 is refused; the request reaches node 1, node 0's slot 100 is emptied and the grant is made live, and node 1 sends its refusal. Before the refusal arrives, **another thread of node 0** fills slot 100 with a fresh notify — no message of node 1's, so no ring is crossed and nothing is overtaken. The refusal then arrives: the grant is freed, the sender's slot keeps the new capability, and the capability node 1 refused is in neither node's space — the model's `refused()` puts it back only while the sender's slot is still empty (`remote.rs:1219-1229`); with the slot taken it frees the grant and leaves the anchor in the space with no place and no grant (`Some(_) => {}`). The sender is told `caps_dropped`, and `check()` answers `Ok(())`: a capability is destroyed and no invariant notices. Severity: wrong result; a capability disappears from the machine.

**(2) One stale grant in a batch strands the rest.** `f6b_a_batch_refused_with_one_stale_grant_strands_the_rest`: node 0 sends one message that moves two capabilities; node 0 frees one of the two grants *locally* before the batch `Refused` arrives (line 844 frees a grant at once when its anchor has no descendant, and no message is sent). `misdirected` then judges the whole batch by `grants.iter().all(|&(g, s)| grantee(g, s))` (`remote.rs:632-634`), so the one stale grant voids the refusal of both: the batch is traced as refused, the second capability's grant stays live, its sender slot stays empty, and it sits in node 0's kernel space for ever, while `check()` answers `Ok(())`. Severity: wrong result. A refusal that names one entry the node no longer has should be judged entry by entry: the grants it still holds are the ones the sender gave up.

## F7: calls the model does not handle

**CONFIRMED.** Both panics need no message and no order, so the reviewer's finding stands exactly as written; I only name the lines.

- `f7_a_derive_into_a_capability_space_of_another_node_panics`: `cap_derive` with a `through()` destination in another node's capability space panics at `lib.rs:1635` (`self.cspaces[&self.cspaces[&space].slots[...]...]`), because the model looks the slot's space up in the caller's table.
- `f7b_a_secondary_capability_of_the_caller_s_own_node_panics`: `sched_bind` with a thread of another node panics at `sched.rs:620`.

Severity: panic of the model, from ordinary calls of the contract. Line 851 is the rule they break: such a capability argument is `invalid` ("A capability argument that belongs to the caller's own node ... is refused the same way"), never a lookup.

## F8: a unit request that is never sent again

**CONFIRMED.** `send_unit_request` (`roles.rs:231-255`) returns without a word when the holder the role word names is not `Held` and live, and leaves `Request::Unit { sent_to }` as it was; the retry pass of `roles_unit` (`roles.rs:384-400`) takes a request back only when `Some(word.holder()) != *sent_to`. So a role handed back to the same holder — a `hand` that fails and is withdrawn, or a hand-over to the node that gave the role up — strands the request for ever. `f8_a_unit_request_is_never_retried_after_the_role_returns_to_its_holder`: node 0 asks the holder of a unit role to attach a device; the role is handed to node 2 and back to node 1; over the next 200 ms of machine time the request is still the same, `sent_to` still names node 1, and no message goes out again, while line 1098 keeps such requests "to send them again once the role word names a live holder". Severity: blocks for ever.

## F9: `thread_resume` during a move

**CONFIRMED IN PART.**

**(1) The zombie runs: real, but the contract says it two ways.** `f9_a_resume_during_a_move_leaves_the_moved_thread_runnable` confirms the reviewer's state: the moved thread, resumed while its state is in transit, runs at the destination with the source's registers while the caller still waits, and it keeps running after a refusal. But line 675 contains both clauses: "`thread_resume` clears its suspension but not its wait, so it runs only after the answer, and only if the move was refused" and, one sentence later, the destination thread "stays suspended (unless `thread_resume` cleared it meanwhile)". The model follows the second; a reviewer can call that a fault only against the first. Severity: wording; the contract must choose one sentence.

**(2) The "missing freezes" are NOT A FAULT.** Line 675 fixes the list exactly: "`sched_configure`, `sched_set_cores`, `sched_bind` and `sched_unbind` on the context are `busy`". `sched_count`, `task_attach` and `task_revoke` are not on it, so the model owes them nothing.

## F10: a late step-4 message, and the window of a code

**NOT A FAULT, both parts; the model does what the contract asks.**

**(1) A late `Handed` traced as a refusal is required.** Line 855: "A message that fails its check changes nothing and is traced (code 11)". A `Handed` that arrives after the hand-over moved on fails its check by line 855's own list ("the message of step 4 of a hand-over only from the node the handing word names as holder, to its target"). `f10_a_late_step_four_message_is_traced_as_a_refusal` shows the trace and the unchanged state; the trace is the record of a message that was right when it was sent and wrong when it arrived, which is what the code is for.

**(2) One peer fills the window of another node's code: the contract's own numbers.** Line 1295: "Each code except 6 may write at most 16 entries in each of its windows. Windows are counted per node." A peer that makes node *X* refuse sixteen messages in one millisecond fills *X*'s window of code 11, and every other peer's insistence in that millisecond is counted in the suppressed counter instead. `f10b_one_peer_fills_the_refusal_window_of_the_node_it_talks_to` measures it: eighteen releases of freed grants in one window give exactly 16 entries of code 11 and a suppressed counter of 2. The reviewer's own text says the model matches the contract; a design critique of line 1295 is not a fault of the model, and the brief for this round is the protocols, not the rate limit.

**One remark, read but not tested:** line 1172 makes a mode 0 `core_start` refuse a module that is not flagged as a first service (`invalid`), and the model's `core_start` reads the module words without that test. I did not build a dead node with a non-first-service module to see it, so I do not report it as a finding.

## F11: what `liveness.rs` checks

**CONFIRMED.** The claim is about the model's own tests, and both halves hold.

- The numbers reproduce: the reviewer's `audit_liveness_coverage` on my copy prints `RUNS=136 WAY_OUT=136 MAX_DEAD=2`, member states `{Dead, Fenced, Fencing, Live, Sealed, Sealing, Unfenced}` (no `Starting`), evidences `{Kill, None, Stale, Stuck}` (no `SelfReported`, `Retire`, `Host`), role states `{Handing, Held, Vacant}`, grant states `{0, 2}` (`GrantState` is `Live = 0, Revoking = 1, Pinned = 2`, so `Revoking` is never reached), core states `{Hung { nmi: true }, Looping, Parked, Running}` (no `Hung { nmi: false }`, `InitPending`, `Off`).
- `way_out` reads the member words, the role words and the grant entries, and nothing else (`liveness.rs:271-300`). `f11_the_way_out_of_liveness_is_blind_to_a_thread_stuck_on_another_node` copies that function into a three-node machine, has a thread of node 0 wait for ever on a notify of node 1 with the grant live, and shows `way_out` answering `Ok(())`: a permanently stuck `Wait::Node` with a request in flight is invisible to it, as the reviewer says.

Severity: wording. Nothing in the design is wrong; the evidence is thinner than a reader of `liveness.rs` would think. The reviewer's "smallest correction" is the right one.

## New finding

**N1: the calls that may name another node's object are a hand-written list, and a call left off it panics.** Line 849: "a call on an object held by another node becomes a message between kernels, and the caller sees the same result, later". The model decides that by matching the call against `capability_arguments()` (`remote.rs:246-270`), which lists `Call`, `Recv`, `Send`, `Signal`/`Poll`/`Wait`, `NotifyBind`, four thread calls, `SchedRead`/`SchedUnbind`, `TimerSet`/`TimerCancel`, `IrqBind`/`IrqAck`, five task calls and `SchedBind`; every other call runs on the caller's node whatever its capabilities name. Two ordinary calls fall through:

- A `ReplyRecv` on a remote endpoint: `n1_a_reply_recv_on_a_remote_endpoint_panics`. Node 1 makes an endpoint and derives a capability of it to node 0; node 0 calls `ReplyRecv` with that endpoint and a local reply object; the model looks the endpoint up in node 0's endpoint table and panics at `ipc.rs:423`: `no entry found for key`. The contract's `reply_recv` is a call on an endpoint, and line 851 says a remote capability argument that is a grant of the executing node may name the object; nothing except the missing list entry stops it from becoming a message.
- `SchedConfigure` with a `sched` of another node: `n1b_a_sched_configure_on_a_remote_sched_panics` panics at `sched.rs:577` (`no entry found for key`) for the same reason. (With a `core` of the caller's node instead of the remote one the same call panics; the model never reaches a state check.)

Severity: panic of the model, reachable by a call the contract allows, from a capability another node derived to the caller. The fix is to drive the decision from the calls' declared capability arguments rather than a list that must be kept in step — but that is for whoever owns the model.

## What I did not check

- The full repository suite (`./verify`), the other crates, and `DODOS_PAGE=16k`/`32k`.
- Machines of more than three nodes, and the non-x86 fence paths.
- The `core_start` mode 0 first-service test of line 1172 (read only, see F10).
- Which faults need more than calls: F5(2) and F5(3) need a message of the right generation, which a node can send (a hand-made `Body` packet in the unit tests, as the report says); every other finding here is reached by calls of the contract alone, in ring order.

## Appendix A: `model/tests/verify_hydrogen.rs`

```rust
//! Verification of review 7 (`gemini-hydrogen`) by a second reader.
//!
//! Every test is written from the contract
//! (`Docs/architecture/kernel-interface.md`, commit 3bc7597) and the model at
//! 2afc901, not from the reviewed report's tests. One rule that the contract
//! does not state is applied throughout: the messages of one ordered pair of
//! nodes travel through one ring, so they arrive in the order they were sent;
//! `System::deliver` panics when a message overtakes an older one of the same
//! pair. Every order below is therefore a legal one.

use dodos_abi::ObjectKind::{Endpoint, Frame, Notify, Reply, Sched, Thread};
use dodos_abi::{MemberState, RoleState};
use dodos_abi::*;
use dodos_model::*;

const DONE: Outcome = Ok(Output::Done);
const WAITS: Outcome = Ok(Output::Waits);
const UT: SlotAddr = SlotAddr::own(25);
const MAILBOX: SlotAddr = SlotAddr::own(START_SLOT_MAILBOX);
const ASPACE: SlotAddr = SlotAddr::own(START_SLOT_ASPACE);
const MS: u64 = 1_000_000;
const NOT_EXEC: Rights = Rights::ALL.without(Rights::EXEC);

const fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

/// The `core` capability of node `n`, in slot 16 + n.
const fn on_core(n: u32) -> SlotAddr {
    SlotAddr::own(START_SLOT_FIRST + n)
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

fn carrying(label: u32, caps: Vec<Transfer>) -> Message {
    Message {
        label,
        flags: 0,
        words: vec![u64::from(label)],
        caps,
        marks: 0,
    }
}

/// A machine of `nodes` nodes, one per physical core.
fn machine(nodes: usize) -> Machine {
    let mut machine = Machine::example();
    while machine.cores.len() < nodes {
        let mut extra = machine.cores[1];
        extra.hw_id = 2 * (machine.cores.len() as u64);
        machine.cores.push(extra);
    }
    machine.membership.stale_ms = 10;
    machine.membership.stuck_ms = 10;
    machine.membership.sweep_ms = 100;
    machine
}

/// A started machine of `nodes` nodes; each node's start-up context gets a
/// budget on its own core, and a reply object in slot 99.
fn started(nodes: usize) -> (System, Vec<ObjId>) {
    let (mut sys, t) = System::boot(&machine(nodes)).unwrap();
    for node in 0..nodes as u16 {
        let sched = Syscall::SchedConfigure {
            sched: s(START_SLOT_SCHED),
            core: on_core(node.into()),
            budget: 1_000_000,
            period: 10_000_000,
            class: 1,
        };
        assert_eq!(sys.apply(node, t[node as usize], sched), DONE);
        assert_eq!(sys.apply(node, t[node as usize], retype(Reply, 0, 99)), DONE);
    }
    (sys, t)
}

/// One more thread on `node`, with its own sched on that node's core.
fn thread_on(sys: &mut System, t: &[ObjId], node: u16, slot: u32) -> ObjId {
    let spare = 3000 - 3 * (slot - 200);
    let root = t[node as usize];
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
            core: on_core(node.into()),
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
        assert_eq!(sys.apply(node, root, call), DONE);
    }
    sys.node(node).object_at(root, s(slot)).unwrap()
}

/// `to` waits on its mailbox for `count` capabilities in `first`.
fn receive(sys: &mut System, t: &[ObjId], to: u16, first: u32, count: u32) {
    let range = Range {
        first: s(first),
        count,
    };
    assert_eq!(
        sys.apply(
            to,
            t[to as usize],
            Syscall::Recv {
                endpoint: MAILBOX,
                reply: s(99),
                range,
                wait: 0,
            },
        ),
        WAITS
    );
}

/// A frame of `from` in slot `frame_slot`, derived into `frame_slot + 1` and
/// moved to `to` in slot `recv`; `from`'s grant is slot 0, serial 0.
fn grant_frame(sys: &mut System, t: &[ObjId], from: u16, to: u16, frame_slot: u32, recv: u32) {
    assert_eq!(sys.apply(from, t[from as usize], retype(Frame, 1, frame_slot)), DONE);
    assert_eq!(
        sys.apply(
            from,
            t[from as usize],
            Syscall::CapDerive {
                source: s(frame_slot),
                destination: s(frame_slot + 1),
                rights: Rights::READ.bits(),
                badge: 0,
            },
        ),
        DONE
    );
    receive(sys, t, to, recv, 1);
    assert_eq!(
        sys.apply(
            from,
            t[from as usize],
            Syscall::Send {
                target: on_core(to.into()),
                message: carrying(1, vec![Transfer::Move(s(frame_slot + 1))]),
            },
        ),
        WAITS
    );
    sys.settle(32);
}

fn map_frame(sys: &mut System, t: &[ObjId], node: u16, slot: u32, address: u64) {
    assert_eq!(
        sys.apply(
            node,
            t[node as usize],
            Syscall::ASpaceMap(Map {
                space: ASPACE,
                frame: s(slot),
                untyped: SlotAddr::NONE,
                address,
                first: 0,
                count: 1,
                rights: Rights::READ.bits(),
            }),
        ),
        DONE
    );
}

/// The index of the oldest message still in flight from `from` to `to`.
fn oldest(sys: &System, from: u16, to: u16) -> Option<usize> {
    sys.pending()
        .iter()
        .position(|p| p.from == from && p.to == to)
}

/// Delivers the next message of one ring, which is the only legal choice.
fn next_in(sys: &mut System, from: u16, to: u16) -> bool {
    match oldest(sys, from, to) {
        Some(index) => {
            sys.deliver(index);
            true
        }
        None => false,
    }
}

/// Delivers every message of one ring, in the order it was sent.
fn settle_ring(sys: &mut System, from: u16, to: u16) {
    while next_in(sys, from, to) {}
}

fn has_refusal(sys: &System, node: u16) -> bool {
    sys.node(node)
        .ring(false)
        .iter()
        .any(|e| e.code() == TraceCode::Refused as u16)
}

// ------------------------------------------------------------------ F1 -----

/// F1, first part: a `RevokeStep` that answers an older revocation frees the
/// grant entry that a *newer* grant of the same index is, while the holder
/// maps it. The order is legal: the message that opens the second transfer is
/// sent *before* the revocation (a second ring would not be enough, because
/// both messages travel from the granting node to the same grantee).
#[test]
fn f1_a_stale_revoke_step_frees_a_live_mapped_grant_in_a_legal_order() {
    let (mut sys, t) = started(2);
    let helper0 = thread_on(&mut sys, &t, 0, 200);
    let helper1 = thread_on(&mut sys, &t, 1, 250);
    // Node 1 holds a mapped frame of node 0 under grant 0, serial 0.
    grant_frame(&mut sys, &t, 0, 1, 100, 110);
    map_frame(&mut sys, &t, 1, 110, 1 << 30);
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((1, 0)));

    // Node 0 sends a second frame, whose grant will reuse index 0, before it
    // revokes anything: the request is older than the revocation in the ring.
    helper_receive(&mut sys, 1, helper1, 150);
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 120)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(1),
                message: carrying(2, vec![Transfer::Move(s(120))]),
            },
        ),
        WAITS
    );
    // Node 0 revokes the parent of the first grant, which node 1 still maps:
    // the revocation waits and is in flight behind the request.
    assert_eq!(sys.apply(0, helper0, Syscall::CapRevoke(s(100))), WAITS);
    // Node 1 drops its remote capability, which no message caused: its
    // release is in flight.
    assert_eq!(sys.apply(1, t[1], Syscall::CapDelete(s(110))), DONE);

    // The release frees index 0 at node 0, though a revocation of it waits.
    settle_ring(&mut sys, 1, 0);
    assert_eq!(sys.node(0).grant_entry(0), None, "the release freed index 0");
    // The request arrives; node 1 asks for the grants.
    assert!(next_in(&mut sys, 0, 1), "the second frame's request");
    // Node 0 grants index 0 again, serial 1, to node 1.
    settle_ring(&mut sys, 1, 0);
    assert_eq!(
        sys.node(0).grant_entry(0).map(|e| (e.0, e.2)),
        Some((1, 1)),
        "index 0 is granted again to node 1"
    );
    // The revocation (sent first) arrives at node 1, which no longer holds a
    // capability of it: it answers *done*.
    assert!(next_in(&mut sys, 0, 1), "the revocation");
    // The new grant arrives and node 1 maps it.
    assert!(next_in(&mut sys, 0, 1), "the new grant");
    map_frame(&mut sys, &t, 1, 150, 2 << 30);
    // The answer to the *old* revocation now frees index 0, which is live.
    settle_ring(&mut sys, 1, 0);

    assert_eq!(
        sys.node(0).grant_entry(0),
        None,
        "the stale answer freed the new grant (0, serial 1)"
    );
    assert_eq!(
        sys.node(1).translated(t[1], 2 << 30),
        Some(Rights::READ),
        "node 1 still translates a frame whose grant no longer exists"
    );
    assert!(
        sys.check().is_err(),
        "the machine invariants see the mapping of a frame under no grant"
    );
    println!("check after the breach: {:?}", sys.check());
    // The caller of the removal is told `again`, as if nothing had happened.
    assert_eq!(sys.node(0).woken(helper0), Some(&Err(Error::Again)));
}

/// Receives on the mailbox of `node` with a helper thread.
fn helper_receive(sys: &mut System, node: u16, helper: ObjId, first: u32) {
    assert_eq!(
        sys.apply(
            node,
            helper,
            Syscall::Recv {
                endpoint: MAILBOX,
                reply: s(99),
                range: Range {
                    first: s(first),
                    count: 1
                },
                wait: 0,
            },
        ),
        WAITS
    );
}

/// F1, second part: with the reused index granted to a *third* node the stale
/// answer is refused, and the caller waits for ever. Legal order: the second
/// grant travels through the ring 0 -> 2, not 0 -> 1.
#[test]
fn f1b_a_stale_revoke_step_with_a_third_node_holds_the_caller_for_ever() {
    let (mut sys, t) = started(3);
    let helper0 = thread_on(&mut sys, &t, 0, 200);
    grant_frame(&mut sys, &t, 0, 1, 100, 110);
    map_frame(&mut sys, &t, 1, 110, 1 << 30);

    // Node 0 revokes; node 1 drops its capability, so index 0 is freed at
    // node 0 while the revocation is still in flight.
    assert_eq!(sys.apply(0, helper0, Syscall::CapRevoke(s(100))), WAITS);
    assert_eq!(sys.apply(1, t[1], Syscall::CapDelete(s(110))), DONE);
    settle_ring(&mut sys, 1, 0);
    assert_eq!(sys.node(0).grant_entry(0), None);
    // Node 0 grants index 0 to node 2 instead: another ring.
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 120)), DONE);
    receive(&mut sys, &t, 2, 110, 1);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(2),
                message: carrying(2, vec![Transfer::Move(s(120))]),
            },
        ),
        WAITS
    );
    settle_ring(&mut sys, 0, 2);
    settle_ring(&mut sys, 2, 0);
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.2)), Some((2, 1)));

    // The revocation arrives at node 1, which holds nothing: it answers done.
    assert!(next_in(&mut sys, 0, 1));
    settle_ring(&mut sys, 1, 0);

    assert!(has_refusal(&sys, 0), "the answer is refused as misdirected");
    sys.run(sys.now() + 200 * MS, MS);
    assert_eq!(
        sys.node(0).woken(helper0),
        None,
        "the caller of the revocation waits for ever"
    );
    assert_eq!(sys.node(0).grant_entry(0).map(|e| e.0), Some(2));
}

// ------------------------------------------------------------------ F2 -----

/// F2, first part: `core_place` binds the node at once, so a stop that
/// follows fences the core the node was *bound* to, not the one that runs it.
#[test]
fn f2_a_stop_after_a_place_of_a_live_node_stops_the_core_of_another_node() {
    let (mut sys, t) = started(3);
    assert_eq!(sys.member(2).state(), MemberState::Live);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace {
            core: on_core(1),
            physical: 2
        }),
        DONE
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop {
            core: on_core(1),
            mode: CORE_STOP_KILL
        }),
        DONE
    );
    sys.run(sys.now() + 20 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Dead);
    assert_eq!(
        sys.core(1),
        CoreState::Running,
        "the core that ran node 1 was never stopped"
    );
    assert_eq!(sys.member(2).state(), MemberState::Dead);
    assert_eq!(
        sys.member(2).evidence(),
        Evidence::Host,
        "node 2 was killed for a stop aimed at node 1"
    );
    assert_eq!(
        sys.check(),
        Ok(()),
        "no invariant catches a dead node whose core still runs"
    );
}

/// F2, second part: `core_stop` mode retire marks unusable the core the node
/// is *placed* on, even when the node does not run on any core.
#[test]
fn f2b_a_retire_of_a_sealed_node_retires_the_core_of_a_live_node() {
    let (mut sys, t) = started(3);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop {
            core: on_core(1),
            mode: CORE_STOP_SEAL
        }),
        DONE
    );
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Sealed);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace {
            core: on_core(1),
            physical: 2
        }),
        DONE
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop {
            core: on_core(1),
            mode: CORE_STOP_RETIRE
        }),
        DONE
    );
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(2).state(), MemberState::Live);
    assert_eq!(sys.core(2), CoreState::Running);
    match sys.apply(0, t[0], Syscall::CoreStatus(on_core(2))) {
        Ok(Output::Status(words)) => assert_ne!(
            words[1] & CORE_STATUS_UNUSABLE,
            0,
            "core 2 is retired while node 2 runs on it"
        ),
        other => panic!("unexpected: {other:?}"),
    }
}

// ------------------------------------------------------------------ F3 -----

/// F3, second part: a request rewrites the caller's remote capabilities to
/// the *index* of their grant, and no node checks that index against the
/// caller. The granter frees the grant itself, so nothing here depends on the
/// order of two messages of one ring.
#[test]
fn f3_a_stale_request_signals_the_notify_of_a_grant_of_a_third_node() {
    let (mut sys, t) = started(3);
    let helper0 = thread_on(&mut sys, &t, 0, 200);
    let helper1 = thread_on(&mut sys, &t, 1, 250);
    // Node 1 has two notifies: A in slot 100, B in slot 101.
    assert_eq!(sys.apply(1, t[1], retype(Notify, 0, 100)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(Notify, 0, 101)), DONE);
    // Grant A to node 0, which is grant 0 of node 1.
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::CapDerive {
                source: s(100),
                destination: s(102),
                rights: Rights::ALL.bits(),
                badge: 0,
            },
        ),
        DONE
    );
    receive(&mut sys, &t, 0, 110, 1);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(0),
                message: carrying(1, vec![Transfer::Derive(s(102), Rights::SEND.bits())]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    assert_eq!(sys.node(1).grant_entry(0).map(|e| (e.0, e.2)), Some((0, 0)));

    // Node 0 signals its remote capability: the request is in the ring.
    assert_eq!(sys.apply(0, helper0, Syscall::Signal(s(110))), WAITS);
    // Node 1 revokes the grant itself, which frees index 0 at once.
    assert_eq!(sys.apply(1, helper1, Syscall::CapRevoke(s(100))), DONE);
    assert_eq!(sys.node(1).grant_entry(0), None);
    // Node 1 grants index 0 again, to node 2 (notify B).
    receive(&mut sys, &t, 2, 110, 1);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(2),
                message: carrying(2, vec![Transfer::Derive(s(101), Rights::SEND.bits())]),
            },
        ),
        WAITS
    );
    for _ in 0..3 {
        settle_ring(&mut sys, 1, 2);
        settle_ring(&mut sys, 2, 1);
    }
    assert_eq!(sys.node(1).grant_entry(0).map(|e| (e.0, e.2)), Some((2, 1)));

    // The stale request arrives at node 1 and is executed on the anchor of
    // index 0, which is now notify B, held by node 2.
    assert!(next_in(&mut sys, 0, 1));
    assert_eq!(
        sys.apply(1, t[1], Syscall::Poll(s(101))),
        Ok(Output::Word(1)),
        "notify B was signalled by a call of node 0's"
    );
    assert_eq!(
        sys.apply(1, t[1], Syscall::Poll(s(100))),
        Err(Error::WouldWait),
        "notify A, the object the call named, has no word"
    );
}

/// F3, third part: the grants of a transfer are installed without the check
/// the contract asks for (live, same serial), so a `send` reports a
/// capability that is already dead. The granter's revocation is its own call.
#[test]
fn f3b_a_transfer_installs_a_capability_of_a_grant_the_granter_freed() {
    let (mut sys, t) = started(2);
    let helper = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CapDerive {
                source: s(100),
                destination: s(101),
                rights: Rights::ALL.bits(),
                badge: 0,
            },
        ),
        DONE
    );
    receive(&mut sys, &t, 1, 110, 1);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(1),
                message: carrying(1, vec![Transfer::Derive(s(101), Rights::READ.bits())]),
            },
        ),
        WAITS
    );
    // The request arrives, node 1 asks for the grants.
    assert!(next_in(&mut sys, 0, 1));
    settle_ring(&mut sys, 1, 0);
    // Node 0 revokes the grant while the answer of the transfer is in flight.
    assert_eq!(sys.apply(0, helper, Syscall::CapRevoke(s(100))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);
    assert!(oldest(&sys, 0, 1).is_some(), "the grants are in flight");
    // Node 1 installs them and reports one capability, none dropped.
    assert!(next_in(&mut sys, 0, 1));
    match sys.node(1).woken(t[1]) {
        Some(Ok(Output::Message(delivery))) => {
            assert_eq!(delivery.received.header.caps(), 1);
            assert_eq!(
                delivery.received.header.flags() & Header::FLAG_CAPS_DROPPED,
                0
            );
        }
        other => panic!("unexpected receiver wakeup: {other:?}"),
    }
    assert_eq!(
        sys.apply(1, t[1], Syscall::Poll(s(110))),
        Err(Error::Gone),
        "the capability delivered is dead on arrival"
    );
}

// ------------------------------------------------------------------ F4 -----

/// F4, first part: a resumed node runs R2 only, so every wait it held on a
/// node that died while it was sealed stays for ever, and so does its frozen
/// thread and the grant it made to the dead generation.
#[test]
fn f4_a_resume_runs_r2_only_and_leaves_a_move_and_a_grant_stuck() {
    let (mut sys, t) = started(3);
    let mover = thread_on(&mut sys, &t, 0, 200);
    // A thread on node 0 to move, with its sched.
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 300)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 301)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::ThreadConfigure {
                thread: s(300),
                cspace: s(START_SLOT_CSPACE),
                aspace: ASPACE,
                fault: SlotAddr::NONE,
                page: s(301),
            },
        ),
        DONE
    );
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 302)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::SchedConfigure {
                sched: s(302),
                core: on_core(0),
                budget: 500_000,
                period: 10_000_000,
                class: 1,
            },
        ),
        DONE
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::SchedSetCores {
                sched: s(302),
                core: on_core(0),
                window: 0,
                mask: 0b11
            },
        ),
        DONE
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::SchedBind {
            sched: s(302),
            thread: s(300)
        }),
        DONE
    );
    // The destination thread and sched, granted by node 2.
    assert_eq!(sys.apply(2, t[2], retype(Thread, 0, 400)), DONE);
    assert_eq!(sys.apply(2, t[2], retype(Sched, 0, 401)), DONE);
    receive(&mut sys, &t, 0, 310, 2);
    assert_eq!(
        sys.apply(
            2,
            t[2],
            Syscall::Send {
                target: on_core(0),
                message: carrying(
                    1,
                    vec![
                        Transfer::Derive(s(400), NOT_EXEC.bits()),
                        Transfer::Derive(s(401), NOT_EXEC.bits()),
                    ]
                ),
            },
        ),
        WAITS
    );
    sys.settle(32);
    // An unmapped grant of node 0 to node 2: index 0.
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 320)), DONE);
    receive(&mut sys, &t, 2, 410, 1);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(2),
                message: carrying(2, vec![Transfer::Move(s(320))]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    assert_eq!(sys.node(0).grant_entry(0).map(|e| (e.0, e.3)), Some((2, 0)));
    // The move to node 2 starts and stays in flight.
    assert_eq!(
        sys.apply(
            0,
            mover,
            Syscall::ThreadMove {
                thread: s(300),
                destination: s(310),
                sched: s(311),
                core: on_core(2),
                budget: 0,
                period: 0,
                class: 0,
            },
        ),
        WAITS
    );
    assert!(oldest(&sys, 0, 2).is_some(), "the move is in flight");
    // Node 1 seals node 0, then kills node 2.
    assert_eq!(
        sys.apply(1, t[1], Syscall::CoreStop {
            core: on_core(0),
            mode: CORE_STOP_SEAL
        }),
        DONE
    );
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(0).state(), MemberState::Sealed);
    assert_eq!(
        sys.apply(1, t[1], Syscall::CoreStop {
            core: on_core(2),
            mode: CORE_STOP_KILL
        }),
        DONE
    );
    sys.run(sys.now() + 10 * MS, MS / 10);
    assert_eq!(sys.member(2).state(), MemberState::Dead);
    // Node 1 resumes node 0.
    assert_eq!(
        sys.apply(1, t[1], Syscall::CoreStart {
            core: on_core(0),
            mode: CORE_START_RESUME,
            image: 0,
            module: 0,
        }),
        DONE
    );
    sys.run(sys.now() + 300 * MS, MS);
    assert_eq!(sys.member(0).state(), MemberState::Live);
    assert_eq!(
        sys.node(0).woken(mover),
        None,
        "the caller of the move waits for ever (contract line 853: it gets gone)"
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::CapDelete(s(300))),
        Err(Error::Again),
        "the moved thread is frozen for ever (contract line 675)"
    );
    assert_eq!(
        sys.node(0).grant_entry(0).map(|e| (e.0, e.3)),
        Some((2, 0)),
        "the grant to the dead generation is neither pinned nor freed"
    );
}

/// F4, second part: a resume is accepted on a core that runs another live
/// node, and the node that ran there is never saved, so the next stop of the
/// resumed node kills it with evidence host.
#[test]
fn f4b_a_resume_on_a_shared_core_kills_the_node_that_was_never_saved() {
    let (mut sys, t) = started(3);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop {
            core: on_core(1),
            mode: CORE_STOP_SEAL
        }),
        DONE
    );
    sys.run(sys.now() + 5 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Sealed);
    assert_eq!(
        sys.apply(0, t[0], Syscall::CorePlace {
            core: on_core(1),
            physical: 2
        }),
        DONE
    );
    // Contract line 1173: mode 1 is `busy` when the core is not confirmed
    // parked; core 2 runs node 2, which writes.
    let resumed = sys.apply(
        0,
        t[0],
        Syscall::CoreStart {
            core: on_core(1),
            mode: CORE_START_RESUME,
            image: 0,
            module: 0,
        },
    );
    assert_eq!(resumed, DONE, "the model accepts what line 1173 refuses");
    assert_eq!(
        sys.apply(0, t[0], Syscall::CoreStop {
            core: on_core(1),
            mode: CORE_STOP_KILL
        }),
        DONE
    );
    sys.run(sys.now() + 10 * MS, MS / 10);
    assert_eq!(sys.member(1).state(), MemberState::Dead);
    assert_eq!(
        sys.member(2).state(),
        MemberState::Dead,
        "node 2 was killed with the stop of node 1"
    );
    assert_eq!(sys.member(2).evidence(), Evidence::Host);
}

/// F4, third part: with two nodes, sealing the one that holds the unit role
/// leaves the last live node alone; when it hangs nothing accuses it. The
/// contract accepts exactly this (line 1138, line 1037): the check is that
/// the model follows it, not that it recovers.
#[test]
fn f4c_the_last_live_node_that_hangs_leaves_the_machine_lost() {
    let (mut sys, t) = started(2);
    let holder = sys.role(0).holder();
    let other = 1 - holder;
    assert_eq!(
        sys.apply(
            other,
            t[other as usize],
            Syscall::CoreStop {
                core: on_core(holder.into()),
                mode: CORE_STOP_SEAL
            },
        ),
        DONE
    );
    assert_eq!(sys.recover(1), 1);
    assert_eq!(sys.role(0).state(), RoleState::Handing);
    sys.hang(other, true);
    sys.run(sys.now() + 250 * MS, 5 * MS);
    // Line 1138: the last node is lost only by its own failure, and then the
    // machine is lost. Line 1037: an accusation needs another live node.
    assert_eq!(sys.member(holder).state(), MemberState::Sealing);
    assert_eq!(sys.member(other).state(), MemberState::Live);
    assert_eq!(sys.role(0).state(), RoleState::Handing);
}

// ------------------------------------------------------------------ F5 -----

/// F5, first part: destroying a thread whose `send` holds no wait there
/// removes its request, so the grants it listed are never asked for and the
/// receiver sees the capabilities dropped.
#[test]
fn f5_a_destroyed_sender_drops_the_capabilities_of_its_send() {
    let (mut sys, t) = started(2);
    let sender = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    receive(&mut sys, &t, 1, 110, 1);
    assert_eq!(
        sys.apply(
            0,
            sender,
            Syscall::Send {
                target: on_core(1),
                message: carrying(7, vec![Transfer::Derive(s(100), Rights::READ.bits())]),
            },
        ),
        WAITS
    );
    // The request arrives and node 1 asks for the grant.
    assert!(next_in(&mut sys, 0, 1));
    assert!(oldest(&sys, 1, 0).is_some(), "the ask is in flight");
    // The sender is destroyed before the answer.
    assert_eq!(sys.apply(0, t[0], Syscall::CapDelete(s(200))), DONE);
    sys.settle(32);
    match sys.node(1).woken(t[1]) {
        Some(Ok(Output::Message(delivery))) => {
            assert_eq!(delivery.received.header.caps(), 0);
            assert_ne!(
                delivery.received.header.flags() & Header::FLAG_CAPS_DROPPED,
                0
            );
        }
        other => panic!("unexpected receiver wakeup: {other:?}"),
    }
    assert_eq!(sys.node(0).grant_entry(0), None, "no grant was made");
}

// ------------------------------------------------------------------ F6 -----

/// F6, first part: a refused move puts the capability back in the slot the
/// sender took it from; if that slot holds something else by then, the
/// capability is stranded in the kernel space and lost. Nothing here depends
/// on the order of the refusal and the answer: the slot is refilled by
/// another thread of the sending node, which is no message at all.
#[test]
fn f6_a_refused_move_is_stranded_when_the_slot_is_refilled() {
    let (mut sys, t) = started(2);
    let helper = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    // Node 1 receives nothing: an empty range refuses every capability.
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Recv {
                endpoint: MAILBOX,
                reply: s(99),
                range: Range::NONE,
                wait: 0,
            },
        ),
        WAITS
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(1),
                message: carrying(1, vec![Transfer::Move(s(100))]),
            },
        ),
        WAITS
    );
    // The request arrives, node 0 grants the move (which empties slot 100),
    // and node 1 refuses it.
    assert!(next_in(&mut sys, 0, 1), "the request");
    assert!(next_in(&mut sys, 1, 0), "the ask");
    assert!(next_in(&mut sys, 0, 1), "the grants");
    assert_eq!(
        sys.node(0).grant_entry(0).map(|e| e.3),
        Some(0),
        "the grant is live"
    );
    assert_eq!(sys.node(0).object_at(t[0], s(100)), None, "the slot is empty");
    assert!(oldest(&sys, 1, 0).is_some(), "the refusal is in flight");
    // Another thread of node 0 fills the slot the capability came from.
    assert_eq!(sys.apply(0, helper, retype(Notify, 0, 100)), DONE);
    let fresh = sys.node(0).object_at(t[0], s(100)).unwrap();
    // The refusal arrives: the grant is freed, the capability is not put back.
    assert!(next_in(&mut sys, 1, 0), "the refusal");
    assert_eq!(sys.node(0).grant_entry(0), None);
    assert_eq!(
        sys.node(0).object_at(t[0], s(100)),
        Some(fresh),
        "the slot keeps the new capability"
    );
    settle_ring(&mut sys, 1, 0);
    assert_eq!(
        sys.node(0).woken(t[0]),
        Some(&Ok(Output::Sent {
            flags: Header::FLAG_CAPS_DROPPED
        })),
        "the sender is told its capabilities were dropped"
    );
    assert_eq!(
        sys.check(),
        Ok(()),
        "no invariant catches a capability stranded in the kernel space"
    );
}

/// F6, second part: the refusal of a batch of grants is checked all or
/// nothing, so one grant that the granter freed meanwhile voids the refusal
/// of the others, which stay live and stranded.
#[test]
fn f6b_a_batch_refused_with_one_stale_grant_strands_the_rest() {
    let (mut sys, t) = started(2);
    let helper = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 100)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::CapDerive {
                source: s(100),
                destination: s(101),
                rights: Rights::READ.bits(),
                badge: 0,
            },
        ),
        DONE
    );
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 102)), DONE);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Recv {
                endpoint: MAILBOX,
                reply: s(99),
                range: Range::NONE,
                wait: 0,
            },
        ),
        WAITS
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(1),
                message: carrying(
                    1,
                    vec![Transfer::Move(s(101)), Transfer::Move(s(102))]
                ),
            },
        ),
        WAITS
    );
    // The request arrives, node 0 grants both, node 1 refuses both.
    assert!(next_in(&mut sys, 0, 1), "the request");
    assert!(next_in(&mut sys, 1, 0), "the ask");
    assert!(next_in(&mut sys, 0, 1), "the grants");
    assert_eq!(sys.node(0).grant_entry(0).map(|e| e.3), Some(0));
    assert_eq!(sys.node(0).grant_entry(1).map(|e| e.3), Some(0));
    assert!(oldest(&sys, 1, 0).is_some(), "the refusal is in flight");
    // Node 0 revokes the parent of the first moved capability, which frees
    // grant 0 at once (nothing maps it).
    assert_eq!(sys.apply(0, helper, Syscall::CapRevoke(s(100))), DONE);
    assert_eq!(sys.node(0).grant_entry(0), None);
    // The refusal of both arrives: it is refused as misdirected, as a whole.
    assert!(next_in(&mut sys, 1, 0), "the refusal");
    assert!(has_refusal(&sys, 0));
    assert_eq!(
        sys.node(0).grant_entry(1).map(|e| e.3),
        Some(0),
        "the second grant stays live for ever"
    );
    assert_eq!(
        sys.node(0).object_at(t[0], s(102)),
        None,
        "the second capability never comes back to its slot"
    );
}

// ------------------------------------------------------------------ F7 -----

/// F7, first part: the destination of `cap_derive` in a capability space of
/// another node is not an argument the model carries (contract line 836), so
/// the call is judged here and panics.
#[test]
fn f7_a_derive_into_a_capability_space_of_another_node_panics() {
    let (mut sys, t) = started(2);
    // Node 1 grants node 0 a capability space.
    assert_eq!(
        sys.apply(
            1,
            t[1],
            retype(
                ObjectKind::CSpace,
                u64::from(CSPACE_SEGMENT_SLOTS),
                100
            )
        ),
        DONE
    );
    receive(&mut sys, &t, 0, 110, 1);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(0),
                message: carrying(1, vec![Transfer::Derive(s(100), Rights::ALL.bits())]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    assert_eq!(sys.apply(0, t[0], retype(Notify, 0, 120)), DONE);
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        sys.apply(
            0,
            t[0],
            Syscall::CapDerive {
                source: s(120),
                destination: SlotAddr::through(110, 1),
                rights: Rights::READ.bits(),
                badge: 0,
            },
        )
    }));
    assert!(outcome.is_err(), "expected the panic of a grant to come");
}

/// F7, second part: a capability argument of the caller's own node is
/// `invalid` when it names no object of the callee's node (line 851); the
/// model instead looks the object up in its own tables and panics.
#[test]
fn f7b_a_secondary_capability_of_the_caller_s_own_node_panics() {
    let (mut sys, t) = started(2);
    // A thread of node 0, and a sched of node 0.
    let id = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 250)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 251)), DONE);
    // Move the thread's sched out of the way: bind the second one instead.
    let slot = 200u32;
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::SchedConfigure {
                sched: s(250),
                core: on_core(0),
                budget: 500_000,
                period: 10_000_000,
                class: 1,
            },
        ),
        DONE
    );
    // Node 0 grants node 1 the thread (a remote capability of the thread).
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Recv {
                endpoint: MAILBOX,
                reply: s(99),
                range: Range {
                    first: s(110),
                    count: 1
                },
                wait: 0,
            },
        ),
        WAITS
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::Send {
                target: on_core(1),
                message: carrying(1, vec![Transfer::Derive(s(slot), NOT_EXEC.bits())]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    assert!(
        sys.node(1).object_at(t[1], s(110)).is_some(),
        "node 1 holds the thread `{id:?}`"
    );
    // Node 1 configures its own sched with the thread of node 0.
    assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 250)), DONE);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::SchedConfigure {
                sched: s(250),
                core: on_core(1),
                budget: 500_000,
                period: 10_000_000,
                class: 1,
            },
        ),
        DONE
    );
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        sys.apply(
            1,
            t[1],
            Syscall::SchedBind {
                sched: s(250),
                thread: s(110),
            },
        )
    }));
    assert!(outcome.is_err(), "expected the panic of a foreign thread");
}

// ------------------------------------------------------------------ F8 -----

/// F8: a unit request is retried only while the role word names another
/// holder than the one it was last sent to; a role that goes back to that
/// holder before the requester runs leaves the request waiting for ever.
#[test]
fn f8_a_unit_request_is_never_retried_after_the_role_returns_to_its_holder() {
    let (mut sys, t) = started(3);
    let attacher = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(
        sys.apply(0, t[0], retype(ObjectKind::IoSpace, 0, 100)),
        DONE
    );
    // Node 0 asks the holder of the IOMMU unit role for a change.
    assert_eq!(
        sys.apply(
            0,
            attacher,
            Syscall::IoSpaceAttach {
                iommu: s(19),
                iospace: s(100),
                device: 0x33,
            },
        ),
        WAITS
    );
    // Node 1 hands the role to node 2 and node 2 takes it.
    assert!(matches!(
        sys.apply(1, t[1], Syscall::RoleHand {
            role: s(20),
            core: on_core(2)
        }),
        Ok(Output::Epoch(_))
    ));
    assert!(next_in(&mut sys, 0, 1), "the unit request");
    assert!(next_in(&mut sys, 1, 0), "its refusal");
    assert_eq!(sys.recover(1), 1);
    assert_eq!(sys.role(0).holder(), 2);
    // Node 2 hands it back to node 1.
    assert!(matches!(
        sys.apply(2, t[2], Syscall::RoleHand {
            role: s(20),
            core: on_core(1)
        }),
        Ok(Output::Epoch(_))
    ));
    sys.run(sys.now() + 200 * MS, MS);
    assert_eq!(sys.role(0).holder(), 1);
    assert_eq!(
        sys.node(0).woken(attacher),
        None,
        "the request waits for ever after the role came back"
    );
}

// ------------------------------------------------------------------ F9 -----

/// F9: `thread_resume` during a move clears the suspension and the move then
/// answers, so the source thread is runnable with no context and no home.
#[test]
fn f9_a_resume_during_a_move_leaves_the_moved_thread_runnable() {
    let (mut sys, t) = started(2);
    // The thread to move, with its sched.
    assert_eq!(sys.apply(0, t[0], retype(Thread, 0, 300)), DONE);
    assert_eq!(sys.apply(0, t[0], retype(Frame, 1, 301)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::ThreadConfigure {
                thread: s(300),
                cspace: s(START_SLOT_CSPACE),
                aspace: ASPACE,
                fault: SlotAddr::NONE,
                page: s(301),
            },
        ),
        DONE
    );
    assert_eq!(sys.apply(0, t[0], retype(Sched, 0, 302)), DONE);
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::SchedConfigure {
                sched: s(302),
                core: on_core(0),
                budget: 500_000,
                period: 10_000_000,
                class: 1,
            },
        ),
        DONE
    );
    assert_eq!(
        sys.apply(
            0,
            t[0],
            Syscall::SchedSetCores {
                sched: s(302),
                core: on_core(0),
                window: 0,
                mask: 0b11
            },
        ),
        DONE
    );
    assert_eq!(
        sys.apply(0, t[0], Syscall::SchedBind {
            sched: s(302),
            thread: s(300)
        }),
        DONE
    );
    let source = sys.node(0).object_at(t[0], s(300)).unwrap();
    // The destination thread and sched, from node 1.
    assert_eq!(sys.apply(1, t[1], retype(Thread, 0, 400)), DONE);
    assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 401)), DONE);
    receive(&mut sys, &t, 0, 310, 2);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(0),
                message: carrying(
                    1,
                    vec![
                        Transfer::Derive(s(400), NOT_EXEC.bits()),
                        Transfer::Derive(s(401), NOT_EXEC.bits()),
                    ]
                ),
            },
        ),
        WAITS
    );
    sys.settle(32);
    let mover = thread_on(&mut sys, &t, 0, 200);
    assert_eq!(
        sys.apply(
            0,
            mover,
            Syscall::ThreadMove {
                thread: s(300),
                destination: s(310),
                sched: s(311),
                core: on_core(1),
                budget: 0,
                period: 0,
                class: 0,
            },
        ),
        WAITS
    );
    // Contract line 675: the thread runs only if the move is refused.
    assert_eq!(sys.apply(0, t[0], Syscall::ThreadResume(s(300))), DONE);
    sys.settle(32);
    assert_eq!(sys.node(0).woken(mover), Some(&DONE));
    assert!(
        sys.node(0).runnable().contains(&source),
        "the moved thread is runnable with no context and no home"
    );
}

// ----------------------------------------------------------------- F10 -----

/// F10, first part: step 4's message is refused when the target has already
/// taken the role, and the refusal is traced. Contract line 855 asks for
/// exactly that, so the model is right here; the test fixes the behaviour.
#[test]
fn f10_a_late_step_four_message_is_traced_as_a_refusal() {
    let (mut sys, t) = started(3);
    assert!(matches!(
        sys.apply(1, t[1], Syscall::RoleHand {
            role: s(20),
            core: on_core(2)
        }),
        Ok(Output::Epoch(_))
    ));
    // Node 2 takes the role before the message of step 4 arrives.
    assert_eq!(sys.recover(16), 1);
    assert_eq!(sys.role(0).state(), RoleState::Held);
    assert_eq!(sys.role(0).holder(), 2);
    sys.settle(32);
    assert!(has_refusal(&sys, 2), "a normal hand-over is traced as refused");
}

/// F10, second part: the window of a trace code is counted per node and per
/// code (contract line 1295), so one peer can fill it for every other peer.
/// The model follows the contract here; the test fixes the numbers.
#[test]
fn f10b_one_peer_fills_the_refusal_window_of_the_node_it_talks_to() {
    let (mut sys, t) = started(2);
    assert_eq!(sys.apply(1, t[1], retype(Notify, 0, 100)), DONE);
    for round in 0..18u32 {
        let child = 102 + round;
        // Node 0 waits for the capability, node 1 derives one and sends it.
        receive(&mut sys, &t, 0, 110, 1);
        assert_eq!(
            sys.apply(
                1,
                t[1],
                Syscall::CapDerive {
                    source: s(100),
                    destination: s(child),
                    rights: Rights::ALL.bits(),
                    badge: 0,
                },
            ),
            DONE,
            "derive, round {round}"
        );
        assert_eq!(
            sys.apply(
                1,
                t[1],
                Syscall::Send {
                    target: on_core(0),
                    message: carrying(1, vec![Transfer::Derive(s(child), Rights::SEND.bits())]),
                },
            ),
            WAITS,
            "send, round {round}"
        );
        sys.settle(32);
        // The peer drops its capability; the release is in flight when the
        // granter revokes the grant that it names.
        assert_eq!(
            sys.apply(0, t[0], Syscall::CapDelete(s(110))),
            DONE,
            "delete, round {round}"
        );
        assert_eq!(
            sys.apply(1, t[1], Syscall::CapRevoke(s(100))),
            DONE,
            "revoke, round {round}"
        );
        sys.settle(32);
    }
    let refusals = sys
        .node(1)
        .ring(false)
        .iter()
        .filter(|e| e.code() == TraceCode::Refused as u16)
        .count();
    assert_eq!(refusals, 16, "16 entries of one code in one window");
    assert_eq!(
        sys.node(1).suppressed(),
        2,
        "the two over the limit are counted, not written"
    );
}

// ----------------------------------------------------------------- N1 -----

/// Runs `call` and returns the text of the panic it raises, if it raises one.
fn panics(sys: &mut System, node: u16, thread: ObjId, call: Syscall) -> Option<String> {
    let caught = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let _ = sys.apply(node, thread, call);
    }));
    let text = caught.err().map(|payload| {
        payload
            .downcast_ref::<&str>()
            .map(|text| (*text).to_string())
            .or_else(|| payload.downcast_ref::<String>().cloned())
            .unwrap_or_default()
    });
    text
}

/// N1: contract 849 names the calls whose capability arguments may name
/// another node, and 851 sends such a call as one message. `ReplyRecv` is not
/// in that list (`remote.rs:246`), so a `ReplyRecv` whose endpoint lives on
/// another node is run against the caller's own node, and panics.
#[test]
fn n1_a_reply_recv_on_a_remote_endpoint_panics() {
    let (mut sys, t) = started(2);
    assert_eq!(sys.apply(1, t[1], retype(Endpoint, 0, 100)), DONE);
    receive(&mut sys, &t, 0, 110, 1);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(0),
                message: carrying(1, vec![Transfer::Derive(s(100), Rights::ALL.bits())]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    let call = Syscall::ReplyRecv {
        reply: s(99),
        message: carrying(2, Vec::new()),
        endpoint: s(110),
        range: Range {
            first: s(199),
            count: 1,
        },
        wait: 0,
    };
    let panic = panics(&mut sys, 0, t[0], call);
    println!("reply_recv on the endpoint of node 1: {panic:?}");
    assert!(
        panic.is_some(),
        "the endpoint of node 1 must be reached by a message, not by a lookup \
         in the tables of node 0"
    );
}

/// N1, second shape: `SchedConfigure` names a `sched` and a `core`, both
/// capabilities, and neither is in the list of 849 either, so the call is run
/// on the caller's node and the `sched` of the other node is not found.
#[test]
fn n1b_a_sched_configure_on_a_remote_sched_panics() {
    let (mut sys, t) = started(2);
    assert_eq!(sys.apply(1, t[1], retype(Sched, 0, 100)), DONE);
    receive(&mut sys, &t, 0, 111, 1);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(0),
                message: carrying(1, vec![Transfer::Derive(s(100), Rights::ALL.bits())]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    let call = Syscall::SchedConfigure {
        sched: s(111),
        core: on_core(0),
        budget: 1_000_000,
        period: 10_000_000,
        class: 1,
    };
    let panic = panics(&mut sys, 0, t[0], call);
    println!("sched_configure on the sched of node 1: {panic:?}");
    assert!(
        panic.is_some(),
        "the sched of node 1 must be reached by a message"
    );
}

// ----------------------------------------------------------------- F11 -----

/// The `way_out` of `liveness.rs:271-300`, copied here to see what it reads.
fn liveness_way_out(sys: &System) -> Result<(), String> {
    for node in 0..3u16 {
        let state = sys.member(node).state();
        if !matches!(
            state,
            MemberState::Live | MemberState::Sealed | MemberState::Dead
        ) {
            return Err(format!("node {node} stays {state:?}"));
        }
    }
    for role in 0..sys.node_count_roles() {
        let word = sys.role(role);
        if word.state() != RoleState::Vacant && sys.member(word.holder()).state() == MemberState::Dead
        {
            return Err(format!("role {role} names dead node {}", word.holder()));
        }
    }
    for node in (0..3u16).filter(|&n| sys.has(n)) {
        for (grant, (grantee, generation, _, state)) in sys.node(node).grant_entries() {
            let over = sys.member(grantee).state() == MemberState::Dead
                || sys.member(grantee).generation() != generation;
            if state == 2 || over {
                return Err(format!("grant {grant} of node {node} has no way out"));
            }
        }
    }
    Ok(())
}

/// F11: `way_out` reads the member words, the role words and the grant
/// entries, and nothing else, so a thread of one node that waits for ever on
/// an object of another node leaves it at `Ok`.
#[test]
fn f11_the_way_out_of_liveness_is_blind_to_a_thread_stuck_on_another_node() {
    let (mut sys, t) = started(3);
    assert_eq!(sys.apply(1, t[1], retype(Notify, 0, 100)), DONE);
    receive(&mut sys, &t, 0, 110, 1);
    assert_eq!(
        sys.apply(
            1,
            t[1],
            Syscall::Send {
                target: on_core(0),
                message: carrying(1, vec![Transfer::Derive(s(100), Rights::ALL.bits())]),
            },
        ),
        WAITS
    );
    sys.settle(32);
    // Node 0 waits on the notify of node 1, and node 1 never signals it: a
    // `Wait::Node` that is never answered, with a request in flight.
    assert_eq!(sys.apply(0, t[0], Syscall::Wait(s(110), 0)), WAITS);
    sys.settle(32);
    assert!(
        sys.node(1)
            .grant_entries()
            .iter()
            .any(|(_, (_, _, _, state))| *state == 0),
        "the grant the wait names is live, so the grant clause is read"
    );
    assert_eq!(
        liveness_way_out(&sys),
        Ok(()),
        "the way out of `liveness.rs` sees the state and calls it a way out"
    );
}
```

## Appendix B: `model/src/system.rs`, `mod verify_hydrogen_unit` (`system_verify_hydrogen_unit_tests.patch`)

```diff
--- a/model/src/system.rs
+++ b/model/src/system.rs
@@ -1473,6 +1473,242 @@
         assert_eq!(
             dodos_abi::member_transition(m_max, m_zero),
             Some(dodos_abi::Transition::Start)
+        );
+    }
+}
+
+#[cfg(test)]
+mod verify_hydrogen_unit {
+    use super::*;
+    use crate::remote::{Body, Packet};
+    use crate::roles::UnitOp;
+    use crate::Output;
+    use dodos_abi::{
+        ObjectKind, PageSize, Rights, SlotAddr, TraceCode, START_SLOT_ASPACE, START_SLOT_CSPACE,
+        START_SLOT_FIRST, START_SLOT_MAILBOX, START_SLOT_SCHED,
+    };
+
+    const DONE: Outcome = Ok(Output::Done);
+    const WAITS: Outcome = Ok(Output::Waits);
+    const UT: SlotAddr = SlotAddr::own(25);
+
+    const fn s(index: u32) -> SlotAddr {
+        SlotAddr::own(index)
+    }
+
+    const fn on_core(n: u32) -> SlotAddr {
+        SlotAddr::own(START_SLOT_FIRST + n)
+    }
+
+    fn retype(kind: ObjectKind, size: u64, destination: u32) -> Syscall {
+        Syscall::UntypedRetype {
+            untyped: UT,
+            kind,
+            size,
+            page: PageSize::Page as u64,
+            memory: 0,
+            destination: s(destination),
+        }
+    }
+
+    /// A started machine of two nodes; each node's first thread has a budget
+    /// and a reply object in slot 99.
+    fn started() -> (System, Vec<ObjId>) {
+        let (mut sys, t) = System::boot(&Machine::example()).unwrap();
+        for node in 0..2u16 {
+            assert_eq!(
+                sys.apply(
+                    node,
+                    t[node as usize],
+                    Syscall::SchedConfigure {
+                        sched: s(START_SLOT_SCHED),
+                        core: on_core(node.into()),
+                        budget: 1_000_000,
+                        period: 10_000_000,
+                        class: 1,
+                    },
+                ),
+                DONE
+            );
+            assert_eq!(
+                sys.apply(node, t[node as usize], retype(ObjectKind::Reply, 0, 99)),
+                DONE
+            );
+        }
+        (sys, t)
+    }
+
+    /// One more thread on `node`, with its own sched on that node's core.
+    fn thread_on(sys: &mut System, t: &[ObjId], node: u16, slot: u32) -> ObjId {
+        let spare = 3000 - 3 * (slot - 300);
+        let root = t[node as usize];
+        let calls = [
+            retype(ObjectKind::Thread, 0, slot),
+            retype(ObjectKind::Frame, 1, spare),
+            Syscall::ThreadConfigure {
+                thread: s(slot),
+                cspace: s(START_SLOT_CSPACE),
+                aspace: s(START_SLOT_ASPACE),
+                fault: SlotAddr::NONE,
+                page: s(spare),
+            },
+            retype(ObjectKind::Sched, 0, spare - 1),
+            Syscall::SchedConfigure {
+                sched: s(spare - 1),
+                core: on_core(node.into()),
+                budget: 500_000,
+                period: 10_000_000,
+                class: 1,
+            },
+            Syscall::SchedBind {
+                sched: s(spare - 1),
+                thread: s(slot),
+            },
+            Syscall::ThreadResume(s(slot)),
+        ];
+        for call in calls {
+            assert_eq!(sys.apply(node, root, call), DONE);
+        }
+        sys.node(node).object_at(root, s(slot)).unwrap()
+    }
+
+    fn caught(panic: std::thread::Result<()>) -> String {
+        let payload = panic.err().expect("a panic");
+        payload
+            .downcast_ref::<&str>()
+            .map(|text| (*text).to_string())
+            .or_else(|| payload.downcast_ref::<String>().cloned())
+            .unwrap_or_default()
+    }
+
+    /// F5, second part: `misdirected` takes a message whose request it does
+    /// not know as its own (`asked` returns `true` on `None`), so a spurious
+    /// `Body::Answer` is not refused, and `answered_request` takes one away
+    /// from `outstanding` while the proxy it stands for is still busy. The
+    /// calling node then sends a seventeenth request and the receiving node
+    /// has no free proxy.
+    #[test]
+    fn f5b_a_spurious_answer_frees_a_proxy_that_is_still_busy() {
+        let (mut sys, t) = started();
+        // Node 1 has a notify; node 0 gets a capability of it.
+        assert_eq!(sys.apply(1, t[1], retype(ObjectKind::Notify, 0, 100)), DONE);
+        assert_eq!(
+            sys.apply(
+                0,
+                t[0],
+                Syscall::Recv {
+                    endpoint: s(START_SLOT_MAILBOX),
+                    reply: s(99),
+                    range: crate::Range {
+                        first: s(110),
+                        count: 1,
+                    },
+                    wait: 0,
+                },
+            ),
+            WAITS
         );
+        assert_eq!(
+            sys.apply(
+                1,
+                t[1],
+                Syscall::Send {
+                    target: on_core(0),
+                    message: crate::Message {
+                        label: 1,
+                        flags: 0,
+                        words: vec![1],
+                        caps: vec![crate::Transfer::Derive(s(100), Rights::ALL.bits())],
+                        marks: 0,
+                    },
+                },
+            ),
+            WAITS
+        );
+        sys.settle(32);
+        // Sixteen threads of node 0 wait on that notify: sixteen proxies of
+        // node 0 at node 1.
+        let mut threads = Vec::new();
+        for index in 0..17u32 {
+            threads.push(thread_on(&mut sys, &t, 0, 300 + index));
+        }
+        for thread in &threads[..16] {
+            assert_eq!(sys.apply(0, *thread, Syscall::Wait(s(110), 0)), WAITS);
+        }
+        sys.settle(64);
+        assert_eq!(sys.node(0).outstanding.get(&1), Some(&16));
+        // A message that answers nothing, of the generation of node 1.
+        let generation = sys.member(1).generation();
+        sys.model(0).receive_packet(Packet {
+            from: 1,
+            generation,
+            to: 0,
+            body: Body::Answer {
+                id: 999_999,
+                outcome: DONE,
+            },
+        });
+        assert!(
+            sys.node(0)
+                .ring(false)
+                .iter()
+                .all(|entry| entry.code() != TraceCode::Refused as u16),
+            "the answer is not refused: `asked` answers true for an unknown request"
+        );
+        assert_eq!(
+            sys.node(0).outstanding.get(&1),
+            Some(&15),
+            "the count of the calling node drops while sixteen proxies are busy"
+        );
+        // The seventeenth request goes out, and node 1 has no proxy for it.
+        assert_eq!(sys.apply(0, threads[16], Syscall::Wait(s(110), 0)), WAITS);
+        let panic = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
+            sys.settle(64);
+        }));
+        let text = caught(panic);
+        println!("the panic of the seventeenth request: {text}");
+        assert!(
+            text.contains("counts its requests"),
+            "expected the expect() of serve_request, got {text:?}"
+        );
     }
+
+    /// F5, third part: `Body::Handed` and `Body::UnitRequest` name a role in
+    /// a word, and both index the role table with it unchecked; a
+    /// `UnitRequest` is exempt from `misdirected`. Both panic.
+    #[test]
+    fn f5c_a_message_naming_a_role_that_does_not_exist_panics() {
+        let (mut sys, _) = started();
+        let generation = sys.member(1).generation();
+        let handed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
+            sys.model(0).receive_packet(Packet {
+                from: 1,
+                generation,
+                to: 0,
+                body: Body::Handed { role: 999 },
+            });
+        }));
+        let text = caught(handed);
+        println!("the panic of a Handed with role 999: {text}");
+        assert!(!text.is_empty());
+
+        let (mut sys, _) = started();
+        let generation = sys.member(1).generation();
+        let unit = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
+            sys.model(0).receive_packet(Packet {
+                from: 1,
+                generation,
+                to: 0,
+                body: Body::UnitRequest {
+                    id: 1,
+                    role: 999,
+                    op: UnitOp::Invalidate,
+                    epoch: 0,
+                },
+            });
+        }));
+        let text = caught(unit);
+        println!("the panic of a UnitRequest with role 999: {text}");
+        assert!(!text.is_empty());
+    }
 }
```

## Appendix C: the ring rule (`ring_order.patch`)

```diff
--- a/model/src/system.rs
+++ b/model/src/system.rs
@@ -163,6 +163,15 @@
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
```

## Appendix D: the README of the test directory

```markdown
# Tests of the verification of review 7 (`gemini-hydrogen`), by deepseek

Everything here applies to `dodos-kernel` at `2afc901` and `Docs` at `3bc7597`.
No file of the repository was changed; this work was done in copies under `/tmp`.

## Files

| file | where it goes | what it is |
|---|---|---|
| `ring_order.patch` | `git apply` in the clone, before the others | the ring rule: `System::deliver(index)` panics when an older message of the same `from`/`to` is still in flight, so the messages of one ordered pair of nodes arrive in the order they were sent |
| `verify_hydrogen.rs` | `model/tests/verify_hydrogen.rs` | 21 integration tests: one or two per finding F1 to F11 of the reviewed report, plus the new finding N1 |
| `system_verify_hydrogen_unit_tests.patch` | `git apply` after the reviewer's `hydrogen/system_review7_unit_tests.patch` | `mod verify_hydrogen_unit` at the end of `model/src/system.rs`: 2 tests that push a hand-made packet and read `outstanding` |

## How to run

```sh
git clone /Users/btw/Documents/repos/dodos-kernel k && cd k
S=/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/review7/tests
cp $S/hydrogen/adversarial_review7.rs model/tests/            # the reviewed tests
git apply $S/hydrogen/system_review7_unit_tests.patch         # theirs, inside the crate
git apply $S/hydrogen/liveness_coverage.patch                 # their audit of liveness.rs
git apply $S/verify-hydrogen/ring_order.patch                 # the ring rule
git apply $S/verify-hydrogen/system_verify_hydrogen_unit_tests.patch
cp $S/verify-hydrogen/verify_hydrogen.rs model/tests/

export PATH="/nix/var/nix/profiles/default/bin:$PATH"
timeout 280 nix develop -c cargo test -p dodos-model --test verify_hydrogen            # 21 pass
timeout 200 nix develop -c cargo test -p dodos-model --lib verify_hydrogen_unit        # 2 pass
timeout 200 nix develop -c cargo test -p dodos-model --test adversarial_review7        # 12 pass, 6 fail
timeout 200 nix develop -c cargo test -p dodos-model --test liveness audit_liveness_coverage -- --nocapture
```

The 6 that fail are the reviewed tests that break the ring: f1b, f1c, f5a, f5b, f6, f7.
Each panics with `overtaking in the ring 0 -> 1` or `1 -> 0`.
My report says, for each of the six, whether the same fault is reachable by a legal order.

## Note on the tests

Every order in `verify_hydrogen.rs` is a legal one under the ring rule: no test relies on a message overtaking another of the same ordered pair.
The two tests of `verify_hydrogen_unit` use a hand-made `Body` packet with the generation of the sending node, and say so in the report.
```
