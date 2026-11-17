# Verification of model review 10 (`2026-11-17-model-review-10-deepseek.md`)

Verification of `/Users/btw/Documents/repos/Docs/reviews/2026-11-17-model-review-10-deepseek.md` against `architecture/kernel-interface.md` (`Docs` at `52c3eab`) and `dodos-kernel` branch `model`, head `073ae9e` (cloned to `/private/tmp/dodos-kernel-verify10`).

Baseline: `nix develop -c ./verify` in `/private/tmp/dodos-kernel-verify10` exits 0 with 47 `test result: ok` lines.

---

## Major findings (1 to 5) and Item 3

### Finding 1 (Major) — Confirmed

- **Claim:** `let_go` (`model/src/locks.rs:414-423`) runs a scripted `Holder`'s event via `apply_once` while the contending call holds earlier locks in `round` (`locks.rs:432-437`), never checks `self.check()` on the holder's trace before `record_rounds` (`locks.rs:541-551`) overwrites `self.locks.steps`, and allows both cores to hold the same lock simultaneously.
- **Contract check:** `architecture/kernel-interface.md:652` ("A core waits for a lock only in the order by kind. A lock that a call finds by reading an object it already holds locked, and that comes earlier in the order than a lock it holds, it **tries**: a try never waits.") and `:660` ("**Why no call deadlocks under it.**" — note the report cites `:681`, which is `#### Unlike cores`).
- **Reproduction:** Added a test in `model/src/scenarios/pass18.rs` using `l2_delivery()` with a `Holder { tries: 0, then: Some((third, Syscall::ThreadCancel(s(300), 7))), core: 1, .. }` placed on the `Endpoint` lock (which `Call` waits on via `Step::Lock` after already holding `Segment` and `Thread(k.t)`). Running `nix develop -c cargo test -p dodos-model repro_finding_1` passed (`1 passed; 0 failed`): `round` pushed `Step::Lock(Endpoint)` and `held.push(Endpoint)`, then `let_go` ran `apply_once(third, cancel)`, which acquired `Segment`, `Thread(300)`, `Endpoint`, and `Reply` while core 0 held `Segment` and `Endpoint`, and the holder's trace in `self.locks.steps` was never checked before `record_rounds` replaced it. The same happens in `contend`'s `never_again` loop (`locks.rs:495-499`) for any lock in `second` not in `first[..=failed]`.
- **Correction check:** The report proposes `self.contend(Contended::Call(thread, call))` or refusing a `Holder` whose `dry_found` contains a lock the caller holds at the wait. Running `self.contend` directly is incomplete because `self.contended` does not include the contending core's currently `held` locks (so the holder's tries on them would still succeed without failing), and refusing `dry_found` overlaps with `held` would wrongly forbid a valid L2 execution where core 1 *tries* a lock in `held`, fails, and restarts. The right fix in `locks.rs` (`let_go` / `round`) is: run the holder's event through `contend` with the caller's `held` locks temporarily in `self.contended` (as `tries: 1, then: None`, representing core 0 holding them) and run `self.check_locks()` (or `self.check()`) on the holder's trace before returning to the caller's rounds.

### Finding 2 (Major) — Confirmed

- **Claim:** In `again_of_tries` (`model/src/locks.rs:558-582`), the escalation loop `for lock in held { self.let_go(lock); }` (`locks.rs:566-569`) is dead in the existing tests (because `contend` at `locks.rs:483-486` already calls `let_go` on `known = first[..=failed]` before the second round), never reads `Holder::entered` (`locks.rs:97`), and removing the loop (mutation `m08`) leaves the whole suite green.
- **Contract check:** `architecture/kernel-interface.md:658` ("it **escalates**. It releases every lock it holds, takes the node's **quiet word** ..., raises the node's kernel epoch by one, **waits until the entry word of every other core of the node reads 0 or at least the new epoch**, runs the call alone, taking its locks in the order ..., and clears the word.").
- **Reproduction:**
  - Applied mutation `m08` (`for lock in held { self.let_go(lock); }` replaced by `let _ = held;` at `model/src/locks.rs:566-569`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines.
  - Checked `pass18.rs:797-856` (`under_l2_a_third_again_of_tries_escalates_to_the_quiet_word_and_runs_alone`): the third call inserts `Holder` on `first_try(&k, k.t, &call)`, which `contend` drains at `locks.rs:484-486` before `again_of_tries` is entered. Adding a temporary test with an unrelated `Holder` on `LockId::Core(1)` (`core: 1, entered: k.m.kernel_epoch, tries: 0, then: None`) confirmed that without `m08`, `again_of_tries` calls `let_go` (draining `contended` to `0`) without ever reading `entered` or recording any entry-word check; with `m08`, `LockId::Core(1)` stays in `contended` across the escalated call (`repro_finding_2` ran `1 passed; 0 failed` cleanly before reverting).
- **Correction check:** The report proposes scripting a holder on a lock the call reads whose try does not fail (e.g., another core's timer) and checking in `check/node.rs` that `Step::Quiet(true)` is followed only by the call's locks with every other holder's entry word read first. Two refinements are needed: (1) a non-failing holder on a lock *after* `failed` in `first` is only tried, not removed, if it survives to round 2 and round 2 still fails — an unrelated holder on another core's lock (e.g., `LockId::Core(1)`) with `entered` set to the old epoch directly tests `again_of_tries` draining `contended` and waiting for entry words; (2) `again_of_tries` (`locks.rs:563-577`) and `Step`/`check/node.rs` should actually inspect `Holder::entered` (via `entered_before` or a recorded `Step` for waiting on entry words) and enforce in `check/node.rs:349-356` that no lock or event step under `Step::Quiet(true)` runs while any other core has an entry word `< epoch` (nonzero). Note also that `check/node.rs:342` already forbids `Step::Try` and `Step::TryFailed` under `quiet`, so `Step::Lock` is the only lock step allowed under `Quiet(true)`.

### Finding 3 (Major) — Confirmed (with one refinement on `m15`'s harm)

- **Claim:** `Model::kernel_epoch` (`model/src/lib.rs:1076`), raised in `locks.rs:565` (escalation) and `caps.rs:490` (`release`), has no invariant in `check.rs`/`check/`; `abi/src/machine.rs` has no constant for word 6 of an untyped's root slot (`model/src/lib.rs:590` keeps `Untyped::ready` instead); and mutations `m09` (no epoch raise on escalation) and `m15` (epoch raised on every destruction under L2 instead of only `live == 1`) both leave `./verify` green.
- **Contract check:** `architecture/kernel-interface.md:657` ("When the last object of an untyped is destroyed, its watermark becomes *ready to return*: the destroying core raises the node's **kernel epoch** (one word of the node block) by one and writes the new value in word 6 of the untyped's root slot"), `:658` ("raises the node's kernel epoch by one"), and `:1910, 1925` (`abi/` gives the 8-word slot layout as constants, with word 6 holding the ready epoch for an untyped root slot).
- **Reproduction:**
  - Inspected `abi/src/machine.rs:48-56` and `model/src/check*.rs`: `abi/src/machine.rs` defines only word 0 `SLOT_UNTYPED_*` constants (no constant for word 6), and `grep kernel_epoch` in `model/src/` finds reads only in `caps.rs:492` (`release`) and `pass18.rs:1069, 1088` (no reader in `check.rs` or `check/`).
  - Applied `m09` (`locks.rs:565` `self.kernel_epoch += 1;` removed) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines.
  - Applied `m15` (`caps.rs:489` `if watched && self.untypeds[&untyped].live == 1 {` replaced by `if watched {`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines.
  - Note on the report's prose for `m15`: the report claims that raising `kernel_epoch` on a non-last destruction causes "a core that entered *after* the raise [to be] read as 'before' it, so the watermark returns later than `:657` allows." That mechanism is slightly off: `release` stores `epoch = self.kernel_epoch` *after* the increment into `untyped.ready`, so any core entering after the destruction reads `>= epoch` and is not delayed; the actual bug in `m15` is raising `kernel_epoch` at an event `:657` forbids (non-last destruction), which no invariant or test catches.
- **Correction check:** The report proposes (1) an invariant that word 6 of an untyped's root slot is `0` or the epoch at which its watermark became ready, (2) an invariant that `kernel_epoch` only increases by 1 at `:657` and `:658`, and (3) a constant in `abi/` for word 6. To make (1) and (2) concrete in the model: check `kernel_epoch` step-by-step against the event's transitions (in `Model::check_event` / `Model::check_memory`) and assert in `pass18.rs:797` and `pass18.rs:1058` that escalation raises `kernel_epoch` by 1 while destroying a non-last object (`live > 1`) leaves `kernel_epoch` unchanged; add `SLOT_UNTYPED_READY_WORD: usize = 6` (or equivalent offset/word constant) to `abi/src/machine.rs`.

### Finding 4 (Major) — Confirmed

- **Claim:** `Model::core_entered` (`model/src/cores.rs:736-741`) sets `part.silent = false` on a resumed core while throttled contexts on that core may have replenishment instants in the past (`at <= self.now`), causing invariant 43 (`model/src/check/sched.rs:77-78`) to fail immediately with `"43: parameters and state of a context"`.
- **Contract check:** `architecture/kernel-interface.md:504` ("otherwise it is **throttled** until its replenishment instant") and `:562-563` ("If that instant is not after now, it is replenished at once").
- **Reproduction:** Both a direct `Model::core_entered` test and a full `System` seal-and-resume test reproduce it:
  1. Direct test (DeepSeek's `repro_finding_4_deepseek`, tested on `one_node(Arch::X86_64, 1)`): placing the first thread on core 0, setting `suspended = true`, `remaining = 0`, `throttled = Some((now, 1))`, `queue = Some(Queued { queue: Queue::Sleeping, key: now, entered })`, and `cores[0].silent = true`, `k.m.check()` returns `Ok(())`; calling `k.m.core_entered(0)` and then `k.m.check()` returns `Err("43: parameters and state of a context")` (`1 passed; 0 failed` when asserting that error).
  2. Full `System` test (`repro_finding_4_via_system` on `S::two()`): reconfiguring node 1's `START_SLOT_SCHED` on core 1 with `budget: 200_000, period: 10_000_000, class: 1`, calling `m.run(MS)` throttles `c1` (`throttled = Some((10000000, 1))` at `now = 1000000`). Calling `m.ok(0, seal(1))`, `m.settle()` reaches `MemberState::Sealed`, and `m.run(20 * MS)` advances `now` past `10_000_000` while core 1 is silent. Calling `m.ok(0, resume(1))` and stepping `m.sys.events()` one event at a time with `m.sys.check()` after each event (as `scenarios/explore.rs` does) fails immediately after `EntryStep { core: 1 }` (which invokes `core_entered(1)`) with `Err("node 1: 43: parameters and state of a context")`. Note that `m.settle()` alone does not catch it because `System::settle` fires the pending `Timer { node: 1, core: 0 }` right after `EntryStep` before calling `check()`, hiding the intermediate broken state.

  ```rust
  #[test]
  fn repro_finding_4_via_system() {
      use super::pass17::{resume, seal};
      let mut m = S::two();
      m.ok(
          1,
          Syscall::SchedConfigure {
              sched: s(dodos_abi::START_SLOT_SCHED),
              node: node_cap(1),
              core: 1,
              budget: 200_000,
              period: 10_000_000,
              class: 1,
          },
      );
      let c1 = m.sys.node(1).context_of(m.t[1]).unwrap();
      m.run(MS);
      assert!(m.sys.node(1).scheds[&c1].throttled.is_some());
      m.ok(0, seal(1));
      m.settle();
      assert_eq!(m.state(1), MemberState::Sealed);
      m.run(20 * MS);
      m.ok(0, resume(1));
      let mut seen_err = None;
      for _ in 0..1000 {
          let events = m.sys.events();
          if events.is_empty() {
              break;
          }
          let ev = events[0];
          m.sys.fire(ev);
          if let Err(e) = m.sys.check() {
              seen_err = Some((ev, e));
              break;
          }
      }
      assert_eq!(
          seen_err.as_ref().map(|(_, e)| e.as_str()),
          Some("node 1: 43: parameters and state of a context")
      );
  }
  ```
- **Correction check:** The report suggests replenishing past-due throttled contexts either at `core_entered` or at the first event of a resumed core before the check runs. Doing it at the first event would still leave `System::check()` broken right after `EntryStep` (`core_entered`). The right fix is in `Model::core_entered` (`model/src/cores.rs:740-775`): after clearing `part.silent = false`, replenish any throttled context on `position` whose replenishment instant is `<= self.now` (via `self.replenish(context, n)` where `n = sched.throttled.1`) before returning, and keep the two tests above (or the `System` test) as regression tests.

### Finding 5 (Major) — Confirmed (with a missed bug on the uncontended path)

- **Claim:** In `finish` (`model/src/locks.rs:531-535`), removing `t.again_tries = 0;` (mutation `m02`) leaves the whole suite green, because no test executes another call of the thread that succeeds (or returns another non-tries-`again` result) between two `again` results of tries.
- **Contract check:** `architecture/kernel-interface.md:666` (`74011e1` `:658`: "Each thread counts its consecutive results `again` that came from this rule ...; **any other result of a call of that thread sets the count to 0**").
- **Reproduction:**
  - Applied `m02` (`t.again_tries = 0;` replaced by `let _ = t;` at `model/src/locks.rs:534`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines.
  - Testing the missing scenario exposed an additional fault in `Model::apply` (`model/src/lib.rs:1381-1386`): when `self.contended.is_empty()` (which is true after `again_of_tries` drained the contended holder), `Model::apply` calls `self.apply_once(thread, call)` (`lib.rs:1390-1406`) instead of `apply_contended`, and `apply_once` **never resets `t.again_tries = 0`**. Running `repro_finding_5_uncontended_reset` on the unmodified model (`k.call(k.t, call)` -> `Err(Error::Again)`, `again_tries == 1`, `contended.is_empty()`, then `k.ok(Syscall::Yield)`) leaves `k.m.threads[&k.t].again_tries == 1` instead of `0`.
- **Correction check:** The report proposes adding a test with a delivery reaching `again`, a `recv` that succeeds, another delivery whose try fails, and `again_tries == 1`. On the unmutated model, that exact test would fail unless an unrelated `Holder` stayed in `contended` during the `recv`, because `apply_once` misses the reset. The complete correction is: (1) in `Model::apply` (`model/src/lib.rs:1381-1386`), reset `again_tries = 0` on the uncontended `true =>` arm as well (not on `apply_once` directly, which `let_go` calls for a holder thread), and keep `t.again_tries = 0;` in `locks::finish` (`locks.rs:534`); (2) add tests covering both an uncontended non-tries-`again` call (`Yield`/`Recv` with `contended` empty) and a contended non-tries-`again` call (with an unrelated `Holder` in `contended`) between two `again` results of tries, asserting `again_tries == 0` after the intervening call and `again_tries == 1` after the next failed try.

### Item 3 — Confirmed on 3(a), Refuted on 3(b)

#### Item 3(a) (`m24` and `m43`: removing `self.next_sweep` from `reserve_due`, `model/src/nodes.rs:1680-1682`) — Confirmed

- **Claim:** Removing `instants.push(self.next_sweep);` (`m43`, replacing it with `let _ = self.next_sweep;`) and also removing `if self.others_exist()` (`m24`) do *not* survive the suite: both fail `scenarios::membership::a_node_that_does_not_consume_a_message_waiting_in_its_ring_is_accused_stuck` (`model/src/scenarios/membership.rs:414`), even though `pass18.rs:644` (`the_first_core_of_an_idle_live_node_keeps_its_sweep_armed`) stays green.
- **Reproduction:** Applied both `m43` and `m24` separately and ran `nix develop -c ./verify` on each:
  - Both fail `scenarios::membership::a_node_that_does_not_consume_a_message_waiting_in_its_ring_is_accused_stuck` at `model/src/scenarios/membership.rs:414` with `assertion failed: left: None, right: Stuck`.
  - Under both `m43` and `m24`, `pass18.rs:644` (`the_first_core_of_an_idle_live_node_keeps_its_sweep_armed`) still passes (`ok`), because `pass18.rs:653` asserts only `idle_until <= m.sys.now() + m.sys.canonical().sweep_ns`, which an open observation expiry instant already satisfies.
- **Correction check:** Wait until the first observation expires (or inspect the node's own timer queue / `next_sweep`) in `pass18.rs:644`, so `pass18.rs:644` itself fails under `m24`/`m43` instead of relying on `membership.rs:414`.

#### Item 3(b) (`m25`: removing `|| self.reclaims.get(&node).is_some_and(|r| r.generation != g)` at `model/src/nodes.rs:1060`) — Survival confirmed, hole claim refuted (equivalent)

- **Claim:** `m25` leaves `./verify` green, and is a non-equivalent hole (Finding 7) because `nodes.rs:1060` is claimed to be the only reader of `Reclaim::generation`, so a second death skips R2/R3/R5.
- **Reproduction:** Applied `m25` at `model/src/nodes.rs:1059-1063` and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines (survival confirmed). However, `Reclaim::generation` is *also* read at `nodes.rs:942` (`r0`), `roles.rs:407` (`r1`), and `pass18.rs:517`. Adding and running `repro_finding_7_two_deaths_under_m25` under `m25` (killing node 1 in `g1`, restarting in `g2`, granting a frame to node 0 in `g2`, forcing a stale `Reclaim` for `g1` onto node 0 right before the second kill, and killing node 1 again) passed cleanly: `reclaim_step` calls `self.r0(1, g2)` (`nodes.rs:1066`), where `r0` (`nodes.rs:942`) sees `reclaim.generation != g2`, resets `*reclaim`, and runs R2, R3, R4, and R5 for `g2`, removing node 0's remote capability. Because `clear_step` (`nodes.rs:1794`) only runs for `MemberState::Fenced` (after `r0`), `roles.rs:407` also checks `reclaim.generation != g`, and `check*.rs` never reads `self.reclaims`, `m25` is **equivalent** on reachable states (see Finding 7 below).

---

## Other findings (6 to 18)

### Finding 6 (Medium) — Confirmed (with line-number and fix-mechanism corrections)

- **Claim:** Under L2, the model locks a woken waiting thread and an `Attached` reply object by their own locks (`Thread`, `Reply`) rather than guarding wait fields and attached reply objects strictly by the lock of the waited-on object (`Endpoint`, `Reply`, `Notify`), and the checker accepts both. (Note: `locked!(crate::Thread, Thread)` and `locked!(crate::ReplyState, Reply)` are at `model/src/locks.rs:190` and `:192`, not `:192` and `:194`.)
- **Contract check:** `architecture/kernel-interface.md:661` (`74011e1` `:653`: "The fields of a thread that waits on an object, which a wake changes ... are guarded by the lock of the object it waits on ..., not by the thread's own lock ... The reply object attached to a thread that waits to receive is guarded in the same way, while it is attached, by the lock of the endpoint that thread waits on").
- **Verification:** Inspected `locks.rs:190,192`, `locks.rs:680-694`, `lib.rs:1885` (`wake`), `ipc.rs:466,474,642-656`, and `pass18.rs:1000-1013` (`under_l2_notify_bind_takes_the_endpoint_then_the_notify_and_tries_neither`). `wake`, `serve`, and `unlink` call `locked(&mut self.threads, ...)` and `locked(&mut self.replies, ...)`, emitting `LockId::Thread` and `LockId::Reply` (so `pass18.rs:1011-1013` explicitly excuses the resulting `Try(Thread)` / `Try(Reply)` steps as an "over-approximation"), and `Snapshot::changed` (`locks.rs:680-694`) unconditionally maps any `threads`/`replies` diff to `LockId::Thread`/`LockId::Reply`. Because `Thread < Endpoint < Reply`, a hypothetical buggy wake changing a waiting thread while holding only `LockId::Thread` (without `Endpoint`) would also pass `check/node.rs`.
- **Correction check:** The report proposes making `Locked::lock` for `Thread` and `ReplyState` return `None` while the thread waits. That signature (`fn lock(id: ObjId) -> Option<LockId>` at `locks.rs:177`) has no access to object state, and `Snapshot::changed` (`locks.rs:680-694`) does not call `Locked::lock`. The real fix is: (1) in `lib.rs:1885` (`wake`) and `ipc.rs:466,474,642-656` (`serve`, `unlink`), access a waiting thread's wait fields and an `Attached` reply's transition via `get_mut` when waking/delivering under the waited-on object's lock instead of recording `Thread`/`Reply` via `locked(...)`; (2) in `locks.rs:680-694` (`Snapshot::changed`), when `before.wait` is an object wait (`Wait::Call | Wait::Recv | Wait::Reply | Wait::Notify`) and only wait/outcome fields changed, require the waited-on object's lock instead of `LockId::Thread`, and when a `ReplyState::Attached(waiter)` transitions on wake, require `Endpoint`'s lock instead of `LockId::Reply`; (3) update `pass18.rs:1000` to assert zero `Step::Try` / `Step::TryFailed` steps at all, and add a `check/node.rs` test rejecting a waiting-thread wake that omits the waited-on object's lock.

### Finding 7 (Medium) — Refuted

- **Claim:** `model/src/nodes.rs:1060` (`|| self.reclaims.get(&node).is_some_and(|r| r.generation != g)`) is the only reader of `Reclaim::generation`, and under mutation `m25` (removing that clause), killing and reclaiming node 1 in generation `g`, restarting it as `g + 1`, and killing it again skips R2, R3, and R5 because `reclaim_step` reads the old `Reclaim` record.
- **Refutation:**
  1. `Reclaim::generation` is *also* read at `nodes.rs:942` (`r0`), `roles.rs:407` (`r1`), and `pass18.rs:517`.
  2. In `reclaim_step` (`nodes.rs:1066`), whenever `node` enters `Fencing`, `Fenced`, or `Unfenced` for generation `g + 1`, it calls `self.r0(node, g + 1)`. Inside `r0` (`nodes.rs:941-949`), `reclaim.generation == generation` is `false` (`g != g + 1`), so `*reclaim` is overwritten with a fresh `Reclaim { generation: g + 1, isolated: true, ..Default::default() }`, resetting `r3`, `acked`, `audit`, and `clear`. Moreover, R2 (`nodes.rs:1074-1087`) drains all `self.remotes` for `node` unconditionally without consulting `Reclaim` fields.
  3. While `m25` does survive `./verify` (47 `test result: ok` lines), running a concrete two-death test (`repro_finding_7_two_deaths_under_m25`, which kills node 1 in `g1`, restarts it in `g2`, grants a frame from node 1 to node 0 in `g2`, injects a stale `Reclaim` for `g1` onto node 0 right before the second kill, and kills node 1 again) passes cleanly under `m25` and removes node 0's `g2` remote capability. `m25` is equivalent.

### Finding 8 (Medium) — Confirmed

- **Claim:** In `resume_step` (`model/src/nodes.rs:1546-1551`), removing `self.ended_done.insert((node, old))` (mutation `m23`) leaves `./verify` green because `r0_effects` (`nodes.rs:954-982`) is idempotent in existing tests and no invariant counts R0 executions per `(node, generation)`.
- **Contract check:** `architecture/kernel-interface.md:1399` (`74011e1` `:1391`: "runs R0, R2 and R3 for every node whose generation ended while it was sealed (**R0 once for that generation**, leaving the reclaim of a later generation of the same node as it is)").
- **Reproduction:** Applied `m23` at `model/src/nodes.rs:1547-1549` and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines. Inspected `nodes.rs:954-982, 1546-1551`: when `drop_ended` finishes in a single reserve step (<= 32 units, as in `pass18.rs:490` and `reviews.rs:570`), `resume_step` visits `(node, old)` once anyway; if `drop_ended` takes multiple reserve steps (> 32 remote capabilities or grants), `m23` re-runs `r0_effects(node, old)` (including `self.peers[node] = Peer::new()`, `self.unit_r0(node)`, and `self.r1(node, old)`) on every step.
- **Correction check:** The report proposes a counter of R0 runs per `(node, generation)` and an invariant that it is 0 or 1. Note a small precision: `ended_done` (`nodes.rs:1557`) is cleared when `resume_step` finishes and the node becomes live, whereas a live node's `reclaims` / R0 count could also track per-`(node, generation)` invocations across `r0` (`nodes.rs:940`) and `resume_step` (`nodes.rs:1547`). Tracking R0 calls per `(node, generation)` (for `(node, old)` in `ended_done`/resume-check or a per-reclaim counter checked in `check/node.rs` to be `<= 1`) together with a multi-step (> 32 objects) `drop_ended` test in `pass18.rs` catches `m23`.

### Finding 9 (Medium) — Confirmed

- **Claim:** `model/src/irq.rs:58` is the only check enforcing `IRQ_LINES_MAX` (`dodos_abi::IRQ_LINES_MAX = 4_096`); `Table::lines` (`model/src/table.rs:308`) is an unbounded `BTreeMap<u32, u64>`; mutation `m28` (`>=` -> `>` at `irq.rs:58`) survives `./verify` because `pass18.rs:452` tests `IRQ_LINES_MAX + 2` (`pass18.rs:456`) rather than the exact boundary `IRQ_LINES_MAX`; and `check_lines` (`model/src/check.rs:316-337`) imposes no `IRQ_LINES_MAX` bound.
- **Contract check:** `architecture/kernel-interface.md:770` (`74011e1` `:749`: "at most `IRQ_LINES_MAX` (4,096) words of 8 bytes (32 KB) ... a line beyond the last word is `unsupported` for `irq_claim`").
- **Reproduction:** Applied `m28` (`>= dodos_abi::IRQ_LINES_MAX` -> `> dodos_abi::IRQ_LINES_MAX` at `model/src/irq.rs:58`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines. Inspected `pass18.rs:452-459` (sets `first_gsi = IRQ_LINES_MAX - 4` and tests `beyond = IRQ_LINES_MAX + 2`), `table.rs:308,654-673` (`lines: BTreeMap<u32, u64>`), and `check.rs:316-337` (`check_lines` checks `held == claimed` with no bound on count or GSI index).
- **Correction check:** Agree with the report: update `pass18.rs:452` (`a_line_beyond_the_last_line_word_is_unsupported`) to assert `Error::Unsupported` at exact `dodos_abi::IRQ_LINES_MAX as u32` (as well as `IRQ_LINES_MAX - 1` succeeding if covered by the IOAPIC), and check in `check_lines` (`check.rs:316-337`) that `self.table.lines.len() <= dodos_abi::IRQ_LINES_MAX` and all keys in `self.table.lines` are `< dodos_abi::IRQ_LINES_MAX as u32`.

### Finding 10 (Medium) — Refuted

- **Claim:** Under mutation `m26` (`let same = true;` in `model/src/roles.rs:341`), a node that was fenced, restarted, and accused again *before* its first fence action would have unit-role take-over measured from the old generation's `confirmed` instant.
- **Refutation:**
  1. Applied `m26` (`let same = record.generation == member.generation();` -> `let same = true;` at `roles.rs:341`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines (survival confirmed).
  2. However, `m26` is **equivalent** on reachable states and the report's claimed divergence state does not trigger the `Fenced | Dead` arm:
     - While a restarted node has been accused again *before its first fence action*, its `member.state()` is `MemberState::Fencing`, which falls into `_ => return None` at `roles.rs:348` (never `MemberState::Fenced | MemberState::Dead`).
     - The only writer of `MemberState::Fenced` (`nodes.rs:865-877`) requires `started = self.table.fences[node as usize].begun(g)` to be `Some(_)`, which guarantees `fences[node].generation == g` (`nodes.rs:900-904`). The only non-boot writer of `MemberState::Dead` (`nodes.rs:1363-1367`) requires `MemberState::Fenced` first (and a slot `Dead` from boot holds no unit role). Thus `same` is always `true` whenever `MemberState::Fenced | MemberState::Dead` is reached for a role holder.
     - On `MemberState::Unfenced` (`roles.rs:347`), `record.begun(member.generation())?` (`table.rs:179-180`) already checks `self.generation == generation` independently of `same`.

### Finding 11 (Medium) — Confirmed

- **Claim:** In `model/src/roles.rs:347` (`MemberState::Unfenced => record.begun(member.generation())? + FENCE_NS + SETTLE_NS`), dropping `+ SETTLE_NS` (mutation `m27`) leaves the suite green because no test measures the take-over delay of an unfenced holder between `FENCE_NS` and `FENCE_NS + SETTLE_NS`.
- **Contract check:** `architecture/kernel-interface.md:1320` and `:1460` (`74011e1` `:1297`: "or the holder is unfenced and `FENCE_NS` + `SETTLE_NS` have passed since the first fence action").
- **Reproduction:** Applied `m27` (`roles.rs:347` `+ FENCE_NS + SETTLE_NS` -> `+ FENCE_NS`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines. Inspected `abi/src/machine.rs:260,262` (`FENCE_NS = 20_000_000`, `SETTLE_NS = 1_000_000`), `scenarios/membership.rs:441-459` (runs `FENCE_NS + MS = 21_000_000` then `2 * MS`, checking holders only at `23 ms`), and `scenarios/units.rs:524-533` (`an_unfenced_holder_keeps_its_unit_roles_for_fence_ns_and_settle_ns`, which runs `FENCE_NS - MS = 19 ms` and then jumps `+ 2 * MS + 2 * SETTLE_NS = 23 ms`, never sampling `[FENCE_NS, FENCE_NS + SETTLE_NS)`).
- **Correction check:** Agree with the report's idea, sharpened to the exact clock: `scenarios/units.rs:524` (`an_unfenced_holder_keeps_its_unit_roles_for_fence_ns_and_settle_ns`) — not just `membership.rs:441` — is the test that names both constants. Measure from the first fence action (`fences[1].started`), assert the unfenced node still holds `IOMMU_ROLE` at `started + FENCE_NS` (and `started + FENCE_NS + SETTLE_NS - 1`), and assert the successor holds it after `started + FENCE_NS + SETTLE_NS`. Note `membership.rs:443` waits for a `Timer` sweep step to unfence after `FENCE_NS`, so asserting exact instants from `fences[1].started` in `units.rs:524` cleanly distinguishes `FENCE_NS` from `FENCE_NS + SETTLE_NS`.

### Finding 12 (Medium) — Confirmed (with a correction to the proposed test)

- **Claim:** Weakening `class == Some(dodos_abi::PageClass::IOSPACE_TABLE)` to `class.is_some()` at `model/src/units.rs:287` (mutation `m38`) leaves the suite green, including `pass18.rs:291` (`the_holder_refuses_an_attach_whose_root_is_not_an_iospace_table_of_the_requester`), because `pass18.rs:303` passes a floor page (`data`) that has no entry (`None`) in `table.classes`.
- **Contract check:** In `architecture/kernel-interface.md` at `74011e1:1016` and `decisions/README.md:145` (D-135 point 12), G9 asks for a page of class `iospace table` held by the requester. (In `52c3eab:1037` / D-137 point 1, G9 was subsequently tightened to class `48 + n` and the attach word; pass 18 implements the D-135 rule.)
- **Reproduction:**
  - Applied `m38` (`class.is_some()` at `units.rs:287`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines.
  - Because `table.classes` (`model/src/memory.rs:185-190`, `model/src/check/table.rs:471-475`) stores only non-data classes (`c.raw() != 0`), an ordinary floor page (`data` at `pass18.rs:303`) has `class == None`, so `m38` (`class.is_some()`) still refuses `attach(data)`.
  - Adding `m.sys.edit_table(|t| { let page = data / t.geometry.page(); Arc::make_mut(&mut t.classes).insert(page, dodos_abi::PageClass::table(4).unwrap()); });` and `assert!(judged(&mut m, holder, requester, 0, attach(data)));` to `pass18.rs:291` passes on the unmutated model and fails under `m38` (`assertion failed: judged(&mut m, holder, requester, 0, attach(data))`).
- **Correction check:** The report proposes testing "a page of the requester's chunk with `PageClass::DATA`". That test is invalid under the model's invariants: `check/table.rs:471-475` (invariant 59) explicitly forbids `c.raw() == 0` (`PageClass::DATA`) in `table.classes`, while ordinary `DATA` pages omit any entry in `table.classes` (`None`) and would still be rejected by `m38`. The right test case is a valid non-iospace class stored in `table.classes` and held by the requester, namely an address-space page-table class (`PageClass::table(4)` or an `aspace` root table page from the requester).

### Finding 13 (Minor) — Confirmed (with a refinement to the proposed invariant)

- **Claim:** Under escalation (`model/src/locks.rs:558-583`, `again_of_tries`), pushing the event's non-lock steps before its `Step::Lock`s (mutation `m12`) passes `check_locks` (`model/src/check/node.rs:307-384`) and leaves the suite green.
- **Contract check:** `architecture/kernel-interface.md:666` (`74011e1:658`: the escalating call "runs the call alone, taking its locks in the order (no try can fail and no link can change, since no other core is in a kernel event)").
- **Reproduction:** Applied `m12` in `locks.rs:573-578` (running `self.run_once(&event)` and `self.record_rounds(&mut steps, &[])` before pushing `Step::Pay(Cost::Lock)` / `Step::Lock(lock)` and `release(&alone, ...)`), and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines. `check_locks` (`check/node.rs:329-384`) checks `Lock` ordering, `Try`/`TryFailed`, `Quiet`, `Unlock`, and `paid == locks.len() + tried`, but never checks that an event's non-lock steps (`Step::Wait`, non-`Lock` `Step::Pay`) follow `Step::Lock`. (More generally, `record_rounds` synthesizes lock acquisition before `others`, so `check_locks` has no ordering check between `Step::Lock` and `others` outside escalation either.)
- **Correction check:** The report proposes an invariant that between `Step::Quiet(true)` and `Step::Quiet(false)`, "every `Step::Wait` or `Step::Pay` step of the event follows at least one `Step::Lock` of the same event." That rejects valid traces as written, because `again_of_tries` pushes `Step::Pay(Cost::Lock)` immediately *before* the very first `Step::Lock` (`locks.rs:574-575`). The right invariant in `check_locks` (`check/node.rs:329-362`) is: under `Quiet(true)..Quiet(false)`, every `Step::Wait(_)` and every `Step::Pay(c)` with `c != Cost::Lock` must occur while `held` is non-empty (after at least one `Step::Lock` and before all locks are `Unlock`ed), with a unit test in `scenarios/checker.rs` asserting failure when such a step precedes `Step::Lock` under `Quiet(true)`.

### Finding 14 (Minor) — Confirmed in part (survival confirmed; mechanism, non-equivalence argument, and proposed test refuted; exposes a missed fault)

- **Claim:** Removing `instants.push(start.since + START_NS);` from `reserve_due` (`model/src/nodes.rs:1688`, mutation `m18`) leaves `./verify` green because no test asserts that a hung starting node is accused at `since + START_NS` instead of up to one `RECOVERY_PERIOD_NS` (10 ms) late.
- **Contract check:** `architecture/kernel-interface.md:1413` and `:1423` (`74011e1` `:1390`, `:1398`): the caller sends wakes every `START_RETRY_NS` until `started` equals the request or the node no longer reads starting with that generation, and a node that does not reach `owned` or beat within `START_NS` is accused with stale.
- **Reproduction:**
  1. Applied `m18` (removed `instants.push(start.since + START_NS);` at `nodes.rs:1688`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines (survival confirmed).
  2. However, the report's explanation of `m18` is wrong on three counts:
     - `instants.push(start.since + START_NS)` (`nodes.rs:1688`) is inside `for start in self.starts.values()`, which arms `reserve_due` only for `start_step` (`start_over`, `nodes.rs:1626,1650`) to clean up `self.starts` on the caller — it has nothing to do with when `evidence()` (`nodes.rs:631-635`) accuses the starting node.
     - In `start_step` (`nodes.rs:1631-1636`), `start.last` is initialized to `now.max(1)` on the first wake and stepped by `START_RETRY_NS = 1_000_000` (1 ms), while `START_NS = 1_000_000_000` (1,000 ms). Whenever `start.since >= 1`, `start.last + START_RETRY_NS` already lands on `start.since + START_NS`! Removing `start.since + START_NS` (`m18`) shifts `start_over` cleanup by 1 ns only in the unreachable-in-scenarios case `start.since == 0` (`1_000_000_001` vs `1_000_000_000`). Thus `m18` is nearly equivalent (only differs at `since == 0` for clearing `self.starts`, never by `RECOVERY_PERIOD_NS` for accusations).
     - Running a hung `fresh` start on a previously unused core (`core 2`, where `boot.rs:900` initializes `idle_until = u64::MAX`) on the **unmutated** model shows that after `5 * START_NS` (5,000,000,000 ns) node 1 is **still `MemberState::Starting` with `Evidence::None`**, and its observation has `at: 5_000_000_000`! Why: `observe_needed` (`nodes.rs:706-710`) expires every observation after `OBSERVATION_LIFE * stale_ns = 4 * 100 ms = 400 ms`, immediately replacing it with a fresh observation whose `at = now`. Thus `now >= observation.at + START_NS` (`nodes.rs:633`) is **unreachable dead code**, and `membership.rs:702` only passed because reused core 1 kept `idle_until = 0` from before death and `CoreWord::names` (`abi/src/machine.rs:933`) matches `Joining`, causing `stale` (`nodes.rs:627-630`) to accuse at `observation.at + STALE_NS` (100 ms) rather than `START_NS` (see Missed Fault 3).
- **Correction check:** The report's proposed test ("asserts the accusation at `since + START_NS` exactly") fails on the unmutated model both because observations are opened only at `observe_needed` (not at `node_start`) and because `nodes.rs:633` never fires before the 400 ms observation expiry. Fix the underlying `Starting` observation bug first (Missed Fault 3), then add the `START_NS` timing test.

### Finding 15 (Minor) — Confirmed (with a correction to the proposed test; exposes a major missed fault in `reclaim_step`)

- **Claim:** In `audited` (`model/src/nodes.rs:1148-1154`), changing `r.node == node` to `r.node == node + 1` (`nodes.rs:1153`, mutation `m22`) leaves `./verify` green because `pass18.rs:477` (`a_node_resumes_while_a_peer_is_unfenced`) holds no remote capability of the unfenced peer.
- **Contract check:** `architecture/kernel-interface.md:1322-1324` (`74011e1` `:1309-1311`: "**R2.** It removes every translation it holds to memory of *X* and every remote capability to memory of *X* ... **R2 is done when no such record remains**") and `:1414` (`74011e1` `:1391`: `node_start` mode 1 runs R2 to R4 for unfenced peers before becoming live).
- **Reproduction:**
  1. Applied `m22` (`r.node == node` -> `r.node == node + 1` at `nodes.rs:1153`) and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines (survival confirmed).
  2. Verified by adding a test (`repro_m22_1_cap_vs_33_and_fenced_r5` / `repro_finding_15`) granting 33 remote frame capabilities from node 2 to node 1 before sealing node 1, unfencing node 2, and resuming node 1: unmutated, node 1 becomes `Live` only after removing all 33 remote capabilities (`remotes` count == `0`); under `m22`, `reclaim_step` removes 32 capabilities in step 1 (hitting `*units == 0` at `nodes.rs:1082`), exits the `while` loop without returning, sets `r3 = true` and `audit = Some([])`, and `audited(2)` wrongly returns `true`, so node 1 becomes `MemberState::Live` while still holding 1 live remote capability of unfenced node 2 (`assertion failed: left: 1, right: 0`). Thus `m22` is a real hole.
  3. Crucially, the same mechanism creates a **missed fault in `reclaim_step`** on the **unmutated** model when node 2 is **fenced**: with 33 remote capabilities on node 1, `reclaim_step` falls out of the R2 loop at `*units == 0`, skips R4 (`audit_len == 0` or any remaining blocks), and writes R5 (`acked[2] = g`, `maps_of[2] = false`) at `nodes.rs:1136-1141` while `rem_at_ack == 1` remote capability of node 2 still remains (see Missed Fault 2).
- **Correction check:** The report proposes: "give the resuming node a remote frame capability of the unfenced peer before it seals, and assert the resume does not become live until R2 has removed it." Running that exact 1-unmapped-capability test **still passes under `m22`** (`1-cap test passed!`), because a single `reclaim_step` removes the 1 capability *before* `resume_step` checks `self.audited(node)` (`nodes.rs:1528-1533`). To fail under `m22`, `pass18.rs:477` must give node 1 **>= 33** remote capabilities from node 2 (exceeding `units = 32` per recovery step, or a mapped remote capability so `remove_root` takes > 1 step) and assert node 1 does not become `Live` until all of them are gone from `remotes`.

### Finding 16 (Minor) — Confirmed (with a correction to the proposed test's secondary assertion)

- **Claim:** `pass18.rs:679-690` (`the_core_that_completes_a_request_writes_its_state_word_done`) always uses core 0 as requester and core 1 to acknowledge, so mutation `m33` (`self.cores[requester].request_state = RequestState::Done;` -> `self.cores[0].request_state = RequestState::Done;` at `model/src/cores.rs:425`) leaves the whole suite green (`check/node.rs:157-165` only catches a mismatch on the requester when `requester != 0`).
- **Contract check:** `architecture/kernel-interface.md:641` (`74011e1:633`: "the completing core … writes *done* when it empties and frees it").
- **Reproduction:**
  1. Applied `m33` at `model/src/cores.rs:425` and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines (survival confirmed).
  2. Added `repro_finding_16_core1_requester` using `two_threads(Arch::X86_64, 2)` where `other` on core 1 issues `Syscall::ASpaceUnmap(s(FRAME))` (`cores[1].request_state == RequestState::InUse`, `cores[0].request_state == RequestState::None`) and core 0 acknowledges (`take_interrupts(0)`): unmutated passes (`k.m.check() == Ok(())`, `cores[1].request_state == RequestState::Done`, `cores[0].request_state == RequestState::None`); under `m33`, `k.m.check()` fails immediately with `Err("TLB: the state word of a request")` because `cores[1].request_state` stays `RequestState::InUse` while `cores[1].request` became `None`. Thus `m33` is a real test gap (empty for distinguishing `requester` from `0`).
- **Correction check:** The report proposes asserting `cores[1].request_state == Done` and `cores[0].request_state != Done`. That works (`cores[0].request_state` is `RequestState::None` when idle, or `InUse` if core 0 started its own request), though asserting `cores[0].request_state == RequestState::None` (when idle) or having core 0 start and leave an `InUse` request before acknowledging core 1's request (or simply running core 1 as requester and calling `k.m.check()`) is clearer than `!= Done`.

### Finding 17 (Minor) — Confirmed in part (survival and narrower test confirmed; equivalence claim and fix details refuted)

- **Claim:** Mutation `m35` (`(Arch::Aarch64 | Arch::Riscv64, _) => {}` -> `(Arch::Aarch64 | Arch::Riscv64, _) => self.stop(core)` at `model/src/system.rs:429`) leaves `./verify` green including `pass18.rs:47` (`a_late_start_wake_of_a_running_core_changes_nothing_on_arm64_and_risc_v`); the report claims `m35` is equivalent because `stop()` has its own `!self.marked(core)` guard (`system.rs:641,660`), and proposes "(the test already compares `parked`; add `Hardware` and the core word)."
- **Contract check:** `architecture/kernel-interface.md:1230` (`74011e1:1207`: "A repeated `CPU_ON` to a core already on returns `ALREADY_ON` or `ON_PENDING` and starts nothing … and a repeated `sbi_hart_start` returns `SBI_ERR_ALREADY_AVAILABLE`").
- **Reproduction:**
  1. Applied `m35` at `model/src/system.rs:429` and ran `nix develop -c ./verify`: exited 0 with 47 `test result: ok` lines (survival confirmed).
  2. **Equivalence refuted:** `stop()` only skips *unmarked* running cores. In `repro_finding_17_marked_running_late_wake`, calling `m.ok(0, kill(1))` and stepping node 0's events until `core_words[1]` carries the fence mark while `hardware[1]` is still `Hardware::Running` (before `HwAction::Stop { core: 1 }` fires), then calling `m.sys.late_wake(1)`, passes unmutated (`Hardware::Running`, `parked` unchanged) and **fails under `m35`** on `Arch::Aarch64` (`assertion failed: left: Parking, right: Running`; and on `Arch::Riscv64` `stop` writes `parked` and sets `Hardware::Off`). `m35` is therefore a real hole (a late `CPU_ON`/`sbi_hart_start` arriving on a marked running core must start/stop nothing).
- **Correction check:** The report misreads `pass18.rs:47`: line `pass18.rs:54` **already** asserts `assert_eq!(m.sys.hardware(1), Hardware::Running, "{arch:?}");` alongside `parked` at `:55`. The missing coverage is calling `m.sys.late_wake(1)` on a **marked** `Running` core (after `kill(1)` marks `core_words[1]` and before `HwAction::Stop` runs), asserting `m.sys.hardware(1) == Hardware::Running` and unchanged `parked` (plus checking `core_words[1]`).

### Finding 18 (Minor) — Confirmed in part (accurate as a limit of invariant 96; note `judge_write` covers write-time checks)

- **Claim:** `check_lines` (`model/src/check.rs:316-337`) builds `taken = Ownership::taken(Owner::Node(self.node), generation)` and compares `held == claimed`; mutation `m32` (`held == claimed` -> `claimed.is_subset(&held)`) is caught by `pass18.rs:1100`, while the checker never re-compares raw line words of dead/old generations with `Table::may_take` at rest (recorded as a limit of invariant 96, not a fault).
- **Contract check:** `architecture/kernel-interface.md:770` (`74011e1:749`) and `:1326` (`74011e1:1311`, R6 freeing dead-generation line words).
- **Verification:** Inspected `check.rs:316-337`, `check/table.rs:19-90` (`judge_write`, invariant 52), and `pass18.rs:1100-1105`. `check_lines` indeed compares only words matching the live generation's `taken` bit pattern against `self.irqs` (`check.rs:317-336`), so line words still held by a dead or fenced older generation are ignored by invariant 96 until R6 clears them (`nodes.rs:1330-1336`). Every write to `Word::Line(_)` is instead checked event-by-event by invariant 52 (`check/table.rs:38-86`, including R6 clearing at `:76-84`). No fault found.

---

## Missed faults found during verification

### Missed Fault 1 (Major) — `Model::apply` never resets `again_tries` on the uncontended path (`model/src/lib.rs:1381-1386`)

- **Contract:** `architecture/kernel-interface.md:666` (`74011e1:658`: "Each thread counts its consecutive results `again` that came from this rule ...; **any other result of a call of that thread sets the count to 0**").
- **Defect:** `locks::finish` (`model/src/locks.rs:531-535`) resets `t.again_tries = 0`, which runs only inside `apply_contended` (`lib.rs:1385`, when `!self.contended.is_empty()`). After `again_of_tries` (`locks.rs:566-569`) or another contended call drains `self.contended`, subsequent calls of the thread go through `self.apply_once(thread, call)` (`lib.rs:1384`), which never resets `again_tries` to `0`.
- **Reproduction:** `repro_finding_5_uncontended_reset` on the unmodified model ran `k.call(k.t, call)` -> `Err(Error::Again)` (`again_tries == 1`, `contended` empty), followed by `k.ok(Syscall::Yield)` (succeeding with `Ok(Output::Done)`): `k.m.threads[&k.t].again_tries` remained `1` instead of resetting to `0`. (Note that adding the reset inside `Model::apply`'s `true =>` arm avoids disturbing `apply_once` calls made by `let_go` for holder threads.)

### Missed Fault 2 (Major) — `reclaim_step` writes R5 `acked[node]` and skips R4 while R2 or R4 work remains (`model/src/nodes.rs:1074-1143`)

- **Contract:** `architecture/kernel-interface.md:1322-1337` (`74011e1:1309-1314`: **R2** "is done when no such record remains"; **R3**; **R4** audits every live block; **R5** writes `acked[X] = g` after R1–R4 finish).
- **Defect:** In `reclaim_step` (`model/src/nodes.rs:1074-1143`), when `*units` reaches `0` inside the R2 loop (`:1074-1087`) because node `X` has more than 32 remote capabilities (or a mapped remote capability whose `remove_root` finished on the 32nd unit), the loop terminates at `while *units > 0` without returning `true`. Execution falls straight through R3, initializes `audit = Some(blocks)`, exits `while *units > 0` in R4 (`:1111-1132`) with every block still un-audited, and on a fenced peer writes **R5 (`maps_of[node] = false`, `acked[node] = g`)** at `nodes.rs:1136-1142` prematurely! The same fall-through happens if R2 takes fewer than 32 units and R4 hits `*units == 0` with remaining `Block::Run` blocks: R5 is still written before R4 finishes. Neither `check.rs` nor `check/` checks that `beacons[me].acked[node] == g` forbids remaining `self.remotes` entries of `node` or non-empty `audit`.
- **Reproduction:** `repro_m22_1_cap_vs_33_and_fenced_r5` (Part B) on the unmodified model granted 33 remote frame capabilities from node 2 to node 1, fenced node 2, and stepped node 1's recovery until `beacons[1].acked[2] == g2`: at the exact instant R5 was written (`rem_at_ack = 1, audit_len = Some(0), node2_state = Fenced`), node 1 still held 1 live remote capability of dead/fenced node 2 and had skipped auditing blocks cleanly.

### Missed Fault 3 (Medium) — `Starting` accusation branch is dead code and reused cores accuse at `STALE_NS` instead of `START_NS` (`model/src/nodes.rs:624-637, 703-710`, `abi/src/machine.rs:932-936`)

- **Contract:** `architecture/kernel-interface.md:1413` and `:1423` (`74011e1:1390`, `:1398`: a starting node whose core does not reach `owned`, or which does not beat, within `START_NS` = 1,000 ms is accused with `stale`).
- **Defects:**
  1. `observe_needed` (`nodes.rs:706-710`) expires every observation after `OBSERVATION_LIFE * stale_ns` (`4 * 100 ms = 400 ms`) and immediately opens a replacement with `at = now`. Because `400 ms < START_NS (1,000 ms)`, `now >= observation.at + START_NS` (`nodes.rs:633`) can never become true before expiry.
  2. `CoreWord::names` (`abi/src/machine.rs:933`) matches `CoreState::Joining` as well as `CoreState::Owned`, and `node_start` does not clear `core_beacons[core].idle_until` (nor does `reserve_due` arm `observation.at + START_NS` or start observing before `SWEEP_NS`).
- **Reproduction:**
  - `repro_finding_14_starting_checks` hung a fresh start on a previously unused core (`core 2`, where `boot.rs:900` initializes `idle_until = u64::MAX`): on the unmodified model after `5 * START_NS` (5,000,000,000 ns), node 1 was still `MemberState::Starting` with `Evidence::None` and `obs = [Observation { node: 1, watched: Heartbeat { core: 2, heartbeat: 0 }, at: 5000000000 }]`.
  - `repro_missed_starting_case_a` ran `membership.rs:702` (`reused core 1`, whose `idle_until` remained `0` from before death): node 1 was accused at `now = 1_100_000_000` (`since + 1,090 ms`), which is `observation.at (1,000 ms, when the sweep fired) + STALE_NS (100 ms)` via `stale` (`nodes.rs:627-630`), never via `starting` (`nodes.rs:631-633`).

---

## Summary of the 15 surviving mutations (plus `m24` and `m43`)

Every mutation below was re-applied to `/private/tmp/dodos-kernel-verify10`, tested with full `nix develop -c ./verify` (`47` `test result: ok` lines when surviving), and reverted cleanly:

| ID | File:Line | Result (`./verify`) | Classification & Summary |
|---|---|---|---|
| `m02` | `locks.rs:534` | Survives (47 ok) | **Real hole** (Finding 5): unreset `again_tries`; exposed Missed Fault 1 (`lib.rs:1384`). |
| `m08` | `locks.rs:566-569` | Survives (47 ok) | **Real hole** (Finding 2): dead escalation `let_go` loop and unread `Holder::entered`. |
| `m09` | `locks.rs:565` | Survives (47 ok) | **Real hole** (Finding 3): escalation `kernel_epoch += 1` unchecked. |
| `m12` | `locks.rs:573-578` | Survives (47 ok) | **Real hole** (Finding 13): `check_locks` does not order `Step::Wait`/`Step::Pay` after `Step::Lock` under escalation. |
| `m15` | `caps.rs:489` | Survives (47 ok) | **Real hole** (Finding 3): `kernel_epoch += 1` on non-last destruction unchecked. |
| `m18` | `nodes.rs:1688` | Survives (47 ok) | **Nearly equivalent** (Finding 14; only shifts `start_step` cleanup by 1 ns at unreachable `since == 0`); exposed Missed Fault 3 (`Starting` observation expiry < `START_NS`). |
| `m22` | `nodes.rs:1153` | Survives (47 ok) | **Real hole** (Finding 15; needs `>= 33` remote caps to trip): `audited` skips checking `remotes`; exposed Missed Fault 2 (`reclaim_step` R5-before-R2/R4 fall-through). |
| `m23` | `nodes.rs:1549` | Survives (47 ok) | **Real hole** (Finding 8): no invariant or multi-step test forbids running R0 twice per ended generation. |
| `m25` | `nodes.rs:1060` | Survives (47 ok) | **Equivalent** (Item 3b / Finding 7 refuted): `r0` (`nodes.rs:942`) and `r1` (`roles.rs:407`) already reset on `reclaim.generation != g`. |
| `m26` | `roles.rs:341` | Survives (47 ok) | **Equivalent** (Finding 10 refuted): `Fenced` requires `fences[node].begun(g).is_some()` (guaranteeing `generation == g`), `Fencing` hits `_ => None`, `Unfenced` uses `begun(g)`. |
| `m27` | `roles.rs:347` | Survives (47 ok) | **Real hole** (Finding 11): unfenced take-over delay `+ SETTLE_NS` untested inside `[FENCE_NS, FENCE_NS + SETTLE_NS)`. |
| `m28` | `irq.rs:58` | Survives (47 ok) | **Real hole** (Finding 9): exact boundary `IRQ_LINES_MAX` (`4096`) untested and `Table::lines` unbounded in `check_lines`. |
| `m33` | `cores.rs:425` | Survives (47 ok) | **Real hole** (Finding 16): no scenario uses a requester core other than `0`. |
| `m35` | `system.rs:429` | Survives (47 ok) | **Real hole** (Finding 17 equivalence claim refuted): stops a marked `Running` core on ARM64/RISC-V when `late_wake` arrives during fencing before `HwAction::Stop`. |
| `m38` | `units.rs:287` | Survives (47 ok) | **Real hole** (Finding 12): `pass18.rs:291` passes `class == None` instead of a non-iospace `PageClass`. |
| `m24`, `m43` | `nodes.rs:1680-1681` | **Killed** (`membership.rs:414`) | **Killed as DeepSeek reported** (Item 3a): both fail `a_node_that_does_not_consume_a_message_waiting_in_its_ring_is_accused_stuck`; `pass18.rs:644` alone stays green. |

---

## Summary of the three narrow or empty tests of `model/src/scenarios/pass18.rs`

| Test (`model/src/scenarios/pass18.rs`) | Mutation attacked | Passes under mutation? | Verdict |
|---|---|---|---|
| `the_core_that_completes_a_request_writes_its_state_word_done` (`pass18.rs:679`) | `m33` (`cores[requester]` -> `cores[0]` at `cores.rs:425`) | Yes (`./verify` 47 ok) | **Empty for distinguishing `requester` from `0`:** requester is always core 0. Switching requester to core 1 (`repro_finding_16_core1_requester`) fails `k.m.check()` under `m33` with `Err("TLB: the state word of a request")`. |
| `the_holder_refuses_an_attach_whose_root_is_not_an_iospace_table_of_the_requester` (`pass18.rs:291`) | `m38` (`class == Some(IOSPACE_TABLE)` -> `class.is_some()` at `units.rs:287`) | Yes (`./verify` 47 ok) | **Narrow/empty for distinguishing `IOSPACE_TABLE` from other classes:** floor `data` has `class == None` in `table.classes`. Passing a requester-held `PageClass::table(4)` page passes unmutated and fails under `m38`. |
| `a_late_start_wake_of_a_running_core_changes_nothing_on_arm64_and_risc_v` (`pass18.rs:47`) | `m35` (`(Arch::Aarch64 \| Arch::Riscv64, _) => {}` -> `self.stop(core)` at `system.rs:429`) | Yes (`./verify` 47 ok) | **Refuted as to equivalence; test confirmed narrower than marked case:** `pass18.rs:54` already checks `Hardware::Running`, and `stop()` only avoids stopping *unmarked* cores; on a marked running core (after `kill(1)` before `HwAction::Stop`), `m35` parks/stops the core (`Parking`/`Off`) whereas unmutated `late_wake` keeps it `Running`. |

---

## Prioritized list of corrections (by severity)

1. **[Major — Finding 1] Fix `let_go` and `never_again` second-core contention in `model/src/locks.rs` (`let_go`, `contend`, `apply_once`)**
   - **Change:** In `model/src/locks.rs`, stop executing holder events via uncontended `apply_once` while the caller holds locks. Run the holder's `(thread, call)` through `self.contend` with the caller's currently `held` locks temporarily represented in `self.contended` (`tries: 1, then: None`, representing another core holding them) so any conflicting wait/try respects L2 ordering and fails/retries rather than dual-holding, and check the holder's recorded `steps` with `check_locks` before `record_rounds` overwrites `self.locks.steps`; apply the same rule inside `contend`'s `never_again` loop (`locks.rs:495-499`).
   - **Test that must fail without it:** Add a test in `model/src/scenarios/pass18.rs` attaching a `Holder` with `then: Some((third, Syscall::ThreadCancel(s(300), 7)))` on the waited-on `Endpoint` lock of an L2 `Call` that already holds `Segment` and `Thread(k.t)`, asserting no trace executes both cores holding the same lock simultaneously and every holder trace passes `check_locks`.

2. **[Major — Missed Fault 2 + Finding 15] Stop `reclaim_step` fall-through before R5/R4 completion in `model/src/nodes.rs` (`reclaim_step`, `audited`) and add an invariant in `model/src/check/node.rs`**
   - **Change:** In `model/src/nodes.rs` (`reclaim_step`, `:1074-1143`), return `true` if `while *units > 0` in R2 exhausts `*units` or if `!self.audited(node)` is not yet ready (so R4 does not run with `0` units and R5 `:1136` never writes `acked[node] = g` while any remote capability of `node` remains in `self.remotes` or `audit` is non-empty; also fix `m22`-style mutation checks by requiring `!self.remotes.values().any(|r| r.node == node)` and `audit.as_ref().is_some_and(Vec::is_empty)` before R5). Add an invariant in `model/src/check/node.rs` checking that whenever `self.table.beacons[me].acked[node] == g` (for a fenced generation `g`), `self.remotes.values().all(|r| r.node != node)` and `self.reclaims[&node].audit.as_ref().is_some_and(Vec::is_empty)`.
   - **Tests that must fail without it:** In `model/src/scenarios/pass18.rs`, (a) update `pass18.rs:477` (`a_node_resumes_while_a_peer_is_unfenced`) to give the resuming node `>= 33` remote frame capabilities of the unfenced peer before sealing and assert it does not become `Live` until `remotes` for that peer is empty (catches `m22`); (b) add a fenced reclaim test with `>= 33` remote capabilities and `>= 33` `Block::Run` blocks asserting `beacons[me].acked[peer] != g` until all remote caps are removed and all blocks are audited.

3. **[Major — Finding 4] Replenish past-due throttled contexts in `Model::core_entered` (`model/src/cores.rs`)**
   - **Change:** In `model/src/cores.rs` (`core_entered`, `:736-775`), after clearing `self.cores[position].silent = false`, collect every context queued on `position` with `throttled == Some((at, n))` and `at <= self.now`, and replenish it via `self.replenish(context, n)` before returning.
   - **Test that must fail without it:** Add `repro_finding_4_via_system` (throttling `c1`, sealing node 1, advancing `20 * MS` past the replenishment instant, resuming node 1, and calling `m.sys.check()` after every single `Event`) in `model/src/scenarios/pass18.rs` (must fail with `"node 1: 43: parameters and state of a context"` after `EntryStep { core: 1 }` without the fix).

4. **[Major — Finding 2] Implement and enforce entry-word waiting in `again_of_tries` (`model/src/locks.rs`) and `check_locks` (`model/src/check/node.rs`)**
   - **Change:** Record the quiet-word wait on entry words in `again_of_tries` (`model/src/locks.rs:558-582`) by waiting on / checking `Holder::entered` (`entered_before(self.kernel_epoch)`) or letting go only holders whose `entered` satisfies `< self.kernel_epoch` (returning `Err(Error::Again)` if an entry-word wait is modeled or asserting the new `Step` in `check/node.rs`), and require in `check_locks` (`model/src/check/node.rs:349-356`) that no lock or effect step under `Step::Quiet(true)` runs before other cores' entry words read `0` or `>= epoch`.
   - **Test that must fail without it:** Add a test in `model/src/scenarios/pass18.rs` placing an unrelated `Holder` on `LockId::Core(1)` with `entered: k.m.kernel_epoch` (`!= 0`, `< new epoch`) before a 3rd escalated call, asserting `again_of_tries` drains `contended` via `let_go` and checks/waits on `entered` (catches `m08`).

5. **[Major — Finding 3] Enforce `kernel_epoch` transitions in `model/src/check/` and add the untyped ready-epoch constant in `abi/src/machine.rs`**
   - **Change:** Add `pub const SLOT_UNTYPED_READY_WORD: usize = 6;` (or matching word offset constant) to `abi/src/machine.rs` alongside `SLOT_UNTYPED_*`; check `kernel_epoch` increments in `Model::check` / `check/node.rs` (only by `+1` on `again_of_tries` escalation and on `release` when `live` transitions `1 -> 0` under L2, and untyped root word 6 == `0` or ready epoch).
   - **Tests that must fail without it:** Assert in `pass18.rs:797` that escalation raises `kernel_epoch` by 1 (catches `m09`) and in `pass18.rs:1058` that destroying a non-last object (`live > 1`) of an untyped under L2 leaves `kernel_epoch` unchanged (catches `m15`).

6. **[Major — Finding 5 + Missed Fault 1] Reset `again_tries` on uncontended calls in `Model::apply` (`model/src/lib.rs`) and test both paths (`model/src/scenarios/pass18.rs`)**
   - **Change:** In `model/src/lib.rs` (`Model::apply`, `:1381-1386`), reset `if let Some(t) = self.threads.get_mut(&thread) { t.again_tries = 0; }` after `self.apply_once(thread, call)` on the `true =>` arm (leaving `apply_once` untouched for `let_go`), and keep the reset in `locks::finish` (`locks.rs:534`).
   - **Tests that must fail without it:** Add two tests in `model/src/scenarios/pass18.rs` between two `again` results of tries: (a) an uncontended `Yield`/`Recv` with `contended` empty asserting `again_tries == 0` right after (catches Missed Fault 1); (b) a contended succeeding `Yield`/`Recv` with an unrelated `Holder` in `contended` asserting `again_tries == 0` right after and `again_tries == 1` after the next failed try (catches `m02`).

7. **[Medium — Missed Fault 3 + Finding 14] Fix `Starting` accusation timing in `model/src/nodes.rs` (`evidence`, `observe_needed`, `reserve_due`, `node_start`) and `abi/src/machine.rs` (`CoreWord::names`)**
   - **Change:** In `abi/src/machine.rs:933` or `nodes.rs:625`, do not treat `CoreState::Joining` cores with stale pre-death `idle_until` values as normal `STALE_NS` run-time stale misses (reset `idle_until` on `node_start` or restrict `stale` at `:627-630` to `CoreState::Owned`), give starting nodes a non-expiring `START_NS` check (e.g., open or preserve the starting observation / measure against `started_at + START_NS` rather than expiring every `4 * STALE_NS = 400 ms`), and arm `reserve_due` at `observation.at + START_NS` (or the start accusation deadline) so hung starts are accused at `START_NS` regardless of previous `idle_until` or `SWEEP_NS`.
   - **Tests that must fail without it:** Update `scenarios/membership.rs:702` (or add a test in `pass18.rs`) to test hanging a fresh start on a previously unused core (`core 2`, `idle_until = u64::MAX`) and verify it is accused `Evidence::Stale` at `START_NS` (not stuck `Starting` at `5 * START_NS`), and verify a reused core (`core 1`) is NOT prematurely accused at `100 ms` (`STALE_NS`) after observation.

8. **[Medium — Finding 6] Guard waiting-thread wait fields and attached reply objects strictly by the waited-on object's lock (`model/src/lib.rs`, `model/src/ipc.rs`, `model/src/locks.rs`)**
   - **Change:** In `model/src/lib.rs:1885` (`wake`) and `model/src/ipc.rs:466, 474, 642-656` (`serve`, `unlink`), access a waiting thread's wait/outcome fields and an `Attached` reply's wake transition under the waited-on object's lock via `get_mut` instead of emitting `LockId::Thread` / `LockId::Reply` via `locked(...)`; in `Snapshot::changed` (`locks.rs:680-694`), attribute wait/outcome-only changes on a waiting thread to the waited-on object's lock (`Endpoint`/`Reply`/`Notify`) and `Attached` reply wake transitions to `Endpoint`.
   - **Tests that must fail without it:** Tighten `pass18.rs:1000` (`under_l2_notify_bind_takes_the_endpoint_then_the_notify_and_tries_neither`) to assert zero `Step::Try` / `Step::TryFailed` steps, and add a `check/node.rs` unit test rejecting a wake of a waiting thread that takes `Thread` without the waited-on object's lock.

9. **[Medium — Finding 8] Count R0 runs per `(node, generation)` and check the bound (`model/src/nodes.rs`, `model/src/check/node.rs`, `model/src/scenarios/pass18.rs`)**
   - **Change:** Record a per-`(node, generation)` R0 execution count (in `Reclaim` / `Model`) incremented by both `r0` (`nodes.rs:940`) and `resume_step` (`nodes.rs:1547`) and assert in `check/node.rs` that each `(node, generation)` count is `<= 1`.
   - **Test that must fail without it:** Add a multi-step (> 32 remote capabilities or grants so `drop_ended` spans multiple recovery steps) resume test in `model/src/scenarios/pass18.rs` asserting R0 runs once for the ended generation (catches `m23`).

10. **[Medium — Finding 9] Bound `Table::lines` in `model/src/check.rs` (`check_lines`) and test exact `IRQ_LINES_MAX` (`model/src/scenarios/pass18.rs`)**
    - **Change:** In `model/src/check.rs:316-337` (`check_lines`), check that `self.table.lines.len() <= dodos_abi::IRQ_LINES_MAX` and all GSI keys are `< dodos_abi::IRQ_LINES_MAX as u32`.
    - **Test that must fail without it:** Update `pass18.rs:452` (`a_line_beyond_the_last_line_word_is_unsupported`) to call `irq_claim` at exact `dodos_abi::IRQ_LINES_MAX as u32` (`4096`) and assert `Err(Error::Unsupported)` (catches `m28`).

11. **[Medium — Finding 11] Test unfenced take-over timing inside `[FENCE_NS, FENCE_NS + SETTLE_NS)` (`model/src/scenarios/units.rs`)**
    - **Change:** No code fix needed in `roles.rs:347`; strengthen `model/src/scenarios/units.rs:524` (`an_unfenced_holder_keeps_its_unit_roles_for_fence_ns_and_settle_ns`).
    - **Test that must fail without it:** In `units.rs:524`, sample from `fences[1].started`, assert the unfenced holder still holds `IOMMU_ROLE` at `started + FENCE_NS` and `started + FENCE_NS + SETTLE_NS - 1`, and assert the successor holds it after `started + FENCE_NS + SETTLE_NS` (catches `m27`).

12. **[Medium — Finding 12] Test a requester-held non-iospace page class in `pass18.rs:291` (`model/src/scenarios/pass18.rs`)**
    - **Change:** No code fix for D-135 (note D-137 later updates G9 to class `48 + n` in `52c3eab:1037`); update `pass18.rs:291` (`the_holder_refuses_an_attach_whose_root_is_not_an_iospace_table_of_the_requester`).
    - **Test that must fail without it:** Set a requester-held page's class in `table.classes` to `dodos_abi::PageClass::table(4).unwrap()` (valid per invariant 59) and assert `!judged(&mut m, holder, requester, 0, attach(data))` (catches `m38`).

13. **[Minor — Finding 13] Enforce lock-before-effect order under escalation in `check_locks` (`model/src/check/node.rs`)**
    - **Change:** In `model/src/check/node.rs:329-362` (`check_locks`), require under `quiet == true` that every `Step::Wait(_)` and every `Step::Pay(c)` with `c != Cost::Lock` occurs only when `!held.is_empty()`.
    - **Test that must fail without it:** Add a unit test in `model/src/scenarios/checker.rs` building an escalated trace where `Step::Pay(Cost::Call)` or `Step::Wait(_)` precedes `Step::Lock(_)` under `Step::Quiet(true)` and asserting `check()` fails (catches `m12`).

14. **[Minor — Item 3a] Strengthen `pass18.rs:644` (`the_first_core_of_an_idle_live_node_keeps_its_sweep_armed`)**
    - **Change:** Advance past the initial open observation's expiry (or inspect `next_sweep` / core 0's timer queue directly) in `model/src/scenarios/pass18.rs:644` so it fails without `instants.push(self.next_sweep)` (`nodes.rs:1680-1681`) rather than relying on `membership.rs:414` (catches `m24` and `m43` directly in `pass18.rs`).

15. **[Minor — Finding 16] Use core 1 as requester in `pass18.rs:679` (`the_core_that_completes_a_request_writes_its_state_word_done`)**
    - **Change:** Change `model/src/scenarios/pass18.rs:679` to start the `ASpaceUnmap` request from `other` on core 1 and acknowledge with `k.m.take_interrupts(0)`, asserting `k.m.check() == Ok(())`, `k.m.cores[1].request_state == RequestState::Done`, and `k.m.cores[0].request_state == RequestState::None` (or testing with an `InUse` request on core 0) (catches `m33`).

16. **[Minor — Finding 17] Test `late_wake` on a marked `Running` core for ARM64 and RISC-V (`model/src/scenarios/pass18.rs:47`)**
    - **Change:** Extend `model/src/scenarios/pass18.rs:47` (`a_late_start_wake_of_a_running_core_changes_nothing_on_arm64_and_risc_v`) to also call `m.sys.late_wake(1)` after `m.ok(0, kill(1))` marks `core_words[1]` while `m.sys.hardware(1) == Hardware::Running` (before firing `HwAction::Stop { core: 1 }`), asserting `m.sys.hardware(1) == Hardware::Running` and unchanged `parked` (catches `m35`).

