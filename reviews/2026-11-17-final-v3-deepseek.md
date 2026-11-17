# Review of `Docs/architecture/kernel-interface.md`, on its own

I read the whole file, 2,306 lines, from the first line to the last, and nothing
else of the repository. I searched nothing on the web. The line numbers below are
lines of that file; every quote was copied from it and checked again against it.

My angle: does the text agree with itself, and is it complete. I looked for
sentences that contradict each other, terms and constants named without a
definition, calls whose results or order of checks are not total, state machines
with an empty or a doubled cell, and bounds and sizes that do not recompute.

Twelve findings. None is about a hardware fact: no external document could be
opened from here, so everything the text quotes from one is outside this review.

---

## 1. The tree of capabilities names a parent the text says does not exist — contradiction

**Quotes.**

- Line 117: "Every capability has one parent, except the capabilities given at
  start-up, each of which is the root capability of its object; **the frames of
  the start-up state are the exception, as descendants of the image untyped**
  (D-110, see [Start-up state](#start-up-state))."
- Line 2019: "It is given once, as kept frames (rule 5), and **never as an
  untyped**."
- Line 2022: "The kernel makes a **kept frame** over each module: ordinary
  memory, write-back, never cleared, **made from no untyped**."
- Line 2024: "**Untypeds of a node.** Each range of the node's floor ... is cut
  into the fewest blocks that are each a naturally aligned power of two".
- Line 2053: "Every start-up capability **except the frames made from the
  start-up untyped** is the root of its object, at depth 1. ... **The frames made
  from the start-up untyped, in the order copied segments, start-up page, message
  page, are its children at depth 2**".

**Scenario.**

1. A reader asks which capability is the parent of the frame in a start-up slot.
   Line 117 answers: the image untyped.
2. There is no image untyped. The image is given as kept frames made from no
   untyped (line 2019, line 2022), and the only untyped the start-up frames come
   from is the node's start-up untyped, cut from the node's floor (line 2024).
3. Line 2053 puts exactly those frames at depth 2 under the start-up untyped,
   while line 117 sends a reader looking for a depth-2 parent inside the kept
   image, where line 2022 says nothing was made from an untyped.
4. The walk of a removal is described from this parent relation, so the sentence
   is load bearing: a builder that follows line 117 links the copied-segment
   frames to the wrong root, and `cap_revoke` on the start-up untyped then misses
   them.

**Smallest correction.** In line 117 replace "as descendants of the image
untyped" by "as descendants of the node's start-up untyped (rule 7)".

---

## 2. By the rule that is stated, a removal wakes 32 threads, not 64, and the timer bound inherits it — contradiction

**Quotes.**

- Line 129: "The step that marks a reply object as dying also wakes, with `gone`,
  the receiver attached to it or the caller that waits for an answer through it
  (**one thread: a reply object is attached or armed, never both**), so no caller
  can meet a waiting receiver whose reply object is dying. This wake is not
  counted in the 32 of a step: **a walk passes through at most one reply
  object**, because below the root of a reply object there are only copies. **A
  call makes at most 32 walks, so it wakes at most 64 threads.**"
- Line 603: "at most one timer, except a step of a removal, which puts **at most
  96 (one for each of its 32 units and for each of the 64 threads its reply
  objects can wake)**".

**Scenario.**

1. A call under `cap_delete` makes at most 32 walks (line 129).
2. Each walk passes through at most one reply object (line 129).
3. Each such reply object wakes one thread, because it is attached or armed,
   never both (line 129).
4. 32 × 1 × 1 = 32, and every wake is one timer, since line 129 says a removal's
   wake is not counted in the 32 but is still a wake.
5. The text writes 64, which needs two threads per reply object — precisely the
   case the parenthesis excludes. Line 603 then takes 64 as the wakes of reply
   objects and adds the 32 units, reaching 96.

The other reading of line 129 is that the 64 are 32 counted wakes plus 32
uncounted ones; under that reading line 603 is wrong as well, because it labels
all 64 as the reply objects' wakes and adds the 32 units on top. One of the two
numbers is wrong under either reading.

**Smallest correction.** Line 129: "so it wakes at most 32 threads by this
rule". Line 603: "at most 64 (one for each of its 32 units and for each of the
32 threads its reply objects can wake)".

---

## 3. The bound on the walk of a removal does not recompute — contradiction

**Quote.** Line 123: "So while the walk is on restricted capabilities the depth
never shrinks and stays equal at most once per level: **at most 128
capabilities**. Once the walk reaches an ordinary capability it stays on ordinary
ones, because everything derived from an ordinary capability is a copy, and a
copy is the root of nothing: **at most 64 more**. So no capability can depend on
itself, and **the walk is shorter than 192 capabilities (the longest one that can
be built has 191)**."

**Scenario.** Both halves are upper bounds of one walk and nothing forbids
reaching both at once: 64 levels that each touch two restricted capabilities,
then an ordinary chain that runs to its own depth of 64, gives 192. For 191 one
of the two segments must be short by one in every case, and no sentence says
which. A model that sizes a visit counter from 191 refuses a legal tree at its
192nd visit, or the bound in the code is 192 and disagrees with the sentence.

**Smallest correction.** "the walk is at most 192 capabilities", and drop the
parenthetical.

---

## 4. One letter, two quantities, in numbers an implementer must compute — contradiction

**Quotes.**

- Line 90: "| *E*, **entries per table** | The number of entries of one table
  page | 512 |"
- Line 683: "Let *H* be the longest hold of the node lock by an event ... and
  ***E* = *N* × *H* the longest kernel event of a core**, its wait for the lock
  included."
- Line 688: "The machine start-up refuses a `CORE_ANSWER_NS` not above the
  longest healthy wait it judges ... 2 × *E* + *D*".
- Line 1502: "The machine start-up refuses a `STALE_NS` not above
  `CORE_ANSWER_NS` + *E*, *E* = *N* × *H* the longest kernel event with its wait
  for the node lock".
- Line 2300: "The longest hold *H* of a node's lock ... and the delivery *D* of
  one interrupt, which bound the cores per node".

**Scenario.**

1. A reader meets *E* first in the table of machine values (line 90), where it is
   512 entries per table page.
2. At line 1502 the start-up gate compares `STALE_NS` against
   `CORE_ANSWER_NS` + *E*. With *E* = 512 bytes or entries, every value in the
   table passes and the gate checks nothing.
3. With the meaning the line itself gives (*N* × *H*, a duration) the gate is a
   real check, and *E* has two meanings in one file. Line 688 uses the same
   letter in the same way.
4. The same happens to *L*: line 91 defines it as the number of levels (4), and
   line 2024 uses "with *L* bytes left" for a length. And to *D*: line 1030 uses
   *D* for a unit's number of domains, line 688 and line 2300 for the delivery
   time of one interrupt. And to *N*: line 603 counts objects in a queue with it,
   while the shape of a node uses it for that node's cores.

**Smallest correction.** Rename the event length in line 683 to a letter no table
uses, "*W* = *N* × *H*", and use it at lines 688, 1502, 1510 and 2300; rename the
length in line 2024; and give the delivery time its own letter.

---

## 5. "about 5 for 192 handles" does not follow from the size of a message — contradiction (arithmetic)

**Quotes.**

- Line 1476: "For each unit it rebuilds, the new holder keeps a cursor in its
  node block ... A rebuild asks each node at most ⌈items / items per message⌉ + 1
  times (**about 5 for 192 handles**: an estimate, not measured)."
- Line 968: "A message takes 1 to 11 consecutive entries (**a `Report` of 28
  items takes the most**; a `Send` of 64 words with 4 grants takes 10)".
- Line 960: "then three words per item".

**Scenario.** A node has 192 remapping handles to report, one item each. One
`Report` carries at most 28 items (line 968), and each item is three words plus
the entry's key (line 960). The holder therefore needs ⌈192 / 28⌉ = 7 asks and one
more that returns *end*: 8. To reach 5 a message would carry 48 items, which the
ring cannot hold. The parenthetical is marked an estimate, but it is computed
from two numbers the same document fixes, and a reader who sizes the cursor or
`REQUESTS_PER_PEER` from it under-provisions.

**Smallest correction.** "about 8 for 192 handles".

---

## 6. The size of the beacons does not recompute — contradiction (arithmetic)

**Quote.** Line 1283: "**Size.** For *n* node slots and *c* physical cores: *c*
core beacons of one page, and *n* node beacons of one page plus 8\*n\* + \*n\*/8 +
16\*n\* bytes rounded up to pages: **about 1.5 MB for 128 slots** on the reference
machine."

**Recomputation.** At *n* = 128: 8*n* = 1,024, *n*/8 = 16, 16*n* = 2,048, so a
node beacon needs 4,096 + 3,088 = 7,184 bytes, rounded up to pages: 8,192. 128 ×
8,192 = 1,048,576 bytes. The reference desktop has 14 physical cores, a number the
text gives itself — line 1030: "with the 14 node slots of the default layout of
the reference desktop (one per physical core of an Intel Core i5-14600KF, to
confirm, D-116 point 4)". Fourteen core beacons are 14 × 4,096 = 57,344. Total
1,105,920 bytes, that is 1.05 MB, not 1.5 MB. Only 54 node beacons of three pages
each, or a machine of 128 cores, reaches 1.5 MB, and the formula gives neither.

**Smallest correction.** "about 1.1 MB for 128 slots (*c* = 14 on the reference
desktop)".

---

## 7. `StartDebug` is 56 bytes and its fields are 52: one port pair where the text needs five — cannot be built as written

**Quotes.**

- Line 2100: "| 24 | Debug | `StartDebug` (**56 bytes**): build (0 production, 1
  development), console kind (u32 each); console address (u64: base port,
  physical address, or 0); base and length of the current crash area (u64 each);
  slot of its kept frame, bytes per debug area (u32 each); entries of the kernel
  ring, of the user ring, bytes per entry, hardware breakpoints, hardware
  watchpoints of a user thread, reserved (u16 each); **then the ports refused to
  this node, as pairs of first and last port (u16 each)**".
- Line 1679: "Some ports are the kernel's for the whole boot: **the legacy PIC
  (0x20-0x21 and 0xA0-0xA1)**, which the kernel masks, and the 8 ports of the
  console or of the stub link when they are a UART on I/O ports. **The PCI
  configuration ports (0xCF8-0xCFF) and the chipset's reset control port** are
  allowed only to the node that holds the plain role `platform`".
- Line 2086, the `Modules` entry, for contrast: "`StartModule` records (40
  bytes): ... offset and length of its name, reserved (u32 each). **The records
  are followed by the name area** of the entry".
- Line 2090, the `Node` entry: "`StartNode` (24 bytes): ... (u32 each); **then
  the core numbers of its cores**, in position order (u32 each)".

**Recomputation.** 4 + 4 (build, console kind) + 8 (console address) + 16 (base
and length) + 4 + 4 (slot, bytes per debug area) + 6 × 2 (entries of both rings,
bytes per entry, two breakpoint counts, reserved) = **52 bytes**. The entry
announces 56, so 4 bytes are left: exactly one port pair. The list that follows
is far longer. A node that does not hold `platform` must be refused the PIC (two
ranges: 0x20-0x21, 0xA0-0xA1), the PCI configuration ports and the reset port —
four pairs — and a fifth when the console is a UART on I/O ports.

**Scenario.** Two entries in the same table do declare a tail (`Modules` with a
name area, `Node` with its core numbers), and in both the stated size is exactly
the fixed fields: `StartModule` 40 = 10 × 4, `StartNode` 24 = 6 × 4, so the size
is the fixed part and the tail unambiguously follows it. `StartDebug` breaks that
pattern: 56 is neither the fixed part (52) nor the fixed part of a record whose
pairs follow (which would be 52). A first stage that reads 56 bytes as the entry
and one pair gains 16 bytes of overrun from a kernel that writes five pairs; a
kernel that writes one pair publishes three ports as allowed that line 1679 says
are refused. Either way the size and the list contradict each other, and the
`busy` of the port gate (line 1679: "An access that touches a port refused to the
caller's node is `busy`, whatever the capability") is then either wrong or
unusable.

**Smallest correction.** State the fixed part as 52 bytes and add, in the words
of `Modules`: "then, after these 52 bytes, the ports refused to this node, as
pairs of first and last port (u16 each), for as many pairs as the difference in
length gives".

---

## 8. `untyped_retype` and `cspace_grow` never say what happens when the object does not fit — unsettled case

**Quotes.**

- Line 159: "| `untyped_retype` | untyped, kind, size argument, destination | |
  `write` on the untyped. One object per call."
- Line 146: "the state, in the order **each call's own rules list its state
  checks** (this item names the codes, not an order among them ... `no_memory`".
- Line 293, for `aspace_map`: "the tables the mapping needs are more than the
  aspace's free list and its untyped can supply (`no_memory`). An untyped of 0
  supplies none. **The untyped can supply as many tables (one page each) as fit
  between its watermark, aligned up to a page, and its end.**"
- Line 170: "Those calls take at most 2 × (*L* − 1) tables (6 tables, 24 KB, on
  the reference machine) **or one segment (8 KB)**, a constant of the machine, so
  they clear within the call and never return `again`."
- Line 1900: "| `no_memory` | The supplied untyped memory is exhausted; supply
  more and repeat |"

**Scenario.**

1. A node holds an untyped of 8 KB whose watermark stands at 4 KB.
2. It calls `untyped_retype` for a child `untyped` of 8 KB. By the rule of the
   call the memory is taken at the watermark, aligned up to the child's size, and
   the aligned start passes the end of the untyped.
3. No rule of the call covers that. The ordered list of line 146 names
   `no_memory`, but it also requires each call's own rules to list its state
   checks, and the rules of `untyped_retype` list none of this kind. The same
   hole is in `cspace_grow`, which takes a segment of 8 KB from the untyped by
   the rule of line 170.
4. Two builders therefore differ: one returns `no_memory` (the meaning of line
   1900), the other `invalid` (an argument that does not fit). A reference model
   cannot be checked against a call whose failure is not written, and the state
   code `no_memory` is reachable only through `aspace_map` and `iospace_map`.

**Smallest correction.** Add to the rules of `untyped_retype`: "If the object,
aligned, would pass the end of the untyped, the call returns `no_memory` and
nothing is taken or cleared." Add the same sentence to the row of `cspace_grow`
for its segment.

---

## 9. `iospace_map` can turn into a unit request, and its row has no state check for that — unsettled case

**Quotes.**

- Line 348: "| `iospace_map` | iospace, frame, untyped, device address, first
  page, page count, rights | | **As `aspace_map`, with these differences.** ..."
- Line 1028: "`iospace_map` writes only the owner's own tables and sends nothing,
  because a unit that reports caching mode 0 needs no invalidation when a
  translation is added; **if a unit reports caching mode 1 or needs write-buffer
  flushing, bit 0 of the flags of the entry `Memory` is set, and every
  `iospace_map` also asks the unit's**".
- Line 1737: "**Nothing here is a rule**: the rules are in the sections named."
- Line 1754, in that list: "| 32, 33 | `IoSpaceMap`, `IoSpaceUnmap` | unchanged |
  `Busy` on an unmapping record; an unmap waits for a unit request (*waiting for a
  unit*), `Busy` if the unit is found failed ([IOMMU](#iommu), D-131); `Again`
  with nothing changed if the unit request table is full (D-140) |"

**Scenario.**

1. A machine declares bit 0 of the flags of the entry `Memory` (a unit with
   caching mode 1).
2. A node that owns an iospace with such a device calls `iospace_map`.
3. By line 1028 the call asks the holder to invalidate, so it becomes a unit
   request: it can wait in *waiting for a unit*, can find the unit failed, and can
   find the unit request table full.
4. The row of the call, which inherits the checks of `aspace_map` "with these
   differences", states none of the three. Its neighbours `iospace_unmap` and
   `iospace_attach` state all three, and the only place that gives them for
   `iospace_map` is the list of line 1754, which declares itself no source of
   rules (line 1737).
5. So the order of checks of the call is not total: a builder cannot tell whether
   the unit checks come before or after the class `denied` and the record `busy`,
   nor what a failed unit returns.

**Smallest correction.** Add to the row of `iospace_map`: "When bit 0 of the
flags of the entry `Memory` is set, the call also asks the unit's role holder to
invalidate: it waits in *waiting for a unit*, returns `busy` if the unit is found
failed, and `again` with nothing changed if the unit request table is full; these
three come after the plain arguments and before the record `busy`."

---

## 10. `node_watch` calls its `node` argument "the core" — contradiction

**Quotes.**

- Line 1400: "| `node_watch` | **node**, index, notify | | `read` on the node,
  which must name the caller's node. Notify 0 unbinds |"
- Line 1445: "**`node_watch`.** Order: **the core** (slot, kind, `read`, then that
  it names the caller's node, `invalid`); the notify if not 0 (slot, kind,
  `send`, then that it belongs to the caller's node, `invalid`); the index below
  4 (`invalid`)".
- Line 1206, the core word: "| 16-31 | **the node slot** (0xFFFF for none) |"

**Scenario.** The contract keeps a node and its cores apart everywhere: a core
word's field names the node its core belongs to (line 1206), and no object of
kind `core` exists in the table of calls (line 1400 names a `node` argument). In
"the core (slot, kind, `read`, then that it names the caller's node)" the
argument is asked to *name a node*, which only the node capability does. A reader
who takes the sentence literally looks for a core capability that the call's own
row does not have, and the two sentences cannot both be satisfied.

**Smallest correction.** In line 1445, "the core" becomes "the node".

---

## 11. A fault that is delivered and then dropped leaves no record — unsettled case

**Quotes.**

- Line 429: "**Delivery is a `call`** by the faulting thread on its fault
  endpoint, with an empty receive range and wait number 0."
- Line 469: "**A fault wait that ends without an answer** leaves the thread
  suspended, with its registers as at the fault, and **drops the fault**. This
  happens when the endpoint or the reply object is destroyed (`gone`), or when
  `thread_cancel` is called with wait number 0."
- Line 482: "word 0 holds in bits 0-31 **the kind of the fault recorded in the
  thread (0 if none)** ... **A fault is recorded when it is not delivered** (no
  handler, or a fault *no context* that found no receiver with an own context),
  and the record is cleared when the thread is resumed".

**Scenario.**

1. A thread faults and a receiver waits on its fault endpoint, so the fault is
   delivered (line 429).
2. The supervisor destroys the fault endpoint, or calls `thread_cancel` with wait
   number 0.
3. The wait ends without an answer: the thread stays suspended with its registers
   as at the fault, and the fault is dropped (line 469).
4. The supervisor now calls `thread_read_regs`. Line 482 records a fault only
   when it was *not* delivered, so word 0 is 0 and words 1-5 are 0, and this
   thread cannot be told apart from one suspended by `thread_suspend` after no
   fault at all. The state exists in the text — "the fault was delivered and then
   dropped" — and no rule assigns it a record or refuses one.

**Smallest correction.** Add to line 469: "and a fault so dropped is recorded as
a fault that was not delivered is".

---

## 12. `sched_read` reports a state bit that no list defines — unsettled case

**Quotes.**

- Line 543: "The state word has bit 0 configured, bit 1 throttled, bit 2 has a
  home, bit 3 lent (its chain is not empty), **bit 4 counted**, bits 8-15 1 + the
  last hardware class or 0 ... Instructions is the count of `sched_count`, 0 when
  counting is off."
- Line 1726: "`SCHED_STATE_CONFIGURED = 1 << 0`, `SCHED_STATE_THROTTLED = 1 << 1`,
  `SCHED_STATE_HOME = 1 << 2`, `SCHED_STATE_LENT = 1 << 3`."
- Line 2283: "Numbers (error codes, bits of the rights, kinds, calls, layout of
  the header) are defined in `abi/`, which is **the reference for values**; this
  document names them."

**Scenario.** A user-space scheduler reads bit 4 of the state word of
`sched_read` to know whether counting is on; counting is turned on and off by
`sched_count`. Bits 0 to 3 have named constants (line 1726) and no constant is
given for bit 4, in that list or in the `Changes` list. Since line 2283 makes
`abi/` the reference for values and this document their namer, the one bit a
scheduler needs to read `instructions` correctly is the one value that is named
in prose and nowhere else. A port that passes the four constants on and takes
`1 << 4` from the prose is guessing a number in the ABI.

**Smallest correction.** Add "`SCHED_STATE_COUNTED = 1 << 4`" to line 1726.

---

# What I checked and found sound

Each of these I recomputed or re-derived from the text and then re-read in the
file.

- **The number of calls.** Line 52 says "64 calls", the table of calls counts 64,
  and line 1739 says the same after the two replacements: "There are still 64
  calls: the two removed calls give their positions to the two new ones".
- **The rights words.** Line 137: "`cap_inspect` of a root returns 0xFF or 0xFB,
  of a kept frame of the kept image 0x45 (`read`, `exec`, `derive`), and of
  another kept frame 0x41 (`read`, `derive`)" — consistent with eight rights at
  bits 0-7 and with the exceptions the paragraph lists for `exec`.
- **`RFLAGS_USER_MASK = 0x0024_0DD5` and `RFLAGS_FIXED = 0x202`** (line 1729) are
  the ten flags the text names (CF, PF, AF, ZF, SF, TF, DF, OF, AC, ID) with IF
  and bit 1 fixed, and nothing else.
- **The capability space.** A `cspace` of at most 2^20 slots clears 128 KB of
  directory at 16 bytes per 128 slots, a segment is 128 × 64 = 8 KB, and a full
  space is 2^20 / 32 = 32,768 calls of the removal's 32 units (lines 111, 603).
- **The sizes of limits.** `SLOT_BYTES = 64`, `CLEAR_STEP_BYTES = 65,536`,
  `IDENTIFIERS_PER_SEGMENT = 65,536`, `IOSPACE_MAX_DEVICES = 16`,
  `MAP_COUNT_MAX = 2^32 − 1` (line 1723) — each is used consistently where the
  text refers to it, and 65,536 identifiers × 8 bytes is the 512 KB the machine
  table needs.
- **The interrupt table.** 64 bytes per claimable vector from 48 to 239 inclusive
  is 192 × 64 = 12 KB per core (line 1922, line 1729: `IRQ_VECTOR_FIRST = 48`,
  `IRQ_VECTOR_LAST = 239`, `IRQ_TABLE_ENTRIES = 192`).
- **The debug area.** 69,632 bytes is 17 × 4,096 (line 1531), and the object-size
  table repeats it (line 1927: "69,632 bytes per physical core, in each of the two
  crash areas"); the kernel ring of 256 × 64 and the user ring of 768 × 64 fit
  inside it after the 64-byte header.
- **The fence record.** `FenceRecord`, 544 bytes, 68 words, of which 64 are one
  per core (line 1792; `CORES_PER_KERNEL_MAX = 64`, line 1776) — the size and the
  field count agree.
- **The messages.** A `Report` of 28 items is 1 + 3 × 28 = 85 words, inside 11
  entries of 64 bytes (704 bytes = 88 words), which is what lines 960, 968 and 975
  say; a `Send` of 64 words and 4 grants is 71 words, inside 10 entries; the
  reserve of answers is `REQUESTS_PER_PEER` + `SENDS_PER_PEER` + 10 = 34.
- **The queue height.** 2 × ⌈log2(*N* + 1)⌉ at 2^32 objects is 66, as line 603
  states.
- **The thread.** 1,856 bytes rounded up to 2 KB, from the fixed part of 1 KB and
  its other parts (line 1918).
- **The times.** 2^63 ns is about 292 years (line 498), 2^36 ns is about 68 s,
  1/64 of a 10 ms period is 156 µs, and the start-up `sched` of 9,843,750 ns in a
  period of 10 ms is 63/64 of a core (line 2070).
- **Admission.** *u* = ⌈*B* × 2^32 / *T*⌉ with the whole core at 2^32 and the sums
  the text forms (line 549) are consistent with `ADMISSION_WHOLE_CORE = 1 << 32`
  (line 1726) and with the start-up context's 63/64 of a period plus the recovery
  reserve.
- **The firing instant.** With tolerance 0, *x* is the deadline, *m* is the index
  of its lowest set bit, and clearing the *m* lowest bits of the deadline leaves
  it unchanged, so the timer fires at its deadline and never early — which is what
  the rule at line 634 asks for.
- **Two state machines I could not break.** The `irq` object (idle, armed, fired,
  plus the pending bit of an edge source) has a rule for bind, unbind, arrival,
  ack, a dying notify and destruction, and none of them contradicts another. The
  member word's eight states have a transition for every event I could construct,
  including a sealing node that returns to live, a start that fails and a resume
  from sealed, and the reserved core state *leaving* is excluded by a rule rather
  than left dangling (line 1202).
- **The park and start confirmations.** Requests are counts, raised before the
  mark; the start request keeps bit 63 so that slot 0 with generation 0 does not
  read as none; each architecture's rule for the bootstrap core matches the reason
  given for it.

# What I did not check

- **Every external fact.** No specification could be opened from here: the Intel
  SDM, VT-d, Arm's DDI 0487 and IHI 0069, PSCI, the SBI and AIA pages, and the
  citations to Linux, TF-A, gdb, OpenSBI and Asterinas. Nothing in this report
  says whether a quotation, a section number or a hardware behaviour is right.
- **Every document behind a link.** memory.md, kernel.md, drivers.md, roles,
  scheduling.md, security.md, agent.md, platform.md, storage.md and the research
  drafts: unread, so any sentence of this contract that leans on one is unchecked,
  and no rule here was compared with a rule there.
- **The `Changes for abi/` list as a whole.** I checked the values that also
  appear in the body of the contract (call numbers, `PageClass`, the start-up
  layouts, `FENCE_RECORD_BYTES`, `IRQ_MAX_CORES_REMAPPED`). I did not audit the
  list line by line, and I did not check it against `abi/`.
- **Most of the 64 calls' order of checks.** I traced the removal, the mapping
  calls, the `thread` calls, `node_start`, `node_watch`, the `irq` calls, the
  grant calls and `untyped_retype`, looking for a missing or a doubled check. The
  others I read but did not build a failing path for, so a gap in one of them
  would not have been seen, and I did not prove that every listed result of every
  call is reachable.
- **The cross-node protocol tables.** I read the attach word's table against its
  state list and spot-checked cells in the others; I did not fill the tables of
  the grant, the unit request, the hand-over, the start, the seal or the take-over
  cell by cell.
- **The whole of § on the gate over page tables and the formal models.** I read
  them once and re-read only the numbers; their arguments are not something I
  tested.
- **The text's claims about its own history** — the review findings and the
  decisions D-99 to D-140. I took the parenthetical references as pointers, not as
  facts.
