# REAPER Lua Scripts for riffkit

This directory holds the Lua scripts that power the high-level **Composition** and **Performance** modes within **`riffkit`**. These scripts focus on automating tedious, repetitive tasks to streamline your workflow and turn REAPER into a truly custom musical environment.

---

### 💡 Core Function

These scripts are built to offer one-click solutions for complex tasks, covering everything from capturing a spontaneous idea to preparing a full media environment for a live show.

---

### 🎸 Composition & Workflow Utilities

These scripts are designed for speed and efficiency, helping you move from a basic idea (a "riff") to a structured composition.

| Script Name | Function & Use Case | **riffkit** Mode |
| :--- | :--- | :--- |
| `quick_scratch_track.lua` | Automatically creates a new project with your preferred VSTs, tracks, and buses pre-loaded for rapid idea capture. | **Composition** |
| `version_snapshot.lua` | Creates a date/time-stamped backup of the project file and notes the current version in a dedicated metadata track. | **Composition** |
| `quick_master_bus_toggle.lua` | Toggles between production/mixing master bus chains and a clean playback/rehearsal master bus chain. | **Composition/Rehearsal** |

### 🎤 Performance & Remote Control Utilities

These scripts are focused on preparing and executing material for live use, leveraging REAPER's flexibility for stage setups.

| Script Name | Function & Use Case | **riffkit** Mode |
| :--- | :--- | :--- |
| `stage_lighting_sync.lua` | Sends MIDI/OSC messages based on markers in the REAPER timeline to control external lighting or video systems. | **Performance** |
| `live_lyric_viewer.lua` | Reformats the synchronized lyrics data (from `lyrics-sync`) into a clean, large-font teleprompter view for an external monitor. | **Performance** |
| `smart_midi_remote.lua` | Customizes REAPER's remote control surfaces to map smartphone/tablet inputs to specific **`riffkit`** functions (e.g., "Start/Stop Track," "Mute My Stem"). | **Performance** |

---

### ⚙️ Installation & Usage

1.  **Placement:** Place all `.lua` files into your REAPER Scripts folder (usually found under `C:\Users\username\AppData\Roaming\REAPER\Scripts` on Windows, or similar paths on macOS/Linux).
2.  **Mapping:** Access the scripts via **Action** $\rightarrow$ **Show Action List...**
3.  **Keybinds:** For maximum efficiency, map frequently used scripts (like `quick_scratch_track.lua`) to custom keyboard shortcuts or MIDI controllers.

---

### 🛠️ Notes & Future Development

* **Remote Control Setup:** To use `smart_midi_remote.lua` with a smartphone/tablet, enable your MIDI-over-network or OSC-to-MIDI app as a MIDI input device in **Options → Preferences → MIDI Devices**.  Edit the `CC_MAP` table at the top of the script to match your controller layout.
* **Lighting Hardware:** `stage_lighting_sync.lua` sends MIDI to REAPER's virtual keyboard input.  For hardware output, create a MIDI track set to monitor input and route its output to your lighting device.
* **OSC/MIDI Template:** A universal controller template for popular OSC apps (TouchOSC, MIDI Designer) is a planned future addition.
