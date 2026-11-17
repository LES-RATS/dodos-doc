# Security review V2, lot A (Opus)

Repository: `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
All tests were written and run in the copy `/private/tmp/dodos-pr3-v2-A-opus`
(the shared clone is unchanged). Two test files were added there:

- `abi/tests/v2a.rs` (14 probes of the pure functions of `abi/`);
- `model/src/scenarios/v2a.rs` (4 scenarios; `mod v2a;` appended to
  `model/src/scenarios/mod.rs`).

Commands, from `/private/tmp/dodos-pr3-v2-A-opus`, with
`PATH=/nix/var/nix/profiles/default/bin:$PATH`:

    nix develop -c cargo test -p dodos-abi --test v2a -- --nocapture
    nix develop -c cargo test -p dodos-model --lib v2a -- --nocapture

Every test below passed in that copy (14 of 14 in `abi`, 4 of 4 in the
model). A passing test here means the weakness is present. Panics are
reported as they happen in the test profile, which keeps overflow checks
(`Cargo.toml`: `[profile.dev.package.dodos-abi] opt-level = 2`, checks on).

---

## Finding 1. The sender of a message between nodes is taken from the header, not from the ring it came on

- **Severity:** exploitable.
- **Attacker:** a hostile kernel of one node. It writes anything into its
  own rings to the other nodes.
- **Where:** `abi/src/ring.rs:187-199`, the header carries the sender:

  ```rust
  /// The header at the start of a message's first entry (16 bytes): its kind,
  /// its length in entries, its sender's node slot and generation, ...
  pub struct RingHeader {
      pub kind: u8,
      pub length: u8,
      pub sender: u16,
      pub sender_generation: u32,
  ```

  The receiver knows the real sender: it reads the ring of the ordered
  pair (from, me). `model/src/rings.rs:480`:

  ```rust
  fn consume(&mut self, from: u16, user: bool, step: u64) -> u64 {
  ```

  But the one check and the handlers use the header's field and never
  compare it with `from`. `model/src/rings.rs:376-378`:

  ```rust
  pub(crate) fn refused(&self, message: &Message) -> Option<u64> {
      let header = &message.header;
      let sender = header.sender;
  ```

  and `model/src/rings.rs:612`, in `receive_message`:

  ```rust
  let from = message.header.sender;
  ```

  `refused` has no parameter for the ring at all, so no rule of the check
  can tie the message to its ring. `abi/src/lib.rs:738` promises the
  opposite to user space: "What the kernel sets on every received message.
  The sender cannot forge any of it."

- **Attack A (identity of a send):**
  1. Nodes 0, 1, 2 are live. A thread of node 1 waits on its mailbox.
  2. Node 2 (hostile) reads node 0's generation in the member words and
     writes on its own user ring 2 → 1 a `Send` whose header says
     `sender = (0, g0)`, with a stamp naming task `TaskId(0, 1)` and the
     mark `PRIVATE`.
  3. Node 1's check compares the stamp's node with the header's sender
     (both 0) and passes; node 1 delivers the message to its thread as a
     message of node 0's task 1 with node 0's marks.
- **Attack B (a unit operation in the owner's name):**
  1. Four nodes, three IOMMU units. Node 0 attaches device 0x10 through
     unit role 0, held by node 1.
  2. Node 2 (hostile) reads the attach word (root) and writes on its ring
     2 → 1 a `UnitRequest` `Detach { device: 0x10, domain: 1, root }`
     whose header says `sender = (0, g0)`.
  3. Node 1's gate judges the operands against requester node 0 (the
     identifier word, the unit's entry and the domain all name node 0),
     finds them allowed, and detaches node 0's device. Node 0 still
     believes its device attached.

  The existing test
  `pass21::a_forged_detach_from_another_node_through_another_unit_is_refused`
  shows the same detach refused when the attacker names itself; naming
  the victim in the header is enough to pass. The same holds for every
  kind: a `Revoke` or `Release` "from" a granter or grantee whose grant
  index and serial the attacker reads in the shared tables, a `Handed` or
  `ReportAsk` "from" a role's holder, a `Signal` on another node's grant.
- **Proof:** `model/src/scenarios/v2a.rs`,
  `v2a_a_send_on_node_2s_ring_that_names_node_0_is_delivered_as_node_0s`
  and
  `v2a_a_detach_on_a_third_nodes_ring_that_names_the_owner_detaches_its_device`.
  Both use the harness's own `System::inject(from, to, message)`, which
  writes on ring `from → to`. Every step is followed by the whole check
  (`S::call`, `S::settle`, `S::run` assert `check() == Ok(())`), so no
  invariant covers it either. Output:

  ```
  running 2 tests
  refused by node 1: 0 -> 0
  woken: Some(Ok(Message(Delivery { received: Received { header: Header(4294967303), badge: 0, marks: Marks(1), task: 1 }, words: [2989] })))
  test scenarios::v2a::v2a_a_send_on_node_2s_ring_that_names_node_0_is_delivered_as_node_0s ... ok
  role 0 holder 1 attacker 2
  entries {16: (0, 1)} domains {16: 1}
  refused by holder: 0 -> 0
  attach word after: Some(Detached)
  test scenarios::v2a::v2a_a_detach_on_a_third_nodes_ring_that_names_the_owner_detaches_its_device ... ok
  ```

- **Fix direction:** the first rule of the one check is
  `header.sender == from` (the ring's sender), or drop the field from the
  header and pass `from` to `refused` and to every handler.

---

## Finding 2. On ARM64, a user watchpoint that the kernel's own access hits is classified as a bug of the kernel

- **Severity:** likely exploitable (a user program stops its node), on
  ARM64. Not run: it depends on hardware behaviour the model does not hold.
- **Attacker:** a user program that may set its hardware breakpoints and
  watchpoints (the fault kind `HardwareBreakpoint` exists for ARM64, and
  `StartDebug` publishes `watchpoints`).
- **Where:** `abi/src/aarch64.rs:208-212`:

  ```rust
  EC_CP15_MCR_MRC | ... | EC_IABT_SAME | EC_DABT_SAME | EC_FP_TRAP32 | EC_SERROR
  | EC_BREAKPOINT_SAME | EC_STEP_SAME | EC_WATCHPOINT_SAME | EC_BKPT32
  | EC_VECTOR_CATCH32 | EC_PMU => NotThread,
  ```

  and `abi/src/lib.rs:804-807`: `NotThread` is "a bug of the kernel (it
  accuses itself, evidence self) or a hardware error, handled by the
  recovery of the node."
- **Attack:**
  1. A thread sets a watchpoint on an address of its own message page (or
     of a buffer it passes to `debug_write`), which lies below the user
     range end and passes the register checks.
  2. The kernel writes the message page (a receive) or reads the buffer.
  3. From memory, not checked against the Arm ARM in this review: an
     unprivileged load or store (`LDTR`/`STTR`) executed at EL1 is matched
     by watchpoints as an EL0 access, so a watchpoint restricted to EL0
     still fires, and the exception is taken from EL1 with EC 0x35
     (watchpoint, same level). Linux's arm64 hardware breakpoint code has
     a path for user watchpoints hit by kernel accesses for this reason
     (from memory).
  4. By the table, EC 0x35 is `NotThread`: the node accuses itself and
     every thread of the node stops with it.

  The same holds on x86-64 for a data breakpoint in DR0-DR3 on a user
  address that the kernel touches at CPL 0 (`model/src/faults.rs:199`
  checks only `word >= user_end`); `abi/` has no classification table for
  x86-64, so the reading there is the kernel's.
- **Proof:** only the classification is shown,
  `abi/tests/v2a.rs::v2a_a_watchpoint_at_el1_is_not_the_threads`
  (passes: `exception_use(0x35 << 26) == Some(NotThread)`).
- **Fix direction:** a debug exception taken at the kernel's level whose
  address is a user address of the current thread is the thread's
  (deliver `HardwareBreakpoint` on return, or disable the user's
  watchpoints while the kernel touches user memory); say so in Faults.

---

## Finding 3. A next sequence left in a kept debug area makes the next correct writer panic

- **Severity:** likely exploitable in a build with overflow checks (the
  model's build, and any debug kernel); in a build without them the index
  wraps and nothing breaks.
- **Attacker:** a hostile kernel that ran a physical core before. A core's
  debug area is kept by the next node that starts on it when its magic
  and version are right (`model/src/debug.rs:261-275`,
  `enter_debug_areas`: "goes on from the next sequences found there").
- **Where:** `abi/src/debug.rs:78-80`:

  ```rust
  pub const fn trace_index(seq: u64, entries: u64) -> u64 {
      (seq - 1) % entries
  }
  ```

  and its caller `model/src/debug.rs:91-94`:

  ```rust
  let seq = *next;
  entry.seq = seq;
  ring[trace_index(seq, entries) as usize] = entry;
  *next = seq + 1;
  ```
- **Attack:**
  1. The hostile node writes `next_user = 0` (or `u64::MAX`) in the debug
     area of a core it holds, magic and version left right.
  2. The node is fenced; R6 frees the core; a correct node starts on it
     and keeps the area.
  3. The first `trace_emit` (or any kernel trace) on that core computes
     `0 - 1` (or `u64::MAX + 1`) and the correct node's kernel panics.
- **Proof:** `model/src/scenarios/v2a.rs`,
  `v2a_a_next_sequence_left_in_a_debug_area_panics_the_next_writer` (it
  edits the area directly, as the hostile kernel would have left it):

  ```
  panicked at abi/src/debug.rs:79:5: attempt to subtract with overflow
  next_user 0x0: Err("panic")
  panicked at model/src/debug.rs:94:17: attempt to add with overflow
  next_user 0xffffffffffffffff: Err("panic")
  test ... ok
  ```

  Also `abi/tests/v2a.rs::v2a_trace_index_of_sequence_0_panics`.
- **Fix direction:** a kept area whose next sequences are 0 or beyond
  what one boot can write is cleared like an area with a wrong magic;
  `trace_index` defined for 0.

---

## Finding 4. `Geometry::valid` overflows on a boot image's page shift instead of refusing it

- **Severity:** hardening (boot image attacker; a panic at start instead of
  `Refusal::MachineValues`; in a build without overflow checks the sum
  wraps and the geometry is still refused).
- **Where:** `abi/src/lib.rs:504`:

  ```rust
  if s[i] != 0 && (s[i - 1] == 0 || s[i] != s[i - 1] + per_level || i > 2) {
  ```

  `s[i - 1]` is the boot image's byte, not yet checked (the check of
  `s[1]` sets `sizes = false` but the loop goes on), so `s[1] + per_level`
  overflows `u8`.
- **Attack:** a boot image with `page_shift = [12, 250, 30, 0]`,
  `entries = 512`, `levels = 4`. `Machine::layout` calls `valid()` first
  (`model/src/boot.rs:631`) and panics there.
- **Proof:** `abi/tests/v2a.rs::v2a_geometry_valid_overflows_on_a_large_page_shift`:

  ```
  panicked at abi/src/lib.rs:504:55: attempt to add with overflow
  valid() on page_shift [12, 250, 30, 0]: Err("panic")
  ```
- **Fix direction:** `s[i - 1].checked_add(per_level) != Some(s[i])`, or
  return as soon as `sizes` is false.

---

## Finding 5. `module_frames` overflows on a module's length or address, and accepts an address not on a page

- **Severity:** hardening (boot image attacker).
- **Where:** `abi/src/machine.rs:1311`, `1325` and `1320`:

  ```rust
  end: len.div_ceil(page) * page,
  ...
  let mut best = PageSize::Page;
  ...
  let aligned = (self.phys + offset).is_multiple_of(bytes)
  ```

  The page size is chosen with no alignment check, so a module at a
  physical address that is not page aligned is cut into frames whose
  first page is not aligned.
- **Attack:** a module of length near 2^64, or at a physical address in the
  last pages of the space, panics the start-up; a module at an unaligned
  address yields frames on unaligned addresses. In the model the first
  case panics earlier, in `boot.rs` (`at += len.next_multiple_of(page)`),
  not in `module_frames` (test
  `v2a_a_file_of_the_boot_image_longer_than_memory_is_not_refused`: a file
  of `0xffff_ffff_ffff_fff5` bytes panics with "attempt to add with
  overflow" in `core::num`, a file of 2^45 bytes is refused `Floors`). A
  kernel that calls `module_frames` on the boot image's values before its
  own checks gets the panic in `abi/`.
- **Proof:** `abi/tests/v2a.rs`:

  ```
  panicked at abi/src/machine.rs:1311:14: attempt to multiply with overflow   (len = u64::MAX)
  panicked at abi/src/machine.rs:1325:27: attempt to add with overflow        (phys = 2^64 - 4096, 3 pages)
  module_frames(phys = 0x1234): [ModuleFrame { size: Page, pages: 2, offset: 0 }]
  ```
- **Fix direction:** say the domain in the documentation (`phys` and `virt`
  page aligned, `phys + len` without overflow) and check it, or compute
  with `checked_*` and return no frame.

---

## Finding 6. An MSI aimed directly at APIC ID 255 is accepted

- **Severity:** hardening (depends on a core with APIC ID 255 and no
  interrupt remapping).
- **Attacker:** a user driver that claims an MSI on such a core.
- **Where:** `abi/src/x86_64.rs:136-141`:

  ```rust
  pub const fn msi_direct(apic_id: u32, vector: u8) -> Option<(u64, u64)> {
      if apic_id > 255 {
          return None;
      }
  ```
- **Attack:** from memory, not checked against the SDM in this review: in
  physical destination mode, destination 0xFF of an MSI (as of an IOAPIC
  entry) is the broadcast to every local APIC; Linux bounds the xAPIC
  physical destination at 0xFE for this reason. An MSI composed for APIC
  ID 255 reaches every core of every node, so one driver's device
  interrupts every node.
- **Proof:** `abi/tests/v2a.rs::v2a_msi_direct_accepts_apic_id_255` (passes:
  address `0xFEEF_F000`). The existing test
  `msi_addresses_follow_the_remappable_and_the_direct_formats` pins
  `msi_direct(255, 239)` as accepted.
- **Fix direction:** `apic_id >= 255` refused (and the same bound for the
  redirection entry of an IOAPIC, `UnitOperation::Redirection`).

---

## Finding 7. Decodings that accept what no constructor writes

- **Severity:** hardening.
- **Where and what:**
  1. `abi/src/machine.rs:1136-1145`, `RoleWord::from_raw`: a *handing* word
     is accepted whatever its holder and target (`2 => true`): holder or
     target `ROLE_NOBODY`, or holder equal to target. A *held* word with
     holder `ROLE_NOBODY` is accepted too.
  2. `abi/src/machine.rs:484-490` and `577-582`: `Owner::Node(n).code()` is
     `n` unchecked, and `Ownership::owner()` falls back to `Unclaimed` for
     a code that names nothing. `Ownership::taken(Owner::Node(0xFFFF), g)`
     passes `from_raw` and reads as `Unclaimed`; `Owner::Node(2000)` is
     refused by `from_raw` but, built directly, reads as `Unclaimed`, and
     `may_take` then lets any node take it. A fail-open default: no caller
     in the model passes such a node today.
  3. `abi/src/ring.rs:225-232`, `RingHeader::credit`: indices 24 to 30 name
     no credit (16 request + 8 send credits) and are returned as credits.
     The model's `credit_in_use` uses `.get(index)` and refuses them; a
     kernel that indexes directly would read past its table.
  4. `abi/src/machine.rs:318-323`, `GateWord::from_raw`: the count of
     pages not of class data is bounded by 4,096 whatever *E* is (a chunk
     of *E* = 512 pages accepts 4,096).
  5. `abi/src/x86_64.rs:98-110`, `dr7_valid`: an instruction breakpoint
     (R/W = 00) with a length other than 00 is accepted; the SDM leaves its
     effect undefined (from memory).
- **Proof:** `abi/tests/v2a.rs`: `v2a_a_handing_role_word_with_nobody_is_accepted`,
  `v2a_an_owner_node_of_0xffff_reads_as_unclaimed` (prints
  `Node(2000) reads as Unclaimed, from_raw None`),
  `v2a_a_credit_index_past_the_credits_is_read_as_one`,
  `v2a_gate_word_not_data_is_bounded_by_4096_only`,
  `v2a_dr7_accepts_an_execution_breakpoint_with_a_length`. All pass.

---

## Finding 8. Pure functions that panic outside a domain their callers must keep

- **Severity:** hardening. Each caller in the model keeps the domain; the
  kernel and user space must too, and nothing in the type says so.
- `abi/src/lib.rs:893-896`, `firing_instant`: a deadline of exactly 2^63
  computes `63 - 64` and panics; above 2^63 it returns an instant before
  the deadline (`firing_instant(2^63 + 5, 0) = 0`). `timer_set` refuses
  `deadline >= TIME_LIMIT` first (`model/src/sched.rs`), so the model is
  safe.
- `abi/src/lib.rs:920-924`, `ClockPage::nanoseconds`: a `shift` of 128 or
  more panics in the reader (user space); the page is the kernel's, so
  only a faulty kernel reaches it.
- `abi/src/lib.rs:868`, `bandwidth`: asserts `period < 2^48 && budget <=
  period`; `sched_configure` checks first (`model/src/sched.rs:784`).
- `abi/src/machine.rs:488`, `Owner::Reserve(j).code()` overflows for
  `j >= 16`.
- **Proof:** `abi/tests/v2a.rs`: `v2a_firing_instant_at_the_time_limit_panics`
  (`panicked at abi/src/lib.rs:896:13: attempt to subtract with overflow`),
  `v2a_clock_page_shift_of_128_panics`
  (`panicked at abi/src/lib.rs:922:22: attempt to shift right with overflow`).

---

## Finding 9. `FeatureMask::fits` and `kind_covers` have no caller, and `fits` omits the size

- **Severity:** hardening.
- **Where:** `abi/src/features.rs:97-103` ("the condition of `thread_move`
  on the destination node") and `125-128`. `thread_move` was removed by
  D-128 (`lib.rs:660-662`); neither function is called in the model. If a
  move comes back with `fits` as its condition, it checks the features and
  the length but not that `thread_bytes` on the destination kind fits the
  thread's area: a destination kind with more baseline state (a larger
  `baseline_bytes`) would save more than the thread object holds.
  `thread_set_features` does check the area (`model/src/threads.rs:175`).
- **Proof:** not run (no caller).

---

## Functions examined and found sound

- `aarch64.rs`: the EC constants (the existing test compares them with
  Linux), `exception_use`, `class_use` (apart from Finding 2), `abort_use`
  (the fault status codes as I read them from memory of DDI 0487; IFSC
  0x11 and 0x21 are reserved for instruction aborts and classed
  `Protection`, harmless), the GIC ranges.
- `debug.rs`: the layouts (64 + 4,032 = 4,096; rings at 4,096 and 20,480,
  ending at 69,632; crash header 4,096), `TraceCode::user`, `TraceEntry`
  accessors and `word2_of` (the slot is masked to 15 bits).
- `features.rs`: `Kind::baseline`, `FeatureMask::check` (order invalid then
  unsupported), `thread_bytes` (the sum cannot overflow: at most 1,024 +
  32 × 2^32).
- `lib.rs`: `SlotAddr`, `Rights`, `Marks`, `PageSize::from_raw`,
  `Geometry::bytes`/`page`/`chunk`/`address_bits`/`root_entry`/`canonical`
  (only called after `valid`; the order of `valid`'s other terms keeps
  `levels * tz` and `address_bits - 1` in range), `MemoryType::for_memory`,
  `mapping_range`, `mapping_rights`, `io_mapping_rights`, `Header::new`,
  `Header::from_raw`, `is_fast`, `FaultKind::from_raw`, `bandwidth` (in its
  domain), `IrqSource` (every bit of each kind is a field or checked
  zero), `TaskId`, `NodeGen`.
- `machine.rs`: `RemoteRef`, `PageClass` (`stored`, `from_raw`, `permits`),
  `AttachWord`, `Ownership::from_raw`/`check`/`may_take` (rules 1 to 4 for
  well-formed owners), `DeviceEntry`, `Member::from_raw`,
  `member_transition` (each row as documented; the generation wraps only
  after 2^32 starts of one slot), `successor`, `best_class`, `barrier`,
  `CoreWord`, `floors`, `round_up` (unit from a valid geometry),
  `clear_step`, `clear_steps`, `IoPortRange`, `ioport_check`, `ports_meet`,
  `FenceRecord::stop_index`.
- `ring.rs`: `NodeMessage::from_raw` (0, 9 and above 12 refused),
  `ring`/`is_request`/`is_answer`/`answers`, `message_entries`, `ring_free`,
  `ring_fits`, `ring_resync` (a producer that goes back makes the
  receiver re-read its own ring only), `RingHeader::new`, `readable`
  (a length that disagrees with the body only skips the same sender's
  entries).
- `riscv64.rs`: `exception_use` and the codes (compared with Linux by the
  existing test).
- `start.rs`: the records and constants; sizes are asserted in `tests.rs`.
- `x86_64.rs`: `canonical`, `rflags` (the mask is CF PF AF ZF SF TF DF OF AC
  ID; the kernel must still clear AC on entry, which is not `abi/`'s),
  `msi_remapped` (handle bit 15 at bit 2; `IRQ_MAX_CORES_REMAPPED` = 341 is
  right: 340 × 192 + 191 = 65,471), `KERNEL_PORTS`, `PCI_CONFIG_PORTS`.
- `abi/tests/review6.rs` and `abi/src/tests.rs`: read for what they pin; the
  only pinned value I dispute is `msi_direct(255, 239)` (Finding 6).

## Not examined

- The Kani proofs were read, not run (Kani is not in Nix).
- The model files outside the lot were read only where a function of the
  lot is called (`rings.rs` receive path, `units.rs` operand check,
  `debug.rs` trace writes, `boot.rs` layout, `sched.rs`, `threads.rs`,
  `faults.rs`); their other functions were not reviewed.
- Hardware behaviour quoted from memory (Finding 2 step 3, Finding 6, the
  DR7 length rule) was not checked against the Arm ARM or the Intel SDM.
