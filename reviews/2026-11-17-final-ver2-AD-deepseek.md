# Verification of the reports V2-A and V2-D (deepseek)

Verifier: Claude Opus 5.5, with the contract and the decisions.

- Contract: `Docs/architecture/kernel-interface.md`, branch `main`, commit `e2551c1`.
- Model: pull request 3 of `dodos-kernel`, head `6312868`.
- My work copy: `/private/tmp/dodos-pr3-ver2-AD-deepseek` (made fresh with
  `cp -R /private/tmp/dodos-pr3-final`). My tests are one file,
  `model/src/scenarios/ver2_ad.rs`, registered by one line `mod ver2_ad;` in
  `model/src/scenarios/mod.rs`, and, for the `abi` findings, one file
  `abi/tests/ver2_ad.rs`. I read the authors' tests in their copies
  (`/private/tmp/dodos-pr3-v2-A-deepseek`, `/private/tmp/dodos-pr3-v2-D-deepseek`)
  and ran nothing there.
- Command for every model test below (from the work copy, with
  `/nix/var/nix/profiles/default/bin` on the path):
  `nix develop -c cargo test -p dodos-model --lib ver2_`.

The verdicts use the four words of the brief: **real, the model's fault**;
**real, the contract's fault**; **intended**; **refuted**.

---

## A1. A message's header names another node than the ring it came on

### What the author says

`Model::refused` (`model/src/rings.rs:376`) is given the message and not the
ring it was read from; the caller `consume` (`rings.rs:478-535`) knows the
ring (`from`) and uses it only for the trace; `receive_message`
(`rings.rs:609-612`) then acts in the name of `message.header.sender`. So a
kernel writing on its own ring can act in any other node's name. The author
proved it with a `Revoke` that node 2 writes on its ring 2 → 1 with node 0's
slot and generation: node 1 applies it and drops its capability of node 0's
frame.

### The lines

`model/src/rings.rs:376-392`: the check reads `header.sender`, compares it
with the node count and with its member word, and never with the ring:

```rust
pub(crate) fn refused(&self, message: &Message) -> Option<u64> {
    let header = &message.header;
    let sender = header.sender;
    if sender >= self.table.nodes { return Some(0); }
    let member = self.table.member(sender);
    ...
```

`rings.rs:496` reads the entry from `self.ring_of(from, me, user)`, and
`rings.rs:515` calls `self.refused(&message)`; `from` reaches only the trace
(`rings.rs:518-519`). `receive_message` takes `from = message.header.sender`
(`rings.rs:611`). Confirmed.

### Is the attacker's move real?

`System::inject(from, to, message)` (`model/src/system.rs:500-515`) writes a
whole message at the head of the ring `from → to` and raises the receiver's
interrupt. The contract maps that ring writable in the sender's kernel: "A
ring *X* → *Y* is mapped writable only in *X*'s kernel and read-only in *Y*'s
(the guarantee of [The gate over page tables]); its writes are plain stores,
not gate calls, since the receiver checks every message." So a faulty kernel
2 can write any bytes on its rings 2 → 0 and 2 → 1, and `inject(2, …)` is
exactly that. Every value in the forged header is public: member words, the
grant table and the use table are "single-writer words of the living part of
the machine table … read by every node".

### Reproduction (mine)

Two tests in `model/src/scenarios/ver2_ad.rs`, on a machine of three nodes of
one core each (`machine(Arch::X86_64, 3, &[&[0], &[1], &[2]])`). The grant is
made by calls (`pass17::granted_to_1`: node 1 waits on its mailbox, node 0
`node_send`s a frame with `derive`), the mapping by a call (`aspace_map` of the
received frame on node 1). The only non-call input is `inject` on node 2's own
ring.

1. `ver2_a1_a_revoke_on_node_2_s_ring_naming_node_0_is_applied` — the
   author's case written again. The same `Revoke` on ring 2 → 1 is refused
   with node 2 in the header (refused count + 1, use entry kept), and applied
   with node 0 in the header (refused count unchanged, node 1's use entry
   gone, node 0's grant entry still there). **Passes**: reproduced.

2. `ver2_a1_a_release_naming_the_holder_frees_the_grant_under_its_mapping` —
   the sharper form, which the author named but did not prove. Node 1 maps the
   granted frame. Node 2 writes on its ring 2 → 0 a `Release` whose header
   names node 1 (slot and generation), with the grant index and serial read
   from node 0's public grant table. Time passes with `System::advance` only
   (no call). Result: node 0's grant entry is freed while node 1 still holds
   its use entry and its translation, and the model's own whole check rejects
   the state. Output (the assertion I first wrote expected G6; the check
   reports node 1's invariant 58 first, which is the same fact seen from the
   holder):

   ```
   assertion `left == right` failed
     left: Err("node 1: 58: translation under no grant")
    right: Err("G6: a grant freed while its holder translates to it")
   ```

   I then fixed the expected value to `node 1: 58: translation under no grant`
   (see the final run below).

3. `ver2_a1_after_the_forged_release_the_granter_reuses_the_memory_node_1_maps`
   — what node 0 can then do, all by calls of its own first thread:
   `cap_delete` of its frame (slot 101), `cap_revoke` of its untyped, and
   `untyped_retype` of a frame of 16 pages. Output:

   ```
   delete: Ok(Done)
   revoke untyped: Ok(Done)
   retype: Ok(Done)
   old base 0x100006000, new base Some((100000000, 10))
   check: Err("node 1: 58: translation under no grant")
   ```

   The new frame covers `0x100000000..0x100010000`, which holds the page
   `0x100006000` that node 1's honest kernel still translates for its user
   program. Nothing refused any step: the anchor of the grant, which is what
   makes a revoke of the untyped wait for the holder in the honest case, was
   removed by the forged `Release`.

### What the contract says

The check, "One check on every message received (D-124, completed by D-129
and D-131)": "Every message carries its kind, its length, its sender's node
and generation … The receiving kernel checks, in one function and before
anything changes: the sender's member word is starting, live, sealing or
sealed with that generation … a message that names a grant (`Revoke`,
`Release`, `Signal`) matches the entry it names, which is the grant entry
naming the sender as grantee with the generation it records and that serial
(on the granting node) …". The sender is a word the message carries, and no
clause ties it to the ring. Nowhere else does the contract say that the
receiver compares the header's sender with the writer of the ring. So the
model does what the contract says.

The guarantee that breaks. The gate, "The guarantee (G)": "every translation
that the hardware can use on *X*'s cores … leads only to: 1. memory *X* owns
… 2. memory granted to *X* by its owner and not yet revoked … So a kernel bug
in *X* can corrupt *X*'s memory, *X*'s devices and what *X* was granted, and
nothing else". After step 2, node 1's translation leads to memory that is
neither owned by node 1 nor granted to it any more, and after step 3 to memory
node 0 has retyped for itself; the bug that did it is in node 2, which was
granted nothing.

The two sentences that might make it intended do not cover it:

- "Not covered: … a grantee's kernel that is faulty in its messages about a
  grant (its `Release`, `RevokeStep`, `SendAnswer` and use index), which can
  make the granter free a frame it still translates (D-131, question 2)." The
  accepted risk is the *grantee* lying about *its own* grant: the frame it
  can lose is one it was given. Here the grantee (node 1) is honest, and the
  liar (node 2) is not party to the grant.
- "The marks of a stamp are as the sending kernel states them: kernels trust
  each other's stamping as they trust each other's checks; a kernel that lies
  about marks is faulty, which the gate does not contain (it damages the marks
  of what it sends and availability, never another node's memory)." This
  trusts what a kernel says about *its own* messages, and it states the bound
  of that trust: never another node's memory. Acting in another node's name is
  not stamping, and the scenario above reaches another node's memory, so this
  sentence is contradicted, not invoked.

### The disagreement, settled

Does acting in another node's name stay inside what the gate promises (a
faulty kernel reaches only its own memory and its own devices)? **No.** The
scenario, in four steps, all by moves the attacker really has:

1. Node 0 grants a frame to node 1; node 1 maps it (honest calls).
2. Node 2, faulty, writes on its own ring 2 → 0 a `Release` with
   `sender = 1`, node 1's generation, node 0's generation, and the grant index
   and serial read from node 0's grant table.
3. Node 0's check passes (the grant entry names node 1 as grantee with that
   generation and serial) and node 0 frees the grant entry and removes the
   anchor.
4. Node 0 reclaims and reuses the memory (`cap_delete`, `cap_revoke` of the
   untyped, `untyped_retype`) while node 1's user program still writes it.

Node 2 never translates node 0's memory, so a narrow reading ("node 2's own
translations lead only to node 2's memory") still holds. But the sentence the
contract uses for the unit of failure is wider: "a kernel bug in *X* can
corrupt *X*'s memory, *X*'s devices and what *X* was granted, and nothing
else", and the "Not covered" list repeats it: "misuse of the gate's legal
interface by a corrupted kernel, which by construction damages only its own
node, what it granted, or availability". Here a bug in node 2 corrupts memory
that node 0 owns, through node 1's honest translation. The other request kinds
widen the reach: a forged `Revoke` takes node 1's authority (shown in test 1;
availability and the agreement between two honest nodes), a forged `Signal`
rings another node's doorbell in the holder's name, and a forged
`UnitRequest` in another node's name asks a unit holder for an operation on
that node's devices (not proved here; the holder judges a request by its
requester, so this needs its own test).

### Verdict

**Real, the contract's fault.** Severity: **critical** (it breaks G and the
unit of failure for a third node, with one ring write and public values; the
author rated it "exploitable", which I confirm and raise).

### Correction

Contract, in "One check on every message received", after "the sender's
member word is starting, live, sealing or sealed with that generation"
insert: "**the sender it names is the node whose ring it came on** (*X* for a
ring *X* → *Y*: the gate maps that ring writable in *X*'s kernel alone, so the
ring, not the header, says who wrote the message)". It is the smallest
sentence that closes it: the receiver already knows which ring it reads, so it
costs one comparison per message and **no new state**. To write now, before
the oracle: a kernel that trusts the header would have to be changed later.
The field `sender` of `RingHeader` (`abi/src/ring.rs:193`) can stay as a
redundancy that the check compares; dropping it would change `abi/`, for no
gain.

Model: `Model::refused` (`model/src/rings.rs:376`) takes the ring's sender,
`fn refused(&self, from: u16, message: &Message)`, and refuses first
`header.sender != from` (`return Some(0)`, traced code 11 like any other
refusal); `consume` passes `from` (`rings.rs:515`). The tests that fail
without it are the three above, turned into refusals: the forged `Revoke`
leaves the use entry, the forged `Release` leaves the grant entry and the
whole check `Ok(())`. I applied this change in my copy and ran them: see the
section "Corrections applied in my copy" at the end.

---

## A2. A module length in the last page of the space panics the layout

**Lines.** `model/src/boot.rs:699-708`: `at += len.next_multiple_of(page)` on a
file length that comes straight from the boot image (`File`, `boot.rs:89-92`);
segments are bounded first (`boot.rs:672-677`), files are not. The same
rounding in `abi::module_frames` (`abi/src/machine.rs:1311`,
`len.div_ceil(page) * page`).

**Reproduction.** `ver2_a2_a_file_of_the_largest_length_panics_the_layout`:
`Machine::example()` with `files[0].len = u64::MAX` makes `System::boot` panic
(caught by `catch_unwind`); with `files[0].len = 1 << 62`, far beyond memory
but without overflow, `System::boot` returns `Err(Refusal::Floors)`. In `abi`,
`ver2_a2_module_frames_of_a_length_in_the_last_page_overflows` (in
`abi/tests/ver2_ad.rs`, command `nix develop -c cargo test -p dodos-abi --test ver2_ad`)
panics on `module_frames(0, None, u64::MAX, …)`. Both pass: reproduced.

**Contract.** Start-up state: "The kernel refuses to start, with a stop record
… if: … the floors, the reserves and the kept memory do not fit in the ordinary
memory (rule 4)". The image is kept memory ("The image region, the modules of
the boot image, is kept memory"), so a module that cannot fit is a refusal the
contract names, and the model gives it for `1 << 62` and panics for
`u64::MAX`. The model is the one at fault. The attacker already owns the boot
(the image is signed: "on a UEFI machine both are inside the one signed
image"), and the SHA-256 check would also fail on a real kernel, so nothing
past the boot is reached.

**Verdict.** **Real, the model's fault.** Severity: **low** (a panic instead of
a refusal, only for a boot image that a signed first stage would not hand
over; the oracle would disagree with a kernel that refuses).

**Correction.** `Machine::layout` (`model/src/boot.rs:708`): compute
`len.checked_next_multiple_of(page).and_then(|l| at.checked_add(l))` and the
`next_multiple_of` of line 707 the same way, returning `Err(Refusal::Floors)`
on `None`. The test that fails without it: the first half of
`ver2_a2_a_file_of_the_largest_length_panics_the_layout`, rewritten to expect
`Err(Refusal::Floors)` for `u64::MAX`. `abi::module_frames` needs no change
once its only callers come after `layout`; its documentation can say "for a
length `layout` accepted".

## A3. `Geometry::canonical` on a geometry `valid` refuses

**Lines.** `abi/src/lib.rs:476-480`, a shift by `address_bits() - 1`.

**Reproduction.** `ver2_a3_canonical_of_an_unbuilt_geometry_overflows`
(abi): `Geometry::default().canonical(1 << 47)` panics. Reproduced. The only
callers are `model/src/faults.rs:139-140` and `:198`, on
`self.machine.geometry`, which `Machine::layout` checked with `valid()` before
anything else (`boot.rs:631`).

**Contract.** Values of the machine and Start-up state: the kernel refuses to
start if "*E* would be more than 4,096 or is not the entries of one page, or
the processor has no large page, or the page sizes the kernel would use are
not one per level, or the user range would not leave the reserved slot …". No
kernel runs on a geometry that `valid` refuses, so no call of `canonical` sees
one.

**Verdict.** **Refuted** as a defect (the input cannot reach the function in
the model or under the contract). The fail-open behaviour with overflow checks
off is true, and a kernel in Zig with safety checks would trap instead. A
`debug_assert!(self.valid())` or one line of documentation ("for a geometry
`valid` accepts") is a free hardening, not a correction.

## A4. `firing_instant` at `TIME_LIMIT`

**Reproduction.** `ver2_a4_firing_instant_at_the_limit_overflows` (abi):
panics at `TIME_LIMIT`; `TIME_LIMIT - 1` gives itself. Reproduced.
`ver2_a4_timer_set_refuses_a_deadline_at_the_limit` (model): `timer_set` with
deadline `TIME_LIMIT` returns `Err(Invalid)` (the guard at
`model/src/sched.rs:1061`), and it is the function's only caller
(`sched.rs:1065`).

**Contract.** "With *x* the smaller of deadline + tolerance and 2^63 − 1, the
firing instant *f* is the number between the deadline and *x* …": the
definition has no value for a deadline of 2^63, and `TIME_LIMIT: u64 = 1 << 63`
bounds every instant; `timer_set` refuses it.

**Verdict.** **Refuted** (unreachable, by a refusal the contract states).
Severity: none.

## A5. `DeviceEntry::used` asserts alignment on the size, not on 128 bytes

**Reproduction.** `ver2_a5_a_device_entry_below_128_bytes_loses_its_low_base_bits`
(abi): `used(0x1041, 0)` reads back `(0x1000, 1)`; at one page it reads back
exactly. Reproduced. The callers: `boot.rs:822` keeps only ranges of at least
a page; `blocks.rs:308-316` halves an entry, which `memory_split` allows only
for "a device entry of more than one page".

**Contract.** The entry's own documentation and the contract: "the base
(aligned on the size, at least one page)"; `memory_split` "must be a block
capability of a device entry of more than one page".

**Verdict.** **Refuted** (the contract's precondition, at least a page, is held
by every writer, and the gate writes the device table). Hardening: the
assertion can say what the documentation says, `log2 >= 12` (or the page
shift), at no cost.

## A6. `AttachWord` keeps 4 KB clear whatever the page

**Reproduction.** `ver2_a6_an_attach_word_takes_a_root_aligned_on_4_kb_only`
(abi): `new(Pinned, 0x2000)` is accepted and round-trips through `from_raw`.
Reproduced. Every writer passes the base of an iospace root frame the node
built (`memory.rs:887`, `units.rs:447-448`, `units.rs:731` keeps a root
already written), and attach words are written only by the gate.

**Contract.** G9: "The tables of an `iospace` follow G2 to G5 as CPU tables
do: classes *iospace table of level k* and *iospace root with n devices
attached*, written only by the gate"; the gate reads the class of the root's
page before it writes the word. A root that is not a page base has no page of
its own and fails that check in a correct gate.

**Verdict.** **Refuted** (no writer can produce such a root; a faulty kernel
writes attach words only through the gate). Hardening, optional: `new` could
take the page and refuse `root % page != 0`; it would change `abi/`, so I do
not recommend it now.

## A7. `trace_index` of sequence 0 or of a ring of no entry

**Reproduction.** `ver2_a7_trace_index_of_sequence_0_and_of_no_entry_panic`
(abi): both panic. Reproduced. In the model the sequences start at 1
(`model/src/debug.rs:66-67`), the writer increments (`debug.rs:94`) and the
reader takes `max(1, …)` (`debug.rs:292`); the ring sizes are the constants
256 and 768.

**Contract.** "the machine start-up … starts every debug area at sequence 1",
and the reader reads "for each *s* from max(1, *n* − *N*) to *n* − 1". But
there is one way in that the author did not name: "**Across nodes and
generations.** An area belongs to its core for the whole boot, whatever node
runs there: a core that starts in a node keeps its area, and if the header's
magic and version are right it sets the node slot and generation and goes on
from the next sequences found there". A faulty kernel writes its own core's
area (it is its memory), so it can leave a header with the right magic and a
next sequence of 0 (or of 2^64 − 1). The next node's honest kernel on that
core then "goes on" from 0, and its first trace computes `0 − 1`: a trap in a
kernel with safety checks, a write to the wrong index otherwise.

**Not run** end to end: the model has no input for a faulty kernel's stores
into its own debug area (the areas live in `table.crash` and only
`Model::write` changes them), so the path stops at the abi function.

**Verdict.** The entries-of-0 case: **refuted** (constants). The sequence-0
case: **real, the contract's fault**, through the adoption rule quoted above.
The guarantee it touches is availability only (the successor kernel stops at
its first trace); memory is not reached. Severity: **low**.

**Correction.** Contract, in "Across nodes and generations", change "and goes
on from the next sequences found there" to "and goes on from the next sequences
found there **if each is at least 1 and below 2^63**, otherwise it clears the
area and starts at 1". Two comparisons at a node start, no new state; now,
since it is a rule of the start-up the oracle will compare.

## A8. `bandwidth` and `RemoteRef::new` assert their preconditions

**Reproduction.** `ver2_a8_bandwidth_and_remote_ref_assert_their_preconditions`
(abi): both panic. Reproduced. The model checks first: `sched_configure`
refuses unless `budget <= period <= SCHED_MAX_PERIOD_NS`
(`model/src/sched.rs:786-790`), and the grant serial is kept on 30 bits
(`model/src/grants.rs:115`, `(entry.serial + 1) & 0x3FFF_FFFF`).

**Contract.** The serial is "30 bits, one more each time the entry is reused"
(the grant table), and `sched_configure`'s plain arguments refuse a budget
above the period and a period above `SCHED_MAX_PERIOD_NS` (`1 << 36`, below
2^48).

**Verdict.** **Refuted**: the inputs are refused before the call by rules of
the contract; an `assert!` on an impossible input is the intended form in
`abi/`.

## A9. `PageSize::Large3` names a size no valid geometry has

**Reproduction.** `ver2_a9_no_geometry_with_a_fourth_page_size_is_valid`
(abi) and `ver2_a9_a_frame_of_the_fourth_page_size_is_unsupported` (model:
`untyped_retype` with page index 3 returns `Err(Unsupported)`). Both pass.

**Contract.** "A frame names its page size by an index: 0 the page, 1 the
first large page, 2 the second, 3 the third"; "**No page is larger than *E*
chunks (design choice, seventh review).** The page sizes stop at the second
large page …; a third … is never used, even where the processor has one … The
start-up page lists only the sizes the kernel uses"; "A page size that the
processor does not support is `unsupported` in `untyped_retype`".

**Verdict.** **Intended** (the index exists in the encoding, the design choice
excludes its use, and the refusal is in place). Severity: none.

## A10. `StartCore`'s comment and its declaration

**Reproduction.** `ver2_a10_start_core_is_28_listed_bytes_and_a_tail_word`
(abi): size 32, `reserved` at 24, `reserved_tail` at 28. Pass.

**Contract.** Entry `Cores`: "`StartCore` records (32 bytes) …: hardware
identifier … (u64); slot … (u32); kind (u16); flags (u16 …); number of hardware
threads, highest performance level, most efficient performance level,
efficiency class (u8 each …); package (u32); reserved (u32)". The fields the
contract lists, its own `reserved (u32)` included, take 8 + 4 + 2 + 2 + 4 + 4
+ 4 = 28 bytes; the record is 32. The `abi` comment says exactly that ("The
fields the contract lists take 28 bytes; the record is 32, so a reserved word
ends it"); the author counted `reserved` as not listed.

**Verdict.** **Refuted** for the code. The contract's row is four bytes short of
its own size; a tidy-up, no guarantee involved: end the row with "reserved
(u32), reserved (u32)". Severity: none.

---

## Report D: what it is, and how I judged it

Every finding of report D is about the checker (`model/src/check*.rs`) or a
test of it, and every state was written into the model's fields by hand. For
a checker that is the right way to probe it (`scenarios/checker.rs` does the
same: "a valid state spoiled in one place, and the check's report"), so I did
not refuse the findings for it. But it changes the question: the model is at
fault through its *checker* only if the contract forbids the state and the
check does not report it; the model's *behaviour* is at fault only if a step
reaches the state. To answer the second question for D1, D2, D3 and D8, I
added each missing check to my copy and ran the whole `dodos-model` suite
(every scenario, the checker tests, the 24 × 5,000-step property test and the
seven seeded explorations), each step followed by the whole check:

```
nix develop -c cargo test -p dodos-model --no-fail-fast -- --skip ver2_a1_a_release --skip ver2_a1_after --skip ver2_a1_a_revoke
test result: ok. 534 passed; 0 failed; 0 ignored; 0 measured; 3 filtered out; finished in 69.92s
(then the 17 integration test binaries: 14, 33, 347, 13, 20, 25, 10, 6, 4, 5, 16, 37, 15, 45, 20, 12, 0 passed, none failed)
```

(The three skipped tests are the A1 attack proofs, which fail once the A1
correction is in the same copy, as they should.) A first form of the D3 check
failed 43 tests, and that told me something; it is reported under D3. Then I
removed every correction (`git apply -R` of my patch) and ran the tests that
expect the corrected behaviour: all seven fail, as below; and I put the
corrections back.

```
test ver2_d1_… ... FAILED   left: Ok(())
test ver2_d2_… ... FAILED   left: Ok(())
test ver2_d3_… ... FAILED   left: Ok(())
test ver2_d8_… ... FAILED   left: Ok(())
test ver2_d4_… ... FAILED   left: None   (the check panicked)
test ver2_d5_… ... FAILED   left: None   (the check panicked)
test ver2_a1_fixed_… ... FAILED   left: Err("node 1: 58: translation under no grant")
```

## D1. A core runs a thread that does not hold its running context

**Lines.** `model/src/check/sched.rs:161-170` (`check_choice`) checks
`core.running` against the queues and the address space of `core.thread`, and
never that `core.thread` is the holder of `core.running`. The model sets both
together at every choice: `self.cores[at].thread = picked.and_then(|(context,
_)| self.holder(context))` (`model/src/sched.rs:368`).

**Reproduction.** `ver2_d1_a_core_running_a_thread_that_does_not_hold_its_context_is_reported`:
on a node of two cores, a second thread configured by calls, then
`cores[0].thread` set to it. Without my check `Model::check()` is `Ok(())`
(the author's result, reproduced); with it, `Err("46: thread of the running
context")`. The whole suite holds the added check: no step reaches the state.

**Contract.** "What runs next" chooses a scheduling context and runs its
holder; the model's own rule 46 says "the running context of each core is its
choice …; the thread it runs … has an address space that is not dying". The
thread a core runs is the holder of the context it charges; a state where the
two differ breaks admission (one context charged, another thread running).

**Verdict.** **Real, the model's fault, in its checker only** (the contract
forbids the state, the check does not report it, no step of the model reaches
it). Severity: **low** (a gap in the net; it would hide a future bug of the
choice).

**Correction.** In `check_choice` (`model/src/check/sched.rs`), after the
existing clauses of 46:
`let holder = core.running.and_then(|(context, _)| self.holder(context));`
`ensure(pending || core.thread == holder, "46: thread of the running context")?;`
(the exception for a pending reschedule is the one the rule already makes).
Test: the one above.

## D2. A core has loaded a root that is not its thread's

**Lines.** `model/src/cores.rs:540-546` (`load_root`) sets `loaded` from
`core.thread`'s address space, not dying; `loaded` is read by one check,
`model/src/check/node.rs:113`, and nothing checks its value. Confirmed by
`grep loaded model/src/check*`.

**Reproduction.** `ver2_d2_a_core_that_loaded_another_space_is_reported`:
another `aspace` made by a call, then `cores[0].loaded` set to it. Without my
check `Ok(())`; with it `Err("G7: root a core loaded")`. The whole suite holds
the check.

**Contract.** G7: "A root is loaded only if it is a table page of the top
level owned by this node", and the model's `load_root` documents itself as
"The root a core loads for the thread it runs (G7)". The TLB rule of
`check_tlb` takes "usable" from `loaded` alone, so a wrong `loaded` would also
blind that check.

**Verdict.** **Real, the model's fault, in its checker only.** Severity:
**low**. The author's "a user thread executing on another party's
translations" is not reachable: the space would still be one of the node's
own (G7 holds), and no step produces the state.

**Correction.** In `check_choice`, the expression of `load_root` as a check:
`let space = core.thread.and_then(|t| self.threads.get(&t)).and_then(|t| t.aspace).filter(|&a| !self.dying(a));`
`ensure(pending || core.loaded == space, "G7: root a core loaded")?;`
Test: the one above.

## D3. The domain numbers of a node's iospaces are not checked

**Lines.** `model/src/check/memory.rs:159-164` counts the iospaces a unit
serves against the unit's number of domains, and never reads
`Model::domains`. Confirmed.

**Reproduction.** `ver2_d3_a_domain_number_outside_the_node_s_range_is_reported`:
an iospace made by a call, put on unit 0, given domain 255, which is outside
node 0's range on a machine of one node (`domain_range` 1..=254). Without my
check `Ok(())`; with it `Err("39: domain number outside the node's range")`.

What I learned on the way: the author's first claim, "a domain number is kept
only while the iospace serves a device", is **not** an invariant of the model,
and should not be. My first form of the check required it and failed 43 tests
(for example `pass17::an_attach_through_another_nodes_unit_uses_a_domain_number_of_the_requesters_range`:
`Err("node 2: 39: domain number of an iospace with no device")`). The model
takes the number at the attach (`memory.rs:892`) and the device enters the
iospace's header only at the answer done, as the contract says ("the device
enters the iospace's header only at the answer done"). The two claims that
hold are: the number lies in the node's range on each unit of its iospace,
and no two iospaces of one unit share one; and, since `units` only grows and
is set with the number (`memory.rs:892-894`), an iospace with a number is on
at least one unit (which catches the author's exact state). With those three
clauses the whole suite passes.

**Contract.** "Domain numbers are shared out by node slot (D-134) … node slot
*s* owns the numbers 1 + *s* × *d* to (*s* + 1) × *d* … A node takes the number
of an iospace from its own range when the iospace gets its first device on the
unit, and frees it with the last", and the reason: "two context entries under
one number with two roots would let translations cached for one node's device
serve another's".

**Verdict.** **Real, the model's fault, in its checker only.** Severity:
**low** (the model is right on every path the suite runs; the holder's gate
also checks the range, `pass17`).

**Correction.** At the end of `check_devices` (`model/src/check/memory.rs`):
for each `(space, domain)` of `self.domains`: `aspaces[space].units` is not
empty ("39: domain number of an iospace on no unit"); for each unit of it,
`self.domain_range(unit, self.node).contains(&domain)` ("39: domain number
outside the node's range") and `(unit, domain)` not seen before ("39: domain
number shared"). Test: the one above.

## D4. The check of scheduling panics on a lend to a thread that does not exist

**Lines.** `model/src/check/sched.rs:40`, `runs` indexes `self.threads[thread]`;
`holder` takes the receiver of the top lend (`:47-48`) before rule 44, later
in the same function, checks that the receiver is live.

**Reproduction.** `ver2_d4_a_lend_to_no_thread_is_reported_not_a_panic`. Before
the correction the check panics (`left: None` under `catch_unwind`); after it,
it returns `Err("41: queue of a context")`: rule 41 comes before 44 in the
function and already rejects the state, so the author's expected "44: lend"
is not the first report, but the state is reported. The state is written by
hand; no step makes a lend to a thread that does not exist (rule 44 holds on
the whole suite).

**Contract.** None at stake: the checker is the model's tool. A panic still
fails the test that reaches the state, with a worse message.

**Verdict.** **Real, the model's fault (robustness of the checker).** Severity:
**low**.

**Correction.** `model/src/check/sched.rs:40`:
`let runs = |thread: &ObjId| self.threads.get(thread).is_some_and(Self::runnable_thread);`
Test: the one above.

## D5. The check of the debug area panics on a next sequence of 0

**Lines.** `model/src/check/debug.rs:23-24`: `next - 2` is computed before
`next >= 1` is tested.

**Reproduction.** `ver2_d5_a_ring_whose_next_sequence_is_0_is_reported_as_88`:
before the correction the check panics; after it, `Err("88: kernel ring")`.
State written by hand; in the model the sequence starts at 1 and only grows.

**Contract.** "starts every debug area at sequence 1". Together with A7: the
contract lets a kernel adopt the next sequences a faulty predecessor left in
its core's area, so a next sequence of 0 is a state the contract can produce
today (not the model); the checker should report it as 88 rather than panic.

**Verdict.** **Real, the model's fault (robustness of the checker).** Severity:
**low**.

**Correction.** The last two lines of `ring_holds`:
`next >= 1 && placed && (next == 1 || ring[((next - 2) % entries) as usize].seq == next - 1)`.
Test: the one above.

## D6. The checker's test of G6 is satisfied by another report

**Lines.** `model/src/scenarios/checker.rs:520-545`: the assertion accepts
`report.ends_with("G6: …") || report.contains("58")`.

**Reproduction.** `ver2_d6_the_checker_s_g6_state_is_reported_by_58`: the
same state gives exactly `Err("node 1: 58: leaves of a use entry")`. Passes:
reproduced. The test therefore never sees G6.

**Contract.** Not involved. The file's own promise ("A check that cannot fail
is caught here") is what the test misses. G6 is not unguarded: 
`pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6`
reaches it and asserts the exact message, and my A1 run reaches it from the
holder's side.

**Verdict.** **Real, the model's fault (a test that does not test what it is
named after).** Severity: **low**.

**Correction.** Replace the state of
`a_grant_freed_while_its_holder_translates_to_it_is_reported` by D7's state
(below) and assert the message exactly with `assert_eq!`. The test that fails
without it is the test itself: with G6's check removed, D7's state gives
`Ok(())` on the machine and the `assert_eq!` fails, which the current
disjunction never does.

## D7. A shorter state that reaches G6

**Reproduction.** `ver2_d7_g6_reports_a_record_unmapping_under_a_freed_grant`:
after a grant made by calls, the grant entry cleared and the use entry's
leaves set to 1 in the machine table, and node 1's capability given a record
*unmapping*: `node(1).check()` is `Ok(())` and `System::check()` is
`Err("G6: a grant freed while its holder translates to it")`. Passes.

**Verdict.** Not a defect (the author says so): **refuted** as a finding,
confirmed as the repair of D6. A record stays *unmapping* "until it is"
complete (contract, the guarantee of unmapping), so the shape is one the
contract allows on the holder; the grant entry freed under it is the A1 state.

## D8. A thread waits on a unit request that is not there

**Lines.** No check reads `Model::unit_requests` for a waiter; rule 14 leaves
out the bounded waits (`model/src/check.rs:706-708`, `Thread::bounded`,
`lib.rs:747-755`). Confirmed.

**Reproduction.** `ver2_d8_a_wait_on_no_unit_request_is_reported`: a thread
configured by calls, then its wait set to `Wait::Unit(0)` with an empty table.
Without my check `Ok(())`; with it `Err("14: a wait on no unit request")`. The
whole suite holds the check.

**Contract.** "**waiting for a unit**, for the confirmation of a unit request
…, which ends at the confirmation, with `busy` when the unit is found failed,
and never at the death of the role's holder, since the request is kept and
sent to the next holder … `thread_cancel` ends none of them: each is bounded."
A wait with no request would never end, against "Every call is bounded".

**Verdict.** **Real, the model's fault, in its checker only.** Severity:
**low**. (The author's further items, the entry's role, epoch and operation,
and `Wait::Hand`, I did not check: the first is what the holder judges, and I
had no time-bounded way to state the second as an invariant.)

**Correction.** In `check_waits` (`model/src/check.rs`), after rule 14: for
each thread whose wait is `Wait::Unit(index)`,
`unit_requests[index]` is `Some` with `waiter == Waiter::Thread(Some(id))`
("14: a wait on no unit request"). Test: the one above.

## D9. `ensure(true, …)` at the end of `check_tasks`

**Lines.** `model/src/check/tasks.rs:55`. Confirmed by reading; the loop above
it does the work.

**Verdict.** **Real, the model's fault (dead code).** Severity: **none** (a
nit).

**Correction.** End the function with `Ok(())`. I made the change in my copy;
the whole suite passes (above). No test can fail for it, since it changes no
behaviour.

---

## Corrections applied in my copy

All in `/private/tmp/dodos-pr3-ver2-AD-deepseek`, uncommitted, saved as a
patch at
`/private/tmp/claude-501/-Users-btw-Documents-repos/5c8846ae-7acb-4ca2-ba00-5657909c6753/scratchpad/ver2-ad-fixes.patch`
(155 lines):

- A1: `Model::refused(&self, from, message)` refuses `header.sender != from`;
  `consume` passes `from`; the four direct calls in
  `scenarios/crossing.rs:579-584` pass the sender as the ring (no assertion
  changed).
- D1, D2: two clauses in `check_choice`. D3: three clauses at the end of
  `check_devices`. D8: one loop in `check_waits`. D4: `runs` with `get`. D5:
  the guard before the subtraction. D9: `Ok(())`.

With all of them, every `dodos-model` test passes except the three A1 attack
proofs (which now fail: the forged messages are refused). That the A1
correction breaks no existing test says that no honest protocol of the model
ever writes a header naming another node than its ring's writer: the
correction costs nothing in behaviour. Without them, the seven tests that
expect the corrected behaviour fail (quoted above). Not run: `verify` (format
and clippy over the copy), Kani, the 16 KB and 32 KB geometries.

## Table

| Finding | Verdict | Severity | Correction in one line |
|---|---|---|---|
| A1 header names another node than its ring | Real, the contract's fault | Critical | Contract: the check adds "the sender it names is the node whose ring it came on"; model: `refused(from, …)` refuses `sender != from` |
| A2 module length in the last page panics the layout | Real, the model's fault | Low | `Machine::layout`: checked rounding and addition, `Refusal::Floors` on overflow |
| A3 `canonical` on an invalid geometry | Refuted (unreachable: start-up refuses the geometry) | None | Optional: document "for a valid geometry" |
| A4 `firing_instant` at `TIME_LIMIT` | Refuted (`timer_set` refuses it) | None | None |
| A5 `DeviceEntry::used` below 128 bytes | Refuted (contract: at least a page, held by every writer) | None | Optional: assert `log2 >= 12` |
| A6 `AttachWord` aligned on 4 KB only | Refuted (only the gate writes roots of frames) | None | None |
| A7 `trace_index` of sequence 0 | Real, the contract's fault (a faulty kernel's header is adopted); entries 0 refuted | Low | Contract: adopt the next sequences only if each is ≥ 1 and < 2^63, else clear and start at 1 |
| A8 `bandwidth`, `RemoteRef::new` assertions | Refuted (inputs refused first) | None | None |
| A9 `PageSize::Large3` | Intended (design choice: no page larger than *E* chunks) | None | None |
| A10 `StartCore` comment | Refuted (the comment is right) | None | Contract tidy-up: the row lists a second `reserved (u32)` |
| D1 core runs a thread not holding its context | Real, the model's fault (checker only) | Low | `check_choice`: `core.thread == holder(core.running)` unless a reschedule is pending |
| D2 loaded root not the thread's | Real, the model's fault (checker only) | Low | `check_choice`: `loaded` equals `load_root`'s expression unless a reschedule is pending |
| D3 domain numbers unchecked | Real, the model's fault (checker only; "only while serving a device" is not an invariant) | Low | `check_devices`: on a unit, in the node's range, unique per unit |
| D4 check panics on a lend to no thread | Real, the model's fault (checker robustness) | Low | `runs` uses `threads.get` |
| D5 check panics on next sequence 0 | Real, the model's fault (checker robustness) | Low | Test `next >= 1` before `next - 2` |
| D6 G6 test satisfied by 58 | Real, the model's fault (test) | Low | Use D7's state and `assert_eq!` the G6 message |
| D7 shorter state reaching G6 | Refuted as a defect (a proof, confirmed) | None | Becomes the state of D6's test |
| D8 wait on no unit request | Real, the model's fault (checker only) | Low | `check_waits`: a `Wait::Unit(i)` thread is the waiter of `unit_requests[i]` |
| D9 `ensure(true, …)` | Real, the model's fault (dead code) | None | End with `Ok(())` |
