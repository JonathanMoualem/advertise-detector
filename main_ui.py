"""
Manages the main application's user interface using Tkinter.
This module is responsible for creating and updating all widgets.
"""

import tkinter as tk
from PIL import Image, ImageTk
import cv2
import ctypes

# --- Constants ---
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480
CANVAS_BG_COLOR = "#1a1a1a"
OVERLAY_COLOR = "#128C7E"
OVERLAY_THICKNESS = 3
FONT_FAMILY = "Segoe UI"
FONT_SIZE_NORMAL = 10
FONT_SIZE_LARGE = 12
FONT_WEIGHT_BOLD = "bold"

# --- Colors (Dark Theme) ---
BG_PRIMARY = "#1e1e1e"
BG_SECONDARY = "#2d2d2d"
FG_PRIMARY = "#ffffff"
FG_SECONDARY = "#b0b0b0"
ACCENT_GREEN = "#128C7E"
ACCENT_RED = "#ff4444"
BUTTON_HOVER = "#383838"

class MainUI:
    """
    Builds and manages the main UI components of the application.
    """
    def __init__(self, master, callbacks):
        self.master = master
        self.callbacks = callbacks
        self.display_width = DISPLAY_WIDTH
        self.display_height = DISPLAY_HEIGHT

        self.master.title("TV Detector Client")
        self.master.configure(bg=BG_PRIMARY)
        self.master.geometry("800x850")
        
        # Enable dark mode for title bar on Windows
        try:
            hwnd = self.master.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(2)), 4)
        except:
            pass
        
        self.canvas = tk.Canvas(self.master, width=self.display_width, height=self.display_height, bg=CANVAS_BG_COLOR, cursor="fleur", highlightthickness=0)
        self.canvas.pack(pady=15)

        # Bind mouse events to the provided callbacks
        self.canvas.bind("<MouseWheel>", self.callbacks["handle_mouse_scroll"])
        self.canvas.bind("<Button-4>", self.callbacks["handle_mouse_scroll"])
        self.canvas.bind("<Button-5>", self.callbacks["handle_mouse_scroll"])
        self.canvas.bind("<ButtonPress-1>", self.callbacks["start_pan"])
        self.canvas.bind("<B1-Motion>", self.callbacks["do_pan"])
        self.canvas.bind("<ButtonRelease-1>", self.callbacks["end_pan"])

        self._create_widgets()

    def _create_widgets(self):
        """Creates and packs all the control widgets."""
        # --- Main Control Frame ---
        main_frame = tk.Frame(self.master, bg=BG_PRIMARY)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Top Button Frame ---
        button_frame = tk.Frame(main_frame, bg=BG_SECONDARY, relief=tk.RAISED, bd=1)
        button_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(button_frame, text="CONTROLS", font=(FONT_FAMILY, 11, FONT_WEIGHT_BOLD), bg=BG_SECONDARY, fg=ACCENT_GREEN).pack(anchor=tk.CENTER, padx=10, pady=5)

        # --- Buttons ---
        button_subframe = tk.Frame(button_frame, bg=BG_SECONDARY)
        button_subframe.pack(pady=5)

        self.btn_toggle = self._create_button(button_subframe, "▶ Start Capturing", self.callbacks["toggle_capture"], ACCENT_GREEN)
        self.btn_toggle.pack(side=tk.LEFT, padx=3)

        self.btn_switch = self._create_button(button_subframe, "📷 Switch Camera", self.callbacks["switch_camera"], "#2c5aa0")
        self.btn_switch.pack(side=tk.LEFT, padx=3)

        self.btn_reset = self._create_button(button_subframe, "↺ Reset View", self.callbacks["reset_view"], "#a67c00")
        self.btn_reset.pack(side=tk.LEFT, padx=3)

        # --- Settings Frame ---
        settings_frame = tk.Frame(main_frame, bg=BG_SECONDARY, relief=tk.RAISED, bd=1)
        settings_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(settings_frame, text="SETTINGS", font=(FONT_FAMILY, 11, FONT_WEIGHT_BOLD), bg=BG_SECONDARY, fg=ACCENT_GREEN).pack(anchor=tk.CENTER, padx=10, pady=5)

        settings_content = tk.Frame(settings_frame, bg=BG_SECONDARY)
        settings_content.pack(fill=tk.X, padx=10, pady=5)

        # --- Performance Settings ---
        perf_frame = tk.Frame(settings_content, bg=BG_SECONDARY)
        perf_frame.pack(fill=tk.X, pady=5)

        # Center container for the performance controls
        perf_center = tk.Frame(perf_frame, bg=BG_SECONDARY)
        perf_center.pack(expand=True)
        
        tk.Label(perf_center, text="Performance:", font=(FONT_FAMILY, 10, FONT_WEIGHT_BOLD), bg=BG_SECONDARY, fg=FG_PRIMARY).pack(side=tk.LEFT, padx=5)
        
        self.mode_var = tk.StringVar(value="Balanced")
        self.mode_buttons = {}
        for mode in ["Weak", "Balanced", "Aggressive"]:
            btn = tk.Button(perf_center, text=mode, font=(FONT_FAMILY, 9, FONT_WEIGHT_BOLD),
                           bg=BG_PRIMARY if mode != "Balanced" else ACCENT_GREEN,
                           fg=FG_SECONDARY if mode != "Balanced" else "white",
                           relief=tk.FLAT, padx=12, pady=5, cursor="hand2",
                           command=lambda m=mode: self._update_mode_btn(m))
            btn.pack(side=tk.LEFT, padx=3)
            self.mode_buttons[mode] = btn

        # --- Strictness Settings ---
        strict_frame = tk.Frame(settings_content, bg=BG_SECONDARY)
        strict_frame.pack(fill=tk.X, pady=5)

        # Center container for the strictness controls
        strict_center = tk.Frame(strict_frame, bg=BG_SECONDARY)
        strict_center.pack(expand=True)
        
        tk.Label(strict_center, text="Strictness:", font=(FONT_FAMILY, 10, FONT_WEIGHT_BOLD), bg=BG_SECONDARY, fg=FG_PRIMARY).pack(side=tk.LEFT, padx=5)
        
        self.strictness_var = tk.StringVar(value="Balanced")
        self.strictness_buttons = {}
        for level in ["Weak", "Balanced", "Aggressive"]:
            btn = tk.Button(strict_center, text=level, font=(FONT_FAMILY, 9, FONT_WEIGHT_BOLD),
                           bg=BG_PRIMARY if level != "Balanced" else ACCENT_GREEN,
                           fg=FG_SECONDARY if level != "Balanced" else "white",
                           relief=tk.FLAT, padx=12, pady=5, cursor="hand2",
                           command=lambda l=level: self._update_strictness_btn(l))
            btn.pack(side=tk.LEFT, padx=3)
            self.strictness_buttons[level] = btn

        # --- Status Bar ---
        self.status_label = tk.Label(self.master, text="Initializing...", bd=1, relief=tk.SUNKEN, 
                                    anchor=tk.W, bg=BG_SECONDARY, fg=FG_SECONDARY, font=(FONT_FAMILY, 9))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def _create_button(self, parent, text, command, color):
        """Helper method to create styled buttons."""
        btn = tk.Button(parent, text=text, command=command, bg=color, fg="white", 
                       font=(FONT_FAMILY, 10, FONT_WEIGHT_BOLD), relief=tk.FLAT, 
                       padx=12, pady=8, cursor="hand2", activebackground="#1a7f6f", activeforeground="white")
        return btn

    def _update_mode_btn(self, mode):
        """Updates the mode setting and button appearance."""
        self.mode_var.set(mode)
        for m, btn in self.mode_buttons.items():
            if m == mode:
                btn.config(bg=ACCENT_GREEN, fg="white")
            else:
                btn.config(bg=BG_PRIMARY, fg=FG_SECONDARY)
        self.callbacks["update_mode"]()

    def _update_strictness_btn(self, level):
        """Updates the strictness setting and button appearance."""
        self.strictness_var.set(level)
        for l, btn in self.strictness_buttons.items():
            if l == level:
                btn.config(bg=ACCENT_GREEN, fg="white")
            else:
                btn.config(bg=BG_PRIMARY, fg=FG_SECONDARY)

    def update_canvas(self, frame):
        """
        Updates the canvas with a new frame.
        Args:
            frame: The image frame (as a NumPy array) to display.
        """
        photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
        self.canvas.photo = photo # Keep a reference to prevent garbage collection

    def draw_overlay(self, box_coords):
        """
        Draws the alignment box and text overlay on the canvas.
        Args:
            box_coords (tuple): A tuple (x1, y1, x2, y2) for the box.
        """
        x1, y1, x2, y2 = box_coords
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=OVERLAY_COLOR, width=OVERLAY_THICKNESS)
        self.canvas.create_text(self.display_width/2, y1 - 20, text="📺 Align TV Here", fill=OVERLAY_COLOR,
                               font=(FONT_FAMILY, FONT_SIZE_LARGE, FONT_WEIGHT_BOLD))

    def show_message(self, message, color=None):
        """
        Displays a message in the center of the canvas, clearing other content.
        Args:
            message (str): The text to display.
            color (str): The color of the text.
        """
        if color is None:
            color = "#ff6b6b"
        self.canvas.delete("all")
        self.canvas.create_text(self.display_width/2, self.display_height/2, text=message, fill=color, 
                               justify=tk.CENTER, font=(FONT_FAMILY, 14, FONT_WEIGHT_BOLD))

    def show_notification_popup(self, message):
        """
        Displays a small popup window in the top-left corner of the camera view with a bell icon and message.
        Automatically closes after 3 seconds.
        """
        # Calculate position: Top-left of the canvas (relative to the main window)
        canvas_x = self.master.winfo_rootx() + self.canvas.winfo_x()
        canvas_y = self.master.winfo_rooty() + self.canvas.winfo_y()
        
        # Create popup window
        popup = tk.Toplevel(self.master)
        popup.geometry(f"250x60+{canvas_x}+{canvas_y}")  # Small size, positioned at top-left
        popup.overrideredirect(True)  # No title bar
        popup.attributes("-topmost", True)  # Always on top
        popup.configure(bg=BG_SECONDARY)
        
        # Add bell icon and message
        icon_label = tk.Label(popup, text="🔔", font=(FONT_FAMILY, 15), bg=BG_SECONDARY, fg=FG_PRIMARY)
        icon_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        msg_label = tk.Label(popup, text=message, font=(FONT_FAMILY, 8), bg=BG_SECONDARY, fg=FG_PRIMARY, wraplength=200)
        msg_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Auto-close after 3 seconds
        popup.after(3000, popup.destroy)
