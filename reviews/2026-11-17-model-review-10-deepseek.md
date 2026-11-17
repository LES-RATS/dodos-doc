# Model review 10: the executable model of the kernel contract against the contract, pass 18

Review of the model branch of `dodos-kernel`, pull request 3, head `073ae9e`
(`crates abi/` and `model/`), against
`architecture/kernel-interface.md` of this repository at `74011e1`.

I made my own copy first and worked only in it:

```
git clone --branch model /Users/btw/Documents/repos/dodos-kernel /private/tmp/dodos-kernel-review10
git -C /private/tmp/dodos-kernel-review10 rev-parse HEAD   ->  073ae9ec81f0ffefa772e1f3c3163b621efb4c06
```

Two more copies (`/private/tmp/mut1`, `/private/tmp/mut2`, and three more) were
made for the mutation campaign of item 5; each mutation was applied to a fresh
copy, `cargo fmt --all` run, and then `./verify` (the whole suite: `cargo fmt
--check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test
--workspace`, then the `16k` and `32k` geometry runs) run in it. The rustc of
the flake answers `rustc 1.100.0 (0ef1bc386 2026-11-09)` outside `nix develop`
too, so `./verify` ran directly. A green run prints 47 `test result: ok` lines;
I checked that count for every green result below. A whole `./verify` takes
about 90 s on this machine.

I read `AGENTS.md`, `model/README.md` and the skills `.claude/skills/dodos-rust`
and `.claude/skills/rust-1-100` before judging any Rust here.

Nothing was committed and nothing was pushed. This file is my only output.

---

## Findings

### 1. Major — the lock a test scripts as held by another core is not a second core: the holder's event takes locks that the contending call holds, and no check looks at it

Contract, `architecture/kernel-interface.md:652`: "**A core waits for a lock
only in the order by kind.** A lock that a call finds by reading an object it
already holds locked, and that comes earlier in the order than a lock it holds,
it **tries**: a try never waits." And `:681`: "**Why no call deadlocks under
it.** A deadlock needs a cycle of cores, each waiting for a lock that the next
one holds."

Model, `model/src/locks.rs:426-441` (`round`): a lock that is waited for and
that has a holder is recorded as `Step::Lock`, and then
`self.let_go(lock)` runs the holder's event (`locks.rs:414-424`) — while the
contending call still holds every earlier lock it took in this round, and while
it holds the very lock it is waiting for:

```rust
            if held.iter().all(|&h| h < lock) {
                steps.push(Step::Lock(lock));
                held.push(lock);
                if self.let_go(lock) {
                    return Round::Changed(held);
                }
```

`let_go` runs the holder as a whole event:

```rust
        let Some((thread, call)) = holder.then else {
            return false;
        };
        let _ = self.apply_once(thread, call);
```

`apply_once` is the single-core path: it reads and writes the node with no
knowledge of the locks the contending call holds, and its own trace is
discarded at once (the next `run_once` overwrites `self.locks.steps`, and
`record_rounds`, `locks.rs:541`, keeps only the steps of the last event).

State where they differ: the scoped holder of
`pass18.rs:768` (`under_l2_a_link_changed…`) is a `ThreadCancel` of the
receiver, scripted on the lock the delivery tries. Let the holder be any call
that needs a lock the contending call already holds — the endpoint the delivery
holds, say (`ThreadCancel` on a waiting thread takes the thread and then the
endpoint it waits on, `model/src/threads.rs`; both are `< Endpoint` in the
order of `LockId`). A real second core would find that lock held by the first
core and, since the endpoint comes after its thread, would *wait* for it; the
model instead has both cores hold the same lock: `apply_once` takes it without
a word, the check of `check/node.rs:306-383` sees only the contending event's
steps, and the run continues. So the model can pass through a state no
interleaving of the contract produces, and the contract's argument that no
cycle exists is not exercised for the second core.

Smallest correction: run the holder's event through the same machinery
(`self.contend(Contended::Call(thread, call))`, or refuse a `Holder` whose
`dry_found` contains a lock the caller holds at the moment of the wait), so
that the second core obeys the order of `:652` and its trace is checked.

### 2. Major — the escalation never waits for the entry words of the other cores: no reachable state has a holder left when it escalates

Contract, `:658`: "it **escalates**. It releases every lock it holds, takes the
node's **quiet word** …, raises the node's kernel epoch by one, **waits until
the entry word of every other core of the node reads 0 or at least the new
epoch**, runs the call alone".

Model, `model/src/locks.rs:558-583` (`again_of_tries`):

```rust
            steps.push(Step::Quiet(true));
            self.kernel_epoch += 1;
            let held: Vec<LockId> = self.contended.keys().copied().collect();
            for lock in held {
                self.let_go(lock);
            }
```

It does not read `Holder::entered` (`locks.rs:91-99`, a field whose only reader
is `caps.rs:509`), and by the time it is reached `self.contended` is already
empty of everything the call touched: `contend` ends a holder for every lock of
`known` before it computes `second` (`locks.rs:485-487`), and the first round
ends a holder for any lock it waits for. So the loop above is dead. The tests
agree: `pass18.rs:797` (`under_l2_a_third_again…`) passes with
`k.m.contended.is_empty()` before the escalation.

State where they differ: mutation 8 of item 5 (below) removes the loop and the
whole suite stays green — a node in which the escalating call runs while another
core is still inside a kernel event is accepted, which `:658` forbids ("waits
until the entry word of every other core … runs the call alone").

Smallest correction: keep one holder through the second round (script it on a
lock the call reads but whose try does not fail, e.g. the timer of another
core), and add to `check/node.rs` the rule that a `Step::Quiet(true)` is
followed only by the locks of the call, with the entry word of every other
holder of the node read first.

### 3. Major — the escalation's raise of the kernel epoch has no check, and neither does the value it writes into the root slot

Contract, `:658` (quoted above: "raises the node's kernel epoch by one") and
`:657`: "the destroying core raises the node's **kernel epoch** (one word of the
node block) by one and writes the new value in word 6 of the untyped's root
slot".

Model: `kernel_epoch` is a field (`model/src/lib.rs:1076`), raised in
`locks.rs:565` and `caps.rs:490`; its value is read at exactly one place,
`caps.rs:509-514` (`entered_before`), through the `ready` epoch that `release`
stored. There is no invariant over it: grep `check.rs` for `kernel_epoch` finds
nothing, and nothing in `abi/` names word 6 of a slot (`grep SLOT_UNTYPED
abi/src/machine.rs` gives the bits of word 0 only; the model keeps
`Untyped::ready`, `lib.rs:590`, instead of a slot word).

State where they differ: mutation 9 (the escalation does not raise the epoch)
and mutation 15 (the epoch is raised at every destruction instead of the last
one) both leave the whole suite green. The second is not harmless: with a
higher epoch stored at a destruction, a core that entered *after* the raise is
read as "before" it, so the watermark returns later than `:657` allows; the
first is a silent loss of the only guard the escalation path gives to a
destruction that races it.

Smallest correction: an invariant that word 6 of an untyped's root slot holds a
value that is 0 or the epoch at which its watermark became ready, and that
`kernel_epoch` only ever increases by one at the two events `:657` and `:658`
name; a constant in `abi/` for word 6.

### 4. Major — invariant 43 breaks at a resume: finding 15 of the ninth review is still live in pass 18

Finding 15 of `2026-11-17-model-review-9-gemini-hydrogen.md:190` said that
`core_entered` clears `silent` while a throttled context's replenishment instant
has passed, and invariant 43 fails at once. The author of pass 18 reports it as
"not reproduced". It reproduces. The two places the finding names are unchanged
by pass 18 (`git diff c7951d8..073ae9e` touches neither
`model/src/check/sched.rs` nor `Model::core_entered`):

- `model/src/check/sched.rs:77-78`:
  `let silent = self.cores.get(sched.core).is_some_and(|c| c.silent);` /
  `let throttled = silent || sched.throttled.is_some_and(|(at, _)| at > self.now);`
- `model/src/cores.rs:740-741`: `let part = &mut self.cores[position];` /
  `part.silent = false;`

I reproduced it with a test I added to my copy (not kept, not committed):

```rust
#[test]
fn finding_15_of_review_9_reproduced() {
    let machine = one_node(Arch::X86_64, 1);
    let mut k = N::on(&machine);
    k.place_first(0);
    let context = k.m.threads[&k.t].home.expect("a home context");
    let now = k.m.now;
    k.m.threads.get_mut(&k.t).unwrap().suspended = true;
    {
        let sched = k.m.scheds.get_mut(&context).unwrap();
        sched.remaining = 0;
        sched.throttled = Some((now, 1));
        let entered = sched.queue.map(|q| q.entered).unwrap_or(0);
        sched.queue = Some(crate::Queued {
            queue: crate::Queue::Sleeping,
            key: now,
            entered,
        });
    }
    k.m.cores[0].silent = true;
    assert_eq!(k.m.check(), Ok(()));   // holds while the core is silent
    k.m.core_entered(0);               // what a resume does
    assert_eq!(k.m.check(), Ok(()));   // fails
}
```

Result: `cargo test -p dodos-model --lib finding_15` fails on the last line with
`left: Err("43: parameters and state of a context")`, `right: Ok(())`. I did not
drive a whole seal and resume through `System` (see "Not checked" below): I put
the context in the state the finding describes and made the single transition
`core_entered` makes, which is the sentence of the finding.

State where they differ: a node sealed (or one core hung) with a context whose
budget ran out, resumed after the context's replenishment instant. The
contract's rule is at `:504` (a context **has budget** when *r* > 0,
"otherwise it is **throttled** until its replenishment instant") and `:562-563`
(exhausted at *r* ≤ 0; "If that instant is not after now, it is replenished at
once"). After the resume the model has a context that is throttled with its
replenishment instant in the past and that is never replenished — and its own
invariant 43 (`check/sched.rs:77-78`) reports it with the message "43:
parameters and state of a context".

Smallest correction: at `core_entered`, or at the first event of a resumed
core, take the timer event of the core's throttled contexts (replenish those
whose instant has passed) before the check runs; the ninth review's own
correction.

### 5. Major — the count of `again` of the rule of tries is never reset by another result: mutation 2 survives

Contract, `:658`: "Each thread counts its consecutive results `again` that came
from this rule …; **any other result of a call of that thread sets the count to
0**".

Model, `locks.rs:523-539` (`finish`):

```rust
        if let Contended::Call(thread, _) = event
            && let Some(t) = self.threads.get_mut(thread)
        {
            t.again_tries = 0;
        }
```

Mutation 2 (below) blanks that assignment and the whole suite is green.

State where they differ: two `again` of tries, then a call of the same thread
that succeeds, then one more failed try. The contract escalates on the *third*
`again` of a streak; the model escalates on the first one after the success,
because `again_of_tries` (`locks.rs:562`) only ever counts up and `finish` is
the only reset. No test has a success between two `again`.

Smallest correction: a test that does exactly that (a delivery that reaches
`again`, a `recv` that succeeds, another delivery whose try fails, and
`again_tries == 1`).

### 6. Medium — the model locks a woken thread and its reply object by their own lock words where the contract guards them by the endpoint's lock, and the checker accepts both: yes, this is a hole

Contract, `:653`: "**The fields of a thread that waits on an object, which a
wake changes** (its state of waiting, its links in the object's queue, the
result and the message words it receives), **are guarded by the lock of the
object it waits on** (an endpoint, a reply object, a notify), **not by the
thread's own lock** … **The reply object attached to a thread that waits to
receive** is guarded in the same way, while it is attached, by the lock of the
endpoint that thread waits on".

Model, `model/README.md:98-99` ("the model locks a woken thread and its reply
object by their own words, where the contract guards them by the lock of the
object waited on") and `locks.rs:29-31`, which calls this "an
over-approximation". It is not an over-approximation of the same rule; it is a
different rule. The `Locked` trait and its `locked!` table (`locks.rs:175-196`:
`locked!(crate::Thread, Thread)` at `:192`, `locked!(crate::ReplyState, Reply)`
at `:194`) give a thread and its reply object a lock word of their own, and
`Snapshot::changed` (`locks.rs:666-764`) turns every thread or reply the event
changed into that lock. The L2 check of `check/node.rs:306-383` accepts
`Try(Thread)` because `Thread < Endpoint`.

State where they differ: `pass18.rs:1000`
(`under_l2_notify_bind_takes_the_endpoint_then_the_notify_and_tries_neither`)
asserts that no endpoint and no notify is tried — and says in a comment that the
woken receiver and its reply object are locked by their own words, "an
over-approximation the check accepts". Two things the contract's discipline
forbids are therefore accepted by the model, and the one thing the contract
requires is never checked: (a) a wake that takes the thread's lock is legal
here, though `:653` says the wake does not take it ("a delivery, an answer, a
signal and the destruction of the object wake a thread without taking its
lock"); (b) a call that changes a waiting thread's fields while holding *only*
the thread's lock (no endpoint) would be accepted, because the endpoint's lock
is only required when the endpoint itself changes — and the whole point of the
sentence is that the endpoint's lock is what makes "the thread still waits on
it" atomic against a concurrent `thread_cancel`. The model also changes the
order graph: with `Thread < Endpoint`, the wake path is endpoint → thread
(tried), where the contract's path has no thread lock at all, so a deadlock
argument proved on the model's order is not an argument about the contract's.

Smallest correction: give the two fields of a waiting thread (and the attached
reply object) no lock word of their own under L2 — `Locked::lock` for
`crate::Thread` and `crate::ReplyState` (`locks.rs:192`, `:194`) returns `None`
while the thread waits, so `Snapshot::changed` adds no lock of its own and the
endpoint is the object locked — and add the invariant that an event that changes a
waiting thread's wait fields holds the lock of the object it waits on. That is
what makes the model check `:653` instead of a stricter rule of its own.

### 7. Medium — the reclaim of a restarted peer is keyed by node and by nothing else: mutation 25 survives

Contract, `:1311` (R2) and the reclaim of §"The calls" `:1391`: a node *Y*
reclaims each generation of *X* on its own; R2, R3 and R5 are steps of that
generation.

Model, `model/src/nodes.rs:1060-1063`:

```rust
            if state != MemberState::Dead
                || self.reclaims.get(&node).is_some_and(|r| r.generation != g)
            {
                self.reclaims.remove(&node);
            }
```

This is the only place the `generation` field of `Reclaim`
(`nodes.rs:63-75`) is read. Mutation 25 removes that second clause, so the
record of an older generation survives a fresh start of the same node, and the
suite is green.

State where they differ: node 1 (generation *g*) is killed, reclaimed by node 0
(`acked = true`, `r3 = true`, `audit = Some([])`, `clear = None`), starts fresh
as *g*+1, and dies again. With the reset gone, `reclaim_step` for *g*+1 reads
the old record: `self.r0(node, g)` on it, then R2 and R3 skipped as already
done (`nodes.rs:1091`, `1102`), then `done` true at `nodes.rs:1531-1535` — R2
("It removes every translation it holds to memory of *X*", `:1311`) is never
run for the second generation. A scenario of two deaths of the same node exists
(`pass18.rs:159` kills node 1, restarts it and kills it again) but it checks the
fence record only, so nothing sees it.

Smallest correction: a test that kills and reclaims node 1 twice and asserts
that node 0's R2 runs again (a remote grant of the second generation is removed
in steps), or key `reclaims` by `(node, generation)`.

### 8. Medium — R0 twice for one generation is accepted: mutation 23 survives

Contract, `:1391`: "runs R0, R2 and R3 for every node whose generation ended
while it was sealed (**R0 once for that generation**, leaving the reclaim of a
later generation of the same node as it is)".

Model, `nodes.rs:1545-1552`, is right (`ended_done.insert((node, old))`); the
mutant that drops the guard is green, so nothing can tell "once" from "again".
That is not only a test gap: R0's effects are idempotent in the model (it ends
waits with `gone`, drops use entries, frees credits), so the model *cannot* show
a second R0 as long as they are — the check has no counter.

Smallest correction: a count of R0 runs per `(node, generation)` in the reclaim,
and an invariant that it is 0 or 1.

### 9. Medium — the line words have no size of their own: the bound `IRQ_LINES_MAX` is one comparison and no table bound, and the boundary is untested

Contract, `:749`: "a line beyond the last word is `unsupported` for
`irq_claim`", with "at most `IRQ_LINES_MAX` (4,096) words of 8 bytes (32 KB)".

Model: `abi/src/machine.rs:118` has the constant; `model/src/irq.rs:58` is the
only reader:

```rust
        if source.is_line() && source.id() as usize >= dodos_abi::IRQ_LINES_MAX {
```

`Table::write_line` (`model/src/table.rs:663-674`) and `Table::line_word`
(`:654-658`) take any `gsi`, so the model's living part has no size at all: the
table is a `BTreeMap` that grows. Mutation 28 changes `>=` to `>` — line 4,096
is then accepted — and the whole suite is green, because
`pass18.rs:452` (`a_line_beyond_the_last_line_word_is_unsupported`) uses a line
well above the bound.

State where they differ: `irq_claim` of GSI 4,096 on a machine whose firmware
lists 4,096 lines. The contract refuses it; the model takes the line, writes a
4,097th word, and `check_lines` (`check.rs:316-338`) is happy.

Smallest correction: a test at exactly `IRQ_LINES_MAX`, and an invariant that
the line words number at most `IRQ_LINES_MAX`.

### 10. Medium — the fence record's generation is not consulted at a take-over: mutation 26 survives

Contract, `:1285`: "word 0, the generation the record concerns"; `:1297`: "its
unit roles are taken over by their successors `FENCE_NS` + `SETTLE_NS` after the
first fence action".

Model, `model/src/roles.rs:336-350`:

```rust
        let record = &self.table.fences[judged as usize];
        let same = record.generation == member.generation();
        let at = match member.state() {
            MemberState::Fenced | MemberState::Dead if same => {
                record.confirmed.unwrap_or(0) + SETTLE_NS
            }
```

Mutation 26 blanks `same` to `true`, and the suite is green. Since the record is
per node slot and survives a generation (`nodes.rs:485`, where the reset of the
record on a start was removed), a record of an older generation is a real state:
a node that was fenced, restarted and is fenced again before its first fence
action. The take-over would then be measured from the *old* confirmation
instant.

Smallest correction: a test with a restart between two fences that arrives at
the take-over before the second fence action, and (with finding 1 of this
report's item 3, `begun`) the same for the unfenced arm.

### 11. Medium — the delay of a take-over of an unfenced peer is a constant nothing binds: mutation 27 survives

Contract, `:1297`: "its unit roles are taken over by their successors
`FENCE_NS` + `SETTLE_NS` after the first fence action".

Model, `roles.rs:347`: `MemberState::Unfenced => record.begun(member.generation())? + FENCE_NS + SETTLE_NS`.
Mutation 27 drops the `SETTLE_NS` and the suite is green: no test takes a role
over from an unfenced node and measures the delay
(`membership.rs:443` measures it for a node that reaches fenced, and the
unfenced test at `:457` does not measure the transfer).

Smallest correction: the test of `membership.rs:443` with the unfenced state,
asserting the holder is still the dead node at `FENCE_NS` and is node 0 at
`FENCE_NS + SETTLE_NS`.

### 12. Medium — the class of an attach's root page is not bound by any test: mutation 38 survives

D-135 point 12 (in `decisions/README.md`): "G9 asks for a page of class *iospace
table* held by the device's node (no class tells a root from a lower table)";
contract `:1016`, row 1 of the operand table: "G9; the identifier word names the requester;
the domain number is in the requester's range on the unit".

Model, `model/src/units.rs:279-290`:

```rust
                let page = root / self.table.geometry.page();
                let class = self.table.classes.get(&page).copied();
                held(device)
                    && in_range(domain)
                    && class == Some(dodos_abi::PageClass::IOSPACE_TABLE)
                    && self.table.holds_page(root, node, generation)
```

Mutation 38 weakens `class == Some(IOSPACE_TABLE)` to `class.is_some()` and
`pass18.rs:291`
(`the_holder_refuses_an_attach_whose_root_is_not_an_iospace_table_of_the_requester`)
still passes. Its "page that is not an iospace table" is a page of the
requester's floor (`m.sys.canonical().floors[requester][0].0 + 4 * 4096`), and
whatever refuses that root — a class it does not have, or the page not being
held in a chunk of the requester for `holds_page` — the class test is not what
refuses it: the weakened test refuses the same root.

State where they differ: an attach whose root is a page of a real, non-iospace
class (a `data` page the requester holds in a chunk of its own). The holder
`:1016` gives G9 to the holder's gate, so the contract refuses the attach; the
model with the weakened test performs it.

Smallest correction: add that case to the test — a page of the requester's
chunk with `PageClass::DATA` — and keep the class test as it is.

### 13. Minor — the order of a call's steps inside an escalation is not checked: mutation 12 survives

Contract, `:658`: the escalating call "runs the call alone, **taking its locks
in the order** (no try can fail …)".

Model, `locks.rs:558-583`: `again_of_tries` pushes `Step::Quiet(true)`, then the
`Step::Lock`s, then runs the event (`run_once`) and `record_rounds` appends the
event's non-lock steps after them. Mutation 12 swaps the two — the event's
effect is recorded *before* its locks — and the suite is green.
`check/node.rs:340-365` requires that no try fails under the word and that the
word is taken with no lock held, but not that a lock comes before the steps of
the effect.

Smallest correction: an invariant that, between `Step::Quiet(true)` and
`Step::Quiet(false)`, every `Step::Wait` or `Step::Pay` step of the event
follows at least one `Step::Lock` of the same event.

### 14. Minor — the end of a start has no due instant: mutation 18 survives

Contract, `:1390` (mode 0 of the start): the caller "sends the wake again at a
due event of its first core every `START_RETRY_NS` (D-135) until the core's
`started` equals its request or the node no longer reads starting with its
generation"; `:1345` and the table of §"What a death does at each step of a
start" (`:1398`): a node that does not beat "within `START_NS`" is accused with
stale.

Model, `nodes.rs:1686-1688` lists `start.since + START_NS` among the instants of
`reserve_due`; mutation 18 removes it and the suite is green. The accusation
still happens, at the next instant of the reserve, which is at most one
`RECOVERY_PERIOD_NS` (10 ms) late — so the model has no bound of `START_NS` on
that accusation, and no test measures it.

Smallest correction: a test that hangs a start and asserts the accusation at
`since + START_NS` exactly (as `pass18.rs:615` does for the wakes).

### 15. Minor — R2 for an unfenced peer does not check that no remote capability is left: mutation 22 survives

Contract, `:1309-1311`: "When *Y* sees *X* in **fenced** (or unfenced, for R2 to
R4 only …) it finishes, in steps of its recovery reserve: **R2.** It removes
every translation it holds to memory of *X* … **R2 is done when no such record
remains**".

Model, `nodes.rs:1148-1156` (`audited`) requires R3, an empty audit list and
`!self.remotes.values().any(|r| r.node == node)`. Mutation 22 makes the last
conjunct compare `node + 1` — it is then always true — and the suite is green,
which means no test resumes beside an unfenced peer that still holds a remote
capability of it. `pass18.rs:477` (`a_node_resumes_while_a_peer_is_unfenced`)
has no grant.

Smallest correction: give the resuming node a remote frame capability of the
unfenced peer before it seals, and assert the resume does not become live until
R2 has removed it.

### 16. Minor — `the_core_that_completes_a_request_writes_its_state_word_done` cannot tell which core wrote the word

`pass18.rs:679-690`: the requester is core 0 (`k.m.cores[0].request_state`) and
core 1 acknowledges. Mutation 33 writes `Done` into `cores[0]` instead of
`cores[requester]` and the test is green, because the requester is always core 0
in every scenario that completes a request, so the two writes are the same
write. The direction the contract gives (`:633`: "the completing core … writes
when it empties and frees it") is guarded, weakly, by the invariant
`check/node.rs:157-165` (`in_use == request.is_some()`), and by that alone.

Smallest correction: a scenario whose requester is core 1 (an idle core 0 owed
the invalidation), asserting `cores[1].request_state == Done` and
`cores[0].request_state != Done`.

### 17. Minor — `a_late_start_wake_of_a_running_core_changes_nothing_on_arm64_and_risc_v` is guarded by `stop()`, not by the test

`pass18.rs:47`. Mutation 35 makes `late_wake` call `self.stop(core)` on ARM64
and RISC-V as well, and the test is green: on ARM64 `stop` does nothing at all
unless a mark is set (`system.rs:641`), and on RISC-V the mark guards it
(`system.rs:660`). So the sentence the test names (`:1207`: "A repeated
`CPU_ON` to a core already on returns `ALREADY_ON` or `ON_PENDING` and starts
nothing") is established by the fence's own guard, and the test would pass whatever `late_wake` did with a
running core. That is a proof narrower than its name, not a wrong test.

Smallest correction: assert the hardware state and the beacon directly after the
late wake on each architecture (the test already compares `parked`; add
`Hardware` and the core word), and note in the test that `stop` is what refuses.

### 18. Minor — the owner word of a line is written and cleared by the model but no check compares the *raw* value with the gate's rule

`check.rs:316-338` builds `taken` from `Ownership::taken(Owner::Node(self.node), generation)`
and compares the set of line words that read that value with the set of lines
this node's `irq`s claim. Mutation 32 (`held == claimed` → `claimed.is_subset(&held)`)
is caught by `pass18.rs:1100`, so the one direction is covered; the other
(`held.is_subset(&claimed)`, a word taken by this node with no `irq`) is the
direction the test covers, and the value is never compared with what
`Table::may_take` would allow (a word taken by a *dead* node's generation reads
as "not taken by this generation", so it is invisible to 96 until R6 clears it —
which is what `:1311` and the barrier are for). I found no state where this is
wrong, and I record it as a limit of the invariant, not as a fault.

---

## Item 1: are the failing tries a real interleaving, and which paths are reachable?

Answer in three parts.

**(a) The holder is a shortcut, not a second core.** Findings 1 and 2 are the
argument. Concretely, what a real second core would do and the model does not:

- The holder's event runs only when the contending call *waits* for the lock,
  and always to completion (`let_go`, `locks.rs:414-424`); it is never in the
  middle of an event with its own locks held. A real second core entered its
  event before the first one and holds whatever it holds while the first core
  runs.
- The holder's event runs on the single-core path, so it makes no try and no
  wait and its lock set is never compared with the one the caller holds. The
  model therefore permits two cores to hold one lock.
- The holder's trace is thrown away (`record_rounds`, `locks.rs:541-556`), so
  the L2 check (`check/node.rs:306-383`) never sees the second core's locks at
  all: a `Holder` whose `then` is a call that takes 20 locks in the wrong order,
  or more than its `k`, is accepted.
- `Holder::entered` (`locks.rs:91-99`, `entered` at `:97`) is written by the tests and read only by
  the watermark's return (`caps.rs:509`); the escalation, which is the one
  protocol the contract builds on the entry words (`:658`), does not read it.

So the claim "the model reaches a failed try, the second round, a changed link,
`again`, and the escalation by the quiet word" is true, and narrower than the
sentence it is a model of: it reaches those five states with a second core that
holds one lock and does nothing else while it is held.

**(b) Which paths of the contract's rule cannot be reached.** Each of these is
a sentence of `:652-658` that has no state in which the model could break it:

- "A lock that a call finds by reading an object it already holds locked … it
  tries" — reachable, and checked (`check/node.rs:336-341`), and mutation 11
  (inverting wait and try) is caught.
- "the call releases every lock it holds, having changed nothing" — reachable;
  mutation 7 is caught. Nothing checks the *amount* released: `held.is_empty()`
  is required before the next lock (`check/node.rs:322-327`), which is the
  right rule.
- "checks that the object it read still leads to the same lock" — reachable;
  mutation 5 is caught, but only by the one test at `pass18.rs:768`. The check
  itself has no invariant: a trace whose second round ignored a changed link
  would pass `check()` as long as the call returned `again`, and the model
  cannot return `again` with a changed link by construction.
- "A call writes nothing before its last try has succeeded" — **not
  reachable**: `contend` runs the call once, after every lock of the round is
  taken (`finish`, `locks.rs:523`). The call's effect never precedes a try, so
  the rule is vacuously true in the model and no mutation of `model/src/` can
  express a violation. This is the largest gap of the pass: the sentence D-135
  added "the call writes nothing before its last try has succeeded" has no
  executable check.
- "an event that is not a call … cannot return `again`" — reachable for a
  `signal` (mutation 3 caught) and for an arrival (`pass18.rs:953`); mutation 4
  (an arrival returns `again`) is caught.
- "at most two rounds" — the check counts `TryFailed` steps (`check/node.rs:360`)
  and the three-round trace of `pass18.rs:889` is refused.
- the quiet word waits for the entry words — **not reachable** (finding 2).
- the quiet word raises the epoch — reachable in code, unchecked (finding 3).
- the count of `again` and its reset — the count is reachable and checked by one
  test; the reset is not (finding 5).

**(c) Does the L2 check refuse every wrong order, or only the ones its tests
feed it?** Only some. `check/node.rs:306-383` refuses: a wait for a lock not
after every lock held; a try of a lock that is not before a lock held; a lock
taken after a failed try while a lock is held; more than two failed tries; the
quiet word with a lock held, or a try under it, or held past the end; more than
`k` at once; the gate lock not last; a lock without its instruction. It does
*not* refuse: an event that holds a lock and writes an object guarded by another
lock when the object it changed is not a change `Snapshot` compares. The
comparison takes threads, endpoints, replies, notifies, timers, tasks and sched
state whole, every slot of a `cspace` by value, and every `irq` whole (to the
core word of its core); it takes an aspace or an iospace **by three counts
only** (`locks.rs:724-731`, `(translations.len(), records.len(), threads.len())`)
and an untyped by `(watermark, clean)` only (`locks.rs:746-749`). So a change to
a mapping's protection (the counts stay the same), or to an untyped's `live`,
`ready` or `zero` alone, is not a "changed object": an event can change it and
take no lock for it. And it does not refuse anything
about the second core (finding 1) or about the writes of an escalation
(finding 13).

The answer to the author's own question — "the model locks a woken thread and
its reply object by their own lock words where the contract guards them by the
endpoint's lock, *and the checker accepts both*: is that a hole?" — is **yes**,
and finding 6 gives the sentence and the state.

---

## Item 2: the pass-18 features, sentence by sentence

For each: the contract's sentence, the code, and a state where they differ (or
"no difference found").

| # | Feature | Contract | Code | Verdict |
|---|---|---|---|---|
| 1 | the quiet word, the `again` count | `:658` | `locks.rs:558-583`, `lib.rs:695`, `check/node.rs:348-356` | differ: findings 2, 3, 5, 13 |
| 2 | the entry words, the kernel epoch | `:657-658` | `caps.rs:509-514`, `cores.rs` (part), `lib.rs:1076` | differ: findings 2, 3 |
| 3 | the watermark ready to return | `:657`, `:164` | `caps.rs:434-446`, `485-503`; `lib.rs:590` | agree on the rule (`pass18.rs:1058` fails under mutations 13, 14, 16); differ in the layout: no word 6 in `abi/` (finding 3) |
| 4 | the owner word of a line | `:749`, `:1311` | `irq.rs:58`, `80-88`, `137`, `345`; `table.rs:654-674`; `check.rs:316` | agree except the bound (finding 9) and the set comparison (finding 18) |
| 5 | the sweep as a due event; `Ping` removed | `:1278`, `:914`, `abi/src/ring.rs:74-110` | `nodes.rs:1680-1681`, `nodes.rs:761-766`, `ring.rs:80-110` | agree; `NodeMessage::from_raw(9) == None`, `ALL` is 11, `pass18.rs:644` and `:658` hold. Mutations 24 and 43 (removing the sweep's instant) are both caught (item 3a) |
| 6 | the start retry | `:1390` | `nodes.rs:1655-1660`, `1645-1652`, `1665-1700` | agree; mutation 17 is caught by `pass18.rs:615`; the end of a start has no due instant (finding 14) |
| 7 | the state word of an invalidation request | `:633` | `cores.rs:74-88`, `311`, `346`, `425`, `588`; `check/node.rs:157-165` | agree; the invariant binds it (`the_core_that_completes…`, mutation 34 caught); the *writer* is untested (finding 16) |
| 8 | the stop of a core on each architecture | `:1283-1296` | `system.rs:425-440`, `551-575`, `588-670` | agree; mutation 36 (RISC-V stop without the mark) and 37 pass under the tests; the entering-core arms are new and `pass18.rs:74`, `:90` bind them |
| 9 | the fence record | `:1283-1285` | `abi/src/machine.rs:271-301`, `table.rs:161-195`, `nodes.rs:897-908`, `1349-1351` | agree on the layout (544 bytes, `stop_index` = core mod 64, written anew, R6 reading `last_stop` only for its generation); differ at the take-over (finding 10) |
| 10 | the holder's operand checks | `:1012-1021` | `units.rs:279-315` | agree except the class of an attach's root (finding 12); the masked redirection's second operand is bound (`pass18.rs:335`, mutation 37 caught) |
| 11 | `resume_step` beside an unfenced peer | `:1391`, `:1309` | `nodes.rs:1526-1545`, `1148-1156` | agree; R2's remote-capability clause is unbound (finding 15); the reset of a restarted peer is unbound (finding 7) |
| 12 | the memory of a destroyed object | `:657` | `caps.rs:428-450`, `485-500` | agree; `check.rs:759-770` reads `ready` |

Two smaller observations on this list, both checked and found correct, are worth
recording because they look like faults and are not:

- `model/src/irq.rs:57-60` returns `unsupported` for a line beyond the bound
  *before* the `busy` of the vector (`:749`: "Then `unsupported` if … the source
  is a line beyond the last line word"), and `abi/`'s `IRQ_LINES_MAX` is 4,096
  as the contract says.
- `nodes.rs:1330-1336` clears the line words of a dead generation in the same
  phase as the use entries but one word per unit, which is what `:1311`'s bound
  asks for ("or one line word").

---

## Item 3: the two mutations the author left green and calls equivalent

**(a) "removing the sweep's armed instant — an old observation instant also
keeps the first core's timer armed".** The claim does not reproduce. I ran it
twice, in `reserve_due` (`model/src/nodes.rs:1680-1681`):

```
old:        let mut instants: Vec<u64> = Vec::new();
            if self.others_exist() {
                instants.push(self.next_sweep);
            }
new (24):   let mut instants: Vec<u64> = Vec::new();
new (43):   let mut instants: Vec<u64> = Vec::new();
            if self.others_exist() {
                let _ = self.next_sweep;
            }
```

Both are **not green**. Both fail
`scenarios::membership::a_node_that_does_not_consume_a_message_waiting_in_its_ring_is_accused_stuck`
at `model/src/scenarios/membership.rs:414` with `left: None, right: Stuck`: the
stuck accusation of a node with a message waiting arrives at the wrong instant.
The observation the author made is true for one test and one test only:
`the_first_core_of_an_idle_live_node_keeps_its_sweep_armed` (`pass18.rs:644`)
stays green, because its assertion is `idle_until <= now + sweep_ns` and an
observation expiry instant inside that window satisfies it — which is precisely
"an old observation instant also keeps the timer armed". So the mutation is a
*weaker* mutation than the author's claim: it does not break the timer-armed
property the sweep test names, and it does break the sweep's own accusation
clock. My reading is that the author ran it and saw `pass18.rs:644` pass; the
suite as a whole does not.

**(b) "the reset of the reclaim of a restarted peer".** The claim reproduces:
mutation 25 (`nodes.rs:1060-1063`, dropping the `|| self.reclaims.get(&node).is_some_and(|r| r.generation != g)` clause) is
green over the whole suite. I judge the mutation *not* equivalent, for the
reason in finding 7: the record's `generation` is read nowhere else, and a
record of a finished generation makes R2, R3 and R5 of the next one read as
done. I did not build the state that shows it (two deaths of one peer with a
remote capability in the second generation); the argument is from the code, and
finding 7 says what a test would have to do.

---

## Item 4: finding 15 of the ninth review

Reproduced (finding 4 above), at the transition `core_entered` makes. I could
not drive it through a real `node_stop` seal and `node_start` resume in the time
I had: the model's seal/resume is a `System` protocol in steps of the recovery
reserve, and my attempts to produce a throttled context by running the model
(`S::two()` and `m.run(MS)` forty times) never throttled anything, because the
first thread of a node of `Machine::example()` is not run at all while time
passes. The state I did build is the one the finding's sentence describes, built
by hand, and the failing line is its own.

---

## Item 5: 42 mutations of my own

Every mutation is applied by a script that asserts the replaced text occurs
exactly once in the file, then `cargo fmt --all`, then `./verify`, in a fresh
copy of the clone:

```
git clone --branch model /private/tmp/dodos-kernel-review10 /private/tmp/mut<N>
python3 /private/tmp/mut_run.py mNN /private/tmp/mut<N>   # asserts one occurrence, patches
cd /private/tmp/mut<N> && cargo fmt --all && ./verify
```

"green" means exit 0 and 47 `test result: ok` lines. "caught" gives the test
that failed, at its own assertion unless noted.

| id | file:line | mutation (old → new) | contract | result |
|---|---|---|---|---|
| m01 | locks.rs:563 | `if tries >= 2 {` → `if tries >= 1 {` | `:658` escalates when the count "is already 2" | caught: `pass18.rs:818` |
| m02 | locks.rs:530-535 | the `t.again_tries = 0;` of `finish` → `let _ = t;` | `:658` "any other result … sets the count to 0" | **green** (finding 5) |
| m03 | locks.rs:606-608 | `!matches!(self, Self::Call(_, call) if !matches!(call, Signal(_)))` → `!matches!(self, Self::Call(..))` | `:655` "`signal` never returns `again`" | caught: `pass18.rs:881` |
| m04 | locks.rs:606-608 | the same predicate inverted with `matches!` | `:654` "An event that is not a call … cannot return `again`" | caught: `pass18.rs:881` and two more |
| m05 | locks.rs:509 | `let changed = first[..=failed].iter().any(...)` → `let changed = false;` | `:652` the second round "checks that the object it read still leads to the same lock" | caught: `pass18.rs:787` |
| m06 | locks.rs:482 | `first[..=failed].to_vec()` → `first[..failed].to_vec()` | `:652` "takes the locks it now knows it needs in the order" | caught: `pass18.rs:764` |
| m07 | locks.rs:479 | the `release(&held, &mut steps);` of the second round → `let _ = &held;` | `:652` "the call releases every lock it holds" | caught: `pass18.rs:758` |
| m08 | locks.rs:566-569 | the `let_go` loop of the escalation → `let _ = held;` | `:658` "waits until the entry word of every other core … runs the call alone" | **green** (finding 2) |
| m09 | locks.rs:565 | `self.kernel_epoch += 1;` of the escalation, removed | `:658` "raises the node's kernel epoch by one" | **green** (finding 3) |
| m11 | locks.rs:432 | `held.iter().all(\|&h\| h < lock)` → `h > lock` | `:652` "A core waits for a lock only in the order by kind" | caught: `pass18.rs:758` |
| m12 | locks.rs:573-578 | the escalation's locks pushed *after* `run_once(&event)` | `:658` "runs the call alone, taking its locks in the order" | **green** (finding 13) |
| m13 | caps.rs:437-446 | the `if clearing != WithinCall && let Some(epoch)` block → `if false && …` | `:657` "until then `untyped_retype` on it returns `again`" | caught: `pass18.rs:1083` |
| m14 | caps.rs:513 | `h.entered < epoch` → `h.entered <= epoch` | `:657` "0 or at least that value" | caught: `pass18.rs:1083` |
| m15 | caps.rs:489 | `if watched && live == 1 {` → `if watched {` | `:657` "When the last object of an untyped is destroyed" | **green** (finding 3) |
| m16 | caps.rs:496 | `(0, true) => ready = Some(epoch)` → watermark reset at once | `:657` the return happens at the first `untyped_retype`, not at the destruction | caught: `pass18.rs:1083` |
| m17 | nodes.rs:1631 | `start.last == 0 \|\| self.now >= start.last + START_RETRY_NS` → `start.last == 0` | `:1390` the wake is sent again every `START_RETRY_NS` | caught: `pass18.rs:615` and `membership` |
| m18 | nodes.rs:1688 | `instants.push(start.since + START_NS);` removed | `:1345` accused "within `START_NS`" | **green** (finding 14) |
| m19 | nodes.rs:898-902 | the record written anew → the old `generation` kept, `started` replaced | `:1285` "writes the record anew (that generation, its instant, every other word 0)" | caught: `cores`/`crossing` (4 tests) |
| m20 | nodes.rs:1333 | `(None, Some(gsi)) => write_line(…, None)` → `(None, Some(_)) => cursor = Clear { phase: 4 … }` | `:1311` "every line word taken by *X*'s generation, which becomes *free*, unclaimed" | caught: `pass18.rs:434` |
| m21 | nodes.rs:1351 | `self.now < last + SETTLE_NS` → `self.now < last` | `:1311` "`SETTLE_NS` have passed since the last stop sent to it" | caught: `mistral.rs` f3 |
| m22 | nodes.rs:1153 | `r.node == node` → `r.node == node + 1` in `audited` | `:1311` R2 "is done when no such record remains" | **green** (finding 15) |
| m23 | nodes.rs:1549-1551 | the `ended_done.insert` guard removed | `:1391` "R0 once for that generation" | **green** (finding 8) |
| m24 | nodes.rs:1680-1681 | the sweep's instant removed, `others_exist` gone too | `:1278` the sweep is a due event every `SWEEP_NS` | caught: `membership.rs:414` |
| m25 | nodes.rs:1060-1063 | the `\|\| self.reclaims.get(&node).is_some_and(\|r\| r.generation != g)` clause removed | the reclaim of a generation that is over (finding 7) | **green** |
| m26 | roles.rs:341 | `let same = record.generation == member.generation();` → `true` | `:1285` "word 0, the generation the record concerns" | **green** (finding 10) |
| m27 | roles.rs:347 | `+ FENCE_NS + SETTLE_NS` → `+ FENCE_NS` for an unfenced peer | `:1297` "`FENCE_NS` + `SETTLE_NS` after the first fence action" | **green** (finding 11) |
| m28 | irq.rs:58 | `>= IRQ_LINES_MAX` → `> IRQ_LINES_MAX` | `:749` "a line beyond the last word is `unsupported`" | **green** (finding 9) |
| m29 | irq.rs:80-84 | `let line_taken = source.is_line() && …` → `false && …` | `:755` "`busy` if the source is a line whose word the rules of taking refuse to this node" | caught: `pass18.rs:391` |
| m30 | irq.rs:135-138 | the `write_line` of the claim → `let _ = taken;` | `:749` "`irq_claim` of a line takes the line's word for the caller's node" | caught: `check::tests`, `pass17`, `pass18` |
| m31 | irq.rs:344-346 | the `write_line(…, None)` of the removal → `let _ = entry.source.id();` | `:749` "the removal of the `irq` writes it *free*, unclaimed" | caught: `pass18.rs:391` |
| m32 | check.rs:333 | `match held == claimed {` → `match claimed.is_subset(&held) {` | `:749` invariant 96 | caught: `pass18.rs:1100` |
| m33 | cores.rs:425 | `cores[requester].request_state = Done` → `cores[0]…` | `:633` "the completing core" writes *done* | **green** (finding 16) |
| m34 | cores.rs:311 | `request_state == InUse` → `== None` at the start of a request | `:633` "a core starts a new request only once its previous one reads *done*" | caught: 4 tests in `cores` |
| m35 | system.rs:429 | `(Aarch64 \| Riscv64, _) => {}` → `self.stop(core)` | `:1207` a wake to a core already on "starts nothing" | **green** (finding 17) |
| m36 | system.rs:660 | the `(Riscv64, _) if !self.marked(core) => {}` arm removed | `:1207` "the gate sends an NMI, SDEI event 0 or the RISC-V stop only to a marked word" | caught: `pass18.rs:61` |
| m37 | units.rs:307 | `target == Masked && (free \|\| names)` → `(free \|\| names) && matches!(target, _)` | `:1020` "masked: the line's word is free or names the requester" | caught: `pass18.rs:335` |
| m38 | units.rs:287 | `class == Some(IOSPACE_TABLE)` → `class.is_some()` | D-135 (12), `:1016` G9 | **green** (finding 12) |
| m39 | boot.rs:661 | `named.contains(&booted[0])` → `true` | "leaves the core firmware booted in no node" | caught: `pass18.rs:140` |
| m40 | check/machine.rs:90-94 | `runners.all(…)` → `.take(1)` then `all` | P2: the core word names one node | caught: `pass18.rs:571` |
| m41 | check/machine.rs:134 | `floor.is_none_or(\|n\| self.running_node(n as u16))` → `floor.is_none_or(\|_\| true)` | G4 on a floor chunk while its node does not run | caught: `crossing.rs:690` and `cores` |
| m42 | ipc.rs:334 | `self.touch(LockId::Notify(notify));` → `let _ = notify;` | `:655` "`notify_bind` with endpoint 0 … tries it before it writes anything" | caught: `pass18.rs:1033` |
| m43 | nodes.rs:1679 | `instants.push(self.next_sweep)` → `let _ = self.next_sweep;` | `:1278` the sweep's due event | caught: `membership.rs:414` |

15 of 42 leave the suite green: m02, m08, m09, m12, m15, m18, m22, m23, m25,
m26, m27, m28, m33, m35, m38. Findings 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15,
16 and 17 are those fifteen, judged one by one; m35 is the one I judge
equivalent (the guard is elsewhere), and m33 is equivalent only because the
requester is core 0 in every scenario.

Four further mutations were written and rejected as *not* mutations, which is
worth recording because they are the natural next attempts: `tries >= 0` in the
escalation and removing `instants.push(start.last + START_RETRY_NS)` are both
killed by the same tests as m01 and m17; blanking `RequestState::Done` to `None`
does not compile (`variant Done is never constructed`), and blanking
`audited(node)` to `true` does not either (`method audited is never used`) —
a reader of my table should know that a mutation which only trips `clippy -D
warnings` is a mutation that was not run.

---

## Item 6: twelve of the 39 tests of `scenarios/pass18.rs`, each failing for the reason its name gives

| test (line) | mutation that breaks the behaviour its name names | fails at |
|---|---|---|
| `under_l2_a_failed_try_takes_a_second_round_in_the_order_and_the_call_goes_on` (746) | m07 (no release after the failed try), m06 (the second round drops the failed lock) | `pass18.rs:758`, `764` — its own asserts that the call goes on and the lock is retaken |
| `under_l2_a_link_changed_by_the_holder_makes_the_call_return_again_with_nothing_changed` (768) | m05 (no link check) | `pass18.rs:787` — the call returns `Waits` instead of `Again` |
| `under_l2_a_third_again_of_tries_escalates_to_the_quiet_word_and_runs_alone` (797) | m01 (escalate on the second `again`) | `pass18.rs:818` — `again_tries` is 1, not 2 |
| `under_l2_a_signal_whose_try_fails_never_returns_again` (859) | m03 (a `signal` may return `again`) | `pass18.rs:881` — the `signal` returns `Again` |
| `under_l2_a_watermark_returns_only_once_every_other_core_left_the_event_it_was_in` (1058) | m14 (entry word `<` → `<=`) | `pass18.rs:1083` |
| `r6_frees_the_line_words_of_a_generation_that_is_over` (434) | m20 (R6 skips the line words) | the test's own asserts on the word |
| `a_node_cannot_claim_a_line_that_another_live_node_holds` (391) | m31 (the removal does not free the word), m30 (the claim does not write it) | the test's own asserts |
| `a_line_word_taken_with_no_irq_of_its_node_is_reported` (1100) | m32 (invariant 96 reads any taken word) | its own assert on the report |
| `a_stop_that_reaches_an_unmarked_core_changes_nothing_on_every_architecture` (61) | m36 (the RISC-V stop ignores the mark) | its own assert that the core still runs |
| `the_holder_refuses_a_masked_redirection_entry_whose_second_operand_is_not_0` (335) | m37 (the target is not required to be masked) | its own assert |
| `the_start_up_refuses_a_layout_that_leaves_the_core_firmware_booted_in_no_node` (140) | m39 (`boot_core_placed` → `true`) | its own `assert_eq!` on `Refusal::Nodes` |
| `a_core_that_two_nodes_run_is_reported_by_p2_even_when_the_first_is_named` (571) | m40 (P2 over the first runner only) | its own assert on the report |

Three of the 39 do not fail for the reason their names give, which is item
6's own finding:

- `the_core_that_completes_a_request_writes_its_state_word_done` (679) — m33
  (the word written into the *requester*'s part is written into core 0's
  instead) is green, because the requester is core 0. Finding 16.
- `the_holder_refuses_an_attach_whose_root_is_not_an_iospace_table_of_the_requester`
  (291) — m38 (the class test weakened to "has some class") is green: its "not
  an iospace table" page has no class at all. Finding 12.
- `a_late_start_wake_of_a_running_core_changes_nothing_on_arm64_and_risc_v` (47)
  — m35 is green because `stop()` refuses; finding 17.

The remaining 24 tests I read but did not mutate one by one; I have no finding
about them beyond what the mutations above touch (m19 caught four tests across
`cores` and `crossing`, m21 caught `mistral`'s f3, m34 caught four tests in
`cores`, m30 caught `check::tests::a_line_claimed_twice_is_reported`, m41 caught
`crossing` and `cores`).

---

## Checked and found correct

- The layout facts of `abi/`: `IRQ_LINES_MAX = 4_096` (`machine.rs:118`),
  `FenceRecord` of 544 bytes with `stop_index(core) = core % 64`
  (`machine.rs:271-301`), `StartMachine` of 88 bytes with `lines` and
  `line_count` at 80 and 84 and `START_MACHINE_LAYOUT = 3` (`start.rs:343-380`,
  `tests.rs:949-955`), `NodeMessage` 1-8 and 10-12 with 9 reserved and
  `from_raw(9) == None` (`ring.rs:74-110`, `tests.rs:2308-2320`). Each is what
  `:1769-1771` says, and the three tests that pin them are not tautological
  except `the_eleven_kinds_of_message_have_their_numbers_and_rings`, which
  computes its expected number from the index (`tests.rs:2311-2314`) and so
  cannot catch a numbering change that `from_raw` follows.
- `check_lines` (invariant 96) and `check_identifiers` (88) have the same shape
  and the same limit; 96 is fed a bad state by `pass18.rs:1100`.
- The two assertions of the L2 check that the tests of `pass18.rs:889` feed
  (a lock after a failed try, three rounds, the quiet word with a lock held, a
  try under it) are each refused, and the `paid == locks.len() + tried` rule
  (`check/node.rs:371-382`) is what makes a `TryFailed` pay its instruction.
- The tests of the fence record (`pass18.rs:159`, `:183`) fail under m19, so
  both are bound to what they name; `the_fence_record_keeps_the_last_stop_of_a_core_at_its_number_mod_64`
  is the one I did not attack directly (no mutation of mine changes
  `stop_index`), so I neither confirm nor deny it.
- `model/src/irq.rs`'s claim path: the "asked at once" result of a claim served
  by the node's own IOAPIC or unit (`irq.rs:195-202`) is exercised by
  `pass18.rs:262`, and the unit chain of a claim by `pass18.rs:210`, `:251`,
  `:588`.
- The whole suite of the clone at `073ae9e` is green: `./verify` exit 0, 47
  `test result: ok`, about 91 s.

## Not checked or could not run

- I did not drive a whole seal-and-resume through `System` for finding 4; the
  reproduction is at `core_entered`, as item 4 says.
- I did not build the two-deaths-of-one-peer state that would show finding 7 as
  a divergence rather than as an argument from the code.
- `nix develop -c ./verify` was not run through `nix` (the rustc of the flake is
  already 1.100.0 outside it, so the binary and the tests are the same); Kani,
  Miri and the address sanitizer are CI only and were not run, so the four
  `core_words_*` proofs (`abi/src/machine.rs:1619-1670`) are not verified
  here.
- The seeded explorations (`scenarios/explore.rs`) ran as part of the suite but
  I did not run them over a range of seeds with `DODOS_SEED`, and I did not run
  `DODOS_COUNTS` to compare coverage floors.
- `model/tests/property.rs`'s floors are unchanged by pass 18 as far as I read
  the diff; I did not measure them.
- The other 27 tests of `pass18.rs`, and the tests of `pass17.rs`, `mistral.rs`
  and `check/tests.rs` beyond those the mutations above trip, I read but did not
  attack one by one.
- I did not check `plan/progress.md` (the documentation repository's rule that a
  moved box is part of done); pass 18's commits touch no documentation repo
  file, and `AGENTS.md` asks for one in the same change as the work.
