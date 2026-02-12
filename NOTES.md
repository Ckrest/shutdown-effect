# Notes - shutdown-effect

Visual shutdown animations with hook system for power transitions.

## Structure

```
shutdown-effect/
├── animations/
│   └── fade/           # Bundled default animation
├── discovery.py        # Animation discovery module
├── graceful-power      # Simple fallback (no animation)
└── manifest.yaml
```

## Build / Run

```bash
# Test discovery
python3 discovery.py

# Test bundled animation (Ctrl+C to exit)
python3 animations/fade/animate.py
```

## Animation Discovery

Animations are discovered from multiple sources (merged):

| Priority | Location | Purpose |
|----------|----------|---------|
| 1 | `SHUTDOWN_EFFECTS_DIR` env var | Explicit override (exclusive) |
| 2 | `~/.config/shutdown-effect/animations/` | User animations |
| 3 | `./animations/` | Bundled defaults |

User animations override bundled animations with the same name.

## Animation Protocol

Each animation (`<name>/animate.py`) must:

1. Print `READY` to stdout when overlay is visible
2. Print `BLACK` to stdout when animation is complete
3. Hold black screen forever until killed

## Path Dependencies

| Path | Purpose |
|------|---------|
| `~/.config/shutdown-effect/animations/` | User-provided animations |
| `./animations/` | Bundled default animations |

## Dependencies

**Python packages:** None (uses standard library + GTK)

**System packages:**
- `python3-gi` - GTK bindings
- `gir1.2-gtklayershell-0.1` - Layer shell for Wayland
- `grim` - Screenshot capture

**Optional (for video animations):**
- `mpvpaper` - Video wallpaper player
- Wayfire `screen-freeze` plugin - Prevents black flash
