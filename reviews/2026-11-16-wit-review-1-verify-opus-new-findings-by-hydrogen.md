# Verification of Opus's new findings (N1–N9) and proposed corrections (C1–C18), by Hydrogen

**Date.** 16 November 2026.
**Judged.** `/Users/btw/Documents/repos/Docs/reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md`: only the nine new findings (N1 to N9) and the eighteen corrections (C1 to C18). Opus's verdicts on DeepSeek's twelve earlier findings are not judged here.
**Against.** The nine WIT contracts of `Vehicoule/DodOS` at `origin/step0-contracts` (commit `aab7417553b4733859685c14f8af7a0c920e2b84`), read via `git show`; `Docs/architecture/security.md`, `agent.md`, `ui.md`, `network.md`, `storage.md`, `memory.md`, `scheduling.md`, `platform.md`, `wasm-abi.md`, `kernel-interface.md`, `decisions/README.md` (D-001 to D-132), and `plan/pending-decisions.md` (P-001 to P-091) in `/Users/btw/Documents/repos/Docs` on `main` (`c93a623d29c190ac506c093e202cc18efb5755f6`).
**Method.** Every quote and line reference in N1–N9 and C1–C18 was checked against the blobs at `aab7417` and `c93a623`. Every attack in N1–N9 was replayed call by call against the WIT rules and comments, and checked against all decisions and pending entries. Each correction C1–C18 was applied to a scratch copy of `contracts/` outside both repositories and tested with `wasm-tools 1.263.0` (`wasm-tools component wit`, plus `component embed --dummy`, `component new`, and `validate --features all` on all six worlds of `core.wit`: `base`, `service`, `app`, `agent`, `wake-word`, `input-engine`), both individually and all eighteen combined. No repository was modified beyond creating this report; nothing was committed.

---

## Verdicts at a glance

### New findings (N1 to N9)

| # | Opus's finding (short) | Quote check | Replay | Covered by D / P? | Verdict |
|---|---|---|---|---|---|
| N1 | Action writes `home`; long-lived instance has `"network"` | Exact | Succeeds | No (`D-035` missed `home`; `P-036` is `external` only) | Confirmed |
| N2 | Secret field feeds plain property -> journal -> agent | Exact | Succeeds (with unmarked-task note) | No | Confirmed |
| N3 | Two contradictory rules for naming a binding | Exact (`actions.wit:42` also affected) | Contradiction holds | No | Confirmed |
| N4 | Input engine can fabricate keys with `forward` | Exact | Succeeds on `canvas` and bar | No | Confirmed |
| N5 | `button.action` invokes "through the task"; app has none | Exact | Unsettled (both outcomes hold) | No (`P-023` is service process only) | Confirmed |
| N6 | `exchange.copy` has no gesture or instance check | Exact | Succeeds (`reversible, local` / long-lived) | No (`D-052` principle unenforced on `copy`) | Confirmed |
| N7 | `surface-info.title` has no setter or cap | Exact | Blocks building | No | Confirmed |
| N8 | Props cap is per call in `core.wit`, per node in `ui.wit` | Exact | Contradiction holds (64 MiB/call) | No | Confirmed |
| N9 | No rule gives store objects the `private` mark | One line error (`296` -> `295`) | Succeeds (when `untrusted` ≠ `accessibility`) | No (`D-035`/`D-036` assume it) | Confirmed |

Counts for N1–N9: 9 confirmed, 0 confirmed with another correction, 0 partly right, 0 wrong.

### Corrections (C1 to C18)

| # | Targets | `wasm-tools` check | Closes target? | Cost / what it breaks | Verdict |
|---|---|---|---|---|---|
| C1 | N2 | Passes (comment) | Leaves 2-step `update` replacement open | Rejects password actions missing `"os-secret"` | Confirmed with another correction |
| C2 | N1 | Passes (comment) | Leaves `undoable`/hold/`budget.external` mismatched | Confirms every `reversible, local` edit in `"network"` apps; reopens `D-035` | Confirmed with another correction |
| C3 | Finding 1 | Passes (comment) | Closes Attacks A & B | Headless services can never persist runtime items in `keep` | Confirmed |
| C4 | Finding 5, N3 | Passes (comment) | Misses `actions.wit:42` and mutable `collection` bindings | Repeats ask again if object version changed | Confirmed with another correction |
| C5 | N4 | Passes (comment) | Lets engine hoard & replay old consumed keys | Breaks no valid engine | Confirmed with another correction |
| C6 | N6 | Passes (comment) | Closes N6 and silent clipboard replacement | Breaks in-app `"Copy"` buttons unless counted as gesture | Confirmed |
| C7 | Finding 4 | Passes (comment) | Still allows silent focus theft after 1.1 s pause | Breaks fast typed `"focus ..."` commands from the agent's bar | Partly right |
| C8 | Finding 6 | Passes (comment) | Closes streaming `progress` note leak | Marks task `untrusted` as soon as any `progress` is read | Confirmed |
| C9 | N5 | Passes (comment) | Introduces cross-app silent theft/mutation; drops `source.input` marks | Arbitrary cross-app `button.action` bypasses isolation | Wrong |
| C10 | Finding 3 | Passes (comment) | Undo of `remember(replaces: ...)` fails to restore old entry | None | Confirmed with another correction |
| C11 | Finding 8 | Passes (comment) | Closes `os-item` & `os-secret` update gaps | Cannot add `"os-secret"` in-place to an existing action | Confirmed |
| C12 | Finding 12, N8 | Passes (comment) | Closes N8; `world app` has no memory budget (`D-073`) | Batched updates needed above 64 KiB props | Confirmed with another correction |
| C13 | N7 | Passes (ABI + comment) | Wrong line (`agent.wit:294`); >~115 surfaces still overflow `list-surfaces` | Minor: new method on `surface` (pre-freeze) | Confirmed with another correction |
| C14 | Finding 7 | Passes (comment) | Closes `invoke`, `subtask`, `tools`, `choose` | Fails fast if agent keeps stale out-of-scope ref | Confirmed |
| C15 | Finding 2 | Passes (comment) | Clarifies per-task `undo` & `journal` | Dropping child `task` to return budget loses child `undo`/`journal` | Confirmed |
| C16 | Finding 9 | Passes (comment) | Closes accidental empty `"network"` scope | Draft manifests using `scope: []` refused | Confirmed |
| C17 | Finding 10 | Passes (comment) | Closes unchosen third-party activation | May block ad-hoc IME switch or `language: ""` fields; selected-language read/keep stays | Confirmed |
| C18 | N9 | Passes (comment) | Omits 5 of 9 zones (`Device`, `Cache`, `Ephemeral`, `Foreign`, `Snapshots`) | Combined with `P-042`/`P-037`, confirms routine `none, external` fetches and blocks `private-allowed: false` remote models | Confirmed with another correction |

Counts for C1–C18: 8 confirmed, 8 confirmed with another correction, 1 partly right, 1 wrong.

---

## Verification of new findings (N1 to N9)

### N1. A local action passes the user's data to the long-lived instance, which has the network
- **Quotes.** All exact at their cited lines:
  - `security.md:177`: `"For an action of reach \`local\`, the declared class is therefore binding, and lying about it gains nothing."`
  - `security.md:297`: `"3. **An application declares an upload as \`none\`, \`local\`.** The instance is linked with every network import answering \`denied\`. **Stops at** linking: the upload fails."`
  - `core.wit:266`: `///   - "/home" is the request's \`home\`, "/tmp" ends with the instance;`
  - `actions.wit:35-36`: `/// The component's own collection, attenuated the same way.` / `home: collection,`
  - `core.wit:256`: `///   - wasi:filesystem preopens: "/home" is \`home\`, "/tmp" a collection of the`
  - `core.wit:259-260`: `///   - wasi:sockets and wasi:http: only with the manifest right "network",` / `///     to the hosts it lists.`
  - `actions.wit:198`: `reversible    local     runs, undoable         runs, undoable`
  - `kernel-interface.md:1097-1098`: `"A process that receives a marked message takes the marks, and keeps them until it is restarted. Everything it sends is marked."` / `"a record written by a marked call is read back marked, through the added marks of its answer."`
- **Attack replay.**
  1. Publisher ships `pub/x` with manifest right `"network"` (even scoped to a single update host) and declares `import` as `change: reversible, reach: local` (`manifest.wit:72, 96`).
  2. A steered task invokes `pub/x.import` with `<user's file>` in `request.objects`. Because the action is `reversible, local`, `tasks.invoke` runs it automatically with no confirmation (`actions.wit:198`).
  3. In the fresh action instance, `request.objects` and `request.home` (plus preopened `/home`) are attenuated to `reversible` (`actions.wit:32-36`), so `/home` is writable. The instance reads `<user's file>` and writes its bytes into `/home` (or via `request.home`).
  4. The long-lived instance (`core.wit:255-260`) watches `/home` (via `collection.changes()`, `store.wit:152`, or `query`/`open`), reads the written object, and sends its bytes via `wasi:http` or `wasi:sockets` (`core.wit:259-260`). Reading that record marks the long-lived instance's process in the kernel (`kernel-interface.md:1098`), but neither `core.wit:259-260`, `network.md:17-33`, nor `kernel-interface.md:1098` directs the network service to refuse outbound traffic from a marked long-lived component.
  The replay succeeds at every step and breaks `security.md:177` as well as Walk-through 3 (`security.md:297`).
- **Covered by D or P?** No. `D-035` assumed reach `local` is binding via fresh-instance linking and did not account for shared writable `home`. `P-036` (`security.md:316`) covers only `change: none, reach: external`.
- **Verdict.** **Confirmed.**

### N2. A secret field can feed a property that is not secret, reaching the journal and the agent
- **Quotes.** All exact at their cited lines:
  - `agent.wit:21-22`: `/// Never: a capability or handle; the value of a secret field (it never` / `/// reaches the agent);`
  - `catalog.wit:92-93`: `/// the value never reaches the surface owner, only an action through` / ``/// `source.input`.``
  - `manifest.wit:32-33`: `//   "os-secret": true` / `//       filled only from a secret field (os:catalog-agent \`field\`);`
  - `actions.wit:148`: `/// Secret properties ("os-secret", manifest.wit) are written as null.`
  - `actions.wit:231-233`: `journal: async func(after: option<u64>, limit: u32) -> result<list<journal-entry>, error>;`
  - `catalog.wit:94-98`: refuses secret field while task is `untrusted`, otherwise requires buttons reading it to invoke actions of one application.
  - `security.md:104`: `"Hostile model or model provider | Everything injected content can do, on every task, from the first token, with no mark set."`
- **Attack replay.**
  1. In an unmarked task with a hostile local model (`security.md:104`), the agent draws an overlay `field` of kind `secret` and a `button` invoking `pub/notes.add` with `{"name": "text", "value": {"input": "pw"}}`, where `text` is a plain string property without `"os-secret": true`. *(Precision on replay: to keep the task unmarked before `overlay.update`, the hostile model or untrusted agent component must name `pub/notes.add` without first calling `tasks.available` or putting `pub/notes.add` in `inference.request.tools`, since reading third-party action metadata marks the task `untrusted` under `actions.wit:188` and `agent.wit:89-90`; a hostile local model can know an installed action's name or target a system action directly, and `surface.update` does not mark the task.)*
  2. `overlay.update` succeeds (`catalog.wit:94-98`): task is unmarked and only one application (`pub/notes`) is named beside the field.
  3. The user sees `pub/notes` named beside the field, types the password, and clicks the button.
  4. `pub/notes.add` (`reversible, local`) runs automatically (`actions.wit:198`). Because `text` has no `"os-secret": true`, `actions.wit:148` writes the plaintext password into `journal-entry.input`. The agent calls `task.journal` (`actions.wit:231-233`) and reads the password in clear, breaking `agent.wit:21-22` and `security.md:88`.
  5. *(Step 5 in Opus)* An external `none, external` read carrying that password in its URL also runs without confirmation unless the task has been marked both `untrusted` and `private` (`actions.wit:200-202`), which under N9 does not happen on `journal` or third-party app writes.
- **Covered by D or P?** No. `security.md` line 372 (list against `8bc6509`) asked to block secret fields in marked tasks and name the receiving app, which `catalog.wit:94-99` implemented, leaving the target property unchecked.
- **Verdict.** **Confirmed.**

### N3. Two rules for naming a binding
- **Quotes.** All exact at their cited lines:
  - `actions.wit:31-32`: `/// Storage arguments, by argument name: the property \`name\` of \`input\`` / `/// is this item.`
  - `core.wit:47-48`: `//   resource        never encoded: the field holds the \`name\` of a \`binding\`` / `//                   carried next to the string`
  - `manifest.wit:29-30`: `//       the value is the name of a binding carried next to the JSON (core.wit` / `//       value encoding);`
  - `actions.wit:205-206`: `/// The confirmation is drawn by the system from the action's typed` / `/// schema and this exact input,`
  - *(Note: `actions.wit:42` has the same wording as line 31-32 for outputs: `"Typed object results, by property name of output."`)*
- **Replay.** Under `actions.wit:31-32`, an input `{"f": null}` paired with `binding{name: "f", item: X}` binds `X` to property `f` (matching DeepSeek's original Finding 5 scenario, and violating `"type": "string"` in `manifest.wit:26`). Under `core.wit:47-48` and `manifest.wit:29-30`, the JSON must be `{"f": "b0"}` paired with `binding{name: "b0", item: X}` (`store.wit:163-165` agrees with `core.wit`). Both cannot hold simultaneously, and they change which call payloads pass schema checks and how `"allow for the rest of this task"` keys repeats.
- **Covered by D or P?** No.
- **Verdict.** **Confirmed.**

### N4. An input engine can make up keys
- **Quotes.** All exact at their cited lines:
  - `input.wit:103-104`: `/// Give a key back: the field receives it as if no engine were active.` / `forward(key-event),`
  - `ui.md:109`: `"Global shortcuts and input injection are capabilities that nobody has by default."`
  - `catalog.wit:194-196`: `///   "key"      {"key", "code", "down", "repeat", "modifiers"}, named as` / `///              in input.wit, only while the node has the focus and no` / `///              input engine consumed the key`
  - `ui.wit:45-46`: `/// Who the value comes from: "user" for what the user typed, dictated or` / `/// chose,`
- **Attack replay.**
  1. A third-party engine (`world input-engine`, `core.wit:381-386`) is active (`input.wit:113`) on a `canvas` text field or the agent's bar (`input.wit:7`). Notice `input.wit:52-55` explicitly stamps `edit-event` from a third-party engine with `app:<engine>` and `untrusted` (`"which can type anything"`), yet places no restriction or provenance tag on `forward(key-event)`.
  2. On a `canvas`, the engine outputs `engine-output::forward` with `"Enter"`, `"Control+A"`, or `"Delete"` that the user never pressed. By `input.wit:103-104`, the field receives it `"as if no engine were active"` (`catalog.wit:194-196`), where key events have provenance `"user"` (`ui.wit:45-46`), triggering deletion or form submission.
  3. On the agent's bar, the engine outputs `edit` committing a malicious request string (`app:<engine>`, `untrusted`) and then `forward` with `"Enter"`, submitting a new agent task the user never initiated; automatic cells (`actions.wit:197-198, 200`) then run.
- **Covered by D or P?** No.
- **Verdict.** **Confirmed.**

### N5. A button on an application's surface invokes "through the task", and an application has no task
- **Quotes.** All exact at their cited lines:
  - `catalog.wit:82-83`: `/// With an action: activating it invokes the action through the task,` / `/// under the same rules as \`task.invoke\`;`
  - `ui.wit:56`: `actions within the task scope,`
  - `catalog.wit:18`: `/// Agent level: what the agent may emit, and the base of every application.`
  - `core.wit:329-343`: `world app` includes `service`, `exchange`, `text-input`, both catalogues, and `export show: async func(screen: surface);`; no `task` handle or import exists there.
- **Unsettled state and outcomes.** State: an application (`world app`) emits a `button` with `action: some(...)` (`catalog.wit:80, 88`) on its own surface (`show`). Actor: the user clicks the button.
  - Outcome (a): `ui.wit:56` (`actions within the task scope`) finds no task on an application surface, so `surface.update` refuses every button with an `action` (blocking action buttons in apps even though `button` is part of `os:catalog-agent`, `"the base of every application"`, `catalog.wit:18`).
  - Outcome (b): `surface.update` accepts the button without a task, and clicking it runs the action with no scope, no marks, no journal, and no matrix confirmation.
- **Covered by D or P?** No. `P-023` settles only where system service actions execute (`shell.wit:11-18`), not `button.action` on application surfaces.
- **Verdict.** **Confirmed.**

### N6. An action instance can write the clipboard
- **Quotes.** All exact at their cited lines:
  - `store.wit:215`: `/// Puts items on the clipboard. Each needs \`share\`.`
  - `store.wit:212`: ``/// user closes it, `denied` if the caller has no visible surface.``
  - `store.wit:225-226`: `/// Answered only right after a paste gesture of the user on the` / ``/// caller's surface; `denied` otherwise.``
  - `core.wit:332`: `import exchange;` (inside `world app`)
  - `core.wit:262-275`: lists linking rules for the fresh action instance (`/home`, `/tmp`, `keep`, `background`, network) and says nothing about `exchange`.
- **Attack replay.**
  1. An `app` component (`world app`) declares an action `edit-home` of class `reversible, local` (or `none, local`, depending on whether `"read-only"` at `core.wit:267-268` strips `share` as well as `write`—`core.wit` does not say).
  2. A task invokes it; it runs automatically without confirmation (`actions.wit:197-198`). Because `core.wit:262-275` imposes no rule on `exchange` and `exchange` is not a manifest right (`core.wit:243-246`, `manifest.wit:69-79`), `exchange.copy` succeeds.
  3. The action instance opens an object from `home` (with `share`) and calls `exchange.copy([item])`. Likewise, a long-lived `world app` instance can call `exchange.copy` in the background with no copy/cut gesture on its surface (`store.wit:215`).
  4. The user's clipboard is overwritten silently (an irreversible clipboard replacement even under `local` / `reversible`, or without user intent), and the user's next paste delivers the app's object.
- **Covered by D or P?** No. `D-052` (`ui.md:34`) states `"The user's gesture is the grant"`, which `store.wit:215-222` failed to enforce on `copy`.
- **Verdict.** **Confirmed.**

### N7. A surface's title has no source
- **Quotes.** Exact:
  - `shell.wit:34` (`/// The owner's text.` above `title: string,` on line 35).
  - `agent.wit:289` (`record surface-info { title: string, provenance: provenance }`) and `agent.wit:294` (`/// The title is the owner's text: reading it marks as \`read\` does.`).
  - `ui.wit:52-68`: `resource surface` has only `update`, `remove`, and `events`. `manifest.wit` defines only package/action titles.
- **Check.** Nothing in the contracts lets a component set or update a surface's title, nor caps its byte length. Blocks building the shell/compositor and `accessibility` projections.
- **Covered by D or P?** No.
- **Verdict.** **Confirmed.**

### N8. The props cap is per node in `ui.wit` and per call in `core.wit`
- **Quotes.** Exact:
  - `core.wit:54-57`: `"The numbers bound one copy by value (rule 6: one Wasm page) or one page of results ... bytes by value in one call (object read, action input and output, node props, one inference message) 65536"`.
  - `ui.wit:29-30`: `/// JSON object: the payload record of that case. "{}" when the case has` / `/// no payload. At most 65536 bytes.` (inside `record node`, `props: string`).
  - `ui.wit:53-54`: `/// At most / 1024 nodes per call.`
- **Replay.** Contradiction holds: 1024 nodes × 65536 bytes = 64 MiB of `props` in one `update` call, directly violating `"bytes by value in one call ... 65536"` and `"one Wasm page"`.
- **Covered by D or P?** No.
- **Verdict.** **Confirmed.**

### N9. No rule says which store objects carry `private`
- **Quotes.** Mostly exact, **with one wrong line citation**:
  - `actions.wit:200-202`: `none | external | runs | runs unless marked private, then confirmation`. Exact paraphrase.
  - `security.md:224`: `"the marks are Meta's [A] and [B]"`. Exact.
  - `store.wit:42-43`: `/// Stamped by the system at each write: who wrote, under which marks.` / `provenance: provenance,`. Exact.
  - `kernel-interface.md:1098`: `"a record written by a marked call is read back marked"`. Exact.
  - `agent.wit:163-164`: ``plus `private` (the memory is the user's data)``. Exact.
  - `agent.wit:287-288`: `` `private` always, since what the user's screen shows is the user's.`` Exact.
  - **Wrong citation at Opus line 279:** Opus writes `Walk-through 2 ("It reads the file, which adds private", security.md:296)`. The quoted words `"It reads the file, which adds \`private\`."` are in **Walk-through 1 at `security.md:295`**, not Walk-through 2 (`security.md:296`, which checks a page fetch before and after reading private data).
- **Attack replay.**
  1. An editor's long-lived instance (`world app`) writes the user's tax document to the `user` zone, or `pub/passwords` writes a vault to `home` (`application` zone). Because long-lived instances run outside any task, writes occur under empty marks (`store.wit:42`, `kernel-interface.md:1098`). No rule in `store.wit` or `storage.md` adds `private` to objects in those zones.
  2. A task becomes `untrusted` without touching `accessibility` (for example, by calling `tasks.available` under `P-042`, using a remote model under `P-037`, reading a `foreign` file, or reading a third-party action output; *note that reading `accessibility` as in Opus's Walk-through 1/2 reference would itself set `private` via `agent.wit:287-288`*).
  3. The task reads the user's tax file or receives an action output computed from the password vault in `home`. Since the stored object has empty marks (`actions.wit:182-183`), `private` is not set.
  4. The steered task calls `none, external` (e.g., an HTTP `GET` carrying the secret in the URL). Under `actions.wit:200-202`, because `private` is unset, the call runs automatically with no confirmation. The `private-allowed` check on remote `inference` (`agent.wit:24-26`) is similarly bypassed.
- **Covered by D or P?** No. `D-035` and `D-036` presuppose the `private` mark, and `security.md:295` assumes files carry it, with no rule defining which store objects carry `private`.
- **Verdict.** **Confirmed.**

---

## Verification of corrections (C1 to C18)

### C1 (N2)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `catalog.wit` after line 93).
- **Closes N2?** Mostly, **but leaves a multi-step `surface.update` bypass**. C1 says `"an update whose button reads a secret field into any other property is refused (invalid)"`. Because `ui.surface.update` inserts or replaces individual nodes by id (`ui.wit:53`), a hostile model or agent can: (1) emit `field` `"f"` with `kind: line` and `button` `"b"` reading `source.input("f")` into a non-secret property (accepted, since `"f"` is `line`), and (2) send a second `update` replacing only node `"f"` with `kind: secret`. If the validator checks only buttons present in the current `update` batch, step 2 passes. Also, `catalog.wit:70-72` applies to all surfaces (`os:catalog-agent`), whereas `"an update whose button..."` could be read narrowly if `"resulting tree"` is not stated.
- **Breaks / cost.** Any action whose password/token input property omitted `"os-secret": true` in its manifest cannot be wired to a `secret` field (intended).
- **Verdict.** **Confirmed with another correction.**
- **Correction.** In `catalog.wit` after line 93, say `"the resulting tree"` rather than `"an update whose button"`:
  ```wit
    /// A secret field feeds only an argument whose property carries
    /// "os-secret" (os:manifest): an update that would leave a button reading
    /// a secret field into any other property is refused (`invalid`).
  ```

### C2 (N1)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `core.wit` after line 270).
- **Closes N1?** Stops silent exfiltration from a `reversible`/`irreversible, local` action through `home` into a `"network"` long-lived instance by forcing confirmation at `tasks.invoke`. However, it leaves an internal contradiction in `actions.wit`:
  - C2 reclassifies the action *only* `"for the confirmation table (tasks.invoke)"`. Under `actions.wit:159-161`, `journal-entry.undoable` is `"True for a done action of change reversible and reach local, and for a held entry"`, and `actions.wit:213-215` puts the 10-second hold only on `"an external modification"`. If the action remains `reach: local` outside the confirmation table, it runs immediately with no hold, writes to `home`, the long-lived instance sees `home.changes()` (`store.wit:152`) and uploads the data over the network in milliseconds—while the UI still marks the entry `undoable: true`, falsely promising that Undo reverts what left! Conversely, `budget.external` (`actions.wit:174`) and `action-info.effect` (`actions.wit:118`) stay ambiguous.
  - Also, C2 does not cover a pre-existing `home` collection written *before* a package update adds `"network"` (where the user consents to `"network"` at update under `D-056`, though `home` data already exists).
- **Breaks / confirmation cost.** Reopens `security.md:177` (based on `D-035`: `"For an action of reach local, the declared class is therefore binding"`) and breaks `security.md:203` (`"Local reversible modification: Automatic, can be undone"`).
  In daily use, **C2 adds a user confirmation to every common `reversible, local` action in every application whose manifest holds `"network"`** (even if `"network"` is only for checking updates, and even in unmarked tasks): saving or editing a note in a syncing notes app, adding a calendar event, creating/checking a task in a todo app, saving a mail draft, bookmarking/marking read in a feed reader, or an MCP adapter persisting an artifact/token in `home` (`mcp.md:30, 44`). Because `"allow for the rest of this task"` requires the exact same `input` and `objects` (`actions.wit:211-213` + C4), acting on five distinct items (e.g., checking five todo items or editing two notes) prompts five times.
- **Alternatives to C2.** (Evaluated in detail alongside C18 in the dedicated section below.)
- **Verdict.** **Confirmed with another correction.** If C2's approach is chosen by the owners, it must treat `reversible`/`irreversible, local` actions in a `"network"` package as `external` across `tasks.invoke` and `journal-entry` as a whole (hold before running, `undoable` during the hold only, counted in `budget.external`), not just in the confirmation table:
  ```wit
  ///   - in a package whose manifest holds the right "network", an action of
  ///     change `reversible` or `irreversible` is treated by `tasks.invoke`
  ///     and `journal-entry` as reach `external` (confirmed, held before
  ///     calling, not undoable once done, counted against `budget.external`):
  ///     what it writes into `home` reaches the long-lived instance, which
  ///     has the network;
  ```

### C3 (Finding 1)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `core.wit:266-268`, `store.wit:170-171`, `actions.wit:56-57`).
- **Closes Finding 1?** Yes: denies `put` and `forget` in all classes (closing Attack B) and states that `get` attenuates the returned handle when `change` is `none` (closing the stronger Attack A). Note a minor clarification: `"read-only when change is none"` should be understood to strip `share` as well as `write` (or keep `{read}` only, `core.wit:148`), so a `none` action cannot bounce a previously kept item out through `outcome.objects` (`actions.wit:42-43`).
- **Breaks / cost.** An action instance can no longer save a newly passed `request.objects` handle into `keep`, or clean up an old `keep` slot. In particular, headless `world service` components (which have no `ui.surface` and therefore cannot use `exchange.pick` or `drop-target`) lose the ability to persist any runtime-received object capability across invocations—which matches `D-035`'s fresh-instance design.
- **Verdict.** **Confirmed.**

### C4 (Finding 5 and N3)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `actions.wit:31-33, 211-213`, `store.wit:28-30`).
- **Closes Finding 5 and N3?** Mostly, **with three remaining gaps**:
  1. **Misses `actions.wit:42`:** `outcome.objects` at `actions.wit:42` still reads `"Typed object results, by property name of output. Each needs share."`, leaving N3 unclosed for outputs.
  2. **Imprecise `"no property names"` in `actions.wit:31-33`:** `"a binding that no property names"` should read `"a binding that no 'os-item' property names"` so a binding cannot be matched by an ordinary string field whose literal text happens to match the binding name.
  3. **Mutable `collection` bindings bypass version pinning (`actions.wit:211-213`):** C4 keys `"allow for the rest of this task"` on `"the same object at the same version, the same collection"`. Unlike objects, collections have no `version` (`actions.wit:139`: `version: none for a collection`). A task (or app) can add private objects into a bound `collection` after the first confirmed call, and a repeat call with `"the same collection"` will then run without re-confirming!
- **Breaks / cost.** A repeat call in an unmarked task asks for confirmation again whenever a bound object has been modified (new version) or replaced (intended).
- **Verdict.** **Confirmed with another correction.**
- **Correction.** Apply C4, plus:
  1. In `actions.wit:31-33` change `"no property names"` to `"no \"os-item\" property names"`.
  2. In `actions.wit:42` replace `"by property name of `output`"` with `"named by an \"os-item\" property of `output` (core.wit, value encoding)"`.
  3. In `actions.wit:211-213` replace `"the same collection"` with `"not a collection, which is mutable and has no version (a call binding a collection always confirms)"`.

### C5 (N4)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `input.wit:103-104`).
- **Closes N4?** **Partially; allows hoarding consumed keys.** C5 allows `forward` for `"only a key this activation received and has not yet given back"`. During one focus activation on a field, a third-party engine receives every keystroke (`input.wit:93-94`). When the user presses `"Enter"` (to accept an IME candidate) or `"Delete"` or `"Control+A"` for editing, the engine *consumes* those keys (emitting `edit` rather than `forward`). Because it has not yet given those consumed keys back, C5 lets the engine hoard `"Enter"`, `"Delete"`, or `"Control+A"` and `forward` them minutes later after committing injected text—still triggering `"Enter"` submission on the agent's bar or shortcut actions on a `canvas`! Also, C5 ends the activation on an invalid `forward`, without stating that the system's own engine immediately takes over the still-focused field.
- **Breaks / cost.** Breaks no legitimate `input-engine`: `input.wit:77-79` already forbids engines from drawing UI (virtual keyboards and emoji pickers are system components or send `edit`, never fabricated `key-event`s).
- **Verdict.** **Confirmed with another correction.**
- **Correction.** In `input.wit:103-104`:
  ```wit
    /// Give a key back: only the current key event, before the engine emits
    /// any `edit` or `candidates` for it or receives the next key; the field
    /// receives it as if no engine were active. Any other `forward` ends the
    /// activation and falls back to the system's own engine: an engine cannot
    /// make up or replay a key.
  ```

### C6 (N6)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `store.wit:215`).
- **Closes N6?** Yes. Requiring a user copy or cut gesture on the caller's surface aligns `copy` with `paste` (`store.wit:225-226`) and denies `copy` in all action instances and unprompted long-lived instances.
- **Breaks / cost.** Breaks programmatic `"Copy"` buttons inside an application (for example, a `"Copy code"` `button` on a surface or inside a `canvas`), unless clicking an in-app copy control counts as a copy gesture or the system provides a copy action/control—otherwise the user must press the OS copy shortcut (`Ctrl+C`) or menu.
- **Verdict.** **Confirmed.**

### C7 (Finding 4, focus part)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `shell.wit` after line 61).
- **Closes Finding 4 (focus)?** Closes stealing focus to the agent's bar (`denied`) and mid-typing-burst focus theft (`busy` within 1 s, plus 500 ms dropped keys). **However, it breaks a common legitimate request and leaves delayed silent focus-stealing open:**
  1. **Breaks typed user commands to focus a window:** When the user types `"focus terminal"` in the agent's bar and presses `Enter`, the system calls `handle`, the agent invokes `shell.focus-surface` within milliseconds—well inside `"a key in the last second"` (`shell.wit`, C7)—so **`focus-surface` immediately returns `busy`!** Even if the agent waits 1 second and retries, the compositor then drops the user's keys for another 500 ms right after switching to the window they asked for.
  2. **Still vulnerable after a 1.1 s pause in an `untrusted` task:** Because `focus-surface` remains `change: none, local` (automatic in all tasks, `actions.wit:197`), an `untrusted` steered task can wait 1.1 seconds (or retry on `busy`) while the user pauses before typing a password, then silently focus another application and capture the keystrokes.
- **Verdict.** **Partly right.** Exclude keys typed in the agent's bar from the `busy` check (so `"focus X"` works at once, without a 500 ms dead zone on an explicit user focus request), and either require confirmation for `focus-surface` in `untrusted` tasks or restrict automatic focus changes to targets named directly from the user's own unmarked request.

### C8 (Finding 6)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `actions.wit:50-52, 221`).
- **Closes Finding 6?** Yes. Adding the instance's marks at that point upon reading any `progress` value (including `fraction` as well as `note`, and at least `untrusted` for third-party apps) closes the streaming leak before the reply future resolves.
- **Breaks / cost.** An unmarked task that invokes a third-party `none, local` action cannot even read `progress.fraction` without immediately picking up `untrusted` (which `P-042` already adds on `available` and `actions.wit:133-135` adds on reading the reply).
- **Verdict.** **Confirmed.**

### C9 (N5)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `catalog.wit:82-83`, `ui.wit:56`).
- **Why C9 is wrong.** C9 changes `ui.wit:56` to allow **any action** (`"on an application surface, any action: see button"`) in `button.action` on any application's surface, executes it in a single-call task under `task.invoke`'s confirmation matrix with `"The click is not a confirmation"`, and returns `"completed" {"entry": id, "output": {...}}, objects` directly to the **surface owner** (`catalog.wit:83-85`).
  Look at what happens with a hostile app (`pub/evil`):
  1. `pub/evil` draws an ordinary `"Play"` or `"Continue"` `button` whose `action` is `{app: "pub/passwords", name: "reveal", args: ...}` (`none, local`), `{app: "os:shell", name: "list-surfaces"}` (`none, local`), or `{app: "pub/notes", name: "delete-all"}` (`reversible, local`).
  2. The user clicks `"Play"`. C9 opens a one-call task marked `untrusted` (the owner's marks).
  3. Under `actions.wit:197-198`, `none, local` and `reversible, local` **run automatically with zero confirmation even when marked `untrusted` (and even when `private`)!** Saying `"The click is not a confirmation"` only stops the click from confirming `external`/`irreversible` actions; it does **not** trigger confirmation on `local` `none` or `reversible` cells!
  4. The system hands `pub/passwords.reveal`'s plaintext `output` and `objects` back to `pub/evil` through `surface.events` (`catalog.wit:84`).
  **Result:** One click on any third-party app's button silently invokes *any* installed app's or system service's `none, local` read and hands the output to the third-party app, and silently runs *any* app's `reversible, local` mutation without confirmation or user visibility! (Further, `world app` has no `task` handle, so returning `"entry": id` to an app surface gives no handle for `undo`; and for `"system"` surfaces, C9's marks list `"those of the owner ... plus those of the bound items"` omits marks of `source.input` fields, such as untrusted text pasted into a `field`.)
- **Verdict.** **Wrong.**
- **Correction.** Either forbid cross-publisher `button.action` on third-party application surfaces (a third-party app's buttons may invoke only its own actions, whereas system surfaces may invoke system/installed actions), OR require an explicit system-drawn confirmation for *every* cross-publisher `button.action` regardless of class (including `none, local` and `reversible, local`) and propagate `source.input` provenance marks as well as owner and `source.object` marks:
  ```wit
    /// With an action: activating it invokes the action through a task,
    /// under the same rules as `task.invoke`: on the agent's overlay, the
    /// overlay's task; on an application surface, a task the system opens
    /// for this one call, whose scope is limited to that application's own
    /// actions (unless the surface owner is `"system"`), and whose marks are
    /// those of the owner (`untrusted` unless `"system"`) plus those of the
    /// bound items and any `source.input` fields read into `args`, journalled
    /// as any task. The click is not a confirmation. The surface owner then gets
  ```
  And in `ui.wit:56`:
  ```wit
    actions within the task scope (on a third-party application surface, only
    the owner's own actions; on a `"system"` surface, any installed action),
  ```

### C10 (Finding 3)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `agent.wit` before line 170).
- **Closes Finding 3?** Fixes journalling and `undo` for `remember` and `forget`, **except one bug on `replaces`**: C10 states `"task.undo forgets the new entry, or restores the forgotten one until the retention period has passed."` Under `agent.wit:177-178`, `"Replaced and forgotten entries are left out."` When `remember(..., replaces: some(old_id))` is undone by `task.undo`, merely forgetting (tombstoning) the new entry leaves `old_id` still replaced and hidden from `recall`! Undo of a replacement must both tombstone/forget the new entry and un-replace `old_id`. (Minor addition: clarify that memory service actions count in the task's scope if memory is excluded by the user.)
- **Breaks / cost.** None; `remember` and `forget` stay automatic as `reversible, local` writes, matching `agent.wit:145-146`.
- **Verdict.** **Confirmed with another correction.**
- **Correction.** Change `"forgets the new entry"` in C10 to:
  ```wit
    /// `task.undo` forgets the new entry (and restores the replaced entry if
    /// `replaces` was set), or restores the forgotten one until the retention
    /// period has passed.
  ```

### C11 (Finding 8)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment edit in `manifest.wit:47-54`).
- **Closes Finding 8?** Yes: adding/removing `"os-item"`, changing `kind`, and adding/removing `"os-secret"` are `refused`; adding a right to `"os-item"` is `a new right`. (Minor detail: removing a right from `"os-item"` or narrowing `content-types` is not explicitly listed in `allowed` on line 45-47, and widening `content-types` reads under `"input constraint widened"`; clear enough for rights.)
- **Breaks / cost.** An update cannot add `"os-secret": true` to an existing action parameter under the same action name (it must add a new action, since removing an action is also refused, `manifest.wit:48`). Intended for ABI/confirmation transparency.
- **Verdict.** **Confirmed.**

### C12 (Finding 12 and N8)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment edits in `core.wit:56-57` and `ui.wit` after line 54).
- **Closes Finding 12 and N8?**
  - **Closes N8** cleanly (`props` capped at 65536 bytes both per node and summed across all nodes in one `update`).
  - **Only partially closes Finding 12.** Charging the retained surface tree `"to the owner's memory budget (D-073)"` works for the agent's overlay (which belongs to a `task`, carrying `budget.memory`, `actions.wit:172-173`), **but `world app` components have NO memory budget in `core.wit`, `manifest.wit`, `ui.wit`, or `memory.md`!** `D-073` (`decisions/README.md:83`) and `memory.md:38` state `"Every task carries a memory budget"`, while `store.collection` carries a disk `quota` (`store.wit:107`), not a compositor RAM budget. For an ordinary application surface (`show`), `"the owner's memory budget"` is still undefined unless a per-app memory budget or a per-surface cap is added.
- **Breaks / cost.** Trees with >64 KiB total `props` (still within 1024 nodes × ~64 B/node) must be split across multiple `update` calls, adding async round-trips on large initial UI mounts. (A single 200-row `table`, `core.wit:64`, remains a single node capped at 65536 bytes.)
- **Verdict.** **Confirmed with another correction.**
- **Correction.** Keep C12's `core.wit` change and define a per-surface retained byte cap (or define an explicit memory budget for `world app` processes in `core.wit`/`memory.md`): e.g., `"At most 1024 nodes per call; the retained tree of a surface is capped at 16 MiB (props and bindings) and charged to the owner's memory budget (for a task, `budget.memory`; for an application, its process memory limit): past either, `update` answers `quota-exceeded` and changes nothing."`

### C13 (N7)
- **Parses?** Yes (`wasm-tools` passes cleanly; `set-title: async func(title: string) -> result<_, error>;` added inside `resource surface` of `ui.wit`, validated across all six worlds).
- **Closes N7 (and remaining gaps)?**
  1. **Citation error in Opus line 421:** Opus says `In shell.wit:34 and agent.wit:285-289, add after "the owner's text"`. `agent.wit:285-289` does **not** contain `"the owner's text"` — it is at **`agent.wit:294`** (`/// The title is the owner's text: reading it marks as \`read\` does.`).
  2. **System surfaces have no package title:** C13 says `"" (the default) shows the package title`, which is undefined when `app == ""` (`"system"` surfaces, `shell.wit:32`).
  3. **Error code unstated:** `set-title` does not state `too-large` over 256 bytes or `invalid` on control characters (implied via `core.wit:53`, better explicit).
  4. **Leaves DeepSeek Finding 11 open once titles can be set:** With a 256-byte title plus `id`, `app`, `display`, `layout`, `focused`, each `surface-info` entry in JSON can reach ~580 bytes. Because `shell.list-surfaces` is unpaged (`shell.wit:54`) and `core.wit:341` lets an app receive `"several"` surfaces with no surface-count cap, ~115 open surfaces exceed the 65536-byte `outcome.output` cap (`actions.wit:40`) and break `list-surfaces` with `too-large`.
- **Breaks / cost.** Additive method on `ui.surface` while `os:core` is 0.1.0 draft (`P-022`/`P-034`).
- **Verdict.** **Confirmed with another correction.**
- **Correction.** Fix the line target to `agent.wit:294`, state `too-large`/`invalid` on `set-title` and system fallback for `app == ""`, and page `list-surfaces` (or cap surfaces per component).

### C14 (Finding 7)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `actions.wit:224, 238`, `agent.wit:90-91, 133-134`).
- **Closes Finding 7?** Yes: explicitly specifies refusal for out-of-scope refs in `invoke`, `subtask`, `inference.request.tools`, and `choose(candidates)`. Minor note: C14 uses `invalid` on `subtask` while using `denied` on `invoke`, `tools`, and `choose`; `core.wit:107` (`"The held rights ... do not allow this"`) fits `denied` on `subtask` as well, though both refuse the call.
- **Breaks / cost.** If the user excludes an app while a task or cached tool list is active, passing any stale ref in `tools` or `choose` fails the entire call with `denied` until the agent drops that ref (intended).
- **Verdict.** **Confirmed.**

### C15 (Finding 2)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `actions.wit:227, 231`).
- **Closes Finding 2?** Closes the two small gaps Opus left (`undo` returning `not-found` for other tasks' ids, and `journal` excluding sub-tasks' entries).
- **Breaks / cost.** One subtle lifetime trade-off: `actions.wit:165-166` says unspent budget of a `subtask` `"returns to the parent when it ends"`. Because `resource task` has no separate `close` method, ending a sub-task to reclaim its budget means dropping its `task` handle—at which point, under C15, the parent can no longer inspect that sub-task's journal or undo its reversible writes.
- **Verdict.** **Confirmed.**

### C16 (Finding 9)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comments in `manifest.wit:73` and `core.wit:260`).
- **Closes Finding 9?** Yes: eliminates accidental unbounded network access from an omitted `scope: []` while preserving arbitrary-host apps (`["*"]`). Minor precision: `manifest.wit:81-82` defines `"A host is an HTTPS origin ..."` and should note `"*"` as the wildcard exception for `"network"`'s `scope` (and clarify whether `wasi:sockets` uses `hostname:port` vs HTTPS origins, since `manifest.wit:81` only mentions HTTPS origins).
- **Breaks / cost.** Existing draft manifests that wrote `scope: []` expecting any-host access are rejected until updated to `["*"]` (intended).
- **Verdict.** **Confirmed.**

### C17 (Finding 10)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `input.wit` after line 110).
- **Closes Finding 10 (Opus's scope)?** Yes: guarantees third-party engines run only after the user explicitly selected them in settings for that purpose and language.
- **Breaks / cost & what stays open.**
  1. **Breaks ad-hoc IME switching & untagged fields:** Requiring settings selection per `(purpose, language)` blocks switching temporarily to another language's IME inside a document tagged `language: "en"` (or `language: ""`, `input.wit:33`, which represents `"unknown"`), unless the user explicitly binds the engine to `"en"` or `""` in settings.
  2. **Stays open for chosen engines:** Once enabled for `(text, en)`, the engine still receives up to 4096 bytes of surrounding text (`input.wit:22-24`) across *all* applications (mail, notes, health, finance—only `"password"`/`"pin"` are excluded, `input.wit:29-31`) and stores it in its persistent writable `home` (`input.wit:110`).
- **Verdict.** **Confirmed.**

### C18 (N9)
- **Parses?** Yes (`wasm-tools` passes cleanly; doc comment in `store.wit:42-43`).
- **Closes N9?** **Only for four of the nine storage zones, leaving five unspecified.**
  C18 specifies: `user` and `application` carry `private`; `system` and `shared packages` do not. Comparing against `storage.md:44-54` (which defines nine zones: `System`, `Packages`, `Cache`, `Device`, `User`, `Application`, `Snapshots`, `Ephemeral`, `Foreign`), C18 leaves out **five zones**:
  - **`Device`** (`"Pairing keys, networks, hardware settings"`, `storage.md:49`): holds credentials and pairing keys yet is outside `user`/`application`, so it would lack `private`.
  - **`Cache`** (`"Compiled code, thumbnails, indexes"`, `"Depends on the origin"`, `storage.md:48`): derived thumbnails and search indexes (`store.wit:147-148`) built from user files sit in `Cache`; without inheriting `private` from their source objects, reading an index or thumbnail drops `private`.
  - **`Ephemeral`** (`"Temporary files, guest session"`, `storage.md:53`): app `/tmp` files or task scratch files holding private user data lack a rule.
  - **`Foreign`** (`"USB sticks, disks of other systems, network shares"`, `storage.md:54`): user backups on a USB stick carry `untrusted` (`core.wit:92, 165`), and whether they also carry `private` is left unsettled.
  - **`Snapshots`** (`storage.md:52`): holds frozen user process state (though not exposed directly as user `store.object` handles).
- **Breaks / confirmation cost.**
  1. **Severe interaction with `P-042` and `P-037` on `none, external`:** Because *every* object in `user` and *every* object in `application` (`home`) carries `private`, any task reading *any* local user file (including downloaded public manuals, articles, or saved bookmarks) or invoking/reading *any* app's `home` (e.g., a weather app's saved city list, an RSS reader's feed list, an editor's settings) immediately becomes `private`. Whenever the task is also `untrusted`—which `actions.wit:188` (`available`, `P-042`), `agent.wit:89-90` (`tools`), or using a remote model (`agent.wit:28-30`, `P-037`) triggers on almost every multi-app task—**every subsequent `none, external` read (web search, HTTP `GET` fetch, RSS refresh) now requires a user confirmation** (`actions.wit:200-202`). This undercuts `security.md:278` (`"So the spread of marks costs few confirmations"`).
  2. **Interaction with remote `inference` (`agent.wit:24-26`):** Under `agent.wit:24-26`, tasks marked `private` cannot call a remote model unless `private-allowed` is `true` (`denied` otherwise). With C18, reading any `user` or `home` object—even non-sensitive public downloads or cached catalogs—blocks remote models that have `private-allowed: false`.
  3. **Interaction with network confinement alternatives for N1:** If every object in `home` is `private`, a long-lived instance cannot be denied networking merely for carrying `private` without breaking all networked apps.
- **Alternatives to C18.** (Evaluated in detail alongside C2 in the next section.)
- **Verdict.** **Confirmed with another correction.**
- **Correction.** Cover all nine zones of `storage.md:44-54` explicitly (until a finer sensitivity model is chosen by the owners):
  ```wit
    /// Stamped by the system at each write: who wrote, under which marks.
    /// Every object of the `user`, `application` and `device` zones, and every
    /// `cache` or `ephemeral` object derived from a `private` object or written
    /// by a `private` task, carries `private`, whoever wrote it; objects of
    /// `system`, `packages` and machine-wide caches do not (`foreign` carries
    /// `untrusted`, and `private` unless the user opens it as public).
  ```

---

## Deep comparison: C2 (N1) and C18 (N9) and their alternatives

Both C2 and C18 adjust rules of `security.md` that rest on `D-035` (fresh-instance effect isolation for local actions, and the two-mark confirmation matrix), and both materially change how often the user sees confirmations.

### Alternatives for C2 (closing N1: `reversible, local` -> `home` -> `"network"` long-lived instance)

| Alternative | Mechanism | Confirmation cost to the user | What it leaves open |
|---|---|---|---|
| **C2 (as corrected above)** | Treat `reversible` and `irreversible, local` actions in packages holding `"network"` as `external` (confirmed, held, counted in `budget.external`, not `undoable` once done). | **High.** Confirms every `reversible, local` edit in any networked app (notes sync, mail draft, calendar, todo, feed state, MCP token write), even in unmarked tasks; `"allow for the rest of this task"` still re-asks per distinct `input`. | Reopens `security.md:177` (`D-035`). Encourages publishers to ask for `"network"` less or move actions into interactive UI flows (`pick`/surface) instead of actions. Past `home` data exists if `"network"` is added later by update. |
| **Alt A: Static manifest rule** | Forbid `local` + `reversible`/`irreversible` in manifests holding `"network"`; publishers must declare those actions `external` with explicit `hosts` (or split network sync into a separate `"network"` package without shared `home`). | **High** for single-package networked apps (identical to C2); **zero** extra confirmations for local-only components when split from a separate sync component. | Forces package splitting or forces apps that only use `"network"` for optional checks to declare every local edit `external`. Preserves `security.md:177` literally. |
| **Alt B: Isolate `home` from `local` actions in `"network"` apps** | Give action instances `/home` **read-only** (even when `reversible`/`irreversible`) whenever the package holds `"network"`, or give action instances a separate `action-home` not readable by the `"network"` long-lived instance. | **Zero** extra confirmations on `reversible, local` actions. | **Breaks stateful actions** in networked apps that legitimately mutate `home` (`core.wit:299`, `mcp.md:30, 44`, e.g., saving mail drafts or updating an app's own `home` database), forcing them to keep user objects in `user`-zone collections passed via `request.objects` instead. |
| **Alt C: Mark-aware network confinement** | Keep `actions.wit:198` automatic; distinguish an `"action-tainted"` mark (separate from C18's `private`) on writes from action instances into `home`, so reading it marks the long-lived instance (`kernel-interface.md:1098`) and the network service blocks or prompts. | **Zero** confirmations on local edits that never trigger an upload (and zero on non-exfiltrating apps). | Cannot be built with `private` alone once C18 makes all `home` objects `private` (every app reading `home` would become blocked). Blocking outbound network breaks background sync after agent edits; prompting inside `network` has no typed action schema (`D-035`, `security.md:208`) and cannot inspect TLS/socket payloads. |
| **Alt D: Confirm only when `objects` non-empty or task is `private`/`untrusted`** | Treat `reversible`/`irreversible, local` in `"network"` apps as `external` only if the task already holds `private`/`untrusted` or `request.objects` is non-empty (plus pre-checking object marks). | **Moderate.** Unmarked tasks creating standalone app items with no user-file input run without confirmation; tasks after any `private` read (which is frequent under C18) or taking any bound file still confirm. | A hostile local model (`security.md:104`) could still smuggle a small user secret known from earlier uncompressed context inside literal `request.input` strings without `objects` or prior `private` mark. |

### Alternatives for C18 (closing N9: defining which store objects carry `private`)

| Alternative | Mechanism | Confirmation cost to the user | What it leaves open |
|---|---|---|---|
| **C18 (with all 9 zones fixed)** | All objects in `user`, `application`, `device` (and derived `cache`/`ephemeral`) carry `private` regardless of writer. | **High under `P-042` / `P-037`.** Reading *any* user file or *any* app's `home` before a `none, external` fetch triggers confirmation whenever `available`/`tools` (`P-042`) or a remote model (`P-037`) marked the task `untrusted`; blocks remote models with `private-allowed: false`. | Over-marks genuinely public files (downloaded RFCs, public RSS feeds cached in `home`, saved public cities), feeding label-creep fatigue (`security.md:276`). |
| **Alt 1: `user` + `device` `private`, `application` `home` by writer marks (or manifest opt-in)** | Objects in `user` and `device` (and derived `cache`) carry `private`; `application` `home` objects carry `private` only when written under `private` or when the app declares its `home` private in the manifest. | **Lower.** Public-cache apps (feed readers, weather, maps, docs) reading their own `home` stay non-`private`, avoiding unnecessary confirmations on `none, external` reads. | **Critical risk if app forgets opt-in:** a password manager or notes app writing user secrets into `home` (`security.md:86`) inside a long-lived instance outside any task will lack `private` unless its manifest declares it (and publishers can omit it). |
| **Alt 2: Default `private`, excluding unmodified `web:` / `packages:` downloads or user-designated `"Public"` collections** | `user`, `application`, `device` default to `private`, except blobs/objects tagged at download from `web:`/`packages:` (carrying `untrusted`, not `private`) or stored in user-marked public collections. | **Medium-low.** Using downloaded public docs or reading public web caches + doing a `none, external` lookup does not confirm (`untrusted` only, not `private`). | **Sensitive downloads:** a bank statement or tax PDF downloaded from `web:` has no `private` mark and could be exfiltrated via `none, external` unless the user marks it `private`. Letting *apps* choose non-`private` collections would violate `security.md:186` (`"never by the producer"`). |
| **Alt 3: Confirm all `external` reads in `untrusted` tasks (`P-036` Option B variant)** | Drop `private` from the confirmation matrix (`actions.wit:200-202` confirms `none, external` whenever `untrusted`, or always per `P-036` Opt B); keep `private` only for `inference.private-allowed` (or drop it). | **Maximum.** Every web search or HTTP `GET` in an `untrusted` task (or every task) asks the user, even when no local data was touched. | Still leaves `inference.private-allowed` (`agent.wit:24-26`) needing a definition of `private` if kept. |
| **Alt 4: Per-value provenance labels & quarantine (FIDES / CaMeL)** | Keep zone-wide `private` from C18, but track `private` and `untrusted` per value/handle instead of OR-ing onto the whole `task`. | **Lowest on multi-step tasks.** Touching a user file in step 1 and a third-party app in step 2 does not force confirmation on an unrelated `none, external` web search in step 3. | **Deferred past v1 by `D-035` and `P-046`** (`"a second provenance system before the first is built"`); does not cover implicit control-flow dependencies without full capability tracking. |

### Combined interaction (C2 + C18 + P-037 + P-042)

Reading C2 and C18 together shows why Opus flagged both for the owners:
1. Under C18, almost any task touching `user` files or an app's `home` picks up `private`; under `P-042` (`available` / `tools`) or `P-037` (remote model), it also picks up `untrusted`. That turns `none, external` (`actions.wit:200-202`) from an automatic read into a confirmed cell across most real tasks.
2. Under C2, any task invoking a `reversible, local` action in a networked app also becomes confirmed (`external`) even in unmarked tasks.
3. Together, C2 + C18 + `P-042`/`P-037` push confirmations back toward confirming routine reads (`none, external`) and routine local writes (`reversible, local` in networked apps), directly raising the confirmation count measured under `P-045`.

---

## What I checked and found correct, and what I did not check

### Checked and found correct
- Every quote in N1–N9 and C1–C18 against `Vehicoule/DodOS` `origin/step0-contracts` (`aab7417553b4733859685c14f8af7a0c920e2b84`) and `Docs` (`c93a623d29c190ac506c093e202cc18efb5755f6`), finding all accurate except the two line errors noted (`security.md:296` -> `295` in N9; `agent.wit:285-289` -> `agent.wit:294` in C13).
- All 18 corrections C1–C18 individually and combined (`ALL C1-C18`) in an isolated scratch copy outside the repositories using `wasm-tools 1.263.0` (`wasm-tools component wit`, `component embed --dummy`, `component new`, `validate --features all` across `base`, `service`, `app`, `agent`, `wake-word`, `input-engine`): all 18 runs and the combined run passed with exit code 0.
- Decisions `D-001` to `D-132` (specifically `D-011`, `D-035`, `D-036`, `D-052`, `D-055`, `D-056`, `D-066`, `D-073`, `D-110`, `D-111`, `D-130`) and pending entries `P-001` to `P-091` (specifically `P-022` to `P-067`).
- Cross-file rules in `security.md`, `agent.md`, `ui.md`, `network.md`, `storage.md`, `memory.md`, `scheduling.md`, `platform.md`, `wasm-abi.md`, `kernel-interface.md` (Marks and services), `contracts/README.md`, and `contracts/mcp.md`.

### Did not check
- Opus's verdicts on DeepSeek's twelve earlier findings (excluded by the prompt; only C3, C4, C7, C8, C10, C11, C12, C14, C15, C16, C17 themselves were verified).
- Opus's unjudged side note on listening capabilities (`network.md:30` vs `manifest.wit:69-79`), which was outside N1–N9 and C1–C18.
- The `verify` script's `deps.toml` tarball download/checksum step against upstream WASI 0.3.2 (checked `verify` source only; vendored `contracts/deps/` inside the `aab7417` checkout was used directly by `wasm-tools`).
- Attack execution on a running Wasmtime or DodOS runtime; all attack replays follow strictly from the WIT specifications and prose documents.
