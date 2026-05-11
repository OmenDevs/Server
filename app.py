import ssl
import socket
import os
import json
import platform
import sys

from dotenv import load_dotenv

# Load environment variables from the .env
load_dotenv(override=True)

# Force CycloneDDS to Domain 0 on the chosen interface (default wlan0 for the linux;
# override with en0 when running on macOS).
_dds_iface = os.getenv("CYCLONEDDS_NETWORK_INTERFACE", "wlan0")
os.environ["CYCLONEDDS_URI"] = (
    f'<CycloneDDS><Domain id="0"><General>'
    f'<NetworkInterfaceAddress>{_dds_iface}</NetworkInterfaceAddress>'
    f'</General></Domain></CycloneDDS>'
)

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRecorder
from rich.console import Console


# --- CycloneDDS Imports ---
from dataclasses import dataclass
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.topic import Topic
from cyclonedds.idl import IdlStruct
from cyclonedds.idl.types import float32

try:
    from realsense_track import RealSenseTrack
    REALSENSE_AVAILABLE = True
except Exception:
    REALSENSE_AVAILABLE = False

# Create the web application with aiohttp
app = web.Application()
# Configure the console for printing messages
console = Console()

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(ROOT, 'recordings')
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Config from .env
SERVER_HOST        = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT        = int(os.getenv("SERVER_PORT", "8000"))
CAMERA_SOURCE      = os.getenv("CAMERA_SOURCE", "0")
CAMERA_FRAMERATE   = os.getenv("CAMERA_FRAMERATE", "30")
CAMERA_RESOLUTION  = os.getenv("CAMERA_RESOLUTION", "1280x720")
ENABLE_RECORDING   = os.getenv("ENABLE_RECORDING", "false").lower() == "true"
CERT_FILE          = os.getenv("CERT_FILE", os.path.join(ROOT, "cert.pem"))
KEY_FILE           = os.getenv("KEY_FILE", os.path.join(ROOT, "key.pem"))

# Active peer connections dictionary for managing multiple clients.
active_connections = {}


# DDS velocity command structure published to the robot.
@dataclass
class VelocityCommand(IdlStruct, typename="VelocityCommand"):
    vx: float32
    vy: float32
    omega: float32


console.log("Initializing CycloneDDS...")
try:
    dds_dp = DomainParticipant(0)
    dds_topic = Topic(dds_dp, "VelocityTopic", VelocityCommand)
    dds_writer = DataWriter(dds_dp, dds_topic)
    console.log("✅ CycloneDDS Publisher Ready")
except Exception as e:
    console.log(f"❌ Failed to initialize CycloneDDS: {e}")
    sys.exit(1)


def stop_robot_dds():
    """Publish a zero-velocity command so the robot halts safely."""
    try:
        dds_writer.write(VelocityCommand(vx=0.0, vy=0.0, omega=0.0))
        console.log("🛑 Robot safely stopped via DDS.")
    except Exception as e:
        console.log(f"⚠️ Failed to send DDS stop command: {e}")

def get_camera_track():
    """Returns a video track from the robot camera."""
    if REALSENSE_AVAILABLE:
        try:
            track = RealSenseTrack()
            console.log("🎥 Camera track created using RealSense pipeline")
            return track
        except Exception as e:
            console.log(f"⚠️ RealSense initialization failed: {e}. Falling back to MediaPlayer.")

    if platform.system() == "Darwin":
        # macOS: avfoundation — "0:none" = video device 0, no audio
        player = MediaPlayer(
            f"{CAMERA_SOURCE}:none",
            format="avfoundation",
            options={"framerate": CAMERA_FRAMERATE, "video_size": CAMERA_RESOLUTION},
        )
    else:
        # Linux (robot): v4l2
        player = MediaPlayer(
            f"/dev/video{CAMERA_SOURCE}",
            format="v4l2",
            options={"framerate": CAMERA_FRAMERATE, "video_size": CAMERA_RESOLUTION},
        )
    console.log(f"🎥 Camera track created from source: {CAMERA_SOURCE}")
    return player.video


async def home(request):
    """For serving the main HTML page"""
    return web.FileResponse('static/index.html')


async def offer(request):
    """
    WebRTC signaling endpoint.
    Vision Pro sends SDP offer → server replies with SDP answer
    and streams the robot camera to it.
    """

    # Retrives the parameters from the request
    params = await request.json()
    offer_sdp = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"],
    )

    pc = RTCPeerConnection()
    pc_id = f"pc_{id(pc)}"
    active_connections[pc_id] = pc

    pc.recorder = MediaRecorder(f"{OUTPUT_DIR}/{pc_id}.mp4", format='mp4') if ENABLE_RECORDING else None

    console.log(f"🔗 New connection: {pc_id}")

    # Add camera track 
    video_track_active = False
    try:
        video_track = get_camera_track()
        pc.addTrack(video_track)
        video_track_active = True
        if pc.recorder:
            pc.recorder.addTrack(video_track)
        console.log("📹 Camera track added")

        @video_track.on("ended")
        async def on_video_ended():
            nonlocal video_track_active
            video_track_active = False
            console.log("🔴 Video track ended")
            if pc.recorder:
                await pc.recorder.stop()
                pc.recorder = None
                console.log(f"🎥 Recording saved: {OUTPUT_DIR}/{pc_id}.mp4")
    except Exception as e:
        console.log(f"❌ Could not open camera: {e}")
        # Fallback: test pattern so connection can still be verified
        player = MediaPlayer("testsrc=size=1280x720:rate=30", format="lavfi")
        pc.addTrack(player.video)
        console.log("⚠️  Using test pattern instead of real camera")

    # This event is triggered when a data channel is created by the client. 
    @pc.on("datachannel")
    def on_datachannel(channel):
        console.log(f"📡 Data channel opened: {channel.label}")
        channel.send(f"🎉 Connected! Session: {pc_id}")

        # This event is triggered when a message is received on the data channel.
        @channel.on("message")
        def on_message(message):
            if not video_track_active:
                console.log("⚠️ Command rejected — video stream not active")
                channel.send("⚠️ Cannot send commands without active video")
                return

            try:
                cmd = json.loads(message)
                if all(k in cmd for k in ("vx", "vy", "omega")):
                    dds_writer.write(VelocityCommand(
                        vx=float(cmd["vx"]),
                        vy=float(cmd["vy"]),
                        omega=float(cmd["omega"]),
                    ))
                    return
                console.log(f"📩 Unrecognized JSON format: {cmd}")
            except json.JSONDecodeError:
                console.log(f"📩 Raw Text Command: {message}")
                channel.send(f"📢 Echo: {message}")
        
        # This events are triggered when the data channel is closed/error.
        def on_data_channel_issue(reason: str):
            console.log(f"⚠️ Data channel issue: {reason}")
            console.log(f"🗑️ Eliminating {pc_id} from active connections")
            stop_robot_dds()
            active_connections.pop(pc_id, None)
            console.log(f"📊 Active connections: {len(active_connections)}")
        @channel.on('close')
        def on_data_channel_close():
            on_data_channel_issue("🔴 closed")
        @channel.on('error')
        def on_data_channel_error(error):
            on_data_channel_issue(f"❌ error: {error}")

    # This event is triggered when the connection state changes.
    @pc.on("connectionstatechange")
    async def on_connection_state_change():
        console.log(f"🔄 State: {pc.connectionState}")
        if pc.connectionState in ("failed", "closed", "disconnected"):
            nonlocal video_track_active
            if hasattr(pc, 'recorder') and pc.recorder and video_track_active:
                try:
                    await pc.recorder.stop()
                except Exception as e:
                    console.log(f"⚠️ Error stopping recorder: {e}")
            video_track_active = False
            await pc.close()
            stop_robot_dds()
            active_connections.pop(pc_id, None)
            console.log(f"🗑️  Removed {pc_id}. Active: {len(active_connections)}")

    # SDP negotiation
    await pc.setRemoteDescription(offer_sdp)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    console.log(f"✅ SDP answer sent to {pc_id}")
    if video_track_active and pc.recorder:
        await pc.recorder.start()
        console.log(f"🎥 Recording started for {pc_id}")

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        }),
    )


async def stop(request):
    """Endpoint to stop the recording and clean up active peer resources."""
    data = await request.json()
    pc_id = data.get("connectionId")
    pc = active_connections.get(pc_id)
    if pc:
        #Stop the recorder if it exists.
        if hasattr(pc, 'recorder') and pc.recorder: 
            try:
                await pc.recorder.stop()
            except Exception as e:
                console.log(f"⚠️ Error stopping recorder: {e}")
        # Close the peer connection.
        try: 
            await pc.close()
            console.log(f"✅ Closed {pc_id}")
        except Exception as e:
            console.log(f"⚠️ Error closing peer connection {pc_id}: {e}")

        stop_robot_dds()
        active_connections.pop(pc_id, None)

        return web.Response(text="ok")
    return web.Response(status=404, text="not found")


def get_private_ip():
    """Gets the private IP address for network connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        console.log(f"❌ Error getting private IP address: {e}")
        return "unavailable"


def build_ssl_context():
    """Load SSL cert/key. Exits with instructions if missing."""
    if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
        console.log("❌ SSL certificates not found! Check README for instructions.")
        raise FileNotFoundError("Missing cert.pem / key.pem")
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    return ctx

app.router.add_static('/static/', os.path.join(ROOT, 'static'), show_index=True) 
app.router.add_get("/", home)
app.router.add_post("/offer", offer)
app.router.add_post("/stop", stop)

if __name__ == "__main__":
    # Obtain the IP of the private network
    private_ip = get_private_ip()
    ssl_context = build_ssl_context()

    console.log("🚀 Robot Camera Server starting...")
    console.log("=" * 55)
    console.log(f"🏠 Local:    https://localhost:{SERVER_PORT}")
    console.log(f"🌐 Network:  https://{private_ip}:{SERVER_PORT}")
    console.log("=" * 55)
    console.log(f"📹 Camera source: {CAMERA_SOURCE}  |  {CAMERA_RESOLUTION} @ {CAMERA_FRAMERATE}fps")
    console.log(f"🎥 Recording: {'enabled' if ENABLE_RECORDING else 'disabled'}")
    console.log("📱 Use the Network URL in your Vision Pro app")
    console.log("=" * 55)

    web.run_app(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        ssl_context=ssl_context,
    )