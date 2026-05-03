
"""
Handles image processing tasks like zooming, panning, and coordinate calculations.
"""

import cv2

# --- Constants ---
MIN_ZOOM = 1.0
MAX_ZOOM = 4.0
BOX_SCALE = 0.6 # 60% of the display size

# Crop must span at least this many pixels in each dimension before sending upstream.
MIN_CAPTURE_SIDE_PX = 32


def _snap_px(val):
    """Match browser Math.round(...) for landmark coordinates."""
    return int(round(val))


class ImageProcessor:
    """
    A class to manage digital zoom, pan, and cropping logic for image frames.
    """
    def __init__(self, display_size):
        self.display_width, self.display_height = display_size
        self.zoom_level = MIN_ZOOM
        self.pan_x = 0.0  # Range -1.0 to 1.0
        self.pan_y = 0.0  # Range -1.0 to 1.0

    def reset_view(self):
        """Resets zoom and pan to their default states."""
        self.zoom_level = MIN_ZOOM
        self.pan_x = 0.0
        self.pan_y = 0.0

    def get_zoomed_frame(self, frame):
        """
        Crops the original frame based on the current zoom and pan settings.
        Args:
            frame (numpy.ndarray): The full-resolution source frame.
        Returns:
            numpy.ndarray or None: The cropped (zoomed) frame, or None if the crop is invalid.
        """
        cam_height, cam_width, _ = frame.shape
        
        crop_w = cam_width / self.zoom_level
        crop_h = cam_height / self.zoom_level
        
        pan_range_x = (cam_width - crop_w) / 2
        pan_range_y = (cam_height - crop_h) / 2
        
        center_x = cam_width/2 + self.pan_x * pan_range_x
        center_y = cam_height/2 + self.pan_y * pan_range_y
        
        x1 = _snap_px(center_x - crop_w / 2)
        y1 = _snap_px(center_y - crop_h / 2)
        x2 = _snap_px(x1 + crop_w)
        y2 = _snap_px(y1 + crop_h)

        # Clamp coordinates to be within frame dimensions
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)

        if x2 > x1 and y2 > y1:
            return frame[y1:y2, x1:x2]
        return None

    def get_capture_region(self, frame):
        """
        Calculates the final high-resolution region inside the alignment box to be captured.
        Args:
            frame (numpy.ndarray): The full-resolution source frame.
        Returns:
            numpy.ndarray or None: The final cropped region for sending, or None if invalid.
        """
        zoomed_frame = self.get_zoomed_frame(frame)
        if zoomed_frame is None:
            return None

        zoomed_height, zoomed_width, _ = zoomed_frame.shape
        box_x1, box_y1, box_x2, box_y2 = self.get_box_coords(self.display_width, self.display_height)

        scale_x = zoomed_width / self.display_width
        scale_y = zoomed_height / self.display_height

        fx1 = _snap_px(box_x1 * scale_x)
        fy1 = _snap_px(box_y1 * scale_y)
        fx2 = _snap_px(box_x2 * scale_x)
        fy2 = _snap_px(box_y2 * scale_y)

        # Clamp entirely inside zoomed bounds; preserve at least 1px span for indexing.
        fx1 = max(0, min(fx1, max(0, zoomed_width - 1)))
        fy1 = max(0, min(fy1, max(0, zoomed_height - 1)))
        fx2 = max(fx1 + 1, min(fx2, zoomed_width))
        fy2 = max(fy1 + 1, min(fy2, zoomed_height))

        roi = zoomed_frame[fy1:fy2, fx1:fx2]
        h, w = roi.shape[:2]
        if h < MIN_CAPTURE_SIDE_PX or w < MIN_CAPTURE_SIDE_PX:
            return None
        return roi

    @staticmethod
    def get_box_coords(width, height):
        """
        Calculates the coordinates for the white alignment box based on a fixed scale.
        Args:
            width (int): The width of the area to draw the box in.
            height (int): The height of the area to draw the box in.
        Returns:
            tuple: A tuple (x1, y1, x2, y2) for the box.
        """
        box_w, box_h = width * BOX_SCALE, height * BOX_SCALE
        center_x, center_y = width / 2, height / 2
        return int(center_x - box_w/2), int(center_y - box_h/2), int(center_x + box_w/2), int(center_y + box_h/2)
