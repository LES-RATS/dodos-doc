# ArtCraft and the "Crafting Apps": licences, offline use, web, MCP, Wasm

Research date: 2026-11-16. Method: `gh` API, plus shallow clones (`git clone --depth 1`) read without building or running anything. Every code citation is `repo:path:line` at the commit listed below. Anything I could not check is marked **not verified**. Labels: **[fact]** means read directly in a cited source. **[assessment]** means my inference from cited facts. Assessments appear only in the Wasm column and section 5.

## Commits read

| Repository | Commit | Repository | Commit |
|---|---|---|---|
| storytold/artcraft | `84a6a7dc` | storytold/photocraft | `6f4a2cba` |
| storytold/vectorcraft | `ed6f22a8` | storytold/filmcraft | `8e001ff8` |
| storytold/lightcraft | `e92905fa` | storytold/pdfcraft | `75a6ce50` |
| storytold/effectcraft | `3d84810b` | storytold/designcraft | `11ad84fd` |
| storytold/figcraft | `559c952d` | storytold/wordcraft | `fe8a8a83` |
| storytold/gridcraft | `1476d4e7` | storytold/deckcraft | `3b6f9e7c` |
| storytold/soundcraft | `5976545f` | storytold/cadcraft | `2ccf5874` |
| storytold/texturecraft | `893d6fbb` | storytold/anicraft | `38541642` |
| storytold/materialcraft | `983e3276` | storytold/craft-anything | `7aebf09a` |
| storytold/craft-libs | `341020b2` | storytold/craft-ai-integrations | `d94a3593` |
| storytold/craft-wiki | `63468221` | | |

---

## Summary table

"Offline" means the code runs with no account, no network and no paid service. The only network traffic is optional, as noted. "MCP" means a first-party server inside the app's own repository.

| Application (Adobe target) | Licence (LICENSE files + Cargo manifest) | Offline, no account | Official web build | MCP in repo | Wasm feasibility [assessment] |
|---|---|---|---|---|---|
| **PhotoCraft** (Photoshop) | MIT OR Apache-2.0 | Yes. Startup update check to api.github.com is on by default and can be switched off. | Yes: `photocraft-web-<ver>.zip` (WebGPU, WebGL2 fallback). No official hosted instance. | Yes. Uses `rmcp` 3.x on stdio. 26 tools. Headless, or bridged to the open app. | Browser: shipped. wasip2: the MCP crate uses tokio `rt-multi-thread`/`net`/`io-std`, which tokio refuses to compile on wasm without `tokio_unstable`. The engine already builds for wasm32. |
| **VectorCraft** (Illustrator) | MIT OR Apache-2.0 | Yes. Same update check. | Yes (zip) | Yes. Hand-written JSON-RPC, no async runtime, stdio. 33 tools. | Browser: shipped. wasip2: plausible for headless. `handle_line(&str)` needs no socket and no thread. |
| **FilmCraft** (Premiere Pro) | MIT OR Apache-2.0 | Yes. Whisper speech models download only on demand, after the user confirms. | Yes (zip) | Yes. `rmcp` on stdio. 17 tools. | Browser: shipped. wasip2: same tokio blocker as PhotoCraft. |
| **LightCraft** (Lightroom) | MIT OR Apache-2.0 | Yes. AI-mask, face and denoise models download on demand. Optional LAN remote-GPU denoise over TCP. | Yes (zip). Cannot import a Lightroom catalog. | Yes. Hand-written, stdio. 28 tools. | Browser: shipped. wasip2: plausible for headless (`handle_line`). |
| **PdfCraft** (Acrobat) | MIT OR Apache-2.0 | Yes | Yes (zip). Browser OCR loads model files from beside the page. | Yes. Hand-written, stdio. 176 tools, all with JSON Schema. Has a compact mode with `tool_search`/`tool_call`. Headless only. | Browser: shipped. wasip2: plausible for headless (`handle_line`). |
| **EffectCraft** (After Effects) | MIT OR Apache-2.0 | Yes. SAM 2.1 model files are downloaded, not bundled. | Yes (zip). Projects stay in browser storage. | Yes. Hand-written, stdio, reads input on its own thread. About 36 tool names. | Browser: shipped. wasip2: `handle_line` exists, but `serve` spawns a thread. |
| **DesignCraft** (InDesign) | MIT OR Apache-2.0 | Yes. The About box says "Open source. No telemetry." | Yes (zip). Its docs say the web build "can't be driven by AI assistants". | Yes. Hand-written, stdio. 26 tools. | Browser: shipped. wasip2: plausible for headless (`handle_line`). |
| Later apps: WordCraft, GridCraft, DeckCraft, SoundCraft, CADCraft, FigCraft, TextureCraft, MaterialCraft, AniCraft, Craft Anything | MIT OR Apache-2.0 (all manifests) | Not audited one by one. Only update checks and app-specific optional sockets found (Zotero, FigCraft collaboration). | Each has a `*-web` app or `packaging/web` | Every one has an MCP server (15 to 25 tools, AniCraft 5) | Not assessed in detail |
| **ArtCraft** itself (AI studio) | Desktop repo: MIT OR Apache-2.0. Backend `artcraft-services`: "ArtCraft License (WIP)", a non-OSI "fair source" licence. | **No.** Generation runs through ArtCraft's OmniGen API with an account and credits, or the user's own Midjourney account or fal API key. | No | No MCP server in the repo. It has client definitions for hosted `/v1/mcp/session/*` endpoints. | Not applicable |

---

## 0. What the suite is, and the "seven"

- The organisation `storytold` has 17 Craft app repositories, plus shared ones (`craft-libs`, `craft-ai-integrations`, `craft-launcher`, `craft-wiki`, and others). Source: `gh repo list storytold`.
- Seven app repositories were created on 2026-09-30 and 2026-10-01: photocraft, filmcraft, vectorcraft, pdfcraft, lightcraft (all 2026-09-30), effectcraft and designcraft (2026-10-01). The others came later, from 2026-10-07 (wordcraft, gridcraft, deckcraft, soundcraft, cadcraft) to 2026-11-01 (materialcraft). Source: `createdAt` in `gh repo list`.
  - These seven match the press framing of "7 free Adobe alternatives" ([aiidelist](https://aiidelist.com/blog/artcraft-photocraft-filmcraft-free-adobe-alternatives), [hotukdeals](https://www.hotukdeals.com/deals/artcraft-crafting-apps-7-free-alternatives-to-adobe-photoshop-illustrator-acrobat-premier-more-early-builds-5000037)).
  - The PdfCraft repository's homepage field is still `getartcraft.com/apps/printcraft` (`gh api repos/storytold/pdfcraft`), which suggests an earlier name.
- Today getartcraft.com/apps headlines "Seventeen apps · Open source · Pure Rust" (fetched 2026-11-16).
- On (a), what you were told is **half right**:
  - ArtCraft is the AI image and video studio. Its value depends on paid hosted models: the [pricing page](https://getartcraft.com/pricing) sells credit plans at $10, $35 and $60 per month. But its desktop code is MIT/Apache (`artcraft:README.md`, License section). The pricing page footnote says ArtCraft "can be used without paying for a subscription. You can bring your own compute and third-party subscriptions."
  - The editors are free software and need no account (details per app below).
  - The ArtCraft backend `storytold/artcraft-services` is under a custom non-OSI licence. It forbids commercial resale, competing products, and forks that remove "paid model services" (`LICENSE.md` via `gh api repos/storytold/artcraft-services/contents/LICENSE.md`).
- The apps state they are built by AI agents. The parity documents express remaining work in "Opus 5.5 agent-hours" (`photocraft:docs/target-app-parity.md:24`).

## 1. Per-application facts

### Common stack (all 17 apps) [fact]

- **Language:** Rust, edition 2024. The apps forbid `unsafe` at workspace level (`photocraft:Cargo.toml:107-108`).
- **UI:** egui/eframe 0.37 on **wgpu** (v30 in PhotoCraft's lock file). No Tauri, no Electron, no web view. PhotoCraft's README says: "A GPU compositor on wgpu (Metal, Vulkan, DX12, WebGPU)… No Electron, no web view" (`photocraft:README.md:77`). The architecture document: "UI toolkit: decided: egui/eframe on wgpu (no webview, no JavaScript)" (`photocraft:docs/architecture.md:15-16`).
- **Lock files:** every app's `Cargo.lock` contains `eframe`, `egui`, `wgpu`, `wasm-bindgen`, `tokio`, `ureq` and `craft-update` (checked by grep on all 17 lock files).
- **Licence:** every app has `license = "MIT OR Apache-2.0"` in its root `Cargo.toml` and ships `LICENSE-MIT` and `LICENSE-APACHE`. GitHub reports Apache-2.0 for all of them.
- **ArtCraft itself is different:** the main app is **Tauri** (`artcraft:crates/desktop/artcraft/tauri.conf.json:3-5`, productName ArtCraft 0.42.1) with a TypeScript `frontend/`. A newer pure-Rust egui client is `artcraft:artcraft-native/README.md:3-5` ("There is no Tauri and no JavaScript; the only webview is the Midjourney sign-in window").

### Size and activity (measured 2026-11-16)

- **Rust lines:** total `*.rs` lines in the shallow clone, tests included.
- **Contributors:** GitHub contributors API with `anon=true`. Bots are included.
- **Open issues and PRs:** counted separately with the GitHub search API.

| Repo | Version | Rust lines (files) | Commits | Contributors | Open issues / open PRs | Last commit (UTC) |
|---|---|---|---|---|---|---|
| photocraft | 0.23.1 | 1,007,017 (2,648) | 13,611 | 602 | 3,732 / 1,683 | 2026-11-16 10:14 |
| vectorcraft | 0.24.1 | 1,345,157 (2,409) | 15,323 | 255 | 940 / 427 | 2026-11-16 05:55 |
| filmcraft | 0.20.1 | 358,429 (902) | 4,047 | 215 | 1,278 / 969 | 2026-11-16 10:26 |
| lightcraft | 0.21.1 | 383,820 (990) | 5,386 | 253 | 906 / 909 | 2026-11-16 10:46 |
| pdfcraft | 0.21.1 | 767,503 (1,563) | 6,495 | 379 | 1,859 / 1,361 | 2026-11-16 09:23 |
| effectcraft | 0.24.1 | 556,655 (1,247) | 4,954 | 173 | 877 / 315 | 2026-11-16 10:10 |
| designcraft | 0.21.0 | 343,317 (679) | 5,541 | 138 | 670 / 411 | 2026-11-16 00:40 |
| figcraft | 0.18.1 | 375,378 | 4,419 | 154 | 249 / 108 | 2026-11-16 |
| wordcraft | 0.18.1 | 323,739 | 3,380 | 271 | 1,691 / 1,490 | 2026-11-16 |
| gridcraft | 0.19.1 | 258,031 | 3,210 | 153 | 1,204 / 1,147 | 2026-11-16 |
| cadcraft | 0.21.0 | 266,419 | 1,615 | 142 | 683 / 701 | 2026-11-16 |
| deckcraft | 0.19.0 | 179,745 | 2,187 | 98 | 425 / 443 | 2026-11-16 |
| soundcraft | 0.20.1 | 110,250 | 1,602 | 95 | 374 / 263 | 2026-11-16 |
| texturecraft | 0.6.1 | 123,669 | 807 | 22 | 93 / 103 | 2026-11-16 |
| anicraft | 0.3.0 | 155,865 | 817 | 4 | 128 / 69 | 2026-11-16 |
| materialcraft | 0.4.1 | 76,442 | 444 | 19 | 37 / 39 | 2026-11-16 |
| craft-libs (shared) | – | 1,146,590 (3,031) | 3,151 | 121 | 246 / 455 | 2026-11-16 |
| artcraft (AI studio) | 0.42.1 | 272,701 | 59 | 7 | 573 / 153 | 2026-11-12 |

### Shared code [fact]

- **`storytold/craft-libs`** holds 152 crates (`craft-libs:crates/`). It covers formats (psd, pdf, svg, tiff, raw, docx, xlsx, idml, …) and shared infrastructure: `ui`, `update`, `flags`, `i18n`, `mcp`, `jsonrpc`, `control-protocol`, `ai-core`.
- **Number of craft-libs crates per app** (from `Cargo.lock` `source = git+…/craft-libs`): PhotoCraft 45, VectorCraft 32, FilmCraft 35, LightCraft 32, PdfCraft 27, EffectCraft 37, DesignCraft 83, the others 15–41.
- **Each app pins craft-libs by git revision.** Several revisions coexist in one app: PhotoCraft 11 distinct revisions, DesignCraft 19, FilmCraft 14 (counted in `Cargo.lock`). Example: `photocraft:Cargo.toml:13-76`.
- **Patched forks:** most apps also use storytold forks of egui, winit and wgpu (11–15 lock entries each; none in AniCraft or Craft Anything).
- **What is not shared:** app engines and MCP servers are written per app, in different styles (see section 4).

### Per app, what it is (from each README)

- **PhotoCraft:** "Image editing; an open-source, clean-room reimplementation of Adobe Photoshop, rebuilt in pure Rust" (`photocraft:README.md:17`). Layers, adjustment layers, layer styles, type, vectors, a brush engine, PSD/PSB round trips, and 8/16/32-bit RGB/CMYK/Lab with ICC colour management (`photocraft:README.md:165-196`). The architecture document counts about 539,000 lines of Rust in 24+ crates (`photocraft:docs/architecture.md:11`).
- **VectorCraft:** Illustrator-style editor. SVG, PDF and `.ai` (PDF-compatible), EPS, DXF and Affinity files (`vectorcraft:README.md:236-242`).
- **FilmCraft:** nonlinear video editor with its own codecs (`filmcraft:README.md:185` and following, codec table). Imports FCP7 XML, AAF and OTIO; does not open `.prproj` (`filmcraft:README.md:296-310`).
- **LightCraft:** non-destructive photo library and raw developer (`lightcraft:README.md:343-360`).
- **PdfCraft:** PDF reader and editor. Forms, signing, OCR, accessibility tagging, redaction (`pdfcraft:README.md:443`).
- **EffectCraft:** motion graphics and compositing. Exports ProRes, HEVC, AV1, WebM and EXR (`effectcraft:README.md:154-155`).
- **DesignCraft:** page layout. Opens `.indd`/`.indt` through `indd-utils` (`designcraft:ROADMAP.md:7`).

## 2. Offline use, network calls, paid dependencies

**Editors in general [fact]**
- No account or paid service appears in any editor's code path that I inspected.
- No telemetry SDK (Sentry, PostHog, Mixpanel, Amplitude) appears in any of the 17 lock files (grep).
- The PhotoCraft README says: "Open source, offline, and yours" (`photocraft:README.md:19`) and "Smart selection runs on your machine, with no cloud and no account" (`photocraft:README.md:125`).

**Network calls found, by type:**

| What | Where | When | Needs payment? |
|---|---|---|---|
| Release check against `https://api.github.com/repos/{repo}/releases` | `craft-libs:crates/update/src/lib.rs:58` (ureq client, `crates/update/Cargo.toml:30`) | At startup, once per launch, when `automatically_check_updates` is on. **Default `true`** (`photocraft:crates/engine/src/prefs.rs:337`, used at `crates/ui-egui/src/updates_ui.rs:116-118`). The web builds do not check, for example "It doesn't check for updates" (`craft-wiki:src/content/docs/apps/vectorcraft/install-update.md:65`). | No |
| Loopback control channel (TCP, token or HMAC authenticated) used by the MCP "bridge" | e.g. `photocraft:apps/photocraft/src/control_server.rs`; HMAC: `photocraft:crates/automation/Cargo.toml:36-38` | Only when agents are enabled, or the app is started with `--control` | No |
| Printing over IPP/CUPS; Windows printing via `winprint` (which pulls `reqwest` and sigstore) | `photocraft:crates/ipp/src/lib.rs`; `photocraft:Cargo.lock` (`craft-print -> winprint -> sigstore-verify -> reqwest`) | When printing | No |
| Model downloads from Hugging Face, pinned and SHA-256 checked | FilmCraft Whisper: `filmcraft:crates/speech/src/models.rs:1-10` ("downloaded on first use, after the user confirms"). LightCraft: `lightcraft:crates/fetch/src/http.rs:1-10`, `crates/faces/src/known.rs:133`. EffectCraft SAM 2.1: `effectcraft:crates/segment/src/lib.rs:186-237` | Only for optional AI features (transcription, masks, faces, denoise, segmentation) | No (free weights) |
| LightCraft remote denoise on another computer's GPU over TCP, unencrypted, for LAN or VPN | `lightcraft:crates/denoise/src/remote.rs:1-21` | Opt-in | No |
| PdfCraft browser OCR fetches model files from `models/` beside the page | `pdfcraft:crates/ui-egui/src/workflows/ocr_web.rs:1-9` | When OCR is used on the web | No |
| WordCraft ↔ Zotero over a local socket | `wordcraft:crates/zotero/src/client.rs:1-8` | Citation feature | No |
| FigCraft collaboration over WebSocket, plus a separate `figcraft-server` app | `figcraft:crates/collab-net/src/net.rs:1-7`; `figcraft:apps/figcraft-server` | Collaboration | Self-hosted. Not verified whether any hosted service exists. |

**Shared AI layer (optional, not linked by the seven editors) [fact]**
- `storytold/craft-ai-integrations` contains adapters for **paid** hosted providers: OpenAI-compatible, Black Forest Labs, Gemini, Vertex, BytePlus Seedance, and "the ArtCraft Omni API-key route".
- It also contains **local** engines: ComfyUI, SAM 3 on Candle, SAM 2.1/BEN2 on rten, and Burn (`craft-ai-integrations:README.md`, Crates table).
- Its own status note: "The extension APIs are still evolving."
- None of the seven editors' lock files contains `craft-ai-client` or a provider adapter. PhotoCraft links only `craft-ai-agents`, the consent and app-list crate (`photocraft:Cargo.toml:16-19`). So hosted generative AI is **not** in the shipped editors today.
- PhotoCraft lists "AI/generative features" as its biggest gap (`photocraft:README.md:312`). FilmCraft says "AI features. Few so far; speech to text is optional and off by default" (`filmcraft:README.md:308`). PdfCraft lists "AI providers" as missing (`pdfcraft:docs/target-app-parity.md:220`).

**ArtCraft (the AI studio) [fact]**
- Requires the ArtCraft API ("Generation… goes through OmniGen: `/v1/omni_gen/{models,cost,generate}/…`") or the user's own Midjourney account or fal key (`artcraft:artcraft-native/README.md:46-60`).
- Credit purchase UI: `artcraft:artcraft-native/src/overlays/account.rs:151` ("Buy credits").
- The 62-model catalogue (Nano Banana, GPT Image, FLUX, Seedance, Kling, Veo, …) is in `artcraft:README.md`, under "Models and Providers".

## 3. Web target

**Every app has a browser build in its repository [fact].**

- **PhotoCraft:**
  - `photocraft:apps/photocraft-web/Cargo.toml` ("PhotoCraft in the browser (eframe web runner, WebGPU with WebGL2 fallback)"). eframe uses the `wgpu` feature, built with Trunk (`apps/photocraft-web/Trunk.toml`) and wasm-bindgen.
  - A boot loader `apps/photocraft-web-boot` loads the gzipped wasm, which is split into 20 MiB parts (`photocraft:packaging/web/README.md:1-15`).
  - The architecture document requires CI to build the engine for `wasm32-unknown-unknown` (`photocraft:docs/architecture.md:182`).
- **Other apps:** each repository has `apps/<app>-web` (AniCraft only `packaging/web`) and `packaging/web/` (directory listing). The wiki documents `<app>-web-<ver>.zip` for each app (e.g. `craft-wiki:src/content/docs/apps/filmcraft/install-update.md:57`).

**Where it is published [fact]**
- As a static-site zip attached to each GitHub release. Example: PhotoCraft v0.23.1 (2026-11-12) has asset `photocraft-web-0.23.1.zip` (`gh release view`). getartcraft.com/apps/photocraft links that zip.
- **No official hosted instance found.** PdfCraft's parity document lists "hosted web app" as missing (`pdfcraft:docs/target-app-parity.md:220`).
- An **unofficial** site, [artcraftsuite.org](https://artcraftsuite.org/), calls itself an "Unofficial community guide" and hosts the apps to "Open online". I did not verify who runs it or which builds it serves.

**What does not work on the web [fact]**

| App | Web limitations found | Source |
|---|---|---|
| PhotoCraft | No TCP control server, so no MCP or agent bridge. No threads: every command runs inline. No crash recovery. No system fonts. No automatic browser-language detection. | `photocraft:apps/photocraft-web/src/main.rs:8`; `docs/control-protocol.md:314`; `docs/development.md:315`; `docs/localization-ka.md:30`; `docs/localization-zh-hans.md:23` |
| VectorCraft | Save and export become downloads. Printing goes through the browser dialog. No update check. Needs https or localhost for GPU and clipboard. | `craft-wiki:…/vectorcraft/install-update.md:63-65` |
| FilmCraft | WebGL2 fallback composites on the CPU, so playback is slower. Uses WebCodecs if present, otherwise its own decoders. Crash snapshots go to browser storage. | `craft-wiki:…/filmcraft/install-update.md:57-62` |
| LightCraft | Library kept in the browser. Cannot import a Lightroom catalog. | `craft-wiki:…/lightcraft/install-update.md:57` |
| PdfCraft | No update check. No crash recovery. | `craft-wiki:…/pdfcraft/install-update.md:59` |
| EffectCraft | Projects, media and settings stay in browser storage. The README says the web build "runs the full app in the browser". | `craft-wiki:…/effectcraft/install-update.md:62`; `effectcraft:README.md:248` |
| DesignCraft | Browser file picker. Save becomes a download. "It can't be driven by AI assistants." | `craft-wiki:…/designcraft/install-update.md:57` |
| SoundCraft (later app) | No third-party plugins. No recording or audio-device choice. Saves as a single `.scraftz` file. | `craft-wiki:…/soundcraft/install-update.md:61` |

## 4. MCP: first-party, in the repositories

On (c), what you were told is **confirmed**. Each app ships its own MCP server, and the organisation ships a suite gateway. Your earlier finding (a third-party server with online credits) does not describe the first-party servers. None of them needs a paid service: they drive the local engine.

**Transport [fact]**
- All app servers use **stdio**, newline-delimited JSON-RPC 2.0.
  - Example: "It opens no network port; the transport is newline-delimited JSON-RPC 2.0 over stdin/stdout" (`pdfcraft:crates/automation/src/mcp.rs:1-6`).
  - PhotoCraft wraps rmcp's `transport-io` (`photocraft:crates/automation/Cargo.toml:32`, `src/server/transport.rs:37-60`).
- No HTTP/SSE MCP transport was found in the editors.
- A separate headless JSON-lines server can run on stdio or loopback TCP (`photocraft-cli serve`, `photocraft:crates/automation/src/lib.rs:12-13`).

**Headless or live document [fact]**
- Most servers have two backends:
  - **Headless:** an in-process engine `Session`, no window.
  - **Bridge:** forwards to the running desktop app over its authenticated loopback TCP control channel. This adds UI inspection, screenshots and pointer and keyboard input.
- Sources: `photocraft:crates/automation/src/lib.rs:5-10`; `vectorcraft:crates/mcp/src/lib.rs:3-13`; `filmcraft:crates/automation/src/lib.rs:3-9`; `lightcraft:crates/mcp/src/lib.rs`; `effectcraft:crates/automation/src/lib.rs:5-12`; `designcraft:crates/mcp/src/lib.rs`.
- **PdfCraft's MCP is headless only.** The running app is driven separately by `pdfcraft-cli ui --control FILE` (`pdfcraft:apps/pdfcraft-cli/src/main.rs:95-96`).
- **PhotoCraft's plain `photocraft-cli mcp`** works in the open window when the person allows agents, and otherwise headless (`photocraft:docs/mcp.md:33-52`).

**Consent [fact]**
- Live control is gated by the suite's `AI-MCP` feature flag in `ArtCraft/flags.toml`, plus the ArtCraft Launcher switch "Let AI agents use Craft apps" (`photocraft:docs/mcp.md:3-26`; `photocraft:crates/automation/src/agent_link.rs:190-212`).
- File access is confined to read and write roots given at launch (`photocraft:docs/mcp.md:38-45`).

**Implementations [fact]**
- **rmcp + tokio:** PhotoCraft, FilmCraft, TextureCraft, MaterialCraft (lock files).
- **Hand-written, no async runtime:** VectorCraft, LightCraft, EffectCraft, DesignCraft, PdfCraft, and most later apps.
- **CADCraft** uses the shared `craft-mcp` crate.
- `craft-libs:crates/mcp` is "Transport-independent MCP server initialization and tool envelopes". It depends only on `craft-jsonrpc` and `serde_json`, and implements MCP 2025-03-26 (`craft-libs:crates/mcp/Cargo.toml:1-15`, `src/lib.rs:1-11`).
- PdfCraft speaks protocol versions 2025-06-18, 2025-03-26 and 2024-11-05 (`pdfcraft:crates/automation/src/mcp.rs:21`).

### Tool lists (names extracted from the cited definition files)

**PhotoCraft**, `photocraft:crates/automation/src/server.rs:772-1142`. Parameters come from `#[derive(JsonSchema)]` structs with `deny_unknown_fields` (`server.rs:46-430`). All tools get `additionalProperties:false` and MCP annotations (`server/conventions.rs:13-32`).

| Tool | Parameters |
|---|---|
| `session_list` | – |
| `doc_open` | `path`, `approve_high_memory` |
| `doc_place` | `path`, `index?`, `scale?`, `fit?`, `center?[x,y]`, `approve_high_memory` |
| `doc_replace_smart_object` | `path`, `index?`, `layer?` |
| `doc_export_layers` | `dir`, `index?`, `format?`, `prefix?`, `visible_only?`, `quality?`, `maximizeCompatibility?` |
| `doc_export_data_sets` | `dir`, `index?`, `format?`, `data_sets?[]`, `naming?` |
| `doc_import_data_sets` | `path`, `index?`, `delimiter?` |
| `doc_new` | `width?`, `height?`, `mode?`, `depth?`, `background?`, `name?` |
| `doc_save`, `doc_export` | `path?`, `format?`, `quality?`, `tiffLayers`, `tiffCompression?`, `tiffTransparency?`, `tiffPyramid`, `tgaBits?`, `dpxBits?`, `ddsCompression?`, `ddsMipmaps`, `pdfSpotPlates?`, `pcraftFullComposite?`, `maximizeCompatibility?`, `index?` |
| `doc_inspect`, `doc_close` | `index?` |
| `doc_render_preview`, `render_preview` | `index?`, `max_side?` |
| `doc_select` | `index` |
| `command_list` | `filter?`, `enabled_only?` |
| `command_run` | `id`, `params?` (any JSON), `wait?` |
| `command_batch` | `steps[]` (each a `command_run` object), `stop_on_error?` |
| `jobs_list` | – |
| `jobs_cancel` | `job?` |
| `ui_inspect` (bridge) | – |
| `ui_screenshot` (bridge) | `max_side?` |
| `ui_pointer` (bridge) | `events[]` (`kind`, `x`, `y`, `pressure`, `tiltX`, `tiltY`, `rotation`), `modifiers?`, `button?` |
| `ui_menu_invoke` (bridge) | `id` |
| `ui_set` (bridge) | `fields` (object) |
| `control_call` (bridge) | `method`, `params?` |

**Other apps:**
- **VectorCraft** (33), `vectorcraft:crates/mcp/src/tools/definitions.rs:95-524`. Each entry is built by `tool(name, title, desc, schema, read_only)` with an explicit `inputSchema` (`definitions.rs:82-92`). Tools: `command_list`, `command_run`, `command_batch`, `doc_inspect`, `render_preview`, `ui_inspect`, `ui_screenshot`, `list_commands`, `run_command`, `inspect_document`, `inspect_ui`, `select_tool`, `pointer_gesture`, `draw_path`, `draw_shape`, `set_paint`, `press_key`, `type_text`, `answer_dialog`, `invoke_menu`, `open_panel`, `screenshot`, `open_file`, `save_file`, `export`, `add_text`, `apply_effect`, `pathfinder`, `transform`, `create_graph`, `text_wrap`, `undo`, `redo`.
- **FilmCraft** (17, rmcp + schemars), `filmcraft:crates/automation/src/server.rs`. Tools: `command_list`, `command_run`, `command_batch`, `doc_inspect`, `render_preview`, `project_inspect`, `sequence_inspect`, `media_import`, `render_frame`, `ui_inspect`, `ui_elements`, `ui_click`, `ui_drag`, `ui_key`, `ui_type`, `ui_screenshot`, `ui_control`.
- **LightCraft** (28), `lightcraft:crates/mcp/src/tools.rs`. Tools: `command_list`, `command_run`, `command_batch`, `doc_inspect`, `render_preview`, `list_commands`, `run_command`, `import`, `query_photos`, `select_photos`, `list_controls`, `get_develop`, `set_develop`, `apply_preset`, `crop`, `render_photo`, `export`, `ui_inspect`, `ui_screenshot`, `screenshot`, `inspect_ui`, `set_ui`, `list_widgets`, `click`, `press_key`, `type_text`, `clipboard`, `pointer_gesture`.
- **PdfCraft** (176 `ToolDef`s, each with `input_schema`, a "JSON Schema (draft 2020-12 subset)", plus `read_only` and `destructive` flags), `pdfcraft:crates/automation/src/tools.rs:13-21` and `:134` onward.
  - Groups: `doc_*`, `page_*`, `text_*`, `form_*`, `comment_*`, `sign_*`, `accessibility_*`, `ocr_*`, `js_*`, `link_*`, `measure_*`, `bookmark_*`, plus `command_list`, `command_run`, `command_batch`, `doc_inspect`, `render_preview`.
  - Compact mode lists only `COMPACT_CORE_TOOLS` plus `tool_search` and `tool_call` (`pdfcraft:crates/automation/src/mcp.rs:45-78`, `:210-255`).
- **EffectCraft** (about 36; some are aliases), `effectcraft:crates/automation/src/tools.rs`. Tools: `list_commands`, `describe_command`, `execute_command`, `run_script`, `get_project`, `get_comp`, `get_layer`, `get_property`, `set_property`, `add_keyframe`, `add_effect`, `list_effects`, `list_fonts`, `get_state`, `render_frame`, `open_project`, `save_project`, `undo`, `redo`, `history`, `script_ui`, `screenshot`, `ui_*` (inspect, elements, click, drag, key, type, set), `control`, `batch`, `command_list`, `command_run`, `command_batch`, `render_preview`, `doc_inspect`.
- **DesignCraft** (26), `designcraft:crates/mcp/src/tools.rs`. Tools: `list_commands`, `execute`, `batch`, `inspect_document`, `get_story`, `set_story_text`, `new_document`, `open_document`, `save_document`, `place_image`, `render_page`, `export_png`, `screenshot`, `select_tool`, `pointer`, `key`, `type_text`, `ime`, `click`, `drag`, `menu_list`, `ui_inspect`, `ui_set`, `dialog_set`, `dialog_confirm`, `dialog_cancel`.
- **Later apps** (tool counts by the same extraction): WordCraft 18, GridCraft 22, DeckCraft 25, SoundCraft 17, CADCraft 15, FigCraft 19, TextureCraft 22, MaterialCraft 20, AniCraft 5, Craft Anything 2 meta-tools (`list_toolsets`, `enable_toolset`). Files: `<app>/crates/mcp/src/tools.rs` or `crates/automation/src/…`, as listed in the commits table repositories.

**Suite gateway (first-party) [fact]**
- `craft-ai-integrations:crates/app/ai-mcp`, the binary `craft-ai-mcp`. It depends only on `serde`, `serde_json`, `dirs` and `craft-ai-agents` (`Cargo.toml:1-20`).
- It exposes four tools (`src/apps/tools.rs:13-48`, names at `src/apps/mod.rs:23-26`):
  - `craft_list_apps` ()
  - `craft_find_tools` (`query`, `app?`, `limit?`)
  - `craft_describe_tool` (`app`, `tool`)
  - `craft_call_tool` (`app`, `tool`, `arguments?`, `timeoutSeconds?`)
- It reaches each app by **starting `<app>-cli mcp` as a child process** (`src/lib.rs:4-12`).

**How regular the definitions are, for automatic translation [fact]**
- **Per-tool level: regular.** Every app tool has a name, a description and an `inputSchema` object. They are generated by schemars (rmcp apps) or written as JSON literals (hand-written apps). PdfCraft and PhotoCraft add read-only and destructive annotations.
- **Engine-command level: not regular.** The 500+ engine commands behind `command_run` (PhotoCraft README: "one registry of 500+ commands", `photocraft:README.md:230`) carry **no JSON Schema**. Their parameters are a free-text "Human/agent-readable parameter description (JSON-ish)" string (`photocraft:crates/engine/src/cmd.rs:22-23`), returned by `command_list` as `params: doc string` (`photocraft:crates/automation/src/server.rs:1028-1031`). Example of such a string: `photocraft:crates/engine/src/layer_style.rs:1193`.
- **Naming varies by app.** A common core recurs in eight apps (`command_list`, `command_run`, `command_batch`, `doc_inspect`, `render_preview`). Otherwise the vocabularies differ (`execute` vs `execute_command` vs `run_command`, `ui_click` vs `click`).

**ArtCraft (AI studio) [fact]**
- No MCP server in `storytold/artcraft`.
- Its API definitions include hosted MCP-session endpoints (`POST /v1/mcp/session/create`, refresh, revoke, list, delete: `artcraft:crates/api_clients/artcraft/artcraft_api_defs/src/mcp_sessions/create_mcp_session.rs`).
- The server side would be in `artcraft-services` (not inspected; fair-source licence). Whether a hosted, credit-billed MCP exists there is **not verified**.

## 5. Running the MCP servers and editors as WebAssembly

### (a) As a `wasm32-wasip2` component, without a browser

No repository targets WASI for an app or MCP server. The only WASI traces:
- FilmCraft runs some parser regression tests on `wasm32-wasip1` under Node's WASI (`filmcraft:docs/testing.md:62-84`).
- Craft Anything **hosts** WIT components with wasmtime (see (c)).

Blockers found in the dependencies [fact, with assessment marked]:

| Concern | Evidence | Effect |
|---|---|---|
| tokio features | PhotoCraft automation enables `rt-multi-thread`, `io-std`, `net` (`photocraft:crates/automation/Cargo.toml:33`). FilmCraft also enables `fs` (`filmcraft:crates/automation/Cargo.toml`). tokio 1.54.1 emits `compile_error!("Only features sync,macros,io-util,rt,time are supported on wasm.")` for those features unless `tokio_unstable` is set (crates.io tokio-1.54.1 `src/lib.rs:503-516`). `net` on wasip2 needs `tokio_unstable` (`src/lib.rs:460-470`). | rmcp/tokio servers (PhotoCraft, FilmCraft, TextureCraft, MaterialCraft) do not compile for wasip2 as they stand. [assessment] |
| Threads | rayon-core 1.13.0 (in PhotoCraft's lock file) falls back to the current thread when thread creation is "Unsupported", naming `wasm32-wasi` (`rayon-core-1.13.0/src/lib.rs:22-30`). VectorCraft's `serve` uses `std::thread::scope` (`vectorcraft:crates/mcp/src/server.rs:282`). EffectCraft's `serve` spawns a reader thread (`effectcraft:crates/automation/src/server.rs:108-113`). | rayon degrades rather than failing. The `serve` loops would need replacing. `handle_line` does not use threads. Whether std threads work on wasip2 is **not verified**: the rustc wasip2 page does not say. |
| Sockets | Bridge mode and the desktop control server use `std::net::TcpStream` and listeners (e.g. `vectorcraft:crates/mcp/src/backend.rs`; `apps/*/src/control_server.rs`). | Headless mode does not need them. |
| GPU | `wgpu` 30.0.1 on `wasm32` (non-emscripten) depends on `js-sys`, `wasm-bindgen` and `web-sys` (`wgpu-30.0.1/Cargo.toml:212-246`), i.e. browser bindings. PhotoCraft's MCP GPU renderer is an optional feature, off by default (`photocraft:crates/automation/Cargo.toml:9-16`). Headless rendering uses the CPU compositor, "used for export, tests, the CLI, and the web fallback" (`photocraft:docs/architecture.md:338`). | No GPU under WASI. Headless can use the CPU path. [assessment] |
| Native libraries | PhotoCraft: "C dependencies (optional LibRaw) only behind features… never on by default for the web target" (`photocraft:docs/architecture.md:184`). | Not a blocker by default |
| Process spawning | `craft-ai-mcp` starts `<app>-cli mcp` children (`craft-ai-integrations:crates/app/ai-mcp/src/lib.rs:4-9`). `photocraft-cli mcp` can launch the app (`photocraft:docs/mcp.md:57-64`). | The gateway and app launching cannot run under wasip2 as written. [assessment] |
| File system | Tools take paths under read and write roots (`photocraft:docs/mcp.md:38-45`). PhotoCraft uses `cap-std` (`photocraft:crates/automation/Cargo.toml:40`). The engine has a `FileSystem` trait with native, web and in-memory implementations (`photocraft:docs/architecture.md:459`). | Compatible in principle with WASI pre-opened directories. **Not verified** by a build. |

**Overall [assessment]**
- The **engines** are already kept wasm-clean for `wasm32-unknown-unknown` (CI gate: `photocraft:docs/architecture.md:182`).
- The **hand-written MCP servers** expose `handle_line(&str) -> Option<String>` and `handle(Value)` with no runtime and no socket:
  - `vectorcraft:crates/mcp/src/server.rs:339,370`
  - `lightcraft:crates/mcp/src/server.rs:94,116`
  - `designcraft:crates/mcp/src/server.rs:120,142`
  - `effectcraft:crates/automation/src/server.rs:63,92`
  - `pdfcraft:crates/automation/src/mcp.rs:123,132`
- That makes their headless mode the most direct candidate for a wasip2 component. None has been built for wasip2 (**not verified**).

### (b) In the browser

- The editors already ship browser builds (section 3).
- **No web build includes the MCP server.** PhotoCraft has "no TCP control server (browsers can't listen on sockets)" (`photocraft:apps/photocraft-web/src/main.rs:8`), and `photocraft-web`'s dependencies do not include `photocraft-automation` (`apps/photocraft-web/Cargo.toml`). DesignCraft's web build "can't be driven by AI assistants" (`craft-wiki:…/designcraft/install-update.md:57`).

### (c) A transport with no sockets or processes; mapping to typed calls (WIT)

**Transport-free cores exist [fact]**
- `craft-libs:crates/mcp` describes itself as transport-independent: "The caller owns routing, transport and JSON-RPC batching" (`src/lib.rs:3-5`).
- The hand-written servers' `handle_line` and `handle` functions are pure message-in, message-out.
- PhotoCraft's rmcp server accepts any `AsyncRead`/`AsyncWrite` pair (`photocraft:crates/automation/src/server/transport.rs:40-46`), but still runs on tokio.

**First-party WIT precedent [fact]**
- Craft Anything hosts plug-in components that export `craft-anything:plugin/tools@0.1.0`, with `describe: func() -> string` (a JSON array of `{name, title, description, input_schema}`) and `call: func(name: string, input: string) -> string` (`craft-anything:crates/engines/wit/plugin.wit:6-18`).
- Plug-ins import nothing and run with fuel and memory limits (`craft-anything:crates/engines/src/wasm_plugin.rs:1-12`).
- This is a **JSON-string** interface, not one typed WIT function per tool.

**Suitability for generating typed WIT functions [assessment from the facts in section 4]**
- **Feasible** for the app-level tools: each has a JSON Schema, from schemars structs or explicit literals. PdfCraft's 176 tools are the most uniform.
- **Not feasible** for the engine commands behind `command_run`/`execute`. Their parameters are free text, and `params` is an untyped `Value`.

## 6. The "covers 95 % of professional needs" claim

**I found no source that makes this claim.**
- Searching every app's README, ROADMAP, parity documents and the wiki found no "95 % of professional needs" wording.
- Two web searches found no such claim either ([search results included gigazine.net, geekextreme.com, artcraft.tips; none states it]).
- In the project's own documents, **95 % is a target, not a measurement**:
  - PhotoCraft: "Remaining to full parity (~95–100%): ~2,300–4,100 Opus 5.5 agent-hours" (`photocraft:docs/target-app-parity.md:24`). The audience table's column is "agent-hours to ~95%" (`:34`).
  - The only "~95%" readiness figure is for the automation dimension alone: "Automation: CLI, MCP, headless server, control channel | ~95% | Ahead of Photoshop here" (`photocraft:docs/target-app-parity.md:301`).
  - A superseded 2026-10-03 estimate ("82% 'of the way', 140–220 agent-hours to 95%") is kept for the record and called "far too optimistic" (`photocraft:docs/target-app-parity.md:26-31`).

**The project's own readiness figures**

| App | Feature breadth | "Ready for real work" | Stage | Source |
|---|---|---|---|---|
| PhotoCraft | ~76% | ~45% (40–50) | alpha | `photocraft:docs/target-app-parity.md:18-22` |
| VectorCraft | ~88% | ~62% full Illustrator; ~65% mainstream | alpha | `vectorcraft:docs/target-app-parity.md:189-193` |
| FilmCraft | ~86% | ~56% (51–61) | alpha | `filmcraft:docs/target-app-parity.md:17-21` |
| LightCraft | 83.2% (checklist), ~77% (weighted) | ~62% (57–67) | alpha | `lightcraft:docs/target-app-parity.md:15-22` |
| PdfCraft | ≈67% (tier-weighted) | ≈50% full Acrobat Pro; ≈55% mainstream | alpha | `pdfcraft:docs/target-app-parity.md:28-34`; `README.md:443` |
| EffectCraft | ≈91% | ≈45% (40–50) | alpha | `effectcraft:docs/target-app-parity.md:18-20` |
| DesignCraft | ~80% | ~47% (42–52) | **pre-alpha** | `designcraft:docs/target-app-parity.md:13-14`; `ROADMAP.md:3` |

**What each app says it lacks (from its own README or parity document)**
- **PhotoCraft:** "not yet a Photoshop replacement for daily professional work". The biggest gaps are "AI/generative features, 15 missing tools, depth in typography and pro workflows, and plug-in compatibility" (`photocraft:README.md:312`). `.8BF`/CEP/UXP plug-in hosting is "out of scope" (`photocraft:docs/architecture.md:480`).
- **FilmCraft:** speed on big footage (grading, keys and export on the CPU); no `.prproj` import; no VST3/AU/OpenFX plugins; H.264 is the only software delivery codec, with no AV1 export; real-world media less tested; few AI features (`filmcraft:README.md:301-308`).
- **LightCraft:** camera colour calibration; unsupported CR3 variants, Nikon HE NEFs and Olympus compressed ORF; heuristic AI masks; no X-Trans denoise or Super Resolution; no HDR display, video, or Book/Map modules (`lightcraft:README.md:351-360`).
- **PdfCraft:** "no office-document-to-PDF, and .docx export that loses layout" (`pdfcraft:README.md:443`). Also missing: most Preferences pages, AI providers, rich media/3D, a hosted web app (`pdfcraft:docs/target-app-parity.md:220`).
- **EffectCraft:** `.aep` projects can't be opened; fidelity is measured for one narrow case (`effectcraft:docs/target-app-parity.md:20`).
- **VectorCraft:** ranked list in `vectorcraft:docs/gaps.md` (referenced at `README.md:234`). Not summarised here.
- **DesignCraft:** pre-alpha. "EPS is still missing" (`designcraft:ROADMAP.md:214`). Gaps listed in `designcraft:docs/gaps.md` (not summarised).
- **Issue load is large:** PhotoCraft alone has 3,732 open issues (section 1).

## 7. Points that matter when embedding behind an AI agent

**Interface stability [fact]**
- All apps are 0.x (0.3–0.24).
- craft-libs is consumed by pinned git revisions, with up to 19 revisions in one app (section 1).
- `craft-ai-integrations` says "The extension APIs are still evolving". `craft-extensions` is described as "(provisional)" (`gh repo list`).
- Engine-command parameters are free-text documentation (section 4).
- PhotoCraft states that its CLI started rejecting unknown flags on 2026-10-07 (`photocraft:docs/roadmap.md:60`). That is a behaviour change within weeks.

**Telemetry [fact]**
- No telemetry SDK in any app's lock file.
- DesignCraft's About box says "Open source. No telemetry." (`designcraft:crates/ui-egui/src/about.rs:238`).
- The update check calls api.github.com by default (section 2). The ArtCraft Launcher fetches `https://api.storyteller.ai/v1/craft_apps/release_info` (`craft-launcher:crates/core/src/feed.rs`).

**Bundled models [fact]**
- No `.onnx`, `.safetensors`, `.gguf`, `.tflite`, `.pt` or `.rten` files in the seven app repositories or in ArtCraft (find).
- Models are downloaded on demand, pinned and hashed (section 2). Their licences are stated per model, for example Whisper as MIT and Apache-2.0 (`filmcraft:crates/speech/src/models.rs:8-10`).

**Trademarks [fact]**
- "The ArtCraft name, wordmark and logos in `docs/brand/` are trademarks of the ArtCraft Team and are not covered by this license… Forks and modified versions must remove them" (`photocraft:README.md:454-457`, under `docs/brand/LICENSE-brand.txt`).
- An Adobe trademark disclaimer follows (`photocraft:README.md:459`).
- The repositories call themselves "clean-room" reimplementations (`photocraft:docs/contributing.md:5`).

**Contributor terms [fact]**
- "Licence: contributions are MIT OR Apache-2.0" (`photocraft:docs/contributing.md:4`).
- No CLA or DCO text was found in CONTRIBUTING, docs or `.github` of the seven apps or ArtCraft (grep for CLA, DCO, Signed-off-by).

**Agent consent model [fact]**
- Live-app control requires the `AI-MCP` flag and the launcher switch. Headless sessions are confined to explicit read and write roots (section 4). An embedder using headless mode does not depend on the launcher.

## Not verified

- Whether any app compiles for `wasm32-wasip2`. Nothing was built.
- Whether std threads are available on wasip2.
- Who operates artcraftsuite.org and which builds it serves.
- Whether `artcraft-services` runs a hosted, credit-billed MCP.
- Full parameter lists for apps other than PhotoCraft and the gateway. Their schemas are in the cited files.
- The per-app network audit for the ten later apps.
