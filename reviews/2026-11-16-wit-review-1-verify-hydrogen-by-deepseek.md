# Verification of the review of DodOS PR 1 WIT contracts (Gemini 4 Hydrogen)

**Report verified:** [2026-11-16-wit-review-1-gemini-hydrogen.md](2026-11-16-wit-review-1-gemini-hydrogen.md), ten findings.
**Object verified against:** `origin/step0-contracts` at `aab7417` of `Vehicoule/DodOS`, read with `git show` (no branch switched), extracted to a scratch copy for the tool runs; the documents at `Docs` (`main`), `decisions/README.md` and `plan/pending-decisions.md`.

I rebuilt every finding from the text, opened the Component Model and WASI sources today (16 November 2026), and reran the tool commands. The reviewer's quotes are in general accurate; the failures are in what the quotes are made to prove.

## What I ran and read

- `wasm-tools 1.263.0` (both `/Users/btw/.nix-profile/bin/wasm-tools` and `nix shell nixpkgs#wasm-tools -c wasm-tools --version`, same version).
- `wasm-tools component wit contracts/` from a `git archive` copy of the PR head: exit 0, output resolving **11 packages** (`os:core`, `os:catalog-agent`, `os:catalog-app`, `os:manifest`, `os:shell`, `wasi:clocks`, `wasi:filesystem`, `wasi:sockets`, `wasi:random`, `wasi:cli`, `wasi:http`).
- The `verify` world loop verbatim (`component embed --dummy` + `component new` + `validate`) for the six worlds `base`, `service`, `app`, `agent`, `wake-word`, `input-engine`: all six encode, and all six validate under **`--features all`**, under `--features=wasm2,component-model,cm-async,cm-map,cm-implements`, under the **default** feature set, and even under `--features=-all,wasm2,component-model,cm-async`. So no world uses `map`, `implements`/`external-id`, or any gated feature today.
- A probe component using `error-context` (a gated feature): `wasm-tools validate --features all` **accepts it**, the default set **rejects it** ("`error-context` requires the component model error-context feature"), and the reviewer's adopted list **rejects it**. This settles finding 9's mechanism empirically.
- Specifications read today: `WebAssembly/component-model` `design/mvp/Concurrency.md` (87 380 bytes), `CanonicalABI.md` (210 282 bytes), `WIT.md` (74 169 bytes), `Explainer.md` (80 395 bytes); `WebAssembly/WASI` `docs/ComponentModelFeatures.md` and `docs/Release.md`; `bytecodealliance/wasm-tools` `crates/wasmparser/src/features.rs`; `modelcontextprotocol` `docs/specification/2026-07-28/basic/transports/streamable-http.mdx`.
- Decisions checked for each finding: D-035, D-053, D-005, and pending P-023 (`plan/pending-decisions.md:497`) and P-046 (`:87`).

---

## Finding 1 — writable `keep` in a fresh action instance

**Verdict: confirmed, with three corrections.**

- *Quote exactness.* `actions.wit:55-57` and `security.md:176` are exact (the reviewer drops the backticks). `core.wit` is cited as `266-267` but the quoted three lines are **`266-268`**: `///   - "/home" is the request's \`home\`, "/tmp" ends with the instance;` / `///     \`keep\`, "/home" and the bound objects are read-only when change is` / `///     none;`. The rule is real: read-only **only** when `change` is `none`.
- *The premise is right.* `keep` is in `world service` (`core.wit:294  import keep;`), the action instance is the same component in another instantiation (`core.wit:253-268`), and the table belongs to the component identity (`store.wit:172-173`). So a `reversible` action instance holds the long-lived instance's whole table, read-write, and `keep.get("docs")` yields a capability `request` never carried. `security.md:177` confirms the linking rule ("storage is read-only when `change` is `none`").
- *Correction 1 — the wrong guarantee is cited.* `store.wit:2-3` is the `store` interface's own comment ("nothing in **this interface** is irreversible"); `keep` is a separate interface (`store.wit:175-189`) and its `put`/`forget` are not versioned. The guarantee actually broken is `actions.wit:159-161`: `/// True for a done action of change \`reversible\` and reach \`local\`, and / /// for a held entry, whose undo cancels the call.` combined with `journal-entry.objects: list<bound>` (`actions.wit:150`), which records only the call's objects — nothing can restore a replaced or forgotten slot. Cite those, plus `security.md:203` ("Local reversible modification | Automatic, can be undone").
- *Correction 2 — a stronger consequence the reviewer missed.* `keep.put` (`store.wit:179-181`) lets an action instance **persist** an item into the long-lived instance's table: a grant the user gave to one action call outlives it and is replayed at the next launch. That is not "an irreversible write to a capability the instance already had"; it is the action adding authority to the application. It also makes the class attenuation unenforceable: `request.objects` is attenuated to the class (`actions.wit:31-33`), and `keep.get` hands back the *same* object with the rights the table held.
- *Not settled by a decision.* D-035 settles the fresh instance, not `keep`. P-023 (`plan/pending-decisions.md:497-505`) covers only the system services' actions (`shell.wit:11-18`) and says explicitly "the fresh instance stays for third-party publishers, whose class it makes binding" (`:505`) — which is exactly the case at issue. So this is the open case the pending decision does **not** cover.
- *The proposed correction.* The first alternative ("return `denied` on every `keep` call inside a fresh action instance") is the right one, for the reason the documents themselves give (P-023: the fresh instance exists to make a third party's class binding; `keep` is the third party's own persistent authority, so its presence voids the mechanism). The second alternative ("read-only `keep`") does **not** fix the finding: `keep.get` still hands the action a capability outside `request`, and the instance can still read `slots`.

## Finding 2 — non-`async` `inference.generate` and `tasks.task.invoke` "release `borrow<task>` before their stream and future finish"

**Verdict: partly right. The quoted Component Model facts are correct; the conclusion drawn from them is not, and none of the four interfaces the review names as ambiguous is in fact ambiguous.**

- *Spec facts, verified.* `Concurrency.md`, section "### Borrows": "a `num_lends` counter on the lent handle is incremented when the subtask starts and decremented **when the caller is notified that the subtask has returned**. If the caller tries to drop a handle while the handle's `num_lends` is greater than zero, the caller traps." And in `CanonicalABI.md`, `Subtask.deliver_resolve` "is called right before the `SUBTASK` resolve event is delivered to wasm … at which point all the borrowed handles are logically returned". So yes: for a call declared `func`, the lend ends when the call returns.
- *Spec facts, verified.* `contains_borrow` is asserted in both `lift_async_value` and `lower_async_value` (`assert(not contains_borrow(t))`), and `contains` descends into `StreamType(u) | FutureType(u)`. So a `stream` or `future` can never carry a `borrow<task>`. Correct.
- *Wrong by implication: `async` does not lengthen a borrow.* For an `async func` the lend also ends when the call resolves — at `task.return` (or cancellation), as the same `deliver_resolve` text says — not when the callee's thread eventually finishes. What `async` buys is the right to keep executing after the resolve; it is not a way to keep a handle lent. So the finding's title ("non-`async` … releases the borrow before their stream finishes") describes every function, `async` or not, and marking these two `async` would change nothing about the borrow.
- *The two functions are host-implemented imports, where `func` is legitimate.* `inference.generate` and `tasks.task.invoke` are implemented by the system, not by a component; the system returns the `(stream, future)` pair without needing a Wasm stack afterwards, exactly as `wasi:sockets` does in the vendored file: `sockets.wit:325  listen: func() -> result<stream<tcp-socket>, error-code>;`. The `async` rule the contracts state for themselves (`actions.wit:60-63`: "a non-async export may not block, and running on after returning would need the Component Model's threads") is about **exports** and does not apply here. That rule is itself correct: `Concurrency.md` says "When a function type does *not* contain `async`, the Component Model traps if the callee blocks at runtime before returning a value".
- *What is genuinely wrong (the reviewer's real finding, better stated).* No sentence in the PR says **when a task ends**. `store.wit:86-88`, `151-152` and `ui.wit:66-67` all say when a stream ends ("Ends when the object is removed or the handle revoked", "Ends when the surface is closed or revoked"), but `tasks.task` says only that `subtask`'s unspent budget "returns to the parent when it ends" (`actions.wit:164-166`) and never says what ends it. So the case is: a task handle dropped while a `generate` stream is still open has two outcomes the text leaves open (budget already returned, or returned later). That is an **unsettled case**, not a broken guarantee, and the fix is one sentence on `tasks.task`, not ownership prose on five interfaces.
- *Over-broad.* `store.object.read-via-stream`, `store.object.changes`, `store.collection.changes` and `ui.surface.events` already state their end condition (`store.wit:86-88`, `store.wit:151-152`, `ui.wit:66-67`), and none of them returns an `own` handle whose destruction ends anything. The "same ownership ambiguity" claim does not hold for them; `input.wit:68-69` is offered as a contrast but is not different in kind.

## Finding 3 — dead rights, missing `target` worlds

**Verdict: 3.1 confirmed, 3.2 confirmed (with a stronger source), 3.3 confirmed, 3.4 partly right.**

- *3.1 confirmed.* `manifest.wit:115-118` limits `target` to four worlds; `accessibility` appears only in `world agent` (`core.wit:359`); `core.wit:241-242` refuses any other import; and the `accessibility` interface has no discovery call (`agent.wit:261-303` defines only the `accessible` resource with `info` and `read`). So an assistive tool has no target world that could import `accessibility`, and no way to be handed an `accessible`. The doc promise is `ui.md:127` ("Reading the tree of another application is a capability, granted by the user to assistive tools") and `agent.wit:251-252` ("assistive tools get it from the user"), which is exact at **251-252**, not 252 (the reviewer's citation is off by one line).
- *3.2 confirmed, and there is a document sentence the reviewer should have quoted.* `ui.md:133`: "**Clients.** Ring buffers in shared memory, no message per buffer. Web Audio for web applications, **a WIT interface for components**." PR 1 has no audio interface for applications at all (`agent.wit` `audio` is speech for the agent: `speak`, `read-aloud`), while `manifest.wit:75-76` grants `"audio-playback"`, `"microphone"`, `"audio-capture"` and `ui.md:134` makes them three distinct capabilities. Same for `ui.md:109` ("Global shortcuts and input injection are capabilities that nobody has by default") against `manifest.wit:78-79`.
- *3.3 confirmed.* `input.wit:53-54` designs for third-party engines (`"app:<engine>"` with `untrusted`), `ui.md:111` for a separate `libhangul` component, `core.wit:370-386` defines `world wake-word` and `world input-engine`, and `manifest.wit:115-118` cannot name either. A package that cannot name its own world cannot be installed.
- *3.4 partly right.* `right` is `record right { name: string, scope: list<string>, why: string }` (`manifest.wit:83`) and only `"network"` has a grammar for `scope` (`:72-73`, `:81-82`). But the harm is small: an over-broad `scope` on a non-network right buys nothing, because no interface exists for those rights (3.2). It is a "say what `scope` means" gap, not a case the contract leaves two outcomes for. Keep it as one clause of the correction, not a scenario.
- *Citation errors.* `manifest.wit:115-119` should be `115-118` (the reviewer uses `115-118` in the scenario itself); `agent.wit:252` should be `251-252`.

## Finding 4 — protocol, port and listening scopes

**Verdict: confirmed, with two corrections.**

- *Quotes exact.* `network.md:21` and `:30` are verbatim. `core.wit:248-250` and `:259-260` are verbatim. `manifest.wit:72-83` is verbatim, including the host grammar ("An HTTPS origin … with a port if not 443"; "`https://*.example.org` also matches every subdomain").
- *Correction 1 — the doc section is Proposed.* `network.md:19`: "**Proposed, 14 November 2026, to validate**, unless marked." So this is not a contradiction with a decided rule; it is a Proposed promise the contract cannot express, which is still a finding (the state, the actor, the two outcomes: either `scope = []` grants every host to a raw socket, or non-HTTPS sockets cannot be granted at all) but a weaker one than "contradiction".
- *Correction 2 — the sharper fact.* `wasi:sockets@0.3.2` **has no `network` resource** (`grep` over the vendored file: only `resource tcp-socket` at `:162` and `resource udp-socket` at `:539`; no `instance-network`, no `network:` parameter). So the "capability carrying its scope" must be enforced entirely by what the linker exposes, and `bind`/`listen` (`sockets.wit:217`, `:325`) are the one place where the manifest's HTTPS-origin grammar can say nothing at all. Say that in the correction: this is why `network.md:30` cannot be carried by `manifest.wit`.
- *`wasi:http/service` and `wasi:cli/command`.* The names are real in 0.3.2 (`http/http.wit:467  world service`, `cli/cli.wit:218  world command`), so `manifest.wit:116-117` targets exist; the tension with "for the long-lived instance" (`manifest.wit:72`) stands as the reviewer states it.
- *`core.wit:272` sub-claim.* "does not state whether `action.hosts` must also satisfy the HTTPS-origin rule" is right: `core.wit:271-273` says "the hosts the manifest lists for that action, over HTTPS", and `manifest.wit:97-100` says the hosts are the action's, with the grammar stated above for the *right*. One cross-reference sentence fixes it.

## Finding 5 — `mcp.md`

**Verdict: 5.1 partly right, 5.2 confirmed, 5.3 confirmed, 5.4 confirmed but it belongs to an OPEN point.**

- *5.1 partly right.* The reading of `mcp.md:27` ("As above") as extending `additionalProperties: false` to output schemas is fair, and `manifest.wit:36-37` scopes that requirement to **input** schemas only, while `manifest.wit:45` allows "a new output property" in an update. But the consequence is a publisher's rule (a v1.1 adapter bumps its schema), not a system guarantee: nothing refuses the tool at run time. File it as a contradiction between two rules of the same document pair, not as "breaks a guarantee".
- *5.2 confirmed.* `mcp.md:30` ("Each written as an object of `home`") against `core.wit:266-268` (`"/home"` is read-only when `change` is `none`) and `actions.wit:35-36` (`home: collection` "attenuated the same way"). A `readOnlyHint: true` tool that returns an image cannot be written. Confirmed as written. (The reviewer's own correction — "a dedicated system-owned return-object store" — is the right shape.)
- *5.3 confirmed.* `actions.wit:42-44` names bindings "by property name of `output`" and the value encoding encodes a resource as "the `name` of a `binding` carried next to the string" (`core.wit:47-48`), so an output binding needs a property; the fallback schema at `mcp.md:27` has exactly one property, `text`, of type string, with no `"os-item"`. Confirmed.
- *5.4 confirmed, but already flagged.* MCP's Streamable HTTP transport: "Every JSON-RPC message sent from the client **MUST** be a new HTTP POST request to the MCP endpoint. 1. The client **MUST** use HTTP POST to send JSON-RPC messages" (specification `2026-07-28`, read today). So a `change: none` remote adapter cannot work under `core.wit:274-275`. But `core.wit:276-282` already opens exactly this ("for reach `external` the class is not binding … The alternative is to confirm every action of reach `external`"), and `security.md:178` states it. So this is a consequence of an **OPEN point already marked** (README:21: "Unsettled points are marked `OPEN:` in the files"), and the smallest correction is one clause under that OPEN point, not a new finding.
- *One more, unnoticed:* `mcp.md:44` says "a token kept between calls lives in `home`, since an action instance keeps nothing else", while `security.md:88` and `188` route secret values "straight to the action" and never to a surface; `home` is the application's own writable storage (`store.wit:35-36`), so the adapter's credential sits in a collection the whole application can read. Say where a stored token lives and who may read it.

## Finding 6 — `text-input` secrets, `canvas`, `applet`, `catalog.wit:145`

**Verdict: 6.1 partly right, 6.2 wrong, 6.3 confirmed, 6.4 confirmed.**

- *6.1 partly right.* The texts the reviewer quotes are exact (`security.md:88`, `input.wit:28-32`, `56`, `70`, `catalog.wit:90-93`). But "the surface owner" in `security.md:88` and `:188` ("A secret field never emits its value to the agent") is the **agent** — the whole page is "Security model of the agent" (`security.md:150-152`), and the field at issue is one the system draws on the agent's overlay. An application's own password field delivering characters to that application is the normal meaning of a password field, not a leak. What is actually unsettled: `input.wit:29-31` gives an application-drawn field the purposes `"password"` and `"pin"` and constrains only the *engine* ("served only by the system's own keyboard engine: no other engine, no dictation, empty surrounding text, nothing learned") and says nothing about who may read `edits`. So: unsettled case, and the reviewer's second suggested correction (say in `security.md:88` that the rule is about fields the system draws for another party) is the right one; the first ("exclude `password`/`pin` from `text-input`") is wrong — it would remove the only way an application's own password field gets a system keyboard.
- *6.2 wrong.* No document promises a `canvas` its size, its scale or a frame callback. `ui.md:12` is the compositor's sentence about **native clients** that hand over buffers ("direct scanout of a full-screen surface … and a frame callback with a deadline, so that a client's content leaves at the same refresh"), and D-007 is the same decision; a Wasm application hands over nothing (that is the OPEN point at `core.wit:320-328` and `catalog.wit:199-201`, which says the GPU-fed canvas "waits for the same thing"). The application chooses the pixel size by choosing the image object it writes (`catalog.wit:188-190`), and the system scales it. A "resize" event is a wish, not a finding.
- *6.3 confirmed.* `catalog.wit:110-116`: "It talks to the surface owner only by event \"message\""; `ui.wit` has `update`, `remove`, `events` and no way to send anything into a node; `agent.md:17` says "Applets are objects of the store, reused and **fed with data** rather than regenerated". One direction exists, the promise needs the other. Confirmed.
- *6.4 confirmed, with a second witness.* `ui.md:89` "Agent level, fifteen kinds", `ui.md:90` "Application level, fifteen more", and `ui.md:44` "that surface accepts only the fifteen agent-level kinds". `catalog.wit:145` ("The document names ten kinds \"and a few more\" without fields") is stale, and its own level defines fifteen (`catalog.wit:213-229`). Confirmed. (The reviewer's count check, 15 for 15 against `ui.md:89-90`, reproduces exactly.)

## Finding 7 — `entity.set`

**Verdict: 7.1 wrong, 7.2 confirmed.**

- *7.1 wrong.* The rule invoked is `agent.wit:2-4`: "Every call that spends or reads on the user's behalf takes the task". `entity.set` neither spends budget nor reads data; it sets a drawn state. The contract's own list of what a call needs the task for does not cover it, so "omits `scope: borrow<task>` … contradicts" does not follow. What does follow, and what the reviewer half-says: nothing says which task a hint belongs to when `handle` is entered again, or what the system does with a hint set outside any task.
- *7.2 confirmed, and it is worse than stated.* `agent.wit:234` ("idle  none of the above, the task done") sits inside the list introduced at `:224-225` ("The states that report a fact the system knows are set by the system alone and always win"), and `:235-236` says the hint is "drawn only while no system state applies". If `idle` counts as a system state, `done` and `failed` can never be drawn; if it does not, the sentence "always win" is contradicted by its own list. Add `:246` ("The last call wins; the hint ends with the task"): the agent reports `done` "at the end" (`:242`) and then returns from `handle` (`core.wit:363`), which ends the task and so ends the hint. The two cases are unreachable in either reading. Confirmed as a contradiction inside one comment block, not merely an unsettled case.

## Finding 8 — `accessibility.read` always `private`

**Verdict: confirmed. The quote is exact at the cited lines and the contradiction is real.**

- `agent.wit:287-288`: "`private` always, since what the user's screen shows is the user's". `security.md:295`: "The agent reads the page through the accessibility tree, which marks the task `untrusted` (origin `web:<origin>`). It reads the file, which adds `private`." `security.md:296`: "If the page is read before any private data, nothing private is yet in the task; the fetch runs and carries nothing private." Under `agent.wit:287-288` that last sentence is dead, because reading the page already added `private`, and by the matrix (`security.md:205`) an external read in a `private` task is confirmed — so the walkthrough's "the fetch runs" is false.
- *A second case of the same contradiction the reviewer did not cite:* `actions.wit:101-103` ("Objects the user handed over with the request … Read-only: the gesture is the grant … Handing adds no mark; reading an object adds its marks") makes `request.screen`'s marks the *surface's* marks (`actions.wit:105-108`), which is `security.md:295`; `agent.wit:287-288` overrides it with `private` always. Both cannot stand.
- *Not settled by a decision.* D-035 settles "two task marks and the confirmation matrix", not what an accessibility read adds.
- *The correction.* The reviewer's is right in shape but must pick: either `agent.wit:287-288` gains the conditional, or `security.md:295-296` is rewritten (and the "not stopped" case becomes stronger, not weaker). Both texts are below in the corrections list.

## Finding 9 — adopted features, `external-id`, `verify --features all`

**Verdict: confirmed on every factual point, with one simplification of the proposed fix.**

- `contracts/README.md:38` is exact: "0.3.1 adopted `map` and `implements`. Nothing else is adopted". `WebAssembly/WASI` `docs/ComponentModelFeatures.md`, read today, refutes "nothing else": the 0.3.1 row is `| 0.3.1 | 🏷️ | \`implements\` and \`external-id\` annotations on plain-named interface imports and exports | 2026-08-06 (#942) |`. `core.wit:26-27` ("async, stream and future; map; implements") omits the same annotation. The practical impact is nil — `wasmparser::features.rs` shows one gate, `cm_implements` ("Support for the `(implements \"...\")` directive"), so `--features cm-implements` covers both — but `README.md:38`'s sentence is wrong as written.
- `verify:18` is exactly `wasm-tools validate --features all "$tmp/$w.wasm"`. My probe shows the looseness concretely: a component whose world imports `error-context` is **accepted** by `--features all` and **rejected** by the adopted set and by the default set ("`error-context` requires the component model error-context feature"). `wasmparser` defaults confirm the gap: `cm_error_context`, `cm_threading`, `cm_gc`, `cm_fixed_length_lists`, `cm_values`, `cm_async_stackful` all default to `false` and are all enabled by `all`. So `verify` cannot enforce the invariant `core.wit:26-28` claims, and `core.wit:27-28`'s "Not `error-context`, not threads: both are still gated" is unchecked.
- *The rerun, as reported.* All six worlds pass `--features all` and the adopted set (`cm-async,cm-map,cm-implements`), as the reviewer says. They also pass the **default** set and `--features=-all,wasm2,component-model,cm-async`, which the reviewer did not report and which means the contracts currently use no gated feature and nothing beyond `cm-async`.
- *One correction to the proposed fix.* Enumerating `wasm2,component-model,cm-async,cm-map,cm-implements` works but pins the core proposals to 2.0, which is stricter than needed for a component coming out of a toolchain; the smallest correct change is to drop `--features all` and use the default set, which in wasm-tools 1.263.0 already is exactly the adopted set. Keep the enumeration only if the point is to freeze the set against future defaults.

## Finding 10 — "what will break a 0.1.0 component"

**Verdict: wrong as a finding (the spec premise is right; the finding is not one).**

- The premise is spec-supported: `WIT.md:1291` — "Note that, at least until subtyping is relaxed in the Component Model, if we had to *add* a new case to `calc-error`, this would be a *breaking change* and require either a new major version or adding a second, distinct `variant` definition used by new functions"; and `WIT.md:1172` on `@since` ("once applied to an item, the item is not modified incompatibly going forward"). So yes, a case, a field or a signature change breaks the ABI.
- But that is the contract's stated design, not a defect: `core.wit:30-32` already says "Adding a case to a variant, enum or flags, or a field to a record, breaks the ABI, and the system serves every published version of os:core." D-005 ("versioned, stable WIT worlds") is a decision on exactly this. "A later change needs `0.2.0`" is therefore what the design says it will do, and does not meet any of the file's five finding shapes.
- Several sub-claims are also inaccurate: `wake-event` and `effect` are **records** (`core.wit:184`, `:157`), not closed enums, and `wake-event.kind` is an open `string` (`core.wit:182-184`); the per-value provenance item is deferred **by a decision** (`security.md:210`, P-046 at `plan/pending-decisions.md:87`: "keep the deferral"), so it is not an unheralded break; and the two "installer will refuse" items (`wasi:clocks/timezone`, the `insecure-seed` value import) are already stated as choices at `core.wit:210-218`, with the upstream note the reviewer cites real (`random/random.wit:23`: "This will likely be changed to a value import").
- Two of its lines are worth keeping as checks: `wasi:clocks@0.3.2` does mark `timezone` `@unstable(feature = clocks-timezone)` (`clocks.wit:106-107`), so `core.wit:210-212` is accurate; and the manifest targets `wasi:http/service`, `wasi:cli/command` do exist in 0.3.2 (`http/http.wit:467`, `cli/cli.wit:218`). Recommend removing finding 10 and moving those two sentences into "checked and found correct".

---

## What the angle should have found and did not

**N1 — A catalogue `button` on an application's own surface has no task to invoke through (`blocks building`, `unsettled case`).**
`catalog.wit:82-87`: "With an action: activating it invokes the action through the task, under the same rules as `task.invoke`; the surface owner then gets \"completed\" … \"failed\"". `ui.wit:54-57` says the system checks "actions within the task scope" on every `update`. But a surface exists outside any task: `world app`'s `show` is called on the long-lived instance (`core.wit:339-342`), and the application's whole interface is catalogue nodes. So the everyday case — a user clicking a button in an application — has no task, no marks, no budget, no journal entry and no confirmation rule. Either `ui.wit` must say that an `invocation` is only accepted on the agent's overlay (and applications use their own IPC), or the contract must define who runs an application's own action when the user clicks it. As written, the central promise of the design ("It acts through the typed actions that each application exports", `agent.md:16`) is only half specified.

**N2 — `undoable` is promised for every done reversible local action, and nothing records what the action wrote (`breaks a guarantee`).**
`actions.wit:159-161` makes `undoable` true for "a done action of change `reversible` and reach `local`"; `security.md:203` says "Automatic, can be undone"; `actions.wit:227-229` says `undo` answers `unsupported` only if the entry is not undoable. But `journal-entry` records `objects: list<bound>` — name, object id and the version the action *received* (`actions.wit:138-140`) — and the input. It records no created object, no version written, no collection entry, and not `home` (`actions.wit:35-36`). So an application's reversible action that creates an object in `home` (the shape `mcp.md:62` proposes for `doc_export`: "Writes a new object; the store keeps versions") yields a journalled entry marked undoable with nothing that names what to restore. The contract needs one of: a `writes: list<bound>` on the journal entry, or `undoable` false unless the writes are on the bound objects.

**N3 — A third-party input engine reads the surrounding text of every focused field, and no right covers it (`breaks a guarantee`).**
`input.wit:21-31`: `field-state.surrounding` is "Text around the cursor, at most 4096 bytes", and `:109-113` hands that state to `engine.activate(home, state, input)`. `ui.md:110` makes an input engine "a component with no network"; `ui.md:111` and `:118` make third-party engines part of the design; `input.wit:52-54` expects their edits to be marked `app:<engine>` and `untrusted`. Nothing limits what the engine *reads*: `input.wit:7-8` routes "the agent's bar" through the same protocol, so the user's request text is in `surrounding` too. D-011 is "one right = one capability = one revocable line", and `manifest.wit:69-79` has no right for this. So text typed into any application, including into the agent's bar, is handed to whichever engine the user last installed, with no grant, no indicator and nothing to revoke. The correction is a right (`"text-input-read"`) or an explicit rule that the engine receives only what the focused field's owner publishes.

**N4 — The contract never says whether the system makes several calls into one instance at a time (`unsettled case`).**
`CanonicalABI.md`: "there can be multiple tasks live in a component instance at a time (even when only synchronous functions are used, due to reentrance)". The contracts depend on the answer in three places: `entity.set` "the hint ends with the task" (`agent.wit:246`), `audio.speak` "A new call for the same task interrupts the previous one" (`agent.wit:211-213`), and `tasks.task.subtask`'s split budget (`actions.wit:164-166`, `247`) — and `world app` explicitly gives one instance several surfaces (`core.wit:339-342`). One sentence on `world agent` and `world service` ("the system makes one call into an instance at a time, except …") settles all three.

**N5 — How a component *finishes* a task is unspecified, so the `keep` hole of finding 1 has a second door (`unsettled case`).**
`store.wit:179-181`: "put … Takes the handle: attenuate first to keep using it". With `keep` reachable from a `reversible` action instance (finding 1), an action can `put` an item it was handed by a request into the component's persistent table, so a capability the agent gave for one call is held by the application at the next launch, after the task ended. Nothing says the system clears, or refuses, table entries made during an action instance. Cover it in the same sentence that closes finding 1.

---

## Corrections, as exact text, in order of severity

**1. `contracts/core.wit`, lines 266-268 — the fresh instance holds only what the request carries; `keep` is denied (fixes finding 1 and N5).**
Replace
```
///   - "/home" is the request's `home`, "/tmp" ends with the instance;
///     `keep`, "/home" and the bound objects are read-only when change is
///     `none`;
```
with
```
///   - "/home" is the request's `home`, "/tmp" ends with the instance;
///     "/home" and the bound objects are read-only when change is `none`;
///   - `keep` answers `denied` to every call (`put`, `get`, `forget`,
///     `slots`): a fresh instance holds only what its request carries, and
///     the table is the long-lived instance's (D-035);
```

**2. `contracts/store.wit`, lines 169-174 — say the same at the interface.**
After `/// Not imported by the agent: nothing survives a task.` add
```
/// Not imported by a fresh action instance either: an action instance's
/// `keep` answers `denied`, so a capability it is handed cannot outlive the
/// call.
```

**3. `Docs/architecture/security.md`, line 296 — resolve finding 8 by rewriting the walkthrough step (the text cannot stand under `agent.wit:287-288`).**
Replace
```
2. **The same page asks for a fetch of `https://evil.example/?d=<secret>`.** An external read in a task marked `private` and `untrusted`. **Stops at** the confirmation (matrix). If the page is read before any private data, nothing private is yet in the task; the fetch runs and carries nothing private.
```
with
```
2. **The same page asks for a fetch of `https://evil.example/?d=<secret>`.** An external read in a task marked `private` and `untrusted`. **Stops at** the confirmation (matrix). Reading any surface's tree marks the task `private` (`contracts/agent.wit`, `accessibility`), so the case where "nothing private is yet in the task" does not arise once the page has been read; it arises only before any read, and then there is no instruction to obey.
```
*If the owners prefer the other side:* leave `security.md:296` and replace `contracts/agent.wit:287-288` with
```
  /// ("app:<component-id>", "web:<origin>", "system"); `untrusted` unless
  /// the owner is the system; `private` when the surface belongs to an
  /// application of the user's zone, never for a web page, whose content is
  /// third-party and not the user's own (security.md, walk-through 2).
```

**4. `contracts/actions.wit`, lines 142-161 — make `undoable` mean something (fixes N2).**
Add to `journal-entry` after `objects: list<bound>,`
```
    /// The objects and collection entries this call created, removed or
    /// wrote, with the version before and after: what `undo` restores. The
    /// system records them from the instance's own store calls.
    writes: list<bound>,
```
and change line 159-161 to
```
    /// True for a done action of change `reversible` and reach `local` whose
    /// writes the journal holds (`writes`), and for a held entry, whose undo
    /// cancels the call.
    undoable: bool,
```

**5. `contracts/catalog.wit`, lines 82-87 — a button outside a task (fixes N1; the alternative is to say it in `contracts/ui.wit:54-57`).**
Add to `catalog.wit` after line 87 (`/// Without: event \"activated\".`):
```
    /// On an application's own surface there is no task: an `invocation` is
    /// refused there (`unsupported`), and the application acts on its own
    /// authority. Only a surface of the agent (`overlay`) carries one.
```

**6. `contracts/input.wit`, lines 21-31 and 109-113 — what an engine may read (fixes N3).**
After line 31 (`/// dictation, empty surrounding text, nothing learned.`) add
```
    /// Only an engine shipped with the system may be given `surrounding`;
    /// for any other engine the field sends the state with `surrounding`
    /// empty, unless the field's owner asked for it in `attach`.
```
and after line 112 (`/// its output.`) add
```
  /// A third-party engine reads no text but what it composes: the field
  /// state it receives carries `surrounding` empty (input.wit, `purpose`),
  /// and the agent's bar is served only by the system's engines.
```

**7. `contracts/agent.wit`, lines 234-247 — `idle` against `done`/`failed`, and the hint's lifetime (fixes finding 7.2).**
Replace lines 234-236 with
```
///   idle       no other state applies and no request is in hand
/// The agent adds only what the system cannot know, as a `hint`, drawn only
/// while no system state applies: it can neither hide a system state nor
/// show one.
```
and replace line 246 with
```
  /// The last call wins; `done` and `failed` stay drawn after `handle`
  /// returns, until the next request of this instance or the overlay closes;
  /// `asking`, `none` end with the task.
```

**8. `contracts/core.wit:345-363` — one call at a time (fixes N4).**
Add after `core.wit:342` (`export show: async func(screen: surface);`), as a comment on `world app`:
```
  /// The system makes one call into an instance at a time: `start`, `resume`,
  /// `show` and `wake` never overlap, and an instance runs no action.
```
and add to `world agent`, before `export handle` (`core.wit:361-363`):
```
  /// One `handle` call per instance at a time: the entity's hint and an
  /// `audio` call "of the task" belong to the one that is running.
```

**9. `contracts/manifest.wit`, lines 75-79 and 115-118 — the rights and worlds the contract defines (fixes finding 3).**
Replace line 115-118 with
```
      /// The world the component targets: "os:core/service@0.1.0",
      /// "os:core/app@0.1.0", "os:core/wake-word@0.1.0",
      /// "os:core/input-engine@0.1.0", "wasi:http/service@0.3.2",
      /// "wasi:cli/command@0.3.2". The installer checks the component's
      /// imports and exports against it.
```
and replace lines 75-79 with
```
    ///   "audio-playback", "microphone", "audio-capture"
    ///                         three distinct rights (ui.md). No WIT
    ///                         interface yet: `OPEN`, refused at 0.1.0
    ///   "accessibility-read"  read other surfaces' trees (assistive tools).
    ///                         `OPEN`: no world imports `accessibility` and
    ///                         no call hands out an `accessible` yet
    ///   "global-shortcuts", "input-injection"
    ///                         held by nobody by default (ui.md). `OPEN`, no
    ///                         interface yet
```
and after line 82 (`/// not 443); "https://*.example.org" also matches every subdomain.`) add
```
    /// `scope` is empty for every right but "network". A listening socket
    /// is not offered in 0.1.0: `wasi:sockets@0.3.2` has no `network`
    /// resource, and a protocol, a port and an incoming scope (network.md,
    /// "Opening a port") do not fit this field.
```

**10. `verify`, line 18 — stop letting gated features through (fixes finding 9).**
Replace
```
  wasm-tools validate --features all "$tmp/$w.wasm"
```
with
```
  # The default feature set of wasm-tools is the set WASI 0.3.2 adopts
  # (cm-async, cm-map, cm-implements); "all" would accept error-context and
  # threads, which core.wit says these files do not use.
  wasm-tools validate --features=wasm2,component-model,cm-async,cm-map,cm-implements "$tmp/$w.wasm"
```

**11. `contracts/README.md`, line 38, and `contracts/core.wit`, lines 26-27 — `external-id` (fixes finding 9's wrong fact).**
`README.md:38`, replace "0.3.1 adopted `map` and `implements`. Nothing else is adopted" with
```
0.3.1 adopted `map`, and the `implements` and `external-id` annotations on
interface names; nothing else is adopted
```
`core.wit:26-27`, replace "(async, stream and future; map; implements)" with "(async, stream and future; map; implements and external-id)".

**12. `contracts/mcp.md`, lines 26-30 and 44 — the four mapping errors (fixes finding 5).**
Line 27, replace
```
| `outputSchema` | `output-schema` | As above. Without one: `{"type": "object", "properties": {"text": {"type": "string"}}} |
```
with
```
| `outputSchema` | `output-schema` | Kept if it fits the subset; no `additionalProperties: false` here, since an update may add an output property (manifest.wit). Without one: `{"type": "object", "properties": {"text": {"type": "string"}, "objects": {"type": "array", "items": {"type": "string", "os-item": {"kind": "object", "rights": ["read"], "content-types": []}}}}}` |
```
Line 30, replace
```
| result image, audio and resource blocks | `outcome.objects` | Each written as an object of `home`, returned as a binding, so the agent passes it on without reading it |
```
with
```
| result image, audio and resource blocks | `outcome.objects` | Each written as an object of `home` when the class allows a write, returned as a binding of a property of `output` that carries `"os-item"`. A tool that returns them cannot be `change none`: cite the system's return store, or declare the action `reversible` |
```
Line 44, add at the end
```
Streamable HTTP sends every request as a `POST` with a body, which an action of change `none` cannot do (core.wit, `world service`): a remote adapter is declared `reversible` or awaits the owners' answer on point 1.
```

**13. `contracts/catalog.wit`, line 145 — the count (fixes finding 6.4).**
Replace
```
/// The document names ten kinds "and a few more" without fields.
```
with
```
/// The document names fifteen kinds at this level (ui.md:90) without fields.
```

**14. `contracts/core.wit`, line 271-273 — cross-reference the host grammar (finding 4).**
Replace
```
///   - reach `external`: wasi:sockets and name lookup fail; wasi:http
///     `client` reaches only the hosts the manifest lists for that action,
///     over HTTPS (the network service holds TLS, D-055, so it sees the host);
```
with
```
///   - reach `external`: wasi:sockets and name lookup fail; wasi:http
///     `client` reaches only the hosts the manifest lists for that action,
///     written with the grammar of `os:manifest` `right` ("https://…", a
///     port if not 443, "https://*.example.org"), over HTTPS (the network
///     service holds TLS, D-055, so it sees the host);
```

**15. `Docs/architecture/security.md`, line 88 — whose memory (fixes finding 6.1).**
Replace
```
| Secrets typed into a secret field (passwords, codes) | Never in the memory of the model or of the surface owner: the system reads the value when the button is activated and hands it to the action |
```
with
```
| Secrets typed into a secret field the system draws for another party (`field` with kind `secret`, and the agent's card) | Never in the memory of the model or of the surface whose interface holds the field: the system reads the value when the button is activated and hands it to the action. A field an application draws itself in a `canvas` gets its characters, as its own password box should |
```

---

## Checked and found correct

- The nine `contracts/*.wit`, `contracts/README.md` and `contracts/mcp.md` at `aab7417` resolve as one set (`wasm-tools component wit`, exit 0, 11 packages).
- The six worlds of `os:core` encode and validate: `base`, `service`, `app`, `agent`, `wake-word`, `input-engine`, under `--features all`, the adopted set, the default set, and `-all,wasm2,component-model,cm-async`.
- `wasi:http/service@0.3.2` (`http/http.wit:467`) and `wasi:cli/command@0.3.2` (`cli/cli.wit:218`) exist, so two of the four `manifest.target` names are right; `@unstable(feature = clocks-timezone)` on `timezone` (`clocks.wit:106-107`) makes `core.wit:210-212` accurate; `random/random.wit:23` does say "This will likely be changed to a value import".
- The WASI release dates in `contracts/README.md:38` reproduce exactly against `WASI/docs/Release.md` (0.3.0 on 2026-06-11, 0.3.2 on 2026-10-13, 0.3.3 on 2026-12-08).
- The 15/15 catalogue count against `ui.md:89-90` (the reviewer's own check): agent level `stack, card, items, text, image, icon, table, progress, divider, button, field, choice, toggle, preview, applet`; application level `virtual-list, row, tree, tree-item, tabs, navigation, page, menu, dialog, text-editor, slider, search, canvas, drag-source, drop-target`.
- `actions.invoke` (`actions.wit:71`), `wake-word.detect` (`core.wit:378`) and `engine.activate` (`input.wit:113`) are `async func` for the reason the commit message gives, and the reason is spec-correct: `Concurrency.md` "When a function type does *not* contain `async`, the Component Model traps if the callee blocks at runtime before returning a value".
- `sockets.wit:145-156` says what the reviewer quotes it as saying ("Send/receive streams remain functional after the original `tcp-socket` handle is dropped … The OS socket is closed only after the last handle is dropped"), and `bind`/`listen` are at `:217` and `:325`.
- `security.md:176`, `:177`, `:203`, `:205`, `:295`, `:296`, `:88`, `:188`; `ui.md:12`, `:16`, `:44`, `:89`, `:90`, `:109`, `:110`, `:127`, `:133`; `network.md:19`, `:21`, `:30`; `agent.md:17`: all read as cited. (`agent.md:27` still says "The world imports `inference`, `memory` and `audio`. These three interfaces are stubs in the contract: nothing is fixed yet", which PR 1 no longer matches; it is in the PR's own list of documents to update, so I do not count it.)

## Not checked

- The `verify` tarball download and its `sha256` against release `v0.3.2` (`verify:31-52`); I did not fetch the 0.3.2 WIT tarball.
- A real component built from Rust 1.100 targeting `wasm32-wasip3` (`core.wit:200-201`, "Checked by hand").
- Wasmtime's component linker semver matching (`core.wit:214-218`): issue `bytecodealliance/wasmtime#7860` and `wit-component`'s semver merging are consistent with the claim, but I did not read the linker code that implements it.
- The MCP schema `2026-07-28` beyond the Streamable HTTP transport page and the `Tool` fields `mcp.md` quotes.
- Whether `dodo package` and the installer can check the JSON Schema subset at `manifest.wit:14-40` (no implementation in either repository).
