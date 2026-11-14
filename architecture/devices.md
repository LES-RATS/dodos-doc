# Device-to-device communication

Statuses are defined in the [README](../README.md#status-legend). Unless a line says otherwise, this file is **Proposed**.

Device-to-device communication and the companion application are deferred until after the alpha (**Decided**, 14 November 2026); the [calendar](../plan/roadmap.md#calendar) places them in 2028.

## Principle

Another device is only one more holder of capabilities. Everything is already a capability behind a WIT interface, so exposing an object, an action or a peripheral remotely needs no separate API (network transparency of Plan 9).

Model (**Decided**, 14 November 2026): distributed capabilities (CapTP, Cap'n Proto), to cite and to read.

## Identity

- Each device has a key.
- Pairing is a key exchange by a displayed code or by contact.
- The devices of one person form a **circle**. The devices of a relative or friend receive limited capabilities.
- **Lost device** (**Decided**, 14 November 2026): any device of the circle withdraws the lost device's key; its capabilities are revoked at the next contact, and its disk stays encrypted.

## Transport

- A direct connection, encrypted end to end, addressed by key and not by IP address, with a relay as fallback.
- Candidate: iroh (Rust, 1.0 since 15 June 2026, QUIC, NAT traversal, stable protocol).
- Local discovery by mDNS and Bluetooth Low Energy.
- The same transport exposes services without an open port (see [network.md](network.md#key-addressed-services)).

## What it gives

- Clipboard and sending of objects.
- Synchronisation. Immutable blobs addressed by hash synchronise without conflict; modifiable objects synchronise by versions. An object modified on both sides: both versions are kept (**Decided**, 14 November 2026).
- Moving a running surface to another device. This goes through `suspend` and `resume`, the only path that crosses two architectures (**Decided**, 14 November 2026; see [platform.md](platform.md#process-state-suspend-resume-and-snapshots)).
- Lent peripherals: the phone's camera and microphone, the desktop's GPU for the laptop's agent.
- A single agent and a single memory on all devices. The agent's memory is an append-only log, merged by union (**Decided**, 14 November 2026; see [agent.md](agent.md#memory)).
- Actions invoked remotely.

## Devices that do not run DodOS

This is the critical point, because the project has no phone.

1. The hosted userland as a companion application on Android, iOS, Linux, macOS and Windows.
2. The web: WebRTC, passkeys between devices.
3. KDE Connect and LocalSend only as optional gateways, as Wasm components, for those who already have them. They are not the product, and they are well integrated nowhere (opinion of the user, 14 November 2026).

The product is the project's own protocol and its companion application. Phones with an unlockable bootloader: native DodOS, later.

To verify: what the platforms open up (Wi-Fi Aware on iOS, interoperability of Quick Share and AirDrop; from memory).

## To study

- AirPlay, Cast and Miracast receivers.
- Matter for the home.
