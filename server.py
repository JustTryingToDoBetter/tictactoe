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

