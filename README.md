# Transscript

A tiny Windows desktop app that turns a video (or audio) file into a text transcript using OpenAI Whisper. Runs entirely on Windows.

---

## What you need

- Windows 10/11
- Python 3.10+ on Windows, on PATH (check with `where python` / `where pythonw`)
- `ffmpeg` on Windows PATH (check with `ffmpeg -version`)
- Two Python packages: `openai-whisper` + `tkinterdnd2`

### Will this run on other machines?

Yes. Nothing is hardcoded to a specific user or install path — the default output folder resolves to `%USERPROFILE%\Desktop\Transcripts`, and the launchers find `pythonw.exe` via PATH. To move this app to another Windows PC:

1. Copy the whole `Transscript\` folder to the new machine.
2. Install Python 3.10+ and make sure it's on PATH (`where python` should find it).
3. Install ffmpeg and make sure it's on PATH (`ffmpeg -version` should print something).
4. From the project folder, run `python -m pip install -r requirements.txt` once.
5. Double-click `run.vbs`.

### Video length & size?

No hard limit. Whisper streams audio through ffmpeg chunk-by-chunk, so a 3-hour file uses the same memory as a 30-second one. Only the **time** scales: roughly real-time or slower on CPU, much faster with a CUDA-capable GPU and an up-to-date NVIDIA driver. Any container ffmpeg supports is fine — mp4, mkv, mov, mp3, wav, etc.

---

## First-time setup (one time only)

Open **PowerShell** or **cmd**, `cd` into the project folder, and run:

```
python -m pip install -r requirements.txt
```

This pulls down PyTorch + Whisper (~2 GB, takes a few minutes), plus `tkinterdnd2` for drag-and-drop.

**The very first time** you pick a model (e.g. `base`), Whisper downloads that model's weights to `%USERPROFILE%\.cache\whisper\` (one-time, then cached). Model sizes: `tiny` ~75 MB, `base` ~150 MB, `small` ~500 MB, `medium` ~1.5 GB.

---

## How to launch

Three ways, all from the project folder:

| File             | What happens                                                        |
| ---------------- | ------------------------------------------------------------------- |
| `run.vbs`        | **Recommended.** Silent launch, no cmd window at all.               |
| `run.bat`        | Double-click friendly. Uses `pythonw.exe`, quick flash then hidden. |
| `transscript.py` | Direct: `python transscript.py` (shows console)                     |

**Tip:** right-click `run.vbs` → *Create shortcut* → drag the shortcut to your desktop/taskbar.

---

## Using the app

1. **Load a video.** Either:
   - drag-and-drop a video file onto the big drop zone at the top, or
   - click **Browse…** and pick one. The file dialog opens to `%USERPROFILE%\Desktop` by default.

   Supported extensions: `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.m4v`, `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`. Anything else will ask for confirmation.

2. **Pick a model.**

   | Model    | Speed   | Accuracy | When to use                |
   | -------- | ------- | -------- | -------------------------- |
   | `tiny`   | Fastest | Rough    | **Default — quick drafts** |
   | `base`   | Fast    | OK       | Good general balance       |
   | `small`  | Medium  | Good     | Important transcripts      |
   | `medium` | Slow    | Better   | When quality matters most  |

   > Whisper runs on **CPU** unless a compatible NVIDIA GPU + up-to-date driver is available. On CPU, expect roughly real-time: a 10-min clip at `base` may take 5–10 minutes.

3. **Pick an output folder.** Default is `%USERPROFILE%\Desktop\Transcripts\` (created on first transcription). Click **Change…** to pick a different one. Your choice is remembered across runs (stored in `config.json`).

4. **Click Transcribe.** The progress bar spins, status shows what's happening. On first use of a model, it'll say "Loading '<model>' model (first run downloads weights)…" — that's the one-time cache fill.

5. **When it's done:**
   - The transcript appears in the text box — scroll, edit, select freely.
   - A `.txt` is already saved in the output folder with the same name as the video (e.g. `meeting.mp4` → `meeting.txt`).
   - **Copy entire transcript** (big button above the text) grabs the whole thing to your clipboard.
   - **Save As…** lets you save a second copy anywhere.

---

## What's in the project folder

```
Transscript/
├── transscript.py      # The actual app (single file, ~300 lines)
├── requirements.txt    # openai-whisper + tkinterdnd2
├── run.vbs             # Silent launcher (recommended)
├── run.bat             # Alternate launcher
├── config.json         # Auto-created; remembers your output folder + model
└── README.md           # This file
```

---

## How it works

`transscript.py` imports `whisper` directly (it's a Python library) and calls `model.transcribe(path)`. The result is written to `<output_dir>/<video_stem>.txt` and also loaded into the GUI.

Model loading and transcription run on a background thread, so the UI stays responsive and you can copy-paste as soon as it's done.

Under the hood, the app also:
- Redirects `sys.stdout`/`sys.stderr` to `os.devnull` (required when running under `pythonw.exe`, otherwise `tqdm` inside Whisper crashes).
- Monkey-patches `subprocess.Popen` with `CREATE_NO_WINDOW` so Whisper's internal ffmpeg calls don't flash a console window.

---

## Troubleshooting

**"openai-whisper isn't installed into this Python"**
You missed the setup step. Run the pip install command above.

**ffmpeg errors ("Audio decoder missing" / "ffmpeg not found")**
Open cmd and type `ffmpeg -version`. If it says "not recognized", your PATH doesn't include the ffmpeg folder. Fix: Control Panel → System → Advanced → Environment Variables → add the `bin` subfolder of your ffmpeg install to the user `Path`.

**"Loading model…" takes forever the first time**
First-run download of model weights. Can be 75 MB (`tiny`) to 1.5 GB (`medium`) depending on choice. Subsequent runs load from `%USERPROFILE%\.cache\whisper\` in a few seconds.

**Transcription is really slow**
Expected on CPU. Pick `tiny` or `base` for speed; use `small`/`medium` only when accuracy matters. A modern NVIDIA GPU with a recent driver unlocks GPU mode automatically.

**App won't close / frozen**
Close the window — the background thread is daemonized and dies with the process.

**Drag-and-drop doesn't work**
`tkinterdnd2` didn't install. Re-run the setup command. The **Browse…** button still works regardless.

---

## Customizing

Everything lives in `transscript.py`. A few easy tweaks:

| Want to…                                             | Edit this                                                 |
| ---------------------------------------------------- | --------------------------------------------------------- |
| Change default output folder                         | `DEFAULT_OUTPUT_DIR` near the top                         |
| Add the `large` model to the dropdown                | Append `"large"` to `MODELS`                              |
| Transcribe non-English                               | Remove `language="en"` from the `model.transcribe()` call |
| Keep more transcript metadata (timestamps, segments) | Use `result["segments"]` instead of `result["text"]`      |

---

## Quick reference

- **Default transcripts folder:** `%USERPROFILE%\Desktop\Transcripts\`
- **Whisper model cache:** `%USERPROFILE%\.cache\whisper\`
- **Config file:** `config.json` in the project folder (auto-managed, safe to delete to reset)
