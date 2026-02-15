from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from datetime import datetime

# --- CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# 10MB max size for images to prevent crashing
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', max_http_buffer_size=10000000)

USERS = {}
HISTORY = []

@app.route("/")
def index():
    # Flask looks for 'index.html' inside the 'templates' folder
    return render_template('index.html') 

# --- SOCKET EVENTS ---

@socketio.on('connect')
def handle_connect():
    print(f"New connection: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in USERS:
        user = USERS[request.sid]
        # Notify others
        emit('user_left', {'sid': request.sid, 'username': user['username']}, broadcast=True)
        
        # System message in chat
        sys_msg = {'type': 'system', 'text': f"🔴 {user['username']} left", 'time': get_time()}
        emit('message', sys_msg, broadcast=True)
        
        # Cleanup
        del USERS[request.sid]
        update_user_list()

@socketio.on('register')
def handle_register(data):
    username = data.get('username')
    # Save user info
    USERS[request.sid] = {'username': username, 'sid': request.sid}
    
    # Send chat history to the new user
    emit('history', HISTORY)
    
    # Tell everyone else a new user joined (Triggers WebRTC connection)
    emit('user_joined', {'sid': request.sid, 'username': username}, broadcast=True)
    
    # System message
    sys_msg = {'type': 'system', 'text': f"🟢 {username} joined", 'time': get_time()}
    HISTORY.append(sys_msg)
    emit('message', sys_msg, broadcast=True)
    
    update_user_list()

# ... (Keep imports and config the same) ...

@socketio.on('chat_message')
def handle_message(data):
    user = USERS.get(request.sid)
    if user:
        # Check if it's text, image, or file
        msg_type = data.get('type', 'text')
        content = data.get('content')
        file_name = data.get('fileName') # New: Get filename
        
        msg = {
            'type': msg_type,
            'sender': user['username'],
            'content': content,
            'fileName': file_name, # New: Send filename to others
            'sid': request.sid,
            'time': get_time()
        }
        
        # Save to history
        HISTORY.append(msg)
        if len(HISTORY) > 50: 
            HISTORY.pop(0)
            
        # Broadcast
        emit('message', msg, broadcast=True)

# ... (Keep the rest of the file exactly the same) ...

@socketio.on('voice_signal')
def handle_voice_signal(data):
    """
    This is the most important part for Screen Sharing and Voice.
    It relays the WebRTC 'handshake' data between two specific users.
    """
    target = data.get('target')
    if target in USERS:
        emit('voice_signal', {
            'sender_sid': request.sid,
            'type': data['type'],
            'payload': data['payload']
        }, room=target)

def update_user_list():
    users = [{'sid': k, 'username': v['username']} for k, v in USERS.items()]
    emit('update_users', users, broadcast=True)

def get_time():
    return datetime.now().strftime("%I:%M %p")

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)