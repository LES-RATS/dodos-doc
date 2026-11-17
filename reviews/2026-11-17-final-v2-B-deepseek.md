# Security review of lot B — `deepseek`

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
Work copy `/private/tmp/dodos-pr3-v2-B-deepseek` (the clone was not touched).
My lot: `model/src/blocks.rs`, `caps.rs`, `debug.rs`, `faults.rs`, `ipc.rs`,
`lib.rs`, `locks.rs`, `memory.rs`, `sched.rs`, `table.rs`, `tasks.rs`,
`threads.rs` — 8,756 lines, read in full.

One finding, exploitable, with two instances and a control, all run. Then
four hardening observations, of which the last three are argued and one is
not run. Then the list of functions I examined and found sound, and what I
did not examine.

---

## Finding 1 — `aspace_map` counts a space's *unhooked* table pages as free, and takes too few pages from the untyped; `rehook` then pops an empty free list

**Severity: exploitable.**

**Attacker.** A user program that may map: it holds a frame and write on an
address space (second instance), or an iospace and a device attached through
the IOMMU unit (first instance). It needs two threads on two cores of the
same node, and one earlier `aspace_unmap`/`iospace_unmap` whose invalidation
is not yet complete — both normal states, not test-only states.

**Files and lines.** `model/src/memory.rs:531-532`, in `aspace_map`:

```rust
        let free = aspace.tables - hooked.len() as u64;
        let missing = (wanted - hooked.len() as u64).saturating_sub(free);
```

`model/src/memory.rs:190`, in `rehook_by`:

```rust
            let page = aspace.free.pop().expect("a table on the free list");
```

**What is wrong.** `ASpace` keeps three sets of table pages
(`model/src/lib.rs:645, 655, 659`):

```rust
    tables: u64,
    free: Vec<u64>,
    unhooked: Vec<(CapId, u64)>,
```

and the checker holds them to `tables == hooked.len() + free.len() +
unhooked.len()` (`model/src/check/table.rs:479-481`:

```rust
            let taken = space.hooked.len() + space.free.len() + space.unhooked.len();
            let followed = space.root.is_none() || space.tables == taken as u64;
            ensure(followed, "59: tables of a space")?;
```

`unhooked` is the whole point of D-137: a table page released by the
clearing of a record does **not** join the free list until the invalidation
that covers its unhooking completes (`model/src/memory.rs:181-185` pushes it
to `unhooked` when `by` is `Some(cap)`, and `finish_unmapping` moves it to
`free` only at the completion). So at any moment while one of these
invalidations is in flight, `aspace.free` is short by exactly
`aspace.unhooked.len()` relative to the count `tables - hooked.len()`
computes. `aspace_map` uses that inflated count, concludes that the free list
already holds the pages the new mapping needs, and returns `missing = 0`.
`record_mapping` then calls `rehook`, which needs `wanted - hooked.len()`
fresh hooks and finds nothing to pop.

The model's own stated rule is broken. It is step 4 of this same function's
contract comment, `model/src/memory.rs:441-442`: the `no_memory` refusal is
meant to fire when the tables needed exceed what *the free list* and the
untyped supply, which is exactly the count computed wrong above.

> // the tables needed are more than the free list and the untyped
> // supply (`no_memory`), and nothing is taken.

The correct computation is `aspace.free.len() as u64`, not
`aspace.tables - hooked.len() as u64`; `hooked.len()` here is recomputed from
the translations, so the difference silently admits the `unhooked` pages.

**Why it matters beyond the panic.** The model is the reference the kernel is
written against. A kernel that computes "what the free list still holds" the
same way takes too few pages from the untyped and then reads a table pointer
off an empty free list — it installs a leaf or an intermediate table into a
physical page that no untyped handed it, which is precisely the authority
(over physical memory, over another node's memory) that G2/G3 exist to
withhold. In the model this shows up as a panic; in a kernel it is a write
into memory the node does not hold.

### The attack, first instance (an iospace that serves a device)

1. Node 0 has two cores; a thread of the node makes an iospace and attaches a
   device through the iommu (`attached`).
2. A second thread of the node is made on the second core.
3. The first thread maps one frame of the iospace's own untyped at
   `1 << 20`: three lower tables are hooked and `tables` becomes 3.
4. The first thread unmaps that frame. The iospace serves a device, so
   `begin_unmap` (`model/src/memory.rs`) takes the unit path: the entries are
   cleared, the record stays `Unmapping`, and the three freed tables go to
   `unhooked`. The call returns `waits`.
5. The second thread maps another frame of the same iospace's untyped at
   `1 << 40`, an address whose three tables are disjoint from the unhooked
   ones. `aspace.tables - hooked.len()` is 3, `wanted - hooked.len()` is 3,
   so `missing` is 0; `aspace.free` is empty. `rehook_by` pops from an empty
   vector.

### The attack, second instance (a plain address space)

Same defect, no device and no driver role needed:

1. One node of two cores; the first thread's context is placed on core 0.
2. A second thread is made on core 1 and yields, so core 1 runs it and is not
   idle (an idle core is not *asked* for the invalidation: `asked == 0`
   completes the request in the call, `model/src/cores.rs:351-356`, and the
   window closes).
3. The first thread makes an address space from the untyped and maps two
   frames at `0` and `1 << 40`: six tables, `tables = 6`, `hooked = 6`.
4. Core 1 holds the tag of the space, so the first thread's `aspace_unmap` of
   the frame at `0` is asked of it: the record stays `Unmapping`, the three
   tables it unhooked stay off the free list, and the call returns `waits`.
   Measured state: `tables=6 hooked=3 free=0 unhooked=3`.
5. The thread of core 1 maps a third frame at `1 << 38`. `aspace.tables -
   hooked.len()` is 3, `wanted - hooked.len()` is 3, `missing` is 0, and
   `aspace.free` is empty.

### The proof

A test file, `model/src/scenarios/v2b.rs`, registered as `mod v2b;` in
`model/src/scenarios/mod.rs` of the work copy only. Three tests; `f1` and
`f1b` are the two instances, `f1c` is the control that shows the same call is
accepted once the pages are on the free list.

Command:

```
cd /private/tmp/dodos-pr3-v2-B-deepseek
PATH=/nix/var/nix/profiles/default/bin:$PATH \
  nix develop -c cargo test -p dodos-model v2b -- --nocapture
```

Output, verbatim (the thread ids and the elapsed time vary between runs; the
rest does not):

```
aspace: tables=6 hooked=3 free=0 unhooked=3
aspace after the answer: tables=6 hooked=3 free=3 unhooked=0
thread 'scenarios::v2b::f1b_an_aspace_map_after_an_unmap_whose_invalidation_is_in_flight' (13122816) panicked at model/src/memory.rs:190:42:
a table on the free list
test scenarios::v2b::f1c_the_same_map_is_accepted_once_the_invalidation_has_completed ... ok
test scenarios::v2b::f1b_an_aspace_map_after_an_unmap_whose_invalidation_is_in_flight ... FAILED
iospace: tables=3 hooked=0 free=0 unhooked=3
thread 'scenarios::v2b::f1_a_map_whose_space_has_unhooked_tables_counts_them_as_free' (13122815) panicked at model/src/memory.rs:190:42:
a table on the free list
test scenarios::v2b::f1_a_map_whose_space_has_unhooked_tables_counts_them_as_free ... FAILED
failures:
    scenarios::v2b::f1_a_map_whose_space_has_unhooked_tables_counts_them_as_free
    scenarios::v2b::f1b_an_aspace_map_after_an_unmap_whose_invalidation_is_in_flight
test result: FAILED. 1 passed; 2 failed; 0 ignored; 0 measured; 523 filtered out; finished in 0.27s
```

The `eprintln!` lines are printed before the calls that panic, so the states
in them are the states the panicking calls run against. `f1c` reaches the
same space with the same three pages merely *moved* from `unhooked` to
`free`, and the same third mapping then succeeds, served entirely out of the
free list (`tables` stays 6, no page from the untyped). The only difference
between `f1c` and `f1b` is that bookkeeping.

Note that these three tests fail on the code of head `6312868`; the 523 other
tests in the crate were not re-run for this report (see "What I did not
examine").

---

## Hardening observations

### H1 — `range_of` fails open on a malformed ioports range word

`model/src/debug.rs:523-525`:

```rust
pub(crate) fn range_of(badge: u64) -> IoPortRange {
    IoPortRange::new(badge & 0xFFFF, badge >> 16 & 0xFFFF).unwrap_or(IoPortRange::ALL)
}
```

A word whose first exceeds its last yields `IoPortRange::ALL`, the *widest*
range, rather than the empty or the refusing answer. `ioports_issue` builds
its badge with `IoPortRange::new(...).ok_or(Error::Invalid)?`, so the only
producer of a malformed word is a start-up capability taken from a boot
image; and `check` refuses such a word anyway (`model/src/check.rs:419-425`,
invariant 93, requires `(inner & 0xFFFF) <= (inner >> 16 & 0xFFFF)` on every
derived `ioports` capability, and `model/src/check.rs:441-448` requires the
root's badge to be exactly `0xFFFF << 16`). I therefore believe it is
unreachable, and I rate it
*hardening*: a fail-open on a value read out of a word is the wrong shape for
a kernel, and it is one missing invariant away from being a full port grant.
**Not run:** I found no state the current checker accepts that reaches it.

### H2 — `memory_split` does not consult the leaf count (G5) of the entry it cuts

`model/src/blocks.rs`, `memory_split`, guards only with `idle_block`:

```rust
        self.idle_block(cap, object)?;
```

while `memory_give`, the call of the same family just above it, calls both
`self.idle_block(cap, object)?` and then `self.mapped_block(object)`.
`mapped_block` for an entry is
`device_leaves[index] != 0`, which `idle_block` does not look at. I could not
reach a state where the two differ: leaves of a device entry exist only for
mappings of frames whose capability descends from that entry's untyped, and
such a frame (or the child untyped in between) is always a child of the
entry's root capability, so `caps[cap].children` is non-empty and
`idle_block` refuses first. I rate this *hardening* — the stronger check is
free and the code reads as if the two calls were meant to agree. **Not run:**
no failing test; the argument above is why.

### H3 — `fits` is judged before `vacant` in `cap_derive`, `cap_move`, `untyped_retype` and `ioports_issue`

`model/src/caps.rs:206-208` (with the comment "Order of checks, step 3: the
depth checks come last"), `:222-223`, `:294-295`, and
`model/src/debug.rs:480-481`. Each reads, in this order:

```rust
        self.fits(place.space, parent, Placing::Derived)?;
        self.vacant(place)?;
```

`Placing::Moved` and `Placing::Retyped(_)` stand in for `Derived` where they
apply. If the "last" of that comment means after the state check of the
contract's step 4, the two are swapped. Both functions are pure, so nothing
but the error code a caller sees differs (`Invalid` where the contract may
say `no_slot` on a full destination). I could not check this against the
contract text — `architecture/kernel-interface.md` is not in this repository
— so I record it as an ordering question and not as a finding. **Not run.**

### H4 — `return_watermark` resets the watermark without re-reading `live`

`model/src/caps.rs:508-528`, `return_watermark`:

```rust
    pub(crate) fn return_watermark(&mut self, untyped: ObjId) -> Result<(), Error> {
        let Some(epoch) = self.untypeds[&untyped].ready else {
            return Ok(());
        };
        if epoch > self.barrier_epoch {
            ...
        }
        let untyped = live(&mut self.untypeds, untyped);
        (untyped.watermark, untyped.clean, untyped.ready) = (0, 0, None);
```

`ready` is raised only when `live` reaches 0, but the reset is not gated on
`live` still being 0, and `take` skips `return_watermark` entirely for
`Clearing::WithinCall` (the segments of `cspace_grow` and the tables of
`aspace_map`). If a `WithinCall` take could raise `live` above 0 while
`ready` is `Some`, the next `return_watermark` would move the watermark back
to 0 over a live object — two live pieces of memory in the same range. I
looked for the interleaving and believe it does not exist: the only two
`WithinCall` callers take from the untyped that the calling space was made
from, and that space's own object holds one `live` on it for as long as the
space exists (`create` → `take`; `destroy` → `release`), so `live` cannot
reach 0 while either caller is still able to run. **Not run:** I found no
reaching state. Worth a `debug_assert!(live == 0)` all the same.

---

## Functions examined and found sound

For each I asked what the attackers of the brief gain, and found no answer I
could prove.

**`blocks.rs`** — `Model::control`, `Model::run` (the `size` argument is
bounded to `chunk_shift ..= chunk_shift + entries_shift` before every shift,
and `place + (1 << size) >> shift` is guarded by the `checked_add` and
`limit` check above it), `Model::memory_take` (both kinds; the run's chunks
must each be a well-formed word this node may take, and `Ownership::none`
chunks are refused twice over), `Model::taken_here`, `Model::block` (the
capability must be the object's root), `Model::idle_block`, `Model::memory_give`
(`node as u16` cannot truncate: `table.nodes` is a `u16` and `node` is checked
below it), `Model::unmap_block` (the in-flight `Completes::Run` scan and the
`kernel_runs` removal), `Model::memory_split` (see H2), `Model::mapped_block`,
`Model::free_block`, `Model::take_block`, `Model::write_freed`,
`Model::remove_block_cap`, `FreedRun::chunks`.

**`caps.rs`** — `footprint` (`ObjectKind::CSpace`'s `segments * 16` cannot
overflow and `.next_power_of_two()` cannot panic: `size <= u64::MAX` gives at
most `2^61`; the frame's `size * bytes` is bounded by `geometry.entries`),
`cap_derive` (the badge rules, the subset rule, and that a kept badge is what
survives), `cap_move`, `cap_delete` (the `via != 0` refusal in a dying space
is the documented single exception, and `through` still demands `write` on
the `via` capability), `cap_revoke`, `cap_inspect`, `untyped_retype` (the
child untyped's clean mark and base), `cspace_grow` (`slots.len() >= max`
is `no_slot` and `max` was validated in `footprint`; the start-up space has
`from == None` and cannot grow), `thread_size`, `depth`, `fits`, `take`
(`checked_next_multiple_of` and `checked_add`, and `Again` leaves only the
clearing bookkeeping changed), `release`, `return_watermark` (see H4),
`create`, `new_cap`, `derive`, `place`, `slot`, `remove`, `next_removed`,
`swept`, `rooted`, `waiter`, `undo` (every arm either does one unit or says
`Wait`), `remove_leaf`, `remove_leaf_dead`, `remove_root`, `remove_cap`,
`destroy` (the `tables` release count, the `attached_to` pin of the root's
class).

**`debug.rs`** — `DebugArea::new`, `DebugArea::write`, `DebugArea::write_raw`,
`CrashArea::new` (the sequence is one more than the previous area's),
`CrashArea::accepted` (a record is accepted only with this boot's commit),
`CrashArea::write_record` (a fence's record does not replace a held one of
the same generation), `Limit`, `Model::stamp`, `Model::entry`,
`Model::trace` (code 6 is exempt from the rate limit; the suppressed count
is reported in a code-3 entry of the next window), `Model::trace_transitions`,
`Model::fail`, `Model::enter_debug_areas`, `Model::ring`, `Model::trace_ring`
(`saturating_sub(entries).max(1)..next` yields at most `entries` values),
`Model::suppressed`, `Model::area_generation`, `Model::crash_record`,
`Model::debug_write` (`length <= DEBUG_WRITE_MAX = 512`, so 16 words and 22
entries at most; a short `words` reads as zero), `Model::trace_emit`,
`Model::ports_refused`, `Model::platform_holder`, `Model::ports_of`,
`Model::ioport` (`ioport_check` fixes the width to 1, 2 or 4 and the access
inside the range before `port + width - 1` is computed, so that sum cannot
underflow or overflow), `Model::ioports_issue` (the child's range must lie
inside the parent's), `Model::entropy_read` (`length <= 64`, `left` is at
least 1 inside the loop, so `1 << (8 * left)` is defined),
`range_of` (see H1).

**`faults.rs`** — `Model::fault` (the asserts are the harness's contract, not
a check the kernel relies on), `Model::fault_once`, `Model::raise` (a fault
with no endpoint, or with a dying one, is recorded and the thread suspended;
*fault no context* is not delivered to a passive receiver), `Model::record`,
`Model::answered` (a label other than 0 or 1, a short block, or a
non-canonical word leaves the thread suspended), `Model::thread_read_regs`
(`busy` unless suspended and not leaving), `Model::thread_write_regs` (the
canonical words, the breakpoint addresses below `user_end`, `dr7_valid`, and
the user-interrupt word `unsupported`; the order is the contract's step 3
before step 4), `Model::page_of`.

**`ipc.rs`** — `Message::check_header`, `Message::check` (the flags word, the
added-marks word, and the message page for more than `REG_WORDS` words, any
capability, or `add_marks`), `Message::rights` (`grant` is added exactly when
the message lists a capability), `notification`, `received`, `Parcel::new`,
`Model::call`, `Model::call_to`, `Model::enter`, `Model::recv`,
`Model::reply_recv`, `Model::send`, `Model::send_to`, `Model::signal`,
`Model::hand_over`, `Model::wait`, `Model::notify_bind`, `Model::listed` (a
slot listed twice, the depth of a capability to derive, and the rights
subset), `Model::receive`, `Model::serve`, `Model::answer`, `Model::has_page`,
`Model::deliver` (the list is resolved again at delivery against what the
sender's slots hold *then*; a range in a dying or destroyed space takes
nothing; the capability is dropped whole, with `FLAG_CAPS_DROPPED`, rather
than partly), `Model::receiver`, `Model::take_caller`, `Model::unlink`.

**`lib.rs`** — `runnable`, `object_at_start`, `enabled`, `woken`,
`longest_walk`, `object_at`, `member`, `role`, `stray_write`, `ownership`,
`untyped_marks`, `map_count`, `gate_word`, `device_leaves`, `page_class`,
`grant_entries`, `grant_entry`, `chunked_or_kept`, `core_list_fences`,
`device_count`, `device_entry`, `frame_at`, `translated`, `apply`, `made`
(the wait number is looked at only when the call waits, and a cancel ends
the wait with `cancelled` at once), `dispatch`, `dispatch_call`,
`addressed_space`, `bound_space` (a revoked task is `gone` from every call
including `cap_delete`), `through`, `full` (empty is `invalid`, dead is
`gone`, dying is `gone`, and an invalid remote capability is `gone` and
buried at the end of the call), `dying`, `cap`, `is` (kind before rights),
`held`, `object`, `optional`, `destination` (slot 0 and beyond the table are
`invalid`), `vacant` (see H3), `window` (`first == 0` or `end > slots.len()`
is `invalid` when a count is given; `first`/`count` are `u32`, so the sum
cannot wrap), `end_bounded`, `wake`.

**`locks.rs`** — `Model::pay`, `Model::wait_mark`, `Model::begin_locks`,
`Model::end_locks` (a node of one core returns before any `Cost::Lock` is
recorded; the gate lock appears only inside the node lock; a lock-free
`signal` that wakes no one takes no lock), `Measured::event_with_waits`,
`Measured::healthy_wait` (both saturating).

**`memory.rs`** — `hooked`, `tables`, `record_mapping`, `leaf_chunks`,
`leaf_target` (the first device entry that contains the frame — a split's
halves cannot shadow each other because the upper half's base is above the
lower's), `count_leaves` (the `+1`/`-1` of a partial mapping sum to the whole
record), `rehook`, `rehook_by` (see finding 1 for the caller's part),
`root_class`, `empty_mapping`, `clear_mapping`, `clear_mapping_pub`,
`finish_unmapping`, `freeze_unmapping` (a failed unit's counts are moved to
`frozen`/`frozen_entries` and never lowered), `begin_unmap`, `io_levels`,
`levels`, `class_of`, `extend_mapping`, `unmap`, `aspace_protect`,
`iospace_attach`, `detach`, `attaching`, `iommu_of`, `attach_answered`,
`set_root_class`, `detach_answered`, `attach_key`, `identifier_key`,
`holds_identifier`, `free_domain`, `detach_local`.

**`sched.rs`** — `Sched::bandwidth`, `Snap`, `EventKind`, `Parameters`,
`Model::now`, `running`, `running_on`, `core_count`, `advance`, `settle`,
`apply_settled`, `next_timer`, `timer_interrupt`, `begin_on`, `begin`,
`snap`, `observe`, `end`, `beat`, `reschedule_others`, `enabled_for`,
`choose` (each round takes one holder out of what can run, so the `unreachable!`
is not reachable), `no_context`, `context_of`, `runnable_thread`, `holder`,
`eligible`, `wanted`, `requeue` (the `assert!` on the change list is a fault
of the model, and the list is appended to under `observe` at every change),
`wake_up` (the comparison is done in `u128`, so `r * t` cannot wrap),
`exhaust`, `replenish`, `pick`, `request_due`, `hardware`, `due`,
`first_context`, `cores_set`, `in_set`, `own_node`, `sched_configure` (the
admission sum and the two `admits` are consistent with `Sched::bandwidth`
including its `pending`, so neither subtraction underflows; `bandwidth(0, 0)`
is 0 rather than a division by zero), `sched_bind`, `sched_unbind`,
`sched_set_cores`, `sched_read`, `sched_count`, `yield_now`, `lend`,
`release_lend`, `release_for_receive`, `sched_dying` (guarded by `retired`),
`timer_set` (`deadline < TIME_LIMIT` before `firing_instant`), `timer_cancel`,
`disarm`, `fire`, `timer_destroyed`, `clear_lend`, `disarm_one`,
`sched_destroyed`, `thread_unscheduled`.

**`table.rs`** — `RoleRecord`, `GrantState`, `Watched`, `Observation`,
`NodeBeacon`, `CoreBeacon`, `RingEntry`, `Ring::new`, `Ring::at`, `Ring::set`,
`RingPair`, `UnitState`, `IrqTableEntry`, `FenceRecord::begun`,
`FenceRecord::last_stop`, `FenceRecord::stopped`, `GrantEntry`, `UseEntry`,
`Word`, `WordWrite`, `Table::member`, `generation`, `core_word`, `holds_page`,
`cores_of`, `write_core` (refuses the reserved state *leaving*),
`start_request`, `started_node`, `writes`, `write_member`, `write_role`,
`gate_word`, `map_count`, `add_leaves` (a count that would go below 0 or past
`u32` panics rather than wrapping), `set_map_count`, `set_class` (the
chunk's `not_data` moves with the page's class in both directions),
`holds_reserve`, `may_take` (a member code beyond the machine is refused by
being read as a live owner of the word's generation), `journal`,
`begin_journal`, `write_owner` (compare-and-swap plus the writer's own member
word), `write_owner_cleared`, `write_entry`, `write_identifier`,
`attach_word`, `swap_attach`, `attached_to`, `line_word`, `write_line`.

**`tasks.rs`** — `marks`, `mark`, `aware`, `task` (a revoked task is `gone`
before its kind is judged, and an empty slot is still `invalid`),
`task_attach` (the marks of the task left move into the thread's own word and
then into the one joined), `detach_task`, `task_mark`, `task_exempt`,
`task_revoke` (the flag is written once; a marked thread is waited for; the
step detaches at most `REMOVAL_STEP`), `stop`, `task_read`, `detach_one`,
`next_task`.

**`threads.rs`** — `leave`, `thread_configure` (suspended, not waiting, not
leaving; the message page's record must be empty or already this thread's),
`message_page` (one page, index 0, ordinary memory, `read` and `write`),
`thread_resume`, `thread_suspend`, `thread_cancel` (the three bounded waits
and a hand-over are not ended), `thread_set_features` (`no_memory` when the
new mask needs more than the area the thread was made with), `bind_space`,
`bind_aspace`, `bind_fault`, `bind_page` (the old record is emptied before
the new one is written, so binding a thread to the page it already holds
leaves the record standing), `unbind_all`.

---

## What I did not examine

- I read the twelve files of my lot in full and nothing else in full. I read
  `abi/src/lib.rs`, `abi/src/machine.rs`, `model/src/table.rs`,
  `model/src/scenarios/mod.rs`, `model/src/scenarios/units.rs` and parts of
  `model/src/check.rs`, `model/src/check/table.rs`, `model/src/cores.rs`,
  `model/src/system.rs`, `model/src/boot.rs`, `model/src/scenarios/pass19.rs`
  and `pass20.rs` only as far as the twelve files led me. I did not review
  the other files of the pull request (`rings.rs`, `grants.rs`, `units.rs`,
  `roles.rs`, `nodes.rs`, `irq.rs`, `check/`, `boot.rs`, `system.rs`,
  `cores.rs`, `scenarios/`) — those are other lots.
- I did not run the crate's full test suite (`./verify`, or `cargo test -p
  dodos-model` without a filter), so I cannot say whether any other test is
  red at head `6312868`. I ran only the three tests of `v2b` (and, while
  working, single tests by name filter). The 523 other tests were compiled,
  not run.
- I did not attempt the ARM64 or RISC-V geometries, the 16 KB and 32 KB page
  geometries, or a `System` of more than three nodes for finding 1. Both
  instances are on x86-64 with 4 KB pages; the arithmetic is
  geometry-independent and `others_hold` short-circuits on ARM64
  (`model/src/cores.rs:273`), so the *TLB* instance of finding 1 is
  x86-64 and RISC-V only, while the iospace instance is not architecture
  dependent.
- I did not check H3 against the contract: `architecture/kernel-interface.md`
  is in the documentation repository, which the brief puts out of reach.
- I did not pursue two leads I could not turn into a test: whether a lend can
  be overwritten in `Sched::chain` (`lend` inserts into `self.lends` without
  clearing an older entry, which I argued is unreachable because every path
  that reaches `serve` for a reply object passes `release_for_receive`
  first); and whether `caps::next_removed`'s `assert!(walk <= 2 *
  LONGEST_WALK)` can be driven past its bound by a tree of depth 64.
  Neither is run.
