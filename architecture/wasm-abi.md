# Wasm ABI and developer journey

Statuses are defined in the [README](../README.md#status-legend). Sections with no status line had none in the source.

Terms: **Wasm** is WebAssembly. A **component** is a Wasm binary in the Component Model format, with typed imports and exports. **WIT** is the language that describes those interfaces; a **world** is the set of interfaces a component imports and exports. **WASI** is the family of standard system interfaces for Wasm.

## Application ABI

**Decided.** Wasm only, through the Component Model, WIT and WASI 0.3. WASI 0.2 and 0.1 are accepted through adapters, to widen the range of languages.

`os:core` requires WASI 0.3: Rust first, the other languages when their tools get there (**Decided**, 14 November 2026). There is no WASI 0.2 variant of the package.

## ABI stability

**Decided.** WIT worlds are versioned and stable, for applications as well as for services and drivers. System calls are behind a code page supplied by the kernel and are never called directly (see [kernel.md](kernel.md#base-decisions)).

Promise: a published component keeps running. A corpus of old binaries in CI verifies it.

## ABI rules

1. Any call on a capability can fail, because it is revocable.
2. No global name: a path exists only relative to a handle.
3. The identity of a component is its publisher key plus its name.
4. Asynchronous is the default.
5. Objects of the store have stable identifiers.
6. Large volumes go through buffer handles or streams, never by value: this is the only copy that the compiler cannot remove.

## core.wit

The contract lives in `contracts/`. It holds three packages, all at version 0.1.0.

| Package | File | Content |
|---|---|---|
| `os:core` | [core.wit](../contracts/core.wit) | Shared types (errors, rights, effect class, marks, provenance) and the three worlds |
| `os:core` | [store.wit](../contracts/store.wit) | Storage (`store`), capabilities kept across launches (`keep`), object exchange (`exchange`) |
| `os:core` | [ui.wit](../contracts/ui.wit) | Surfaces and the open interface tree |
| `os:core` | [actions.wit](../contracts/actions.wit) | Actions on the application side, tasks on the agent side, agent stubs |
| `os:catalog-agent`, `os:catalog-app` | [catalog.wit](../contracts/catalog.wit) | The two catalogue levels, each versioned on its own (see [ui.md](ui.md#catalogue)) |

The first draft, a single file, was validated by `wasm-tools 1.263`.

### Worlds

| World | For | Imports | Exports |
|---|---|---|---|
| `service` | A component without interface: service, server, background work. No function assumes a screen, a GPU, a keyboard or an agent | `keep` | `actions`, `start`, `suspend`, `resume` |
| `app` | A component that draws with the catalogue. Includes `service` | `exchange`, the two catalogue levels | `show` |
| `agent` | The agent | The agent catalogue level, `inference`, `memory`, `audio` (stubs) | `handle` |

Life cycle:

- `start(home)`: first launch, or launch with no saved state. `home` is the component's own collection.
- `suspend()`: save state into `home` now. Once it returns, the system may destroy the instance at any time. It is the only path that crosses devices and architectures, so a component saves data, not memory.
- `resume(home)`: called instead of `start` on a new instance when `suspend` completed before, possibly on another device.
- `show(surface)`: the shell gives the application a surface. It is called after `start` or `resume`, zero or more times: an application can run with no surface and get one later, or several.

The same component is instantiated in two ways: long-lived (`start` or `resume`, later `suspend`), and once per action, as a fresh instance on which the system calls only `actions.invoke` (see [agent.md](agent.md#effect-class)).

### Actions

Actions are what makes a component drivable by the agent. Every component exports the `actions` interface, which only executes (`invoke`). The declaration of the actions (name, description, input and output schema, effect class) is in the signed package manifest; there is no `list-actions` function. WIT has no free annotations, so the manifest is a separate contract. That contract does not exist yet (**Open**; see [open questions](../research/open-questions.md#open-items-in-the-contract-files)).

### Growth and encoding

- Adding a case to a variant, an enum or flags, or a field to a record, breaks the ABI (from memory in the source's verification list), and the system serves every published version of `os:core`.
- What is expected to grow is therefore open: `error` is a wide list with a fallback case `other`; node kinds, event kinds, journal states and principals are strings. Adding a kind to a catalogue is a minor version, not a break.
- A typed value carried as a string (action input and output, node props, event value) is UTF-8 JSON. Resources are never encoded: a field holds the name of a binding carried next to the string.
- String formats are specified in the files: component identity, object identifier, entry names, the grammar of the filter of `query`.
- WIT has version annotations (`@since`, `@unstable`, `@deprecated`), but no free annotations.

### Revision

**Decided, 14 November 2026**: a complete revision, as the first contract of step 0 of the [build order](../plan/roadmap.md#build-order). The files at version 0.1.0 carry it:

- `suspend` and `resume` (see [platform.md](platform.md#process-state-suspend-resume-and-snapshots));
- the effect class in two fields, and actions in the manifest (see [agent.md](agent.md#effect-class));
- a wide list of errors with a fallback case;
- `sync`, versions, metadata, rights held, persistence of a received object (`keep`);
- object picker, drag and drop, clipboard (see [ui.md](ui.md#giving-an-object-to-an-application));
- provenance on objects and results;
- `start` without a mandatory surface (the surface comes through `show`);
- an open encoding for the interface tree;
- specified string formats.

Still open (**Open**):

- Driver interfaces, and the management of surfaces by the agent, are not in the contract. The audio interface of the agent is a stub.
- The items marked `OPEN` in the contract files are listed in [open questions](../research/open-questions.md#open-items-in-the-contract-files).

## Compile service

**Aligned; optimised tier Open.** The compile service is the only producer of machine code (see [security.md](security.md#chain-of-trust)).

- Three tiers, in the manner of ART (the Android runtime), with the switch made between two launches by the project's compile service (Wasmtime does not switch by itself).
- Launch without installing: the baseline compiler Winch, almost instant.
- Installation: Cranelift, ahead of time.
- Background: an optimised tier, to build entirely. No LLVM back end handles components, no tool lowers a component into plain modules, and Cranelift has no profile-guided optimisation.
- No JIT in applications.
- Overhead measured on libsodium in 2026: 2.41 times native for Wasmtime, 1.46 with `wide-arithmetic` (see [gates](../plan/gates.md#overhead-gates)).
- Merging the components of one publisher: the `meld` tool, young. Composition by `wac`.
- Machine code is cached by component hash, compiler version and instruction set.
- A component does not map a blob into its memory (see [memory.md](memory.md#paging-in-user-space)).

### Optimised tier

**Open; deferred until after the alpha** (**Decided**, 14 November 2026). Leads to try: wasm2c then LLVM (requires decomposing the component, handling the stack switches of async, and LLVM on the machine or a remote service); the Cranelift inliner between components; weval for interpreted languages.

### Performance levers

In addition to the three compilation tiers. Verified 13 November 2026 unless noted.

- `wide-arithmetic` proposal: on the libsodium bench, Wasmtime 46 goes from 2.41 to 1.46 times native, Wasmer 7.1 from 2.08 to 1.33. The bench is cryptographic, so this gain does not generalise as it is; it shows that part of the gap comes from missing instructions.
- Segue: the base of the memory in a segment register, median gain of 7.8 % on SPEC. An option of Wasmtime.
- Memory protection keys (ColorGuard): less address space reserved per instance. An option of Wasmtime.
- Cranelift inliner, including between components: 1.26 times on one bench, disabled by default at its release.
- Translation of Wasm to C then a native compiler (wasm2c): at the level of the best runtimes. A serious lead for the optimised tier, because it reuses LLVM with no back end to write.
- Interpreted languages (JS, Python, Lua): partial evaluation by weval, 2 to 5 times faster than the interpreter, still in beta.
- SIMD and relaxed SIMD, tail calls: from memory.

NASA's runtime (SpaceWasm, JPL) is a Wasm 1.0 interpreter designed for safety and determinism, not for speed: nothing to take from it on this point.

### Cost of async

**Open.** The asynchronous model of components costs about 3.5 times on synchronous calls in Wasmtime; optimisation is in progress upstream. To measure on the project's interfaces.

### Threads

**Open.** WASI 0.3.0 (11 June 2026) has no threads. Cooperative threads are expected in a 0.3.x (Rust aims at the end of 2026, date uncertain); preemptive threads later, tied to `shared-everything-threads`, which is not implemented in Wasmtime (calendar verified 14 November 2026 by web search). Until then, the parallelism of a Wasm application goes through several instances, which suits one kernel per core. Native code (Ladybird, inference) needs real threads from the start.

## How userland builds against the OS

- **Wasm components** (applications, agent): the standard Wasm target, with no toolchain specific to the OS.
- **Native Rust code**: a target `x86_64-unknown-dodos`, and a platform crate with two implementations, hosted (Linux, macOS) and native. Services are written against it and compile for both.
- **Native C and C++ code** (web engine, Skia, Mesa, SQLite, drivers): mlibc with the project's system layer, libc++, cross-compilation by clang or `zig cc`.
- **Rust standard library on the target**: mandatory early; it is in step 2 of the [kernel track](../plan/roadmap.md#kernel-track). Shortest route: plug it onto mlibc, which is ported anyway (supposed precedent: Managarm; from memory). The Rust support of seL4 serves as a model for the platform crate without the standard library.
- **POSIX as a library**: a file descriptor is a handle, and each process receives a name table from its parent. There is no global file system.
- **Static linking** first. Loading of executables is done in user space.
- Porting Ladybird: see [web.md](web.md#porting-ladybird).

## Developer journey

The SDK is the hosted userland: a developer needs neither DodOS nor a virtual machine.

- **One tool, `dodo`**: `new`, `run` (launches the component on Linux or macOS in a window), `test`, `actions` (calls the exported actions as the agent would), `package` (blobs and signed manifest). `dodo run <url>` launches without installing.
- **Languages**, state verified 13 November 2026:

  | Level | Languages |
  |---|---|
  | WASI 0.3 components | Rust only (target `wasm32-wasip3`, tier 2 since Rust 1.100) |
  | WASI 0.2 components | C and C++ (wasi-sdk), Go and TinyGo, Python (`componentize-py`), JS (`ComponentizeJS`, or the lighter `componentize-qjs`), C# in pre-release |
  | WASI 0.1 modules only, to wrap with the standard adapter | Zig, Swift, Ruby |
  | No path today | Kotlin, Java and Dart (WasmGC is not yet compatible with the async of components in Wasmtime), PHP, Lua, Elixir |
  | Not verified | Odin |

  The WASI 0.1 adapter for Zig and Swift is "from memory". Limits of Wasm: no JIT in a component, no parallelism in WASI 0.3 (several instances instead).
- **Two libc, two sides**: wasi-libc for C compiled to Wasm (applications), mlibc for native C (system). It is not a choice between the two.
- **Four ways to draw**, from the simplest to the freest: the DodOS catalogue (the same as the agent's), the system's interface library (gpui) compiled to Wasm, a web application (HTML, CSS, JS in LibWeb), raw WebGPU.
- **Tauri applications**: the model is the same (web interface in the system's engine, Rust back end). The back end is recompiled as a Wasm component if its dependencies allow it.
- **Porting existing code**: wasi-libc. Files there are already pre-opened handles, which matches rule 2.
- **Debugging**: DWARF in Wasm with lldb in hosted mode. Debugging is a capability per component (see [security.md](security.md#permissions)). Traces: the black box (see [platform.md](platform.md#crash-and-shutdown)), exported in a standard format (Perfetto, to verify) (**Proposed**).
- Web applications: see [web.md](web.md#web-applications).

### Rescue tools

- uutils coreutils as Wasm components (target `wasm32-wasip2` since 0.10; a few tools do not compile yet). findutils targets only WASI 0.1.
- Shell: brush, which compiles for `wasm32-wasip3` experimentally; nushell does not compile for WASI.
- They are present in the recovery slot, usable by the project and by the agent.

### Terminal and shell

**Proposed, 14 November 2026, to validate.** The terminal is an application. The shell: port an existing one with structured data, whose commands are the actions; no new language. Nushell was the candidate; it is withdrawn until a native port is verified, because Nushell does not compile for WASI (**Decided**, 14 November 2026).

### Compiling on DodOS

**Proposed.** Not a goal of version 1; development is done from Linux and macOS with the hosted userland.

## Native applications

**Aligned.** Set aside for now: Wasm and WIT remain the only ABI of applications. A native ABI would cost more than it brings (one binary per architecture, a libc and an executable format to keep stable, the port of each runtime). To reopen only before a concrete need.

## Electron applications

Not planned (**Decided**, 14 November 2026). A compatibility layer (an `electron` module and `node:` modules backed by capabilities, rendering in LibWeb) is possible for applications with no native module. The web version of the application is the default path.

## Tests

The WASI suite is the authoritative test suite for the ABI (see [plan/verification.md](../plan/verification.md#authoritative-test-suites)).
