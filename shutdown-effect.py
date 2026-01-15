#!/usr/bin/env python3
"""
Shutdown effect with customizable animations.

Usage:
  shutdown-effect.py <action> [options]

Actions:
  shutdown, reboot, logout, suspend, hibernate, windows, test

Options:
  --animation, -a NAME   Animation to use: fire, fade, sakura (default: fire)
  --hold TIME            Hold black screen for TIME seconds in test mode (default: 3)

Examples:
  shutdown-effect.py test                    # Test with default animation
  shutdown-effect.py test -a fade            # Test fade animation
  shutdown-effect.py shutdown -a sakura      # Real shutdown with sakura

Orchestration flow:
1. Start animation subprocess (it captures screenshot + shows overlay)
2. Wait for "READY" signal (overlay is visible, screen captured)
3. Wait for "BLACK" signal (animation complete)
4. Execute power action (systemd handles process termination)
5. Animation holds black screen until system kills it

Animation protocol (via stdout):
- "READY" = screenshot captured, overlay visible, safe to close windows
- "BLACK" = animation complete, screen is fully black
- Animation must NOT exit - it holds the black screen until killed
"""

import subprocess
import os
import sys
import time
import threading
import signal
import argparse

# ============================================================================
# CONFIGURATION
# ============================================================================
DEFAULT_ANIMATION = "fire"  # Available: "fade", "sakura", "fire"
ANIMATIONS_DIR = os.environ.get(
    "SHUTDOWN_ANIMATIONS_DIR",
    os.path.join(os.path.dirname(__file__), "animations")
)
DEBUG_LOG = "/tmp/shutdown-debug.log"


def get_animation_script(animation_name):
    """Get the path to the animation script for the specified animation"""
    return os.path.join(ANIMATIONS_DIR, animation_name, "animate.py")


def install_signal_handlers():
    """Ignore SIGTERM/SIGINT to stay alive during shutdown"""
    def signal_handler(signum, frame):
        pass
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


# Power commands (None = test mode)
POWER_COMMANDS = {
    "shutdown": ["sudo", "-A", "shutdown", "-h", "now"],
    "reboot": ["sudo", "-A", "reboot"],
    "logout": ["loginctl", "terminate-session", ""],
    "suspend": ["systemctl", "suspend"],
    "hibernate": ["systemctl", "hibernate"],
    "windows": ["sudo", "-A", "reboot"],
    "test": None,
}


def get_session_id():
    """Get current login session ID"""
    try:
        result = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if parts:
                return parts[0]
    except Exception:
        pass
    return ""


def debug_log(msg):
    """Write debug message to file with timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
        f.flush()


def init_debug_log():
    """Initialize debug log file (call once at startup)"""
    with open(DEBUG_LOG, "w") as f:
        f.write(f"=== Shutdown Debug Log - {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.flush()


def close_windows_gracefully(done_event, debug=False):
    """Close all application windows via Wayfire IPC.

    Returns True on success, False on error (always sets done_event).
    """
    success = True

    try:
        from wayfire import WayfireSocket
    except ImportError as e:
        debug_log(f"ERROR: Cannot import wayfire module: {e}")
        print(f"ERROR: wayfire module not available: {e}", file=sys.stderr)
        done_event.set()
        return False

    try:
        sock = WayfireSocket()
        views = sock.list_views()

        if debug:
            debug_log(f"Found {len(views)} views total")
            for i, v in enumerate(views):
                debug_log(f"  VIEW {i}: {v}")

        closed_count = 0
        for view in views:
            try:
                app_id = view.get("app-id", "")
                title = view.get("title", "")
                view_type = view.get("type", "")

                # Skip layer-shell surfaces
                if view_type in ("background", "panel", "overlay"):
                    if debug:
                        debug_log(f"SKIP (layer-shell): {app_id} / {title}")
                    continue
                # Skip known overlay app-ids
                if app_id in ("gtk-layer-shell", "shutdown-overlay", "mpvpaper",
                              "fade-animation", "fire-black-overlay", "sakura-animation"):
                    if debug:
                        debug_log(f"SKIP (known overlay): {app_id}")
                    continue
                if not title or title == "nil":
                    if debug:
                        debug_log(f"SKIP (no title): {app_id}")
                    continue
                if "shutdown-effect" in title or "animate.py" in title:
                    if debug:
                        debug_log(f"SKIP (our process): {title}")
                    continue

                if debug:
                    debug_log(f"CLOSING: {app_id} / {title}")
                sock.close_view(view["id"])
                closed_count += 1
                time.sleep(0.05)
            except Exception as e:
                debug_log(f"Error closing view {view.get('id', '?')}: {e}")

        debug_log(f"Closed {closed_count} windows")
    except Exception as e:
        debug_log(f"ERROR in close_windows_gracefully: {e}")
        print(f"ERROR: Failed to close windows: {e}", file=sys.stderr)
        success = False

    done_event.set()
    return success


class AnimationProcess:
    """Manages the animation subprocess and signal communication."""

    def __init__(self, script_path):
        self.script_path = script_path
        self.process = None
        self.ready_event = threading.Event()
        self.black_event = threading.Event()
        self._reader_thread = None

    def start(self):
        """Start the animation subprocess."""
        if not os.path.exists(self.script_path):
            debug_log(f"ERROR: Animation script not found: {self.script_path}")
            print(f"ERROR: Animation script not found: {self.script_path}", file=sys.stderr)
            return False

        debug_log(f"Starting animation: {self.script_path}")
        self.process = subprocess.Popen(
            ["python3", self.script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        # Start reader thread to watch for signals
        self._reader_thread = threading.Thread(target=self._read_signals, daemon=True)
        self._reader_thread.start()
        return True

    def _read_signals(self):
        """Read stdout from animation process for READY/BLACK signals."""
        try:
            for line in self.process.stdout:
                line = line.strip()
                debug_log(f"Animation signal: {line}")
                if line == "READY":
                    self.ready_event.set()
                elif line == "BLACK":
                    self.black_event.set()
        except Exception as e:
            debug_log(f"Error reading animation signals: {e}")
        finally:
            # If process exits without signaling, set events to unblock waiters
            self.ready_event.set()
            self.black_event.set()

    def wait_ready(self, timeout=5.0):
        """Wait for animation to signal READY (overlay is visible)."""
        debug_log(f"Waiting for READY signal (timeout={timeout}s)")
        result = self.ready_event.wait(timeout=timeout)
        if not result:
            debug_log("WARNING: Timeout waiting for READY signal")
        return result

    def wait_black(self, timeout=30.0):
        """Wait for animation to signal BLACK (animation complete)."""
        debug_log(f"Waiting for BLACK signal (timeout={timeout}s)")
        result = self.black_event.wait(timeout=timeout)
        if not result:
            debug_log("WARNING: Timeout waiting for BLACK signal")
        return result

    def is_running(self):
        """Check if animation process is still running."""
        return self.process is not None and self.process.poll() is None

    def terminate(self):
        """Terminate the animation process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()


def send_ipc(method):
    """Send IPC command to Wayfire"""
    try:
        from wayfire import WayfireSocket
        import json
        sock = WayfireSocket()
        sock.client.settimeout(2.0)
        msg = json.dumps({"method": method, "data": {}}).encode('utf8')
        sock.client.send(len(msg).to_bytes(4, byteorder='little') + msg)
        sock.read_message()
        sock.close()
        return True
    except Exception as e:
        debug_log(f"WARNING: IPC {method} failed: {e}")
        return False


def send_ipc_with_retry(method, max_attempts=5, delay=1.0):
    """Send IPC command with retry logic (for post-resume when compositor may be slow)"""
    for attempt in range(max_attempts):
        if send_ipc(method):
            return True
        if attempt < max_attempts - 1:
            debug_log(f"Retrying {method} in {delay}s (attempt {attempt + 1}/{max_attempts})")
            time.sleep(delay)
    debug_log(f"ERROR: {method} failed after {max_attempts} attempts")
    return False


def unfreeze_compositor(retry=False):
    """Unfreeze the compositor (cleanup for test mode)"""
    if retry:
        success = send_ipc_with_retry("screen-freeze/unfreeze")
    else:
        success = send_ipc("screen-freeze/unfreeze")
    if success:
        debug_log("Compositor unfrozen")


def show_cursor(retry=False):
    """Show the cursor (cleanup for test mode)"""
    if retry:
        success = send_ipc_with_retry("cursor-control/show")
    else:
        success = send_ipc("cursor-control/show")
    if success:
        debug_log("Cursor restored")


def execute_power_action(action, animation=None, hold_time=3):
    """Execute the power action.

    Args:
        action: The power action to execute
        animation: Optional AnimationProcess to terminate in test mode
        hold_time: How long to hold in test mode (seconds)
    """
    cmd = POWER_COMMANDS.get(action)

    # Test mode - just wait then terminate animation
    if cmd is None:
        debug_log(f"[TEST] Animation complete, waiting {hold_time} seconds...")
        print(f"[TEST] Animation complete. Waiting {hold_time} seconds...")
        time.sleep(hold_time)
        if animation:
            animation.terminate()
        # Cleanup: unfreeze compositor and restore cursor
        unfreeze_compositor()
        show_cursor()
        debug_log("[TEST] Done")
        print("[TEST] Done.")
        return

    # Logout needs session ID
    if action == "logout":
        session_id = get_session_id()
        if session_id:
            cmd = ["loginctl", "terminate-session", session_id]
            debug_log(f"Logout: using session ID {session_id}")
        else:
            debug_log("ERROR: Could not determine session ID for logout")
            print("ERROR: Could not determine session ID for logout", file=sys.stderr)
            if animation:
                animation.terminate()
            return

    # Windows needs boot entry
    if action == "windows":
        debug_log("Setting Windows boot entry...")
        result = subprocess.run(
            ["sudo", "-A", "efibootmgr", "--bootnext", "0003"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            debug_log(f"WARNING: efibootmgr failed: {result.stderr}")
            print(f"WARNING: Could not set Windows boot entry", file=sys.stderr)

    debug_log(f"Executing power action: {' '.join(cmd)}")
    print(f"Executing: {' '.join(cmd)}")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Keep process alive until system powers off
    # Animation subprocess continues showing black screen
    if action in ("suspend", "hibernate"):
        debug_log("Waiting for resume from suspend/hibernate...")
        time.sleep(3)  # Brief pause for compositor to wake up
        if animation:
            animation.terminate()
        # Cleanup: unfreeze compositor and restore cursor after resume
        # Use retry=True because compositor may be slow to respond after waking
        unfreeze_compositor(retry=True)
        show_cursor(retry=True)
        debug_log("Resumed from suspend/hibernate, compositor unfrozen")
    else:
        # Hold indefinitely until killed by shutdown
        debug_log("Holding until system shuts down...")
        while True:
            time.sleep(1)


def list_animations():
    """List available animations"""
    animations = []
    if os.path.isdir(ANIMATIONS_DIR):
        for name in os.listdir(ANIMATIONS_DIR):
            script = os.path.join(ANIMATIONS_DIR, name, "animate.py")
            if os.path.exists(script):
                animations.append(name)
    return sorted(animations)


def parse_args():
    """Parse command line arguments"""
    available = list_animations()

    parser = argparse.ArgumentParser(
        description="Shutdown effect with customizable animations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available animations: {', '.join(available) or 'none found'}

Examples:
  %(prog)s test                      # Test animation
  %(prog)s test -a fade              # Test fade animation
  %(prog)s shutdown -a sakura        # Real shutdown with sakura
"""
    )

    parser.add_argument(
        "action",
        choices=["shutdown", "reboot", "logout", "suspend", "hibernate", "windows", "test"],
        help="Power action to execute"
    )
    parser.add_argument(
        "-a", "--animation",
        default=DEFAULT_ANIMATION,
        choices=available if available else None,
        help=f"Animation to use (default: {DEFAULT_ANIMATION})"
    )
    parser.add_argument(
        "--hold",
        type=int,
        default=3,
        metavar="SECONDS",
        help="Hold black screen for N seconds in test mode (default: 3)"
    )

    return parser.parse_args()


def main():
    args = parse_args()
    action = args.action
    animation_name = args.animation
    hold_time = args.hold


    # Install signal handlers early
    install_signal_handlers()

    # Initialize debug log
    debug_mode = (action == "test")
    init_debug_log()
    debug_log(f"Starting shutdown-effect: action={action}, animation={animation_name}")

    # =========================================================================
    # STEP 1: Start animation (it will capture screenshot and show overlay)
    # =========================================================================
    print(f"[1/3] Starting {animation_name} animation...")
    script_path = get_animation_script(animation_name)
    animation = AnimationProcess(script_path)

    if not animation.start():
        print("ERROR: Failed to start animation", file=sys.stderr)
        return 1

    # =========================================================================
    # STEP 2: Wait for animation to signal READY (overlay visible)
    # =========================================================================
    print("[2/3] Waiting for overlay...")
    if not animation.wait_ready(timeout=5.0):
        print("WARNING: Animation did not signal READY, proceeding anyway", file=sys.stderr)

    # =========================================================================
    # STEP 3: Let systemd handle window/process termination
    # =========================================================================
    # We don't close windows ourselves - systemd will SIGTERM all processes
    # when the shutdown command executes. This avoids lag from compositor
    # work during the animation and respects apps' save dialogs.
    print("[3/3] Animation playing (systemd will handle cleanup)...")
    debug_log("Skipping manual window close - letting systemd handle it")

    # =========================================================================
    # STEP 4: Wait for animation to reach BLACK (full black screen)
    # =========================================================================
    print("Waiting for animation to complete...")
    if not animation.wait_black(timeout=30.0):
        print("WARNING: Animation did not signal BLACK, proceeding anyway", file=sys.stderr)

    # =========================================================================
    # STEP 5: Execute power action (animation continues showing black)
    # =========================================================================
    print("Animation complete.")
    debug_log("Executing power action...")
    execute_power_action(action, animation, hold_time)

    return 0


if __name__ == "__main__":
    sys.exit(main())
