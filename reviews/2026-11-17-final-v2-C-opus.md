# Lot C, second final review (Opus): attack report

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
All tests were run in the copy `/private/tmp/dodos-pr3-v2-C-opus`. The
tests are in one new file, `model/src/scenarios/v2c.rs`, declared by one
added line `mod v2c;` at the end of `model/src/scenarios/mod.rs`. Command
for every test below (from the copy):

    export PATH=/nix/var/nix/profiles/default/bin:$PATH
    nix develop -c cargo test -p dodos-model --lib v2c -- --nocapture --test-threads=1

Each test prints what it observed and asserts the attack's result, so a
test that passes means the attack worked.

The files of the lot were read in the order of the brief. Findings are
numbered in the order found, not by severity. A summary ranked by severity
is at the end.

---

## boot.rs

### Finding 1. A large writable segment of the boot image panics the start-up (hardening)

Attacker: a boot image with any values.

`model/src/boot.rs:1218-1222`:

```rust
let child = |model: &mut Self, size: PageSize, pages: u64, index: u32| {
    let bytes = model.bytes(size);
    let taken = model
        .take(start_untyped, pages * bytes, bytes, Clearing::None)
        .expect("the start-up untyped holds the frames of the start-up");
```

The copied (writable) segments, the start-up page and the message page are
all taken from `untypeds[0]`, the first block of node 0's floor. Nothing in
`Machine::layout` (`boot.rs:625-865`) compares the length of the writable
segments with that block: `floors()` (abi `machine.rs:1236`) only sees the
floor size, and the segment checks (`boot.rs:670-689`) only check place,
overlap and W^X. A segment longer than the first block reaches the
`expect`.

Attack:
1. The boot image declares a writable segment of 8 chunks (16 MB on the
   reference machine); the floor is 3 chunks.
2. `Model::boot` passes every check of `layout` and panics in `build`.

The real kernel, written against this, has no refusal for this case
(`Refusal` has no variant for it): it either faults at boot or copies
beyond its untyped.

Proof: `c1_a_large_writable_segment_panics_the_start_up`. Output:

```
panicked at model/src/boot.rs:1222:18:
the start-up untyped holds the frames of the start-up: NoMemory
C1: Model::boot panicked
```

### Finding 2. Other boot values reach a panic instead of a refusal (hardening)

Attacker: a boot image (BootNodes), and the machine description the start-up
reads.

a. `boot.rs:422-424`, a `BootNode` window:

```rust
(0..64)
    .filter(|i| mask >> i & 1 == 1)
    .map(|i| (64 * window + i) as usize)
```

`window` is the `u64` of `BootNode` (abi `machine.rs:1216`). `64 * window`
overflows for `window >= 2^58`; the model panics, a release build wraps
and the window names cores 0 to 63, so a record no valid layout produces is
accepted as another one. The check `c < self.cores.len()` at
`boot.rs:646` comes after the multiplication. Proof:
`c2_a_boot_node_window_that_overflows`: `panicked at model/src/boot.rs:424:35:
attempt to multiply with overflow`.

b. `boot.rs:434`, a core whose kind is not in the kind list:

```rust
self.kinds[usize::from(self.core_list()[core].kind)]
```

No check that `Core::kind < kinds.len()`. Proof:
`c3_a_core_of_an_unknown_kind`: `panicked at model/src/boot.rs:434:19:
index out of bounds: the len is 1 but the index is 7`.

c. `boot.rs:791-799`, MAXPHYADDR against the memory map:

```rust
let words = 1u64 << (self.phys_bits - geometry.chunk_shift());
let mut owners = vec![Ownership::none().raw(); words as usize];
...
owners[(at / chunk) as usize] = Ownership::free(Owner::Unclaimed).raw();
```

`phys_bits` is never range-checked: a usable region above `2^phys_bits`
indexes past the array; `phys_bits < chunk_shift` underflows and
`phys_bits >= 64 + chunk_shift` overflows the shift (`boot.rs:817` shifts
`1u64 << self.phys_bits` too). Proof: `c5_phys_bits_below_the_memory_map`
(the reference machine with `phys_bits - 1`): `panicked at
model/src/boot.rs:799:19: index out of bounds: the len is 4096 but the index
is 4096`.

d. Not run, read only: `BootNodes.slots` is a `u32` in the ABI
(`machine.rs:1207`) and a `u16` in `Machine::boot_nodes` (`boot.rs:186`):
a kernel that copies the model's type truncates 65,537 slots to 1 before
the `NODES_MAX` check at `boot.rs:652`.

### Finding 3. The crash areas, the kept ranges and the feedback tables are never checked; the checker accepts a misaligned large-page frame (hardening)

Attacker: the loader's values of the boot image (crash bases, image base,
kept ranges) and firmware's (feedback tables).

`boot.rs:130-132` says each crash base is "on a chunk boundary", and
`boot.rs:1281-1288` makes kept frames of first large pages from it:

```rust
for base in std::iter::once(machine.crash.0).chain(machine.crash.1) {
    ...
    self.kept_frame(place, base, PageSize::Large1, chunk_pages, read_derive);
}
```

`layout` never checks the alignment, nor that the crash areas, the image
(`image_base`), the kept ranges and the feedback tables lie in memory,
inside `2^phys_bits`, or apart from each other. They are kept frames
(`read`, `derive`) of the first service, so any physical range they name is
readable by it; they are taken out of ordinary memory (`kept_ranges`), so
they cannot overlap a floor, but they can cover MMIO, ACPI NVS or one
another. No invariant checks that a frame's base is aligned on its page
size (`grep is_multiple_of model/src/check*` finds only cspace sizes, the
watermark and mapping addresses).

Proof: `c4_a_crash_area_off_its_chunk_boundary` (crash base moved by one
page): `C4: boot accepted; check = Ok(())`.

Functions of boot.rs found sound: `without`, `sorted`, `blocks` (the loop
always advances by at least 1 because `at < end`), `start_page_bytes`
(counts are bounded by memory; the result is compared with
`START_PAGE_MAX_PAGES`), `Machine::single`, `nodes`, `features`,
`state_kind`, `core_list`, `kept_ranges`, `table` (indices are bounded by
the checks of `layout`; `best_nodes` is never empty because the booted core
must be placed), `Model::boot`, `start`, `kept_frame`. The timing checks
of `layout` (`boot.rs:745-767`) use saturating arithmetic and `u64` products
of `u32` values; `cores_supported` above 64 only makes them stricter. The
segment checks use `checked_add` for the end and then compare with
`user_end`, so `next_multiple_of(page)` cannot overflow afterwards.

---

## cores.rs

No finding proved. Read: `width`, `here`, `position`, `all_cores` (width 64
handled), `core_of`, `running_core`, `post`, `mark_leaving`, `leave`,
`others_hold`, `start_request`, `invalidate_on`, `start_barrier`,
`answer_pending`, `complete`, `forget_waiter`, `go_idle`, `wake_core`,
`load_root`, `cache_here`, `spurious`, `translated_in`, `request_free`,
`take_interrupts`, `watch_own_cores` (the subtraction `now - stale` is
evaluated only after `now >= watched.1 + stale`), `pending_ipis`,
`auto_deliver` (bounded), `silence`, `due_now`, `set_now`, `fail_on`,
`receive_interrupt`, `begin_fresh`, `core_entered`, `enter_idle`,
`begin_resume`.

One question left open (not run): `core_entered` (`cores.rs:775-797`)
clears the core's `ipis` but not its `pending` set, and `enter_idle` does
not answer what is pending. A request of another core of the node that
asked this core before it parked would wait until the core next goes idle
or takes another invalidation interrupt. I did not build the state of a
resume with a request in flight to see whether it can arise.

`core_entered` writes the core word owned when it reads *joining* without
checking that the word names this node's slot (`cores.rs:791-796`); only
`System` calls it, with the cores of the node, so I found no input that
reaches it with another node's word.

---

## grants.rs

### Finding 4. The holder of a grant maps the physical frame the granting node writes in its `Send`, not the frame of the anchor (exploitable)

Attacker: a hostile kernel of one node (the granting node), which writes
anything into its own ring to the victim.

`model/src/grants.rs:30-40` says the holder learns a grant "from a `Send`
and the anchor it names in the granting node's grant table: the entry, the
serial, the anchor's rights and depth, and its frame". The code takes all
of these from the message body. `send_received` passes each `Granted` of
the body to `place_remote` (`grants.rs:390-396`), which writes:

```rust
rights: granted.rights,                       // grants.rs:457
...
self.frames.insert(id, granted.frame);        // grants.rs:476
let remote = Remote { ..., depth: granted.depth };
```

The one check on a received message (`rings.rs:458-461`) only looks at the
stamp of a `Send`:

```rust
Body::Send { stamp, .. } => {
    let task = dodos_abi::TaskId::from_raw(stamp.0);
    (stamp.0 != 0 && (task.counter() == 0 || task.node() != sender)).then_some(stamp.0)
}
```

and the grant entry (`table.rs:213-221`) holds no frame to compare with.
When the holder maps the remote frame, `memory.rs:120-128` counts its
leaves in the use entry, not in the map counts of the chunks, and invariant
58 (`check/table.rs:261-268`) only asks that a grant entry with that serial
and grantee exist.

Attack:
1. Node 1 (hostile) makes a real grant of one page of its own to node 0
   with `node_send`; node 0's mailbox has a waiting receiver.
2. Before node 0 consumes the ring, node 1 rewrites the `Send` in its own
   ring 1 -> 0: the frame's base becomes the first chunk of node 0's floor,
   its pages a whole chunk, its rights `ALL`.
3. Node 0 delivers it; the receiver holds a "remote frame" over node 0's
   own floor (where the start-up frames and the kernel objects retyped from
   the first untyped live), and maps it read and write.
4. The map counts of those chunks do not move, so the memory can also be
   reused under the mapping.

Proof: `spoof::c8_a_granting_node_chooses_the_physical_frame_the_holder_maps`.
Output:

```
C8: node 0 holds a remote frame at 0x100000000, 512 pages; its floor starts at 0x100000000
C8: node 0 maps it: Ok(Done)
```

and `m.sys.check()` is `Ok(())` after the map (asserted). The memory type
(`frame.memory`) and the page size are taken from the message the same way.

Fix direction: the holder reads frame, rights and depth from the anchor the
grant entry names on the granting node (written by that node's gate), or
the grant entry carries them; invariant 58 compares a remote frame with
them.

Other functions of grants.rs (see the end for the list) were read; the
others' attacks route through `rings.rs`, below.

---

## rings.rs

### Finding 5. The receiver takes a message's sender from its header, not from the ring it came in: any node acts in the name of any other (exploitable)

Attacker: a hostile kernel of one node, writing into its own rings.

Each ordered pair of node slots has its own rings (`rings.rs:271-275`), so
the receiver knows the sender from the ring. `consume(from, ...)` reads
ring `from` → `me` but never compares `from` with the header's sender.
`refused` (`rings.rs:376-401`) takes the sender from the header:

```rust
let header = &message.header;
let sender = header.sender;
if sender >= self.table.nodes {
    return Some(0);
}
let member = self.table.member(sender);
```

and so does `receive_message` (`rings.rs:612`):

```rust
let from = message.header.sender;
```

Every later check (the grant entry's grantee, the use entry's granter, the
role word's holder, the credit toward the sender, the stamp's node) is then
made against the forged sender. `from` is used only for the trace of a
refused message (`rings.rs:519-520`).

Attack A (a grant revoked by a third node):
1. Three nodes. Node 0 grants node 1 a frame; node 1 holds a valid remote
   frame capability.
2. Node 2 (hostile) reads node 0's grant table in the machine table (grant
   index and serial) and writes, in its own ring 2 -> 0, a `Release` whose
   header names node 1 and node 1's generation.
3. Node 0's check passes (the entry's grantee is node 1); node 0 frees the
   grant and removes its anchor; node 1's remote capability is invalid.

Proof: `spoof::c6_a_release_forged_by_a_third_node_frees_another_grantees_grant`:

```
C6: refused by node 0: 0
C6: grant entry on node 0 after: None
C6: node 1's remote frame still valid: false
```

Attack B (an identity forged):
1. Three nodes; node 0's mailbox has a waiting receiver.
2. Node 2 writes in ring 2 -> 0 a `Send` whose header names node 1 and
   whose stamp is node 1's start-up task (`TaskId::new(1, 1)`).
3. Node 0 delivers it with that task identifier: the receiver believes node
   1's start-up task sent it.

Proof: `spoof::c7_a_send_forged_by_a_third_node_carries_another_nodes_task`:

```
C7: node 0's receiver woke with Some(Ok(Message(Delivery { received: Received { header: Header(4294967303), badge: 0, marks: Marks(0), task: 281474976710657 }, words: [42] })))
```

(281474976710657 = node 1, counter 1.) The same path, not run: a
`UnitRequest` naming another requester (a detach of that node's device,
which D-140 ties to its requester), a `Revoke` that removes another holder's
remote capability, a `Handed` or `ReportAsk` that claims to come from the
role's holder, and an answer to another node's credit (the credit serials
are sequential, `rings.rs:324`, so guessable). The checker accepted every
state (each `S::run` step asserts `sys.check()`); no invariant ties a
message to its ring.

Fix direction: `refused` returns `Some` when `header.sender != from`, and
`receive_message` takes `from` from the ring.

### Finding 6. A producer index moved back makes the receiver's subtraction overflow (likely exploitable: a panic in the model, a wrap in a release kernel)

Attacker: a hostile kernel of one node, which writes the producer index of
its own ring.

`rings.rs:489-503`:

```rust
let produced = self.ring_of(from, me, user).produced;
let mut consumed = self.consumed(from, me, user);
let start = ring_resync(produced, consumed, size);
if start != consumed { ... consumed = start; }
if produced == consumed { ... }
let available = produced - consumed;
```

`ring_resync` (abi `ring.rs:179-185`) uses wrapping arithmetic: with
`produced < consumed`, `produced.wrapping_sub(consumed)` is huge, so the
consumer becomes `produced.wrapping_sub(entries)`, which is above `produced`
whenever `produced < entries`. The plain subtraction then overflows.

Attack:
1. Node 1 sends node 0 four entries; node 0 consumes them (consumer 4).
2. Node 1 writes its producer index back to 0, then adds one message
   (producer 1).
3. At the ring's interrupt node 0 panics at `rings.rs:503`.

Proof: `spoof::c9_a_producer_index_moved_back_overflows_the_receiver`:

```
C9: node 0 consumed 4 entries of ring 1 -> 0
panicked at model/src/rings.rs:503:29:
attempt to subtract with overflow
C9: node 0 served the ring: Err("panic")
```

In a release build the subtraction wraps to `entries` and the resync then
reads a ring of stale entries, which the check refuses one by one, so the
real kernel would survive if it uses wrapping arithmetic; the model, the
reference, does not say so, and a kernel that copies `-` with overflow
checks (or `debug_assert`) falls over. Fix: `wrapping_sub` at
`rings.rs:503`, as at `rings.rs:535`.

