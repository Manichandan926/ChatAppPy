from flask import Flask, request, jsonify
import json
import random
from datetime import datetime
from collections import defaultdict
import uuid

app = Flask(__name__)

BOT_HISTORY = []
USER_ROLE = {}
USER_NAMES = {}
USER_SESSIONS = {}  # Track active sessions
MESSAGE_METADATA = {}  # Store timestamps, read status
TYPING_INDICATORS = {}  # Who's typing
ROOM_CHANNELS = defaultdict(list)  # Multiple chat rooms

@app.route("/")
def home():
    return "API is alive. Go to <a href='/whatsapp'>/whatsapp</a> to chat."

@app.route("/messages")
def get_messages():
    result = []
    for idx, msg in enumerate(BOT_HISTORY):
        meta = MESSAGE_METADATA.get(idx, {})
        result.append({
            "id": idx,
            "content": msg,
            "timestamp": meta.get("timestamp"),
            "read_by": meta.get("read_by", [])
        })
    return jsonify(result)

@app.route("/send", methods=["POST"])
def send_message():
    data = request.json
    message = data.get("message", "").strip()
    browser_id = data.get("browser_id")
    username = data.get("username", "").strip()

    if not message:
        return jsonify(status="empty")

    if message.lower().startswith("register "):
        parts = message.lower().split(" ", 1)
        if len(parts) == 2:
            role = parts[1].upper()
            if role in ["A", "B"]:
                USER_ROLE[browser_id] = role
                USER_NAMES[browser_id] = username or f"User {role}"
                USER_SESSIONS[browser_id] = {"joined_at": datetime.now().isoformat()}
                
                BOT_HISTORY.append(f"👤 {USER_NAMES[browser_id]} ({role}) joined")
                MESSAGE_METADATA[len(BOT_HISTORY)-1] = {"timestamp": datetime.now().isoformat(), "read_by": []}
                return jsonify(status="ok")

    if browser_id in USER_ROLE:
        role = USER_ROLE[browser_id]
        name = USER_NAMES.get(browser_id, f"User {role}")
        msg_text = f"[{role}] {name}: {message}"
        BOT_HISTORY.append(msg_text)
        
        msg_id = len(BOT_HISTORY) - 1
        MESSAGE_METADATA[msg_id] = {
            "timestamp": datetime.now().isoformat(),
            "sender_id": browser_id,
            "read_by": [browser_id]
        }
        
        return jsonify(status="ok", message_id=msg_id)
    else:
        return jsonify(status="error", message="Please register first")

@app.route("/typing", methods=["POST"])
def typing_status():
    data = request.json
    browser_id = data.get("browser_id")
    is_typing = data.get("is_typing", False)
    
    if is_typing:
        TYPING_INDICATORS[browser_id] = USER_NAMES.get(browser_id, "User")
    else:
        TYPING_INDICATORS.pop(browser_id, None)
    
    return jsonify(typing=list(TYPING_INDICATORS.values()))

@app.route("/online-users")
def get_online_users():
    users = []
    for bid, role in USER_ROLE.items():
        users.append({
            "browser_id": bid,
            "name": USER_NAMES.get(bid),
            "role": role,
            "joined_at": USER_SESSIONS.get(bid, {}).get("joined_at")
        })
    return jsonify(users)

@app.route("/whatsapp")
def whatsapp_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Advanced Chat UI</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --primary: #0088cc; --primary-dark: #005fa3;
    --bg-dark: #0d1117; --bg-secondary: #161b22; --bg-tertiary: #21262d;
    --text-primary: #c9d1d9; --text-secondary: #8b949e;
    --accent: #58a6ff; --success: #3fb950;
}
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg-dark); color: var(--text-primary); height: 100vh; overflow: hidden; }
.container { display: flex; height: 100vh; }
.sidebar { width: 320px; background: var(--bg-secondary); border-right: 1px solid var(--bg-tertiary); display: flex; flex-direction: column; }
.sidebar-header { padding: 20px; border-bottom: 1px solid var(--bg-tertiary); background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%); }
.sidebar-header h2 { font-size: 24px; color: white; }
.user-registration { padding: 16px; border-bottom: 1px solid var(--bg-tertiary); }
.user-registration input { width: 100%; padding: 10px; margin-bottom: 8px; background: var(--bg-tertiary); border: 1px solid var(--bg-tertiary); border-radius: 6px; color: var(--text-primary); }
.user-registration button { width: 100%; padding: 10px; background: var(--primary); color: white; border: none; border-radius: 6px; cursor: pointer; transition: 0.2s; margin-top: 4px; }
.user-registration button:hover { background: var(--primary-dark); }
.online-users { flex: 1; overflow-y: auto; padding: 12px; }
.user-item { padding: 12px; margin-bottom: 8px; background: var(--bg-tertiary); border-radius: 8px; border-left: 3px solid var(--success); }
.user-item-name { font-weight: 500; }
.user-item-role { font-size: 12px; color: var(--text-secondary); }
.chat-area { flex: 1; display: flex; flex-direction: column; }
.chat-header { padding: 16px 24px; border-bottom: 1px solid var(--bg-tertiary); background: var(--bg-secondary); }
.messages { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 12px; }
.message-group { display: flex; animation: fadeInUp 0.3s ease; }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.message-group.sent { justify-content: flex-end; }
.message-bubble { max-width: 55%; padding: 10px 14px; border-radius: 12px; font-size: 14px; word-wrap: break-word; }
.message-group.sent .message-bubble { background: var(--primary); color: white; }
.message-group.received .message-bubble { background: var(--bg-tertiary); color: var(--text-primary); }
.message-group.system .message-bubble { background: transparent; color: var(--text-secondary); border: 1px solid var(--bg-tertiary); max-width: 80%; text-align: center; margin: 8px auto; font-size: 12px; }
.typing-indicator { display: flex; gap: 4px; padding: 10px; }
.typing-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-secondary); animation: bounce 1.4s infinite; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { opacity: 0.5; } 40% { opacity: 1; } }
.input-area { padding: 16px 24px; background: var(--bg-secondary); border-top: 1px solid var(--bg-tertiary); display: flex; gap: 12px; }
.input-wrapper { flex: 1; display: flex; background: var(--bg-tertiary); border-radius: 20px; padding: 10px 16px; }
#msg { flex: 1; background: transparent; border: none; color: var(--text-primary); outline: none; }
.send-btn { width: 40px; height: 40px; border-radius: 50%; background: var(--primary); border: none; color: white; cursor: pointer; }
</style>
</head>
<body>
<div class="container">
    <div class="sidebar">
        <div class="sidebar-header"><h2>💬 Chat</h2></div>
        <div class="user-registration" id="regForm">
            <input type="text" id="usernameInput" placeholder="Your name...">
            <button onclick="registerUser('A')">Join as A</button>
            <button onclick="registerUser('B')">Join as B</button>
        </div>
        <div class="online-users" id="usersList"></div>
    </div>
    <div class="chat-area">
        <div class="chat-header">
            <h1>General Chat</h1>
            <p id="userStatus">Not registered</p>
            <div id="typingStatus" style="font-size:12px; color:var(--text-secondary); margin-top:8px;"></div>
        </div>
        <div class="messages" id="chat"></div>
        <div class="input-area">
            <div class="input-wrapper">
                <input type="text" id="msg" placeholder="Type..." onkeydown="handleEnter(event)" oninput="notifyTyping()">
            </div>
            <button class="send-btn" onclick="sendMsg()">➤</button>
        </div>
    </div>
</div>

<script>
const browserId = Math.random().toString(36).substring(2);
let currentUser = null, currentRole = null;
let typingTimeout = null;

async function registerUser(role) {
    const username = document.getElementById('usernameInput').value.trim() || `User ${role}`;
    currentUser = username;
    currentRole = role;
    document.getElementById('userStatus').textContent = `${username} (${role})`;
    document.getElementById('regForm').style.display = 'none';
    await sendMessage(`register ${role}`, username);
    loadMessages();
}

async function sendMessage(text, username = currentUser) {
    await fetch('/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, browser_id: browserId, username })
    });
}

function notifyTyping() {
    clearTimeout(typingTimeout);
    fetch('/typing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ browser_id: browserId, is_typing: true })
    });
    typingTimeout = setTimeout(() => {
        fetch('/typing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ browser_id: browserId, is_typing: false })
        });
    }, 2000);
}

async function loadMessages() {
    try {
        const [msgRes, onlineRes, typingRes] = await Promise.all([
            fetch('/messages'),
            fetch('/online-users'),
            fetch('/typing', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ browser_id: browserId, is_typing: false }) })
        ]);
        
        const messages = await msgRes.json();
        const onlineUsers = await onlineRes.json();
        const typingData = await typingRes.json();
        
        const chatDiv = document.getElementById('chat');
        let html = '';
        
        messages.forEach(msg => {
            const isSent = currentRole && msg.content.includes(`[${currentRole}]`);
            const type = msg.content.includes('joined') ? 'system' : 'chat';
            
            html += `<div class="message-group ${isSent ? 'sent' : type === 'system' ? 'system' : 'received'}">
                <div class="message-bubble">${msg.content.replace(/\[.\]/, '').trim()}</div>
            </div>`;
        });
        
        if (typingData.typing.length > 0) {
            html += `<div class="typing-indicator"><span style="color:var(--text-secondary);">${typingData.typing.join(', ')} typing</span><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
        }
        
        chatDiv.innerHTML = html;
        chatDiv.scrollTop = chatDiv.scrollHeight;
        
        document.getElementById('usersList').innerHTML = onlineUsers.map(u => 
            `<div class="user-item"><div class="user-item-name">${u.name}</div><div class="user-item-role">Role: ${u.role}</div></div>`
        ).join('');
        
    } catch (e) { console.error("Error:", e); }
}

async function sendMsg() {
    const input = document.getElementById('msg');
    const text = input.value.trim();
    if (!text || !currentRole) return;
    input.value = '';
    await sendMessage(text);
    await loadMessages();
}

function handleEnter(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMsg();
    }
}

setInterval(loadMessages, 1000);
loadMessages();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(port=5000, debug=True)
