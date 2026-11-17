# Lot D, security review (v2-D-opus)

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
Every test below was written in a copy, `/private/tmp/dodos-pr3-v2-D-opus`,
and run there with
`nix develop -c cargo test -p dodos-model <filter> -- --nocapture`.
The probes are:

- `model/tests/v2d_probe.rs` (new file, finding 2);
- `model/src/check/tests.rs`, appended after the comment
  `// Lot D probes (v2-D-opus).` (findings 1, 3, 6);
- `model/src/scenarios/checker.rs`, appended after the same comment
  (findings 3, 4, 5).

All test names start with `v2d_`, so `cargo test -p dodos-model v2d`
runs them all. The original clone was not changed.

My lot is the checker of invariants and its tests. So most findings are
of the kind "a state the checker accepts and should not" or "the checker
panics where it should name an invariant". The checker is the oracle the
real kernel will be judged against: a hole in it lets a wrong kernel
pass.

---

## Finding 1. Invariant 52 accepts a take written in the name of another node

**Severity:** hardening (a hole in the oracle). The checker accepts a
write that hands a chunk to another node's current generation. No path
of the model was seen to make this write, but a kernel that made it
would pass.

**Attacker:** a kernel that is buggy or hostile, judged by the oracle.
Also any later reader of the word: the node named in the word without
having taken it.

**Where:** `model/src/check/table.rs:38-48`, `judge_write`, the case
`after_state == 2` (a take):

```rust
2 => {
    let allowed = match owner {
        o if o == writer => state == 1 || g != write.generation,
        0xFFFF => true,
        _ if reserve => write.holds,
        _ => write.owner.is_some_and(|m| {
            m.state() == dodos_abi::MemberState::Dead || state == 2 && m.generation() != g
        }),
    };
    let named = after_owner == writer || after_owner == owner;
    ensure_write(state != 0 && allowed && named && after_g == write.generation)
}
```

The comment above it says the rules of taking "give it to the writer".
But `named` also accepts `after_owner == owner`, the owner before the
write. The generation written is always the writer's
(`after_g == write.generation`). It is never the old owner's.

**Attack:**

1. Node 1 is live in generation 1. A chunk word reads *taken* by node 1
   with an older generation (5), which the rules let anyone take.
2. Node 0 (generation 1) writes *taken*, owner node 1, generation 1:
   its own generation, which happens to be node 1's current one.
3. Invariant 52 judges the write. `allowed` holds because node 1's word
   is of a generation that is over. `named` holds because
   `after_owner == owner`. `after_g` equals the writer's generation. The
   write is accepted.
4. The word now reads as owned by node 1's live generation. Node 1 never
   took the chunk: it is the authority of a chunk given to another party
   in that party's name.

The second probe shows the same with a word free and unclaimed: the
after word reads *taken by unclaimed* (owner `0xFFFF`) with the writer's
generation, and it is accepted.

The fix: `named` is `after_owner == writer`, or `after_owner == owner`
only when `owner` is a reserve that the writer holds.

**Proof:** `model/src/check/tests.rs`, tests
`v2d_take_in_the_name_of_the_old_owner_is_accepted` and
`v2d_take_in_the_name_of_unclaimed_is_accepted`. Each journals the write
the same way as the existing tests of invariant 52 (`table.journal`,
then `writes.push`) and asserts `check() == Ok(())`.

```
$ nix develop -c cargo test -p dodos-model --lib v2d -- --nocapture --test-threads=1
test check::tests::v2d_take_in_the_name_of_the_old_owner_is_accepted ... g0 1 g1 1 member1 Live
ok
test check::tests::v2d_take_in_the_name_of_unclaimed_is_accepted ... ok
```

Node 1 is `Live` with generation 1, and node 0's generation is 1. So the
accepted word reads "taken by node 1, generation 1": node 1's current
generation.

---

## Finding 2. `io_width` of the boot image is never checked; the checker and a user call panic

**Severity:** exploitable by a boot image with any values. The model
panics (debug build) on a user's `iospace_map`, and the checker panics
on any state that holds an iospace.

**Attacker:** the boot image (the `Machine` handed to `Model::boot`).
Then a user program, for the map.

**Where:** the start-up checks, `Machine::layout`
(`model/src/boot.rs:625` onward), refuse bad geometry, cores, nodes,
segments and floors. They never read `io_width` (`boot.rs:144`). It is
then used unchecked:

- `model/src/check/memory.rs:74`: `true => 1u128 << self.machine.io_width,`
- `model/src/check/memory.rs:110`:
  `let span = |k: u32| u128::from(geometry.page()) * u128::from(geometry.entries).pow(k);`
- `model/src/check/memory.rs:113`:
  `.find(|&k| span(k) >= 1u128 << self.machine.io_width)`
- `model/src/check/table.rs:470`:
  `let most = 2 * (self.levels(id) as usize).saturating_sub(1);`,
  which calls `io_levels` (`model/src/memory.rs:377`:
  `(width - page).div_ceil(geometry.entries.trailing_zeros())`)
- outside my lot, the system call path, `model/src/memory.rs:421`:
  `(1 << self.machine.io_width, io_mapping_rights(map.rights))`

**Attack:**

1. The boot image sets `io_width` to 8, 64, 125 or 130. `Model::boot`
   accepts all four.
2. The first process retypes an untyped into an iospace. This succeeds.
3. Width 130: the next `check()` panics at `check/memory.rs:113`, "shift
   left with overflow". Width 125: it panics at `check/memory.rs:110`
   (`u128::pow`), "multiply with overflow", because the first level
   whose span reaches 2^125 has a span past 2^128. Width 8: it panics
   at `memory.rs:377` ("subtract with overflow"), reached from
   `check/table.rs:470` (`check.rs:299`); the backtrace is below.
4. Width 64: an `IoSpaceMap` by the user panics at `memory.rs:421`.
   In a release build, `1 << 64` on `u64` masks the shift to `1 << 0`,
   so the limit becomes 1 byte and every map is refused. Width 8 in a
   release build wraps `io_levels` to about 2^32 levels.

The fix: refuse at start-up an `io_width` outside
[page shift + log2 *E*, 64] (or the widths the units really have:
39, 48, 57). Then the checker can keep `1u128 <<`.

**Proof:** `model/tests/v2d_probe.rs`, four tests.

```
$ nix develop -c cargo test -p dodos-model --test v2d_probe -- --nocapture --test-threads=1
test v2d_checker_on_io_width_125 ... retype: Ok(Done)
thread 'v2d_checker_on_io_width_125' panicked at model/src/check/memory.rs:110:33:
attempt to multiply with overflow
check: Err(Any { .. })
ok
test v2d_checker_on_io_width_130 ... retype: Ok(Done)
thread 'v2d_checker_on_io_width_130' panicked at model/src/check/memory.rs:113:43:
attempt to shift left with overflow
check: Err(Any { .. })
ok
test v2d_map_on_io_width_64 ...
thread 'v2d_map_on_io_width_64' panicked at model/src/memory.rs:421:18:
attempt to shift left with overflow
map with width 64: Err(Any { .. })
ok
```

and, with `env RUST_BACKTRACE=1`, for width 8:

```
retype with width 8: Ok(Done)
thread 'v2d_io_width_below_page' panicked at model/src/memory.rs:377:5:
             at ./src/memory.rs:377:5
             at ./src/memory.rs:387:21
             at ./src/check/table.rs:470:34
             at ./src/check.rs:299:14
check: Err(Any { .. })
test result: ok. 1 passed
```

---

## Finding 3. A debug area left by a dead generation is adopted; its sequences panic the writer and the checker

**Severity:** exploitable. The full chain was run: a hostile
generation writes its own core's debug area, dies, and the slot starts
fresh on that core. The two checker panics are also proved directly.

**Attacker:** a hostile kernel of one node, which writes anything into
its own memory, here the debug areas of its cores. Its victim is the
next generation of the node on those cores, and the checker.

**Where:**

- `model/src/debug.rs:262-276`, `enter_debug_areas`, outside my lot:
  a core that starts keeps the area when magic and version are right,
  "and goes on from the next sequences found there":
  ```rust
  if area.magic != DEBUG_AREA_MAGIC || area.version != DEBUG_AREA_VERSION {
      *area = DebugArea::new(generation);
  }
  (area.generation, area.slot) = (generation, self.node);
  ```
  `next_kernel` and `next_user` are not checked.
- `model/src/debug.rs:91-94`, `write`: `let seq = *next; ... *next = seq + 1;`
- `model/src/check/debug.rs:16-25`, `ring_holds`, in my lot:
  ```rust
  let placed = ring.iter().enumerate().all(|(index, entry)| {
      entry.seq == 0
          || (entry.seq < next
              && entry.seq + entries >= next
              && (entry.seq - 1) % entries == index as u64)
  });
  let last = next == 1 || ring[((next - 2) % entries) as usize].seq == next - 1;
  next >= 1 && placed && last
  ```
  The guard `next >= 1` is read last, after `next - 2` has been
  computed. `entry.seq + entries` overflows for a sequence within N of
  `u64::MAX`.

**Attack:**

1. The hostile kernel of node 1 writes, in the debug area of its core,
   `next_kernel = u64::MAX` (or 0), and keeps magic and version.
2. Node 1 is killed, fenced, reclaimed and dead. A fresh start puts
   generation 2 on the same core.
3. `enter_debug_areas` keeps the area and its sequences. The new
   kernel's first trace entry computes `seq + 1` on `u64::MAX`: a panic
   in a debug build, a wrap to 0 in a release build. After the wrap,
   `trace_index(0)` underflows.
4. With `next = 0` already in the area, `check()` panics in
   `ring_holds` instead of reporting "88: kernel ring".

The fix: `enter_debug_areas` also clears an area whose next sequences
are 0, or whose entries contradict them (exactly what `ring_holds`
checks). `ring_holds` tests `next >= 1` first and uses `checked_add`.

**Proof:** in `model/src/check/tests.rs`,
`v2d_ring_next_zero_panics_the_checker` and
`v2d_ring_next_max_panics_the_checker_and_the_writer`:

```
test check::tests::v2d_ring_next_max_panics_the_checker_and_the_writer ...
thread '...' panicked at model/src/check/debug.rs:20:20:
check: Err(Any { .. })
thread '...' panicked at model/src/debug.rs:94:17:
write: Err(Any { .. })
test check::tests::v2d_ring_next_zero_panics_the_checker ...
thread '...' panicked at model/src/check/debug.rs:23:35:
Err(Any { .. })
```

The whole chain is `v2d_a_fresh_start_adopts_the_sequences_a_dead_generation_left`
in `model/src/scenarios/checker.rs`, run, passes:

```
$ nix develop -c env RUST_BACKTRACE=1 cargo test -p dodos-model --lib v2d_a_fresh -- --nocapture
thread 'scenarios::checker::v2d_a_fresh_start_adopts_the_sequences_a_dead_generation_left' panicked at model/src/debug.rs:94:17:
             at ./src/debug.rs:94:17
             at ./src/boot.rs:1344:14
             at ./src/boot.rs:1086:28
             at ./src/system.rs:805:17
             ...
after the fresh start: Err(Any { .. })
```

`boot.rs:1342-1344` is `self.enter_debug_areas();` and then the first
trace entry of the start (`self.trace(TraceCode::Text, ...)`). So the
fresh start of generation 2 panics on the sequence that generation 1
left. The test sets the area after node 1 is dead (`edit_table` on core
1's area), which stands for the last write of the hostile generation.
This chain was run, so I grade the finding **exploitable** in the
model: a hostile generation makes every later fresh start of its slot
on that core fail (debug build), or wrap its ring (release build).

---

## Finding 4. A remote root capability may hold any rights; a frame granted read-only can be mapped writable unseen

**Severity:** hardening (a hole in the oracle: an authority beyond its
grant that no invariant covers).

**Attacker:** a holder node's kernel that is buggy, or a user program
of the holder if the holder's kernel widened the rights at receipt.

**Where:**

- `model/src/check.rs:438-449`, invariant 3:
  ```rust
  // A root remote capability has the rights of its anchor.
  let remote = self.remotes.contains_key(&cap.object);
  let rights = remote || if kept { row } else { every };
  ```
  The comment states a rule; the code accepts every set of rights.
  `Remote` (`model/src/grants.rs:21-28`) does not even keep the
  anchor's rights, so no check can compare them. `System::check`
  (`check/machine.rs`) does not compare them with the anchor on the
  granter either.
- `model/src/check/table.rs:261-268`, invariant 58: a translation to a
  remote frame `continue`s before the rights test at lines 403-407
  (`writable || read_only`). So nothing judges the rights of a mapping
  of granted memory.

**Attack:**

1. Node 0 grants a frame to node 1 with `read` only (`NodeSend`,
   `Transfer::Derive(frame, READ)`).
2. On node 1, the root remote capability ends up with
   `read | write | derive`. In the test I write this directly, as a
   wrong kernel would.
3. `System::check` accepts the state.
4. Node 1's user maps the frame read-write. The call succeeds, the
   check after it passes, and node 1 translates node 0's frame writable.

The fix: keep the anchor's rights in `Remote` (they are in `Granted`),
check root remote rights equal them (invariant 3), and judge
`rights ⊆ granted rights` for remote translations in 58.

**Proof:** `model/src/scenarios/checker.rs`,
`v2d_a_writable_mapping_of_a_frame_granted_read_only_is_not_reported`,
run, passes:

```
test scenarios::checker::v2d_a_writable_mapping_of_a_frame_granted_read_only_is_not_reported ... rights granted: Rights(1)
translation on node 1: Some(Rights(3))
ok
```

The grant carried `READ` (1). After the spoiled rights, `System::check`
returned `Ok(())`. The read-write map succeeded, `S::ok` checked the
machine after it, and node 1 translates the frame with `READ | WRITE`
(3).

---

## Finding 5. G4 for device entries is only "at least"; an over-counted entry is never reported on a machine

**Severity:** hardening. No invariant covers a leaked count. A device
entry whose leaf count stays above its leaves never returns to its pool:
a resource one party exhausts for others.

**Where:**

- `model/src/check/machine.rs:149-154`:
  ```rust
  for (entry, &held) in entries.iter().enumerate() {
      ensure(
          held <= table.device_leaves[entry],
          "G4: a leaf count below its leaves",
      )?;
  }
  ```
- `model/src/check/table.rs:420-428`: on a node that shares its table
  (`shared == true`, every node of a `System`), the node's check also
  only asks `l <= m`.

The chunk counts just above (`machine.rs:139-146`) require equality
while the owner runs (`alive`). The device entries have no such
refinement, though `entry_leaves` already includes the leaves a failed
unit keeps for ever (`frozen_entries`, `table.rs:212-216`).

**Attack:**

1. A kernel on a machine of two nodes leaves a device entry's leaf count
   one or more above the leaves that target it (for example, an unmap
   that does not decrement).
2. `System::check` accepts it after every step, for ever. The entry can
   never be freed or given.

The fix: require equality for an entry whose owner runs, as for chunks.

**Proof:** `model/src/scenarios/checker.rs`,
`v2d_a_device_leaf_count_above_its_leaves_is_not_reported`: it adds 5 to
`device_leaves[0]` on `S::two()` and asserts `sys.check() == Ok(())`.

```
test scenarios::checker::v2d_a_device_leaf_count_above_its_leaves_is_not_reported ... device entries: 8196
ok
```

The message "G4: a leaf count below its leaves" itself is made to fail
by no test; see finding 7.

---

## Finding 6. The checker panics on bad states instead of naming the invariant

**Severity:** hardening. The checker is fed only states the model makes,
but its purpose is to name what is wrong. A panic hides which invariant
broke, and a harness that catches panics loses the report.

- `model/src/check/sched.rs:40`:
  `let runs = |thread: &ObjId| Self::runnable_thread(&self.threads[thread]);`
  It is called at line 50 on `holder`, which can be the receiver of the
  top lend (line 48). The receiver's existence is checked only at line
  120 (invariant 44), which runs later. A lend to a destroyed thread
  panics.
  **Proof:** `v2d_lend_to_a_missing_receiver_panics_the_checker`:
  `panicked at model/src/check/sched.rs:40:72` (run, passes).
- `model/src/check/debug.rs:23`, `next - 2` before `next >= 1`, and
  `:20`, `entry.seq + entries`: see finding 3 (run).
- `model/src/check/memory.rs:74, 110, 113` and `check/table.rs:470`:
  see finding 2 (run).
- Not run: `check/debug.rs:57`, `self.table.crash.areas[core.number as usize]`;
  `check/table.rs:321`, `table.owners[chunk as usize]` for a block past
  the table; `check/debug.rs:169`, `regs[REG_DR0..=REG_DR3]` for a
  register block shorter than `REGS_WORDS`. Each indexes with a value of
  the state before any check of its range.

---

## Finding 7. Checker messages that no test makes fail, and one checker test that is vacuous

**Severity:** hardening (the tests).

These messages appear in no test (searched in `src/check/tests.rs`,
`src/scenarios/` and `tests/`):

```
18: a watermark ready to return under a live object
35: page size
35: record of a frame
54: block of no entry
58: frame
58: page size
88: an attach word with no identifier word or root beside it
G4: a leaf count below its leaves
TLB: a barrier that invalidates, or an invalidation that is a barrier
TLB: the state word of a request
credits: more sends than SENDS_PER_PEER
epoch: a barrier beyond the kernel epoch
epoch: raised by more than one at a time
epoch: the node's epoch is not its last raise
epoch: word 6 of an untyped's root slot is not the epoch its watermark became ready at
```

Mutation: I disabled five of them together and ran the whole model
suite. The five were the 88 attach check (`check.rs:342-345`), G4 device
`held <=` (`machine.rs:151`), `sends <= SENDS_PER_PEER` (`node.rs:359`),
the request state word (`node.rs:162`), and the epoch of word 6
(`node.rs:339`). Result: every suite passed.

```
$ nix develop -c cargo test -p dodos-model 2>&1 | grep -E "test result|FAILED|^error|Running"
     Running unittests src/lib.rs ...
test result: ok. 529 passed; 0 failed; ...
     Running tests/blocks.rs ...
test result: ok. 14 passed; 0 failed; ...
...
     Running tests/property.rs ...
test result: ok. 15 passed; 0 failed; ...
...
```

That is 19 test binaries, every one `ok`, 1155 tests passed in all, none
failed. The count includes 10 of my own probes (6 in the library, 4 in
`tests/v2d_probe.rs`), which touch none of the five checks. So none of the five checks is guarded by a test. That breaks the
rule of `dodos-rust`, "a test fails without the code it guards". The
five edits were then undone.

`model/src/scenarios/checker.rs`,
`a_grant_freed_while_its_holder_translates_to_it_is_reported`, accepts
`report.ends_with("G6: ...") || report.contains("58")`, so it passes
without G6. I replaced
`ensure(held, "G6: a grant freed while its holder translates to it")`
(`machine.rs:177`) with `ensure(true || held, ...)`:

```
test scenarios::checker::a_grant_freed_while_its_holder_translates_to_it_is_reported ... ok
test scenarios::pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6 ... FAILED
```

So G6 is guarded by `pass18`, but the checker's own test of G6 is
vacuous. It also ends with a dead `let _ = Member::new;`.

`model/src/scenarios/explore.rs:31-39` and `:174-183`: a `DODOS_SEED`
that does not parse falls back to all 24 seeds, but `reached` still sees
the variable set and skips every coverage assertion. A typo silently
runs the explorations without their floors. Not run.

---

## Notes (not findings)

- `check.rs:308-314` says of invariant 88: "names a root of class
  48 + n with n at least the words that name it". The code
  (`check.rs:339-345`) only asks n ≠ 0. For a root of one of this node's
  spaces, 59 (`check/table.rs:448-454`) asks n to be exactly
  `attached_to(root)`, so the gap is only for a root no space of this
  node holds. Not probed further.
- `check/tasks.rs:55`: `ensure(true, "50: running thread of a revoked task")`
  is dead code.
- `check/node.rs:134-141`, G5: a stale kernel translation is accepted
  for any chunk whose word reads taken by this node in any generation
  (`mine` does not read the generation). With 57 this covers only the
  window of a `Completes::Run` request. Not probed.
- `check/machine.rs:282`, `in_ring`: the range `start..ring.produced`
  is empty when `produced` wrapped past `u64::MAX`; unreachable in
  practice (2^64 messages).

---

## Functions examined and found sound (apart from the above)

`check.rs`: `ensure`, `depths`, `marked`, `census`, `written_block`,
`check` (its order), `check_lines`, `check_tree` (apart from finding 4),
`check_removal` (the topological sort ends and counts every capability),
`check_slots`, `check_objects`, `check_waits` (14: queue entries plus 12
and 13 make every queued thread wait on its queue; bounded waits cannot
sit in a queue), `check_memory`, `check_bindings`; `check_identifiers`
apart from the note.
`check/cores.rs`: `check_cores`.
`check/debug.rs`: `check_area` 89-91 (window rebuild), `check_records`.
`check/machine.rs`: `check`, `check_cores` (P2, P3, the fence),
`check_counts` for chunks, `check_grants`, `check_rings`, `check_units`,
`in_ring`, `check_fence_order`, `check_reserve`, `released`, `served`,
`running_node`, `has_generation`, `peers_of`, `peers_sending`, `serves`.
`check/memory.rs`: `check_spaces` (35-38; address arithmetic done after
the bound in u128), `check_devices`.
`check/node.rs`: `check_window`, `check_crossing`, `check_tlb`,
`check_requests`, `check_marks`, `check_locks`, `check_epoch`,
`check_credits`.
`check/sched.rs`: `check_sched` (apart from line 40), `check_choice`,
`check_timers`, `check_events`.
`check/table.rs`: `read`; `judge_write` for releases (state 1);
`chunk_leaves`, `entry_leaves`, `leaves_by_target`; `check_table` 53-57
and 59.
`check/tasks.rs`: `check_tasks`, `check_irqs`.
`scenarios/mod.rs`: the helpers `N` and `S` check after every call and
step.
`scenarios/checker.rs`: each test asserts the exact message, except the
G6 one (finding 7).

## Not examined, or only skimmed

- `check/tests.rs` (2825 lines): skimmed. Its tests use `spoiled` with
  exact messages, and I searched it for weak assertions (`is_err`,
  `contains`); none found. I did not read every test.
- `scenarios/explore.rs`: read the helpers and the coverage mechanism,
  not every exploration body line by line.
- The files outside my lot that my findings touch (`boot.rs`,
  `memory.rs`, `debug.rs`, `grants.rs`): read only as far as each
  finding needed.
