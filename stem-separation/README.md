# stem-separation: Isolate Parts for Practice

This workflow is the backbone of the **Learning** and **Rehearsal** modes, allowing you to quickly strip out an instrument or create customized backing tracks for your bandmates.

It focuses on automating the process of taking a single audio file and splitting it into component stems (Vocals, Drums, Bass, Other).

---

### 💡 Core Function

The goal is to provide a seamless process to:

1.  **Extract** individual tracks (stems) from a stereo mix (MP3, WAV, etc.).
2.  **Import** those stems into a **REAPER Project Template** (`.RPP`) with tracks correctly labeled, routed, and ready for practice.

This transforms any song into a customizable practice tool where you can mute your own instrument, slow down the tempo, and start playing along.

---

### ⚙️ Workflow & Dependencies

This component acts as a **workflow wrapper** around powerful external AI models.

| Step | Action | Required Tool/Dependency | Output |
| :--- | :--- | :--- | :--- |
| **Step 1: Separation** | Run your audio file through a separation model. | **Demucs** or **Spleeter** (external AI tools) | 4-6 separate WAV files (e.g., `bass.wav`, `drums.wav`, etc.). |
| **Step 2: Project Creation** | Use the custom template and/or script. | **`riftkit/stem-separation/stem_template.RPP`** | A REAPER project with all stems aligned and grouped. |

#### External Dependencies: Demucs / Spleeter

You **must** have a working installation of a modern stem separation tool (like **Demucs** or **Spleeter**) accessible from your system to run the core separation step.

* *Note: This repository does not host the stem separation code; it only provides the post-processing and REAPER integration steps.*

---

### 🚀 Usage Instructions

#### Step 1: Separate the Audio

1.  Take your song's master audio file and run it through your configured **Demucs** or **Spleeter** installation.
2.  Ensure the separated files (stems) are placed into a new, dedicated project folder (e.g., `/MyProject/Stems/`).

#### Step 2: Load the REAPER Template

1.  Copy the **`stem_template.RPP`** file from this directory into your new project folder.
2.  Open the template file in REAPER.
3.  The template contains pre-labeled and pre-routed tracks (Bass, Drums, Guitar, etc.).

#### Step 3: Insert and Align Stems

1.  In REAPER, use **File** $\rightarrow$ **Insert media file...**
2.  Select all the separated stems from your `/Stems/` folder.
3.  **Crucially:** Drag and drop the stems onto their corresponding, pre-labeled tracks in the template.

You now have a fully functional practice project. You can mute the Guitar track to play along or lower the volume on the Bass track for **Joey** to practice his part.

---
### 🛠️ Next Steps & Future Development

* **Automated Import Script:** Create a Lua script that automatically detects and aligns common stem names, eliminating the manual drag-and-drop in Step 3.
* **Batch Processing:** Developing tools to process an entire setlist of songs at once.
* **Model Configuration:** Documenting settings that yield the best results for separation models.