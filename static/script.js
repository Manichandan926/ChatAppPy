const socket = io();
let myUsername = "";
let localStream = null;
let screenStream = null;
let peers = {};
let isMicMuted = false;
let isDeafened = false;

// 10MB Limit (Matches server config)
const MAX_FILE_SIZE = 10 * 1024 * 1024; 

const rtcConfig = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };

// --- INIT ---
document.getElementById('usernameInput').addEventListener('keydown', e => { if(e.key==='Enter') join(); });
document.getElementById('msgInput').addEventListener('keydown', e => { if(e.key === 'Enter') sendText(); });

async function join() {
    const nameInput = document.getElementById('usernameInput');
    const name = nameInput.value.trim();
    if (!name) return;
    myUsername = name;
    
    document.getElementById('loginOverlay').style.display = 'none';
    document.getElementById('myAvatar').textContent = name[0].toUpperCase();

    try {
        localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (e) {
        console.error("Audio denied:", e);
        alert("Microphone access is required for voice!");
    }

    socket.emit('register', { username: name });
}

// --- SOCKET LISTENERS ---
socket.on('message', appendMessage);

socket.on('history', msgs => {
    const box = document.getElementById('chatArea');
    box.innerHTML = '<div class="system-msg" style="margin-top:auto;">Welcome to #general!</div>';
    msgs.forEach(appendMessage);
});

socket.on('update_users', users => {
    const list = document.getElementById('userList');
    list.innerHTML = users.map(u => `
        <div class="user-item">
            <div class="avatar">
                ${u.username[0].toUpperCase()}
                <div class="status-badge"></div>
            </div>
            <div style="font-weight:600; color:var(--text-normal); font-size:14px;">
                ${u.username} ${u.username === myUsername ? '(You)' : ''}
            </div>
        </div>
    `).join('');
});

// --- CHAT LOGIC ---
function sendText() {
    const input = document.getElementById('msgInput');
    if (input.value.trim()) {
        socket.emit('chat_message', { type: 'text', content: input.value });
        input.value = '';
    }
}

function sendImage() {
    const file = document.getElementById('imgInput').files[0];
    if (!file) return;
    
    if (file.size > MAX_FILE_SIZE) {
        alert("Image is too large (Max 10MB)");
        return;
    }

    const reader = new FileReader();
    reader.onload = e => socket.emit('chat_message', { type: 'image', content: e.target.result });
    reader.readAsDataURL(file);
    document.getElementById('imgInput').value = ''; 
}

// NEW: Send File Function
function sendFile() {
    const file = document.getElementById('fileInput').files[0];
    if (!file) return;

    if (file.size > MAX_FILE_SIZE) {
        alert("File is too large (Max 10MB)");
        return;
    }

    const reader = new FileReader();
    reader.onload = e => {
        socket.emit('chat_message', { 
            type: 'file', 
            content: e.target.result,
            fileName: file.name 
        });
    };
    reader.readAsDataURL(file);
    document.getElementById('fileInput').value = ''; 
}

function appendMessage(msg) {
    const box = document.getElementById('chatArea');
    const div = document.createElement('div');
    
    if (msg.type === 'system') {
        div.className = 'system-msg';
        div.textContent = msg.text;
    } else {
        div.className = 'message';
        
        // Determine Content HTML based on type
        let contentHtml = '';
        
        if (msg.type === 'image') {
            contentHtml = `<img src="${msg.content}" class="msg-img" onclick="window.open(this.src)">`;
        } else if (msg.type === 'file') {
            // New File Card Style
            contentHtml = `
                <div class="file-card">
                    <span class="material-icons-round" style="font-size:30px; color:#5865f2;">description</span>
                    <div style="margin-left:10px;">
                        <div style="font-weight:bold; color:#dcddde;">${msg.fileName}</div>
                        <a href="${msg.content}" download="${msg.fileName}" style="color:#00b0f4; font-size:12px; text-decoration:none;">Download</a>
                    </div>
                </div>`;
        } else {
            contentHtml = `<div class="msg-text">${msg.content}</div>`;
        }

        div.innerHTML = `
            <div class="avatar" style="margin-top:4px;">${msg.sender[0].toUpperCase()}</div>
            <div class="msg-content">
                <div class="msg-header">
                    <span class="msg-user">${msg.sender}</span>
                    <span class="msg-time">${msg.time}</span>
                </div>
                ${contentHtml}
            </div>
        `;
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// --- WEBRTC LOGIC (Same as before) ---
socket.on('user_joined', data => { if (data.username !== myUsername) createPeer(data.sid, true); });

socket.on('user_left', data => {
    if (peers[data.sid]) { peers[data.sid].close(); delete peers[data.sid]; }
    const vid = document.getElementById(`vid-wrapper-${data.sid}`);
    if(vid) vid.remove();
    const aud = document.getElementById(`audio-${data.sid}`);
    if(aud) aud.remove();
    checkVideoGrid();
});

socket.on('voice_signal', async data => {
    if (!peers[data.sender_sid]) createPeer(data.sender_sid, false);
    const pc = peers[data.sender_sid];
    
    if (data.type === 'offer') {
        await pc.setRemoteDescription(data.payload);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        socket.emit('voice_signal', { target: data.sender_sid, type: 'answer', payload: answer });
    } else if (data.type === 'answer') {
        await pc.setRemoteDescription(data.payload);
    } else if (data.type === 'ice-candidate' && data.payload) {
        await pc.addIceCandidate(data.payload);
    }
});

function createPeer(sid, initiator) {
    const pc = new RTCPeerConnection(rtcConfig);
    peers[sid] = pc;

    if (localStream) localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
    if (screenStream) screenStream.getTracks().forEach(t => pc.addTrack(t, screenStream));

    pc.ontrack = e => {
        if (e.track.kind === 'video') {
            addVideo(e.streams[0], sid);
        } else {
            const audio = document.createElement('audio');
            audio.srcObject = e.streams[0];
            audio.autoplay = true;
            audio.style.display = 'none'; 
            audio.id = `audio-${sid}`;
            document.body.appendChild(audio);
            if (isDeafened) audio.muted = true;
        }
    };

    pc.onicecandidate = e => {
        if (e.candidate) socket.emit('voice_signal', { target: sid, type: 'ice-candidate', payload: e.candidate });
    };

    if (initiator) {
        pc.onnegotiationneeded = async () => {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            socket.emit('voice_signal', { target: sid, type: 'offer', payload: offer });
        };
    }
}

// --- CONTROLS ---

function toggleMic() {
    if (!localStream) return;
    isMicMuted = !isMicMuted;
    localStream.getAudioTracks()[0].enabled = !isMicMuted;
    
    const btn = document.getElementById('micBtn');
    if (isMicMuted) {
        btn.classList.add('active-red');
        btn.querySelector('span').textContent = 'mic_off';
    } else {
        btn.classList.remove('active-red');
        btn.querySelector('span').textContent = 'mic';
    }
}

function toggleDeafen() {
    isDeafened = !isDeafened;
    const btn = document.getElementById('deafenBtn');
    if (isDeafened) {
        btn.classList.add('active-red');
        btn.querySelector('span').textContent = 'headset_off';
        if (!isMicMuted) toggleMic(); 
    } else {
        btn.classList.remove('active-red');
        btn.querySelector('span').textContent = 'headset';
    }
    document.querySelectorAll('audio').forEach(a => a.muted = isDeafened);
    document.querySelectorAll('video').forEach(v => { if (v.id !== 'vid-me') v.muted = isDeafened; });
}

async function toggleScreen() {
    const btn = document.getElementById('screenBtn');
    if (!screenStream) {
        try {
            screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
            btn.classList.add('active-green');
            Object.values(peers).forEach(pc => {
                screenStream.getTracks().forEach(t => pc.addTrack(t, screenStream));
            });
            addVideo(screenStream, 'me');
            screenStream.getVideoTracks()[0].onended = () => stopScreenShare(); 
        } catch (e) { console.error("Screen share cancelled"); }
    } else {
        stopScreenShare();
    }
}

function stopScreenShare() {
    const btn = document.getElementById('screenBtn');
    if (screenStream) {
        screenStream.getTracks().forEach(t => t.stop());
        screenStream = null;
        btn.classList.remove('active-green');
        const myVid = document.getElementById('vid-wrapper-me');
        if (myVid) myVid.remove();
        checkVideoGrid();
    }
}

function addVideo(stream, sid) {
    const grid = document.getElementById('videoGrid');
    grid.style.display = 'flex';
    if (document.getElementById(`vid-wrapper-${sid}`)) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'video-wrapper';
    wrapper.id = `vid-wrapper-${sid}`;
    
    const vid = document.createElement('video');
    vid.srcObject = stream;
    vid.autoplay = true;
    vid.id = `vid-${sid}`;
    if (sid === 'me' || isDeafened) vid.muted = true;
    
    const label = document.createElement('div');
    label.className = 'video-label';
    label.textContent = sid === 'me' ? 'My Screen' : 'User Screen';

    wrapper.appendChild(vid);
    wrapper.appendChild(label);
    grid.appendChild(wrapper);
}

function checkVideoGrid() {
    const grid = document.getElementById('videoGrid');
    if (grid.children.length === 0) grid.style.display = 'none';
}