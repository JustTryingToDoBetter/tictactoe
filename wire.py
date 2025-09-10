import json, struct, time, uuid

PROTOCOL_VERSION = '1.0'

def now_ms(): return int(time.time() * 1000)
def new_id(): return str(uuid.uuid4())

def send_obj(sock, obj: dict):
    data = json.dumps(obj).encode('utf-8')
    hdr = struct.pack("!I", len(data))
    sock.sendall(hdr + data)

def recv_obj(sock):
    # Read 4 bytes length
    hdr = _recvall(sock, 4)
    if not hdr: return None
    (length,) = struct.unpack("!I", hdr)
    payload = _recvall(sock, length)
    if not payload: return None
    return json.loads(payload.decode("utf-8"))


def _recvall(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def envelope(msg_type, game_id, payload, msg_id=None):
    return {
        "type": msg_type,
        "id": msg_id or new_id(),
        "ts": now_ms(),
        "game_id": game_id,
        "version": PROTOCOL_VERSION,
        "payload": payload,
    }