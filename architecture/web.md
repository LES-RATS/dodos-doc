# Web engine and web content

Statuses are defined in the [README](../README.md#status-legend).

## Web engine

**Decided.** The web engine is a fork of Ladybird (its libraries LibWeb for rendering and LibJS for JavaScript).

- The fork is perpetual: Ladybird has refused every external contribution since 5 June 2026 and has closed the embedding request.
- The project follows the published versions, starting from the first alpha, and decides on each version upgrade.
- The project tracks Ladybird's security fixes (see [security.md](security.md#vulnerabilities)).

Ladybird was verified on 13 November 2026 against commit c8b525e: process architecture, dependencies, Rust crates, JIT, accessibility, input methods, WebGPU, contribution policy.

## Porting Ladybird

Verified on commit c8b525e of 13 November 2026. The port needs:

- LibCore (it has POSIX and Windows variants; macOS reuses POSIX);
- a LibIPC transport (existing ones: Unix socket, Windows with a handle broker, Mach port);
- 49 vcpkg dependencies on mlibc (the C library used for native code; see [wasm-abi.md](wasm-abi.md#how-userland-builds-against-the-os));
- the Rust crates: Ladybird has about thirty (LibJS, its JIT, the CSS engine, the core of the Compositor, LibWasm);
- an AudioServer back end, the sandbox, fonts without Fontconfig, and RequestServer (curl) on the project's network stack.

The Hub process, without Qt since PR 14109, is the control junction. Estimate of the audit: 4 to 7 months for two people once mlibc, Rust, Vulkan and the network are in place.

Still to add or wire: WebGPU in LibWeb (see [gpu.md](gpu.md#gpu-for-applications)); text composition on the project's input protocol (see [ui.md](ui.md#input)); the accessibility tree (see [ui.md](ui.md#accessibility)). The state of hardware video decoding in Ladybird is unknown (see [media.md](media.md#hardware-video-decoding)).

## Web content and capabilities

**Aligned.** Each site is a principal (an identity that holds rights), with a fixed "web world".

A site is a scheme and a registrable domain; provenance names the origin (**Proposed**, 16 November 2026).

- One process per web site (see [security.md](security.md#three-boundaries)).
- The web is a surface like the others. Web sites export no actions; the agent falls back on the accessibility tree for them (see [agent.md](agent.md#how-the-agent-acts)).

## Web applications

- The WIT interfaces granted by the manifest appear as ES modules (`import { open } from "os:core/store"`), with the mapping of jco: a resource becomes a class, a `result` an exception, an async function a `Promise`, a stream a `ReadableStream`.
- This is reserved for signed packages, never for ordinary sites.
- JS and TS of web applications run on LibJS, without the JIT whatever P-052 answers for the web content process (**Proposed**, 16 November 2026; [security.md](security.md#points-for-the-two-owners), point 26).
- Debugging uses the developer tools of Ladybird.

## JIT in the web content process

**Open.** The right to create executable code for the web content process: LibJS has had a JIT active by default since October 2026 (PR 12492 and 12613). It is the only exception under discussion to the rule that only the compile service produces machine code (see [security.md](security.md#chain-of-trust)).

## Tests

WPT (the Web Platform Tests) is the authoritative test suite for the web (see [plan/verification.md](../plan/verification.md#authoritative-test-suites)).
