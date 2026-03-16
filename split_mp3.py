import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import pygame
from pydub import AudioSegment
import time
import threading

ROOT_DATA = Path(__file__).parent / "root_data"
SPLITTED_DATA = Path(__file__).parent / "splitted_data"


class MP3Splitter:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 Splitter")
        self.root.geometry("700x500")

        pygame.mixer.init()

        self.audio = None
        self.audio_length_ms = 0
        self.current_file = None
        self.playing = False
        self.start_pos_ms = None
        self.end_pos_ms = None
        self.split_count = 0
        self.play_start_time = 0
        self.play_offset_ms = 0
        self.updater_running = False

        self._build_ui()
        self._load_file_list()

        self.root.bind("j", self._mark_start)
        self.root.bind("k", self._mark_end)
        self.root.bind("l", self._confirm_split)
        self.root.bind("<space>", self._toggle_play)

    def _build_ui(self):
        # File list
        frame_top = tk.Frame(self.root)
        frame_top.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(frame_top, text="MP3 Files in root_data:").pack(anchor=tk.W)
        self.file_listbox = tk.Listbox(frame_top, height=6)
        self.file_listbox.pack(fill=tk.X)
        self.file_listbox.bind("<<ListboxSelect>>", self._on_file_select)

        # Transport controls
        frame_ctrl = tk.Frame(self.root)
        frame_ctrl.pack(fill=tk.X, padx=10, pady=5)

        self.btn_play = tk.Button(frame_ctrl, text="Play / Pause (Space)", command=lambda: self._toggle_play(None))
        self.btn_play.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(frame_ctrl, text="Stop", command=self._stop)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        # Seek bar
        frame_seek = tk.Frame(self.root)
        frame_seek.pack(fill=tk.X, padx=10, pady=5)

        self.seek_var = tk.DoubleVar(value=0)
        self.seek_bar = ttk.Scale(frame_seek, from_=0, to=100, variable=self.seek_var, command=self._on_seek)
        self.seek_bar.pack(fill=tk.X)

        self.time_label = tk.Label(frame_seek, text="00:00 / 00:00")
        self.time_label.pack()

        # Markers
        frame_marks = tk.Frame(self.root)
        frame_marks.pack(fill=tk.X, padx=10, pady=5)

        self.start_label = tk.Label(frame_marks, text="Start [J]: --:--", fg="green", font=("monospace", 12))
        self.start_label.pack(side=tk.LEFT, padx=10)

        self.end_label = tk.Label(frame_marks, text="End [K]: --:--", fg="red", font=("monospace", 12))
        self.end_label.pack(side=tk.LEFT, padx=10)

        self.confirm_label = tk.Label(frame_marks, text="Confirm [L]", font=("monospace", 12))
        self.confirm_label.pack(side=tk.LEFT, padx=10)

        # Splits log
        frame_log = tk.Frame(self.root)
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(frame_log, text="Split log:").pack(anchor=tk.W)
        self.log_text = tk.Text(frame_log, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Instructions
        tk.Label(self.root, text="J = mark start | K = mark end | L = confirm split | Space = play/pause",
                 font=("monospace", 10), fg="gray").pack(pady=5)

    def _load_file_list(self):
        self.file_listbox.delete(0, tk.END)
        if not ROOT_DATA.exists():
            ROOT_DATA.mkdir(parents=True, exist_ok=True)
        for f in sorted(ROOT_DATA.glob("*.mp3")):
            self.file_listbox.insert(tk.END, f.name)

    def _on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        filename = self.file_listbox.get(sel[0])
        filepath = ROOT_DATA / filename
        self._load_file(filepath)

    def _load_file(self, filepath):
        self._stop()
        self.current_file = filepath
        self.audio = AudioSegment.from_mp3(str(filepath))
        self.audio_length_ms = len(self.audio)
        self.start_pos_ms = None
        self.end_pos_ms = None
        self.start_label.config(text="Start [J]: --:--")
        self.end_label.config(text="End [K]: --:--")

        # Count existing splits
        stem = filepath.stem
        out_dir = SPLITTED_DATA / stem
        if out_dir.exists():
            existing = list(out_dir.glob("*.mp3"))
            self.split_count = len(existing)
        else:
            self.split_count = 0

        self.seek_bar.config(to=self.audio_length_ms)
        self.seek_var.set(0)
        self._update_time_label(0)
        self._log(f"Loaded: {filepath.name} ({self._fmt(self.audio_length_ms)})")

        pygame.mixer.music.load(str(filepath))

    def _toggle_play(self, event):
        if self.audio is None:
            return
        if self.playing:
            pygame.mixer.music.pause()
            self.play_offset_ms = self._current_pos_ms()
            self.playing = False
        else:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.unpause()
            else:
                start_sec = self.play_offset_ms / 1000.0
                pygame.mixer.music.play(start=start_sec)
            self.play_start_time = time.time()
            self.playing = True
            if not self.updater_running:
                self.updater_running = True
                self._update_position()

    def _stop(self):
        pygame.mixer.music.stop()
        self.playing = False
        self.play_offset_ms = 0
        self.seek_var.set(0)
        if self.audio:
            self._update_time_label(0)

    def _on_seek(self, val):
        if self.audio is None:
            return
        ms = float(val)
        self.play_offset_ms = ms
        self._update_time_label(ms)
        if self.playing:
            pygame.mixer.music.stop()
            pygame.mixer.music.play(start=ms / 1000.0)
            self.play_start_time = time.time()

    def _current_pos_ms(self):
        if self.playing:
            elapsed = (time.time() - self.play_start_time) * 1000
            pos = self.play_offset_ms + elapsed
            return min(pos, self.audio_length_ms)
        return self.play_offset_ms

    def _update_position(self):
        if not self.playing:
            self.updater_running = False
            return
        pos = self._current_pos_ms()
        if pos >= self.audio_length_ms:
            self.playing = False
            self.play_offset_ms = 0
            pos = 0
        self.seek_var.set(pos)
        self._update_time_label(pos)
        self.root.after(100, self._update_position)

    def _update_time_label(self, ms):
        total = self._fmt(self.audio_length_ms)
        cur = self._fmt(ms)
        self.time_label.config(text=f"{cur} / {total}")

    def _mark_start(self, event):
        if self.audio is None:
            return
        self.start_pos_ms = self._current_pos_ms()
        self.start_label.config(text=f"Start [J]: {self._fmt(self.start_pos_ms)}")
        self._log(f"Start marked at {self._fmt(self.start_pos_ms)}")

    def _mark_end(self, event):
        if self.audio is None:
            return
        self.end_pos_ms = self._current_pos_ms()
        self.end_label.config(text=f"End [K]: {self._fmt(self.end_pos_ms)}")
        self._log(f"End marked at {self._fmt(self.end_pos_ms)}")

    def _confirm_split(self, event):
        if self.audio is None:
            messagebox.showwarning("No file", "Load an MP3 file first.")
            return
        if self.start_pos_ms is None or self.end_pos_ms is None:
            messagebox.showwarning("Markers", "Set both start (J) and end (K) markers first.")
            return
        if self.start_pos_ms >= self.end_pos_ms:
            messagebox.showwarning("Invalid range", "Start must be before end.")
            return

        stem = self.current_file.stem
        out_dir = SPLITTED_DATA / stem
        out_dir.mkdir(parents=True, exist_ok=True)

        self.split_count += 1
        out_path = out_dir / f"{self.split_count}.mp3"

        segment = self.audio[int(self.start_pos_ms):int(self.end_pos_ms)]
        segment.export(str(out_path), format="mp3")

        duration = self._fmt(self.end_pos_ms - self.start_pos_ms)
        self._log(f"Saved: {out_path.relative_to(Path(__file__).parent)} ({duration})")

        # Reset markers
        self.start_pos_ms = None
        self.end_pos_ms = None
        self.start_label.config(text="Start [J]: --:--")
        self.end_label.config(text="End [K]: --:--")

    def _log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    @staticmethod
    def _fmt(ms):
        s = int(ms / 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


if __name__ == "__main__":
    root = tk.Tk()
    app = MP3Splitter(root)
    root.mainloop()
