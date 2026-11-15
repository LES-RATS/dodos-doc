# Review 7 of the DodOS kernel contract and its reference model: the gate over page tables, and the contract against itself

Angle: Part 1 — the gate over page tables after its correction (contract section
"The gate over page tables", G1 to G14, and `aspace_map`, `aspace_unmap`,
`aspace_protect`, `iospace_attach`, `iospace_detach`; model files
`model/src/{memory,table,blocks}.rs` and what they call; tests `gate_attack.rs`,
`gate_words.rs`, `memory.rs`, `blocks.rs`). Part 2 — the contract read end to end
against itself.

Reviewer: DeepSeek. Date: 16 November 2026.

## What I read and ran

Read:

- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` at commit
  `3bc7597`, in full for Part 2, and in detail for: [Values of the
  machine](#values-of-the-machine) (79-97), [Order of checks](#order-of-checks)
  (134-142), [Frames](#frames)–[IOMMU](#iommu) (234-357), [Chunks, floors and the
  ownership words](#chunks-floors-and-the-ownership-words) (754-779), [The gate
  over page tables](#the-gate-over-page-tables) (868-906), [Reclaim](#reclaim) and
  [The reclaim barrier](#the-reclaim-barrier) (1094-1131), [Rights](#rights) and
  [Errors](#errors) (1517-1547), [Object sizes](#object-sizes) and [The
  capability slot](#the-capability-slot) (1549-1600), [Start-up
  state](#start-up-state) (1601-1742), [Open points](#open-points) (1872-1894).
- `git -C Docs diff 5d93e8f..3bc7597 -- architecture` and `git -C dodos-kernel
  diff --stat d4e883b..2afc901` (pass 13, 5,280 lines added).
- `dodos-kernel` at `2afc901` on branch `model`: `AGENTS.md`,
  `.agents/skills/dodos-rust/SKILL.md`, `verify`, `abi/src/{lib,machine,x86_64,
  tests}.rs`, `model/src/{memory,table,blocks,roles,recovery,check/table,
  faults,boot,system}.rs`, and `model/tests/{gate_attack,gate_words,memory}.rs`.
- I did not open the four reports of the sixth review.

Ran (in a copy at `/tmp/review7-deepseek`, nothing written under
`/Users/btw/Documents/repos` except this file):

- `nix develop -c ./verify` at `2afc901`: passes, all three geometries.
- A new test file `model/tests/review7_deepseek.rs` (five probes, printed in full
  in the findings that use them), run on the three page sizes:
  `nix develop -c cargo test -p dodos-model --test review7_deepseek` with
  `DODOS_PAGE` unset, `16k` and `32k`. Three probes fail on all three
  geometries, two pass. The file is not in `verify` and does not change the
  repository.
- `cargo test -p dodos-model --test gate_attack --test gate_words --test memory
  --test blocks` on the three geometries, read for what each correction pins.

## Verdict

The corrections of pass 13 keep the guarantee for every attack I could build on
the three page sizes: no call lets a node map memory it does not own, no map
count leaves a translation uncounted, and the two rules that D-124 added to
"Order of checks" (`denied` from a page class, `denied` from a device
identifier) each fire where the contract says — except that the first of them
can never fire at all, so its place in the order is unverified. Three faults are
real: `abi` computes the canonical boundary from the user range end and so
refuses a canonical address on a legal machine, a mapping made in steps is
completed by a call whose page count differs from the one that started it, and
the model counts device pages and kept pages in the gate word of a chunk that
G2 says they do not lie in. Read as a kernel author, the contract also
contradicts itself three times in ways that change the result of a call: the
definition of `denied`, the order of `denied` against `busy` in "Order of
checks", and a `busy` clause of `aspace_protect` that can never hold.

---

## Findings

### F1. The canonical-address check follows the user range end and not the architecture, so a legal machine refuses canonical addresses

**What is wrong.** `abi` decides whether an address is canonical by taking the
power of two at or above the user range end and treating it as the
sign-extension boundary: `let half = self.user_end.next_power_of_two(); address <
half || address >= half.wrapping_neg()`. That is the architecture's boundary only
when `user_end` happens to lie in the top half of the address bits. `Geometry::
valid` requires only `user_end != 0 && user_end % chunk == 0 && user_end <= 1 <<
(address_bits - 1)` (`abi/src/lib.rs:474-477`), so a machine whose user range
ends lower — a perfectly ordinary choice of the value of the machine — moves the
canonical boundary down with it.

**Where.** `abi/src/lib.rs:443-449` (`Geometry::canonical`), against
`abi/src/x86_64.rs:118-121` (`canonical`: bits 47 to 63 all equal) and the
contract's rule "the words the architecture requires to be canonical addresses
must be canonical" (`architecture/kernel-interface.md:423`).

**How I know.** Run. On all three geometries:

```rust
#[test]
fn the_canonical_boundary_follows_the_architecture_and_not_the_user_range_end() {
    let x86 = dodos_abi::x86_64::GEOMETRY;
    let canonical = (1 << 47) - 1;
    assert!(x86.canonical(canonical));
    // A legal geometry of the same processor whose user range ends at half
    // of the address bits instead of just below them.
    let low = Geometry { user_end: 1 << 46, ..x86 };
    assert!(low.valid(), "a user range end of 2^46 is a value of the machine");
    assert_eq!(
        low.canonical(canonical),
        dodos_abi::x86_64::canonical(canonical),
        "an address whose bits 47-63 are equal is canonical on x86-64, whatever \
         the user range end"
    );
}
```

fails: `low.canonical(0x0000_7FFF_FFFF_FFFF)` is `false`,
`x86_64::canonical` of the same address is `true`. The three geometries the
suite runs all sit just below the half (`0x7F80_0000_0000`, `2^46 - 2^36`,
`2^50 - 2^39`), which is why the existing test
(`abi/src/tests.rs:256-276`) cannot see it: it walks the boundary of the two
geometries it was given instead of the boundary of the architecture.

**What a kernel author would do wrong.** Copy `Geometry::canonical` into the
kernel and lose the ability to redirect a faulted thread: a `thread_write_regs`
whose rip or rsp lies in the top part of the user range would be `invalid`
(`model/src/faults.rs:186`), and an answer with label 1 to such an address
would be treated as "another label" and leave the thread suspended
(`model/src/faults.rs:127`, contract line 411: "A non-canonical address counts
as another label"). The upper half (`>= 0xFFFF_8000_0000_0000` on four levels)
would be refused too.

**Smallest correction.** Derive the boundary from the geometry's own address
bits and not from `user_end`: `let bits = self.address_bits(); address >> (bits -
1) == 0 || address >> (bits - 1) == (u64::MAX >> (bits - 1))`, and add to
`Geometry::valid` that `user_end <= 1 << (address_bits - 1)`, which it already
has. Pin it with a test at `user_end = 1 << (address_bits - 2)`.

### F2. A mapping made in steps is completed by a call whose page count differs from the one that started it

**What is wrong.** G3 names the identity of the call that continues a partial
mapping as "same frame capability, space, address, first page and rights" — the
page count is not in the list — and says that "the step that writes the last leaf
clears the mark and returns success". With another page count there is no such
leaf: the mapping the first call asked for is not the mapping the last call
completes. `aspace_map`'s own state list repeats the same five fields (contract
line 282), so contract and model agree, and both are wrong about what a
resumption is: the model accepts any *larger* or *smaller* count than the number
of pages still to write, and returns `ok` with a shorter mapping.

**Where.** Contract `architecture/kernel-interface.md:887` (G3) and `:282`
(`aspace_map`, state check 1). Model `model/src/memory.rs:194-206` (the guard
`m.count < map.count`, with no comparison against `map.count` itself).

**How I know.** Run, on all three geometries:

```rust
#[test]
fn a_partial_mapping_is_not_completed_by_a_call_of_another_page_count() {
    let mut machine = Machine::example();
    machine.gate_chunks = 1;
    let mut k = K::on(&machine);
    let viewer = k.with_aspace();
    k.small(3, 40);
    k.no(map(40, s(UT), AT, 3, Rights::READ), Error::Again);
    let outcome = k.outcome(map(40, s(UT), AT, 2, Rights::READ));
    let page = k.page();
    assert!(
        !(outcome == DONE && k.m.translated(viewer, AT + page).is_some()),
        "a call that asks for two pages finished a record the first call made \
         for three: the record is no longer partial and holds two pages"
    );
}
```

fails on `DODOS_PAGE` unset, `16k` and `32k` with exactly that message: the
second call returns `ok`, the record is no longer partial, and two pages are
translated where the first call asked for three.

**What a kernel author would do wrong.** Two things. A server that retries a
512-page mapping after a `busy` from somewhere else, with a stale `count` in its
argument block, silently gets a shorter mapping and believes it. And a
`aspace_protect` "within the bound of one gate call" is then judged over a
mapping whose `count` is the sum of what several different calls asked for —
which is how F9's clause came to be written twice.

**Smallest correction.** Put the page count into the identity in both places:
"the same call again (same frame capability, space, address, first page, page
count and rights)", and in the model `m.count < map.count && m.count + (map.count
- m.count) == map.count` — that is, accept the resume only when the requested
range is the one the record is being built for (`map.first == m.first` covers
the tail), which is `m.count == done && map.count == done + remaining`. Simplest
correct form: keep the requested count in the record (one more field, or derive
it as `m.count` when `partial`), and require `map.count >= m.count` **and** that
the addresses of the remaining pages are the frame's pages
`m.first + m.count .. m.first + m.count + (map.count - m.count)`.

### F3. `denied` is defined as a missing right, but two state checks that are not rights return it

**What is wrong.** The table of errors says `denied` means "A right is missing".
Two sections return `denied` for a state that no capability's rights can improve:
the class of the page a mapping targets (contract line 284) and the owner of a
device identifier for `iospace_attach` (contract line 342). "Order of checks"
knows this and says so (line 139), so the contract states the general definition
and then excepts it in one place and not the other. `abi` repeats the wrong
definition: `abi/src/lib.rs:199-200`, `/// A right is missing. Denied = 3`.

**Where.** `architecture/kernel-interface.md:1540` (`| denied | A right is
missing |`) against `:284` and `:342`; `abi/src/lib.rs:199`.

**How I know.** Read.

**What a kernel author would do wrong.** Write a caller that, on `denied`, tries
to derive a stronger capability and call again — the documented remedy for a
missing right — and loop for ever: a device identifier held by another live node
is `denied` and no derivation changes it. Or, in the kernel, order the class
check after the rights check because "`denied` is a right" — which is the right
order by accident, but for the wrong reason.

**Smallest correction.** One line in the table: "`denied` | A right is missing,
or a page class or device owner refuses the call ([Order of
checks](#order-of-checks))". The same sentence in `abi/src/lib.rs:199`.

### F4. "Order of checks" puts `busy` before `denied` among the state errors; the two calls that return a state `denied` put it before `busy`

**What is wrong.** Item 4 of "Order of checks" enumerates the state errors in an
order — `busy`, `no_slot`, `no_memory`, `would_wait`, `budget` — and then adds
`denied` "from two state checks". The section's own opening is "Every call checks
in this order and returns the first failure", so the enumeration is an order. Both
calls that produce a state `denied` judge it *before* at least two `busy` checks:
`aspace_map` judges the class (`denied`, line 284) before the map count (`busy`,
line 285) and before `no_memory` (line 286); `iospace_attach` judges the
identifier word (`denied`, line 342) before four `busy` checks (lines 343 to 348).
The model follows the two calls, not item 4 (`model/src/memory.rs:242` before
`:252`; `model/src/memory.rs:492` before `:496`, `:501` and `:504`).

**Where.** `architecture/kernel-interface.md:139` against `:284-286` and
`:342-348`.

**How I know.** Read; the model's line order confirms which of the two the
reference follows.

**What a kernel author would do wrong.** Implement item 4 literally — collect the
state errors and return the first in the order given — and return `busy` from
`aspace_map` where the reference returns `denied`, because a page class refuses
the leaf *and* the map count would pass. The differential test would then fail on
a state the contract's own table does not distinguish, and the author would
believe the model is wrong.

**Smallest correction.** In item 4, say that the two gate `denied`s are judged at
their place in the call's own list, not at the end: "…and `denied` from two state
checks that guard a rule of the gate, judged where `[Calls on address
spaces](#calls-on-address-spaces)` and `[IOMMU](#iommu)` put them, before the
`busy`es that follow".

### F5. The gate word has no field for the pages of a chunk not of class data: G4's bits 32-44 are never written, and `abi::GateWord` is used nowhere

**What is wrong.** G4 gives the gate word two fields: the map count in bits 0-31
and "in bits 32-44 the number of pages of the chunk whose class is not *data*
(G2)". `abi` models this (`GateWord::new(map_count, not_data)`,
`GateWord::from_raw` refusing a `not_data` above `1 << 12`,
`abi/src/machine.rs:175-205`). The model does not: `table.maps` is "the map count
of each chunk (G4)" as a raw `u64` per chunk, and `count_leaves` adds and
subtracts one to the whole word (`model/src/memory.rs:87-110`), so bits 32-44
stay 0 for ever. `Node::map_count` (`model/src/lib.rs:1133`) is documented as
"the map count of a chunk" and returns the whole word, which under G4 is not a
count. `GateWord` appears nowhere in `model/src`, `model/tests` or `abi/tests`.

**Where.** Contract `architecture/kernel-interface.md:888` (G4) and `:886` (G2,
"also holds the number of pages of the chunk whose class is not *data*, so a leaf
that covers a whole chunk reads one word instead of a byte per page"). Model
`model/src/table.rs:172` (`maps: Arc<Vec<u64>>`), `model/src/memory.rs:87-110`,
`model/src/check/table.rs:287-289` (`leaves == *table.maps`, which pins bits
32-44 to 0).

**How I know.** Read, and run: the probe below **passes**, which is the finding —
after a page table is taken into a chunk, the word's bits 32-44 are 0.

```rust
#[test]
fn the_gate_word_of_a_chunk_holds_no_count_of_pages_not_of_class_data() {
    let mut k = K::new();
    let log2 = k.chunk_shift();
    let block = common::slot(41);
    common::take_run(&mut k.m, k.t, log2, block);
    let base = run_base(log2);
    let viewer = k.with_aspace_for(block);
    k.small(1, 40);
    k.ok(map(40, SlotAddr::own(block), AT, 1, Rights::READ));
    assert!(k.m.translated(viewer, AT).is_some());
    let page = k.page();
    let table_page = base + 2 * page;
    let chunk = table_page >> k.chunk_shift();
    let word = k.m.map_count(chunk);
    assert_eq!(word >> 32, 0, "...");
    let word = dodos_abi::GateWord::from_raw(word).expect("a gate word");
    assert_eq!(word.not_data(), 0);
}
```

**What a kernel author would do wrong.** Implement the constant-work rule G2 asks
for — a leaf that covers a whole chunk reads the chunk's count of pages not of
data, one word, and refuses if it is not 0 — and then implement the *model's*
version, which reads a byte per page or a range query over the class map. The two
differ in the number of reads the gate makes per leaf, which is the whole reason
G2 chose the field (`Why: a check per page of a large leaf would be up to E × E ×
E reads in one call`, line 887). And an author who keeps the field will fail the
model's invariant 58, which requires the gate word to equal the leaf count.

**Smallest correction.** Either drop the field from G4 and from `abi` (then G3's
bound may say "reads the class of each page the leaf covers", with the cost made
explicit), or model it: a second array `not_data: Vec<u16>` beside `maps`, written
by the two places that insert into and remove from `table.classes`
(`model/src/memory.rs:297-300`, `model/src/caps.rs:333`, `:986`,
`model/src/system.rs:468`), checked by invariant 58 or 59 against
`table.classes`, and read by `class_of` for a leaf larger than a page.

### F6. A device leaf, and a leaf into the global read-only set, is counted in the gate word of a chunk, though G2 says such pages lie in no chunk

**What is wrong.** G2: "A page of device memory or of the global read-only set
lies in no chunk: its class is not stored but follows from where it lies (an
entry of the device table, a kept range)". G4's map count is "the number of
leaves of the owner's tables (CPU and IOMMU) that target pages of the chunk" — a
page of no chunk is not a page of the chunk. The model counts leaves by physical
address with no such distinction: `leaf_chunks` cuts every leaf into chunk
indices by `at >> chunk_shift` regardless of class (`model/src/memory.rs:74-85`),
and `count_leaves` adds one to that index's word (`:87-110`).

**Where.** Contract `architecture/kernel-interface.md:886` (G2) and `:888` (G4).
Model `model/src/memory.rs:74-85` and `:87-110`; the invariant that licenses it,
`model/src/check/table.rs:287-289`.

**How I know.** Run, on all three geometries:

```rust
#[test]
fn a_device_leaf_is_not_counted_in_the_gate_word_of_a_chunk() {
    let mut k = K::new();
    let viewer = k.with_aspace();
    k.ok(Syscall::UntypedRetype {
        untyped: s(DEV), kind: Frame, size: 1,
        page: PageSize::Page as u64,
        memory: MemoryType::Uncached as u64,
        destination: s(40),
    });
    let (_, _, base) = k.m.frame_at(k.t, s(40)).unwrap();
    let chunk = base >> k.chunk_shift();
    let before = k.m.map_count(chunk);
    k.ok(map(40, s(UT), AT, 1, Rights::READ));
    assert_eq!(k.m.map_count(chunk), before, "...");
}
```

fails on all three: `left: 1, right: 0` on the reference machine (the device range
at 2 MB is chunk 1, whose ownership word is *none*), `left: 5, right: 4` on 16 KB
pages and `left: 3, right: 2` on 32 KB pages, where chunk 0 covers the machine
table, the kept image and the device range together. The 16 KB and 32 KB numbers
show the second half of the fault: on a machine whose chunk is larger than the
low region, the map count of chunk 0 already counts four leaves into the global
read-only set before the device mapping, though no page of chunk 0 is *data*.

**What a kernel author would do wrong.** Implement G4 literally (count only leaves
that target the chunk's own pages) and the model's audit (G14, and invariant 58)
will declare a containment violation on a machine that maps its own kept image or
its own device registers. Or implement the model and have R6 clear a count that
was never the chunk's: R6 sets "every chunk whose ownership word reads *taken* by
*X*'s generation … whose map count becomes 0" (line 1110), and a leaf into *X*'s
kept frame, or into *X*'s device entry, is not one of those — the count of a
*none* chunk is written by a gate that G4 does not give it to.

**Smallest correction.** One sentence in G4: "a leaf of device memory is counted
in its device entry's ownership word, and a leaf into the global read-only set in
no count", and then make the model refuse to count in a chunk whose ownership word
is *none*. That also makes G5 ("give, destroy and retype require map count 0")
mean something for device blocks, where it now means nothing: `mapped_block`
returns `false` for `Block::Entry` (`model/src/blocks.rs:253-268`).

### F7. The model's `PageClass` is one variant, so three of G2's six classes are neither recorded nor checked, and G3 (3)'s "next level down" has no check

**What is wrong.** G2 names six classes — *data*, *gate*, *global read-only*,
*device*, *iospace table*, *page table of level k*. `abi` gives all six
(`PageClass::{DATA, GATE, GLOBAL_READ_ONLY, DEVICE, IOSPACE_TABLE, table(level)}`,
`abi/src/machine.rs:117-171`). The model has a *different* type of the same name
with a single variant, `pub(crate) enum PageClass { Table }`
(`model/src/table.rs:127-130`), and `class_of` can return only `DEVICE`,
`GLOBAL_READ_ONLY`, `DATA` and `PageClass::table(1)` — always level 1, whatever
the table's level (`model/src/memory.rs:329-348`). No page is ever recorded as
*gate* or as *iospace table*, and no page is recorded with a level.

**Where.** Model `model/src/table.rs:127-130`, `model/src/memory.rs:297-300`
(always `PageClass::Table`), `model/src/caps.rs:333`, `model/src/memory.rs:
329-348`.

**How I know.** Read. `grep -rn "PageClass" model/src` returns one variant and
four write sites, all `Table`.

**What a kernel author would do wrong.** Take the model as the executable
statement of G2 and store one bit per page — "is this a table page" — and then
have nothing to check G3 (3)'s "an entry that is not a leaf must point to a table
page of the next level down" against, nor a *gate* page against. A page that is a
level-1 table used as a level-2 table is a hole the contract names and the model
does not.

**Smallest correction.** Give the model's `PageClass` the six classes of `abi`
(the type already exists) and store the level with the table page, since the
level is what `aspace_map` knows when it takes the table
(`model/src/memory.rs:288-300`, `tables(...)` at `:270` already computes it).

### F8. The class check of `aspace_map` and `aspace_protect` can never return its `denied`, so the place D-124 gave it in the order of checks has no executable check

**What is wrong.** The contract adds a state `denied` for the class of the page a
mapping targets and places it third of five state checks. It then says in the same
sentence that "a correct kernel never reaches this one, since frames never cover
table or gate pages, kept frames have no `write` and device frames no `exec`"
(line 284). Both statements are true, and together they mean the rule cannot be
exercised: a `Leaf` that a class refuses is one the plain-argument check has
already refused (`write` with `exec` is `invalid`, `exec` on a device frame is
`invalid`), and a page that is a table is never a page of a frame (invariant 58,
`model/src/check/table.rs:283`, forbids a translation to a table page, and the
untyped watermark never hands a frame the page a table was taken from). I looked
for the four states the check guards and found none of them reachable:
`class_of` returns `DATA` for every page of every frame that is not kept and not
device.

**Where.** Contract `architecture/kernel-interface.md:284` and `:292`
(`aspace_protect`). Model `model/src/memory.rs:242-245` and `:432-441` (the two
`denied`s), which no test in `gate_attack.rs`, `gate_words.rs` or `memory.rs`
reaches.

**How I know.** Read, plus a search: no test in `model/tests` asserts `Denied`
from `aspace_map` or `aspace_protect` on a class, and the model's own comment in
the contract's words says why.

**What a kernel author would do wrong.** Two ways. Read line 284 as a promise
that a mapping of a page a class refuses is refused, and rely on it to catch a
buggy `untyped_retype` that hands out a page already used as a table — which is
exactly the bug the check exists for, and which the *contract* admits no correct
kernel reaches, so nothing tests that the check is even in the right place
relative to the map count. Or omit it, since it is unreachable, and lose the one
defence against a fault in the watermark.

**Smallest correction.** Say plainly that the check is a defence against a fault
of the gate's own input and that the reference model cannot reach it, and add to
the model one test that reaches it through a state the model can build — a page
placed in `table.classes` by hand, as `model/src/check/tests.rs:2079` already
does for the invariant, then a mapping of a frame that covers it; that at least
pins the order (`denied` before the map-count `busy`, after the two `busy`es
above it).

### F9. `aspace_protect`'s "`busy` … a mapping that touches more than *E* chunks, which only a mapping made in steps does" can never hold

**What is wrong.** The state list of `aspace_protect` is "`busy` if the record is
empty, a binding, **a partial mapping**, a mapping in another space, or **a
mapping that touches more than *E* chunks, which only a mapping made in steps
does**". The last clause names a subset of the third: a mapping that touches more
than *E* chunks is, by G3, a mapping made in steps, and a mapping made in steps
is partial, which is already `busy` two words earlier. Under the contract's own
values the fifth clause is dead; the model implements it as a live check
(`model/src/memory.rs:421-431`) that nothing can reach, and its own comment says
so ("a mapping that touches more chunks than one call of the gate checks is
`busy`").

**Where.** `architecture/kernel-interface.md:292`. Model
`model/src/memory.rs:421-431`.

**How I know.** Read. A non-partial mapping is written entirely in one call, and
one call checks at most *E* chunks (G3), so `touched <= gate_chunks` for every
non-partial mapping, and `mapping.partial` returns `busy` first; with the test
knob `gate_chunks` lowered the check becomes reachable only in a configuration
where the bound is not *E* (see F10).

**What a kernel author would do wrong.** Read the fifth clause as the rule for
protecting a large mapping and try to reach it, and never find the state: the
mapping is `busy` as partial. Or implement the fifth clause as a *separate* state
that a protect may reach, and return `busy` for a mapping the call should have
protected.

**Smallest correction.** Delete the fifth clause, and add after the sentence what
the author needs: "a mapping made in steps is always partial and therefore always
`busy`; to change its rights, unmap it and map it again (G3)".

### F10. The model's step loop has a floor of one leaf per call that the contract does not state, and which holds the "at most *E* chunks" bound only because of the three geometries' values

**What is wrong.** G3 says "One call of the gate checks at most *E* chunks", and
"A leaf of ordinary memory touches at most *E* chunks (a run, hence a frame, is at
most *E* chunks)". The model's step loop always writes at least one leaf, whatever
it costs: `while done + step < map.count { let c = cost(..); if step > 0 && spent
+ c > budget { break; } … }` (`model/src/memory.rs:226-235`). So the bound *E* is
respected only when one leaf costs at most *E* chunks, which is true of the three
geometries because in each of them the largest page size divided by the chunk is
exactly *E* (2^30/2^21 = 2^36/2^25 = 2^39/2^27 = 512, 2048, 4096 = *E*). It is not
a consequence of G3, and `Geometry::valid` permits a machine where it fails — for
example `page_shift: [12, 21, 30, 39]` with *E* = 512 and four levels, where a leaf
of the third large page covers 2^18 chunks in one call.

**Where.** `architecture/kernel-interface.md:887` (G3, "Bound (design
choice)"). Model `model/src/memory.rs:220-241`, `abi/src/lib.rs:458-478`
(`Geometry::valid`).

**How I know.** Read, with the arithmetic of the three geometries checked by the
suite's own frame tests (`model/tests/gate_attack.rs:431-490` asserts one map
count per chunk of a 1 GB leaf, and `gate_chunks` is `u64::from(geometry.entries)`
at `model/src/boot.rs:350`).

**What a kernel author would do wrong.** Implement the step loop as the model has
it and accept a leaf that costs more than *E* chunk checks in one call — the very
cost G3's bound exists to prevent — and then have the proof of the gate fail on
that machine, or assume that a leaf is at most one table's worth of chunks because
G3 says "a frame is at most *E* chunks" without noticing that this is chunks of
the frame, not chunks of the target.

**Smallest correction.** One sentence in G3: "a machine on which the largest page
size is more than *E* chunks is refused at start-up, so that one leaf always fits
one call", added to `Geometry::valid` in `abi` as `largest_page <= chunk * E`.
Then the model's floor is true and the bound is a bound.

### F11. G2 lists *global read-only* and *device* as values of the stored per-page class byte, in the same paragraph that says their class is not stored

**What is wrong.** "The byte is `PageClass` of `abi/`: 0 *data*, 1 *gate*, 2
*global read-only*, 3 *device*, 4 *iospace table*, 16 + k *page table of level k*"
— and, nine words later in the same paragraph, "A page of device memory or of the
global read-only set lies in no chunk: **its class is not stored** but follows from
where it lies". A kernel author cannot tell whether a byte of 2 or 3 is a legal
value of the array (for a page the gate can reach) or a value that must never
appear. `abi` provides both constants and the model's `class_of` returns both.

**Where.** `architecture/kernel-interface.md:886`, two halves of one paragraph.

**How I know.** Read.

**What a kernel author would do wrong.** Write 2 or 3 into the page classes for
the kept image and the device range at start-up — harmless, and it makes every
"is the byte 0" test cost a comparison instead of a mask — or assert at start-up
that no byte is 2 or 3, and then fail a machine whose device range falls inside a
chunk's physical index (which it does on the 16 KB and 32 KB geometries; see F6).

**Smallest correction.** Say which clauses are about the array and which are about
the six names: "the byte holds 0, 1, 4 or 16 + k; 2 and 3 are values of
`PageClass` that the array never holds, because such a page lies in no chunk".

### F12. The model's reclaim comment says the contract has a gap that the contract closed

**What is wrong.** `model/src/recovery.rs:1023-1027`: "// CONTRACT-GAP
(reported): the barrier does not say that the context entries of the node must be
gone; when the holder of a unit is itself fenced, nobody has blocked them (R1)
until its successor rebuilds the unit. The model waits for that too." The barrier
does say it: "and no context entry of any IOMMU unit names *X*'s generation … so
that *X*'s devices can write into no memory reused after its death"
(`architecture/kernel-interface.md:1124`), added by this change (D-124).

**Where.** `model/src/recovery.rs:1023-1027` against
`architecture/kernel-interface.md:1124`.

**How I know.** Read.

**What a kernel author would do wrong.** Read the model's comment, conclude the
contract leaves the case open, and choose the model's own answer — or ask the
owners for a decision that is already in the text. Worse, an author who removes
the model's extra wait "because the barrier does not require it" reopens the hole
the sentence closes: a device of a dead node writing into memory already given
out.

**Smallest correction.** Delete the comment, or replace it with "the barrier
requires it: [Reclaim](#the-reclaim-barrier), 'and no context entry of any IOMMU
unit names X's generation'".

---

## What I checked and found right

- **The guarantee (G) for the calls I could build.** No call in my probes or in
  the suite lets a node map memory it does not own: `aspace_map` and `iospace_map`
  refuse a chunk whose word is not the caller's (through the invariant rather
  than a check of their own, which is sound: `memory_give` and the destruction of
  a block need no descendants and no live piece, so a frame outlives no block),
  and `sys.check()` stays `Ok(())` after every attack I wrote.
- **Six classes in `abi`, with the contract's numbers**: `DATA` 0, `GATE` 1,
  `GLOBAL_READ_ONLY` 2, `DEVICE` 3, `IOSPACE_TABLE` 4, `table(level)` 17 to 24
  (contract: 16 + k, k from 1); `from_raw` refuses 5 to 16 and 25 and above
  (`abi/src/machine.rs:117-171`), and `PageClass::permits` encodes G3 (3) and (4)
  — a data page never with a device memory type nor write-and-execute, a global
  read-only page never writable, a device page never executable and always with a
  device memory type, a table or gate page never a leaf target.
- **The map count at the limit, the same in the three artefacts.** Contract G4:
  `MAP_COUNT_MAX` = 2^32 − 1 leaves per chunk, and a count that would pass it is
  `busy` (`:888`). `abi`: `MAP_COUNT_MAX: u64 = u32::MAX as u64`
  (`abi/src/machine.rs:104`), and a 32-bit field in `GateWord`, so no word can
  hold a count above it. Model: `map_count_max` defaults to
  `dodos_abi::MAP_COUNT_MAX` (`model/src/boot.rs:349`) and the check is
  `count + leaves > map_count_max` → `busy` (`model/src/memory.rs:252-263`), after
  the "already translated" and the class checks, as G4 says. Within one call it is
  right too: two leaves of one call in one chunk with the maximum at 1 is `busy`
  and the count does not move —
  `a_map_count_that_would_pass_its_limit_within_one_call_is_busy` passes on all
  three geometries. (The knob lower than `MAP_COUNT_MAX` is what G4 asks for,
  "tested with a smaller maximum so that this rule is reached".)
- **The map count equals the leaves**, in both directions: `record_mapping`,
  `extend_mapping` and `empty_mapping` add and subtract the mapping's own count
  once (`model/src/memory.rs:51-72`, `:352-380`, `:112-124`), a device leaf and a
  kept leaf included (F6), and invariant 58 requires `leaves == *table.maps`
  (`model/src/check/table.rs:287`). A partial record is counted once, not twice,
  and an unmap of a partial record gives every leaf back — the suite's
  `a_mapping_beyond_the_budget_of_a_gate_call_is_written_in_steps` and my probes
  agree.
- **A partial record for every other rule**: `aspace_unmap` undoes the pages it
  holds, `aspace_protect` is `busy` on it, a removal of the capability undoes it,
  and no thread is woken — `gate_attack.rs:492-528` and F2's probe.
- **The bound of one call, on the three geometries.** Every frame is at most *E*
  pages, every leaf is at most *E* chunks, and the step loop charges one per chunk
  touched (`model/src/memory.rs:220-241`, `model/src/memory.rs:74-85`): a frame of
  one 1 GB page is one leaf per call on the reference machine, as G3 says, and a
  frame of *E* pages of a page size equal to the chunk is one call of *E* leaves.
  The `again` of a stepped mapping leaves a record that the audit of G14 and
  invariant 58 still accept.
- **`iospace_attach`, one owner word per device identifier.** The word is keyed by
  segment and device (`identity_key`, `model/src/memory.rs:540-543`), taken by
  `may_take` on the rules of taking (free and this node's, unclaimed, or of a dead
  node) and by a taken word of the caller's own generation
  (`holds_identifier`, `:547-559`); detaching removes it, so it reads free and
  unclaimed (`detach_local`, `:561-575`); another node's word is `denied`, for an
  attach and for a detach alike, at the place the contract's IOMMU list gives it.
  The suite's `a_node_cannot_attach_or_detach_a_device_whose_identifier_another_node_holds`
  covers the pair of them.
- **A node dying while attached.** The context entry names the node's generation
  and the barrier requires it gone before dead (`:1124`), R1 clears it, and the
  model waits for it before writing dead (`model/src/recovery.rs:1027-1030`); the
  suite's `a_node_that_dies_with_an_attached_device_leaves_no_context_entry`
  reaches dead. The identifier word is *not* freed by any step, which the text
  does not ask for: "After dead, every ownership word and device entry owned by
  *X* is free for any live node", and a free-then-taken word of a dead node is
  takeable by rule 3 of taking, so no node can be locked out of a device.
- **Leftover usable memory as device memory.** Rule 6 of the start-up
  (`:1658`) and `model/src/boot.rs:670-684` agree exactly, and the kept ranges are
  taken out of the device set (`taken.extend(kept …)`), so no page of the kernel
  image, of the kept image, of the machine table or of a crash area can be reached
  as a device frame — which is what the guarantee needs.
- **The contract's numbers, spot-checked and right.** 64 calls (I counted the
  table at `:58-67`: 6 + 7 + 8 + 8 + 7 + 2 + 6 + 5 + 9 + 2 + 3 + 1 = 64); *E* ≤
  4,096 and 12 bits for the page count; "134 million" = 512^3; "16 MB for 64 GB" =
  64 GiB / 4 KiB; `IDENTIFIERS_PER_SEGMENT` 65,536 × 8 = 512 KB; 0xFF, 0xFB, 0x45,
  0x41 against the rights of a kind; the capability slot's bit 5 for the partial
  mark and `abi`'s `SLOT_RECORD_PARTIAL = 1 << 5`; `abi::Error`'s twelve codes and
  the table of errors, in the same order and with the same one-line meanings; the
  ownership word's state 3, "never written", defined at `:763` and refused by
  `Ownership::from_raw`, so G2's "as a word with state 3 does" is not a
  contradiction.
- **The anchors.** Every `](#…)` link in the file resolves to a heading: no
  broken anchor in `kernel-interface.md` (checked over all 106 headings).
- **The suite.** `nix develop -c ./verify` passes at `2afc901` on all three
  geometries, including the two new gate test files and `blocks.rs`.

## What I did not have time to check

- The two-node races of G6 (grants, the use entry's leaf count, revocation in two
  steps) and of the `iospace` copies, beyond the one attack the suite already has.
  I did not write a test that revokes a grant while a device of the grantee maps
  it, nor one that gives a chunk under a live grant.
- D-114 ("a device that moves with its driver") as a state transition: I read the
  identifier word's rules and the model's `holds_identifier`, but did not build a
  `thread_move` of a driver whose device is attached and check whether the word
  follows the driver or stays with the node.
- A PCI requester-id alias across a bridge (two functions that present the same
  identifier): the contract keys the word by `segment << 16 | identifier` and the
  model by the same key, so two units of one segment share a word; I did not
  decide whether that is right for a bridge that rewrites the identifier, and did
  not verify the hardware fact against a primary source (**not verified**).
- Whether a page can change class while a grant or an IOMMU entry of the old class
  remains. I checked the one path that exists (a page becomes a table page only at
  the watermark, so no translation to it can exist) and found it sound, but did
  not attack the grant path.
- Interrupted removal (a `cap_delete` of a frame whose record is partial, over
  several steps) and the interaction with the audit of G14, beyond invariant 58.
- The four reports of the sixth review, so I have not checked that each of the 38
  findings is answered, only those that touch my angle.
- `cargo kani`, Miri and the sanitizer (not in Nix), so the pure functions of
  `abi/` are checked by their tests only.
