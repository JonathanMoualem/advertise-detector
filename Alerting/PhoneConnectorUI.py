import json
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import messagebox

import qrcode
from PIL import ImageTk

from Alerting.Alerts import SANDBOX_CODE, TWILIO_NUMBER, USER_CONFIG_FILE


class PhoneConnector:
    """
    A class to handle the connection of a phone number to WhatsApp for receiving alerts.
    """

    def __init__(self, root, sandbox_code=SANDBOX_CODE, twilio_num=TWILIO_NUMBER):
        self.root = root
        self.sandbox_code = sandbox_code
        self.twilio_num = twilio_num
        self.root.title("Connect WhatsApp")
        self.root.geometry("400x550")
        self.root.configure(bg="#2b2b2b")

        # Scene 1: Input Number
        self.input_frame = tk.Frame(self.root, bg="#2b2b2b")
        self.setup_input_scene()

        # Scene 2: QR/Link (Hidden initially)
        self.qr_frame = tk.Frame(self.root, bg="#2b2b2b")

    def setup_input_scene(self):
        """
        Sets up the input scene with a phone number entry field and a "Next" button.
        """
        self.input_frame.pack(expand=True, fill="both")
        tk.Label(self.input_frame, text="Enter Your Phone Number", font=("Arial", 14, "bold"), bg="#2b2b2b",
                 fg="white").pack(
            pady=20)
        tk.Label(self.input_frame, text="Use international format (e.g., +972501234567)", bg="#2b2b2b",
                 fg="#cccccc").pack()

        self.num_entry = tk.Entry(self.input_frame, font=("Arial", 12), width=25)
        self.num_entry.pack(pady=10)
        self.num_entry.insert(0, "+972")
        self.num_entry.bind("<Return>", lambda e: self.save_and_next())

        tk.Button(self.input_frame, text="Next: Connect WhatsApp", command=self.save_and_next, bg="#128C7E", fg="white",
                  font=("Arial", 10, "bold"), pady=10).pack(pady=20)

    def save_and_next(self):
        """
        Validates the entered phone number, saves it to a config file, and transitions to the QR code scene.
        """
        number = self.num_entry.get().strip().replace(" ", "")
        if not number.startswith("+") or len(number) < 10:
            messagebox.showerror("Error", "Please enter a valid number starting with +")
            return

        # Save to file
        with open(USER_CONFIG_FILE, "w") as f:
            json.dump({"user_number": number}, f)

        # Switch Scenes
        self.input_frame.pack_forget()
        self.setup_qr_scene()

    def setup_qr_scene(self):
        """
        Sets up the QR code scene with a QR code and a manual link.
        """
        self.qr_frame.pack(expand=True, fill="both")

        # Create WhatsApp link
        clean_twilio = self.twilio_num.replace("+", "").replace(" ", "")
        encoded_msg = urllib.parse.quote(self.sandbox_code)
        wa_link = f"https://wa.me/{clean_twilio}?text={encoded_msg}"

        tk.Label(self.qr_frame, text="Final Step: Join Sandbox", font=("Arial", 14, "bold"), bg="#2b2b2b",
                 fg="#128C7E").pack(pady=10)

        # Generate QR
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(wa_link)
        qr_img = ImageTk.PhotoImage(qr.make_image(fill_color="white", back_color="#2b2b2b"))

        qr_label = tk.Label(self.qr_frame, image=qr_img, bg="#3c3c3c")
        qr_label.image = qr_img
        qr_label.pack(pady=10)

        # The clickable Manual Link
        link_label = tk.Label(self.qr_frame, text=f"Click here to send message manually", fg="#00aaff", cursor="hand2",
                              bg="#2b2b2b", font=("Arial", 10, "underline"))
        link_label.pack(pady=10)
        link_label.bind("<Button-1>", lambda e: webbrowser.open(wa_link))

        tk.Label(self.qr_frame, text=f"Send '{self.sandbox_code}' to {self.twilio_num}", bg="#2b2b2b",
                 fg="white", font=("Arial", 9)).pack()

        tk.Button(self.qr_frame,
                  text="Finished Connecting whatsapp",
                  command=self.root.destroy, bg="#128C7E",
                  fg="white",
                  font=("Arial", 10, "bold"), pady=8).pack(pady=20)
        
        # Bind Enter key to finish setup
        self.root.bind("<Return>", lambda e: self.root.destroy())


if __name__ == "__main__":
    root = tk.Tk()
    # Use your actual Twilio Sandbox code here
    app = PhoneConnector(root, sandbox_code=SANDBOX_CODE)
    root.mainloop()
