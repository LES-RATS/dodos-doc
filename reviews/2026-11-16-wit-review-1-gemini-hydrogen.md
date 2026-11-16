# Review of DodOS PR 1 WIT contracts (`origin/step0-contracts`)

**Object:** Pull request 1 of `Vehicoule/DodOS` (`origin/step0-contracts`, head `aab7417`), comprising the nine WIT files in `contracts/` (`core.wit`, `store.wit`, `ui.wit`, `input.wit`, `actions.wit`, `agent.wit`, `catalog.wit`, `manifest.wit`, `shell.wit`), `contracts/README.md`, `contracts/mcp.md`, `contracts/deps/`, `contracts/deps.toml`, and `verify`, checked against `Docs/architecture/`, `Docs/contracts/README.md`, `Docs/decisions/README.md`, and the WebAssembly Component Model / WASI 0.3.2 specifications read on 16 November 2026.

Note on scope: PR 1 explicitly lists in *"What the documents must change (not edited here)"* the sections of `Docs` (`wasm-abi.md`, `agent.md`, `open-questions.md`, `ui.md`, `storage.md`, `security.md`, `scheduling.md`, `platform.md`, `decisions/README.md`, `plan/progress.md`) that still describe the pre-PR-1 `8bc6509` contracts. Those expected documentation updates are not repeated as findings here except where an active contradiction or unbacked guarantee remains against decided behaviour or PR 1's own rules.

---

## Findings

### 1. Writable `keep` in fresh action instances contradicts "holds only what `request` carries" and breaks reversibility (`breaks a guarantee`, `contradiction`)

- **Quotes:**
  - `contracts/actions.wit:55-57`: `"/// Runs one action in a fresh instance: nothing is shared with the running\n/// application, and the instance is destroyed afterwards. It holds only\n/// what request carries, and its imports are linked to match the class"`
  - `Docs/architecture/security.md:176`: `"- Each action runs in a fresh instance, on which the system calls only actions.invoke. The instance shares no memory with the running application and is destroyed afterwards. It holds only what the request carries (input, bound objects, the home collection), attenuated to the class."`
  - `contracts/core.wit:266-267`: `"///   - \"/home\" is the request's home, \"/tmp\" ends with the instance;\n///     keep, \"/home\" and the bound objects are read-only when change is\n///     none;"`
  - `contracts/store.wit:2-3`: `"// Every write is versioned, so nothing in this interface is irreversible and a\n// store capability is safe to hand to an action of change reversible."`
  - `contracts/store.wit:179-186`: `"  /// slot: 1 to 64 bytes of [a-z0-9-]. Replaces what the slot held. Takes\n  /// the handle: attenuate first to keep using it. At most 256 slots.\n  put: async func(slot: string, item: item) -> result<_, error>;\n...\n  forget: async func(slot: string) -> result<_, error>;"`
- **Scenario:**
  1. A user uses the object picker (`exchange.pick`) or drag-and-drop (`drop-target`) to grant an application `write` access to an existing user collection outside its `home`, and the long-lived instance persists that capability via `keep.put("docs", item)` (`store.wit:170-181`).
  2. Later, an agent task invokes a `change: reversible, reach: local` action on that application. Per the confirmation matrix (`actions.wit:198`), a reversible local action runs automatically without user confirmation, even in a task marked `untrusted`.
  3. Because `core.wit:267` makes `keep` read-only *only* when `change` is `none`, the fresh action instance receives full read-write access to `keep`.
  4. The action instance calls `keep.get("docs")` to access and modify a user collection that was never part of `request.objects` or `request.home` (and is never recorded in `journal-entry.objects` at `actions.wit:138-150`), violating `"It holds only what request carries"`.
  5. Worse, the action can call `keep.forget("docs")` or `keep.put("docs", ...)` (`store.wit:179,186`). `keep` is not versioned and has no `undo`; replacing or forgetting a slot permanently destroys the persisted grant without confirmation, violating the guarantee at `store.wit:2-3` that every operation available to a `reversible` action is versioned and undoable.
- **Smallest correction:** Either return `denied` on every `keep` call (`put`, `get`, `forget`, `slots`) inside a fresh action instance so the instance truly holds only what `request` carries, or restrict action instances to read-only `keep` (`get`/`slots` only, with returned items read-only for `change: none` and still recorded/disabled unless explicitly bound) and forbid `keep.put`/`keep.forget` in action instances altogether.

---

### 2. Non-`async` `inference.generate` and `tasks.task.invoke` release `borrow<task>` before their `stream` and `future` finish (`breaks a guarantee`, `unsettled case`)

- **Quotes:**
  - `contracts/agent.wit:2-4`: `"// Every\n// call that spends or reads on the user's behalf takes the task, so that the\n// system charges its budget and applies its marks."`
  - `contracts/agent.wit:121,126`: `"/// Streams the output. Cancellation: drop both reading ends; generation\n/// stops and nothing more is charged.\n...\ngenerate: func(scope: borrow<task>, request: request) -> tuple<stream<event>, future<result<outcome, error>>>;"`
  - `contracts/actions.wit:164-166`: `"/// What the task may still spend. Budgets are split, never copied: a\n/// sub-task's budget is taken from its parent's, and what it did not spend\n/// returns to the parent when it ends."`
  - `contracts/actions.wit:219-220,225`: `"/// Progress and cancellation as in actions.invoke: drop both reading ends to cancel.\n...\ninvoke: func(action: action-ref, input: string, objects: list<binding>) -> tuple<stream<progress>, future<result<reply, error>>>;"`
  - Component Model `CanonicalABI.md` (`lift_borrow`, `canon_lower`, `canon task.return`) and `Concurrency.md` (Section "Borrows"): `lift_borrow` registers a lender on the call's `Subtask`; on a non-`async` call, `subtask.deliver_resolve()` decrements `num_lends` immediately when `func` returns `tuple<stream, future>`. `task.return` and `lift_async_value` forbid `contains_borrow`, so a `stream` or `future` never carries a `borrow<task>`.
  - Contrast with `contracts/deps/sockets/sockets.wit:145-156` (`wasi:sockets/types@0.3.2`): `"WASI uses shared ownership semantics: the tcp-socket handle and all derived stream and future values reference a single underlying OS socket: Send/receive streams remain functional after the original tcp-socket handle is dropped... The OS socket is closed only after the last handle is dropped."`
- **Scenario:**
  1. The agent calls `scope.subtask(actions, share)` (`actions.wit:247`) to obtain an owned `sub: task` handle whose budget `share` was subtracted from `scope`.
  2. The agent starts `inference.generate(sub, req)` or `sub.invoke(action, input, objects)`. Because both functions are synchronous (`func`, not `async func`), the Component Model call resolves immediately on returning `(stream, future)` and drops `sub`'s `num_lends` back to zero.
  3. The caller drops `sub` (`resource.drop`) while holding and reading the returned `stream` and `future`. Because neither reading end was dropped, cancellation (`agent.wit:121`, `actions.wit:220`) has not been requested.
  4. The contracts leave two conflicting outcomes unsettled:
     - If dropping `sub` ends the sub-task and immediately returns its unspent `budget` to `scope` (`actions.wit:165-166`), the still-open `generate` or `invoke` stream/future either continues spending tokens/CPU and adding marks after the sub-task ended (breaking budget splitting) or fails abruptly despite not being cancelled.
     - If derived `stream`/`future` ends keep the underlying sub-task alive via shared ownership after `sub` is dropped (as `wasi:sockets` specifies for `tcp-socket`), `sub` has not ended on drop, unspent budget return is silently delayed until both ends close or resolve, and `scope` has no way to tell when its budget returns.
  5. The same ownership ambiguity appears on `store.object.read-via-stream` (`store.wit:61`), `store.object.changes` (`store.wit:88`), `store.collection.changes` (`store.wit:152`), and `ui.surface.events` (`ui.wit:67`) when the `object` (e.g., passed to `keep.put`, which moves ownership at `store.wit:180`), `collection`, or `surface` handle is dropped while streams remain open (by contrast, `input.wit:68-69` explicitly defines `field.edits` as ending when `field` is dropped).
- **Smallest correction:** State explicitly on `tasks.task`, `inference.generate`, `store.object`, `store.collection`, and `ui.surface` whether derived streams and futures use shared ownership (keeping a sub-task alive and deferring unspent budget return until the last derived reading end closes/resolves, mirroring `wasi:sockets`) or close/cancel when the resource handle is dropped.

---

### 3. Dead rights and omitted targets in `os:manifest` block assistive tools, audio apps, and third-party input engines (`blocks building`, `contradiction`)

- **Quotes:**
  - `contracts/manifest.wit:69-79`: `"/// A right the package asks for. Names known in this version (an\n/// unknown name makes the installer refuse the package, rather than run\n/// it without a right it expects):\n///   \"network\"             wasi:sockets and wasi:http for the long-lived\n///                         instance; scope: the hosts, empty for any\n///   \"background\"          woken without a surface (D-053)\n///   \"audio-playback\", \"microphone\", \"audio-capture\"\n///                         three distinct rights (ui.md)\n///   \"accessibility-read\"  read other surfaces' trees (assistive tools)\n///   \"global-shortcuts\", \"input-injection\"\n///                         held by nobody by default (ui.md)"`
  - `contracts/manifest.wit:83`: `"record right { name: string, scope: list<string>, why: string }"`
  - `contracts/manifest.wit:115-119`: `"/// The world the component targets: \"os:core/service@0.1.0\",\n/// \"os:core/app@0.1.0\", \"wasi:http/service@0.3.2\",\n/// \"wasi:cli/command@0.3.2\". The installer checks the component's\n/// imports and exports against it."`
  - `contracts/core.wit:241-242`: `"/// A component may import any subset of this world, and nothing else: the\n/// installer refuses a component with another import."`
  - `contracts/core.wit:359`: `import accessibility;` appears only in `world agent` (`core.wit:349-364`), not in `world service` (`283-316`) or `world app` (`329-343`).
  - `contracts/agent.wit:252`: `"/// The agent gets it only through request.screen, when the user\n/// attached a window; assistive tools get it from the user."`
  - `Docs/architecture/ui.md:111`: `"libhangul (Korean, LGPL, so in a separate component)"`
  - `Docs/architecture/ui.md:127`: `"- **Reading the tree of another application is a capability**, granted by the user to assistive tools."`
  - `contracts/input.wit:53-54`: `"\"app:<engine>\" with untrusted through a third-party engine"`
  - `contracts/core.wit:383-386`: `"world input-engine {\n  include base;\n  export engine;\n}"`
- **Scenario:**
  1. **Assistive tools cannot build or run:** An assistive tool packaged via `os:manifest` must set `target` to `"os:core/service@0.1.0"` or `"os:core/app@0.1.0"` (`manifest.wit:115-118`) and request right `"accessibility-read"` (`manifest.wit:77`). Yet neither `service` nor `app` imports `accessibility` (`core.wit:283-343`), and `core.wit:241-242` makes the installer refuse any component with another import. Even if `service` or `app` imported `accessibility` (which only defines the `accessible` resource type and no discovery/handle-acquisition call), there is no interface by which an assistive tool obtains an `accessible` handle on another surface (`request.screen` exists only in `world agent`).
  2. **Audio, shortcut, and injection rights have no WIT interface:** `"audio-playback"`, `"microphone"`, `"audio-capture"`, `"global-shortcuts"`, and `"input-injection"` are listed as known manifest rights, while no allowed `manifest.target` world imports an interface for audio streams, global shortcuts, or input injection.
  3. **Third-party `input-engine` and `wake-word` components cannot be packaged:** `input.wit:53` and `ui.md:111` explicitly design for third-party `input-engine` components and `core.wit:370-386` defines `world wake-word` and `world input-engine`, yet `manifest.wit:115-118` restricts `target` to `service`, `app`, `wasi:http/service`, and `wasi:cli/command`.
  4. **Unsettled `right.scope`:** `manifest.wit` specifies `scope` syntax only for `"network"` (`"the hosts, empty for any"`), leaving valid/invalid `scope` values undefined for the other seven rights.
- **Smallest correction:** Add `"os:core/wake-word@0.1.0"` and `"os:core/input-engine@0.1.0"` to `manifest.target`; specify how an assistive `service`/`app` imports `accessibility` and acquires `accessible` handles (or defer `"accessibility-read"`, `"audio-*"`, `"global-shortcuts"`, `"input-injection"` out of `0.1.0` until their interfaces exist); and state that `scope` must be empty for every right that takes no scope.

---

### 4. `network.md` protocol, port, and listening scopes cannot be represented in `os:manifest` or `core.wit` (`contradiction`, `unsettled case`)

- **Quotes:**
  - `Docs/architecture/network.md:21`: `"An application has no access to the network without a capability, and the capability carries its scope (hosts, ports, outgoing or incoming). Every incoming packet with no matching listening capability is dropped."`
  - `Docs/architecture/network.md:30`: `"- The application requests a listening capability in its manifest: protocol, port, and scope (machine, circle of devices, local network or internet)."`
  - `contracts/manifest.wit:72-73,81-83`: `"///   \"network\"             wasi:sockets and wasi:http for the long-lived\n///                         instance; scope: the hosts, empty for any\n...\n/// A host is an HTTPS origin (\"https://api.example.org\", with a port if\n/// not 443); \"https://*.example.org\" also matches every subdomain.\nrecord right { name: string, scope: list<string>, why: string }"`
  - `contracts/core.wit:248-250,259-260`: `"/// A plain wasi:http/service component (a server launched per request,\n/// platform.md) or wasi:cli/command component (a rescue tool) runs in its\n/// own WASI world, with the same linking rules for the network\n...\n///   - wasi:sockets and wasi:http: only with the manifest right \"network\",\n///     to the hosts it lists."`
  - `contracts/deps/sockets/sockets.wit:217,325`: `tcp-socket` exposes `bind: func(local-address: ip-socket-address)` and `listen: func() -> result<stream<tcp-socket>, error-code>;`.
- **Scenario:**
  1. A `service` component imports `wasi:sockets/types@0.3.2` to connect over raw TCP/UDP or to `bind` and `listen` on a port (`network.md:30`).
  2. Under `manifest.wit:72-83`, the only network right is `"network"`, whose `scope` entries must be HTTPS origins (`"https://..."`) or `[]` for any host. There is no way to declare a non-HTTPS host/port, distinguish TCP vs UDP vs HTTP, distinguish outgoing vs incoming listening, or express `machine`, `circle of devices`, `local network`, or `internet` scopes. Consequently, either raw sockets and listening fail to be scoped as `network.md:21,30` promises (forcing an all-or-nothing `scope = []`), or non-HTTPS sockets cannot be granted at all.
  3. In addition, `core.wit:248-250` applies `"the same linking rules for the network"` to `wasi:http/service@0.3.2` and `wasi:cli/command@0.3.2`, contradicting `manifest.wit:72` which restricts `"network"` to `"the long-lived instance"` (both WASI worlds are request/command-scoped, not long-lived `service` instances); and `core.wit:272` (`action.hosts`) does not state whether per-action `hosts` must also satisfy the HTTPS-origin + `*.` subdomain rule of `manifest.wit:81-82`.
- **Smallest correction:** Either add structured protocol/port/direction/listening-scope fields or rights to `manifest.wit` matching `network.md:21,30`, or explicitly document in `core.wit` and `manifest.wit` that non-HTTPS sockets and listening (`bind`/`listen`) are unsupported in `0.1.0` (`access-denied`), clarify `"network"` for `wasi:http/service` and `wasi:cli/command`, and cross-reference the HTTPS origin grammar for `action.hosts`.

---

### 5. `contracts/mcp.md` breaks forward-compatible `output-schema`, uses read-only `home` for return objects, and conflicts with `GET`/`HEAD`-only `change: none` external actions (`contradiction`, `breaks a guarantee`)

- **Quotes:**
  - `contracts/mcp.md:26-30`:
    `"| inputSchema | input-schema | Kept if it fits the subset of manifest.wit; additionalProperties: false added at every object (the confirmation must show everything sent); a schema outside the subset is refused, not rewritten |"`
    `"| outputSchema | output-schema | As above. Without one: {\"type\": \"object\", \"properties\": {\"text\": {\"type\": \"string\"}}} |"`
    `"| result image, audio and resource blocks | outcome.objects | Each written as an object of home, returned as a binding, so the agent passes it on without reading it |"`
  - `contracts/mcp.md:44`: `"8. **Remote servers.** Over Streamable HTTP with OAuth, the adapter is an action of reach external to the server's host"`
  - `contracts/manifest.wit:27,36-37,45`: `"\"os-item\": {\"kind\": \"object\" | \"collection\", \"rights\": [<rights>],\n//               \"content-types\": [<media types>]}"`; `"// An input schema has \"type\": \"object\" at the root and \"additionalProperties\":\n// false at every object, so that a confirmation shows everything sent."`; `"// Updates (ABI). ... allowed     a new action; a new optional input property; a new output\n//               property"`
  - `contracts/core.wit:47-49`: `"//   resource        never encoded: the field holds the name of a binding\n//                   carried next to the string\n// Readers ignore object keys they do not know."`
  - `contracts/core.wit:266-268,274-275`: `"- \"/home\" is the request's home, \"/tmp\" ends with the instance;\n    keep, \"/home\" and the bound objects are read-only when change is\n    none;"` and `"when change is none, only the methods GET and HEAD, with no request body."`
  - `contracts/actions.wit:40-44`: `"/// JSON object matching the output schema. At most 65536 bytes.\noutput: string,\n/// Typed object results, by property name of output. Each needs\n/// share.\nobjects: list<binding>,"`
- **Scenario:**
  1. **`outputSchema` with `additionalProperties: false` breaks updates:** `manifest.wit:36` restricts `"additionalProperties": false` strictly to `input-schema`, so callers ignore unknown output keys (`core.wit:49`) and updates may add new output properties (`manifest.wit:45`). `mcp.md:27` writes `"As above"` for `outputSchema`, forbidding new output properties in v1.1 without breaking v1.0 output validation.
  2. **`change: none` MCP tools cannot write `outcome.objects` into `home`:** A read-only MCP tool (`readOnlyHint: true` -> `change: none`, `mcp.md:37`) returns an image or resource block. `mcp.md:30` writes each block `"as an object of home"`. At runtime, `core.wit:267` links `request.home` read-only whenever `change` is `none`, so `home.create` / `write` fails with `denied` (`"/tmp"` is ephemeral and destroyed with the action instance).
  3. **Returned bindings have no matching property in `output-schema`:** When `outputSchema` is absent, `mcp.md:27` yields `{"type": "object", "properties": {"text": {"type": "string"}}}`, yet `mcp.md:30` returns `outcome.objects` bindings that correspond to no property of `output` and no `"os-item"` keyword (`actions.wit:42`, `core.wit:47-48`).
  4. **Remote MCP `Streamable HTTP` collides with `GET`/`HEAD`-only `change: none`:** MCP Streamable HTTP uses `POST` with a JSON-RPC request body even for read-only `tools/call` requests, which `core.wit:274-275` rejects (`HTTP-request-denied`) unless the read-only tool is misclassified as `reversible`.
- **Smallest correction:** Remove `additionalProperties: false` from `outputSchema` in `mcp.md:27`; define an `"os-item"` property in the fallback `output-schema` (e.g., `"objects"` array of `"os-item"` or named fields) to match `actions.wit:42`; clarify that a tool returning new objects in `home` cannot use `change: none` (or give actions a dedicated system-owned return-object store); and align `mcp.md:44` with `core.wit:274-275`.

---

### 6. `text-input` leaks `"password"`/`"pin"` fields to surface owners, `canvas`/`applet` lack `ui.md`/`agent.md` data & display paths, and `catalog.wit` miscounts app kinds (`contradiction`, `unsettled case`, `wrong fact`)

- **Quotes:**
  - `Docs/architecture/security.md:88`: `"| Secrets typed into a secret field (passwords, codes) | Never in the memory of the model or of the surface owner: the system reads the value when the button is activated and hands it to the action | [Provenance marks](#provenance-marks) (Decided, D-035) |"`
  - `contracts/input.wit:28-32,56,70`: `"/// Open set: \"text\", \"name\", \"email\", \"url\", \"number\", \"phone\", \"date\",\n/// \"time\", \"terminal\", \"password\", \"pin\". A \"password\" or \"pin\" field is\n/// served only by the system's own keyboard engine: no other engine, no\n/// dictation, empty surrounding text, nothing learned.\npurpose: string;"`, `"record edit-event { edit: edit, provenance: provenance }"`, `"edits: func() -> stream<edit-event>;"`
  - `Docs/architecture/ui.md:12,16`: `"- From the first version: shared buffers without copy; direct scanout of a full-screen surface ... and a frame callback with a deadline, so that a client's content leaves at the same refresh."` (`D-007`); `"- **Displays** (**Decided**, 14 November 2026): several screens, scaling per screen and hot-plugging are in the compositor's contract."` (`D-060`)
  - `contracts/catalog.wit:188-202`: `"/// A drawing area of the owner's own drawing. Its pixels are the image\n/// object source (any image type the system previews), drawn again at\n/// each new version: the owner draws by writing versions. Events:\n///   \"pointer\"  ...\n///   \"key\"      ...\nrecord canvas { alt: string, source: option<object-ref> }"`
  - `Docs/architecture/agent.md:17`: `"Applets are objects of the store, reused and fed with data rather than regenerated."`
  - `contracts/catalog.wit:110-116`: `"/// It talks to the surface owner only by event \"message\"\nrecord applet { source: object-ref }"`
  - `contracts/catalog.wit:145`: `"/// The document names ten kinds \"and a few more\" without fields."`
  - `Docs/architecture/ui.md:90`: `"- Application level, fifteen more: virtual-list and row ... drag-source, drop-target."`
- **Scenario:**
  1. **Password/PIN leak on `canvas`:** `security.md:88` (D-035) requires secret inputs never to enter the surface owner's memory (`catalog.wit:90-93` enforces this for catalogue `field` kind `secret`). Yet `input.wit:29-32,70` allows a surface owner to attach a `text-input` field to its own `canvas` with `purpose: "password"` or `"pin"`, causing `edits` to stream every committed secret character directly into the surface owner's Wasm memory.
  2. **Unbuildable `canvas` sizing, scaling, and frame pacing:** `ui.wit` and `catalog.wit:188-202` give a `canvas` owner only `"pointer"` (normalized `0.0..1.0`) and `"key"` events, with no logical/physical pixel dimensions, no per-display scale factor (`D-060`), no resize/DPI-change event, and no frame deadline (`D-007`), forcing the app to guess resolution and rewrite a versioned `store.object` per frame.
  3. **No path to feed data into an `applet`:** `catalog.wit:116` has only `source: object-ref` and `ui.wit` has no outbound message method to a node, so a reused `applet` stored as a read-only object cannot be fed task data without regenerating or modifying the stored JS object (`agent.md:17`).
  4. **Stale comment in `catalog.wit:145`:** `catalog.wit:145` claims `ui.md` `"names ten kinds 'and a few more'"`, whereas `ui.md:90` explicitly names `"fifteen more"` (all 15 of which `catalog.wit:213-229` defines).
- **Smallest correction:** Either exclude `"password"` and `"pin"` from `text-input.field-state.purpose` (or state explicitly in `security.md:88` that D-035 applies to catalogue `field(secret)` and not app-drawn `canvas` fields); add `"resize"` (width, height, scale) and optional `"frame"` events on `canvas` or note the deferral alongside `OPEN`; add an optional data/props binding or message mechanism to `applet` (or amend `agent.md:17`); and fix `catalog.wit:145` to `"fifteen more"`.

---

### 7. `entity.set` omits `scope: borrow<task>`, and `hint::done`/`failed` contradicts `idle` ("the task done") and "the hint ends with the task" (`contradiction`, `unsettled case`)

- **Quotes:**
  - `contracts/agent.wit:2-4`: `"// Every\n// call that spends or reads on the user's behalf takes the task, so that the\n// system charges its budget and applies its marks."`
  - `contracts/agent.wit:234-237`: `"///   idle       none of the above, the task done\n/// The agent adds only what the system cannot know, as a hint, drawn only\n/// while no system state applies: it can neither hide a system state nor\n/// show one."`
  - `contracts/agent.wit:241-247`: `"/// asking: the agent waits for the user's answer in its overlay.\n/// done, failed: the agent's own report at the end (the journal is the\n/// record). none clears it.\nenum hint { none, asking, done, failed }\n\n/// The last call wins; the hint ends with the task.\nset: async func(hint: hint) -> result<_, error>;"`
  - `contracts/core.wit:363`: `"export handle: async func(request: request, scope: task, overlay: surface);"`
- **Scenario:**
  1. Near completion of a user request, the agent calls `entity.set(hint::done)` (or `hint::failed`) to report the final state `"at the end"` (`agent.wit:242`) and returns from `handle`.
  2. Because `"the hint ends with the task"` (`agent.wit:246`), returning from `handle` ends the task and immediately clears `done`/`failed`; and even if `idle` (`"the task done"`, `agent.wit:234`) is treated as an active system state rather than a fallback, `"drawn only while no system state applies"` hides `done`/`failed`. Thus `done` and `failed` can only be shown if the agent holds `handle` open artificially after finishing work.
  3. Unlike every other stateful interface in `agent.wit` (`inference`, `memory`, `audio`), `entity.set` omits `scope: borrow<task>`, leaving ambiguous which task/sub-task owns the hint if `handle` calls overlap (`ui.md:56` side panel) or if the agent creates `subtask`s.
- **Smallest correction:** Add `scope: borrow<task>` to `entity.set(scope: borrow<task>, hint: hint) -> result<_, error>`, clarify that `idle` applies when no active system state *and no terminal hint* applies, and specify whether `done`/`failed` persist after `handle` returns (e.g., until the next task or overlay dismissal).

---

### 8. `accessibility.read` always adding `private` contradicts `security.md` Walk-through 2 (`contradiction`)

- **Quotes:**
  - `contracts/agent.wit:285-289`: `"/// What reading adds to the task: origin the surface's owner\n/// (\"app:<component-id>\", \"web:<origin>\", \"system\"); untrusted unless\n/// the owner is the system; private always, since what the user's\n/// screen shows is the user's."`
  - `Docs/architecture/security.md:295-296`: `"1. **A web page tells the agent to send a file.** The agent reads the page through the accessibility tree, which marks the task untrusted (origin web:<origin>). It reads the file, which adds private.\n2. **The same page asks for a fetch of https://evil.example/?d=<secret>.** An external read in a task marked private and untrusted. **Stops at** the confirmation (matrix). If the page is read before any private data, nothing private is yet in the task; the fetch runs and carries nothing private."`
- **Scenario:** In Walk-through 2 (`security.md:296`), the user asks the agent to summarize a public web page attached in `request.screen` and fetch an external URL before reading any user file. Under `agent.wit:287-288`, reading the web page's accessibility tree immediately marks the task `private`, forcing a confirmation dialog on the external fetch even though `"nothing private is yet in the task"`. (Conversely, under `security.md:296`, reading the web page does not add `private`.)
- **Smallest correction:** Settle whether `accessibility.read` sets `private` unconditionally (updating `security.md:296` walk-through 2) or only when the read surface itself holds private/user data (updating `agent.wit:287-288`).

---

### 9. WASI 0.3.1/0.3.2 adopted-features description omits `external-id`, and `verify` runs `--features all` instead of the adopted feature set (`wrong fact`, `blocks building`)

- **Quotes:**
  - `contracts/core.wit:26-28`: `"// Uses no Component Model feature beyond those WASI 0.3.2 adopts (async,\n// stream and future; map; implements). Not error-context, not threads:\n// both are still gated."`
  - `contracts/README.md:38`: `"WASI 0.3 rests on the Component Model's async (async functions, stream, future); 0.3.1 adopted map and implements. Nothing else is adopted ([adopted features](https://github.com/WebAssembly/WASI/blob/main/docs/ComponentModelFeatures.md)), and these files use nothing else."`
  - `verify:18`: `"  wasm-tools validate --features all \"$tmp/$w.wasm\""`
  - Upstream `WebAssembly/WASI/main/docs/ComponentModelFeatures.md` (read 16 November 2026): WASI 0.3.1 adopted both `map<K, V>` (`🗺️`, `#943`) and `implements and external-id annotations on plain-named interface imports and exports` (`🏷️`, `#942`), and WASI CI validates exclusively with those adopted features enabled `"so a proposal that depends on an un-adopted feature fails validation"`.
- **Scenario:** Running `verify` with `--features all` allows un-adopted gated features (`cm-error-context`, `cm-threading`, `cm-gc`, `cm-fixed-length-lists`, etc.) to pass validation silently, defeating the invariant claimed in `core.wit:26-28` and `contracts/README.md:38`. Tested with `wasm-tools 1.263.0`: all six worlds (`base`, `service`, `app`, `agent`, `wake-word`, `input-engine`) already encode and pass `wasm-tools validate --features=wasm2,component-model,cm-async,cm-map,cm-implements`.
- **Smallest correction:** Update `core.wit:27` and `contracts/README.md:38` to list `implements` and `external-id`, and replace `--features all` in `verify:18` with `--features=wasm2,component-model,cm-async,cm-map,cm-implements`.

---

### 10. Evolution: Changes already announced in `Docs` that will break a component compiled against `0.1.0`

Under Component Model rules and `core.wit:30-34`, adding an enum/variant/flags case, adding a record field, altering function signatures, or adding a mandatory export breaks ABI compatibility with compiled `0.1.0` binaries and requires a `0.2.0` package version (forcing the OS to keep serving `0.1.0` alongside `0.2.0` per `core.wit:31`). The following changes already announced in `Docs/` and PR 1 cannot ship incompatibly in `0.1.x` without breaking `0.1.0` components:

1. **Per-value provenance labels and FIDES quarantined reading** (`D-035`, `Docs/architecture/security.md:210,281,324`, `contracts/actions.wit:244-246`):
   Moving from whole-task taint to per-value provenance and quarantined reading changes `actions.outcome`, `tasks.reply`, `tasks.request`, `inference.message`, `inference.outcome`, and `tasks.task.subtask` semantics (stopping bidirectional taint flow). Components built against `0.1.0` assume single `provenance` structs and task-level `marks()`, requiring `os:core@0.2.0`.
2. **Closed enums, variants, records, and signatures on `agent.wit`, `core.wit`, `shell.wit`, and `manifest.wit`**:
   - **Memory embeddings** (PR 1 item 14 `"embeddings to add in a minor version when recall needs them"`): changing `memory.recall`'s parameters (`agent.wit:180`) or adding fields to `memory.entry` (`agent.wit:152-168`) breaks `0.1.0` components; only adding a *new* function (`@since(version = 0.1.x)`) avoids an ABI break.
   - **Closed `inference` and `entity` types** (`agent.wit:40,65,103,244`): `enum tier`, `enum role`, `variant event` (`text`/`call` only — no reasoning/image/audio event), and `enum hint` have no fallback case. Adding any new case breaks `0.1.0` `agent` components.
   - **Closed `core.wit` and `shell.wit` enums/records**: `error` (`other(string)`), `node.kind`, `event.kind`, `journal-entry.state`, and `principal` are open, whereas `rights`, `marks`, `change`, `reach`, `effect`, `wake-event`, `layout` (`shell.wit:28`), `text-style`, and `field-kind` are closed (`catalog.wit:7` assumes a newer host serves older props, whereas `inference`, `shell`, and `core` types cross ABI boundaries directly).
3. **Future exports and stabilized WASI interfaces (`gpui` accessibility, `wasi:webgpu`, snapshots, `wasi:clocks/timezone`, WASI `0.3.x` -> `0.4`/`1.0`)**:
   - **`gpui` in Wasm (`core.wit:320-328`) and multi-display/frame callbacks (`D-007`, `D-060`):** `core.wit:323-324` notes `gpui` in Wasm *"needs its accessibility tree exported"*. Adding a required export to `world app` (or a mandatory suspend/snapshot/frame hook) rejects every compiled `0.1.0` component; new drawing paths must be optional or placed in `0.2.0` (whereas optional imports like `wasi:webgpu` or audio playback/capture keep `0.1.0` components running under `core.wit:241`, as do new `os:catalog-app` node kinds under `ui.wit:6-8`).
   - **Stabilizing `wasi:clocks/timezone@0.3.2` (`core.wit:210-212`, `deps/cli/cli.wit:207-208`) and `wasi:random` value imports (`deps/random/random.wit:21-25`):** A `0.1.0` installer enforcing *"any subset of this world, and nothing else"* (`core.wit:241-242`) will refuse components compiled once Rust/WASI toolchains emit `timezone` or migrate `get-insecure-seed` to a value import in a later WASI series; and static world checks (`wasm-tools component targets`, `core.wit:217-218`) fail on `0.3.0` vs `0.3.2` differences without semver matching.
4. **Unsettled security policy switches (`core.wit:274-282`, `actions.wit:189-192`, `security.md:316,320`)**:
   - Confirming every `reach: external` action (`core.wit:280-281`) breaks `0.1.0` agents/workflows expecting `none, external` fetches to run automatically; conversely, strictly enforcing `GET`/`HEAD` with no body (`core.wit:274-275`) breaks `0.1.0` `change: none, reach: external` RPC/MCP Streamable HTTP adapters (`mcp.md:44`) that send `POST` queries.
   - Changing whether `tasks.available` marks third-party manifests `untrusted` (`actions.wit:189-192`) alters confirmation behaviour for `0.1.0` agents when querying external reads.
5. **Lowering any size cap or tightening `os:manifest` schema updates (`core.wit:51-70`, `manifest.wit:45-51`)**:
   Lowered size caps (`core.wit:52-53`) or breaking schema changes (`manifest.wit:48-51`) break existing `0.1.0` callers.

---

## Checked and found correct

- **`wasm-tools` parsing, world encoding, and WASI 0.3.2 feature validation:** With `wasm-tools 1.263.0`, `wasm-tools component wit contracts/` exits 0 across all 9 WIT files and 6 vendored `deps/` packages. Every world (`base`, `service`, `app`, `agent`, `wake-word`, `input-engine`) encodes via `component embed --dummy` + `component new` and passes `wasm-tools validate` under `--features=wasm2,component-model,cm-async,cm-map,cm-implements` as well as `--features all`.
- **Vendored WASI 0.3.2 `deps/` and error variant names:** `contracts/deps.toml` pins `wasi-wit-0.3.2.tar.gz` (`sha256 2e918e047c6ad251a44b4d1141359495a27219058fd7090f8b8142f6bc0ec311`, `cli`, `clocks`, `filesystem`, `http`, `random`, `sockets`), `world base` omits `@unstable(feature = clocks-timezone) timezone`, and `core.wit:244-246` cites exact WASI `error-code` case names (`wasi:sockets` `access-denied` in `deps/sockets/sockets.wit:24`, `wasi:http` `HTTP-request-denied` in `deps/http/http.wit:72`, `wasi:filesystem` `access` in `deps/filesystem/filesystem.wit:197`, `os:core` `denied` in `core.wit:108`).
- **Component Model `async` lifting/lowering in `actions.invoke`, `engine.activate`, `wake-word.detect`, and `store.object.write-via-stream`:** `actions.invoke` (`actions.wit:71`), `wake-word.detect` (`core.wit:378`), and `engine.activate` (`input.wit:113`) are correctly marked `async func` so the callee can call `task.return` with the stream/future handles and continue executing its implicit thread cleanly (`CanonicalABI.md` / `Concurrency.md` keep-alive semantics) without Component Model threads (`🧵`). `audio.speak` (`agent.wit:213`), `audio.read-aloud` (`agent.wit:219`), and `store.object.write-via-stream` (`store.wit:64`) are `async func` taking borrows/streams and resolving on completion, so their `borrow` lifetimes match Component Model dynamic borrow tracking (`num_lends > 0` until completion).
- **Catalogue kind counts and names (`catalog.wit` vs `ui.md:89-90`):** Both levels match 15 for 15:
  - `os:catalog-agent/kinds.kind` (`catalog.wit:118-138`): `stack`, `card`, `items`, `text`, `image`, `icon`, `table`, `progress`, `divider`, `button`, `field`, `choice`, `toggle`, `preview`, `applet` (15, matching `ui.md:89`).
  - `os:catalog-app/kinds.kind` (`catalog.wit:213-229`): `virtual-list`, `row`, `tree`, `tree-item`, `tabs`, `navigation`, `page`, `menu`, `dialog`, `text-editor`, `slider`, `search`, `canvas`, `drag-source`, `drop-target` (15, matching `ui.md:90`).
- **`icon-name` (`catalog.wit:39-54`) and overlay rules:** `system` and `untrusted` are present in `icon-name` and blocked on the agent's overlay (`ui.wit:58`, `catalog.wit:36-38`); `security.md` threat-model rules for `principal` origins (`model:`, `capture`, `device:`, `foreign`), `request-part` modalities, `action-info` provenance, `journal-entry` (`held` state, `undoable` during hold, secret nulled in journal), `budget` splitting, and `exchange.copy` provenance preservation are faithfully carried into `core.wit`, `store.wit`, and `actions.wit`.
- **Kernel boundary check:** `os:core`, `os:catalog-*`, `os:manifest`, and `os:shell` assume nothing below userland ABI and depend on no kernel ABI constants (`D-005`).

---

## Not checked

- `verify` tarball download and `sha256sum` comparison against GitHub release `v0.3.2` (`curl` network download in `verify:31-52`, `contracts/deps.lock` content-comparison against the live upstream release archive).
- Compiling a real Rust component targeting `wasm32-wasip3` with Rust 1.100 (`core.wit:200-202`, PR 1 "Checked by hand, not in CI") to verify empirically that an empty Rust `std` binary emits only the interfaces in `world base`.
- Full automated compliance of `contracts/mcp.md` against every schema field of upstream MCP specification `schema/2026-07-28/schema.ts` beyond the tool/annotation/result properties quoted in `mcp.md`.
