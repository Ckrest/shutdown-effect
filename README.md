# Shutdown Effect

Visual shutdown animations with a hook system for Wayland compositors.

Provides a framework for smooth visual transitions during power actions. Ships with a bundled `fade` animation; users can add their own custom animations.

## Features

- **Hook System**: Add custom animations via `~/.config/shutdown-effect/animations/`
- **Bundled Default**: `fade` animation works out of the box (GTK layer-shell)
- **Protocol-Based**: Simple stdout signaling (READY/BLACK)
- **Discovery**: Merges bundled and user animations automatically

## Installation

```bash
git clone https://github.com/Ckrest/shutdown-effect.git
cd shutdown-effect
```

### Dependencies

- Python 3.10+
- GTK 3.0 with GtkLayerShell (`python3-gi`, `gir1.2-gtklayershell-0.1`)
- `grim` (for screenshot capture in fade animation)

Video-based animations may also require:
- `mpvpaper` (for video playback)
- Wayfire with screen-freeze plugin (optional, prevents black flash)

## Usage

### Test Bundled Animation

```bash
# Run fade animation (Ctrl+C to exit)
python3 animations/fade/animate.py

# Test discovery
python3 discovery.py
```

### Add Custom Animations

Create your animations in `~/.config/shutdown-effect/animations/`:

```bash
mkdir -p ~/.config/shutdown-effect/animations/my-animation
# Create animate.py following the protocol below
```

### Animation Protocol

Each animation must be a directory containing `animate.py` that:

1. Prints **READY** to stdout when overlay is visible
2. Prints **BLACK** to stdout when screen is fully black
3. Holds the black screen until killed

```python
#!/usr/bin/env python3
# ~/.config/shutdown-effect/animations/my-animation/animate.py

# ... set up your overlay/effect ...

print("READY", flush=True)  # Signal: safe to proceed

# ... play animation ...

print("BLACK", flush=True)  # Signal: animation complete

# Hold forever until killed
while True:
    time.sleep(1)
```

### Animation Discovery

Animations are discovered from multiple sources (merged):

1. `SHUTDOWN_EFFECTS_DIR` environment variable (if set, exclusive)
2. `~/.config/shutdown-effect/animations/` (user animations)
3. `./animations/` (bundled defaults)

User animations override bundled animations with the same name.

```bash
# Check what animations are available
python3 discovery.py

# Override with environment variable
SHUTDOWN_EFFECTS_DIR=/path/to/animations python3 discovery.py
```

### Integration

Designed to be called by an orchestrator like [power-manager](https://github.com/Ckrest/power-manager):

```python
import subprocess

proc = subprocess.Popen(
    ["python3", "path/to/animate.py"],
    stdout=subprocess.PIPE, text=True
)

# Wait for READY
for line in proc.stdout:
    if line.strip() == "READY":
        break

# ... close windows ...

# Wait for BLACK
for line in proc.stdout:
    if line.strip() == "BLACK":
        break

# Execute power action
subprocess.run(["systemctl", "poweroff"])
```

## Bundled Animations

### fade/

Simple fade to black using GTK layer-shell.
- Captures screenshot with `grim`
- Fades to black over 1 second
- No additional assets required

## Creating Video Animations

For video-based effects (fire, particles, etc.), use `mpvpaper`:

```python
#!/usr/bin/env python3
# Example video animation structure

import subprocess
import os

VIDEO = os.path.join(os.path.dirname(__file__), "effect.webm")

# Start video with mpvpaper
proc = subprocess.Popen([
    "mpvpaper", "-o", "loop", "*", VIDEO
])

print("READY", flush=True)

# Wait for video duration or detect completion
import time
time.sleep(5)  # Adjust to your video length

print("BLACK", flush=True)

# Hold until killed
while True:
    time.sleep(1)
```

## License

MIT License - see [LICENSE](LICENSE)
