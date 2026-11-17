# Security Review Report: Lot B

Repository reviewed: `/private/tmp/dodos-pr3-final` (branch `model`, commit `6312868`).
Proof-of-concept tests were added only in the working copy `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs` without modifying `/private/tmp/dodos-pr3-final`.

## Findings

### Finding 1: A node holding a reserve role can take the same reserve memory chunk twice

- **Severity**: `exploitable`
- **Attacker**: A user program holding `memory_control` on a node that claims a `Reserve` role.
- **Location**:
  - `model/src/blocks.rs:83`:
```rust
            if self.taken_here(word) || !self.table.may_take(word, self.node) {
                return Err(Error::Busy);
            }
```
  - `model/src/blocks.rs:161-172`:
```rust
    fn taken_here(&self, word: Ownership) -> bool {
        if word.state() != OwnState::Taken {
            return false;
        }
        match word.owner() {
            Owner::Node(owner) => {
                owner == self.node && word.generation() == self.table.generation(self.node)
            }
            Owner::Reserve(_) => false,
            Owner::Unclaimed => false,
        }
    }
```
  - Related ABI rule in `abi/src/machine.rs:619` (`Ownership::may_take`) and invariant in `model/src/check/table.rs:42` (`judge_write`): `Ownership::may_take` returns `holds_reserve` for `Owner::Reserve(_)` even when `word.state() == OwnState::Taken` and `word.generation() == generation`.
- **Attack**:
  1. The node claims a `Reserve(j)` role with `Syscall::RoleClaim`, so `table.holds_reserve(self.node, j)` is `true`.
  2. A user thread calls `Syscall::MemoryTake` (`kind = 0`) on a chunk whose ownership word has `Owner::Reserve(j)` (`OwnState::Free`). `memory_take` sets the word to `Ownership::taken(Owner::Reserve(j), generation)` and creates a live `Untyped` block capability at destination slot 160.
  3. The user thread calls `Syscall::MemoryTake` a second time on the same `place` and `size`, targeting slot 161.
  4. `taken_here` sees `Owner::Reserve(j)` and returns `false`, and `may_take` returns `true` because `holds_reserve` is `true` regardless of `OwnState::Taken`. `memory_take` creates a second live `Untyped` block capability covering the exact same physical chunk, violating invariant 53 (`53: two blocks on a chunk`), and lines 109–119 reset `map_count` to `0` and clear all `table.classes` on the chunk while objects from the first block still exist.
- **Proof**:
  - Test `scenarios::units::poc_blocks_1_reserve_chunk_can_be_taken_twice` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
    `test scenarios::units::poc_blocks_1_reserve_chunk_can_be_taken_twice ... ok`

---

### Finding 2: `memory_split` omits the `mapped_block` check and splits blocks with frozen IOMMU leaves

- **Severity**: `exploitable`
- **Attacker**: A user program holding `memory_control` and a device-memory `Untyped` block capability.
- **Location**: `model/src/blocks.rs:280-298`:
```rust
    pub(crate) fn memory_split(
        &mut self,
        thread: ObjId,
        control: SlotAddr,
        untyped: SlotAddr,
    ) -> Outcome {
        self.control(thread, control)?;
        let (cap, object) = self.block(thread, untyped)?;
        let Some(Block::Entry(index)) = self.untypeds[&object].block else {
            return Err(Error::Invalid);
        };
        let page = self.page().trailing_zeros();
        let entry = self.table.devices[index];
        if entry.log2() <= page {
            return Err(Error::Invalid);
        }
        self.idle_block(cap, object)?;
        self.return_watermark(object)?;
```
  (Compare with `model/src/blocks.rs:213`, where `memory_give` checks `if self.mapped_block(object) { return Err(Error::Busy); }`, and `model/src/caps.rs:960`, where block destruction checks `mapped_block`.)
- **Attack**:
  1. A user thread takes a multi-page device entry with `Syscall::MemoryTake`, retypes a `Frame` from it, and maps that frame into an attached `IoSpace` with `Syscall::IoSpaceMap`, incrementing `table.device_leaves[index]`.
  2. The IOMMU unit stops answering (`unit.broken = true` or a timeout occurs). The thread calls `Syscall::IoSpaceUnmap`, which returns `Err(Error::Busy)` and freezes the leaf count (`device_leaves[index] > 0`, `frozen_entries[index] == 1`).
  3. The thread deletes the `Frame` capability with `Syscall::CapDelete` so the untyped block has no children (`untyped.live == 0`). `Syscall::MemoryGive` properly refuses with `Err(Error::Busy)` because `mapped_block(object)` is `true`.
  4. The thread calls `Syscall::MemorySplit` on the device block. Because `memory_split` does not check `mapped_block(object)`, it splits the device entry into two free entries owned by the node and destroys the block capability.
  5. The thread calls `Syscall::MemoryTake` on the lower half entry. Line 126 resets `table.device_leaves[index] = 0` while `frozen_entries[index]` is still `1`, breaking invariant 58 (`58: map count`) and allowing `Syscall::MemoryGive` of the halves to another node while the failed IOMMU still retains DMA access to that memory.
- **Proof**:
  - Test `scenarios::units::poc_blocks_2_memory_split_splits_device_with_frozen_leaves` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
    `test scenarios::units::poc_blocks_2_memory_split_splits_device_with_frozen_leaves ... ok`

---

### Finding 3: Destroying a pinned `IoSpace` releases its root and table pages back to its parent `Untyped`

- **Severity**: `exploitable`
- **Attacker**: A user program that owns an `IoSpace` attached to a device whose IOMMU unit fails or refuses detach.
- **Location**: `model/src/caps.rs:1142-1161` and `1193-1195`:
```rust
            ObjectKind::ASpace | ObjectKind::IoSpace => {
                let space = self.aspaces.remove(&id).expect("names a live entry");
                self.iospaces.remove(&id);
                self.domains.remove(&id);
                // G2: the gate turns the table pages back into data, only
                // once the root's count of devices is 0; a detach answered
                // *failed* leaves the attach word *attached*, and the pages
                // keep their class until the machine restarts (D-137).
                let page = self.machine.geometry.page();
                let pinned = space.root.is_some_and(|r| self.table.attached_to(r) > 0);
                for at in space.table_pages().filter(|_| !pinned) {
                    self.table.set_class(at / page, None);
                }
                for untyped in object
                    .from
                    .iter()
                    .flat_map(|from| [*from].repeat(space.tables as usize))
                {
                    self.release(untyped);
                }
            }
```
  and:
```rust
        if let Some(untyped) = object.from {
            self.release(untyped);
        }
```
- **Attack**:
  1. A user thread creates a child `Untyped`, retypes an `IoSpace` from it, and attaches a device to that `IoSpace` via `Syscall::IoSpaceAttach`.
  2. The IOMMU unit stops confirming (or refuses detach). The user thread deletes the `IoSpace` capability with `Syscall::CapDelete`.
  3. During `IoSpace` destruction, `attached_to(r) > 0` (`pinned == true`), so lines 1152–1154 preserve `PageClass::iospace_root(1)` on the physical root page (and any table page classes). However, lines 1155–1161 and 1193–1195 still call `self.release(untyped)`, returning `untyped.live` to `0`.
  4. Because `untyped.live == 0`, the user thread can immediately call `Syscall::UntypedRetype` (calling `return_watermark`) to reallocate the exact same pinned physical root page as a new `ASpace` (overwriting `PageClass::iospace_root(1)` with `PageClass::table(4)` and breaking invariant `88: an attach word with no identifier word or root beside it`), or as a `Frame` / `Thread` / `CSpace`, or return the backing block to another node via `Syscall::MemoryGive` while the device remains `AttachState::Attached` to that physical root page.
- **Proof**:
  - Test `scenarios::units::poc_caps_1_pinned_iospace_released_to_untyped` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
    `test scenarios::units::poc_caps_1_pinned_iospace_released_to_untyped ... ok`

---

### Finding 4: Failed explicit detach drops a device from `iospaces` and `domains` while `AttachWord` stays `Attached`, bypassing `IoSpaceUnmap` freeze and freeing the domain ID

- **Severity**: `exploitable`
- **Attacker**: A user program issuing `IoSpaceAttach` with `SlotAddr::NONE` when an IOMMU unit fails, or a hostile kernel holding the IOMMU role returning `UnitResult::Failed`.
- **Location**:
  - `model/src/memory.rs:1063-1068`:
```rust
        let refused = result == dodos_abi::UnitResult::Done
            && word.state() == Some(dodos_abi::AttachState::Attached)
            && waiter != crate::units::Waiter::Step;
        if !refused {
            self.detach_local(iommu, device);
        }
```
  - `model/src/memory.rs:1116-1128`:
```rust
    fn detach_local(&mut self, iommu: ObjId, device: u16) -> u16 {
        let unit = live(&mut self.iommus, iommu);
        unit.order.retain(|&other| other != device);
        unit.detaching.remove(&device);
        let iospace = unit.attached.remove(&device);
        let iospace = iospace.expect("the device is attached");
        live(&mut self.iospaces, iospace).retain(|&found| found != (iommu, device));
        let domain = self.domains.get(&iospace).copied().unwrap_or(0);
        if self.iospaces[&iospace].is_empty() {
            self.domains.remove(&iospace);
        }
        domain
    }
```
  - `model/src/memory.rs:677-689` (`unmap`) and `model/src/memory.rs:321-325` (`begin_unmap`): both check `self.iospaces.get(&space).and_then(|s| s.first())` to detect whether an `IoSpace` still serves devices and whether its IOMMU unit has failed.
- **Attack**:
  1. A user thread attaches a device to an `IoSpace` and maps a `Frame` into that `IoSpace` with `Syscall::IoSpaceMap`, incrementing `map_count` on the frame's chunk.
  2. The thread calls `Syscall::IoSpaceAttach` with `iospace = SlotAddr::NONE` to detach the device.
  3. The IOMMU unit fails (`UnitResult::Failed`, e.g., timeout or a hostile IOMMU role holder answering `Failed`).
  4. In `detach_answered`, `word.state()` is still `AttachState::Attached(root)`, but because `result != UnitResult::Done`, `refused` evaluates to `false`. `detach_answered` calls `detach_local(iommu, device)`, removing `(iommu, device)` from `iommus[iommu].attached`, emptying `iospaces[iospace]`, and calling `self.domains.remove(&iospace)`.
  5. When the user thread next calls `Syscall::IoSpaceUnmap` on the mapped frame, `unmap` and `begin_unmap` inspect `self.iospaces.get(&space).and_then(|s| s.first())`, see `None`, skip `freeze_unmapping` and invalidation, return `Ok(Output::Done)` instead of `Err(Error::Busy)`, and decrement `map_count` back to `0`.
  6. The user can now delete the frame, retype the physical memory for another purpose, or give the block to another node via `Syscall::MemoryGive` while the device remains `AttachState::Attached(root)` to that `IoSpace` page table. Furthermore, if triggered by a hostile IOMMU holder injecting `UnitResult::Failed` (leaving `unit_failed` `false`), `self.domains.remove(&iospace)` frees that hardware domain number for reuse on another `IoSpace` while the old device is still attached to that domain.
- **Proof**:
  - Test `scenarios::units::poc_memory_1_failed_detach_drops_iospace_device_and_unmaps_without_freeze` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
    `test scenarios::units::poc_memory_1_failed_detach_drops_iospace_device_and_unmaps_without_freeze ... ok`

---

### Finding 5: `message_page` lets a thread bind a remote granted `Frame` without counting in `UseEntry::leaves`, surviving grant revocation

- **Severity**: `exploitable`
- **Attacker**: A user program on a grantee node receiving a `Frame` capability via `NodeSend`, together with a granter node deleting or revoking that `Frame` and reusing its physical page.
- **Location**:
  - `model/src/threads.rs:69-82`:
```rust
    fn message_page(&self, thread: ObjId, at: SlotAddr) -> Result<CapId, Error> {
        let cap = self.cap(thread, at, Rights::READ)?;
        let object = self.caps[&cap].object;
        let one_page = self.frames.get(&object).is_some_and(|frame| {
            frame.page == PageSize::Page
                && frame.pages == 1
                && frame.memory == MemoryType::WriteBack
        });
        if self.objects[&object].kind == ObjectKind::Frame && !one_page {
            return Err(Error::Invalid);
        }
        self.is(cap, ObjectKind::Frame, Rights::READ.union(Rights::WRITE))?;
        Ok(cap)
    }
```
  - Interaction with `model/src/grants.rs:653-666` (`revoke_anchor`): `revoke_anchor` checks `u.leaves == 0` and immediately calls `self.free_grant(grant)` without sending `Body::Revoke` to the grantee node when `leaves == 0`.
- **Attack**:
  1. Node 0 derives a 1-page `WriteBack` `Frame` with `READ | WRITE` and grants it to node 1 via `Syscall::NodeSend`.
  2. Node 1 creates a new thread and calls `Syscall::ThreadConfigure` passing the received remote frame slot as `page`.
  3. `message_page` does not reject `self.remotes.contains_key(&object)` and `bind_page` sets `Record::Binding(target)` without incrementing `table.uses[grantee][use_entry].leaves` (which stays `0`).
  4. Node 0 deletes or revokes the parent frame capability via `Syscall::CapDelete`. `revoke_anchor` reads `leaves == 0`, frees node 0's grant entry immediately without sending `Body::Revoke` to node 1, and lets node 0 retype the same physical page (for instance into an `ASpace` page table root).
  5. Node 1's thread continues to hold `thread.page = Some(remote_cap)` bound to that physical page (even passing `System::check()`), allowing node 1's kernel to read and write IPC message words into a physical page now owned and reused by node 0.
- **Proof**:
  - Test `scenarios::units::poc_threads_1_remote_message_page_survives_grant_revocation` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
    `test scenarios::units::poc_threads_1_remote_message_page_survives_grant_revocation ... ok`

---

### Finding 6: `Model::depth` panics with subtraction underflow when a hostile kernel grants a capability with `depth == 0`

- **Severity**: `hardening`
- **Attacker**: A hostile kernel sending a forged `Body::Send` message with `Granted { depth: 0, .. }` (alongside a matching `GrantEntry` in its own `grants` table) to a receiver node whose user thread subsequently derives or moves that capability.
- **Location**: `model/src/caps.rs:380-389`:
```rust
    pub(crate) fn depth(&self, cap: CapId) -> usize {
        let chain: Vec<CapId> =
            std::iter::successors(Some(cap), |cap| self.caps.get(cap)?.parent).collect();
        // Grants: a root remote capability has the depth of its anchor.
        let top = chain.last().and_then(|top| self.caps.get(top));
        let offset = top
            .and_then(|top| self.remotes.get(&top.object))
            .map_or(0, |remote| remote.depth - 1);
        chain.len() + offset
    }
```
  (Neither `rings.rs::refused` nor `grants.rs::place_remote` validates that `granted.depth` lies in `1..=TREE_DEPTH`; note also `chain.len() + offset` can overflow if `granted.depth == usize::MAX`.)
- **Attack**:
  1. Node 1 waits on `Syscall::Recv` at its mailbox endpoint.
  2. A hostile kernel on node 0 records a matching `GrantEntry` in its own `table.grants[0]` and writes a `Body::Send` ring message containing `Granted { grant: 0, serial: 1, rights: READ | DERIVE, depth: 0, .. }`.
  3. Node 1 delivers the remote capability with `remote.depth = 0`.
  4. When node 1 calls `Syscall::CapDerive` (or `CapMove` / `NodeSend` / `UntypedRetype`) on that slot, `fits` invokes `self.depth(source)`, which evaluates `remote.depth - 1` (`0usize - 1`) and panics.
- **Proof**:
  - Test `scenarios::units::poc_caps_2_remote_depth_zero_panics_in_depth` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
```text
thread 'scenarios::units::poc_caps_2_remote_depth_zero_panics_in_depth' (13146955) panicked at model/src/caps.rs:387:33:
attempt to subtract with overflow
test scenarios::units::poc_caps_2_remote_depth_zero_panics_in_depth - should panic ... ok
```

---

### Finding 7: `CrashArea::new` panics on `u64` overflow when `previous_crash.sequence == u64::MAX`

- **Severity**: `hardening`
- **Attacker**: A boot image supplying `previous_crash` with `sequence == u64::MAX`.
- **Location**: `model/src/debug.rs:102-109`:
```rust
    pub(crate) fn new(boot_id: u64, previous: u64, cores: usize) -> Self {
        Self {
            boot_id,
            sequence: previous + 1,
            stop: None,
            areas: (0..cores).map(|_| DebugArea::new(1)).collect(),
        }
    }
```
  (Called from `model/src/boot.rs:962` with `previous.sequence` directly from `machine.previous_crash` without validation.)
- **Attack**:
  1. Construct a `Machine` whose `previous_crash` field has `sequence == u64::MAX` (for example `CrashArea::new(1, u64::MAX - 1, 1)`).
  2. Call `Model::boot(&machine)`.
  3. `CrashArea::new` evaluates `previous + 1` and panics on `u64` addition overflow instead of saturating or rejecting the boot image.
- **Proof**:
  - Test `scenarios::units::poc_debug_1_previous_crash_max_sequence_panics_on_boot` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
```text
thread 'scenarios::units::poc_debug_1_previous_crash_max_sequence_panics_on_boot' (13146956) panicked at model/src/debug.rs:105:23:
attempt to add with overflow
test scenarios::units::poc_debug_1_previous_crash_max_sequence_panics_on_boot - should panic ... ok
```

---

### Finding 8: `enter_debug_areas` preserves a core's `next_kernel`/`next_user` counters without validating `>= 1` or overflow bounds

- **Severity**: `hardening`
- **Attacker**: A hostile kernel that previously owned a physical core before that core joins or resumes an honest node.
- **Location**:
  - `model/src/debug.rs:262-276`:
```rust
    pub(crate) fn enter_debug_areas(&mut self) {
        let generation = self.table.generation(self.node);
        for core in self
            .cores
            .iter()
            .map(|c| c.number as usize)
            .collect::<Vec<_>>()
        {
            let area = &mut std::sync::Arc::make_mut(&mut self.table.crash).areas[core];
            if area.magic != DEBUG_AREA_MAGIC || area.version != DEBUG_AREA_VERSION {
                *area = DebugArea::new(generation);
            }
            (area.generation, area.slot) = (generation, self.node);
        }
    }
```
  - `model/src/debug.rs:82-95` (`DebugArea::write`):
```rust
        let seq = *next;
        entry.seq = seq;
        ring[trace_index(seq, entries) as usize] = entry;
        *next = seq + 1;
```
- **Attack**:
  1. A hostile kernel runs on physical core `c`, leaves `area.magic == DEBUG_AREA_MAGIC` and `area.version == DEBUG_AREA_VERSION` intact, and sets `area.next_kernel = 0` (or `u64::MAX`), or sets `area.next_user = 0` (or `u64::MAX`), in core `c`'s debug area.
  2. When core `c` is transferred to an honest node that starts (`boot.rs:1342`) or resumes, `enter_debug_areas` sees valid `magic` and `version` and does not reset `area`.
  3. On the very next line (`boot.rs:1344`), `self.trace(TraceCode::Text, ...)` calls `DebugArea::write`, which calls `abi::debug::trace_index(0, ...)` (`(seq - 1) % entries`) and panics on subtraction underflow (or panics on `seq + 1` overflow if `next == u64::MAX`). Even if `next_kernel` is `1` and `next_user` is `0`, any user `Syscall::DebugWrite` immediately panics in `trace_index(0, ...)`.
- **Proof**: Not run, because `DebugArea` ring-index corruption on core reuse was established by inspection of `enter_debug_areas`, `boot.rs:1342-1344`, `debug.rs:82-95`, and `abi/src/debug.rs:78-80` (`(seq - 1) % entries`), and is not exercised separately as a PoC test.

---

### Finding 9: `sched_configure` fails to reset `sched.consumed` when deconfiguring and reconfiguring from the unconfigured state

- **Severity**: `hardening`
- **Attacker**: A user program with `MANAGE` and `READ` rights on a `Sched` context.
- **Location**:
  - `model/src/sched.rs:818-827`:
```rust
        let sched = live(&mut self.scheds, context);
        if off {
            sched.configured = false;
            (sched.remaining, sched.deadline, sched.throttled) = (0, 0, None);
            (sched.budget, sched.period, sched.pending) = (0, 0, None);
        } else if !sched.configured {
            sched.configured = true;
            (sched.budget, sched.period, sched.pending) = (budget, period, None);
            (sched.remaining, sched.deadline) = (budget as i64, now + period);
        } else {
```
  - Contradicts the documented contract in `model/src/sched.rs:892-893`:
```rust
    /// Consumed counts since the context was last configured from the
    /// state not configured, and reads 0 while it is not configured.
```
- **Attack**:
  1. A user thread configures a `Sched` context, binds it to a thread, and runs until `sched.consumed > 0`.
  2. The thread deconfigures the context via `Syscall::SchedConfigure` with `budget = 0, period = 0` (`off = true`), then reconfigures it via `Syscall::SchedConfigure` with a non-zero budget and period (`!sched.configured`).
  3. Because neither branch resets `sched.consumed = 0`, `Syscall::SchedRead` returns the accumulated `consumed` counter from before deconfiguration instead of `0`.
- **Proof**:
  - Test `scenarios::units::poc_sched_1_consumed_not_reset_on_reconfigure` in `/private/tmp/dodos-pr3-v2-B-hydrogen/model/src/scenarios/units.rs`.
  - Command:
    `PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture`
  - Output:
    `test scenarios::units::poc_sched_1_consumed_not_reset_on_reconfigure ... ok`

---

### Finding 10: `Table::attached_to` truncates `.count() as u8` without saturation

- **Severity**: `hardening`
- **Attacker**: A machine configuration or shared-table writer creating 256 or more `AttachWord` entries referencing the same `IoSpace` root address.
- **Location**: `model/src/table.rs:708-716`:
```rust
    pub(crate) fn attached_to(&self, root: u64) -> u8 {
        let words = self
            .attach
            .values()
            .filter_map(|&raw| dodos_abi::AttachWord::from_raw(raw));
        words
            .filter(|w| w.state().is_some() && w.root() == root)
            .count() as u8
    }
```
- **Attack**:
  1. If 256 `AttachWord` entries in `table.attach` are non-NONE and carry the same `root`, `.count()` returns `256`, which truncates `as u8` to `0`.
  2. Any count between `17` and `255` causes `PageClass::iospace_root(n)` (`abi/src/machine.rs:176-180`) to return `None`; at `256`, `attached_to(root)` wraps to `0`, causing `caps.rs:1151` (`pinned = space.root.is_some_and(|r| self.table.attached_to(r) > 0)`) and `memory.rs:1018` (`set_root_class`) to treat a root pinned by 256 devices as having `0` attached devices.
- **Proof**: Not run; normal `IoSpaceAttach` enforces `IOSPACE_MAX_DEVICES == 16` per `IoSpace`, so triggering 256 entries requires either direct shared `attach` table writes by a hostile IOMMU kernel or a machine with >= 256 attached devices.

---

## Combined PoC Verification Run

Command:
```sh
PATH="/nix/var/nix/profiles/default/bin:$PATH" nix develop /private/tmp/dodos-pr3-v2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-v2-B-hydrogen/Cargo.toml -p dodos-model poc_ -- --nocapture
```

Exact output:
```text
running 8 tests

thread 'scenarios::units::poc_debug_1_previous_crash_max_sequence_panics_on_boot' (13146956) panicked at model/src/debug.rs:105:23:
attempt to add with overflow
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
test scenarios::units::poc_debug_1_previous_crash_max_sequence_panics_on_boot - should panic ... ok
test scenarios::units::poc_blocks_1_reserve_chunk_can_be_taken_twice ... ok
test scenarios::units::poc_sched_1_consumed_not_reset_on_reconfigure ... ok

thread 'scenarios::units::poc_caps_2_remote_depth_zero_panics_in_depth' (13146955) panicked at model/src/caps.rs:387:33:
attempt to subtract with overflow
test scenarios::units::poc_caps_2_remote_depth_zero_panics_in_depth - should panic ... ok
test scenarios::units::poc_threads_1_remote_message_page_survives_grant_revocation ... ok
test scenarios::units::poc_caps_1_pinned_iospace_released_to_untyped ... ok
test scenarios::units::poc_blocks_2_memory_split_splits_device_with_frozen_leaves ... ok
test scenarios::units::poc_memory_1_failed_detach_drops_iospace_device_and_unmaps_without_freeze ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 523 filtered out; finished in 0.86s
```

---

## Functions Examined and Found Sound

- **`model/src/blocks.rs`**: `Model::control`, `Model::run`, `Model::block`, `Model::idle_block`, `Model::memory_give`, `Model::unmap_block`, `Model::mapped_block`, `Model::free_block`, `Model::take_block`, `Model::write_freed`, `Model::remove_block_cap`, `FreedRun::chunks`.
- **`model/src/caps.rs`**: `footprint`, `Model::cap_derive`, `Model::cap_move`, `Model::cap_delete`, `Model::cap_revoke`, `Model::cap_inspect`, `Model::untyped_retype`, `Model::cspace_grow`, `Model::thread_size`, `Model::fits`, `Model::take`, `Model::release`, `Model::return_watermark`, `Model::create`, `Model::new_cap`, `Model::derive`, `Model::place`, `Model::slot`, `Model::remove`, `Model::next_removed`, `Model::swept`, `Model::rooted`, `Model::waiter`, `Model::undo`, `Model::remove_leaf`, `Model::remove_leaf_dead`, `Model::remove_root`, `Model::remove_cap` (remaining non-`IoSpace` arms of `Model::destroy` were also found sound).
- **`model/src/debug.rs`**: `DebugArea::new`, `DebugArea::write_raw`, `DebugArea::write`, `CrashArea::accepted`, `CrashArea::write_record`, `Model::stamp`, `Model::entry`, `Model::trace`, `Model::trace_transitions`, `Model::fail`, `Model::ring`, `Model::trace_ring`, `Model::suppressed`, `Model::area_generation`, `Model::crash_record`, `Model::debug_write`, `Model::trace_emit`, `Model::ports_refused`, `Model::platform_holder`, `Model::ports_of`, `Model::ioport`, `Model::ioports_issue`, `Model::entropy_read`, `range_of`.
- **`model/src/faults.rs`**: `Model::fault`, `Model::fault_once`, `Model::raise`, `Model::record`, `Model::answered`, `Model::thread_read_regs`, `Model::thread_write_regs`, `Model::page_of`.
- **`model/src/ipc.rs`**: `Listed::cap`, `Message::check_header`, `Message::check`, `Transfer::rights`, `notification`, `received`, `Parcel::new`, `Model::call`, `Model::call_to`, `Model::enter`, `Model::recv`, `Model::reply_recv`, `Model::send`, `Model::send_to`, `Model::signal`, `Model::hand_over`, `Model::wait`, `Model::notify_bind`, `Model::listed`, `Model::receive`, `Model::serve`, `Model::answer`, `Model::has_page`, `Model::deliver`, `Model::receiver`, `Model::take_caller`, `Model::unlink`.
- **`model/src/lib.rs`**: `Space::table_pages`, `Event::bounded`, `Stale::eq`, `Stale::deref`, `Stale::deref_mut`, `live`, `Model::geometry`, `Model::bytes`, `Model::page`, `Model::runnable`, `Model::object_at_start`, `Model::enabled`, `Model::woken`, `Model::longest_walk`, `Model::object_at`, `Model::member`, `Model::role`, `Model::stray_write`, `Model::ownership`, `Model::untyped_marks`, `Model::map_count`, `Model::gate_word`, `Model::device_leaves`, `Model::page_class`, `Model::grant_entries`, `Model::grant_entry`, `Model::chunked_or_kept`, `Model::core_list_fences`, `Model::device_count`, `Model::device_entry`, `Model::frame_at`, `Model::translated`, `Model::apply`, `Model::made`, `Model::dispatch`, `Model::bury_stale`, `Model::dispatch_call`, `Model::addressed_space`, `Model::bound_space`, `Model::through`, `Model::full`, `Model::dying`, `Model::cap`, `Model::is`, `Model::held`, `Model::object`, `Model::optional`, `Model::destination`, `Model::vacant`, `Model::window`, `Model::end_bounded`, `Model::wake`.
- **`model/src/locks.rs`**: `Model::pay`, `Model::wait_mark`, `Model::begin_locks`, `Model::end_locks`, `Model::event_with_waits`, `Model::healthy_wait`.
- **`model/src/memory.rs`**: `hooked`, `tables`, `Model::record_mapping`, `Model::leaf_chunks`, `Model::leaf_target`, `Model::count_leaves`, `Model::rehook`, `Model::rehook_by`, `Model::root_class`, `Model::empty_mapping`, `Model::clear_mapping`, `Model::clear_mapping_pub`, `Model::finish_unmapping`, `Model::freeze_unmapping`, `io_levels`, `Model::levels`, `Model::aspace_map`, `Model::class_of`, `Model::extend_mapping`, `Model::aspace_protect`, `Model::iospace_attach`, `Model::detach`, `Model::attaching`, `Model::iommu_of`, `Model::attach_answered`, `Model::set_root_class`, `Model::attach_key`, `Model::identifier_key`, `Model::holds_identifier`, `Model::free_domain`.
- **`model/src/sched.rs`**: `Parameters::bandwidth`, `Model::now`, `Model::running`, `Model::running_on`, `Model::core_count`, `Model::advance`, `Model::settle`, `Model::apply_settled`, `Model::next_timer`, `Model::timer_interrupt`, `Model::begin_on`, `Model::begin`, `Model::snap`, `Model::observe`, `Model::end`, `Model::beat`, `Model::reschedule_others`, `Model::enabled_for`, `Model::choose`, `Model::no_context`, `Model::context_of`, `Model::runnable_thread`, `Model::holder`, `Model::eligible`, `Model::wanted`, `Model::requeue`, `Model::wake_up`, `Model::exhaust`, `Model::replenish`, `Model::pick`, `Model::request_due`, `Model::hardware`, `Model::due`, `Model::first_context`, `Model::cores_set`, `Model::in_set`, `Model::own_node`, `Model::sched_bind`, `Model::sched_unbind`, `Model::sched_set_cores`, `Model::sched_read`, `Model::sched_count`, `Model::yield_now`, `Model::lend`, `Model::release_lend`, `Model::release_for_receive`, `Model::sched_dying`, `Model::timer_set`, `Model::timer_cancel`, `Model::disarm`, `Model::fire`, `Model::timer_destroyed`, `Model::clear_lend`, `Model::disarm_one`, `Model::sched_destroyed`, `Model::thread_unscheduled`.
- **`model/src/table.rs`**: `Ring::new`, `Ring::at`, `Ring::set`, `CrashRecord::begun`, `CrashRecord::last_stop`, `CrashRecord::stopped`, `Table::member`, `Table::generation`, `Table::core_word`, `Table::holds_page`, `Table::cores_of`, `Table::write_core`, `Table::start_request`, `Table::started_node`, `Table::writes`, `Table::write_member`, `Table::write_role`, `Table::gate_word`, `Table::map_count`, `Table::add_leaves`, `Table::set_map_count`, `Table::set_class`, `Table::holds_reserve`, `Table::may_take`, `Table::journal`, `Table::begin_journal`, `Table::write_owner`, `Table::write_owner_cleared`, `Table::write_entry`, `Table::write_identifier`, `Table::attach_word`, `Table::swap_attach`, `Table::line_word`, `Table::write_line`.
- **`model/src/tasks.rs`**: `Model::marks`, `Model::mark`, `Model::aware`, `Model::task`, `Model::task_attach`, `Model::detach_task`, `Model::task_mark`, `Model::task_exempt`, `Model::task_revoke`, `Model::stop`, `Model::task_read`, `Model::detach_one`, `Model::next_task`.
- **`model/src/threads.rs`**: `leave`, `Model::thread_configure`, `Model::thread_resume`, `Model::thread_suspend`, `Model::thread_cancel`, `Model::thread_set_features`, `Model::bind_space`, `Model::bind_aspace`, `Model::bind_fault`, `Model::bind_page`, `Model::unbind_all`.

## What Was Not Examined

All 12 files assigned to lot B (`blocks.rs`, `caps.rs`, `debug.rs`, `faults.rs`, `ipc.rs`, `lib.rs`, `locks.rs`, `memory.rs`, `sched.rs`, `table.rs`, `tasks.rs`, `threads.rs` in `model/src/`) were read in full. The following files outside lot B were consulted only where directly called by lot B code, and were not audited function by function:

- Remaining files under `model/src/` (`boot.rs`, `cores.rs`, `grants.rs`, `irq.rs`, `nodes.rs`, `rings.rs`, `roles.rs`, `system.rs`, `units.rs`, `check/*.rs`, `scenarios/*.rs`).
- All files in `abi/src/`.
