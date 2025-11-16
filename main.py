from pymongo import MongoClient
import multiprocessing
import socket
import pathlib
import mimetypes
import datetime
import time

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote_plus, urlparse

# КОНФІГУРАЦІЯ
SOCKET_HOST = "0.0.0.0"
SOCKET_PORT = 5000

HTTP_HOST = "0.0.0.0"
HTTP_PORT = 3000

MONGO_URI = "mongodb://mongodb:27017"
DB_NAME = "msg_db"
COLLECTION_NAME = "messages"

# MONGO DB
mongo_client = None


def get_mongo():
    global mongo_client
    if mongo_client:
        return mongo_client

    for attempt in range(10):
        try:
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)
            mongo_client.admin.command("ping")
            print("✅ MongoDB connected")
            return mongo_client
        except Exception:
            print("⏳ Waiting for MongoDB...")
            time.sleep(1)

    raise RuntimeError("❌ Cannot connect to MongoDB")


# ЗБЕРЕЖЕННЯ ДАНИХ У MONGO DB
def save_msg(data: dict):
    try:
        client = get_mongo()
        client[DB_NAME][COLLECTION_NAME].insert_one(data)
        print("✅ Saved to MongoDB:", data)
    except Exception as e:
        print("❌ MongoDB error:", e)


# SOCKET SERVER
def run_socket_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((SOCKET_HOST, SOCKET_PORT))
    sock.listen(1)
    print(f"Socket server ready on tcp://{SOCKET_HOST}:{SOCKET_PORT}")

    while True:
        conn, _ = sock.accept()
        data = conn.recv(1024).decode()
        if data:
            fields = dict(pair.split("=") for pair in data.split("&"))
            save_msg(
                {
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "username": unquote_plus(fields.get("username")),
                    "message": unquote_plus(fields.get("message", "")),
                }
            )
        conn.close()


# HTTP SERVER
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SOCKET_HOST, SOCKET_PORT))
        sock.sendall(raw)
        sock.close()
        print(f"Data ({len(raw)} bytes) sent to Socket-server {SOCKET_PORT}")

        self.send_response(302)
        self.send_header("Location", "/")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        static = {
            "/": "front-init/index.html",
            "/message": "front-init/message.html",
        }
        if path in static:
            self.send_html(static[path])
        elif path.startswith("/front-init/"):
            self.send_static()
        else:
            self.send_html("front-init/error.html", 404)

    def send_html(self, filename, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        try:
            with open(filename, "rb") as f:
                self.wfile.write(f.read())
        except FileNotFoundError:
            self.send_response(500)
            self.wfile.write(b"Internal Server Error: File not found")

    def send_static(self):
        fp = pathlib.Path("." + self.path)
        if not fp.exists():
            return self.send_html("front-init/error.html", 404)

        mt = mimetypes.guess_type(fp)[0] or "text/plain"
        self.send_response(200)
        self.send_header("Content-Type", mt)
        self.end_headers()
        self.wfile.write(fp.read_bytes())


# HTTP SERVER LAUNCHER
def run_http_server():
    print(f"HTTP server ready on http://{HTTP_HOST}:{HTTP_PORT}")
    HTTPServer((HTTP_HOST, HTTP_PORT), Handler).serve_forever()


# BOTH SERVERS LAUNCH IN PARALLEL USING MULTIPROCESSING
if __name__ == "__main__":
    multiprocessing.Process(target=run_socket_server).start()
    multiprocessing.Process(target=run_http_server).start()


# docker-compose up --build

# http://localhost:3000

# Checkup in MongoDB:
# docker ps
# docker exec -it mongodb mongosh
# use msg_db
# db.messages.find().pretty()
