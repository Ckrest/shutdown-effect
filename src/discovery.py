"""
Animation discovery for shutdown-effect.

Finds available animations by merging from multiple sources (highest priority first):
1. SHUTDOWN_EFFECTS_DIR environment variable (explicit override - exclusive)
2. XDG user config dir / animations/ (via platformdirs)
3. Package-local ./animations/ (bundled defaults)

If SHUTDOWN_EFFECTS_DIR is set, only that directory is used.
Otherwise, user config and bundled defaults are merged (user overrides bundled).

Each animation is a directory containing an animate.py script that follows
the shutdown-effect protocol (prints READY then BLACK to stdout).
"""

import os
from pathlib import Path

from platformdirs import user_config_dir

# XDG config location
XDG_ANIMATIONS_DIR = Path(user_config_dir("shutdown-effect")) / "animations"

# Package-local animations (bundled defaults)
LOCAL_ANIMATIONS_DIR = Path(__file__).parent / "animations"


def _get_animations_from_dir(directory: Path) -> dict[str, Path]:
    """Scan a directory for valid animations."""
    result = {}
    if directory and directory.is_dir():
        for entry in directory.iterdir():
            if entry.is_dir() and (entry / "animate.py").exists():
                result[entry.name] = entry
    return result


def get_all_animations() -> dict[str, Path]:
    """
    Get all available animations merged from all sources.

    Priority (highest first):
    1. SHUTDOWN_EFFECTS_DIR (if set, exclusive)
    2. XDG user config dir / animations/ (via platformdirs)
    3. Package-local bundled defaults (./animations/)

    User animations override bundled animations with the same name.

    Returns:
        Dict mapping animation name to its full path.
    """
    # If environment variable is set, use exclusively
    env_dir = os.environ.get('SHUTDOWN_EFFECTS_DIR')
    if env_dir:
        return _get_animations_from_dir(Path(env_dir))

    # Otherwise merge: bundled first, then user (user overrides)
    result = {}
    result.update(_get_animations_from_dir(LOCAL_ANIMATIONS_DIR))
    result.update(_get_animations_from_dir(XDG_ANIMATIONS_DIR))
    return result


def list_animations() -> list[str]:
    """
    List available animation names.

    Returns:
        Sorted list of animation names.
    """
    return sorted(get_all_animations().keys())


def get_animation_script(name: str) -> Path | None:
    """
    Get the path to an animation's script.

    Args:
        name: Animation name (directory name)

    Returns:
        Path to animate.py, or None if not found.
    """
    animations = get_all_animations()
    if name in animations:
        return animations[name] / "animate.py"
    return None


# Legacy compatibility
def get_animations_dir() -> Path | None:
    """
    Get the primary animations directory.

    Note: This returns only one directory. For full discovery,
    use get_all_animations() instead.
    """
    env_dir = os.environ.get('SHUTDOWN_EFFECTS_DIR')
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    if XDG_ANIMATIONS_DIR.is_dir():
        return XDG_ANIMATIONS_DIR
    if LOCAL_ANIMATIONS_DIR.is_dir():
        return LOCAL_ANIMATIONS_DIR
    return None


if __name__ == "__main__":
    # CLI for testing discovery
    print("Animation sources:")
    print(f"  ENV (SHUTDOWN_EFFECTS_DIR): {os.environ.get('SHUTDOWN_EFFECTS_DIR', '(not set)')}")
    print(f"  XDG: {XDG_ANIMATIONS_DIR} {'(exists)' if XDG_ANIMATIONS_DIR.is_dir() else '(not found)'}")
    print(f"  Local: {LOCAL_ANIMATIONS_DIR} {'(exists)' if LOCAL_ANIMATIONS_DIR.is_dir() else '(not found)'}")
    print()
    print(f"Available animations: {list_animations()}")
    print()
    for name, path in sorted(get_all_animations().items()):
        print(f"  {name}: {path}")
