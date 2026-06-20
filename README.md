# riffkit: Music Workflow for REAPER

***

### 🛠️ What is `riffkit`?

**`riffkit`** is the public-facing name for my music workflow system. Built around the **REAPER Digital Audio Workstation (DAW)**, it's a flexible collection of scripts and workflows for producing and consuming music and lyrics, from rough ideas to full-band collaboration.

**It is not a product or a startup.** It is my personal creative infrastructure, shared openly because you might find the components useful for your own creative work.

### 🎸 The Four Modes of `riffkit`

This infrastructure is built to support a resilient creative cycle, ensuring you spend less time on logistics and more time creating.

| Mode | Goal & Use Case | **`riffkit`**'s Role |
| :--- | :--- | :--- |
| **Learning** | Learn individual parts by isolating drums, guitar, bass, vocals, or keyboards. | **Slow-down playback** without pitch change, and **mute/diminish** specific stems so you can practice one part against the rest of the song. |
| **Rehearsal** | Practice as a band, distribute parts, and prep the full arrangement. | Easy generation of project files where bandmates can practice with their part muted, essentially acting as a **Digital Band Practice Manager**. |
| **Composition** | Capture and arrange ideas the moment inspiration hits. | Streamlined project templates for scratch tracks, with easy tools for **lyric sync** and **version control**. |
| **Performance** | Prepare the full media environment for live shows. | Centralized control over backing tracks, synchronized lyrics/chords on screen, and the potential to control external systems (like lighting or video). |

### 📌 Example Use Case: Church Band

`riffkit` is useful any time a group needs to turn songs into something people can actually rehearse and perform.

One concrete example:

* A church band plays twice a week.
* They receive 4 MP3s about 3 days before the service.
* Each song becomes its own REAPER project, usually with up to about five parts to manage.
* Each band member needs to learn their own part well enough to play the set.
* The band may also want lyrics on a large TV during rehearsal or performance.

In that workflow, `riffkit` helps by:

* separating the song into stems so each player can mute their own part and learn the others
* generating or syncing lyrics for a shared display
* building one REAPER project per song that is ready for practice or playback

### 📌 Example Use Case: Concert Ingestion

Sometimes the starting point is a full concert recording instead of clean song files.

In that workflow:

* a long MP3 or WAV contains multiple songs back-to-back
* `riffkit` splits the recording into individual song files first
* a sidecar `.txt` file can provide the song titles in order
* each resulting song can then flow through the normal stem / lyrics / REAPER project pipeline

### ⚙️ How It Works (The Core Components)

`riffkit` is intentionally modular. Grab the pieces you need, adapt them, or ignore the rest.

* **Audio Stemming:** Workflows for isolating individual **stems** (guitar, bass, drums, vocals) from a single mix using tools like **UVR (Ultimate Vocal Remover)**, creating customized backing tracks after processing time rather than instantly.
* **Lyrics & Sync:** Leverages **AI transcription** (Whisper) to generate synchronized lyrics and even **chord suggestions** from any audio file, which are then imported directly into the REAPER timeline via **Lua Scripts**.
* **Concert Splitting:** Breaks long multi-song recordings into individual song files before the normal workflow runs, using silence gaps as a first-pass boundary signal.
* **REAPER Scripts:** A growing collection of Lua scripts that automate repetitive tasks, turning the DAW into a powerful, custom-fit environment for your entire creative process.

*Note: concert splitting relies on `ffmpeg` and `ffprobe` being available on your PATH.*

### 🤝 Philosophy: Use It or Lose It

* **Built for Me First:** Features are added only when I need them for my own creative projects.
* **Share Without Obligation:** The code is **open source** for you to use or adapt. There are **no support promises** and no commercial roadmap.
* **Modular Design:** Take the scripts you need; leave the rest. The components are designed to work independently.

### 🧭 Public Direction

`riffkit` is aimed at small, real-world music workflows where people need to learn and perform a short set of songs with limited prep time.

Near-term focus:

* **Church band workflow:** take a handful of delivered MP3s, split stems, sync lyrics, and package the songs for practice and service playback.
* **Concert ingestion:** split a long live recording into song-sized files before running the normal workflow.
* **Part learning:** make it easy for each player to hear the rest of the band while muting their own part.
* **Lyric display:** support large-screen lyric viewing for rehearsal or performance.
* **Reliable packaging:** keep the output predictable so a project can be handed off and reused without a lot of manual cleanup.

For a longer view of where the project is headed, see [docs/ROADMAP.md](docs/ROADMAP.md).
For the concrete scenarios currently in scope, see [docs/USE_CASES.md](docs/USE_CASES.md).
For the testing approach and fixture plan, see [docs/TESTING.md](docs/TESTING.md).

***

**Ready to explore the components?**
Check the folders for specific REAPER scripts and documentation on the integrated workflows.

*Historical note: this project was originally called Songster.*
