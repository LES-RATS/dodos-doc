"""Exhaustive state explorer for four protocols between nodes, as the
contract states them after the eighth review (D-131, pass 14C).

Each scenario is a finite model explored breadth first over every
interleaving of its steps. Every scenario has the contract's rules
("correct") and variants with one rule broken on purpose; each property is
shown to fail on at least one variant, so that none holds by construction.

  crossing  A grant revoked by its owner X while its holder Y deletes it:
            the `Release` crossing the `Revoke`, a `Revoke` that finds the
            root already gone, a record left *unmapping* by Y's other cores,
            the release pending while the ring has no room.
  unit      A unit request of node R across a planned hand-over of the unit
            role from X to Y, with the death of Y, and of X, at each step;
            take-over judged on the target of a handing word; requests
            answered *elsewhere* and kept by the requester.
  rings     A `node_send` of X to Y and a `Signal` back, while X seals and
            resumes and Y dies and starts fresh, with messages in flight on
            the rings in both directions.
  waiter    A thread of X that waits for a `SendAnswer` and is destroyed,
            and Y that dies: the answer applied without its thread, credits
            and the reserve of answers.

Properties (each checked in every reachable state, and liveness: from every
reachable state a quiet state is reachable):
  crossing  ISOLATION  X never frees the grant while Y has a leaf or an
                       invalidation in flight under it;
            CREDIT     a credit in use always has its request or its answer
                       in flight;
            DONE       a finished revocation has freed the entry;
            liveness   every revocation ends.
  unit      ONE-HOLDER at most one node maps the unit's registers, counting
                       a stopped node until its posted writes have settled;
            SERVED     a request is served only by the node the role word
                       reads held by, with the request's epoch;
            liveness   every request ends done.
  rings     RECEIVER   no message acts on a later generation of its receiver;
            SENDER     no signal of an ended generation is delivered;
            liveness   every wait ends, by the answer or by `gone`.
  waiter    CREDIT     as above; LEAK  no grant entry stays unanswered with
                       nothing in flight; RESERVE  the answers owed never
                       exceed the reserve; liveness.

Run (Python 3, no dependency):

    python3 -I node-protocol-explorer.py                 # every scenario and variant
    python3 -I node-protocol-explorer.py crossing        # one scenario, all variants
    python3 -I node-protocol-explorer.py rings:correct

A variant that holds prints OK with its numbers of states and transitions; a
variant that fails prints the shortest trace (breadth first) to the first
violation. The exit status is 0 when the correct models hold and every
broken variant fails.
"""

import sys
import time
from collections import deque


def explore(sc):
    """Breadth-first exploration; returns a dict with ok, why, trace, states."""
    t0 = time.time()
    s0 = sc.initial()
    ids = {s0: 0}
    states = [s0]
    parent = [-1]
    plabel = [None]
    succ = []

    def trace(j):
        out = []
        while parent[j] != -1:
            out.append(plabel[j])
            j = parent[j]
        return out[::-1]

    i = 0
    while i < len(states):
        s = states[i]
        err = sc.check(s)
        if err:
            return dict(ok=False, why=err, trace=trace(i), states=len(states),
                        transitions=sum(len(x) for x in succ), secs=time.time() - t0)
        out = []
        for lab, n in sc.successors(s):
            j = ids.get(n)
            if j is None:
                j = len(states)
                ids[n] = j
                states.append(n)
                parent.append(i)
                plabel.append(lab)
            out.append(j)
        succ.append(out)
        i += 1
    n = len(states)
    pred = [[] for _ in range(n)]
    for a, outs in enumerate(succ):
        for b in outs:
            pred[b].append(a)
    good = [sc.quiet(s) for s in states]
    q = deque(j for j in range(n) if good[j])
    while q:
        b = q.popleft()
        for a in pred[b]:
            if not good[a]:
                good[a] = True
                q.append(a)
    bad = next((j for j in range(n) if not good[j]), None)
    ntrans = sum(len(x) for x in succ)
    if bad is not None:
        return dict(ok=False, why="LIVENESS: no quiet state is reachable from here",
                    trace=trace(bad), states=n, transitions=ntrans, secs=time.time() - t0)
    return dict(ok=True, states=n, transitions=ntrans, secs=time.time() - t0)


def put(s, **kw):
    """A copy of the state (a dict frozen as a sorted tuple) with fields changed."""
    d = dict(s)
    d.update(kw)
    return tuple(sorted(d.items()))


# ---------------------------------------------------------------------------
# Scenario 1: a Release crossing a Revoke
# ---------------------------------------------------------------------------


class Crossing:
    """X granted a frame to Y, which maps it once. A removal on X reaches the
    anchor (thread T); Y may delete its root remote capability at any time.
    Y's record goes *unmapping* when its leaf is cleared and empty when its
    other cores have acknowledged; the use entry's count covers the leaf
    until then (Grants, TLB). The kernel ring Y -> X keeps one entry for the
    answer to X's one credit; a Release needs room beyond it."""

    VARIANTS = {
        "correct": "the contract's rules (Grants: revocation, release, a Release crossing a Revoke)",
        "release_keeps_wait": "a Release on a revoking entry frees it but does not end the revocation (the text before D-131)",
        "release_no_credit": "a Release ends the revocation but the Revoke in flight keeps its credit",
        "count_at_clear": "the holder lowers its use count when it clears the leaf, before its cores acknowledge",
        "release_beside_step": "a removal done for a Revoke also sends a Release, before its last RevokeStep (expected to hold: the crossing rule covers it)",
        "done_on_any_answer": "the removal ends at any RevokeStep, also one that reports the root not removed",
        "wait_after_not_yet": "after a RevokeStep that reports the root not removed, the removal keeps waiting instead of sending again",
    }
    EXPECT_OK = {"correct", "release_beside_step"}

    def __init__(self, v):
        self.v = v

    def initial(self):
        # mode "?" chooses first whether Y's thread will ever delete its root ("d") or never ("n"),
        # so that a run with nobody to rescue a waiting revocation exists
        return put((), mode="?", xe="L", tc="I", cr=0, cs=0, kxy=(), kyx=(),
                   yr="P", yrec="M", yu="U", yt="I")

    def count_seen(self, d):
        if self.v == "count_at_clear":
            return 1 if d["yrec"] == "M" else 0
        return 1 if d["yrec"] in ("M", "U") else 0

    def successors(self, s):
        d = dict(s)
        v = self.v
        if d["mode"] == "?":
            yield "run where Y will delete its root", put(s, mode="d")
            yield "run where Y never deletes its root", put(s, mode="n")
            return
        # X: the removal reaches the anchor
        if d["tc"] == "I":
            yield "X: a removal reaches the anchor", put(s, tc="S")
        if d["tc"] == "S":
            if d["xe"] == "F":
                yield "X: the removal finds the entry freed and removes the anchor", put(s, tc="D")
            elif d["xe"] == "L" and self.count_seen(d) == 0:
                yield "X: writes revoking, reads Y's count 0, frees the entry at once", put(s, xe="F", tc="D")
            elif d["cr"] == 0:
                cs = 1 - d["cs"]  # the credit's serial: one more at each use (two values suffice: one credit)
                yield (f"X: writes revoking, sends Revoke (serial {cs}), waits",
                       put(s, xe="V", cr=1, cs=cs, kxy=d["kxy"] + (("Rv", cs),), tc="W"))
        # X consumes the kernel ring from Y
        if d["kyx"]:
            m, rest = d["kyx"][0], d["kyx"][1:]
            if m[0] == "St":
                _, sn, removed = m
                if d["cr"] == 1 and d["cs"] == sn:
                    xe = "F" if (removed and d["xe"] == "V") else d["xe"]
                    tc = "S" if d["tc"] == "W" else d["tc"]
                    if v == "done_on_any_answer" and d["tc"] == "W":
                        tc = "D"
                    if v == "wait_after_not_yet" and not removed:
                        tc = d["tc"]
                    yield (f"X: consumes RevokeStep #{sn} ({'root removed' if removed else 'not yet'})",
                           put(s, kyx=rest, cr=0, xe=xe, tc=tc))
                else:
                    yield f"X: refuses RevokeStep #{sn} (its credit is not in use)", put(s, kyx=rest)
            else:  # Release
                if d["xe"] != "F":
                    cr, tc = d["cr"], d["tc"]
                    if d["xe"] == "V" and v != "release_keeps_wait":
                        if v != "release_no_credit":
                            cr = 0
                        tc = "S" if tc == "W" else tc
                    yield "X: consumes Release, frees the entry", put(s, kyx=rest, xe="F", cr=cr, tc=tc)
                else:
                    yield "X: refuses Release (entry already free)", put(s, kyx=rest)
        # Y deletes its root remote capability, in removal steps
        if d["yt"] == "I" and d["mode"] == "d":
            yield "Y: a thread deletes the root remote capability", put(s, yt="A")
        if d["yt"] == "A":
            if d["yr"] == "R":
                yield "Y: the deletion finds the root removed", put(s, yt="D")
            elif d["yrec"] == "M":
                yield "Y: removal step clears the leaf (record unmapping), returns again", put(s, yrec="U")
            elif d["yrec"] == "E":
                if not d["kyx"]:
                    yield "Y: removes the root, sends Release, frees its use entry", put(s, yr="R", yu="F", yt="D", kyx=d["kyx"] + (("Rl",),))
                else:
                    yield "Y: removes the root, Release pending (no room)", put(s, yr="R", yu="P", yt="D")
        if d["yrec"] == "U":
            yield "Y: its other cores acknowledge: record empty, count lowered", put(s, yrec="E")
        if d["yu"] == "P" and not d["kyx"]:
            yield "Y: sends the pending Release, frees its use entry", put(s, yu="F", kyx=d["kyx"] + (("Rl",),))
        # Y consumes the kernel ring from X
        if d["kxy"]:
            (_, sn), rest = d["kxy"][0], d["kxy"][1:]
            if d["yu"] == "F":
                yield f"Y: refuses Revoke #{sn} (no use entry: no answer)", put(s, kxy=rest)
            elif d["yu"] == "P":
                yield (f"Y: Revoke #{sn} finds the release pending: answers removed, drops it",
                       put(s, kxy=rest, yu="F", kyx=d["kyx"] + (("St", sn, True),)))
            elif d["yrec"] == "M":
                yield (f"Y: Revoke #{sn}: clears the leaf (unmapping), answers not yet",
                       put(s, kxy=rest, yrec="U", kyx=d["kyx"] + (("St", sn, False),)))
            elif d["yrec"] == "U":
                yield (f"Y: Revoke #{sn}: record still unmapping, answers not yet",
                       put(s, kxy=rest, kyx=d["kyx"] + (("St", sn, False),)))
            else:
                msgs = (("Rl",), ("St", sn, True)) if v == "release_beside_step" else (("St", sn, True),)
                yield (f"Y: Revoke #{sn}: removes the root, frees its use entry, answers removed",
                       put(s, kxy=rest, yr="R", yu="F", kyx=d["kyx"] + msgs))

    def check(self, s):
        d = dict(s)
        if d["xe"] == "F" and d["yrec"] in ("M", "U"):
            return "ISOLATION: X freed the grant while Y still has a leaf or an invalidation in flight under it"
        if d["cr"] == 1:
            inflight = (any(m == ("Rv", d["cs"]) for m in d["kxy"]) or any(m[0] == "St" and m[1] == d["cs"] for m in d["kyx"])
                        or ("Rl",) in d["kyx"] or d["yu"] == "P")  # a Release in flight or pending ends it too
            if not inflight:
                return "CREDIT: a request credit stays in use with neither its Revoke, its answer nor a Release in flight"
        if d["tc"] == "D" and d["xe"] != "F":
            return "DONE: the revocation ended with the grant entry not freed"
        return None

    def quiet(self, s):
        d = dict(s)
        return (d["tc"] in ("I", "D") and d["yt"] in ("I", "D") and not d["kxy"] and not d["kyx"]
                and d["yu"] != "P" and d["yrec"] != "U")


# ---------------------------------------------------------------------------
# Scenario 2: a unit request across a hand-over and the deaths of its parties
# ---------------------------------------------------------------------------


class Unit:
    """Nodes 0 (X, the holder), 1 (R, the requester, which is also the
    successor of X when X dies, being next in index order) and 2 (Y, the
    target of a planned hand-over of the unit role; X is its successor). R's request stays
    in its unit request table until a holder answers done; a holder serves
    only with the epoch the word holds and not after step 1 of its
    hand-over; a request it serves waits for the unit's confirmation. A node
    dies at most once (X or Y): it stops at once and its posted writes settle
    later; the take-over of a word waits for that settling of the node the
    word is judged on."""

    VARIANTS = {
        "correct": "the contract's rules (Roles, Devices and shared hardware, What crosses between nodes)",
        "check_drops_epoch": "the receive check drops a request whose epoch is not the role's (the text before D-131)",
        "handing_judged_on_holder": "the take-over of a handing word is judged on the node that hands (the text before D-131)",
        "takeover_either": "a handing word may be taken over when either the node that hands or the target is no longer live (the review's correction, which Opus's verification broke)",
    }
    EXPECT_OK = {"correct"}
    X, R, Y = 0, 1, 2

    def __init__(self, v):
        self.v = v

    def initial(self):
        # word: (state, holder, target, epoch); alive: per node; settled: per node
        return put((), word=("H", 0, -1, 0), alive=(1, 1, 1), settled=(0, 0, 0), maps=(1, 0, 0),
                   hstep=0, deaths=0, entry=("Q",), ring=(), ans=(), served=(), unit=(), r0=(1, 1, 1),
                   bad="")

    def successor_of(self, d, dead):
        alive = d["alive"]
        for k in (1, 2, 3):
            n = (dead + k) % 3
            if alive[n]:
                return n
        return None

    def successors(self, s):
        d = dict(s)
        v = self.v
        st, holder, target, ep = d["word"]
        alive, settled, maps = list(d["alive"]), list(d["settled"]), list(d["maps"])
        # ---- the requester R
        if alive[self.R] and d["entry"][0] == "Q" and st == "H" and alive[holder]:
            if holder == self.R:
                # its own node holds the role: served without a message
                if maps[self.R]:
                    yield "R: holds the role itself, submits its own request", put(s, entry=("S", self.R, ep), unit=d["unit"] + ((self.R, self.R, ep),), served=d["served"] + ((self.R, ep),))
            else:
                yield f"R: sends its request to node {holder} with epoch {ep}", put(s, entry=("S", holder, ep), ring=d["ring"] + ((holder, ep),))
        # R0 at R for a dead holder: a request sent to it is queued again
        for n in (self.X, self.Y):
            if not alive[n] and not d["r0"][n] and alive[self.R]:
                e = d["entry"]
                ne = ("Q",) if (e[0] == "S" and e[1] == n) else e
                r0 = list(d["r0"]); r0[n] = 1
                ring = tuple(m for m in d["ring"] if m[0] != n)
                ans = tuple(a for a in d["ans"] if a[0] != n)
                yield f"R: R0 for node {n}: its request to it is queued again", put(s, entry=ne, r0=tuple(r0), ring=ring, ans=ans)
        # ---- a holder consumes a request
        if d["ring"]:
            (to, rep), rest = d["ring"][0], d["ring"][1:]
            if not alive[to]:
                pass  # a dead node consumes nothing; R0 at R drops these
            elif v == "check_drops_epoch" and rep != ep:
                yield f"node {to}: the receive check drops the request of epoch {rep} (no answer)", put(s, ring=rest)
            else:
                begun = (to == self.X and d["hstep"] >= 1)
                ok = st == "H" and holder == to and (rep == ep or v == "serve_any_epoch") and not begun and maps[to]
                if ok:
                    yield f"node {to}: serves the request (epoch {rep}), submits it to the unit", put(s, ring=rest, unit=d["unit"] + ((to, self.R, rep),), served=d["served"] + ((to, rep),))
                else:
                    yield f"node {to}: answers elsewhere (epoch {rep})", put(s, ring=rest, ans=d["ans"] + ((to, "E"),))
        # ---- the unit confirms a submitted operation
        if d["unit"]:
            (h, req, rep), rest = d["unit"][0], d["unit"][1:]
            if alive[h]:
                if h == self.R:
                    yield "the unit confirms R's own request: done", put(s, unit=rest, entry=("D",))
                else:
                    yield f"the unit confirms: node {h} answers done", put(s, unit=rest, ans=d["ans"] + ((h, "D"),))
            else:
                yield f"node {h} died: its submitted operation is dropped", put(s, unit=rest)
        # ---- R consumes an answer
        if d["ans"] and alive[self.R]:
            (frm, kind), rest = d["ans"][0], d["ans"][1:]
            e = d["entry"]
            if e[0] == "S" and e[1] == frm:
                ne = ("D",) if kind == "D" else ("Q",)
                yield f"R: consumes {'done' if kind == 'D' else 'elsewhere'} from node {frm}", put(s, ans=rest, entry=ne)
            else:
                yield f"R: refuses an answer from node {frm}", put(s, ans=rest)
        # ---- the planned hand-over X -> Y
        h = d["hstep"]
        if alive[self.X] and st == "H" and holder == self.X:
            if h == 0 and alive[self.Y]:
                yield "X: step 1, stops serving (elsewhere to new requests)", put(s, hstep=1)
            if h == 1 and not any(u[0] == self.X for u in d["unit"]):
                yield "X: steps 2 and 3, queue drained, unmaps the unit", put(s, hstep=3, maps=tuple(0 if k == self.X else maps[k] for k in range(3)))
            if h == 3:
                if alive[self.Y]:
                    yield "X: step 4, writes handing (X -> Y)", put(s, hstep=4, word=("D", self.X, self.Y, ep + 1))
                else:
                    yield "X: step 4 refused (Y not live): maps again, stays the holder", put(s, hstep=0, maps=tuple(1 if k == self.X else maps[k] for k in range(3)))
        if st == "D" and alive[self.Y] and target == self.Y:
            if not maps[self.Y]:
                yield "Y: step 5, maps the unit (the word names it as target)", put(s, maps=tuple(1 if k == self.Y else maps[k] for k in range(3)))
            else:
                yield "Y: step 5, writes held (Y)", put(s, word=("H", self.Y, -1, ep + 1))
        # ---- deaths and settling
        if d["deaths"] < 1:
            for n in (self.X, self.Y):
                if alive[n]:
                    a = list(alive); a[n] = 0
                    r0 = list(d["r0"]); r0[n] = 0
                    yield f"node {n} dies (stopped)", put(s, alive=tuple(a), deaths=1, r0=tuple(r0))
        for n in range(3):
            if not alive[n] and not settled[n]:
                se = list(settled); se[n] = 1
                yield f"node {n}: its posted writes have settled", put(s, settled=tuple(se), maps=tuple(0 if k == n else maps[k] for k in range(3)))
        # ---- take-over by the successor
        judged = None
        if st == "H":
            judged = holder
        elif st == "D":
            if v == "handing_judged_on_holder":
                judged = holder
            elif v == "takeover_either":
                judged = holder if not alive[holder] else (target if not alive[target] else None)
                if judged is not None and alive[judged]:
                    judged = None
            else:
                judged = target
        if judged is not None and not alive[judged]:
            ready = settled[judged]
            succ = self.successor_of(d, judged)
            if ready and succ is not None:
                yield (f"node {succ}: takes over (judged on node {judged}), maps the unit, rebuilds",
                       put(s, word=("H", succ, -1, ep + 1), maps=tuple(1 if k == succ else maps[k] for k in range(3)), hstep=0))

    def check(self, s):
        d = dict(s)
        alive, settled, maps = d["alive"], d["settled"], d["maps"]
        live_mappers = [n for n in range(3) if maps[n] and (alive[n] or not settled[n])]
        if len(live_mappers) > 1:
            return f"ONE-HOLDER: nodes {live_mappers} map the unit's registers at once"
        return None

    def quiet(self, s):
        d = dict(s)
        return d["entry"] == ("D",) and not d["ring"] and not d["ans"]


class UnitServed(Unit):
    """The same model, with the property SERVED checked at each submission:
    the node that serves is the one the word reads held by, with that epoch."""

    VARIANTS = {
        "correct": Unit.VARIANTS["correct"],
        "serve_any_epoch": "a holder serves a request of any epoch",
    }

    def successors(self, s):
        d = dict(s)
        st, holder, target, ep = d["word"]
        for lab, n in super().successors(s):
            nd = dict(n)
            if len(nd["served"]) > len(d["served"]):
                h, rep = nd["served"][-1]
                if not (st == "H" and holder == h and rep == ep):
                    n = put(n, bad=f"SERVED: node {h} served a request of epoch {rep} while the word reads {d['word']}")
            yield lab, n

    def check(self, s):
        d = dict(s)
        if d["bad"]:
            return d["bad"]
        return super().check(s)


# ---------------------------------------------------------------------------
# Scenario 3: a resume and a fresh start with messages in flight
# ---------------------------------------------------------------------------


class Rings:
    """X sends Y one stamped send carrying one grant (thread T waits for the
    SendAnswer); Y may signal X through the grant's doorbell. X may seal and
    resume (same generation); Y may die and start fresh once (its generation
    grows). Every message carries its sender's and its receiver's
    generation. A sealed node sends and consumes nothing."""

    VARIANTS = {
        "correct": "the contract's rules (What crosses between nodes: the check, What ends with a generation)",
        "resume_resets_consumer": "a resume sets the consumer indices to the producers, as a fresh start does (the text before D-131)",
        "check_refuses_sealed_sender": "the check refuses a message whose sender is sealed (the text before D-131, found by this explorer)",
        "fresh_keeps_consumer": "a fresh start keeps its consumer indices (expected to hold: the check of the receiver generation refuses what was sent before)",
        "no_receiver_check": "the receiver does not check the receiver generation (expected to hold: the fresh start's reset drops what was sent before)",
        "neither": "a fresh start keeps its consumer indices and the receiver does not check the receiver generation",
        "no_sender_check": "the receiver does not check the sender's generation",
    }
    EXPECT_OK = {"correct", "fresh_keeps_consumer", "no_receiver_check"}

    def __init__(self, v):
        self.v = v

    def initial(self):
        return put((), xs="L", t="I", cr=0, grant="N", gy=0, ys="L", yrestarts=0, xr0=1,
                   uxy=(), kyx=(), uyx=(), yuse=0, sig=0, bad="")

    def sender_ok(self, sender_state, sender_gen, cur_gen):
        if self.v == "no_sender_check":
            return True
        states = ("L", "S") if self.v != "check_refuses_sealed_sender" else ("L",)
        return sender_state in states and sender_gen == cur_gen

    def successors(self, s):
        d = dict(s)
        v = self.v
        xlive, ylive = d["xs"] == "L", d["ys"] == "L"
        # X sends
        if xlive and d["t"] == "I" and d["cr"] == 0 and ylive:
            yield "X: node_send to Y with one grant; T waits", put(s, t="W", cr=1, grant="L", uxy=d["uxy"] + (("Send", d["gy"]),))
        # Y consumes the user ring from X
        if ylive and d["uxy"]:
            (_, rgen), rest = d["uxy"][0], d["uxy"][1:]
            if not self.sender_ok(d["xs"], 0, 0):
                yield "Y: refuses the Send (sender not starting, live or sealing)", put(s, uxy=rest)
            elif rgen != d["gy"] and v not in ("no_receiver_check", "neither"):
                yield "Y: refuses the Send (an earlier generation of Y)", put(s, uxy=rest)
            else:
                bad = d["bad"] or ("RECEIVER: a Send acted on a later generation of its receiver" if rgen != d["gy"] else "")
                for dl in (True, False):
                    yield (f"Y: consumes the Send, {'delivers' if dl else 'would_wait'}; answers",
                           put(s, uxy=rest, yuse=1 if dl else d["yuse"], kyx=d["kyx"] + (("Ans", d["gy"], dl),), bad=bad))
        # Y signals through the grant
        if ylive and d["yuse"] and not d["uyx"]:
            yield "Y: grant_signal (Signal on the user ring)", put(s, uyx=(("Sig", d["gy"]),))
        # X consumes, only while live
        if xlive and d["kyx"]:
            (_, sgen, dl), rest = d["kyx"][0], d["kyx"][1:]
            if self.sender_ok(d["ys"], sgen, d["gy"]) and d["cr"] == 1:
                yield (f"X: consumes the SendAnswer ({'delivered' if dl else 'not delivered'})",
                       put(s, kyx=rest, cr=0, t="D" if d["t"] == "W" else d["t"], grant="A" if dl else "F"))
            else:
                yield "X: refuses an answer", put(s, kyx=rest)
        if xlive and d["uyx"]:
            (_, sgen), rest = d["uyx"][0], d["uyx"][1:]
            if self.sender_ok(d["ys"], sgen, d["gy"]):
                bad = d["bad"] or ("SENDER: a signal of an ended generation of Y is delivered" if sgen != d["gy"] else "")
                yield "X: delivers the signal to the doorbell's notify", put(s, uyx=rest, sig=1, bad=bad)
            else:
                yield "X: refuses a signal of an ended generation", put(s, uyx=rest)
        # X seals and resumes
        if xlive:
            yield "X: seals (keeps its threads, its waits and its rings)", put(s, xs="S")
        if d["xs"] == "S":
            kw = {}
            if v == "resume_resets_consumer":
                kw = dict(kyx=(), uyx=())
            yield "X: resumes (same generation)", put(s, xs="L", **kw)
        # Y dies, X runs R0 (at once if live, at its resume if sealed)
        if ylive and d["yrestarts"] < 1:
            yield "Y: dies (accused)", put(s, ys="D", xr0=0)
        if xlive and not d["xr0"]:
            t = "D" if d["t"] == "W" else d["t"]
            grant = "P" if d["grant"] in ("L", "A") else d["grant"]
            yield "X: R0 and R3 for Y: the wait ends with gone, the credit is freed, the grant pinned", put(s, xr0=1, t=t, cr=0, grant=grant)
        # Y starts fresh: generation grows, consumer indices of the rings into Y set to producers
        if d["ys"] == "D" and (d["xr0"] or d["xs"] == "S"):
            grant = "F" if d["grant"] == "P" else d["grant"]
            keep = v in ("fresh_keeps_consumer", "neither")
            yield "Y: starts fresh (generation + 1), consumes nothing sent before", put(s, ys="L", gy=d["gy"] + 1, yrestarts=1, uxy=d["uxy"] if keep else (), yuse=0, grant=grant)

    def check(self, s):
        return dict(s)["bad"] or None

    def quiet(self, s):
        d = dict(s)
        return d["t"] != "W" and d["xs"] == "L" and not d["kyx"] and not d["uxy"] and not d["uyx"]


# ---------------------------------------------------------------------------
# Scenario 4: a thread that waits for another node and is destroyed
# ---------------------------------------------------------------------------


class Waiter:
    """Threads of X send stamped sends with one grant each to Y (one send
    credit, so one reserved answer); a waiting thread may be destroyed; Y may
    die. The answer acts on the grant and frees the credit in the event that
    consumes it, whether or not a thread still waits."""

    VARIANTS = {
        "correct": "the contract's rules (Calls between nodes, Credits, What a thread's destruction undoes)",
        "answer_dropped_without_thread": "an answer that finds no thread is dropped (the text before D-131)",
        "credit_freed_at_destroy": "destroying the waiting thread frees its credit at once, before the answer",
        "answer_credit_only": "an answer that finds no thread frees the credit but does not act on the grant",
        "r0_keeps_waits": "R0 for a dead peer does not end the waits for its answers",
    }
    EXPECT_OK = {"correct"}
    SENDS = 2
    CREDITS = 1

    def __init__(self, v):
        self.v = v

    def initial(self):
        # grants: per send index, state N none, L live unanswered, A answered, F freed, P pinned
        # mode "?" chooses first whether waiting threads may be destroyed ("d") or not ("n")
        return put((), mode="?", sent=0, credits=(), waiting=(), grants=("N",) * self.SENDS, uxy=(), kyx=(), ys="L", r0=1)

    def successors(self, s):
        d = dict(s)
        v = self.v
        if d["mode"] == "?":
            yield "run where waiting threads may be destroyed", put(s, mode="d")
            yield "run where no thread is destroyed", put(s, mode="n")
            return
        ylive = d["ys"] == "L"
        g = list(d["grants"])
        if ylive and d["sent"] < self.SENDS and len(d["credits"]) < self.CREDITS:
            k = d["sent"]
            g2 = list(g); g2[k] = "L"
            yield (f"X: thread {k} sends with grant {k}, waits",
                   put(s, sent=k + 1, credits=d["credits"] + (k,), waiting=d["waiting"] + (k,), grants=tuple(g2), uxy=d["uxy"] + (k,)))
        for k in (d["waiting"] if d["mode"] == "d" else ()):
            cr = d["credits"]
            if v == "credit_freed_at_destroy":
                cr = tuple(c for c in cr if c != k)
            yield f"X: thread {k} is destroyed while it waits", put(s, waiting=tuple(w for w in d["waiting"] if w != k), credits=cr)
        if ylive and d["uxy"]:
            k, rest = d["uxy"][0], d["uxy"][1:]
            for dl in (True, False):
                yield f"Y: consumes send {k}, {'delivers' if dl else 'would_wait'}", put(s, uxy=rest, kyx=d["kyx"] + ((k, dl),))
        if d["kyx"]:
            (k, dl), rest = d["kyx"][0], d["kyx"][1:]
            if v == "answer_dropped_without_thread" and k not in d["waiting"]:
                yield f"X: answer {k} finds no thread and is dropped", put(s, kyx=rest)
            elif v == "answer_credit_only" and k not in d["waiting"]:
                yield f"X: answer {k} finds no thread: frees the credit only", put(s, kyx=rest, credits=tuple(c for c in d["credits"] if c != k))
            else:
                g2 = list(g)
                if g2[k] == "L":
                    g2[k] = "A" if dl else "F"
                yield (f"X: consumes answer {k}, applies it to grant {k}, frees the credit",
                       put(s, kyx=rest, grants=tuple(g2), credits=tuple(c for c in d["credits"] if c != k),
                           waiting=tuple(w for w in d["waiting"] if w != k)))
        if ylive:
            yield "Y: dies (accused)", put(s, ys="D", r0=0, uxy=(), kyx=())
        if not ylive and not d["r0"]:
            g2 = ["P" if x in ("L", "A") else x for x in g]
            waiting = d["waiting"] if v == "r0_keeps_waits" else ()
            yield "X: R0 and R3 for Y: waits end with gone, credits freed, grants pinned", put(s, r0=1, waiting=waiting, credits=(), grants=tuple(g2))
        if not ylive and d["r0"] and "P" in g:
            yield "X: Y's generation is over: pinned grants freed", put(s, grants=tuple("F" if x == "P" else x for x in g))

    def check(self, s):
        d = dict(s)
        for c in d["credits"]:
            if c not in d["uxy"] and not any(a[0] == c for a in d["kyx"]) and d["ys"] == "L":
                return f"CREDIT: the credit of send {c} stays in use with nothing in flight"
        for k, x in enumerate(d["grants"]):
            if x == "L" and d["ys"] == "L" and k not in d["uxy"] and not any(a[0] == k for a in d["kyx"]):
                return f"LEAK: grant {k} stays live and unanswered with nothing in flight"
        if len(d["uxy"]) + len(d["kyx"]) > self.CREDITS:
            return "RESERVE: Y owes X more answers than the reserve of the kernel ring holds"
        return None

    def quiet(self, s):
        d = dict(s)
        return not d["waiting"] and not d["uxy"] and not d["kyx"] and (d["ys"] == "L" or d["r0"])


# ---------------------------------------------------------------------------

SCENARIOS = {"crossing": Crossing, "unit": Unit, "unit-served": UnitServed, "rings": Rings, "waiter": Waiter}
DEFAULT = ["crossing", "unit", "unit-served", "rings", "waiter"]


def run(names):
    failures = 0
    for name in names:
        scen, _, var = name.partition(":")
        cls = SCENARIOS[scen]
        variants = [var] if var else list(cls.VARIANTS)
        for v in variants:
            r = explore(cls(v))
            tag = f"{scen}:{v}"
            if r["ok"]:
                print(f"{tag}: OK, {r['states']} states, {r['transitions']} transitions, "
                      f"every state can reach a quiet state ({r['secs']:.1f} s)", flush=True)
            else:
                print(f"{tag}: VIOLATION after {len(r['trace'])} steps: {r['why']} "
                      f"({r['states']} states seen, {r['secs']:.1f} s)", flush=True)
                for i, step in enumerate(r["trace"], 1):
                    print(f"  {i}. {step}")
            if r["ok"] != (v in cls.EXPECT_OK):
                failures += 1
                print(f"  UNEXPECTED: {tag} was expected to {'hold' if v in cls.EXPECT_OK else 'fail'}", flush=True)
    return failures


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(1 if run(args or DEFAULT) else 0)
