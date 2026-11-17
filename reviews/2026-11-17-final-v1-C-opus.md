# Review of lot C (Opus), PR `model` at 6312868

Repository read at `/private/tmp/dodos-pr3-final` (unchanged). Experiments
ran in a copy, `/private/tmp/dodos-pr3-C-opus`.

- `nix develop -c ./verify` on the unchanged copy: exit 0. Every `test result`
  line says `ok` (for example `523 passed` for the lib tests).
- The probes are in one added file, `model/src/scenarios/review_c.rs`, and
  registered in `scenarios/mod.rs`, in the copy only. Command:
  `nix develop -c cargo test -p dodos-model --lib review_c -- --nocapture --test-threads=1`.

Severities: **stop** (stops the merge), **fix** (should be fixed),
**question**.

---

## model/src/boot.rs

### 1. fix: inputs of the machine that panic instead of being refused

The start-up has a `Refusal` for values out of range (`MachineValues`,
`Floors`, …). Several values are never checked and end in a panic or an
arithmetic overflow:

| Input (edit of `Machine::example()`) | Result | Line |
|---|---|---|
| `floors.floor_node = 0` | panic `index out of bounds: the len is 0 but the index is 0` | `boot.rs:1105` `let start_at = untypeds[0].0;` (also `floor[0]` at 1213) |
| `cores[1].kind = 7` (only 1 kind) | panic `index out of bounds: the len is 1 but the index is 7` | `boot.rs:434` `self.kinds[usize::from(self.core_list()[core].kind)]` |
| `phys_bits = 20` (below the chunk shift) | panic `attempt to subtract with overflow` | `boot.rs:791` `1u64 << (self.phys_bits - geometry.chunk_shift())` |
| `phys_bits = 30` (usable memory above 2^phys_bits) | panic `index out of bounds: the len is 512 but the index is 2054` | `boot.rs:799` `owners[(at / chunk) as usize] = …` |
| `boot_nodes = Some((2, vec![(0,1), (u64::MAX/32, 1)]))`, `accept_unfenced = true` | panic `attempt to multiply with overflow` | `boot.rs:424` `.map(\|i\| (64 * window + i) as usize)` |

I ran each one with `probe_boot_inputs` and the command above; the panics
quoted are the ones it printed. `phys_bits = 64` aborted the process
(`memory allocation of 70368744177664 bytes failed`), so I removed that case.
`node_start` checks its window against `CORE_WINDOWS` (`nodes.rs:142`).
`BootNodes` is not checked in the same way.

### 2. fix: the size of the start-up page uses old sizes of two records

`start_page_bytes` (`boot.rs:570-592`) lists the bytes of each entry. Two
of them do not match the ABI:

```rust
        40,          // 7th item: entry BootTimes
        ...
        80,          // 15th item: entry Machine
```

The ABI says `assert_eq!(size_of::<StartBootTimes>(), 48);` and
`assert_eq!(size_of::<StartMachine>(), 96);` (`abi/src/tests.rs:1066,
1094`). The doc of `StartMachine` reads "(96 bytes since D-137, 88 since
D-135, 80 since D-129)" (`abi/src/start.rs:339-340`), so 80 is the size of
D-129. I matched the list to the 21 required kinds of `StartKind`
(`start.rs:66-91`; the four optional ones are pushed after it). The other
fixed sizes agree with the ABI: Untyped 16, Cores 32, Kept 16, Memory 56,
Roles 8, Image 48, Kinds 56, Crash 32, Iommu 16, Feedback 16, Framebuffer 32.
The page comes out 24 bytes short. So `StartPage` (more than 63 pages) and
the number of pages of slot 9 can be off by one page at the edge. No test
caught it.

### 3. question: `Refusal::Floors` does not document one of its causes

`boot.rs:845` `if self.floors.plain_roles >= ROLES_PLAIN_MAX { return
Err(Refusal::Floors); }`. The doc of `Floors` (`boot.rs:474-476`) names
floors, reserves, kept memory, *k* and the times, but not the number of
plain roles.

## model/src/cores.rs

### 4. fix (minor): a duplicated statement and an arm that cannot run

- `cores.rs:779-781`:
  ```rust
        let part = &mut self.cores[position];
        part.silent = false;
        let part = &mut self.cores[position];
  ```
  The second `let` does nothing. It looks like a leftover from an edit.
- `cores.rs:394` `Flush::Nothing => {}` cannot run, because
  `invalidate_on` already returns on `Flush::Nothing` at line 369.

I found nothing else in cores.rs. I checked `start_request`, `start_barrier`
(its only caller, `caps.rs:518`, calls it again while the epoch is not
covered), `answer_pending`, `watch_own_cores` (the subtraction
`now - stale` comes after the `now >= watched.1 + stale` check, and
`watched.1 >= 1`) and `core_entered`.

## model/src/grants.rs

### 5. fix: a check that can never be true, in `node_send` and `irq_bind`

`grants.rs:178` (the doorbell of `node_send`) and `irq.rs:224` both read
`if self.remotes.contains_key(&object) { return Err(Error::Invalid); }`
for an object that `held(…, ObjectKind::Notify, …)` has just checked is a
notify. `remotes` gets entries only in `place_remote` (`grants.rs:484`),
and those are always `ObjectKind::Frame` (`grants.rs:469`). So the branch
cannot be taken. A reader takes it for a rule of the contract. In
`irq_bind` it even comes after the `busy` check, as if the order mattered.

### 6. question: the "anchor with a descendant" branches look unreachable, and one contradicts its doc

`release_received` (`grants.rs:825-828`):
```rust
        let anchor = self.anchor(grant);
        if anchor.is_some_and(|a| self.caps[&a].children.is_empty()) {
            self.free_with_anchor(grant);
        }
```
Its doc says "it frees the entry if its anchor has no descendant,
otherwise the anchor stays, held by nobody". "Held by nobody" means the
entry is freed and the anchor kept, which is what `free_with_anchor` does.
But the code does not free the entry when the anchor has children (or when
the anchor is missing): the grant entry stays `Live`. Also, an anchor is
made only in the kernel space (`make_grant`), which no user slot address
reaches. I found no `derive` from it. So `children` is probably always
empty, and the branches at `grants.rs:131`, `grants.rs:826` and
`nodes.rs:1555` would be dead. Which reading is meant?

### 7. question: a comment says "wait", the code returns `again`

`grants.rs:667-675`:
```rust
        // A `Revoke` already in flight for this grant: wait for its answer.
        ...
        let Some(thread) = caller.filter(|_| !in_flight) else {
            return Ok(false);
        };
```
`Ok(false)` means `again` with no wait (see the doc of `revoke_anchor`).
The thread does not wait for the answer.

### 8. fix (minor): the serial rule of a grant is written twice, with a magic mask

`grants.rs:115` `(entry.serial + 1) & 0x3FFF_FFFF` and `nodes.rs:1434-1435`
(R6, phase 2) `.insert(grant, (entry.serial + 1) & 0x3FFF_FFFF)`. They are
the same rule, written by hand twice, and the 30-bit width (bits 12-41 of
the `Revoke` word, `abi/src/ring.rs:56-59`) has no named constant.

## model/src/rings.rs

### 9. stop: a user ring is served 16 *messages* per interrupt, not 16 *entries*, and its test cannot tell the difference

The contract bound is in entries. The ABI says `/// Entries of a user ring
served per interrupt.` `pub const RING_USER_STEP: u64 = 16;`
(`abi/src/ring.rs:26-27`). The module doc says "at most `RING_USER_STEP`
entries per interrupt" (`rings.rs:10-11`), and so do `serve_user_rings`'s
doc ("at most 16 entries per ring", `rings.rs:555`) and `Ipi::Ring` ("after
a step of 16"). But `consume` counts messages (`rings.rs:487-513`):
```rust
        while served < step {
            ...
            self.set_consumed(from, user, consumed + length);
            served += 1;
```
A `Send` can take up to 10 entries (`ring.rs:15-16`), so one interrupt can
serve 160 entries of one ring.

The test that guards the rule,
`mistral.rs:408 f14_one_interrupt_serves_at_most_sixteen_entries_of_a_user_ring`,
injects 17 `Signal`s of one entry each. For those, messages and entries are
the same, so the test cannot fail on this mistake.

How I know: `probe_one_interrupt_serves_sixteen_messages_not_sixteen_entries`
injects 17 `Send`s of 8 words (2 entries each) from node 1 to node 0 and
fires one `Event::Ipi { node: 0, core: 0 }`. It printed `entries per message
2, consumed in one interrupt 32`.

### 10. question: `resume_step`'s doc says it consumes the rings, but it does not

`nodes.rs:1658-1661`: "...then the rings that waited are consumed under the
check, and the node becomes live." `resume_step` (`nodes.rs:1662-1726`)
never consumes a ring. The kernel rings are served later by
`serve_kernel_rings` in the next reserve step, and a user ring only at an
`Ipi::Ring`. `receive_interrupt` (`cores.rs:752-757`) drops an interrupt
when every core of the node is silent, and `serve_user_rings` drops it when
`consumes()` is false (not `ready`). So I could not convince myself that a
user ring that holds entries across a seal and resume is ever served again.
The sender sends the interrupt only when the ring goes from empty to not
empty (`rings.rs:337-354`). I did not build a scenario that reaches it.

## model/src/irq.rs

### 11. fix (minor): the formula of the remapping handle is written four times

The rule "core number × 192 + (vector − 48)" is computed separately at
`irq.rs:77-78` (with `saturating_sub`), `irq.rs:155-156`, `irq.rs:288-289`
(`line_target`) and `irq.rs:434-435` (`handle_of`). Its inverse is at
`units.rs:259`. `irq_claim` computes it twice under the same name `handle`,
once from `self.cores[position].number` and once from the argument `core`.
The values are equal today, but `handle_of` exists and could be used in
all four places.

### 12. question: the order of checks in `irq_claim`'s comment

`irq.rs:30-32` says "the source as its format allows, a GSI that an IOAPIC
serves (judged with the source), then the vector". The code checks the core
number between the GSI and the vector (`irq.rs:43-48`, "Then a core
number…"). If the contract's order is source, GSI, core, vector, the first
comment should say so.

## model/src/nodes.rs

### 13. fix: R1's unit timeout is judged on the monotonic clock, all the others on the clock of membership

The README says the clock of membership leaves out the debugger stop for
"the waits (a request's start, a unit's submission, a start, a hand-over)".
`unit_step` judges a submission on that clock:
`at + IOMMU_WAIT_NS <= self.membership_now()` (`units.rs:687, 702`, with
`at = self.membership_now()` at `units.rs:403, 544`). R1's submission,
added by pass 21, is judged on the monotonic clock instead:
```rust
                && self.table.units[&role]
                    .queue
                    .iter()
                    .any(|&(s, at)| s == serial && at + dodos_abi::IOMMU_WAIT_NS <= self.now)
```
(`nodes.rs:1093-1096`). The queue's instant comes from `submit_for`,
`let now = self.now;` (`units.rs:439, 482`). After a debugger stop between
the submission and the check, R1 judges the unit failed earlier than every
other wait would. Also, `unit_deadline` (`units.rs:738-752`) does not list
R1's submission, so `reserve_due` has no instant for it. I found this by
reading, not by a run.

### 14. question: `start_image` is state that nothing reads

`nodes.rs:257-260`:
```rust
        self.start_image = (image == dodos_abi::NODE_IMAGE_REPLACEMENT, module);
        if mode == NODE_START_RESUME {
            self.table.resume_replacement[target as usize] = self.start_image.0;
        }
```
`start_image` (`lib.rs:1143`) is read nowhere else (grep `start_image`),
and its `.1` (the module) is never read. For a fresh start, the image and
the module are checked and then dropped: the started node always builds
from `machine.segments` (`system.rs:805`). A node that drives two starts
also overwrites the field. Either it is dead and should go, or a rule of
the replacement image or the module is missing.

### 15. fix (comment): the reserve step's doc gives a wrong order and a bound the code does not keep

`nodes.rs:1925-1929`: "at most 32 units of work, in this order: …, the
reclaims and R6, the roles, the units, the kernel rings, …". The code runs
`unit_step`, then `serve_kernel_rings`, then `roles_step`
(`nodes.rs:1955-1957`), and the inline comment explains why the rings come
before the roles. Also, `start_step`, `fence_step`, `unit_step`,
`send_pending` (up to 32 more), `observe_needed` and
`accuse_with_evidence` take nothing from `units`. So "at most 32 units"
holds only for the reclaims, R6, `unpin`, the rings, the rebuilds and the
seal.

### 16. question: R4's audit accepts any reserve's word

`audit_block` (`nodes.rs:1273-1287`), whose doc says "every ownership word
it covers still reads taken by this node with its generation":
```rust
                    && (w.owner() == me || matches!(w.owner(), dodos_abi::Owner::Reserve(_)))
```
Any reserve passes, including one whose role this node does not hold. R6
checks `self.table.holds_reserve(node, j)` (`nodes.rs:1393`). If a block of
this node may cover only its own reserves' chunks, R4 checks less than its
doc says.

## model/src/rings.rs, model/src/roles.rs: reports

### 17. question: `Item::Handle` is never built

`rings.rs:63-75` documents a `Report` item as "a device …, a remapping
handle it claimed, or a line …", and `REPORT_ITEMS` is sized for it.
`items()` (`roles.rs:590-630`) builds only `Item::Device` and `Item::Line`.
The rebuild ignores `Item::Handle(_) => {}` (`roles.rs:547`). Grep finds no
construction of `Item::Handle` in `model/src`. The rebuild does not touch
`unit.remap` either. So either the handles are left out of the model on
purpose (say so where the item is documented), or the rebuild of the
remapping entries is missing.

## model/src/roles.rs

### 18. stop: a second `role_hand` on a unit role in hand-over leaves the first caller waiting for ever

`role_hand` for a unit role (`roles.rs:139-152`):
```rust
                self.handing.insert(
                    role,
                    Handover { target, started: self.membership_now(), caller: Some(thread) },
                );
                live(&mut self.threads, thread).wait = Wait::Hand(role);
```
While steps 1 to 4 run, the role word still reads held by this node
(`hand_step` writes *handing* only at step 4). So a second `role_hand` from
another thread passes every check and replaces the `Handover`. `hand_step`'s
`finish` wakes only `hand.caller`, the second thread (`roles.rs:256-267`),
and nothing else ends `Wait::Hand` (`ipc.rs:661` only clears `caller` in
`unlink`). The first thread waits for ever. That breaks "Every system call
has a bounded duration" (`AGENTS.md`). `hand_all_units` guards against this
case with `!self.handing.contains_key(&role)` (`roles.rs:195`). `role_hand`
does not.

How I know: `probe_a_second_role_hand_orphans_the_first_caller`. It uses
three nodes, node 1 holds the IOMMU role, and node 1 gets a second thread.
The unit is held undrained as in `mistral.rs:265-269`. Both threads call
`RoleHand` to node 2, then the unit drains and 50 ms run. It printed:
```
second role_hand: Ok(Waits)
after: first waits Hand(0), second waits None, role Held
first woken None, second woken Some(Ok(Epoch(2)))
```
The hand-over completed for the second caller, and the first is still in
`Wait::Hand(0)`.

### 19. question: the rebuild keeps an entry whose report does not match its attach word

`rebuild_step` (`roles.rs:498-505, 521-526`) keeps an old context entry if
a report of its node names the device, whatever root the report names. It
rewrites the entry only if `rebuilt_attach` holds (the attach word reads
*attached* with the reported root). If a node reports the device with a
root that the attach word does not hold, the old entry, with its old
generation, is neither cleared nor rewritten. The comment says "keep the
entries that match, rewrite those that differ … clear every other entry no
report claims". Is a claimed entry that matches nothing meant to stay?

## model/src/units.rs

### 20. question: `confirmed` confirms more than its doc says, and it mutates

`units.rs:487-496`: "A unit that works confirms what was submitted before
the current instant's check". The code clears the whole queue, including a
submission made in the same event, and returns true. It is also the only
`&mut self` function among the predicates it sits with (`unit_failed`,
`unit_work`). It is called inside `&&` chains (`nodes.rs:1092`,
`roles.rs:280`), where the side effect is easy to miss.

## model/src/system.rs

### 21. fix (minor): a duplicated comment paragraph

`system.rs:645-651`: the ARM64 comment says the same thing twice ("ARM64:
SDEI event 0 to a core whose kernel registered its handler, which completes
the event and calls `CPU_OFF`." and then "ARM64: SDEI event 0 to a core
whose kernel registered its handler; the handler writes `parked` …").

### 22. question: a fresh start whose `Model::start` refuses leaves its core `Entering` for ever

`system.rs:804-808`:
```rust
            let Ok((mut model, _)) =
                Model::start(&self.machine, &self.layout, table, node, &joining)
            else {
                return;
            };
```
`Model::start` can refuse with `StartPage`, because the node entry grows
with the number of cores. When it refuses, the core stays
`Hardware::Entering` with no model, and nothing is written or traced. The
starter's `START_NS` ends the start, but the core is stranded in a state no
event leaves.

---

## Files read whole

- `model/src/boot.rs`
- `model/src/cores.rs`
- `model/src/grants.rs`
- `model/src/irq.rs`
- `model/src/nodes.rs`
- `model/src/rings.rs`
- `model/src/roles.rs`
- `model/src/system.rs`
- `model/src/units.rs`

I also read `AGENTS.md`, `model/README.md` and the two skills in full.

## Read in part, only as far as needed

- `model/src/lib.rs`: lines 1-400, 740-760, 1138-1145.
- `model/src/caps.rs`: `release`, `return_watermark`, the aspace
  destruction step.
- `model/src/ipc.rs`: `check_header`, `unlink`.
- `model/src/scenarios/mod.rs`, `units.rs` (head), `mistral.rs` (F14 and the
  undrained unit), `pass19.rs` (one test).
- `abi/src/ring.rs` (constants, `message_entries`, `RingHeader`),
  `abi/src/machine.rs` (`floors`, `BootNodes`, the membership times),
  `abi/src/start.rs` (`StartKind`, `StartBootTimes`, `StartMachine`), and the
  size asserts of `abi/src/tests.rs`.

## Not read

The rest of `model/src` (`blocks.rs`, `check*`, `debug.rs`, `faults.rs`,
`locks.rs`, `memory.rs`, `sched.rs`, `table.rs`, `tasks.rs`, `threads.rs`,
most scenario files), `model/tests/`, and the rest of `abi/`.

Not checked:

- The contract text, which is not in this repository. Where I name a rule of
  the contract, I took it from the ABI docs, the README or the code comments.
- Whether the slot count of the start-up space (`boot.rs:1104-1128`) uses
  the right physical base for every copied module. `frames_of(start_at, …)`
  uses the untyped's base for each one, while `build` places them one after
  another. My probe with two large writable segments showed no harm,
  because the count is rounded up to 128.
