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
    """A WebRTC video track that streams color frames from a RealSense D435i."""

    def __init__(self):
        super().__init__()
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        self.pipeline.start(config)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        loop = asyncio.get_event_loop()
        try:
            frames = await loop.run_in_executor(None, self.pipeline.wait_for_frames)
        except Exception as e:
            print(f"⚠️ RealSense wait_for_frames error: {e}")
            return self._empty_frame(pts, time_base)

        frame = frames.get_color_frame()
        if not frame:
            return self._empty_frame(pts, time_base)

        # RealSense gives BGR, av expects RGB
        image = cv2.cvtColor(np.asanyarray(frame.get_data()), cv2.COLOR_BGR2RGB)
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

    def _empty_frame(self, pts, time_base):
        """Return a black frame as a safe fallback."""
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame
