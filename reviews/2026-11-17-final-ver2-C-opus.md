# Verification of the Lot C attack report (Opus, second final review)

Verification of `/scratchpad/final/reports/v2-C-opus.md` against the contract
`Docs/architecture/kernel-interface.md` (branch `main`) and the decisions
`D-100` to `D-140`.

Read-only clone for reference: `/private/tmp/dodos-pr3-final`, head `6312868`.
My own work copy, made fresh with `rm -rf` and `cp -R` as the brief says:
`/private/tmp/dodos-pr3-ver2-C-opus`. The report's author's copy
(`/private/tmp/dodos-pr3-v2-C-opus`) was read but nothing was run in it.

The author's file existed; the output file did not, so this report is written
from nothing, and every number in it comes from my own runs. I changed
nothing in any repository: in my copy the only changes are one new test file
`model/src/scenarios/ver2c.rs` and the line `mod ver2c;` appended to
`model/src/scenarios/mod.rs`.

## How the reproductions were made and run

From `/private/tmp/dodos-pr3-ver2-C-opus`:

    export PATH=/nix/var/nix/profiles/default/bin:$PATH
    nix develop -c cargo test -p dodos-model --lib ver2c -- --nocapture --test-threads=1

Fourteen tests, `test result: ok. 14 passed; 0 failed; 0 ignored; 0 measured;
523 filtered out; finished in 5.29s` (the first run of the command compiles:
1 m 03 s). Every test but the two of the rebuild runs in well under a second;
those two are the 5 s. Each test prints what it
observed and asserts the attack's *result*, so a passing test means the
attack worked. They are 300 lines, written from the code and the contract
after reading the author's file, not copied from it; where I depart from
theirs, I say so.

The channel an attack uses matters, so: the model gives a test two inputs of
this kind, and both are the right shape for a faulty kernel.

- `System::inject(from, to, message)` writes a message at the head of the ring
  `from` → `to`, and its own documentation says what it is for: "a faulty,
  late or forged message that the receiver must judge like any other"
  (`model/src/system.rs:497-500`). A kernel writes its ring with plain stores
  — the contract says so ("its writes are plain stores, not gate calls, since
  the receiver checks every message", ki:968) — so a message a kernel leaves
  in its own ring is exactly what `inject` builds.
- `System::edit_table` writes the shared machine table, i.e. the memory a
  node's kernel owns (its own ring's entries and its own producer index) or
  reads (the fixed part). A faulty kernel writing its own ring is not
  something the gate forbids: the gate holds page tables, and a ring is
  ordinary memory of its writer.

Two of the author's attacks reach their state *only* through these two, and
that is right; two of them I had to rebuild to make the attack reach as far
as they claimed (findings 4 and 5-A), see below.

Contract shorthand in this report: `ki:NNN` is line NNN of
`Docs/architecture/kernel-interface.md`.

## The findings, one by one

Findings are taken in the order of the report's summary (severity), not its
numbering, because two of them decide the others.

---

## Finding 5 — the receiver takes a message's sender from its header, not from the ring it came in

**Real, the contract's fault.** Severity: high (exploitable; a third node acts
in another node's name, and one of the three routes does reach another node's
memory once the grant protocol is read as a whole — see 5-A′ below).

### What the code does

`Model::consume(from, …)` reads ring `from` → `me` and calls
`self.refused(&message)` (`model/src/rings.rs:471-505`); `refused`
(`rings.rs:376-401`) takes `let sender = header.sender;` and judges every
later check — the grant entry's grantee, the use entry's granter, the role
word's holder, the credit toward the sender, the stamp's node — against that.
`receive_message` then takes `let from = message.header.sender;`
(`rings.rs:612`). The ring the message came from is used in one place only:
the trace of a refusal (`rings.rs:519-520`). `from` is never compared with
`header.sender`.

### The three reproductions (all run)

`v5a_a_release_forged_by_a_third_node_frees_the_grantee_grant` — three nodes;
node 0 grants node 1 a frame and node 1 holds the remote capability; node 2
writes a `Release` for that grant and serial in its own ring 2 → 0 with a
header naming node 1:

    V5a: grant 0 serial 0 is live; node 1's frame is valid
    V5a: node 0 refused 0 of ring 2 -> 0's messages; grant after: false; node 1's frame valid: false

`v5b_a_send_forged_by_a_third_node_carries_another_nodes_task` — node 2 writes
a `Send` in ring 2 → 0 naming node 1 and node 1's start-up task:

    V5b: node 0 refused 0; its receiver woke with Some(Ok(Message(Delivery { received: Received { header: Header(4294967303), badge: 0, marks: Marks(0), task: 281474976710657 }, words: [42] })))
    V5b: the task 281474976710657 names node 1

`v5c_a_detach_forged_in_another_nodes_name_clears_its_context_entry` — node 0
attached its device through node 1, the IOMMU role's holder; node 2 writes a
`UnitRequest` `Detach` in ring 2 → 1 naming node 0:

    V5c: node 0's context entry before: Some((0, 1)), domain 1
    V5c: node 1 refused 0 of ring 2 -> 1's messages; the context entry after: None

Three for three: no message is refused, and every effect lands.

### What the contract says

The check is stated on the sender the message carries, and never on the ring
(`ki:966`, "One check on every message received"):

> Every message carries its kind, its length, its sender's node and
> generation, and the generation of the receiver it was sent to […] The
> receiving kernel checks, in one function and before anything changes: the
> sender's member word is starting, live, sealing or sealed with that
> generation […]

and, for what a lie about the message's own contents may cost:

> The marks of a stamp are as the sending kernel states them: kernels trust
> each other's stamping as they trust each other's checks; a kernel that lies
> about marks is faulty, which the gate does not contain (it damages the
> marks of what it sends and availability, never another node's memory).

The machinery, meanwhile, makes the sender knowable without the header, and
says so in the same subsection (`ki:967-968`):

> Each ordered pair of node slots (*X* → *Y*) has a **kernel ring** and a
> **user ring** […] A ring *X* → *Y* is mapped writable only in *X*'s kernel
> and read-only in *Y*'s.

So a message found in ring *X* → *Y* was written by *X*'s kernel, and the
receiver can check it for one comparison. The contract does not ask for that
comparison.

### Verdict

The model does exactly what the contract's check says, so this is not the
model's fault. A guarantee of the contract breaks, and I name it: **the check
of `ki:966` is the only thing that ties a message to a sender, and it is
stated on a value the sender writes.** The three parts break three different
sentences:

| Route | Sentence that breaks | How |
|---|---|---|
| A, a forged `Release` | "The kernel refuses to start" is untouched; the grant rule of `ki:917` ("*X* acts on the message only if the entry has that serial and names *Y*, with the generation *Y* sent it from, as its grantee … it then frees the entry if its anchor has no descendant") — it names *Y* truthfully, and the message is not *Y*'s | a third node frees another grantee's grant; the grantee's capability becomes invalid (availability) |
| B, a forged `Send` stamp | nothing: D-134's "a task identifier of the sender's node" is satisfied by the carried sender, and the stamp trust sentence above admits the damage | the receiver believes node 1's task sent it (marks, admitted) |
| C, a forged `UnitRequest` | **D-140 point 3**, "A detach is tied to its requester: operation 2 checks the identifier word with the requester's generation" | the *requester* is the carried sender; node 2 detaches node 0's device |

D-140 point 3 exists to close exactly the class of fault the author's C is:
the thirteenth contract review's finding 3 was "Faulty requester `Op 2 detach`
… corrupts another node's live `AttachWord`", and its correction was to judge
the operands against the requester. Judged against a forged requester the
check is satisfied by a third node. So D-140 point 3 does not hold as written.

### The question the brief leaves open: does acting in another name stay inside what the gate promises?

The gate's promise (D-117 point 2, D-120 points 2 and 3, and the report's
own wording) is that a faulty kernel "reaches only its own memory and its own
devices". Take the three scenarios:

- **C, the detach.** Node 2 makes node 1 clear node 0's IOMMU context entry.
  Node 0's device stops doing DMA. No node reaches another node's memory: node
  2 gains no translation, no device register, no capability; it takes away
  node 0's device. That is *availability*, which the marks sentence above
  admits ("it damages the marks of what it sends and availability"). So this
  stays inside the gate's promise, and outside D-140's aim.
- **B, the task identity.** The receiver attributes a message to node 1's
  task. Marks; explicitly admitted by the sentence quoted above. Stays inside.
- **A, the forged `Release`.** As the author ran it, node 1 holds the remote
  capability but does not map it, so the effect is node 1's capability going
  invalid: availability again, inside. But the release protocol read as a
  whole does not keep it there, and this is where the answer changes:

### Finding 5-A′ — a `Release` frees the grant although the grantee still translates to the frame

**Real, the contract's fault.** Severity: high. This is the same code path as
5-A, and a *forged* release is not needed to reach it: any holder that
releases early reaches it. So it is a finding of its own, and it settles the
question above.

`release_received` (`model/src/grants.rs:807-829`) frees the entry when the
anchor has no descendant:

    let anchor = self.anchor(grant);
    if anchor.is_some_and(|a| self.caps[&a].children.is_empty()) {
        self.free_with_anchor(grant);
    }

The anchor's children are in the *granting* node's kernel space and a
mapping on the holder adds none of them (`make_grant` derives the anchor as a
child of the frame capability, `grants.rs:330-345`; the holder's mapping
counts a leaf in its own use entry and in no child of the anchor). So the
grant is freed whatever the holder still maps. Reproduced as
`v5a2_a_release_forged_while_the_grantee_maps_frees_the_grant_under_the_mapping`:
node 1 maps the granted page, then node 2 forges the release.

    V5a2: node 1 maps node 0's frame at 0x100007000; its use entry counts 1 leaves
    V5a2: grant live: false; node 1's translations: 23; check Err("node 1: 58: translation under no grant")

The model reaches a state its own checker forbids: invariant 58 of
`model/src/check/table.rs:255-268` requires a translation under a remote frame
to name a grant that is live with that serial and names this node as grantee.
The contract states the guarantee this breaks twice. `ki:914`:

> *Y*'s gate maps a frame of *X* only while the grant is live, and that is the
> only way a node maps memory it does not own (D-120 point 3).

and `ki:915`:

> So *X*'s memory never returns to an untyped while *Y* still translates to
> it, and a chunk under a live grant is never given (D-120 point 3).

The sentence that should carry it is the release rule, `ki:917`, and it does
not: "*X* acts on the message only if the entry has that serial and names *Y*
… it then frees the entry if its anchor has no descendant in *X*'s list". Only
the revocation path (`ki:915`) reads the holder's leaf count, and only the
ordering rule of `ki:914` binds the pair. So a holder that releases while its
root still has records returns the granting node's chunk to circulation under
a live translation: node 0 may then revoke and retype the frame, and node 1's
stale translation reaches node 0's memory. The gate's promise ("never another
node's memory") breaks through a route the third node can trigger at will and
the true holder can trigger by itself.

The same hole is on the other side of the answer: `send_answered`
(`grants.rs:490-520`) frees every grant whose frame the `SendAnswer` says was
not delivered, again without reading the use count, so a forged `SendAnswer`
in the grantee's name (read, not run: its credit index and serial are
guessable, `peer.serial` counts up from 0) frees a mapped grant too.

**Correction (contract).** In `ki:917`, "Release by the holder", replace

> it then frees the entry if its anchor has no descendant in *X*'s list;
> otherwise the anchor stays, held by nobody, until an ancestor's removal
> reaches it

with

> it then frees the entry if its anchor has no descendant in *X*'s list **and
> the count in *Y*'s use entry at the index the grant entry records is 0;
> otherwise the entry stays live and the release is traced (code 11) and
> dropped**

and add the same condition to the `SendAnswer` rule ("the grants of the frames
not delivered freed"). Cost: one read of the use entry *X* already names by
index, per release and per `SendAnswer` — the same read `ki:915` already makes
for a revocation, so nothing is added to the hot path of a mapping. When: at
the message's own step, no waiting, no answer. New state: none — the use
index and the leaf count exist (`ki:909`), and `ki:914` already requires the
ordering that makes the read meaningful.

**Correction (model).** `Model::release_received` (`grants.rs:807-829`): free
only if `self.table.uses[me][&entry.use_index]`'s `leaves == 0` (the use index
is written back by `send_answered`, so it is in the entry); otherwise trace
and leave the entry live. Same in `send_answered` for a grant the answer says
was not delivered. My test `v5a2…` fails without it (the checker's invariant
58 fires inside `m.run`), and passes with it.

### Correction (contract), for the check itself

In `ki:966`, "One check on every message received", after "The receiving
kernel checks, in one function and before anything changes:", insert

> the sender the header carries is the node whose ring the message was read
> from (ring *X* → *Y* is writable only in *X*'s kernel, so *Y* knows it)

Cost: one comparison per message received, on two 16-bit values already in
hand (`consume` has the ring's `from`; the header has the sender); nothing on
a mapping or a call. When: at the message's own step. New state: none.

**Correction (model), for the same.** `Model::refused` takes the ring:
`fn refused(&self, from: u16, message: &Message)`, returns `Some` when
`message.header.sender != from`; `consume` passes `from`. Then every check of
`ki:966` judges the true sender, and 5-A, 5-B, 5-C are refused with code 11.
My tests `v5a`, `v5b`, `v5c` are the tests that fail without it (they assert
the *attack*, so they turn red; I did not invert them to a negative test —
the author's fix direction, and mine, is the same one line).

I did not run the report's other reaches of this finding and neither does my
verdict depend on them. One of them I can settle by reading and it is
**refuted**: a forged `Handed` gains nothing, because the check requires the
role word to read *handing* with **this** node as target (`rings.rs:438-450`),
and the attacker cannot make the word name it. `ReportAsk` (a forged ask makes
the asked node send its own reports to the forger) and a forged `Revoke` (it
must name a use entry naming the forger as granting node) stay inside the
same "availability and marks" answer as C and B.

---

## Finding 4 — the holder maps the frame the `Send` carries, not the frame of the anchor

**Real, the model's fault.** Severity: highest of this report (exploitable; it
is the only finding here that hands a node another node's memory with the
whole check clean).

### What the code does

`send_received` hands each `Granted` of the message body to `place_remote`
(`grants.rs:390-396`), which writes `rights: granted.rights` for the new
capability (`grants.rs:457`), `self.frames.insert(id, granted.frame)`
(`grants.rs:476`) and `depth: granted.depth`, all taken from the message. The
check on a received `Send` (`rings.rs:466-470`) looks at the stamp only; it
never looks at the grant index or serial the message names, and the model's
`table::GrantEntry` (`table.rs`) holds no frame and no rights to compare with.
So nothing in the model ties the placed frame to the granting node's anchor.

### My reproduction (sharper than the author's)

The author's `c8` names node 0's *own* floor, so node 0 maps memory it already
owns: the damage is the missing map count, not a foreign mapping. I ran the
attack with **node 2's** floor, which is the case the gate's promise is about:
`v4_the_granting_node_writes_the_frame_the_holder_maps`, three nodes, node 1
grants node 0 a page of its own, then writes node 2's floor into the frame of
the `Send` it left in its own ring (the frame base and page count are in the
model's ring entry; the floor's address is in the fixed part of the machine
table, which every kernel reads):

    V4: node 2's floor starts at 0x100c00000, chunks of 0x200000
    V4: node 0 holds a remote frame at 0x100c00000, 512 pages
    V4: node 0 maps it: Ok(Done)
    V4: check after the map: Ok(())

Node 0, the *victim's* accomplice, maps a whole chunk of node 2's floor read
and write, and `System::check()` is `Ok(())`. Nothing counts the leaves
against the chunk either: `check/table.rs:255-268` skips the ownership count
for a remote frame (`continue`) and counts the leaf in the use entry instead,
by design (G6), so the granting node's own books stay balanced.

### What the contract says

`ki:911`: "A remote frame capability … its kind is `frame`, and **its rights,
depth and by-kind fields are those of the anchor**", and the model's own
doc-comment for `Granted` states the rule it should implement: the holder
learns a grant "from a `Send` and the anchor it names in the granting node's
grant table: the entry, the serial, the anchor's rights and depth, and its
frame" (`grants.rs:29-35`). The frame the holder gets is the anchor's, not the
message's.

### Verdict and correction

The contract forbids it and the model allows it: **the model's fault**.

The model cannot follow the contract with the state it has: the anchor is a
slot of the *granting* node's kernel capability space (`anchor_index`,
`grants.rs:41-44`), which the holder cannot read, whereas the contract puts a
64-byte anchor copy inside the 128-byte grant entry of the machine table
(`ki:909`), which every node reads. So the model's grant entry is missing a
field the contract has.

- **Function:** `Model::place_remote` (`grants.rs:430-486`) and the grant entry
  in `model/src/table.rs`.
- **Change:** `GrantEntry` gains the anchor's frame (base, pages, page size,
  memory type), its rights and its depth, written by `make_grant`; `refused`
  refuses a `Send` whose listed grant index and serial do not name an entry
  whose grantee is the carried sender with that generation and serial;
  `place_remote` takes rights, depth and frame from the entry and not from the
  message body.
- **Cost:** 4,096 entries × about 32 bytes in the model's living part — the
  contract's entry is 128 bytes and already holds it, so this is no new state
  in the contract, only in the model. No cost on a mapping.
- **Test that fails without it:** `v4_the_granting_node_writes_the_frame_the_holder_maps`
  (asserting `placed.base == node 2's floor` and the map's `Ok(Done)`); with
  the change the `Send` is refused and node 0 gets no frame.

---

## Finding 7 — a `Report` whose next key does not advance keeps the rebuild asking for ever

**Real, the contract's fault.** Severity: likely exploitable (one node stops a
unit for the whole machine, at no cost, for as long as it answers; the model's
own liveness bound fires).

### What the code does

`report_received` (`roles.rs:659-684`) takes any key that is not
`REPORT_END` as the next key, including one not above the key asked, and
`rebuild_step` (`roles.rs:452-480`) then asks the same node again from it. A
node that answers is never skipped (`roles.rs:440-444` skips only a node that
no longer writes), and `rebuild.items` grows by `REPORT_ITEMS` per answer.

### My reproduction (shorter than the author's 45 s run)

Two tests.

`v7_a_report_whose_next_key_does_not_advance_stalls_the_rebuild` — node 1
holds the unit roles and is killed; node 2 takes over and asks node 0; node 0
rewrites the `next` key of every `Report` it writes in its own ring to node 2
to the key asked (0), one event at a time, the clock moved only to the next
timer:

    V7: 500 events, 0 reports rewritten, rebuilding true, items 0
    V7: 1000 events, 236 reports rewritten, rebuilding true, items 0
    …
    V7: 4000 events, 1736 reports rewritten, rebuilding true, items 0

(`check()` asserted `Ok(())` every 500 events, 1736 reports rewritten, the
rebuild still running when the loop ended).

`v7b_a_unit_request_waits_while_the_rebuild_never_ends` — the harm: node 0
asks the rebuilding holder for a device while the rebuild runs:

    V7b: 335 reports rewritten, the rebuild of node 2 runs
    V7b: node 0's attach: Ok(Waits)
    V7b: 735 reports rewritten; node 2 rebuilding true; node 0 still waiting true

So the unit serves nobody — every attach, detach and interrupt claim behind
that unit waits, exactly as `ki:940` says ("a request for a unit the holder is
rebuilding is kept until the rebuild ends") — and the rebuild never ends.

### What the contract says

`ki:1476`, "The reports are pulled":

> The holder asks again from the next key until *end*, then moves to the next
> node in index order […] **A rebuild asks each node at most ⌈items / items
> per message⌉ + 1 times** (about 5 for 192 handles: an estimate, not
> measured).

The model does what the first sentence says; the second sentence is the
guarantee that breaks, and it breaks against a node that answers at once with
a key of its choosing. (The author's run reached the model's own bound, "the
reserve makes progress for ever", `nodes.rs:1968-1974`, which is the model
saying the same thing: 100,000 steps at one instant without progress. I did
not need to reach it; the ask count and the waiting request are the same
evidence in less time.)

### Correction

**Contract.** In `ki:1476`, after "The holder asks again from the next key
until *end*", add

> A `Report` whose next key is neither *end* nor above the key asked ends
> that node's report as *end* does, and is traced (code 11)

Cost: one comparison of two 64-bit keys; no new state — the cursor already
holds the key asked (`ki:1476`). When: in the event that consumes the answer.
With it the bound of ⌈items / items per message⌉ + 1 holds by construction.

**Model.** `Model::report_received` (`roles.rs:659-684`): at the answer,
`rebuild.key` still holds the key asked (it is overwritten by this very
match), so `match next { REPORT_END => …, key if key > rebuild.key => rebuild.key = key, _ => { rebuild.node = from + 1; rebuild.key = 0; trace(Refused) } }`.
My test `v7b…` fails without it (node 0's request is answered and the rebuild
ends), and `v7…` likewise.

---

## Finding 6 — a producer index moved back makes the receiver's subtraction overflow

**Real, the contract's fault (and the model's own arithmetic contradicts `abi/`'s).** Severity: likely exploitable — a node traps on a value a peer writes; the reference model panics.

### What the code does

`consume` (`rings.rs:489-503`): `ring_resync(produced, consumed, size)` is
wrapping arithmetic (`abi/src/ring.rs:179-185`), so with `produced < consumed`
it returns `produced.wrapping_sub(entries)`, a value *above* `produced`, and
the next line, `let available = produced - consumed;`, is a checked
subtraction that overflows. Line 535 of the same function uses
`wrapping_sub` for the same difference.

### My reproduction

`v6_a_producer_index_moved_back_overflows_the_receiver` — node 1 writes four
messages into its ring to node 0, node 0 consumes them, node 1's kernel writes
its own producer index back to 0 (a plain store into its own ring header) and
writes one more message:

    V6: node 0 has consumed 4 entries of ring 1 -> 0
    (panic) attempt to subtract with overflow at model/src/rings.rs:503:29

### What the contract says

`ki:968`:

> The **producer index** is in the ring's header, written by *X* only; the
> **consumer index** of each ring into *Y* is in *Y*'s node beacon, written by
> *Y* only; both are 64-bit counts that never go back.

and `ki:966` gives one index rule only:

> **a producer index more than the ring's entries ahead of the consumer
> index** first moves the consumer index to the producer index minus the
> ring's entries

The ahead case has a rule; the behind case has none, because the contract says
the counts never go back. But a faulty kernel writes plain stores into its own
ring, so "never go back" is a property of a correct kernel, not an invariant
of the machine. `abi/src/ring.rs:154-158` states the arithmetic the model
should use: "64-bit counts that never go back, so the difference is taken
modulo 2^64", and `ring_free`/`ring_resync` are written that way; `consume`'s
own last line is too. Line 503 is the one place the model trusts the counts'
monotonicity.

### Verdict and correction

The model does what the contract says (nothing, for a producer behind the
consumer), and the guarantee that breaks is the one the resync sentence exists
to give: a receiver consumes whatever a peer's ring holds and traces what it
cannot use, instead of failing. **The contract's fault**, with a one-line model
correction that its own `abi/` already implies.

- **Contract:** extend the sentence at `ki:966` — after "a producer index more
  than the ring's entries ahead of the consumer index first moves the consumer
  index to the producer index minus the ring's entries", add "and a producer
  index below the consumer index moves the consumer index to the producer
  index; both are traced (code 11), and every difference of two indices is
  taken modulo 2^64". Cost: one subtraction, no new state, in an event that
  already runs.
- **Model:** `rings.rs:503`, `produced.wrapping_sub(consumed)`, as at
  `rings.rs:535`. My test `v6…` fails without it (it asserts the panic).

Whether the *real* kernel falls over depends on its arithmetic: Rust release
builds wrap, a Zig `ReleaseSafe` build traps (the project's kernel is Zig and
Rust, and the Zig style names assertions). The contract should not leave that
choice to the implementation.

---

## Finding 1 — a writable segment longer than the start-up untyped panics the start-up

**Real, the contract's fault.** Severity: hardening (low: the boot image is
signed and the first stage is outside the gate's threat model, but the kernel
dies at start-up instead of refusing with a stop record).

`child` (`boot.rs:1216-1222`) takes the frames of the copied segments, of the
start-up page and of the message page from `untypeds[0]` with
`.expect("the start-up untyped holds the frames of the start-up")`.
`layout` compares nothing with that block. My
`v1_a_writable_segment_larger_than_the_first_untyped_panics`:

    V1: floor 6291456 bytes = 3 chunks; the writable segment becomes 8 chunks
    (panic) the start-up untyped holds the frames of the start-up: NoMemory

The contract says where the copy comes from and how big the source is:
`ki:2024` (rule 7) makes the start-up untyped the *first block* of the floor
("The first of them, the node's **start-up untyped**, pays for the frames of
the node start-up"), and `ki:2054` says "Each writable segment is copied into
frames made from the start-up untyped". On the reference machine the floor is
three chunks, cut into blocks of two and one: the start-up untyped is 4 MB, and
nothing in the contract forbids a 16 MB writable segment. The refusal list
(`ki:2005-2010`) has no entry for it, so the kernel has no refusal to give and
the model has no `Refusal` to return.

**Correction (contract).** Add to the refusal list at `ki:2005-2010`: "or the
copied frames of the writable segments, with the start-up page and the message
page, do not fit in the start-up untyped (rule 7)". Smallest form: one bullet,
checked where the floors are laid out; the sizes are already computed there.
Cost: nothing at run time; no new state. The model then needs a `Refusal`
variant (or to reuse `Floors`) and the check in `layout`, where `floors[0]`'s
first block and `module_frames` are both in hand; my `v1…` test then asserts a
refusal instead of a panic.

The report's remark that the real kernel has no refusal for this is right:
`Refusal`'s eight variants (`boot.rs:453-483`) map one to one onto the
contract's list.

---

## Finding 2 — other boot values reach a panic instead of a refusal

**Real, the contract's fault**, three parts, one verdict each; severity
hardening (low). The three are all values of the machine or of the boot image,
both of which come from firmware and the first stage, and the contract's
refusal list does not include them. All three of my reproductions panic.

a. **`BootNodes` window.** `initial_nodes` (`boot.rs:419-427`) multiplies
   `64 * window` before any check (`boot.rs:646` tests `c < self.cores.len()`
   afterwards). My `v2a…` with a window of 2^58:

       (panic) attempt to multiply with overflow at model/src/boot.rs:424:35

   In a release build the multiplication wraps and names cores 0 to 63, so a
   record no layout can produce is accepted as another one. `nodes.rs:142-147`
   already checks a window against `CORE_WINDOWS` for `node_start`; the same
   check belongs here.

b. **A core of an unknown kind.** `kind_of` (`boot.rs:432-434`) indexes
   `self.kinds[usize::from(core.kind)]` with no check. My `v2b…` with kind 7:

       (panic) index out of bounds: the len is 1 but the index is 7 at boot.rs:434:19

c. **MAXPHYADDR.** The ownership words are sized
   `1u64 << (self.phys_bits - chunk_shift)` (`boot.rs:795`) and then indexed by
   the chunks of ordinary memory (`boot.rs:799`, and `boot.rs:817` shifts
   `1u64 << self.phys_bits` for the device table). My `v2c…` with
   `phys_bits` equal to the chunk shift (21):

       (panic) index out of bounds: the len is 1 but the index is 2054 at boot.rs:799:19

   Nothing in `layout` range-checks `phys_bits`; the contract never mentions
   MAXPHYADDR.

d. **`BootNodes.slots`.** The report says it read, not ran, that the ABI's
   `u32` becomes a `u16` in `Machine::boot_nodes` (`boot.rs:186`). Confirmed by
   reading, and **it cannot be run**: the model's own input type cannot hold
   65,537, so the value is truncated by whoever builds the `Machine`, before
   `layout`'s `n as usize <= NODES_MAX` (`boot.rs:658`). Real, the model's
   fault, severity: a fidelity gap, not an attack — the model cannot test a
   refusal the contract demands ("the number of node slots is more than
   `NODES_MAX` (1,024)", `ki:2001`). Correction: `boot_nodes:
   Option<(u32, Vec<(u64, u64)>)>`; `nodes()` already returns `usize`.

**Correction (contract), for a, b and c.** Add one bullet to the refusal list
(`ki:2005-2010`): "or a value of the machine is outside its range: MAXPHYADDR
below the top of the memory map or above 63; a core whose kind the entry
`Kinds` does not list; a `BootNodes` window above 2^54". Cost: three
comparisons at start-up; no new state.

**Correction (model), for a, b, c.** The model already has the variant it
needs — `Refusal::MachineValues`, documented as "the values of the machine are
out of range" (`boot.rs:478-480`) — and does not use it:
`Machine::layout` refuses `phys_bits` outside `chunk_shift..=63` and above the
memory map's top, refuses `core.kind >= kinds.len()`, and tests the window
against `CORE_WINDOWS` as `node_start` does; `Refusal::Nodes` for a window that
names no core of the machine. My `v2a`, `v2b`, `v2c` are the tests that fail
without that.

---

## Finding 3 — the crash areas are kept with no check, and a misaligned chunk-sized frame is built

**Real, the model's fault.** Severity: hardening (low-medium: an object the
contract says cannot exist, and no invariant sees it).

The report's three claims: the crash bases are never checked (alignment, inside
memory, inside `2^phys_bits`, apart from one another), and no invariant checks
that a frame's base is aligned on its page size. My
`v3_a_crash_area_off_its_chunk_boundary_is_accepted` moves the current crash
base by one page and boots:

    V3: boot accepted it; check Ok(()); frames of the crash base 0x300001000: 1
    V3: aligned on its page size: false; base % 2097152 = 4096

So the machine start-up keeps a 2 MB frame at an address 4 KB above a 2 MB
boundary. `ki:243` says what that frame is: "A frame has a page size … a
number of pages from 1 to *E*, a memory type and a kind of memory … Its pages
are physically contiguous and **aligned on the page size**." The model's own
type documentation claims the value it did not check ("The bases of the current
and of the previous crash area, each on a chunk boundary", `boot.rs:127-129`).
`grep is_multiple_of model/src/check*` finds cspace sizes, the untyped
watermark and mapping addresses — never a frame's base.

The other half of the report's claim (the kept ranges, the image, the feedback
tables never checked to lie in memory or apart from each other) I read and
confirm as described: `kept_ranges` (`boot.rs:611-621`) only collects them, and
`layout` subtracts them from ordinary memory, so most overlaps degrade into a
`Floors` refusal, but a base outside memory or above `2^phys_bits` is accepted
and turned into kept frames.

**Correction (model).** Two places, both cheap. (1) `Machine::layout`: refuse a
crash base that is not a multiple of the chunk, or that with its length leaves
the addressable range, or that overlaps the kept image or another kept range
(`Refusal::Floors` fits the contract's "the floors, the reserves and the kept
memory do not fit in the ordinary memory"). (2) `check` — the contract's
sentence above deserves an invariant: "every frame's base is a multiple of its
page size", added beside 35 in `check/memory.rs`; the final state already
holds every frame. My `v3…` test turns from "boot accepted, check Ok" into "boot
refused"; the invariant is tested by feeding the checker the state my test
builds today (`scenarios/checker.rs`'s pattern).

The contract needs no change: `ki:243` already forbids the frame, and the
refusal list does not have to name the crash bases because they are the first
stage's values, not the kernel's.

---

## Finding 8 — the domain numbers of a unit are cut to 16 bits

**Real, the model's fault, but unreachable on a machine the contract describes.**
Severity: lowest (hardening).

`domain_range` (`units.rs:238-245`) casts to `u16`:
`(first as u16)..=((first + per - 1) as u16)`. My
`v8_the_domain_numbers_of_a_unit_are_cut_to_16_bits` with `domains = 2^17` on
two slots:

    V8: slot 0 1..=65535, slot 1 0..=65534

— the ranges overlap and slot 1 owns 0, which the code's own comment says is
never used.

But the contract reads *D* from the unit's capability register (`ki:1030`): "*D*
= 2^(4 + 2 × ND), **from 16 to 65,536**". With any legal *D* and *n* slots the
last number of the last slot is 1 + *n* × *d* − 1 = *n* × *d* ≤ *D* − 2 ≤
65,534, so the cast never truncates. So the state is not a machine's; it is a
model input the model accepts because `layout` checks only that each slot gets
at least one number (`boot.rs:655-659`).

**Correction (model).** Refuse `domains` outside `16..=65_536` in
`Machine::layout` (`Refusal::MachineValues`), and take the cast out of
`domain_range` (compute in `u32` and cast once, with the range's end bounded by
*D* − 2). Cost: one comparison at start-up; no new state. `v8…` then asserts a
refusal, and the legal maximum (`domains = 65,536`, 2 and 3 slots) stays as it
is today.

---

## The notes the report left unproved, settled

- **`cores.rs`, `core_entered` clearing `ipis` but not `pending`.** *Not run*,
  with the reason: it needs a resume (or a start) with another core's
  invalidation request already pending on the entering core, and I could not
  build that state from the calls a test may make in the time I had. My reading
  of the code agrees with the author's and sharpens it: `core_entered`
  (`cores.rs:775-797`) clears `ipis`, `enter_idle` (`cores.rs:848-855`) sets the
  idle mark and answers nothing, and `answer_pending` runs only from `go_idle`
  (`cores.rs:501-514`, at the next idle) and from `take_interrupts` on an
  `Ipi::Invalidate` (`cores.rs:637-647`). A core that re-enters with a request
  in `pending` therefore answers it only at its next idle or invalidation — the
  requester's protocol (set the bit, then read the idle mark) is not violated,
  but nothing wakes the core. If reachable, it is a liveness gap of the model at
  a resume, and the fix is that `core_entered` answers what is pending before it
  goes idle. This needs a test, not a verdict from me.
- **`nodes.rs`, `node_start`'s module argument judged and ignored**, and
  `System::enter` dropping a failed `Model::start` silently. Read, agree, and I
  take the author's word: not holes of the model, gaps of the contract's text
  about what a fresh start with module *m* runs. Neither is an attack.
- **`irq.rs`, the `u16` handle `core × 192 + (vector − 48)`** and two cores with
  one APIC ID. Read, agree that firmware provides the identifiers and the
  contract does not require them distinct; hardening only, and the same family
  as finding 2b (a value of the machine the start-up does not check).
- **`units.rs`, the unit service table keyed by any credit index.** I checked
  this one further than the author did and it is **real but small**: `refused`
  passes a `UnitRequest` whatever its credit (`rings.rs:453-454`), while
  `unit_requested` keys its service table on `(from, index)` (`units.rs:540-556`)
  and the request credits are 16 of the header's 31 (`abi/src/ring.rs:19, 38`;
  `Peer::new` has 24 entries, 16 request and 8 send). So a hostile requester can
  use indices 16 to 30: the holder performs the operation, answers with a credit
  that no request credit of the sender occupies, and the answer is refused at
  the other end by the `credit_in_use` check. The effect is a service entry per
  peer beyond the contract's 16, and an answer that goes nowhere. Verdict: real,
  the contract's fault, severity lowest — `ki:966` verifies a credit for an
  answer and not for a request, though `ki:940` says every request carries one.
  Correction: `ki:966`, add to the sentence on the check "and a request's credit
  is one of this node's request credits toward the sender, in use with that
  serial". No new state. I did not run it: it needs a device
  no other node has attached and a forged credit index; the forged messages of
  `v5a`, `v5b` and `v5c` already show that the `UnitRequest` path takes a forged
  header and a credit no request of the sender made.

## Two remarks on the report's own tests

- `c8` (finding 4) names node 0's *own* floor as the frame, which understates
  the attack: node 0 maps memory it already owns. With a third node's floor the
  result is the same `Ok(())` from the checker and a real foreign mapping; I
  ran that (`v4`), and it is the version the correction must be tested against.
- `c6` (finding 5-A) releases a grant that is not mapped. The version with a
  mapping reaches a state the checker forbids (`v5a2`), so the finding is
  stronger than the report claims and its fix belongs in `release_received`, not
  only in the check of the sender.

## What I did not run, and why

- The report's `c10` as it stands (its 45 s run to the model's own progress
  bound): I reproduced the same attack with a bounded loop and a waiting unit
  request instead (`v7`, `v7b`), in a few seconds.
- The other reaches of finding 5 (a forged `Revoke`, `ReportAsk`, or an answer
  to another node's credit). Read, not run; the `Handed` one I refute by
  reading, and the `SendAnswer` one I give as a route to 5-A′.
- The `cores.rs` resume question, for the reason given above.
- The model's behaviour in a release build (finding 2a's wrap): read from the
  arithmetic, not run — the workspace builds with overflow checks on.
- The real kernel's arithmetic (finding 6): read, not run; there is no kernel
  implementation in this repository to run.
- The byte encoding of a ring message (a body longer than its header says): the
  model's ring holds Rust values, so it cannot be tested here; the author's
  reason stands.

## Summary

| # | Finding | Verdict | Severity (mine) | Correction, one line |
|---|---|---|---|---|
| 4 | The holder maps the frame, rights and depth the `Send` carries, not the anchor's (`grants.rs:430-486`) | real, the model's fault | highest, exploitable | Put the anchor's frame and rights in the grant entry (`ki:909`) and take them from it in `place_remote`; refuse a `Send` whose grant it does not name. |
| 5-A′ | A `Release` frees the grant although the grantee still translates to the frame (`grants.rs:807-829`; invariant 58 fires) | real, the contract's fault: `ki:915`/D-120 (3) breaks | high | Add "and the count in *Y*'s use entry is 0" to the release rule at `ki:917`, and the same to the `SendAnswer` route. |
| 5 | The receiver takes the sender from the header, never from the ring (`rings.rs:376-401, 612`) | real, the contract's fault: D-140 (3) does not hold; the gate's memory promise holds for B and C, and 5-A′ is where it does not | high | `ki:966`: "the sender the header carries is the node whose ring the message was read from"; `refused` takes the ring's `from`. |
| 7 | A `Report` key that does not advance keeps the rebuild asking for ever (`roles.rs:659-684`) | real, the contract's fault: the bound of `ki:1476` breaks | likely exploitable | `ki:1476`: a next key that is neither *end* nor above the key asked ends the report, and is traced. |
| 6 | `produced - consumed` after a wrapping resync overflows (`rings.rs:503`) | real, the contract's fault: `ki:966` has no rule for a producer behind the consumer | likely exploitable | `ki:966`: a producer below the consumer moves the consumer to it; differences modulo 2^64. Model: `wrapping_sub`. |
| 1 | A writable segment larger than the start-up untyped panics the start-up (`boot.rs:1216-1222`) | real, the contract's fault: the refusal list of `ki:2005-2010` lacks it | hardening, low | Add the refusal: the copied frames must fit the start-up untyped (rule 7, `ki:2024`/`ki:2054`). |
| 2a, b, c | A `BootNodes` window overflows, an unknown core kind and MAXPHYADDR below the map panic (`boot.rs:424, 434, 795-799, 817`) | real, the contract's fault: the refusal list lacks them | hardening, low | Add "a value of the machine is outside its range"; the model's `Refusal::MachineValues` already says it and is unused. |
| 2d | `BootNodes.slots` is a `u16` in the model and a `u32` in the ABI (`boot.rs:186`) | real, the model's fault, not run (the type cannot express it) | hardening, lowest | `Option<(u32, Vec<(u64, u64)>)>`. |
| 3 | The crash areas and kept ranges are never checked, and a chunk-sized frame is built off its boundary (`boot.rs:1281-1288`) | real, the model's fault: `ki:243` forbids that frame | hardening, low-medium | Refuse a crash base off the chunk in `layout`, and add "a frame's base is a multiple of its page size" to `check`. |
| 8 | The domain numbers are cut to 16 bits (`units.rs:238-245`) | real, the model's fault, unreachable: `ki:1030` caps *D* at 65,536 | hardening, lowest | Refuse `domains` outside `16..=65_536` in `layout`, and compute the range in `u32`. |
| n | A `UnitRequest`'s credit is not checked (`rings.rs:453-454`) | real, the contract's fault, not run | lowest | `ki:966`: a request's credit must be a request credit toward the sender, in use with that serial. |
| n | `core_entered` clears `ipis` and leaves `pending` unanswered (`cores.rs:775-797`) | not run — needs a resume with a request in flight, which I could not build | unknown | (a test first: answer what is pending before the core goes idle) |

