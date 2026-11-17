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

---

## irq.rs

No finding proved. Read: `irq_claim`, `irq_bind`, `unmask_line`,
`irq_ack`, `line_target`, `interrupt`, `interrupt_on`, `line_masked`,
`signal_bits`, `unbind_irq`, `unbind_one_irq`, `irq_removal`, `handle_of`,
`msi_removal`, `line_remap_removal`, `handle_asking`, `line_asking`,
`irq_destroyed`.

Notes from reading, not run:

- The handle `core × 192 + (vector − 48)` is cast to `u16`
  (`irq.rs:79`, `148`, `292`, `435`). With remapping the core is below 341,
  so the handle fits; without remapping the APIC ID must be at most 255 and
  a core's number is at most its APIC ID only if the hardware identifiers
  are distinct. `boot.rs` never checks that they are (the core list is only
  sorted, `boot.rs:454-458`), so two cores with one APIC ID would make every
  later core number larger than its identifier. Firmware gives the APIC
  IDs; hardening only.
- `irq_claim` of an MSI does not tie the source's requester identifier to a
  device this node attached; the remapping entry it writes is for this
  node's own core and vector, so I found no gain for the caller.
- `served` and `ioapic_role` compute `first_gsi + inputs` in `u32`
  (`irq.rs:38`, `units.rs:125`); the boot values are not checked against
  overflow (same family as finding 2).

---

## nodes.rs

No finding proved in this file itself; its message handlers are reached
through finding 5. Read: `node_of`, `others_live`, `node_start` (window
checked against `CORE_WINDOWS` before `64 × window`, `nodes.rs:142-147`),
`first_service_module`, `node_stop`, `node_status`, `own_core`,
`node_idle`, `node_perf`, `node_watch`, `accuse`, `accuse_self`,
`park_all`, `observe_watched`, `unwatch_one`, `publish_counters`,
`park_confirmed`, `membership_now`, `locked_now`, `evidence`, `needed`,
`successors`, `real`, `observe_needed`, `accuse_with_evidence`,
`fence_step`, `fence_unit`, `r0`, `r0_effects`, `r1`, `r1_done`,
`had_device`, `reclaim_step`, `audited`, `audit_block`,
`containment_violated`, `barrier_holds`, `clear_step`, `unpin`,
`seal_step`, `resume_step`, `ended_while_sealed`, `drop_ended`,
`start_step`, `start_over`, `start_due`, `reserve_due`, `others_exist`,
`reserve_work`, `reserve_step`, `take_hw`, `idle_table`.

Notes, not run:

- `node_start` stores the image and module in one field of the model,
  `start_image` (`nodes.rs:257`), which nothing reads but
  `resume_replacement`; a fresh start always builds from the boot layout
  (`system.rs:805`). The `module` argument is judged
  (`first_service_module`, any segment index passes) and then ignored.
  Not a hole of the model, but the reference does not say what a fresh
  start with module *m* runs.
- `System::enter` drops a failed `Model::start` silently
  (`system.rs:804-808`): the core stays `Entering` and the node `Starting`
  until its start evidence. `Model::start` refuses only for the start-up
  page, and the start-up page of a node slot outside the initial layout is
  never checked at machine start-up (`layout` checks no start-up page at
  all; `System::boot` checks those of the initial nodes by starting them).
- `evidence` and `observe_needed` read the observations from the accusing
  node's own beacon, but every condition (heartbeat unchanged, consumer
  unchanged, `idle_until`) is read from the accused node's words, so a
  hostile node cannot make the gate accept stale or stuck evidence against
  a node that beats and consumes. I did not find a way around it.

---

## roles.rs

### Finding 7. A `Report` whose next key does not advance keeps a rebuild asking for ever (likely exploitable: a unit role stops serving; the model panics)

Attacker: a hostile kernel of one node that answers the new holder's
`ReportAsk`.

`model/src/roles.rs:678-684`, in `report_received`:

```rust
match next {
    REPORT_END => {
        rebuild.node = from + 1;
        rebuild.key = 0;
    }
    key => rebuild.key = key,
}
```

Any key but `REPORT_END` is taken, including one not above the key asked.
`rebuild_step` (`roles.rs:452-480`) then asks the same node again from that
key. Nothing bounds the number of asks, and a node that answers is never
skipped (`roles.rs:440-444` skips only a node that no longer writes). While
the rebuild runs, the new holder serves no request of the unit
(`serves_role`, `units.rs:427-429`; requests are kept, `units.rs:535-537`),
so every node's attaches, detaches and interrupt claims behind that unit
wait. `rebuild.items` also grows by up to 28 items per answer
(`roles.rs:676`) with no bound.

Attack:
1. Three nodes; node 1 holds the IOMMU and IOAPIC roles and is killed;
   node 2 takes the roles over and rebuilds, asking node 0.
2. Node 0 (hostile) writes every `Report` of its own ring to node 2 with
   next key 0 (the key asked).
3. Node 2 asks again, and again.

Proof: `spoof::c10_a_report_whose_next_key_does_not_advance_stalls_the_rebuild_for_ever`
(it fires one event at a time, rewrites node 0's ring after each, and moves
the clock only to the next timer due). In the model, a kernel message and
its answer take no time, so node 2's recovery reserve makes progress at
the same instant for ever and the model's own bound fires:

```
panicked at model/src/nodes.rs:1974:9:
the reserve makes progress for ever
```

An earlier variant that injected the forged answers itself panicked the
same way. In a real machine the round trip takes time, so the rebuild
does not stop the node: it just never ends, for as long as node 0 answers.
Fix direction: a `Report` whose next key is not above the key asked (or
that is not `REPORT_END`) ends that node's report, and is traced.

Other functions of roles.rs read and found sound: `role_of`,
`reserve_taken`, `role_claim`, `role_hand`, `vmx`, `hand_all_units`,
`roles_step`, `roles_work`, `hand_step`, `handed` (the role is judged by
`refused` first), `take_over_due`, `take_step`, `after_take`,
`rebuilt_attach` (a reported device is kept only if its attach word reads
*attached* with that root, so a hostile report cannot add another node's
device), `serve_kept`, `items`, `report_asked` (the role index is checked
by `refused` before it indexes `role_records`).

