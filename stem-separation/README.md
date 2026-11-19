# stem-separation: Isolate Parts for Practice

This workflow is the backbone of **riffkit**'s **Learning** and **Rehearsal** modes, allowing you to quickly strip out an instrument or create customized backing tracks for your bandmates.

It focuses on automating the process of taking a single audio file and **stemming** it (splitting it into its component tracks: Vocals, Drums, Bass, Other).

---

### 💡 Core Function

The goal is to provide a seamless process to:

1.  **Extract** individual tracks (**stems**) from a stereo mix (MP3, WAV, etc.) using AI tools.
2.  **Import** those stems into a **REAPER Project Template** (`.RPP`) with tracks correctly labeled, routed, and ready for practice.

This transforms any song into a customizable practice tool where you can mute your own instrument, slow down the tempo, and start playing along.

---

### ⚙️ Workflow & Dependencies

This component acts as a **workflow wrapper** around powerful external AI models.

| Step | Action | Required Tool/Dependency | Output |
| :--- | :--- | :--- | :--- |
| **Step 1: Stemming** | Run your audio file through Demucs. | **Demucs** (`pip install demucs`) | 4 WAV files: `vocals.wav`, `drums.wav`, `bass.wav`, `other.wav` |
| **Step 2: Project Creation** | riffkit writes a `.RPP` with the stems on named tracks. | **`riffkit/reaper_project.py`** | A REAPER project: Vocals, Drums, Bass, Other, plus the original mix muted. |

#### External Dependencies: Demucs

You **must** have Demucs installed to run the core stemming step:

```bash
pip install demucs
```

* *Note: This repository does not host the stem separation code; it only provides the post-processing and REAPER integration steps.*

---

### 🚀 Usage Instructions

#### Option A: Automated (recommended)

Run `riftkit.py` from the repo root. It separates the stems (model
`htdemucs_ft`, WAV output) and writes a project file next to them:

```bash
./riftkit.py song.mp3 --output ~/music/projects
```

Open `~/music/projects/htdemucs_ft/song/song.RPP` in REAPER. The four stems
are on their tracks and the original song is on a muted last track, so
you can switch between the mix and the parts. Nothing to import.

Other models: `--stem-model htdemucs` is about four times faster and
rougher; `--stem-model htdemucs_6s` adds guitar and piano stems.

#### Option B: Manual

1.  Run `demucs -n htdemucs_ft song.mp3` directly. Stems land in `separated/htdemucs_ft/song/`.
2.  Open any REAPER project with tracks named Vocals, Drums, Bass and Other
    (`stem_template.RPP`, if you have one, is not in the repo).
3.  **Actions** → **Show Action List** → **Load ReaScript** → select `import_stems.lua`,
    run it and pick any one stem file. It places each stem on its matching track.

You now have a fully functional practice project. Mute your own instrument track to play along, or lower the Bass track for **Joey** to practice his part.

---

### 🛠️ Next Steps & Future Development

* **Batch Processing:** Developing tools to process an entire setlist of songs at once.
* **Model Configuration:** `htdemucs_ft` is now the default. Still to document: Demucs `--shifts` and overlap settings, and whether UVR's RoFormer models do better on live recordings.
