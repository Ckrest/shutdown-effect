# Shutdown Effect

Customizable shutdown/reboot animations for Linux desktops.

## Features

- Multiple animation styles (fire, fade, sakura)
- Works with various power actions (shutdown, reboot, suspend, hibernate)
- Test mode for previewing animations
- Wayland compatible using layer-shell

## Usage

```bash
# Test animation
shutdown-effect.py test

# Test with specific animation
shutdown-effect.py test -a fade

# Real shutdown with animation
shutdown-effect.py shutdown -a sakura

# Reboot with animation
shutdown-effect.py reboot
```

## Available Animations

- `fire` - Fire effect (default)
- `fade` - Simple fade to black
- `sakura` - Cherry blossom petals

## Configuration

Set `SHUTDOWN_ANIMATIONS_DIR` environment variable to customize the animations directory.

## Requirements

- Python 3.8+
- GTK3 with GtkLayerShell
- systemd (for power actions)

## License

MIT
