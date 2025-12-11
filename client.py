
"""
Main entry point for the TV Detector Client application.
Orchestrates the interaction between the UI, camera, image processing, and network modules.
"""

import tkinter as tk
import cv2
from login_window import LoginWindow
from main_ui import MainUI
from camera_manager import CameraManager
from image_processor import ImageProcessor
from network_manager import NetworkManager

# --- Constants ---
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480
REFRESH_DELAY_MS = 15

# Frame Rate Modes: (frames_to_send, frames_to_wait)
MODE_PARAMS = {
    "Weak": (1, 30),
    "Balanced": (3, 10),
    "Aggressive": (10, 2)
}
DEFAULT_MODE = "Balanced"

class AppController:
    """
    Controller class that manages the application state and logic.
    """
    def __init__(self, master, phone_number):
        self.master = master
        self.phone_number = phone_number
        
        # --- Modules ---
        self.camera = CameraManager()
        self.processor = ImageProcessor(display_size=(DISPLAY_WIDTH, DISPLAY_HEIGHT))
        self.network = NetworkManager()
        
        # --- State ---
        self.is_running = False
        self.frame_counter = 0
        self.is_capturing_phase = True
        self.frames_to_send, self.frames_to_wait = MODE_PARAMS[DEFAULT_MODE]

        # --- UI Initialization ---
        self.ui = MainUI(self.master, self.get_callbacks())
        
        # --- Start ---
        print("Attempting to open camera...")
        self.camera.open_camera()
        print("Camera open attempt finished.")
        
        self.ui.status_label.config(text=f"Logged in as: {self.phone_number} | Camera Active")
        self.master.after(REFRESH_DELAY_MS, self.update)

    def update(self):
        """
        Main update loop. Captures frames, processes them, updates the UI,
        and handles the automatic capture cycle.
        """
        if self.camera.is_working:
            frame = self.camera.get_frame()
            if frame is not None:
                if self.is_running:
                    self.handle_capture_cycle(frame)
                
                zoomed_frame = self.processor.get_zoomed_frame(frame)
                if zoomed_frame is not None and zoomed_frame.size > 0:
                    resized_frame = cv2.resize(zoomed_frame, (self.ui.display_width, self.ui.display_height))
                    self.ui.update_canvas(resized_frame)
                    
                    box_coords = self.processor.get_box_coords(self.ui.display_width, self.ui.display_height)
                    self.ui.draw_overlay(box_coords)
                else:
                    self.ui.show_message("Processing Error")
            else:
                self.ui.show_message("No Video Signal")
        else:
            self.ui.show_message(f"Camera {self.camera.video_source_index} Unavailable\nClick 'Switch Camera'")
        
        self.master.after(REFRESH_DELAY_MS, self.update)

    def handle_capture_cycle(self, frame):
        """
        Manages the timing for sending frames to the server based on the selected performance mode.
        """
        self.frame_counter += 1
        if self.is_capturing_phase:
            region = self.processor.get_capture_region(frame)
            if region is not None and region.size > 0:
                data = {
                    'phone_number': self.phone_number,
                    'strictness': self.ui.strictness_var.get()
                }
                self.network.send_frame_async(region, data)
            
            if self.frame_counter >= self.frames_to_send:
                self.is_capturing_phase = False
                self.frame_counter = 0
        else:
            if self.frame_counter >= self.frames_to_wait:
                self.is_capturing_phase = True
                self.frame_counter = 0

    # --- Callbacks for UI ---
    def get_callbacks(self):
        """Returns a dictionary of callback functions for the UI module."""
        return {
            "handle_mouse_scroll": self.handle_mouse_scroll,
            "start_pan": self.start_pan,
            "do_pan": self.do_pan,
            "end_pan": self.end_pan,
            "toggle_capture": self.toggle_capture,
            "switch_camera": self.switch_camera,
            "reset_view": self.reset_view,
            "update_mode": self.update_mode,
        }

    def toggle_capture(self):
        """Toggles the automatic capture process on/off."""
        self.is_running = not self.is_running
        if self.is_running:
            self.ui.btn_toggle.config(text="Stop Capturing", bg="red", fg="black")
            self.frame_counter = 0
            self.is_capturing_phase = True
        else:
            self.ui.btn_toggle.config(text="Start Capturing", bg="green", fg="black")

    def switch_camera(self):
        """Switches to the next available camera source."""
        self.camera.switch_camera()
        self.reset_view()

    def reset_view(self):
        """Resets zoom and pan to default values."""
        self.processor.reset_view()

    def update_mode(self):
        """Updates the capture parameters based on the selected performance mode."""
        mode = self.ui.mode_var.get()
        self.frames_to_send, self.frames_to_wait = MODE_PARAMS[mode]

    def handle_mouse_scroll(self, event):
        """Handles mouse scroll events for zooming."""
        if event.num == 5 or event.delta < 0:
            self.processor.zoom_level -= 0.1
        else:
            self.processor.zoom_level += 0.1
        
        self.processor.zoom_level = max(1.0, min(4.0, self.processor.zoom_level))
        if self.processor.zoom_level == 1.0:
            self.reset_view()

    def start_pan(self, event):
        """Records the starting position for a pan operation."""
        self.pan_start_x, self.pan_start_y = event.x, event.y

    def do_pan(self, event):
        """Calculates and applies the pan offset based on mouse movement."""
        dx, dy = event.x - self.pan_start_x, event.y - self.pan_start_y
        
        self.processor.pan_x -= dx / self.ui.display_width
        self.processor.pan_y -= dy / self.ui.display_height
        
        self.processor.pan_x = max(-1.0, min(1.0, self.processor.pan_x))
        self.processor.pan_y = max(-1.0, min(1.0, self.processor.pan_y))
        
        self.pan_start_x, self.pan_start_y = event.x, event.y

    def end_pan(self, event):
        """Placeholder for end pan event."""
        pass

if __name__ == '__main__':
    # Step 1: Create and run the login window first.
    login = LoginWindow()
    phone_number = login.run() # This will block until the login window is closed.

    # Step 2: Only if login was successful, create and run the main app.
    if phone_number:
        root = tk.Tk()
        app = AppController(root, phone_number)
        root.mainloop()
    else:
        print("Login cancelled. Exiting.")
