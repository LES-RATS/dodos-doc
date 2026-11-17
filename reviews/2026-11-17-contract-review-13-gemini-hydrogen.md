# Contract Review 13 (Pass 20)

**Reviewer:** Gemini 4 Hydrogen  
**Date:** 2026-11-17  
**Target:** `architecture/kernel-interface.md` at `main` (`6eb2f4b`, Pass 20 / `D-138`–`D-139`), cross-checked against `architecture/kernel.md` and `architecture/scheduling.md` at `6eb2f4b` and directly retrieved external references where opened.

---

## Findings

### Finding 1 — CRITICAL: Lock-free `signal` (`:669`) corrupts a live `notify` and returns `ok` after deletion/move, violating `gone` and `:668`, and omits `notify_bind`'s barrier

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:12` (Rule 2):
  > "**Any call can fail with `gone`.** A capability is revocable at any time (rule 1 of the [ABI](wasm-abi.md#abi-rules))."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:231` (`notify_bind`):
  > "If the word is not zero and a thread already waits to receive on the endpoint, and the first one has an own scheduling context (D-110), the notification is delivered at once."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:668` (`Reading a capability slot`):
  > "**Once it holds the lock, the call reads again the sequence word of each segment its lookup read without it, and if one has changed it looks the slot up again under the lock (D-138):** so no call acts on a capability that an event of another core removed between its read and its lock."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:669` (`Signalling a notify`):
  > "`signal` sets its bits by one atomic OR on the notify's word, then reads whether a thread waits on the notify or on the endpoint bound to it, and returns without the lock if none does; otherwise it takes the lock, checks its lookup as above, and wakes the first waiter if the word is not 0. Every other write of the word (an arrival, a firing timer, a receive that takes the bits) is an atomic operation too, made under the lock. A `signal` whose OR reached a notify that an event of another core destroyed after the lookup has signalled it before its destruction: the bits are lost with the notify, and the call succeeds. The removal of the lost wake-up that the trial's test hammers rests on two orders, the waiter's (it records that it waits, then reads the word) and the signal's (its OR, then its read of the waiters), each a store before a load; the small model of the atomic signal ([Changes for `abi/` and the model](#changes-for-abi-and-the-model-d-128-d-129)) checks them."

**Scenario / Contradiction:**
Line `669` considers only the case where the `notify` object itself is *destroyed* concurrently (`"the bits are lost with the notify, and the call succeeds"`). It fails whenever the `notify` stays alive (held by another capability slot or its root) while the caller's slot *S* is deleted, revoked, or moved concurrently under the node lock:

1. **Returning `ok` after deletion/move and mutating a live `notify` (no waiter):**
   - Core 0 calls `signal(S)` and looks up slot *S* without the node lock (`:668`), reading `notify` *N* with badge *B*. No thread is waiting on *N* or its bound endpoint.
   - Core 1 acquires the node lock, completes `cap_delete(S)` (or `cap_revoke` removing *S*, or `cap_move(S -> S2)`), and then completes `poll(N)` (which returns 0 and clears `N.word`). Core 1 releases the node lock.
   - Core 0 now executes the atomic OR of *B* into `N.word`, reads that no waiter exists on *N* or its bound endpoint, and **returns `ok` without ever taking the node lock or re-reading the segment sequence word**.
   - Result: `signal(S)` returns `ok` after `cap_delete(S)` and `poll(N)` both completed (non-linearizable, violating `:668`'s *"no call acts on a capability that an event of another core removed between its read and its lock"* and Rule 2 `gone`), and injects phantom bits *B* into live *N* (which a later `wait`/`poll` consumes).

2. **Mutating a live `notify` before returning `gone`/`invalid` (waiter present):**
   - Same interleaving, except a receiver waits on *N* or its bound endpoint.
   - Core 0 executes the atomic OR into `N.word` *before* acquiring the node lock, then takes the lock, detects that *S*'s segment sequence word changed (`:668`), re-looks up *S* (finding it empty/dead/moved), and returns `gone` or `invalid` — **after already setting bits *B* in `N.word`**. The next wake-up or `recv`/`poll` on *N* observes bits from a call that failed.

3. **Missing store-load barrier in `notify_bind`:**
   - `:669` says lost-wake-up freedom rests on *"two orders, the waiter's (it records that it waits, then reads the word) and the signal's (its OR, then its read of the waiters), each a store before a load"*.
   - However, under `:231`, `notify_bind(N, ep)` can run when a receiver with an own context is *already* waiting on `ep`: it stores the binding (`N.bound_ep = ep`) and loads `N.word` to deliver at once if non-zero. Without a store-load barrier in `notify_bind` between storing the binding and reading `N.word`, a concurrent lock-free `signal` on `N` can store `N.word |= B` and read `N.bound_ep == 0` (returning `ok` without taking the lock) while `notify_bind` reads `N.word == 0` under the lock, losing the wake-up.

**Smallest correction:**
Take the node lock in `signal` before mutating `N.word` (so `:668`'s rule — re-checking the segment sequence word under the lock before acting on the capability — holds for `signal` just as for every other call, eliminating Scenarios 1, 2, and 3 cleanly under L1); or, if `signal` must remain lock-free when uncontended, validate a per-slot generation/epoch or hold/re-check the capability state atomically before mutating `N.word` (which a bare word OR on `N` without holding the lock cannot achieve for slot deletion/move), and add `notify_bind`'s store-load barrier (binding write ordered before reading `N.word`) to `:669`.

---

### Finding 2 — CRITICAL: A failed IOMMU unit deadlocks every subsequent dead node's reclaim barrier (`:1326`, `:1353`, `:398`), and R6 (`:768`, `:1339`) erases retired `(core, vector)` handles (`:793`)

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:398, 400` (`IOMMU`):
  > "- the reclaim barrier of a node that had a device behind the unit never holds, since the holder cannot confirm that it blocked that device and does not write `acked` for the node: the node stays fenced, its memory frozen, until the machine restarts ([The reclaim barrier](#the-reclaim-barrier))."
  > "Why: a unit that does not confirm cannot be repaired by software, so the memory a device behind it may still reach is kept out of use and nothing else stops."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:768, 793` (`Interrupts`):
  > "When a node's generation ends, R6 leaves the tables of its cores with no entry claimed before the cores are free ([Reclaim](#reclaim))."
  > "**if one was answered *failed*, the vector, its remapping entry and so its handle (the core's number and the vector) are not reused while the unit is failed, that is until the machine restarts (D-139):** the vector stays claimed on its core with no irq, `irq_claim` of it is `busy`, and no other source can be given the handle that the failed unit may still hold in its cache"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1326` (`R1`):
  > "**R1.** If *Y* holds a unit role, it blocks *X*'s devices on that unit: it clears every context entry whose iospace root table lies in memory the ownership table gives to *X* or in *X*'s floor, clears the remapping entries of *X*'s cores on that unit (for an IOAPIC role, masks the inputs whose line words *X*'s generation took), and invalidates; R1 is done when the unit confirms, and stays undone on a unit that has failed ([IOMMU](#iommu))."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1339` (`R6. Clear`):
  > "The live node that sees the barrier hold walks, through its gate and in steps of its recovery reserve: every chunk whose ownership word reads *taken* by *X*'s generation ... and every chunk of *X*'s floor, whose map count becomes 0 and whose page classes become *data*; every device entry taken by *X*'s generation, whose leaf count becomes 0; ... every entry of *X*'s grant table ...; every entry of *X*'s use table ...; every line word taken by *X*'s generation, which becomes *free*, unclaimed (D-135); the attach word beside every identifier word taken by *X*'s generation, which becomes 0 ...; and every core word that names *X*'s generation, which becomes *free* (keeping the flag unusable)..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1353` (`The reclaim barrier`), `:1375`, and `:1485`:
  > "A holder has done R1 for *X* on its units before its R5; a node that takes a unit role writes `acked[X]` = *g* only once it has run R1 for *X* on that unit, and writes it back to 0 first if it had acknowledged *X* before ([Roles](#roles), R1 at every change of holder)."
  > "a holder whose unit failed never writes `acked[X]` if a device of *X* sat behind that unit"
  > "For each such node *Z* that is not dead, it does not write `acked[Z]` = *Z*'s generation until that R1 is done"

**Scenario / Contradiction:**
There are two coupled containment and liveness defects here:

1. **Machine-wide reclaim deadlock when any IOMMU unit fails:**
   Lines `398`, `400`, and `1375` state that only a node *that had a device behind the failed unit* stays fenced (`"nothing else stops"`). However, `:1326` unconditionally defines R1 for *X* on every IOMMU unit *Y* holds as *"done when the unit confirms, and stays undone on a unit that has failed"*, and `:1353` and `:1485` forbid *Y* from writing `acked[X] = g` until R1 is done on every unit *Y* holds, regardless of whether *X* had any device attached behind the failed unit. Once a single IOMMU unit *U* fails, its holder *Y* can never complete R1 on *U* for **any** subsequent dying node *X* — even a node with zero devices and zero remapped interrupts behind *U*. Every node that dies after *U* fails stays stuck in `fenced` forever, freezing all of its memory and physical cores.

2. **R6 erases `:793`'s retired `(core, vector)` handles and misses interrupt tables:**
   - First, `:1339` (`R6. Clear`) explicitly lists every table/word R6 walks and omits the **interrupt tables** of *X*'s cores, even though `:768` relies on R6 to clear them before the cores become free (and `:1339`'s bound calculation omits them).
   - Second, suppose physical core *P* of node *X* holds a vector *v* retired by `:793` (`*failed*` IEC invalidation on failed unit *U*), or *X* dies while holding active remapping entries on *P* whose IEC invalidation *U* cannot confirm. When *X* passes R6 (for instance, because *X* had no DMA device behind *U*, once Part 1 is fixed; or if *X* had vectors retired earlier on *U* before dying), `:768` states *"R6 leaves the tables of its cores with no entry claimed before the cores are free"*. Clearing every entry of *P*'s interrupt table in R6 destroys the retired state of `(P, v)` (`:793`)! When core *P* is allocated to a new node, `irq_claim` on `(P, v)` succeeds and hands out handle `(P, v)`, allowing *U*'s stale cached interrupt-entry-cache entry to deliver interrupts under the wrong vector or source.

**Smallest correction:**
1. In `:1326`, `:1353`, and `:1485`: when an IOMMU unit *U* has failed, R1 on *U* for *X* checks whether *X* had any context entry on *U* (root in *X*'s chunks or floor, or any attach word/identifier word of *X* naming an iospace on *U*). Only if *X* had such a device behind *U* does R1 stay undone and withhold `acked[X]` (`:398`, `:1375`). If *X* had no device behind *U*, *Y* still clears *X*'s IRTEs on *U* in memory, retires those active `(core, vector)` handles (since *U*'s IEC cannot be invalidated), and marks R1 on *U* done so *X* can reclaim cleanly (`:400`).
2. Keep a per-physical-core **retired-vector bitmap** (192 bits = 24 bytes per physical core in the living/kept machine table, cleared only at machine start-up and checked by `irq_claim`): `:793` sets `(core, vector)` in it on any `*failed*` IEC invalidation, R1 sets it for any active IRTE of *X* cleared on a failed IOMMU unit, and R6 (`:768`, `:1339`) explicitly walks *X*'s cores' interrupt tables to clear claimed entries while preserving the retired-vector bitmap until the machine restarts.

---

### Finding 3 — HIGH: Faulty requester `Op 2 detach` (`:1036`) corrupts another node's live `AttachWord` (`*attached*` → `*detached*`)

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:342` (`IOMMU`):
  > "The kernel does not check that a device belongs to the unit's scope: discovering the devices is the platform service's job. A device attached through the wrong unit stays blocked, since its own unit still blocks it."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1035-1036, 1040` (`The operands of each operation`):
  > "| 1 attach | device identifier (0-15), domain number (16-31) | physical address of the iospace's root table | G9: the attach word moves from *pinned* to *attached* with that root (or reads *attached* with it), the root being of class 48 + *n*, *n* ≥ 1, held by the requester; the identifier word names the requester with its generation; the domain number is in the requester's range on the unit (D-137) |"
  > "| 2 detach | device identifier (0-15), domain number (16-31) | 0 | the context entry names that domain number in the requester's range (or none is left: a detach is idempotent); once the invalidation is complete, the holder's gate writes the attach word *detached* if it reads *attached*; the identifier word stays the requester's until the requester's gate writes it *free* at the answer, with the attach word 0, which it does only if the word reads *detached* with the root its entry names (D-137, D-139) |"
  > "A request whose operands fail these checks is not written to the unit: the holder traces it (code 11, [What the kernel traces](#what-the-kernel-traces)) and answers it done, so the requester's entry ends; a correct requester never sends one, and a faulty one gains nothing by it."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1475` (`Take-over after a death`):
  > "...writing a context entry only for a device whose attach word reads *attached* with the root the report names"

**Scenario / Contradiction:**
Unlike `Op 1 attach` (`:1035`), `Op 2 detach` (`:1036`) **does not check `IdentifierWord(device)`** against the requester and its generation, and accepts any request whose context entry on that unit is empty (`"or none is left: a detach is idempotent"`).
1. Victim node *V* attaches device `dev` (behind IOMMU unit `U1`) to its `iospace`, setting `IdentifierWord(dev) = *taken*(V, g_V)` and `AttachWord(dev) = *attached*(root_V)`.
2. A faulty kernel in another node *R* sends `UnitRequest(Op 2 detach, dev, domain_in_R)` to the holder *H* of a *different* IOMMU unit `U0`.
3. On `U0`, the context entry for `dev` is empty (`"none is left"`), so `:1036`'s check passes!
4. *H* runs invalidation on `U0` and *H*'s gate flips `AttachWord(dev)` from `*attached*(root_V)` to **`*detached*(root_V)`**.
5. Victim *V*'s subsequent `iospace_attach(..., iso_V, dev)` returns `busy` (`:367`, col `*detached*`), and if `U1`'s holder dies and a successor rebuilds `U1` (`:1475`), `AttachWord(dev) == *detached*(root_V)` causes the rebuild to **clear *V*'s live context entry on `U1`**, halting *V*'s active DMA via a forged request on `U0`.

**Smallest correction:**
Add the ownership check to `Op 2 detach` in `:1036`: require `IdentifierWord(device)` to name the requester with its current generation (just as `Op 1` in `:1035` does) before invalidating or changing `AttachWord(device)` from `*attached*` to `*detached*`.

---

### Finding 4 — HIGH: Out-of-header `*attached*` state contradictions (`:369`, `:372` vs `:370`, `:373`, `:384`), and infinite `again` loop on faulty-holder `detach answered done` during `iospace` destruction (`:371`)

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:369, 370, 371, 372, 373` (`The attach word against every event`, D-139):
  - `:369` (row `attach answered *failed*`, col `*attached*`):
    > "stays *attached* (the holder served the attach, then the unit did not confirm its invalidation): *n* and the identifier word stay, the device stays out of the header, `busy`; the root and its tables keep their class until the machine restarts"
  - `:370` (row `detach asked`, col `*attached*`):
    > "the entry is marked *detaching* and operation 2 is sent; if it is already *detaching*, `busy` and a step returns `again`"
  - `:371` (row `detach answered done`, col `*attached*`):
    > "the holder refused the request (it traces it): the *detaching* mark is cleared, the device stays in the header, `busy`"
  - `:372` (row `detach answered *failed*`, col `*attached*`):
    > "stays *attached*: *n* and the identifier word stay; the device leaves the header; `busy`; the root and its tables keep their class until the machine restarts ... and the destruction goes on"
  - `:373` (row `iospace destroyed`, col `*attached*`):
    > "the step asks the detach, as above"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:384, 391`:
  > "- the device is already attached to this iospace with no request of it in flight: its attach word *attached* with this iospace's root, and its entry in the header not *detaching* (success, nothing changes);"
  > "a detach answered *failed* takes the device out of the header with its attach word *attached* and the count above 0, so the destruction goes on and ends with the root and its tables keeping their class, lost to the node until the machine restarts (below; D-139: the device stayed in the header and every step asked its detach again, for ever)."

**Scenario / Contradiction:**
1. **Out-of-header `*attached*` contradicts `:370`, `:373`, and `:384`:**
   After `attach answered *failed*` (`:369`) or `detach answered *failed*` (`:372`), `AttachWord(dev)` reads `*attached*(root)` with *n* > 0, **while `dev` has no entry in the `iospace`'s header**. However, the table's col `*attached*` assumes a header entry always exists:
   - `:373` (`iospace destroyed`) says `"the step asks the detach, as above"`, which cannot mark a non-existent header entry `*detaching*` (and if destruction skips devices absent from the header per `:391`, `:373` col `*attached*` is wrong when `dev` is out of the header);
   - `:370` (`detach asked`) assumes an entry exists to mark `*detaching*`;
   - `:384` says `"its attach word *attached* with this iospace's root, and its entry in the header not *detaching*"` without stating `"and its entry is in the header"`.
2. **Infinite `again` loop when a faulty holder sends `UnitAnswer(done)` without running its gate (`:371`):**
   During `iospace` destruction (`:373`, `:391`), if a step sends `Op 2 detach` for an in-header `*attached*` device and a faulty unit holder refuses/ignores it and replies `UnitAnswer(done)` without changing `AttachWord(dev)` to `*detached*`, `:371` clears `*detaching*` and **leaves the device in the header**. The next `cap_delete` / `cap_revoke` step sees the exact same device in the header without `*detaching*`, sends `Op 2` again, gets `UnitAnswer(done)` again, and loops `again` **forever** — reproducing the exact infinite-destruction DoS fixed for `*failed*` in `:372`/`391`.

**Smallest correction:**
1. In `:370`, `:373`, and `:384`: explicitly distinguish the out-of-header `*attached*` state left by `:369`/`372` (`dev` not in the `iospace` header): `iospace_attach(..., iso, dev)` returns `busy` (`:381` unit failed, and `dev` is not in the header in `:384`), `iospace_attach(..., 0, dev)` returns `busy` (`:390`), and `iospace` destruction (`:373`) does nothing / skips it (leaving *n* > 0 and root/table classes non-reusable until reboot).
2. In `:371` (col `*attached*`, row `detach answered done`): when the `Op 2` was sent by `iospace` destruction (or whenever the unit holder refused `Op 2`), take the device out of the header while keeping `AttachWord = *attached*`, *n* > 0, and `IdentifierWord = *taken*` (identical to `:372`, `detach answered *failed*`), so teardown terminates without freeing the unconfirmed root/tables.

---

### Finding 5 — HIGH: Incomplete D-138 / D-139 cleanup across `kernel-interface.md` (`:17`, `:2112`, `:148`, `:1769`, `:1787–1788`, `:1913–1916`)

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:17` and `:2112`:
  > "Inside a node the cores share the node's state, under locks ([A node of several cores](#a-node-of-several-cores))."
  > "The node's cores share its objects, under locks ([A node of several cores](#a-node-of-several-cores))"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:148` (`Order of checks`):
  > "A call that passes every check may still return `again`, having done a bounded step of its work (removal, clearing of memory), or, for `recv` and `reply_recv` by a thread without an own context, having recorded a fault *no context* that it could not receive ([Faults](#faults)), or, in a node of several cores, having changed nothing because the request of its core is in use or has just been started for the barrier of a watermark ([A node of several cores](#a-node-of-several-cores), D-138)."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1769, 1787, 1788` (`Changes for abi/ and the model`):
  > "**Errors.** No new code. `Again`, with nothing changed, is a new result of `untyped_retype`, `memory_give` and `memory_split` for the barrier of a watermark, in the rows above (D-138); the fourteen calls to which D-134 and D-135 gave the `again` of the rule of tries under L2 lost it with L2."
  > "- Since D-137: ... in an invalidation request and in an entry of the unit request table, the head of the chain of the tables a change unhooked; ... the new *k* of each call (`locks::bound` of the model: ...), withdrawn by D-138."
  > "- Since D-138: ... the quiet word with its ticket lock, the entry word of each core and the two bits of a thread's count of `again` stay in the layout, reserved and written as 0, so that a lock per object can come back without a change of format ([A node of several cores](#a-node-of-several-cores)); the *k* of each call and the `again` of the rule of tries leave `abi/` and the model."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1913–1916` (`Object sizes`):
  > "| `sched` | ... and a lock word (D-129) |"
  > "| `task` | 256 bytes, a lock word included |"
  > "| `thread` | ... the state *leaving its core* and a lock word ... |"
  > "| `aspace`, `iospace` | ... eight range-lock words and a lock word; the header of an iospace holds a lock word too ... |"

**Scenario / Contradiction:**
1. **Residual `"under locks"`:** Lines `17` and `2112` still say `"under locks"`, whereas `:666`, `kernel.md:28`, and `scheduling.md:9` say `"under one node lock"` after D-138 removed L2.
2. **Incomplete `Order of checks` (`:148`):** Line `148` lists zero-side-effect `again` only for an in-use core invalidation request and a watermark barrier, omitting three other zero-side-effect `again` cases in the contract: (a) a full `unit request table` (`:1043`: *"returns `again` with nothing changed"* on `iospace_unmap`, `iospace_attach`, `irq_claim`, and removal steps), (b) `cap_revoke` finding `REQUESTS_PER_PEER` credits exhausted (`:915`: *"returns `again` with no message and no wait"*), and (c) `thread_suspend` or repeated `task_revoke` calls finding *leaving its core* still set (`:692`, `:1142`; contrast `:1894`, which explicitly includes *"a request, a credit or an entry in use, or a barrier started"*).
3. **Stale D-137 unhooked-table description and missing D-139 entries in `Changes for abi/` (`:1787–1788`, `:1754`, `:1759`):**
   - Line `1787` (`Since D-137`) still says an invalidation request and a unit request table entry hold *"the head of the chain of the tables a change unhooked"*, directly contradicting D-139 in `:267`, `:329`, and `:1043` (*"the chain is kept outside the tables ... the request grows by 2 × (L − 1) words"* and `"at most 2 × (L_io − 1)"`).
   - There is no `Since D-139` entry in `:1788–1789` (omitting the unhooked-table address arrays, `AttachWord` D-139 changes, `Report` bit 32 mask state, and keeping retired vectors on `*failed*` IEC invalidation), and the Calls table (`:1754`, `:1759`) omits `IoSpaceAttach` and the `Again` on full `unit request table` for `IoSpaceUnmap`, `IoSpaceAttach`, and `IrqClaim` (`:1043`).
4. **Incomplete D-138 reserved-word list in `:1788` and `Object sizes` (`:1913–1916`):**
   - `:1788` omits the per-object lock words (`sched`, `task`, `thread`, `aspace`, `iospace`), per-core lock words, and `8` aspace range-lock words that `:671` explicitly keeps reserved and written as 0.
   - In `Object sizes`, `:1912` (`"reserved"`) and `:1917` (`"stays free ... D-138"`) note that their lock fields are reserved, whereas `:1913–1916` still describe the `sched`, `task`, `thread`, `aspace`, and `iospace` lock/range-lock words as active without marking them reserved.

**Smallest correction:**
Update `:17` and `:2112` to `"under one node lock"`; add full `unit request table` entries, `cap_revoke` credit exhaustion, and *leaving its core* to `:148`; update `:1787` and add `Since D-139` (plus `IoSpaceAttach` and unit-request-table `Again` in the Calls table); and add the missing reserved lock/range-lock words to `:1788` and mark them reserved in `:1913–1916`.

---

### Finding 6 — MEDIUM: `CORE_ANSWER_NS` bound `2 × E + D` (`:687–688`, `:1510`) conflicts with `now` read at kernel entry (`:497`), and kernel vectors `240–255` (`:799`) lack priority separation

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:497` (`Clock`):
  > "**The kernel uses the same value.** Every event of a kernel (a call, an interrupt, a fault) has one instant, `now`: the clock read at its entry, with the same parameters."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:329, 331` (`TLB`):
  > "...the instant it was started..."
  > "A core that does not acknowledge a request within `CORE_ANSWER_NS` of its start is a failure of the node, not of the call: the core that starts a request arms a due event of its timer queue at that instant, and if the request is not complete then, the node accuses itself"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:687–688` and `:1510`:
  > "Each asked core answers at the interrupt sent to it, which it takes at the latest at the end of its current kernel event, at most *E* after the request started; then come the interrupt's delivery *D* and the event of the interrupt itself, its wait for the lock and its work included ... at most *E* again. So a wait for a request lasts at most 2 × *E* + *D* ... **The machine start-up refuses a `CORE_ANSWER_NS` not above the longest healthy wait it judges, for the largest *N* the image supports (entry `Node`), from the values measured for that image (D-131, D-137, D-138): 2 × *E* + *D*,** with *E* = *N* × *H*"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:799`:
  > "Vectors 0 to 47 and 240 to 255 are the kernel's: exceptions, the range of the legacy PIC (masked, its spurious vectors ignored), the timer, the interrupts between kernels and the spurious vector of the APIC. Vectors 48 to 239 can be claimed. The priority class of a vector is its high four bits, so the platform service orders interrupts by the vector it chooses."

**Scenario / Contradiction:**
1. **Unaccounted pre-lock wait in `2 × E + D`:**
   Under `:497`, a kernel event has one `now` read *at its entry*, before taking the node lock. Under L1 (`:683`), a requester waits up to `(N − 1) × H` to acquire the node lock before writing its request and sending the invalidation IPIs (`:329`). If `"the instant it was started"` (`:329`, `:331`) is `now` from kernel entry, then the asked core can take up to `(N − 1) × H` (requester's lock wait) + *E* (asked core's current event) + *D* + *E* (interrupt event) = `2 × E + (N − 1) × H + D` (up to nearly `3 × E + D`) — exceeding the `2 × E + D` check in `:688` and `:1510`. Conversely, if the requester reads the clock *inside the node lock* when sending the IPIs, `:329`/`:687` needs to say so explicitly rather than relying on `:497`.
2. **Equal priority class for all kernel vectors `240–255` (`:799`):**
   Every kernel vector (timer, TLB invalidation, leave, reschedule, user-ring wake-up, APIC spurious) sits in the single top priority class `15` (`240–255`) with no relative priority ordering specified inside `240–255`, allowing bursts of lower-urgency IPIs (such as reschedule or user-ring wake-ups) to be dispatched ahead of timer, invalidation, or leave interrupts when multiple vectors are latched in IRR.

**Smallest correction:**
State explicitly in `:329`, `:331`, and `:687` that `"the instant it was started"` is read from the clock *after* acquiring the node lock when the request's IPIs are sent (or raise the start-up check in `:688` and `:1510` to `2 × E + (N − 1) × H + D`), and fix a relative vector order inside `240–255` in `:799` (keeping timer, leave, and invalidation vectors above reschedule/ring wake-ups).

---

### Finding 7 — MEDIUM: Missing target-core check in G9 for ARM64/RISC-V line routes (`:1082` vs `:1039`), and omitted failure cleanup in `:1044` vs `:349`

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1039` (`Op 5 redirection entry`):
  > "claimed: the handle, or the APIC ID, names a core whose word names the requester, and the line's word names the requester with its generation"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1082` (`G9. IOMMU tables`):
  > "A line's redirection entry (and on ARM64 the route of an SPI, on RISC-V the target of an APLIC source) is written only for the node the line's word names with its generation, or masked when the word is free or names the requester with its generation (D-135, D-137, [Interrupts](#interrupts))."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:349` (`iospace_unmap`):
  > "If the unit is found failed, the call returns `busy`, the record is emptied with its counts kept and the unhooked tables never join the free list, keeping their class (below)."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1044` (`At the answer`):
  > "*done* completes the entry (the counts of the record's leaves are lowered and the record is emptied, or the waiting call ends with its result) ... *failed* empties the record with its counts kept, or ends the waiting call with `busy`"

**Scenario / Contradiction:**
1. **Unchecked target core on ARM64 / RISC-V line routes (`:1082`):**
   On x86-64, `:1039` verifies both that the line word names the requester and that the target `handle` or `APIC ID` names a physical core whose core word names the requester. In G9 (`:1082`), the ARM64 SPI route (`GICD_IROUTER`) and RISC-V APLIC target rule checks *only* the line word, omitting any gate check that the target core (`GICD_IROUTER` affinity / `MPIDR`, or RISC-V target hart in `:960`) belongs to the requester (`CoreWord` naming the requester's generation). A faulty requester holding a line word on ARM64 or RISC-V could therefore steer its line interrupt onto another live node's physical core.
2. **Omitted unhooked-table handling on `*failed*` (`:1044` vs `:349`):**
   Line `1044` states that `*done*` completes an unmap entry and `*failed*` *"empties the record with its counts kept"*, without stating (as `:349` requires) that the `at most 2 × (L_io − 1)` unhooked table addresses stored in the `unit request table` entry (`:1043`) must **not** be placed on the `iospace`'s free list when the answer is `*failed*` (they remain off the free list with their class kept until `iospace` destruction).

**Smallest correction:**
1. In `:1082` (and in the ARM64/RISC-V operation rules corresponding to `:1039`), require the holder's gate to check that an enabled SPI route (`GICD_IROUTER`) or APLIC target names a physical core whose `CoreWord` names the requester with its current generation.
2. In `:1044`, add explicitly that on `*failed*`, the unhooked tables listed in the unit request entry do not join the `iospace`'s free list (matching `:349`).

---

### Finding 8 — LOW: Watermark-barrier "already in flight" check (`:676` vs `:881`, `:1744`) and `idle_until` omission (`:1281` vs `:650`)

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:676` (`barrier`):
  > "Otherwise the call starts a barrier and returns `again` with nothing changed: the request of its core ... while the request of its core is in use it returns `again` with nothing changed, as any call that needs it does."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:881` (`memory_give`) and `:1744`:
  > "until the barrier that returns it is complete, the call starting it if none covers it"
  > "`Again` with nothing changed while the watermark is ready to return and no complete barrier covers it; the call starts the barrier if none is in flight"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:650` (`Idle`) and `:1281` (`Beacons`):
  > "Its kernel sets the hardware timer to the next instant it must act (the earliest replenishment instant or firing instant, which it knows exactly because there is no periodic tick)"
  > "`idle_until`, the instant of its next armed timer when it goes idle (the largest value if none), written on the clock it is compared on: in a development image, the monotonic instant of the timer less the stopped time when the core goes idle"

**Scenario / Contradiction:**
1. **Redundant barrier start across two cores:** Lines `881` and `1744` state that a call starts a watermark barrier only *"if none covers it"* / *"if none is in flight"*, whereas `:676` checks only `"the request of its core"`. If Core 0 has already started a barrier covering epoch *e*, a concurrent `untyped_retype` / `memory_give` / `memory_split` on Core 1 for an untyped at epoch ≤ *e* starts a redundant second barrier IPI wave instead of waiting (`again`) on Core 0's already in-flight barrier. (Safe, since both still return `again`, but causes extra IPIs to idle cores and contradicts `:1744`.)
2. **`idle_until` wording:** Line `1281` calls `idle_until` *"the instant of its next armed timer"*, whereas `:650` arms the hardware timer for *"the earliest replenishment instant or firing instant"*. If a core goes idle with an armed scheduling-context replenishment and no `timer` object, `"next armed timer"` literally leaves `idle_until = u64::MAX` even though `:650` arms the timer for that replenishment.

**Smallest correction:**
Track an `in_flight_barrier_epoch` (or check whether any core's active barrier request already covers the untyped's word 6 epoch) in `:676` so Core 1 returns `again` without sending a duplicate barrier; and change `:1281` from `"its next armed timer"` to `"the earliest replenishment or firing instant armed on its hardware timer"` (matching `:650`).

---

## What I checked and found correct

- **Watermark epoch barrier under L1 (`:673–678`, `:164`, `:881`, `:885`, `:887`, `:138`):** Using a node-wide `kernel_epoch` on last object destruction and a core-broadcast `barrier_epoch` on `untyped_retype`, `memory_give`, `memory_split`, and block destruction closes the D-137 `entry_word` gap cleanly under L1 without per-entry memory barriers.
- **`Tasks and marks` under L1 (`:1114–1157`):** Taking the single node lock (`D-138`) resolves Review 12 Finding 2: `task_attach` and message delivery can no longer race on `T.task`, `T.own_word`, and `Task.marks`.
- **D-139 `Report` bit 32 mask state & IOAPIC rebuild (`:960`, `:1039`, `:1475`):** Recording the active mask state in bit 32 of the `Report` item and applying it during IOAPIC rebuild prevents unmasking idle, fired, or dying lines on role take-over (Review 12 Finding 6).
- **Unhooked-table array `2 × (L − 1)` / `2 × (L_io − 1)` and free-list link clearing (`:267`, `:329`, `:1043`):** Storing unhooked table addresses in the invalidation request / unit request table entry and clearing the first word under the gate lock before re-hooking preserves G3(4) after every store (Review 12 Finding 5).
- **`idle_until` and debugger `stopped time` (`:1281`, `:1292`, `:1660`):** Both `idle_until` and `now − STALE_NS` are now expressed on `monotonic − stopped_time` in development builds, fixing Review 12 Finding 10. (Note also that `now − STALE_NS` in `:1292` does not underflow when `now − t >= STALE_NS` and `t >= 0`.)
- **Cross-file lock consistency:** [kernel.md:28](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L28) and [scheduling.md:9](file:///Users/btw/Documents/repos/Docs/architecture/scheduling.md#L9) match `D-138`'s `"under one node lock"`.
- **External citations audited on 2026-11-17 (only URLs directly retrieved below):**
  - `https://df.lth.se/~getz/ARM/SysReg/AArch64-tlbi-aside1is.html` — opened on 2026-11-17; matches `:328`'s verbatim quote on the Inner Shareable broadcast domain.
  - `https://df.lth.se/~getz/ARM/SysReg/AArch64-tlbi-vae1is.html` — opened on 2026-11-17; confirms IS-domain ASID + VA invalidation and EL2&0 regime when `HCR_EL2.{E2H,TGE} == {1,1}` (`:328`).
  - `https://df.lth.se/~getz/ARM/SysReg/AArch64-ttbr0_el1.html` and `https://df.lth.se/~getz/ARM/SysReg/AArch64-ttbr0_el2.html` — opened on 2026-11-17; matches `:328`'s quotes on `CnP` Warm reset UNKNOWN and `CONSTRAINED UNPREDICTABLE` when `CnP == 1` with differing translation tables.
  - `https://docs.riscv.org/reference/aia/v1.0/IMSIC.html` — opened on 2026-11-17; confirms `:768`/`774` supervisor-level IMSIC interrupt file identities `1..2047` (0 invalid) and address/data MSI delivery (`seteipnum_le`).
  - `https://docs.riscv.org/reference/sbi/v3.0/ext-hsm.html` (redirect target of `https://docs.riscv.org/reference/sbi/ext-hsm.html` cited at `:1228`, `:1316`) — opened on 2026-11-17; confirms `STOPPED = 1` (*"The hart is not executing in supervisor-mode or any lower privilege mode."*), `sbi_hart_start`, `sbi_hart_stop`, and `sbi_hart_get_status`.
  - `https://github.com/torvalds/linux/commit/e1c467e69040` — opened on 2026-11-17; confirms `:1310` BSP wake-up via NMI instead of INIT-SIPI-SIPI.
  - `https://gnu.googlesource.com/binutils-gdb/+/master/gdbsupport/x86-xstate.h?format=TEXT` — opened on 2026-11-17; base64-decoded header confirms `#define X86_XSTATE_AVX_SIZE 832` (`:1915`).

---

## What I did not check

- **External specifications not opened on 2026-11-17:**
  - Intel SDM combined volumes, order `325462-093` (September 2026) — **not opened**.
  - *Arm Architecture Reference Manual for A-profile architecture*, Arm DDI 0487, version `M.d` (30 September 2026), including `C5.5.60`, `C5.5.11`, `C5.2.1`, `B2.3.1`, `D8.17` (rule `IWZCBG`), `D8.17.1`, `D8.17.7`, `D8.17.8`, and `D8.2.9` — **not opened**.
  - *Arm Power State Coordination Interface*, `DEN0022F.b` (PSCI 1.3), including `5.1.7`, `5.1.8`, `5.6.2`, `5.7.2`, `5.9`, and `6.6` — **not opened**.
  - *Intel Virtualization Technology for Directed I/O Architecture Specification* (VT-d), revision `5.20`, order `D51397-019` (April 2026), including `§5.1.5.1`, `§6.2.2.1`, `§6.5.2.8` Figure 6-8, and `§11.4.2` — **not opened**.
  - `https://trustedfirmware-a.readthedocs.io/en/v2.12.0/components/sdei.html` — **not opened** (HTTP 404).
  - `https://wiki.osdev.org/PCI` — **not opened** (HTTP 403).
  - Remaining citations in `kernel-interface.md` (`Arm IHI 0069`, Zephyr `intc_intel_vtd.h`, QEMU `intel_iommu.h`, Linux `genericirq.html` / `intel_idle.c` / `tlb.c` / `smp.c`, M. von Tessin `5618.pdf`, RISC-V unprivileged/privileged/crypto specs, OpenSBI `pmu`/`fwft` specs, Arm AARCHMRS, `riscv-unified-db`) — **not opened**.
- **Repository code and sibling files outside the reviewed targets:** `abi/`, the Rust reference model, `decisions/README.md`, and sections of `kernel-interface.md` unrelated to multi-core L1/IOMMU/G1–G14/`abi/` changes (such as capability space depth/derivation rules untouched by D-138/D-139, ELF/boot details, and `platform.md`/`memory.md`/`drivers.md`) were not audited in full in this pass.
