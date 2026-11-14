# Review 4: the one-core model against the contract, the abi and itself

**Reviewer**: fourth independent review, asked by the two humans before the merge.
**Subject**: the executable reference model on branch `model`, commit `264423f`
("Defend every rule with a test, and reach the deep states at random"), in
`/Users/btw/Documents/repos/dodos-kernel/model/`.
**Artefacts compared**: the contract `Docs/architecture/kernel-interface.md`
(443 lines, read whole), the interface in code `dodos-kernel/abi/src/lib.rs`
(542 lines), and the model `src/lib.rs`, `src/caps.rs`, `src/ipc.rs`,
`src/check.rs`, `src/check/tests.rs`, `tests/calls.rs`, `tests/property.rs`
(8,090 lines of Rust in all).
**Method**: I read everything first, then applied **154 mutations** to a scratch
copy outside the repositories (`/tmp/mut/repo`), one rule at a time, and ran
either the fast suite (`--lib --test calls`, ~5 s) or the whole suite (~50 s)
for each. 139 compiled; 6 of those turned out to be no-ops and I discarded them;
**of the 133 real mutations, 127 were caught by a named test**. The 6 survivors
are reported as T1–T6: five are *numbers* no test pins, one is a limit whose
guard is loose. The original trees were left untouched (`git status` clean in
both repositories; nothing committed, nothing pushed).

**Verdict in one line**: I found **no wrong behaviour** in the model. Every
mutation of a rule that the contract fixes was caught. The model is a faithful
oracle. The findings below are about the *contract* (two internal contradictions
it should settle, one mechanism it promises and does not define, and one set of
wire values it never states), about *six rules it leaves undefined*, about *six
untested numbers or thresholds*, and about *the code being harder to re-read
than it needs to be*.

Baseline: `cargo test -p dodos-model` → 95 lib tests, 244 in `calls.rs`, 8 in
`property.rs`, all green (property: 24 seeds × 5,000 steps, 47 s).
`cargo test -p dodos-abi` → 11 green.

---

## 1. Findings, by severity

### 1.1 Wrong behaviour

**None.** I looked for one specifically with mutation testing, and the model
defends every rule that the contract fixes: the order of checks (four separate
order tests, including the header exception), the three kinds of slot, the
dying rules, both removal budgets, the fixed removal order, the depth rule in
all four places it applies, the second check at delivery, all-or-nothing
transfer at both ends, the `caps_dropped` flag on both sides, the reply object's
three states, the notification-before-caller order, and `grant` on reply
objects. 132 mutations of those rules were caught, most by the test whose name
states the rule.

Two areas deserve one line each, because a reader will wonder:

- The model never blocks, never recurses, and never loops unboundedly except in
  `remove` (bounded by 32 steps and the 128-slot budget) and `next_removed`
  (bounded by an `assert!` at twice the walk limit). Both match Rules 4 and 5.
- The random test checks `Model::check` after **every** call, and
  `apply` refuses a thread that cannot run, so the oracle cannot be driven
  outside the contract's state space.

### 1.2 Contract errors

#### C1. The start-up page cannot say which slot holds which capability (contract error)

**Where**: contract, *Start-up information*; `abi/src/lib.rs` `StartEntry`,
`StartKind`; `model/src/lib.rs` `boot()` (slots `START_SLOT_FIRST` and
`START_SLOT_FIRST + 1`).

**What is wrong**: the prose says "4 its `sched`, 5 `debug`; the others start at
slot 16 and **the start-up page gives the slot of each one**". But the page's
entries are `(kind, offset, length)` and the `Untyped` entry is described as
"the list of `untyped` ranges (address, size, device or not)". No entry carries
a slot number, in the contract, in `abi::StartEntry` (which is
`{kind, reserved, offset, len}`), or in the model (which hard-codes 16 and 17).
The first process therefore cannot know where its untyped, `core`, `irq`,
`iospace` or `debug` capabilities are, and neither can a kernel author.

**How I know**: read in the contract and in `abi`, and the model's `boot()` has
nothing to read a slot from.

**Suggestion**: give the `Untyped` (and `Cores`, `Irq`, …) entries a slot field,
or say that the fixed order of the list *is* the slot order from
`START_SLOT_FIRST` upwards. One sentence; it is the first thing the boot code
will need.

#### C2. A `frame` is an object in one table and not in the other (contract error)

**Where**: contract, *Objects* (row `frame`) versus *Object sizes* (last row,
"`frame` | No object: the capability slot holds the mapping record").

**What is wrong**: *Objects* lists `frame` among the kernel objects, and *Call
reference* makes it a kind that `untyped_retype` creates ("the page size and the
number of pages for a `frame`"), with a root capability, memory taken from the
untyped, and destruction when that root goes. *Object sizes* then says a frame
is not an object at all. Two honest kernel authors will disagree about whether a
frame consumes a kernel object, whether `check`'s "an object exists iff its root
capability does" applies, and whether the memory is released by the untyped.

**How I know**: read; the model takes the second reading with the memory of the
pages (only the pages, no object overhead — `caps.rs:41` `footprint`), which I
believe is what was meant, but nothing in the contract says so.

**Suggestion**: keep "no kernel object" in *Object sizes* and add, in
*Capabilities and objects*, "a frame takes only its pages from the untyped; its
capability alone records the mapping".

#### C3. `task_revoke` is "one operation" and `cap_revoke` returns `again` (contract error)

**Where**: contract, *Tasks and provenance*: "`task_revoke` removes every right
of the task **in one operation**. It is `cap_revoke` on the root of the task, so
it uses the same distributed protocol."

**What is wrong**: the Capabilities table says `cap_revoke` "Returns `again`
while descendants remain", and Rule 4 says every long operation runs in bounded
steps. The same object cannot be both. Note that *Tasks and provenance* carries
its own "Proposed" status, so this is not a defect of the decided text, but it
is a sentence a reader of the whole file will trip over.

**How I know**: read.

**Suggestion**: "in one operation" → "in one call, repeating while it returns
`again`".

#### C4. The dying-space exception is stated twice, with two different scopes (contract error)

**Where**: contract, *The derivation tree*, paragraph *Removal ends*: first "A
thread whose capability space is dying gets `gone` from every call except
`cap_delete` **on its own slots**", then, four sentences later, "A thread whose
capability space is dying gets `gone` from every call except `cap_delete`; once
the space is destroyed, from every call."

**What is wrong**: the second statement omits "on its own slots", which is the
whole point: whether a thread in a dying space may still `cap_delete` a slot
reached through a `via` capability. The model takes the strict reading
(`lib.rs` `cap_delete`: `if self.dying(own) && slot.via() != 0 { Gone }`), and
`thread_whose_capability_space_is_dying_deletes_its_own_slots_only` pins it, but
a kernel author reading the second sentence will implement the loose one.

**How I know**: read; confirmed by the test that exists for it.

**Suggestion**: delete the second sentence's clause, or write "except `cap_delete`
on a slot of its own space (a `via` is `gone` as any other use of a dying
object)". Also note the tension with the same paragraph's "before any argument is
looked at": deciding "its own slots" requires looking at `via`. Say that the
`via` of a slot address is looked at before the rule applies.

#### C5. `grant` means "through an endpoint" and the model also needs it on a reply object (contract error, wording)

**Where**: contract, *Rights* table (`grant`), versus *Call reference*, `send`
row ("`send`, and `grant` if the message lists capabilities") applied to "an
endpoint **or reply object**", and `reply_recv` ("`send` on the reply object,
then as `recv`").

**What is wrong**: the Rights table is the only place that says what `grant`
*means*, and it says "Transfer capabilities through an endpoint". The model
requires `grant` on a reply object for `send` and `reply_recv` carrying
capabilities (`ipc.rs` `Message::rights`, and both call sites;
`message_with_capabilities_needs_grant` asserts it). An author implementing the
Rights table literally would forget the reply object.

**How I know**: read; `abi::Rights::GRANT`'s doc comment repeats the same narrow
wording, so the mistake is copied into the code's own documentation.

**Suggestion**: "`grant` | Transfer capabilities through an endpoint or a reply
object", in both the contract and `abi/src/lib.rs:122`.

#### C6. The numeric wire values live only in `abi/` (contract error, missing)

**Where**: contract has *Errors* (11 names, no numbers), *Rights* (8 names, no
bit numbers), *Objects* (16 kinds, no numbers), *Messages* (a header of label /
words / caps / flags, no bit layout).

**What is wrong**: the contract says "the contract of the kernel: its objects,
its system calls and the rules that bind them", and the README of the model says
the executable model, the oracle harness and the kernel are all written from it.
But an error number, a right bit, a kind number and the header layout are part of
the system-call interface, not of the architecture layer (which the contract
does delegate, in *Registers*, and only for "which register or which field of the
message page carries each one"). They exist only in `abi/src/lib.rs`. That is a
defensible design — `abi/` *is* the interface in code — but the contract nowhere
says so, and the result is that the contract alone is not enough for a kernel
author, which is the promise of the file's first paragraph.

**How I know**: read all three artefacts; the numbers appear in `abi` only
(`Error = 0..10`, `Rights` `1 << 0..7`, `ObjectKind = 0..15`,
`Header` label 0-31 / words 32-38 / caps 39-41 / flags 42-63).

**Suggestion**: one sentence in *Call reference, one core*, in *Registers*: "the
numeric values of the errors, the rights, the kinds and the layout of the header
are fixed by the crate `abi/` and are provisional like the counts around them."

#### C7. `vcpu` is a reserved kind in the contract and absent from `ObjectKind` (minor)

**Where**: contract *Objects*, last row; `abi::ObjectKind` (16 variants, 0..15).

**What is wrong**: the contract says "`vcpu` | Reserved name, not built." The
kind numbers are wire values; reserving a name with no number is fine, but a
reader will ask whether 16 is taken. Say "no number is reserved".

### 1.3 Undefined (the contract is silent; the model chose; a kernel author must guess)

#### U1. What becomes of a thread when its address space or its fault endpoint is destroyed (undefined)

**Where**: contract, *Threads* (`thread_configure` accepts an `aspace` and a
fault endpoint and says nothing more); `model/src/lib.rs` `thread_configure`,
which checks both and **keeps neither** (and says so: `CONTRACT-GAP (Threads)`).

**What is wrong**: this is the largest hole in the modelled part. Three
consequences are unstated: does a thread whose aspace is destroyed fault, get
`gone`, or keep running? Is a thread woken when its fault endpoint is destroyed
(by the general "destroying an object wakes every thread that waits on it")?
Must `thread_configure` be refused when the old aspace is dying? The model
cannot answer any of them because it stores neither, so the oracle will not
catch a kernel that answers them differently.

**How I know**: read; the model is explicit about the gap, which I credit, but a
gap in the oracle is a gap in what the kernel is tested against.

**Suggestion**: at minimum, decide whether `thread_configure` records the fault
endpoint, and store it in the model so that "destroying the fault endpoint wakes
the thread with `gone`" or "does nothing" is decided once. If the answer is "the
architecture layer faults the thread", say it and say the model does not cover
faults.

#### U2. May a dying `cspace` be grown? (undefined)

**Where**: contract, *The derivation tree*, "so a dying space only shrinks";
`model/src/caps.rs` `cspace_grow`, which does not look at the dying flag.

**What is wrong**: a thread holding `manage` on a dying space (from a live
space) can call `cspace_grow` on it. The model allows it: 4 KB more is taken,
128 empty slots are added, and the sweep will walk past them. The contract's
"only shrinks" is about capabilities, not slots, so both readings survive; but
one is a way to make a bounded removal take unboundedly long (grow between two
`cap_delete` calls).

**How I know**: read; I verified the model accepts it by reading
`cspace_grow` — no test covers it, either way.

**Suggestion**: say that only the *capabilities* of a dying space only shrink,
and that `cspace_grow` on a dying space is `gone` (one line in the `cspace_grow`
row) — the second is the one I would choose.

#### U3. A transfer whose *sender's* slots fail the second check because the sender's space began to die (undefined)

**Where**: contract, *Transfer of capabilities*: "Checked again at delivery,
against what the listed slots hold at that moment: the same checks as when the
call was made". *Removal ends* only states the receiver side ("a delivery to a
receiver whose receive range is in a dying or destroyed space drops the
capabilities").

**What is wrong**: if the caller's own space starts dying between the call and
the delivery, the sender's slots now answer `gone` (§ *Removal ends*: a thread
whose space is dying gets `gone` from every call), so the second check fails and
the model drops the capabilities although the capability being moved is alive.
A reader may well expect the transfer to succeed, because the *capability* is
not dying.

**How I know**: read the code (`ipc.rs` `deliver` re-runs `listed` on
`parcel.sender`) and the test that pins it
(`capabilities_of_a_caller_whose_space_began_to_die_are_dropped_at_delivery`).

**Suggestion**: one clause in *Transfer of capabilities*: "if the sender's slots
themselves are gone, the same as a failed check".

#### U4. What a call outside the modelled groups returns (undefined)

**Where**: contract, *System calls*: "The other groups are specified when their
model is written"; `model/src/lib.rs` `Syscall::Other` → `Err(Unsupported)`.

**What is wrong**: the contract fixes `unsupported` for a *kind* this version
does not make, and defines the error as "Not available on this architecture or
kernel version". It does not say what `aspace_map` or `yield` returns in the
one-core version. `unsupported` is a reasonable choice, `invalid` ("wrong object
type") is another, and the model's choice silently becomes the oracle's answer.

**Suggestion**: one sentence in *System calls*: "in a version whose model does
not yet cover a group, its calls return `unsupported`".

#### U5. The start-up space's size and the start-up untypeds' sizes (undefined, minor)

**Where**: contract, *Start-up information* ("its size is fixed by the boot
image", "the model gives … the two untypeds below"); `model/src/lib.rs`
`BOOT_UNTYPED_BYTES` 64 MiB, `BOOT_DEVICE_BYTES` 1 MiB, one segment.
**What is wrong**: nothing, but these three numbers are now the oracle's boot
state, and they are stated only in the model. If the numbers are meant to be
free, say so where the model says it.

#### U6. `thread_suspend` on a thread bound to no capability space (undefined, minor)

Model: `Done` (only `thread_resume` is specified to be `busy`). Read from the
code; no test covers it.

### 1.4 Untested (a rule no test defends; confirmed by a surviving mutation)

#### T1. The message limit of 64 words is not pinned anywhere (untested)

**Where**: `abi/src/lib.rs:18` `MAX_WORDS`; every test writes `MAX_WORDS + 1`.
**What is wrong**: changing `MAX_WORDS` to 65 **and** to 127 leaves the whole
suite green (`cargo test -p dodos-model`, 347 tests, including the random test,
whose generator also uses the constant). The contract says 64 and a kernel will
hard-code 64 in its message page; nothing would catch a drift. The other limits
*are* pinned by literals: 4 by a `5` in `check/tests.rs`
(`receive_range_of_more_than_4_slots_that_waits_is_reported`), 32 by `33` in
`one_call_wakes_a_thread_of_a_reply_object_at_each_of_its_32_steps`, 128 by the
`Output::Slots(128)` assertion and by the 128-call test, 192 by `193`.
**How I know**: run (`max_words_65`, `max_words_127` → SURVIVED).
**Suggestion**: one assertion with a literal, e.g. in `abi`'s tests:
`assert_eq!((MAX_WORDS, MAX_CAPS, REG_WORDS), (64, 4, 6))`, and the same for the
tree depth and the start-up slots. It is the cheapest possible guard and it also
documents that these are wire numbers.

#### T2. The numbers of the error codes are not pinned (untested)

**Where**: `abi/src/lib.rs` `Error` (0..10); `abi`'s `error_codes_are_stable`
asserts only 0, 1, 2 and 10.
**What is wrong**: `Denied = 3` and `Invalid = 4` can be swapped and everything
stays green (run: SURVIVED). A kernel that returns the wrong number is a kernel
whose error handling differs from the oracle's and nothing notices.
**Suggestion**: assert all eleven values in `error_codes_are_stable`.

#### T3. The bits of the rights are not pinned (untested)

**Where**: `abi/src/lib.rs:114-123`.
**What is wrong**: swapping `READ` (1<<0) and `WRITE` (1<<1) leaves everything
green (run: SURVIVED). Same class as T2, same one-line fix.

#### T4. Invariant 20 (depth ≤ 64) is only guarded to within two levels (untested)

**Where**: `model/src/check.rs:204`; `check/tests.rs::tree_deeper_than_64_is_reported`
derives `TREE_DEPTH` links on top of a capability already at depth 3, so the
final depth is 67.
**What is wrong**: raising the limit inside `check` from 64 to 66 leaves the
whole suite green (run: SURVIVED). The other 11 invariants I mutated (5, 14, 15,
17, 19, 21, 22, 23, 25, 28, 29) are all caught by their own test.
**Suggestion**: build the chain so that its last link sits at exactly
`TREE_DEPTH`, and add a test at `TREE_DEPTH + 1`.

#### T5. `START_SLOT_FIRST` is only caught incidentally (untested)

**Where**: `abi/src/lib.rs:39`.
**What is wrong**: changing 16 to 17 is caught only by the random test, through
the slot layout its generator chose (`objects_of_every_kind_are_seen_dying`
fails); no unit test mentions 16. It is a contract number and the start-up page
promises it.
**Suggestion**: fold into T1's one-line assertion.

#### T6. The `size == 0` rule for the other kinds is tested with one value (untested, small)

`footprint` accepts `size == 0` for every kind but `untyped`, `frame` and
`cspace`; `size_argument_is_zero_for_the_other_kinds` tries only `1`. Making
`Thread` accept `size == 7` passes (run: SURVIVED). Low value, one extra loop
iteration.

### 1.5 Minor

#### M1. `LONGEST_WALK = 3 * TREE_DEPTH` is the right number for the wrong reason (minor)

`model/src/lib.rs:356`. The contract's 192 is `128 + 64`: "at most 128
capabilities … at most 64 more". The 128 comes from the number of slots in a
segment, not from the tree depth; `3 * 64` is a coincidence. If `TREE_DEPTH` ever
becomes 32, this expression gives 96 and the contract gives 160. Write
`CSPACE_SEGMENT_SLOTS as usize + TREE_DEPTH`, or `128 + TREE_DEPTH` with a
comment. Related, same line: the contract says the walk is "shorter than 192
capabilities (the longest one that can be built has 191)", while invariant 24
accepts `== 192` and `walk_of_a_removal_longer_than_192_capabilities_is_reported`
only refuses 193. Two off-by-ones that cancel; state one of them.

#### M2. Constants a kernel needs are private to the model (minor)

`caps.rs:15` `DIRECTORY_BYTES = 8`, `caps.rs:18` `REMOVAL_SLOTS = 128`,
`caps.rs:20` `PAGE = 4096`, the `1 << 20` maximum in `footprint`, and **every
object size** (thread 1 KB, sched 128, endpoint/reply/notify 64, aspace 4 KB) —
the contract's *Object sizes* table, in code, only here. `abi/` carries
`REMOVAL_STEP`, `TREE_DEPTH`, `CSPACE_SEGMENT_SLOTS`, `SLOT_BYTES`, `MAX_*` and
the start-up slots, but no size. The kernel will need all of them and will take
them from the model or, worse, from the contract by hand. See the table in § 2.

#### M3. The receive range's 4 is `MAX_CAPS` (minor)

`lib.rs` `window()` uses `MAX_CAPS` for "the receive range … at most 4". Two
separate rules of the contract share one constant; if the message limit ever
moves to 8, receive ranges silently become 8 too. A `RANGE_SLOTS` in `abi`
would keep them apart.

#### M4. `unlink` returns a value no caller uses (minor)

`ipc.rs:454` returns `Wait`; all nine call sites discard it. Drop the return and
it becomes `std::mem::take` instead of `mem::replace` plus a return.

#### M5. `abi::Error::NoSlot`'s doc contradicts the contract (minor)

`abi/src/lib.rs:96`: "No free capability slot." The contract says "The
destination slot is not empty, or the capability space is at its maximum", which
is a different (and correct) rule: the model returns `no_slot` for both, and it
is *not* about a free slot. `abi` is the documentation a kernel programmer reads
in the IDE; fix it.

#### M6. `CONTRACT-GAP (Messages)` is mislabelled (minor)

`ipc.rs:54` `received()` says "the receiver gets the marks and the identifier of
the sender's task, which the one-core reference does not have". The contract
*does* fix them; the *model* does not model tasks. That is a model reduction, not
a contract gap. The marker is otherwise used well (two genuine gaps: start-up
information and thread_configure).

#### M7. `Header::is_fast` is used only by its own test (minor)

`abi/src/lib.rs:341`. Either the model should use it (it never takes the fast
path, correctly, since it models no registers) or the doc should say it is for
the kernel.

#### M8. `Census` is test-only API in the shipped module (minor)

`check.rs:18-70`, `census()`. It exists so the random test can assert what it
reaches; it is `pub`, documented as "no part of the behaviour", and it makes the
invariant module 70 lines longer for the humans to read. A `#[cfg(feature =
"census")]` gate documents "this is not the contract".

#### M9. Naming: `space` is three different things (minor, but see § 4)

`Model::space()` (resolve a slot address), `CSpace` (the object), `space` (a
local variable of type `ObjId` naming a capability space), `Place` (a space plus
an index). Plus `Call::Call` (the enum and its variant), `Syscall::Call`,
`Model::call`. `own()` is a particularly misleading name for "the thread's
bound capability space, unless it was destroyed".

#### M10. The start-up page has fields the contract does not mention (minor)

`abi::StartHeader.magic`, `StartEntry.reserved`, and `START_MAGIC`. Additive and
harmless, but the contract's *Start-up information* claims to describe the page
and does not mention a magic or a version check.

---

## 2. The three artefacts, constant by constant

`⚑` marks a value a kernel needs but cannot get from `abi/` (§ M2).
`✓` marks agreement I checked and found correct.

| # | Value | Contract | `abi/` | model | Verdict |
|---|---|---|---|---|---|
| 1 | message words in registers | 6 ("6 on x86-64") | `REG_WORDS = 6` | uses `is_fast` only via `abi` | ✓ |
| 2 | message words in all | 64 | `MAX_WORDS = 64` | `MAX_WORDS` | ✓ value, **untested** (T1) |
| 3 | capabilities per message | 4 | `MAX_CAPS = 4` | `MAX_CAPS` | ✓ |
| 4 | slots per receive range | 4 | — (uses `MAX_CAPS`) | `MAX_CAPS` | ⚑ one constant, two rules (M3) |
| 5 | bytes of a capability slot | 32 | `SLOT_BYTES = 32` | `SLOT_BYTES` | ✓ |
| 6 | slots per `cspace` segment | 128, "4 KB" | `CSPACE_SEGMENT_SLOTS = 128` | `SEGMENT_BYTES = 128*32 = 4096` | ✓ |
| 7 | capabilities per removal step | 32 | `REMOVAL_STEP = 32` | `REMOVAL_STEP` | ✓ |
| 8 | slots examined per call of removal | 128 | **absent** | `REMOVAL_SLOTS = 128` (private) | ⚑ M2 |
| 9 | depth of the tree | 64 | `TREE_DEPTH = 64` | `TREE_DEPTH` | ✓ value, **untested** (T4, T1) |
| 10 | bound on the removal walk | shorter than 192 (191 built) | **absent** | `LONGEST_WALK = 3*TREE_DEPTH` = 192, invariant allows 192 | ⚑ + off-by-one (M1) |
| 11 | maximum `cspace` slots | "non-zero multiple of 128, at most 2^20" | **absent** | `size <= 1 << 20` (private literal) | ⚑ M2 |
| 12 | directory | "8 bytes per 128 slots, rounded up to a power of two" | **absent** | `DIRECTORY_BYTES = 8`, `next_power_of_two` | ⚑ M2 |
| 13 | `untyped` child size | power of two, ≥ 4 KB | **absent** | `is_power_of_two() && size >= PAGE` | ⚑ M2 |
| 14 | 4 KB | implied everywhere | `PageSize::Size4K.bytes()` | `PAGE = 4096` (private) | ⚑ M2 |
| 15 | page sizes | 4 KB / 2 MB / 1 GB | `PageSize` = 12/21/30 bits | `page.bytes()` | ✓ |
| 16 | thread size | 1 KB (no vector state) | **absent** | `1024` | ⚑ M2 |
| 17 | sched size | 128 B | **absent** | `128` | ⚑ M2 |
| 18 | endpoint/reply/notify | 64 B | **absent** | `64` | ⚑ M2 |
| 19 | aspace/iospace | one root table, 4 KB | **absent** | `PAGE` | ⚑ M2 |
| 20 | task size | 256 B | **absent** | not made (`Unsupported`) | ⚑ M2 |
| 21 | timer/irq size | 64 B | **absent** | not made (`Unsupported`) | ⚑ M2 |
| 22 | start-up slots | 1 cspace, 2 aspace, 3 thread, 4 sched, 5 debug, others from 16 | `START_SLOT_*` = 1,2,3,4,5,16 | uses `abi` | ✓ value, 16 **untested** (T5) |
| 23 | start-up: which slot holds which untyped | "the start-up page gives the slot" | no field for it | hard-coded 16, 17 | **C1** |
| 24 | errors | 11 names, in this order | `Error` = 0..10, same order | passes `Error` through | ✓ names; numbers **untested** (T2) |
| 25 | rights | 8 names, in this order | bits 0..7, same order | by name | ✓ names; bits **untested** (T3) |
| 26 | kinds | 16 + `vcpu` reserved | `ObjectKind` = 0..15, no `vcpu` | by name | ✓ except C7 |
| 27 | header | label 32, words, caps, flags (no widths) | label 0-31, words 32-38, caps 39-41, flags 42-63 | `Header::new` | ⚑ C6 |
| 28 | flag `caps_dropped` | named, no bit | `1 << 0` | `FLAG_CAPS_DROPPED` | ⚑ C6 |
| 29 | flag `notification` | named, no bit | `1 << 1` | `FLAG_NOTIFICATION` | ⚑ C6 |
| 30 | marks | 64 bits, bit 0 private, bit 1 untrusted | `PRIVATE = 1<<0`, `UNTRUSTED = 1<<1` | `Marks::NONE` only | ✓ |
| 31 | start-up page | version, entries `(kind, offset, length)` | `StartHeader`, `StartEntry`, 9 `StartKind` | not modelled | ✓ + M10 |
| 32 | object-size entry | "interface version and object sizes" | `StartKind::ObjectSizes` | not modelled | ⚑ no format fixed anywhere |
| 33 | `MAX_WORDS` boundary at 127 | — | `words()` is 7 bits | — | ✓ consistent |

**Calls** ✓: the contract's *System calls* group table lists exactly 45 calls
("about 45"); `abi::Call` has exactly 45 variants with the same names and the
same grouping (6 + 4 + 8 + 6 + 4 + 2 + 5 + 5 + 3 + 2), and no `repr`, so no
number leaks. The one-core reference covers 18 of them, and the model's
`modelled()` list matches the `Syscall` variants one for one. I found **no call
in one artefact and missing or renamed in another.**

**Where the parts outside the call reference contradict it**: C2 (frame),
C3 (task_revoke), C4 (the dying-space sentence), C5 (grant), and — the only
other one I found — *Objects* says a `reply` "returns the caller's budget" and
*Synchronous or asynchronous* says a `call` runs "on the caller's budget", while
the modelled call reference has no budget anywhere and `reply_recv` returns no
budget. That is scope, not contradiction, but a reader will look for the rule.

---

## 3. The contract as the only source: where two honest authors differ

I went through *Call reference, one core* rule by rule. Most of it is
unusually tight — the order of checks, the four budgets/limits, the order of
removal, the two-phase transfer and the notification-before-caller order are all
decided, and the model follows each one, with a test named after the rule. Below
are the places where I think two honest authors would **not** write the same
observable behaviour, or where I had to read the code to know the answer. For
each: reading A, reading B, and what the model does.

| # | Rule | Reading A | Reading B | Model |
|---|---|---|---|---|
| 1 | the header is read "right after the capability the call acts on (whose rights, `grant` included, are judged first with the number of capabilities the header states)" | the *limits* of the header are judged after the first capability's rights, so 5 caps with no `grant` is `denied` | the header's limits are part of reading the header, so it is `invalid` | **A** (`grant_is_judged_before_the_limits_of_the_header`). The sentence needs "its *rights* are judged first, its *limits* after" |
| 2 | "a slot becomes dead when its capability is removed by someone else" | `cap_delete` on a live capability leaves the slot **empty**; every other removal leaves it **dead** | every removal leaves the slot dead, and "by someone else" is redundant | **A**. This is the single most load-bearing distinction of the model (`Slot::Empty` vs `Slot::Dead`) and it is stated nowhere explicitly. Say it |
| 3 | a transfer whose sender's slots are gone at delivery | drop (the re-check fails) | deliver as at call time, because the sender's capability was alive then | **A**, and the contract only rules on the receiver's side (U3) |
| 4 | `send` on an **attached** reply object | `would_wait` ("`would_wait` if it is not armed") | `busy` — the object is in use by a thread | **A** (`send_on_an_attached_reply_object_would_wait`). Defensible, but say "idle or attached both give `would_wait`" |
| 5 | `reply_recv` that answers **and** finds a pending notification | answer, then return the notification (the object becomes idle) | return the notification and keep the reply armed | **A** (`reply_recv_answers_and_returns_a_pending_notification_before_a_caller`). Decided by "`send` on the reply object, then as `recv`", two tables apart from the notification rule |
| 6 | a `call` arriving while a notification is pending on a bound notify | the message is delivered, the word stays pending | the notification is delivered first, the message queues | **A** (the `call` row; no test names it, but `recv_returns_a_pending_notification_…` implies it) |
| 7 | `cap_delete` on a dead slot reached through a **dying** space's `via` | `gone` (any use of a dying object) | `Done` (the one exception is `cap_delete`) | **A** (C4, and `thread_whose_capability_space_is_dying_deletes_its_own_slots_only`) |
| 8 | `cspace_grow` on a dying space | allowed (only capabilities shrink) | `gone` | **A** (U2) |
| 9 | order of "kind, size, device rule" in `untyped_retype` | device rule, then kind, then size (`unsupported` after `invalid`) | kind, then device, then size | **A** (`untyped_retype_judges_the_kind_before_the_size`) |
| 10 | which of `no_slot` / `no_memory` wins when both are true | `no_slot` (step 4 lists it first) | `no_memory` (memory is the scarcer resource) | **A** (`no_slot_is_reported_before_no_memory`) |
| 11 | `thread_configure`'s fault endpoint and aspace | recorded, and the thread is woken when they are destroyed | accepted and forgotten | **B**, and the contract does not say (U1) |
| 12 | an object destroyed while a thread waits on it, when the removal's step budget runs out | the thread waits until a later call | the thread is woken with `gone` by the call that destroys the object | **B** (a wake costs one of the 32 steps) |

**The pairs that meet in one state**, as asked:

- **dying and suspended.** The model keeps them independent and consistent:
  `runnable()` needs "not suspended and not waiting", so a suspended thread in a
  dying space that is woken with `gone` gets its outcome and does *not* run; and
  `thread_resume` on a thread bound to a dying space succeeds
  (`thread_bound_to_a_dying_space_can_be_resumed`). The contract states both
  halves ("a thread bound to a dying space can be resumed"; "it runs again only
  when it is resumed") and I found no contradiction. ✓
- **dead slot and dying space.** Two different answers, both correct and both
  tested: a dead slot in a *live* space is `gone` for every use and `Done` for
  `cap_delete`; any slot in a *dying* space is `gone` even for `cap_delete`
  through a `via`, while `cap_delete` directly on it still works. The only
  ambiguity is C4, and the model takes the strict reading.
- **the 32 and the 128 running out in the same step.** `remove` spends a step
  before it walks, and `next_removed` can return `None` after moving the sweep
  past up to 128 slots; either way the answer is `again`, and the last
  capability removed in a call returns `Done`. There is no state in which a call
  returns `again` with nothing left to do: the loop reaches
  `if next == target { Done }` before it reaches the `steps == 0` test. ✓
- **a reply object armed while its caller is destroyed.** `destroy(Thread)` calls
  `unlink`, and `unlink` sets the object to `Idle`; the server is not woken (it
  is not waiting). That is exactly "when a caller disappears while its request is
  being served, the reply object becomes idle", and
  `reply_object_becomes_idle_when_its_caller_disappears` pins it. The converse
  ("a caller is not woken when the server thread alone is destroyed") is pinned
  too. ✓
- **a notification bound to an endpoint whose receiver is suspended.** `signal`
  hands the word to the front of the endpoint's queue even when that thread is
  suspended, and the thread runs only after `thread_resume`; the reply object
  becomes idle. `suspended_thread_that_waits_to_receive_still_gets_a_notification`
  pins it. ✓

---

## 4. Reading guide for the two humans

The model is 8,090 lines, but the part that *is* the contract is about 1,900:
`src/lib.rs` (729), `src/caps.rs` (613), `src/ipc.rs` (471), `src/check.rs`
(482). The rest is tests, which you should read second, not first, and
`tests/property.rs`, which you should read only if you doubt the random test's
honesty (it is honest: hand-written xorshift with fixed seeds, biases documented,
and `at_risk` asks a *copy* of the state what a call means).

### 4.1 The ten places to read first and most carefully

In this order. If you read only these, you have read the contract as code.

1. **`src/lib.rs:541-600`** — `space`, `own`, `through`, `full`, `dying`, `cap`,
   `is`. Every call enters here, and *all* of `invalid`/`gone`/`denied` and the
   whole dying-space rule is in these 60 lines. If this is wrong, everything is
   wrong and no test would look wrong.
2. **`src/caps.rs:41-80`** — `footprint`. Every object size, every alignment,
   the 128-multiple, the 2^20 maximum, the directory rounding, and the
   `unsupported` set, in 30 lines. It is the densest piece of the contract in the
   code.
3. **`src/caps.rs:248-278`** — `fits`. This is the safety argument that took the
   contract two revisions (D-101, D-103). Five lines of logic, four readings
   (moved root / moved copy / derived / retyped), one comparison each. Read it
   with the contract's "Why:" paragraph beside it.
4. **`src/caps.rs:458-510`** — `next_removed`, the removal walk. It marks a
   capability dying, starts the sweep of a space, wakes the thread of a reply
   object, and decides which capability goes next, all inside one `for`. It is
   the hardest function in the model and it is where a mistake would be
   invisible.
5. **`src/caps.rs:512-548`** — `swept`, the 128-slot budget. "A slot counts as
   examined when the sweep moves past it, so a full slot is not counted while its
   capability is being removed" is one `match` arm; read it twice.
6. **`src/caps.rs:409-456`** — `remove`: the 32-step budget, the choice between
   removing and waking, `again` versus `Done`, and the `next == target`
   comparison that decides **empty** versus **dead**.
7. **`src/ipc.rs:373-430`** — `deliver`. All-or-nothing transfer, the second
   check, the index arithmetic (`window.first + i`), `caps_dropped`. Three
   closures capture `self` and `window`; read the assertions, not the shape.
8. **`src/ipc.rs:331-372`, `354`, `454`** — `serve`, `answer`, `unlink`: the
   reply object's three states and who becomes idle when. Together with
   `check.rs`'s invariants 15 and 22 these are the whole IPC state machine.
9. **`src/lib.rs:652-690`** — `window`: the receive range. Five rules in fifteen
   lines (empty range has no address; slot 0; beyond the table; ≤ 4; `write` on
   the `via`), and the order in which they fire is part of the contract.
10. **`src/check.rs:330-455`** — `check_waits`. Invariants 12–17, 22, 29. This is
    the model's own oracle: it is what makes the random test worth anything.

### 4.2 What to make simpler, concretely

- **`swept` returns `Option<Option<CapId>>`** (`caps.rs:512`) and needs a six-line
  doc comment to say what the two levels mean. Make it a three-variant enum
  (`Found(CapId)` / `EndOfTable` / `OutOfSlots`). This is the single
  highest-value simplification: it removes the only place in the model where the
  type does not say what the value means.
- **`listed` returns `Vec<(CapId, Option<Rights>)>`** and `deliver` reads
  `rights.is_some()` as "this is a derive". `Transfer` already says this; return
  the same shape (or reuse `Placing`).
- **`untyped_retype`'s `let no_exec = Rights::EXEC.without(rights);`**
  (`caps.rs:203`) is a set-difference used as an `if`. Two named constants and an
  `if` would read in one second instead of ten.
- **`Syscall::Other`'s first line** (`lib.rs:518`) —
  `self.space(thread, SlotAddr::NONE, Access::Read)?;` — exists only to get
  `gone` for a dying space "before any argument is looked at". Name it:
  `self.live_space(thread)?`.
- **`Access`** is a two-variant enum that maps to two right constants; pass
  `Rights` and delete the enum.
- **`Place = (ObjId, u32)`** appears in 15 signatures as a tuple that is
  destructured as `(space, index)`. A two-field struct with named fields would
  remove the "which is which" question in `check.rs` and in `remove`.
- **`own()`** means "the capability space this thread is bound to, if it still
  exists" and **`space()`** means "the capability space a slot address names".
  Both are called `space` at their call sites. Rename `own` to
  `bound_cspace`, and `space` to `cspace_of`.
- **Invariant numbering** in `check.rs`: 1–30 in an order that is not ascending,
  with `20`, `21`, `24`, `28` filed under "The derivation tree" and `5`, `6`,
  `7`, `27` under "Slots". The numbers appear in test assertions, so renumbering
  costs an hour; but a reader has to hold 30 numbers in her head to follow the
  doc comment. At minimum reorder the doc comment to ascend and put the number
  in the code's own `ensure` string (it already is), so the doc comment is an
  index and not a story.
- **`check_removal`** (`check.rs:211`) is a topological sort written with two
  closures (`after`, `before`) and a `BTreeMap<CapId, usize>` counter. Four lines
  of prose above it saying "an edge A → B means A must be removed before B; the
  graph has a cycle iff the walk can revisit itself" would make it readable, and
  the four lines could replace the current doc.
- **Three copies of the depth walk**: `Model::depth` (`caps.rs:238`),
  `check_tree`/`check_slots` (`check.rs:203`, `241`), `Census` (`check.rs:44`).
  One `fn depth(&self, cap)` reused everywhere would remove two of them.
- **Three copies of "is this object dying"**: `Model::dying` (`lib.rs:591`),
  `check_tree`'s `root`, `check_waits`'s inline expression, `Census`'s `root`.
  `Model::dying` is already public enough to be used by `check`.
- **`let (all, segment) = (Rights::ALL, CSPACE_SEGMENT_SLOTS);`** in `boot()`
  (`lib.rs:412`) — a tuple of two unrelated constants for no reason.
- **`boot()`'s `add` closure** returns `model.caps[&cap].object`, capturing
  `model` mutably and `space` before it exists. Six lines of builder would read
  better than one clever closure, and `boot` is the first function a reader
  meets.

### 4.3 What could be removed without losing a rule

- **`unlink`'s return value** (M4) — nine call sites discard it.
- **`Census` and `census()`** (M8) — test-only; gate them and 70 lines leave the
  module a human reads.
- **`Access`** (above) — after passing `Rights`, 15 match arms go.
- **`Checked<T>`** — used twice; `Result<T, Error>` is shorter and clearer.
- **`BOOT_UNTYPED_BYTES`/`BOOT_DEVICE_BYTES` are `pub`** but nothing outside
  reads them; make them private until the harness needs them.
- **`Segment`/`Sweep` overlap**: `Sweep.held` is a snapshot that invariant 23
  compares against. It is load-bearing (it is how "a dying space only shrinks"
  is enforced) but its doc comment says "what a dying capability space keeps",
  which does not say that. One sentence: "the capabilities the space held when
  it began to die; invariant 23 refuses any other".
- **`Output::Inspect`'s `rights`/`badge`** and `Output::Slots` are the results of
  exactly one call each; fine, but they are why `Output` has six variants — worth
  one comment at the type.

### 4.4 Comments that cite a section which does not say what the code does

I scanned the 106 comments that name a contract section. Four are imprecise,
none is wrong:

- `caps.rs:485` "Slots and addresses: `cap_delete` acts on the slot it names,
  which becomes empty" — *Slots and addresses* only says that a slot becomes
  **dead** when removed "by someone else"; the "empty" half is an inference (C2
  reading 2 above). The comment is right; the contract is thin.
- `caps.rs:216` "Errors: `no_slot` also means that the space is at its maximum."
  — that is from *Errors*, not from *Slots and addresses*, which is the section
  the preceding comment names. Cosmetic.
- `ipc.rs:54` `CONTRACT-GAP (Messages)` — not a contract gap (M6).
- `lib.rs:541` `space()`'s doc says the dying rule "except `cap_delete`", while
  the function enforces it unconditionally and `cap_delete` patches around it.
  The doc is about the caller's obligation, not the function's effect.

---

## 5. What is correct, in one line each (so the report is not only fault-finding)

- The order of checks: four tests, one per table order, including the header
  exception. No deviation found.
- The three slot states and their two error codes: complete, and the
  dead-slot/empty-slot asymmetry between `cap_delete` and everything else is
  right.
- The four rules of the derivation tree (parent, no outliving, root capability
  owns the object, 64): complete and each defended.
- The depth rule D-103 in all four places (derive, retype, move, IPC delivery),
  including "a copy of a space capability goes anywhere" and "a space may hold
  its own root": correct, and the `check` invariant that backs the argument for
  termination is there.
- Removal: both budgets, the order, the sweep semantics, the `again`/`Done`
  boundary, the reply wake that is not counted, and the accepted limit about
  competing derivations — all correct and all tested, including the 128-call and
  32-wake exact counts.
- Object life cycle and memory: watermark, alignment per kind, the reset only
  when the last object goes, segments returned to the untyped, `exec` inheritance
  and device memory — correct.
- IPC: the five thread states, `call`/`recv`/`reply_recv`/`send`/`signal`/`wait`/
  `poll`/`notify_bind`, the notification-before-caller order, the badge rule, the
  reply object's three states, badge 0 on replies — correct.
- Transfer of capabilities: check at call and at delivery, all-or-nothing, the
  `caps_dropped` flag on both sides, "the server is not told about its own
  reply's drop", slot-listed-twice, the depth of a derive — correct.
- Suspension is independent of waiting; rights are checked at call time and a
  waiting thread is disturbed only when its object is destroyed — correct.
- The test suite is honest: one test per behaviour, named after the behaviour;
  check after every call; a mutation of any rule I tried is caught by the test
  whose name states it.

The six survivors are all *numbers or thresholds* (T1–T6), not rules, and each is
one line of test away. That is the strongest evidence I can give that the model
is ready to be the oracle.

---

## 6. What I did not verify

- Kani, Miri and the sanitizer are CI-only and not in the Nix shell; I did not
  run them. `abi`'s four proofs are `#[cfg(kani)]` and I read, not ran, them.
- `cargo fmt`/`clippy` are part of `verify`; I ran the tests only.
- The property test's 24 seeds are what they are; I read the generator and
  checked that its biases are documented, but I did not add seeds of my own.
- I did not read `/Users/btw/Documents/repos/Docs/reviews/` (as instructed), so
  any finding here that duplicates an earlier review is independent, not copied.
- I did not review the contract's parts that describe no code yet (tasks,
  scheduling, cores, time, interrupts, power, debugging) beyond asking whether
  they contradict the call reference (§ 2).
