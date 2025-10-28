# Songster: Personal Music Production Workflow

**MP3 → practice-ready REAPER project in 5 minutes**

Stem separation + synchronized lyrics + flexible playback for learning covers, writing songs, and playing with bands.

---

## What This Is

This is my personal music production environment. I'm a 64-year-old guitarist with 50+ years of playing experience and 35+ years as a professional software developer (PE). I got tired of spending 30+ minutes on manual workflows every time I wanted to learn a cover, practice with my church band, or record for YouTube.

**Songster connects existing tools into an integrated workflow:**
- Take any MP3 (like an SRV song I want to learn)
- Separate it into stems (vocals, drums, bass, guitar)
- Transcribe vocals to synchronized lyrics
- Generate a REAPER project ready for practice
- Mute my instrument, play along with the rest of the band
- Adjust tempo without changing pitch
- Display lyrics on a big screen if needed

**This is personal infrastructure, not a product.** It works for me. It might work for you. I'm sharing it because someone else might find it useful, and documenting helps me think.

---

## Status

**Working:**
- ✅ Whisper transcription to synchronized lyrics ([existing repo](https://github.com/owencorpening/Reaper_InsertLyrics))
- ✅ UVR stem separation (manual workflow)
- ✅ REAPER Lua scripts for lyrics insertion
- ✅ Daily use for real music work

**In Progress:**
- 🔨 Python integration script (connecting the pieces)
- 🔨 One-command MP3 → project workflow
- 🔨 REAPER project templates

**Planned:**
- 📋 Phone remote control (OSC)
- 📋 Big screen lyrics display
- 📋 Better batch processing

**Philosophy:** Features get added when I need them for my own work. No roadmap, no promises, no pressure.

---

## Real Use Cases

### Learning Covers (My Primary Use)
**Example: Learning a Stevie Ray Vaughan song for YouTube**

Before Songster: 30-45 minutes of manual work
- Download MP3
- Run through stem separator
- Create REAPER project manually
- Import each stem to tracks
- Run Whisper separately
- Parse JSON and insert lyrics
- Set up routing and monitoring

With Songster: ~5 minutes
```bash
songster "srv_texas_flood.mp3"
# Opens REAPER with stems on tracks, lyrics synchronized, ready to practice
```

I mute the guitar track, play along with vocals/bass/drums, and the lyrics are right there on the timeline.

### Church Band Prep
Get 3-5 songs on Thursday, need to be ready by Sunday.

**Old way:** Spend Friday evening manually prepping each song  
**Songster way:** Run the script Friday morning, practice Friday afternoon

### Writing Originals
When inspiration hits, I need to capture ideas without workflow friction.

**Use Songster's templates to:**
- Quick-start recording sessions
- Layer scratch tracks
- Add vocal melodies with automatic transcription
- Keep everything synchronized and organized

### Teaching Students
Create practice tracks with their part muted, lyrics visible, tempo adjustable.

---

## How It Works

### The Workflow
```
MP3 file
    ↓
UVR (Ultimate Vocal Remover) - separates stems
    ↓
vocals.wav, drums.wav, bass.wav, other.wav
    ↓
Whisper - transcribes vocals with timestamps
    ↓
lyrics.json
    ↓
Python script - generates REAPER project
    ↓
REAPER project with:
  - Stems imported to tracks
  - Lyrics as items on timeline
  - Proper routing and monitoring
  - Ready for practice/performance
```

### The Tools
- **Ubuntu Studio Linux** - Purpose-built for audio (real-time kernel, JACK audio)
- **REAPER DAW** - Scriptable, powerful, affordable ($60)
- **UVR** - Stem separation (vocals, drums, bass, other)
- **Whisper** - OpenAI's transcription model
- **Python + Lua** - Glue and automation
- **All open source or one-time purchase** - No subscriptions

---

## Installation

### Prerequisites
```bash
# Ubuntu Studio (or similar Linux with audio setup)
# REAPER installed
# Python 3.8+

sudo apt install python3-pip python3-tk ffmpeg git
```

### 1. Install UVR (Ultimate Vocal Remover)
```bash
git clone https://github.com/Anjok07/ultimatevocalremovergui.git
cd ultimatevocalremovergui
pip3 install -r requirements.txt

# Test it
python3 UVR.py
```

### 2. Install Whisper
```bash
pip3 install openai-whisper
```

### 3. Install Songster Scripts
```bash
git clone https://github.com/[your-username]/songster.git
cd songster
pip3 install -r requirements.txt

# Make the main script executable
chmod +x songster.py
```

### 4. Install REAPER Lua Scripts
```bash
# Copy Lua scripts to REAPER's Scripts folder
cp scripts/reaper/*.lua ~/.config/REAPER/Scripts/

# In REAPER: Actions → Show action list → ReaScript → Load
# Select the InsertLyrics.lua script
```

---

## Usage

### Quick Start: Process a Song
```bash
# Basic usage
./songster.py "my_song.mp3"

# Specify output directory
./songster.py "srv_texas_flood.mp3" --output ~/music/projects/

# Use specific UVR model
./songster.py "song.mp3" --model MDX23C

# Skip stem separation (if you already have stems)
./songster.py "song.mp3" --stems-only

# Skip transcription (instrumental track)
./songster.py "song.mp3" --no-lyrics
```

### Manual Workflow (If You Prefer Control)
```bash
# 1. Separate stems with UVR
cd ultimatevocalremovergui
python3 UVR.py
# Use GUI to process your MP3

# 2. Transcribe vocals
whisper vocals.wav --model medium --output_format json

# 3. Create REAPER project manually or use template

# 4. In REAPER: Run InsertLyrics.lua script
# Actions → InsertLyrics → Select the JSON file
```

---

## Configuration

Edit `config.yaml` to customize:

```yaml
# Paths
uvr_path: "/path/to/ultimatevocalremovergui"
reaper_projects: "~/music/projects"
templates: "~/.config/songster/templates"

# UVR Settings
default_model: "MDX23C"  # Or "htdemucs", "demucs", etc.

# Whisper Settings
whisper_model: "medium"  # Or "small", "large"
language: "en"

# REAPER Settings
default_tempo: 120
time_signature: "4/4"
```

---

## Project Structure

```
songster/
├── README.md                 # This file
├── LICENSE                   # MIT License
├── songster.py              # Main integration script
├── config.yaml              # User configuration
├── requirements.txt         # Python dependencies
│
├── scripts/
│   ├── reaper/
│   │   ├── InsertLyrics.lua       # Lyrics insertion
│   │   └── CreateProject.lua      # Project generation
│   ├── separate_stems.py          # UVR wrapper
│   ├── transcribe.py             # Whisper wrapper
│   └── create_project.py         # REAPER project generator
│
├── templates/
│   ├── practice.RPP-template      # 4-track practice template
│   ├── recording.RPP-template     # Multi-track recording
│   └── performance.RPP-template   # Live performance with backing
│
├── docs/
│   ├── WORKFLOW.md               # Detailed workflow documentation
│   ├── TROUBLESHOOTING.md        # Common issues and solutions
│   └── EXAMPLES.md               # Real-world examples
│
└── examples/
    └── srv_example/              # Example workflow with sample files
```

---

## Examples

### Example 1: Learning an SRV Cover
```bash
# Download "Texas Flood" MP3
youtube-dl [url] -o texas_flood.mp3

# Process it
./songster.py texas_flood.mp3

# Songster creates:
# ~/music/projects/texas_flood/
#   ├── texas_flood.RPP          (REAPER project)
#   ├── stems/
#   │   ├── vocals.wav
#   │   ├── drums.wav
#   │   ├── bass.wav
#   │   └── guitar.wav
#   └── lyrics.json

# Open in REAPER, mute guitar track, play along
```

### Example 2: Church Band Prep
```bash
# Batch process multiple songs
for song in *.mp3; do
    ./songster.py "$song" --template performance
done

# Creates practice projects for the whole band
# Sunday morning: load projects, display lyrics, play
```

### Example 3: Writing an Original
```bash
# Use the composition template
./songster.py --new-project "my_song" --template composition

# Records to scratch tracks
# Run Whisper on vocal takes
# Keeps everything synchronized
```

---

## FAQ

### Is this a product?
No. It's personal infrastructure I use daily. I'm sharing it because someone else might find it useful.

### Will you add feature X?
If I need it for my own music work, probably. Otherwise, pull requests are welcome.

### Do you provide support?
No promises. I'll answer questions when I can. The code is documented. Issues and discussions are welcome.

### Why REAPER and not [other DAW]?
REAPER is scriptable (Lua, Python, EEL), affordable ($60), runs great on Linux, and doesn't require subscriptions. For this kind of workflow automation, it's perfect.

### Why UVR instead of Demucs?
I used UVR on my Mac for years. I know which models sound good for my use cases. Demucs is also excellent—use whatever works for you.

### Can I use this on Windows/Mac?
Maybe. The Python scripts should work. UVR works on all platforms. REAPER works everywhere. You'll need to adjust paths and possibly some audio routing.

### Does this work with [other stem separator]?
Yes, if you modify `separate_stems.py` to call your preferred tool. It's modular.

### Can I use this commercially?
Yes (MIT License). But it's designed for personal/small-scale use. If you're building a commercial product, you probably need something more robust.

### Why share this at all?
Because documenting helps me think. Because someone else might find it useful. Because open source is how I learned to code.

---

## Contributing

This is personal infrastructure, but contributions are welcome:

- **Bug reports:** Open an issue
- **Feature requests:** Describe your use case (I might need it too)
- **Pull requests:** Keep them focused and documented
- **Documentation:** Always appreciated
- **Examples:** Share your workflows

**No contribution is too small.** Fixed a typo? Found a better way to do something? Share it.

---

## Technical Notes

### Why Python + Lua?
- Python for workflow automation and file processing
- Lua for REAPER integration (it's REAPER's native scripting language)
- Both are readable and maintainable

### Why Not a GUI?
Maybe later. Command-line is faster for power users, easier to script, and I can integrate it into my existing workflows. If someone wants to build a GUI, go for it.

### Performance
On my Ubuntu Studio mini-PC:
- UVR stem separation: ~2-3 minutes for a 4-minute song
- Whisper transcription: ~30 seconds (medium model)
- REAPER project creation: ~5 seconds
- **Total:** ~5 minutes hands-off processing

### Storage
Each processed song creates ~100-150MB of files (stems + project). Plan accordingly.

---

## Background: Why This Exists

I've been playing guitar for 50+ years and writing code professionally for 35+ years (PE). At 64, retired, I wanted to spend more time making music and less time on tedious workflows.

Every time I wanted to:
- Learn a cover for YouTube
- Prep songs for church band
- Capture a composition idea
- Create a practice track

...I was doing the same manual steps. Separate stems. Transcribe. Import. Set up. Over and over.

**I'm a software developer. This is automation problem.**

So I built Songster. Not as a product. Not for a market. Just as **personal creative infrastructure** that makes my musical life better.

I'm sharing it because:
1. Documenting helps me think
2. Someone else might find it useful
3. Open source is how I learned to code
4. Maybe someone will contribute improvements

If it helps you learn that SRV solo, write that song, or prep for Sunday service—great. If not, that's fine too. I'll still be here, making music with these tools.

---

## Related Projects

- **Whisper:** https://github.com/openai/whisper
- **UVR:** https://github.com/Anjok07/ultimatevocalremovergui
- **REAPER:** https://www.reaper.fm/
- **My Substack:** https://owencorpening.substack.com/ (writing about the process)

---

## License

MIT License - Do whatever you want, just credit the source.

See [LICENSE](LICENSE) for details.

---

## Contact

- **GitHub Issues:** For bugs, questions, feature requests
- **Discussions:** For sharing workflows, examples, ideas
- **Substack:** For longer-form writing about the process

---

*"The best camera is the one you have with you. The best music production workflow is the one that gets out of your way."*

---

**Status:** Personal project, actively used, shared generously.  
**Last Updated:** October 2025