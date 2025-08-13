
import threading
import time
import random
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, messagebox

# External dependency:
#   pip install pynput
try:
    from pynput.keyboard import Controller, Key
except Exception as e:
    Controller = None
    Key = None

# ---------------------------
# Typing utilities & models
# ---------------------------

QWERTY_NEIGHBORS = {
    'a': list("qwsz"),
    'b': list("vghn"),
    'c': list("xdfv"),
    'd': list("erfcxs"),
    'e': list("wsdfr"),
    'f': list("rtgdvc"),
    'g': list("tyfhvb"),
    'h': list("yugjnb"),
    'i': list("ujko"),
    'j': list("uikhm"),
    'k': list("ijolm,"),
    'l': list("kop;."),
    'm': list("nj,"),
    'n': list("bhjm"),
    'o': list("iklp"),
    'p': list("ol;["),
    'q': list("was"),
    'r': list("edfgt"),
    's': list("aqwzedx"),
    't': list("rfgy"),
    'u': list("yhji"),
    'v': list("cfgb"),
    'w': list("qase"),
    'x': list("zsdc"),
    'y': list("tugh"),
    'z': list("asx"),
    '1': list("2q"),
    '2': list("13w"),
    '3': list("24e"),
    '4': list("35r"),
    '5': list("46t"),
    '6': list("57y"),
    '7': list("68u"),
    '8': list("79i"),
    '9': list("80o"),
    '0': list("9p"),
    ',': list("kml."),
    '.': list(",;l/"),
    ';': list("l,p."),
    "'": list(";"),
    '-': list("0="),
    '=': list("-"),
    '/': list(".;"),
}

PUNCTUATION_SET = set(",.!?;:")

def keep_case(src_char: str, neighbor: str) -> str:
    if src_char.isupper():
        return neighbor.upper()
    return neighbor

def adjacent_key(char: str) -> str:
    base = char.lower()
    if base in QWERTY_NEIGHBORS and QWERTY_NEIGHBORS[base]:
        return keep_case(char, random.choice(QWERTY_NEIGHBORS[base]))
    # Fallback random letter
    pool = "abcdefghijklmnopqrstuvwxyz"
    return random.choice(pool).upper() if char.isupper() else random.choice(pool)

def secs_per_char_for_wpm(wpm: float) -> float:
    # 5 chars per word heuristic
    # delay per char = 60 / (wpm*5) = 12 / wpm
    return 12.0 / max(wpm, 1.0)

class Settings:
    def __init__(self,
                 min_wpm=45,
                 max_wpm=70,
                 letter_typo_rate=0.03,
                 punct_typo_rate=0.02,
                 enable_corrections=True,
                 micro_pauses=True,
                 think_pause_chance=0.08,
                 jitter_std=0.25,
                 correction_latency=(0.15, 0.55)):
        self.min_wpm = min_wpm
        self.max_wpm = max_wpm
        self.letter_typo_rate = letter_typo_rate
        self.punct_typo_rate = punct_typo_rate
        self.enable_corrections = enable_corrections
        self.micro_pauses = micro_pauses
        self.think_pause_chance = think_pause_chance
        self.jitter_std = jitter_std  # stddev (fraction of base delay)
        self.correction_latency = correction_latency

    def sample_wpm(self) -> float:
        return random.uniform(self.min_wpm, self.max_wpm)

class HumanTyper:
    def __init__(self, settings: Settings, ui_callback=None):
        self.settings = settings
        self.keyboard = Controller() if Controller else None
        self.stop_event = threading.Event()
        self.ui_callback = ui_callback  # function(str) to post status

    # ------------- Low-level key actions -------------
    def _type_char(self, c: str):
        if self.keyboard is None:
            return
        if c == "\n":
            self.keyboard.press(Key.enter)
            self.keyboard.release(Key.enter)
        else:
            # Controller.type handles shift for symbols
            self.keyboard.type(c)

    def _backspace(self, n=1, delay=0.045):
        if self.keyboard is None:
            return
        for _ in range(n):
            self.keyboard.press(Key.backspace)
            self.keyboard.release(Key.backspace)
            time.sleep(delay)

    # ------------- Delays -------------
    def _char_delay(self, base_wpm: float) -> float:
        base = secs_per_char_for_wpm(base_wpm)
        # Gaussian jitter; clamp to sane range
        jittered = random.gauss(base, base * self.settings.jitter_std)
        return max(0.001, min(jittered, base * 3))

    def _pause_after_word(self, word: str):
        if not self.settings.micro_pauses:
            return
        # Longer words: tiny pause
        if len(word) >= 8:
            time.sleep(random.uniform(0.08, 0.22))
        # Occasional "think" pause
        if random.random() < self.settings.think_pause_chance:
            time.sleep(random.uniform(0.25, 0.9))

    def _pause_after_punct(self, ch: str):
        if not self.settings.micro_pauses:
            return
        if ch in ".!?":
            time.sleep(random.uniform(0.25, 0.65))
        elif ch in ",;:":
            time.sleep(random.uniform(0.08, 0.25))

    # ------------- Typo strategies -------------
    def _maybe_letter_typo(self, word: str, base_wpm: float):
        """Return (did_typo: bool, typed_prefix: str, backspaces: int)."""
        if not self.settings.enable_corrections:
            return False, "", 0
        if len(word) < 3 or random.random() >= self.settings.letter_typo_rate:
            return False, "", 0

        # Choose a typo type
        typo_type = random.choices(
            ["substitution", "transposition", "duplicate", "omission"],
            weights=[0.45, 0.25, 0.2, 0.1]
        )[0]

        if typo_type == "substitution":
            i = random.randint(0, len(word) - 1)
            wrong = adjacent_key(word[i])
            typed = word[:i] + wrong
            self._type_slow(typed, base_wpm)
            # realize mistake
            time.sleep(random.uniform(*self.settings.correction_latency))
            self._backspace(1)
            return True, typed, 1

        if typo_type == "transposition" and len(word) >= 4:
            i = random.randint(0, len(word) - 2)
            if word[i].isspace() or word[i+1].isspace():
                return False, "", 0
            typed = word[:i] + word[i+1] + word[i]
            self._type_slow(typed, base_wpm)
            time.sleep(random.uniform(*self.settings.correction_latency))
            self._backspace(2)
            return True, typed, 2

        if typo_type == "duplicate":
            i = random.randint(0, len(word) - 1)
            typed = word[:i+1] + word[i]
            self._type_slow(typed, base_wpm)
            time.sleep(random.uniform(*self.settings.correction_latency))
            self._backspace(1)
            return True, typed, 1

        if typo_type == "omission":
            # Skip a letter, then backspace and retype correct so far
            i = random.randint(1, len(word) - 2)
            typed = word[:i]  # missing char at i
            self._type_slow(typed, base_wpm)
            time.sleep(random.uniform(*self.settings.correction_latency))
            # backspace typed so far, then retype correctly up to i
            self._backspace(len(typed))
            self._type_slow(word[:i], base_wpm)
            return True, word[:i], len(typed)

        return False, "", 0

    def _maybe_punct_typo(self, punct: str, base_wpm: float) -> bool:
        if not self.settings.enable_corrections:
            return False
        if punct not in PUNCTUATION_SET or random.random() >= self.settings.punct_typo_rate:
            return False
        # Choose a nearby/wrong punctuation
        candidates = list(PUNCTUATION_SET - {punct})
        wrong = random.choice(candidates)
        self._type_slow(wrong, base_wpm)
        time.sleep(random.uniform(*self.settings.correction_latency))
        self._backspace(1)
        return True

    # ------------- Core typing -------------
    def _type_slow(self, text: str, base_wpm: float):
        for ch in text:
            if self.stop_event.is_set():
                return
            self._type_char(ch)
            time.sleep(self._char_delay(base_wpm))

    def type_text(self, text: str):
        if self.keyboard is None:
            raise RuntimeError("pynput is not available. Please install it with 'pip install pynput'.")

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Split into tokens keeping punctuation
        tokens = []
        current = []
        for ch in text:
            if ch.isalnum() or ch in ("'", "_"):
                current.append(ch)
            else:
                if current:
                    tokens.append("".join(current))
                    current = []
                tokens.append(ch)
        if current:
            tokens.append("".join(current))

        i = 0
        while i < len(tokens) and not self.stop_event.is_set():
            token = tokens[i]

            # Choose a WPM for this token/word
            base_wpm = self.settings.sample_wpm()

            if token.strip() == "":
                # spaces/newlines as-is
                self._type_slow(token, base_wpm)
                i += 1
                continue

            if token.isalnum() or ("'" in token and token.replace("'", "").isalnum()):
                # A "word"
                did_typo, typed_prefix, backspaces = self._maybe_letter_typo(token, base_wpm)
                if self.stop_event.is_set():
                    break
                # type the rest correctly
                remaining = token[len(typed_prefix):] if did_typo else token
                self._type_slow(remaining, base_wpm)
                self._pause_after_word(token)
            elif token in PUNCTUATION_SET:
                # Maybe wrong punctuation then fix
                did_punct_typo = self._maybe_punct_typo(token, base_wpm)
                if self.stop_event.is_set():
                    break
                self._type_slow(token, base_wpm)
                self._pause_after_punct(token)
            else:
                # Other symbols/spaces/newlines
                self._type_slow(token, base_wpm)

            i += 1

    # Public controls
    def start(self, text: str, countdown=3):
        self.stop_event.clear()
        def run():
            if self.ui_callback:
                self.ui_callback("Click into your target text field now...")
            for sec in range(countdown, 0, -1):
                if self.ui_callback:
                    self.ui_callback(f"Typing starts in {sec}...")
                print("\a", end="")  # system beep (may be ignored)
                time.sleep(1.0)
            if self.ui_callback:
                self.ui_callback("Typing...")
            self.type_text(text)
            if self.ui_callback:
                self.ui_callback("Done or stopped.")
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def stop(self):
        self.stop_event.set()


# ---------------------------
# GUI
# ---------------------------

PERSONALITIES = {
    "Balanced": dict(min_wpm=45, max_wpm=70, letter_typo_rate=0.03, punct_typo_rate=0.02,
                     think_pause_chance=0.08, jitter_std=0.25),
    "Fast but Messy": dict(min_wpm=70, max_wpm=110, letter_typo_rate=0.06, punct_typo_rate=0.04,
                           think_pause_chance=0.05, jitter_std=0.28),
    "Slow and Careful": dict(min_wpm=30, max_wpm=45, letter_typo_rate=0.015, punct_typo_rate=0.01,
                             think_pause_chance=0.12, jitter_std=0.18),
}

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Human Typist")
        self.geometry("860x640")
        self.resizable(True, True)

        self.settings = Settings()
        self.typer = None

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # Top: instructions
        self.info = tk.StringVar(value="Paste your text below. Set options. Click Start, then click into your target field.")
        info_lbl = ttk.Label(root, textvariable=self.info, foreground="#333")
        info_lbl.pack(anchor="w", pady=(0,6))

        # Text input
        txt_frame = ttk.LabelFrame(root, text="Input Text")
        txt_frame.pack(fill="both", expand=True)
        self.textbox = scrolledtext.ScrolledText(txt_frame, wrap=tk.WORD, height=16)
        self.textbox.pack(fill="both", expand=True, padx=6, pady=6)

        # Options
        opt = ttk.LabelFrame(root, text="Typing Settings")
        opt.pack(fill="x", pady=8)

        # Personality
        ttk.Label(opt, text="Preset:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.preset = ttk.Combobox(opt, values=list(PERSONALITIES.keys()), state="readonly")
        self.preset.set("Balanced")
        self.preset.grid(row=0, column=1, sticky="w", padx=6, pady=4)
        self.preset.bind("<<ComboboxSelected>>", self.apply_preset)

        # WPM range
        ttk.Label(opt, text="Min WPM:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.min_wpm_var = tk.StringVar(value=str(self.settings.min_wpm))
        ttk.Entry(opt, textvariable=self.min_wpm_var, width=8).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(opt, text="Max WPM:").grid(row=1, column=2, sticky="w", padx=6, pady=4)
        self.max_wpm_var = tk.StringVar(value=str(self.settings.max_wpm))
        ttk.Entry(opt, textvariable=self.max_wpm_var, width=8).grid(row=1, column=3, sticky="w", padx=6, pady=4)

        # Typos
        ttk.Label(opt, text="Letter typo %:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.letter_typo_var = tk.StringVar(value=str(int(self.settings.letter_typo_rate*100)))
        ttk.Entry(opt, textvariable=self.letter_typo_var, width=8).grid(row=2, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(opt, text="Punct typo %:").grid(row=2, column=2, sticky="w", padx=6, pady=4)
        self.punct_typo_var = tk.StringVar(value=str(int(self.settings.punct_typo_rate*100)))
        ttk.Entry(opt, textvariable=self.punct_typo_var, width=8).grid(row=2, column=3, sticky="w", padx=6, pady=4)

        # Corrections & pauses
        self.corr_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Simulate corrections", variable=self.corr_var).grid(row=3, column=0, sticky="w", padx=6, pady=4)

        self.pause_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Smart micro-pauses", variable=self.pause_var).grid(row=3, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(opt, text="Think pause chance %:").grid(row=3, column=2, sticky="w", padx=6, pady=4)
        self.think_var = tk.StringVar(value=str(int(self.settings.think_pause_chance*100)))
        ttk.Entry(opt, textvariable=self.think_var, width=8).grid(row=3, column=3, sticky="w", padx=6, pady=4)

        ttk.Label(opt, text="Jitter (std as % of base):").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        self.jitter_var = tk.StringVar(value=str(int(self.settings.jitter_std*100)))
        ttk.Entry(opt, textvariable=self.jitter_var, width=8).grid(row=4, column=1, sticky="w", padx=6, pady=4)

        # Buttons
        btns = ttk.Frame(root)
        btns.pack(fill="x", pady=8)
        self.start_btn = ttk.Button(btns, text="Start Typing (3s)", command=self.on_start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Preview Plan", command=self.on_preview).pack(side="left", padx=6)

        # Status
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(root, textvariable=self.status).pack(anchor="w")

        # Footer
        tip = ("Tip: After clicking Start, immediately click into your target window (Google Docs, Word, etc.). "
               "Grant Accessibility permissions on macOS (System Settings → Privacy & Security → Accessibility).")
        ttk.Label(root, text=tip, wraplength=780, foreground="#555").pack(anchor="w", pady=(8,0))

    def apply_preset(self, *_):
        name = self.preset.get()
        conf = PERSONALITIES.get(name, {})
        # Update UI values
        self.min_wpm_var.set(str(conf.get('min_wpm', self.settings.min_wpm)))
        self.max_wpm_var.set(str(conf.get('max_wpm', self.settings.max_wpm)))
        self.letter_typo_var.set(str(int(conf.get('letter_typo_rate', self.settings.letter_typo_rate)*100)))
        self.punct_typo_var.set(str(int(conf.get('punct_typo_rate', self.settings.punct_typo_rate)*100)))
        self.think_var.set(str(int(conf.get('think_pause_chance', self.settings.think_pause_chance)*100)))
        self.jitter_var.set(str(int(conf.get('jitter_std', self.settings.jitter_std)*100)))

    def _read_settings(self) -> Settings:
        try:
            min_wpm = float(self.min_wpm_var.get())
            max_wpm = float(self.max_wpm_var.get())
            ltr = float(self.letter_typo_var.get()) / 100.0
            ptr = float(self.punct_typo_var.get()) / 100.0
            think = float(self.think_var.get()) / 100.0
            jit = float(self.jitter_var.get()) / 100.0
        except ValueError:
            messagebox.showerror("Invalid settings", "Please enter numeric values for WPM and percentages.")
            raise

        if min_wpm <= 0 or max_wpm < min_wpm:
            messagebox.showerror("Invalid WPM", "Ensure Min WPM > 0 and Max WPM ≥ Min WPM.")
            raise ValueError("Bad WPM range")

        s = Settings(
            min_wpm=min_wpm,
            max_wpm=max_wpm,
            letter_typo_rate=ltr,
            punct_typo_rate=ptr,
            enable_corrections=self.corr_var.get(),
            micro_pauses=self.pause_var.get(),
            think_pause_chance=think,
            jitter_std=jit
        )
        return s

    def post_status(self, msg: str):
        self.status.set(msg)
        self.update_idletasks()

    def on_preview(self):
        # Light-weight preview: show a few sampled delays/typos likelihoods
        try:
            s = self._read_settings()
        except Exception:
            return

        sample_wpm = [round(random.uniform(s.min_wpm, s.max_wpm), 1) for _ in range(5)]
        delays = [round(secs_per_char_for_wpm(w), 3) for w in sample_wpm]
        preview = (f"Sample WPMs: {sample_wpm}\n"
                   f"Base char delays (s): {delays}\n"
                   f"Letter typo rate: {int(s.letter_typo_rate*100)}%\n"
                   f"Punctuation typo rate: {int(s.punct_typo_rate*100)}%\n"
                   f"Think pause chance: {int(s.think_pause_chance*100)}%\n"
                   f"Corrections: {'on' if s.enable_corrections else 'off'} • Micro-pauses: {'on' if s.micro_pauses else 'off'}")
        messagebox.showinfo("Preview", preview)

    def on_start(self):
        text = self.textbox.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("Empty text", "Please paste some text to type.")
            return

        # Ensure dependency
        if Controller is None:
            messagebox.showerror("Missing dependency",
                                 "The 'pynput' package is required.\n\nInstall with:\n    pip install pynput")
            return

        try:
            self.settings = self._read_settings()
        except Exception:
            return

        self.typer = HumanTyper(self.settings, ui_callback=self.post_status)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.post_status("Prepare target window. Typing starts after countdown...")
        self.typer.start(text, countdown=3)

        # Re-enable Start when thread finishes (polling)
        def poll():
            if self.typer and self.typer.stop_event.is_set():
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
            else:
                self.after(300, poll)
        self.after(300, poll)

    def on_stop(self):
        if self.typer:
            self.typer.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.post_status("Stopped by user.")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
