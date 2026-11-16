# Review 8 (Hydrogen) judged by a second model: cross-node messages, rings, and failure

Report judged: [2026-11-16-contract-review-8-gemini-hydrogen.md](./2026-11-16-contract-review-8-gemini-hydrogen.md), 12 findings, angle "what crosses between nodes, and failure".

Contract read: [kernel-interface.md](../architecture/kernel-interface.md) in the Docs repository at commit `0d282a3`, whose file was last changed by `fa90461`; every line quoted below is byte-identical to `d0916a9`, so the report's line numbers hold.

My explorer: [/tmp/review8_verify_deepseek/explore.py](/tmp/review8_verify_deepseek/explore.py), run with `timeout 120s python3 -B -I /tmp/review8_verify_deepseek/explore.py` (13 checks, exit 0, output in `/tmp/review8_verify_deepseek/out.txt`). Each finding below is modelled as a state machine taken from the contract's sentences, with one queue per ring and the two rings of an ordered pair delivered in order. Every check is run twice: with the contract's rule and with one mutation. The mutation is named at each check and the two results are printed; a check whose mutation cannot break it is called out as one that cannot fire. Four of the report's scenarios (its `D2`, `F1`, `G1`, `G2`) are shown to fail on a rule the text does not contain, and two of its checks (`D2`, `E2`) can only fire through a transition the text does not allow.

## Verdicts

| # | Verdict | Severity in my judgement | The correction, in one line |
|---|---|---|---|
| 1 | CONFIRMED | `blocks for ever` | In `:897`, `UnitRequest` leaves the epoch condition and a request of any epoch is answered, never dropped silently; in `:1328` a requester answered "elsewhere" sends again to the node the word names as holder **or as target while it is handing**, and the target keeps a request of the handing epoch until it writes `held`. |
| 2 | CONFIRMED IN PART — part 1 only | `blocks for ever` | `:909`: at a resume with generation *g* the consumer indexes are kept and the rings into the node are drained under the receive check; the sentence "messages to it wait in its rings until it resumes" then stands. Parts 2 and 3 (R3, R5) fall. |
| 3 | CONFIRMED | `blocks for ever` (the missing `use_index`: `unbounded kernel operation`) | `:872`: a `Release` that frees an entry in state *revoking* ends the wait of the thread that waits for `RevokeStep` on that entry; and `:864`'s grant entry records the index of the use entry it addresses. |
| 4 | CONFIRMED IN PART — the leak under one reading; the credit half falls | `wrong result` | `:897`: an answer answers a request this node sent to that sender and has not resolved, even if the thread that sent it was destroyed; `:922` then frees the grants the answer says were not delivered. |
| 5 | CONFIRMED IN PART — items 1 to 5 stand | `wrong result` for 1, 2, 3; `blocks for ever` for 3's missing end; `unbounded kernel operation` for 4 and 5 | Per item, in the detail below. |
| 6 | NOT A FAULT | `unspecified` (a different gap, `blocks for ever`) | No rule resets the producer, and none should: `:899` says both counts never go back. What the text owes is how far the consumer advances past a message whose length it does not know. |
| 7 | CONFIRMED | `blocks for ever` | `:1321` gains a row for a handing word: the successor takes the role when the **target** is fenced, unfenced or dead, with this table's delays; the handing node may not map the unit again. |
| 8 | CONFIRMED | `breaks isolation` (a) and `blocks for ever` (c) | Raise the last park request in the same gate call that writes `sealed` and check `panic` there; add `sealing → live` for a node that finds no other live node. |
| 9 | CONFIRMED | `blocks for ever` | The NMI handler returns by `IRET` into the stub and the stub writes `parked` after every wake. |
| 10 | CONFIRMED IN PART — claims 1 and 4 verified, 2 and 3 not verified here | `blocks for ever` | Add `SDEI_EVENT_ENABLE` to `:1205`, `:1120` and [kernel.md:149](../architecture/kernel.md#L149), and complete the event with `SDEI_EVENT_COMPLETE_AND_RESUME` into a stub that calls `CPU_OFF`. |
| 11 | CONFIRMED | `wrong result` (it fences healthy nodes) | `:1182` adds with saturation (or the guard is skipped when nothing is armed), and a non-idle core arms a heartbeat event no later than `now + STALE_NS / 2`. |
| 12 | CONFIRMED IN PART — items 1 to 3 stand, 4 and 5 do not | `blocks for ever` for item 1 | `:939` must say the node agent multiplexes one `node_watch` bound on the caller's own node, `:1308` must signal on the bind as well as on each change, and the slot count is a decision of the owners. |

Verdicts in count: CONFIRMED 6 (1, 3, 7, 8, 9, 11); CONFIRMED IN PART 5 (2, 4, 5, 10, 12); NOT A FAULT 1 (6); IMPOSSIBLE SCENARIO 0; NOT VERIFIED 0.

---

## Finding 1 — an old-epoch or `handing` `UnitRequest` is dropped, and the caller waits for ever

**CONFIRMED.** `blocks for ever`.

Two sentences of the contract cannot both hold:

- `:885`, row 4: "an old epoch is answered "elsewhere" and the requester sends again to the holder the role word names; at R0 it is kept for the next holder".
- `:897`: "a role message (`UnitRequest`, `Handed`, `ReportAsk`, `Report`) names the role's current epoch, and comes from the node the step requires … A message that fails any of these changes nothing, is consumed, and is traced (code 11 …)".

An old-epoch `UnitRequest` fails the first clause of `:897`, so it is consumed with no answer; `:885` says it is answered "elsewhere". `:1328` agrees with `:885` and not with `:897`: "the holder refuses a request with another epoch (an answer between kernels that never reaches user space), and the requester reads the role word again and sends it to the holder it names". So the report quotes the lines correctly and the contradiction is real.

The end of the wait. Nothing else ends it: `:194` says the state "ends at the answer or with `gone` when that node is accused"; `:1215` (R0) ends the waits for answers of a node that is **fencing**, and here *X* is live and healthy; `:922`'s `thread_cancel` does not end a `node_send` wait, and `:1329` step 1 has *X* already refusing to serve the unit. So the thread waits for ever, and `:194`'s "both are bounded" is false in this case.

The report's scenario is right, and its own interleaving is not the only one. The case that needs no race at all is the one `:885` and `:909` promise to handle: a request kept at R0 "for the next holder" (`:1215`: "it keeps the unit requests aimed at a role *X* holds, to send them again once the role word names a live holder"; `:909`: "except a unit request to a role *Y* held, which it keeps and sends again to the next holder") carries the epoch of the dead holder, and the next holder's `:897` drops it. My check `S1d` traces exactly that: the kept request carries `e1`, the new holder is at `e2`, code 11, the thread waits. The mechanism the contract gives for surviving a holder's death is the mechanism that guarantees the drop.

**The correction I would write**, in two places, because the report's single sentence is incomplete:

> `:897`: "a role message (`Handed`, `ReportAsk`, `Report`) names the role's current epoch and comes from the node the step requires; a `UnitRequest` names any epoch and may come from any node that is starting, live or sealing, and is answered "elsewhere" when its epoch is not the role's or the role is not held by this node."

> `:1328`: "the requester reads the role word again and sends it to the holder it names, or, while the word is handing, to the target, which keeps a request of the handing epoch and serves it when it writes held."

My check `S1b` is that second half: with the report's fix alone and `:1328` unchanged, the requester is answered "elsewhere" by *X* four times in a row and never reaches a holder that serves it (trace in `out.txt`), because `:1317` keeps *X* as the holder "until the target writes held" and `:1328` sends the requester back to the holder.

## Finding 2 — `node_start` mode `resume`

**CONFIRMED IN PART.** Part 1 stands; parts 2 and 3 fall. `blocks for ever` for part 1.

**Part 1, the ring reset. CONFIRMED.** `:909` in one sentence says both "it sets the consumer index of every ring into it to that ring's producer index, so it consumes nothing sent before" and, three clauses later, "messages to it wait in its rings until it resumes or is accused". My check `S2a`: *X* waits for a `RevokeStep` (`:870`), is sealed, *Y* answers into *Y* → *X* while *X* is sealed, *X* resumes with the same generation, `:909` discards the answer, and the thread waits in `waiting for another node` for ever — *Y* is live, so nothing in R0 or `:909`'s "what ends with a generation" reaches it. The mutation that clears it is the report's fix.

**Part 2 (R3) falls.** The gap it needs is closed twice in the text. `:874`: "when *Y* is reclaimed, *X* frees the grants whose grantee is that generation of *Y*" — no condition on *X*'s state, so a resumed *X* owes that freeing; and `:1220`: "When *Y* sees *X* in **fenced** (or unfenced, for R2 to R5 only as far as they touch *Y*'s own memory), it finishes, in steps of its recovery reserve" — so a resumed *X*, now live and reading the beacons, runs R3 for any grantee still fenced. My check `S2c` cannot fire: with `:867` and `:1220` in the model the grant is either pinned (grantee fenced) or freed (grantee dead, and its devices already blocked by R1 and by the barrier of `:1243`). The report's *mechanism* also fails: its step 3 needs *X* to read a stale use count, but `:1229` (R6) frees "every entry of *X*'s use table" of the dead node, so the count `:869` reads is 0 and `:870` frees the grant "at once", with no `Revoke` and no wait. `S2d` is that check, and it cannot fire; its trace shows the count is already 0.

**Part 3 (R5) falls for the same reason, and leaves one wording fault.** `:1238`'s cell for a sealed node reads "`maps_of` bit *X* clear (a sealed node that maps *X*'s memory delays *X* until it is resumed, and acknowledges before it runs any thread, or killed)". `:1293` and `:874` have the resume run R0 and R2 only, and only R5 "clears `maps_of` bit *X* and writes `acked[X]` = *g*" (`:1225`). So the parenthetical promises a write the resume does not make — a **wording** fault. It is not a deadlock, because the resumed node is live and `:1220` then has it run R2 to R5 for every node it sees fenced, and the barrier of `:1233` waits on `acked`, which that run writes. My check `S2b` shows both sides: with `:1220` in the model the barrier holds and *Z* dies; with `:1220` removed — the report's premise — *Z* stays fenced for ever. Remove the premise and the finding goes.

**Correction:** as in the table for part 1; and for part 3, write `:1238`'s parenthetical as "acknowledges in the recovery that follows its resume, before any thread of its own runs on a mapping of *X*'s memory" — or add R5 to `:1293` and `:874`, which is cheap and keeps the promise literal.

## Finding 3 — a `Release` crossing a `Revoke`

**CONFIRMED.** `blocks for ever`; the `use_index` half is a separate `unbounded kernel operation`.

The crossing is real and nothing in the text closes it. *X*'s thread waits for `RevokeStep` (`:870`, `waiting for another node`). *Y* removes the root remote capability, "frees its use entry once the message is in the ring" (`:872`) and sends `Release`. *Y* then reads the `Revoke`, fails `:897`'s match ("the use entry naming the sender as granting node with that generation and serial") and answers nothing. *X* then reads the `Release`, which `:872` says to act on "only if the entry has that serial and names *Y*" — it does — so *X* frees the entry, and no sentence wakes the thread. The two rings are independent (`:900`: "Messages of different rings may arrive in any order relative to each other"), so the crossing is allowed, and `S3` reaches it in four steps: the thread stays in `waiting for another node` with both rings empty and nothing left to do.

Two things the report gets slightly wrong.

- `S3b` shows the non-crossing order is safe: a `Revoke`-driven removal also sends a `Release` (`:872` "by any removal"), but the ring *Y* → *X* delivers in order, so the `RevokeStep` is taken first and the later `Release` is consumed as stale by `:897`. Only the crossing breaks it.
- The `use_index` half: `:869` has *X* read "the count of *Y*'s use entry" after writing *revoking*, and nothing in the grant entry names that entry — `:864` lists the anchor, the grantee, its generation, the serial, the state, the doorbell and the link fields, and `:1614` records that "the grantee's slot address leaves the grant entry"; `:866` puts the use index in the **remote capability on *Y***, which *X* cannot read. So *X* must scan *Y*'s 4,096 use entries of 32 bytes, which contradicts `:910`'s "Each node does constant work per message". It is bounded, so it is not `blocks for ever`; it is `unbounded kernel operation` (128 KB read inside a gate call) and a real gap. The report's proposed `SendAnswer(delivered)` route is sound and its own parenthesis shows it knew the alternative: the entry a `node_send` makes is written by *X* before the message leaves, so the cleanest is for *X* to choose the index and name it in the message.

**Correction:** in `:872`, after "it then frees the entry if its anchor has no descendant in *X*'s list": "If the entry is in state *revoking* and a thread waits for `RevokeStep` on it, this message ends that wait, with `again` when the removal is not finished and with success when it is." In `:864`, "and the index of the use entry it addresses on the grantee (12 bits)".

## Finding 4 — a thread destroyed while it waits

**CONFIRMED IN PART.** The leak stands under one reading of `:897`; the credit half falls; the severity is `wrong result`, not `blocks for ever`.

The case is not settled: `:134` says "a wait for an answer of another node ends, and the answer, when it comes, finds no thread and is dropped", `:922` says "A thread destroyed while it waits drops the answer, and the grants end as the answer says", and `:897` accepts an answer only if it "answers a request this node sent to that sender and **still waits for**". Read `still waits for` at thread level and the answer is consumed with code 11 and `:922` never runs: the grant entries stay live, and `S4a` shows the state with one live grant and nothing left to do. Read it at node level — this node has an unresolved send — and the answer frees the grants and `:922`'s last clause is true. `S4a` runs both readings and only the first leaves the grant live. My verdict is that the *sentence* is wrong, not that the design is.

The credit half of the finding has no rule behind it. `:903`: "A sender counts its messages in flight from its producer index and the receiver's consumer index" — so the slot of a `Send` is reclaimed when the *receiver* consumes the message, whatever happens to the thread, and `:905`'s answer reserve is bounded by those indices too. `S4b` builds the report's leak as a check and it cannot fire: in flight never exceeds 8. The second scenario the report gives — "if *X* frees the credit early, it can overflow the answer reserve" — has the same hole: there is no count to free.

**Correction:** `:897`: "an answer (`RevokeStep`, `UnitAnswer`, `SendAnswer`) answers a request this node sent to that sender and has not yet resolved, even if the thread that made it has been destroyed"; and `:134`: "a wait for an answer of another node ends, and the answer, when it comes, frees what it names and wakes no thread".

## Finding 5 — "one bounded step, nothing kept on behalf of the sender" (`:878`)

**CONFIRMED IN PART.** Items 1, 2, 3, 4, 5 stand; item 3's severity is `blocks for ever` for the missing end and `unspecified` for the `ReportAsk` room.

- **Item 1, one cursor for all rebuilds.** `:888` ("a cursor in its node block"), `:906` ("the reports of a rebuild as a cursor in the node block") and `:1366` ("its cursor of reports for a rebuild") are one cursor per node, and a node holds several unit roles at once — `:1316`: "one **unit role** per IOMMU unit, per IOAPIC (x86-64), per GIC ITS and one for the GIC distributor" — so two take-overs in flight overwrite each other and one unit's rebuild clears a live node's context entry (`:1330` "clears every other entry no live node claims"). The report's `E1` exercises the successor's side and has the right shape; the conclusion stands. `wrong result`, and the loss can be DMA into unmapped memory.
- **Item 2, a `sealing` node.** `:888` asks "each live node"; `:1330` keeps without a report only "the entries whose root table lies in memory the ownership table gives to a **sealed** node or in its floor"; `:897` accepts a report only from "a **live** node". A node in `sealing` is none of the three (`:1301`: it keeps its threads, its memory and "finishes or refuses with `gone` the requests it serves"), so its context entries are cleared while its devices still have translations. `wrong result`. The report's `E2` hard-codes the clearing in its transition, so its check cannot distinguish the contract from a wrong implementation; the three sentences above are the argument, and they hold without a script.
- **Item 3, no end to the reports.** `:1330` says the successor "keeps the context entries that match … and clears every other entry no live node claims", and nothing says when the reports are complete: a node with no item sends no message (`:888` "as many `Report` messages as it has items"), so silence and delay are one thing. `blocks for ever` (the rebuild cannot end) or `wrong result` (it ends early and clears a live entry). And `:906`'s list of kernel messages that "wait in state that already exists until there is room beyond that reserve" omits `ReportAsk`, so a `ReportAsk` that finds no room has no defined fate.
- **Item 4, `Revoke` cannot be one bounded step.** `:882` has the receiver remove "at most 32 units … undoing mappings with its own cores' invalidations"; `:365` says "The invalidations of one call, or of one removal step, are grouped into one wait before the call returns", and `:347` says an invalidation of a unit "made on another node waits for it" — a `UnitRequest` and its answer, up to `IOMMU_WAIT_NS`. So the handler either waits (`:878`'s "one bounded step" and `:644`'s "a removal step never waits for another core (it returns `again`)") or answers `done` before the invalidations (`:882` would then free a frame that a device still writes). `:910`'s list of the two exceptions names the `UnitRequest`'s wait and not the `Revoke`'s. The report's `G1` and `G2` are the two horns, correctly.
- **Item 5, `IOMMU_WAIT_NS` inside the reserve.** `S11c`: 1 ms of waiting needs 7 periods of a reserve that has 156 µs of each 10 ms (`:1356`), so a message queued behind one slow unit request waits 70 ms, against `:902`'s "at most one period of the recovery reserve (10 ms) before it is served, an answer included". The three numbers cannot all stand.

**Corrections**, by item: a report bitmap indexed by unit and a per-unit pending flag, `sealing` and `starting` nodes included in `ReportAsk`, `:897` and `:1330`; a `ReportDone`, or a last flag on the final report; `Revoke` answering `RevokeStep(again)` while the invalidations are still in flight, with the wait recorded in the use entry (`:878`, `:882`); and `:902` saying that a unit request polls once per reserve slice instead of holding it.

## Finding 6 — the outgoing ring of a node that dies and starts fresh

**NOT A FAULT**, with one real gap beside it. `blocks for ever` belongs to that gap, not to the ring reset.

`:899` settles it: "both are 64-bit counts that never go back", and `:980`'s list for a fresh start resets the gate words, the page classes, the device leaf counts and the *use* table, empties nothing else about rings, and then "sets the consumer index of every ring **into** it to the ring's producer index". Nothing says a node zeroes its own producer, and nothing should: a fresh *Y*(2) continues the count it reads in the header, *X* keeps its consumer, and the entries *X* has not yet consumed carry *Y*(1)'s generation, which `:897` refuses ("the sender's member word is starting, live or sealing with that generation"). `S6a` puts the check side by side: the contract's rule holds, and the mutation that breaks it is `Y*(2)` zeroing the producer — a transition the report's `F1` puts in its *contract* mode. `F3` does the same. So `F1` fails on a rule the text does not contain, and its "if *Y*(2) zeroes prod = 0" is one of two things the text does not choose between, not a fault.

The gap beside it is in the first step of both `F1` and this finding: `:897` says a message that fails the check "is consumed", and never says how far the consumer advances. Its own list of what it checks includes "the kind and the length are ones it knows", so a length of 0 or 12 is a case it means to handle, and consuming by a length of 0 does not advance. `S6b` runs both readings: advancing by the length leaves the consumer stuck for ever (the check fires after three attempts), advancing by one entry holds. That is a new finding, below.

## Finding 7 — `role_hand`, the target dies after step 4

**CONFIRMED.** `blocks for ever`.

The sentences the report quotes say what it says. `:1317`: "for handing, the node that hands: it stays the holder the word names until the target writes held". `:1321`: a unit role changes holder without the holder only when "The holder is fenced or dead, and `SETTLE_NS` has passed … or the holder is unfenced and `FENCE_NS` + `SETTLE_NS` …". `:1338`: `role_hand` is "`busy` if the role is not held by the caller's node". `:1336`: `role_claim` is "`busy` if the role is held or handing and its holder or target is starting, live, sealing or sealed". The seal's condition is `:1154`: "No role word of a unit role names it, as holder or as target". And `:1243` requires "every unit role is held, **not handing**, by a node that is live or sealing, and that holder has `acked[X]` = *g*".

So with *X* live, *Y* fenced and settled, and the word `handing(X → Y, e2)`: a take-over is refused (the holder *X* is live), `role_claim` is `busy`, `role_hand` is `busy`, *X* cannot seal, and the reclaim barrier of a third node *Z* never shuts. `S7a` reaches a state with no transition at all, and the mutation that opens it is a row for a handing word. `:1329`'s own promise — "if *Y* dies after step 4, the successor of *Y* takes over with a rebuild" — is the sentence contradicted, and so is "no role word stays handing to a node that will not take it".

**A worse sibling, `S7b`:** the same death while *X* is **sealing**. `:1301` has a sealing node hand each unit role to its successor; the word becomes `handing(X → Y, e2)`; *Y* dies; `:1154` then refuses `sealed` because a unit role word names *X* as the holder of a handing word, and `:1148`–`:1161` has no transition from `sealing` back to `live`. So the sealing node is stuck with its cores running, cannot seal, cannot be resumed, and its unit role is wedged. Here the deadlock needs no third node.

**Correction:** as in the table, with a second sentence: "A node that has written `handing` maps the unit again only if the gate refused step 4; once step 4 is written, the handing node neither maps the unit nor serves it."

## Finding 8 — `sealed` before the park request, no `panic` check, and a two-node seal

**CONFIRMED**, all three, with the first narrower than stated. `breaks isolation` for the first two, `blocks for ever` for the third.

- **`sealed` before `park_request` (`:1301`, `:1151`, `:1154`).** `:1154`'s condition is "its other cores have parked", so the core that writes `sealed` is not among them, and `:1301` raises that core's park request *after* writing `sealed`. `:1151`'s condition is "Every core whose word names the node is confirmed parked by the seal's park request". The gate can compare two numbers, `parked` and `park_request`; at the instant `sealed` is written they are equal from the previous cycle, so the condition reads true while the last core of the old kernel still executes. The window is a few instructions, so this is real but narrow, and the fix is the order, not a new word: the last core raises its own park request in the same gate call that writes `sealed`.
- **No `panic == 0` (`:1154`, `:1151`, `:1181`).** A core that finds a failure writes `panic` non-zero and "sends an interrupt to a core of the next live node" (`:1181`); nothing in `:1154` or `:1151` reads it, and `:1189` says "a sealed node is never observed for stale evidence … only the evidence kill, retire and seal can accuse it" — so a sealed block with `panic` set can be resumed, and the evidence `self` can never be used against it.
- **Two nodes, one sealing (`:1155`, `:1148`–`:1161`, `:1299`).** If the only live node fails while the other is `sealing`, no node is live; `:1155` needs "any live node, with evidence"; there is no `sealing → live`; and the sealing node cannot even finish (`:1154` refuses while a unit role names it, and `:1329`'s step 4 needs a live target). The machine stops with a kernel still running.

**Corrections:** the three in the table; for the third, `sealing → live` made by the sealing node itself when no other node is starting, live or sealing, which also lets it accuse the failed node.

## Finding 9 — the x86-64 park stub and the NMI-blocking latch

**CONFIRMED.** `blocks for ever`; also `wrong result` for the second half.

The hardware sentence is right. Intel's SDM, Vol. 3A, "Handling Multiple NMIs": "While an NMI interrupt handler is executing, the processor blocks delivery of subsequent NMIs until the next execution of the IRET instruction. This blocking of NMIs prevents nested execution of the NMI handler" (quoted from the SDM's page 192 of Vol. 3A in the widely mirrored copy, [xem/minix86 manual](https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-192.html); the same sentence appears in §7.7.1 of the 2024 order the report cites, and as §6.7.1 in the editions before). LWN's "The x86 NMI iret problem" states the consequence in the same words ([lwn.net/Articles/484932](https://lwn.net/Articles/484932/)). So a handler that jumps into a halt loop instead of returning by `IRET` leaves NMIs blocked, and on the bootstrap core — which `:1200` stops "by the NMI of step 1 alone", with no `INIT` — nothing else clears the latch.

The two failures the report builds from it follow from the text as it stands: `:1199` has the handler "enter the park stub's loop with interrupts masked" without an `IRET`, and `:1202` has the stub, on waking, only "read its start request and, if one names a node, go to the entry stub; otherwise halt again", so a fence's park request is never written into `parked` and `FENCE_NS` (`:1351`) turns a sealed node into an `unfenced` one (`:1158`), which `:1208` says freezes all the memory it holds. The second half is also a contradiction inside the text: `:1199`'s handler *does* write `parked` when it sees `fencing`, while `:1202`'s stub does not, and the two describe the same wake.

**Correction:** as in the table, and add to `:1202`: "the stub writes `parked` at every wake, before it reads the start request."

## Finding 10 — the ARM64 SDEI lifecycle

**CONFIRMED IN PART.** `blocks for ever`. I verified two of its four claims at their sources and could not verify two.

- **Claim 1, the missing `SDEI_EVENT_ENABLE`: verified.** Trusted Firmware-A's own description of a client's initialisation: "The client then registers a handler for that event, enables the event, and unmasks all events on the current PE" ([TF-A docs, components/sdei.rst, v2.12.0](https://github.com/ARM-software/arm-trusted-firmware/blob/master/docs/components/sdei.rst)). The contract's list at `:1205` ("every core having registered the kernel's handler and unmasked itself when it entered its node") and [kernel.md:149](../architecture/kernel.md#L149) name registration and unmasking and not the enable. So the signal may be refused on a core that is registered and unmasked.
- **Claim 4, `CPU_OFF` inside an uncompleted event: verified in substance, the citation is imprecise.** The sentence the report quotes — "a CPU_OFF from that not-yet-completed context wedges EL3 on some firmware" — is from the cover letter and review of the arm64 cross-CPU NMI series by Kiryl Shutsemau, which is where `arm64_nmi_cpu_stop()` is introduced ([v3 cover](https://ratatoskr.run/linux-arm-kernel/2026/06/17131380/t), [v4 cover](https://ratatoskr.run/lkml/2026/06/17148508/t)); the merged comment in `arch/arm64/kernel/smp.c` says the bookkeeping lives in one place and does not carry that sentence. So the claim stands and the line reference `smp.c:840-844` does not.
- **Claims 2 and 3 (CPU_ON wiping private event state, CPU_SUSPEND power-down masking the PE): not verified here.** I did not read `services/std_svc/sdei/sdei_state.c` or `sdei_intr_mgmt.c` in this session, so I do not endorse or reject them; the finding stands on claims 1 and 4.

**Correction:** as in the table. It needs one decision of the owners too: whether the kernel calls `SDEI_EVENT_ENABLE` on every `CPU_ON` (the safe reading) or the boot image makes a `CPU_ON` unnecessary for fence-class-1 cores.

## Finding 11 — `STALE_NS` and the deadlines

**CONFIRMED**, both halves. `wrong result`, and it fences healthy nodes. `STALE_NS` is 100 ms (`:1348`).

- **The `u64` wrap. CONFIRMED.** `:1171`: "`idle_until`, the instant of its next armed timer when it goes idle (the largest value if none)"; `:1182`: "now > `idle_until` + `STALE_NS`". With `idle_until = 2^64 − 1` and `STALE_NS = 10^8`, `u64` addition gives 99 999 999, so the guard is satisfied by every instant after 100 ms of uptime. `S11a` computes both readings: the contract's arithmetic convicts two of the three cores of a healthy idle node — the two the sweep's single interrupt does not wake (`:1189`: "a successor that is idle with no armed timer is sent an interrupt and a ping message", one interrupt, one core) — while the other two cores still read the observed heartbeat. The mutation that clears it is saturating arithmetic. The report's "every idle core … is immediately accused" overstates it only in that an observation must exist; `:1189`'s sweep takes one every `SWEEP_NS` and records the core's heartbeat, so it does.
- **A frozen heartbeat on a running core. CONFIRMED, and worse.** `:1171`: "`heartbeat`, a counter written at the exit of every kernel event of the core". `:564`: "the hardware timer is set to the earliest of: the instant the running context's budget ends (now + *r*, when it runs from the ready queue), the first replenishment instant of the four throttled queues, and the first firing instant of the timer queue. With nothing armed, it is not set." `:483` allows a period of 2^36 ns = 68.7 s, and `:557` lets a throttled context run on slack. So a core that runs one compute-bound thread makes no kernel event for up to 68.7 s while it is not idle, its heartbeat does not move, and `:651` — "or its heartbeat goes stale while it is not idle, the node accuses itself" — kills the node; the sweep of `:1189` does not help, because it wakes only a successor that *is* idle. `S11b` shows both sides with the mutation "a heartbeat event armed at `now + STALE_NS/2`". 68.7 s is 687 × `STALE_NS`, so no value of `STALE_NS` inside `:1348`'s 10 ms to 1 s range can close this: the period bound and the heartbeat rule contradict each other.

**Correction:** `:1182`: "and, when a timer is armed, now > `idle_until` + `STALE_NS`, the addition raised no higher than the largest value; when none is armed, this clause does not hold" — plus a rule in `:564` and `:1171` that a core that is not idle arms a heartbeat event no later than `now + STALE_NS / 2`, and that this event is what `:651` reads.

## Finding 12 — D-128 points 4, 5 and 10

**CONFIRMED IN PART.** Items 1 to 3 stand; items 4 and 5 do not.

- **Item 1, the direct contradiction. CONFIRMED** and the sharpest thing in the report. `:939`: "A wait that must end if the peer dies binds `node_watch` for the peer's node to the same notify with another badge bit". `:1281`: "`node_watch` | node, index, notify | | `read` on the node, which must name the caller's **own** node". `:1308`: "the core (slot, kind, `read`, then that it names the caller's node, `invalid`)". A library that does what `:939` says gets `invalid`. `blocks for ever`, since the wait it was meant to end never ends.
- **Item 2, four slots. CONFIRMED** *given* item 1: `:1357` "`NODE_WATCH_SLOTS` | 4 | The node agent and up to three supervisor replicas", and `:1308` is "`busy` if the notify is not 0 and the index is bound". Every waiting client cannot have a slot. This needs a decision of the owners, because the two readings differ: one watch per client on the peer's node (then 4 is far too few and `:1281` must change) or one watch per node on the caller's own view (then 4 is enough and the agent multiplexes, and `:939` must say so).
- **Item 3, the missed edge. CONFIRMED as `unspecified`.** `:1308`: "the notify is signalled … **at least once after each change** of a member word or a role word that the node processes". A death that happens before the bind is not a change after it, so a client that binds and waits after the death waits for ever. Nothing tells it to read the words first. `blocks for ever`.
- **Item 4, `SENDS_PER_PEER` node-wide. NOT A FAULT.** `:907` states the bound: "a node has at most `SENDS_PER_PEER` (8) sends in flight to each peer". A stated limit is not a contradiction, and `:903` counts it from the ring indices, so the report's starvation by "threads destroyed in flight" does not arise either. Whether the supervisor deserves a reserved slot is a decision of the owners, not a fault of the text.
- **Item 5, a dead mailbox looks like a busy one. NOT A FAULT.** `:2097` says it already: "a node whose agent has died is unreachable from other nodes until a supervisor restarts it". The report's finding is that same sentence read as a defect; it is a stated price, and D-128 is where the owners accepted it.

---

## The reviewer's two scripts: can each check fail?

Both scripts exist and run. `/tmp/review8_hydrogen/explore_cross_node_rings.py` (550 lines) and `/tmp/review8_hydrogen/explore_cores_failure_sealing.py` (429 lines) share a breadth-first search (`bfs`, lines 10–35 of the first) whose mode string selects the rule set, and each check is `bfs(init, trans, inv)` with `inv` firing on a marked state. Three things follow, and they are the reason I rebuilt the scenarios rather than trust its output.

1. **Most checks can fail, and I ran them.** `A1`, `B1`, `B4`, `C1`, `E1`, `H1`, `I1`, `I2`, `J1`, `K1`, `L1`, `L2`, `M1`, `M2` are real: each `inv` fires on a state the transition function can reach, and each has a `fixed` mode in which it does not. `A1`, `B1`, `C1`, `L1`, `M1` and `M2` agree with my own runs.
2. **Four checks fail on a rule the text does not contain, so they prove nothing about the text.** `F1` puts in its *contract* mode both "Y(2) keeps the old header" and "Y(2) zeroes prod = 0" (lines 419–423); `:899` settles the first. It also puts two gate violations by the dying node in every mode, including *contract* (lines 414–417: a length of 0, and `prod` jumped to 500 "without gate"), so its *contract* mode contains senders the text forbids. `G1` and `G2` put in their *contract* modes two implementations of the `Revoke` handler — answer `done` before the invalidations, or block inside the step — and `inv` convicts both; but the text forbids both (`:882`, `:365`), so the check convicts a hypothesis, not the contract. `D2` frees the send credit early, which `:903` does not allow. `E2` hard-codes `('corrupted_dma', …)` as a transition.
3. **The invariants are reachability of a marked state, so a missing transition makes a run "HOLDS" vacuously, and no check asks whether a legal step exists.** The clearest case is the report's own `A2`, printed as "HOLDS (20 states)": in its `fixed` mode a requester answered "elsewhere" while the word reads `handing` re-sends to *X* again (line 113: "R gets elsewhere, re-reads handing(X->Y,e2) -> X"), so the requester never finishes, and the invariant — "not stuck_dropped" — cannot see it. My `S1b` is that gap: with the report's fix alone the requester circulates for ever. Two smaller things: `bfs` stops expanding at `max_states` with `continue` rather than reporting truncation (line 27), so a "HOLDS" could in principle be a budget cut (not in these runs: 2 to 20 states); and no scenario models liveness, which is what findings 7 and 8(c) are about, so those two conclusions rest on the prose alone.

---

## New findings

### N1. The requester answered "elsewhere" is sent back to the node that refused it (`:1328`, `:1317`)

`blocks for ever`. `:1328`: "the requester reads the role word again and sends it to the holder it names". `:1317`: a handing word "stays the holder the word names until the target writes held". So during a planned hand-over the rule sends the requester to the handing node, which has stopped serving the unit (`:1329` step 1) and answers "elsewhere" again. My check `S1b` runs the report's own fix and still finds the requester circulating: four "elsewhere" answers and no progress. The report's correction for finding 1 is therefore incomplete, and `:1328` needs the target named for a handing word. A second, smaller half: nothing says what answer a requester gets when its epoch **matches** a handing word — `:897` passes such a message and `:1329` step 1 denies the service (`S1c`).

**Correction:** the one in finding 1, second half.

### N2. A request kept at R0 and sent to the next holder names the dead holder's epoch (`:1215`, `:909`, `:897`)

`blocks for ever`. `:1215`: R0 "keeps the unit requests aimed at a role *X* holds, to send them again once the role word names a live holder"; `:909`: "except a unit request to a role *Y* held, which it keeps and sends again to the next holder". The request carries the epoch its thread read (`:1328`: "Requests to a holder carry the epoch the requester read"), which is the dead holder's epoch, and the new holder's epoch is at least two greater (`:1329` steps 4 and 5: "e + 1", "e + 2"). So `:897`'s epoch rule consumes the kept request, and the mechanism for surviving a holder's death is the mechanism that drops the request. `S1d` traces it. This is the sibling of finding 1 that needs no race.

**Correction:** the same exemption as finding 1 — a `UnitRequest` whose epoch is not the role's is answered "elsewhere", never dropped — and one clause in `:1215`: "kept and sent again with the epoch the word then names".

### N3. "Consumed" does not say by how many entries (`:897`, `:899`, `:1183`)

`blocks for ever`. `:897` checks "the kind and the length are ones it knows" and then says a message that fails "changes nothing, is consumed, and is traced (code 11)". `:899`: "A message takes 1 to 11 consecutive entries". So for a message whose length is 0, or 12, or longer than what the producer wrote, the number of entries the consumer must step over is undefined, and stepping by the length of 0 does not move. `S6b` runs both readings: the ring stays blocked for ever under one, and clears under the other. The consequence is not confined to the faulty sender: `:1183`'s stuck evidence then convicts the **receiver** ("the consumer index still reads *c* with now − t ≥ `STUCK_NS`"), so a single bad length in one ring kills a healthy node. The report reaches this only as a fix suggestion inside finding 6.

**Correction:** in `:897`, "A message that fails any of these, and any message whose length is not one the receiver knows, is consumed by one entry and traced (code 11 …)".

### N4. `ReportAsk` has nowhere to wait (`:906`, `:888`)

`unspecified`. `:888` has the new holder of a unit role "ask every live node for its report on the unit", and `:906` lists the kernel messages that wait in existing state for room: "a `Release` as *release pending* in the use entry; the reports of a rebuild as a cursor in the node block; a `Handed` as the handing role word (at most one per role); a `Ping` as the sweep's observation (one per pair)". `ReportAsk` is not among the four, and there is no fifth line. A `ReportAsk` that finds no room beyond the answer reserve has no state to wait in and no rule to be dropped by, so a rebuild of a unit can silently skip a node and then clear that node's live context entries (`:1330`). `wrong result` if it is dropped, `blocks for ever` if it is queued with no place.

**Correction:** add to `:906`: "a `ReportAsk` as a pending flag per unit and per live node in the node block, cleared when that node's last `Report` arrives", which is also what N4 needs in order to know when the reports are complete.

### N5. A `Release` that frees an entry in state *revoking* leaves `X`'s in-flight request counted (`:903`, `:872`)

`wrong result` (a small one, and the fix for finding 3 should cover it). `:904` counts a node's requests in flight "from its producer index and the receiver's consumer index", so the request count of the skipped `Revoke` comes back when *Y* consumes it — good — but the thread that waited for `RevokeStep` must be woken by the `Release` (finding 3), and `:872` has to say whether the removal step then returns `again` or success. As written, `:870`'s "the removal step on *X* returns `again` after each answer until *Y* reports the root removed, and then frees the entry" describes a sequence the crossing never produces.

**Correction:** the sentence in finding 3, with "and the removal step returns success, as if `Y` had reported the root removed".

---

## What I could not verify

- Finding 10's claims 2 and 3 (the `CPU_ON` reset of private event state, and the power-down mask on `CPU_SUSPEND` wakeup): I did not read TF-A's `sdei_main.c`/`sdei_state.c` at v2.12.0 in this session. Marked as not verified above, not as false.
- Finding 10's citation of `arch/arm64/kernel/smp.c:840-844`: the sentence quoted is from the NMI-series cover letter, not from the merged file, as far as I could see. The claim is right; the line reference is not.
- Finding 8(c)'s timing question — how long a node stays in `sealing` — is not given anywhere in the contract, so I could not bound the window; the state machine has no exit at all, which is enough for the verdict.
- Nothing in this file was run against a machine: every check is a state machine over the contract's sentences, and the hardware claims are the reports of the sources cited.
