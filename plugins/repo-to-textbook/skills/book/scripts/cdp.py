"""Minimal Chrome DevTools Protocol client (stdlib only) for printing a page to PDF.

Launches headless Chrome with a throwaway profile, loads the page, waits until
`window.__BOOK_READY__ === true` (set by book.js after Paged.js finishes) and
calls Page.printToPDF with the page's own CSS page size.
"""

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request


class CDPError(RuntimeError):
    pass


class _WebSocket:
    def __init__(self, url, timeout):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key))
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("websocket handshake failed")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise CDPError("websocket handshake rejected: %r" % resp[:200])
        self.buf = resp.split(b"\r\n\r\n", 1)[1]

    def send(self, text):
        data = text.encode()
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise CDPError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            opcode = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise CDPError("websocket closed by browser")
            if opcode == 0x9:  # ping -> ignore (Chrome does not require pong for CDP)
                continue
            parts.append(payload)
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def print_to_pdf(chrome, html_path, pdf_path, timeout=180):
    profile = tempfile.mkdtemp(prefix="r2t-cdp-")
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--remote-debugging-port=0", "--remote-allow-origins=*", "--user-data-dir=" + profile, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        port_file = os.path.join(profile, "DevToolsActivePort")
        deadline = time.time() + 30
        while not os.path.exists(port_file) or not open(port_file).read().strip():
            if proc.poll() is not None or time.time() > deadline:
                raise CDPError("Chrome did not start its DevTools endpoint")
            time.sleep(0.1)
        port = int(open(port_file).read().split()[0])
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=10).read())
        page = next(t for t in targets if t.get("type") == "page")
        ws = _WebSocket(page["webSocketDebuggerUrl"], timeout=timeout)
        counter = [0]

        def call(method, **params):
            counter[0] += 1
            mid = counter[0]
            ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise CDPError("%s: %s" % (method, msg["error"].get("message")))
                    return msg.get("result", {})

        def evaluate(expr):
            r = call("Runtime.evaluate", expression=expr, returnByValue=True)
            return r.get("result", {}).get("value")

        call("Page.navigate", url="file://" + os.path.abspath(html_path))
        deadline = time.time() + timeout
        while evaluate("window.__BOOK_READY__ === true") is not True:
            if time.time() > deadline:
                pages = evaluate("document.querySelectorAll('.pagedjs_page').length")
                raise CDPError("timed out after %ds waiting for pagination (%s pages so far)" % (timeout, pages))
            time.sleep(0.4)
        err = evaluate("window.__BOOK_ERROR__ || null")
        if err:
            raise CDPError("render error:\n" + err)
        result = call("Page.printToPDF", preferCSSPageSize=True, printBackground=True,
                      displayHeaderFooter=False, marginTop=0, marginBottom=0, marginLeft=0, marginRight=0)
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(result["data"]))
        return evaluate("document.querySelectorAll('.pagedjs_page').length")
    finally:
        if ws:
            ws.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
