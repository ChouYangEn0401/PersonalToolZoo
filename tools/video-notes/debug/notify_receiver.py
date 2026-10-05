"""socket 模式的測試接收端：在 127.0.0.1:8787 等 POST，收到就印出來。

    python debug\\notify_receiver.py            # 另一個視窗再跑：VideoNotes <網址> --post
    python debug\\notify_receiver.py --port 9000

真正要串接的程式照這個樣子寫就好：收 JSON、回 200。
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            data = json.loads(body)
            notes = data.pop("notes", "")
            print(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"--- notes（{len(notes)} 字）---\n{notes[:800]}")
        except ValueError:
            print(body[:2000])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8787)
    port = p.parse_args().port
    print(f"等待 POST：http://127.0.0.1:{port}/video-notes   （Ctrl+C 結束）")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
