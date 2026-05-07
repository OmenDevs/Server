import asyncio
import sys
import os

import numpy as np
import cv2
import av

from aiortc import VideoStreamTrack

# Add local librealsense build path to find pyrealsense2
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "librealsense", "build", "Release")))

import pyrealsense2 as rs


class RealSenseTrack(VideoStreamTrack):
    """
    A WebRTC video track that reads frames from a RealSense D435i camera.

    Enables color, depth, and infrared streams simultaneously so switching
    between them is instant — no pipeline restart needed.

    Usage:
        track = RealSenseTrack()
        track.set_stream("depth")   # "color" | "depth" | "infrared"
    """

    VALID_STREAMS = ("color", "depth", "infrared")

    def __init__(self):
        super().__init__()
        self.pipeline = rs.pipeline()
        config = rs.config()

        # Enable all three streams upfront for instant switching
        config.enable_stream(rs.stream.color,    640, 480, rs.format.bgr8, 30)
        config.enable_stream(rs.stream.depth,    640, 480, rs.format.z16,  30)
        config.enable_stream(rs.stream.infrared, 640, 480, rs.format.y8,   30)

        self.pipeline.start(config)
        self.active_stream = "color"
        self.colorizer = rs.colorizer()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_stream(self, stream_type: str):
        """Switch the active camera stream. Silently ignores unknown types."""
        if stream_type in self.VALID_STREAMS:
            self.active_stream = stream_type

    # ── aiortc VideoStreamTrack protocol ─────────────────────────────────────

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        loop = asyncio.get_event_loop()
        try:
            frames = await loop.run_in_executor(None, self.pipeline.wait_for_frames)
        except Exception as e:
            print(f"⚠️ RealSense wait_for_frames error: {e}")
            return self._empty_frame(pts, time_base)

        image = self._extract_image(frames)
        if image is None:
            return self._empty_frame(pts, time_base)

        video_frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self):
        super().stop()
        try:
            self.pipeline.stop()
        except Exception:
            pass

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_image(self, frames):
        """Extract and convert the active stream frame to an RGB numpy array."""
        if self.active_stream == "color":
            frame = frames.get_color_frame()
            if not frame:
                return None
            # RealSense gives BGR, av expects RGB
            return cv2.cvtColor(np.asanyarray(frame.get_data()), cv2.COLOR_BGR2RGB)

        elif self.active_stream == "depth":
            frame = frames.get_depth_frame()
            if not frame:
                return None
            # Colorizer output is already RGB
            return np.asanyarray(self.colorizer.colorize(frame).get_data())

        elif self.active_stream == "infrared":
            frame = frames.get_infrared_frame()
            if not frame:
                return None
            # Y8 grayscale → RGB
            return cv2.cvtColor(np.asanyarray(frame.get_data()), cv2.COLOR_GRAY2RGB)

        return None

    def _empty_frame(self, pts, time_base):
        """Return a black frame as a safe fallback."""
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame
