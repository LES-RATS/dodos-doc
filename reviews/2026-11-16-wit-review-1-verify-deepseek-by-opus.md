# Verification of the first WIT review (DeepSeek, hostile component), by Opus

**Date.** 16 November 2026.
**Judged.** `reviews/2026-11-16-wit-review-1-deepseek.md`, twelve findings.
**Against.** The nine WIT files of `Vehicoule/DodOS` at `origin/step0-contracts`, head `aab7417`, read with `git show` (line numbers are those blobs); `architecture/security.md`, `agent.md`, `ui.md`, `network.md`, `kernel-interface.md` (Marks and services), `decisions/README.md`, `plan/pending-decisions.md`, all on `main` at `c93a623`.
**Method.** For each finding I checked every quote at its line, rebuilt the attack call by call from the WIT text and its comments, looked for a decision or a pending entry that already settles it, and tested the proposed correction against the rest of the contract. No repository was changed; this file is the only output. No web source was needed: no finding rests on an external fact, except one remark about other input-method systems in finding 10, which I flag as from memory.

## Verdicts at a glance

| # | Reviewer's title (short) | Verdict |
|---|---|---|
| 1 | Action instance holds `keep` | Confirmed with another correction |
| 2 | Journal entries by bare number | Partly right (a small unsettled case; the attack does not follow) |
| 3 | Agent erases memory without class or journal | Confirmed with another correction |
| 4 | Shell names surfaces by string; focus is class `none` | Partly right (focus only) |
| 5 | Grant for the rest of a task keyed on `input` alone | Confirmed with another correction (the scenario needs fixing) |
| 6 | Progress note adds no mark | Confirmed with another correction |
| 7 | Decision table has no row for the scope | Partly right (list arguments only) |
| 8 | Update check ignores `os-item`, `os-secret` | Partly right (gap real; both attacks overstated or reversed) |
| 9 | Empty `network` scope | Partly right (not a contradiction; the omission point holds) |
| 10 | Input engine keeps other publishers' text | Partly right (the missing rule is the user's choice of engine) |
| 11 | Uncapped `title` breaks `list-surfaces` | Wrong as stated; the real defect is N7 |
| 12 | Node tree has no total cap | Confirmed with another correction |

New findings from the same angle: N1 to N9. The two most serious problems in this verification are new findings, N1 and N2. Both break a guarantee that the security page states as holding.

Quote accuracy: every quote I checked is exact at its cited line except one. In finding 11, "node props at 65536 (`contracts/actions.wit:57`)" is wrong: line 57 of `actions.wit` is about `request` and linking. The props cap is at `ui.wit:29-30` and `core.wit:56-57`. Two claims in the reviewer's "What I checked" list are wrong too: "The secret path is consistent between the four files" (see N2) and "The `world service` linking rules for reach `local` are sound" (see N1 and finding 1).

---

## Finding 1. An action instance holds `keep`

**Quotes.** All exact: `security.md:176`, `actions.wit:55-57`, `core.wit:267-268`, `core.wit:294`, `store.wit:172-173`.

**Case.** The case holds, and the text is stronger than the reviewer says. `core.wit:266-268` lists `keep` among the imports of the once-per-action instance, so `keep` is linked there. The reviewer missed one line that shows the system means it: `store.wit:170-171`, "a capability received at run time (picker, drop, **action argument**) dies with the instance unless it is put here". Only an action instance receives an action argument. So the contract plans for an action instance to keep its arguments, against "nothing is shared with the running application, and the instance is destroyed afterwards" (`actions.wit:55-56`). That is a contradiction between two files, and attack B follows from it exactly as written: a reversible local action runs automatically (`actions.wit:198`), `keep.put` takes the bound item (`store.wit:179-181`), and the long-lived instance gets it back later.

Attack A is weak as the reviewer frames it, because the kept item already belongs to the same component. The stronger reading is one the reviewer did not give. "`keep` ... read-only when change is `none`" does not say that `get` hands back an item attenuated to read-only. If `get` returns the item with the rights it was kept with, an action of class `none` writes a kept object. Then the declared class is not binding for a local action, which breaks `security.md:177` ("lying about it gains nothing").

**Settled or pending?** Neither. D-035 decides the fresh instance and does not address `keep`.

**Proposed correction.** "The action instance imports no `keep`" closes attack B but has two problems. First, it leaves `store.wit:171` contradicting it. Second, it does not close the path that matters most: under change `reversible` the instance can copy the *content* of the bound object into `home`, which is writable and shared with the long-lived instance (`actions.wit:35-36`, `core.wit:266`). That path is N1.

**Correction I would write.** In the action instance, `keep` offers `get` and `slots` only, and `get` returns the item attenuated to the class. `put` and `forget` answer `denied` in every class. `forget` is refused because losing a kept grant cannot be undone through the journal. `store.wit:171` drops "action argument". The text in C3 below. The copy into `home` is handled by N1.

## Finding 2. `undo` and `journal` address an entry by a bare number

**Quotes.** All exact.

**Case.** The first outcome, where one task reads every task's journal, does not follow. `undo` and `journal` are methods of `resource task`, and `actions.wit:74-76` says a task "carries the delegated rights, the marks, the budget and the journal". `task.journal(...)` therefore returns that task's journal. An id that only means something on a task handle is exactly what rule 2 allows: "a name only exists relative to a handle" (`core.wit:18`). It is the same pattern as a `keep` slot or a `node-id`. The reviewer's claim that "a `u64` is a name, which `core.wit:18` forbids" misreads the rule.

The second outcome is wrong too. `subtask` returns a `task`, which the parent holds, so an entry of the sub-task is undone through that handle.

What remains is small. Nothing says what `undo` answers for an id that is not in this task's journal, and nothing says whether a parent's `journal` lists its sub-tasks' entries.

**Verdict.** Partly right. This is an unsettled case, not a broken guarantee. One sentence fixes it (C15).

## Finding 3. The agent changes the user's memory with no journal entry

**Quotes.** All exact.

**Case.** The attack follows as far as step 4. `forget` and `remember(replaces: ...)` are plain calls that take the task (`agent.wit:171, 174`), and no line puts them in the journal. The user therefore cannot see them in the task's record, and `task.undo` cannot reach them.

Step 5 overstates the damage. The contract itself says "a forget can be undone until then" (`agent.wit:145-146`). By the contract's own words, a forget behaves like a versioned store write: it can be undone while retention lasts.

**Proposed correction.** "Confirmation in every task, as `irreversible`" is wrong. It contradicts `agent.wit:145-146`. It puts a confirmation on an effect the matrix runs automatically for every other undoable local change (`actions.wit:198`, `security.md:203`). It would also add confirmations, which `security.md:276-281` counts as the main cost of the model.

**Correction I would write.** Each `remember` and `forget` is an entry of the task's journal, recorded as an action of the system's memory service with change `reversible` and reach `local`, and `task.undo` can undo it (C10). That gives the call the same treatment as every other reversible local change: automatic, recorded, and undoable.

## Finding 4. Shell surfaces named by string; `focus-surface` is class `none`

**Quotes.** All exact.

**Case, the string ids.** This part does not hold. The shell's actions run in the shell's own process (`shell.wit:11-18`, pending as P-023, recommendation A). The task's right to call them comes from its scope (P-040), not from the id. The id is a name inside the service whose action the task holds, which rule 2 allows.

The proposed fix ("a shell action refuses a surface the caller does not hold") would make the actions useless. The agent holds no `ui.surface` other than its own overlay (`core.wit:363`), and managing windows through actions is the purpose of the file (`shell.wit:1-2`).

**Case, focus.** This part holds. `shell.wit:59-61` justifies class `none` by "the arrangement of the screen, which holds no data". But focus decides where the user's next keys go (`ui.md:109`, and "the focus" is listed as trusted path at `security.md:92`). Here is the attack:

1. The user is typing a password into the window they are looking at.
2. A steered task calls `focus-surface` on another application's surface. That call runs automatically (`actions.wit:197`).
3. The rest of the password lands in the other application.

Nothing in the contract stops this.

**Case, `open-app`.** The claim does not follow. `open-app` passes the application nothing from the task, and the application runs only with the rights the user granted at install.

**Verdict.** Partly right: the focus part only. Correction C7.

## Finding 5. The grant for the rest of a task is keyed on `input` alone

**Quotes.** All exact.

**Case.** The defect is real, but the reviewer's scenario depends on one reading of an ambiguous line. The scenario binds an item named `body` while the input says `"body": null`. Two files disagree on how bindings are named. `actions.wit:31-32` says "the property `name` of `input` is this item": the binding's name is the property name. `core.wit:47-48` and `manifest.wit:29-30` say the property's *value* is the binding's name. Under the second reading the scenario's second call has a different input, so it asks again. That contradiction is N3.

A scenario that works under both readings:

1. In a task not marked `untrusted`, the agent calls `send` with input `{"to":"a@b.example","attachment":"f"}` and binding `f` set to file X. The user confirms, sees X, and chooses "allow for the rest of this task".
2. The agent calls `send` again with the same input string and binding `f` set to file Y, which is private.
3. The string is identical, so the call "runs without asking" (`actions.wit:211-213`).

On the journal: `bound` records the object id and version, so the record does name what left. But the version stays readable only "while that entry is undoable" (`store.wit:28-30`), and an external send is never undoable. Its content can therefore be dropped by retention, which breaks "so the user can see what left" (`security.md:287`). A digest, as the reviewer proposes, would not show the user anything. Keeping the version readable would.

**Correction.** C4: the grant also covers the bound items (same object at the same version), and a version bound to an external entry stays readable as long as the journal keeps the entry.

## Finding 6. The progress note adds no mark

**Quotes.** All exact.

**Case.** Confirmed. Progress is the only path in `tasks` from a third party to the agent that adds no mark. "The system never feeds it to a model as trusted" (`actions.wit:50-51`) cannot be enforced: the agent component reads the stream, and the agent is outside the trusted base (`security.md:135`).

The scenario needs one fix. Once the agent reads the reply of `sync`, the reply marks the task `untrusted` (`actions.wit:133-134`). The attack therefore works only if the action keeps its future open while it writes progress, or if the agent acts before reading the reply. An untrusted agent may do either. Whether the final external read is then confirmed depends on whether the `reveal` reply carries `private`, which the contract never settles (N9).

**Proposed correction.** A `provenance` field in `record progress` is awkward. The same record is written by the action on the application side (`actions.invoke`), so the action would fill a field that the system then overwrites. One sentence saying that reading progress adds marks is enough (C8).

## Finding 7. The decision table has no row for the scope

**Quotes.** All exact.

**Case, `invoke`.** This part does not follow. `actions.wit:186` defines the scope as "actions this task may invoke". The task "carries the delegated rights" (line 75), and `denied` is "the held rights ... do not allow this" (`core.wit:107`). An action outside the scope is therefore one the task may not invoke, and step 3 of the attack ("the table says runs") ignores the definition.

**Case, the list arguments.** This part holds. `subtask(actions)`, `inference.request.tools` and `choose(candidates)` each take a list that the caller supplies. The text says what the list should contain, but not whether the system refuses an entry outside the scope, drops it, or serves it. Making it explicit costs one clause.

**Verdict.** Partly right. Correction C14, which also adds the sentence for `invoke` for clarity.

## Finding 8. The update table ignores `os-item` and `os-secret`

**Quotes.** All exact.

**Case.** The gap is real: neither keyword falls into any of the three update buckets (`manifest.wit:45-54`). Both attacks are wrong, though.

Attack A says the widened rights reach "every document the user hands the app through the picker, a drop or the clipboard". That is wrong for three reasons:

- `os-item` governs action arguments only. The picker is governed by `pick-request.want` (`store.wit:207-208`), and a drop is read-only (`catalog.wit:210`).
- Attenuation only narrows (`manifest.wit:30-31`, `store.wit:90-92`). The action receives at most what the task holds, and objects handed over in a request are read-only (`actions.wit:101-103`).
- The class still caps the result.

What really changes is that an action of class `reversible` can now write items the task holds with write. That stays inside a class the user already accepted, and versioned writes can be undone. It is still worth classifying.

Attack B has the direction reversed. Adding `os-secret` narrows who can fill the property: the model and the agent no longer can, only a secret field typed by the user can. That already reads as "an input constraint narrowed", which is refused. The dangerous change is *removing* `os-secret`. The property is then written in the journal and can be filled by the model, while existing secret fields keep feeding it. That is the same hole as N2.

**Correction.** C11: a right added to `os-item` counts as a new right; adding, removing or changing the kind of an `os-item`, and adding or removing `os-secret`, are refused.

## Finding 9. An empty `network` scope

**Quotes.** All exact.

**Case.** This is not a contradiction. `core.wit:242-243` hands granting to the manifest ("Granting is the manifest's (os:manifest)"), and the manifest defines an empty scope as any host. The two lines do not disagree.

The reviewer's second point holds: an empty list is what a publisher writes by omission, and it is the unbounded case.

The proposed correction (at least one host) is wrong. It forbids any third-party application that needs arbitrary hosts, such as a feed reader, which P-067 does not exclude.

**Correction.** C16: write "any host" as an explicit `["*"]` and refuse an empty scope. Accidental omission is then impossible, and the any-host case still exists.

## Finding 10. A third-party input engine keeps the surrounding text

**Quotes.** All exact.

**Case.** The engine receives every key while it is active (`input.wit:93-94`), so the keys themselves are the content. The surrounding text adds at most 4096 bytes that were written before. Keeping what it learns in `home` is the feature (`input.wit:110`), not a leak. Every input-method system I know gives the engine the surrounding text (Wayland's input-method protocol, Android's input method service); that is from memory, not checked today.

The process boundary (`security.md:22`) protects address spaces. It is not a promise that no component the user chose sees another publisher's text. What the contract really lacks is the rule that makes this acceptable: nothing says that a third-party engine runs only after the user chose it.

**Proposed correction.** The reviewer's correction would break the engine. A read-only `home` means it cannot learn, and "a dictionary update is an action with a class" needs a task, which typing does not have.

**Verdict.** Partly right. Correction C17. Step 5 of the attack (typing the remembered text into another field) leads to a real defect the reviewer did not see: N4.

## Finding 11. An uncapped `title` breaks `list-surfaces`

**Quotes.** All exact except the wrong citation `actions.wit:57`, noted above.

**Case.** The attack does not follow. Step 1 says an application "sets its window title to 100 kB". But the reviewer also notes that no interface carries a title, and that is right: `ui.surface` has no title function. An application therefore has no way to set any title, short or long. The count of surfaces is not the application's either: "The shell gives the app a surface" (`core.wit:339-341`), and the application cannot create one.

The real defect is that `surface-info.title`, "The owner's text" (`shell.wit:34`, `agent.wit:289`), has no source anywhere in the contract. That is N7.

**Verdict.** Wrong as stated.

## Finding 12. The node tree of one surface has no total cap

**Quotes.** All exact.

**Case.** Confirmed as an unsettled case. Per-call caps only; `remove` is the only way down; the compositor holds the tree; no line says whose memory pays for it.

**Proposed correction.** The 4096-node cap is too low for an ordinary application. A file tree is made of `tree-item` nodes, and the catalogue has no on-demand tree; only `virtual-list` is fed on demand. A node count also leaves the bytes unbounded: 4096 × 64 KiB of props is 256 MiB.

**Correction.** Charge the tree to the owner's memory, as D-073 charges memory to whoever creates it, and answer `quota-exceeded` past that budget. The same file also caps props per node and not per call; fixing that is N8. Correction C12.

---

## New findings

### N1. A local action passes the user's data to the long-lived instance, which has the network. Breaks a guarantee.

- "For an action of reach `local`, the declared class is therefore binding, and lying about it gains nothing." (`security.md:177`); walk-through 3: "An application declares an upload as `none`, `local`. ... **Stops at** linking" (`security.md:297`).
- The action instance gets "/home" as "the request's `home`" (`core.wit:266`). `home` is "The component's own collection, attenuated the same way" (`actions.wit:35-36`), so it is writable when change is `reversible`. The long-lived instance's "/home" is the same collection (`core.wit:256`), and it holds the network with the manifest right "network" (`core.wit:259-260`).

Scenario:

1. `pub/x` asks for "network" ("to check for updates") and declares `import` as change `reversible`, reach `local`.
2. A steered task calls `task.invoke({app:"pub/x", name:"import"}, ..., [<the user's file>])`. This runs automatically and can be undone (`actions.wit:198`).
3. The instance copies the file's bytes into `home`.
4. Later, the long-lived instance reads `home` and uploads the content.

No confirmation appears at any step. The long-lived instance is in no task, so the matrix never applies to it. Kernel marks do not stop it either. The long-lived instance becomes marked when it reads the marked record (`kernel-interface.md:1097-1098`), but neither the contract nor `network.md` says the network service refuses anything to a marked process. Walk-through 3 is defeated by declaring the upload `reversible` instead of `none`. The same path is open to a legitimate syncing application, whose writes really do reach a server.

Removing `keep` from the instance (finding 1) does not close this.

**Correction (C2).** In a package that holds "network", an action of change `reversible` or `irreversible` counts as reach `external` for the confirmation table. The cost: write actions of syncing applications are confirmed. That is honest, because their effect does leave the machine. The alternative is to confine the long-lived instance of a marked component, which no document designs yet. This reopens a line of `security.md` that rests on D-035, so I recommend it and leave the choice to the two owners.

### N2. A secret field can feed a property that is not secret. The password then reaches the journal and the agent. Breaks a guarantee.

- "Never: ... the value of a secret field (it never reaches the agent)" (`agent.wit:21-22`); "the value never reaches the surface owner, only an action through `source.input`" (`catalog.wit:92-93`).
- `os-secret` is "filled only from a secret field" (`manifest.wit:32-33`). That restricts the property to one source; it does not restrict where a secret field may flow. The journal writes as null only the "Secret properties ("os-secret", manifest.wit)" (`actions.wit:148`), and the agent reads the journal (`actions.wit:231-233`). The overlay checks for a secret field are that the task is not `untrusted` and that the buttons invoke actions of one application (`catalog.wit:94-98`). Neither check concerns the target property.

Scenario:

1. In a task with no mark (for example, a hostile local model, `security.md:104`), the model draws a `field` of kind `secret` and a button invoking `pub/notes.add` with `{"name":"text","value":{"input":"pw"}}`. `text` is a plain string.
2. The update is accepted: the task is unmarked and only one application is named.
3. The user types the password.
4. The action runs automatically (reversible, local). The journal holds the password in clear, and `task.journal` returns it to the agent.
5. An external read of change `none` carrying the password in its address runs without confirmation unless the task is both `private` and `untrusted` (`actions.wit:200-202`). The journal adds no mark that the contract states.

The reviewer listed this path as checked and consistent.

**Correction (C1).** The system refuses a button that reads a secret field into a property without `os-secret`, and an update may neither add nor remove `os-secret` (C11).

### N3. Two rules for naming a binding. Contradiction.

- "Storage arguments, by argument name: the property `name` of `input` is this item." (`actions.wit:31-32`): the binding's name is the name of the property.
- "resource never encoded: the field holds the `name` of a `binding` carried next to the string" (`core.wit:47-48`) and "the value is the name of a binding carried next to the JSON" (`manifest.wit:29-30`): the binding's name is the *value* of the property.

The two rules give different inputs for the same call. They decide whether the confirmation, which is drawn "from ... this exact input" (`actions.wit:205-206`), shows which item is attached. They also decide whether finding 5's original scenario works.

**Correction (in C4).** Follow `core.wit`. A binding that no property names, or a name that no binding carries, is `invalid`.

### N4. An input engine can make up keys. Breaks a guarantee.

- "Give a key back: the field receives it as if no engine were active." (`input.wit:103-104`), with the type `forward(key-event)`, which accepts any key. Against: "Global shortcuts and input injection are capabilities that nobody has by default." (`ui.md:109`).
- A forwarded key reaches a `canvas` as a "key" event (`catalog.wit:194-196`). An event's provenance is "user" for what the user typed (`ui.wit:45-46`), and nothing marks a forwarded key differently.

Scenario: a third-party engine active on an application's `canvas` field forwards "Enter", "Control+A" or "Delete" that the user never pressed, and the application acts on them as the user's keys. On the agent's bar, the engine commits text and then forwards "Enter", which sends a request the user never submitted. That request starts with an untrusted part, but it is still a task the user never asked for, and its automatic cells run.

**Correction (C5).** `forward` returns only a key that this activation received and has not yet given back. Any other key ends the activation.

### N5. A button on an application's surface invokes "through the task", and an application has no task. Unsettled case.

- "With an action: activating it invokes the action through the task, under the same rules as `task.invoke`" (`catalog.wit:82-83`); `update` checks "actions within the task scope" (`ui.wit:56`). The agent catalogue is "the base of every application" (`catalog.wit:18`), and `world app` has no task (`core.wit:329-343`).
- State: an application draws a button invoking another publisher's action, with literal arguments and items it holds. Actor: the user clicks. The text allows two outcomes. (a) The update is refused, because there is no scope to check against, and applications cannot use action buttons at all. (b) The update is accepted, and the call runs with no marks, no scope and no journal, and the click stands in for a confirmation. That would make another component act on the application's input with nothing recorded.

**Correction (C9).** On an application surface, the click opens a task for that one call. Its scope is the one action. Its marks are those of the owner (`untrusted` unless the owner is the system) plus the marks of the bound items. It is journalled, and the matrix applies; the click is not a confirmation.

### N6. An action instance can write the clipboard. Breaks the class binding.

- "Puts items on the clipboard. Each needs `share`." (`store.wit:215`). Unlike `pick` ("`denied` if the caller has no visible surface", `store.wit:212`) and `paste` ("Answered only right after a paste gesture", `store.wit:225-226`), `copy` has no condition. `world app` imports `exchange` (`core.wit:332`), and the list of what the action instance gets (`core.wit:262-275`) says nothing about `exchange`.

Scenario: an action of class `none`, `local` of an `app` component calls `exchange.copy` on an object it can share, such as one opened from its `home`. The user's clipboard is replaced, and the old content cannot be brought back. That is a change under class `none`. The user's next paste then carries the application's object into another application. The same call from a long-lived instance without any gesture is the classic clipboard-replacement trick.

**Correction (C6).** `copy` is answered only right after a copy or cut gesture of the user on the caller's surface, and is therefore always denied in an action instance.

### N7. A surface's title has no source. Blocks building.

`surface-info.title` is "The owner's text" (`shell.wit:34`). `accessibility.surface-info.title` is "the owner's text" as well, and reading it adds marks (`agent.wit:289, 294`). No function of `ui.surface` (`ui.wit:52-68`) and no field of the manifest is described as setting it. An implementer has to invent the source and its cap.

**Correction (C13).** Add `surface.set-title` with a 256-byte cap; "" falls back to the package title.

### N8. The props cap is per node in `ui.wit` and per call in `core.wit`. Contradiction.

- "bytes by value in one call (object read, action input and output, node props, one inference message) 65536", justified as "one copy by value (rule 6: one Wasm page)" (`core.wit:54-57`).
- "props ... At most 65536 bytes" for each node (`ui.wit:29-30`), with "At most 1024 nodes per call" (`ui.wit:53-54`).

Under the per-node reading, one `update` copies up to 64 MiB by value, which goes against the rule the cap is meant to serve. This is the main multiplier in finding 12.

**Correction (in C12).** The cap applies per node and to all the nodes of one `update` together.

### N9. No rule says which store objects carry `private`. Breaks a guarantee.

- The matrix and D-036 depend on `private`: "none / external: runs unless marked private" (`actions.wit:200-202`); "the marks are Meta's [A] and [B]" (`security.md:224`).
- An object's marks come from its writer: "Stamped by the system at each write: who wrote, under which marks" (`store.wit:42-43`). A record is "read back marked" only if "written by a marked call" (`kernel-interface.md:1098`). The contract adds `private` explicitly in two places only: memory entries ("plus `private` (the memory is the user's data)", `agent.wit:163-164`) and accessibility reads ("`private` always", `agent.wit:287-288`).

A user's document written in an editor's long-lived instance is written outside any task, so it carries no marks. A password vault in an application's `home` carries none either. A task that reads such a document, or receives an action reply computed from it, therefore never gains `private`. The one cell that depends on `private`, an external read in an `untrusted` task, then runs automatically. Walk-through 2 ("It reads the file, which adds `private`", `security.md:296`) assumes a rule the contract does not contain. This finding also decides the ending of finding 6's scenario.

**Correction (C18).** Every object of the user zone or of an application zone carries `private`, whoever wrote it.

### Seen outside the angle, not judged

`network.md:30` says an application asks for a listening capability in its manifest, but `manifest.wit:69-79` lists no such right, and an unknown right makes the installer refuse the package. As written, a server has no way to get a port.

---

## Corrections to the WIT files, in order of severity

Each one names the file, the place, and the exact text. The companion edits to `security.md` are noted where a WIT change makes a line of it false.

**C1 (N2). `catalog.wit`, after line 93** ("only an action through `source.input`."), add:

```
    /// A secret field feeds only an argument whose property carries
    /// "os-secret" (os:manifest): an update whose button reads a secret field
    /// into any other property is refused (`invalid`).
```

**C2 (N1). `core.wit`, after line 270** ("reach `local`: every network import fails;"), add:

```
///   - in a package whose manifest holds the right "network", an action of
///     change `reversible` or `irreversible` counts as reach `external` for
///     the confirmation table (`tasks.invoke`): what it writes into `home`
///     reaches the long-lived instance, which has the network;
```

Companion edit: `security.md:177` should read "For an action of reach `local` in a package without the right "network", ...".

**C3 (finding 1). `core.wit:266-268`.** Replace

```
///   - "/home" is the request's `home`, "/tmp" ends with the instance;
///     `keep`, "/home" and the bound objects are read-only when change is
///     `none`;
```

with

```
///   - "/home" is the request's `home`, "/tmp" ends with the instance;
///     "/home" and the bound objects are read-only when change is `none`;
///   - `keep`: `get` and `slots` only; `get` returns the item attenuated to
///     the class (read-only when change is `none`); `put` and `forget`
///     answer `denied`, so nothing the request carried outlives the
///     instance;
```

In `store.wit:170-171`, replace "a capability received at run time (picker, drop, action argument) dies with the instance unless it is put here." with "a capability received at run time (picker, drop) dies with the instance unless it is put here; an action instance cannot put (core.wit, `world service`)."

In `actions.wit:56-57`, replace "It holds only what `request` carries" with "It holds only what `request` carries, and reads `keep` (see `world service`)". Companion edit: `security.md:176` lists `keep` (read only) among what the instance holds.

**C4 (finding 5 and N3).** In `actions.wit:31-33`, replace

```
    /// Storage arguments, by argument name: the property `name` of `input`
    /// is this item. Attenuated by the system to the action's class
    /// (read-only when change is `none`).
```

with

```
    /// Storage arguments. A property of `input` that carries "os-item"
    /// holds the name of one of these bindings (core.wit, value encoding); a
    /// binding that no property names, or a name that no binding carries, is
    /// `invalid`. Attenuated by the system to the property's "os-item"
    /// rights and to the action's class (read-only when change is `none`).
```

In `actions.wit:211-213`, replace "the user may allow an action with this exact input for the rest of a task not marked `untrusted`, so a repeat runs without asking;" with "the user may allow an action with this exact input and the same bound items (the same object at the same version, the same collection) for the rest of a task not marked `untrusted`, so a repeat runs without asking, and a call that binds another item or another version asks again;".

In `store.wit:28-30`, after "while that entry is undoable." add "Every version bound to a journal entry of reach `external` stays readable as long as the journal keeps the entry, so the user can see what left."

**C5 (N4). `input.wit:103-104`.** Replace "/// Give a key back: the field receives it as if no engine were active." with

```
    /// Give a key back: only a key this activation received and has not yet
    /// given back; the field receives it as if no engine were active. Any
    /// other key ends the activation: an engine cannot make up a key.
```

**C6 (N6). `store.wit:215`.** Replace "/// Puts items on the clipboard. Each needs `share`." with

```
  /// Puts items on the clipboard. Each needs `share`. Answered only right
  /// after a copy or cut gesture of the user on the caller's surface;
  /// `denied` otherwise, and always in an action instance, which has none.
```

**C7 (finding 4). `shell.wit`, after line 61** ("sees and can redo by hand."), add:

```
    /// `focus-surface` also decides where the user's next keys go: it
    /// answers `busy` while the user types (a key in the last second,
    /// starting value to calibrate) and `denied` for the agent's bar, and
    /// the compositor drops keys for 500 ms after the move, as a
    /// confirmation ignores input after it appears.
```

**C8 (finding 6). `actions.wit:50-52`.** Replace "Short text for the user. Third-party text: the system never feeds it to a model as trusted." with "Short text for the user. Third-party text: reading a progress value adds to the task the marks the instance holds at that point (at least `untrusted` for a third-party application), as reading the reply does." In `actions.wit:221`, replace "Whatever the action returns" with "Every progress value, and whatever the action returns".

**C9 (N5). `catalog.wit:82-83`.** Replace "With an action: activating it invokes the action through the task, under the same rules as `task.invoke`; the surface owner then gets" with

```
    /// With an action: activating it invokes the action through a task,
    /// under the same rules as `task.invoke`: on the agent's overlay, the
    /// overlay's task; on an application surface, a task the system opens
    /// for this one call, whose scope is that action and whose marks are
    /// those of the owner (`untrusted` unless the owner is the system) plus
    /// those of the bound items, journalled as any task. The click is not a
    /// confirmation. The surface owner then gets
```

In `ui.wit:56`, replace "actions within the task scope" with "actions within the task scope (on an application surface, any action: see `button`)".

**C10 (finding 3). `agent.wit`, before line 170**, add:

```
  /// Each call of `remember` and `forget` is an entry of the task's journal,
  /// as an action of the system's memory service of change `reversible`,
  /// reach `local`: `task.undo` forgets the new entry, or restores the
  /// forgotten one until the retention period has passed.
```

**C11 (finding 8). `manifest.wit:47-54`.** In "refused", after "an output property removed or its values widened", add "; "os-item" added to or removed from a property, or its kind changed; "os-secret" added or removed". Replace "a class raised (`none` to `reversible` or `irreversible`, `local` to `external`) or a host added:" with "a class raised (`none` to `reversible` or `irreversible`, `local` to `external`), a host added, or a right added to an "os-item":".

**C12 (finding 12 and N8).** In `core.wit:56-57`, replace "node props, one inference message)" with "node props of one node and of all the nodes of one `update` together, one inference message)". In `ui.wit`, after line 54 ("At most 1024 nodes per call."), add "The tree the system holds for a surface is charged to the owner's memory budget (D-073); past it, `update` answers `quota-exceeded` and changes nothing."

**C13 (N7).** In `ui.wit`, inside `resource surface`, add:

```
    /// The title shown in window lists and read through `accessibility`:
    /// plain text, at most 256 bytes; "" (the default) shows the package
    /// title.
    set-title: async func(title: string) -> result<_, error>;
```

In `shell.wit:34` and `agent.wit:285-289`, add after "the owner's text": ", set by `ui.surface.set-title`, at most 256 bytes". In the caps list of `core.wit`, add "title of a surface (bytes) 256".

**C14 (finding 7).** In `actions.wit`, after line 224, add "An action outside the scope answers `denied`, whatever its class." In `actions.wit:238`, after "A sub-task whose scope is the given subset of this one", add "(`invalid` if `actions` names one outside this task's scope)". In `agent.wit:90-91` and `agent.wit:133-134`, add "a ref outside the task's scope makes the call answer `denied`".

**C15 (finding 2). `actions.wit:227` and `231`.** Replace "Undoes one journal entry." with "Undoes one entry of this task's journal; `not-found` for any other id (an entry of a sub-task is undone through the sub-task)." Replace "Entries with id greater than `after`" with "Entries of this task's journal, not its sub-tasks', with id greater than `after`".

**C16 (finding 9).** In `manifest.wit:73`, replace "scope: the hosts, empty for any" with "scope: the hosts, or ["*"] for any host; an empty scope is refused". In `core.wit:260`, replace "to the hosts it lists." with "to the hosts it lists ("*": any host)."

**C17 (finding 10). `input.wit`, after line 110**, add:

```
  /// A third-party engine is activated only for the purposes and languages
  /// for which the user chose it in the settings; the system's own engine
  /// serves every other field.
```

**C18 (N9). `store.wit:42-43`.** Replace "/// Stamped by the system at each write: who wrote, under which marks." with

```
    /// Stamped by the system at each write: who wrote, under which marks.
    /// Every object of the user zone or of an application zone also carries
    /// `private` (the user's data), whoever wrote it; objects of the system
    /// zone and of shared packages do not.
```

C18 is ranked last only because it changes how often confirmations appear. By the harm it prevents, it belongs with C1 and C2. The two owners should read C2 and C18 together: both change the cost of the matrix.

## What I checked, and what I did not

Checked:

- Every quote of the twelve findings, at its line, in the nine WIT blobs at `aab7417` and in the documents on `main` at `c93a623`.
- The decisions D-011, D-035, D-036, D-056 and D-073.
- The pending entries P-022, P-023, P-036, P-040, P-042, P-050 and P-067, and the table of all pending entries for anything on `keep`, the journal, memory, surfaces, input engines or `private`. None covers a finding here except P-023 (where shell actions run), P-040 (who chooses the scope) and P-067 (network scope), and none of those settles the point at issue.
- The kernel rules for marks (`kernel-interface.md:1067-1099`) and `network.md:17-33`.

Not checked:

- I did not run `verify` or `wasm-tools`. I did not read `deps/`, `mcp.md`, `storage.md` beyond a search for marks, or `scheduling.md`.
- I tested no attack on running code: each scenario follows from the quoted lines.
- The remark on other input-method systems in finding 10 is from memory.
- The numbers I propose (one second and 500 ms for focus, 256 bytes for a title) are starting values, not measurements.
