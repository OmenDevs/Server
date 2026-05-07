
## This is a Debug file to test the RealSense camera
## use given command on terminal to test
## sudo PYTHONPATH=./librealsense/build/Release \
## python3 ./Server/viewer.py

import sys
import os

# Add local librealsense build path to find pyrealsense2
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "librealsense", "build", "Release")))

import pyrealsense2 as rs
import numpy as np
import cv2

def main():
    print("Which stream do you want to view?")
    print("  1 - Color (RGB)")
    print("  2 - Depth")
    print("  3 - Infrared")
    choice = input("Enter 1, 2, or 3: ").strip()

    pipeline = rs.pipeline()
    config = rs.config()

    if choice == "1":
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        stream_name = "Color"
    elif choice == "2":
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        stream_name = "Depth"
    elif choice == "3":
        config.enable_stream(rs.stream.infrared, 640, 480, rs.format.y8, 30)
        stream_name = "Infrared"
    else:
        print("Invalid choice.")
        sys.exit(1)

    pipeline.start(config)
    print(f"\nOpening {stream_name} stream... Press Q to quit.\n")

    try:
        while True:
            frames = pipeline.wait_for_frames()

            if choice == "1":
                frame = frames.get_color_frame()
                if not frame:
                    continue
                image = np.asanyarray(frame.get_data())
            elif choice == "2":
                frame = frames.get_depth_frame()
                if not frame:
                    continue
                colorizer = rs.colorizer()
                colorized = colorizer.colorize(frame)
                image = np.asanyarray(colorized.get_data())
            elif choice == "3":
                frame = frames.get_infrared_frame()
                if not frame:
                    continue
                image = np.asanyarray(frame.get_data())

            cv2.imshow(stream_name, image)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()