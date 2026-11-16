# The model against the contract: what crosses, grants, a thread on another core, the fence

Review of the executable model of the DodOS kernel, `dodos-kernel` branch `model`,
head 633f6f3 (pull request 3), against `architecture/kernel-interface.md` (decisions
read up to D-133). I read `AGENTS.md`, `model/README.md` and the skill `dodos-rust`,
then the contract's sections for the four mechanisms named in the task sentence by
sentence, and the code that must implement each sentence. I changed nothing in any
repository; the only file I write is this one.

Tests ran only in a copy: `/tmp/dk-review`, made with
`tar --exclude=./target -cf - . | (cd /tmp/dk-review && tar xf -)` from
`633f6f3`. There, `nix develop -c cargo test -p dodos-model` is green
(941 tests over the crate's targets, 0 failed). Every line I cite is from the
repository, not from the copy.

Three findings. The first is a state a call reaches that no sentence of the
contract allows; the other two are checks that cannot fail, one shown by a
mutation that leaves the whole suite green.

---

## Finding 1 — a message from a thread attached to no task is refused by the receiver, and its sender waits for ever

**Severity: breaks a guarantee.** Rule 4 of the contract (`kernel-interface.md:14`):

> 4. **Every call is bounded.** A long operation (revocation, deletion of a large
> object, clearing of memory) runs in bounded steps and returns `again`; the caller
> repeats the call.

The contract says what a message carries when it leaves (`kernel-interface.md:1083`,
with `kernel-interface.md:1061`):

> - the identifier of the sender's task (0 if the sender is attached to none);

> An identifier is never reused within one generation of the node, and identifier 0
> means "no task";

and what the receiver does with it (`kernel-interface.md:934`):

> a `Send`'s stamp carries a task identifier of the sender's node. A message that
> fails any of these changes nothing, is consumed, and is traced (code 11 of
> [What the kernel traces](#what-the-kernel-traces)).

The model stamps exactly what the first sentence says, and checks exactly what the
third says, and the two together lose the message. `model/src/grants.rs:292`:

```rust
    pub(crate) fn stamp_of(&self, thread: ObjId) -> (u64, u64) {
        let task = self.threads[&thread]
            .task
            .map_or(0, |t| self.tasks[&t].id.raw());
        (task, self.marks(thread).map_or(0, |m| m.bits()))
    }
```

written into the message at `model/src/grants.rs:261`:

```rust
        let (task, marks) = self.stamp_of(thread);
        ...
        let body = Body::Send {
            header,
            stamp: (task, marks | added),
```

and refused by the receiver's one check, `model/src/rings.rs:432`:

```rust
            Body::Send { stamp, .. } => {
                let task = dodos_abi::TaskId::from_raw(stamp.0);
                (task.node() != sender).then_some(stamp.0)
            }
```

`dodos_abi::TaskId::node()` is `(raw >> 48) as u16` (`abi/src/lib.rs:1061`), so a
stamp of 0 — "no task" — names node 0.

**Inputs that make them differ.** Two nodes of one core each (`Machine::example()`
through the harness `S` of `model/src/scenarios/mod.rs`). The first thread of node 1
leaves its task, which is the contract's own detach (`task_attach`, task 0;
`model/src/tasks.rs:45`); a thread freshly made by `untyped_retype` is in the same
state, since a new thread is attached to no task. Node 1 sends an empty message to
node 0 with `node_send` (no frames, no doorbell):

```rust
    let _ = m.call(1, Syscall::TaskAttach {
        thread: s(dodos_abi::START_SLOT_THREAD),
        task: SlotAddr::NONE,
    });
    assert_eq!(m.call(1, send(0, vec![], SlotAddr::NONE)), WAITS);
    m.sys.settle(100_000);
```

What the model does, printed from that probe in the copy:

```
refused 0 -> 1; wait Node { peer: 0, credit: 16 };
check Err("CREDIT: a credit in use with neither its request nor its answer in flight")
```

Node 0 consumed the message and refused it (`model/src/rings.rs:489`, the `Some(named)`
arm, one entry of the `refused` count and one code-11 trace), and wrote no
`SendAnswer`: a refused message is consumed and answers nothing. Node 1's thread waits
in `Wait::Node { peer: 0, credit: 16 }` — a send credit in use — and nothing ends that
wait: R0 ends it only when node 0 is accused (`model/src/nodes.rs:942`), and a node
that merely refuses a message is healthy. The call is then not bounded, and the model's
own `CREDIT` invariant (`model/src/check/machine.rs:225`) says so at the next step, so
this is not a silent state: no scenario of the model may enter it.

Two smaller points that follow from the same lines, and that I did not need to run:
the check is asymmetric (a taskless sender whose node index is 0 passes, since
`0.node() == 0`), and the shape is reachable from the documented calls alone, without
any fault.

**Smallest correction.** In `refused`, treat a task identifier with a zero counter as
what the contract says it is — no task — instead of as node 0:

```rust
            Body::Send { stamp, .. } => {
                let task = dodos_abi::TaskId::from_raw(stamp.0);
                (task.counter() != 0 && task.node() != sender).then_some(stamp.0)
            }
```

and in `kernel-interface.md:934`, "a `Send`'s stamp carries a task identifier of the
sender's node, or 0 for a sender attached to none". Either correction alone removes the
stuck wait; both are needed for the model and the text to say one thing.

---

## Finding 2 — the `RESERVE` invariant cannot fail

**Severity: a check that cannot fail** (the sentence it names is `kernel-interface.md:943`).

> **Answers** (`RevokeStep`, `UnitAnswer`, `Report`, `SendAnswer`) always have room:
> the kernel ring *Y* → *X* keeps `REQUESTS_PER_PEER` + `SENDS_PER_PEER` + 10 entries
> (34) for the answers to *X*: one entry for each credit *X* can have in use toward
> *Y*, and 10 more because a `Report` takes up to 11 entries; a new holder has at most
> one `ReportAsk` in flight to each node, whatever the number of units it rebuilds, so
> one `Report` at most is owed to it.

The check, `model/src/check/machine.rs:196`:

```rust
        for (x, model) in self.models() {
            for y in (0..n).filter(|&y| y != x) {
                let peer = &model.peers_of(y);
                let owed = peer.iter().flatten().count() as u64;
                ensure(
                    owed <= RING_ANSWER_RESERVE,
                    "RESERVE: answers owed exceed the reserve",
                )?;
```

`owed` is the number of *credits* in use toward `y`. `peers_of` returns
`self.peers[peer].credits.clone()` (`model/src/check/machine.rs:305`), and that vector
is `vec![None; REQUESTS_PER_PEER + SENDS_PER_PEER]` (`model/src/rings.rs:205`), so
`owed ≤ 16 + 8 = 24`. `REQUESTS_PER_PEER` and `SENDS_PER_PEER` are 16 and 8
(`abi/src/ring.rs:19-20`), and `RING_ANSWER_RESERVE` is `16 + 8 + 10 = 34`
(`abi/src/ring.rs:34`). `24 ≤ 34` always: the ensure is a tautology, and the node's own
check asserts the vector's length (`model/src/check/node.rs:328`), so no reachable
state makes it false. It is listed as one of the invariants that holds because the
seeded explorations check it (`model/src/scenarios/explore.rs:7`).

It is not only too weak in its bound; it counts the wrong quantity. The sentence bounds
the *entries* the answers take — a `Report` takes 11 entries of the 34 — and no check
anywhere counts the entries of the answers owed against what the ring has free. The
`Report`-takes-eleven case is the whole reason for the `+ 10`, and nothing tests it.

**Smallest correction.** Count entries instead of credits, and against the room the ring
actually has:

```rust
                let owed: u64 = peer.iter().flatten()
                    .map(|c| match c.completes {
                        Completes::Report { .. } => RING_MESSAGE_ENTRIES_MAX as u64,
                        _ => 1,
                    })
                    .sum();
                let free = ring_free(produced, consumed, RING_KERNEL_ENTRIES);
                ensure(free >= owed, "RESERVE: ...")?;
```

(where `produced`/`consumed` are the indices of the ring `y` → `x` into `x`). A cheaper
equivalent, in the spirit of the sentence quoted: check its premise instead — at most
one `ReportAsk` in flight to each node across all rebuilds, which `roles.rs:459` already
enforces as `busy`.

---

## Finding 3 — the fence's "park request before the mark": the model cannot show it, and the check named after it cannot fail

**Severity: a check that cannot fail.** The contract (`kernel-interface.md:1261`):

> For **each** physical core *p* whose word names *X*'s generation (owned or joining),
> in parallel: the driver raises *p*'s park request, then marks *p*'s word, then stops
> *p* by the means of its architecture; and it cancels every start request aimed at *X*.

with its reason (`kernel-interface.md:1182`):

> **Why the request before the mark:** a confirmation read between the two would answer
> the previous park (DeepSeek, [second round](../reviews/2026-11-16-verify-kernel-shape-round2-by-deepseek.md), fault 1).

and the gate's condition for the mark (`kernel-interface.md:1171`): "*N* is fencing or
unfenced with *g*, and this driver raised the core's park request first (below)".

The model implements the order (`model/src/nodes.rs:911`):

```rust
        for core in unconfirmed {
            let word = self.table.core_word(core).expect("names the node");
            if !word.is_marked() {
                // The park request first, then the mark.
                self.table.park_requests[core] += 1;
                let before = self.table.core_words[core];
                self.table.write_core(core, before, word.marked());
            }
            self.hw_out.push(HwAction::Stop { core });
```

and the invariant that names it (`model/src/check/machine.rs:77`):

```rust
            ensure(
                !word.is_marked() || table.park_requests[core] != 0,
                "fence: a word marked before its park request was raised",
            )?;
```

**Mutation, in the copy only.** I swapped the two statements of `model/src/nodes.rs:914`
(the mark written first, then the request raised) and ran
`nix develop -c cargo test -p dodos-model` in `/tmp/dk-review`: 941 tests, all green,
before and after. The mutation is not a slip in the check — it is invisible to the model.

Why it cannot fail:

- `park_requests[core]` is raised by one and, per the contract
  (`kernel-interface.md:1177`), "never lowered and never reset". After the first fence
  or seal of a core, `park_requests[core] != 0` is true for the rest of the machine's
  life, so the ensure is unconditionally true for every core that was ever fenced,
  however the mark was written. It can only bite on a core's very first fence.
- Even there it sees nothing. One fence step is one event of the driver, and the check
  runs after it: the request and the mark are both in place by then, so the two orders
  produce the same state. No input reaches a state where the ensure's left side is
  true and its right side false through the code, which is why the swap is green.

`check/machine.rs:73` ("a stop in flight under a word that is not marked") is a real
check — it needs the stop to still be in the action list — and the mutation leaves it
untouched.

**Smallest correction.** The check needs the request the core had when the record
started, which the fence record has room for: the contract's word 3 of the record is
"reserved, 0" (`kernel-interface.md:1261`), and the model's `FenceRecord`
(`model/src/table.rs:165`) has no generation word at all. Write, at `started`
(`model/src/nodes.rs:908`), the count of parks given to each of *X*'s cores, and
require for a marked core of a fencing generation
`park_requests[core] > that_count` instead of `!= 0`; then the swap of the two
statements in `fence_unit` fails the check, and the model shows the order the contract
argues for.

---

## What I checked and found correct

Each line is a sentence of the contract and the code that implements it. Where I name a
function I read all of it.

### 1. What crosses between nodes (the rings, credits, the reserve of answers, the one check, resync)

| Contract sentence | Code |
|---|---|
| twelve kinds, two rings per ordered pair, kinds 1–10 kernel and 11–12 user ("Two rings per ordered pair") | `dodos_abi::NodeMessage` and `NodeMessage::ring()` `abi/src/ring.rs:115`; `Model::ring_of` `rings.rs:247` |
| a header and entries of 64 bytes, 64 entries each, a message takes ⌈(16 + 8 × words)/64⌉ entries (gap 3) | `RING_ENTRY_BYTES`, `RING_KERNEL_ENTRIES`, `message_entries` `abi/src/ring.rs:11-27`, `:148`; `Body::words`, `Body::entries` `rings.rs:139`, `:153` |
| the header: kind, length, sender's node and generation, receiver's generation, credit and serial | `RingHeader` `abi/src/ring.rs:192`; written at `rings.rs:311` |
| producer index in the ring, consumer index in the receiver's beacon, both never going back | `write_message` `rings.rs:282` (`ring.produced += entries`); `consumed`/`set_consumed` `rings.rs:253`, `:513` |
| "the receiver drains both rings at once. No message waits in a ring for a user thread: a `Send` that finds no receiver waiting is answered `would_wait` and consumed" | `send_received` `grants.rs:350` (the `receiver` is filtered to the first waiter with an own context; the else writes `delivered: false`), `sent()` `grants.rs:48` → `would_wait` |
| the user ring served at its interrupt, at most 16 entries per ring, the interrupt repeated while entries remain | `serve_user_rings` `rings.rs:531`, `RING_USER_STEP` `abi/src/ring.rs:27`, re-insert of `Ipi::Ring` `rings.rs:545` |
| the kernel ring served in the recovery reserve, each message one unit | `serve_kernel_rings` `rings.rs:550`, called from `reserve_step` `nodes.rs:1710` |
| the one check on every message received, before anything changes, and a refused message consumed and traced | `refused` `rings.rs:351`, `consume` `rings.rs:454` (`set_consumed` before the apply, `TraceCode::Refused`) |
| a header it cannot read consumed as one entry; a producer more than the ring's entries ahead moves the consumer to the producer minus the entries; both traced | `RingHeader::readable` `abi/src/ring.rs:238`; `ring_resync` `abi/src/ring.rs:178`, used at `rings.rs:465`; the trace at `rings.rs:468` |
| credits: 16 requests and 8 sends per peer, in use until the answer or the peer's generation ends (R0) | `Peer` `rings.rs:186`, allocated in `write_message` `rings.rs:301`, freed by `take_credit` `rings.rs:344`, dropped by `r0` (`self.peers[node] = Peer::new()`, `nodes.rs:963`) |
| answers always have room; a request with no credit free returns `again` with no wait; a `Release` waits as *release pending*; a `Signal` as *signal pending*, 32 per event in the order of the use table; a `Send` beyond 8 is `busy` | `ring_room` `rings.rs:261` (reserve 34 for a kernel message that is not an answer, 0 for an answer or a user message); `revoke_anchor` `grants.rs:618`; `remote_destroyed` `grants.rs:772`; `grant_signal` `grants.rs:557`; `send_pending` `rings.rs:625` over a `BTreeMap` of use entries (`table.rs:284`), so ascending index = the use table's order; `node_send`'s `SENDS_PER_PEER − 2` for a capability without `manage`, `grants.rs:215` |
| what ends with a generation: R0 drops the credits and the pending signals and releases; a fresh start sets every consumer index to the producer index; a resume keeps them and runs the steps first | `r0` `nodes.rs:942`; `skip_rings` `rings.rs:686`; `resume_step` `nodes.rs:1494` |

The refusal counter and trace, the resync, and the consumer-index arithmetic behave as
written; I read `consume` end to end. Finding 1 is the one message the check loses.

### 2. Grants and remote capabilities

| Contract sentence | Code |
|---|---|
| the anchor is a slot of the granting node's derivation list, a new child of the frame capability with the rights asked and badge 0 | `anchor_index` `grants.rs:43` (slot `1 + grant` of the node's kernel space, `build_kernel_space` `grants.rs:61`), `make_grant` `grants.rs:302` |
| the entry: grantee node and generation, a 30-bit serial, a state of free, live, revoking or pinned, the use index with *answered*, the doorbell and its links | `GrantEntry` `table.rs:176`, `free_grant` writing `(serial + 1) & 0x3FFF_FFFF` `grants.rs:112` |
| the serial grows at every freeing, R6's included, and a fresh start never resets it | `table.serials` survives a fresh start (the table is shared and `Model::start` reads it); `free_grant` `grants.rs:112`; `clear_step` phase 2 `nodes.rs:1296` |
| a remote frame capability is valid when the grant entry is live with that serial and the granting node's member word names the generation the use entry records, in a state starting, live, sealing or sealed (gap 10) | `valid` `grants.rs:79` |
| a use of an invalid remote capability is `gone` judged with the slot, and the slot becomes dead at the end of the call unless its record holds a mapping (gap 15) | `full` `lib.rs:1697` (the `invalid` test and `self.stale`), `dispatch`/`bury_stale` `lib.rs:1402`, `:1414` |
| only `node_send` makes a grant: 4 frames of the caller's own node, a `move` or a remote frame `invalid`, the rights a subset of the source's | `node_send` `grants.rs:146`, the list loop `grants.rs:189` |
| the receiver's range takes the remote capabilities all or none, else `caps_dropped`, and the `SendAnswer` carries each use index or none | `send_received` `grants.rs:350` (`room`, `uses_free`, `accepted`), `place_remote` `grants.rs:432`, `send_answered` `grants.rs:496` |
| the answer is applied whether or not the thread still waits | `send_answered` `grants.rs:496`, `forget_sender` `grants.rs:539`, `revoke_answered` `grants.rs:738` |
| revocation: not *answered* → `again` with no message; else *revoking*, then read the count at the use index, counted only if that entry names this node, this grant, its serial and its generation; 0 → freed at once; else a `Revoke` and a wait | `revoke_anchor` `grants.rs:618` |
| the holder's step: one removal step of at most 32 units on the root remote capability, `RevokeStep` answered at once, the root kept while a record under it is unmapping | `revoke_received` `grants.rs:709` → `remove_root` (removal machinery, `caps.rs`) |
| `Release` by the holder: free the entry once the message is in the ring, or *release pending*; no message for a generation that is over; a removal done for a `Revoke` sends none | `remote_destroyed` `grants.rs:772` |
| `Release` on a *revoking* entry ends the revocation, frees the entry, and a `Revoke` in flight stops counting as in flight | `release_received` `grants.rs:812` |
| `Revoke` reaching a use entry with *release pending*: the root is already removed, answer removed, drop the pending release, free the use entry | `revoke_received` `grants.rs:709`, first arm |
| a pinned grant: `again` with no message until the grantee releases or its generation is over | `revoke_anchor` `grants.rs:641`; `grantee_over` `grants.rs:139` |
| the doorbell: a notify of the granting node, its badge's bits, set as by `signal`; a dying notify gets nothing; a grant without a doorbell, revoking or pinned, nothing | `grant_signal` `grants.rs:557`, `signal_received` `grants.rs:582` |
| destroying a notify unbinds its doorbells, one unit each, after its timers, its irqs and its watches | `undoorbell_one` `grants.rs:601`, ordered in `caps.rs` (`ObjectKind::Notify` arm) |
| generations: a grant dies with its grantee's generation (pinned, then freed when the generation is over); R2 removes the holder's roots of a dead granter; a resume runs R0, R2, R3 and R4, R5 and sends no release | `reclaim_step` R3 `nodes.rs:1084`, `unpin` `nodes.rs:1374`, `resume_step` `nodes.rs:1494`, `drop_ended` `nodes.rs:1548` |

One limitation, which I do not report as a finding because no input can make it differ:
the contract fixes the order of the two writes under a grant ("When *Y*'s gate adds a leaf under a grant, it first adds it to the count of
its use entry, then reads the grant entry again, and undoes the count and refuses
(`gone`) if the entry is no longer live with that serial", `kernel-interface.md:880`). The model reads the grant entry first and
refuses before raising the count (`memory.rs:528`, `Error::Gone`), and raises the count
later in `record_mapping` → `count_leaves` (`memory.rs:51`, `:119`). Every kernel event
of the model is one atomic step, so the two orders cannot be told apart and no check
could catch a violation; the contract's "so at least one sees the other" is simply not
modelled.

### 3. A thread that runs on another core of its node

| Contract sentence | Code |
|---|---|
| a call that must stop a thread on another core marks it *leaving its core* and sends that core the leave interrupt | `mark_leaving` `cores.rs:217`, `post(core, Ipi::Leave)` |
| at that interrupt the core saves its registers, stops running it and clears the mark; while the mark is set the thread is not runnable | `leave` `cores.rs:236` called from the end of every event of the core (`sched.rs:253`), `runnable_thread` excluding `leaving` `sched.rs:426`, and `apply` refusing to run a marked thread (`lib.rs:1354`, `runnable()`) |
| no call reads or writes it: `thread_read_regs`, `thread_write_regs`, `thread_configure` are `busy`; `thread_suspend` returns `again`; a removal step returns `again` and sets the suspended flag (gap 14); `task_revoke` returns `again` while a thread of the task is marked; `sched_configure` waits for nothing | `faults.rs:159`, `:206`; `threads.rs:105`; `caps.rs:896`; `tasks.rs:125`; `sched.rs:747`, `:792` |
| the node accuses itself when a core stops answering, with reason 9 | `watch_own_cores` `cores.rs:605`, `accuse_self` `nodes.rs:499` |
| a change that removes or reduces translations is invalidated on every core of the space's set that is not idle; ARM64 in the call; x86-64 and RISC-V by the request of the calling core; the kernel's own space asks every other core, idle ones included | `others_hold` `cores.rs:253`, `start_request` `cores.rs:272` (the `Aarch64` broadcast, the idle-word skip `space.is_some() && idle.mark`, `None => all_cores()`), `invalidate_on` `cores.rs:348` |
| at the interrupt a core does what each request pending on it asks, clears its pending bit, sets its position in the acknowledged set, and the last acknowledgement completes the request in the same event | `answer_pending` `cores.rs:379`, `complete` `cores.rs:405` |
| a request that asks no core completes in the call | `start_request`, `if asked == 0 { self.complete(at) }` `cores.rs:331` |
| the counts are lowered at the completion, not at the clearing | `complete` → `finish_unmapping` `memory.rs:245`; `count_leaves` `memory.rs:119` |
| an idle core is not asked: it sets its mark before reading its pending set, the requester reads the mark and sets *owes*; waking clears both and invalidates every tag before loading a root | `go_idle` `cores.rs:444`, `wake_core` `cores.rs:463`, `load_root` `cores.rs:483` |
| a call that needs its core's request while it is in use returns `again`; a removal step never waits | `request_free` `cores.rs:567`, and the removal steps' `Undone::Wait` in `caps.rs` |
| a spurious fault is resolved on the faulting core without a message | `spurious` `cores.rs:528` |
| clean cores: a core invalidates its whole TLB before the node's first instruction | `core_entered`/`enter` `system.rs:659` (fresh TLB per `CorePart`) |

The checks that name these sentences are real, not tautologies: `check_tlb`
(`check/node.rs:82`) fails on any cached translation its space no longer holds unless a
request asks that core, the core owes it, or the core is silent; `check_requests`
(`:157`) fails on a request that asks its own core, is complete, or outlives
`CORE_ANSWER_NS`; `check_marks` (`:227`) fails on a marked thread on a core without the
leave interrupt pending.

### 4. The fence of every core of a node, and R0 to R6

| Contract sentence | Code |
|---|---|
| every core whose word names the generation, owned or joining; each raised, marked, stopped; every start request aimed at the node cancelled | `fence_unit` `nodes.rs:857` (`cores_of`, the raise/mark/stop order at `:911`, the cancellation in both arms) |
| the node is fenced when every core is confirmed, unfenced after `FENCE_NS`, tried again every `SWEEP_NS`, and the driver replaced when it stops writing | `fence_unit`, `fence_step` `nodes.rs:819` (the re-drive of a dead driver) |
| a confirmation counts only for the request current at that moment, by architecture: x86-64 `parked`, ARM64 and RISC-V the machine's answer (never the handler's own write) | `park_confirmed` `nodes.rs:589` |
| the fence record in the living part: the first action writes it, a driver that takes over keeps it, each stop writes its core's word, the confirmation once | `FenceRecord` `table.rs:165`, reset at the accusation `nodes.rs:474`, `started`/`confirmed`/`last_stop` written in `fence_unit` |
| the start request and `started`: the stub writes the request it takes, 0 when it parks; the starter sends the wake again every `START_RETRY_NS` until `started` equals its request or the node is no longer starting | `start_step` `nodes.rs:1576`; `wake` writing `started` `system.rs:650`; `write_parked` clearing it `system.rs:505` |
| the park request is a count, raised before the mark, in the gate of the node that asks | `nodes.rs:915` (the order is right; see finding 3 for the check) |
| R0 at the sight of fencing | `r0` `nodes.rs:942`, called from `observe_watched` `:532` and `reclaim_step` `:1048` |
| R1 on every unit role the node holds, done when the unit confirms | `r1` `nodes.rs:985`, `r1_done` `:1017` |
| R2 removes every translation it holds to the node's memory, done when no record stays unmapping | `reclaim_step` `nodes.rs:1068` |
| R3 pins the grants made to the generation, and frees each once the generation is over, one unit each | `reclaim_step` `nodes.rs:1084`, `unpin` `:1374` |
| R4 audits one block per unit and stops the machine on a mismatch | `reclaim_step` `nodes.rs:1097`, `audit_block` `:1145`, `containment_violated` `:1160` |
| R5 clears `maps_of` and writes `acked`, only when R1 is done and only for a fenced node | `reclaim_step` `nodes.rs:1130` |
| the barrier of the table, and R6: chunks and floor to map count 0 and class data, device entries to leaf count 0, grant and use entries freed, core words free once stopped and `SETTLE_NS` past the last stop, then dead | `barrier_holds` `nodes.rs:1172`, `clear_step` `nodes.rs:1226`, `dodos_abi::barrier` |
| the seal: hand the unit roles over, answer the kernel rings, finish the requests, write `sealed` last with the last park request in the same gate call; return to live when no other node is live | `seal_step` `nodes.rs:1407` |

The second fence check (`check/machine.rs:73`, "a stop in flight under a word that is not
marked") is the one that ends the fault the contract cites
(`nodes.rs:919` pushing `HwAction::Stop` only after the mark); it does fail when the
order of `nodes.rs:917` and `:919` is swapped, which I checked in the copy.

---

## What I did not check

- Kani, Miri and the sanitizers (not in Nix; CI only), and `verify` as a whole — I ran
  `cargo test -p dodos-model` only, and not on three page sizes.
- The twelve kinds one by one against their word layouts (gap 3) beyond `Send`,
  `SendAnswer`, `Revoke`, `RevokeStep`, `Release`, `Signal`, `ReportAsk`, `Report`,
  `Ping` and `UnitRequest`, which I traced; `UnitAnswer` and `Handed` I read only in the
  receive path.
- The rest of the model: the derivation tree, deletion, the scheduler and admission,
  the IOMMU, debug and start-up. I did not survey the 14,000 lines and did not audit
  `check/tests.rs`, whose 191 spoiled-state tests cover one node's invariants only —
  none of them covers a machine-level invariant (`RESERVE`, `CREDIT`, `LEAK`,
  `ONE-HOLDER`, P2, P3), which are left to the seeded explorations.
- The external facts the contract cites (the Intel SDM, TF-A v2.12.0, DEN 0022E, the
  SBI HSM extension, the Linux commits). They are outside my angle, and I did not open
  them today.
- The liveness of the other waits: I traced `node_send`, revocation, `Release` and the
  rebuild, not every wait the contract names.
