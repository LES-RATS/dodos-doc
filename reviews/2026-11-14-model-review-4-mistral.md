# Review of the DodOS kernel executable reference model (branch `model`) — 2026-11-14, Mistral

Reviewer: review sub-agent (Mistral). Scope: `dodos-kernel/model/` on branch `model`, against
`Docs/architecture/kernel-interface.md`, `dodos-kernel/AGENTS.md`,
`.agents/skills/dodos-rust/SKILL.md`, and `abi/src/lib.rs`. Read-only in the repositories; all
experiments were run in a scratch copy outside the repo
(`/Users/btw/.vibe/logs/session/unified/20d379bf-10a4-b8e1-0368-2d2f1be64415/scratchpad/probe/`,
an instrumented copy of `abi/` + `model/` with work counters plus an `attacks` binary).
The folder `Docs/reviews/` was not read.

Test run: `cd /Users/btw/Documents/repos/dodos-kernel && nix --extra-experimental-features
'nix-command flakes' develop -c cargo test -p dodos-model` → exit 0, 244 unit tests + 8 property
tests pass (about one minute). `git status` in `dodos-kernel` is clean, branch `model`.

Severity scale used below: **wrong behaviour** (model contradicts the contract), **contract
error** (the contract itself violates its own general rules or leaves a cost unbounded),
**accepted limit worth knowing** (allowed by the contract; the humans should know the number),
**undefined** (contract silent, model decided), **untested** (rule not exercised by any test),
**minor**.

---

## Findings, sorted by severity

### F1 — Contract error: no rule bounds the length of an endpoint/notify queue or the work of one wake, so "every call bounded" does not bound the work of a call

- **Severity:** contract error (with a model-cost consequence).
- **Where:** contract `kernel-interface.md:151` ("each waiting thread is linked through its own
  thread object" — implying O(1) unlink in a real kernel) and `:93` (removal wakes at most 32
  threads per step / 64 per call, but says nothing about the cost *per wake*); model
  `model/src/ipc.rs:454-467` (`unlink` uses `VecDeque::retain`, i.e. O(queue length) per woken
  thread).
- **What is wrong:** the queue of callers on an endpoint is bounded only by how many threads the
  attacker can create and park with `call` — no rule (not the step bound of 32, not the slot
  budget of 128, not "no kernel heap") bounds its length. Each of the ≤32 wakes of one removal
  step can therefore cost O(n) in the model, so one `cap_delete` call costs O(32·n) and the whole
  teardown O(n²) — unbounded in the attacker's memory. The contract's own arithmetic bounds only
  the *count* of wakes, never the per-wake work, so rule "every call bounded" is not satisfied by
  the letter of the rules. In a real kernel that links waiters through their own thread objects
  the unlink is O(1) and this disappears; the contract never says so.
- **How I know:** confirmed by run. Sequence: create endpoint `E` (root in boot slot 20); spawn
  n client threads; each does `call(s(20), msg(1, vec![]), Range::NONE)` with no receiver, so it
  joins the queue (each push is O(1) in the model); then `cap_delete(s(root_of_E))` until
  `Done`. Measured: n=2048 → 65 calls (= n/32 + 1), queue-scan counter 2,098,176 ≈ n²/2;
  n=16384 → 513 calls, queue-scan counter 134,225,920 ≈ n²/2. The model's `retain` is a
  model-cost artifact (the model may allocate; the kernel may not), but the *contract* gap — queue
  length and per-wake cost unbounded — stands on its own.
- **Suggest:** add to the contract, next to line 151, that a waiter is unlinked from a queue in
  constant time (it is linked through its own thread object), and/or state an explicit bound on
  queue length. In the model, note in a comment that `retain` is O(n) where the kernel is O(1),
  or keep a `VecDeque` plus per-thread back-pointer if the oracle should mirror the cost.

### F2 — Accepted limit worth knowing: the cost to kill a hostile process, and that it can be made non-terminating unless the supervisor suspends the child's threads first

- **Severity:** accepted limit worth knowing (contract line 94 accepts it explicitly).
- **Where:** contract `kernel-interface.md:92` (step budgets: ≤32 capabilities removed/woken and
  ≤128 slots examined per call) and `:94` ("Each call removes 32 capabilities against at most
  four new capabilities per competing call (a message), and a supervisor that wants a certain
  end suspends those threads first"); model removal in `model/src/caps.rs`.
- **What is wrong (i.e. what the attacker can do):** a process with a full capability space costs
  `ceil(caps/32) + ceil(slots_of_dying_spaces/128)` `cap_delete` calls to destroy. Measured
  (scenario S1): a child whose cspace is grown to the maximum 2^20 slots and filled with
  1,048,573 capability copies needs **40,960 `cap_delete` calls** on its untyped root
  (= 2^20/32 + 2^20/128 = 32768 + 8192); each call stays within budget (≤32 removal steps,
  ≤128 walk iterations, ≤128 slot examinations). Worse (scenario S2): while that removal runs,
  the child can keep deriving into a live space; measured with k derives per supervisor call:
  k=31 → removal **ended** after 1506 calls; **k=33, 40, 64 → did not end within 2600 calls**,
  the child thread still alive and deriving (net +k−32 caps per round). So without suspending
  the child's threads, a hostile process can postpone its own death **without bound** (needs ≥33
  plain `cap_derive` calls, or ≥9 four-capability IPC messages, per removal call; the contract's
  own number is 4 per message). With `thread_suspend` on the child's threads first, the end is
  certain and costs exactly the formula above. The model matches the contract here; the test
  `removal_does_not_end_while_another_thread_keeps_deriving` only exercises 4 rounds.
- **How I know:** confirmed by runs S1 and S2 (scratch `attacks` binary, counters in the
  instrumented copy). Sequence for S2: child pre-fills 512 copies under an untyped-copy in its
  live space; loop { child does k `cap_derive(via(live_root), new_slot)`; supervisor does
  `cap_delete(s(child_untyped_root))` } until `Done` or a call cap.
- **Suggest:** none for the model. For the humans: the number to remember is 40,960 calls for a
  maximal hostile process, and "suspend threads first" is mandatory, not optional, if the
  supervisor wants a bounded kill. Consider a test that suspends first and asserts the exact
  call count formula.

### F3 — Accepted limit worth knowing: a killed server holds its callers until the removal reaches their reply objects; there is no timeout

- **Severity:** accepted limit worth knowing (contract `kernel-interface.md:93` states it:
  "A server whose space is dying can therefore no longer answer: its callers get `gone` when its
  reply objects are destroyed").
- **Where:** contract `:93`; model `model/src/caps.rs` / `model/src/ipc.rs` (reply-object wake on
  the step that marks it dying, not counted in the 32).
- **What the attacker can do:** a malicious server that is killed keeps every armed caller
  waiting until the supervisor's `cap_delete` walk reaches the reply object. Measured (scenario
  S4): small server (untyped 16 MiB, one reply root created first from it, cspace of 128 slots,
  one server thread, endpoint + reply copies in it, one armed caller) → the caller is woken
  with `gone` after **1 `cap_delete` call** (6 removal steps, 13 walk iterations, 127 slot
  examinations — all inside one call's budgets). Large server (cspace grown to 2^20 slots = 516
  segments, 65,536 extra copies under the endpoint copy) → the caller is freed after **2564
  `cap_delete` calls** (= 65536/32 + 516). While the server is *alive*, it can hold callers
  forever: a caller that is armed in a reply object waits with no timeout in the one-core model.
- **How I know:** confirmed by runs S4a/S4b. Sequence: server process U (untyped in boot slot
  50), reply root R retyped from U *first* into boot slot 52, cspace F into slot 51, grown;
  server thread SP in F slot 2; `derive(s(20), via(F,4))` (endpoint copy), `derive(s(52),
  via(F,3))` (reply copy); SP does `recv(s(4), s(3), Range::NONE)`; client CL does
  `call(s(20), msg(1, vec![]), Range::NONE)` → armed in R; then `cap_delete(s(50))` until
  `woken(CL) == Some(Err(Gone))`.
- **Suggest:** none; the behaviour is contractual. Worth stating in the contract's summary that
  "kill a server" costs the removal formula before its clients are released.

### F4 — Undefined: `notify_bind` with a pending word while both a notify waiter and an endpoint receiver wait — the model wakes the notify waiter, the contract does not say

- **Severity:** undefined (model-decided, not marked CONTRACT-GAP).
- **Where:** contract `kernel-interface.md:146` (`recv`: "In order: a pending notification of the
  bound `notify`; the first caller in the queue; otherwise the thread waits") and the `signal`
  rule that fixes priority; the `notify_bind` sentence says only that the word is "delivered at
  once" to a waiting receiver. Model: `model/src/ipc.rs` (bind path) wakes the notify waiter.
  The other model gaps *are* marked (`model/src/ipc.rs:43,55`, `model/src/lib.rs:398,692`).
- **What is wrong:** when a `notify_bind` stores a word while a thread already waits on that
  notify *and* a receiver waits on the bound endpoint, the model delivers to the notify waiter
  and leaves the receiver queued. The contract's "in order" list is written for `recv`, not for
  the bind-time race, so both readings are defensible.
- **How I know:** confirmed by run P2: thread W does `wait` on notify N; thread R does `recv` on
  endpoint E bound to N; then `notify_bind(N, word)` → W is woken with the word, R stays
  `Waits`. No test covers this interleaving (untested as well).
- **Suggest:** either fix a priority in the contract for the bind-time delivery, or mark the
  model's choice CONTRACT-GAP like the others.

### F5 — Minor: the walk-bound numbers in the model (192, and 384 per call) do not match the contract sentence (longest buildable walk 191)

- **Severity:** minor (harmless in practice; numbers disagree).
- **Where:** contract `kernel-interface.md:87`: "the walk is shorter than 192 capabilities (the
  longest one that can be built has 191)". Model: `model/src/lib.rs:356`
  `LONGEST_WALK = 3 * TREE_DEPTH` = 192; invariant `model/src/check.rs:236` allows
  `longest_walk <= 192`; the per-call assert in `model/src/caps.rs:464` allows
  `walk <= 2 * LONGEST_WALK` = 384; the test
  `longest_walk_that_the_depth_rule_allows_is_within_the_bound` builds 191.
- **What is wrong:** nothing behavioural — D-103 plus the 64-level limit make a walk longer
  than 191 unbuildable, so the looser internal invariant can never fire. But a reader comparing
  code to contract will see 192/384 where the contract says 191.
- **How I know:** read in code; the 191-long walk is exercised by the named test (passes).
- **Suggest:** define `LONGEST_WALK = 191` (or comment that 3·64 is a safe over-approximation of
  the contract's 191).

### F6 — Minor: the contract is ambiguous about the size of a one-core thread (1 KB vs 2 KB); the model chose 1 KB, unmarked

- **Severity:** minor / undefined.
- **Where:** contract `kernel-interface.md:121` ("Object sizes are rounded up to a power of two
  (a thread in the one-core reference: 1 KB)") vs `:283` (object table: "`thread` | 1 KB, plus
  the vector state area (1 KB in the one-core reference, which has no vector state)") — the
  table reads as 2 KB for the one-core reference. Model: `model/src/caps.rs:60`
  `ObjectKind::Thread => (1024, size == 0)`, test `model/tests/calls.rs:3152 thread_takes_1_kb`.
- **What is wrong:** the two contract sentences disagree; the model follows line 121 and takes
  1 KB total, without a CONTRACT-GAP mark.
- **How I know:** read in code and contract; run S8 confirmed the watermark arithmetic follows
  the 1 KB choice (4 threads fit where the 2 KB reading would fit 2).
- **Suggest:** fix one of the two contract sentences (say the table is authoritative, or say the
  watermark rounding ignores the vector area on a core without vector state).

### F7 — Untested: rules no test exercises

- **Severity:** untested.
- **(a)** The bind-time notification priority of F4 — no test interleaves `notify_bind` with a
  waiting notify waiter and a waiting endpoint receiver.
- **(b)** The per-wake unlink cost / queue-length behaviour of F1 — queue *semantics* (FIFO,
  unlink on destroy, wake count ≤32) are tested, but no test or invariant bounds queue length or
  per-wake work (the model cannot express it without counters; my scratch counters measured it).
- **(c)** The exact kill-cost formula of F2 (ceil(caps/32)+ceil(slots/128)) is not asserted by
  any test; `removal_does_not_end_while_another_thread_keeps_deriving` covers only 4 rounds of
  deriving and never measures the ending call count.
- **(d)** The 192-vs-191 walk bound of F5 (the test builds 191 but nothing asserts the invariant
  constant equals the contract's number).
- **How I know:** read of `model/src/check/tests.rs`, `model/tests/calls.rs`,
  `model/tests/property.rs` (all 244+8 tests) plus the runs above.

### F8 — Wrong behaviour

**None found.** After a sentence-by-sentence comparison of the contract (rules, objects, system
calls, rights, errors, call reference) against `model/src/{lib,caps,ipc,check}.rs`, I found no
place where the model's observable behaviour contradicts the contract. See the last section.

---

## Per role: what an attacker can do to others in the worst case

Setup built in scratch: supervisor (boot) creates processes, each with its own cspace + untyped +
thread; a server with an endpoint and reply objects; clients with badged endpoint copies; a
memory service handing child untypeds down; kills while traffic is in flight.

### Malicious client against the server and other clients

- **Queue flooding (F1):** park one thread per `call` on the endpoint with no receiver. Queue
  length is bounded only by attacker memory. Destroying the endpoint then costs n/32+1
  `cap_delete` calls with O(n²) scan work in the model (measured 134M scans at n=16384). Each
  individual `call` push is O(1), so flooding itself is cheap for the attacker and expensive
  only at teardown — and the teardown bill is paid by whoever deletes the endpoint (the
  supervisor or the server's owner).
- **Badges cannot be forged:** a caller is seen with the badge of the endpoint *copy it used*
  (measured: A's badge 0xA, B's 0xB). Sharing a capability is delegation, by design — colluders
  can share one badge, but cannot impersonate a badge they were not given.
- **Capabilities sent in messages** (grant/move) become the receiver's, but remain in the
  sender's derivation tree: when the sender is killed, the moved cap dies in the receiver's
  space too (measured S5: B's slot 10 became a dead `gone` slot after A's `cap_delete`).
  So a malicious client can hand the server caps that will later vanish — the server must not
  rely on received caps outliving the sender (contractual).
- **Receive range:** a delivery into a full/occupied or dying range drops the capabilities with
  the `caps_dropped` flag; the words are still delivered (measured S7). This harms only the
  receiver itself.
- **Dying while armed in a reply object:** the reply goes idle; the server's later `send` gets
  `would_wait` (measured S10) — a client can make one answer vanish, but cannot make the server
  answer the wrong caller (reply is armed with exactly one caller; `send` on an unarmed or
  already-answered reply is `would_wait`).

### Malicious server against its clients

- **Hold callers while alive:** a caller armed in a reply object waits with no timeout
  (one-core model, synchronous call). The server can keep any number of callers parked
  indefinitely by simply never `send`ing.
- **After the server is killed:** callers are freed with `gone` only when the removal reaches
  their reply objects — cost to the killer is the full removal formula (F3: 1 call for a tiny
  server, 2564 calls for a 2^20-slot/65k-cap server, 40,960 calls for a maximal process).
  A dying server cannot answer anymore (every call on a dying object is `gone`), so it cannot
  hold callers past that point.
- **Answer twice / answer the wrong caller:** impossible — second `send` is `would_wait`;
  `send` on a reply armed with another caller is `would_wait` (measured S10).
- **Capabilities in replies:** land only inside the caller's declared receive range; otherwise
  dropped with `caps_dropped` (all-or-nothing transfer) — the server cannot push caps outside
  the caller's range.

### Malicious child against its supervisor

- **Kill cost:** `ceil(caps/32) + ceil(dying slots/128)` `cap_delete` calls; measured **40,960**
  for a maximal child (2^20-slot cspace fully filled, 64 MiB untyped) (S1). Each call is within
  budget, so no single call is unbounded — the *total* is linear in the child's size.
- **Non-termination:** by deriving ≥33 caps per removal call (≥9 four-cap messages) into a live
  space, the child can keep the removal from ever ending (measured S2: k≥33 did not end in 2600
  calls; k=31 ended after 1506). The supervisor must `thread_suspend` the child's threads
  first for a certain, bounded end (contract line 94 says exactly this). The child **cannot**
  make itself unkillable — only arbitrarily slow without suspension.
- **64 depth levels:** consumed by nesting spaces-that-create-spaces (contract line 89); after
  that, derivations fail `invalid`. This limits structure, not the kill.
- **Slots and untyped:** filling them only makes retype fail `NoMemory`; deletion still works.
- **Hiding capabilities:** impossible. Caps moved into another process's space (IPC transfer)
  are still descendants in the derivation tree and die with the owner — measured S5 (B's slot
  became `gone` after A's kill). D-103 (a space holds only what is deeper) blocks cycles, so
  the removal tree is always acyclic (tested; 191-longest walk builds fine).
- **Work per supervisor call while the child acts between steps:** bounded — ≤32 removal
  steps, ≤128 walk iterations, ≤128 slot examinations per call (measured in S1/S2 counters).

### Two colluding processes through a shared space or shared endpoint

- **Shared endpoint:** calls are served FIFO by arrival; each caller is seen with the badge of
  the copy it used (S5: A with 0xA, B with 0xB). Collusion can share one endpoint copy and thus
  one badge — that is delegation, not impersonation.
- **Shared space / moved caps:** A can move its notify root into B's receive range during a
  `call` (S5: landed in B's slot 10, `Inspect Notify ALL`); the cap stays A's descendant and is
  revoked when A is killed (B's slot → dead `gone`), while B's own caps are untouched. So
  collusion cannot launder capabilities past a revocation.

### Reuse of memory after a kill

- The untyped watermark returns to the start exactly when the last object made from it is
  destroyed (measured S6: after the kill, 4 aspaces fit again where none did; deleting the
  child untyped returns the memory to the boot untyped). This matches contract line 121.
- The kernel does not clear frame *contents* on reuse; the contract assigns clearing to the
  memory service. The model has no memory contents, so this is not modelled — by design, not a
  gap (nothing to test).

---

## What I checked and found correct

- **Tests pass:** `cargo test -p dodos-model` → 244 unit + 8 property tests, exit 0 (~1 min);
  working tree clean on branch `model`.
- **No wrong-behaviour divergence** model vs contract, sentence by sentence: order of argument
  checks (including "kind judged before size" for `untyped_retype`, unsupported kinds after the
  device-memory rule), rights checked at call time, depth limit 64, D-103 on every placement
  (cap_move/cap_derive/untyped_retype/IPC delivery), removal step budgets (32/128, `again` until
  the last step, fixed order most-recent-child-first, sweep from slot 1), dying semantics
  (`gone` from the first step; a dying space only shrinks; delivery into a dying range drops
  caps, words delivered), reply wake not counted in the 32 and ≤64 wakes per call, one-shot
  replies, all-or-nothing cap transfer with `caps_dropped`, badges (opaque u64, per-copy),
  suspension independent of waiting, watermark rule, device memory, slot/address limits — all
  match and are covered by the test suite.
- **Limits behave per contract** (run S8): cspace max 2^20 ok, 2^20+128 and 2^32 `invalid`;
  untyped power-of-two ≥ page (4096 ok; 0, 2048, 4095, 4097, 12288 `invalid`); frame
  u64::MAX pages → `invalid` (overflow), 1<<40 pages → `no_memory`; message 64 words ok / 65
  `invalid`; 4 caps ok / 5 `invalid`; receive-range count 5 `invalid`;
  `SlotAddr::from_raw(u64::MAX)` → `invalid`; badge u64::MAX accepted; `signal` without badge
  delivers word 1.
- **Kill/reuse behaviour** (S6): watermark returns to 0 exactly when the last object from an
  untyped dies; memory returns to the parent untyped when a child untyped is deleted.
- **IPC edge behaviour** (S7, S10): shared-space slot filling a receive range →
  `Sent { flags: CAPS_DROPPED }`, caller woken with caps=0, words delivered; reply is one-shot;
  `send` on idle/wrong reply → `would_wait` with the other caller undisturbed; caller killed
  while armed → reply idle → server's send `would_wait`.
- **CONTRACT-GAP marks** are present where the contract is silent: notification header/flag
  (`model/src/ipc.rs:43`), message marks (`ipc.rs:55`), start-up information (`lib.rs:398`),
  thread exit (`lib.rs:692`) — verified in code; no other unmarked model-only decisions found
  except F4 and F6 above.
- **The model allocates** (Vec/VecDeque for queues and trees). That is fine for an oracle; the
  contract's "no kernel heap" constrains the real kernel, whose queues are linked through the
  waiting threads' own objects (contract line 151) — see F1 for the cost consequence in the
  model.
