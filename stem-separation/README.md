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
| **Step 2: Project Creation** | Use the custom template and/or script. | **`riffkit/stem-separation/stem_template.RPP`** | A REAPER project with all stems aligned and grouped. |

#### External Dependencies: Demucs

You **must** have Demucs installed to run the core stemming step:

```bash
pip install demucs
```

* *Note: This repository does not host the stem separation code; it only provides the post-processing and REAPER integration steps.*

---

### 🚀 Usage Instructions

#### Option A: Automated (recommended)

Run `riftkit.py` from the repo root — it separates the stems and drops the template next to them:

```bash
./riftkit.py song.mp3 --output ~/music/projects
```

Then open the generated `stem_template.RPP` in REAPER and skip to Step 3 below.

#### Option B: Manual

1.  Run `demucs song.mp3` directly. Stems land in `separated/htdemucs/song/`.
2.  Copy **`stem_template.RPP`** from this directory into your project folder.
3.  Open the template in REAPER.

#### Step 3: Auto-import Stems with the Lua Script

1.  In REAPER: **Actions** → **Show Action List** → **Load ReaScript** → select `import_stems.lua`.
2.  Run the script and pick any one stem file when prompted.
3.  The script scans the folder and places each stem on its matching track (Vocals, Drums, Bass, Other) automatically.

You now have a fully functional practice project. Mute your own instrument track to play along, or lower the Bass track for **Joey** to practice his part.

---

### 🛠️ Next Steps & Future Development

* **Batch Processing:** Developing tools to process an entire setlist of songs at once.
* **Model Configuration:** Documenting settings that yield the best results for Demucs models (e.g. `htdemucs_ft` for fine-tuned separation).
