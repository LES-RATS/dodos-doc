# Security review of a pull request: lot A

Repository: `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`, the
diff `origin/main..HEAD`. Work copy (nothing in the shared clone was changed):
`/private/tmp/dodos-pr3-v2-A-deepseek`.

My lot, in the order I read it: `abi/src/aarch64.rs`, `abi/src/debug.rs`,
`abi/src/features.rs`, `abi/src/lib.rs`, `abi/src/machine.rs`,
`abi/tests/review6.rs`, `abi/src/ring.rs`, `abi/src/riscv64.rs`,
`abi/src/start.rs`, `abi/src/tests.rs`, `abi/src/x86_64.rs`.

The toolchain works: `nix develop -c cargo test -p dodos-abi` ran 74 + 2 tests
green before I changed anything. Every test I wrote lives in my work copy; the
only edit to existing code is the one registration line named at the end.

## Findings

### 1. A message's sender is a word of the message: any node can act in any other node's name

- Severity: **exploitable**
- Attacker: a whole hostile kernel of one group of cores (node 2), which writes
  its own ring and reads the shared machine table.
- Files: `abi/src/ring.rs:193` (the header), `abi/src/ring.rs:239` (the one
  check the interface defines), and the model that implements it at
  `model/src/rings.rs:376`.

```rust
// abi/src/ring.rs:193
pub struct RingHeader {
    pub kind: u8,
    pub length: u8,
    pub sender: u16,
    pub sender_generation: u32,
    pub receiver_generation: u32,
    pub credit: u32,
}
```

```rust
// abi/src/ring.rs:234-243
/// Whether the receiver can read the header, with `available` entries
/// between its consumer index and the producer index: a kind it knows
/// and a length from 1 to `RING_MESSAGE_ENTRIES_MAX` that does not
/// reach past the producer index. A header it cannot read is consumed
/// as one entry (D-131).
pub const fn readable(&self, available: u64) -> bool {
    NodeMessage::from_raw(self.kind).is_some()
        && self.length >= 1
        && self.length as usize <= RING_MESSAGE_ENTRIES_MAX
        && self.length as u64 <= available
}
```

The interface offers one check of a received header and it does not look at
`sender`, `sender_generation`, `receiver_generation` or `credit`. The model
then implements the check in one function that is *not given the ring the
message came from*:

```rust
// model/src/rings.rs:373-376
/// The one check on every message received (D-124, D-129, D-131), in
/// one function and before anything changes. `None` passes; `Some`
/// names what it named, for the trace (code 11).
pub(crate) fn refused(&self, message: &Message) -> Option<u64> {
```

The caller reads the peer's ring and hands over only the message, so the
header's sender is the identity everything downstream uses:

```rust
// model/src/rings.rs:496
let entry = self.ring_of(from, me, user).at(consumed).cloned();
...
// model/src/rings.rs:515
Some(message) => match self.refused(&message) {
...
// model/src/rings.rs:609-612
fn receive_message(&mut self, message: Message) {
    let sender = self.table.member(message.header.sender);
    self.applied.0.push((message.header, sender));
    let from = message.header.sender;
```

The check that *is* made on the header is that the sender's member word is
starting, live, sealing or sealed with the generation named
(`model/src/rings.rs:385-390`), and that word is a public single-writer word
of the machine table which every node reads. So a node that names another
node there passes the whole check.

The attack, as numbered steps (node 2 is the attacker, nodes 0 and 1 honest):

1. Node 0 grants node 1 a frame by a `node_send` with `derive`. Node 1 then
   holds a remote capability and a use entry that names node 0.
2. Node 2 reads the shared use table of node 1. The entry holds `granter`,
   `grant`, `serial`, `generation` (`model/src/table.rs:228-237`) and is
   readable by every node, as the grant table is.
3. Node 2 reads the member words of node 0 and node 1, for their generations.
4. Node 2 writes one `Revoke` into its own ring to node 1 (the ring a faulty
   or hostile node leaves bytes on, which `System::inject` models) with
   `sender = 0`, `sender_generation = node 0's`, `receiver_generation = node
   1's`, the credit field none, and the `(grant, serial, use_index)` it read.
5. Node 1 consumes the message and passes it: nothing compares `sender` with
   the ring's owner.
6. `revoke_received` (`model/src/grants.rs:704-727`) marks the capability's
   root dying and removes it: **node 1's authority over the frame is
   destroyed in node 0's name, though node 0 never asked, and node 0's grant
   entry stays live** — the two nodes now disagree about a capability, which
   is the state the barrier and R2..R6 exist to prevent.
7. The whole check of invariants accepts the state, and no invariant covers
   the fact that a message applied in a name was not written on that name's
   ring: `System::check()` returns `Ok(())` at step 6.

Proof (both directions, so the reader sees that the sender word is the only
difference):

- Test: `model/src/scenarios/attack_v2a.rs`, registered by
  `model/src/scenarios/mod.rs:7` (`mod attack_v2a;`), one test
  `a_message_naming_another_node_as_its_sender_is_applied_in_that_node_s_name`.
  It builds a three-node machine (`machine(Arch::X86_64, 3, &[&[0], &[1], &[2]])`),
  makes the grant, then injects the same `Revoke` twice on the same ring of
  node 2: once `sender = 2` (refused, the use entry stays), once `sender = 0`
  (applied, the use entry is gone, node 0's grant entry still there), and
  asserts `m.sys.check() == Ok(())`.
- Command: `nix develop -c cargo test -p dodos-model --lib attack_v2a`
- Output (verbatim, last lines):

```
running 1 test
test scenarios::attack_v2a::a_message_naming_another_node_as_its_sender_is_applied_in_that_node_s_name ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 523 filtered out; finished in 0.38s
```

The test asserts the behaviour that is there, so it stops failing as soon as
the hole is closed (the fix is to compare `header.sender` with the ring's
owner, or to drop the field and use the ring's owner as the sender): it is a
proof of the attack, not a fix.

The same shape applies to every request kind (a request needs no credit to
match, only an answer does — `model/src/rings.rs:462-473`, and the check of
a request is the header alone): a `Handed` forged in the holder's name tells
the receiver that a unit role is now its, and a `Release` forged in the
grantee's name frees the granter's grant entry. I proved the `Revoke` only.

### 2. A module length is never checked against the space: a boot image rounds it up past the top

- Severity: **likely exploitable** (a boot image stops the kernel, or, with
  the overflow checks off, silently gives a module no frames)
- Attacker: a boot image with any values. (Such an attacker may own the boot
  already; the contract still requires a refusal instead of a panic, and
  `Refusal` has no case for it.)
- Files: `abi/src/machine.rs:1305-1314` (`module_frames`) and its two users
  `model/src/boot.rs:1104` and `model/src/boot.rs:1244/1267`; the model's own
  rounding at `model/src/boot.rs:708`.

```rust
// abi/src/machine.rs:1305-1313
pub const fn module_frames(
    phys: u64,
    virt: Option<u64>,
    len: u64,
    geometry: Geometry,
) -> ModuleFrames {
    let page = geometry.page();
    ModuleFrames {
        phys,
        virt,
        offset: 0,
        end: len.div_ceil(page) * page,
        geometry,
    }
}
```

```rust
// model/src/boot.rs:699-708
        let files = self.files.iter().map(|f| (f.len, None, false));
        for (len, vaddr, copied) in segments.chain(files) {
            let large = PageSize::ALL[1..]
                ...
            at = at.next_multiple_of(large.unwrap_or(page));
            modules.push((at, vaddr, len, copied));
            at += len.next_multiple_of(page);
        }
```

A segment's length is bounded in `layout()` (`segment.vaddr.checked_add(
segment.len)` and `end > geometry.user_end` refuses it, `model/src/boot.rs:672-677`),
but a `File`'s length is not checked anywhere before line 708: it comes
straight from the boot image.

The attack, as numbered steps:

1. The boot image names one file with `len = 2^64 - 1` (the model's `File`,
   `model/src/boot.rs:89-92`).
2. `layout()` reaches `at += len.next_multiple_of(page)`, which is an
   addition with overflow: the model panics (debug) instead of refusing the
   layout. With the overflow checks off the sum wraps, the image and every
   later range of the layout are wrong, and `module_frames` gives the module
   `end = 0`, that is no frame at all — while `frames_of(...).count()` sizes
   the start-up space (`model/src/boot.rs:1104-1113`) from the same zero.

Proof:

- Test: `model/tests/attack_boot.rs`, `a_boot_image_with_a_file_of_the_largest_length_is_refused`,
  which boots `Machine::example()` with `machine.files[0].len = u64::MAX`
  under `catch_unwind` and fails if the model panics.
- Command: `nix develop -c cargo test -p dodos-model --test attack_boot`
- Output (verbatim, last lines):

```
running 1 test
test a_boot_image_with_a_file_of_the_largest_length_is_refused ... FAILED

---- a_boot_image_with_a_file_of_the_largest_length_is_refused stdout ----

thread 'a_boot_image_with_a_file_of_the_largest_length_is_refused' (13097295) panicked at /rustc/0ef1bc386059596dada8fb65b50425aab2ea637a/library/core/src/num/mod.rs:1327:5:
attempt to add with overflow
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace

thread 'a_boot_image_with_a_file_of_the_largest_length_is_refused' (13097295) panicked at model/tests/attack_boot.rs:15:19:
the model panicked instead of refusing the layout

test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

- The same arithmetic in `abi`'s own function, both builds:
  `abi/tests/review_v2a.rs`, tests
  `module_frames_overflows_on_a_length_near_the_top_of_the_space` (debug) and
  `module_frames_of_a_length_near_the_top_of_the_space_has_no_frames`
  (release), command `nix develop -c cargo test -p dodos-abi --test review_v2a`
  and the same with `--release`; both green (9 and 8 tests). The debug output
  on failure is `panicked at abi/src/machine.rs:1311:14: attempt to multiply
  with overflow`; the release test shows a module of `2^64 - 1` bytes has an
  empty iterator.

### 3. `Geometry::canonical` shifts by `address_bits() - 1` without checking the geometry

- Severity: **hardening** (a panic in debug; with the checks off every address
  is canonical, which is the wrong way for the check to fail)
- Attacker: a boot image or a machine whose entry `Memory` holds zeros.
- File: `abi/src/lib.rs:476-480`.

```rust
// abi/src/lib.rs:457-480
pub const fn address_bits(&self) -> u32 {
    self.page_shift[0] as u32 + self.levels * self.entries.trailing_zeros()
}
...
pub const fn canonical(&self, address: u64) -> bool {
    let top = address >> (self.address_bits() - 1);
    top == 0 || top == u64::MAX >> (self.address_bits() - 1)
}
```

`Geometry::default()` is documented as the value `valid` refuses ("The
default is all zero, which `Geometry::valid` refuses"), and it has
`address_bits() == 0`, so the shift amount is `0 - 1`. `canonical` has no
`valid()` guard and no `Option`.

The attack, as numbered steps:

1. The machine publishes a `Geometry` of zeros (or the kernel reads the entry
   `Memory` before it runs `valid`).
2. The kernel asks `canonical` of a register a user thread wrote
   (`thread_write_regs` is the caller of `geometry.canonical` in the model,
   `model/src/faults.rs:139`).
3. Debug: an arithmetic panic — the node stops on a user call. With the
   overflow checks off: the shift amount wraps, `top` is `address >> 63` and
   the second term is `u64::MAX >> (u32::MAX % 64) == 1`, so **every** address
   is canonical, including `1 << 47` on a machine whose tables translate 48
   bits, and the user thread is given a non-canonical `rip`/`rsp`.

Proof: `abi/tests/review_v2a.rs`, tests
`canonical_on_an_invalid_geometry_is_a_subtraction_with_overflow`
(`#[cfg(debug_assertions)]`, asks `catch_unwind` and requires the panic) and
`canonical_on_an_invalid_geometry_is_true_for_every_address`
(`#[cfg(not(debug_assertions))]`, requires `canonical` to be true of
`0, 1, 1<<47, 1<<63, u64::MAX`). Both green under the two commands above
(`cargo test -p dodos-abi --test review_v2a`: 9 passed; `--release`: 8
passed), and the release arm passing is the proof of the fail-open.

The model itself is not reachable: `Machine::layout` checks `geometry.valid()`
before anything else (`model/src/boot.rs:631`). The defect is in the
contract's function, for the kernel to hit.

### 4. `firing_instant` at `TIME_LIMIT`: a panic in debug, and an instant before the deadline with the checks off

- Severity: **hardening**
- Attacker: none reached in the model (`timer_set` refuses `deadline >=
  TIME_LIMIT` first, `model/src/sched.rs:1061`); a caller that does not is a
  panic or a wrong timer.
- File: `abi/src/lib.rs:883-903`.

```rust
// abi/src/lib.rs:883-903
pub const fn firing_instant(deadline: u64, tolerance: u64) -> u64 {
    if deadline == 0 {
        return 0;
    }
    let sum = deadline.saturating_add(tolerance);
    let x = if sum < TIME_LIMIT - 1 { sum } else { TIME_LIMIT - 1 };
    let differ = (deadline - 1) ^ x;
    // The index of the highest bit in which deadline − 1 and x differ;
    // they differ, since x ≥ deadline.
    let m = 63 - differ.leading_zeros();
    x >> m << m
}
```

At `deadline == TIME_LIMIT` the window closes: `x == TIME_LIMIT - 1 ==
deadline - 1`, so `differ == 0`, `leading_zeros() == 64` and `63 - 64`
underflows.

The attack, as numbered steps:

1. A caller passes a deadline of exactly `TIME_LIMIT` (the value the contract
   says every instant is below, and that `timer_set` refuses).
2. Debug: an arithmetic panic. With the checks off: the shift amount wraps and
   the function returns `0` for every tolerance, an instant *before* the
   deadline it was given, which in this design means "no timer" and arms one
   that fires at once if `instant <= now`.

Proof: `abi/tests/review_v2a.rs`, tests
`firing_instant_at_the_limit_of_the_clock_is_a_subtraction_with_overflow`
(debug, requires the panic for tolerances 0, 1 and `u64::MAX`) and
`firing_instant_at_the_limit_of_the_clock_is_above_its_window` (release,
requires `0`; I read `0` for all three tolerances). Both green in the two runs
quoted in finding 3. The Kani proof of the function assumes `deadline <
TIME_LIMIT` (`abi/src/lib.rs:1195`), which is why no proof covers this.

### 5. `DeviceEntry::used` asserts the wrong alignment: a size below 128 bytes loses bits of its base

- Severity: **hardening**
- Attacker: a caller that passes a small `log2` (no caller in the model does:
  `model/src/boot.rs:822` filters `len >= page`).
- File: `abi/src/machine.rs:636-645`.

```rust
// abi/src/machine.rs:634-646
    /// A used entry of `1 << log2` bytes at `base`, unclaimed.
    pub const fn used(base: u64, log2: u32) -> Self {
        assert!(log2 < 64 && base & ((1 << log2) - 1) == 0);
        Self {
            range: base | log2 as u64 | Self::USED,
            owner: Ownership::free(Owner::Unclaimed),
        }
    }
```

The word holds the base, the size in bits 0-5 and the flag *used* in bit 6
(the struct's own documentation, and `log2()`/`base()` at `:658-668`), so the
base must be aligned on 128 bytes whatever `log2` says; the assertion is
`base & ((1 << log2) - 1)`, which for `log2 < 7` leaves the fields' bits in
the base untouched, and for `log2 == 0` is vacuous (`base & 0`).

The attack, as numbered steps:

1. A caller asks for a range of one byte at `0x1041` (`used(0x1041, 0)`).
2. The assertion passes, and the word's bit 6 of the base is read back as the
   flag *used*, its bits 0-5 as the size: the entry now describes `2` bytes at
   `0x1000`, and the caller's base is silently gone. The entry is written into
   the device table, and the gate later hands out a range nobody asked for (or
   splits it, `model/src/blocks.rs:312-316`).

Proof: `abi/tests/review_v2a.rs`,
`a_device_entry_of_a_size_below_128_bytes_loses_bits_of_its_base`: it reads
back `(entry.base(), entry.log2()) == (0x1000, 1)` for the first entry and
`(0, 6)` for `used(0x40, 6)`, and requires `used(0x41, 0)` not to panic. Green
in both runs of finding 3.

### 6. An attach word keeps a constant 4 KB clear, whatever the machine's page

- Severity: **hardening**
- Attacker: none reached in the model (a root comes from a frame the kernel
  built, `model/src/memory.rs:887`, `model/src/units.rs:447`); the interface
  accepts a root no page of a 16 KB or 32 KB machine starts at, and the gate
  looks up the class of `root / page`, another page.
- File: `abi/src/machine.rs:263-287`.

```rust
// abi/src/machine.rs:255-287
impl AttachWord {
    pub const NONE: Self = Self(0);
    /// The address bits that a page of the smallest size leaves 0.
    const LOW: u64 = 0xfff;

    /// `None` for a root of 0 or not aligned on the smallest page.
    pub const fn new(state: AttachState, root: u64) -> Option<Self> {
        if root == 0 || root & Self::LOW != 0 {
            return None;
        }
        Some(Self(root | state as u64))
    }

    /// `None` for a word that fails its check: a state 0 with an address,
    /// a state with no address, or a bit set between the state and the
    /// address.
    pub const fn from_raw(raw: u64) -> Option<Self> {
        let root = raw & !Self::LOW;
        match (raw & 0b11, root, raw & Self::LOW & !0b11) {
            (0, 0, 0) => Some(Self::NONE),
            (1..=3, 1.., 0) => Some(Self(raw)),
            _ => None,
        }
    }
```

The documentation says "aligned on a page"; the machine's page size is a
value of the machine (`Geometry::page_shift[0]`, 12, 14 or 15 in the abi's own
tests). On a 16 KB page a root of `0x2000` passes both `new` and `from_raw`,
and `0x2000 / 0x4000 == 0`, so the page whose class the gate checks is not the
page the root starts in.

The attack, as numbered steps:

1. A machine publishes the 16 KB geometry (`page_shift[0] == 14`).
2. A word is built or read with `root = 0x2000`, which is 4 KB-aligned and no
   page frame's base.
3. `AttachWord::new` accepts it, `AttachWord::from_raw` accepts it, and the
   iospace root's class is looked up at `root / page == 0` while the address
   the IOMMU is given is `0x2000` — two different pages, one class read for
   another.

Proof: `abi/tests/review_v2a.rs`,
`an_attach_word_accepts_a_root_that_is_aligned_to_four_kilobytes_only`: it
takes the 16 KB geometry of `abi/src/tests.rs` (valid, `page() == 16 << 10`),
requires `0x2000` not to be a multiple of the page, and requires `new`,
`root()` and `from_raw` to accept it. Green in both runs.

### 7. `trace_index` of a sequence below one, and of a ring of no entry

- Severity: **hardening**
- Attacker: a caller of `debug_write`/`trace_emit` that reaches the index
  computation with a sequence of 0 or a ring of 0 entries (the model's own
  reader keeps `seq >= 1` by `(..).max(1)`, `model/src/debug.rs:292`).
- File: `abi/src/debug.rs:76-80`.

```rust
// abi/src/debug.rs:76-80
/// The entry of sequence `seq` (at least 1) sits at index (seq − 1) mod
/// `entries` of its ring.
pub const fn trace_index(seq: u64, entries: u64) -> u64 {
    (seq - 1) % entries
}
```

The attack, as numbered steps:

1. A sequence of 0 is passed (the header of a debug area is `0` before the
   first entry is written, `DebugAreaHeader.next_kernel`).
2. Debug: a subtraction with overflow. With the checks off: `seq - 1` wraps to
   `u64::MAX` and the index is `entries - 1`, so the oldest entry of the ring
   is overwritten by a write meant for the first — a traced event lost and
   another replaced.
3. A ring of 0 entries is a division by zero in every build.

Proof: `abi/tests/review_v2a.rs`, tests
`trace_index_of_a_sequence_below_one_is_a_subtraction_with_overflow` (debug)
and `trace_index_of_a_ring_of_no_entry_is_a_division_by_zero` (both builds).
Green in both runs. Kani's proof of the function assumes `seq >= 1` and picks
one of the two real rings as `entries` (`abi/src/debug.rs:236-256`).

### 8. `bandwidth` and `RemoteRef::new` assert what their documentation only states

- Severity: **hardening**
- Attacker: a user program whose `sched_configure` reaches `bandwidth` with a
  budget above its period, or a node whose grant serial reaches 2^30. The
  model checks both first (`model/src/sched.rs:786-790` refuses unless
  `budget <= period <= SCHED_MAX_PERIOD_NS`; `RemoteRef::new` is reached with
  a serial the model keeps 30 bits, `model/src/rings.rs:324`), so nothing is
  reachable today.
- Files: `abi/src/lib.rs:864-881`, `abi/src/machine.rs:73-84`.

```rust
// abi/src/lib.rs:864-881
pub const fn bandwidth(budget: u64, period: u64) -> u64 {
    if period == 0 {
        return 0;
    }
    assert!(period < 1 << 48 && budget <= period);
```

```rust
// abi/src/machine.rs:73-84
    pub const fn new(node: u16, grant: u16, serial: u32, use_entry: u16) -> Self {
        assert!((node as usize) < NODES_MAX && (grant as usize) < GRANTS);
        assert!(serial < 1 << 30 && (use_entry as usize) < GRANTS);
```

The attack, as numbered steps (why it matters at all):
1. `assert!` is a panic in every build, not an error value, and the contract
   offers the kernel no `Option`/`Result` form of either function.
2. A kernel that calls `bandwidth` before its own range check turns one user
   call into a stop of the node; a grant serial that wraps (30 bits, one more
   at each use) turns the 2^30th grant into a panic.

Proof: `abi/tests/review_v2a.rs`,
`bandwidth_and_a_remote_reference_panic_on_the_inputs_their_documentation_excludes`,
which catches the panics of `bandwidth(2, 1)`, `bandwidth(1, 1 << 48)`,
`RemoteRef::new(1024, ..)`, `RemoteRef::new(1, 4096, ..)`,
`RemoteRef::new(1, 0, 1 << 30, ..)`, and reads `RemoteRef::new(1023, 4095,
(1 << 30) - 1, 4095).raw() == u64::MAX` back. Green in both runs.

### 9. `PageSize::Large3` is a page size no geometry admits, and the start page publishes its slot

- Severity: **hardening**
- Attacker: a boot image, or a kernel that reads `StartMemory.page_shift[3]`
  without `Geometry::valid`.
- Files: `abi/src/lib.rs:440-460` (`PageSize`, `Geometry::bytes`) with
  `abi/src/lib.rs:493-537` (`valid`), and `abi/src/start.rs:337-357`.

```rust
// abi/src/lib.rs:509-516
        let mut i = 2;
        while i < 4 {
            // Present only after a present size, one level up, below the
            // level of the root, and at most E chunks (index 2 at most).
            if s[i] != 0 && (s[i - 1] == 0 || s[i] != s[i - 1] + per_level || i > 2) {
                sizes = false;
            }
```

`i > 2` refuses every fourth page size, so `valid` is false whenever
`page_shift[3] != 0`: `PageSize::Large3` names a value the contract can never
hold, `Geometry::bytes(Large3)` is `None` on every valid geometry, and yet the
start page has four slots for it (`page_shift: [u8; 4]`) and `PageSize::ALL`
has four.

The attack, as numbered steps:
1. A boot image writes a non-zero `page_shift[3]`, which `valid` refuses.
2. A kernel that sizes a leaf by index 3 before checking `valid` gets
   `1 << shift` bytes of a size no table of the machine maps, and the gate's
   "one leaf fits one call" bound (G3) no longer holds for it.

Proof: `abi/tests/review_v2a.rs`,
`no_valid_geometry_holds_a_fourth_page_size` walks six `page_shift[3]` values
on the x86-64 geometry and requires none to be valid, and `PageSize::ALL` to
have four entries. Green in both runs. (The repository already tests three of
these in `abi/src/tests.rs:342-378`; the finding is that the *value* survives
in the interface with no rejection of its own.)

### 10. `StartCore`'s comment and its declaration disagree by one word

- Severity: **hardening** (a comment, and a kernel writer's size assertion)
- Attacker: none (a documentation defect)
- File: `abi/src/start.rs:139-158`.

```rust
// abi/src/start.rs:139-155
/// One physical core, sorted by hardware identifier, so a core's position
/// is its core number. The fields the contract lists take 28 bytes; the
/// record is 32, so a reserved word ends it.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct StartCore {
    pub hw_id: u64,
    pub slot: u32,
    pub kind: u16,
    pub flags: u16,
    pub threads: u8,
    pub perf_highest: u8,
    pub perf_efficient: u8,
    pub efficiency_class: u8,
    pub package: u32,
    pub reserved: u32,
    pub reserved_tail: u32,
}
```

The named fields run 8 + 4 + 2 + 2 + 1 + 1 + 1 + 1 + 4 = 24 bytes, then *two*
reserved words bring the record to 32 — the repository's own offsets say so
(`offset_of!(StartCore, reserved) == 24` and `.., reserved_tail)` is 28,
`abi/src/tests.rs:965-975`). Either the comment is stale (one word too many in
the record) or a four-byte field the contract lists is missing from the
declaration; a kernel that lays the record out from "28 + one reserved word"
writes its last field over `reserved_tail`.

Proof: not run as a test — there is nothing to execute; the offsets quoted are
read from `abi/src/tests.rs` and the sizes agree with
`size_of::<StartCore>() == 32` there (`:1080`). I am reporting it because the
review is asked to read every line, and the sentence is wrong about the
declaration.

## Functions I examined and found sound, and why

`abi/src/aarch64.rs`

- `exception_use`, `class_use`, `abort_use`: the class table
  `EXCEPTION_CLASSES` has exactly the 49 values of the test at
  `abi/src/tests.rs:2120-2189` (45 from Linux's `esr.h` plus 0x14, 0x1B, 0x1E,
  0x3D), the shift and mask are 26 and 0x3F, the fault status code is bits
  5:0, and the routing (aborts to `abort_use`, every other class to
  `class_use`) is consistent with the "reserved" answers. I could not check
  the ARM values themselves (no external documentation allowed), so I checked
  them against the repository's own pinned list and against the two rules the
  file states (a translation fault at any level and a permission fault are
  page faults; an access fault that is not a translation fault is a
  protection fault). The Kani proof
  `an_arm64_class_is_classified_exactly_when_the_architecture_defines_it`
  only feeds syndromes whose fault status code is 0, which its own comment
  says.
- The GIC constants (31/32/1019/1056-1119/4096-5119/8192) are pinned by
  `abi/src/tests.rs:2299-2315`.

`abi/src/debug.rs`

- The sizes are the ones the area adds up to: 64 + 4,032 = 4,096, 256 × 64 =
  16,384, 768 × 64 = 49,152, 4,096 + 16,384 = 20,480, and 69,632 = 17 × 4,096
  (`abi/src/tests.rs:1690-1760`). `CoreCrashRecord` adds to 4,032 and
  `CrashAreaHeader` to 4,096 including a 152-byte `StopRecord`.
- `TraceEntry::word2_of`/`code`/`slot`/`generation`/`continued`: bit 16 flag,
  bits 17-31 the slot masked by 0x7fff (every node slot is below 1,024,
  `NODES_MAX`), bits 32-63 the generation; the mask cannot lose a slot a
  machine can have.
- `trace_index` itself, for `seq >= 1` and `entries >= 1`, is a modulo and
  stays inside the ring (see finding 7 for the two excluded arguments).

`abi/src/features.rs`

- `FeatureMask::check`: the order is Invalid then Unsupported as documented;
  bits 48-63 must be 0, a bit that names no listed state feature is Invalid,
  a length without a with-length feature and a feature without a length are
  Invalid, then bit 31, a feature the kind lacks and a length other than the
  kind's are Unsupported. `fits` and `kind_covers` compare the whole 64-bit
  feature word, so an instruction feature is covered too.
- `thread_bytes`: sums u32 bytes into a u64 (no overflow: 31 × 2^32 < 2^37),
  masks bit 31 out of the optional set, and ends in
  `checked_next_power_of_two` — the only failure is `None`.
- `Kind::baseline`: excludes the large features and bit 31, as documented.

`abi/src/lib.rs`

- `Rights`, `Marks`, `SlotAddr`, `PageSize`, `MemoryType`, `ObjectKind`,
  `FaultKind`, `TaskId`, `NodeGen`, `IrqSource` (its three kinds, the reserved
  bits of each and the requester ID round-trip), `ClockPage::nanoseconds` (the
  128-bit product and the documented truncation, which the tests pin).
- `Header::new`/`from_raw`/`is_fast`: bits 32-38 words (7 bits, 64 fits), 39-41
  caps (4 fits), 42-63 flags; `from_raw` accepts every flag on purpose and the
  model checks the sender's flags itself (`model/src/ipc.rs:48-49` rejects
  anything but `FLAG_ADD_MARKS`), so a user cannot forge a kernel flag.
- `mapping_range`: the order of the four refusals is the documented one, the
  `checked_mul` cannot be passed by a count that runs past the frame, and the
  range is compared in both directions (`address <= limit && bytes <= limit -
  address`), so the end cannot wrap.
- `mapping_rights`, `io_mapping_rights`: the unknown bits, the missing `read`
  and the write-and-exec pair are all refused; `exec` is refused for an
  iospace.
- `Geometry::valid`: I walked every clause for overflow and for reachability
  of `(1 << shift)` with a shift of 64 or more. `address_bits() <= 64` comes
  before `root_entry()` and before the last shift, `levels` is bounded to 2..8
  before `levels - 1`, `entries == 1 << (page_shift[0] - 3)` is reached only
  after `page_shift[0] >= 12`, and `chunk()` is only called after the sizes
  chain. The one unguarded use is `canonical` (finding 3).
- `Geometry::bytes`, `page`, `chunk`, `sizes`, `address_bits`, `root_entry`:
  read back the fields, and every shift is bounded by the geometry the tests
  pin (12/21/30, 14/25/36, 15/27/39) plus the review6 cases.
- `IrqSource::from_raw`: kind 1 has bits 8-9 clear and bits 10-31 clear, kind 2
  has bits 10-31 clear, kind 3 has bits 16-63 clear; a kind outside 1..3 is
  refused. A line's GSI is bounded where it is used (`model/src/irq.rs:46-56`:
  an IOAPIC must serve it and it must be below `IRQ_LINES_MAX`), and a core
  event is refused where the machine has none (`:62-64`).

`abi/src/machine.rs`

- `RemoteRef`: the fields are 10/12/30/12 bits with no overlap and the top
  value is `u64::MAX`; the read-backs truncate exactly the widths the
  constructor writes.
- `PageClass`: every constructor's byte is inside `from_raw`'s set, `stored`
  refuses gate (1), global read-only (2) and device (3), `iospace_table` and
  `iospace_level` are 33..40, `iospace_root`/`root_devices` are 48..64 (17
  values, devices 0 to 16); `permits` refuses tables, gates and every leaf
  both writable and executable, and a device page that is executable or not of
  a device type.
- `GateWord`: the map count is 32 bits, the not-data count 13 bits bounded by
  4,096, and `from_raw` refuses bit 45 and above.
- `Ownership`: `check` is the top 14 bits of the 50-bit repacked word, `make`
  writes them at bits 2-15, `from_raw` refuses state 3, a word *none* other
  than 0, a free word with a generation and an owner code that names nothing;
  the random test at `abi/src/tests.rs:1810-1848` shows a flip of a check bit
  is always caught. `may_take` implements the four rules the tests pin, and
  the reserve rule is given the *index* its caller holds
  (`model/src/table.rs:572`, `holds_reserve(node, j)`), so node A cannot take
  a chunk owned by reserve B.
- `Member`, `member_transition`: the refusal of a middle state (8-15), an
  evidence of 7, a class of 3 and bits 9-15; each row's conditions (the
  generation is kept or incremented by one, the class is written by a fresh
  start only, evidence and driver kept or cleared, an accusation names both,
  a redrive changes the driver) match the table the file documents, and no
  row lets a fenced, unfenced or dead node reach live, sealing or sealed.
- `successor`, `best_class`, `barrier`, `BarrierView`: `successor` cannot index
  out of its slice and returns `None` before any modulo when no node is live;
  the barrier's five lines are the five states with a rule, `Dead` passing.
- `CoreWord`: the check is the top 12 bits of the word with its check bits
  zeroed, `from_raw` recomputes it and refuses everything else, the two
  constructors name only `Owned` and `Joining`, and `names` refuses `Leaving`.
- `RoleWord`: state 3 refused, a vacant word must name nobody and a held word
  no target; the epoch is 29 bits at 34-62 and bit 63 is *failed*, kept by
  `keeping_failed`.
- `floors`, `round_up`, `clear_step`, `clear_steps`, `Floors`: every product
  and sum is `checked_*`, the total is compared with the ordinary memory, and
  the two clearing functions are bounded by the same 64 KB step.
- `IoPortRange::new`/`contains`/`covers`, `ioport_check`, `ports_meet`: first
  ≤ last ≤ 0xFFFF, the width is 1, 2 or 4, the end is `checked_add`, and the
  value of an out is `value >> (8 * width) == 0`.
- `DeviceEntry` (except `used`, finding 5): `log2` is 6 bits, `base` masks the
  same 7.
- `module_frames`' iterator, for the lengths a segment can have: the frame
  sizes are the geometry's, each page count is bounded by *E*, the loop always
  advances, and the last frame ends at the length rounded up (`abi/src/tests.rs:1606-1652`).
- `MemberState`, `Evidence`, `Transition`, `CoreState`, `RoleState`,
  `RoleKind`, `Governs`, `OwnState`, `Owner` (the codes 0..1023 and 0xFFF0..0xFFF7
  are disjoint, 0xFFF8..0xFFFE names nothing), the numbers of nodes, grants,
  deliberate bounds, times of membership, the fence record `stop_index`
  (`core % 64`, one index per core of a window), and every `const` of the file
  that the tests pin.

`abi/tests/review6.rs`

- Both tests pass and both assert what they say: a 64 KB granule has 8,192
  entries, which `TABLE_ENTRIES_MAX` refuses, and an `E` that is not
  `1 << (page_shift[0] - 3)` is refused. The second test's positive case
  (`entries: 512` on 4 KB) is valid.

`abi/src/ring.rs`

- `NodeMessage::from_raw` (1-8 and 10-12, 0 and 9 and 13 refused), `ALL`, the
  rings, `is_request`/`is_answer`/`answers`, `message_entries` (11 for the
  largest `Report`, 10 for a `Send` of 64 words and 4 grants),
  `ring_free`/`ring_fits`/`ring_resync` (both indices are wrapping counters and
  the resynchronised consumer is never more than the entries behind),
  `RingHeader::credit`/`new` (4 + 27 bits of a 32-bit field), `UnitResult`,
  `UnitOperation`. `RING_ANSWER_RESERVE` is 34 = 16 + 8 + 11 − 1.
- `RingHeader::readable` is sound as a check of the length; the finding is what
  it does *not* check (finding 1).

`abi/src/riscv64.rs`

- `CAUSES` has the 20 codes the test at `abi/src/tests.rs:2191-2232` lists,
  `SCAUSE_INTERRUPT` is bit 63, and `exception_use` classifies every listed
  code and returns `None` for an interrupt bit, a reserved code and a custom
  code above 23. The Kani proof of the equivalence holds for every `scause`.
  Same caveat as ARM64: the values are checked against the repository's own
  pinned list, not against the specification.

`abi/src/start.rs`

- Every record adds up and the offsets are pinned by
  `abi/src/tests.rs:869-1047` and `:1049-1118`: `StartMachine` is 96 bytes
  with `chunks` at 32, `StartMemory` 56, `StartDebug` 56, `StartKindRecord`
  56, `StartImage` 48, `StartBootTimes` 48, `StartModule` 40, `StartProcess`
  40, `StartCore` 32, `StartCrash` 32, `StartShare` 24, `StartNode` 24,
  `StartEntry` 24, `StartFirmwareTable` 24, `StartMemoryRange` 24,
  `StartUntyped` 16, `StartInterrupts` 16, `StartIommu` 16, `StartKept` 16,
  `StartFeedback` 16, `StartIoApic` 8, `StartRole` 8, `StartHeader` 16.
- `RETIRED_WORD_BYTES` is `x86_64::IRQ_TABLE_ENTRIES / 8 == 24`, and the three
  architectures' table sizes are pinned equal by
  `abi/src/tests.rs:2299-2315`, so the division is exact and the coupling
  between one architecture's constant and a shared size is tested (a size
  computed two ways, but guarded).
- `START_MAGIC`, `START_VERSION`, the fixed slots 1-15 and `START_SLOT_FIRST`
  = 16, `START_FREE_SLOTS`, every flag, and slot 0 never used (which is what
  `SlotAddr::own(0) == NONE` encodes).
- The flags of `StartNode`, `StartUntyped`, `StartCore` and `StartMemory` are
  disjoint bits, and `StartDebug`'s 52 + 4 = 56 agrees with its comment (unlike
  `StartCore`, finding 10).

`abi/src/tests.rs`

- The 70-odd pinning tests agree with the code I read value by value,
  including the ones I could check arithmetically: `USER_RANGE_END == 255 <<
  39`, `GEOMETRY` valid and its `user_end` exactly `half - root_entry`,
  `RFLAGS_USER_MASK` = CF, PF, AF, ZF, SF, TF, DF, OF, AC, ID and
  `RFLAGS_FIXED` = bit 1 and IF, `DR7_USER_MASK` = L0-L3 and bits 16-31,
  `REGS_WORDS` = 26, `IRQ_TABLE_ENTRIES` = 192 = 239 − 48 + 1, the bandwidth
  values, the firing instants, `ClockPage` = 40, the ring reserve, the fence
  record index, the debug area, the crash records, and the ownership and
  member words. Nothing in it is weakened, and no test contradicts a value of
  my lot.

`abi/src/x86_64.rs`

- `GEOMETRY` is `valid` and its boundary is tight (`user_end == (1 << 47) -
  (1 << 30)`), `canonical` agrees with `Geometry::canonical` on the reference
  values the tests pin, `msi_remapped`/`msi_direct` (the handle is below 2^16
  exactly when the core number is below 341, `IRQ_MAX_CORES_REMAPPED`, which
  the tests check from both sides), `dr7_valid`, `rflags`, `KERNEL_PORTS`,
  `PCI_CONFIG_PORTS`, `UART_PORTS`, the register indices and `REGS_CANONICAL`
  (rsp and rip and the two segment bases).
- `PCI_CONFIG_PORTS`/`KERNEL_PORTS` are pure values; whether `ioport_check`'s
  caller also refuses the platform ports to a node without the plain role is
  the model's business, and the model does it (`model/src/debug.rs` and
  `model/src/roles.rs`), so nothing is missing in the values themselves.

## Observations that are not findings

- `aarch64::exception_use` and `riscv64::exception_use` are called by nothing
  in the model: `grep -rn "exception_use" model/src` returns nothing, and
  `Model::fault` takes a `FaultKind` directly (`model/src/faults.rs:21`). So
  the classification of a hardware exception — the one place where a mistake
  means a user program is taken for a bug of the kernel (`NotThread` accuses
  the node) — is covered only by the value tables of `abi/src/tests.rs`. I
  could not attack it for want of the architecture manuals; I state the gap.
- A hostile node's beacon (`acked`, `maps`) and its member word are its own
  memory, so `machine::barrier` and `Ownership::may_take` decide on data the
  other node writes. That is the contract's design (a node's words are single
  writer); it does mean "no memory is freed under a node that still maps it"
  cannot hold against a lying node. I did not hunt for a case where an honest
  node is hurt by it.
- `model/src/irq.rs:78-79` computes the retired bit of a vector as
  `core * IRQ_TABLE_ENTRIES + vector - IRQ_VECTOR_FIRST` and truncates it with
  `as u16` before looking the bit up. The value is below 2^16 exactly when the
  core number is below 341, which is checked only when the machine has
  interrupt remapping (`remapped_core`); a machine without remapping may have
  a core of a number up to 1,023 (`NODES_MAX`) and the lookup then reads
  another bit. Not run: no retired bit is ever written without a unit that
  confirms an invalidation, so I could not make the truncated lookup change an
  outcome; I report the latent truncation for whoever gives it a test.
- The lot's files are large but a few hundred lines are values and their
  pinning tests; I read every line of the eleven files and every line of the
  model I cite.

## What I did not examine

- `abi/src/tests.rs` line by line against the ARM, RISC-V and Intel manuals:
  not allowed to look outside the repository, so the architecture values are
  checked against the lists the repository itself pins (the `esr.h`/`csr.h`
  copies) and against the internal rules of the code, not against the source
  of truth.
- The rest of the model beyond what the abi's functions reach: `caps.rs`,
  `cores.rs`, `locks.rs`, `nodes.rs`, `roles.rs`, `sched.rs`, `system.rs`,
  `table.rs`, `tasks.rs`, `threads.rs`, `units.rs`, the invariant checker in
  `check/`, and the scenarios other than the one I added. In particular
  `member_transition`'s caller (the gate of a node's state), the barrier's
  caller (R6) and the gate over page tables (`G2`/`G3`/`G4`) are only reached
  as far as my findings needed them.
- The three architectures' interrupt-controller details (GIC, IMSIC, IOAPIC)
  beyond the constants of my lot.
- Kani, Miri and the sanitizer (CI only, not in Nix). My tests are ordinary
  `cargo test` runs, debug and release where the difference matters.

## How to rerun

```
export PATH=/nix/var/nix/profiles/default/bin:$PATH
cd /private/tmp/dodos-pr3-v2-A-deepseek
nix develop -c cargo test -p dodos-abi --test review_v2a          # 9 passed
nix develop -c cargo test --release -p dodos-abi --test review_v2a # 8 passed
nix develop -c cargo test -p dodos-model --lib attack_v2a          # 1 passed
nix develop -c cargo test -p dodos-model --test attack_boot        # FAILED: the panic of finding 2
```

The release run names these eight, all green:
`no_valid_geometry_holds_a_fourth_page_size`,
`canonical_on_an_invalid_geometry_is_true_for_every_address`,
`module_frames_of_a_length_near_the_top_of_the_space_has_no_frames`,
`a_device_entry_of_a_size_below_128_bytes_loses_bits_of_its_base`,
`an_attach_word_accepts_a_root_that_is_aligned_to_four_kilobytes_only`,
`firing_instant_at_the_limit_of_the_clock_is_above_its_window`,
`trace_index_of_a_ring_of_no_entry_is_a_division_by_zero`,
`bandwidth_and_a_remote_reference_panic_on_the_inputs_their_documentation_excludes`.
The four `debug_assertions`-only tests are absent there, and the release arm of
`canonical`, of `module_frames` and of `firing_instant` take the place of their
debug arms. The five tests that hold in both builds are present in both runs.

Files added in the work copy: `abi/tests/review_v2a.rs`,
`model/tests/attack_boot.rs`, `model/src/scenarios/attack_v2a.rs`; one line
added to `model/src/scenarios/mod.rs` (`mod attack_v2a;`). Nothing else was
changed, and nothing in the shared clone.

The whole `dodos-abi` package is green with my file added:
`nix develop -c cargo test -p dodos-abi` prints 74 passed (the library), then
2 (`review6`) then 9 (`review_v2a`). I did **not** run the whole
`dodos-model` suite: only the one scenario and the one boot test named above,
so I cannot say that my one-line registration in
`model/src/scenarios/mod.rs` leaves every other model test passing, though it
adds a module and changes nothing else. Exercise that if the work copy is
reused.
