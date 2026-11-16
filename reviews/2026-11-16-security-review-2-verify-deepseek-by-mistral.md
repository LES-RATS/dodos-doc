# Verification of `2026-11-16-security-review-2-deepseek.md` (by Mistral)

Subject judged: `reviews/2026-11-16-security-review-2-deepseek.md`, which reviews
commit `e8c2b17` of this repository (`architecture/security.md`, `plan/pending-decisions.md`
and others) and commit `8b6cb05` of `/Users/btw/Documents/repos/dodos` (`contracts/*.wit`).
Both working trees are at exactly those commits; I read `architecture/security.md` end to
end (398 lines), the cited ranges of `plan/pending-decisions.md`, `architecture/storage.md`,
`architecture/memory.md`, `decisions/README.md` (D-035, D-036 at lines 45-46), the diff of
`e8c2b17`, and the contracts at `8b6cb05` (`core.wit`, `actions.wit`, `store.wit`,
`catalog.wit`, `manifest.wit`, `shell.wit`, `agent.wit`, `mcp.md`, plus a `point N` search
over all of `contracts/` including `deps/`). External facts were checked at their sources
today, 16 November 2026, and each is named where used. Verdicts: confirmed, confirmed with
another correction, partly right, wrong. Line numbers are those of the files as they stand
in `e8c2b17` / `8b6cb05`.

---

## 1. The local-write rule and the "outlives the instance" sentence

**Verdict: partly right.** The false sentence is confirmed; the headline attack is not real
as written, because the point-16 trigger is the action's class, not the write destination.

**Quotes checked.** All five quotes match the files: `security.md:184` (point 16, "What an
action of change `reversible` or `irreversible` writes into `home` reaches the long-lived
instance ... So in a task marked `untrusted`, such an action of reach `local` in a package
whose manifest holds \"network\" is decided by the matrix as an external modification:
confirmed, held, counted in the external budget."); `security.md:182` ("... `put` and
`forget` refused, so nothing the request carried outlives the instance"); `core.wit:284-287`
(same keep rule and the same "outlives the instance" clause); `security.md:351` ("... an
action then cannot use a capability the application kept, such as a folder the user picked
once"); `security.md:214` (matrix row "Local reversible modification | Automatic, can be
undone | Automatic, can be undone"). `store.wit:219` is `pick`; `actions.wit:107-110` says
handing an object over adds no mark and reading it adds its marks; `actions.wit:31-36` says a
binding is attenuated to the property's `os-item` rights and to the action's class (read-only
when `change` is `none`), so under `change: reversible` a bound item with `write` is writable;
`core.wit:284-286` likewise returns a kept item attenuated to the class, writable under
`reversible`.

**Replay of the review's scenario.** Steps 1-3 are possible as described: a signed package
with the right "network" (`manifest.wit:80-83`), a `save-note` action declared
`reversible`/`local`, a task marked `untrusted` (a page read) and `private` (the user's file
read), a kept folder `~/Documents` picked once. Step 4 is where the replay diverges: the
review quotes only the unchanged matrix row `security.md:214` and concludes "No confirmation".
But the matrix has three changed rows stated in the contract at `actions.wit:224-230`, and
`actions.wit:226-229` states the point-16 trigger with **no destination condition**: "in a
task marked `untrusted`, an action of change `reversible` or `irreversible` and reach `local`
of a package whose manifest holds \"network\" is decided as an external modification". So
`save-note` is decided at `tasks.invoke` as an external modification — confirmed, held,
counted in `budget.external`, not undoable once done (`security.md:184`, `core.wit:302-305`,
`actions.wit:170-174`) — before it can write anywhere, including the kept item. If the user
confirms, the external-modification row applies (provenance and exact content displayed,
`security.md:217`) plus the hold. Steps 5-7 of the review therefore never happen unconfirmed.

**My reading (the user's question 1).** The rule, as written, applies whatever place the
instance writes to — `home`, an item `keep.get` returns, or a bound item carrying `write` —
and the settling lines are: `actions.wit:226-229` (the trigger is stated without any
destination condition, in the contract's own matrix comment "Three rows change"), and
`security.md:199` ("The matrix ... decides on the marks of the task and of the objects bound
to the pending call") — the matrix decides the pending call at invoke, before any write
exists to inspect, so a destination-conditioned reading is not even decidable at invoke time.
In `security.md:184` and `core.wit:300-301` the "writes into `home`" clause is the
justification for the rule, not a condition on it; "such an action" can only mean the action
of that class and reach in that package. The attack is stopped as written; what is at fault
is the wording, which led the review itself to misread the trigger, and one genuinely false
sentence: "so nothing the request carried outlives the instance" (`security.md:182`,
`core.wit:286-287`) is contradicted by `security.md:184` itself — what the instance writes
into `home` (or into a writable kept or bound item) does outlive the instance and is readable
by the long-lived instance outside any task. That sentence is true only of the `keep` table
(`put`/`forget` refused).

**The proposed correction.** Partly applicable. Rewording point 16 to enumerate every
destination is right and costs nothing: the trigger is unchanged (class + reach +
package-right + mark, decided at invoke), so no honest user pays any additional
confirmation, and nothing breaks — `actions.wit:226-229` already states it that way. But the
review's framing ("the file leaves the machine unconfirmed in a task marked `private` and
`untrusted`") must be withdrawn: in such a task the action is confirmed at invoke. The
"outlives the instance" sentence must be fixed in both places; that part of the correction
closes a real contradiction.

---

## 2. `private` does not follow a copy/drag out of a surface

**Verdict: confirmed with another correction.** The route inconsistency is real, and the
review's fix direction is the one I would write; but the scenario's step 3 is incomplete —
it holds only if the page is not read through the accessibility tree.

**Quotes checked.** All match: `security.md:196` (tree read "adds `private` always ... and
`untrusted` unless the owner of the surface is the system"); `security.md:204` (a capture
takes the union of the marks of the surfaces it captures); `security.md:203` (a pasted or
dropped part keeps the provenance of the object it came from); `store.wit:227-231` (the
clipboard keeps each item's provenance and so does every paste; "A paste never turns
third-party content into origin \"user\""); `core.wit:168-175` (`untrusted` is always set for
the origins `app:`, `web:`, `device:`, `foreign`; reading adds the data's marks to the
reading task); `core.wit:176-183` (`private` comes from the zones at read, plus tree reads);
`security.md:216` (matrix row "External read | Automatic | Automatic without the \"private\"
mark, confirmation otherwise"); `store.wit:197-198` (the shell holds the picker and the
clipboard).

**Replay.** The mechanics the review describes are correct: a selection copied out of a
third-party surface and pasted into the bar carries the item's provenance
(`security.md:203`, `store.wit:227-231`). If that item is a cache/ephemeral object, it keeps
its writer's marks (`security.md:195`), so the task starts `untrusted` (origin `app:`) but not
`private`. The correction to the scenario: step 3 says "The task reads the page: `untrusted`
(already set)" — but if the agent reads the open page through its accessibility tree (the
route the design provides, `actions.wit:111-114` `screen`, and the one walk-through 1 uses at
`security.md:311`), then `security.md:196` adds `private` and the fetch in step 3 is confirmed;
walk-through 2 says exactly this at `security.md:312`. The exploitable variant is the one
where no tree read occurs: the instruction and the secret both arrive via the paste itself
(or the page is fetched over the network, origin `web:`, marks `untrusted` only). Then the
external read in an `untrusted`-but-not-`private` task is automatic (`security.md:216`) and
the pasted data rides in the address — the `private` × `untrusted` cell of the matrix never
fires, which is the one cell D-036 exists to guard (decisions/README.md:46). So the finding
stands as a case the text does not settle: what marks a copied selection carries is not
settled (`store.wit:227-231` keeps the item's provenance; `core.wit:176-183` adds `private`
only for zone reads and tree reads), while `security.md:196`'s own rationale — "what the
user's screen shows is the user's" — covers copy, cut and drag as much as the tree.

**The count (the user's question 2).** With the review's rule (every route out of a surface
carries `private` always), pasting a public web page into the bar makes the task `private`
and `untrusted`, so the cost is exactly: one confirmation per external read in that task
(`security.md:216`); external modifications and irreversible locals are confirmed whatever
the marks, so they do not change; the grant for the rest of the task is unavailable in a
marked task (point 27, `security.md:340-344`, `actions.wit:238-249`); and `private` context
goes to a remote model only if the user enabled that provider (point 15's costs,
`security.md:349`). Marks die with the task, so the cost is per task, not per paste. What
the unmarked paste leaves open is the other side of the same cell: surface-shown private data
copied out and pasted without a `private` mark, exfiltrated in the address of an automatic
external read in an `untrusted` task, with no confirmation — the residual named at
`security.md:185` ("data carried in the address") was priced for non-private data.
**The rule I would write is the review's**: extend `security.md:196` to every route out of a
surface (tree read, copy/cut, drag, capture), with `private` always and `untrusted` unless
the owner of the surface is the system, and align `security.md:203` and `:204` to it. The
tree-read route already pays this cost for on-screen reads of even public pages, so the
extension makes the routes consistent and its marginal cost falls only on tasks that use
copy/drag instead of reading the surface; the alternative (carry only the surface's marks,
as captures do) would let the producer's marks decide what is private, which is exactly what
point 15 rejects ("the producer decides, against \"never by the producer\"",
`security.md:349`).

**The proposed correction.** Closes the finding; costs one confirmation per external read in
tasks that used a surface-content route; breaks nothing structural. Apply, with the scenario
corrected as above.

---

## 3. "A false class gains nothing for a local action" vs the new residual

**Verdict: partly right.** The gap is real; the claim that the quoted sentence is false is
overstated.

**Quotes checked.** `security.md:103` (row "Hostile or compromised application ... a false
class gains nothing for a local action (D-035). **Not stopped**: a false class on an action of
reach `external`"); `security.md:184` ("In a task without the mark it stays automatic, which
leaves the residual of a hostile local model"); `security.md:183` ("For an action of reach
`local`, the declared class is therefore binding, and lying about it gains nothing."). All
match.

**Replay.** The sentences at `103` and `183` are about *false* classes, and they remain true:
the instance is linked to the class (`core.wit:280-299` — every network import answers
`denied` for reach `local`), so lying about the class gains nothing. What the review's
scenario shows is different and real: a hostile application need not lie. The user asks "file
this contract in `<app>`" with their own file; the task never reads untrusted content, so it
is unmarked; the action `save-note` (truthfully `reversible`/`local`) is automatic
(`security.md:214`); it writes the bound file into `home` or a kept item; the long-lived
instance, which holds "network", sends it outside any task. No confirmation ever appears.
That residual is acknowledged — `security.md:184` names it and row `105` lists it — but
attributed to "a hostile local model" only, while a hostile application suffices; row `103`'s
"Not stopped" cell omits it. Note also that D-036 as decided "targets agent tasks"
(decisions/README.md:46), so the exfil through the long-lived instance sits outside the rule's
literal scope; the page prices it only as a residual. So: the row is incomplete and the
attribution at `184` is too narrow, but the two quoted sentences are not contradicted.

**The proposed correction.** Apply it: scope the `103` claim to the store effect, add the
true-class networked-package local write to the "Not stopped" cell, and say "a hostile
application, or a hostile local model" at `184`. Text-only; no honest user pays a
confirmation; nothing breaks.

---

## 4. `TPM2_PolicyAuthorize` cited to Part 1

**Verdict: confirmed.**

**Quotes checked.** `security.md:55` and `plan/pending-decisions.md:908` both say "TCG, TPM
2.0 Library Part 1, `TPM2_PolicyAuthorize`". Both match.

**Source read today, 16 November 2026.** TCG, "Trusted Platform Module 2.0 Library Part 3:
Commands, Version 185, March 12, 2026"
(trustedcomputinggroup.org/wp-content/uploads/Trusted-Platform-Module-2.0-Library-Part-3-Commands_Version-185_pub.pdf —
found today); the contents of revision 1.81 Part 3 list "Table 154 — TPM2_PolicyAuthorize
Command" and "Table 155/166 — TPM2_PolicyAuthorizeNV"; revision 1.46 lists "23.16
TPM2_PolicyAuthorize". Commands are defined in Part 3; Part 1 is the Architecture volume.
The substantive claim — a policy authorized by a signature of the project's key is satisfied
by any later signature of the same key, so every image the project ever signed can unseal —
is the correct semantics of `TPM2_PolicyAuthorize`. Only the volume is wrong.

**The proposed correction.** "TCG, TPM 2.0 Library Part 3: Commands, `TPM2_PolicyAuthorize`",
in both places. Closes it; text-only; breaks nothing. Apply.

---

## 5. "Points 15 to 28 are written there as recommended"

**Verdict: confirmed.**

**Quote checked.** `security.md:390`: "Points 15 to 28 are written there as recommended."
Matches.

**Contract search (mine, today, over all of `contracts/` including `deps/`).** The `point N`
references are exactly: `core.wit` 1 (line 313), 15 (184), 16 (307), 17 (287); `actions.wit` 5
(206), 16 (229), 18 (226), 27 (244-245, split across lines), 28 (230); `catalog.wit` 18 (112),
22 (90); `shell.wit` 28 (71); `agent.wit` 3 (28), 6 (201); `mcp.md` 5 (63), 6 (64). Points 19,
20, 21, 23, 24, 25 and 26 appear nowhere; and there is indeed no capture interface, no
confirmation-focus rule and no scanout rule in `contracts/` (grep today: "capture" appears
only as the origin/principal in `core.wit:92` and in marks prose). So the sentence is false
for seven of the fourteen points, exactly as the review says.

**The proposed correction.** "Points 15, 16, 17, 18, 22, 27 and 28 are written there as
recommended; points 19, 20, 21, 23 and 26 have no place in a WIT file yet, and 24 and 25 are
not contract matter." Accurate against my search. Apply.

---

## 6. CaMeL section 6.4

**Verdict: confirmed.**

**Quote checked.** `security.md:299`: "... which covers the control-flow dependencies that
CaMeL tracks one by one (section 6.4)". Matches. The diff of `e8c2b17` confirms the citation
was changed from "section 5.4" to "section 6.4" by this commit (parent `e8c2b17^` line 283
says "section 5.4").

**Source read today, 16 November 2026.** arXiv 2503.18813v2, "Defeating Prompt Injections by
Design" (Debenedetti et al.), 24 Jun 2025, https://arxiv.org/html/2503.18813v2. The direct
fetch of the HTML truncates at about 33 KB (through §5.4), but the headings I read directly
from it are "### 5.3 Capabilities" and "### 5.4 CaMeL Interpreter", and the header reads
"arXiv:2503.18813v2 [cs.CR] 24 Jun 2025". Through the search index of that same v2 HTML page
today I read the paper's own cross-reference: "This is analogous to an SQL injection attack
in which an adversary manipulates the query parameters rather than the structure of the query
itself. **We show in Section 6.4 that this can be taken one step further and even enable
arbitrary code execution.**" Two independent readers of v2 give §6.4's title as "when data
flow becomes control flow" (0xchamin reading note, 4 August 2026) and quote its figure
caption: "Data Flow effectively becomes Control Flow as all tools can be chosen based on the
instructions from data" (§6.4, p.17); a visual summary describes §6.4 as the demonstration
that Claude, o3-mini and o1 can be induced to generate code turning email-derived
instructions into arbitrary tool calls. So §6.4 is a subsection of the evaluation in which the
authors attack their own design (parameter-level manipulation reaching arbitrary code
execution); the fine-grained per-value tracking of control and data flow is described in
§5.3 "Capabilities" and §5.4 "CaMeL Interpreter".

**The user's question 3.** In v2, the section that describes what `security.md:299` cites
CaMeL for — the control-flow dependencies tracked value by value — is **§5.3 "Capabilities"
and §5.4 "CaMeL Interpreter"**. **§6.4 is titled "When data flow becomes control flow"** (title
read from two secondary readers of v2 plus the v2 HTML's own "We show in Section 6.4 ..."
cross-reference; I could not open the §6.4 heading in the primary HTML directly because the
fetch truncates before §6 — the part I read in the primary source is the §5.3/§5.4 headings
and the intro's pointer to §6.4). §6.4 is the attack study, not the tracking description.

**The proposed correction.** "(sections 5.3 and 5.4)", or §5.4 alone as before the commit.
Right; closes it; text-only. Apply.

---

## 7. P-055 option C and the authority over the NV index

**Verdict: confirmed (as an unsettled case).**

**Quotes checked.** `plan/pending-decisions.md:908` (option C: "Against the signing key and
a minimum version in a TPM NV index raised by security updates (`TPM2_PolicyAuthorizeNV`, or
a counter). Gives: updates do not break unlocking, and an old signed image no longer
unlocks. Costs: one NV index and one write per security update.") and `security.md:55`.
Both match.

**The case the text does not settle.** A grep over the whole Docs repository (today) finds
the NV index named only at `security.md:55`, `security.md:358` and `pending-decisions.md:908`;
nothing names who may write it. The old flawed image is itself signed by the project's key,
so with a plain writable NV index the two candidates are as the review says: either any
signed image may rewrite the minimum down (then option C gives nothing over option A — the
attacker boots the old image, writes its version back, unseals), or the write requires an
authority the old image does not hold, which the entry never defines. The "or a counter"
alternative is not interchangeable: an NV counter (`TPMA_NV_COUNTER`) can only be
incremented (`TPM2_NV_Increment`), never written down, while `TPM2_PolicyNV` (Part 3, e.g.
§23.9 in rev 1.59, found today) reads an NV operand in a policy — the two mechanisms have
different write authorities. (The counter property is from the TPM 2.0 specification
structures, Part 2, which I did not re-read line by line today — from the specification, not
from a fresh read.) The choice decides whether the recommendation is worth anything, and the
owners are asked to choose it.

**The proposed correction.** Sound; I would write the fallback the review offers as the
primary text, because the authority cannot be written down today: state as option C's cost
that an old signed image can lower a plain NV index, in which case C equals A, unless the
index is an NV counter the TPM refuses to decrease, read by `TPM2_PolicyNV` in the unseal
policy. Closes the unsettled case by making the gap explicit; costs no confirmations;
breaks nothing.

---

## 8. Ladybird's `AudioServer`

**Verdict: confirmed.**

**Quote checked.** `security.md:139`: "Ladybird's helpers that serve one site
(RequestServer, ImageDecoder, AudioServer)". Matches.

**Source read today, 16 November 2026.** `Documentation/ProcessArchitecture.md` at master of
LadybirdBrowser/ladybird (raw.githubusercontent.com, read today). The table "Process | How
many" gives: "**RequestServer** | One per browsing session and top-level site, plus one per
session with no site"; "**ImageDecoder** | One per browsing session and site, or one for a
single process"; "**MediaServer** | One per renderer"; "**AudioServer** | One per renderer";
"**VideoDecoderServer** | One per MediaServer"; "**WebRTCClient** | One per **WebContent**
process". The prose: "**RequestServer** and **ImageDecoder** are shared by the renderers of a
site, while the processes below the renderers each work for a single renderer." So
AudioServer serves one renderer, not one site, and a renderer can host documents of more than
one site.

**The proposed correction.** "Ladybird's helpers that serve one site (RequestServer,
ImageDecoder) and its per-renderer helpers (MediaServer, AudioServer, VideoDecoderServer,
WebRTCClient)". Right (VideoDecoderServer is one per MediaServer and WebRTCClient one per
WebContent, both per-renderer in effect). Apply; text-only; small.

---

## 9. "row 104"

**Verdict: confirmed.**

**Quotes checked.** `security.md:334` ends: "A hostile local model is not covered by this
recommendation: row 104 keeps it as a residual." The sentence is new in `e8c2b17` (verified in
the diff). Line 104 of the current file is the row "Hostile content read by the agent (prompt
injection)"; the hostile model row is line 105, and it is the one carrying the residual.
`plan/pending-decisions.md:690` (P-037, option A tail) says "a hostile local model stays a
residual (security.md, row of the hostile model)" — number-free and right, as the review says.

**The proposed correction.** "the row of the hostile model in [Adversaries](#adversaries)
keeps it as a residual". Right — a number rots (this very commit added lines). Apply.

---

## The corrections I would apply, as exact text, in order of severity

1. **The surface-content routes (finding 2) — the only live unconfirmed path I found.** In
   `architecture/security.md:196`, replace
   "**Reading a surface's accessibility tree** adds `private` always, since what the user's
   screen shows is the user's, and `untrusted` unless the owner of the surface is the system"
   with:
   "**Reading a surface, by any of the routes the system offers, adds `private` always —
   its accessibility tree (`accessibility`), a selection copied or cut from it
   (`exchange.copy`), an item dragged out of it, a capture of it — and `untrusted` unless the
   owner of the surface is the system, since what the user's screen shows is the user's.**"
   In `security.md:203`, after "keeps the provenance of the object it came from (the
   clipboard keeps it)", add: "A pasted or dropped part therefore starts its task with the
   marks of the surface it came from, not only with the origin of its producer." In
   `security.md:204`, change "takes the union of the marks of the surfaces it captures" to
   "takes the union of the marks of the surfaces it captures, and adds `private` always". In
   `contracts/core.wit:182-183`, extend the tree-read sentence to the same four routes.
   Cost: one confirmation per external read in a task that used a surface route (`security.md:216`);
   nothing else changes; marks die with the task.

2. **The false "outlives the instance" sentence (finding 1).** In `architecture/security.md:182`,
   replace "so nothing the request carried outlives the instance" with "so nothing the
   request carried is *kept* by the instance; what the instance writes where its own
   component can read it afterwards is the subject of the next bullet". In
   `contracts/core.wit:286-287`, replace "so nothing the request carried outlives the
   instance" with "so nothing the request carried is kept; what the instance writes where
   its own component can read it afterwards is decided under point 16". Closes the
   contradiction with `security.md:184`; text-only.

3. **Point 16's trigger, stated destination-independently (finding 1).** In
   `architecture/security.md:184`, replace the first two sentences with: "**A local write of
   a package that holds the network** (Proposed, [point 16](#points-for-the-two-owners)). In
   a task marked `untrusted`, every action of change `reversible` or `irreversible` and
   reach `local` of a package whose manifest holds \"network\" is decided by the matrix as an
   external modification: confirmed, held, counted in the external budget — whatever it
   writes, because what it writes into `home`, into an item `keep.get` returns, or into a
   bound item that carries `write` can be read by the long-lived instance, which holds the
   right \"network\" if the manifest asks for it, outside any task." Keep the rest of the
   bullet ("In a task without the mark it stays automatic, which leaves the residual of a
   hostile application, or a hostile local model ..." — see 4 below). Mirror the same wording
   in `contracts/core.wit:300-305`. This matches what `actions.wit:226-229` already states and
   what the matrix can actually decide at invoke (`security.md:199`); no change in
   confirmations, nothing breaks.

4. **The adversary row and the residual's attribution (finding 3).** In
   `architecture/security.md:103`, replace "a false class gains nothing for a local action
   (D-035). **Not stopped**: a false class on an action of reach `external` ([point
   1](#points-for-the-two-owners))" with "a false class gains nothing for a local action's
   effect on the store (D-035). **Not stopped**: a false class on an action of reach
   `external` ([point 1](#points-for-the-two-owners)); a true local class of a package that
   holds \"network\", run in a task without the `untrusted` mark, which its long-lived
   instance can then send off the machine ([point 16](#points-for-the-two-owners))". In
   `security.md:184`, replace "which leaves the residual of a hostile local model" with
   "which leaves the residual of a hostile application, or a hostile local model". Text-only.

5. **P-055 option C's unsettled authority (finding 7).** In `plan/pending-decisions.md:908`,
   replace option C with: "C. Against the signing key and a minimum version held in an NV
   *counter* the TPM refuses to decrease (`TPMA_NV_COUNTER`, read by `TPM2_PolicyNV` in the
   unseal policy), incremented once by each security update. Gives: updates do not break
   unlocking, and an old signed image no longer unlocks. Costs: one NV counter and one
   increment per security update — or, if that authority cannot be written down today, the
   cost that an old signed image can lower a plain NV index (`TPM2_PolicyAuthorizeNV`) and the
   option then equals A." (Mirror in `security.md:55` and `security.md:358` if adopted.)

6. **The CaMeL citation (finding 6).** In `architecture/security.md:299`, replace "(section
   6.4)" with "(sections 5.3 and 5.4)". Text-only; the pre-commit value 5.4 was already right.

7. **The TPM volume (finding 4).** In `architecture/security.md:55` and
   `plan/pending-decisions.md:908`, replace "TCG, TPM 2.0 Library Part 1,
   `TPM2_PolicyAuthorize`" with "TCG, TPM 2.0 Library Part 3: Commands,
   `TPM2_PolicyAuthorize`". Text-only.

8. **The "points 15 to 28" sentence (finding 5).** In `architecture/security.md:390`, replace
   "Points 15 to 28 are written there as recommended." with "Points 15, 16, 17, 18, 22, 27
   and 28 are written there as recommended; points 19, 20, 21, 23 and 26 have no place in a
   WIT file yet, and 24 and 25 are not contract matter." Text-only.

9. **"row 104" (finding 9).** In `architecture/security.md:334`, replace "row 104 keeps it as
   a residual" with "the row of the hostile model in [Adversaries](#adversaries) keeps it as
   a residual". Text-only.

10. **Ladybird's helpers (finding 8).** In `architecture/security.md:139`, replace
    "Ladybird's helpers that serve one site (RequestServer, ImageDecoder, AudioServer)" with
    "Ladybird's helpers that serve one site (RequestServer, ImageDecoder) and its
    per-renderer helpers (MediaServer, AudioServer, VideoDecoderServer, WebRTCClient)".
    Text-only.

The review's two "smaller points" also check out and are worth fixing with the above:
`plan/pending-decisions.md:654` still points at "lines 312-329" for the points (they are now
332-345) and "line 132" for the sources (now line 160) — verified; and `security.md:188`
lists "a keyboard accepted" among the fixed-class administration actions while point 12
(`security.md:342-344`) makes acceptance a gesture — verified, harmless.

---

## What I checked and found correct in the review

- Every quoted line of `security.md`, `core.wit`, `actions.wit`, `store.wit`,
  `pending-decisions.md` that its nine findings cite — all match the files at `e8c2b17` /
  `8b6cb05`, including the line numbers (184, 182, 351, 214-217, 196, 204, 203, 216, 103,
  183-185, 55, 390, 299, 139, 334, 195; core.wit:168-175, 176-187, 284-289, 300-312;
  actions.wit:31-36, 107-110, 170-174, 226-230, 240-249; store.wit:44-47, 197-198, 219,
  227-231; pending-decisions.md:908).
- The claim that `e8c2b17` changed the CaMeL citation from 5.4 to 6.4, and that the "row 104"
  sentence is new in the commit — both verified in `git show e8c2b17`.
- Point 16's mechanics across the three texts (`security.md:184`, `core.wit:300-312`,
  `actions.wit:226-230`): same trigger (marked task, `reversible`/`irreversible`, reach
  `local`, package holding "network") and same consequences (confirmed, held, counted in
  `budget.external`, not undoable once done per `actions.wit:170-174`) — with the one
  destination-wording divergence treated in finding 1 above.
- Point 27 against `actions.wit:238-249` (grant pinned to object versions, collection binds
  always ask, grant ends on the `untrusted` mark) and point 28 against `shell.wit:65-72`
  (`denied` for the bar and a confirmation, `busy` while the user types elsewhere, no key
  dropped, confirmed in a marked task) — both agree with the page.
- Point 17 against `core.wit:284-289` — same text as `security.md:182` and `security.md:351`.
- The `private` zone rule is the same in `security.md:195`, `storage.md:64`,
  `core.wit:176-187`, `store.wit:44-47`; the zone list of `storage.md:44-54` has exactly the
  nine zones. No contradiction with the asset table.
- The reserved rights in `manifest.wit:73-100` ("audio-playback", "microphone",
  "audio-capture", "accessibility-read", "global-shortcuts", "input-injection" reserved,
  installer refuses them) and the absence of any camera/screen-capture right; no
  notification interface (`catalog.wit:86-87` itself says "no interface in this version").
- Attack 2's correction at `security.md:312`; the indicator claim at `security.md:13`; the
  discreet-mark limit at `security.md:282`.
- External facts in its "checked and found correct" list, re-verified today: the Microsoft
  Community Hub page "[UPDATED]: Microsoft UEFI Signing Requirements" (the GPLv3 sentence and
  the GRUB 2 example, read today); Wasmtime's `docs.wasmtime.dev/security.html` ("on aarch64
  the `csdb` instruction is disabled by default due to its significant performance penalty",
  read today); CaMeL v2's header "arXiv:2503.18813v2 [cs.CR] 24 Jun 2025" (read today in the
  v2 HTML). One trivial slip: the "Decided" shared-cache line is at `memory.md:22`, not
  `memory.md:23` as the review wrote.

## What I did not check

- The kernel repository (`dodos-kernel`): the "replacement slot" line at `security.md:31` and
  the open point at `kernel-interface.md:2215`.
- The §6.4 heading in the primary arXiv HTML (my fetch truncates at ~33 KB, before §6); the
  title "When data flow becomes control flow" comes from two secondary readers of v2 plus
  the v2 HTML's own "We show in Section 6.4 ..." cross-reference quoted through its search
  index. The §5.3/§5.4 headings and the intro sentence I read in the primary v2 HTML directly.
- Part 2 of the TCG library (NV attribute semantics, `TPMA_NV_COUNTER`) — from the
  specification's structure, not re-read line by line today; Part 3 TOCs for
  `TPM2_PolicyAuthorize`/`TPM2_PolicyNV` were found today.
- Whether an Intel fTPM implements `TPM2_PolicyAuthorizeNV` and NV counters as option C needs.
- The GPU trial claims behind P-098 option C (`ui.md:14`) and the latency gate's numbers.
- `plan/progress.md` and the state of pull request 1 of the system repository beyond commit
  `8b6cb05`; the full diff of `e8c2b17` beyond the lines quoted; decisions other than D-035
  and D-036; the pending entries P-092 to P-103 beyond what the findings quote (I read
  P-055 and P-037 in full and the group-3 intro at `pending-decisions.md:654`).
- Ladybird's Hub "not sandboxed yet" sentence — the ProcessArchitecture.md read today
  confirms Hub's role in launching helpers; I did not verify the "owns cookies, web storage,
  blob URLs, permissions and fonts" sentence verbatim (not one of the nine findings).
