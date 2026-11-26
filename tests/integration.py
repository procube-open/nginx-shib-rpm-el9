import http.client
import http.server
import os
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest


def read_exact(connection, size):
    data = b""
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise EOFError("incomplete FastCGI record")
        data += part
    return data


def fcgi_record(record_type, request_id, content):
    return struct.pack("!BBHHBB", 1, record_type, request_id, len(content), 0, 0) + content


class Authorizer(socketserver.BaseRequestHandler):
    def handle(self):
        params = b""
        while True:
            header = read_exact(self.request, 8)
            version, record_type, request_id, size, padding, _ = struct.unpack("!BBHHBB", header)
            if version != 1:
                raise ValueError("unexpected FastCGI version")
            content = read_exact(self.request, size)
            read_exact(self.request, padding)
            if record_type == 4:
                if content:
                    params += content
                else:
                    break

        if b"redirect" in params:
            response = (
                b"Status: 302 Found\r\nLocation: /login\r\n"
                b"Set-Cookie: first=1; Path=/\r\nSet-Cookie: second=2; Path=/\r\n"
                b"Cache-Control: no-store\r\n\r\n"
            )
        else:
            response = b"Status: 200 OK\r\nVariable-REMOTE_USER: alice\r\n\r\n"

        self.request.sendall(
            fcgi_record(6, request_id, response)
            + fcgi_record(6, request_id, b"")
            + fcgi_record(3, request_id, b"\0" * 8)
        )


class Backend(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(self.server.server_address[0].encode())

    def log_message(self, format, *args):
        pass


class AJP(socketserver.BaseRequestHandler):
    def handle(self):
        header = read_exact(self.request, 4)
        if header[:2] != b"\x12\x34":
            raise ValueError("unexpected AJP packet")
        read_exact(self.request, struct.unpack("!H", header[2:])[0])
        messages = [
            b"\x04\x00\xc8\x00\x02OK\x00\x00\x01\xa0\x03\x00\x01\x32\x00",
            b"\x03\x00\x02ok\x00",
            b"\x05\x00",
        ]
        for message in messages:
            self.request.sendall(b"AB" + struct.pack("!H", len(message)) + message)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class DNS(socketserver.BaseRequestHandler):
    def handle(self):
        data, connection = self.request
        end = 12
        while data[end]:
            end += data[end] + 1
        end += 5
        question = data[12:end]
        response = (
            data[:2] + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + question
            + b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 1, 4)
            + socket.inet_aton(self.server.address)
        )
        connection.sendto(response, self.client_address)


class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        auth_server = Server(("127.0.0.1", 0), Authorizer)
        backend1 = Server(("127.0.0.1", 0), Backend)
        backend2 = Server(("127.0.0.2", backend1.server_address[1]), Backend)
        ajp_server = Server(("127.0.0.1", 0), AJP)
        cls.dns = socketserver.UDPServer(("127.0.0.1", 0), DNS)
        cls.dns.address = "127.0.0.1"
        cls.servers = [auth_server, backend1, backend2, ajp_server, cls.dns]
        for server in cls.servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        auth, backend, _, ajp, dns = [s.server_address[1] for s in cls.servers]
        config = f"""
            daemon off;
            master_process off;
            pid {cls.temp.name}/nginx.pid;
            error_log stderr info;
            events {{ worker_connections 128; }}
            http {{
                resolver 127.0.0.1:{dns} valid=1s ipv6=off;
                upstream dynamic_backend {{
                    zone dynamic_backend 64k;
                    server backend.example.invalid:{backend} resolve;
                }}
                upstream sticky_backend {{
                    server 127.0.0.1:{backend};
                    server 127.0.0.2:{backend};
                    sticky cookie route path=/;
                }}
                server {{
                    listen 127.0.0.1:{cls.port};
                    location = /lua {{
                        content_by_lua_block {{
                            local core = require "resty.core.base"
                            ngx.say(jit.version)
                            ngx.say(core.version)
                        }}
                    }}
                    location = /protected {{
                        shib_request /auth;
                        shib_request_use_headers on;
                        content_by_lua_block {{ ngx.say(ngx.var.remote_user) }}
                    }}
                    location = /auth {{
                        internal;
                        fastcgi_pass 127.0.0.1:{auth};
                        fastcgi_pass_request_body off;
                        fastcgi_param CONTENT_LENGTH "";
                        fastcgi_param REQUEST_URI $request_uri;
                    }}
                    location = /sticky {{ proxy_pass http://sticky_backend; }}
                    location = /dynamic {{ proxy_pass http://dynamic_backend; }}
                    location = /ajp {{ ajp_pass 127.0.0.1:{ajp}; }}
                    location = /headers {{
                        more_set_headers "X-Test: present";
                        return 204;
                    }}
                }}
            }}
        """
        config_path = os.path.join(cls.temp.name, "nginx.conf")
        with open(config_path, "w", encoding="utf-8") as file:
            file.write(config)
        subprocess.run(["nginx", "-t", "-c", config_path], check=True)
        cls.nginx = subprocess.Popen(
            ["nginx", "-c", config_path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        for _ in range(100):
            if cls.nginx.poll() is not None:
                raise RuntimeError(cls.nginx.stderr.read().decode())
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("nginx did not start")

    @classmethod
    def tearDownClass(cls):
        cls.nginx.terminate()
        cls.nginx.communicate(timeout=10)
        for server in cls.servers:
            server.shutdown()
            server.server_close()
        cls.temp.cleanup()

    def request(self, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.getheaders(), response.read().decode()
        connection.close()
        return result

    def test_luajit_and_resty_core(self):
        status, _, body = self.request("/lua")
        self.assertEqual(status, 200)
        self.assertIn("LuaJIT 2.1", body)
        self.assertIn("0.1.34", body)

    def test_ajp_backend(self):
        status, _, body = self.request("/ajp")
        self.assertEqual((status, body), (200, "ok"))

    def test_headers_more(self):
        status, headers, _ = self.request("/headers")
        self.assertEqual(status, 204)
        self.assertIn(("X-Test", "present"), headers)

    def test_shibboleth_remote_user(self):
        status, _, body = self.request("/protected")
        self.assertEqual((status, body), (200, "alice\n"))

    def test_shibboleth_redirect_preserves_cookies(self):
        status, headers, _ = self.request("/protected?redirect")
        self.assertEqual(status, 302)
        self.assertEqual([v for k, v in headers if k.lower() == "set-cookie"],
                         ["first=1; Path=/", "second=2; Path=/"])
        self.assertIn(("Location", "/login"), headers)

    def test_native_sticky_cookie(self):
        status, headers, first = self.request("/sticky")
        self.assertEqual(status, 200)
        cookie = next(v.split(";", 1)[0] for k, v in headers if k.lower() == "set-cookie")
        for _ in range(3):
            status, _, backend = self.request("/sticky", {"Cookie": cookie})
            self.assertEqual((status, backend), (200, first))

    def test_native_dynamic_dns_updates(self):
        for _ in range(50):
            if self.request("/dynamic")[2] == "127.0.0.1":
                break
            time.sleep(0.1)
        else:
            self.fail("nginx did not resolve the upstream DNS address")
        self.dns.address = "127.0.0.2"
        for _ in range(50):
            time.sleep(0.1)
            if self.request("/dynamic")[2] == "127.0.0.2":
                break
        else:
            self.fail("nginx did not update the upstream DNS address")


if __name__ == "__main__":
    unittest.main()
