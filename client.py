import socket
import json

def send_message(sock, obj):
    line = json.dumps(obj, separators=(",", ":")) + "\n"
    sock.sendall(line.encode('utf-8'))

def receive_message(sock, buffer):
    try:
        chunk = sock.recv(4096)
        if not chunk:
            return None, buffer  # peer closed
        buffer += chunk.decode("utf-8")
        if "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip() == "":
                return None, buffer
            return json.loads(line), buffer
    except socket.timeout:
        return None, buffer

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('127.0.0.1', 12345))

# Send PLAYER_JOINED message
send_message(client, {"type": "PLAYER_JOINED", "name": "Jay"})

# Receive response from server
buffer = ""
msg, buffer = receive_message(client, buffer)
if msg:
    print(f"received: {msg}")
else:
    print("No message received from server.")

client.close()