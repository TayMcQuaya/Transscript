"""Simple desktop transcription app — pure Windows, in-process Whisper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import Tk, Toplevel, StringVar, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

# --- pythonw.exe fixups ---------------------------------------------------
# 1) Under pythonw.exe, sys.stdout/stderr are None. Anything that writes to
#    stderr (tqdm inside whisper, any library print) crashes with
#    "NoneType has no 'write'". Point them at devnull.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# 2) Each child process launched by whisper (ffmpeg, etc.) flashes a cmd
#    window because they're console-subsystem binaries. Default Popen to
#    CREATE_NO_WINDOW so nothing pops up.
if sys.platform == "win32":
    _CREATE_NO_WINDOW = 0x08000000
    _orig_popen_init = subprocess.Popen.__init__

    def _silent_popen_init(self, *args, **kwargs):
        if "creationflags" not in kwargs:
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _silent_popen_init
# --------------------------------------------------------------------------

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

MODELS = ["tiny", "base", "small", "medium"]
DEFAULT_MODEL = "tiny"
DEFAULT_OUTPUT_DIR = str(Path.home() / "Desktop" / "Transcripts")
DEFAULT_BROWSE_DIR = str(Path.home() / "Desktop")
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v",
              ".mp3", ".wav", ".m4a", ".flac", ".ogg"}
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"

MODEL_TOOLTIP = (
    "Which Whisper model to use.\n\n"
    "• tiny   — fastest, rough accuracy. Best for quick drafts.\n"
    "• base   — fast, okay accuracy. Good general default.\n"
    "• small  — slower, good accuracy. For important transcripts.\n"
    "• medium — slowest, best accuracy. Use when quality matters.\n\n"
    "CPU-only on this machine, so 'tiny' or 'base' are the practical picks."
)
OUTPUT_TOOLTIP = (
    "Where the .txt transcript file will be saved.\n\n"
    "The filename matches the video's name (e.g. meeting.mp4 → meeting.txt).\n"
    "Your choice is remembered between runs."
)
DROP_TOOLTIP = (
    "Drag a video or audio file here, or use Browse below.\n\n"
    "Supported: mp4, mkv, mov, avi, webm, m4v, mp3, wav, m4a, flac, ogg."
)
TRANSCRIBE_TOOLTIP = (
    "Start transcribing the loaded file.\n"
    "Runs on a background thread — the window stays usable while it works."
)
COPY_TOOLTIP = "Copy the full transcript to your clipboard."
SAVE_TOOLTIP = "Save a copy of the transcript to a different location/filename."

_MODEL_CACHE: dict[str, object] = {}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"output_dir": DEFAULT_OUTPUT_DIR, "model": DEFAULT_MODEL}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass


def strip_drop_path(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("{"):
        end = raw.find("}")
        if end != -1:
            return raw[1:end]
    return raw.split()[0] if " " in raw and not os.path.exists(raw) else raw


class Tooltip:
    """Lightweight tooltip that appears next to a widget on hover."""

    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay = delay_ms
        self._after_id: str | None = None
        self._tip: Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        frame = ttk.Frame(self._tip, relief="solid", borderwidth=1, padding=(8, 6))
        frame.pack()
        ttk.Label(
            frame, text=self.text, justify="left", wraplength=360,
            background="#ffffe0",
        ).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


def transcribe(video_path: str, model_name: str, output_dir: str,
               status_cb=None) -> tuple[bool, str, str]:
    try:
        import whisper
    except ImportError as e:
        return False, (
            "openai-whisper isn't installed into this Python.\n\n"
            "Fix: open cmd/PowerShell and run:\n"
            '  python -m pip install openai-whisper\n\n'
            f"Import error: {e}"
        ), ""

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        return False, f"Can't create output folder:\n{output_dir}\n\n{e}", ""

    try:
        if model_name in _MODEL_CACHE:
            model = _MODEL_CACHE[model_name]
        else:
            if status_cb:
                status_cb(f"Loading '{model_name}' model (first run downloads weights)…")
            model = whisper.load_model(model_name)
            _MODEL_CACHE[model_name] = model

        if status_cb:
            status_cb(f"Transcribing with '{model_name}' — CPU-only, please wait…")

        result = model.transcribe(
            video_path,
            language="en",
            fp16=False,
            verbose=None,
        )
    except Exception as e:
        return False, f"Whisper failed:\n\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}", ""

    text = (result.get("text") or "").strip() + "\n"
    txt_path = Path(output_dir) / (Path(video_path).stem + ".txt")
    try:
        txt_path.write_text(text, encoding="utf-8")
    except OSError as e:
        return False, f"Transcript generated but saving failed:\n{txt_path}\n\n{e}", ""

    return True, text, str(txt_path)


class App:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Transscript — Video → Text")
        self.root.geometry("820x680")
        self.root.minsize(640, 500)

        self.cfg = load_config()
        self.video_path: str | None = None

        self.output_dir_var = StringVar(value=self.cfg.get("output_dir", DEFAULT_OUTPUT_DIR))
        self.model_var = StringVar(value=self.cfg.get("model", DEFAULT_MODEL))
        self.status_var = StringVar(value="Drop a video or click Browse to start.")

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        # Drop zone
        drop_frame = ttk.Frame(self.root, relief="ridge", borderwidth=2)
        drop_frame.pack(fill="x", **pad)
        self.drop_label = ttk.Label(
            drop_frame,
            text=("Drag a video file here\nor click Browse below"
                  if DND_AVAILABLE else "Click Browse below to choose a video"),
            anchor="center", justify="center", padding=20,
        )
        self.drop_label.pack(fill="x")
        Tooltip(self.drop_label, DROP_TOOLTIP)
        if DND_AVAILABLE:
            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_drop)

        # File row
        file_row = ttk.Frame(self.root)
        file_row.pack(fill="x", **pad)
        browse_btn = ttk.Button(file_row, text="Browse…", command=self._browse_video)
        browse_btn.pack(side="left")
        Tooltip(browse_btn, "Open a file picker to choose a video/audio file.")
        self.file_label = ttk.Label(file_row, text="(no file selected)", foreground="#666")
        self.file_label.pack(side="left", padx=10)

        # Controls
        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", **pad)
        model_lbl = ttk.Label(ctrl, text="Model:")
        model_lbl.pack(side="left")
        Tooltip(model_lbl, MODEL_TOOLTIP)
        model_box = ttk.Combobox(
            ctrl, textvariable=self.model_var, values=MODELS, state="readonly", width=10
        )
        model_box.pack(side="left", padx=(4, 16))
        model_box.bind("<<ComboboxSelected>>", lambda _e: self._persist())
        Tooltip(model_box, MODEL_TOOLTIP)

        out_lbl = ttk.Label(ctrl, text="Output folder:")
        out_lbl.pack(side="left")
        Tooltip(out_lbl, OUTPUT_TOOLTIP)
        out_entry = ttk.Entry(ctrl, textvariable=self.output_dir_var, width=44)
        out_entry.pack(side="left", padx=4)
        Tooltip(out_entry, OUTPUT_TOOLTIP)
        change_btn = ttk.Button(ctrl, text="Change…", command=self._pick_output_dir)
        change_btn.pack(side="left")
        Tooltip(change_btn, "Pick a different folder for saved transcripts.")

        # Action row
        action = ttk.Frame(self.root)
        action.pack(fill="x", **pad)
        self.transcribe_btn = ttk.Button(
            action, text="Transcribe", command=self._start_transcribe, state="disabled"
        )
        self.transcribe_btn.pack(side="left")
        Tooltip(self.transcribe_btn, TRANSCRIBE_TOOLTIP)
        self.progress = ttk.Progressbar(action, mode="indeterminate", length=260)
        self.progress.pack(side="left", padx=12)
        ttk.Label(action, textvariable=self.status_var).pack(side="left")

        # Copy bar ABOVE the transcript box
        copy_bar = ttk.Frame(self.root)
        copy_bar.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(copy_bar, text="Transcript:", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.top_copy_btn = ttk.Button(
            copy_bar, text="📋 Copy entire transcript",
            command=self._copy, state="disabled",
        )
        self.top_copy_btn.pack(side="right")
        Tooltip(self.top_copy_btn, COPY_TOOLTIP)

        # Transcript text
        self.text = ScrolledText(self.root, wrap="word", font=("Segoe UI", 10))
        self.text.pack(fill="both", expand=True, padx=10, pady=(2, 6))

        # Footer row (Save As + saved indicator)
        out = ttk.Frame(self.root)
        out.pack(fill="x", **pad)
        self.saveas_btn = ttk.Button(out, text="Save As…", command=self._save_as, state="disabled")
        self.saveas_btn.pack(side="left")
        Tooltip(self.saveas_btn, SAVE_TOOLTIP)
        self.saved_label = ttk.Label(out, text="", foreground="#080")
        self.saved_label.pack(side="left", padx=12)

    # --- event handlers ---

    def _on_drop(self, event) -> None:
        self._set_video(strip_drop_path(event.data))

    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a video or audio file",
            initialdir=DEFAULT_BROWSE_DIR,
            filetypes=[
                ("Media files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mp3 *.wav *.m4a *.flac *.ogg"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._set_video(path)

    def _set_video(self, path: str) -> None:
        path = path.strip('"').strip("'")
        if not os.path.isfile(path):
            messagebox.showerror("Invalid file", f"Not a file:\n{path}")
            return
        ext = Path(path).suffix.lower()
        if ext and ext not in VIDEO_EXTS:
            if not messagebox.askyesno("Unusual file type",
                                       f"{ext} isn't a typical media extension. Try anyway?"):
                return
        self.video_path = path
        self.file_label.configure(text=Path(path).name, foreground="#000")
        self.transcribe_btn.configure(state="normal")
        self.status_var.set("Ready. Click Transcribe when you're set.")

    def _pick_output_dir(self) -> None:
        initial = self.output_dir_var.get() or DEFAULT_OUTPUT_DIR
        if not os.path.isdir(initial):
            initial = DEFAULT_BROWSE_DIR
        chosen = filedialog.askdirectory(title="Choose output folder", initialdir=initial)
        if chosen:
            self.output_dir_var.set(os.path.normpath(chosen))
            self._persist()

    def _persist(self) -> None:
        self.cfg["output_dir"] = self.output_dir_var.get()
        self.cfg["model"] = self.model_var.get()
        save_config(self.cfg)

    def _start_transcribe(self) -> None:
        if not self.video_path:
            return
        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            messagebox.showerror("Missing output folder", "Pick an output folder first.")
            return
        self._persist()

        self.transcribe_btn.configure(state="disabled")
        self.top_copy_btn.configure(state="disabled")
        self.saveas_btn.configure(state="disabled")
        self.saved_label.configure(text="")
        self.text.delete("1.0", "end")
        self.progress.start(12)

        video = self.video_path
        model = self.model_var.get()

        def status_cb(msg: str) -> None:
            self.root.after(0, self.status_var.set, msg)

        def worker() -> None:
            ok, payload, txt_path = transcribe(video, model, out_dir, status_cb)
            self.root.after(0, self._on_done, ok, payload, txt_path)

        status_cb(f"Starting '{model}'…")
        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, ok: bool, payload: str, txt_path: str) -> None:
        self.progress.stop()
        self.transcribe_btn.configure(state="normal")
        if not ok:
            self.status_var.set("Failed.")
            messagebox.showerror("Transcription failed", payload)
            return
        self.text.insert("1.0", payload)
        self.top_copy_btn.configure(state="normal")
        self.saveas_btn.configure(state="normal")
        self.status_var.set("Done.")
        self.saved_label.configure(text=f"Saved: {txt_path}")

    def _copy(self) -> None:
        text = self.text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Copied to clipboard.")

    def _save_as(self) -> None:
        text = self.text.get("1.0", "end-1c")
        if not text.strip():
            return
        default_name = Path(self.video_path).stem + ".txt" if self.video_path else "transcript.txt"
        path = filedialog.asksaveasfilename(
            title="Save transcript as…",
            defaultextension=".txt",
            initialfile=default_name,
            initialdir=self.output_dir_var.get() or DEFAULT_OUTPUT_DIR,
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.saved_label.configure(text=f"Saved: {path}")
        except OSError as e:
            messagebox.showerror("Save failed", str(e))


def main() -> None:
    root = TkinterDnD.Tk() if DND_AVAILABLE else Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
