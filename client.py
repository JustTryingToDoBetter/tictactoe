import socket

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

client.connect(('127.0.0.1', 12345))
client.sendall(b"hello, server!")
data = client.recv(1024)
print(f"recieved: {data.decode()}")
client.close()
