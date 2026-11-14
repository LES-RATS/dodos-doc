# Media

Statuses are defined in the [README](../README.md#status-legend). Unless a line says otherwise, this file is **Proposed** (14 November 2026, to validate).

## Codecs

- Free codecs first: AV1, VP9, Opus, FLAC.
- AV2 to follow: specification 1.0 published on 28 May 2026, about 30 % less bitrate than AV1; no optimised decoder and no consumer hardware found (search of 14 November 2026). Nothing to do before an optimised decoder exists; it will enter as one more component.
- H.264 and AAC through FFmpeg and Vulkan Video; patents to put to legal counsel.

## Protected video

- There is no route to Widevine today. An independent browser is still waiting for its licence (Zen), and nothing was found on EME in Ladybird (search of 14 November 2026, community sources).
- The user reports that Zen received its licence on 14 November 2026 (seen on X, not found again by search). If this is confirmed, the route exists for an independent browser, under conditions to find out.
- Position until then: an accepted and displayed limit; the workaround is casting from another device. To re-evaluate with volume.

## Hardware video decoding

**Open.** Through Vulkan Video. NVK decodes only H.264 since Mesa 26.3 (H.265 blocked, AV1 not confirmed), and depends on a nouveau patch to carry into the project's fork (verified 13 November 2026). In the meantime, software decoding by FFmpeg. The state of hardware video decoding in Ladybird is unknown.

## Fonts

One system family under the OFL licence, and Noto for script coverage and emoji.
