# lyrics-sync: AI-Powered Lyric & Chord Synchronization

This component is the engine behind `riffkit`'s **Learning** and **Composition** modes, turning any audio file into a time-coded, editable project with lyrics and/or chord suggestions.

It uses two primary tools to achieve this: **local Whisper transcription** and **custom REAPER Lua scripts**.

---

### 💡 Core Function

The goal is to automatically take an audio file (MP3, WAV, etc.) and generate a REAPER project where:

1.  The lyrics are **synchronized** precisely to the audio track.
2.  Each word/phrase is placed on the timeline as an editable **REAPER Item**.
3.  Optional **chord suggestions** are included for quick learning.

This is far faster than manually typing lyrics and setting time markers!

---

### ⚙️ Workflow & Dependencies

This component is a **two-step workflow** that requires one external dependency:

| Step | Action | Required Tool/Dependency | Output |
| :--- | :--- | :--- | :--- |
| **Step 1: Transcription** | Run the vocal stem through `transcribe_adaptive.py` (adaptive multi-pass local Whisper). | **Local `openai-whisper`** via `lyrics-sync/transcribe_adaptive.py` | A **`riffkit-transcript-v1` JSON file** with word-level timestamps. |
| **Step 2: Import** | Run the custom script inside REAPER. | **`riftkit/lyrics-sync/InsertLyrics.lua`** (Whisper JSON) or **`AddLyrics.lua`** (plain text) | Lyrics inserted as timed items on a REAPER track. |

#### External Dependency: Local Whisper

You must have a workflow that produces timestamped JSON locally. For this pass, use the repo virtualenv and `openai-whisper` to generate a JSON transcript with word timestamps when you need word-level timing.

* *Note: This repository does not host the model weights; it expects a local Whisper install in your working environment.*

---

### 🚀 Usage Instructions

#### Step 1: Prepare the JSON

1.  Place the song audio file (ideally an isolated vocals stem) in your desired project directory.
2.  Run the adaptive transcription pipeline — see [docs/session1-transcription-notes.md](../docs/session1-transcription-notes.md) for full options:

    ```bash
    .venv/bin/python lyrics-sync/transcribe_adaptive.py vocals.mp3 \
      --lyrics reference_lyrics.txt   # optional: disambiguates misheard words
    ```

3.  Keep the JSON file in the same directory as your REAPER project file (`.RPP`) or wherever you want to browse for it.

#### Step 2: Run the REAPER Script

Two scripts are available depending on your source material:

| Script | Use when… |
| :--- | :--- |
| **`InsertLyrics.lua`** | You have Whisper JSON with `segments` or `words` timestamps. |
| **`AddLyrics.lua`** | You have a plain `.txt` file; the script auto-aligns lines to peaks or silences in the Vocals track. |

For either script:

1.  Open or create your REAPER project and ensure a track named **Lyrics** exists.
2.  In REAPER, go to **Actions** → **Show Action List** → **Load ReaScript**.
3.  Select the appropriate script and run it. A file picker will prompt for your JSON or `.txt` file.
4.  Lyrics are inserted as timed media items on the Lyrics track.

#### Troubleshooting

* If the lyrics don't appear, verify a track named exactly **Lyrics** exists in the project.
* For `InsertLyrics.lua`, confirm the JSON contains Whisper-style `segments` or `words` data, or the older legacy `transcription` array.
* For `AddLyrics.lua`, ensure a track named **Vocals** exists with audio — the script uses it for timing detection.
* Check the REAPER Console for error messages from the script.

---
### 🛠️ Next Steps & Future Development

* **Batch Processing:** Currently, this is a per-song operation. Future development will focus on batch processing multiple files.
* **Chord Integration:** Integrating a separate chord detection library to add a chord track in parallel with the lyric track.
* **Configuration:** Adding a simple user interface to let users specify the JSON format or track placement.
