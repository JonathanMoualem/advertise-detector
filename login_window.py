
"""
Handles the initial user login window for phone number validation.
"""

import tkinter as tk
from tkinter import messagebox

# --- Constants ---
WINDOW_WIDTH = 300
WINDOW_HEIGHT = 200
MIN_PHONE_DIGITS = 7
LOGIN_BUTTON_COLOR = "#4CAF50"

class LoginWindow:
    """
    A modal window that prompts the user for a phone number and validates it.
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Login")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.phone_number = None
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        tk.Label(self.root, text="TV Detector Login", font=("Arial", 16, "bold")).pack(pady=20)
        
        tk.Label(self.root, text="Enter Phone Number:").pack()
        self.entry = tk.Entry(self.root, font=("Arial", 12))
        self.entry.pack(pady=5)
        self.entry.focus_set() 
        
        self.root.bind('<Return>', lambda event: self.validate())
        
        self.btn_login = tk.Button(self.root, text="Login", command=self.validate, width=15, bg=LOGIN_BUTTON_COLOR, fg="black")
        self.btn_login.pack(pady=20)
        
        self.center_window()

    def center_window(self):
        """Centers the login window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def validate(self):
        """Validates the entered phone number."""
        phone = self.entry.get().strip()
        if phone.isdigit() and len(phone) >= MIN_PHONE_DIGITS:
            self.phone_number = phone
            self.root.destroy()
        else:
            messagebox.showerror("Login Error", "Please enter a valid phone number (digits only).", parent=self.root)

    def on_close(self):
        """Handles the window close event."""
        self.root.destroy()

    def run(self):
        """
        Runs the login window's main loop and returns the phone number upon completion.
        Returns:
            str or None: The validated phone number, or None if login was cancelled.
        """
        self.root.mainloop()
        return self.phone_number
