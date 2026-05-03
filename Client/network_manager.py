"""
Manages network communication for sending captured frames to the server.
"""

import os
import urllib.parse

import cv2
import requests
import threading

# --- Constants ---
DEFAULT_DETECTOR_ORIGIN = "http://127.0.0.1:6000"


def detector_origin():
    """Base URL without trailing slash, e.g. http://detector:6000"""
    url = os.environ.get("DETECTOR_URL", DEFAULT_DETECTOR_ORIGIN).strip().rstrip("/")
    if url.endswith("/upload"):
        url = url[: -len("/upload")].rstrip("/")
    return url


def detector_upload_url():
    return f"{detector_origin()}/upload"


def detector_notifications_url(phone_number: str):
    q = urllib.parse.quote(phone_number, safe="")
    return f"{detector_origin()}/get_notifications?phone_number={q}"


class NetworkManager:
    """
    A class to handle sending image data to a server asynchronously.
    """

    def __init__(self, server_url=None):
        self.server_url = server_url or detector_upload_url()

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
            requests.post(self.server_url, files=files, data=data)
        except requests.exceptions.RequestException as e:
            print(f"Error sending image: {e}")

    def get_notifications(self, phone_number):
        """
        Polls the server for new notifications for the given phone number.
        Returns a list of notification dicts.
        """
        try:
            response = requests.get(detector_notifications_url(phone_number))
            if response.status_code == 200:
                data = response.json()
                return data.get('notifications', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching notifications: {e}")
        return []
