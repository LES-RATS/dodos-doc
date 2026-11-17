# Security Review Report — Lot C (`v2-C-hydrogen`)

Repository: `/private/tmp/dodos-pr3-final` (branch `model`, head `6312868`), tested in copy `/private/tmp/dodos-pr3-v2-C-hydrogen`.
Proof tests added in `/private/tmp/dodos-pr3-v2-C-hydrogen/model/tests/review_c_hydrogen.rs` and run via `nix develop -c cargo test -p dodos-model --test review_c_hydrogen`.

---

## Findings

### File 1: `model/src/boot.rs`

#### Finding 1 — Unchecked `Core::kind` index panics `Machine::layout()` instead of returning `Refusal::MachineValues`
- **Severity:** likely exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:411`, `model/src/boot.rs:433-435`, `model/src/boot.rs:641`, `model/src/boot.rs:646`
  ```rust
  // model/src/boot.rs:433-435
  pub fn kind_of(&self, core: usize) -> dodos_abi::Kind {
      self.kinds[usize::from(self.core_list()[core].kind)]
  }
  ```
  ```rust
  // model/src/boot.rs:641-646
  let nodes = self.initial_nodes();
  let mut named = BTreeSet::new();
  let fits = nodes.iter().all(|cores| {
      let alike = cores
          .iter()
          .all(|&c| c < self.cores.len() && self.state_kind(c) == self.state_kind(cores[0]));
  ```
- **Attack:**
  1. The boot image provides a `Machine` with `kinds` empty or with any `Core` whose `kind` field is `>= self.kinds.len()` (e.g., `machine.cores[0].kind = 99`).
  2. `Model::boot` / `System::boot` calls `Machine::layout()`.
  3. On line 641, `initial_nodes()` runs (if `self.single()`, line 411 calls `self.state_kind(c)` -> `self.kind_of(c)`), or on line 646 `self.state_kind(c)` runs, without first checking `core.kind < self.kinds.len()`.
  4. Indexing `self.kinds[...]` panics with an out-of-bounds access instead of returning `Err(Refusal::MachineValues)`.
- **Proof:**
  Test in `model/tests/review_c_hydrogen.rs`:
  ```rust
  #[test]
  fn boot_invalid_core_kind_panics_instead_of_refusal() {
      let mut machine = Machine::example();
      machine.cores[0].kind = 99;
      let res = std::panic::catch_unwind(|| Model::boot(&machine));
      assert!(res.is_err(), "expected panic on out-of-range core kind");
  }
  ```
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  thread 'boot_invalid_core_kind_panics_instead_of_refusal' (13045048) panicked at model/src/boot.rs:434:19:
  index out of bounds: the len is 1 but the index is 99
  test boot_invalid_core_kind_panics_instead_of_refusal ... ok
  ```

---

#### Finding 2 — Unchecked `64 * window + i` arithmetic overflow / wrap-around in `Machine::initial_nodes()`
- **Severity:** exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:418-427`
  ```rust
  // model/src/boot.rs:418-427
  match &self.boot_nodes {
      Some((_, nodes)) => nodes
          .iter()
          .map(|&(window, mask)| {
              (0..64)
                  .filter(|i| mask >> i & 1 == 1)
                  .map(|i| (64 * window + i) as usize)
                  .collect()
          })
          .collect(),
  ```
- **Attack:**
  1. The boot image sets `boot_nodes = Some((1, vec![(1u64 << 58, 1)]))` (with `mask` having bit 0 set and `window = 1 << 58`, or any `window >= 1 << 58`).
  2. `Machine::layout()` calls `self.initial_nodes()` on line 641 before validating `window`.
  3. In debug builds, `64 * window` panics with arithmetic overflow.
  4. In release builds (wrapping arithmetic), `64 * (1 << 58)` wraps to `0`, bypassing the `c < self.cores.len()` check on line 646 and silently placing core `0` under an invalid `BootNodes` window.
- **Proof:**
  Test in `model/tests/review_c_hydrogen.rs`:
  ```rust
  #[test]
  fn boot_nodes_window_overflow_panics_instead_of_refusal() {
      let mut machine = Machine::example();
      machine.boot_nodes = Some((1, vec![(1u64 << 58, 1)]));
      let res = std::panic::catch_unwind(|| Model::boot(&machine));
      assert!(res.is_err(), "expected panic on 64 * window overflow");
  }
  ```
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  thread 'boot_nodes_window_overflow_panics_instead_of_refusal' (13045049) panicked at model/src/boot.rs:424:35:
  attempt to multiply with overflow
  test boot_nodes_window_overflow_panics_instead_of_refusal ... ok
  ```

---

#### Finding 3 — Unvalidated `phys_bits` causes shift underflow/overflow, OOM, and out-of-bounds indexing into `owners`
- **Severity:** exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:791-807`, `model/src/boot.rs:817`
  ```rust
  // model/src/boot.rs:791-800
  let words = 1u64 << (self.phys_bits - geometry.chunk_shift());
  let mut owners = vec![Ownership::none().raw(); words as usize];
  ...
  for &at in chunks.iter().filter(|at| !in_floor.contains(at)) {
      owners[(at / chunk) as usize] = Ownership::free(Owner::Unclaimed).raw();
  }
  ```
  ```rust
  // model/src/boot.rs:817
  let device = without(&vec![(0, 1u64 << self.phys_bits)], &sorted(taken));
  ```
- **Attack:**
  1. `Machine::layout()` never validates `self.phys_bits` against `geometry.chunk_shift()`, `64`, or the maximum address in `self.memory` / `kept`.
  2. Setting `phys_bits < geometry.chunk_shift()` (e.g., `phys_bits = 10`) panics on subtraction underflow at line 791. Setting `phys_bits >= 64` panics on shift overflow at line 817 (and large valid values like `phys_bits = 63` cause multi-terabyte `vec!` allocation).
  3. Setting `phys_bits` smaller than the highest usable RAM chunk (e.g., `phys_bits = 32` when usable RAM is at 4 GiB) causes `at / chunk >= words`, panicking with an out-of-bounds index into `owners` at line 799 (or line 804).
- **Proof:**
  Test in `model/tests/review_c_hydrogen.rs`:
  ```rust
  #[test]
  fn boot_phys_bits_underflow_or_oob_panics_instead_of_refusal() {
      let mut small = Machine::example();
      small.phys_bits = 10;
      let res_small = std::panic::catch_unwind(|| Model::boot(&small));
      assert!(res_small.is_err(), "expected panic on phys_bits < chunk_shift");

      let mut below_ram = Machine::example();
      below_ram.phys_bits = 32;
      let res_oob = std::panic::catch_unwind(|| Model::boot(&below_ram));
      assert!(res_oob.is_err(), "expected OOB panic on chunk >= 1<<phys_bits");
  }
  ```
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  thread 'boot_phys_bits_underflow_or_oob_panics_instead_of_refusal' (13045051) panicked at model/src/boot.rs:791:29:
  attempt to subtract with overflow
  thread 'boot_phys_bits_underflow_or_oob_panics_instead_of_refusal' (13045051) panicked at model/src/boot.rs:799:19:
  index out of bounds: the len is 2048 but the index is 2054
  test boot_phys_bits_underflow_or_oob_panics_instead_of_refusal ... ok
  ```

---

#### Finding 4 — Overlapping `RegionKind::Usable` regions (or `Usable` overlapping `Reserved`/`Unusable`) duplicate chunks across nodes and reserves
- **Severity:** exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:718-732`, `model/src/boot.rs:775-807`
  ```rust
  // model/src/boot.rs:718-732
  let regions = |kind| {
      let regions = self.memory.iter().filter(|region| region.kind == kind);
      sorted(regions.map(|r| (r.base, r.base + r.len)).collect())
  };
  let ordinary: Ranges = without(&regions(RegionKind::Usable), &kept)
      .into_iter()
      .map(|(s, e)| (s.next_multiple_of(page), e / page * page))
      .filter(|(s, e)| s < e)
      .collect();
  let chunks: Vec<u64> = ordinary
      .iter()
      .flat_map(|&(s, e)| {
          (s.next_multiple_of(chunk)..e / chunk * chunk).step_by(chunk as usize)
      })
      .collect();
  ```
- **Attack:**
  1. `Machine::layout()` never merges or rejects overlapping `RegionKind::Usable` descriptors in `self.memory`, nor does it subtract `RegionKind::Reserved` or `RegionKind::Unusable` regions from `ordinary`.
  2. A boot image supplies two overlapping `RegionKind::Usable` descriptors covering `[ram, ram + 10 * chunk)`. `chunks` contains every chunk address twice.
  3. `take` hands the same physical chunk addresses out to node floors and reserves (or two different nodes' floors when sized appropriately), and marks chunks in `reserves` as `Ownership::free(Owner::Reserve(_))` even while another node holds a start-up `Untyped` over the same chunk.
  4. Both nodes can retype and map the same physical page concurrently, breaking memory isolation (`ONE-HOLDER` / invariant 55).
- **Proof:**
  Test in `model/tests/review_c_hydrogen.rs` (`boot_overlapping_usable_regions_hand_same_chunk_to_two_nodes`).
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  overlapping usable sys.check() = Err("node 0: 55: translation to a free word")
  test boot_overlapping_usable_regions_hand_same_chunk_to_two_nodes ... ok
  ```

---

#### Finding 5 — `floor_node == 0` or a floor too small for start-up frames panics in `Model::build()`
- **Severity:** likely exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:769-773`, `model/src/boot.rs:1105`, `model/src/boot.rs:1213`, `model/src/boot.rs:1218-1222`
  ```rust
  // model/src/boot.rs:1105
  let start_at = untypeds[0].0;
  ```
  ```rust
  // model/src/boot.rs:1213-1222
  let start_untyped = floor[0];
  ...
  let taken = model
      .take(start_untyped, pages * bytes, bytes, Clearing::None)
      .expect("the start-up untyped holds the frames of the start-up");
  ```
- **Attack:**
  1. `abi::floors` accepts `floor_node = 0` (yielding `floor = 0`), and `Machine::layout()` never checks that `sizes.floor > 0` or that the first block `untypeds[0]` of each node's floor is large enough to hold the copied writable segments, start-up page, and message page.
  2. With `floor_node = 0`, `untypeds` is empty and `Model::build()` panics at line 1105 (`index out of bounds`).
  3. With `floor_node = chunk` and a writable segment of length `chunk`, `Model::build()` panics at line 1222 (`the start-up untyped holds the frames of the start-up: NoMemory`).
- **Proof:**
  Tests `boot_zero_floor_panics_in_build` and `boot_small_floor_with_writable_segment_panics_in_build` in `model/tests/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  thread 'boot_small_floor_with_writable_segment_panics_in_build' (13045053) panicked at model/src/boot.rs:1222:18:
  the start-up untyped holds the frames of the start-up: NoMemory
  thread 'boot_zero_floor_panics_in_build' (13045054) panicked at model/src/boot.rs:1105:24:
  index out of bounds: the len is 0 but the index is 0
  test boot_small_floor_with_writable_segment_panics_in_build ... ok
  test boot_zero_floor_panics_in_build ... ok
  ```

---

#### Finding 6 — `Machine::layout()` fails to validate `Segment::rights` for `Rights::READ` and forbidden bits
- **Severity:** likely exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:686-689`, `model/src/boot.rs:1274-1276`
  ```rust
  // model/src/boot.rs:686-689
  let both = Rights::WRITE.union(Rights::EXEC);
  if self.segments.iter().any(|s| s.rights.contains(both)) {
      return Err(Refusal::WriteAndExec);
  }
  ```
- **Attack:**
  1. `Machine::layout()` only rejects segments having both `WRITE` and `EXEC`. It does not check that `s.rights` includes `Rights::READ` or that no capability-only bits (e.g. `DERIVE`, `GRANT`) are set.
  2. A boot image supplies a segment with `rights = Rights::EXEC` (without `Rights::READ`).
  3. `Model::boot` succeeds and maps the segment without `READ` in the start-up address space, immediately violating invariant `"38: rights of a mapping"` (`Model::check()` fails).
- **Proof:**
  Test `boot_segment_without_read_right_breaks_model_check` in `model/tests/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  segment without READ model.check() = Err("38: rights of a mapping")
  test boot_segment_without_read_right_breaks_model_check ... ok
  ```

---

#### Finding 7 — Unchecked arithmetic on `File::len`, `kept`, `memory`, and `crash` overflows in `Machine::layout()`
- **Severity:** likely exploitable
- **Attacker:** A boot image with any values.
- **Location:** `model/src/boot.rs:614-620`, `model/src/boot.rs:706-708`, `model/src/boot.rs:720`
  ```rust
  // model/src/boot.rs:706-708
  at = at.next_multiple_of(large.unwrap_or(page));
  modules.push((at, vaddr, len, copied));
  at += len.next_multiple_of(page);
  ```
- **Attack:**
  1. A boot image sets `files[0].len = u64::MAX` (or sets `image_base`, `kept`, `feedback`, `crash`, or `Region::base + Region::len` so their sum overflows `u64`).
  2. `Machine::layout()` performs unchecked addition / `next_multiple_of` on these values and panics with arithmetic overflow instead of returning `Err(Refusal::...)`.
- **Proof:**
  Test `boot_file_len_overflow_panics` in `model/tests/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen -- --nocapture`
  Output:
  ```
  thread 'boot_file_len_overflow_panics' (13045047) panicked at /rustc/0ef1bc386059596dada8fb65b50425aab2ea637a/library/core/src/num/mod.rs:1327:5:
  attempt to add with overflow
  test boot_file_len_overflow_panics ... ok
  ```

---

### File 2: `model/src/cores.rs`

#### Finding 8 — `go_idle()` calls `answer_pending()` after `choose()`, leaving woken threads unqueued (`41: queue of a context`) and their own core idle (`46: running context`)
- **Severity:** exploitable
- **Attacker:** A user program making system calls from several threads/cores on a multi-core node.
- **Location:** `model/src/cores.rs:501-514`, `model/src/sched.rs:254-287`
  ```rust
  // model/src/cores.rs:501-514
  pub(crate) fn go_idle(&mut self) {
      let at = *self.at;
      self.cores[at].loaded = None;
      if self.width() == 1 {
          return;
      }
      if !self.cores[at].idle.mark {
          self.pay(Cost::IdleWord);
          self.cores[at].idle.mark = true;
      }
      if !self.cores[at].pending.is_empty() {
          self.answer_pending();
      }
  }
  ```
  ```rust
  // model/src/sched.rs:255-287
  self.choose(entry);
  ...
  match self.cores[at].thread {
      Some(_) => self.load_root(),
      None => {
          self.go_idle();
          self.cache_here();
      }
  }
  self.reschedule_others();
  ```
- **Attack:**
  1. On a multi-core x86-64/RISC-V node, thread `t1` runs on core 1 with an address space cached in core 1's TLB, and thread `t2` runs on core 0.
  2. `t2` calls `ASpaceUnmap`, starting an invalidation request on core 0 that sets core 1's pending bit for core 0 and posts `Ipi::Invalidate` to core 1; `t2` blocks in `Wait::Cores(0)`.
  3. `t0` moves `t2`'s scheduling context to core 1 via `SchedConfigure` (or even leaves it on core 0).
  4. Before core 1 takes `Ipi::Invalidate`, `t1` on core 1 blocks (e.g., `Syscall::Wait` on an empty `Notify`).
  5. In `Model::end`, `choose()` finds nothing runnable on core 1 (`cores[1].thread = None`) and runs `requeue()`. Then `go_idle()` runs *after* `choose()`, sees `cores[1].pending` is non-empty, and calls `answer_pending()` -> `complete(0)` -> `wake(t2)`.
  6. Because `requeue()` only runs inside `choose()`, `t2`'s context is never placed on its ready queue (violating invariant `"41: queue of a context"`). Furthermore, `reschedule_others()` skips `core == at`, so if `t2`'s context is on core 1, core 1 stays idle with `idle.mark = true` and no `Ipi::Reschedule`.
- **Proof:**
  Test `cores_go_idle_answers_pending_and_misses_self_reschedule` in `model/tests/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model --test review_c_hydrogen cores_go_idle -- --nocapture`
  Output:
  ```
  sys.check() after go_idle -> answer_pending = Err("node 0: 41: queue of a context")
  test cores_go_idle_answers_pending_and_misses_self_reschedule ... ok
  ```

---

### File 3: `model/src/grants.rs`

#### Finding 9 — `send_received` trusts `words.len()` and `grants.len()` from `Body::Send`, panicking the receiving kernel in `Header::new`
- **Severity:** exploitable
- **Attacker:** A hostile kernel of one group of cores sending a forged `Body::Send` over its user ring.
- **Location:** `model/src/grants.rs:405`, `model/src/rings.rs:458-461`
  ```rust
  // model/src/grants.rs:405
  let header = Header::new(header.label(), words.len(), caps, flags).expect("within limits");
  ```
  ```rust
  // model/src/rings.rs:458-461
  Body::Send { stamp, .. } => {
      let task = dodos_abi::TaskId::from_raw(stamp.0);
      (stamp.0 != 0 && (task.counter() == 0 || task.node() != sender)).then_some(stamp.0)
  }
  ```
- **Attack:**
  1. An honest thread on node 0 waits in `Syscall::Recv` on `START_SLOT_MAILBOX`.
  2. Hostile node 1 injects a `Body::Send` into its user ring to node 0 with `words.len() > WORDS_MAX` (e.g., `vec![0; 2000]`) or with more than `CAPS_MAX` (8) accepted grants while the receiver's `Recv` window has enough empty slots. `refused()` only validates `stamp.0` and passes the message.
  3. `send_received()` calls `Header::new(header.label(), words.len(), caps, flags).expect("within limits")` and panics the receiving kernel (`within limits: Invalid`), causing a cross-node denial of service.
- **Proof:**
  Test `hostile_send_with_excess_words_panics_receiver` in `model/src/scenarios/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model scenarios::review_c_hydrogen::hostile_send_with_excess_words_panics_receiver -- --nocapture`
  Output:
  ```
  thread 'scenarios::review_c_hydrogen::hostile_send_with_excess_words_panics_receiver' (13103629) panicked at model/src/grants.rs:405:76:
  within limits: Invalid
  note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
  test scenarios::review_c_hydrogen::hostile_send_with_excess_words_panics_receiver ... ok
  ```

#### Finding 10 — `send_received` writes unvalidated `stamp.1` bits into an unaware task's `marks`, breaking `Marks` validity and invariants
- **Severity:** exploitable
- **Attacker:** A hostile kernel sending `Body::Send` with reserved bits set in `stamp.1`.
- **Location:** `model/src/grants.rs:411-416`
  ```rust
  // model/src/grants.rs:411-416
  if !self.aware(server) {
      self.mark(server, stamp.1);
  }
  let mut received = crate::ipc::received(header, 0);
  received.marks = dodos_abi::Marks::from_bits(stamp.1).unwrap_or(dodos_abi::Marks::NONE);
  received.task = stamp.0;
  ```
- **Attack:**
  1. An unaware server task/thread on node 0 calls `Syscall::Recv` on `START_SLOT_MAILBOX`.
  2. Hostile node 1 injects a `Body::Send` with `stamp.1 = 0b100` (a reserved bit not in `Marks::ALL`).
  3. `send_received()` calls `self.mark(server, stamp.1)` without masking or validating `stamp.1` via `Marks::from_bits`, storing reserved bit `0b100` directly into `task.marks` / `thread.marks`.
  4. Invariant 49 (`"49: marks of a task"`) fails immediately, `Model::marks()` returns `None` (losing all valid marks on future IPC), and `Delivery.received.marks` silently falls back to `Marks::NONE`.
- **Proof:**
  Test `hostile_send_with_reserved_mark_bits_corrupts_receiver_marks` in `model/src/scenarios/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model scenarios::review_c_hydrogen::hostile_send_with_reserved_mark_bits_corrupts_receiver_marks -- --nocapture`
  Output:
  ```
  thread 'scenarios::review_c_hydrogen::hostile_send_with_reserved_mark_bits_corrupts_receiver_marks' (13103631) panicked at model/src/scenarios/review_c_hydrogen.rs:117:11:
  assertion `left == right` failed
    left: Err("node 0: 49: marks of a task")
   right: Ok(())
  test scenarios::review_c_hydrogen::hostile_send_with_reserved_mark_bits_corrupts_receiver_marks ... ok
  ```

#### Finding 11 — `send_received` / `place_remote` / `valid` never verify `Granted` against the granter's grant entry or memory ownership, letting a hostile kernel grant any physical address
- **Severity:** exploitable
- **Attacker:** A hostile kernel that holds at least one live grant to the victim node.
- **Location:** `model/src/grants.rs:79-91,389-397,430-486`, `model/src/memory.rs:547-557`, `model/src/check/table.rs:261-268`
  ```rust
  // model/src/grants.rs:475-484
  live(&mut self.cspaces, place.space).slots[place.index as usize] = Slot::Full(cap);
  self.frames.insert(id, granted.frame);
  let remote = Remote {
      node: granter,
      grant: granted.grant,
      serial: granted.serial,
      use_entry,
      depth: granted.depth,
  };
  self.remotes.insert(id, remote);
  ```
  ```rust
  // model/src/grants.rs:87-90
  entry.is_some_and(|e| e.state == GrantState::Live && e.serial == remote.serial)
      && used
          .is_some_and(|u| u.serial == remote.serial && member.generation() == u.generation)
      && current
  ```
- **Attack:**
  1. Hostile node 1 makes one legitimate `NodeSend` granting a small read-only frame to node 0 (`grant = 0, serial = 0`).
  2. Node 1 injects a second `Body::Send` whose `Granted` reuses `(grant: 0, serial: 0)` with arbitrary `frame` (`base`, `pages`, `page`, `memory`) and `rights: Rights::READ | Rights::WRITE` (e.g. `base` pointing to a private frame belonging to node 0 or another node).
  3. Neither `refused()` nor `place_remote()` verifies `granted` against `table.grants[granter][grant]`, checks `e.grantee == self.node`, validates `frame`, or enforces 1-to-1 anchor ownership.
  4. When node 0 maps the received remote frame via `ASpaceMap`, `valid()` only checks that `grants[1][0]` is `Live` with `serial == 0`, and `check_table()` (`check/table.rs:261-268`) skips `targets` and chunk leaf validation for `self.remotes`. Node 0 maps its own private frame (or any physical page of class `Data`) read-write under a forged remote capability, and `System::check()` passes.
- **Proof:**
  Test `hostile_send_with_forged_frame_lets_receiver_map_arbitrary_physical_address` in `model/src/scenarios/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model scenarios::review_c_hydrogen::hostile_send_with_forged_frame_lets_receiver_map_arbitrary_physical_address -- --nocapture`
  Output:
  ```
  test scenarios::review_c_hydrogen::hostile_send_with_forged_frame_lets_receiver_map_arbitrary_physical_address ... ok
  ```

#### Finding 12 — `place_remote` accepts `Granted { depth: 0 }`, panicking the receiver with integer underflow on `CapDerive`
- **Severity:** exploitable
- **Attacker:** A hostile kernel sending `Body::Send` with `Granted { depth: 0, ... }`.
- **Location:** `model/src/grants.rs:482`, `model/src/caps.rs:385-388`
  ```rust
  // model/src/grants.rs:482
  depth: granted.depth,
  ```
  ```rust
  // model/src/caps.rs:385-388
  let offset = top
      .and_then(|top| self.remotes.get(&top.object))
      .map_or(0, |remote| remote.depth - 1);
  chain.len() + offset
  ```
- **Attack:**
  1. Hostile node 1 holds a live `(grant: 0, serial: 0)` to node 0 and injects a `Body::Send` carrying `Granted { grant: 0, serial: 0, rights: READ | DERIVE, depth: 0, ... }`.
  2. `place_remote()` stores `remote.depth = 0`.
  3. When any thread on node 0 calls `CapDerive` (or another syscall calling `fits()` -> `depth()`) on the received capability, `caps.rs:387` evaluates `remote.depth - 1` (`0usize - 1`), panicking node 0's kernel with subtraction underflow.
- **Proof:**
  Test `hostile_send_with_zero_depth_panics_receiver_on_derive` in `model/src/scenarios/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model scenarios::review_c_hydrogen::hostile_send_with_zero_depth_panics_receiver_on_derive -- --nocapture`
  Output:
  ```
  thread 'scenarios::review_c_hydrogen::hostile_send_with_zero_depth_panics_receiver_on_derive' (13123117) panicked at model/src/caps.rs:387:33:
  attempt to subtract with overflow
  note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
  test scenarios::review_c_hydrogen::hostile_send_with_zero_depth_panics_receiver_on_derive ... ok
  ```

#### Finding 13 — `node_send` does not check `depth(cap) < TREE_DEPTH`, creating anchors at depth `TREE_DEPTH + 1`
- **Severity:** likely exploitable
- **Attacker:** A user program calling `Syscall::NodeSend`.
- **Location:** `model/src/grants.rs:189-210,315`
  ```rust
  // model/src/grants.rs:315
  self.derive(cap, rights, 0, place);
  ```
- **Attack:**
  1. A user thread on node 0 derives a `Frame` capability via `CapDerive` until `depth(cap) == TREE_DEPTH` (64).
  2. Unlike local IPC (`model/src/ipc.rs:388`), `node_send()` never checks `self.depth(cap) >= TREE_DEPTH`.
  3. Calling `Syscall::NodeSend` with `Transfer::Derive(cur, Rights::READ.bits())` calls `make_grant()` -> `self.derive(cap, ...)`, inserting an anchor capability at depth 65 (`> TREE_DEPTH`) and violating invariant `"20: depth of the tree"` (while also advertising `depth = 65` to the remote node).
- **Proof:**
  Test `node_send_frame_at_tree_depth_creates_anchor_over_limit` in `model/src/scenarios/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model scenarios::review_c_hydrogen::node_send_frame_at_tree_depth_creates_anchor_over_limit -- --nocapture`
  Output:
  ```
  check after node_send at TREE_DEPTH = Err("node 0: 20: depth of the tree")
  test scenarios::review_c_hydrogen::node_send_frame_at_tree_depth_creates_anchor_over_limit ... ok
  ```

#### Finding 14 — `send_answered` records `use_index` and keeps grant/anchor alive even when `delivered == false`
- **Severity:** hardening
- **Attacker:** A hostile kernel answering `Body::Send` with `SendAnswer { delivered: false, dropped: false, uses: [Some(0)] }`.
- **Location:** `model/src/grants.rs:509-518`
  ```rust
  // model/src/grants.rs:509-518
  for (i, grant) in grants.into_iter().enumerate() {
      match uses.get(i).copied().flatten() {
          Some(use_index) => {
              if let Some(entry) = self.table.grants[me].get_mut(&grant) {
                  (entry.use_index, entry.answered) = (Some(use_index), true);
              }
          }
          None => self.free_with_anchor(grant),
      }
  }
  ```
- **Attack:**
  1. Honest node 0 sends a frame to node 1 via `NodeSend`.
  2. Hostile node 1 replies with `Body::SendAnswer { delivered: false, dropped: false, uses: vec![Some(0)] }`.
  3. `send_answered()` keeps grant 0 marked `answered = true` with `use_index = Some(0)` and keeps its anchor capability allocated, while waking the sender thread with `Err(Error::WouldWait)`. The sender believes the send failed and no grant was established, yet a grant table slot (up to `GRANTS`) and an anchor capability stay occupied until explicitly revoked.
- **Proof:**
  Test `hostile_send_answer_not_delivered_with_use_index_leaks_grant` in `model/src/scenarios/review_c_hydrogen.rs`.
  Command: `nix develop -c cargo test -p dodos-model scenarios::review_c_hydrogen::hostile_send_answer_not_delivered_with_use_index_leaks_grant -- --nocapture`
  Output:
  ```
  test scenarios::review_c_hydrogen::hostile_send_answer_not_delivered_with_use_index_leaks_grant ... ok
  ```

---

