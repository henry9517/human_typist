
# Human Typist

Local keyboard emulation that types your text into any focused app (Google Docs, Word, email, etc.) with human-like behavior:
- Variable WPM (min/max) + per-character jitter
- Realistic typos (substitution, transposition, duplicate, omission) and **live corrections** using Backspace
- Occasional punctuation mistakes (auto-corrected)
- Micro-pauses after long words and punctuation + occasional "think" pauses
- GUI with presets: **Balanced**, **Fast but Messy**, **Slow and Careful**

## Quick Start

### 1) Requirements
- Python 3.9+
- Windows or macOS (on macOS grant Accessibility permissions)

### 2) Install
```bash
# (optional) virtual environment — Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# python3 -m venv .venv
# source .venv/bin/activate

# install dependency
pip install -r requirements.txt
```

### 3) macOS Accessibility
System Settings → Privacy & Security → Accessibility → add your Terminal/IDE and enable it.

### 4) Run
```bash
python human_typist.py   # Windows
# or
# python3 human_typist.py  # macOS/Linux
```
