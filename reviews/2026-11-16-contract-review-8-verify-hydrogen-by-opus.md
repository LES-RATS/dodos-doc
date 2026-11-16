# Verification of contract review 8 (Hydrogen): what crosses between nodes, and failure

Report judged: [2026-11-16-contract-review-8-gemini-hydrogen.md](2026-11-16-contract-review-8-gemini-hydrogen.md), 12 findings.
Contract read: `architecture/kernel-interface.md` at Docs commit `0d282a3` (after `git pull`, already up to date). Between `d0916a9`, which the report read, and `0d282a3`, the only change to the contract is at lines 1574-1576 (the D-110 start-up list) and in the open point on the watchdog; no line the report quotes changed. Line numbers below are those of `0d282a3`.

Verifier: Claude Opus 5.5. Own explorer: `/tmp/verify8_opus_h/explore.py` (three models; run with `timeout 60 python3 -B -I /tmp/verify8_opus_h/explore.py`).

**The reviewer's scripts** (`/tmp/review8_hydrogen/explore_cross_node_rings.py`, `/tmp/review8_hydrogen/explore_cores_failure_sealing.py`) exist and run, and every line of output the report prints is reproduced. But every "contract" variant writes the reviewer's reading as one transition straight into a named bad state (for example, in scenario A, `if ep != cur_ep:` leads to `'stuck_dropped'`), and the invariant only tests for that name. Each "fixed" variant holds because the fix is written into its transitions, and each "vacuity" variant puts the bad transition back. So a check fails only if the reviewer's reading of the text is correct. The scripts do not test the text. They show the scenarios but prove nothing beyond them. Where my verdict differs from the report (5.4 for CPU TLBs, the G1 and G2 scenarios, 6's reset of the producer to 0), the script models a reading the text rules out.

## Table of verdicts

| # | Finding | Verdict | Severity (mine) | Correction in one line |
|---|---|---|---|---|
| 1 | `UnitRequest` of an old or handing epoch dropped by the receive check | CONFIRMED | blocks for ever | Take `UnitRequest` out of the epoch test of the check; the holder answers "elsewhere" to every request it does not serve, during steps 1 to 4 included |
| 2 | Resume drops live messages; omits R3 to R5 | CONFIRMED IN PART | blocks for ever (2a); unspecified (2b, 2c) | A resume keeps its consumer indexes and drains its rings under the check; it runs R0 to R5 for nodes whose generation ended while it was sealed |
| 3 | `Release` crossing `Revoke`; grant entry has no use index | CONFIRMED | blocks for ever; unspecified (index) | A `Release` that frees an entry in state *revoking* ends the waiting removal step; the grant entry holds the use index, learned from `SendAnswer` |
| 4 | Thread destroyed while waiting for `SendAnswer` | CONFIRMED IN PART | wrong result (grant entries leak) | `SendAnswer` carries the grant indexes and serials of its `Send`; the sender frees the undelivered ones from the answer, with or without a thread |
| 5 | "One-shot, bounded, nothing kept" fails for `ReportAsk`, `Revoke`, `UnitRequest` | CONFIRMED IN PART | wrong result; blocks for ever (end of reports); unspecified (remote IOMMU invalidation in a removal step) | Reports pulled by the new holder (ask from index *k*, answer with items and next index or end); sealing and starting nodes report; owners decide the IOMMU wait in the kernel ring. CPU TLB part is NOT A FAULT |
| 6 | Outgoing rings of a dead node never reset | CONFIRMED IN PART | unspecified (faulty peer stalls the receiver) | A message whose header fails the check of kind or length is consumed as one entry; reload part is not a fault |
| 7 | Target of `role_hand` dies after step 4 | CONFIRMED (and wider) | blocks for ever; also two nodes map one unit | The take-over of a handing word is judged on its target, never on the node that hands |
| 8 | Sealed written before the park request; no `panic` test; two-node seal | CONFIRMED IN PART | wrong result (8.1); unspecified (8.2); accepted price (8.3) | The last core raises its park request before it writes sealed; sealing to sealed requires `panic` = 0 |
| 9 | x86-64 bootstrap core parked inside its NMI handler; stub ignores the park request on wake | CONFIRMED (and wider) | blocks for ever (core lost until restart); breaks the fence (node unfenced) | The handler leaves the NMI by `IRET` into the park stub; the stub writes `parked` at every wake |
| 10 | ARM64 SDEI life cycle | CONFIRMED IN PART | breaks the fence (class 1 core unfenced) | Register, enable and unmask at every entry stub and after every power-down idle exit; how the handler stops the core needs a decision |
| 11 | `idle_until` overflow; busy core with no kernel event taken for stale | CONFIRMED IN PART | wrong result (healthy nodes fenced) | While a core is not idle its timer is armed at most `STALE_NS` / 2 ahead; `idle_until` is cleared at the exit from idle |
| 12 | D-128 points 4, 5, 10 | CONFIRMED IN PART | wording (12a); unspecified (12b, 12d) | `:939` names the caller's own node; the library multiplexes one watch; TOCTOU and dead mailbox are NOT A FAULT |
| N1 | (new) "In flight" counted two ways; the reserve for answers can overflow | CONFIRMED | blocks for ever | A request or send is in flight until its answer is consumed |
| N2 | (new) A removal done by a `Revoke` also sends `Release`, so the waiter can hang with no crossing | CONFIRMED | blocks for ever | A removal done by a `Revoke` sends no `Release`; with 3's fix either order ends the wait |
| N3 | (new) The contract allows a take-over while the target is in step 5 | CONFIRMED | breaks "one holder of a unit" | Same correction as 7 |
| N4 | (new) Any x86-64 bootstrap core that parked itself before its fence ends up unfenced | CONFIRMED | breaks the fence | Same correction as 9 (stub writes `parked` at every wake) |
| N5 | (new) R2 and removal steps run by a `Revoke` need a remote IOMMU invalidation but have no thread to wait | CONFIRMED | unspecified | Needs a decision of the owners, with 5.4 |

Count over the report's 12 findings: CONFIRMED 4 (1, 3, 7, 9); CONFIRMED IN PART 8 (2, 4, 5, 6, 8, 10, 11, 12); no finding is wholly NOT A FAULT, IMPOSSIBLE SCENARIO or NOT VERIFIED. Parts that fall inside them: NOT A FAULT for 5.4 (CPU TLBs), 6 (reload), 8.3 (accepted price), 12c and 12e; IMPOSSIBLE SCENARIO for the report's G1 trace (inside 5.4); NOT VERIFIED for two side claims of 9 (the section number in order 325384-086, and INIT clearing NMI blocking). New findings: 5, all CONFIRMED.

---

## Finding 1: `UnitRequest` of an old or handing epoch

**Verdict: CONFIRMED.** Severity: blocks for ever.

The lines say what the report says. Line 897 lists among the checks made "before anything changes": "a role message (`UnitRequest`, `Handed`, `ReportAsk`, `Report`) names the role's current epoch", and "A message that fails any of these changes nothing, is consumed, and is traced (code 11 ...)". Line 885 (the table row of `UnitRequest`) says "an old epoch is answered 'elsewhere' and the requester sends again to the holder the role word names", and line 1328 says "the holder refuses a request with another epoch (an answer between kernels that never reaches user space)". Line 948 repeats it: "a request with an old epoch is refused by the holder and sent again to the new one". So three sentences promise an answer and the one check that runs first drops the request with none.

Rebuilt scenario: R reads held (*X*, *e*) and sends `UnitRequest(e)`. *X* runs `role_hand` steps 1 to 4 and writes handing (*X* → *Y*, *e* + 1) before it drains R's ring. At the check, *e* is not the current epoch, so the message is consumed with no answer. R's thread is in *waiting for another node*, which "ends at the answer or with `gone` when that node is accused" (line 194), and "`thread_cancel` ends neither". *X* stays live, so the thread waits for ever.

A second gap sits next to it: step 1 of line 1329 says "*X* stops accepting new requests for *u*", without saying what it answers. A request with the current epoch *e* that arrives during steps 1 to 3 passes the check and then gets nothing defined. During handing, line 1317 makes *X* the holder the word names, so a requester that reads handing (*X* → *Y*, *e* + 1) sends to *X* with *e* + 1. That request passes the check, and *X*, which did "its last act on *u*" at step 4, has nothing defined to answer.

The reviewer's correction is right in direction but leaves both cases open. It also restates a sender condition that the first clause of line 897 already checks. Correction to paste:

- In line 897, replace "a role message (`UnitRequest`, `Handed`, `ReportAsk`, `Report`) names the role's current epoch, and comes from the node the step requires (the role word's holder or target, a requester for a request, a live node for a report)" with: "a role message other than a request (`Handed`, `ReportAsk`, `Report`) names the role's current epoch and comes from the node the step requires (the role word's holder or target, a node that reports); a `UnitRequest` passes this check whatever its epoch, and its epoch is judged by the holder (Roles)".
- In line 1328, after "the holder refuses a request with another epoch", add: "The holder answers 'elsewhere' to every request it does not serve: a request with another epoch, a request that arrives after step 1 of a planned hand-over of the unit, and any request while the role word is handing. A requester that receives 'elsewhere' while the word it reads is handing keeps the request in its node's list of waiting unit requests (What crosses between nodes) and sends it again once the word reads held, to the holder it names."

Checked against the rest: R0 (line 1215) already keeps the unit requests aimed at a dead holder in the same list. The list exists (line 904). No sentence makes a holder keep anything on behalf of a requester.

## Finding 2: `node_start` resume

**Verdict: CONFIRMED IN PART.** 2a confirmed (blocks for ever). 2b confirmed as an omission, but the hang it describes depends on Finding 3b. 2c is a contradiction of wording, which a general rule already covers once the node is live.

**2a.** Line 909: "When *Y* starts again (a fresh start with generation *g* + 1, or a resume with *g*), before it runs any thread, it sets the consumer index of every ring into it to that ring's producer index, so it consumes nothing sent before". The same bullet goes on: "A sealed node sends and consumes nothing: messages to it wait in its rings until it resumes or is accused". Those messages exist. A seal "finishes or refuses with `gone` the requests it serves" (line 1301), but nothing ends the waits of its own threads. A thread of *X* in `node_send` (line 922), or a removal waiting for `RevokeStep` (line 870), keeps waiting through the seal. *Y* answers into *Y* → *X* with receiver generation *g*. At the resume the answer is skipped, and *Y* is live, so the thread waits for ever (line 194). `Release` and `Signal` from holders are skipped in the same way. A skipped `Release` leaves *X*'s grant entry live after *Y* freed its use entry, and a later revocation of it then hangs as in Finding 3. A skipped `Signal` loses a doorbell, and the data plane signals only on empty to not empty (line 938), so the peer that waits on it may wait for ever. Nothing is gained by the skip at a resume: the check of line 897 already refuses every message whose sender's generation is over, or whose receiver generation is not *g*.

**2b.** Lines 874 and 1293 list R0 and R2 only. R3, for grants the resumed node made to a generation that ended while it was sealed, is missing. "When *Y* is reclaimed, *X* frees the grants whose grantee is that generation of *Y*" (line 874) is the rule, and a sealed *X* does not run it. Those entries stay live. The hang the report describes (a later revocation sends `Revoke` to *Y*(2), which drops it) happens only if *X* reads a non-zero count. Which use entry *X* reads is not defined at all (Finding 3b). If the read reaches the entry R6 cleared, the count is 0 and the entry is freed at once (line 870). So the hang is conditional, and the leak of entries is certain.

**2c.** Line 1238 already says that a sealed node "acknowledges before it runs any thread". That is R5, which lines 874 and 1293 do not list. The general rule "When *Y* sees *X* in fenced ... it finishes, in steps of its recovery reserve: R2 ... R5" (line 1220) applies to the resumed node once it is live, so the barrier is not frozen for ever. But the order line 1238 promises (before any thread) contradicts line 1293.

Correction to paste:

- Line 909, replace the sentence quoted above with: "When *Y* starts fresh with generation *g* + 1, before it runs any thread, it sets the consumer index of every ring into it to that ring's producer index, so it consumes nothing sent before. At a resume with generation *g* it keeps its consumer indexes and, after the steps of the resume, consumes what waited in its rings under the check (messages from a generation that is over are refused by the check)."
- Lines 874 and 1293, replace "runs R0 and R2 for every node whose generation ended while it was sealed" with "runs R0 to R5 for every node whose generation ended while it was sealed (R3 frees at once the grants to a generation that is already over; R4 and R5 only for a node still fenced or unfenced)".
- Line 1634 (the model plan, "the reset at a generation's end") is to be read as the fresh start only.

## Finding 3: `Release` crossing `Revoke`, and the missing use index

**Verdict: CONFIRMED.** Severity: blocks for ever (crossing); unspecified (index).

The crossing, rebuilt from the text: *X* writes *revoking*, reads a count above 0, sends `Revoke(G, s)`, and its thread waits (line 870). *Y* deletes its root, sends `Release(G, s)` and "frees its use entry once the message is in the ring" (line 872). At *Y*, the `Revoke` fails "matches the entry it names ... the use entry naming the sender as granting node ... and serial" (line 897), so it is consumed with no answer. At *X*, the `Release` passes the check (the entry has that serial and names *Y*). Line 872 then "frees the entry if its anchor has no descendant", and no sentence ends the waiting removal step. Line 194 gives the thread no other way out while *Y* lives. My model A reproduces it in 4 steps (`/tmp/verify8_opus_h/explore.py`, "A Revoke/Release [contract]"). The invariant fails when a removal waits with no answer queued and the entry is no longer revoking, or when the count in flight is not 0 once both rings are empty.

The index: line 870 makes *X* read "the count of *Y*'s use entry". The grant entry (line 864) holds the grantee, its generation, the serial, the state, the anchor, the doorbell and the links. Line 1614 says "the grantee's slot address leaves the grant entry". The use index is chosen by *Y* at delivery and kept in *Y*'s remote capability (line 866, bits 52-63), and no message carries it back. The text at `b15f37c` had "the slot address of the remote capability's root on the grantee (filled by the grantee's answer)"; pass 14B removed it and put nothing in its place. Without it, *X* must scan *Y*'s 4,096 use entries inside a removal step.

The reviewer's correction (a `Release` on a *revoking* entry wakes the waiter, and the count in flight is decreased) is correct: in my model it holds ("[reviewer]: HOLDS"). Its second part is written as a thinking aloud ("Wait: ..."), not as a sentence to paste. Correction to paste:

- Line 872, after "otherwise the anchor stays, held by nobody, until an ancestor's removal reaches it", add: "If the entry is *revoking* and a removal step waits for its `RevokeStep`, the `Release` also ends that wait as a `RevokeStep` that reports the root removed would, and the `Revoke` stops counting as in flight."
- Line 864, after "a state (2 bits ...)", add: "the index of the grantee's use entry (12 bits), written by the granting node's gate from the `SendAnswer`, which gives it for each frame delivered". Line 870, after "if the count of *Y*'s use entry is then 0": "(the use entry at the index the grant entry records, counted only if it names this node, this grant, its serial and this node's generation; a grant whose `SendAnswer` has not come back yet makes the removal step return `again` with no message)". Line 1614, add "the index of the grantee's use entry is in the grant entry (learned from `SendAnswer`)". There is room: 64 bytes of anchor, 10 bytes of fields, 8 of doorbell and 4 of links leave about 42 of the 128.

Siblings: N2 (the same hang with no crossing at all) and N1 (what "in flight" means).

## Finding 4: thread destroyed while waiting for `SendAnswer`

**Verdict: CONFIRMED IN PART.** Severity: wrong result (grant entries leak until the frame's next removal).

What holds: line 134 says "a wait for an answer of another node ends, and the answer, when it comes, finds no thread and is dropped". Line 922 says "A thread destroyed while it waits drops the answer, and the grants end as the answer says". These do not agree. Following 922 needs a place that knows which grant entries the send made, once the thread is gone. The `SendAnswer` row (line 892) carries only "delivered (with or without the frames) or `would_wait`". The node block keeps "the requests and sends it has in flight to each peer" (line 1366), but the text does not say it holds the grant indexes. So an implementation either keeps the grants live with nobody to free them, or frees them without the answer and may free grants that *Y* delivered.

What falls: "permanently leaked" is overstated. Each grant's anchor is a child of the caller's frame capability (line 867), so any removal of that frame on *X* reaches the anchor and revokes it. (That path does hit 3b's missing index.) The leak of a `SENDS_PER_PEER` credit does not follow from the text as written. Line 903 says "A sender counts its messages in flight from its producer index and the receiver's consumer index", and the consumed `Send` is no longer counted. It would follow under the other counting the text also uses (N1), which N1's correction adopts, so the correction below covers it.

Correction to paste:

- Line 892 (row 10), add: "It carries the grant indexes and serials of the `Send` it answers, each with its use index if delivered."
- Line 922, replace "At the answer, the sender frees the grant entries that were not delivered" with "At the answer, the sender frees the grant entries the answer names as not delivered, and records the use index of each delivered one; this is done whether or not the sending thread still waits, and the send stops counting as in flight".
- Line 134, replace "and the answer, when it comes, finds no thread and is dropped" with "and the answer, when it comes, finds no thread to wake; its effect on grants and on the count in flight is applied as for any answer".
- In line 897, the answer clause becomes "answers a request or a send this node sent to that sender and has not yet seen answered".

## Finding 5: "only one-shot operations cross; one bounded step; nothing kept on behalf of the sender"

**Verdict: CONFIRMED IN PART.** Taken one by one:

**5.1 One cursor for several rebuilds. CONFIRMED** (wrong result). Line 906 says "the reports of a rebuild as a cursor in the node block", and line 1366 says "its cursor of reports for a rebuild": singular. Rebuilds at the same time are the ordinary case. "node 0 holds every unit role from machine start-up" (line 1326), so its death makes one successor rebuild every unit at once and send one `ReportAsk` per unit to each node. The text says neither that a second ask waits nor that it replaces the first. If it replaces it, the first rebuild "clears every other entry no live node claims" (line 1330). The severity is wrong result, not breaks isolation: a cleared context entry blocks the node's own device and lets no node reach another's memory.

**5.2 Sealing and starting nodes are neither asked nor kept. CONFIRMED** (wrong result). Line 888 asks "each live node"; line 897 accepts "a live node for a report"; line 1330 keeps without a report only entries of "a sealed node or in its floor". A sealing node is "Owned, running ... Valid" (line 1140) and its devices run. A node resuming is starting with its iospaces as they were (line 1293). Both lose their context entries.

**5.3 No end to a node's reports. CONFIRMED** (unspecified; blocks for ever, or clears too early). A node with no item sends nothing, and nothing tells the new holder that a node's last `Report` has come. Line 1330's "Each report is bounded" bounds the count, not the end.

**5.4 `Revoke` cannot finish a TLB shootdown in one step.** For CPU TLBs: **NOT A FAULT.** Line 644: "a removal step never waits for another core (it returns `again`)". Line 327: "Meanwhile the frame capability's record is **unmapping** ...: a removal that reaches it returns `again` ... So the memory of a frame never returns to its untyped while a core of the node may still hold a translation to it". So the holder's step returns, its `RevokeStep` reports the root not removed, and line 870 has *X* "return `again` after each answer until *Y* reports the root removed". That is exactly the reviewer's "fixed" G3. The G1 scenario (done before the shootdown ends) is impossible: the root is not removed while a record under it is unmapping. On ARM64 the broadcast completes inside the step (line 326). For IOMMU invalidations: **CONFIRMED**, unspecified (see N5). Line 948 sends "the invalidation after an unmap ... including those done by removal steps" as a unit request "for which the caller waits in *waiting for another node*". A removal step run for a `Revoke` in the kernel ring has no caller thread, and the text gives the record no state like *unmapping* for a remote unit invalidation.

**5.5 `IOMMU_WAIT_NS` inside a reserve of 156 µs per 10 ms. CONFIRMED IN PART.** A kernel event is atomic under L1, and line 910 allows a `UnitRequest` "its wait, at most `IOMMU_WAIT_NS`" (1 ms, line 365). One such step overruns the reserve's budget by about 6.4 times (1 ms against 156 µs, line 1356). That breaks the claim of line 902, "under full load a message of the kernel ring waits at most one period of the recovery reserve (10 ms)", and the admission of other contexts on core 0 by up to 1 ms per step. It is bounded, so "unbounded kernel operation" is overstated. The case is the hardware-fault edge (a unit that does not confirm within 1 ms is a fault, line 365), but contract bounds are by construction.

The headline "breaks isolation" holds for none of 5.1 to 5.5.

Corrections:

- 5.1, 5.3 and the D-128 sentence together, to paste over rows 7 and 8 (lines 888-889) and the cursor clauses of lines 906 and 1366: "`ReportAsk` names the unit, the epoch and the index of the first item wanted; the asked node answers at once with one `Report` holding the items from that index that fit in one message and the index of the next item, or *end*. The new holder asks again until *end*, from each node, in steps of its recovery reserve; a `Report` is an answer (it has room in the reserve of answers), and the asked node keeps nothing." Line 906 then drops "the reports of a rebuild as a cursor in the node block", and line 1366 drops "its cursor of reports for a rebuild". Cost: at most about 5 round trips per node for 192 handles. A message has 11 entries of 64 bytes, and a handle is a few bytes (estimate, not measured).
- 5.2, lines 888, 897 and 1330: replace "each live node" and "a live node for a report" with "each node that is starting, live or sealing", and in line 1330 replace "a sealed node" with "a node that is starting, sealing or sealed".
- 5.4 (IOMMU) and 5.5: needs a decision of the owners. The options: (a) accept a kernel-ring step of up to `IOMMU_WAIT_NS`, and say that the reserve's budget overruns by it and that the 10 ms latency holds only when units confirm within the budget; (b) the holder answers "pending" when the unit has not confirmed within the step, and the requester sends the idempotent request again (the holder keeps nothing but the hardware queue's own state); (c) the holder keeps one slot per in-flight request (`REQUESTS_PER_PEER` × *n*) to answer later, an exception to D-128 to write down. I recommend (b): it keeps D-128 as decided and costs one more round trip only when the hardware is slow.

## Finding 6: outgoing rings of a dead node

**Verdict: CONFIRMED IN PART.** Severity: unspecified (a faulty peer can stall its receiver's ring).

What holds: line 897 refuses a message whose "kind and length are ones it knows" fail, and it is "consumed", but the text does not say by how many entries. A length of 0 consumed "by its length" never advances. This is needed with or without a reload. Line 897 accepts that "a kernel that lies ... damages ... availability", but a receiver that spins on one entry is an unbounded loop in the receiver's own kernel, which the bounds of line 910 exclude.

What falls: "nothing resets the outgoing rings" is not a fault. The producer index is "a 64-bit count that never goes back" (line 899), so the restarted node continues from it. Every entry left by the dead generation carries its sender generation, and the check refuses it ("the sender's member word is starting, live or sealing with that generation", line 897). The reviewer's branch where *Y*(2) "zeroes producer = 0" is not in the text, which says the count never goes back. An inflated producer is caught up by the receiver once consumption per bad entry is defined.

Correction to paste, line 897, after "is consumed, and is traced (code 11 ...)": "A message whose header fails the check of kind or length (a length of 0, above 11, or reaching past the producer index) is consumed as one entry. A producer index more than the ring's entries ahead of the consumer index counts as that many entries ahead, and the excess is traced."

## Finding 7: the target of `role_hand` dies after step 4

**Verdict: CONFIRMED, and wider than reported.** Severity: blocks for ever. The reviewer's correction breaks the one-holder guarantee.

Line 1329: "if *Y* dies after step 4, the successor of *Y* takes over with a rebuild". The gate condition (line 1321): "The holder is fenced or dead ... or the holder is unfenced". Line 1317: "for handing, the node that hands: it stays the holder the word names until the target writes held, so wherever a rule speaks of the holder of a role, a handing word names the node that hands". So with *X* live, no take-over passes the gate. `role_hand` is `busy` "if the role is not held by the caller's node" (line 1338). The reclaim barrier needs "every unit role is held, not handing" (line 1243), so every later death stays fenced. A seal of *X* "waits until the target has taken the role" (line 1154), and a sealing node has no timeout (`SEAL_NS` applies to a sealed node, line 1164), so the seal never ends. My model C, with *X* never dying, ends in "role word stays handing for ever".

Wider (N3): the same rule lets the successor of *X* take over when *X* dies after step 4. *X* is then the fenced holder named by the word, while *Y* is still in step 5 and has already mapped the unit's registers ("*Y* maps the unit through its gate ... and writes held", line 1329). Model C, contract variant, 4 steps: Y maps, X dies, S takes over and maps. The invariant fails when *Y* and *S* both map. That contradicts "Why two nodes never hold a unit role at once" (line 1333).

The reviewer's correction ("either the holder *X*, or the target *Y* ... is no longer starting, live or sealing") keeps that hole: model C, "[reviewer]", same 4-step trace. Correction to paste, line 1321, unit row, last column: "For a held word: the holder is fenced or dead, and `SETTLE_NS` has passed since the stop was confirmed; or the holder is unfenced and `FENCE_NS` + `SETTLE_NS` have passed since the first fence action. For a handing word: the same test applied to the target, never to the node that hands (after step 4 it no longer maps the unit), and the successor is computed from the target." Line 1329 then reads "if *X* dies after step 4, *Y* completes step 5; if *Y* dies after step 4, the successor of *Y* takes over with a rebuild". My model C, "[verifier]": HOLDS (no double mapping, no state stuck in handing).

## Finding 8: the seal

**Verdict: CONFIRMED IN PART.**

**8.1 Order of sealed and the park request. CONFIRMED,** but the severity is wrong result, not breaks isolation. Line 1301: "writes sealed, and parks every core after raising its park request". Line 1154 makes sealed "its last write before its last core parks". So for the last core, the park request is raised after sealed is written, and its `parked` still equals the old request. Line 1151 lets `node_start` resume when "Every core whose word names the node is confirmed parked by the seal's park request". If the gate reads "confirmed" as `parked` = request, it passes in that window, and the start request and NMI reach a core that has not yet parked. What happens next lies within the node: the old kernel's gate still accepts writes (the member word reads starting with the same generation, line 1165), and the start NMI can arrive before the stub halts. The core then never joins, and the node is accused stale after `START_NS` and loses its objects. No other node's memory is reached. Correction to paste, line 1301: "... writes the instant of its seal in its node beacon, raises the park request of each of its cores, parks every core but the one that writes, writes sealed as that core's last gate write, and parks it; their words stay *owned*."

**8.2 No test of `panic`. CONFIRMED IN PART,** as a contradiction. Line 1155 lets any live node accuse a sealed node with any evidence that holds, self included. Line 1163 says "A sealed node does not beat, so only the evidence kill, retire and seal can accuse it". A core that wrote `panic` and "parks itself" (line 1181) counts as parked for line 1154, so a node that found a failure in itself can become sealed. Under line 1163 it can then be resumed. Correction to paste, line 1154, condition: add "and `panic` in its node beacon is 0"; line 1163: "only the evidence self, kill, retire and seal can accuse it".

**8.3 Two nodes, the live one fails while the other seals.** The scenario is real, but it is the loss line 1257 accepts: "the last node is lost only by its own failure, and then the machine is lost". It extends to the seal window, during which a sealing node can neither accuse (line 1155, "any live node") nor go back to live. This is not a defect of the text. If the owners want to close the window: needs a decision of the owners (a transition sealing (*g*) → live (*g*) by the node itself while it still holds its roles, or letting a sealing node accuse and abort its seal). I would not add a transition for it.

## Finding 9: the x86-64 bootstrap core and NMI

**Verdict: CONFIRMED, and wider than reported** (N4). Severity: the bootstrap core is lost until restart, and a node holding it becomes unfenced.

Hardware, checked at a copy of the source. Intel SDM Vol. 3A, "6.7.1 Handling Multiple NMIs", in the edition mirrored at <https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-192.html>: "While an NMI interrupt handler is executing, the processor blocks delivery of subsequent NMIs until the next execution of the IRET instruction." The substance of the report holds. Two side claims are not verified. The report's quotation ("the processor masks further NMIs until the IRET instruction is executed") is not the SDM's wording but a paraphrase in quotation marks, and I could not open order 325384-086 to check its section number §7.7.1. Its claim that INIT clears NMI blocking on application processors is not verified either. The conclusion for the bootstrap core does not depend on it.

9.1: line 1199 has the handler "enter the park stub's loop with interrupts masked", with no `IRET`. Line 1200 sends no INIT to the bootstrap core. Line 1202 says "The stub is also how a parked core is started, the bootstrap core included, with no INIT", by an NMI (line 1120). With NMIs blocked since the fence's NMI, that start NMI is never delivered, the start fails after `START_NS`, and the core cannot run a node again before restart.

9.2: line 1202: "An NMI wakes it: it reads its start request and, if one names a node, goes to the entry stub; otherwise it halts again". It does not write `parked`. A parked core runs the stub's own NMI vector ("installs vectors for NMI", line 1202), not the kernel's handler of step 1. So a sealed node whose bootstrap core parked at the seal, and which is then accused (evidence seal after `SEAL_NS`, or kill), gets a raised request that nothing confirms. The node becomes unfenced (line 1158), and its memory is frozen until restart (line 1208). Application processors are saved by INIT and SIPI, which re-enter the stub (step 3).

N4, the sibling: the same happens without a seal. A core that finds a failure "parks itself" (line 1181), and `node_stop` of one's own node has "every core of the node park itself at the end of its current event" (line 1300). In both cases the fence raises the request afterwards (line 1196: "raises *p*'s park request, then marks ..."). A self-parked bootstrap core is then never confirmed. On a machine whose bootstrap core belongs to a node, every self-detected failure of that node ends unfenced.

Correction to paste. Line 1199, replace "and enters the park stub's loop with interrupts masked" with "and returns by `IRET` into the park stub, with interrupts masked, so that NMIs are delivered again". Line 1202, replace "An NMI wakes it: it reads its start request" with "An NMI wakes it: its handler writes the park request it reads into `parked`, reads its start request, and returns by `IRET`; if the start request names a node the stub goes to the entry stub; otherwise it halts again". The reviewer's correction says the same in substance.

## Finding 10: ARM64 SDEI

**Verdict: CONFIRMED IN PART.** Severity: a class 1 core can stay unconfirmed (node unfenced).

Checked against TF-A v2.12.0 (`services/std_svc/sdei/`, fetched from the tag) and Linux master (`arch/arm64/kernel/smp.c`, fetched 16 November 2026):

1. **Enable.** The report's citation is wrong: `sdei_signal` (sdei_main.c, line 911) checks only that the event is 0, mapped and signalable, and a valid target. It raises the SGI without testing registration or enable. The substance holds through the dispatch path. In sdei_state.c, the state table (lines 69-88) allows DISP only from `rEG_` (registered and enabled); from `reG_` (registered, not enabled) DISP is `X___`. sdei_intr_mgmt.c lines 438-454 then "leave the interrupt pending so that it's delivered when the event is enabled". So without `SDEI_EVENT_ENABLE` the fence's handler never runs. Line 1205 and kernel.md line 149 name "registration, unmasking", not enable.
2. **`CPU_ON` resets private events.** Confirmed: `sdei_cpu_on_init` (sdei_main.c, lines 65-84) clears each private entry (`se->state = 0`) and calls `sdei_pe_mask()`, and it is subscribed to `psci_cpu_on_finish` (line 1111). Line 1120 has the entry stub only unmask, so every core started by `CPU_ON` has event 0 unregistered.
3. **Power-down suspend masks the PE.** Confirmed: `sdei_cpu_wakeup_init` (lines 87-95) calls `sdei_pe_mask()`, subscribed to `psci_suspend_pwrdown_finish` (line 1114). A trigger on a masked PE is acknowledged and lost: "This PE is masked. We EOI the interrupt, as it can't be delegated" (sdei_intr_mgmt.c, lines 351-352). `node_idle` method 2 with flag bit 0 (line 1306) leads there.
4. **`CPU_OFF` from inside the handler.** The Linux comment exists, at smp.c lines 886-892 of master (not 840-844): "it runs inside an SDEI event that is deliberately never completed (completing it has firmware resume the wedged context), and a CPU_OFF from that not-yet-completed context wedges EL3 on some firmware". But the report says that Linux "completes with `COMPLETE_AND_RESUME` into a stub that then calls `CPU_OFF`". That is false: the same comment says the SDEI path passes false "and only park[s]".

Correction to paste for 1 to 3. Line 1120, replace "which unmasks the fence's signal first (ARM64: `SDEI_PE_UNMASK`)" with "which arms the fence's signal first (ARM64: `SDEI_EVENT_REGISTER` and `SDEI_EVENT_ENABLE` of event 0, then `SDEI_PE_UNMASK`, since PSCI `CPU_ON` clears the private events)". In the `node_idle` paragraph (line 1306), add: "On ARM64, a core that leaves a state that loses its context calls `SDEI_PE_UNMASK` before it runs anything else". In kernel.md line 149, "SDEI registration, enabling of event 0, and unmasking".

For 4: needs a decision of the owners, or a trial. The options: (a) the handler completes with `SDEI_EVENT_COMPLETE_AND_RESUME` to a stub that calls `CPU_OFF` (not checked on firmware); (b) the handler parks without completing, as Linux does, and confirmation is the handler's write of `parked`, which makes such cores signalled but confirmed by the dying kernel's code, as line 1205 already accepts for a Trusted OS core.

## Finding 11: `idle_until` and stale evidence

**Verdict: CONFIRMED IN PART.** Severity: wrong result (healthy nodes fenced).

- The overflow: the text is arithmetic, and "the largest value" + `STALE_NS` is not below now in arithmetic. It is a trap for the implementation only (wording). Write the test as "now − `STALE_NS` > `idle_until`".
- Reset at the exit from idle: CONFIRMED, unspecified. Line 1171 sets `idle_until` "when it goes idle" and never clears it. A core woken early by an interrupt keeps a far `idle_until` (the largest value if no timer was armed) and cannot be found stale if it then hangs.
- A busy core with no kernel event: CONFIRMED, wrong result. The heartbeat is "written at the exit of every kernel event" (line 1171); "there is no periodic tick" (line 614); "With nothing armed, it is not set" (line 564); a period may be up to 2^36 ns (line 483). A thread that computes for more than `STALE_NS` (100 ms) with no system call makes its core's heartbeat stand still. The sweep then fences a healthy node, and on a node of several cores the node accuses itself (line 651). Line 1191 accepts fencing a slow node for stalls, not for ordinary computation.

Correction to paste. Line 564, after "With nothing armed, it is not set": "except that while the core runs a thread the timer is set no later than now + `STALE_NS` / 2, an event that only beats". Line 1171: "`idle_until` ... when it goes idle (the largest value if none), and 0 again at its first event after idle". Line 1182: "now − `STALE_NS` > `idle_until`".

## Finding 12: D-128 points 4, 5 and 10

**Verdict: CONFIRMED IN PART.** Separated:

- **Prices of D-128, accepted, not defects.** A remote wait no longer ends at the peer's death, and no lending crosses nodes (lines 939, 943, 2091). Only owners grant frames, nothing but frames crosses, and the signal is tied to a grant (line 2092). Every node needs a mailbox agent, and a node whose agent died is unreachable until it is restarted (line 2097). The report agrees.
- **12a. CONFIRMED** (wording). Line 939 says "binds `node_watch` for the peer's node", while lines 1281 and 1308 require that the node "name the caller's node". Line 1308 also signals "after each change of a member word or a role word that the node processes", the peer's included, so the right call exists. Correction to paste, line 939: "binds `node_watch` on its own node to the same notify with another badge bit, which is signalled after each change of a member word its node processes, the peer's included, and reads the peer's member word in the frame of slot 13 after binding and after each wake".
- **12b. CONFIRMED** (unspecified). With `NODE_WATCH_SLOTS` = 4 per node, held by "The node agent and up to three supervisor replicas" (line 1357), a binding per wait as line 939 describes cannot be made. Correction to paste, after the sentence above: "The library binds no watch per wait: the node agent holds one and signals the local waiters whose peer changed."
- **12c. TOCTOU: NOT A FAULT.** Line 1308 signals "at least once after each change", and the member word is readable at any time through slot 13. A waiter that reads the word after binding, as the correction of 12a says, misses no death.
- **12d. One `SENDS_PER_PEER` shared by every process of a node. CONFIRMED** (availability inside a node). Line 907 counts per node pair, so any process can hold the 8 sends to a peer and make `node_send` from the supervisor return `busy` (line 921). Its amplification "threads destroyed in flight per Finding 4" does not follow from line 903. Needs a decision of the owners: a per-task quota or reserved sends for the reserve roles' holders, or accept it, with the placement service and supervisor as the defence.
- **12e. Dead mailbox and `would_wait`: NOT A FAULT.** It is the accepted price of line 2097, "a node whose agent has died is unreachable from other nodes until a supervisor restarts it".

---

## New findings

### N1: "in flight" is counted two ways, and the reserve for answers can overflow

**CONFIRMED.** Severity: blocks for ever.

Line 903: "A sender counts its messages in flight from its producer index and the receiver's consumer index". Line 904: "until an earlier request to that peer is answered". Line 1366: the node keeps "the requests and sends it has in flight to each peer". Line 905 rests on the second reading: "the kernel ring *Y* → *X* keeps `REQUESTS_PER_PEER` + `SENDS_PER_PEER` entries for the answers to *X*, which *X* bounds by its own limits". Under the first, a request stops counting once *Y* has consumed it, while its answer still waits in *Y* → *X* for *X*'s reserve to consume it. So *X* can have any number of answers waiting. My model B ("[index]") reaches 25 answers in the 24-entry reserve; under "until answered" it holds. Once the reserve is full, an answer has no room, and "no kernel ever waits on a full ring" (line 903) leaves *Y* no defined act: the answer is lost and its thread waits for ever.

Correction to paste, line 903: "A request or a send is in flight from the moment it is written until the sender has consumed its answer, or until the peer's generation ends (R0); the sender keeps these counts in its node block." Line 1634 (the model plan): the counts are to be tested against this.

### N2: a removal done by a `Revoke` also sends `Release`

**CONFIRMED.** Severity: blocks for ever, with no crossing at all.

Line 872: "When *Y* removes the root remote capability of a grant (by any removal), it sends *X* a `Release`". The removal that a `Revoke` drives is one of them. Within that step *Y* writes both `Release` and the `RevokeStep` that reports the root removed, in an order the text does not fix. If `Release` comes first, *X* frees the entry and its serial grows (line 865). The `RevokeStep` then fails "matches the entry it names ... that serial" (line 897) and is dropped, and the removal waits for ever. Model A with the holder's own deletion turned off: contract variant, hang in 4 steps (Release then Step); the reviewer's and my corrections hold.

Correction to paste, line 872, after "(by any removal)": "other than a removal done for a `Revoke`, whose last `RevokeStep` stands for the release". With Finding 3's correction, either order then ends the wait.

### N3: the contract allows a take-over while the target is in step 5

**CONFIRMED.** Severity: breaks "Why two nodes never hold a unit role at once" (line 1333). See Finding 7: model C, contract variant. Closed by the same correction.

### N4: a self-parked x86-64 bootstrap core is never confirmed

**CONFIRMED.** Severity: breaks the fence (the node is unfenced). See Finding 9: lines 1181, 1196, 1202 and 1300. Closed by the same correction (the stub writes `parked` at every wake).

### N5: R2 and removal steps run by a `Revoke` need a remote IOMMU invalidation and have no thread to wait

**CONFIRMED.** Severity: unspecified.

R2 runs in the recovery reserve and removes mappings "on its iospaces through the unit role holders" (line 1222). A `Revoke` is a removal step in the kernel ring. Line 948 makes each such invalidation a unit request "for which the caller waits in *waiting for another node*". Neither has a caller, and "A request is held by the thread that waits for it" (line 1328). The CPU case has its rule (the record stays *unmapping*, the step returns `again`, line 327); the IOMMU case has none. Needs a decision of the owners, with 5.5. The option I recommend: extend *unmapping* to "a unit invalidation in flight", hold the request in the record (linked into a list in the node block, at most `REQUESTS_PER_PEER` per unit holder), and have the step return `again` until the `UnitAnswer`.

