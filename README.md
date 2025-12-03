# riffkit: The Composer's Creative Infrastructure

***

### 🛠️ What is `riffkit`?

**`riffkit`** is my personal, evolving system for creating, rehearsing, and producing music. Built around the **REAPER Digital Audio Workstation (DAW)**, it's a flexible collection of scripts and workflows designed to bridge the gap between initial musical ideas and full band collaboration.

**It is not a product or a startup.** It is my personal creative infrastructure, shared openly because you might find the components useful for your own creative work.

### 🎸 The Four Modes of `riffkit`

This infrastructure is built to support a resilient creative cycle, ensuring you spend less time on logistics and more time creating.

| Mode | Goal & Use Case | **`riffkit`**'s Role |
| :--- | :--- | :--- |
| **Learning** | **Quickly master** new songs, chords, and leads from any track. | **Slow-down playback** without pitch change, and **mute/diminish** specific instrument stems for isolated practice. |
| **Rehearsal** | Practice as a band, distribute parts, and prep the full arrangement. | Easy generation of project files where bandmates can practice with their part muted, essentially acting as a **Digital Band Practice Manager**. |
| **Composition** | Capture and arrange ideas the moment inspiration hits. | Streamlined project templates for scratch tracks, with easy tools for **lyric sync** and **version control**. |
| **Performance** | Prepare the full media environment for live shows. | Centralized control over backing tracks, synchronized lyrics/chords on screen, and the potential to control external systems (like lighting or video). |

### ⚙️ How It Works (The Core Components)

`riffkit` is intentionally modular. Grab the pieces you need, adapt them, or ignore the rest.

* **Audio Stemming:** Workflows for isolating individual **stems** (guitar, bass, drums, vocals) from a single mix using tools like **UVR (Ultimate Vocal Remover)**, instantly creating customized backing tracks.
* **Lyrics & Sync:** Leverages **AI transcription** (Whisper) to generate synchronized lyrics and even **chord suggestions** from any audio file, which are then imported directly into the REAPER timeline via **Lua Scripts**.
* **REAPER Scripts:** A growing collection of Lua scripts that automate repetitive tasks, turning the DAW into a powerful, custom-fit environment for your entire creative process.

### 🤝 Philosophy: Use It or Lose It

* **Built for Me First:** Features are added only when I need them for my own creative projects.
* **Share Without Obligation:** The code is **open source** for you to use or adapt. There are **no support promises** and no commercial roadmap.
* **Modular Design:** Take the scripts you need; leave the rest. The components are designed to work independently.

***

**Ready to explore the components?**
Check the folders for specific REAPER scripts and documentation on the integrated workflows.