# Model review 6 — the gate over page tables, and the three artefacts (deepseek)

Reviewed: `dodos-kernel` at `d4e883b` (branch `model`), `abi/` and `model/` in that
tree; the contract `Docs/architecture/kernel-interface.md` as it stands in this
docs tree; the 23 settled problems of pass 11 in `Docs/research/drafts/abi-changes.md`
section 8.1, as the contract now states them.

I did not open any other file under `Docs/reviews/`.

## Verdict

The gate's claim survives the attacks I could put to it: no sequence of legal
gate requests that I found — on paper or in the model — ends with a writable
mapping of a page table, of another node's memory, of the gate's own records or
of the machine table, and R2, R3, R5 and R6 are modelled and pinned by tests.
But the model enforces several of the gate's rules *by construction* instead of
by the rule, so it cannot answer for a kernel that implements G2, G3(3) and
G3(4) wrongly: page classes are one of the contract's six, the class check has
no error in the ordered list of `aspace_map`, and G3(5)'s bound is short by a
factor of the entries per call; and one side door is open — a device identifier
is not tied to the entry that records its owner, so any node may attach any
device. Every number I checked agrees across the three artefacts except
`SCHED_BYTES` (the contract contradicts itself), `FRAME_MAX_PAGES` and the
"at most 512 pages" of the Kani list (in the contract but not in `abi/`, and
they contradict *E*), the map-count width (in none of the three), and the MSI
message format (in the contract and the model, not in `abi/`); 78 mutants over
the ten pre-pass-12 groups and the 23 settled problems killed 69, and of the
nine survivors four are now killed by tests I wrote, one only on the reference
geometry, and four remain unpinned (two unreachable, one dead code, one
invariant that no test drives).

## What I ran

- Baseline `cargo test --workspace` on the reference geometry and with
  `DODOS_PAGE=16k`, before and after the two test files I added: green both
  times. The 16 KB geometry of the model is `page_shift [14, 25, 36]`,
  *E* = 2048, *L* = 3; the reference is `[12, 21, 30]`, *E* = 512, *L* = 4.
- Two test files of my own, in the model's test directory of a scratch copy:
  `model/tests/gate_attack.rs` (7 tests, part 1) and `model/tests/gate_words.rs`
  (4 tests, part 2). All 11 pass on both geometries.
- 78 mutants (50 in `abi/`, 28 in `model/`) applied one at a time to a second
  copy: `git checkout` before and after each, the group's own test binaries
  first, then the wide set and both geometries, then — for the nine survivors —
  `property`, `recovery` and `liveness`, which my first pass left out. Numbers
  below. One mutant (`Busy = 7 → 8`) was rewritten as `Unsupported = 10 → 13`
  because a duplicate discriminant does not build.

## Findings

Most serious first. Each says what is wrong, where, how I know, what a kernel
author would do wrong from it, and the smallest correction.

### F1. The gate's own cost sentence is wrong per call, and the class check has no error (G3(5), G3(3) against the ordered checks)

**What.** G3 ends (contract line 879): "Every step is constant work; a leaf of a
page size larger than a chunk costs one check per chunk it covers, at most *E*."
Two things are wrong.

1. The bound is per leaf, not per call. A call writes up to *E* entries
   (§"Bounds", line 294), so the ownership-word checks are up to *E* × (*S*/chunk)
   = 512 × 512 = 262,144 on the reference machine (a 1 GB leaf over a 2 MB
   chunk), 2048 × 2048 = 4,194,304 on the 16 KB geometry. And the page-class
   reads of G3(3) are one per *page*: up to *E* × (*S*/*P*) = 512 × 262,144 =
   134,217,728 reads in one `aspace_map` call on the reference machine
   (8.6 × 10⁹ on the 16 KB geometry with 64 GB leaves — only the user range
   limits it in practice).
2. The ordered checks of `aspace_map` (contract lines 280-284, step 4) contain
   **no class check and therefore no error for a class violation**, while G3(3)
   makes the class read part of "for each entry". A kernel author reading the
   ordered list writes no class check at all; a kernel author reading G3 has no
   error code to return.

**How I know.** Read: G3 (879), G4 (880), §Bounds (294), the ordered checks
(270-284); `abi/src/lib.rs:415` (`chunk_shift() = page_shift[1]`, so a 1 GB leaf
is 512 chunks and a 2 MB leaf 512 pages); the model's `aspace_map`
(`model/src/memory.rs:142-300`) has no class check — its `leaf_chunks` loop is
only the G4 map count — and the class walk lives in the invariant
`model/src/check/table.rs:183-201`, which fires *after* the event. Ran: my
`gate_attack.rs` test 7 (`a_frame_of_one_gigabyte_counts_in_every_chunk_it_covers`)
builds a 1 GB frame and shows the model walking every chunk, and takes 16,384
`again` steps at 64 KB per step to zero it.

**What a kernel author does wrong.** Reads the class of an entry's first page only
(a 2 MB leaf covers 512 pages whose classes may differ), or takes G3(5)'s "at most E" as the budget of a gate call and gives the
gate a 512-entry queue that a single 1 GB mapping cannot drain in one call. With
the ordered list as written, the same author returns nothing when the class
forbids the write.

**Smallest correction.** Replace "at most *E*" with "at most *E* × *S*/chunk
word checks and *E* × *S*/*P* class reads per call" (and say what the gate does
when that is more than its budget: refuse the call, or bound the entry sizes of
one call). Add to the ordered checks of `aspace_map`, `aspace_protect` and
`iospace_map` a step "the class of each target page permits this leaf
(`invalid`)" before the state checks, and add it to `aspace_map` in the model,
not only to invariant 58.

### F2. Page classes: the contract has six, `abi/` none, the model one (G2, G3(3), G3(4))

**What.** G2 (878) requires six classes per page — *data*, *page table of level
k*, *iospace table*, *gate*, *global read-only*, *device* — and G3(4) turns three
of them into permission rules: no kernel leaf writable and executable, global
read-only pages never writable, device pages never executable and carrying a
device memory type, user leaves never kernel-executable. `abi/` publishes only
an offset (`abi/src/start.rs:288`, `page_classes: u32`) and names no class value.
The model has `PageClass` with a single variant, `Table`
(`model/src/table.rs:126-129`), and invariant 59 asserts the class table is
exactly the set of the node's table pages (`model/src/check/table.rs:270-283`),
which makes "class *data*" the same as "no entry".

So the model enforces the part of G3(3) that matters most — a leaf may not point
to a table page — as invariant 58 (`check/table.rs:247-257`), i.e. by detecting
the forbidden state after the fact, and it never reaches that state because a
table page is taken at an untyped's watermark and no frame can cover it. The
*device*, *global read-only* and *gate* classes have no representation at all;
the rule that protects the machine table's living part is a capability rights
rule in the model (test 6 of `gate_attack.rs`: a `write` derived from the
read-only slot-13 capability is `denied`, and a mapping asking for `write` is
`denied`), not a class rule.

**How I know.** Read: G2 (878), G3(3)(4) (879), R6 (1100), the model's
`PageClass`, `aspace_map` (no class check), invariant 59; ran the two invariants
by mutating them (`M10` "58: translation to a table page" and `M13` "55:
translation to a free word" are killed; `M11` and `M14` are not, see F5).

**What a kernel author does wrong.** Codes `data = 0` and treats "no byte
written" as *data*, then gives the gate's own save area, the clock page or a
device page no class byte — and the first `aspace_map` of a page-sized frame over
the gate's stack succeeds, because the gate's class check finds *data*.

**Smallest correction.** Publish the six class values in `abi/` (a `PageClass`
enum, one byte, 0 = data), state that "no byte written" is invalid rather than
*data*, and model *device* and *global read-only* as the model already models
*table*: at least in invariant 58, with a test that maps a device page for
execution and one that maps a global read-only page writable, both refused.

### F3. A device identifier is not tied to the entry that records its owner, so G9's rule cannot be checked (side door)

**What.** G9 (885) writes a context entry "only if the root it names is a
top-level iospace table owned by the node that owns the device", and contract
line 780 says a device belongs to the node where its driver runs, which takes
the device's entries with `memory_take`. But the *identifier* that
`iospace_attach` takes (contract 333, "a plain identifier whose form the
architecture layer fixes") is never tied to the device-table entry that holds
the ownership word, and the rules of `iospace_attach` (335-346) never read a
word. In the model, any node that holds the `iommu` root (every node does, with
`manage`) may attach any identifier to its own `iospace`.

**How I know.** Ran: `gate_attack.rs` test 4,
`a_node_attaches_a_device_whose_entry_another_node_holds` — node 1 attaches
device id 4 while node 0 holds entry 0 of the device table, and the model returns
`done` and its invariants hold. Read: the ordered rules of `iospace_attach`
(335-346) and `model/src/memory.rs`'s attach path, which checks the `iommu` and
`iospace` capabilities and the identifier's form only.

**What a kernel author does wrong.** Implements exactly what the contract says,
and node 1 redirects node 0's device into node 1's page tables: the device's DMA
writes node 0's memory under node 1's leaves, and node 0's frames are reachable
from a node that does not own them. This is the one attack in part 1 that the
contract's own standard ("a right the caller does not hold") forbids and the
model allows.

**Smallest correction.** One more ordered check in `iospace_attach`: the
device-table entry that covers the identifier must read *taken* by the caller
(one word read; for a split entry, by the node that took it), `denied`
otherwise; and the model's attach reads `table.devices[...].owner` through
`may_take`. A start-up page field that maps identifiers to entries would make
this checkable by the kernel at all.

### F4. The width of a map count is fixed in none of the three (G4)

**What.** G4 (880) makes "a count that would overflow" a `busy` of the mapping
call, but no artefact says how wide the word is: `abi/` has no `MAP_COUNT_MAX`,
the start-up page does not publish it (`abi/src/start.rs:284-299`, the eight
offsets and four counts only), and the model invents `u32::MAX` with the comment
"the contract fixes no width" (`model/src/boot.rs:178,314`). Because of that the
rule is not pinned: mutant `M09` (`count + leaves > max` → `count > max`)
survives the whole suite on both geometries, and my `gate_attack.rs` test 3
(`a_map_count_that_would_pass_its_limit_is_busy`) can only reach the check by
setting `Machine::map_count_max = 1` by hand.

**What a kernel author does wrong.** Uses a 16-bit count per chunk (512 leaves
fit; a chunk is 2 MB and holds 512 pages at 4 KB, so the count saturates exactly
when a second 2 MB mapping arrives) and wraps to 0, after which G5's "map count
0" holds and the chunk is given away while translations to it remain.

**Smallest correction.** Add `MAP_COUNT_MAX = u32::MAX` to `abi/`'s "Sizes and
limits" (line 1433) and a test with a count at the limit; or state the width in
G4 and drop the model's private field.

### F5. Nine sentences of the contract have no test; four are now pinned, one only on one geometry

The mutation run, by group (killed / survived):

| group | mutants | killed | survived |
|---|---|---|---|
| capabilities | 7 | 7 | — |
| threads | 4 | 4 | — |
| IPC | 5 | 5 | — |
| notifications | 2 | 2 | — |
| memory and devices | 22 | 20 | M20, M21 |
| gate over page tables | 15 | 10 | M08, M09, M11, M14, A35 |
| scheduling and time | 2 | 2 | — |
| interrupts | 1 | 1 | — |
| tasks and marks | 3 | 3 | — |
| faults and registers | 0 (in the threads/memory groups) | — | — |
| start-up | 6 | 5 | A48 |
| I/O ports | 4 | 3 | A38 |
| cores and roles | 1 | 1 | — |
| error codes, rights, kinds, nodes | 2 + 1 + 1 + 2 | 6 | — |

The nine survivors, what rule each breaks, and their state now:

| id | the rule broken | sentence | after my tests |
|---|---|---|---|
| A35 | a free word has generation 0 | 762, 765 | killed by `gate_words.rs`, both geometries |
| A38 | a port access has width 1, 2 or 4 | 1397 | killed by `gate_words.rs`, both geometries (and by the Kani harness `port_checks_follow_the_contract`, which CI runs but `cargo test` does not) |
| A48 | a module takes the largest page size that fits | 1644 | killed by `gate_words.rs`, both geometries |
| M21 | a destroyed block of a reserve chunk keeps the reserve's code | 773 | killed by `gate_words.rs`, both geometries |
| M08 | a leaf counts in every chunk it covers | 880 | killed by `gate_attack.rs` on the reference geometry; **not reachable at 16 KB** (a chunk is 64 GB, so no test there builds a two-chunk run) |
| M09 | a count that would overflow is `busy` | 880 | unreachable, see F4 |
| M11 | a use entry counts the grantee's leaves | 882 | surviving: invariant 58's use-entry count (`check/table.rs:262-267`) has no test |
| M14 | a use entry of another generation is not the grantee's | 882 | surviving: the generation test in `model/src/remote.rs` cannot be reached with the model's own flows |
| M20 | a given block has map count 0 | 807, 881 | no test *can* pin it: `blocks.rs:252-263` is dead, because a chunk under a live grant cannot be given (G6's "never given" fires first) and a granter's own count is 0 for a granted chunk |

Also: the model never reads `TABLE_ENTRIES_MAX`, `LEVELS_MIN`, `IOMMU_WAIT_NS`,
`START_VERSION` or `clear_steps` at all (zero references under `model/`), so
mutating them cannot fail a model test — `A17`, `A18`, `A20`, `A46` and `A49`
survive the whole suite by construction, not by luck. `NODES_MAX`, `GRANTS`,
`DEVICE_TABLE_SPARE`, `Marks` and `member_transition` are referenced but their
values are not pinned by the model: `A42`, `A43`, `A45` and `A47` survive.
`A12`, `A13`, `A23` and `A25` are killed by
`model/tests/calls.rs::numbers_of_the_contract_are_those_of_the_interface`, the
one test that pins the byte sizes, and it pins `SCHED_BYTES = 256`,
`TASK_BYTES = 256`, `IRQ_BYTES`, `TIMER_BYTES`, `REPLY_BYTES`, `NOTIFY_BYTES`,
`SLOT_BYTES`, `ASPACE_BYTES`, `IOSPACE_BYTES`, `REMOVAL_STEP`, `REMOVAL_SLOTS`,
`TREE_DEPTH` and the capability-space numbers — the right place for them — but it
mentions neither `ENTROPY_MAX_BYTES`, `Marks`, `NODES_MAX`, `GRANTS`,
`DEVICE_TABLE_SPARE`, the object-kind numbers, `IOMMU_WAIT_NS`, `clear_steps` nor
`START_VERSION`. `A21` and `A29` die somewhere in the wide set that I did not
narrow down. `A47` is the one that matters: the model *re-implements*
`abi::member_transition`'s table instead of calling it, so the model does not pin
the table it claims to follow.

**Smallest correction.** Add the four tests I wrote (appendix) to
`model/tests/`, add a use-entry test for M11 and a two-chunk-run test on both
geometries for M08, and either make `memory_give`'s map-count check reachable or
delete `mapped_block` and say in G5 that a chunk with a live grant is refused
before its count is read.

### F6. Two page sizes: the second geometry exercises less than it looks

**What.** Two rules are pinned only on the reference geometry, two are not
pinned at all, and one architecture rule is exercised wrongly on the second.

- `abi::x86_64::canonical` hard-codes the four-level form (`>> 47`) and
  `model/src/faults.rs:125,182` uses it on the three-level geometry too, whose
  user end is still 47 bits — so the second geometry never exercises the
  canonical rule (a 3-level x86-64 user end is 39 bits).
- `A17` (`TABLE_ENTRIES_MAX 4096 → 2048`) and `A18` (`LEVELS_MIN 2 → 3`) survive
  the whole suite: no model machine has *E* above 2048 and none has *L* = 2,
  although both are legal in `abi/`.
- `M08` (F5) is unreachable at 16 KB.
- `Geometry::valid` refuses a machine whose second page size is 0 (`page_shift[1]
  == 0` would make a chunk 1 byte); the contract's list of refusals (start-up
  state) does not mention it, so a machine that the contract accepts is refused
  by the model.

**What a kernel author does wrong.** Trusts the second geometry as evidence that
the *L* = 3 and *E* = 4096 paths work, and gets a canonical-address check that
passes a 39-bit address on a 3-level table.

**Smallest correction.** One test with a 3-level `iospace` faulting on an address
between 2^39 and 2^47 (and a geometry whose `user_end` is 39-bit), one machine
with *E* = 4096, and the `page_shift[1] == 0` refusal added to the contract's
list.

### F7. `SCHED_BYTES`: the contract contradicts itself

Line 1433 says "Unchanged: `SCHED_BYTES = 128`"; line 1547 (object sizes) says
`sched` is 256 bytes, with a reason; `abi/src/lib.rs:129` and the model use 256.
Where the three disagree, two of them agree with 1547. A kernel author sizing a
`sched` from the "Values to add" list writes 128 bytes and overruns it.
**Smallest correction.** Delete `SCHED_BYTES` from the "Unchanged" list.

### F8. `FRAME_MAX_PAGES` and "at most 512 pages" are stale against *E*

Line 1433 requires `FRAME_MAX_PAGES = 512` in `abi/`; it is not there (grep over
`abi/src`), and line 1444 describes the mapping harness as "holds at most 512
pages", while lines 236, 294 and 1552 say *at most E*, `abi`'s own
`mapping_range` doc says "At most *E* pages" (`abi/src/lib.rs:488`) and its
harness is named `accepted_mapping_lies_below_the_limit_and_holds_at_most_e_pages`.
Also `abi/src/x86_64.rs:9` carries `TABLE_ENTRIES = 512` (a per-architecture
value) beside `abi/src/lib.rs:139` `TABLE_ENTRIES_MAX = 4096` (the machine's
limit): two sources for *E*, and the geometry is the one the model uses.
**Smallest correction.** Drop `FRAME_MAX_PAGES`, say *E* in 1444, and say in
`abi/` that the entries per table are the machine's (`Geometry::entries`), with
`x86_64::TABLE_ENTRIES` only as the reference machine's value.

### F9. The MSI message format is not in `abi/`

G10 (886) and the interrupt section fix the MSI address and data. The only copy
is `model/src/irq.rs:13,94` (`0xFEE0_0000 | ...`); `abi/` has nothing, so a
kernel author writing the real gate has no tested constant, and the two
architectures' layers cannot share it. **Smallest correction.** Move the two
functions into `abi::x86_64` with the test the model already has.

### F10. "The gate takes typed handles … never a raw physical index" is false of `memory_take`

Line 819 says the gate takes typed handles and never a raw physical index; line
788 says `memory_take`'s `place` is the run's physical base (kind 0) and the
entry's index (kind 1). The rule that actually makes it safe is the one the
model implements — `may_take` on every word of the run, which refuses another
node's memory (`abi/src/machine.rs:309-334`, Kani-proved). A kernel author who
believes 819 checks "the handle names a block this node owns" writes no per-word
check and maps any run it likes. **Smallest correction.** Rewrite 819: "the gate
takes a run's base and a block's handle, and decides by the words of the run".

### F11. Small disagreements between contract and `abi/` names

- The contract's start-up entry 17 (1715) and `StartMachine`
  (`abi/src/start.rs:284-299`) agree field for field (eight offsets, `chunks`,
  `device_capacity`, `role_count`, `grants_per_node`, `layout`, `reserved`;
  64 bytes) — but `gate_words` and `page_classes` are published as offsets of
  frames the contract describes but `abi/` never types, so a kernel author has
  no layout for the bytes they point at. The contract gives one (755-763 for the
  ownership word, the class table's one byte per page in 878); `abi/` gives none.
- `MemoryControl` is kind 19 in `abi/src/lib.rs` and unnamed in the numbers the
  contract's object table lists; `A30` (`19 → 21`) survives the whole model
  suite, so nothing in the model pins the kind numbers at all
  (`calls.rs`'s numbers test covers sizes and call numbers, not kinds).
- `Marks::UNTRUSTED`, `TaskFlags::AWARE/REVOKED`, `NodeGen` and `ClockPage` are
  present and typed; `ClockPage` is 40 bytes in `abi/` and in the contract's
  debug section. `A29` (the `UNTRUSTED` bit) dies in the wide set, but I did not
  narrow which binary kills it, and the numbers test does not mention it.

## What I checked and found right

- **The doors of the gate I could try are shut.** A writable derivation from the
  living part's read-only capability is `denied`, and a mapping that asks for
  `write` on it is `denied` (`gate_attack.rs` test 6), on both geometries. The
  kept frames of the modules are `read` and `exec` only.
- **Recovery writes are modelled and pinned.** R2 (`model/src/recovery.rs:746`,
  `reclaim_unit`), the barrier (R3), R5 and R6 are exercised; `A36`, `A37`, `A44`
  and `M15`, `M27`, `M28` all die. My test 1
  (`the_holder_of_a_grant_loses_its_mapping_when_the_granter_is_accused`) shows
  the grantee's slot becomes `invalid`, not `gone` — the contract's distinction.
- **The map-count compare-and-swap holds.** Every write of the living part goes
  through a read-check-swap of the word the gate read (`blocks.rs:283-288`), and
  invariant 52 (`check/table.rs:91`) refuses a write of an ownership word by a
  node that does not own it.
- **A node that dies with an attached device leaves no context entry** (my test
  5; invariant 81), and R1 clears its mappings.
- **No class flip is reachable** (watermark monotonicity, and the class is reset
  when a space is destroyed), so G2's "the gate turns a data page into a table
  page and back" cannot be attacked through the model's flows.
- **Kani.** Twenty-two harnesses in `abi/` are in CI (`verify.yml`, job `kani`), and
  they pin `may_take`'s four rules, the check field's read-back, `floors`,
  `module_frames`, `clear_step(s)`, `firing_instant`, `bandwidth`,
  `IrqSource::from_raw`, the port rule and the member/role transition table. Two
  of them are weaker than the sentence they are cited for: the port harness
  catches a width of 8 (A38) but the module-frames harness does *not* catch an
  exact fit (A48) — by reading its assertions, since Kani is not installed here —
  because both a large page and *E* small pages cover the module
  in order.
- **The order of checks of `aspace_map` in the model matches the contract's
  four steps**, including that no right is judged on the frame before the plain
  arguments (`self.cap(thread, map.frame, Rights::READ)` asks for `read` on the
  *capability space being addressed*, not on the frame — I checked this because
  it looked like an order bug and is not), and that the rights subset is `denied`
  after the word's shape is `invalid`.

## What I did not check

- Most of the 23 settled problems in detail: I compared the numbers and the
  orders of the ten pre-pass-12 groups sentence by sentence and mutated 78
  values, but I did not re-read the scheduling, tasks and interrupts sections
  against `model/src/sched.rs`, `tasks.rs` and `irq.rs` line by line; `faults`
  has no mutants of its own (the group's rules are covered by `memory` and
  `threads`).
- The `System` (several nodes) paths beyond the recovery tests: the proxy, the
  remote mappings of a multi-node address space and the message-page lend order
  of `recv` were read, not exercised.
- The architecture layers beyond x86-64 (`aarch64.rs`, `riscv64.rs`) and the
  debug, features and crash-record groups.
- The two tests I wrote are not in the repository: they are in my scratch copy
  only, so nothing here changes the tree. `gate_words.rs` is reproduced below;
  `gate_attack.rs` is summarised test by test.

## Appendix A — `model/tests/gate_words.rs` (all four pass on both geometries)

```rust
//! Rules of the machine table's words and of the start-up page that the
//! suite does not pin (found by mutation, see the review): a free word with
//! a generation, the width of a port access, a module that fits a large page
//! exactly, and the code a destroyed block of a reserve chunk keeps.

use dodos_abi::*;
use dodos_model::*;

const fn word(state: u64, owner: u16, generation: u32) -> u64 {
    let v = state | (owner as u64) << 2 | (generation as u64) << 18;
    let check = v.wrapping_mul(CHECK_MUL) >> 50;
    state | check << 2 | (owner as u64) << 16 | (generation as u64) << 32
}

#[test]
fn a_free_word_with_a_generation_is_refused() {
    // "No block covers the chunk; its generation is 0."
    let unclaimed = Owner::Unclaimed.code();
    let node = Owner::Node(3).code();
    assert!(Ownership::from_raw(word(1, unclaimed, 0)).is_some());
    assert_eq!(Ownership::from_raw(word(1, unclaimed, 0)), Some(Ownership::free(Owner::Unclaimed)));
    assert!(Ownership::from_raw(word(1, node, 0)).is_some());
    for generation in [1, 2, 0x8000_0000] {
        assert_eq!(
            Ownership::from_raw(word(1, unclaimed, generation)),
            None,
            "free word of generation {generation}"
        );
        assert_eq!(Ownership::from_raw(word(1, node, generation)), None);
    }
    // A word that is *taken* keeps its generation.
    assert_eq!(
        Ownership::from_raw(word(2, node, 5)),
        Some(Ownership::taken(Owner::Node(3), 5))
    );
}

#[test]
fn a_port_access_of_eight_bytes_is_refused() {
    // "width is 1, 2 or 4."
    let range = IoPortRange::new(0x3F8, 0x3FF).unwrap();
    assert_eq!(ioport_check(range, 0x3F8, 1, Some(0xFF)), Ok(()));
    assert_eq!(ioport_check(range, 0x3F8, 2, Some(0xFFFF)), Ok(()));
    assert_eq!(ioport_check(range, 0x3FC, 4, Some(0xFFFF_FFFF)), Ok(()));
    assert_eq!(ioport_check(range, 0x3F8, 8, Some(0)), Err(Error::Invalid));
    assert_eq!(ioport_check(range, 0x3FF, 2, Some(0)), Err(Error::Invalid));
}

#[test]
fn a_module_that_fits_a_large_page_exactly_keeps_one_frame() {
    let (m, _) = Model::boot(&Machine::example()).unwrap();
    let geometry = m.geometry();
    let large = geometry.bytes(PageSize::Large1).unwrap();
    // "the largest supported page size ... that is not longer than what
    // remains rounded up to a page": an exact fit takes the large size.
    let frames: Vec<_> = module_frames(0, None, large, geometry).collect();
    assert_eq!(
        frames,
        [ModuleFrame {
            size: PageSize::Large1,
            pages: 1,
            offset: 0,
        }]
    );
    // And a byte more is the large page followed by one page.
    let frames: Vec<_> = module_frames(0, None, large + 1, geometry).collect();
    assert_eq!(
        frames.iter().map(|f| (f.size, f.pages)).collect::<Vec<_>>(),
        [(PageSize::Large1, 1), (PageSize::Page, 1)]
    );
}

#[test]
fn a_destroyed_block_of_a_reserve_chunk_keeps_the_reserves_code() {
    // "Destroying a block writes *free* with the same owner into its words
    // (the reserve's code for a reserve chunk)."
    let (mut m, t) = Model::boot(&Machine::example()).unwrap();
    let shift = m.geometry().chunk_shift();
    let chunk = 1u64 << shift;
    let reserve = Ownership::free(Owner::Reserve(0)).raw();
    let bits = Machine::example().phys_bits;
    let at = (0..(1u64 << (bits - shift)))
        .map(|c| c << shift)
        .find(|&base| m.ownership(base >> shift) == reserve)
        .expect("a reserve chunk");
    // The role of the reserve is vacant at start-up: claim it first.
    let role = (21..=22)
        .map(|index| SlotAddr::own(index))
        .find(|&role| matches!(m.apply(t, Syscall::RoleClaim(role)), Ok(Output::Epoch(_))))
        .expect("a reserve role");
    let _ = role;
    let take = Syscall::MemoryTake {
        control: SlotAddr::own(START_SLOT_MEMORY_CONTROL),
        kind: 0,
        place: at,
        size: u64::from(shift),
        destination: SlotAddr::own(120),
    };
    assert_eq!(m.apply(t, take), Ok(Output::Done));
    assert_eq!(m.check(), Ok(()));
    assert_eq!(
        m.ownership(at >> shift),
        Ownership::taken(Owner::Reserve(0), 1).raw(),
        "the block is taken with the reserve's code"
    );
    assert_eq!(m.apply(t, Syscall::CapDelete(SlotAddr::own(120))), Ok(Output::Done));
    assert_eq!(m.check(), Ok(()));
    assert_eq!(m.ownership(at >> shift), reserve, "free with the reserve's code");
    assert_eq!(chunk, 1 << shift);
}
```

## Appendix B — `model/tests/gate_attack.rs` (7 tests, all pass on both geometries)

| test | the attack | result |
|---|---|---|
| `the_holder_of_a_grant_loses_its_mapping_when_the_granter_is_accused` | a grantee keeps a mapping of the granter's memory across the granter's death | R2 unmaps it; the slot becomes `invalid` (not `gone`), as the contract says |
| `a_block_whose_grantee_maps_it_is_not_given` | give a block away while a grantee holds a mapping of it | `busy` by "a piece lives", so G5's map-count check is never reached (this is M20) |
| `a_map_count_that_would_pass_its_limit_is_busy` | a count at the limit | only reachable by setting `map_count_max = 1`; the store value is `u32::MAX` (F4) |
| `a_node_attaches_a_device_whose_entry_another_node_holds` | node 1 attaches a device whose entry node 0 holds | allowed by the model — F3 |
| `a_node_that_dies_with_an_attached_device_leaves_no_context_entry` | R1/R6 of a node with a device | invariant 81 holds; the context entry is cleared |
| `the_kept_frame_of_the_living_part_of_the_machine_table_is_never_writable` | derive `write` from slot 13, and map it writable | `denied` both ways, on both geometries |
| `a_frame_of_one_gigabyte_counts_in_every_chunk_it_covers` | a 1 GB leaf over 512 chunks | each chunk's count rises by one; creating the frame costs 16,384 `again` steps at 64 KB (F1) |
