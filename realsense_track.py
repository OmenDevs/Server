import asyncio
import sys
import os
import threading

import numpy as np
import cv2
import av

from aiortc import VideoStreamTrack

# Add local librealsense build path to find pyrealsense2
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "librealsense", "build", "Release")))

import pyrealsense2 as rs


class RealSenseTrack(VideoStreamTrack):
    """A WebRTC video track that streams color frames from a RealSense D435i.

    Capture runs on a background thread into a single-slot buffer, so `recv()`
    always hands WebRTC the most recent frame. If the encoder or network briefly
    falls behind, older frames are overwritten in place instead of piling up in
    the librealsense queue — preventing multi-second video lag.
    """

    def __init__(self):
        super().__init__()
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        self.pipeline.start(config)

        self._latest_lock = threading.Lock()
        self._latest_image = None
        self._frame_ready = threading.Event()
        self._stop_capture = threading.Event()
        self._capture_thread = threading.Thread(
            target=self._capture_loop, name="RealSenseCapture", daemon=True
        )
        self._capture_thread.start()

    def _capture_loop(self):
        # Drain the camera as fast as it produces frames so librealsense's
        # internal queue never holds anything older than ~1 frame.
        while not self._stop_capture.is_set():
            try:
                frames = self.pipeline.wait_for_frames()
            except Exception as e:
                print(f"⚠️ RealSense wait_for_frames error: {e}")
                continue
            color = frames.get_color_frame()
            if not color:
                continue
            image = cv2.cvtColor(np.asanyarray(color.get_data()), cv2.COLOR_BGR2RGB)
            with self._latest_lock:
                self._latest_image = image
            self._frame_ready.set()

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        # Block only on the very first frame; after that the slot is always populated.
        if not self._frame_ready.is_set():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._frame_ready.wait)

        with self._latest_lock:
            image = self._latest_image

        if image is None:
            return self._empty_frame(pts, time_base)

        video_frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self):
        super().stop()
        self._stop_capture.set()
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
