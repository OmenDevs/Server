// Global variables to store the data channel and peer connection
var peerConnection = null;
var connectionId = null;
var dataChannel = null;;

// Gesture analysis state
var gestureAnalysisActive = false;

// Function to show the connection status badge
function showConnectionBadge(id) {
    connectionId = id;

    // Remove existing badge if it exists
    const existingBadge = document.getElementById("connection-badge");
    if (existingBadge) {
        existingBadge.remove();
    }

    // Create the badge
    const badge = document.createElement("div");
    badge.id = "connection-badge";
    badge.innerHTML = `🆔 ${id}`;

    // Add the badge to the body so it floats
    document.body.appendChild(badge);
}

// Function to show the "Connecting..." status
function showConnectingBadge() {
    // Remove existing badge if it exists
    const existingBadge = document.getElementById("connection-badge");
    if (existingBadge) {
        existingBadge.remove();
    }

    // Create the connecting badge
    const badge = document.createElement("div");
    badge.id = "connection-badge";
    badge.innerHTML = `⏳ Connecting...`;
    badge.classList.add("connecting");

    /// Add the badge to the body so it floats
    document.body.appendChild(badge);
}

// Function to update the badge to connected
function updateBadgeToConnected(id) {
    const existingBadge = document.getElementById("connection-badge");
    if (existingBadge) {
        existingBadge.innerHTML = `🆔 ${id}`;
        existingBadge.classList.remove("connecting");
        existingBadge.classList.add("connected");
    }
}


// Log function to print pretty messages to the console 
function log(message, object) {
    const logElement = document.getElementById("log");
    const timestamp = new Date().toLocaleTimeString();

    let objectHtml = '';
    if (object) {
        if (typeof object === 'string') {
            objectHtml = `<span class="log-string">"${object}"</span>`;
        } else if (typeof object === 'object') {
            objectHtml = `<pre class="log-object">${JSON.stringify(object, null, 2)}</pre>`;
        } else {
            objectHtml = `<span class="log-value">${object}</span>`;
        }
    }

    logElement.innerHTML += `
        <div class="log-entry">
            <span class="log-timestamp">${timestamp}</span>
            <span class="log-message">${message}</span>
            ${objectHtml}
        </div>
    `;

    // Auto-scroll to the bottom
    logElement.scrollTop = logElement.scrollHeight;
    console.log(message, object);
}


// Function to send messages through the data channel
function sendMessage(message) {
    const channel = dataChannel;
    const sendButton = document.getElementById("send");
    if (channel && channel.readyState === 'open' && !sendButton.disabled) {
        channel.send(message);
        log("📤 Message sent:", message);
    } else {
        log("⚠️ The data channel is not open or the button is disabled");
    }
}

// Send the message typed in the input with id "message" when the button with id "send" is clicked
document.getElementById("send").addEventListener("click", () => {
    const messageInput = document.getElementById("message");
    const message = messageInput.value;
    messageInput.value = ""; // Clear the input after sending the message
    sendMessage(message);
});

// Send the message typed in the input with id "message" when the Enter key is pressed
document.getElementById("message").addEventListener("keypress", (event) => {
    if (event.key === "Enter") {
        const messageInput = document.getElementById("message");
        const message = messageInput.value;
        sendMessage(message);
        messageInput.value = ""; // Clear the input after sending the message
    }
});

async function createPeerConnection() {
    //1. Create the RTCPeerConnection and the data channel
    log("🚀 Starting WebRTC connection");
    peerConnection = new RTCPeerConnection({
        iceServers: [
            { urls: "stun:stun.l.google.com:19302" } // This allows us to use a public Google STUN server.
            // The STUN server helps browsers discover their public IP address and the port they should use to communicate with each other.
        ]
    });
    peerConnection.addTransceiver('video', { direction: 'recvonly' });
    log("🔗 RTCPeerConnection created");
    // Request access to camera and microphone
    log("🎥 Requesting camera and microphone access...");
    // Configure the event to receive remote streams
    peerConnection.ontrack = (event) => {
        log("📺 Remote stream received");
        const remoteVideo = document.getElementById("remoteVideo");
        remoteVideo.srcObject = event.streams[0];
    };
    // Create the data channel to send messages
    log("📡 Creating data channel to send messages");
    dataChannel = peerConnection.createDataChannel("chat");
    // Configure the onopen event of the data channel
    dataChannel.onopen = () => {
        log("🟢 Data channel open");
        // Enable the send button when the channel is open
        document.getElementById("send").disabled = false;
    };
    // Configure the onmessage event of the data channel
    dataChannel.onmessage = (event) => {
        const message = event.data;
        console.log("🔍 DEBUG: Message received:", message); // DEBUG LOG
        // Distinguish between different types of server messages
        if (message.includes("Connected")) {
            log("👋 Welcome message:", message);
            const connectionIdReceived = message.split("Session: ")[1];
            connectionId = connectionIdReceived;
            updateBadgeToConnected(connectionIdReceived);
        } else if (message.includes("Echo:")) {
            log("📢 Server echo:", message);
        } else if (message.includes("Switched to")) {
            log("🎥 Stream switched:", message);
        } else if (message.includes("⚠️")) {
            log("⚠️ Warning:", message);
        } else {
            log("📥 Message received:", message);
        }
    };
    // Configure the onclose event of the data channel
    dataChannel.onclose = () => {
        log("🔴 Data channel closed");
        // Disable the send button when the channel closes
        document.getElementById("send").disabled = true;
    };
    // Configure the oniceconnectionstatechange event to handle changes in the ICE connection state
    peerConnection.oniceconnectionstatechange = (event) => {
        log("🧊 ICE state:", peerConnection.iceConnectionState);
    };
}

// Negotiate the WebRTC connection with the server
async function negotiate() {
    try {
        log("🤝 An offer will be created to initiate the WebRTC connection");
        const offer = await peerConnection.createOffer();
        log("📝 Offer created:", offer);
        await peerConnection.setLocalDescription(offer);
        // Promise that waits for the ICE candidates to be collected
        // This is important to ensure that all ICE candidates have been collected before sending the offer to the server.
        // ICE candidates are necessary to establish the connection between peers.
        // They can be local or remote, and are used to find the best communication route between peers.
        // log("⏳ Waiting for all ICE candidates to be collected...");
        // await new Promise((resolve) => {
        //     peerConnection.onicecandidate = (event) => {
        //         if (event.candidate === null) {
        //             log("✅ All ICE candidates have been collected");
        //             resolve();
        //         } else {
        //             log(`🥇 New ICE candidate of type: ${event.candidate.type}`, event.candidate);
        //         }
        //     };
        // });
        //Send the offer to the server to establish the connection
        const response = await fetch("/offer", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ sdp: peerConnection.localDescription.sdp, type: peerConnection.localDescription.type })
        });
        log("⏳ Offer sent to the server, waiting for response...");
        const answer = await response.json();
        log("📬 Response received from the server:", answer);
        log("📜 Configuring the remote description with the server's response");
        // What this does is configure the remote description of the peer connection with the server's response.
        // The goal is to establish the WebRTC connection between peers. This indicates how we will communicate with the other end.
        await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
        log("🎉 WebRTC connection successfully negotiated");
    } catch (error) {
        log("❌ Error negotiating the WebRTC connection:", error);
    }
}

// This function is executed when the "Start connection" button is clicked
let sessionActive = false;
let localStream = null;

async function start() {
    // Show connecting badge from the start
    showConnectingBadge();
    await createPeerConnection();
    await negotiate();
    sessionActive = true;
    updateStartButton();
}

async function stopSession() {
    log("🛑 Closing session and recording...");
    // Notify the server to stop the recording
    try {
        await fetch("/stop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ connectionId })
        });
        log("📡 Stop notice sent to the server");
    } catch (e) {
        log("⚠️ Could not notify the server to stop the recording", e);
    }
    if (peerConnection) {
        peerConnection.getSenders().forEach(sender => {
            if (sender.track) sender.track.stop();
        });
        peerConnection.close();
        peerConnection = null;
    }
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }
    document.getElementById("localVideo").srcObject = null;
    document.getElementById("remoteVideo").srcObject = null;
    sessionActive = false;
    updateStartButton();
    log("✅ Session ended and resources released.");
}

function updateStartButton() {
    const startButton = document.getElementById("start");
    if (sessionActive) {
        startButton.textContent = "Stop session 🛑";
        startButton.onclick = stopSession;
    } else {
        startButton.textContent = "Start connection 🚀";
        startButton.onclick = start;
    }
}


window.addEventListener("load", async () => {
    //await init();
    updateStartButton();
});