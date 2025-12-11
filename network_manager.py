
"""
Manages network communication for sending captured frames to the server.
"""

import requests
import threading
import cv2

# --- Constants ---
SERVER_URL = "http://127.0.0.1:5000/upload"

class NetworkManager:
    """
    A class to handle sending image data to a server asynchronously.
    """
    def __init__(self, server_url=SERVER_URL):
        self.server_url = server_url

    def send_frame_async(self, frame, data):
        """
        Encodes a frame to JPEG and sends it to the server in a separate thread
        to avoid blocking the main UI.
        Args:
            frame (numpy.ndarray): The image frame to send.
            data (dict): A dictionary of metadata to send along with the image.
        """
        _, img_encoded = cv2.imencode('.jpg', frame)
        threading.Thread(target=self._send_task, args=(img_encoded, data)).start()

    def _send_task(self, img_encoded, data):
        """
        The actual task that runs in a thread to send the request.
        """
        try:
            files = {'image': ('capture.jpg', img_encoded.tobytes(), 'image/jpeg')}
            response = requests.post(self.server_url, files=files, data=data)
            # Optional: Log server response for debugging, but can be noisy.
            # print(f"Server response: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error sending image: {e}")
