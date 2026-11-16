# Eighth review of the contract: inside a node of *N* cores, and the contract against itself

Review of [kernel-interface.md](../architecture/kernel-interface.md) at `fa90461`,
"the start-up values of the D-110 list follow `abi/` and D-121, D-125" (2122
lines) — line numbers are those of that commit. The
angle is the inside of a node: what is per physical core and what the node's
cores share; the two locking variants and the claim that one layout serves both;
the bound of a call as its one-core bound plus (*N* − 1) times a lock hold; a
thread running on another core; an address space used by several cores; the gate
with several cores; scheduling, admission and interrupts per core; the places
that still describe the old shape; the call table against its lists of values,
errors and rights; and *N* = 1.

Read: the contract end to end; `architecture/kernel.md`; `decisions/README.md`
(D-026 to D-029, D-107, D-110, D-114 to D-129); `abi/` on branch `model` of the
kernel repository at `8c2adef` (`abi/src/lib.rs`, `machine.rs`, `start.rs`,
`debug.rs`, read with `git show`); and the earlier drafts and verifications
(`research/drafts/kernel-shape-*.md`, `reviews/2026-11-16-verify-kernel-shape-*.md`,
`reviews/2026-11-16-verify-multicore-challenge-*.md`), so as to leave out what
they closed and to check that what they found is in fact closed.

Each finding quotes the lines at fault, says what breaks and in which state of
the machine, and gives the smallest paste-ready fix. Nothing in the repository
changed except this file; the explorations are in `/tmp/review8/check.py`.

| # | Severity | Lines | One sentence |
|---|---|---|---|
| 1 | blocks for ever | 327, 328, 644, 972, 979 | An idle core is "sent no interrupt" and acknowledges "when it wakes", yet the unmap "returns when every acknowledgement is in" and G5 needs "every core of the node past a flush epoch": a node with one idle core can never give memory back, destroy a block or change a page class, and the freeing of memory stops for ever rather than for a while. |
| 2 | breaks isolation | 475, 476, 533, 626, 647 | A thread marked *leaving its core* is still **runnable** (it is neither suspended nor waiting), so after `sched_configure` moves its context "and waits for nothing" the new core is free to run it while the old core still runs it: two cores, one thread, one set of registers. |
| 3 | breaks isolation | 250, 273, 287, 295, 297, 327, 1782 | The text defines a full record twice (a mapping or a binding, and separately "a mapping whose entries are cleared"), and neither `aspace_map` nor `aspace_unmap` refuses a record of kind 3, although line 327 promises both are `busy`: one of the two readings leaves a live translation with no record and a map count that never returns to zero, which G14 turns into a stopped machine. |
| 4 | breaks isolation | 622, 630, 635, 637, 1737, 1751, 1783 | Variant L2 needs a lock word in an `untyped` and in an entry of the interrupt table, and neither has one: an untyped's whole state is in its 64-byte capability slot and `Object sizes` has no row for it, and an interrupt entry is written by "the node's kernel … for any of its cores" with no lock named — two `untyped_retype`s can take the same bytes and an `irq_ack` can lose an arrival for ever. |
| 5 | breaks isolation | 326, 974, 1290, 1291 | The ARM64 invalidation is a broadcast that "applies to all PEs in the same Inner Shareable shareability domain", nothing at machine start-up or `node_start` checks a core's domain, and the per-node tag tables need `TTBRn_EL1.CnP = 0`, never stated: a core of the node, or of another node sharing an ASID, can keep a translation the call promised to remove. |
| 6 | unbounded kernel operation | 365, 620, 641, 644, 645, 981, 1347 | Under L1 the node lock is held for a whole kernel event, and an event may wait for a unit's confirmation ("every change on the unit waits", with no bound at all on a stuck unit) or walk the node's tables for the audit of G14, so (*N* − 1) × *H* passes `CORE_ANSWER_NS` at *N* = 11 with *H* = 1 ms and at *N* = 3 with the threshold at the low end of its own range, while the image accepts 64 cores: a healthy node accuses itself and kills every process in it. |
| 7 | unbounded kernel operation | 325, 328, 620, 653 | *N* = 1 pays for protocols it does not have — the idle mark with two compare-and-swaps and a load of the kernel's own root at every idle transition, and a write of the tag's core set at every switch of address space — none of which the "leaves out the protocols" list covers, though both subsections claim a node of one core pays nothing. |
| 8 | wrong result | 180, 440, 647 | `thread_resume` "succeeds when the thread is already in the state asked for", so a resume (or a second suspend) from another core answers `ok` in the middle of a `thread_suspend`'s wait, and `thread_read_regs` and `thread_configure` are not refused on a marked thread: the caller is told a thread that is still executing is stopped. |
| 9 | wrong result | 635, 981, 1224, 979 | The audit of G14 and of R4 takes no lock under L2, so a map, a give or a retype on another core falls between a map count and the leaves it counts, the mismatch is "a violation of containment", and the machine stops with a stop record during a recovery. |
| 10 | unspecified | 635, 642, 979 | The gate lock is a lock of the node block, not a kind, so L2's "one order fixed by kind" does not place it and the bound *k* × (*N* − 1) × *h* does not count it, and no rule forbids a call that holds an object lock and then takes the gate while another takes them in the other order. |
| 11 | unspecified | 866, 867, 917, 921, 937 | `grant_signal` needs `send` on a remote frame capability, whose rights are "those of the anchor", which are "the rights the item asks": nothing requires the sender to ask for `send`, so the ordinary read-only ring grant leaves the grantee unable to ring its doorbell and `node_send` succeeds anyway. |
| 12 | wording | 17, 200, 752, 935, 1702 | "Rule 7 is withdrawn (D-128)" contradicts the Rules list, where rule 7 stands with new text, and three other places cite it as in force — the sentence means the *old* rule 7 and says so nowhere. |
| 13 | wording | 1439, 1613, 1614, 1922 | The lists of values disagree with the text: `StartMachine`'s "layout version (0)" sits in the same cell as "the layout version is 1 since D-129"; the crash record is now one per physical core and `abi/` still calls it the node's; and the `abi/` list gives no offset for any of the lock words the text reserves. |
| 14 | wording | 92, 622, 485, 506 | "It is the only numbering of cores in this contract" is false: every new rule numbers a node's cores by their position 0 to *N* − 1, while a `sched`'s cores set, `node_start` and `sched_set_cores` use machine core numbers with a window and a mask, and the two are used in adjacent paragraphs without a word about which is which. |
| 15 | wording | 921, 1625, 1708, 1729, 1731 | `node_send` returns `no_memory` for a full grant table, though the error means "the supplied untyped memory is exhausted; supply more and repeat", and `send` on a frame (the doorbell) is added in the `abi/` list but is in neither the contract's table of rights nor any of its rules of use. |

## 1. An idle core is not waited for, and G5 waits for it for ever

Three rules, each clear alone, cannot all hold.

Line 327: "the caller waits in the state *waiting for its node's cores*, holding
no lock, and its call returns when every acknowledgement is in. Meanwhile the
frame capability's record is **unmapping**".

Line 328: "**An idle core is not waited for (design choice).** … a request then
only records in that part the invalidation it owes, which the core does when it
wakes, before it loads a root of the node again; it is sent no interrupt for it."

Line 644 confirms the second reading for the bound: "so such a wait lasts at
most *N* × *H* (L1) … (an idle core is not waited for: it does what it owes when
it wakes, [TLB])".

So the set of cores the requester waits for excludes the idle ones — but line
327 says the call returns "when every acknowledgement is in", and line 329 says
a core that does not acknowledge "within `CORE_ANSWER_NS` is a failure of the
node, not of the call: the node accuses itself". A node with one idle core in
the aspace's tag set (line 325: "the set of the node's cores that have loaded
its tag") therefore either waits for an acknowledgement that no interrupt will
ask for, which is the node's own failure after 10 ms, or excludes the core and
leaves its invalidation owed. The second is what the text intends, and then the
flush epoch breaks:

Line 972, G5: "`memory_give`, the destruction of a block and a change of page
class require: … a local invalidation since the count reached zero (on a node of
several cores, every core of the node past a flush epoch, G12)."

Line 979: "Each core keeps a **flush epoch** that only its gate increments, at
each full invalidation of its TLB and at each acknowledgement of an
invalidation".

An idle core's epoch moves only when it wakes and does the invalidation it owes.
An idle core with no context placed on it is woken by nothing: line 628, "an
event on core *a* that makes a context placed on core *b* eligible … sends *b*
the kernel's reschedule interrupt" — a core with no context placed on it has
none to make eligible, and line 499 places every new context on "the node's
first core (position 0)". So on a node of *N* > 1 cores, the cores other than
position 0 begin idle and stay idle until the placement service moves something
to them. While any one core of the node is idle and behind the epoch recorded
when a chunk's map count reached zero, `memory_give`, the destruction of a block
and a retype of a page-class change are `busy` — not for a moment, but for as
long as that core stays idle, which is unbounded:

```
C. an unmap whose core set holds an idle core
   state reached: kind=unmapping, epoch of the idle core=3,
                  epoch recorded when the count reached 0=4
   G5 verdict: refused, and refused again after every retry
   blocked by: an idle core counting as past every flush epoch
```

The check is the two premises (no interrupt for an idle core; the epoch moves
only on an acknowledgement) and the property "the freeing of memory is refused
only while some core is about to acknowledge". It fails on exactly one mutation:
the requester clearing the idle core's bit, the core's epoch being counted as
past everything while it owes nothing.

That last point is the substance: an idle core that loaded the kernel's own root
(line 328) holds *no* translation of any address space of the node, so there is
nothing for it to invalidate and no epoch for it to reach. The text should say
so, and the requester should then be able to treat it as past the epoch.

**Smallest fix.** Add to line 328: "An idle core is not in the set the requester
waits for and not in the set G5 waits for either: it has loaded the kernel's own
root before going idle, so it holds no translation of any address space of the
node, its part records nothing it owes, and G5 counts a core that is idle as
past every flush epoch. A core that is not idle but does not acknowledge within
`CORE_ANSWER_NS` remains a failure of the node." And in line 972 or G12, after
"every core of the node past a flush epoch": "(a core that is idle is past
every epoch, [TLB](#tlb-one-core-and-several))".

## 2. A thread marked *leaving its core* is still runnable

Line 647: "a call that must stop such a thread (suspend it, destroy it, revoke
its task, move its context to another core) marks it **leaving its core** and
sends *b* the kernel's leave interrupt; at that interrupt *b* saves the thread's
registers into the thread object, stops running it and clears the mark. While the
mark is set, no core runs the thread and no call reads or writes its registers.
… `sched_configure` that moves a context waits for nothing, and its holder runs
on the new core once the mark is clear."

Line 475: "A thread is **runnable** when it is not suspended and does not wait."

Line 476: "A context is **eligible** when it is configured, not dying, and its
holder is runnable."

Line 533: "1. the holder of the first context of the ready queue (the nearest
deadline …)".

The mark is in none of these. A marked thread is not suspended, so it is
runnable; its context is eligible; and once `sched_configure` has moved the
context (line 626: "the placement service moves it to another core of the node
with `sched_configure`"), the new core's choice takes it. The call "waits for
nothing", so there is no ordering that keeps the new core off until the mark
clears; the old core is still running the thread until it takes the leave
interrupt, which it takes "at the latest at the end of its current kernel event"
(line 644). Two cores therefore run one thread for up to one kernel event: one
register set, one stack, and after a few hundred cycles neither is meaningful.

```
B. one thread on two cores after sched_configure moves it
   trace: ['sched_configure to core 2', 'choice on core 2 runs the thread']
   blocked by: adding the mark to the definition of *runnable*
```

The check fails on exactly that mutation. It also makes line 647's own promise
("its holder runs on the new core once the mark is clear") follow from the
definition instead of resting on a separate sentence.

The same hole is open on the destroy path (a thread whose place on a core is
being undone is runnable until the mark clears) and on `task_revoke`, whose
first call "waits until every thread of the task that ran on another core has
left it, so the task is stopped when the call returns": a thread of the task
that is not on another core keeps running, which is intended, but a thread
marked *leaving* its core is counted as having left by a reader of the state
and as runnable by the scheduler.

**Smallest fix.** Line 475 becomes: "A thread is **runnable** when it is not
suspended, does not wait, and is not marked *leaving its core*."

## 3. The record of an unmap is full and not full, and two of the three checks do not refuse it

Line 250: "**A frame capability holds one record, empty or full.** A full record
is either a **mapping** or a **message page binding**."

Line 1782: "Word 2 is the record: bits 0-1 its kind (0 empty, 1 mapping, 2
message page binding, 3 unmapping: a mapping whose entries are cleared and whose
invalidation on other cores of the node is in flight …)".

So a record of kind 3 is "a mapping" in one place and neither a mapping nor a
binding in the other: whether it is *full* is decided by which sentence the
implementer read. Line 327 states what the contract wants from a full record of
that kind: "the frame capability's record is **unmapping** …: a removal that
reaches it returns `again`, and `aspace_unmap` and `aspace_protect` on it are
`busy`."

The checks do not carry that out:

- `aspace_unmap`, line 273: "Succeeds without effect if the record is empty.
  `busy` if the record names an `iospace` or a thread." A record of kind 3 names
  an aspace and holds a range, so the call proceeds on it a second time.
- `aspace_map`, line 287: "the frame capability's record is full (`busy`, even
  if it names this aspace)". Under line 250's reading it is not full, and the
  mapping goes into a range whose invalidation is still in flight.
- `aspace_protect`, line 297, is the only one that names the state: "`busy` if
  the record is empty, a binding, unmapping, a partial mapping …".

Both readings hurt, differently:

```
A. unmapping record, then aspace_map, then the acknowledgement
   trace: ['aspace_unmap', 'aspace_map', 'ack from core 1']
   end state: map count 1, no leaf in any table, no record
   blocked by: the record of kind 3 made full for `aspace_map`
```

Step by step, on core *a*: `aspace_unmap` clears the entries, decrements the
chunk's map count to 0, sets the record of kind 3 and waits for core *b*. Core
*c* calls `aspace_map` with the same capability at another address of the same
chunk; nothing refuses it, so it writes a leaf, the map count becomes 1 and the
record becomes a mapping again. Core *b* acknowledges, and line 295 applies:
"The record is emptied, and the capability leaves the aspace's list, once every
core has invalidated." The leaf stays, no record names it, and the map count
never returns to 0. Every later walk of records misses that translation, and
G14 (line 981) finds a chunk "whose map count equals the number of entries of
its tables that point into it" false, which is "a violation of containment: the
machine stops with a stop record". The other reading is the same hole from the
other side: a second `aspace_unmap` on the record of kind 3 passes 273's checks,
decrements the map count again (below zero, or not at all, depending on how the
effect is read) and starts a second round of acknowledgements.

**Smallest fix.** Replace line 250's second sentence with: "A record is empty,
a mapping, a message page binding or **unmapping** — a mapping whose entries
are cleared and whose invalidation on other cores of the node is in flight. An
*unmapping* record counts as full: `aspace_map` and `aspace_unmap` are `busy` on
it, and a removal that reaches it returns `again`." Then line 273 reads
"`busy` if the record names an `iospace` or a thread, or is unmapping".

## 4. Variant L2 has no lock word for an `untyped` and none for an interrupt entry

Line 630 promises: "**Locking: two variants with one layout (open point).** …
Both variants use the same object sizes and fields, fixed now, so the choice
changes no layout."

Line 635: "**L2, a lock per object** | A lock word in each object that a call
changes (endpoint, notify, reply, timer, thread, `sched`, task, aspace, iospace,
untyped) …".

Line 637 reserves them: "The lock words are reserved in every object now, inside
the sizes of [Object sizes](#object-sizes) (64 bytes for an endpoint, a notify, a
reply and a timer; 256 for a `sched` and a task; the 1 KB fixed part of a
thread; the header page of an aspace)".

Two of the named objects have nowhere to put one.

**An untyped has no body.** Line 1783: "`untyped`: in word 0, bits 25-30 the
log2 of its size, bit 31 device memory, bit 32 it has a clean mark, bit 33 it is
a block …, bit 34 the block is a device entry; the place of a block is its
first byte, in word 1 …. Word 2 is the watermark and word 3 the clean mark, as
offsets from the first byte." Everything about an untyped is in its 64-byte
capability slot, whose eight words are accounted for by line 1770 onwards (word
0 state, kind, rights, depth and the kind's bits; word 1 the object; words 2-3
the kind's fields; words 4-5 the derivation list; words 6-7 the space's list of
records). `Object sizes` (line 1737) has no row for an `untyped`: the sizes are
"the bytes `untyped_retype` takes on this node" (line 1905), so an untyped owns
no bytes of its own at all. Under L2, two `untyped_retype`s on one untyped
capability from two cores read the same watermark, take the same bytes and write
the same watermark: two kernel objects at one address, the second overwriting
the first's memory. That is not a lost statistic; it is two tasks sharing a page
table page.

**An interrupt entry is written by every core of the node.** Line 622: "Each is
written only by its core, except the interrupt table, which the node's kernel
writes for any of its cores, since a claim is a call." Line 723: "Each physical
core has one table, which belongs to the node its core word names". Line 1751:
"`irq` | An entry of a physical core's interrupt table, 64 bytes per claimable
vector (12 KB per core on x86-64), kept at machine start-up". An entry changes
`armed`, `fired` and `pending` at an arrival, at `irq_bind`, at `irq_ack` and in
the removal steps of a notify, from whatever core of the node happens to call.
L2's list of locked objects does not name it, and 637's list of sizes does not
name it either. A lost `irq_ack` update either loses an interrupt for ever (the
notify is never signalled again and a device stops) or signals one twice (a
driver that acks once per signal runs two iterations over one ring).

Under L1 both are sound, because the node lock serialises whole events. That is
why the fault is L2's, and why it is a fault of the sentence "one layout" rather
than of the design.

**Smallest fix.** Add after line 637: "Two objects have no lock word in variant
L2, and take the gate lock instead: the state of an `untyped` (its watermark and
its clean mark, which live in the capability's slot) and the entry of an
interrupt table (which any of the node's cores writes). Every call that changes
either takes the gate lock, and `untyped_retype`, `irq_bind`, `irq_ack` and an
arrival count it in *k*." The dearer alternative, a one-page body for an
untyped and a reserved word in each 64-byte interrupt entry, is what a model
would need to avoid a gate call on every arrival; I recommend the first and note
that it must be settled before the layout is frozen, since it decides an object's
shape.

## 5. The ARM64 broadcast reaches one shareability domain, not the node

Line 323 is the promise: "When a call returns (or a removal step returns
`again`), no thread on any core can use a translation that the call removed or
reduced."

Line 326 is the means: "**ARM64:** a broadcast invalidation inside the call
(`TLBI VAE1IS` for a range, `TLBI ASIDE1IS` for a tag …) completed by `DSB ISH`.
'The invalidation applies to all PEs in the same Inner Shareable shareability
domain as the PE that executes this System instruction' … and a TLBI effect is
complete once a DSB follows it. No interrupt and no wait. A broadcast also
removes entries of the same ASID on cores of other nodes, which use their own
tables of tags: that costs them a refill, never safety, since an invalidation
never adds a translation."

Two conditions carry the promise, and the contract checks neither.

1. **The domain.** A node's cores must lie in one Inner Shareable domain for a
   broadcast to reach all of them. Nothing checks it: `node_start`'s plain
   arguments (line 1290) are "the mode is 0 or 1; the kernel image is 0 or 1; …
   the window is below 1024 and the mask is not 0", and its state (line 1291)
   refuses a core "not free, or … unusable, or if the cores named differ in a
   state feature or a vector length". The machine start-up refuses a bad layout
   of features, cores and memory; no value of the machine is a domain. A node of
   two cores in two domains — two sockets, or two partitions of one SoC — passes
   every check and then invalidates on one core only, "no interrupt and no
   wait", while the promise of line 323 says otherwise. The second core keeps a
   writable translation to a frame whose memory the node has given back to an
   untyped and another node has since taken.
2. **`CnP`.** G7 (line 974) gives "one table per node" of tags and line 326
   uses `TLBI ASIDE1IS`, a broadcast matched by `(VMID, ASID)`. The second
   round's verification closed this against Arm DDI 0487
   ([`reviews/2026-11-16-verify-multicore-challenge-opus-by-hydrogen.md`](2026-11-16-verify-multicore-challenge-opus-by-hydrogen.md),
   C5): per-node ASIDs "work only with `CnP = 0` and local-only `TLBI` (`ASIDE1`
   / `VALE1`) or explicit IPI shootdowns, never `TLBI ASIDE1IS`", because with
   `TTBRn_EL1.CnP = 1` the architecture requires identical `(VMID, ASID)` →
   page-table associations across the domain or declares the behaviour
   `CONSTRAINED UNPREDICTABLE`. The words `CnP` and `TTCNP` appear nowhere in
   the contract or in `kernel.md`, so nothing here closes C5, and line 326's
   reassurance ("A broadcast also removes entries of the same ASID on cores of
   other nodes … never safety") is exactly the sentence `CnP = 1` makes false:
   with one table of tags per node, another node's core cannot hold a conflicting
   association.

**Smallest fix.** In line 326: "The cores of a node are in one Inner Shareable
shareability domain — the machine start-up records each core's domain as a value
of the machine and `node_start` refuses a set that differs in it — and on ARM64
the kernel clears `TTBRn_EL1.CnP` for the per-node tag tables, so a broadcast
matched by `(VMID, ASID)` is a hit on another node's tables, that is a refill,
never an ambiguous entry; a node whose cores cannot share a domain takes the
interrupt path of x86-64."

## 6. The longest hold *H* is not bounded, and (*N* − 1) × *H* passes the node's own failure threshold at eleven cores

Line 639: "*H* the longest hold of the node lock (L1) and *h* the longest hold of
an object lock (L2), each on the slowest kind of core in the node". Line 641:
"with L1, a call's bound is its one-core bound plus (*N* − 1) × *H*". Line 645:
"**a lock wait, or an answer awaited from another core of the node, longer than
`CORE_ANSWER_NS`** (10 ms, provisional …) is a failure of the node (below). So
every wait of a kernel event is bounded by construction, whatever the hardware
does."

Line 644 excludes one kind of wait from a hold: "**no lock is held across a wait
for another core.**" It says nothing about a wait for hardware, and the kernel
has one, inside a call, by design:

Line 365: "**Invalidations of the IOMMU wait for the hardware (design choice).**
… The kernel waits for the confirmation. A unit that does not confirm within 1 ms
(provisional) is a hardware fault of the unit, not of a node: the holder of its
role keeps the role and tries again, **every change on the unit waits**, and the
devices behind it keep the translations they have …. The invalidations of one
call, or of one removal step, are grouped into one wait before the call returns."

So a call that changes an `iospace` map waits, inside its own kernel event,
before it returns; under L1 that event holds the node lock, and with a unit that
does not confirm the wait has no bound at all. The audit of G14 does the same
without any hardware: line 981, "It walks its own tables, bounded by its own
memory", on a node that may hold 64 GB, whose class table alone is "one byte per
page of ordinary memory in the living part" (line 969) — 16 million entries to
walk at 100 ns each is seconds, in one event, under one lock.

Then the arithmetic of line 641 with a hold of 1 ms:

```
   N= 1: (N-1)*H =   0.00 ms
   N= 8: (N-1)*H =   7.00 ms
   N=11: (N-1)*H =  10.00 ms  PASSES CORE_ANSWER_NS
   N=16: (N-1)*H =  15.00 ms  PASSES CORE_ANSWER_NS
   N=64: (N-1)*H =  63.00 ms  PASSES CORE_ANSWER_NS
E. first N at which a lock wait passes the node's own failure threshold: 11 (H = 1 ms)
```

`CORES_PER_KERNEL_MAX` is 64 (line 1347: "Cores of one node at most: the bitmaps
of a node's cores are 64 bits"), and nothing refuses a node whose bound exceeds
its own threshold. The crossing is worse at the low end of the range the text
allows the threshold to take: `CORE_ANSWER_RANGE_NS = (1_000_000,
100_000_000)` (line 1613), so an image that sets 1 ms makes a node of three cores
fail on a single hold of 1 ms. So the contract admits a node on which routine
contention — a mapping change queued behind a unit invalidation, or a map behind
one step of the audit — makes a healthy node accuse itself, and line 329 then
kills every process in the node.

There is a second, smaller gap in the same paragraph: line 644 gives a waiting
call at most *N* × *H* (L1) "plus the delivery of one interrupt", while line 641
gives a call "its one-core bound plus (*N* − 1) × *H*" and counts no wait at all.
A call that both takes the lock and waits — `thread_suspend`, the first call of
`task_revoke`, `aspace_unmap` and `aspace_protect` on x86-64 and RISC-V (line
644) — is bounded by neither sentence.

**Smallest fix.** In line 644, add: "No lock is held across a wait for hardware
either: a call or a removal step that waits for a unit's confirmation, and every
step of the audit of G14, is split into states of its thread, so that *H* is the
work of one event with no wait in it, and no node the image accepts can make
(*N* − 1) × *H* pass `CORE_ANSWER_NS`." And in line 641: "its one-core bound,
plus (*N* − 1) × *H* if it holds a lock, plus the wait of line 644 if it
waits" — a call does not pay both for nothing.

## 7. *N* = 1 pays for two protocols that the "leaves out" list does not cover

Line 620: "**A kernel built for *N* = 1 keeps every field of the layout and
leaves out the protocols** (no lock instruction, a plain read of a slot and a
plain OR on a notify word, the state *leaving its core* never reached), so that
a node of one core pays nothing on its common path for the cores it does not
have (the principle of D-117: a guarantee is paid at a failure or a rare
event)."

Line 653 repeats it: "**What it costs on the common path.** A node of one core:
nothing (above)."

Two protocols of the same subsection are outside both lists and cost on a
one-core node.

1. **The idle transition.** Line 328: "Before it goes idle it loads the kernel's
   own root, so that it walks no table of the node's address spaces while idle,
   and writes an idle mark in its part of the node block …. The core writes its
   idle mark and then reads its requests, and a requester writes its request and
   then reads the mark, each by a compare-and-swap that orders the two." With
   *N* = 1 there is no other core to free a page under it, and line 324 already
   gives the whole rule for one core: "The kernel invalidates the translations
   of the range on its own core before it returns". So the load of the root and
   the two compare-and-swaps buy nothing on one core, and they are paid on the
   most frequent event of an idle machine — which is the opposite of "paid at a
   failure or a rare event".
2. **The tag's core set.** Line 325: "The header of an aspace holds the set of
   the node's cores that have loaded its tag since it was last invalidated on
   them (a bitmap over the node's core positions, `CORES_PER_KERNEL_MAX` bits)."
   On one core the bit is always bit 0 and is always already set after the first
   load, so the write is a store per switch of address space that no rule can
   use; nothing says the field is left out at *N* = 1 or written only when it
   changes.

The rest of 620's list is right: the cspace sequence word becomes a plain read,
the notify's word a plain OR, and the lock is left out (line 979: "a node of one
core, nothing (its image leaves the lock out)"). Those are items 7, 8 and 11 of
the hot-path list the earlier verification drew
([`reviews/2026-11-16-verify-kernel-shape-round2-by-deepseek.md`](2026-11-16-verify-kernel-shape-round2-by-deepseek.md),
§4.3, whose other two items are memory, not path). The two paths above are not
on it, and they are on the hot path of an idle machine.

**Smallest fix.** Extend line 620's parenthesis to: "(no lock instruction, a
plain read of a slot and a plain OR on a notify word, the state *leaving its
core* never reached, no idle mark and no load of the kernel's own root before
going idle, and no core set in a tag's header — the invalidation before the call
returns is the whole rule on one core)".

## 8. A resume, or a second suspend, answers `ok` in the middle of a suspend's wait

Line 180: "`thread_resume`, `thread_suspend` … Both succeed when the thread is
already in the state asked for. … `thread_suspend` on a thread that is running
on another core of its node returns only once that core has left it, so that a
suspended thread executes nothing".

Line 647: "`thread_suspend` waits for the mark to clear".

The flag is set at the start of the suspend, and the wait is for the mark, with
the caller "holding no lock" (line 644). Three things follow:

```
D. thread_suspend returns ok while the thread runs
   trace: ['thread_suspend on core 1 (sets the flag, marks, waits)',
           'thread_resume on core 2 succeeds, clears the flag',
           "leave interrupt on core 2 ends the suspend's wait",
           'the thread runs']
   blocked by: thread_resume being busy on a marked thread
```

1. A `thread_resume` on another core clears the flag, the mark clears when the
   old core leaves, and `thread_suspend` returns `ok` for a thread that is
   runnable and about to run. A debugger that believes the promise writes the
   registers and memory of a live thread.
2. A second `thread_suspend` — from a third core, or from the same one — finds
   the flag already set and returns `ok` at once, on a thread that is still
   executing.
3. The register calls do not know the mark either. Line 440: "`thread_read_regs`
   … State: `busy` if the thread is not suspended (so a thread never reads its
   own registers). A waiting thread can be read. The block holds the values the
   thread will see when it resumes". A marked thread is suspended and passes that
   check, so the call reads registers that the old core has not saved yet, or is
   changing now — which is what 647 forbids in words: "no call reads or writes
   its registers". `thread_configure` (line 179) is the same: it is `busy` only
   if the thread "is not suspended and does not wait".

**Smallest fix.** In line 180: "`thread_resume` is `busy` on a thread marked
*leaving its core*, and a `thread_suspend` that finds another in progress waits
for the same mark and returns when it is clear." In line 440: "`busy` if the
thread is marked *leaving its core* as well", and the same clause in line 179's
`thread_configure`.

## 9. The audit of G14 and of R4 takes no lock under L2

Line 981: "**G14. Audit.** The audit of a recovery (R4) also checks, for each
chunk the auditing node holds, that its map count equals the number of entries of
its tables that point into it. It walks its own tables, bounded by its own
memory. A mismatch is a violation of containment: the machine stops with a stop
record."

Line 1224: "**R4. Audit.** It checks that every ownership word covered by its own
live blocks still reads taken by it with its generation, and that its map counts
match its tables … A mismatch is a violation of containment: the machine stops
with a stop record."

Recovery is not a call: line 1249, "Recovery is work in the kernel that is not a
call: the driver's fence, every node's steps R0 to R5, step R6, the rebuild of a
unit role", and it runs in the recovery reserve, in steps. Under variant L1 each
step is one kernel event under the node lock, so the comparison is atomic against
everything else in the node. Under variant L2 nothing is named: line 635 locks
"each object that a call changes", and an audit changes nothing; line 979's gate
lock covers "every write of the living part by the node and every write of the
node's tables", not reads. So the two halves of one comparison run on a moving
target: a concurrent `aspace_map` on another core raises a chunk's map count and
writes its leaf between the half that reads the count and the half that reads the
leaves, or vice versa, and the mismatch is "a violation of containment" — the
machine stops with a stop record, during a recovery, on a healthy node, from
ordinary use. R4's ownership words have the same hole against a concurrent
`memory_give` or the destruction of a block on another core.

The variant is chosen after the measures (line 630), so this is not a corner of
an unlikely configuration: it is a rule that changes correctness when the open
point is settled the other way.

**Smallest fix.** Add to G14: "Under variant L2 the audit takes the gate lock for
each step, and a step compares the counts and the leaves of the chunks it visits
under it, so that no change of another core falls between a map count and the
leaves it counts; R4 reads the ownership words under the same lock." The
alternative, an audit against a copy of the tables, is the copy rule 3 forbids.

## 10. The gate lock orders the gate calls; nothing orders a gate call with an object call

Line 979: "**What serialises its writes:** one **gate lock** per node, a queue
lock in the node block, held for one gate call and never across a wait for
another core; every write of the living part by the node and every write of the
node's tables is made under it (… with variant L2 it is what orders gate calls
from different cores)."

Line 635: "a call takes its locks in one order fixed by kind, at most *k* per
call (*k* fixed by the call's rules)". Line 642: "with L2, a call that takes *k*
locks is bounded by its one-core bound plus *k* × (*N* − 1) × *h*".

The gate lock is a lock of the node block, not a kind; so the order does not
place it, and *k* does not count it, although it is the one lock that a mapping
call, a grant, a role word and a core word all take, and therefore the most
contended. Concretely: `aspace_map` takes the aspace's lock (a kind) and then,
to write leaves, the gate lock; `node_send` takes the node's mailbox (a kind)
and then writes grant entries in the living part. If any path takes the gate
lock first and then a kind's lock — the audit of G14 updating a counter, a gate
call that wakes a thread on the scheduler's queues, a removal step that lowers a
grant's count and then takes the use table's — the two paths deadlock, both
inside a kernel event, and line 645 then declares the node failed and stops it.

**Smallest fix.** In line 979, after "held for one gate call": "The gate lock is
the last of every order: a call takes it after all the object locks of its
order and gives it up before them, a gate call never acts on an object whose
lock its caller holds, and *k* of [Bounds](#a-node-of-several-cores) counts it."

## 11. `grant_signal` needs a right that `node_send` never requires

Line 917: "`grant_signal` | frame | | `send` on the remote frame capability."

Line 866: "**A remote frame capability** … its rights, depth and by-kind fields
are those of the anchor".

Line 867: "*X*'s gate writes one grant entry per frame before the message leaves:
the anchor is a new child of the frame capability in *X*'s derivation list, with
the rights the item asks (a subset of the source's) and badge 0".

Line 921 gives the checks of `node_send`: "the capability list, at most 4 frame
capabilities of the caller's own node, each *derive* with its rights".

So the right to ring a doorbell is decided by a rights word the sender chooses,
and nothing in `node_send`'s checks or in the rules of grants requires that word
to hold `send`. The ordinary case is a read-only ring: line 937, "Each side maps
the other's ring read-only" — the item asks `read`, the anchor gets `read`, and
`grant_signal` on it (line 917, and line 868: "`grant_signal` rings the grant's
doorbell") is `denied` for ever. The failure is silent on the sender's side:
`node_send` succeeds, the message is delivered to the mailbox agent, and the
service's doorbell is unreachable, so the remote call path of D-128 — request in
a ring, `grant_signal` on the peer's ring, wait on one's own notify (line 938) —
stops at its first step with no diagnosis.

**Smallest fix.** In line 921, after "each *derive* with its rights": "and, when
the call names a doorbell, `send` as well, since `grant_signal` needs it and a
right never grows". The alternative, in line 867: "an anchor whose grant names a
doorbell also gets `send`", keeps the right out of the sender's hands but hides
it from the message; I recommend the first.

## 12. Rule 7 is withdrawn and stands

Line 935: "Rule 7 is withdrawn (D-128). A thread on node *X* can no longer call a
service on node *Y* …".

Line 17, in the list of rules: "7. **Objects belong to one node, and only one-shot
operations cross between nodes (D-128).** A **node** is one kernel: its block of
state and the set of physical cores it runs on, fixed when the node starts …".

Three places cite it as in force: line 200, the `call` row, "The endpoint is an
endpoint of the caller's node: a call never crosses nodes (rule 7)"; line 752,
"The tables of a node's cores, their vectors and the node's `irq_control` belong
to that node (rule 7)"; line 1702, "a call never crosses nodes (rule 7)".

A reader finishing the contract meets a numbered rule 7 and a sentence saying
rule 7 is withdrawn. The sentence means the *former* rule 7 (the one that let a
call, a wait and a capability cross between nodes), and nowhere says so.

**Smallest fix.** Line 935: "**Rule 7 in its old form is replaced (D-128):** a
thread on node *X* can no longer call a service on node *Y*, wait on *Y*'s
objects, or receive from *Y* a capability other than a frame; what stands in its
place is rule 7 of [Rules](#rules)".

## 13. The lists of values disagree with the text

Three items, all of them in the two lists that tell `abi/` and the model what to
hold.

1. **`StartMachine`'s layout version is 0 and 1 in one cell.** Line 1922: "the
   capacity of the device table, the number of roles, `GRANTS`, the layout
   version (0) (u32 each); … and the layout version is 1 since D-129". The same
   cell, two values. The `abi/` list is unambiguous (line 1627: "`StartMachine`
   80 bytes with the offsets of the core words, park requests and start
   requests, layout version 1"), so a reader who follows 1922 writes 0 and the
   machine start-up refuses its own start-up page.
2. **The crash record is one per physical core and `abi/` still calls it the
   node's.** Line 1439: "**The core record** is at offset 64 of the core's debug
   area (4,032 bytes)". Line 1614 changes the headers to version 2, "the header
   holding a core number and the node slot it last ran", and `DEBUG_AREA_BYTES`
   "is per physical core". `abi/src/debug.rs` at `8c2adef` still defines
   `NODE_CRASH_RECORD_BYTES` and `NodeCrashRecord`, documented as the node's
   record. The `abi/` list renames `CORE_WATCH_SLOTS`, `CORE_START_*`,
   `CORE_IMAGE_*`, `CORE_STOP_*` and `CORE_STATUS_WORDS` (line 1615) and adds
   `CrashReason::CoreSilent = 9` (line 1613) — a reason whose text is "another
   core of the node did not answer" — but never says the record became the
   core's.
3. **No lock word has an offset in the `abi/` list.** The text reserves lock
   words in `Object sizes` (line 1744: "64 bytes, a lock word included"; 1745,
   1746, 1747 "the state *leaving its core* and a lock word"; 1748: "eight
   range-lock words and a lock word" in an aspace's header), and the `abi/` list
   adds only `CSPACE_DIRECTORY_BYTES = 16` (line 1614). No offset of any of those
   words is published, so two independent implementations of the layout cannot
   agree, and `abi/` cannot check them. Two objects have no lock word at all
   (finding 4), and the `irq` entry — 64 bytes, line 1751 — has none named.

**Smallest fix.** Delete "(0)" in line 1922. Add to the `abi/` list, under
"Renamed": "`NodeCrashRecord` → `CoreCrashRecord`, `NODE_CRASH_RECORD_BYTES` →
`CORE_CRASH_RECORD_BYTES`: one record per physical core, at offset 64 of its
debug area, reason 9 *another core of the node did not answer*". Add under
"Added": "the offset of the lock word in an `endpoint`, a `notify`, a `reply`, a
`timer`, a `sched`, a `task` and the fixed part of a `thread`, the offsets of the
eight range locks and the lock in an aspace's header, and the lock of each core's
part of the node block".

## 14. "It is the only numbering of cores in this contract"

Line 92: "**core number** | The position of a physical core in the core list of
the start-up page (entry `Cores`). It is the only numbering of cores in this
contract".

Line 622: "Each core of the node has its own part of the node block, at the
core's **position** *j* in the node (0 to *N* − 1, in the order of core numbers)".

Line 485, a `sched`'s parameter: "cores | The cores where the context may be
placed, by core number ([Values of the machine](#values-of-the-machine)): a
window of 64 cores and a mask (`sched_set_cores`)". Line 506:
"`sched_set_cores` | sched, node, window, mask … The set is the cores whose core
number is 64 × window + *i*, for each bit *i* set in the mask". Line 1290:
`node_start`'s "the window is below 1024 and the mask is not 0".

Line 1907 mixes the two in one clause: "`StartCore` records (32 bytes), one per
physical core, sorted by hardware identifier, so a core's position is its core
number" — true of the core list of the start-up page, false of the position in a
node, where 0 is the node's first core and not the machine's.

So there are two numberings, and the text uses both: machine core numbers for
placement and for a node's membership, positions for every new rule of D-129
(the partition of the node block, the tag bitmaps, the per-core lock words, the
adaptation of a core's parts to *N*). The sentence at 92 therefore misleads in
exactly the place a reader looks up what "core" means, and a reader who thinks a
cores set names positions writes a `sched_set_cores` that silently selects the
wrong cores.

**Smallest fix.** Line 92: "It is the only numbering of cores of the machine; a
node also numbers its own cores by their position in the node, 0 to *N* − 1
([A node of several cores](#a-node-of-several-cores))."

## 15. `no_memory` for a full grant table, and `send` on a frame outside the table of rights

Line 921: "Then the state, in order: `busy` if `SENDS_PER_PEER` sends of the
caller's node are in flight to it, or if the message does not fit in the user
ring; `no_memory` if the caller's grant table has fewer free entries than the
frames listed."

Line 1729: "| `no_memory` | The supplied untyped memory is exhausted; supply more
and repeat |". Line 1731: "| `busy` | The object is in a state that forbids the
call |".

The grant table is memory the node keeps, fixed at machine start-up ("`GRANTS`
(4,096) per node", line 2119), and the caller supplies nothing and repeats
nothing. A client that reads `no_memory` will try to supply memory it has no way
to supply, and a supervisor cannot tell "you are granting frames faster than they
are released" from "your untyped is empty" — the two need different responses.
The neighbouring checks in the same sentence already use `busy` for exactly this
kind of state.

Line 1625, in the `abi/` list: "`Rights`: no new bit; `send` on a frame is the
right to ring its grant's doorbell." The contract's own table of rights (lines
1708 to 1716) says of `send`: "Call or send on an endpoint; signal a
notification" — and nothing more, so a reader of the rights table alone cannot
know that a frame carries a `send` at all, and the one place that does say it is
a list of changes to another repository.

**Smallest fix.** In line 921, "`busy` if the caller's grant table has fewer
free entries than the frames listed". In the table of rights, the `send` row
becomes "Call or send on an endpoint; signal a notification; ring the doorbell of
a grant through its remote frame capability."

## Appendix A: the check

`/tmp/review8/check.py` (Python 3, no dependencies, run with
`timeout 60 python3 -B check.py`). Each scenario is an explicit transition
system whose moves are the rules quoted above, plus a property the contract
states; the script prints the shortest trace to a state the contract forbids, and
the mutation that removes the trace. A check whose property could not fail would
prove nothing, so each is listed with the clause that makes it fail:

| Scenario | Finding | Property | The mutation that removes the trace |
|---|---|---|---|
| A | 3 | no map count above 0 with no record and no leaf | the record of kind 3 counting as full for `aspace_map` |
| B | 2 | at most one core runs a thread | the mark in the definition of *runnable* |
| C | 1 | freeing is refused only while some core is about to acknowledge | an idle core past every flush epoch |
| D | 8 | a thread whose suspension returned `ok` does not run | `thread_resume` `busy` on a marked thread |
| E | 6 | (*N* − 1) × *H* below `CORE_ANSWER_NS` for every *N* the image accepts | a hold with no wait for hardware in it |

## Appendix B: checked and found consistent

So as not to leave them unsaid, these were checked and hold.

- **The call table is 64 calls and every number in the `abi/` list is right.**
  The `Call` enum of `abi/src/lib.rs` at `8c2adef` has 64 variants without
  discriminants; counted by position, the numbers the list names are exactly
  `0 CapDerive`, `1 CapMove`, `3 CapRevoke`, `7 ASpaceMap`, `8 ASpaceUnmap`,
  `9 ASpaceProtect`, `10 Call`, `13 Send`, `18 ThreadConfigure`,
  `22 ThreadSuspend`, `24 SchedConfigure`, `27 SchedSetCores`, `38 TaskRevoke`,
  `40 CoreStart`, `41 CoreStop`, `42 CoreStatus`, `46 IrqClaim`, `47 SchedRead`,
  `51 CoreIdle`, `52 CoreWatch`, `53 CorePlace`, `57 ThreadMove`, `58 SchedCount`,
  `63 CorePerf`. `CorePlace` (53) and `ThreadMove` (57) are the two removed calls
  and their numbers do become `NodeSend` and `GrantSignal` (lines 1602 and 1603),
  every other call keeps its number, `TaskExempt` stays at 35, and the argument
  lists of the renamed calls match the call reference.
- **The old shape is gone from the text.** No `thread_move`, `core_place`, proxy,
  remote capability of a kind other than a frame, or parking of a core survives
  as a rule: line 626 removes the move of a thread between nodes, 935 to 940
  replace the remote call with rings and a doorbell, and 1616 and 1635 remove
  `PROXIES_PER_PEER`, `PROXY_BYTES`, the proxy code and `moves.rs`. The park
  request and the start request are per physical core (line 1621), as D-129
  says.
- **Every "per core" that remains is right.** Lines 723, 1294, 1349, 1374, 1751,
  1756 and 1631 speak of a physical core's table, start sequence, wake-up, debug
  area, entry count or part of the node block; the node-wide things — the gate,
  the reclaim proof, the node lock — are spoken of as the node's.
- **The sizes of the new records follow from their fields.** `StartMachine` 80
  bytes (line 1922, and line 1627 agrees), `StartNode` 24 (lines 1627 and 1916),
  `StartCore` 32 (line 1907, one per physical core, sorted by hardware
  identifier), the debug area 69,632 = 17 × 4,096 with a 64-byte header and a
  4,032 byte record, the kernel ring 256 × 64 and the user ring 768 × 64, and the
  crash record's offsets 64, 72, 80, 88, 96 + 32 words, 352, 480, 2,528, 3,552
  summing to 4,032. The one stale size is the D-110 list's own, at line 1575
  ("a `StartCore` of 24 bytes"), which describes what the table replaces.
- **The remapping handles are consistent.** 340 × 192 + 191 = 65,471 < 65,536 <
  341 × 192 + 191 = 65,663, so "a core of number 341 or more cannot be claimed
  on" follows from "at most 65,536 entries" and the 16-bit field. Only the name
  `IRQ_MAX_CORES_REMAPPED = 341` reads as an inclusive maximum and is one too
  high; the sentence is right.
- **The ring numbers hold**: two 64-entry rings of 64-byte entries are 8 KB per
  ordered pair, the answer reserve of 16 + 8 entries fits in 64, and
  `RING_MESSAGE_ENTRIES_MAX = 11` leaves the reserve intact for the largest
  `Send`.
- **`MAP_COUNT_MAX` and G4 agree**: bits 0-31 of the gate word (line 971) hold
  the count and line 290 refuses a mapping that would pass it.
- **The closures the second round claims are in the text**: the park request is
  raised before the mark, R6 frees a core word only after a confirmation and
  `SETTLE_NS`, and the generation is written by the compare-and-swap that checks
  the member word. The one finding of that round that the text does not close is
  the ARMv8 ASID question (C5), which is finding 5 here.
