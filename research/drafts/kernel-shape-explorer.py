"""Exhaustive state explorer for the protocols of elastic kernels (C*),
second round (research draft kernel-shape-opus.md, part 9).

Three scenarios, each a separate finite model explored breadth first over
every interleaving; each has a corrected protocol ("correct") and versions
with one rule removed, which must fail.

  moves    cores that leave one kernel and join another; the fence of a
           kernel of several cores; park confirmation per fence class
           (forced: the stop lands whatever the core does; signalled: lost
           while the joining core has not unmasked yet, so the driver
           retries); a fence signal in flight across a move; the bootstrap
           core; a unit-role holder that takes cores; a TLB shootdown of a
           frame racing a move, and the reuse of that frame.
  seal     kernels with zero cores (sealed for a replacement), their wake
           and resume, the reclaim barrier, a revocation and an IOMMU entry
           of a sealed kernel, admission at resume, retirement, fresh starts,
           a supervisor that may disappear. Core moves are atomic here; the
           moves scenario checks them.
  credits  the ring from one kernel X to a kernel Y: user and kernel
           message classes, user receivers that never read, Y's death and
           fresh start, the table of pending signals.

Run (Python 3, no dependency):

    python3 -I kernel-shape-explorer.py              # every scenario and variant
    python3 -I kernel-shape-explorer.py moves        # one scenario, all variants
    python3 -I kernel-shape-explorer.py moves:correct seal:no_seal_timeout
    python3 -I kernel-shape-explorer.py full             # moves and shootdown together (about 6 min)
    python3 -I kernel-shape-explorer.py --witness "lost on core" moves:correct

The default run (moves, shootdown, seal, credits, every variant) takes about
a minute and a half on the machine it was written on; "full" is run only
when named. --witness prints the shortest trace to a transition whose label
contains the text, to show that a case is reachable in a protocol that holds.

Each result line gives states, transitions and seconds. A variant that
holds prints OK; a variant that fails prints the shortest trace (breadth
first) to the first violation.
"""

import sys
import time
from array import array
from collections import deque

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Violation(Exception):
    pass


def explore(sc):
    """Breadth-first exploration of scenario `sc`; returns a result dict."""
    t0 = time.time()
    radix = sc.radix

    def enc(s):
        n = 0
        for v, r in zip(s, radix):
            n = n * r + v
        return n

    def dec(n):
        out = [0] * len(radix)
        for i in range(len(radix) - 1, -1, -1):
            n, out[i] = divmod(n, radix[i])
        return tuple(out)

    s0 = sc.initial()
    assert len(s0) == len(radix) and all(0 <= v < r for v, r in zip(s0, radix)), "bad initial state"
    assert dec(enc(s0)) == s0
    e0 = enc(s0)
    ids = {e0: 0}
    codes = [e0]
    parent = array("i", [-1])
    labels = {}
    label_list = []
    plabel = array("I", [0])
    offsets = array("Q", [0])
    flat = array("I")
    quiet = bytearray()

    def label_id(lab):
        j = labels.get(lab)
        if j is None:
            j = len(label_list)
            labels[lab] = j
            label_list.append(lab)
        return j

    def trace(j):
        out = []
        while parent[j] != -1:
            out.append(label_list[plabel[j]])
            j = parent[j]
        out.reverse()
        return out

    i = 0
    while i < len(codes):
        s = dec(codes[i])
        err = sc.check(s)
        if err:
            return dict(ok=False, why=err, trace=trace(i), states=len(codes),
                        transitions=len(flat), secs=time.time() - t0)
        quiet.append(1 if sc.quiescent(s) else 0)
        for lab, n, viol in sc.successors(s):
            e = enc(n)
            j = ids.get(e)
            if j is None:
                j = len(codes)
                ids[e] = j
                codes.append(e)
                parent.append(i)
                plabel.append(label_id(lab))
            if viol:
                return dict(ok=False, why=viol, trace=trace(i) + [lab], states=len(codes),
                            transitions=len(flat), secs=time.time() - t0)
            flat.append(j)
        offsets.append(len(flat))
        i += 1
    nstates, ntrans = len(codes), len(flat)
    del ids
    # Liveness: from every reachable state some quiescent state is reachable.
    indeg = array("I", bytes(4 * nstates))
    for j in flat:
        indeg[j] += 1
    roff = array("Q", bytes(8 * (nstates + 1)))
    acc = 0
    for j in range(nstates):
        roff[j] = acc
        acc += indeg[j]
    roff[nstates] = acc
    del indeg
    fill = array("Q", roff[:nstates])
    rflat = array("I", bytes(4 * ntrans))
    for src in range(nstates):
        for k in range(offsets[src], offsets[src + 1]):
            dst = flat[k]
            rflat[fill[dst]] = src
            fill[dst] += 1
    del fill
    good = bytearray(quiet)
    q = deque(j for j in range(nstates) if good[j])
    while q:
        n = q.popleft()
        for k in range(roff[n], roff[n + 1]):
            p = rflat[k]
            if not good[p]:
                good[p] = 1
                q.append(p)
    bad = next((j for j in range(nstates) if not good[j]), None)
    if bad is not None:
        return dict(ok=False, why="LIVENESS: no quiescent state is reachable from here",
                    trace=trace(bad), states=nstates, transitions=ntrans, secs=time.time() - t0)
    return dict(ok=True, states=nstates, transitions=ntrans, secs=time.time() - t0)


# ---------------------------------------------------------------------------
# Scenario 1: core moves, fences, park confirmation, roles, shootdown
# ---------------------------------------------------------------------------

FREE, OWNED, LEAVING, JOINING = 0, 1, 2, 3
LIVE, FENCING, FENCED, DEAD = 0, 1, 2, 3
NONE_UNMAP, WAIT, DONE = 0, 1, 2
FORCED, SIGNALLED = 2, 1  # the contract's fence classes 2 and 1


class Moves:
    """Kernels 1..NK; kernel 1 (A) owns the frame F. Per core: the core word
    (state, kernel, fence mark), what the core executes, its phase in the
    entry stub (1 masked, 2 unmasked: only signalled cores have phase 1),
    a pending start request, park confirmation (parked equals the current
    request; parked ever written), a fence signal in flight, the TLB tag of
    F, a pending shootdown, and a take in progress (the kernel taking, and
    the word it read, for its compare-and-swap)."""

    CF = 13
    W, WK, WM, EX, ST, SP, PKC, PKA, SIG, TLB, PD, TI, TO = range(13)
    VARIANTS = {
        "correct": "the protocol of part 9",
        "stale_parked": "a take or a settle trusts any park ever confirmed, not the current request",
        "no_mark": "no fence mark: the fence signals any core its words name, a take ignores marks",
        "giver_live_only": "the verifier's repair instead of the mark: a leaving core is taken only while its giver is live",
        "r6_inflight": "R6 frees core words while a fence signal is still in flight",
        "take_any_class": "a unit-role holder may take a core of a weaker fence class",
        "role_at_read": "the role is checked when a take reads the word, not again at its compare-and-swap",
        "bsp_moves": "the bootstrap core may be given and taken",
        "free_early": "a giver writes free before its core parks; a taker reads only the word",
        "fence_owned": "the fence covers only cores whose word reads owned",
        "no_flush": "no TLB flush when a core leaves or joins",
        "acks_owned": "a shootdown waits only for cores whose word reads owned",
        "acks_wait_only": "a shootdown waits only for acknowledgements written by the cores themselves (expected to hold: a leaving core acknowledges before it parks)",
        "park_no_ack": "a leaving core parks without acknowledging, and the shootdown waits only for written acknowledgements (the verifier's Test 5)",
    }

    def __init__(self, variant, nk=3, owners=(1, 1, 2, 3), cls=(FORCED, SIGNALLED, FORCED, FORCED),
                 bsp=(False, False, False, True), role=2, deaths=2, frame=True):
        assert variant in self.VARIANTS, variant
        self.v = variant
        self.nk, self.nc = nk, len(owners)
        self.owners, self.cls, self.bsp, self.role0, self.D = owners, cls, bsp, role, deaths
        NK1 = nk + 1
        core_r = [4, NK1, 2, NK1, 3, NK1, 2, 2, NK1, NK1, 2, NK1, 2 * NK1]
        self.G = self.nc * self.CF
        # globals: M[1..nk], ROLE, FOWN, AMAP, UNMAP, DEATHS
        self.radix = core_r * self.nc + [4] * nk + [NK1, NK1, 2, 3, deaths + 1]
        self.marks = variant not in ("no_mark", "giver_live_only")
        self.frame = frame

    # field helpers
    def f(self, c, i):
        return c * self.CF + i

    def M(self, k):
        return self.G + k - 1

    @property
    def ROLE(self):
        return self.G + self.nk

    @property
    def FOWN(self):
        return self.G + self.nk + 1

    @property
    def AMAP(self):
        return self.G + self.nk + 2

    @property
    def UNMAP(self):
        return self.G + self.nk + 3

    @property
    def DEATHS(self):
        return self.G + self.nk + 4

    def initial(self):
        s = []
        for c in range(self.nc):
            k = self.owners[c]
            s += [OWNED, k, 0, k, 0, 0, 1, 0, 0, 0, 0, 0, 0]
        # Without the frame, A's address space never maps F: no load, no unmap, no reuse.
        s += [LIVE] * self.nk + [self.role0, 1, 1 if self.frame else 0, NONE_UNMAP, 0]
        return tuple(s)

    def names(self, s, c, k):
        return s[self.f(c, self.W)] in (OWNED, LEAVING, JOINING) and s[self.f(c, self.WK)] == k

    def covered(self, s, c, k):
        if self.v == "fence_owned":
            return s[self.f(c, self.W)] == OWNED and s[self.f(c, self.WK)] == k
        return self.names(s, c, k)

    def kclass(self, s, k):
        cs = [self.cls[c] for c in range(self.nc) if self.names(s, c, k)]
        return min(cs) if cs else FORCED

    def running(self, s, k):
        return any(s[self.f(c, self.EX)] == k and s[self.f(c, self.ST)] == 0 for c in range(self.nc))

    def conf(self, s, c):
        return s[self.f(c, self.PKA)] if self.v == "stale_parked" else s[self.f(c, self.PKC)]

    def lab(self, k):
        return "-ABCDEFG"[k]

    def successors(self, s):
        f, M = self.f, self.M
        nk, nc, v = self.nk, self.nc, self.v
        live = [k for k in range(1, nk + 1) if s[M(k)] == LIVE]
        A = 1

        def new(*pairs):
            L = list(s)
            for i, x in pairs:
                L[i] = x
            return tuple(L)

        # Accusation (panic, stale heartbeat, kill), never of the last live kernel.
        if s[self.DEATHS] < self.D:
            for k in live:
                if len(live) >= 2:
                    yield (f"accuse {self.lab(k)}", new((M(k), FENCING), (self.DEATHS, s[self.DEATHS] + 1)), None)

        for k in range(1, nk + 1):
            st = s[M(k)]
            if st == FENCING and live:
                for c in range(nc):
                    if not self.covered(s, c, k):
                        continue
                    wm, sig = s[f(c, self.WM)], s[f(c, self.SIG)]
                    if self.marks and wm == 0:
                        # The driver's compare-and-swap marks the word and makes a new park request.
                        yield (f"fence {self.lab(k)} marks core {c}", new((f(c, self.WM), 1), (f(c, self.PKC), 0)), None)
                    if (wm == 1 or not self.marks) and s[f(c, self.SP)] == k and s[f(c, self.EX)] == 0:
                        yield (f"fence {self.lab(k)} cancels the start request of core {c}", new((f(c, self.SP), 0)), None)
                    if (wm == 1 or not self.marks) and sig == 0 and (s[f(c, self.EX)] == k or not self.marks):
                        yield (f"fence {self.lab(k)} sends its stop to core {c}", new((f(c, self.SIG), k), (f(c, self.PKC), 0)), None)
                if v == "fence_owned":
                    done = all(not (s[f(c, self.W)] == OWNED and s[f(c, self.WK)] == k
                                    and (s[f(c, self.EX)] == k or s[f(c, self.SP)] == k)) for c in range(nc))
                else:
                    done = all(s[f(c, self.EX)] != k and s[f(c, self.SP)] != k for c in range(nc))
                if done:
                    yield (f"fence {self.lab(k)} confirmed", new((M(k), FENCED)), None)
            if st == FENCED and live:
                if v == "r6_inflight" or all(s[f(c, self.SIG)] != k for c in range(nc)):
                    L = list(s)
                    for c in range(nc):
                        if self.names(s, c, k):
                            L[f(c, self.W)], L[f(c, self.WK)], L[f(c, self.WM)] = FREE, 0, 0
                        if L[f(c, self.TI)] == k:
                            L[f(c, self.TI)], L[f(c, self.TO)] = 0, 0
                    if L[self.FOWN] == k:
                        L[self.FOWN] = 0
                    if k == A:
                        L[self.AMAP] = 0
                        if L[self.UNMAP] == WAIT:
                            L[self.UNMAP] = DONE
                        for c in range(nc):
                            L[f(c, self.PD)] = 0
                    L[M(k)] = DEAD
                    yield (f"R6 for {self.lab(k)}: words cleared, {self.lab(k)} dead", tuple(L), None)

        # A fence signal lands (INIT, SDEI, fence_hart).
        for c in range(nc):
            k = s[f(c, self.SIG)]
            if not k:
                continue
            ex, sp = s[f(c, self.EX)], s[f(c, self.SP)]
            if ex == 0 and sp == 0:
                yield (f"stop of {self.lab(k)} lands on parked core {c}", new((f(c, self.SIG), 0), (f(c, self.PKC), 1), (f(c, self.PKA), 1)), None)
                continue
            viol = None
            if ex not in (0, k) or sp not in (0, k):
                viol = f"P7: the stop of {self.lab(k)} lands on core {c}, which runs or starts {self.lab(ex or sp)}"
            if self.cls[c] == SIGNALLED and s[f(c, self.ST)] == 1 and not viol:
                yield (f"stop of {self.lab(k)} lost on core {c} (SDEI still masked)", new((f(c, self.SIG), 0)), None)
            else:
                yield (f"stop of {self.lab(k)} lands on core {c}",
                       new((f(c, self.EX), 0), (f(c, self.SP), 0), (f(c, self.ST), 0), (f(c, self.SIG), 0),
                           (f(c, self.PKC), 1), (f(c, self.PKA), 1)), viol)

        # Unit role: the successor takes over once the holder's stop is confirmed.
        h = s[self.ROLE]
        if h and s[M(h)] in (FENCED, DEAD) and live:
            best = max(live, key=lambda k: (self.kclass(s, k), -k))
            yield (f"unit role moves to {self.lab(best)}", new((self.ROLE, best)), None)

        # The frame F of kernel A: translation loads, unmap with shootdown, reuse.
        for c in range(nc):
            if s[f(c, self.EX)] == A and s[f(c, self.ST)] == 0 and s[self.AMAP] and s[f(c, self.TLB)] != A:
                yield (f"core {c} loads F for A", new((f(c, self.TLB), A)), None)
        if (s[self.UNMAP] == NONE_UNMAP and s[self.AMAP] and s[M(A)] == LIVE
                and any(s[f(c, self.EX)] == A and s[f(c, self.ST)] == 0 for c in range(nc))):
            L = list(s)
            for c in range(nc):
                tgt = (s[f(c, self.W)] == OWNED and s[f(c, self.WK)] == A) if v == "acks_owned" else self.names(s, c, A)
                L[f(c, self.PD)] = 1 if tgt else 0
            L[self.AMAP], L[self.UNMAP] = 0, WAIT
            yield ("A unmaps F and sends its shootdown", tuple(L), None)
        for c in range(nc):
            if not s[f(c, self.PD)]:
                continue
            if s[f(c, self.EX)] == A and s[f(c, self.ST)] == 0:
                t = 0 if s[f(c, self.TLB)] == A else s[f(c, self.TLB)]
                yield (f"core {c} flushes and acknowledges", new((f(c, self.TLB), t), (f(c, self.PD), 0)), None)
            elif v not in ("acks_wait_only", "park_no_ack") and (
                    not self.names(s, c, A) or (s[f(c, self.W)] == LEAVING and self.conf(s, c))):
                yield (f"core {c} counts as acknowledged (no longer A's, or parked)", new((f(c, self.PD), 0)), None)
        if s[self.UNMAP] == WAIT and not any(s[f(c, self.PD)] for c in range(nc)):
            yield ("unmap done", new((self.UNMAP, DONE)), None)
        if s[self.UNMAP] == DONE and s[self.FOWN] == A and s[M(A)] == LIVE:
            yield ("A gives F away", new((self.FOWN, 0)), None)
        if s[self.FOWN] == 0:
            for k in live:
                yield (f"{self.lab(k)} takes F", new((self.FOWN, k)), None)

        # Core moves.
        for c in range(nc):
            W, WK, WM = s[f(c, self.W)], s[f(c, self.WK)], s[f(c, self.WM)]
            ex, st, sp = s[f(c, self.EX)], s[f(c, self.ST)], s[f(c, self.SP)]
            # give (core_give): the owner's gate writes leaving and a new park request
            if W == OWNED and WM == 0 and ex == WK and st == 0 and s[M(WK)] == LIVE and any(
                    d != c and s[f(d, self.W)] == OWNED and s[f(d, self.WK)] == WK for d in range(nc)):
                viol = None
                if self.bsp[c]:
                    if v != "bsp_moves":
                        pass
                    else:
                        viol = f"P8: the bootstrap core {c} is given away"
                if not self.bsp[c] or v == "bsp_moves":
                    nw = (FREE, 0) if v == "free_early" else (LEAVING, WK)
                    yield (f"{self.lab(WK)} gives core {c}", new((f(c, self.W), nw[0]), (f(c, self.WK), nw[1]), (f(c, self.PKC), 0)), viol)
            # the leaving core parks (stub, CPU_OFF, hart_stop): the request is confirmed
            if ex != 0 and st == 0 and ((W == LEAVING and WK == ex) or (v == "free_early" and W == FREE)):
                t = s[f(c, self.TLB)] if v == "no_flush" else 0
                pd = s[f(c, self.PD)] if v == "park_no_ack" else 0
                yield (f"core {c} parks", new((f(c, self.EX), 0), (f(c, self.PKC), 1), (f(c, self.PKA), 1),
                                              (f(c, self.PD), pd), (f(c, self.TLB), t)), None)
            # settle: a confirmed parked leaving core becomes free
            if W == LEAVING and WM == 0 and self.conf(s, c) and sp == 0 and live:
                yield (f"core {c} settles free", new((f(c, self.W), FREE), (f(c, self.WK), 0)), None)
            # take, step 1: a live kernel reads the word and decides
            if s[f(c, self.TI)] == 0 and sp == 0 and WM == 0:
                if v == "free_early":
                    obs_ok = W == FREE
                else:
                    obs_ok = W == FREE or (W == LEAVING and self.conf(s, c))
                    if v == "giver_live_only" and W == LEAVING:
                        obs_ok = obs_ok and s[M(WK)] == LIVE
                if obs_ok:
                    for k2 in live:
                        if not self.running(s, k2):
                            continue  # a take is a gate call made on a core that runs the taker
                        if self.bsp[c] and v != "bsp_moves":
                            continue
                        if s[self.ROLE] == k2 and self.cls[c] < self.kclass(s, k2) and v != "take_any_class":
                            continue
                        to = (0 if W == FREE else 1) * (nk + 1) + WK
                        yield (f"{self.lab(k2)} reads core {c} free to take", new((f(c, self.TI), k2), (f(c, self.TO), to)), None)
            # take, step 2: compare-and-swap against the word read in step 1
            k2 = s[f(c, self.TI)]
            if k2 and self.running(s, k2):
                ow, ok_ = divmod(s[f(c, self.TO)], nk + 1)
                same = (W == (FREE if ow == 0 else LEAVING)) and WK == ok_ and (WM == 0 or not self.marks) and sp == 0
                # The gate's commit re-reads the role word: a holder (or a kernel that became
                # the holder since step 1) never takes a weaker core. The first run of this
                # explorer found the take-over between step 1 and step 2 without this check.
                if same and v not in ("take_any_class", "role_at_read") and s[self.ROLE] == k2 \
                        and self.cls[c] < self.kclass(s, k2):
                    same = False
                if same:
                    viol = None
                    if s[self.ROLE] == k2 and self.cls[c] < self.kclass(s, k2):
                        viol = f"P6: unit-role holder {self.lab(k2)} takes core {c} of weaker fence class"
                    if self.bsp[c]:
                        viol = f"P8: the bootstrap core {c} is taken by {self.lab(k2)}"
                    yield (f"{self.lab(k2)} takes core {c} (word joining) and writes a start request",
                           new((f(c, self.W), JOINING), (f(c, self.WK), k2), (f(c, self.WM), 0), (f(c, self.SP), k2),
                               (f(c, self.TI), 0), (f(c, self.TO), 0)), viol)
                else:
                    yield (f"{self.lab(k2)}'s compare-and-swap on core {c} fails", new((f(c, self.TI), 0), (f(c, self.TO), 0)), None)
            # start: the core leaves the park for the kernel's entry stub
            if sp:
                viol = f"P1: core {c} is started into {self.lab(sp)} while it runs {self.lab(ex)}" if ex else None
                t = s[f(c, self.TLB)]
                yield (f"core {c} starts in {self.lab(sp)}'s entry stub",
                       new((f(c, self.EX), sp), (f(c, self.SP), 0), (f(c, self.ST), 1 if self.cls[c] == SIGNALLED else 2),
                           (f(c, self.TLB), t)), viol)
            if ex and st == 1:
                yield (f"core {c} unmasks its stop signal", new((f(c, self.ST), 2)), None)
            if ex and st == 2:
                if s[M(ex)] == LIVE and W == JOINING and WK == ex and WM == 0:
                    t = s[f(c, self.TLB)] if v == "no_flush" else 0
                    yield (f"core {c} checks its word and enters {self.lab(ex)}", new((f(c, self.ST), 0), (f(c, self.TLB), t)), None)
                else:
                    yield (f"core {c} finds {self.lab(ex)} not live and powers itself off",
                           new((f(c, self.EX), 0), (f(c, self.ST), 0), (f(c, self.PKC), 1), (f(c, self.PKA), 1)), None)
            if ex and st == 0 and W == JOINING and WK == ex and WM == 0 and s[M(ex)] == LIVE:
                yield (f"core {c} joined {self.lab(ex)}", new((f(c, self.W), OWNED)), None)

    def check(self, s):
        f, M = self.f, self.M
        for c in range(self.nc):
            k = s[f(c, self.EX)]
            if not k:
                continue
            if not self.names(s, c, k):
                return f"P2: core {c} runs {self.lab(k)} but its word no longer names it"
            if s[M(k)] == DEAD:
                return f"P3: core {c} runs dead kernel {self.lab(k)}"
            t = s[f(c, self.TLB)]
            if s[f(c, self.ST)] == 0 and t not in (0, k):
                return f"P5: core {c} runs {self.lab(k)} with a translation {self.lab(t)} installed"
            if s[self.FOWN] != 1 and k == 1 and t == 1:
                return f"P4: F was given away but core {c} still runs A with A's translation of F"
        return None

    def quiescent(self, s):
        f, M = self.f, self.M
        if any(s[M(k)] in (FENCING, FENCED) for k in range(1, self.nk + 1)):
            return False
        for c in range(self.nc):
            if s[f(c, self.W)] in (LEAVING, JOINING) or s[f(c, self.SP)] or s[f(c, self.ST)] or s[f(c, self.SIG)] or s[f(c, self.TI)]:
                return False
        return s[self.UNMAP] != WAIT


class MovesNoFrame(Moves):
    """The moves scenario without the frame F. Sound for P1-P3 and P6-P8 and for
    the liveness of moves and fences: the transitions of F (loads, unmap,
    acknowledgements, give, take) write only F's fields (TLB, PD, UNMAP,
    FOWN, AMAP) and no guard of a move, a fence, a take-over or R6 reads
    them, so removing them changes no reachable value of the other fields."""
    VARIANTS = {k: d for k, d in Moves.VARIANTS.items() if k not in ("no_flush", "acks_owned", "acks_wait_only", "park_no_ack")}

    def __init__(self, variant):
        super().__init__(variant, deaths=2, frame=False)


class Shootdown(Moves):
    """The moves scenario with the frame F and at most one accusation:
    P4, P5 and the liveness of the shootdown, with moves and one fence."""
    VARIANTS = {k: Moves.VARIANTS[k] for k in ("correct", "stale_parked", "no_flush", "acks_owned", "acks_wait_only", "park_no_ack")}

    def __init__(self, variant):
        super().__init__(variant, deaths=1, frame=True)


class MovesFull(Moves):
    """Everything of the moves scenario together, two accusations (about six
    minutes for the corrected protocol): run only when named, as full."""

    def __init__(self, variant):
        super().__init__(variant, deaths=2, frame=True)


# ---------------------------------------------------------------------------
# Scenario 2: kernels with zero cores, wake, resume, barrier, revocation,
# IOMMU entries, admission, retirement, fresh starts
# ---------------------------------------------------------------------------

S_LIVE, S_FENCING, S_FENCED, S_DEAD, S_SEALED, S_SEALED_OLD, S_RETIRED = range(7)


class Seal:
    """Kernels A=1, B=2, C=3 and four physical cores. B starts with two cores
    and contexts admitted on both (NEED = 2); A and C with one each. A grants
    a frame H to B, which maps it. B owns a device whose IOMMU context entry
    sits on a unit whose role C holds. A holds one block beyond its floor.
    Only B seals (the replacement path); the supervisor may disappear."""

    VARIANTS = {
        "correct": "the rules of part 9 (SEAL_NS evidence, resume needs admission, rebuild keeps sealed owners, give before retiring)",
        "no_seal_timeout": "a sealed kernel can be accused only by the supervisor's kill",
        "resume_any": "a sealed kernel resumes on whatever cores are free",
        "rebuild_live_only": "a unit rebuild keeps only the entries of live kernels",
        "retire_then_give": "a kernel retires before giving back its memory",
    }
    T = 4
    NEED0 = (0, 1, 2, 1)

    # fields
    MA, MB, MC, NA, NB, NC_, NEEDB, ROLE, G, BM, RP, ACKB, DEVE, BDEV, SUP, WAKE, MEMA, DEATHS = range(18)

    def __init__(self, variant, deaths=2):
        assert variant in self.VARIANTS
        self.v, self.D = variant, deaths
        self.radix = [7, 7, 7, 5, 5, 5, 3, 4, 3, 2, 2, 2, 2, 2, 2, 2, 2, deaths + 1]

    def initial(self):
        return (S_LIVE, S_LIVE, S_LIVE, 1, 2, 1, 2, 3, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0)

    def m(self, s, k):
        return s[k - 1]

    def n(self, s, k):
        return s[2 + k]

    def need(self, s, k):
        return s[self.NEEDB] if k == 2 else 1

    def free(self, s):
        return self.T - s[self.NA] - s[self.NB] - s[self.NC_]

    def successors(self, s):
        v = self.v
        live = [k for k in (1, 2, 3) if self.m(s, k) == S_LIVE]
        lab = "-ABC"

        def new(*pairs):
            L = list(s)
            for i, x in pairs:
                L[i] = x
            return tuple(L)

        # Accusations: a live kernel fails (bounded); a sealed kernel past SEAL_NS
        # (evidence, not counted as a failure); a sealed kernel killed by the supervisor.
        for k in (1, 2, 3):
            mk = self.m(s, k)
            drivers = [j for j in live if j != k]
            if not drivers:
                continue
            if mk == S_LIVE and s[self.DEATHS] < self.D:
                yield (f"accuse {lab[k]}", new((k - 1, S_FENCING), (self.DEATHS, s[self.DEATHS] + 1)), None)
            if mk == S_SEALED_OLD and v != "no_seal_timeout":
                yield (f"accuse {lab[k]}: sealed longer than SEAL_NS", new((k - 1, S_FENCING)), None)
            if mk in (S_SEALED, S_SEALED_OLD) and s[self.SUP]:
                yield (f"supervisor kills sealed {lab[k]}", new((k - 1, S_FENCING)), None)
        for k in (1, 2, 3):
            mk = self.m(s, k)
            if mk == S_FENCING:
                yield (f"fence {lab[k]} confirmed", new((k - 1, S_FENCED)), None)
            if mk == S_FENCED and live and self.barrier(s, k):
                L = list(s)
                L[k - 1] = S_DEAD
                L[2 + k] = 0
                if k == 1:
                    L[self.G], L[self.MEMA], L[self.RP] = 0, 0, 0
                if k == 2:
                    L[self.BM], L[self.RP], L[self.ACKB], L[self.BDEV], L[self.DEVE], L[self.WAKE] = 0, 0, 0, 0, 0, 0
                    L[self.G] = 0  # grants to B's generation die with it (R3, then freed)
                yield (f"R6 for {lab[k]}: {lab[k]} dead", tuple(L), None)
        # unit role take-over and rebuild
        h = s[self.ROLE]
        if self.m(s, h) in (S_FENCED, S_DEAD) and live:
            succ = live[0]
            keep = self.m(s, 2) in (S_LIVE, S_SEALED, S_SEALED_OLD)
            if v == "rebuild_live_only":
                keep = self.m(s, 2) == S_LIVE
            deve = s[self.DEVE] if keep else 0
            yield (f"unit role moves to {lab[succ]}, which rebuilds the unit", new((self.ROLE, succ), (self.DEVE, deve)), None)
        # B's R2 for A
        if self.m(s, 1) in (S_FENCING, S_FENCED) and self.m(s, 2) == S_LIVE and not s[self.ACKB]:
            yield ("B removes its mappings of A and acknowledges (R2, R5)", new((self.BM, 0), (self.ACKB, 1)), None)
        # seal B (the first half of a replacement)
        if self.m(s, 2) == S_LIVE and s[self.ROLE] != 2 and len(live) >= 2:
            yield ("B seals: its cores leave, its vectors are masked", new((self.MB, S_SEALED), (self.NB, 0)), None)
        if self.m(s, 2) == S_SEALED:
            yield ("SEAL_NS passes", new((self.MB, S_SEALED_OLD)), None)
        if self.m(s, 2) in (S_SEALED, S_SEALED_OLD) and not s[self.WAKE]:
            yield ("a message for sealed B arrives (wake wanted)", new((self.WAKE, 1)), None)
        # resume B
        if self.m(s, 2) in (S_SEALED, S_SEALED_OLD) and s[self.SUP]:
            fr = self.free(s)
            want = s[self.NEEDB]
            cores = want if fr >= want else (fr if v == "resume_any" and fr >= 1 else 0)
            if cores:
                L = list(s)
                L[self.MB], L[self.NB], L[self.WAKE] = S_LIVE, cores, 0
                if L[self.RP]:  # pending revocation served before any thread runs
                    L[self.BM], L[self.RP], L[self.G] = 0, 0, 0
                if self.m(s, 1) in (S_FENCING, S_FENCED):
                    L[self.BM], L[self.ACKB] = 0, 1
                yield (f"supervisor resumes B on {cores} core(s)", tuple(L), None)
        if s[self.SUP]:
            yield ("the supervisor disappears", new((self.SUP, 0)), None)
        # core moves (atomic here)
        for k in live:
            if self.free(s) >= 1 and self.n(s, k) < self.T:
                yield (f"{lab[k]} takes a free core", new((2 + k, self.n(s, k) + 1)), None)
            if self.n(s, k) >= 2 and self.n(s, k) - 1 >= self.need(s, k):
                yield (f"{lab[k]} gives a core", new((2 + k, self.n(s, k) - 1)), None)
        # grant H from A to B and its revocation
        if s[self.G] == 1 and self.m(s, 1) == S_LIVE:
            yield ("A revokes H: grant revoking, Revoke sent to B", new((self.G, 2), (self.RP, 1)), None)
        if s[self.RP] and self.m(s, 2) == S_LIVE:
            yield ("B removes H and answers; A frees the grant", new((self.BM, 0), (self.RP, 0), (self.G, 0)), None)
        if s[self.G] == 0 and self.m(s, 1) == S_LIVE and self.m(s, 2) == S_LIVE and not s[self.BM]:
            yield ("A grants H to B again; B maps it", new((self.G, 1), (self.BM, 1), (self.ACKB, 0)), None)
        # device of B
        if self.m(s, 2) == S_LIVE and not s[self.BDEV]:
            yield ("B's driver attaches its device", new((self.BDEV, 1), (self.DEVE, 1)), None)
        # A's memory and retirement
        if self.m(s, 1) == S_LIVE and s[self.MEMA]:
            yield ("A gives back its block (memory_give)", new((self.MEMA, 0)), None)
        if self.m(s, 1) == S_LIVE and not s[self.MEMA]:
            yield ("A takes a block (memory_take)", new((self.MEMA, 1)), None)
        if (self.m(s, 1) == S_LIVE and s[self.G] == 0 and s[self.ROLE] != 1 and len(live) >= 2
                and (not s[self.MEMA] or v == "retire_then_give")):
            yield ("A retires: its last core leaves", new((self.MA, S_RETIRED), (self.NA, 0)), None)
        # fresh starts by the supervisor
        for k in (1, 2, 3):
            if self.m(s, k) in (S_DEAD, S_RETIRED) and s[self.SUP] and self.free(s) >= 1 and live:
                L = list(s)
                L[k - 1], L[2 + k] = S_LIVE, 1
                if k == 1:
                    L[self.ACKB] = 0
                if k == 2:
                    L[self.NEEDB], L[self.BM], L[self.ACKB], L[self.RP], L[self.WAKE] = 1, 0, 0, 0, 0
                yield (f"supervisor starts {lab[k]} fresh on a free core", tuple(L), None)

    def barrier(self, s, x):
        if x != 1:
            return True  # only A's memory is mapped by another kernel here
        mb = self.m(s, 2)
        if mb == S_LIVE:
            return s[self.ACKB] == 1
        if mb in (S_SEALED, S_SEALED_OLD, S_FENCING, S_FENCED):
            return s[self.BM] == 0
        return True

    def check(self, s):
        for k in (1, 2, 3):
            if self.m(s, k) == S_LIVE and self.n(s, k) < self.need(s, k):
                return f"BUDGET: live kernel {'-ABC'[k]} holds {self.n(s, k)} core(s) for contexts admitted on {self.need(s, k)}"
        if s[self.BDEV] and self.m(s, 2) in (S_LIVE, S_SEALED, S_SEALED_OLD) and not s[self.DEVE]:
            return "IOMMU: B still owns an attached device, but its context entry was cleared"
        if self.m(s, 1) == S_RETIRED and s[self.MEMA]:
            return "RETIRE: A retired with a block it can no longer give back"
        return None

    def quiescent(self, s):
        if any(self.m(s, k) in (S_FENCING, S_FENCED) for k in (1, 2, 3)):
            return False
        if s[self.G] == 2:
            return False
        if s[self.WAKE] and self.m(s, 2) in (S_SEALED, S_SEALED_OLD):
            return False
        return True


# ---------------------------------------------------------------------------
# Scenario 3: credits between two kernels
# ---------------------------------------------------------------------------


class Credits:
    """The ring from kernel X to kernel Y. Four user tasks on X send stamped
    messages that Y's user threads never read (the adversarial case); X's
    kernel must send its own requests (unit requests, revocations), which Y's
    kernel always consumes. Y may die (twice) and start fresh; X runs R0
    before Y's barrier lets it restart. A table at X holds one pending signal
    for Y's notify, tagged with Y's generation."""

    VARIANTS = {
        "correct": "two credit classes per peer (user Qu = 4 with a per-task cap of 1, kernel Qk = 2), counters reset per generation, pending signals purged at R0",
        "shared_credit": "one pool Q = 4 for every class, a per-task cap of Q/4",
        "no_gen_reset": "X keeps its counts of messages in flight across Y's fresh start",
        "no_purge": "R0 keeps the pending signal of Y's old generation",
    }
    QU, QK, Q = 4, 2, 4
    T0, T1, T2, T3, AU, BU, AK, BK, KP, YL, YG, R0D, PS, PSG, DEATHS = range(15)

    def __init__(self, variant, deaths=2):
        assert variant in self.VARIANTS
        self.v, self.D = variant, deaths
        self.radix = [2, 2, 2, 2, 5, 5, 5, 5, 3, 2, 2, 2, 2, 2, deaths + 1]

    def initial(self):
        return (0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0)

    def cap(self):
        return self.Q if self.v == "shared_credit" else self.QU + self.QK

    def successors(self, s):
        v = self.v

        def new(*pairs):
            L = list(s)
            for i, x in pairs:
                L[i] = x
            return tuple(L)

        yl = s[self.YL]
        for t in range(4):
            if s[t] == 0 and yl:
                room = (s[self.BU] + s[self.BK] < self.Q) if v == "shared_credit" else (s[self.BU] < self.QU)
                if room:
                    yield (f"task {t} sends a stamped message to Y", new((t, 1), (self.AU, s[self.AU] + 1), (self.BU, s[self.BU] + 1)), None)
        if s[self.KP] < 2:
            yield ("X's kernel needs to send a request to Y", new((self.KP, s[self.KP] + 1)), None)
        if s[self.KP] and yl:
            room = (s[self.BU] + s[self.BK] < self.Q) if v == "shared_credit" else (s[self.BK] < self.QK)
            if room:
                yield ("X's kernel sends its request", new((self.KP, s[self.KP] - 1), (self.AK, s[self.AK] + 1), (self.BK, s[self.BK] + 1)), None)
        if yl and s[self.AK]:
            yield ("Y's kernel consumes a request (its consumed counter grows)", new((self.AK, s[self.AK] - 1), (self.BK, max(0, s[self.BK] - 1))), None)
        if yl and s[self.DEATHS] < self.D:
            yield ("Y dies: its ring is dropped", new((self.YL, 0), (self.AU, 0), (self.AK, 0), (0, 0), (1, 0), (2, 0), (3, 0),
                                                      (self.DEATHS, s[self.DEATHS] + 1)), None)
        if not yl and not s[self.R0D]:
            L = list(s)
            L[self.R0D] = 1
            if v != "no_gen_reset":
                L[self.BU], L[self.BK] = 0, 0
            if v != "no_purge" and L[self.PS] and L[self.PSG] == s[self.YG]:
                L[self.PS], L[self.PSG] = 0, 0
            yield ("X runs R0 for Y", tuple(L), None)
        if not yl and s[self.R0D]:
            yield ("Y starts fresh (next generation)", new((self.YL, 1), (self.YG, 1 - s[self.YG]), (self.R0D, 0)), None)
        if yl and not s[self.PS]:
            yield ("X signals Y's notify; the signal waits in X's pending table", new((self.PS, 1), (self.PSG, s[self.YG])), None)
        if yl and s[self.PS] and s[self.AU] + s[self.AK] < self.cap():
            viol = None
            if s[self.PSG] != s[self.YG]:
                viol = "STALE: a signal for Y's old generation is delivered to the new one"
            yield ("the pending signal is delivered", new((self.PS, 0), (self.PSG, 0)), viol)

    def check(self, s):
        if s[self.AU] + s[self.AK] > self.cap():
            return "RING: more messages in flight than the ring holds"
        return None

    def quiescent(self, s):
        return s[self.KP] == 0


# ---------------------------------------------------------------------------

SCENARIOS = {"moves": MovesNoFrame, "shootdown": Shootdown, "seal": Seal, "credits": Credits, "full": MovesFull}
DEFAULT = ["moves", "shootdown", "seal", "credits"]
# acks_wait_only is expected to hold: it shows that the shootdown's "counts as
# acknowledged" path is redundant while a leaving core acknowledges before it parks.
EXPECT_OK = {"correct", "acks_wait_only"}


def run_witness(name, needle):
    """Shortest trace to the first transition whose label contains `needle`."""
    scen, _, var = name.partition(":")
    base = SCENARIOS[scen]

    class W(base):
        def successors(self, s):
            for lab, n, viol in super().successors(s):
                yield lab, n, (f"WITNESS: {lab}" if needle in lab else viol)

    r = explore(W(var or "correct"))
    print(f"{name}: {r['why'] if not r['ok'] else 'no such transition is reachable'} ({r['states']} states)")
    for i, step in enumerate(r.get("trace", []), 1):
        print(f"  {i}. {step}")


def run(names):
    failures = 0
    for name in names:
        scen, _, var = name.partition(":")
        cls = SCENARIOS[scen]
        variants = [var] if var else list(cls.VARIANTS)
        for v in variants:
            sc = cls(v)
            r = explore(sc)
            tag = f"{scen}:{v}"
            if r["ok"]:
                print(f"{tag}: OK, {r['states']} states, {r['transitions']} transitions, "
                      f"every state can reach a quiet state ({r['secs']:.1f} s)", flush=True)
            else:
                print(f"{tag}: VIOLATION after {len(r['trace'])} steps: {r['why']} "
                      f"({r['states']} states seen, {r['secs']:.1f} s)", flush=True)
                for i, step in enumerate(r["trace"], 1):
                    print(f"  {i}. {step}")
            # the corrected protocol must hold; every broken variant must fail
            if r["ok"] != (v in EXPECT_OK):
                failures += 1
                print(f"  UNEXPECTED: {tag} was expected to {'hold' if v in EXPECT_OK else 'fail'}", flush=True)
    return failures


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--witness":
        run_witness(sys.argv[3], sys.argv[2])
        sys.exit(0)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(1 if run(args or DEFAULT) else 0)
