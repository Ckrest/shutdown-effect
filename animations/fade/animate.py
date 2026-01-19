#!/usr/bin/env python3
"""
Fade animation for shutdown effect.

Protocol signals (printed to stdout):
- "READY" = screenshot captured, overlay visible, safe to close windows
- "BLACK" = animation complete, screen is fully black

Takes a screenshot, displays it as a layer-shell overlay,
and fades it to black over FADE_DURATION seconds.
Then HOLDS the black screen forever until system kills the process.

Usage: animate.py [screenshot_path]
  If screenshot_path not provided, captures a new screenshot.
"""

import subprocess
import os
import sys
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, Gdk, GtkLayerShell, GdkPixbuf, GLib

# Animation settings
FADE_DURATION = 1.0  # seconds
FRAME_RATE = 60  # fps

DEFAULT_SCREENSHOT = "/tmp/shutdown-fade-screenshot.png"


class FadeOverlay:
    def __init__(self, screenshot_path):
        self.screenshot_path = screenshot_path
        self.window = None
        self.drawing_area = None
        self.pixbuf = None
        self.alpha = 1.0
        self.fade_start_time = None
        self.fading = False
        self.signaled_black = False

    def signal(self, msg):
        """Send a signal to the orchestrator via stdout."""
        print(msg, flush=True)

    def create_overlay(self):
        """Create overlay using layer-shell"""
        window = Gtk.Window()

        GtkLayerShell.init_for_window(window)
        GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_namespace(window, "fade-animation")

        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_exclusive_zone(window, -1)
        GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self.on_draw)
        self.drawing_area.connect("realize", self.hide_cursor)
        window.add(self.drawing_area)
        window.connect("realize", self.hide_cursor)

        self.window = window
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.screenshot_path)

    def hide_cursor(self, widget):
        display = Gdk.Display.get_default()
        blank_cursor = Gdk.Cursor.new_from_name(display, "none")
        if widget.get_window():
            widget.get_window().set_cursor(blank_cursor)

    def on_draw(self, widget, cr):
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        if self.pixbuf and self.alpha > 0:
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint_with_alpha(self.alpha)
        return True

    def start_fade(self):
        self.fading = True
        self.fade_start_time = time.time()
        frame_interval = int(1000 / FRAME_RATE)
        GLib.timeout_add(frame_interval, self.animate_frame)

    def animate_frame(self):
        if not self.fading:
            return False

        elapsed = time.time() - self.fade_start_time
        progress = min(elapsed / FADE_DURATION, 1.0)
        self.alpha = 1.0 - progress
        self.drawing_area.queue_draw()

        if progress >= 1.0:
            self.fading = False
            # Signal BLACK - screen is now fully black
            if not self.signaled_black:
                self.signaled_black = True
                self.signal("BLACK")
            # DON'T quit - keep the black overlay visible
            # The system shutdown will kill us
            return False

        return True

    def run(self):
        self.create_overlay()
        self.window.show_all()

        # Process events to ensure overlay is visible
        while Gtk.events_pending():
            Gtk.main_iteration()

        # Signal READY - overlay is visible, safe to close windows
        self.signal("READY")

        GLib.timeout_add(100, self.start_fade)

        # Run GTK main loop forever - we hold the black screen
        # until system shutdown kills this process
        Gtk.main()


def capture_screenshot(path):
    """Capture fullscreen screenshot"""
    result = subprocess.run(["grim", path], capture_output=True)
    return result.returncode == 0 and os.path.exists(path)


def main():
    # Get screenshot path from args or use default
    if len(sys.argv) > 1:
        screenshot_path = sys.argv[1]
    else:
        screenshot_path = DEFAULT_SCREENSHOT
        if not capture_screenshot(screenshot_path):
            print("ERROR: Failed to capture screenshot")
            sys.exit(1)

    overlay = FadeOverlay(screenshot_path)
    overlay.run()


if __name__ == "__main__":
    main()
