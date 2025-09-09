import socket
import json

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

client.connect(('127.0.0.1', 12345))
client.sendall(b"hello, server!")
data = client.recv(1024)
print(f"recieved: {data.decode()}")
client.close()


def send_message(sock, obj):
    line = json.dumps(obj, separators=('', ':')) + "\n" ## struture  ajson body thing
    sock.sendall(line.encode('utf-8'))

def receive_message(sock, buffer):
    try:
        chunk = sock.recv(4096)
        if not chunk:
            return None, buffer  ## peer closed
        buffer += chunk.decode("utf-8")

        if "\n" in buffer:
            line,buffer = buffer.split("\n", 1)
            if line.strip() == "":
                return None, buffer
            return json.loads(line), buffer
    
    except server.timeout:
        return None, buffer