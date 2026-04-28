"""
Manages network communication for sending captured frames to the server.
"""

import requests
import threading
import cv2
import urllib.parse

# --- Constants ---
SERVER_URL = "http://127.0.0.1:6000/upload"

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

    def get_notifications(self, phone_number):
        """
        Polls the server for new notifications for the given phone number.
        Returns a list of notification dicts.
        """
        print(f"Fetching notifications for {phone_number}")
        try:
            response = requests.get(f"{self.server_url.replace('/upload', '/get_notifications')}?phone_number={urllib.parse.quote(phone_number)}")
            print(f"Response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Response JSON: {data}")
                return data.get('notifications', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching notifications: {e}")
        return []
