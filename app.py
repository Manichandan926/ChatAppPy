from flask import Flask, request, jsonify
from datetime import datetime
from collections import defaultdict
import time

app = Flask(__name__)

# --- In-Memory Storage ---
BOT_HISTORY = []  # List of dicts: {'id': int, 'sender': str, 'role': str, 'text': str, 'time': str, 'type': str}
USER_SESSIONS = {}  # browser_id -> {'name': str, 'role': str, 'last_seen': float}
TYPING_STATUS = {}  # browser_id -> timestamp

@app.route("/")
def home():
    return "API is alive. Go to <a href='/whatsapp'>/whatsapp</a> to chat."

@app.route("/messages")
def get_messages():
    # client sends the ID of the last message they already have
    last_id = int(request.args.get('last_id', -1))
    
    # Return only messages newer than last_id
    new_messages = [msg for msg in BOT_HISTORY if msg['id'] > last_id]
    
    return jsonify(new_messages)

@app.route("/send", methods=["POST"])
def send_message():
    data = request.json
    message = data.get("message", "").strip()
    browser_id = data.get("browser_id")
    username = data.get("username", "").strip()

    if not message:
        return jsonify(status="empty")

    # Update session activity
    if browser_id in USER_SESSIONS:
        USER_SESSIONS[browser_id]['last_seen'] = time.time()

    # --- Registration Logic ---
    if message.lower().startswith("register "):
        parts = message.lower().split(" ", 1)
        if len(parts) == 2:
            role = parts[1].upper()
            if role in ["A", "B"]:
                USER_SESSIONS[browser_id] = {
                    'name': username or f"User {role}", 
                    'role': role,
                    'last_seen': time.time()
                }
                
                new_msg = {
                    'id': len(BOT_HISTORY),
                    'sender': "System",
                    'role': 'SYSTEM',
                    'text': f"👤 {USER_SESSIONS[browser_id]['name']} joined as {role}",
                    'time': datetime.now().isoformat(),
                    'type': 'system'
                }
                BOT_HISTORY.append(new_msg)
                return jsonify(status="ok")

    # --- Chat Logic ---
    if browser_id in USER_SESSIONS:
        user = USER_SESSIONS[browser_id]
        new_msg = {
            'id': len(BOT_HISTORY),
            'sender': user['name'],
            'role': user['role'],
            'text': message,
            'time': datetime.now().isoformat(),
            'type': 'chat'
        }
        BOT_HISTORY.append(new_msg)
        return jsonify(status="ok")
    else:
        return jsonify(status="error", message="Please register first")

@app.route("/typing", methods=["POST"])
def typing_endpoint():
    data = request.json
    browser_id = data.get("browser_id")
    is_typing = data.get("is_typing", False)
    
    if is_typing:
        TYPING_STATUS[browser_id] = time.time()
    else:
        TYPING_STATUS.pop(browser_id, None)
    
    # Clean up old typing statuses (> 3 seconds)
    current_time = time.time()
    active_typing = []
    
    for bid, timestamp in list(TYPING_STATUS.items()):
        if current_time - timestamp > 3:
            del TYPING_STATUS[bid]
        else:
            name = USER_SESSIONS.get(bid, {}).get('name', 'Unknown')
            active_typing.append(name)
            
    return jsonify(typing_names=active_typing)

@app.route("/online-users")
def get_online_users():
    # Remove users inactive for > 60 seconds
    current_time = time.time()
    active_users = []
    
    for bid, data in list(USER_SESSIONS.items()):
        if current_time - data['last_seen'] < 60:
            active_users.append(data)
        # We don't delete them from session, just don't show as 'online'
            
    return jsonify(active_users)

@app.route("/whatsapp")
def whatsapp_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pro Chat</title>
<style>
/* --- MODERN DARK THEME CSS --- */
:root {
    --bg-app: #0f172a;
    --bg-panel: #1e293b;
    --border: #334155;
    --primary: #3b82f6;
    --primary-hover: #2563eb;
    --text-main: #f1f5f9;
    --text-muted: #94a3b8;
    --bubble-sent: #3b82f6;
    --bubble-received: #334155;
    --green: #22c55e;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background-color: var(--bg-app);
    color: var(--text-main);
    height: 100vh;
    display: flex;
    overflow: hidden;
}

/* Sidebar */
.sidebar {
    width: 300px;
    background: var(--bg-panel);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    transition: transform 0.3s ease;
}

.header {
    padding: 20px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    gap: 10px;
}

.user-list {
    flex: 1;
    overflow-y: auto;
    padding: 10px;
}

.user-card {
    padding: 10px;
    margin-bottom: 5px;
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    display: flex;
    align-items: center;
    gap: 10px;
}

.status-dot {
    width: 8px;
    height: 8px;
    background: var(--green);
    border-radius: 50%;
    box-shadow: 0 0 5px var(--green);
}

/* Main Chat */
.chat-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    background-image: radial-gradient(var(--border) 1px, transparent 1px);
    background-size: 20px 20px;
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    scroll-behavior: smooth;
}

/* Scrollbar Styling */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* Message Bubbles */
.msg-row {
    display: flex;
    width: 100%;
    opacity: 0;
    animation: fadeIn 0.3s forwards;
}

@keyframes fadeIn { to { opacity: 1; transform: translateY(0); } }

.msg-row.sent { justify-content: flex-end; }
.msg-row.received { justify-content: flex-start; }
.msg-row.system { justify-content: center; margin: 10px 0; }

.bubble {
    max-width: 60%;
    padding: 10px 14px;
    border-radius: 12px;
    position: relative;
    font-size: 0.95rem;
    line-height: 1.4;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
}

.msg-row.sent .bubble {
    background: var(--bubble-sent);
    color: white;
    border-bottom-right-radius: 2px;
}

.msg-row.received .bubble {
    background: var(--bubble-received);
    color: var(--text-main);
    border-bottom-left-radius: 2px;
}

.msg-row.system .bubble {
    background: rgba(0,0,0,0.3);
    color: var(--text-muted);
    font-size: 0.8rem;
    border-radius: 20px;
    padding: 4px 12px;
}

.sender-name {
    font-size: 0.75rem;
    font-weight: 700;
    margin-bottom: 4px;
    color: rgba(255,255,255,0.7);
}

.timestamp {
    font-size: 0.7rem;
    opacity: 0.7;
    text-align: right;
    margin-top: 4px;
}

/* Typing Indicator */
.typing-bar {
    padding: 5px 20px;
    height: 24px;
    font-size: 0.8rem;
    color: var(--text-muted);
    font-style: italic;
}

/* Input Area */
.input-area {
    padding: 20px;
    background: var(--bg-panel);
    display: flex;
    gap: 10px;
    border-top: 1px solid var(--border);
}

input {
    flex: 1;
    background: var(--bg-app);
    border: 1px solid var(--border);
    padding: 12px;
    border-radius: 24px;
    color: white;
    outline: none;
    font-size: 1rem;
}

input:focus { border-color: var(--primary); }

button {
    background: var(--primary);
    color: white;
    border: none;
    padding: 0 20px;
    border-radius: 24px;
    cursor: pointer;
    font-weight: 600;
    transition: background 0.2s;
}

button:hover { background: var(--primary-hover); }

/* Registration Modal */
.modal-overlay {
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.8);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
}

.modal {
    background: var(--bg-panel);
    padding: 30px;
    border-radius: 16px;
    width: 90%;
    max-width: 400px;
    border: 1px solid var(--border);
    text-align: center;
}

.modal input { width: 100%; margin: 15px 0; }
.btn-group { display: flex; gap: 10px; justify-content: center; }

</style>
</head>
<body>

<div class="modal-overlay" id="loginModal">
    <div class="modal">
        <h2>Welcome</h2>
        <p style="color:var(--text-muted); margin-top:5px;">Enter your name to join</p>
        <input type="text" id="usernameInput" placeholder="Your Display Name">
        <div class="btn-group">
            <button onclick="register('A')">Join as A</button>
            <button onclick="register('B')" style="background:#475569">Join as B</button>
        </div>
    </div>
</div>

<div class="sidebar">
    <div class="header">
        <span>👥</span> Online Users
    </div>
    <div class="user-list" id="userList">
        </div>
</div>

<div class="chat-container">
    <div class="header">
        <span id="headerTitle">Chat Room</span>
    </div>
    
    <div class="chat-messages" id="chatBox">
        </div>

    <div class="typing-bar" id="typingBar"></div>

    <div class="input-area">
        <input type="text" id="msgInput" placeholder="Type a message..." autocomplete="off">
        <button onclick="sendMessage()">Send</button>
    </div>
</div>

<script>
// --- CONFIGURATION ---
const browserId = Math.random().toString(36).substring(2);
let lastMessageId = -1;
let myRole = null;
let myName = null;
let typingTimer = null;

// --- REGISTRATION ---
async function register(role) {
    const nameInput = document.getElementById('usernameInput');
    const name = nameInput.value.trim() || `User ${role}`;
    
    myName = name;
    myRole = role;

    await fetch('/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            message: `register ${role}`,
            browser_id: browserId,
            username: name
        })
    });

    document.getElementById('loginModal').style.display = 'none';
    document.getElementById('headerTitle').innerText = `${name} (${role})`;
    document.getElementById('msgInput').focus();
    
    startPolling();
}

// --- CORE CHAT LOGIC ---
async function startPolling() {
    setInterval(fetchMessages, 1000);     // Fetch new messages
    setInterval(fetchOnlineUsers, 3000); // Fetch online users
    setInterval(fetchTypingStatus, 1500); // Fetch typing status
}

async function fetchMessages() {
    try {
        // Only ask for messages NEWER than the last one we saw
        const response = await fetch(`/messages?last_id=${lastMessageId}`);
        const messages = await response.json();

        if (messages.length === 0) return;

        const chatBox = document.getElementById('chatBox');
        
        // Smart scroll detection: are we at the bottom?
        const isAtBottom = (chatBox.scrollHeight - chatBox.scrollTop) <= (chatBox.clientHeight + 100);

        messages.forEach(msg => {
            appendMessageToDOM(msg);
            lastMessageId = msg.id; // Update our tracker
        });

        if (isAtBottom) {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    } catch (e) { console.error("Poll error", e); }
}

function appendMessageToDOM(msg) {
    const chatBox = document.getElementById('chatBox');
    const div = document.createElement('div');
    
    // Determine class
    let rowClass = 'msg-row';
    if (msg.type === 'system') rowClass += ' system';
    else if (msg.role === myRole) rowClass += ' sent';
    else rowClass += ' received';
    
    div.className = rowClass;

    const timeStr = new Date(msg.time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

    if (msg.type === 'system') {
        div.innerHTML = `<div class="bubble">${escapeHtml(msg.text)}</div>`;
    } else {
        div.innerHTML = `
            <div class="bubble">
                <div class="sender-name">${escapeHtml(msg.sender)}</div>
                ${escapeHtml(msg.text)}
                <div class="timestamp">${timeStr}</div>
            </div>
        `;
    }

    chatBox.appendChild(div);
}

async function sendMessage() {
    const input = document.getElementById('msgInput');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    
    // Optimistic UI: You could append immediately here, but for now we wait for polling
    await fetch('/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            message: text,
            browser_id: browserId,
            username: myName
        })
    });
    
    // Trigger immediate fetch
    fetchMessages();
}

// --- UTILITIES ---
function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// --- TYPING & USERS ---
const msgInput = document.getElementById('msgInput');
msgInput.addEventListener('input', () => {
    clearTimeout(typingTimer);
    fetch('/typing', {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({browser_id: browserId, is_typing: true})
    });
    
    typingTimer = setTimeout(() => {
        fetch('/typing', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({browser_id: browserId, is_typing: false})
        });
    }, 2000);
});

msgInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

async function fetchOnlineUsers() {
    const res = await fetch('/online-users');
    const users = await res.json();
    const list = document.getElementById('userList');
    list.innerHTML = users.map(u => `
        <div class="user-card">
            <div class="status-dot"></div>
            <div>
                <div style="font-weight:600; font-size:0.9rem">${escapeHtml(u.name)}</div>
                <div style="font-size:0.75rem; color:var(--text-muted)">${u.role}</div>
            </div>
        </div>
    `).join('');
}

async function fetchTypingStatus() {
    const res = await fetch('/typing', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({browser_id: browserId, is_typing: false}) // Just query
    });
    const data = await res.json();
    const bar = document.getElementById('typingBar');
    if (data.typing_names.length > 0) {
        bar.textContent = `${data.typing_names.join(', ')} is typing...`;
    } else {
        bar.textContent = '';
    }
}

</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(port=5000, debug=True)