from flask import Flask, request, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
import time
from datetime import datetime
import uuid

# --- CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

# Async mode 'eventlet' is best for performance, 'threading' is fine for local testing
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- IN-MEMORY STORAGE ---
# structure: { session_id: { 'username': str, 'room': str, 'id': str } }
USERS = {}
HISTORY = []

@app.route("/")
def index():
    return render_template_string(frontend_code)

# --- SOCKET.IO EVENTS (The Real-Time Protocol) ---

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    user = USERS.get(request.sid)
    if user:
        # Notify others that user left (for Voice and Chat)
        username = user['username']
        emit('user_left', {'sid': request.sid, 'username': username}, broadcast=True)
        
        # Add system message
        sys_msg = {
            'type': 'system',
            'text': f"❌ {username} disconnected",
            'time': datetime.now().strftime("%H:%M")
        }
        emit('message', sys_msg, broadcast=True)
        del USERS[request.sid]

@socketio.on('register')
def handle_register(data):
    username = data.get('username')
    # Store user session
    USERS[request.sid] = {
        'username': username,
        'id': request.sid,
        'mute': False
    }
    
    # Send history to new user
    emit('history', HISTORY)
    
    # Broadcast join to others
    emit('user_joined', {'sid': request.sid, 'username': username}, broadcast=True)
    
    # System message
    sys_msg = {
        'type': 'system',
        'text': f"👋 {username} landed in the server",
        'time': datetime.now().strftime("%H:%M")
    }
    HISTORY.append(sys_msg)
    emit('message', sys_msg, broadcast=True)
    
    # Send updated user list
    update_user_list()

@socketio.on('chat_message')
def handle_message(data):
    user = USERS.get(request.sid)
    if user:
        msg = {
            'type': 'chat',
            'sender': user['username'],
            'text': data['msg'],
            'sid': request.sid, # used for styling self vs others
            'time': datetime.now().strftime("%H:%M")
        }
        HISTORY.append(msg)
        # Keep history limited to 50 messages to save memory
        if len(HISTORY) > 50:
            HISTORY.pop(0)
        emit('message', msg, broadcast=True)

# --- WEBRTC SIGNALING (The Voice Protocol) ---
# WebRTC requires a "Signal Channel" to exchange connection info.
# We use Socket.IO as that channel.

@socketio.on('voice_signal')
def handle_voice_signal(data):
    """
    Relays WebRTC signals (Offers, Answers, ICE Candidates) 
    between peers.
    target_sid: The specific user we want to connect to.
    """
    target_sid = data.get('target')
    if target_sid in USERS:
        # Forward the data to the specific target, tagging who sent it
        emit('voice_signal', {
            'sender_sid': request.sid,
            'type': data['type'],
            'payload': data['payload']
        }, room=target_sid)

def update_user_list():
    # Convert dict to list for frontend
    user_list = [{'sid': k, 'username': v['username']} for k, v in USERS.items()]
    emit('update_users', user_list, broadcast=True)

# --- FRONTEND CODE (Embedded for single-file convenience) ---
frontend_code = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Clone (WebRTC)</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        :root {
            --bg-tertiary: #202225;
            --bg-secondary: #2f3136;
            --bg-primary: #36393f;
            --text-normal: #dcddde;
            --text-muted: #72767d;
            --header-primary: #fff;
            --interactive-normal: #b9bbbe;
            --interactive-hover: #dcddde;
            --brand-experiment: #5865f2;
            --brand-hover: #4752c4;
            --green: #3ba55c;
            --red: #ed4245;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'gg sans', 'Segoe UI', Tahoma, sans-serif; background: var(--bg-primary); color: var(--text-normal); height: 100vh; display: flex; overflow: hidden; }

        /* Sidebar (Users + Voice) */
        .sidebar { width: 240px; background: var(--bg-secondary); display: flex; flex-direction: column; }
        
        .voice-panel {
            background: var(--bg-tertiary);
            padding: 10px;
            border-bottom: 1px solid #202225;
        }
        
        .voice-status {
            display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 10px;
        }
        
        .connection-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); margin-right: 8px; }
        .connection-dot.connected { background: var(--green); box-shadow: 0 0 8px var(--green); }
        
        .controls { display: flex; gap: 5px; }
        .btn-icon {
            background: transparent; border: none; color: var(--interactive-normal); cursor: pointer; padding: 5px; border-radius: 4px;
        }
        .btn-icon:hover { background: rgba(255,255,255,0.1); }
        .btn-icon.active { color: var(--red); }

        .user-list-container { flex: 1; padding: 10px; overflow-y: auto; }
        .user-list-header { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 10px; }
        
        .user-item { display: flex; align-items: center; padding: 8px; border-radius: 4px; margin-bottom: 2px; cursor: pointer; }
        .user-item:hover { background: rgba(79, 84, 92, 0.32); }
        .avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--brand-experiment); display: flex; align-items: center; justify-content: center; margin-right: 10px; font-weight: bold; color: white; position: relative; }
        
        /* Speaking Indicator */
        .speaking-ring {
            position: absolute; top: -2px; left: -2px; right: -2px; bottom: -2px;
            border-radius: 50%; border: 2px solid var(--green);
            opacity: 0; transition: opacity 0.1s;
        }

        /* Main Chat */
        .main { flex: 1; display: flex; flex-direction: column; background: var(--bg-primary); }
        .chat-header { height: 48px; border-bottom: 1px solid #26272d; display: flex; align-items: center; padding: 0 16px; box-shadow: 0 1px 0 rgba(4,4,5,0.02); }
        .chat-area { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        
        /* Messages */
        .message { display: flex; gap: 16px; margin-top: 5px; animation: fadeIn 0.2s; }
        .message:hover { background: rgba(4,4,5,0.07); }
        .msg-content { display: flex; flex-direction: column; }
        .msg-header { display: flex; align-items: baseline; gap: 8px; }
        .username { font-weight: 500; color: var(--header-primary); cursor: pointer; }
        .username:hover { text-decoration: underline; }
        .timestamp { font-size: 0.75rem; color: var(--text-muted); }
        .text { color: var(--text-normal); font-size: 1rem; line-height: 1.375rem; white-space: pre-wrap; word-wrap: break-word; }
        
        .system-msg { color: var(--text-muted); font-size: 0.9rem; text-align: center; margin: 10px 0; font-style: italic; display: flex; align-items: center; justify-content: center; gap: 10px; }
        .system-msg::before, .system-msg::after { content: ""; height: 1px; background: #4f545c; flex: 1; opacity: 0.3; }

        /* Input */
        .input-area { padding: 0 16px 24px; }
        .input-wrapper { background: #40444b; border-radius: 8px; padding: 11px; display: flex; }
        .msg-input { background: transparent; border: none; color: var(--text-normal); width: 100%; outline: none; font-size: 1rem; }

        /* Modal */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 1000; }
        .modal { background: var(--bg-primary); padding: 30px; border-radius: 5px; width: 400px; text-align: center; box-shadow: 0 0 15px rgba(0,0,0,0.5); }
        .modal input { width: 100%; padding: 10px; background: var(--bg-tertiary); border: 1px solid #202225; color: white; border-radius: 3px; margin-bottom: 20px; outline: none; }
        .btn-join { background: var(--brand-experiment); color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; width: 100%; font-weight: 600; }
        .btn-join:hover { background: var(--brand-hover); }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>

<div class="modal-overlay" id="loginModal">
    <div class="modal">
        <h2 style="color: white; margin-bottom: 20px;">Welcome to DisClone</h2>
        <input type="text" id="username" placeholder="Enter a username">
        <button class="btn-join" onclick="joinServer()">Join Server</button>
    </div>
</div>

<div class="sidebar">
    <div class="voice-panel">
        <div class="voice-status">
            <div style="display:flex; align-items:center;">
                <div class="connection-dot" id="voiceDot"></div>
                <span style="font-size: 12px; font-weight: 700;">Voice Connected</span>
            </div>
        </div>
        <div class="controls">
            <button class="btn-icon" id="micBtn" onclick="toggleMic()">🎤</button>
            <button class="btn-icon" id="deafenBtn" onclick="toggleDeafen()">🎧</button>
        </div>
    </div>
    
    <div class="user-list-container">
        <div class="user-list-header">Online Users</div>
        <div id="userList"></div>
    </div>
</div>

<div class="main">
    <div class="chat-header">
        <span style="font-weight: bold; font-size: 16px;"># general</span>
    </div>
    <div class="chat-area" id="chatArea"></div>
    <div class="input-area">
        <div class="input-wrapper">
            <input type="text" class="msg-input" id="msgInput" placeholder="Message #general" autocomplete="off">
        </div>
    </div>
</div>

<script>
    const socket = io();
    let myUsername = "";
    let localStream;
    let peers = {}; // Keep track of WebRTC connections: { sid: RTCPeerConnection }
    let isMuted = false;
    
    // --- WEBRTC CONFIGURATION ---
    const rtcConfig = {
        iceServers: [
            { urls: "stun:stun.l.google.com:19302" } // Public STUN server to find IP
        ]
    };

    // --- JOIN LOGIC ---
    async function joinServer() {
        const input = document.getElementById('username');
        if(!input.value) return;
        myUsername = input.value;
        
        document.getElementById('loginModal').style.display = 'none';
        
        // 1. Get Microphone Access immediately
        try {
            localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            // By default, join muted to avoid feedback loops in testing
            localStream.getAudioTracks()[0].enabled = true; 
            document.getElementById('voiceDot').classList.add('connected');
        } catch (e) {
            console.error("Mic access denied", e);
            alert("Microphone access is required for voice chat!");
        }

        // 2. Register with Socket Server
        socket.emit('register', { username: myUsername });
    }

    // --- SOCKET.IO HANDLERS ---
    
    // 1. Chat & User Management
    socket.on('message', (msg) => {
        appendMessage(msg);
    });

    socket.on('history', (history) => {
        history.forEach(appendMessage);
        scrollToBottom();
    });

    socket.on('update_users', (users) => {
        const list = document.getElementById('userList');
        list.innerHTML = users.map(u => `
            <div class="user-item">
                <div class="avatar">
                    ${u.username[0].toUpperCase()}
                    <div class="speaking-ring" id="ring-${u.sid}"></div>
                </div>
                <div style="font-weight: 500; font-size: 14px;">${u.username} ${u.username === myUsername ? '(You)' : ''}</div>
            </div>
        `).join('');
    });

    // --- WEBRTC LOGIC (The Advanced Part) ---

    // A. New User Joined -> We initiate the call (Mesh Network)
    socket.on('user_joined', async (data) => {
        if(data.username === myUsername) return; // Don't call myself
        console.log("New user joined, initiating call to:", data.username);
        createPeerConnection(data.sid, true); // true = I am the initiator
    });

    // B. User Left -> Cleanup
    socket.on('user_left', (data) => {
        if(peers[data.sid]) {
            peers[data.sid].close();
            delete peers[data.sid];
            // Remove audio element
            const audio = document.getElementById(`audio-${data.sid}`);
            if(audio) audio.remove();
        }
    });

    // C. Handle Signals (Offer, Answer, ICE)
    socket.on('voice_signal', async (data) => {
        const senderSid = data.sender_sid;
        const type = data.type;
        const payload = data.payload;

        if (!peers[senderSid]) {
            // If I receive an offer but don't have a peer yet, create one (non-initiator)
            createPeerConnection(senderSid, false);
        }

        const pc = peers[senderSid];

        try {
            if (type === 'offer') {
                await pc.setRemoteDescription(new RTCSessionDescription(payload));
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                socket.emit('voice_signal', { target: senderSid, type: 'answer', payload: answer });
            } else if (type === 'answer') {
                await pc.setRemoteDescription(new RTCSessionDescription(payload));
            } else if (type === 'ice-candidate') {
                if(payload) {
                    await pc.addIceCandidate(new RTCIceCandidate(payload));
                }
            }
        } catch (e) {
            console.error("Signal Error", e);
        }
    });

    function createPeerConnection(targetSid, isInitiator) {
        const pc = new RTCPeerConnection(rtcConfig);
        peers[targetSid] = pc;

        // Add my local audio stream to the connection
        if (localStream) {
            localStream.getTracks().forEach(track => pc.addTrack(track, localStream));
        }

        // Handle ICE Candidates (Networking)
        pc.onicecandidate = (event) => {
            if (event.candidate) {
                socket.emit('voice_signal', { target: targetSid, type: 'ice-candidate', payload: event.candidate });
            }
        };

        // Handle Incoming Stream (When the other person speaks)
        pc.ontrack = (event) => {
            console.log("Received remote stream from", targetSid);
            let audio = document.getElementById(`audio-${targetSid}`);
            if (!audio) {
                audio = document.createElement('audio');
                audio.id = `audio-${targetSid}`;
                audio.autoplay = true;
                document.body.appendChild(audio);
            }
            audio.srcObject = event.streams[0];
            
            // Visualizer for speaking (Simple volume detection)
            monitorAudioLevel(event.streams[0], targetSid);
        };

        // If I am the initiator, I create the offer
        if (isInitiator) {
            pc.onnegotiationneeded = async () => {
                try {
                    const offer = await pc.createOffer();
                    await pc.setLocalDescription(offer);
                    socket.emit('voice_signal', { target: targetSid, type: 'offer', payload: offer });
                } catch (e) { console.error(e); }
            };
        }
    }

    // --- UI HELPERS ---

    function monitorAudioLevel(stream, sid) {
        // Simple AudioContext to detect volume for the green ring
        const audioContext = new AudioContext();
        const mediaStreamSource = audioContext.createMediaStreamSource(stream);
        const scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);
        
        mediaStreamSource.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);

        scriptProcessor.onaudioprocess = function(event) {
            const inputBuffer = event.inputBuffer;
            const inputData = inputBuffer.getChannelData(0);
            let sum = 0;
            for (let i = 0; i < inputData.length; i++) { sum += inputData[i] * inputData[i]; }
            let rms = Math.sqrt(sum / inputData.length);
            
            const ring = document.getElementById(`ring-${sid}`);
            if(ring) {
                ring.style.opacity = rms > 0.02 ? 1 : 0;
            }
        };
    }

    function appendMessage(msg) {
        const chatArea = document.getElementById('chatArea');
        const div = document.createElement('div');
        
        if (msg.type === 'system') {
            div.className = 'system-msg';
            div.innerHTML = `${msg.text} <span style="font-size:0.7em">${msg.time}</span>`;
        } else {
            div.className = 'message';
            div.innerHTML = `
                <div class="avatar">${msg.sender[0].toUpperCase()}</div>
                <div class="msg-content">
                    <div class="msg-header">
                        <span class="username">${msg.sender}</span>
                        <span class="timestamp">${msg.time}</span>
                    </div>
                    <div class="text">${formatText(msg.text)}</div>
                </div>
            `;
        }
        chatArea.appendChild(div);
        scrollToBottom();
    }
    
    function formatText(text) {
        // Simple Link and Markdown formatting
        return text
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/https?:\/\/\S+/g, '<a href="$&" target="_blank" style="color:#00b0f4">$&</a>');
    }

    function scrollToBottom() {
        const chatArea = document.getElementById('chatArea');
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // Input Handling
    const input = document.getElementById('msgInput');
    input.addEventListener('keydown', (e) => {
        if(e.key === 'Enter') {
            const txt = input.value.trim();
            if(txt) {
                socket.emit('chat_message', { msg: txt });
                input.value = '';
            }
        }
    });
    
    function toggleMic() {
        const track = localStream.getAudioTracks()[0];
        track.enabled = !track.enabled;
        document.getElementById('micBtn').classList.toggle('active');
        document.getElementById('micBtn').textContent = track.enabled ? '🎤' : '🔇';
    }

    function toggleDeafen() {
        // Mute all remote audio elements
        isMuted = !isMuted;
        document.querySelectorAll('audio').forEach(a => a.muted = isMuted);
        document.getElementById('deafenBtn').classList.toggle('active');
    }

</script>
</body>
</html>
"""

if __name__ == "__main__":
    # HOST='0.0.0.0' allows other computers on your wifi to connect
    print("--- Starting Discord Clone Server ---")
    print("1. Ensure you installed: pip install flask flask-socketio eventlet")
    print("2. Open http://localhost:5000 in multiple tabs")
    print("3. For Voice to work between different devices, you need HTTPS or localhost.")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)