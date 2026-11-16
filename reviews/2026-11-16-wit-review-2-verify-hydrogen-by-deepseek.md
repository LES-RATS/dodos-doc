# Verification of `2026-11-16-wit-review-2-gemini-hydrogen.md`

**Judged:** the ten findings of the second-review file against commit `8b6cb05` of `/Users/btw/Documents/repos/dodos` (branch `step0-contracts`), compared with `aab7417`, in `contracts/*.wit`, `contracts/mcp.md`, `contracts/README.md` and `verify`; the architecture documents in `/Users/btw/Documents/repos/Docs/architecture/`; `decisions/README.md` and `plan/pending-decisions.md`.

**How.** Every quote was read at `8b6cb05` with line numbers (`git show 8b6cb05:contracts/...`, `awk '{printf "%d: %s\n", NR, $0}'`); every scenario was replayed against the quoted lines; `git diff aab7417 8b6cb05` was read for every hunk a finding rests on, so that "introduced" below means "the quoted rule or claim first appears in this commit". The `verify` claims were reproduced in a copy of the tree outside the repository, `/tmp/wrv-h` (copied with `cp -R contracts verify target`, never edited in place; `diff -r` against `contracts/` afterwards shows the copy is the committed tree). Nothing in either repository was modified; this file is the only output.

**Toolchain, at its own source, on 16 November 2026:** `wasm-tools 1.263.0` (`/Users/btw/.nix-profile/bin/wasm-tools`), `sha256sum (Darwin) 1.0` at `/sbin/sha256sum`, `shasum` at `/usr/bin/shasum`, BSD `sed` of Darwin 27.2.0. WASI 0.3.2 on 13 October 2026 and 0.3.1 on 11 August 2026 were confirmed on the web (search result quoting the WASI release notes and wasi.dev roadmap); the gating of `error-context` was confirmed at the tool, not from memory.

## Verdicts at a glance

| # | Subject | Verdict | Introduced by `8b6cb05`? | Its correction |
|---|---|---|---|---|
| 1 | `none, external` reads `home`/`keep` unconfirmed; "which the long-lived instance can do anyway" | **confirmed** | the false claim yes; the hole is older | partly: both branches break an honest component; mine below |
| 2 | bound `collection` carries no mark; "shared packages carry none" | **partly right** | yes | the second branch is right; the first is already settled by a line it did not quote |
| 3 | secret field dead end on an application surface | **confirmed** (3.1), **confirmed as unsettled** (3.2), **partly right** (3.3) | 3.1 yes; 3.2 in part; 3.3 no | 3.1 and 3.2 close it; 3.3's second half is over-claimed |
| 4 | `exchange.copy` gesture cannot be recognised | **confirmed** | yes | right, and buildable (an `option` field on `button`) |
| 5 | reserved "microphone" vs the wake-word target; socket scope | **confirmed** (microphone), **confirmed but older** (sockets), **weak** (long-lived-instance note) | microphone yes; sockets no | both buildable |
| 6 | `"os-item"` inside array `items` in `mcp.md` | **confirmed** | yes | right; I prefer the other branch of its either/or |
| 7 | `writes: list<bound>` cannot express metadata or collection writes | **confirmed** | yes | right; one more defect it missed |
| 8 | `update` accepts a parent cycle | **confirmed** | no, older | right and minimal |
| 9 | `choose` marks; "the task's marks when the call started" | **partly right** | no, older | sub-1 right; sub-2's stated harm is one of two readings |
| 10 | four `verify` bypasses, macOS `sha256sum --status` failure | **confirmed**, all five reproduced | 1–4 yes, 5 no | 1 is not portable as written; 2 does not close its own bypass |

---

## 1. `none, external` action instances read `home` and `keep` (`breaks a guarantee`, `wrong fact`)

**Quotes.** All exact at `8b6cb05`: `core.wit:310-312` (the "Known limit, not a hole" sentence), `core.wit:283-286` (`"/home" is the request's \`home\``, `keep`: `get` and `slots` only, attenuated to the class), `core.wit:293-299` (reach `external`: sockets and name lookup fail, `wasi:http` `client` reaches only the hosts the manifest lists for that action, GET and HEAD for change `none`), `manifest.wit:80-83` and `117-118`, `actions.wit:211-213`, `219-221`, `226-229`. One slip: "`request.objects` at `actions.wit:109`" — line 109 is the doc line; the field is line 110. Nothing turns on it.

**Replay, step by step.** A package with `rights: []` and an action `fetch {change: none, reach: external, hosts: ["https://attacker.example"]}` is legal: `manifest.wit:117-119` requires at least one host for reach `external` and says nothing about the "network" right, and `manifest.wit:80-83` scopes "network" to "the long-lived instance" only. `grep -n '"network"' contracts/*.wit` finds no line that ties `action.hosts` to that right, in either direction. In a task marked `untrusted` and not `private` — reachable, since `actions.wit:204-205` says a page of `available` holding a third-party entry "marks the task `untrusted`" and gives it no `private` — `tasks.invoke` reads the `none, external` row at `actions.wit:219-221` as `runs`. Inside the instance, `/home` is the request's `home` (`core.wit:282`) and is readable; `core.wit:177-179` makes every read from the application zone carry `private`, which marks the instance and not the task, so the matrix has already decided. A `GET` with the bytes in the address, or `keep.get("doc")` for a file the user picked once (`store.wit:186-190`; `store.wit:178` puts the table on the component identity, so the action instance reads the long-lived instance's slots), carries it out. The scenario replays.

**Where the review is right and where it is not.** The claim "which the long-lived instance can do anyway" is false for exactly the packages that matter. `core.wit:259-262`: "an import that is not granted is still linked, and every call on it fails with its interface's own refusal (… wasi:http `HTTP-request-denied` …)", and `core.wit:275-276` gives `wasi:sockets` and `wasi:http` to the long-lived instance "only with the manifest right "network"". A package without that right reaches no host from its long-lived instance at all; a package with it can still list action hosts outside its scope, which the long-lived instance cannot reach either. So the sentence is wrong in the no-right case and in the out-of-scope case, and it is wrong precisely where it is load-bearing: `security.md:216` decides that an external read in a task marked both `private` and `untrusted` is confirmed, `security.md:349` (point 15) states the cost as "almost every task that touches the user's data or an application's `home` is `private`, so once it is also `untrusted`, every external read is confirmed", and D-036 (`security.md:236`) is decided. The instance reads the `private` data after the decision, so that guarantee does not fire. The review's third sub-point is also right and new: `actions.wit:211-213` says the matrix counts the marks "of the items bound to the call", while `actions.wit:226-229` and `core.wit:302` condition the network-local override on the task alone.

**Introduced?** The false claim and the `private`-from-the-zone rule are new in `8b6cb05` (the diff adds both). The matrix row itself is unchanged from `aab7417`, and `keep` in a `none` action instance was already imported read-only there ("`keep`, "/home" and the bound objects are read-only when change is `none`"). Under `aab7417`'s marks (the writer's, not the zone's) an application's own `home` carried `untrusted`, not `private`, so the trifecta this opens did not exist yet. Verdict: introduced.

**Its correction.** Both branches break an honest component, in opposite directions.

- "Make `/home` and `keep` answer `denied` in any `change: none, reach: external` instance that runs unconfirmed in a task marked `untrusted`": this breaks the remote MCP adapter that `mcp.md:44` describes — "a token kept between calls lives in `home`, since an action instance keeps nothing else" — and every API client whose credential sits in `home`. `security.md:350` already rejects the same idea for `local` ("the request must carry it").
- "Require every host in `action.hosts` to be within the package's "network" right": this grants the long-lived instance network authority to satisfy an action's authority. A package whose only network use is inside actions — the least-authority shape — could no longer declare a host at all; `mcp.md:44` and `core.wit:300` both frame "network" as the long-lived instance's right, and this would make it mandatory.

Both are buildable; neither is the smallest rule. Mine makes the sentence true instead of deleting it: the limit holds where the manifest holds "network" over every host of the action, and where it does not, a marked task confirms the call. Exactly one matrix clause and one sentence change, and no honest component loses a capability it has today.

## 2. Bound `collection` handles and "shared packages carry none" (`unsettled case`, `contradiction`)

**Quotes.** Exact: `store.wit:113-117` (`collection-info` has `held` and `quota` only, no `provenance`, while `object-info` has one at line 47), `store.wit:165`, `core.wit:168-170`, `core.wit:176-182`, `actions.wit:211-213`, `219-221`.

**Replay.** A `user`-zone folder bound in `objects` of a `none, external` call: `collection-info` carries nothing the matrix can read, and `core.wit:177` speaks of "every read", which binding is not. So `tasks.invoke` has no `private` to see. That much is right. But the review stops one line short: `actions.wit:240-241` reads "the same bound objects (the same object at the same version; a call that binds a collection, which has no version, always asks)". Read outside its paragraph that settles Outcome A against the review — the call asks. Read inside its paragraph (it is the grant-for-the-rest-of-the-task rule) it means only that a grant never covers a collection. So the state is not "the text does not settle which outcome": the text states both, in the same file, and they disagree whenever the matrix's own row would be automatic. That is a sharper finding and it omits the review's Outcome A, which as stated is contradicted.

**Introduced?** Yes for the part that matters: `8b6cb05` added "from the marks of the task and of the items bound to the call", which is what gives a bound item any role in the matrix at all, and added the "always asks" parenthetical in the same commit. `collection-info` is unchanged.

**Second sub-claim.** `core.wit:180-182` "objects of the system zone and of shared packages carry none" against `core.wit:168-170` "`untrusted` is always set for the origins "app:", "web:", "device:" and "foreign"": literally inconsistent, and `security.md:195` repairs it in the next clause — "objects of the system zone and of shared packages carry none. `untrusted` keeps following the writer and the origin" — which `core.wit:180-182` lacks, having only the foreign-media clause. The review's quotation of `security.md:195` prints that as "System zone and shared packages: none. untrusted keeps following the writer and the origin", which is not the page's wording; the meaning is right, the quotation marks are not. Small severity: `storage.md:64` makes clear the objects meant are package blobs, whose origin is not `app:`.

**Its correction.** The added sentence for collections is right, and the reworded `core.wit:180-182` closes the letter of the contradiction. Neither says what `tasks.invoke` should do about `240-241`; my text does, by removing the "always asks" reading and keeping the zone rule.

## 3. Secret fields (`contradiction`, `blocks building`, `unsettled case`)

**Quotes.** Exact: `catalog.wit:98-101` (event carries null for kind `secret`; "the value never reaches the surface owner, only an action through `source.input`"), `catalog.wit:84-86` (a button with an action on an application's own surface is refused, `invalid`), `input.wit:58` and `73-74` (`attach` … "`not-found` if the node is not a `canvas` of `screen`"), `manifest.wit:32-36`, `actions.wit:224-226`, `catalog.wit:106-112`. `catalog.wit:82-84` is quoted as "activating it invokes the action under the same rules as `task.invoke`" — accurate.

**3.1, my reading of the event path.** An application on its own surface emits `node {kind: "field", props: {"label": "Password", "kind": "secret", "value": ""}}` (legal: `catalog.wit:156-157` "An application surface accepts both levels"). The user types. The system sends the owner its events (`ui.wit:78-79`), and for this field the event is `{kind: "changed", node: some(id), value: "null", provenance: {origin: "user", …}}` — `catalog.wit:99-100`: "the event carries null"; `ui.wit:42`: "JSON; "null" when the event has no value". Not the value. The owner cannot put it there either: "`value` is ignored on update" (`catalog.wit:99`). The action path is shut, because `catalog.wit:84-86` (new in `8b6cb05`) refuses every button with an action on that surface, and `text-input.attach` refuses a `field` node (`input.wit:73`). And `input.wit:8` says what should have happened: "The catalogue's own fields (`field`, `search`, `text-editor`) … their owners only see the resulting value" — for a catalogue field the owner sees the value. So on an application's surface two files disagree and one of them delivers nothing: the app gets a field it can never read, and the contract does not refuse it. That is a dead end an honest builder walks into, since `secret` is the obvious kind for a password box, and the only escape (`canvas` + `text-input` with `purpose: "password"`, `input.wit:29-32`, `security.md:89`) costs a drawing loop for a catalogue-only application.

**Introduced?** Yes. The null rule is old, but in `aab7417` a button with an action was allowed on an application's surface ("actions within the task scope"), so `source.input` could carry the value to an action. `8b6cb05` closed that path (`catalog.wit:84-86`) without giving the application surface another one.

**3.2, `tasks.invoke` with a literal for an `os-secret` property.** `manifest.wit:33` says the property is "filled only from a secret field"; `actions.wit:224-226` says an action that receives a secret "is confirmed whatever its class". Nothing states what happens when the agent passes `{"pw": "guess123"}` itself. Of the two outcomes the review names, the second is worse than it says: `manifest.wit:35` requires the confirmation to show the secret masked, so the user would be confirming an action whose exact input (`actions.wit:233-235`: "from the action's typed schema and this exact input") they cannot read. Calling it a contradiction overstates it — "filled only from a secret field" describes a path, not a refusal — but as an unsettled case with a confirmation that cannot be checked, it stands.

**Introduced?** In part. "filled only from a secret field" is `aab7417`'s wording; the mandatory confirmation of `8b6cb05` is what turns the ambiguity into a hazard.

**3.3, the overlay.** The zero-button case is a real hole in the wording: "accepted only if the buttons that read it all invoke actions of one application, which the system names beside the field" (`catalog.wit:107-110`) is true of an empty set, and there is no application to name. The second half is over-claimed. Nothing clears a secret field when the task takes the mark, true, but two rules bound the damage and the review cites neither: `ui.wit:55` checks "every update against the tree it would leave", so the next update is judged with the field present and is refused while the task is marked; and any action that receives a secret is confirmed whatever its class (`manifest.wit:34-36`, `actions.wit:224-226`), with the receiving application named first — so the failure mode is a user typing a password into an agent card and then confirming a named application, not a silent handover. Still worth stating; not a `breaks a guarantee`.

**Introduced?** No. Both the overlay rule and the vacuity are `aab7417`'s; `8b6cb05` only moved the confirmation sentence.

**Its corrections.** 3.1: its first branch (deliver the value to the owning application) is the right one and I would take it; its second (refuse `secret` on application surfaces) also closes the hole and is cheaper, but it silently removes the password purpose from every application-drawn field that is not in a canvas. 3.2: right, buildable, and it breaks nothing an honest agent does — `mcp.md:44` already routes a token through a secret field. 3.3: the "at least one button" clause is right; the clearing clause is unnecessary once the update check and the mandatory confirmation are read together, and I would write the milder version below.

## 4. `exchange.copy`'s gesture (`blocks building`)

**Quotes.** Exact: `store.wit:221-225` (new in this commit), `catalog.wit:96` (`button { label, tone, action }`, no role), `catalog.wit:184-185` (`menu { label }`), `catalog.wit:215` (`canvas`), `ui.wit:39-44` (`event`).

**Replay.** The application handles "activated" on its own button (`catalog.wit:95`, "Without: event "activated"") and calls `exchange.copy`. The system must decide whether a copy or cut gesture of the user on that surface preceded it. The copy key it sees; a menu entry it draws itself; but "a copy button of that surface the user activated" it cannot tell from any field of `button` — the label is publisher text, localized (`ui.md:119` has French in the interface) and optional in form. So the builder either guesses from labels, or treats every activation as a gesture, which lets a hostile application overwrite the clipboard on any click. Both outcomes are in the text, neither is chosen. `ui.md:93` ("semantic and not visual") is the entry criterion the kind does not meet. Nothing in `ui.md` supplies a copy affordance (`grep -i copy architecture/ui.md` gives lines 12 and 37 only), and D-052 does not settle it. Confirmed.

**Introduced?** Yes — the whole clause is new.

**Its correction.** Right, and cheaper than it says: `catalog.wit:5-11` already allows a catalogue to add an `option` field in a minor version, so `role: option<string>` on `button` breaks no ABI. Restricting the gesture to the system's key would break localized and icon-only copy buttons in honest applications; the "once, within one event turn" clause is worth adding because nothing else bounds a repeat.

## 5. Reserved "microphone" and the wake-word target (`contradiction`)

**Quotes.** Exact: `manifest.wit:73-79`, `88`; `manifest.wit:135-138`; `manifest.wit:100-102`; `core.wit:264-267`, `275-276`, `409-417`; `ui.md:135`.

**Replay 1.** `manifest.wit:88` makes "microphone" reserved — "no audio interface for applications", so "the installer refuses a package that asks for it" (`manifest.wit:76-77`). `manifest.wit:136` lists `os:core/wake-word@0.1.0` as a target, and `world wake-word` hands `detect` live samples of the microphone (`core.wit:412-417`). A package asking for the right is refused; a package not asking for it receives the microphone. `ui.md:135` and `security.md:94` both make the microphone a distinct right. Confirmed, and the two readings the review gives are the only two. The new target is what makes it live: in `aab7417` the target list was `service`, `app`, `wasi:http/service`, `wasi:cli/command`.

**Replay 2.** "network" is "served by wasi:sockets/types, wasi:http/client … scope: the hosts", and a host is an HTTPS origin (`manifest.wit:100-102`). In the vendored tree, `contracts/deps/sockets/sockets.wit:253` takes `remote-address: ip-socket-address`, `:676` sends to an `ip-socket-address`, `:828` resolves a bare name to `list<ip-address>`. An origin cannot be enforced on those: two origins share an address. So a non-`["*"]` scope either links sockets to nothing (the review's reading) or cannot be honoured; the text states neither. Confirmed as a gap, but not introduced: `aab7417` already said `"network" wasi:sockets and wasi:http for the long-lived instance; scope: the hosts` — the ambiguity is older, and "served by wasi:sockets/types, wasi:http/client" only names it.

**The carried-forward clause.** "`manifest.wit:80-81` restricts "network" to "the long-lived instance", while `core.wit:264-266` applies those rules to `wasi:http/service` and `wasi:cli/command`, which have no long-lived `service` instance": `core.wit:266` says "with the same linking rules for the network", which is the rule doing the work; a server's only instance is the one that holds the right. I would not report this.

**Its corrections.** Both are buildable. The microphone one has a cost the review does not state: "served by os:core/wake-word `detect`" means the right is granted for a target, not for an import, which is a second kind of right in a record whose doc says a right is "served by the imports it names" (`manifest.wit:74`). Either the doc admits target-served rights, or the right is refused for every target but `wake-word`; the second is smaller and I would write that.

## 6. `"os-item"` inside array `items` (`contradiction`)

**Quotes.** Exact: `manifest.wit:26-31` ("two keywords of DodOS, on a property of type string"), `mcp.md:27`, `mcp.md:30` (quoted with honest `...` elisions), `catalog.wit:76`, `actions.wit:31-36`, `45-47`.

**Replay.** `mcp.md:27` generates, for a tool with no `outputSchema`, `"objects": {"type": "array", "items": {"type": "string", "os-item": {...}}}`. `manifest.wit:26` allows `"os-item"` "on a property of type string"; the `items` subschema is not a property; `manifest.wit:39-41` refuses anything outside the stated subset, and `mcp.md:26` says a schema outside the subset is refused. So the document's own default is a schema its own rule refuses, for every MCP server without an output schema. Confirmed, and it is a two-file contradiction inside one commit.

**Its second and third sub-claims.** `catalog.wit:76` `argument { name: string, value: source }` names a top-level property, so a button cannot fill an array element — right, and it is why any legalisation of `items` must be confined to output schemas, where no `argument` reads it. The third, that `actions.wit:45-47` never says what the system does with an extra, missing or mistyped binding in `outcome.objects` while `actions.wit:33-36` refuses the input side, is right and smaller than the review makes it: "Each needs `share`" limits the damage, but the asymmetry is real.

**Introduced?** Yes — `mcp.md:27`, `mcp.md:30` and `actions.wit:45-47` all changed in this commit.

**Its correction.** Both branches are buildable. I prefer legalising `items` in an *output* schema only (the review's first branch, narrowed): the default exists to carry several images out, and a single top-level property would truncate them, while an input property can never be an array of bindings because `argument` addresses one name.

## 7. `writes: list<bound>` (`blocks building`, `breaks a guarantee`)

**Quotes.** Exact: `actions.wit:144-146`, `157-161`, `170-174`, `260-264`; `store.wit:24-25`, `73-77`, `113-117`.

**Replay 1.** A `reversible, local` action calls `set-meta` only. `store.wit:24-25`: "Every `write`, `write-via-stream` and `resize` that succeeds yields a greater number. Metadata changes do not." The journal records `bound {name, object: some(id), version: some(v)}` at the version it left — the same `v` as before — and `undoable` is true (`actions.wit:170-173`), because the action is reversible, local and its writes are held. `undo` "restores: the version before" (`actions.wit:159-160`), which is the same version; `object.at` opens retained content versions (`store.wit:86-88`), not metadata. So `undo` answers success and the metadata change stays. Confirmed, and worse than "cannot restore": the contract promises the user an undo that does nothing.

**Replay 2.** Two removals of an entry named `draft.txt`, one in `home` and one in a sub-collection: `bound` has no parent, and a removed entry and a collection are both `object: none, version: none` — so the record cannot tell the two removals apart, cannot tell a removal from a collection, and cannot name the object that was removed. Added to what the review says: because a collection has no version at all, `conflict` ("if a later write touched the same objects", `actions.wit:262-263`) can never fire for an entry write, so an undo of a removal can delete an entry that another action re-created in between.

**Introduced?** Yes. `writes` and the "whose writes the journal holds" clause are new in this commit; before, `undoable` was bare and the journal carried no writes.

**Its correction.** Right as far as it goes — the doc's "What `undo` restores" is what makes the record wrong — and it needs the two additions above: metadata changes and collection identity are restored from the system's own log, and `conflict` covers a later metadata write.

## 8. A parent cycle in `update` (`breaks a guarantee`)

**Quotes.** Exact: `ui.wit:55-58`, `agent.wit:307`.

**Replay.** `a` with `parent: none`, `b` with `parent: some("a")`: accepted. Then `a` with `parent: some("b")`: "existing parent" is satisfied, the tree has no root, and `agent.wit:307` ("Nodes in depth-first order") has no start. A builder either loops or drops both nodes silently. Confirmed.

**Introduced?** No. `aab7417` had the same "existing parent" in the same list; `8b6cb05` only reworded the sentence around it.

**Its correction.** Right and minimal; "existing parent with no cycle" also catches `parent: some(itself)`. Buildable by walking to the root from each changed node, bounded by the 1024-node cap.

## 9. `inference.choose` and "when the call started" (`breaks a guarantee`, `contradiction`)

**Quotes.** Exact: `agent.wit:24-26`, `72-73`, `88-91`, `116-119`, `133-137`.

**Replay 1.** `generate` says of `tools`: "The system adds their names, descriptions and schemas from the manifests itself; this marks the task as `available` does" (`agent.wit:88-90`). `choose` says of `candidates`: "ranks `candidates` (actions of the scope …) for the user's `words`, fills each input to its schema" (`agent.wit:133-136`) — same publisher text reaches the model, and no mark. Smaller than the review says: a candidate is "of the scope", and the scope is what the task was handed; but the descriptions and schemas are third-party text read by the model, which is what `generate`'s `tools` sentence already provides for — that sentence is old, and `choose` never got the equivalent. Confirmed as an omission, pre-existing (`choose` gained only the scope sentence in this commit).

**Replay 2.** `agent.wit:24-26` gates a remote model on "Data of a task marked `private`"; `agent.wit:72-73` says the system reads the request's objects, "so reading adds their marks to the task". The review's leak needs the gate to be evaluated before that read. Nothing says it is — the natural implementation reads the context, marks the task, then checks `private-allowed` — so the claimed outcome ("the remote model receives the `private` object despite `private-allowed: false`") is one of two readings, and not the likely one. What is really wrong is narrower: `agent.wit:116-118` records the outcome's provenance as "the task's marks when the call started", which for a first call excludes the marks the request's own objects add during that call, so the parenthetical "(whatever was in the context may have steered the output)" is not guaranteed by the rule it justifies. Verdict: partly right.

**Its corrections.** Sub-1's sentence is right, cheap, and copies the rule `generate` already states for `tools`. Sub-2's rewrite is right too, but it should say it is about the recorded marks, not about a leak of private data.

## 10. `verify` (`blocks building`, `breaks a guarantee`)

**Quotes.** Exact: `verify:23`, `32-34`, `40-41`, `51-57`, `75`, `78`. The new lines (`features()`, the rights block, the feature-string validate) are all `8b6cb05`'s; `75` and `78` are unchanged from `aab7417`. `contracts/README.md:46` is where the promise lives: "that every world encodes as a valid component, validated with only the Component Model features that world uses, as listed in `verify` (a world missing from the list, or a feature WASI has not adopted, fails); that every right `manifest.wit` names is served by an import of a world or marked reserved".

**Reproduced, in `/tmp/wrv-h` (a copy; `head -64 verify > v.sh` runs the three checks that precede the download):**

| Test | Result |
|---|---|
| unmodified `./verify`, macOS 27.2.0 arm64 | **exit 1**: `usage: sha256sum [-bctwz] [files ...]` then `deps: https://…/wasi-wit-0.3.2.tar.gz does not match its sha256`; the three earlier checks pass ("worlds: 6 encoded and validated with their features") |
| `"network"` changed to `served by :` | exit 0, `rights: 2 served by an import` |
| `"accessibility-read"` changed to `served by accessibility:` | exit 0, `3 served`; `import accessibility;` is at `core.wit:396`, inside `world agent` |
| one right line with two spaces, one as `"camera2"` | exit 0; the block parses 6 lines instead of 8; `reserved` drops from 6 to 4 |
| `err: option<error-context>` added to `manifest.wit` | exit 0; line 10 alone (`wasm-tools component wit contracts/`) also exits 0, so the parse accepts the gated type |
| `world extra-world { import foo: func() -> result<_, error-context>; }` appended to `store.wit` | exit 0 |
| `world sneaky  {` (two spaces) appended to `core.wit` | exit 0; the sed at `verify:23` lists the six worlds and not this one |
| the same `error-context` inside `catalog.wit` (imported by `world app`) | exit 0 |
| unwrapped control: `world ec-test { import f: func() -> result<_, error-context>; }` in `core.wit` | validate with `-all,wasm2,component-model,cm-async` → **exit 1**, "`error-context` requires the component model error-context feature"; with `--features=all` → exit 0 |

So all four bypasses and the macOS failure are real. Two corrections to the review's own account of them:

- **Why macOS fails, at the source.** `/sbin/sha256sum` is Darwin 1.0 and takes `[-bctwz]` only; `-c` and `--status` are unknown, so both `sha256sum -c --status` calls fail, the first quietly (`2>/dev/null`), the second loudly, and `verify` exits 1 after downloading. The download itself is fine: `echo "$sum  target/wasi-wit-0.3.2.tar.gz" | shasum -a 256 -c -` prints `OK`. The fallback branch is reached because line 75's failure is indistinguishable from a hash mismatch. CI (`/Users/btw/Documents/repos/dodos/.github/workflows/verify.yml:11`) is `ubuntu-latest`, so the gate is green while a Darwin contributor's tree is red; the flake lists `aarch64-darwin` among its systems but its devShell adds only `wasm-tools curl`, so no GNU `sha256sum` reaches the path.
- **The review's second correction does not close its own fourth bypass.** It proposes wrapping the non-world interfaces "in a temporary test world validated with `--features="-all,wasm2,component-model,cm-async"`". I built exactly that: a probe world in `package os:manifest` importing `format`, embedded with `wasm-tools component embed --dummy . --world os:manifest/probe-format` (the bare name resolves in the root package, `os:core`, and fails). It builds and validates — and still exits 0 with `err: option<error-context>` in `named-blob`, because a type-only interface exports no functions: the dummy component carries no trace of its types (`wasm-tools print` of the probe has zero occurrences of `error-context`). `manifest.wit`, `catalog.wit` and `shell.wit` contain **no** `func(` at all, so no world wrapper can reach their types. The same holds for the binary WIT: `wasm-tools component wit . --wasm` then `validate --features="-all,wasm2,component-model,cm-async"` exits 0 with the gated type present. What does work is a text check on the source.

**Its first correction is not portable.** It proposes `[a-z:/]\+` at `verify:52`. BSD `sed` (macOS) does not implement `\+` in a basic regex — `echo abc | sed 's/\([a-z]\)\+/X/'` prints `abc` — so on Darwin the substitution would never match, the words `served`, `by`, `wasi:sockets/types,` … would be handed to `grep` as import names, and `verify` would fail on the unmodified tree. `[a-z][a-z0-9:/-]*` does the same job with only `*`: it leaves `served by :` unchanged, which makes the loop's `grep` fail, so the bypass closes. Its other two clauses (search the four installable worlds rather than all of `core.wit`; fail when a quoted right line does not parse) are right and buildable — `awk '/^world (service|app|wake-word|input-engine) \{/{f=1} f&&/^\}/{f=0} f'` yields the 12 imports those worlds make, and counting lines that look like right lines with a loose pattern (`8` today) against the parsed count catches both the indentation and the digit cases.

**Its third correction** (`shasum -a 256 -c`) is right and works: `target/…: OK`, exit 0.

---

## What I checked and found correct

- Every quote listed in findings 1–9 and 10 exists at the cited lines of `8b6cb05`, with the exceptions named above (`security.md:195` paraphrased in quotation marks; `actions.wit:109` is a doc line, the field is 110).
- The matrix rows, the "Three rows change" paragraph, the grant paragraph and the journal records as read at `8b6cb05`; `git diff aab7417 8b6cb05` for `core.wit`, `actions.wit`, `catalog.wit`, `store.wit`, `ui.wit`, `input.wit`, `agent.wit`, `manifest.wit`, `mcp.md`, `verify`, `README.md`.
- The six worlds encode and validate under `-all,wasm2,component-model,cm-async` with `wasm-tools 1.263.0`; `error-context` is refused by that feature string and accepted under `--features=all`.
- WASI 0.3.2 on 13 October 2026, 0.3.1 on 11 August 2026 (web, source named above).
- D-036 is decided (`security.md:236`); P-093 and P-094 are *Leaning*, not decided (`pending-decisions.md:978-980`, `994`), so finding 1 is not settled against the reviewer.

## What I did not check

- Anything outside `contracts/`, `verify`, `contracts/README.md` and the cited architecture and decision pages: no kernel contracts, no runtime code (there is none yet), no Rust build against `wasm32-wasip3`.
- `verify` on Linux end to end: I ran only lines 1–64 plus the sha256 lines, not a full `nix develop -c ./verify` on a Linux host, so the three later checks against the tarball are untested as a sequence.
- I did not read the round-1 reviews except where a finding cites them; duplicate findings are judged on their own evidence.
- The review's claims about WASI 0.3.0/0.3.3 dates, the `wasi:http/service` per-request instance and the MCP Streamable HTTP POST rule (`mcp.md:44`) I took from the documents and did not verify at their sources.

---

# The corrections I would apply, in order of severity

### 1. `core.wit:310-312` and `actions.wit:224-230` — an external read of `home` and `keep` in a marked task (`breaks a guarantee`)

`contracts/core.wit`, replacing lines 310-312:

```
/// A limit only where the manifest holds "network" over every host of the
/// action: there, an instance of reach `external` reads its own `home` and
/// the items of its `keep` after the matrix decided and may send them to
/// those hosts, which the long-lived instance can do anyway. A host outside
/// that scope, or any host for a package without the right "network", is
/// out of the long-lived instance's reach: in a task marked `untrusted`,
/// `tasks.invoke` decides such an action as an external modification.
```

`contracts/actions.wit`, replacing lines 224-230:

```
    /// Four rows change (security.md): an action that receives a secret
    /// ("os-secret", manifest.wit) is confirmed whatever its class, the
    /// secret shown masked (point 18); in a task marked `untrusted`, an
    /// action of change `reversible` or `irreversible` and reach `local` of a
    /// package whose manifest holds "network" is decided as an external
    /// modification (see `world service`, point 16); in a task marked
    /// `untrusted`, an action of reach `external` that lists a host outside
    /// the package's "network" scope, or any host if it holds no such right,
    /// is decided as an external modification (see `world service`); in a
    /// task marked `untrusted`, `focus-surface` of os:shell is confirmed
    /// (point 28).
```

### 2. `verify:75, 78` — the command fails on macOS (`blocks building`)

Replace both uses with a helper placed above the deps block:

```
sha256-ok() {
  if sha256sum --help 2>&1 | grep -q -- '--status'; then
    sha256sum -c --status -
  else
    shasum -a 256 -c - >/dev/null
  fi
}
```

then `if ! echo "$sum  $tarball" | sha256-ok; then` and `echo "$sum  $tarball" | sha256-ok || {`.

### 3. `verify:40-64` — the rights check accepts anything (`breaks a guarantee`)

After `>"$tmp/rights"`, before the emptiness test, add:

```
quoted=$(awk '/A right the package asks for/,/record right/' contracts/manifest.wit |
  grep -c '^ *///  *"[^"]*"  *[a-z]')
parsed=$(wc -l <"$tmp/rights" | tr -d ' ')
if [ "$quoted" -ne "$parsed" ]; then
  echo "rights: a right line in contracts/manifest.wit does not parse" >&2
  exit 1
fi
```

and replace lines 52-53 with:

```
      for i in $(echo "$rest" | sed 's/^served by \([a-z][a-z0-9:/-]*\(, [a-z][a-z0-9:/-]*\)*\):.*$/\1/' | tr ',' ' '); do
        if ! awk '/^world (service|app|wake-word|input-engine) \{/{f=1} f&&/^\}/{f=0} f' contracts/core.wit |
             grep -Eq "^ *import $i(@[0-9.]+)?;"; then
```

### 4. `verify:23-36` and a gated-feature scan — un-adopted features outside a world's functions (`breaks a guarantee`)

Replace line 23 with `worlds=$(sed -n 's/^world \([a-z-]*\) *{$/\1/p' contracts/core.wit)`, and add before the world loop:

```
if grep -nE '^ *world [a-z-]+ *\{' contracts/*.wit | grep -v '^contracts/core.wit:'; then
  echo "worlds: a world outside contracts/core.wit is not validated" >&2
  exit 1
fi
```

and after the loop, because no world can carry the types of a type-only package:

```
if grep -nE '\berror-context\b' contracts/*.wit; then
  echo "contracts: error-context is a gated feature, not adopted by WASI 0.3.2" >&2
  exit 1
fi
```

### 5. `catalog.wit:98-101` — a secret field on an application's surface (`blocks building`)

```
    /// Event "changed" with the new value as a JSON string. For kind
    /// `secret` on the agent's overlay, the event carries null and `value` is
    /// ignored on update: the value never reaches the agent, only an action
    /// through `source.input`. On an application's own surface the owner
    /// receives the value as for any other kind, since the system draws that
    /// secret for the application itself (security.md); the system serves a
    /// `secret` field with purpose "password" (input.wit).
```

### 6. `store.wit:221-225` and `catalog.wit:96` — the copy gesture (`blocks building`)

`contracts/catalog.wit`, replacing line 96:

```
    /// `role`: open set, "copy" and "cut" in this version. The shell reads
    /// it, never the label, to know that an activation is the gesture of
    /// `exchange.copy` (store.wit).
    record button { label: string, tone: tone, role: option<string>, action: option<invocation> }
```

`contracts/store.wit`, replacing lines 221-225:

```
  /// Puts items on the clipboard. Each needs `share`. Answered only right
  /// after a copy or cut gesture of the user on the caller's surface, once
  /// per gesture and within one event: the copy key, a menu entry, or a
  /// `button` whose `role` is "copy" or "cut" that the user activated;
  /// `denied` otherwise, and always in an action instance, which has none.
  /// The system pins the
```

### 7. `core.wit:176-182` and `actions.wit:240-241` — a bound collection (`unsettled case`)

Insert after `core.wit:180` ("…still marks its reader."):

```
  /// A collection bound to a call marks it by its zone the same way, though
  /// `collection-info` carries no provenance: binding a `user`, `application`,
  /// `snapshot` or `device` collection marks the call `private`, a `foreign`
  /// one `untrusted`, so `tasks.invoke` decides as for an object of that zone.
```

and, replacing `core.wit:180-182` with:

```
  /// reader. Cache and ephemeral objects keep their writer's marks; objects
  /// of the system zone and of shared packages take no `private` mark,
  /// keeping `untrusted` by writer and origin; foreign media carry
  /// `untrusted` by their origin.
```

`contracts/actions.wit:240-241`, so that the grant paragraph stops reading as a rule of its own: "a call that binds a collection, which has no version, is never covered by the grant and asks when the matrix asks".

### 8. `actions.wit:157-161` — what `undo` restores (`breaks a guarantee` for metadata)

```
    /// What the call created, wrote or removed, as the system saw it in the
    /// instance's own store calls: each object at the version it left, a
    /// removed entry or a collection with version none. A summary for the
    /// user: `undo` restores from the system's own log of the call's store
    /// operations, which is what holds the metadata of a change that left no
    /// version, the object a removed entry had and the collection it belonged
    /// to; `conflict` covers a later change of metadata too.
```

### 9. `manifest.wit:80-83, 88` — the microphone and the socket scope (`contradiction`)

`contracts/manifest.wit:80-83`:

```
    ///   "network"             served by wasi:sockets/types, wasi:http/client:
    ///                         for the long-lived instance; scope: the hosts,
    ///                         or ["*"] for any host; an empty scope is
    ///                         refused; sockets and name lookup are served
    ///                         only by ["*"], a socket address being an
    ///                         address and not an origin
```

and, separately, `contracts/manifest.wit:88`:

```
    ///   "microphone"          served by os:core/wake-word `detect`: the
    ///                         samples of its stream, for the target
    ///                         "os:core/wake-word@0.1.0" only; the installer
    ///                         refuses it for any other target (ui.md)
```

### 10. `manifest.wit:32-36` — a literal for an `os-secret` property (`unsettled case`)

```
//   "os-secret": true
//       filled only from a secret field (os:catalog-agent `field`), which
//       feeds no other property; a call that would set it otherwise answers
//       `invalid` (tasks.invoke); an action that receives one is confirmed
//       whatever its class; shown masked in the confirmation, written as null
//       in the journal, never sent to a model
```

### 11. `catalog.wit:106-110` — the overlay's secret field (`unsettled case`)

```
    /// A secret field on the agent's overlay: refused while the task is
    /// marked `untrusted` (injected text asking for a password in the
    /// agent's own card); otherwise accepted only if at least one button
    /// reads it and every button that reads it invokes actions of one
    /// application, which the system names beside the field. When the task
    /// takes the `untrusted` mark the field and its buttons stop answering:
    /// typing into it gives no value and activating one answers `denied`.
```

### 12. `manifest.wit:26-31` and `actions.wit:45-47` — `"os-item"` in an output array (`contradiction`)

```
// and two keywords of DodOS, on a property of type string; in an output
// schema "os-item" may also sit on the `items` subschema of one array, one
// binding per element, never in an input schema, where a catalogue
// `argument` names a top-level property only:
```

and in `actions.wit`, after "Each needs `share`.": "Each must match the property's `kind` and `content-types`; a binding that no `"os-item"` property names, or a name that no binding carries, is `invalid`, as for `input`."

### 13. `ui.wit:57` — the cycle (`breaks a guarantee`)

In `contracts/ui.wit:57`, replace `existing parent,` with `existing parent with no cycle,`.

### 14. `agent.wit:116-118, 133-137` — the marks of a model call (`wrong fact`)

In `choose`: "Including a third-party action in `candidates` marks the task and `choices.provenance` `untrusted`, as `tools` in `generate` does."

In `outcome`: "the task's marks after the system read `request.messages[*].objects`, which is the marks the context carried (whatever was in it may have steered the output), plus `untrusted` for a remote model (OPEN above)."
