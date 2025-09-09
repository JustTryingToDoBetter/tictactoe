import socket
import json

## create server 

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM) ## object

server.bind(('127.0.0.1', 12345)) ## bind
server.listen(1) #listen for in comming connection
print('server is listening')

conn, addr = server.accept() ## conncection
print(f'connected by {addr}')

data = conn.recv(1024) ## receive data
print(f'receieve: {data.decode()}')

conn.sendall(b'hello, client') ## send response
conn.close() ## close connection
server.close() ## kill server


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