
"""
Manages camera operations, including opening, switching, and capturing frames.
"""

import cv2

# --- Constants ---
MAX_CAMERA_INDICES = 5

class CameraManager:
    """
    A class to encapsulate camera functionalities using OpenCV.
    """
    def __init__(self):
        self.vid = None
        self.video_source_index = 0
        self.is_working = False
        self.width = 0
        self.height = 0

    def open_camera(self):
        """
        Opens the camera at the current index and verifies it's operational.
        Returns:
            bool: True if the camera was opened successfully, False otherwise.
        """
        if self.vid:
            self.vid.release()
        
        self.vid = cv2.VideoCapture(self.video_source_index)
        
        if self.vid.isOpened():
            ret, _ = self.vid.read()
            if ret:
                self.width = self.vid.get(cv2.CAP_PROP_FRAME_WIDTH)
                self.height = self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT)
                self.is_working = True
            else:
                self.is_working = False
        else:
            self.is_working = False
        
        return self.is_working

    def switch_camera(self):
        """
        Cycles to the next camera index and attempts to open it.
        Returns:
            bool: True if the new camera was opened successfully, False otherwise.
        """
        self.video_source_index = (self.video_source_index + 1) % MAX_CAMERA_INDICES
        return self.open_camera()

    def get_frame(self):
        """
        Retrieves a single frame from the currently opened camera.
        Returns:
            numpy.ndarray or None: The captured frame, or None if capture fails.
        """
        if self.is_working and self.vid.isOpened():
            ret, frame = self.vid.read()
            if ret:
                return frame
        return None

    def release(self):
        """
        Releases the camera resource when it's no longer needed.
        """
        if self.vid:
            self.vid.release()
