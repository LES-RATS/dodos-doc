# Verification of Hydrogen's contract-only review (v3), with full context

Report verified: `scratchpad/final/reports/v3-hydrogen.md` (14 findings).
Contract: `Docs/architecture/kernel-interface.md` on `main`. The head is
now `1d83b8d`, one commit past `6e7d8c0`; `git diff --stat 6e7d8c0 HEAD`
touches only `reviews/`, so the contract is byte for byte the one the
brief names. Line numbers below are those of that file (2,306 lines). The
reviewer's line numbers match it for every quote I checked.

Outside sources opened today, 17 November 2026:

- Intel SDM, combined volumes, from https://cdrdv2.intel.com/v1/dl/getContent/671200.
  The title page reads "Order Number: 325462-093US". In this edition the
  APIC chapter is chapter 13 (for example §13.8.5).
- VT-d, from https://cdrdv2.intel.com/v1/dl/getContent/671081, "Rev. 5.20,
  Order Number: D51397-019".
- Not opened: the IOAPIC datasheet (82093AA) and the ICH/PCH datasheets
  that define the IOAPIC EOI register and Remote IRR; Arm IHI 0069 (GICv3);
  the RISC-V AIA and SBI documents; Arm DDI 0487 M.d (no finding rests on
  it). When a claim rests on one of these, I say so.

---

## Finding 1: a moved context runs on two cores at once

**Quotes.** Lines 183, 511, 512, 522, 539, 565, 609, 611, 612, 664 and 692
are exact. The "..." gaps leave out text but do not change the meaning.

**Replay.** This is a node with cores *a*, *b*, *c*. *T* is the home of
context *S*, which is placed on *a*. *P* is a passive server.

1. *T* calls *P*. The delivery lends *S* to *P* (line 609). *T* waits, so
   its home is not runnable, and the holder is *P* (line 611). *P* runs on
   *a* (line 662).
2. On *b*, `sched_configure(S, ..., core c)` writes *S*'s core = *c* and
   moves *S* into *c*'s sum and queues (lines 539, 662). It marks *P*
   *leaving its core* and sends *a* the leave interrupt (line 692). It
   waits for nothing (line 692).
3. Core *a* has not yet taken the interrupt, so it is still executing *P*
   in user mode on *S*.
4. On *b*, a second event ends *T*'s wait. Any of these does it:
   `thread_cancel(T, 0)` (line 183); `send` on *P*'s reply object by
   another server thread (line 205), since any thread holding the reply
   object may answer (line 132); or the destruction of that reply object
   (line 129). `thread_cancel` does not look at other cores (line 692).
5. *T* is not suspended, does not wait and is not marked. So *T* is
   runnable (line 511).
6. The holder is the home when the home is runnable (line 611), so it is
   now *T*. *S* is configured, not dying, and its holder is runnable, so
   *S* is eligible (line 512). Before this event *S* was not eligible: its
   holder *P* was marked. So the event made a context placed on *c*
   eligible, which puts *S* into *c*'s queues and sends *c* the reschedule
   interrupt (line 664).
7. Core *c* chooses *S* and runs *T* on it. Core *a* is still running *P*
   on *S* until it takes the leave interrupt.

The only sentence that tries to prevent this is line 511: "the event that
clears the mark makes its context eligible on the core where the context is
now placed". It works only while the holder is the marked thread. Once the
holder becomes another thread, eligibility no longer depends on *P*'s mark.
D-131 brought in the mark for this very case ("a context moved by
`sched_configure` chosen on its new core while its old core still ran it",
line 511), and the case comes back through a change of holder.

Step 7 of the report goes too far. It says *S* is linked into the queues of
both *a* and *c*, which breaks line 565. That does not follow. The move takes
*S* out of *a*'s queues. Core *a* only holds a pointer to the thread it runs.
All events run under the one node lock (line 666), so the queues stay sound.
What is real is the double run itself. Both cores spend *S*'s budget during
the window. When *a* takes the leave interrupt, it charges *S* again for the
time since its last event. *S* overruns by at most that window, and the
exhaustion rule takes the overrun back from *S*. Core *a* also gives that
time to a context that is no longer in its sum, but this happens on every
move, with or without the second event. Nothing outside *S* breaks. A stated
invariant does break: "The **holder** of a context is the one thread that
may run on it" (line 512).

A related gap, with no move involved. *S* stays on *a*, *P* runs it, and
*T*'s wait ends on *b*. *S* was eligible before and after, so line 664
sends no interrupt. Line 589 ("A context that passes from one holder to
another inside one event ... is not woken") confirms that no wake-up
happens. Core *a* keeps running *P*, which is no longer the holder, until
its next event. That can be as late as `STALE_NS` / 2 or the end of the
budget. Lines 613-614 say a time limit frees the client "at once". On several
cores it frees the client only at *a*'s next event. Nothing runs twice, so
this is a matter of latency.

**Verdict.** **Real**, of low severity, not "breaks a guarantee" in the
strong sense. The broken invariant is "one thread runs a context". The
cost is a bounded overrun charged to the context that overran. The window
is one leave interrupt.

**Correction.** In line 512, after "its holder is runnable", add:
"and it is not *moving*: `sched_configure` that moves a context while a
thread runs it on its old core marks the context *moving* with that
thread's mark, and the leave interrupt that clears the thread's mark clears
it (D-131)". In line 692, after "its holder runs on the new core once the
mark is clear", add: "and an event that changes the holder of a context
that another core is running sends that core the reschedule interrupt
through the gate (G10)". The cost is one bit in the `sched` object (new
state; I did not check whether the object has a spare bit) and one interrupt. Both are paid
at a move or at a change of holder across cores, never on a memory access.

---

## Finding 2: clearing the tables of `aspace_map` with 16 KB pages

**Quotes.** Lines 98, 99, 103, 167, 168, 170, 266 and 2195 are exact.

**Replay.** With *P* = 16 KB and *L* = 3 (line 2195), one call takes at
most 2 × (*L* − 1) = 4 tables, or 64 KB. Taken at a page-aligned watermark,
those tables can carry up to *P* − 64 bytes of padding. The worst case is
just under 80 KB to clear, as the report computes.

What prevents the contradiction is line 170 itself. The 64 KB step of line
167 belongs to "A creation", that is, `untyped_retype`. Line 170 takes the
tables "by the same rule", meaning the clean mark and its padding, and then
says why these calls never need a step: they take "at most 2 × (*L* − 1)
tables ... a constant of the machine, so they clear within the call and
never return `again`". The bound it relies on is a constant of the machine,
not 64 KB. Line 98 says a count of bytes that bounds one step does not
change with *P*. It does not say that every call clears at most 64 KB. The
tables are counted in pages, and pages scale with *P*. No sentence caps the
clearing of one `aspace_map`, `iospace_map` or `cspace_grow` at 64 KB.

**Verdict.** **Refuted** as a contradiction. What remains is a cost: on
ARM64 with 16 KB pages, one `aspace_map` may clear just under 80 KB in one
call, against just under 28 KB on the reference machine. Line 170 states
this only for the reference machine. If the owners want the worst case
stated, line 170 could add "(at most 4 tables and the padding of one, just
under 80 KB, with 16 KB pages)". That is wording, not a fix.

---

## Finding 3: level lines claimed on a node that does not hold the controller's role

**Quotes.** Lines 196, 775, 776, 780, 781, 787, 789, 791, 797, 971, 1043,
1082 and 1770 are exact (1082 is the last sentence of G9).

**The contradiction the report did not quote.** Line 797 says: "otherwise
the masking and unmasking of a level line are requests to the role holder,
slower and still correct". Arrival step 1 (line 780) masks a level source
at the controller before the end of interrupt, and line 815 repeats it for
x86-64: "A level line is masked in the IOAPIC before the end of interrupt".
Line 818 then says: "An arrival never involves the role holder." On a node
that does not hold the IOAPIC's role, and is not in line 797's
directed-EOI case, step 1 is a request to the holder. That breaks line 818.
The text contradicts itself. The report's scenario A is the consequence.

**Replay, x86-64, scenario A.** The node is *D*; another node *H* holds
the IOAPIC's role. The local APIC does not suppress EOI broadcasts, either
because the processor cannot (bit 24 of the version register is 0) or
because the kernel does not turn suppression on. *D* has claimed level GSI
*g* on one of its cores.

1. The device asserts *g*. The IOAPIC delivers the interrupt and sets the
   entry's Remote IRR (IOAPIC datasheet, not opened).
2. Step 1 on *D*: *D* cannot write the redirection entry, because the
   registers of a unit are mapped only in the holder's gate view (line
   1082). The masking is "a request to the role holder" (line 797). The
   interrupt path has no entry of the unit request table, no rule for a
   full table, and no thread to wait (lines 787, 1043).
3. Step 2 on *D*: the end of interrupt at the local APIC. The SDM says:
   "If the terminated interrupt was a level-triggered interrupt, the local
   APIC also sends an end-of-interrupt message to all I/O APICs" (§13.8.5,
   "Signaling Interrupt Servicing Completion", 325462-093). The default of
   bit 12 of the Spurious Interrupt Vector Register "is 0, indicating that
   EOI broadcasts are performed" (same section). The IOAPIC clears Remote
   IRR (datasheet, not opened).
4. *g* is still asserted and not yet masked, so the IOAPIC delivers again.
   That is the next arrival. The irq is fired, so nothing is signalled
   (line 789 holds for the signal). Step 1 runs again, then step 2, and so
   on until *H* writes the mask.
5. *H* serves its kernel ring within one period of its recovery reserve
   under load (line 971, 10 ms). So *D*'s core takes back-to-back arrivals
   for up to about 10 ms at the vector's priority. The kernel's own
   vectors 240 to 255 (line 799) are in a higher priority class, so the
   heartbeat timer still gets through. I find no fence of *D*. The storm is
   bounded by *H*'s latency, not unbounded as the report says.

So line 787 ("no loop and no queue", one constant path per arrival) still
holds for each arrival. Line 789's claim that being signalled once is "what
bounds an interrupt storm" does not hold on this path. Neither does line
797's "still correct".

In the directed-EOI case of line 797, *D* writes the vector into the
IOAPIC's EOI register to acknowledge. Step 1 is then not needed: with
suppression, the local end of interrupt sends nothing to the IOAPIC, and
Remote IRR stays set until the EOI register is written, so the line cannot
arrive again. But the text still says step 1 masks the line, and it gives
no rule for this case. The mapping of the EOI register is finding 4.

**ARM64 and RISC-V.** The report extends the storm to a GIC distributor SPI
and an APLIC line. I did not open IHI 0069 or the AIA. From memory, which I
have not checked: GICv3 with `EOImode` = 1 splits priority drop from
deactivation, and an SPI that stays active is not signalled again until
`ICC_DIR_EL1` deactivates it. That is a way to hold the line on the
claiming core without the distributor. The contract chooses neither way.
Whether either architecture storms is not shown here.

**Scenario B.** This is real. If `irq_ack` and `irq_bind` on a level line
of another node are requests, nothing says whether the call waits in
*waiting for a unit*. The list in line 1043 names `iospace_unmap`,
`iospace_attach`, `irq_claim` and remapping writes, not these. The general
`again` on a full table is covered: line 148 and line 1043 ("A call that
finds no free entry returns `again` with nothing changed") apply to any
call. The unbinding of `irq` entries when a notify is destroyed (line 791)
is a removal step, and line 1043 covers its `again`, but no entry kind
"what a step completes" names it. `busy` on a failed unit does not arise:
operation 5 "is answered at once" (line 1045), and an IOAPIC role has no
`IOMMU_WAIT_NS`.

**Verdict.** **Real**. It breaks the stated guarantee of line 818 and the
"still correct" of line 797. The severity is a contradiction plus a
bounded storm. Scenario B is a real but minor gap.

**Correction** (in the Nodes item of line 797, replacing the sentence
from "Where the local APIC suppresses" to "still correct"):
"A level line is claimed on a core of a node that does not hold its
controller's role only where its arrival needs no holder. On x86-64 that is
where the local APIC suppresses the broadcast of the end of interrupt,
which the kernel then turns on at start: the arrival does not mask the
line, because the IOAPIC's Remote IRR holds it until it is acknowledged,
and `irq_ack`, or a bind that arms it, acknowledges it by one write of the
line's vector into the IOAPIC's EOI register where it has one, and
otherwise by a unit request (operation 5, no thread waiting, like a step;
`again` when the table is full). Elsewhere that claim is `unsupported`,
judged with the core number. On ARM64 and RISC-V the architecture layer
states how a line is held without its controller's holder, or the claim is
`unsupported` (D-140)."
Line 818 then stays true. The cost falls on claims only: a refused claim on
old local APICs, where the line goes to the holder's node. It needs no new
state. Before this is written, the IOAPIC datasheet must be opened to check
how Remote IRR is cleared on an IOAPIC without an EOI register: Linux
switches the entry to edge and back, and a plain unmask may not be enough.

---

## Finding 4: the IOAPIC's EOI register, G9, and shared vectors

**Quotes.** Lines 768, 774, 797, 799, 1055 and 1082 are exact.

**Part 1, the mapping.** Real. Line 1055 lists, under "What needs no
role", "the acknowledgement of a level line through the IOAPIC's EOI
register". Line 797 has the claiming core make the write. G9 (line 1082)
says: "The registers of a unit are mapped only in the gate view of the node
its role word reads held by". The IOAPIC is such a unit (line 797: "the
holder of the IOAPIC's role"). No sentence gives a node that does not hold
the role a mapping of the EOI register, or a gate call that writes it. The
report also says the EOI register (offset 0x40) shares one 4 KB page with
`IOREGSEL` and `IOWIN`. That comes from the IOAPIC/PCH datasheets, which I
did not open, and the contract does not state it. If it is true, no
mapping finer than a page can split them. A gate call that writes only the
EOI register does not depend on it either way.

**Part 2, shared vectors.** Partly real. Vectors are claimed per physical
core (lines 768, 774), so two level lines of one IOAPIC can carry the same
vector on two cores. Operation 5 writes "for a level line the vector of
the remapping entry" (line 1035). VT-d §5.1.5.1 asks for that match only
"For platforms using End-of-Interrupt (EOI) broadcasts" (rev. 5.20, quoted
above in its section "I/OxAPIC Programming"). That an EOI-register write
clears Remote IRR in every entry with that vector is IOAPIC datasheet
behaviour, not opened. Under that behaviour, the trace is:

1. *A* (node 1) has level GSI 16 on core 0, vector 50. *B* (node 2) has
   level GSI 17 on core 1, vector 50. Both are in line 797's directed-EOI
   case.
2. GSI 17 is delivered, so its Remote IRR is 1 and *B*'s irq is fired. Its
   driver has not yet cleared the device.
3. *A*'s driver calls `irq_ack`, which writes 50 into the EOI register.
   The Remote IRR of GSI 16 and of GSI 17 are both cleared.
4. GSI 17 is still asserted, so it is delivered again to core 1. *B*'s irq
   is fired, so nothing is signalled (line 770: "no further signal until
   `irq_ack`"). Delivery sets Remote IRR again.

So there is no duplicate signal: the report's "breaking line 789" is
refuted. What remains is one extra kernel entry on another node's core for
each of *A*'s acknowledgements. That is cross-node interference, bounded by
*A*'s own arrivals (an `irq_ack` on an armed irq writes nothing, line 776).
In the broadcast case, the holder masks before the end of interrupt, and
an armed line has Remote IRR 0, so the same collision is harmless there.

**Verdict.** Part 1 is **real**: a contradiction between line 797/1055 and
G9. Part 2 is **real but minor**. It is availability interference, not a
duplicate signal.

**Correction.** In G9, after "or names as target of a handing", add:
"except the EOI register of an IOAPIC, which the gate of any node writes,
with the vector of a level line the node's line word holds, by one gate
call (G10), never mapped". In the operand table, row 5, replace "and for a
level line the vector of the remapping entry" with: "and for a level line
the vector of the remapping entry where the end of interrupt is broadcast;
where it is suppressed, the line's offset in its IOAPIC plus 48, so that a
write into the EOI register names one entry (VT-d §5.1.5.1 asks for the
match only with broadcasts)". The node then writes that value, not the
vector, into the register. Without remapping, the holder's gate refuses a
claimed level line whose vector another claimed level entry of the same
IOAPIC carries (`busy`). That is one read of at most the IOAPIC's inputs,
at a claim. The cost falls on claims and acknowledgements only. It needs
no new state, because the line word gives the owner. Linux does the same
with remapping: `entry->vector = info->ioapic.pin` in
`drivers/iommu/intel/irq_remapping.c`, from memory, not opened today.

---

## Finding 5: `iospace_map` when the unit caches entries that are not present

**Quotes.** Lines 196, 344, 348, 1028, 1043 and 1770 are exact. Line 2091
names the flag: "flags (bit 0 `iospace_map` also asks the unit's role
holder to invalidate".

**Replay.** Line 1028 says "every `iospace_map` also asks the unit's role
holder to invalidate". No other sentence says how. The `iospace_map` row
(line 348) is "As `aspace_map`" with differences that leave out the
request. Line 1043's list of calls that wait in *waiting for a unit* does
not name it. The `again` on a full table is covered by line 148 and line
1043 ("A call that finds no free entry returns `again`"), so on that point
only line 1770's list is short. Still undefined: whether the call waits;
what it returns when the unit is found failed; what happens on an iospace
that serves no device, where line 344 says it belongs to no unit; and, for
a mapping made in steps (G3), at which step it asks.

Waiting matters. Line 325 ends with "Translations that were added may cause
no fault". VT-d §6.1 says: "When the CM field is reported as Set, any
software updates to remapping structures ... (including updates to
not-present entries ...) requires explicit invalidation of the caches"
(rev. 5.20). If `iospace_map` returned before the unit confirmed, a device
could fault on a translation the call reported as made. This costs DMA
faults, not isolation: the counts cover the new leaves from the moment they
are written.

**Verdict.** **Real**, an unsettled case. It shows up only where bit 0 is
set, mostly emulated IOMMUs, since §6.1 says "software implementations
(emulation)" may report CM = 1. Severity: minor.

**Correction.** In the `iospace_map` row (line 348), add at the end:
"Where bit 0 of the flags of the entry `Memory` is set and the iospace
serves devices, the last step ends by a unit request (operation 3, the
iospace's domain number) and waits in *waiting for a unit*. It succeeds at
done. At *failed* it returns `busy` with the mapping made and counted. When
the unit request table is full, it returns `again` with nothing changed,
judged before any entry is written. An iospace that serves no device sends
nothing: the invalidation of its first attach covers it." Add
`iospace_map` to the list of calls in line 1043 and to line 1770. No new
state. It is paid on a map only, and only on those machines.

---

## Finding 6: a faulty node keeps a rebuild going for ever

**Quotes.** Lines 940, 943, 960, 966, 968, 1475, 1476 and 1485 are exact.

**Replay.** *H* holds unit *u* and dies. The successor *S* writes held,
maps *u* and pulls the reports (line 1475). *Z* is live and faulty.

1. *S* sends `ReportAsk(u, e, key 0)` to *Z* (line 1476).
2. *Z* answers one `Report` with 0 items and next key 0, on its kernel ring
   *Z* → *S*, with the right credit and serial. That passes line 966.
3. *S* "asks again from the next key until *end*" (line 1476), so it sends
   `ReportAsk(u, e, 0)` again. Go to step 2.
4. Requests for *u* are "kept until the rebuild ends" (line 940). The old
   holder's reclaim is acknowledged only after the rebuild (line 1475:
   "Then it serves requests ... and acknowledges the reclaim of the old
   holder"). The dead holder's memory and cores stay pinned.

*Z* drains its rings and beats, so neither stuck nor stale evidence holds.
No sentence checks that keys advance. The bound "A rebuild asks each node
at most ⌈items / items per message⌉ + 1 times" (line 1476) is asserted, not
enforced.

**What settles it.** The contract puts availability outside what it
promises against a faulty kernel. Line 966: a kernel that lies "damages the
marks of what it sends and availability, never another node's memory".
Line 1093 lists among what is not covered: "misuse of the gate's legal
interface by a corrupted kernel, which by construction damages only its own
node, what it granted, or availability". No memory leaves its owner here.

**Verdict.** **Intended** as a class (lines 966, 1093). But the bound in
line 1476 is false against a faulty asked node, and one comparison makes it
true. Severity: minor (availability).

**Correction** (in line 1476, after "the key of the next item or *end*"):
"The holder takes a `Report` only if its item keys rise from the key asked
and its next key, unless *end*, is above the last of them and above the key
asked. Otherwise it traces it (code 11) and treats that node's report as
ended, so what that node would have claimed is cleared, which costs only
that node." That is one comparison per item, at a rebuild only. No new
state.

---

## Finding 7: a rebuild report does not tie a device to its reporter

**Quotes.** Lines 1030, 1035, 1061, 1063, 1068, 1082 (G9), 1475 and 1476
are exact, apart from the marked gaps.

**Replay.** Healthy node *A* owns `dev_A`: identifier word *taken* (*A*,
*g*), attach word *attached* (`root_A`), domain number `DID_A` in *A*'s
range. Faulty node *Z* owns `dev_Z`, attached to `root_Z` with `DID_Z` in
*Z*'s range. The holder of the IOMMU unit dies, and *S* rebuilds.

1. *S* asks the nodes in index order (line 1476). Take *A* < *Z*. *A*
   reports (`dev_A`, `root_A`, `DID_A`), which *S* keeps or writes.
2. *Z* reports `dev_Z` honestly and adds the item (`dev_A`, `root_A`,
   `DID_Z`).
3. *S*'s checks in line 1475: "writing a context entry only for a device
   whose attach word reads *attached* with the root the report names".
   `dev_A`'s attach word reads *attached* (`root_A`), so this passes. G9's
   general rule asks for a root "of class 48 + *n* with *n* ≥ 1 in memory
   held by the node that owns the device". `root_A` is *A*'s, so this
   passes. "clears a reported entry whose domain number lies outside its
   reporter's range": `DID_Z` is in *Z*'s range, so this passes. No check
   reads `dev_A`'s identifier word against the reporter. The table of
   operations has that check for an attach ("the identifier word names the
   requester with its generation", line 1035), and line 1475 gives lines an
   explicit "checked as at that request", but no such phrase covers
   devices.
4. *S* "rewrites those that differ" (line 1475): `dev_A`'s context entry
   becomes (`root_A`, `DID_Z`). If *A* was sealed, its entry was "kept
   without a report", and *Z*'s item overwrites it in the same way.
5. `dev_A` and `dev_Z` now share `DID_Z` with two different roots. VT-d
   §6.2.2.1: "Software must ensure that, if multiple context-entries are
   programmed with the same Domain-id (DID), such entries must be
   programmed with the same values for the Second-Stage Page Translation
   Pointer (SSPTPTR) ... This is required since hardware implementations
   tag the various translation caches with DID" (rev. 5.20, quoted as the
   contract quotes it in line 1030). After the invalidation of the whole
   unit that ends the rebuild, a walk of `root_A` by `dev_A` fills IOTLB
   entries tagged `DID_Z`, and `dev_Z`, which *Z*'s driver controls, can hit
   them. *Z*'s device then reaches *A*'s memory. That breaks G (lines 1061,
   1063) for a healthy node, through a faulty kernel, which is what G9
   exists to prevent.

A weaker variant needs no shared number: *Z* reports (`dev_A`, `root_A`,
`DID_A`). `DID_A` is outside *Z*'s range, so *S* "clears" `dev_A`'s live
entry. Whether *A*'s own report, if it comes later, writes it back depends
on the order. That is availability only.

**Verdict.** **Real**, and it **breaks a guarantee** (G, for another
node's memory). This is the most serious finding of the report.

**Correction.** In line 1475, after "writing a context entry only for a
device whose attach word reads *attached* with the root the report names",
add: "and whose identifier word names the reporter with its generation
(the check of operation 1); an item that fails it is not written, is
traced (code 11) and claims nothing". In G9 (line 1082), after "with the
root the request names", add: "(or the report names, at a rebuild), for a
device whose identifier word names the requester (or the reporter) with its
generation". It costs one word read per reported device, at a rebuild only,
and no new state. The identifier word has one owner, so at most one
reporter passes for each device, and the order of the asks no longer
matters.

---

## Finding 8: a faulty peer overruns the reserve of answers

**Quotes.** Lines 962, 966, 968, 971, 975, 1517 and 1521 are exact.

**Replay.** Line 966 checks, for requests, only the epoch of a `ReportAsk`
and the stamp of a `Send`. It checks no credit. Faulty *X* writes 64
one-entry `Send`s into the user ring *X* → *Y*, which is *X*'s own memory
with plain stores (line 968). *Y* serves 16 per interrupt and answers each
with a `SendAnswer` on the kernel ring *Y* → *X*. *X* does not move its
consumer index. After 64 answers, minus whatever else *Y* had in that ring,
the next answer does not fit. Line 975 says answers "always have room"
because "one entry for each credit *X* can have in use toward *Y*", which
counts the credits of a correct *X*. Several `ReportAsk`s from an *X* that
holds a role work the same way: the check never asks for "at most one in
flight". Line 975 gives no rule for an answer that does not fit.

What breaks: *Y*, a healthy node, meets a case its kernel has no rule for.
Writing past *X*'s consumer index would hurt only *X*: *X*'s own receive
rule already handles a producer index "more than the ring's entries ahead"
(line 966). Blocking, or treating the case as impossible, would hurt *Y*.
The ring *Y* → *X* stays full, so stuck evidence will convict *X* in the
end. The overflow itself still comes first.

**Verdict.** **Real**, an unsettled case on a healthy node, caused by a
faulty one. Severity: minor.

**Correction** (line 966, at the end of the list "and by kind"): "a
request (`Revoke`, `UnitRequest`, `ReportAsk`, `Send`) whose answer would
not fit in the free entries of the kernel ring toward its sender is refused
before anything changes (only a sender that exceeds its credits causes
it)". The receiver reads the sender's consumer index, which it already
reads to write. That is one comparison per request, with no new state and
no cost on a correct path.

---

## Finding 9: the credit of an incoming request is not checked

**Quotes.** Lines 966, 972, 1045, 1518, 1520 and 1793 are exact. In
`abi/src/ring.rs` (outside the contract), the credit takes values 0 to 30,
and 31 is `CREDIT_NONE`.

**Replay.** The holder's unit service table is "indexed by the peer and the
credit, so none is searched" (line 1045). It has 16 entries per peer.
Faulty *X* sends a `UnitRequest` with credit 20, or 31. Line 966 checks the
credit of answers only. The index (*X*, 20) falls in the next peer's
entries or beyond the table. Either the holder overwrites a healthy peer's
request in flight, whose requester then waits until a holder answers,
which may be never, or a bounds check stops the healthy holder. A second
request with credit 0 while (*X*, 0) is in use overwrites *X*'s own entry,
which hurts only *X*.

**Verdict.** **Real**. It can damage a healthy peer, or the healthy holder
if the index is checked by a panic. Severity: moderate (a missing check on
the one receive function the contract says is complete).

**Correction** (line 966, after "a `UnitRequest` passes whatever its
epoch, which the holder judges"): "and names a credit below
`REQUESTS_PER_PEER` (a `Revoke` and a `ReportAsk` too; a `Send`, below
`SENDS_PER_PEER`) whose entry of the unit service table is not in use".
That is two comparisons per request, with no new state.

---

## Finding 10: a requester answered *elsewhere*, and a holder that keeps answering it

**Quotes.** Lines 940, 941, 1044 and 1465 are exact.

**Part 1, the contradiction.** Real, and a three-way one. Line 1044:
resend "at once if the role word now reads held by a live node with another
epoch, and otherwise once it does". Line 941: "at once if the role word
reads held by another node". Line 1465: "if it reads held, it sends the
request to the holder it names with that epoch". A correct holder answers
*elsewhere* while its word still reads held (*X*, *e*) during steps 1 to 3
of a planned hand-over (line 1466). Under line 1465 the requester sends
straight back to *X*, which answers *elsewhere* again. That loop of
messages lasts until step 4 writes handing. Under line 1044 the requester
waits for the new epoch. D-131 (decisions, line 141) reads: "the requester
keeps it while the word is handing and resends it with the current epoch".
That is closest to line 1044.

**Part 2, a faulty holder that answers *elsewhere* for ever.** Intended.
It is availability damage by a faulty kernel. The holder could just as
well never answer, and lines 966 and 1093 put that outside the guarantee.
No memory is at stake, because every write to the unit passes G9.

**Verdict.** Part 1 **real**, minor (a loop of messages for a correct
system during a hand-over). Part 2 **intended**.

**Correction.** Lines 941 and 1465 take the rule of line 1044. In line
1465, replace "if it reads held, it sends the request to the holder it
names with that epoch; if it reads handing, it keeps the request queued and
sends it once the word reads held" with "if it reads held by a live node
with another epoch than the one it sent, it sends the request to that
holder with that epoch; otherwise it keeps it queued and sends it once the
word does". In line 941, replace "at once if the role word reads held by
another node" with "at once if the role word reads held by a live node
with another epoch". It costs nothing.

---

## Finding 11: a `Report` does not say how many items it carries

**Quotes.** Lines 949, 960 and 1793 are exact.

**Replay.** The header gives a length in entries, and a message "takes
⌈(16 + 8 × words) / 64⌉ entries" (line 949). A `Report` of *k* items has 1
+ 3*k* words after the header. For *k* = 2, 3 and 4, that is 7, 10 and 13
words, or 72, 96 and 120 bytes with the header, and all three take 2
entries. The report's arithmetic is right. Reading padding zeros as an
item gives (key 0, 0, 0). If key 0 names device 0, its domain number 0 lies
outside every range, and line 1475 "clears a reported entry whose domain
number lies outside its reporter's range". So a correct reporter can have
another node's device 0 cleared. Neither the contract nor `abi/` defines
the encoding of a key either: line 1476 orders "devices ... by identifier;
then the remapping handles ...; then the lines ... by global system
interrupt" in one key space and does not say how.

**Verdict.** **Real**. It **cannot be built as written**. Severity: minor
(wire format).

**Correction** (row 8 of the words table, line 960): "One: the number of
items (bits 0-4); then the key of the next item, or *end* (all ones); then
three words per item ... At most 28 items | 86 (11 entries)". 16 + 8 × 86
= 704 bytes, still 11 entries, so the reserve of answers does not change.
Add: "A key holds its kind in bits 61-63 (0 a device, 1 a remapping
handle, 2 a line, 3 and 4 the ITS items of finding 12) and its identifier
in bits 0-60 (a device: its PCI segment in bits 16-31 and its identifier
in bits 0-15; a handle; a line: the index of its line word), so keys
compare as numbers in the order of line 1476." No new state.

---

## Finding 12: a GIC ITS has no `Report` items

**Quotes.** Lines 944, 960, 1082, 1475 and 1476 are exact.

**Replay.** Line 1475 has a GIC ITS rebuilt by issuing "again the mappings
the live nodes report". The items of lines 944, 960 and 1476 are devices,
remapping handles and lines. An ITS mapping is none of these. A rebuild of
an ITS has nothing to issue.

The report also says "2 payload words after a 64-bit key cannot even carry
device ID, ITT base, event ID, LPI, and collection ID". That is refuted
with two item kinds. An ITS device item can be a key (the device
identifier) plus the address of its interrupt translation table with its
size, plus 0. An ITS event item can be a key (device identifier and event
identifier, 32 bits each) plus the LPI, plus the target core. Each fits
three words.

**Verdict.** **Real**. It **cannot be built as written** for ARM64 with an
ITS. It does not arise on the reference machine. Severity: minor.

**Correction** (in line 960, before "At most 28 items"): "for an ITS
device, the physical address of its interrupt translation table with its
number of event identifier bits less one in bits 0-4, then 0; for an ITS
event, its LPI, then the core number of its collection". In line 1476, add
"then the ITS devices, by identifier, and their events, by device and
event" to the fixed order. In line 1475, after "issues again the mappings
the live nodes report", add "each checked as at its request (G9)". No new
state.

---

## Finding 13: "it takes over the cursors" of the console

**Quotes.** Lines 1451, 1475, 1523, 1632, 1633, 1647, 1649 and 1651 are
exact.

**Replay.** Line 1475 says a new console holder "takes over the cursors"
while it "rebuilds it without reading anything of the old holder's", and
line 1451 forbids anything "that cannot be rebuilt from the kept memory,
the hardware and the reports of the nodes". I find no console cursor in
kept memory, in a beacon, in a report, or in the list of what each node
keeps (line 1523). The old holder's counts "since the previous message"
(messages 10, 12 and 14) and its place in the queue of lines to write are
its own.

**Verdict.** **Real**, but a matter of wording. The outcome is a few
console lines lost or written twice at a change of holder. The console is
output only, and production images have none by default. Severity: minor.

**Correction** (line 1475, replacing "for the console, it takes over the
cursors"): "for the console, it starts from what it reads at the take-over
(the member and role words, the counts as they read then), so lines the
old holder had not yet written are lost, and the first messages 10, 12 and
14 count from the take-over". No new state.

---

## Finding 14: the debugger stub's stop

**Quotes.** Lines 900, 1083, 1312, 1315, 1316 and 1660 are exact.

**Part 1, RISC-V.** Real. The stub sends "the architecture's strongest
signal (as the fence does)", and each core "saves its registers ... and
waits on that release word" (line 1660). On RISC-V with the stop extension,
the fence's signal is `fence_hart`, "a forced stop ... leaves it in the
state STOPPED" (line 1316). No supervisor handler runs, and the hart can
come back only through `sbi_hart_start`, so it does not resume where it
was. A stop by the stub would end every other hart's node. The handler
path the stub needs ("a handler that finds no fence mark on its core's
word knows the signal is the stub's") exists on RISC-V only on the
cooperative path: the kernel's interrupt.

**Part 2, two cores enter at once.** Real and minor. Nothing says how the
release word is raised. Two entries at once (0x03 on one core, a
breakpoint on another) could make two stubs, each adding its own stop
length to the stopped time.

**Part 3, cores that do not stop.** Intended. Line 1660: "a core that does
not stop within 10 ms is shown to gdb as running". The stub accepts it by
its own text. The gate-refusal case (a failing node whose member word no
longer allows its gate to send) rests on which core enters the stub "at a
failure of any node". The text does not fix that, so the scenario does not
follow. At worst the stub stops fewer cores and shows them as running.

**Verdict.** Parts 1 and 2 are **real**. They concern development images
only, so the severity is low. Part 3 is **intended** or does not follow.

**Correction** (line 1660). After "the architecture's strongest signal (as
the fence does)", add "(on RISC-V the kernel's own interrupt, never
`fence_hart`, which does not resume a hart)". After "after it has raised
the stop in the release word of kept memory", add "by a compare-and-swap
from lowered; a core whose compare-and-swap fails is being stopped by
another entry, and saves its registers and waits as at the signal". No new
state. It is paid in development images only.

---

## Summary table

| Finding | Verdict | Severity (mine) | Correction in one line |
|---|---|---|---|
| 1. Moved context runs on two cores | Real | Low: bounded overrun of the context's own budget; breaks "one thread runs a context" | Line 512: a context is not eligible while *moving* (one bit, set by a move that leaves a running thread, cleared at its leave); line 692: a change of holder across cores sends a reschedule interrupt |
| 2. Clearing beyond 64 KB with 16 KB pages | Refuted | — | Line 170 already exempts these calls ("a constant of the machine"); at most, state the 16 KB worst case (just under 80 KB) |
| 3. Remote level lines: storm and missing rules | Real | Contradiction (line 797 against line 818) plus a storm bounded by about 10 ms | A level line on a node that does not hold its controller's role only with EOI-broadcast suppression (the IOAPIC's Remote IRR holds it; ack by the EOI register or a request with no waiter); otherwise `unsupported` |
| 4. IOAPIC EOI register against G9; shared vectors | Part 1 real; part 2 real, minor (no duplicate signal) | Contradiction; cross-node interference | G9 exception: any node's gate writes the EOI register for its own level line, never mapped; with suppression, the RTE vector of a level line is its offset + 48 |
| 5. `iospace_map` with CM = 1 | Real | Minor, unsettled case | The last step sends operation 3 and waits in *waiting for a unit*: `busy` at *failed*, `again` when the table is full; nothing for an iospace with no device |
| 6. Endless `Report` loop | Intended (availability is outside G: lines 966, 1093), but the stated bound is false | Minor | Take a `Report` only if its keys rise from the key asked; otherwise trace it and end that node's report |
| 7. Report not tied to the device's owner | Real | **Breaks G** (shared domain number lets *Z*'s device reach *A*'s memory) | Line 1475 and G9: a reported device is written only if its identifier word names the reporter with its generation |
| 8. Reverse ring overrun | Real | Minor | Line 966: refuse a request whose answer would not fit in the free entries toward its sender |
| 9. Credit of an incoming request unchecked | Real | Moderate (a healthy peer's entry or the holder itself) | Line 966: a request's credit below its kind's count, and its unit service entry not in use |
| 10. *elsewhere* | Part 1 real (three rules); part 2 intended | Minor | Lines 941 and 1465 take line 1044's rule: resend only to a live holder with another epoch |
| 11. `Report` item count | Real | Minor (cannot be built) | First word: number of items (bits 0-4); define the key (kind in bits 61-63); still 11 entries |
| 12. GIC ITS items | Real (the "cannot fit" claim refuted) | Minor (ARM64 only) | Two item kinds, ITS device and ITS event, three words each, in the fixed order, checked as at their request |
| 13. Console cursors | Real (wording) | Minor | The new holder starts from what it reads at take-over; lines in flight may be lost |
| 14. Debugger stub | Parts 1-2 real; part 3 intended or does not follow | Low (development images only) | RISC-V: the stub sends the kernel's interrupt, never `fence_hart`; the release word is raised by compare-and-swap |
