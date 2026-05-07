# Locomotion — Robot Camera Server 🤖

WebRTC server that streams a RealSense D435i camera to an iOS/visionOS client, with real-time depth, color, and infrared stream switching.

## Requirements

- Python 3.9+
- Intel RealSense D435i camera
- [librealsense](https://github.com/IntelRealSense/librealsense) built locally **or** `pyrealsense2` installed via pip (Ubuntu)

---

## Setup

### 1. Configure the RealSense backend

**macOS** — Install prerequisites and build `librealsense` locally:

1. Install prerequisites:
   ```bash
   xcode-select --install
   brew install cmake libusb pkg-config openssl
   ```

2. Clone and build `librealsense` inside the project folder:
   ```bash
   cd Locomotion
   git clone https://github.com/realsenseai/librealsense.git
   cd librealsense
   mkdir build && cd build
   cmake .. \
     -DBUILD_EXAMPLES=true \
     -DBUILD_GRAPHICAL_EXAMPLES=true \
     -DFORCE_RSUSB_BACKEND=ON \
     -DBUILD_PYTHON_BINDINGS=ON \
     -DPYTHON_EXECUTABLE=$(which python3)
   make -j2
   ```

**Ubuntu** — Install via pip (no local build needed):
```bash
pip install pyrealsense2
# Install udev rules (one-time):
sudo cp librealsense/config/99-realsense-libusb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 2. Install Python Server dependencies

```bash
cd Locomotion/Server
pip3 install -r requirements.txt
```

### 3. Generate SSL certificates

WebRTC requires HTTPS. Generate self-signed certs (development only):

```bash
cd Server
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

### 4. Configure the environment

Copy the example file and edit as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `SERVER_HOST` | `0.0.0.0` | Bind address. Set to the robot's Ethernet IP when testing over cable |
| `SERVER_PORT` | `8000` | Port the server listens on |
| `CAMERA_SOURCE` | `0` | Camera device index |
| `CAMERA_FRAMERATE` | `30` | Stream frame rate |
| `CAMERA_RESOLUTION` | `1280x720` | Stream resolution |
| `ENABLE_RECORDING` | `false` | Set to `true` to save sessions to `recordings/` |

---

### 5. Run the server

```bash
sudo python3 Server/app.py   # macOS
python3 Server/app.py        # Ubuntu (after udev rules)
```

The server prints its local and network URLs on startup. Use the **Network URL** in the iOS app.

---

## Stream Switching

The client can switch streams in real time over the WebRTC data channel:

| Command | Stream |
|---|---|
| `stream:color` | RGB color (default) |
| `stream:depth` | Colorized depth map |
| `stream:infrared` | Infrared (grayscale) |

---

## Fallback

If the RealSense camera is not connected, the server automatically falls back to a regular webcam via `MediaPlayer`. Stream switching commands will have no effect in fallback mode.

---

## Files

| File | Description |
|---|---|
| `app.py` | WebRTC signaling server, HTTP routes, startup |
| `realsense_track.py` | RealSense camera pipeline and stream switching |
| `viewer.py` | Local debug tool — preview streams without WebRTC |
| `requirements.txt` | Python dependencies |
