# logic/video_distributed.py
import socket, threading, time, psutil

BROADCAST_PORT = 50505
BROADCAST_INTERVAL = 5   # sec

class NodeAnnouncer(threading.Thread):
    """Broadcast presence so other nodes can discover us."""
    def __init__(self, role="client", gpu="cpu"):
        super().__init__(daemon=True)
        self.role = role
        self.gpu = gpu
        self.running = True

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            return
        while self.running:
            try:
                cpu = psutil.cpu_percent()
                msg = f"HELLO;role={self.role};gpu={self.gpu};cpu={cpu:.0f}"
                sock.sendto(msg.encode("utf-8"), ("255.255.255.255", BROADCAST_PORT))
            except Exception:
                pass
            time.sleep(BROADCAST_INTERVAL)

    def stop(self):
        self.running = False


class NodeListener(threading.Thread):
    """Listen to broadcast and keep a list of visible nodes.
       If the port is occupied, it silently disables itself (avoids crashes on autoreload)."""
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.nodes = {}
        self._enabled = True

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", BROADCAST_PORT))
        except Exception:
            # Another instance already listening (e.g., autoreload). Disable gracefully.
            self._enabled = False
            return

        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                ip = addr[0]
                msg = data.decode("utf-8", errors="ignore")
                if msg.startswith("HELLO;"):
                    parts = dict(p.split("=", 1) for p in msg[6:].split(";") if "=" in p)
                    parts["ip"] = ip
                    parts["last_seen"] = time.time()
                    self.nodes[ip] = parts
            except Exception:
                pass

    def get_nodes(self):
        now = time.time()
        return [n for n in self.nodes.values() if now - n.get("last_seen", 0) < 15]

    def stop(self):
        self.running = False
