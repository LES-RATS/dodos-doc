# User interface

Statuses are defined in the [README](../README.md#status-legend). Sections with no status line had none in the source.

This file covers the compositor, the shell, the agent's interface, the design system and its catalogue, input, accessibility, audio, localisation and settings.

## Compositor

**Decided.** The compositor is the system program that assembles the finished image buffers of all programs into what the screen shows.

- A small system compositor in Rust, written by the project, which assembles finished buffers. The Compositor of Ladybird, the shell and the GPU service are its clients.
- From the first version: shared buffers without copy; direct scanout of a full-screen surface (the surface's buffer is sent to the screen as it is, with no composition and no added frame); and a frame callback with a deadline, so that a client's content leaves at the same refresh.
- Direct scanout stays decided subject to the GPU trial (**Decided**, 14 November 2026; see [gpu.md](gpu.md#trial-at-the-head-of-the-track)).
- Direct scanout stops, and the compositor composes, whenever a confirmation, the secure attention view or a full microphone, camera or capture indicator must be on screen, or any other surface above the full-screen one; it resumes when none is. The detector's discreet mark does not stop it. The latency gate of full-screen WebGPU is measured with no system element shown (**Proposed**, 16 November 2026; alternatives in [security.md](security.md#points-for-the-two-owners), point 21: stop for the discreet mark too, or a hardware plane if the GPU trial shows planes).
- Intermediate step: a separate video buffer, placed on a hardware plane.
- Afterwards: a protocol where Ladybird hands over several layers, for web layer animations.
- **Displays** (**Decided**, 14 November 2026): several screens, scaling per screen and hot-plugging are in the compositor's contract.
- The compositor owns the focus and draws the cursor on the hardware plane, directly from input events.
- The compositor draws the indicators and confirmations, out of reach of applications (see [security.md](security.md#baseline)).
- In the [build order](../plan/roadmap.md#build-order), the compositor first exists in a hosted version; fallback and test paths are in [gpu.md](gpu.md#fallback-and-test-paths).

## Shell

**Aligned**; the renderer is **Decided** (14 November 2026).

- There is no desktop environment: a surface manager centred on the agent, which serves as a launcher. A **surface** is a region of the screen owned by one program.
- The shell and the DodOS catalogue are drawn by gpui (Apache-2.0, published on crates.io, wgpu rendering on Linux since February 2026, AccessKit, Wasm target, headless mode), with the components of gpui-kit. Verified 13 November 2026.
- gpui is the shell renderer for version 1 (**Decided**, 14 November 2026).
- **Trial**, in weeks 1-2 of the [calendar](../plan/roadmap.md#calendar), as a validation of that choice: draw the catalogue with gpui and write the window back end of gpui for the project's compositor. LibWeb is compared in the same trial.
- Rune (a pre-release that refuses every pull request) is the fallback only if the trial fails.
- Same theme tokens as the web.

### Giving an object to an application

**Decided, 14 November 2026.** The object picker, drag and drop and the clipboard are held by the shell, and hand over an attenuated capability (a capability with reduced rights). The user's gesture is the grant: there is no permission dialog.

In the contract ([contracts/store.wit](../contracts/README.md)), the `exchange` interface gives `pick`, `copy` and `paste`. Drag and drop is part of the interface tree: the kinds `drag-source` and `drop-target` of the application catalogue, and the event "dropped". A capability received this way dies with the instance unless the component stores it through the `keep` interface.

## Agent interface format

**Aligned.**

- The model emits A2UI 1.0 (Express format) against a DodOS catalogue, translated to the interface tree of `os:core/ui` ([contracts/ui.wit](../contracts/README.md)): a flat list of nodes linked by ids, with no style, no URL, no code and no position.
- The encoding is open: a node names its kind by a string and carries its fields (`props`) as JSON. The kinds and their fields are WIT types in the two catalogue packages (see [Catalogue](#catalogue)). A new kind is a new minor version of a catalogue; a component built against an old catalogue keeps working.
- The agent draws on the `overlay` surface it receives with a request; that surface accepts only the fifteen agent-level kinds.
- Buttons are bound to the typed actions of the task.
- A JS applet without capabilities (the `applet` kind) covers the rest, including 3D.
- The interface tree is validated by the system at each update: kind known and allowed on the surface, props matching the kind, existing parent, actions within the scope of the task, size caps. A rejected update changes nothing.
- A2UI has no official Rust SDK (TypeScript, Python, Dart, Swift, Kotlin). The project writes its own Rust compiler from the specification and its conformance suites (**Decided**, 14 November 2026).
- The DodOS catalogue in A2UI format remains to be produced; WIT is the source and the A2UI catalogue is generated from it (see [Catalogue](#catalogue)).

## Agent surface

**Decided, 14 November 2026.**

- A surface of the shell, in glass, called by a key or by the wake word.
- An input bar at the bottom centre. It extends into a right side panel for a long task and its log.
- A generated interface is a card in the panel, which the user can detach into an ordinary surface.
- A confirmation is drawn by the system above the surface concerned.
- On a narrow screen: a sheet at the bottom.

## Design system

**Proposed** (under discussion in the source), with the points marked Decided.

- **Principle: a presence, not a window.** This holds for the agent and for all the native userland the project ships: settings, files and others are services that export actions and catalogue views, displayed by the shell, with no application frame.
- **Semantic, never stylistic.** The agent and catalogue applications emit only intentions (`tone`, `text-style`).
- **Inspirations assembled.** The roles of Material 3 Expressive (colour roles derived from a source colour, type scale, shape scale, spring-based motion), without its mobile components; the proportions and restraint of Adwaita (desktop density, content first); the frosted glass of COSMIC (Dual Kawase blur, shipped in COSMIC 1.3.0).
- **Material carries trust.** Frosted glass is reserved for the system and the agent. Only the compositor sees the pixels of other surfaces, so an application cannot imitate it. Applications have opaque tonal surfaces. An opacity setting exists for accessibility.
- **Glass for applications**: reserved for the system at first (**Decided**). If it opens one day, it will be a material supplied by the compositor and visibly distinct from the system's.
- **Visual identity** of who is speaking (agent, application, system), of the effect class (see [security.md](security.md#effect-class)) and of provenance.
- **Motion** is driven by the compositor, can be interrupted, and is subject to the latency gates.
- **Cost of the framework.** An application that bundles gpui pays for it every time (static linking, 8 to 15 MB quoted by a guide, to measure; plus its own glyph atlas and GPU context). A catalogue application pays nothing: rendering is in the shell, which is the project's equivalent of a shared library. Consequence: the project's native userland is written against the catalogue, which will have to grow beyond the agent's fifteen types.

### Tokens

**Decided, 14 November 2026.** A design token is a named design value (a colour, a size) shared by all renderers.

- Two layers: primitives and semantic roles, in the Design Tokens 2025.10 format (first stable version; a report of a W3C community group, outside the standards track).
- A component token is created only if a component cannot be expressed through the roles.
- A single source file, from which the tokens for gpui and for CSS are generated.
- Light, dark and high-contrast themes through the format's resolution module; density is a set of tokens.
- Two rendering engines in version 1: gpui in the shell and CSS in LibWeb.

### Catalogue

**Decided, 14 November 2026**: two levels, in two WIT interfaces versioned separately, as proposed below.

- The two levels are the packages `os:catalog-agent` and `os:catalog-app`, both at 0.1.0, in [contracts/catalog.wit](../contracts/README.md). They hold types only: a case name of `kind` is the kind string of a node, and its payload record is the node's props.
- Agent level, fifteen kinds: `stack`, `card`, `items`, `text`, `image`, `icon`, `table`, `progress`, `divider`, `button`, `field`, `choice`, `toggle`, `preview`, `applet`.
- Application level, fifteen more: `virtual-list` and `row` (a long list fed on demand), `tree` and `tree-item`, `tabs`, `navigation` (side navigation) and `page`, `menu`, `dialog`, `text-editor`, `slider`, `search`, `canvas` (drawing area), `drag-source`, `drop-target`.
- An application surface accepts both levels; the agent's overlay accepts only the agent level.
- Entry criteria for a type: semantic and not visual; accessible by construction; identical rendering in the rendering engines; adaptive layout with no absolute position.
- WIT is the source; the A2UI catalogue is generated from it.
- Everything else goes through an escape hatch: applet, WebGPU surface or web view.
- Test: reference screenshots per type and per theme.
- The catalogue describes meaning, not layout, so the same tree can be rendered per surface template (see [platform.md](platform.md#embedded)).

### Icons

**Decided.** Material Symbols in the Rounded variant (Apache-2.0, a variable font with four axes: fill, weight, grade, optical size), as a subset. The contract exposes the project's own semantic names, frozen, associated with the glyphs: the set stays replaceable without breaking the ABI. They are the enum `icon-name` of `os:catalog-agent` ([contracts/catalog.wit](../contracts/README.md)); its list is a starting set to review.

### To watch

ReactiveScript (solidjs, MIT, experimental version 0.1 of October 2026): a reactive interface language verified at compile time and designed to be written correctly by an AI. It compiles to Solid 2.0, so to the DOM. A possible lead for applets and web applications; nothing to adopt today.

## Input

- **Chain.** Linux drivers (USB HID, I2C HID) that produce evdev events; libinput, ported, for the touchpad and gestures (the device discovery of udev must also be emulated for it); xkbcommon for keyboard layouts.
- **Security.** Only the focused surface receives keys. Global shortcuts and input injection are capabilities that nobody has by default.
- **Input methods.** A text input protocol (surrounding text, pre-edit, commit, cursor rectangle), on the model of Wayland's text-input. An input engine is a component with no network. The virtual keyboard, the emoji picker and the agent's voice dictation go through the same protocol.
- **Engines**, later: librime (Chinese, BSD, portable), libhangul (Korean, LGPL, so in a separate component), mozc (Japanese, very heavy to build: Bazel and JDK).
- **Ladybird** (**Open**): text composition exists in LibWeb, wired today through Qt. It is to be wired to the project's protocol.

- **Pointer prediction** (idea of the user, 14 November 2026; **Proposed**). The speed and direction of the pointer predict where it is going. Uses: prepare the likely target (hover state, preloading, focus), and compensate the display latency of the cursor. Not applied to full-screen surfaces, which receive raw input. To measure: the error on stops and sharp turns, since an overshooting cursor is worse than a late one.

## Localisation

**Proposed, 14 November 2026, to validate.** ICU4X for locales; input engines as Wasm components with no network, plugged into the text input protocol; English and French in version 1; message format to choose (Fluent or MessageFormat 2).

## Accessibility

- **Tree format to decide** (**Open**). Ladybird has its own tree, exported to NSAccessibility and AT-SPI2 (PR 9156), and set aside AccessKit for web content: it lacks search by predicate and text markers. AccessKit remains valid for the shell.
- **The DodOS catalogue is semantic by construction**: its interfaces are accessible with no extra work.
- **Screen reader**: deterministic, written by the project on these trees, with the agent's speech synthesis. The agent does not replace it.
- **In the compositor**: magnifier, colour filters, high contrast through the theme tokens, reduced motion.
- **Live captions** by the local speech recognition model.
- **Reading the tree of another application is a capability**, granted by the user to assistive tools.

## Audio

- **Drivers.** Linux sound drivers (Intel HDA, USB audio) in the emulation layer. They expose a ring buffer in shared memory.
- **Audio service.** Written by the project (Fuchsia's is tied to its IPC and was not extracted), native, with a guaranteed scheduling budget: a mixing graph pulled by the device clock, with a fixed quantum of 128 frames at 48 kHz (2.7 ms). Model of PipeWire and CoreAudio, without taking their code.
- **Clients.** Ring buffers in shared memory, no message per buffer. Web Audio for web applications, a WIT interface for components.
- **Rights.** Playback, microphone and capture of the sound of other applications are three distinct capabilities. The microphone has its indicator drawn by the compositor.
- Wake word and echo cancellation: [agent.md](agent.md#voice). Bluetooth audio: [network.md](network.md#bluetooth).

## Settings, notifications and rights

**Proposed, 14 November 2026, to validate.**

- Each service exports its settings as actions with a schema. The settings screen is generated from the catalogue, and the agent changes settings through the same path.
- Notifications: a surface of the shell; a notification carries actions and a priority class.
- Rights screen: a query on the capability tree.
