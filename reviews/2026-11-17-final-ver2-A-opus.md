# Verification of lot A of the second round (V2-A, Opus)

The report verified: `reports/v2-A-opus.md`. Its author attacked `dodos-kernel`
at head `6312868` (PR 3, branch `model`) with no access to the contract or the
decisions.

- My work copy: `/private/tmp/dodos-pr3-ver2-A-opus`, a fresh `cp -R` of
  `/private/tmp/dodos-pr3-final` (the copy I was told to make; nothing of the
  author's copy was read into it and nothing of their tests was copied).
- The contract: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
  (branch `main`), and the decisions `Docs/decisions/README.md`.
- Two test files of mine: `abi/tests/ver2a.rs` (16 tests) and
  `model/src/scenarios/ver2a.rs` (5 scenarios, `mod ver2a;` added to
  `model/src/scenarios/mod.rs`).
- Commands, from the copy, with `PATH=/nix/var/nix/profiles/default/bin:$PATH`:

      nix develop -c cargo test -p dodos-abi --test ver2a -- --nocapture
      nix develop -c cargo test -p dodos-model --lib ver2a -- --nocapture

  Result: 16 of 16 in `abi`, 5 of 5 in the model. A passing test means the
  weakness is there. The test profile keeps the overflow checks the workspace
  sets (`Cargo.toml`, `[profile.dev.package.dodos-abi] opt-level = 2`, checks
  on), so a panic is what a debug kernel would do.
- Fixes: where I say a fix makes a test fail, I applied it in my copy, ran the
  test, and reverted. Five of the corrections below were run that way; the
  others are stated as the function, the change and the test, without running
  the change. I say which is which.

Nothing in any repository was changed and nothing was committed; my copy is
dirty only by the two test files and the one added `mod`.

---

## The question the brief puts first: a header that names another node than the ring it came on

This decides finding 1, so it comes before it.

**What the contract says.** The paragraph "*One check on every message received
(D-124, completed by D-129 and D-131)*" (contract line 966) opens: "Every
message carries its kind, its length, its sender's node and generation, and the
generation of the receiver it was sent to". Every rule that follows is a
predicate on those carried fields: "the sender's member word is starting, live,
sealing or sealed with that generation"; "a `Send`'s stamp carries 0 ... or a
task identifier of the sender's node with a counter that is not 0". D-140
restates the tie the same way (line 1040, "What ties each request to its
requester"): "The receive check holds the sender's node and generation against
its member word ...; then each operation names something of the requester's,
which the holder's gate reads in a word written by gates". So the author is
right about the letter: the contract never tells the receiver to hold the
carried sender against the ring the message came on (`from`), even though the
receiver knows `from` for free (the ring index). D-129 and D-131 built the
whole check on the carried field. The model is faithful to that: `refused`
(`model/src/rings.rs:376`) has no ring parameter at all, and `consume` calls it
as `self.refused(&message)` while holding `from` in hand
(`model/src/rings.rs:515`).

**Does acting in another node's name stay inside what the gate promises?** The
promise is G, in "The gate over page tables": "So a kernel bug in *X* can
corrupt *X*'s memory, *X*'s devices and what *X* was granted, and nothing else:
the unit of failure that D-107 and D-115 already accept. A faulty kernel is
bounded to its own memory without two-stage translation (D-117)." D-120 point 2
extends the gate's scope to "what reaches memory or another core without the
page tables: IOMMU tables, interrupts sent to another core, the sensitive
ports, firmware calls".

Three scenarios, and the answer is not one answer. All three are run below as
tests, on the model, with the attacker on node 2, the victim receiver node 1
and the third node whose name is used node 0.

1. **A `Send` in another node's name — inside.** The effect is a delivery to
   node 1's thread carrying node 0's task and marks, plus availability. The
   paragraph admits exactly this: "The marks of a stamp are as the sending
   kernel states them: kernels trust each other's stamping as they trust each
   other's checks; a kernel that lies about marks is faulty, which the gate does
   not contain (it damages the marks of what it sends and availability, never
   another node's memory)". No byte of another node's memory is reached: the
   frames the message lists are the attacker's own grants, and the use entries
   node 1 writes are node 1's own table. So this one is intended by the
   contract; what a receiving service may infer from a stamp is the marks
   problem, not the gate's.

2. **A `UnitRequest` in the owner's name — outside.** My test detaches node 0's
   device through node 1. G spoken per node is not broken: node 1's own gate
   writes node 1's own IOMMU tables, page classes and words, and every
   translation node 1's cores can use still leads only where G allows. What
   breaks is the sentence G is summarised by for a *faulty kernel's reach*: node
   2 changed another node's device state (the context entry of device 0x10 and
   node 0's attach word, which now reads *detached* while node 0's kernel
   believes it attached) and wrote rows of the living machine table of node 1.
   D-120 point 2 names IOMMU tables in the gate's scope precisely so that a
   faulty kernel cannot reach them; it reached them through another node's gate.
   The only reason it could is that node 1 could not tell node 2 from node 0.

3. **An answer in another node's name — outside, and worse.** My third test
   ends node 1's wait for node 0's answer with a forged `SendAnswer` and takes
   node 1's credit toward node 0. The credit is the handle of the one-shot
   protocol: `RevokeStep`, `UnitAnswer`, `Report` and `SendAnswer` are applied
   on the strength of it. The same forgery with `RevokeStep { removed: true }`
   is what frees a frame: the granter's gate lowers the counts and frees a
   frame that *node 0* still translates, and the frame may then be given to a
   fourth node — which does break G, at the fourth node. The gate's "not
   covered" list admits this for the grantee: "a grantee's kernel that is faulty
   in its messages about a grant (its `Release`, `RevokeStep`, `SendAnswer` and
   use index), which can make the granter free a frame it still translates". It
   admits the grantee, the node the frame was granted to, which is the node the
   credit is toward. Here the credit is node 1's toward node 0, and node 2,
   which holds no grant at all, destroys node 0's grant. That admission does not
   cover it.

So: scenario 1 is intended; scenarios 2 and 3 are outside what the gate
promises. The check as written cannot tell the three apart, because it never
looks at the ring. The smallest correction is one rule in the check, in the
contract and in `refused` alike; I ran it and it makes the tests fail (finding
1, correction). The author's severity ("exploitable") is right for 2 and 3; for
1 alone it would be low.

---

## Finding 1. The sender is taken from the header, not from the ring it came on

**What I opened.** `abi/src/ring.rs:187-199` (`RingHeader`, `sender: u16`, and
`sender_generation: u32`); `model/src/rings.rs:376-460` (`refused`, whose first
act is `let sender = header.sender;` and which has no `from`);
`model/src/rings.rs:489-491` (`consume(from, user, step)` reads ring `from` and
calls `self.refused(&message)`); `model/src/rings.rs:612-613`
(`let from = message.header.sender;` in `receive_message`, which is what every
handler is given); `abi/src/lib.rs:738` (the promise to user space: "What the
kernel sets on every received message. The sender cannot forge any of it." —
read, and it is about the fields of a received message, not about the sender's
identity); `model/src/units.rs:252-331` (`operands_allowed`, whose `from` is
`(from, generation(from))` taken from the header at `units.rs:529`).

**My tests.** Three, all reaching the state the way a faulty kernel does: it
writes into a ring it owns, through the harness's own `System::inject(from, to,
message)`, which writes on ring `from → to` and interrupts the target. Nothing
in them writes a model field except the test of finding 3.

    scenarios::ver2a::ver2a_a_detach_written_on_a_third_nodes_ring_in_the_owners_name_detaches_the_device
    scenarios::ver2a::ver2a_a_send_written_on_a_third_nodes_ring_in_another_nodes_name_is_delivered_as_that_nodes
    scenarios::ver2a::ver2a_an_answer_written_on_a_third_nodes_ring_in_another_nodes_name_is_applied

Each is written so that the honest version of the same message is refused in the
same test first, which is the control: naming itself, the attacker gains
nothing.

Output (`--nocapture`):

    refused by the holder: 1
    attach word after the forged detach: Some(Detached)
    the unit's entry of the device: None
    delivered to node 1: Some(Ok(Message(Delivery { received: Received { header: Header(4294967303), badge: 0, marks: Marks(0), task: 1 }, words: [7] })))
    the serial that ended node 1's wait: Some(1)
    node 1's credits toward node 0: 0
    node 1 woke with: Some(Ok(Sent { flags: 0 }))

The detach test: four nodes, three IOMMU units, node 0 attached device 0x10
through role 0, held by node 1. The detach in node 2's own name is refused
(`refused by the holder: 1`) and the attach word still reads *attached*; the
same operation on the same ring with `sender = (0, g0)` in the header detaches
it (`Some(Detached)`, and the unit's context entry is gone). Every step asserts
the whole check (`S::call`, `S::settle`, `S::run` all compare `check()` with
`Ok(())`), so no invariant covers this.

The send test: three nodes, node 1's first thread waits to receive. The `Send`
in node 2's own name is refused (its stamp names node 0's task). The same
message with `sender = (0, g0)` in the header is delivered to node 1's thread as
node 0's task 1.

The answer test: node 0's core is stopped (`System::hang`), so node 1's
`NodeSend` to it waits and the answer never comes. Node 2 then writes
`SendAnswer { delivered: true }` naming node 0, guessing the credit: serial 0
is refused, serial 1 is accepted, node 1's wait ends with `Sent { flags: 0 }`
and its credit toward node 0 is taken (`0` left). Node 1's node block is not
shared, so the guess is the attack: 16 indices and a small serial space, and a
wrong guess costs one refused message.

**The contract.** The paragraph quoted at the top. Also line 972 ("Credits"):
"A credit is in use from the moment its message is written into the ring until
the sender has consumed its answer". Line 1040 (D-140): "The receive check
holds the sender's node and generation against its member word".

**Verdict.** **Real, the contract's fault.** The model does what the contract
says — the check is on the carried sender — and the guarantee breaks in two of
the three scenarios: the gate's summary ("a kernel bug in *X* can corrupt *X*'s
memory, *X*'s devices and what *X* was granted, and nothing else") for the unit
operation, and G itself for the answer that frees another node's frame. Severity
**high**: a faulty kernel of one node acts on the devices of a second and on the
grants between the second and a third, and the answer forgery needs only a
guessable credit.

**Correction.** Contract first, then the model, one rule each.

- The contract, one clause in the paragraph "One check on every message
  received" (line 966), among the checks before "by kind": "and the message came
  on the ring of the pair from its sender: the sender it carries is the node of
  the ring it was read from." The smallest that closes it is that sentence; it
  costs one comparison per message received — nothing at all, since the receiver
  has `from` already and compares two `u16`s; no new state. It must be added to
  the paragraph and to D-140's "What ties each request to its requester", which
  restates the tie.
- The model, `Model::refused` (`model/src/rings.rs:376`): take the ring's sender
  as a parameter and refuse first thing — `if sender >= self.table.nodes ||
  sender != from { return Some(0) }` — and pass `from` at the one call site
  (`rings.rs:515`). `receive_message` then has the ring's sender without reading
  the header, and the `who` word of the trace may keep `from`. The test that
  fails without it: the three tests above. I ran this change: with it, the
  detach test fails (`attach word after: Some(Attached)`, entry still
  `Some((0, 1))`), the send test fails (`node 1 receives it: None`) and the
  answer test fails (node 1's wait never ends); the four direct callers of
  `refused` in `scenarios/crossing.rs:579-584` take the new argument and compile
  (I did not rerun that file's tests, so I claim they compile, not that they
  pass).
- `abi/` needs nothing: the field stays, its meaning becomes "the sender's node,
  which the receiver checks against the ring".

---

## Finding 2. A user watchpoint the kernel's own access hits is the kernel's, on ARM64

**What I opened.** `abi/src/aarch64.rs:186-215` (`class_use`), and the constant
it uses, `EC_WATCHPOINT_SAME = 0x35` (`aarch64.rs:108`): `EC_BREAKPOINT_SAME |
EC_STEP_SAME | EC_WATCHPOINT_SAME` are in the arm that returns `NotThread`.
`abi/src/lib.rs:804-807`: `NotThread` is "a bug of the kernel (it accuses
itself, evidence self) or a hardware error, handled by the recovery of the
node". `model/src/faults.rs:193-200` (`thread_write_regs`: `REG_DR0..=REG_DR3 =>
word >= user_end`), which lets a thread name any breakpoint address inside its
own range. The model has no hardware-breakpoint match at all (`grep
HardwareBreakpoint model/src` finds only the fault kind at `faults.rs:24,31`),
so nothing in the model fires a `#DB` or a watchpoint.

**My test.**

    abi/tests/ver2a.rs::ver2a_a_watchpoint_at_the_kernels_own_level_is_not_the_threads

It asserts `exception_use(0x35 << 26) == Some(ExceptionUse::NotThread)` and, for
contrast, `exception_use(0x34 << 26) == Some(Fault(HardwareBreakpoint))`. It
passes. That is only the classification; the scenario needs the hardware.

**The hardware premise, checked.** The author left it "from memory, not checked
against the Arm ARM in this review". I checked it in the Arm Architecture
Reference Manual, D2.9 "Watchpoint exceptions" (I had the PDF text of DDI 0487
K.a, 2024, `/private/tmp/armka.txt`; the contract cites M.d, and this rule is not
one the 2024 and 2026 editions differ on): "The PAC control relates to the
privilege of the memory access, not to the Exception level at which the access
was made: Load unprivileged or Store unprivileged instructions executed at EL1,
or executed at EL2 when HCR_EL2.E2H is 1, are treated as unprivileged EL0
accesses", with the example "if the PE executes a Load unprivileged or Store
unprivileged instruction at EL1, the resulting data access triggers a watchpoint
only if both: PAC is programmed to a value that generates watchpoints on EL0
accesses" and "Example A64 Load unprivileged and Store unprivileged instructions
are LDTR and STTR". A watchpoint that fires so is taken without a change of
level, i.e. with `EC = 0x35`, which is what the table calls `NotThread`.

So the attack works if the kernel touches a thread's memory with `LDTR`/`STTR` —
which is the ordinary way to copy to and from a user address space, and which
the contract does not name anywhere (`grep LDTR STTR` over `Docs/architecture`
finds nothing), so the contract neither requires it nor forbids it. The other
input the attack needs, a watchpoint whose PAC admits EL0 accesses, is the
thread's own: `StartDebug` publishes `watchpoints` (`abi/src/start.rs:452`) and
the thread's watchpoint control is part of its state.

**The contract.** Two sentences disagree, and that is the defect. The kind 9 row
of Faults promises the thread's watchpoints to the thread: "hardware breakpoint |
9 | ... | breakpoint or watchpoint from a lower level (0x30, 0x34); word 3 the
bits of the thread's breakpoints or watchpoints that hit". And the ARM64 bullet
of the same section says: "every class taken at the kernel's own level (0x21,
0x25, 0x31, 0x33, 0x35), every AArch32 class ... is a bug of the kernel, which
accuses itself (evidence self)". And "self" evidence stops the node: "The node
beacon of *X* has `panic` ≠ 0 with *X*'s generation. A core of *X* writes it
when it finds a failure in *X* (a kernel assertion, a double fault, an unexpected
exception in kernel mode, ...)" (Detection: evidence, not opinion). So a thread
that sets a watchpoint on its own message page stops every thread of its node.

**Verdict.** **Real, the contract's fault** for ARM64: the model (and the
classifier it is written from) does exactly what the contract says, and the
guarantee that breaks is the contract's own promise that the thread's watchpoint
is delivered as kind 9 to the thread — instead the whole node is accused. It
depends on an implementation premise the contract leaves open (the kernel's
copies with `LDTR`/`STTR`), which is why I give it **medium**: in a kernel that
copies with ordinary loads it does not fire; in one that uses the unprivileged
forms, any thread stops its node.

- **x86-64 half: not run, with the reason.** The model holds no debug-register
  match, so no test can reach a `#DB`; and `abi/` has no classification table for
  x86-64 exceptions (the kernel's own reading decides). The premise is real
  (`dr7_valid` accepts a data breakpoint on any user address, and Intel's DR0-DR3
  data breakpoints have no privilege qualifier: SDM §20.2.5 "A data breakpoint
  for reading or writing data is triggered if any of the bytes participating in
  an access is within the range defined by a breakpoint address register and its
  LENn field"), so a kernel write at CPL 0 to a user address a thread watches does
  raise `#DB`; the contract's kind 9 row then makes it the thread's, with word 0
  "the faulting instruction" — which at CPL 0 is the *kernel's* instruction. What
  a handler does with that, and what leaks, the contract does not say. This is
  real as a gap in the contract, **low** until a rule exists; the model cannot be
  blamed for what it does not model.

**Correction.**

- Contract, `#### Faults`, the ARM64 bullet (line 459): remove `0x35` from the
  list "every class taken at the kernel's own level (0x21, 0x25, 0x31, 0x33,
  0x35)" and add one sentence to the same bullet: "0x35 is the thread's, as kind
  9, when `FAR_ELx` (`FnV` = 0) lies in the faulting thread's user range: a load
  or store unprivileged instruction executed at EL1 is an EL0 access for
  watchpoint matching (Arm DDI 0487, D2.9), so the class says nothing about which
  level made the access." Cost: one read of `FAR_ELx` and a comparison on a
  watchpoint exception only — never on an ordinary access, so nothing on
  G's cost path; no new state (the thread's range and its watchpoints are
  already known).
- Contract, same section, the x86-64 bullet: one sentence, "a `#DB` whose DR6
  bits name one of the thread's breakpoints and whose faulting instruction is
  the kernel's own access to the thread's memory is kind 9 with word 0 the
  thread's interrupted instruction; the kernel's access resumes when the thread
  does" — the smallest that closes it, no new state, cost one comparison on a
  `#DB`.
- Model: nothing to change in what it holds. `aarch64::class_use` is right for a
  class taken by the kernel's own code; the decision needs the address, so the
  kernel's fault path must ask `FAR_ELx` first, and `abi/` gains one pure
  function for it if the contract's sentence lands (a Kani proof over the two
  words; AGENTS.md asks for one). The test that fails without the model change is
  none — there is no model change — so the guard for this finding is the
  contract's sentence, and the abi test above pins the classification it must
  stop short of.

---

## Finding 3. A next sequence left in a kept debug area panics the next writer

**What I opened.** `abi/src/debug.rs:76-80`: "The entry of sequence `seq` (at
least 1) sits at index (seq − 1) mod `entries`", `(seq - 1) % entries`.
`model/src/debug.rs:88-95` (`write`: `let seq = *next; ... trace_index(seq,
entries); *next = seq + 1;`) and `model/src/debug.rs:262-276`
(`enter_debug_areas`, whose line 271 keeps an area "if the area's magic and
version are right" and goes on from `next_kernel`/`next_user`).

**My test.** `scenarios::ver2a::ver2a_a_next_sequence_of_0_left_in_a_kept_debug_area_panics_the_next_writer`,
plus `abi/tests/ver2a.rs::ver2a_trace_index_of_sequence_0_panics`.

The model test does the whole sequence, not a field: node 0 runs on core 0 and
traces (its area reads `next_kernel 2`), node 1 kills it, the core is reclaimed,
and the area is left *as the faulty generation left it* — I set `next_kernel` and
`next_user` to 0 in it, which is the one input in this report that is a field
write rather than a call, because the model has no call that writes a kernel's
own memory: the write is a faulty kernel writing its own core's area, the class
of input `edit_table` exists for, exactly as `System::inject` stands for a
faulty kernel's ring writes. Then node 1 starts node 0 fresh on core 0.

Output:

    kept area: magic 0x62446f44 version 2 next_kernel 2 next_user 1
    thread '...' panicked at abi/src/debug.rs:79:5: attempt to subtract with overflow
    the next node's first trace: Err(Any { .. })

and, from the abi test, `trace_index(0, 4032)` → `Err(Any { .. })` at
`abi/src/debug.rs:79:5`. So the next node's first trace panics with the sequence
the previous generation left. (`u64::MAX` panics one step later, at
`*next = seq + 1`, `model/src/debug.rs:94`.)

**The contract.** `#### What the kernel keeps for debugging`, "Across nodes and
generations": "An area belongs to its core for the whole boot, whatever node runs
there: a core that starts in a node keeps its area, and if the header's magic and
version are right it sets the node slot and generation and **goes on from the next
sequences found there**, otherwise it clears the area and starts at 1. It reads
nothing else from the area". And the trace ring's own rules: "Word 0 | the
sequence *s*, at least 1"; "When the ring is full the oldest entry is overwritten:
**writing never fails and never waits**."

**Verdict.** **Real, the contract's fault.** The model does what the sentence
says — magic and version right, go on from the next sequences — and two
guarantees of the same section break: a sequence of 0 (the contract says "at
least 1"), and "writing never fails". Severity **low**: it costs a panic only in
a build with overflow checks (a model, a development kernel — the contract's
"two builds" section) and in a release kernel the index wraps and an entry of
sequence 0 is written, which "a reader keeps only if both reads give s" never
keeps: silent loss of one trace entry, no memory unsafety. What it buys the
attacker is the whole next node: a panic is a self-accusation, and every thread of
the node stops.

**Correction.**

- Contract, that sentence: "…and goes on from the next sequences found there
  **unless a next sequence is one this boot cannot have written — 0, or so large
  that the next entry's sequence would not fit — in which case it clears the area
  and starts at 1**". Smallest that closes it; cost one comparison per ring at
  each start of a core, nothing on the trace path; no new state (it reads what it
  already reads).
- Model, `Model::enter_debug_areas` (`model/src/debug.rs:271`): add to the
  condition `|| area.next_kernel == 0 || area.next_user == 0 || area.next_kernel
  == u64::MAX || area.next_user == u64::MAX`, so an area it cannot continue is
  cleared like one with a wrong magic. The test that fails without it: the
  scenario above. I ran this change: the start then succeeds (`the next node's
  first trace: Ok(())`) and my test fails, as it should.
- `trace_index` (`abi/src/debug.rs:78`) keeps its documented domain; if a caller
  can still hand it 0, its doc should say that 0 is not a sequence and the caller
  clears — not that the function is total. A Kani proof over `seq >= 1` already
  follows from the code; the domain is the caller's, and this is the caller's
  bug.

---

## Finding 4. `Geometry::valid` overflows on a boot image's page shift

**What I opened.** `abi/src/lib.rs:492-520` (`valid`), the line at 504:
`if s[i] != 0 && (s[i - 1] == 0 || s[i] != s[i - 1] + per_level || i > 2)`, and
`model/src/boot.rs:629-637` (`layout` calls `geometry.valid()` first and returns
`Refusal::MachineValues` on false).

**My test.** `abi/tests/ver2a.rs::ver2a_geometry_valid_overflows_on_a_large_page_shift`:
`page_shift [12, 250, 30, 0]`, `entries = 512`, `levels = 4`, `user_end` the
reference machine's. Output: `panicked at abi/src/lib.rs:504:55: attempt to add
with overflow`, `valid() on page_shift [12, 250, 30, 0]: Err(Any { .. })`. The
same values with `s[1] = 0` are refused in words (`!valid()`), which is what the
loop would have said had it not run past a false `sizes`.

**The contract.** "Values of the machine" (line 99): "*E* is the number of 8-byte
entries of one page (*P* / 8), and at most 4,096 ... **The kernel refuses to start
on a machine whose page would need more** (design choice: the 64-byte slot stays
as it is)", and the refusal list (line 1645) has "6 machine values out of range",
with "The kernel refuses to start, with a stop record ... and, if the boot image
declares a console, a message on it, if:" (line 1994). Also "Values of the
machine", line 100: "each page size is *E* times the one before ... and exists
only if *i* < *L*; the first large page, the chunk, is required."

**Verdict.** **Real, the model's fault** (`abi/` is the contract in code and the
model builds on it). The contract does not allow a panic where it has a refusal
with a stop record and a console message: the value is a boot image's, and the
kernel's answer to a bad one is `MachineValues`, which `layout` is ready to
return. Severity **low** — the attacker is the boot image, which is signed, so
this is a robustness bug, not an attack; in a build without overflow checks the
sum wraps, `sizes` becomes false, and the geometry is refused.

**Correction.**

- Model, `Geometry::valid` (`abi/src/lib.rs:492`): the shape rule is "none after
  a missing one", so `let mut sizes = ...; if !sizes { return false; }` before the
  loop — that is the contract's sentence exactly, and the loop then never adds to
  an unchecked `s[i - 1]`. If the loop is kept, the smallest change at line 504 is
  `s[i] != s[i - 1].saturating_add(per_level)` (a sum that overflows is never a
  valid `u8` shift, so `sizes` is false either way). The test that fails without
  it: the one above. I ran the `saturating_add` form: `valid()` returns false
  instead of panicking and my test fails. Cost: nothing; no new state.

---

## Finding 5. `module_frames` on a module's length or address

**What I opened.** `abi/src/machine.rs:1284-1345` (`module_frames`,
`end: len.div_ceil(page) * page` at 1311, `let mut best = PageSize::Page;` at
1325, `(self.phys + offset).is_multiple_of(bytes)` at 1320);
`model/src/boot.rs:690-712` (the kept image's layout, `at +=
len.next_multiple_of(page)`).

**My tests.** `abi/tests/ver2a.rs::ver2a_module_frames_overflows_on_a_length_and_on_an_address`
(prints `attempt to multiply with overflow` at `machine.rs:1311` for
`len = u64::MAX`, and `attempt to add with overflow` at `machine.rs:1325` for
`phys = 2^64 − 4096`), `ver2a_module_frames_of_an_unaligned_address_are_unaligned_pages`
(`module_frames(phys = 0x1234)` gives `ModuleFrame { size: Page, pages: 2,
offset: 0 }`), and
`scenarios::ver2a::ver2a_a_file_of_the_boot_image_longer_than_memory_panics_the_layout`
(`a file of 2^64 - 11 bytes: Err(Any { .. })` — `attempt to add with overflow`
in `core::num`, from `boot.rs`; `a file of 2^45 bytes: Err(Floors)`).

**The contract.** Rule 5, "Kept frames": "A module is covered by a run of kept
frames in consecutive slots: at each position the kernel takes the largest page
size that the processor supports, on which the physical address of the position
(and, for a segment, its virtual address) is aligned ... **No module is refused
for its size.**" And the loader's side, line 1994: "The first stage lays out the
modules in order, **each on a page boundary**, from a physical address aligned on
2^*k*."

**Verdict.** Split.

- **The unaligned address: refuted.** The contract fixes the domain the
  function's doc names ("at each position the largest supported page size on
  which the physical address (and, for a segment, the virtual address) is
  aligned"), and the model's `layout` builds every module at
  `at.next_multiple_of(large.unwrap_or(page))` from an aligned `image_base`, so
  no caller can hand `module_frames` an unaligned address. The frames are
  unaligned only for an argument no contract-conforming caller passes; the doc
  should say so, but nothing is broken.
- **The overflow: real, the model's fault.** The contract has a refusal for a
  layout that does not fit ("the floors, the reserves and the kept memory do not
  fit", refusal 5 in the start-up list) and a start-up that refuses "with a stop
  record ... and a message on it" (line 1994). The model panics before it can
  refuse, in `boot.rs` rather than in `module_frames`, as the author says.
  Severity **low**: the boot image is signed, so this is a robustness bug in the
  start path, not an attack — and "No module is refused for its size" makes the
  intended answer a refusal of the *layout* on the sizes it cannot place, not a
  refusal of the module.

**Correction.**

- Model, `Model::layout` (`model/src/boot.rs:703-707`): replace the two additions
  with checked ones and return `Refusal::MachineValues` (or the more exact
  refusal 5) when they fail — I ran this: `let Some(next) =
  len.checked_next_multiple_of(page).and_then(|bytes| at.checked_add(bytes)) else
  { return Err(Refusal::MachineValues) }`, and the test above then fails because
  the layout returns `Ok(true)` (that is, `is_err()`), as it should.
- Model, `module_frames` (`abi/src/machine.rs:1311`, `1320`): `end` and
  `phys + offset` with `checked_*`/`saturating_*`, or the doc's domain stated and
  checked — "phys and virt on a page boundary, and `phys + len` below 2^64" — with
  no frame yielded outside it. The test that fails without it: the abi test
  above. Cost: nothing on any path the model or a kernel takes; no new state.

---

## Finding 6. An MSI aimed directly at APIC ID 255 is accepted

**What I opened.** `abi/src/x86_64.rs:134-141`: `msi_direct(apic_id, vector)`,
`if apic_id > 255 { return None }`, then `Some((0xFEE0_0000 | (apic_id as u64) <<
12, vector as u64))`.

**My test.** `abi/tests/ver2a.rs::ver2a_msi_direct_accepts_the_broadcast_apic_id`:
`msi_direct(255, 0xEF) == Some((0xFEEF_F000, 0xEF))`, `msi_direct(256, ..) ==
None`. It passes.

**The hardware premise, checked** (the author left it "from memory"): Intel SDM,
order 325462-093, Vol. 3, §13.6.2.1 "Physical Destination Mode": "either a single
destination (local APIC IDs 00H through FEH) or a broadcast to all APICs (the
APIC ID is FFH) may be specified in physical destination mode." The MSI address
bits 19:12 carry that destination in physical destination mode, so an MSI
composed for APIC ID 255 is a broadcast to every local APIC on the machine, and a
redirection entry's 8-bit destination field has the same meaning.

**The contract.** Interrupts, line 814: "A core whose APIC ID is greater than 255
cannot be reached this way (`unsupported`), for an MSI and for a line alike, since
a redirection entry in physical destination mode holds an APIC ID of 8 bits
(D-137)."

**Verdict.** **Real, the contract's fault.** The model implements the contract's
sentence faithfully, and the sentence is wrong by one value: an APIC ID of 255 is
*not* a reachable core, it is the broadcast. A driver that claims an MSI on such a
core interrupts every core of every node — availability for every other node, and
interrupts arriving on vectors no node has a claim for. Severity **low**: it needs
a machine with a core of APIC ID 255 (a 256-core machine, or a firmware numbering
that reaches it) and no interrupt remapping, which the contract says is the normal
case and drivers.md requires.

**Correction.**

- Contract, line 814: "A core whose APIC ID is 255 or greater cannot be reached
  this way (`unsupported`) ... since destination FFH in physical destination mode
  is the broadcast to all APICs (Intel SDM, Vol. 3, §13.6.2.1) and a redirection
  entry holds an APIC ID of 8 bits". Cost: nothing; no new state. The same bound
  must be said for a line's redirection entry, whose `Redirection` operands
  (line 1039) name an APIC ID for a core "whose word names the requester" — the
  bound is one comparison at the claim.
- Model, `abi/src/x86_64.rs:137`: `if apic_id >= 255`. The test that fails
  without it: the one above. I ran it: my test fails at its first assertion. Note
  that `abi/src/tests.rs` pins `msi_direct(255, 239)` as accepted, so that pinned
  test changes with the contract — it is a pinned value of the contract, not a
  guard, and changing it with the contract is not weakening a test.
- The `Redirection` half is **not run**: the model's check
  (`model/src/units.rs:355-362`) accepts a `Direct` target whose `apic` is a core
  of the machine, and the model's example machine has no core of APIC ID 255, so
  no scenario reaches the broadcast; the one comparison belongs next to the
  contract's sentence.

---

## Finding 7. Decodings that accept what no constructor writes

**My tests**, all in `abi/tests/ver2a.rs`, all passing:

    ver2a_a_handing_role_word_with_nobody_is_accepted
    ver2a_an_owner_node_of_0xffff_reads_as_unclaimed
    ver2a_a_credit_index_past_the_credits_is_read_as_one
    ver2a_a_gate_word_takes_more_pages_than_a_chunk_of_512_has
    ver2a_dr7_accepts_an_execution_breakpoint_with_a_length

Output: `held(ROLE_NOBODY): Some(RoleWord(34359738365))`, `credit index 24..
30: Some((n, 5))`, `not_data 4000 on a chunk of 512 pages:
Some(GateWord(17179869184001))`, `dr7 0xc0001: true`,
`taken(Node(0xFFFF)) -> Unclaimed, from_raw Some(Unclaimed)`, and
`Node(2000)` reads `Unclaimed` too.

What I opened: `abi/src/machine.rs:1136-1145` (`RoleWord::from_raw`, `2 => true`,
and `1 => word.target() == ROLE_NOBODY` which does not look at the holder);
`machine.rs:484-490` (`Owner::code`, unchecked) and `575-582`
(`Ownership::owner`, whose `None` becomes `Unclaimed`), with `may_take`'s
`Owner::Unclaimed => true` at `machine.rs:598-621`; `abi/src/ring.rs:225-232`
(`credit`, `index == CREDIT_NONE` only); `machine.rs:318-323`
(`GateWord::from_raw`, `(raw >> 32) as u16 > 1 << 12`); `abi/src/x86_64.rs:98-110`
(`dr7_valid`: the mask and the I/O condition only).

**The contract.** Role words, "The role word": "bits 0-1 the state (0 vacant, 1
held, 2 handing); bits 2-17 the holder ...; bits 18-33 the target (handing only,
otherwise 0xFFFF)". Ownership, "the ownership words": "A node *X* of current
generation *g* may write *taken* (*X*, *g*) into a word that is free or taken and
whose owner is: ... 2. unclaimed", and "Any other owner is refused". Credits:
"Each node keeps in its node block, for each peer, `REQUESTS_PER_PEER` (16)
request credits and `SENDS_PER_PEER` (8) send credits" — 24 in all. G4: "in bits
32-44 the number of pages of the chunk whose class is not *data*". Debug registers
(SDM §20.2.4, read in the cited edition): "If the corresponding RWn field in
register DR7 is 00 (instruction execution), then the LENn field should also be
00. The effect of using other lengths is undefined", and "Instruction breakpoints
for other operand sizes are undefined".

**Verdicts, one by one.**

1. **Handing word with nobody, held word with nobody: refuted as a defect.** The
   contract says the target is "handing only, otherwise 0xFFFF" and nothing about
   the holder's code being a node slot; `from_raw`'s own doc promises only "`None`
   for state 3, a vacant word that names a holder or a target, or a held word that
   names a target", and it delivers exactly that. A handing word to `ROLE_NOBODY`
   is consumed harmlessly: `refused` compares `w.holder() == sender` with a
   `sender` the check has already bounded below `nodes`, so 0xFFFF never matches.
   Severity **informational**; the fix is the doc's, not the code's: say which
   words are the gate's to write, and that `from_raw` narrows nothing further.
2. **`Owner::Node` unchecked, `Unclaimed` as the fall-through: real, hardening.**
   `may_take` treats `Unclaimed` as "any node may take", so a *corrupt* ownership
   word whose owner code reads 0xFFFF or a code above `NODES_MAX` is handed to
   whoever asks first, while the word still reads *taken*. The contract refuses
   the other owners and provides the check field for exactly this: "bit flips in
   the tables of memory (the check field of the ownership words and ECC **narrow**
   it)" — narrow, not exclude, so the contract admits corrupt words. No caller in
   the model passes an invalid node (`grep` of `Owner::Node(` finds only values
   from the table), so nothing is exploitable today: severity **low**, fail-open
   by construction. Correction: `Owner::Node(node).code()` unchanged (it is a
   constructor, and its domain is the node slots), but `Ownership::owner()` must
   not turn "a code that names nothing" into a *takeable* owner: return the raw
   code (an `Option<Owner>`, or a fourth variant `Corrupt`) and make `may_take`
   refuse it, as it refuses `OwnState::None`. The test that fails without it:
   `ver2a_an_owner_node_of_0xffff_reads_as_unclaimed`, rewritten to assert
   `None`/refusal. Cost: one branch where a corrupt word is read; no new state.
3. **A credit index of 24 to 30: real, hardening.** There are 24 credits and
   `CREDIT_NONE` is 31, so indices 24-30 name nothing, yet `credit()` returns
   `Some`. The model survives because `credit_in_use` uses
   `self.peers[peer].credits.get(index)`, which is `None` there; a kernel indexing
   its table directly would read past it. Severity **low**. Correction:
   `RingHeader::credit`, `if index == CREDIT_NONE || index as usize >=
   REQUESTS_PER_PEER + SENDS_PER_PEER { None }`; the test above, rewritten. Cost
   nothing; no new state. (The contract should also say, once, "no other value of
   bits 0-4 is a credit".)
4. **`GateWord::from_raw` bounded by 4,096: refuted.** The function has no
   geometry and its doc says so in the same sentence: "more pages not of class
   data than a chunk can have (*E* ≤ 4,096)". `E` is a machine value at most
   4,096, so the maximum is the only bound a geometry-free decoder can state; a
   caller that needs the exact bound has its `geometry` and must use it. Severity
   **informational**: the fix is a sentence, "a reader checks this count against
   its own *E*", and nothing in `abi/` changes.
5. **`dr7_valid` and an execution breakpoint with a length: real, hardening.** The
   contract's kind 9 row and `thread_write_regs`' doc speak of "the breakpoint
   control within the user mask (`invalid`)"; the contract's rule for what a user
   may set is the SDM's, and the SDM says the combination is undefined, not
   forbidden, so a kernel that must not act on undefined input should refuse it
   as it already refuses the I/O condition (`DR7_CONDITION_IO`). Severity **low**
   (the effect is undefined hardware behaviour for a thread that sets it on
   itself — no other node, no other thread). Correction: in `dr7_valid`, for each
   `n`, refuse `word >> (16 + 4*n) & 0b11 == 0 && word >> (18 + 4*n) & 0b11 != 0`;
   the test above, rewritten; cost one more comparison per breakpoint at
   `thread_write_regs`; no new state. One more thing on the same line:
   `dr7_valid`'s doc cites "Intel SDM, volume 3, 18.2.4", and in the edition the
   contract cites (325462-093) the DR7 fields are §20.2.4 and the length rules
   §20.2.5. D-135 says each specification is cited in one edition, so the section
   number is to correct with the rule.

---

## Finding 8. Pure functions that panic outside the domain their callers keep

**My tests** (all pass): `ver2a_firing_instant_at_and_beyond_the_time_limit_panics`
(`panicked at abi/src/lib.rs:896:13: attempt to subtract with overflow`),
`ver2a_clock_page_shift_of_128_panics` (`panicked at abi/src/lib.rs:922:22:
attempt to shift right with overflow`), `ver2a_bandwidth_outside_its_domain_panics`
(`assertion failed: period < 1 << 48 && budget <= period`, `lib.rs:868`) and
`ver2a_an_owner_reserve_past_the_reserves_overflows_its_code`
(`abi/src/machine.rs:488:33: attempt to add with overflow`).

What I opened: `abi/src/lib.rs:888-903` (`firing_instant`; its comment says "they
differ, since x ≥ deadline", which is false once `deadline ≥ TIME_LIMIT`);
`lib.rs:918-925` (`ClockPage::nanoseconds`, `>> self.shift`); `lib.rs:862-877`
(`bandwidth`, whose own doc names its domain); `machine.rs:481-490`
(`Owner::code`, `OWNER_RESERVE_BASE + j`); and the callers that keep each domain
in the model: `sched.rs` (`timer_set` refuses `deadline >= TIME_LIMIT` first;
`sched_configure` checks the period and the budget first), and no caller of
`Owner::Reserve` with `j >= RESERVES_MAX` (`RESERVES_MAX = 8`).

**The contract.** "Clock": `TIME_LIMIT` is "Every instant and every duration
given to a call is below this" (`abi/src/lib.rs:816`); admission: "the bandwidth of
a context, ⌈budget × 2^32 / period⌉ ... The period is below 2^48 (a valid one is
at most 2^36), and the budget at most the period"; the clock page is "the clock
page that the kernel writes and every address space maps read only" — a reader is
user space, and a `shift` of 128 or more is a kernel bug, so a faulty kernel is
the only source; reserves: "one owner code per reserve, at most eight".

**Verdict.** **Real, the model's fault for `firing_instant` and `Owner::Reserve`,
but hardening only.** Each is a `const fn` whose domain its callers keep, and its
panic is reachable only by a caller that has already broken the contract's own
bound — which for `firing_instant` is "every instant given to a call is below
`TIME_LIMIT`" and for `Owner::Reserve` is `RESERVES_MAX`. Nothing in the model
calls them outside it, so the answer to "does an attacker reach it" is no; the
answer to "is it right" is no. `ClockPage::nanoseconds` is the one with an
attacker: any thread reads the clock page, so a faulty kernel that writes a shift
of 128 panics *user space*, which is the one place a panic in `abi/` is not even
the node's. `bandwidth`'s `assert!` is not a weakness: it is a debug check of a
value the kernel computes from its own checks.

**Correction.** Serve each function's documented domain instead of panicking:

- `firing_instant` (`abi/src/lib.rs:888`): `if deadline == 0 || deadline >=
  TIME_LIMIT { return 0 }` — or hold at `TIME_LIMIT - 1` — and the comment's "they
  differ, since x ≥ deadline" becomes true by construction. The test that fails
  without it: the one above. Cost: one comparison per timer arm; no new state.
- `Owner::code` (`abi/src/machine.rs:488`): `Self::Reserve(j)` where `j <
  RESERVES_MAX` is the only valid `Reserve`, and the constructor should say so
  (`const fn reserve(j: u16) -> Option<Self>`), so the overflow becomes
  impossible rather than caught. The test above, rewritten.
- `ClockPage::nanoseconds` (`abi/src/lib.rs:920`): the reader's rule is in the
  `abi/` doc and in the contract ("a reader starts over if [the sequence] was odd
  or changed"); add "and if `shift` or `mult` is out of range it reads 0", i.e.
  `if self.shift >= 128 { return 0 }`. The test above, rewritten. Cost: nothing
  on a hot path a kernel takes; user space pays one comparison.
- `bandwidth`: nothing to change; its `assert!` is the model's own.

I did not run these four fixes; each is a one-line change at the line named.

---

## Finding 9. `FeatureMask::fits` and `kind_covers` have no caller, and `fits` omits the size

**What I opened.** `abi/src/features.rs:95-104` (`fits`, whose doc is "Whether a
kind has every feature of the mask and its length: the condition of `thread_move`
on the destination node") and `features.rs:120-127` (`kind_covers`);
`abi/src/lib.rs:36` (both re-exported); `model/src/threads.rs:175`
(`thread_set_features` checks the area, as the author says); `abi/src/lib.rs:660`
("`thread_move`, removed by D-128"). `grep` over `abi/src` and `model/src` finds
no caller of either: only tests use them (`abi/src/tests.rs:1570-1580, 2019`).

**The contract.** D-128 decided that "a process lives in one node" and that "only
one-shot operations cross between nodes"; the call reference keeps the place of
`thread_move` as a tombstone ("Between nodes: the doorbell of a grant, at the
place of `thread_move`, removed by D-128"). There is no `thread_move`, so no
condition of it exists.

**Verdict.** **Refuted** as a defect: no caller, no call, no guarantee. The
function is not reachable, so a destination kind with a larger `baseline_bytes`
saves more than the thread object holds only if someone writes a call that uses
`fits` — the author says as much ("If a move comes back with `fits` as its
condition"). What is left is a stale doc comment naming a call that no longer
exists. Severity **informational**, no correction owed to the model; if the
project wants it tidy, the smallest change is `features.rs:97-98` to "Whether a
kind has every feature of the mask and its length: the condition any future move
of a thread between unlike kinds would need, its size checked separately
(`thread_bytes`)". `kind_covers` is the same: no caller, and it is the answer to a
question the contract no longer asks in a call.

---

## What I did not examine

- `Kani` proofs: read, not run (not in Nix). The report's own note stands.
- The parts of the model outside lot A: read only where a lot A function is
  called (`rings.rs`'s receive path, `units.rs`'s `operands_allowed` and
  `unit_requested`, `debug.rs`'s writes and `enter_debug_areas`, `boot.rs`'s
  layout, `grants.rs`'s `send_answered`, `faults.rs`'s register calls).
- The hardware text of the editions the contract cites: the two premises I used
  (Arm DDI 0487 D2.9, Intel SDM §13.6.2.1 and §20.2.4/20.2.5) were read in the
  text of DDI 0487 K.a and of order 325462-093 that were on this machine. The
  contract cites DDI 0487 M.d, and I did not have M.d's text, so the ARM64 quote
  is from K.a. The rule I quote is a "PAC relates to the privilege of the access"
  sentence that the contract's own ARM64 list also rests on; if M.d changed it,
  finding 2's premise changes with it.
- The contract's own review history (the reviews it cites) beyond the sentences
  quoted here.

---

## Table

| Finding | Verdict | Severity | Correction, one line |
|---|---|---|---|
| 1. The sender is taken from the header, not from the ring | real, the contract's fault (the model is faithful; the marks half alone would be intended) | high | add "the sender it carries is the node of the ring it was read from" to the one check, and pass `from` into `Model::refused` as `sender != from` (ran; the three forged-message tests then fail) |
| 2. A user watchpoint at the kernel's own level | real, the contract's fault; the x86-64 half not run, with reason (no debug match in the model) | medium (needs the kernel's copies with `LDTR`/`STTR`) | take 0x35 out of "a bug of the kernel" and make it kind 9 when `FAR_ELx` is in the thread's user range (Arm DDI 0487 D2.9); the kernel asks `FAR_ELx` first, `abi/` gains the pure rule |
| 3. A next sequence left in a kept debug area | real, the contract's fault | low (panic in a checked build; silent entry loss otherwise) | clear a kept area whose next sequence is 0 or `u64::MAX` ("goes on from the next sequences found there, unless…"), in the contract and in `enter_debug_areas` (ran; the test then fails) |
| 4. `Geometry::valid` overflows on a page shift | real, the model's fault | low (boot image) | return false as soon as `sizes` is false, or `s[i - 1].saturating_add(per_level)` at `lib.rs:504` (ran; the test then fails) |
| 5. `module_frames` on a length or address | real, the model's fault (the overflow); refuted for the unaligned address | low (boot image) | checked arithmetic in `layout` and in `module_frames`, the domain in the doc (ran; the test then fails) |
| 6. An MSI at APIC ID 255 | real, the contract's fault | low (needs a 255 core and no remapping) | "APIC ID 255 or greater cannot be reached this way", since FFH is the broadcast (Intel SDM §13.6.2.1), and `apic_id >= 255` in `msi_direct` (ran; the test then fails) |
| 7.1 A role word that names nobody | refuted (a doc matter) | informational | say in the role word's doc which words a gate may write |
| 7.2 An owner of 0xFFFF reads as unclaimed | real, hardening | low (needs a corrupt word) | `Ownership::owner()` must not turn a code that names nothing into a takeable `Unclaimed`; `may_take` refuses it |
| 7.3 A credit index of 24-30 | real, hardening | low (the model uses `.get`) | `RingHeader::credit` returns `None` for any index but 0-23 and 31 |
| 7.4 `GateWord` bounded by 4,096 | refuted (the doc says "E ≤ 4,096") | informational | a reader compares against its own `E` |
| 7.5 `dr7_valid` and a length on an execution breakpoint | real, hardening | low | refuse LEN ≠ 00 with R/W = 00 (SDM: undefined) |
| 8. Pure functions outside their domain | real, the model's fault, hardening | informational | `firing_instant` holds at `TIME_LIMIT`, `Owner::Reserve` is fallible, `nanoseconds` reads 0 for a shift of 128 or more |
| 9. `fits` and `kind_covers` with no caller | refuted (no call, no caller; a stale doc) | informational | reword `features.rs:97` to stop naming `thread_move` |

Count: one high, one medium, seven low, and four refuted or informational. Two
of the author's claims I refute in part (5's unaligned address, 7.4) or whole (9),
and one I sharpen well past where they left it (1: the answer forgery, which
frees another node's frame, not only another node's device).

My test files, to read:

- `/private/tmp/dodos-pr3-ver2-A-opus/abi/tests/ver2a.rs`
- `/private/tmp/dodos-pr3-ver2-A-opus/model/src/scenarios/ver2a.rs`
