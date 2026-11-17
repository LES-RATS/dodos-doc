# Verification of `2026-11-17-contract-review-13-gemini-hydrogen.md`

**Verifier:** Mistral (review sub-agent), 2026-11-17.
**Target:** branch `main`, head `6eb2f4b`, read through `Docs/architecture/kernel-interface.md` (2303 lines), `Docs/architecture/kernel.md`, and decisions D-128..D-139 in `Docs/architecture/decisions/README.md` (lines 138-148).
**Method:** every quote in the report was re-read at its cited file:line. All quotes are exact, with one exception noted under Finding 1 (the report's parenthetical about `poll` misstates its result; the quoted contract text itself is exact). Each scenario was replayed as a numbered trace of single reads and writes. A finding stands only if some observer sees a result that no order of the two calls could give, or memory that is no longer a notify is written. Corrections are judged against the owners' principle: a guarantee is paid at a failure or a rare event, never per memory access; a lock on every `signal` is against it unless nothing cheaper holds.

---

## Finding 1 — lock-free `signal` racing slot deletion/move and `notify_bind` (report: CRITICAL)

**Quotes.** Exact: `kernel-interface.md:12` ("**Any call can fail with `gone`.**"), `:231`, `:668`, `:669`. The report's parenthetical "poll(N) (which returns 0 and clears N.word)" is inaccurate: `poll` returns `would_wait` on a zero word and clears nothing. The trace below uses the correct result.

**Trace, scenario 1 (no waiter).** Core 0: (1) lock-free lookup of slot S reads notify N with badge B; (2) core 1, under the node lock, completes `cap_delete(S)` and runs `poll(N)` (word is 0, returns `would_wait`); (3) core 0 atomically ORs B into N.word; (4) core 0 reads "whether a thread waits on the notify or on the endpoint bound to it", finds none, and "returns without the lock if none does" (:669).
**Verdict: refuted.** The observable results (poll returned `would_wait`, `signal(S)` returned ok, N.word holds B, S dead) are exactly those of the sequential order poll → signal → `cap_delete`, in which `signal` legitimately completed before the revoke. The OR is one atomic write to a notify that still exists (another slot holds it), so no observer sees a result no order could give, and no memory that is not a notify is written. Rule 2 says a call *can* fail with `gone` — not that it must — and :669 explicitly lets the lock-free `signal` return without ever taking the lock. The D-138 barrier paragraph covers the only memory-safety case (object destruction before reuse): "A `signal` whose OR reached a notify that an event of another core destroyed after the lookup has signalled it before its destruction: the bits are lost with the notify, and the call succeeds" (:669).

**Trace, scenario 2 (waiter present).** (1) Core 0 looks up S lock-free, reads N, badge B; (2) core 0 ORs B into N.word before taking the lock; (3) core 1, under the lock, deletes S; (4) core 0 takes the lock, re-reads S's segment sequence word, finds it changed, re-looks up S under the lock, finds it dead, returns `gone` — with B already in N.word.
**Verdict: refuted as a violation.** The memory written is a live notify, not "memory that is no longer a notify". The bits B are exactly the badge bits that any capability with the same badge would signal — `cap_derive` keeps the badge ("asking for the same one is accepted"), so another slot S′ holding N with badge B can legally OR the same bits at any moment. No observer of N sees anything that a legal concurrent signal through S′ could not give; the caller's `gone` is permitted by rule 2. The contract's own :669 specifies that the OR precedes the lock and is not undone; the re-check under the lock gates only the wake ("no call acts on a capability that an event of another core removed between its read and its lock", :668), and here it correctly declines to wake.

**Trace, scenario 3 (`notify_bind`).** (1) Receiver R is already waiting to receive on endpoint ep. (2) Thread A takes the node lock and calls `notify_bind(N, ep)`. (3) A stores the binding N.bound = ep. (4) Thread B, on another core, looks up slot S holding N lock-free and atomically ORs B into N.word (a locked OR, so B's later loads cannot be reordered before it). (5) B reads N.bound and ep's queue, reads bound = 0 (A's store at (3) not yet globally visible), finds no waiter, and returns ok without the lock. (6) A loads N.word, reads 0 (B's OR at (4) not yet visible to A — on x86-TSO a load may be satisfied while the core's own earlier store to a different address is still in its store buffer), so per :231 no notification is "delivered at once". Result: R waits forever although N.word holds B — a lost wake-up at bind time.
**Verdict: confirmed in part.** :669 claims "The removal of the lost wake-up ... rests on two orders, the waiter's ... and the signal's ... each a store before a load", but in this interleaving the relevant pair is `notify_bind`'s (store binding, then load word), and no sentence gives that pair a store-load order. On x86-TSO and on ARM64 both sides can read 0 as traced. This is a liveness gap (a lost wake-up at a bind), not a memory-safety hole.

**Severity: medium**, not CRITICAL — scenarios 1 and 2 are refuted; only the `notify_bind` ordering gap stands, and it costs a wake-up, not memory.

**Correction judgment.** The report's first suggestion — taking the node lock in `signal` before mutating N.word — is rejected: it puts a lock on every `signal`, against the owners' principle, and destroys the lock-free path D-138 deliberately keeps and the trial measured ("under one node lock, held for one kernel event, with a lock-free slot read and a lock-free signal"). Nothing cheaper does not hold here, but the lock is not needed: scenarios 1-2 are already benign. The report's second suggestion is right and cheap (paid at a bind, a rare event). Exact text, to append to the last sentence of :669:

> In `notify_bind` the write of the binding is ordered before the read of the word (a store-load barrier between the two), so a `signal` whose OR lands while the bind runs either is seen by the bind's read of the word or finds the binding and wakes the receiver at once: the bind is the third order of the same rule.

---

## Finding 2 — failed IOMMU unit vs reclaim barrier; R6 and retired handles (report: CRITICAL)

**Quotes.** Exact: `:398`, `:400`, `:768` ("R6 leaves the tables of its cores with no entry claimed before the cores are free"), `:793`, `:1326`, `:1339`, `:1353`, `:1375`, `:1485`.

**Part 1 (machine-wide deadlock of every later dead node).** **Verdict: refuted.** The withholding of `acked` is scoped to device-bearing nodes by the sentences the report itself quotes: :398 "the reclaim barrier of a node that had a device behind the unit never holds, since the holder cannot confirm that it blocked that device and does not write `acked` for the node"; :1375 "a holder whose unit failed never writes `acked[X]` if a device of *X* sat behind that unit"; :400 "the memory a device behind it may still reach is kept out of use and nothing else stops". :1485's own rationale is context-entry-based — "so the reclaim barrier of Z never holds while a context entry of the unit still names Z" — and :1353's barrier condition is "no context entry of any IOMMU unit names X's generation". A node with no device behind the failed unit has no context entry there, so nothing stops it. The only residue is that :1326's "stays undone on a unit that has failed" read alone with :1485 invites the misreading; one scoping clause removes it (below, low).

**Part 2 (R6 erases retired handles).** **Verdict: confirmed.** Trace: (1) unit U times out and fails; its holder answers `failed` to the in-flight IEC invalidation of irq (P, v), so per :793 "the vector stays claimed on its core with no irq, `irq_claim` of it is `busy`, and no other source can be given the handle that the failed unit may still hold in its cache". (2) Later node X dies; X had no device behind U, so per :398/:1375 the barrier holds (:1353) and R6 runs. (3) :768 says R6 "leaves the tables of its cores with no entry claimed before the cores are free", and the line-word paragraph of the same section says "step R6 clears the words that a generation that is over took, as it clears the interrupt tables of its cores" — so R6 clears P's table entry for v, destroying the "stays claimed" marker. (4) :1339's R6 walk list ("every line word taken by X's generation ... the attach word ... every core word that names X's generation") and its Bound sentence ("the line words, the identifier words of each segment and the core words") omit the interrupt tables entirely, so the walk as specified never touches them — an internal inconsistency with :768. (5) Core P's word becomes free, a new node starts on P, and the entry stub clears the table again anyway (:1411, :2024: "Each core passes the entry stub, ... clears its interrupt table"). (6) The new node's `irq_claim(P, v)` now succeeds and reuses the handle that the failed unit may still hold in its IEC cache — the exact reuse :793 forbids. Impact is misdelivered interrupts (the stale entry delivers the old source to vector v on P), not memory writes.

**Severity: high** for Part 2 (not CRITICAL; Part 1 refuted; impact is interrupt misdelivery after a hardware failure plus core reuse, not DMA). The :1339/:768 list inconsistency is a low documentation defect on its own.

**Correction judgment.** The report's retired-vector bitmap is right in kind and is paid at a failure, consistent with the principle. Two completions: the bitmap must live outside the interrupt table (the entry stub at the next `node_start` also clears the table, so table entries cannot carry the retirement across a core reuse), and :1339's walk and Bound must list the tables. Exact texts:

- In :793, after "`irq_claim` of it is `busy`", insert:

> The retirement is recorded outside the table: a retired-vector bitmap of 192 bits per physical core in the living part of the machine table, set at the `*failed*` answer and by R1 for every interrupt entry of the core it clears on a failed unit, read by `irq_claim` (`busy` while a bit is set), left untouched by the entry stub and by R6, and cleared only at machine start-up.

- In :1339's walk list, replace "every line word taken by X's generation, which becomes free, unclaimed (D-135);" with:

> every line word taken by X's generation, which becomes free, unclaimed (D-135), and every entry of the interrupt table of each of X's cores, which becomes free, except an entry whose vector the retired-vector bitmap marks, which stays claimed with no irq (D-139);

- In :1339's Bound sentence, after "the line words, the identifier words of each segment and the core words" add "and the `IRQ_TABLE_ENTRIES` entries of each of X's cores".

- In :1326, replace "and stays undone on a unit that has failed" with:

> and on a unit that has failed it is done for every node but a node that had a device behind that unit, for which it stays undone ([IOMMU](#iommu))

---

## Finding 3 — faulty requester, operation 2 detach, flips another node's attach word (report: HIGH)

**Quotes.** Exact: `:342`, `:1035`, `:1036`, `:1040`, `:1475`.

**Trace.** (1) V attaches dev through unit U1: identifier word `taken(V, g_V)`, attach word `*attached*(root_V)`, context entry on U1 names V's domain. (2) A faulty requester R sends `UnitRequest` operation 2 (detach, dev, domain_in_R) to H, the holder of a different unit U0 — "any node → holder of a unit role" (kind 4), no ownership check on the request. (3) H's gate applies the :1036 check: the context entry of dev on U0 is empty, so "or none is left: a detach is idempotent" passes. Unlike operation 1 (:1035: "the identifier word names the requester with its generation"), operation 2 never checks `IdentifierWord(device)`. (4) H clears nothing on U0, invalidates U0, then "the holder's gate writes the attach word *detached* if it reads *attached*" — the attach word is one word per device identifier, shared across units, so H flips V's live word to `*detached*(root_V)`. (5) V's `iospace_attach` now returns `busy` (:367, col *detached*), and at the next rebuild of U1 the `*detached*` row applies — "no context entry is written; the kept detach is served once the rebuild ends and answered done" (:1475) — clearing V's live context entry; V's DMA is halted. :1040's "a faulty one gains nothing by it" is false for operation 2.
**Verdict: confirmed.** No sentence prevents it: the operand check is the only gate, and it passes on an empty entry without an identifier-word check.

**Severity: high** (as reported) — a faulty node can halt another node's device traffic and clear its live context entries at a rebuild. There is a second, worse variant the report's correction does not close: the *owner* sending the detach to the wrong unit's holder also passes the empty-entry check and flips its own word to `*detached*` before the real unit blocked the device; the requester's gate then writes 0 and frees the identifier while the real context entry still translates, so the device can DMA into memory the owner subsequently frees — a containment hole, not just availability.

**Correction judgment.** Adding the identifier-word check to operation 2 is necessary and closes the reported cross-node scenario, but it is not sufficient for the wrong-unit-by-owner variant. Exact text for :1036, replacing "the context entry names that domain number in the requester's range (or none is left: a detach is idempotent);" with:

> the identifier word names the requester with its generation, and the context entry names that domain number in the requester's range, or none is left and the attach word already reads *detached* (a detach is idempotent);

Cost: one identifier-word read per detach — paid at a detach, a rare event, consistent with the principle.

---

## Finding 4 — out-of-header `*attached*` contradictions; infinite `again` on refused detach (report: HIGH)

**Quotes.** Exact: `:369-373`, `:384`, `:391`.

**Part 1.** **Verdict: mostly refuted.** An out-of-header `*attached*` (after an attach or detach answered `*failed*`, :369/:372) is the deliberate paid state: "the device stays out of the header" / "the device leaves the header", and the root keeps its class until the machine restarts. The header-driven rows (:370 "the entry is marked *detaching*", :373 "the step asks the detach, as above") simply do not apply to a device that is not in the header — the destruction iterates its header (:391 "first detaches each of its devices"), so no action is owed. The one genuine gap is :384: "the device is already attached to this iospace ... its attach word *attached* with this iospace's root, and its entry in the header not *detaching* (success, nothing changes)" does not require the entry to be present, so re-attaching an out-of-header device "succeeds with nothing changed" and leaves it unreported (its context entry is then cleared at the next rebuild, :1475: "otherwise no report claims it, and it is cleared with the word left *attached*") — an availability wrinkle, not a contradiction.

**Part 2.** **Verdict: confirmed as a loop, but only against a faulty holder.** :371 (detach answered done, col *attached*): "the holder refused the request (it traces it): the *detaching* mark is cleared, the device stays in the header, `busy`"; the next destruction step asks again (:370/:373), and so on forever, if the holder keeps answering done without writing `*detached*`. But that requires a holder that lies about its answer, and the contract already bounds that: "a kernel that lies about marks is faulty, which the gate does not contain (it damages the marks of what it sends and availability, never another node's memory)". The hardware case — the one D-139 actually fixed — is the `*failed*` answer, and :372/:391 already let "the destruction go on". No memory is written and no other node is damaged; the cost is availability of the caller's own removal.

**Severity: low**, not HIGH.

**Correction judgment.** The :384 clause is worth adding (free). Treating a refused done at destruction like :372 is a cheap hardening and safe — the device would leave the header with the word left `*attached*`, n > 0, exactly the :369/:372 paid state. Exact texts:

- :384, change "and its entry in the header not *detaching* (success, nothing changes)" to "and its entry in the header present and not *detaching* (success, nothing changes)".
- Optionally, :371 col *attached*, after "the device stays in the header, `busy`", add: "at a step of a destruction the device leaves the header as at a detach answered *failed* (:372), and the destruction goes on".

---

## Finding 5 — incomplete D-138/D-139 cleanup (report: HIGH)

**Quotes.** Exact: `:17`, `:2112`, `:148`, `:1769`, `:1787`, `:1788`, `:1912-1917`; cross-file: `kernel.md` multi-core section and `scheduling.md:9` ("a node of several cores shares its objects under one node lock (D-128, D-129, D-138, ...)").

**Verdict: confirmed on all four sub-claims, but severity low** — these are stale or incomplete words in summary and abi/ change lists; no behavioral hole follows from any of them.

1. :17 "Inside a node the cores share the node's state, under locks" and :2112 "The node's cores share its objects, under locks" are stale against :666 and `kernel.md`/`scheduling.md:9` ("under one node lock, held for one kernel event, with a lock-free slot read and a lock-free signal").
2. :148's summary of zero-side-effect `again` names only the bounded step, the no-context fault, the request of its core and the watermark barrier; it omits the full unit request table (:1043 "A call that finds no free entry returns `again` with nothing changed"), credit exhaustion (:915 "returns `again` with no message and no wait"), and *leaving its core* (:692). The general rule exists at :1894 ("a request, a credit or an entry in use, or a barrier started"), so this is a summary incompleteness, not a missing guarantee.
3. :1787 still says "the head of the chain of the tables a change unhooked", contradicting D-139 (:267 "the chain is kept outside the tables", :329 "at most 2 × (L − 1)", :1043 "at most 2 × (L_io − 1)"); there is no "Since D-139" bullet after :1788; the Calls table has no `IoSpaceAttach` row (rows jump 32, 33 → 38) and rows 32, 33 and 46 lack the unit-request-table `Again` of :1043.
4. :1788's reserved list omits the per-object lock words, the 16-byte directory entry, the eight range-lock words and the per-core lock word that :671 keeps reserved; :1913-1916 describe those lock words as active without "reserved" (contrast :1912, :1917).

**Correction judgment.** All corrections are zero-cost text edits, paid never. Exact texts:

- :17 and :2112: "under locks" → "under one node lock (D-138)".
- :148: append to the `again` sentence: "the Errors table below gives the general rule (a request, a credit or an entry in use, or a barrier started)".
- :1787: replace "the head of the chain of the tables a change unhooked" with "the addresses of the tables a change unhooked, kept outside the tables (D-139)".
- After the "Since D-138" bullet (:1788), add a bullet: "**Since D-139.** The chain of unhooked tables is kept outside the tables (in the invalidation request and in the unit request table entry, at most 2 × (L − 1) and 2 × (L_io − 1) words); an interrupt entry whose invalidation a failed unit answered `*failed*` is recorded in the retired-vector bitmap and stays claimed until the machine restarts, and `irq_claim` of it is `busy`."
- Calls table: add a row after 32, 33 — "| 34 | `IoSpaceAttach` | waits for a unit request (waiting for a unit); `Again` if the unit's request table is full; `Busy` if the unit is found failed (D-131) |" — and append "`Again` if the unit's request table is full" to rows 32, 33 and 46.
- :1788: extend "stay in the layout, reserved and written as 0" with "and so do the lock word inside every object (endpoint, notify, reply and timer of 64 bytes, sched and task of 256 bytes, thread, aspace and iospace header), the 16-byte directory entry of a cspace, its eight range-lock words and the lock word of each core ([Object sizes](#object-sizes), D-138)".
- :1913-1916: mark each lock word "reserved since D-138" (e.g. :1913 "a lock word (D-129), reserved since D-138").

---

## Finding 6 — CORE_ANSWER_NS bound vs `now` at entry; kernel vector priority (report: MEDIUM)

**Quotes.** Exact: `:497`, `:329`, `:331`, `:687-688`, `:1510`, `:799`.

**Scenario 1.** **Verdict: confirmed as a real ambiguity with a real consequence.** Trace: (1) core A enters the call and reads `now` at entry (:497 "the clock read at its entry"); (2) A waits for the node lock up to (N−1)×H before it can write the request; (3) A takes the lock, writes the request carrying "the instant it was started", sends the IPIs, and "arms a due event of its timer queue at that instant" (:331); (4) the asked core answers at most E after the request started, then D, then at most E again (:687-688), so the wait is at most 2×E+D *measured from the request's start*; (5) start-up only refuses a CORE_ANSWER_NS "not above ... 2 × E + D" (:688). If "the instant it was started" is the entry `now` of step (1), the true bound is 2×E + (N−1)×H + D — the requester's own lock wait is uncounted, because E = N×H counts the *asked* core's event, not the requester's wait before the request exists — and a healthy node could accuse itself falsely when the due event fires. No sentence says where the start instant is read.

**Scenario 2.** **Verdict: refuted.** Nothing in the contract promises an order inside vectors 240-255 ("The priority class of a vector is its high four bits" is stated only for the claimable range), and the 2×E+D bound already includes the interrupt's event whatever the dispatch order — "its wait for the lock and its work included" — so no observer sees anything impossible. The proposed vector ordering is optional polish, not a fix.

**Severity: medium** for scenario 1 (a false self-accusation fences a healthy node — liveness; the start-up check exists precisely to prevent it and would under-refuse), none for scenario 2.

**Correction judgment.** Raising the bound would charge every request; reading the clock once more under the lock is paid at a request, a rare event, and keeps 2×E+D exact. Exact text for :329, where the request's fields are listed — change "the instant it was started" to:

> the instant it was started, read from the clock after the node lock is taken, when the request is written and the asked cores' interrupts are sent (not the `now` of the call's entry)

---

## Finding 7 — G9 target-core check on ARM64/RISC-V; :1044 vs :349 (report: MEDIUM)

**Quotes.** Exact: `:1039`, `:1082`, `:349`, `:1044`.

**Scenario 1.** **Verdict: confirmed.** On x86-64, operation 5 requires "the handle, or the APIC ID, names a core whose word names the requester" (:1039). G9 (:1082) for the ARM64 SPI route / RISC-V APLIC target checks only "the node the line's word names with its generation" — the target core is unchecked, so a faulty requester holding a line word can route its line onto another live node's physical core. The target's kernel takes the interrupt at that vector: ignored if unclaimed, or delivered to the other node's claimed irq — cross-node interrupt injection. SPIs cannot reach kernel vectors (they are ≥ 32, and the claimable range is device vectors), and an interrupt is not a memory write, so the impact is availability and driver confusion, not containment.
**Severity: low** (the report's medium is high for an availability-only injection).

**Scenario 2.** **Verdict: refuted.** The sentence that already prevents it is :267 — "An unhooked table joins the free list only at the completion of the invalidation that covers its unhooking ... for an iospace at the unit's confirmation" — together with :349 ("the unhooked tables never join the free list, keeping their class"). On a `*failed*` answer there is no confirmation, so the tables never join the free list; :1044's "empties the record with its counts kept" is about the request record, not the tables. Adding the clause to :1044 is harmless clarity only.

**Correction judgment.** The scenario-1 correction is right and cheap (one core-word read at a route write, a rare event). Exact text, appended to :1082:

> and the route's target (the affinity written to GICD_IROUTER on ARM64, the APLIC target on RISC-V) names a core whose word names the requester with its generation, as the handle or the APIC ID must on x86-64

---

## Finding 8 — watermark barrier "in flight" check; `idle_until` wording (report: LOW)

**Quotes.** Exact: `:676`, `:881`, `:1744`, `:650`, `:1281`.

**Scenario 1.** **Verdict: confirmed, low.** :676 checks only "the request of its core" in use, while :881 says "the call starting it if none covers it" and :1744 "the call starts the barrier if none is in flight". Each core has one request, so a second core whose own request is free starts a duplicate barrier IPI wave instead of returning `again` on the in-flight one. Safe (both barriers ask every core and only raise the barrier epoch), but it contradicts :1744's wording and wakes idle cores twice.

**Scenario 2.** **Verdict: confirmed, low.** :1281 writes `idle_until` as "the instant of its next armed timer when it goes idle (the largest value if none)", while :650 arms the hardware timer at "the earliest replenishment instant or firing instant". Read literally ("timer" = a `timer` object), an idle core with only a replenishment or the sweep armed writes the largest value, so the stale test "now − STALE_NS > that core's `idle_until`" never fires for it. The sweep paragraph itself relies on the wider reading — "the first core of a live or sealing node is never idle with nothing armed: its `idle_until` is at most `SWEEP_NS` ahead" — so with the literal reading a hung first core is invisible to the other nodes' sweeps.

**Correction judgment.** Both corrections are cheap and correct: the in-flight barrier epoch is one word written under the lock at a retype whose watermark is ready (a rare event), and the :1281 rewording is free. Exact texts:

- :676, after "while the request of its core is in use it returns `again` with nothing changed, as any call that needs it does", add:

> a barrier is in flight while any core's request holds an uncompleted barrier: one in-flight-barrier word, written under the node lock when a barrier starts and cleared at its completion, and a call whose watermark is ready returns `again` with nothing changed while it is set, instead of starting a second barrier

- :1281: replace "the instant of its next armed timer when it goes idle (the largest value if none)" with "the earliest replenishment or firing instant armed on its hardware timer when it goes idle (the largest value if none)".

---

## What the report missed (same passages, same standard of proof)

1. **The entry stub also clears the interrupt table.** :1411 and :2024: "Each core passes the entry stub, ... clears its interrupt table". So retired-handle protection cannot live in the interrupt table at all — not only across R6 (Finding 2) but across the next `node_start` on the core. The retired-vector bitmap must be checked by `irq_claim` independently of the table, and both R6 and the entry stub must leave it untouched.
2. **The formal-models list is stale against D-138.** Item 3 of "The formal models of D-027" in Changes for abi/ still names only the shootdown, the lock-free slot read, and the atomic signal. The D-138 watermark barrier against the two lock-free paths is not in the model list, and the atomic-signal model does not name `notify_bind`'s store-load order — the Finding 1, scenario 3 gap, missed in this passage.
3. **Finding 3's correction does not close the wrong-unit-by-owner variant** (see Finding 3): an owner detaching through a different unit's holder passes the empty-entry check, flips its own word to `*detached*` before the real unit blocked the device, and the requester's gate then writes 0 and frees the identifier while the real context entry still translates — the device can DMA into memory the owner then frees. The empty-entry case must also require the word to read `*detached*`.
4. **Finding 8 scenario 2's consequence was not connected**: with the literal "next armed timer" reading, `idle_until` is the largest value for an idle first core, so "now − STALE_NS > idle_until" never holds and a hung first core is never found stale by the other nodes' sweeps; the sweep paragraph's own "its `idle_until` is at most `SWEEP_NS` ahead" shows the intended reading is the hardware timer's next armed instant.

---

## Corrections to apply, in order of severity

1. **High — operation 2 detach operand check** (`kernel-interface.md:1036`): replace "the context entry names that domain number in the requester's range (or none is left: a detach is idempotent);" with "the identifier word names the requester with its generation, and the context entry names that domain number in the requester's range, or none is left and the attach word already reads *detached* (a detach is idempotent);".
2. **High — retired-vector bitmap and R6 walk** (`kernel-interface.md:793`, `:1339`): in :793, after "`irq_claim` of it is `busy`", insert "The retirement is recorded outside the table: a retired-vector bitmap of 192 bits per physical core in the living part of the machine table, set at the `*failed*` answer and by R1 for every interrupt entry of the core it clears on a failed unit, read by `irq_claim` (`busy` while a bit is set), left untouched by the entry stub and by R6, and cleared only at machine start-up."; in :1339 replace "every line word taken by X's generation, which becomes free, unclaimed (D-135);" with "every line word taken by X's generation, which becomes free, unclaimed (D-135), and every entry of the interrupt table of each of X's cores, which becomes free, except an entry whose vector the retired-vector bitmap marks, which stays claimed with no irq (D-139);", and in the Bound sentence add "and the `IRQ_TABLE_ENTRIES` entries of each of X's cores" after "the core words".
3. **Medium — `notify_bind` store-load barrier** (`kernel-interface.md:669`): append to the last sentence: "In `notify_bind` the write of the binding is ordered before the read of the word (a store-load barrier between the two), so a `signal` whose OR lands while the bind runs either is seen by the bind's read of the word or finds the binding and wakes the receiver at once: the bind is the third order of the same rule."
4. **Medium — request start instant** (`kernel-interface.md:329`): change "the instant it was started" to "the instant it was started, read from the clock after the node lock is taken, when the request is written and the asked cores' interrupts are sent (not the `now` of the call's entry)".
5. **Low — G9 target-core check on ARM64/RISC-V** (`kernel-interface.md:1082`): append "and the route's target (the affinity written to GICD_IROUTER on ARM64, the APLIC target on RISC-V) names a core whose word names the requester with its generation, as the handle or the APIC ID must on x86-64".
6. **Low — in-flight barrier word** (`kernel-interface.md:676`): after "while the request of its core is in use it returns `again` with nothing changed, as any call that needs it does", add "a barrier is in flight while any core's request holds an uncompleted barrier: one in-flight-barrier word, written under the node lock when a barrier starts and cleared at its completion, and a call whose watermark is ready returns `again` with nothing changed while it is set, instead of starting a second barrier".
7. **Low — `idle_until` wording** (`kernel-interface.md:1281`): replace "the instant of its next armed timer when it goes idle (the largest value if none)" with "the earliest replenishment or firing instant armed on its hardware timer when it goes idle (the largest value if none)".
8. **Low — :384 header clause** (`kernel-interface.md:384`): change "and its entry in the header not *detaching* (success, nothing changes)" to "and its entry in the header present and not *detaching* (success, nothing changes)". Optional, same severity: in :371 col *attached*, after "the device stays in the header, `busy`", add "at a step of a destruction the device leaves the header as at a detach answered *failed* (:372), and the destruction goes on".
9. **Low — :1326 scoping clause** (`kernel-interface.md:1326`): replace "and stays undone on a unit that has failed" with "and on a unit that has failed it is done for every node but a node that had a device behind that unit, for which it stays undone ([IOMMU](#iommu))".
10. **Low, documentation only — D-138/D-139 cleanup**: :17 and :2112 "under locks" → "under one node lock (D-138)"; :148 append "the Errors table below gives the general rule (a request, a credit or an entry in use, or a barrier started)"; :1787 replace "the head of the chain of the tables a change unhooked" with "the addresses of the tables a change unhooked, kept outside the tables (D-139)"; add a "Since D-139" bullet after :1788 ("The chain of unhooked tables is kept outside the tables (in the invalidation request and in the unit request table entry, at most 2 × (L − 1) and 2 × (L_io − 1) words); an interrupt entry whose invalidation a failed unit answered `*failed*` is recorded in the retired-vector bitmap and stays claimed until the machine restarts, and `irq_claim` of it is `busy`."); Calls table add row "| 34 | `IoSpaceAttach` | waits for a unit request (waiting for a unit); `Again` if the unit's request table is full; `Busy` if the unit is found failed (D-131) |" and append "`Again` if the unit's request table is full" to rows 32, 33 and 46; :1788 extend the reserved list with "the lock word inside every object (endpoint, notify, reply and timer of 64 bytes, sched and task of 256 bytes, thread, aspace and iospace header), the 16-byte directory entry of a cspace, its eight range-lock words and the lock word of each core ([Object sizes](#object-sizes), D-138)"; :1913-1916 mark each lock word "reserved since D-138"; add the D-138 watermark barrier and `notify_bind`'s order to the formal-models list (item 3 of "The formal models of D-027").
