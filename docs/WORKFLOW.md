# riffkit Workflow Documentation

## Overview
This document describes the workflow from an incoming song file to a practice-ready REAPER project.

For command-level procedures, see [docs/sops/README.md](sops/README.md).

## Typical Flow

1. Receive the song as an MP3, WAV, or similar file.
2. Separate the song into stems with Demucs.
3. Generate or import lyrics with local Whisper-based transcription when needed.
4. Open the REAPER template.
5. Use the REAPER scripts to import stems, place lyrics, and prepare playback or performance controls.

## Example Scenario

For a church band:

1. Songs are delivered a few days before the service.
2. Each player learns their own part by muting that stem and practicing with the rest.
3. Lyrics can be displayed on a monitor or TV during rehearsal or performance.
4. The finished project becomes the band’s practice and playback reference for that service.
