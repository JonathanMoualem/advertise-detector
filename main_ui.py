
"""
Manages the main application's user interface using Tkinter.
This module is responsible for creating and updating all widgets.
"""

import tkinter as tk
from PIL import Image, ImageTk
import cv2

# --- Constants ---
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480
CANVAS_BG_COLOR = "black"
OVERLAY_COLOR = "white"
OVERLAY_THICKNESS = 5
FONT_FAMILY = "Arial"
FONT_SIZE_NORMAL = 10
FONT_SIZE_LARGE = 12
FONT_WEIGHT_BOLD = "bold"

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
        self.canvas = tk.Canvas(self.master, width=self.display_width, height=self.display_height, bg=CANVAS_BG_COLOR, cursor="fleur")
        self.canvas.pack()

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
        # --- Control Frames ---
        button_frame = tk.Frame(self.master)
        button_frame.pack(pady=5)
        settings_frame = tk.Frame(self.master)
        settings_frame.pack(pady=5)
        strictness_frame = tk.Frame(self.master)
        strictness_frame.pack(pady=5)

        # --- Buttons ---
        self.btn_toggle = tk.Button(button_frame, text="Start Capturing", width=15, command=self.callbacks["toggle_capture"], bg="green", fg="black")
        self.btn_toggle.pack(side=tk.LEFT, padx=5)
        self.btn_switch = tk.Button(button_frame, text="Switch Camera", width=15, command=self.callbacks["switch_camera"])
        self.btn_switch.pack(side=tk.LEFT, padx=5)
        self.btn_reset = tk.Button(button_frame, text="Reset View", width=15, command=self.callbacks["reset_view"])
        self.btn_reset.pack(side=tk.LEFT, padx=5)

        # --- Performance Settings ---
        tk.Label(settings_frame, text="Performance:", font=(FONT_FAMILY, FONT_SIZE_NORMAL, FONT_WEIGHT_BOLD)).pack(side=tk.LEFT, padx=5)
        self.mode_var = tk.StringVar(value="Balanced")
        for mode in ["Weak", "Balanced", "Aggressive"]:
            tk.Radiobutton(settings_frame, text=mode, variable=self.mode_var, value=mode, command=self.callbacks["update_mode"]).pack(side=tk.LEFT, padx=5)

        # --- Strictness Settings ---
        tk.Label(strictness_frame, text="Strictness:", font=(FONT_FAMILY, FONT_SIZE_NORMAL, FONT_WEIGHT_BOLD)).pack(side=tk.LEFT, padx=5)
        self.strictness_var = tk.StringVar(value="Balanced")
        for level in ["Weak", "Balanced", "Aggressive"]:
            tk.Radiobutton(strictness_frame, text=level, variable=self.strictness_var, value=level).pack(side=tk.LEFT, padx=5)

        # --- Status Bar ---
        self.status_label = tk.Label(self.master, text="Initializing...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

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
        self.canvas.create_text(self.display_width/2, y1 - 20, text="Align TV Here", fill=OVERLAY_COLOR, font=(FONT_FAMILY, FONT_SIZE_LARGE, FONT_WEIGHT_BOLD))

    def show_message(self, message, color="white"):
        """
        Displays a message in the center of the canvas, clearing other content.
        Args:
            message (str): The text to display.
            color (str): The color of the text.
        """
        self.canvas.delete("all")
        self.canvas.create_text(self.display_width/2, self.display_height/2, text=message, fill=color, justify=tk.CENTER)
