# Contract review 11 (Mistral): what pass 18 wrote into the kernel contract

Review of pass 18, commit `74011e1`, against the whole of
[architecture/kernel-interface.md](../architecture/kernel-interface.md) (2,285 lines,
read whole) and decisions D-128 to D-135 in [decisions/README.md](../decisions/README.md).
Reviewed 17 November 2026. I changed nothing in any repository; this file is my only
output. All line numbers are of `architecture/kernel-interface.md` at `74011e1`.
External specifications were checked at their sources on 17 November 2026 (editions
named in the contract's editions block, line 80); nothing below is claimed from memory
unless marked so.

## Findings

### 1. Wrong Arm citation: "B2.3, 'TLBI Effects, Completed TLBI Effects and Invalidation Scopes'" does not exist in DDI 0487 M.d — low

`kernel-interface.md:328`:

> "and a TLBI effect is complete once a DSB follows it (Arm DDI 0487, B2.3, \"TLBI Effects, Completed TLBI Effects and Invalidation Scopes\")."

In the edition the contract itself names (line 80: "Arm DDI 0487, version M.d (30
September 2026)", confirmed current: the release history of the downloaded M.d PDF lists
30/Sep/2026 as the top entry), section B2.3 is "Ordering requirements defined by the
formal concurrency model" (with subsections B2.3.1 "Basic definitions" and following).
No section titled "TLBI Effects, Completed TLBI Effects and Invalidation Scopes" exists
anywhere in M.d's table of contents (the full TOC of the M.d issue was searched: zero
matches for "TLBI Effects", "Completed TLBI", "Invalidation scope"). The rules the
sentence needs are D8.17.8 "Ordering and completion of TLB maintenance instructions"
(a TLBI is complete once a DSB follows it) and D8.17.7 "Broadcast TLB maintenance" (the
Inner Shareable scope). Decision D-135 item (11) itself names "the Arm ARM's TLB rules
D8.17 and D8.17.1", so the contract's B2.3-plus-title also contradicts the decision it
cites. The same sentence cites C5.5.60 for both instructions: in M.d, C5.5.60 is
"TLBI VAE1IS … TLB Invalidate by VA, EL1, Inner Shareable" but TLBI ASIDE1IS is
C5.5.11 "TLBI ASIDE1IS … TLB Invalidate by ASID, EL1, Inner Shareable".

Severity: low. The substantive claim (broadcast scope, DSB completion) is true and is
supported at D8.17.7/D8.17.8 and on the instruction pages; the pointer is wrong, and a
reader following it lands in the formal concurrency model.

Smallest correction: in line 328, replace "(Arm DDI 0487, B2.3, \"TLBI Effects,
Completed TLBI Effects and Invalidation Scopes\")" with "(Arm DDI 0487, D8.17.8; the
broadcast scope is D8.17.7)", and cite C5.5.11 for `TLBI ASIDE1IS` where C5.5.60 is
meant for it.

### 2. The start-up check on `CORE_ANSWER_NS` does not bound the L2 quiet-word wait it exists to prevent — medium

Two sentences together promise that a healthy node never accuses itself through ordinary
contention, but the check only bounds the L1 term:

`kernel-interface.md:671`:

> "**a lock wait, a wait for the quiet word, or a request not complete, longer than
> `CORE_ANSWER_NS`** … is a failure of the node … **The machine start-up refuses a
> `CORE_ANSWER_NS` not above (*N* − 1) × *H* for the largest *N* the kernel image
> supports (entry `Node`), *H* being the longest hold measured for that image (D-131):**
> otherwise ordinary contention would make a healthy node accuse itself …"

`kernel-interface.md:664` defines the terms: "Let *H* be the longest hold of the **node
lock (L1)** and *h* the longest hold of an **object lock (L2)**". The bounds the same
section states are:

- `kernel-interface.md:667`: "with L2, a call that takes *k* locks is bounded by its
  one-core bound plus 2 × *k* × (*N* − 1) × *h*"
- `kernel-interface.md:668`: "with L2, every call and every event may first wait for the
  quiet word, for at most *N* − 1 escalated calls"
- `kernel-interface.md:658`: "**Bound of an escalated call:** its one-core bound, plus
  *E*, the longest kernel event of another core of the node … plus the escalated calls
  ahead of it in the queue of the word, at most *N* − 1, each of the same bound", and
  "a wait for the quiet word longer than `CORE_ANSWER_NS` is a failure of the node, as a
  lock wait is."

So the waits that trigger self-accusation at line 671 under L2 include quiet-word waits
bounded by (*N* − 1) escalated calls, each of one-core bound + *E* + (*N* − 1) × (the
same) — a bound that involves *E*, a whole kernel event, and the one-core bound, none of
which is bounded by (*N* − 1) × *H* (which bounds only single lock holds of the L1 node
lock). The L2 lock-wait term 2 × *k* × (*N* − 1) × *h* is likewise not bounded by
(*N* − 1) × *H* for *k* > 1. The Numbers row repeats the same check
(`kernel-interface.md:1489`: "and above (*N* − 1) × *H* for the largest *N* the image
supports, which the machine start-up checks (D-131)").

Scenario, step by step: a machine of *N* = 64 cores (allowed: `CORES_PER_KERNEL_MAX` =
64, line 1480) running an L2 image; the boot image sets `CORE_ANSWER_NS` = 10 ms (in
range, line 1489) and *H* small enough that 10 ms > 63 × *H*, so the start-up check of
line 671 passes. Many threads on different cores make calls whose tries keep failing
(another core keeps changing the queue head a call reads — the case the escalation exists
for, line 658), so each third attempt escalates. The cores that arrive at the kernel
while one escalation holds the quiet word write their entry word 0 and wait at entry
(line 658); each escalated call can take one-core bound + *E* + up to 63 further
escalated calls ahead of it in the ticket queue. With *E* of the order of 1 ms (a long
event: a removal step with many units, a burst of interrupts), a core waiting for the
quiet word can wait well beyond 10 ms. By line 658 and line 671 that wait "longer than
`CORE_ANSWER_NS` … is a failure of the node": the healthy node writes `panic` (self
evidence, line 1270) and is fenced — exactly what the check at line 671 was written to
make impossible ("otherwise ordinary contention would make a healthy node accuse
itself"), but the check bounds only (*N* − 1) × *H*.

Severity: medium. It is a gap between a stated check and a stated guarantee, not a
protocol deadlock; `CORE_ANSWER_NS` is provisional and *H* is to be measured (open
points, line 2259), but as written the check does not cover the L2 terms it is used to
justify.

Smallest correction: for an L2 image, make the machine start-up refuse a
`CORE_ANSWER_NS` not above the L2 terms as well — 2 × *k*max × (*N* − 1) × *h* for the
largest *k* the image allows, and (*N* − 1) × (one-core bound + *E* + (*N* − 1) × the
escalated bound) for the quiet word — or scope the sentence at line 671 to L1 ("under L1,
otherwise ordinary contention would make a healthy node accuse itself").

### 3. Sealed state: the sweep sentence and the seal-evidence row cannot both be read literally — low (unsettled case)

`kernel-interface.md:1275` (evidence table):

> "| **seal** | *X* is sealed and the instant of its seal, in its node beacon, is older
> than `SEAL_NS` | Any live node; the sweep |"

`kernel-interface.md:1278` (the sweep):

> "every live or sealing node also observes its two successors **among the nodes that are
> starting, live or sealing**, in cyclic index order, every `SWEEP_NS` … A sealed node is
> **never observed … by the sweep** … only the evidence kill, retire and seal can accuse
> it."

Under the literal sweep sentence, a sealed successor is not among the nodes the sweep
observes, so "the sweep" in the seal row can never look at a sealed node and the seal
evidence of an unneeded sealed node is checked only by "any live node" when it looks for
another reason ("A node is judged only when someone needs it", line 1277). The stated
time for the sealed state then does not hold as written:

- `kernel-interface.md:1488` (Numbers): "`SEAL_NS` | 1 s | … Time a node may stay sealed
  before evidence seal accuses it"
- `kernel-interface.md:960`: "messages to it wait in its rings until it resumes or is
  accused (with evidence seal, after `SEAL_NS`)"
- `kernel-interface.md:1253`: "A node sealed for longer than `SEAL_NS` (1 s,
  provisional) **may be accused** by any live node with evidence seal"

The two outcomes the text allows: (a) the sweep does check the seal instant of a sealed
successor (one read of its node beacon) — then "among the nodes that are starting, live
or sealing" and "never observed … by the sweep" at line 1278 are wrong; (b) the sweep
really never observes sealed nodes — then a sealed node that owes nothing (no messages
in its rings, no grants anyone revokes, nobody waiting for it) is accused by nobody
within `SEAL_NS`, and the rows at 1488, 960 and the rationale at 1253 ("without `SEAL_NS`,
a sealed node that never resumes would hold the reclaim barrier … for ever") are not
kept as stated times; its memory stays frozen until the machine restarts.

Severity: low. A sealed node with pending messages or revoked grants is accused within
`SEAL_NS` by the waiter ("A thread that waits for *X* makes its kernel observe *X*",
line 1277), so the common case is covered; the hole is the sealed node nobody needs.

Smallest correction: one sentence at line 1278 — "the sweep also reads the seal instant
of a successor that is sealed, and accuses it with evidence seal once it is older than
`SEAL_NS`" — or, if reading (b) is intended, drop "the sweep" from the seal row at 1275
and say who accuses an unneeded sealed node.

### 4. Debugger stop: the guarantee "no node accuses another for the time stopped" depends on paths the suspend rule does not name — low (unsettled case, development images only)

`kernel-interface.md:1639`:

> "a core that does not stop within 10 ms is shown to gdb as running. Before the release,
> the stub clears every open observation of every node beacon, so that **no node accuses
> another for the time stopped**. … **While the release word is raised, the clocks of
> membership stop (D-135):** `CORE_ANSWER_NS`, `FENCE_NS` and `SEAL_NS` are not measured
> and no node accuses itself; **a wait, a due event or a step of a fence** that finds the
> release word raised suspends, and resumes once it is cleared, its time counted from
> then …"

The suspend list names a wait, a due event and a step of a fence. It does not name a
call, an interrupt arrival, or a step of the recovery reserve (R0–R6 run in the
reserve, line 1338; only fence steps are named). A core that does not stop within 10 ms
keeps running, and its calls proceed. The stuck evidence row (`kernel-interface.md:1272`)
reads:

> "| **stuck** | The gate recorded an observation (one of the two rings *Y* → *X*, its
> consumer index *c*, instant *t*) taken when the ring was not empty and after *Y* sent
> *X* an interrupt, and the consumer index still reads *c* with now − *t* ≥ `STUCK_NS` |
> A node with a message waiting in a ring to *X* |"

and observations are "written by the gate only" (line 1279) with no release-word
condition stated. So the case the text does not settle: while the release word is
raised, a non-stopped core Y makes a `node_send` to the stopped node X; the send is a
call (not suspended), the gate records a stuck observation with instant *t*; `STUCK_NS`
is not among the suspended clocks (D-135 item (6) names only `CORE_ANSWER_NS`,
`FENCE_NS`, `SEAL_NS`), so the evidence ages in real time during the stop. Whether "a
node with a message waiting in a ring to *X*" can then accuse for the time stopped
depends on where that check runs: if only at a wait, a due event or a sweep (all of
which suspend), the guarantee at 1639 holds; if it also runs at an arrival or in a
recovery-reserve step (neither named as suspending), the accusation is made while the
release word is raised and the guarantee does not hold. The text allows both outcomes.

Severity: low — development images only (the release word exists only there), and the
stale and stuck accusers named in the table are waits and sweeps, which do suspend.

Smallest correction: add "a step of the recovery reserve and an arrival" to the suspend
list at line 1639, or state that the gate writes no observation and makes no accusation
while the release word is raised.

## What I checked and found correct

Attack 1, quiet word (line 658, proof at 660): no deadlock or livelock found. The quiet
word is waited for only with no lock held — at kernel entry (entry word written 0 first)
and in the escalation path, since line 658 defines the entry word as "0 outside one and
**while it waits for the quiet word**", which covers a second escalating core spinning
on the ticket lock. The holder takes the word only after releasing every lock, waits
only for the other cores' current events, and holds the word across no wait for another
core or unit (a wait for the node's cores or a unit is entered at the end of an event
with the word cleared first, lines 660, 670). A core that entered just before the word
was taken keeps its old epoch in its entry word and the escalator waits for it — that is
the "+ *E*" term of the escalated bound. Two escalating cores are served in ticket
order; after the first clears the word the second raises the epoch again and cores that
entered meanwhile already read at least the new value. A core that stops answering while
holding or waiting for the word is caught by line 671 (`CORE_ANSWER_NS`), which is the
self-accusation path — the gap in what the start-up check bounds is finding 2, not a
missing detection. An interrupt on a waiting core is acknowledged and, for a level
source, masked first (steps that take no lock), the rest of the arrival is done once the
word is clear (line 658); nothing is lost or delivered twice, since the irq states'
pending bit and masking rules are unchanged. The adapted no-deadlock proof at line 660
("The quiet word adds no cycle") holds step by step for the reasons above. The frequency
limit is a real bound: the kernel's own time in every event is charged to the context
running at entry (line 552), so the two `again` plus the escalated call cost at least
3 × *c* of the escalating context's budget and a context of budget *b* per period makes
at most *b* / (3 × *c*) escalations per period (line 658). Epoch wrap: the kernel epoch
is one 64-bit word raised at each escalation and each last destruction of an untyped
(line 657); no wrap rule is stated, and none is reachable in practice — noted, not a
finding. Per-entry cost: one write to the core's **own** line at each entry and exit and
one read of the epoch per entry (line 658), the epoch word written only at an escalation
and a last destruction, so no shared-line write and nothing on a memory access, as the
text claims.

Attack 2, "a call writes nothing before its last try has succeeded" (line 652) against
every call of the list at line 656: I walked the list and found no call that must write
before a try. The two new rules are right and complete as far as the text goes: the
reply object attached to a waiting receiver is guarded by the lock of the object it
waits on (line 653, "its attached reply object needs no lock of its own: above", line
655), and `memory_give` tries the derivation-list neighbour before it starts its core's
invalidation request, `memory_split` likewise removing from the derivation list (line
656). Removal steps keep the rule unit by unit (line 652). `signal`'s atomic OR is the
single stated exception and `signal` never returns `again` (line 655). `irq_claim` over
several remapping units can end `busy` with earlier units written (D-134 item 6), which
is a bounded step done with result `busy`, not an `again` after a change, and the line
word is taken in the same gate call after the derivation segment was tried (line 749).

Attack 3, line owner words (line 749, `IRQ_LINES_MAX` = 4,096 words = 32 KB at lines 749
and 1758): a node can no longer take, mask or redirect another node's line — the word is
taken by the rules of taking at `irq_claim` in the same gate call as the remapping entry,
`busy` if the rules refuse it or the node's current generation already holds it on any
core and vector, `unsupported` for a line beyond the last word, freed by the irq's
removal, cleared by R6 "as it clears the interrupt tables" (line 749); G9 (line 1063)
allows the redirection entry "only for the node the line's word names with its
generation, or masked when the word is free or names the requester". MSI needs no line
word (the remapping-handle range check is in the operation table, lines 1016–1021); a
line shared by two devices is one word, so the second claim is `busy`. `StartMachine` =
88 bytes checks out field by field (8 u32 offsets + 1 u64 + 4 u32 + 8 u32 = 88). Eleven
message kinds with number 9 reserved (line 914, `NodeMessage` at line 1771).

Attack 4, sweep and `Ping` removal: the sweep is armed every `SWEEP_NS` at a due event of
the first core of every live or sealing node (line 1278); a silent successor's first
core is found by stale evidence within `SWEEP_NS` + `STALE_NS` (line 1278); a silent
core other than the first is found by the first core's own sweep (line 1278); a starting
successor is observed for stale and its starter wakes it every `START_RETRY_NS` at due
events until `started` equals the request (lines 1278, 1399; `START_RETRY_NS` = 1 ms,
line 1487); the all-idle case is covered because "the first core of a live or sealing
node is never idle with nothing armed" (line 1278); the recovery reserve arms no timer
when it has no work (line 1338). No leftover `Ping` or twelve-kinds sentence remains in
the contract — only the removal notes (lines 914, 1278 parenthetical, 1769, 1771). The
sealed state is finding 3.

Attack 5: the start retry is a due event of the starter's first core every
`START_RETRY_NS` (line 1399, step 2; Numbers line 1487). The debugger's suspension of the
membership clocks is as decided in D-135 item (6) — `CORE_ANSWER_NS`, `FENCE_NS`,
`SEAL_NS` — and the waits, due events and fence steps suspend (line 1639); the residual
unsettled case is finding 4. The watermark returns through the kernel epoch: the last
destruction raises the epoch and writes it in word 6 of the root slot (line 657; slot
word 6 at line 1925), and the first `untyped_retype` that finds every other core's entry
word 0 or at least that value returns it (line 657) — coherent with the escalation's use
of the same words. The invalidation request has a state word, *in use* / *done*, written
*done* by the completing core, and a call or step that needs the request while it is in
use returns `again` with nothing changed (lines 329, 1769). G9's weaker wording (line
1063, "a page of class *iospace table* held by the node that owns the device"): no, it
does not let a node point a device at a lower-level table and reach memory it does not
hold — the contract says so itself in the same sentence ("a lower table named as root
still leads only to memory that G3 checked for that node, so containment holds, and only
that node's device translates wrongly"), because every page of that class held by the
node was G3-checked when the node took it. An unfenced peer gets R2 to R4 only and no
`acked` (line 1309: "*Y* writes no `acked[X]` for it until it is fenced, D-135"; the
resume runs "R2 to R4 for those unfenced", line 1391), which unblocks the resume.

Attack 6, citations, all verified at source on 17 November 2026 in the editions named at
line 80:

- VT-d revision 5.20, order D51397-019, April 2026 (downloaded; title page and §6.5.2.8
  "Interrupt Entry Cache Invalidate Descriptor" with Figure 6-8 bit fields: IIDX bits
  47:32, IM bits 31:27, G bit 4, Type 4h — as line 1019 states them). §6.2.2.1 DID /
  SSPTPTR quote at line 1011 verbatim. §5.1.5.1 "I/OxAPIC Programming" at line 1020
  verbatim, including Interrupt_Index bits 63:49 and [15] bit 11, bit 48 remappable, and
  "must match the Vector field programmed in the referenced IRTE". §11.4.2 Capability
  Register ND field at line 2278 confirmed.
- Intel SDM order 325462-093, September 2026 (downloaded, 5,364 pages; title page
  "325462-093US September 2026"). §11.4.2 MP-initialization BSP quote at line 1289
  verbatim. §11.4.4.1 Table 11-1: 10 ms after INIT and 200 µs between the two SIPIs,
  confirmed (lines 1290, 1484 "10.2 ms"). §26.8 "The INIT signal is blocked whenever a
  logical processor is in VMX root operation …", §34.5.1 "INIT operations are inhibited
  when the processor enters SMM", §34.14.2 "INIT signals are blocked after RSM if and
  only if the logical processor will be in VMX root operation" — all verbatim as quoted
  at line 1289.
- PSCI DEN0022F.b (PSCI 1.3 Issue F.b, confirmed current via den0022/latest). §5.7.2
  AFFINITY_INFO quote at line 1203 verbatim ("Callers must be aware that the state
  returned by the AFFINITY_INFO call is affected by calls to CPU_ON and CPU_OFF…").
  §6.6 "Implementation CPU_ON/CPU_OFF races" exists as cited.
- Arm DDI 0487 M.d, 30 September 2026 (downloaded full PDF, 129 MB; release history top
  entry 30/Sep/2026; TOC and the cited section pages read). C5.5.60 = TLBI VAE1IS with
  HCR_EL2.{E2H,TGE} = {1,1} acting on EL2&0 — the line 328 claim is correct for VAE1IS
  (but see finding 1 for ASIDE1IS = C5.5.11 and for the B2.3 title). C5.2.1 `ALLINT`
  quote at line 1294 verbatim. D8.17 rule IWZCBG at line 333 verified on the D8.17 page.
  D8.17.1 break-before-make at line 334 exists. D8.2.9 Table D8-26 for the 16 KB granule
  at line 2173: level 0 starts at IA[47], 2 entries, 2048 entries below, and
  "48 = 14 + 3×11 + 1" all correct.
- The editions block itself (line 80) names all four editions correctly as current on
  17 November 2026.

The only wrong external citation found is finding 1.

## What I did not check

- The full DDI 0487 M.d PDF was not read word by word; the TOC was searched exhaustively
  for the finding-1 titles and the cited sections (C5.5.11, C5.5.60, C5.2.1, D8.17,
  D8.17.1, D8.2.9, D8.17.7, D8.17.8, B2.3) were read on their pages.
- Arm IHI 0069 (GIC) is cited at line 749 without an edition; the editions block does not
  name it, so there was no pinned edition to verify against.
- Citations other than the four specifications — TF-A v2.12.0 SDEI sources and Linux
  v6.12 idle/TLB comments (lines 1295–1297, 337), the RISC-V SBI HSM / AIA / unprivileged
  ISA links, the seL4 references — were not re-fetched today; they are from earlier
  passes, not re-verified here.
- `ESR_ELx.EC` fault-class detail and the per-core-part cache-line alignment of the node
  block in `abi/` are not verifiable from this repository's text alone.
- The review files the contract cites (review 10 and earlier, including
  `2026-11-17-contract-review-10-deepseek.md` and its verification) were used only as
  cited; I did not re-read them.
- `kernel.md`'s pass-18 changes were seen through the commit diff, not re-read whole.
- The reference model was not run (it is not what this brief asks of a contract review),
  and the measured values (*H*, *E*, stall times) are open points by design (line 2259);
  finding 2 is about the check's formula, not about any measurement.
