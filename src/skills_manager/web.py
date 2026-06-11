from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .core import (
    DEFAULT_STATE_FILE,
    ConfigurationError,
    SkillsManager,
    SkillsManagerError,
    StateStore,
    expand_path,
)


STATIC_DIR = Path(__file__).with_name("static")


@dataclass
class WebContext:
    state_file: Path
    agent_paths: Mapping[str, str | Path] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def select_state_file(self, value: str) -> None:
        if not value.strip():
            raise ConfigurationError("状态文件路径不能为空")
        state_file = expand_path(value)
        StateStore(state_file).load()
        with self.lock:
            self.state_file = state_file

    def manager(self) -> SkillsManager:
        with self.lock:
            state_file = self.state_file
        return SkillsManager(StateStore(state_file), self.agent_paths)

    def dashboard(self) -> dict[str, Any]:
        with self.lock:
            state_file = self.state_file
        result = self.manager().dashboard()
        result["state_file_path"] = str(state_file)
        return result


class SkillsManagerHandler(BaseHTTPRequestHandler):
    context: WebContext

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self.send_json(HTTPStatus.OK, self.context.dashboard())
            return
        static_files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        if path not in static_files:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        filename, content_type = static_files[path]
        content = (STATIC_DIR / filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "仅接受 JSON"})
            return
        try:
            payload = self.read_json()
            path = urlparse(self.path).path
            if path == "/api/state-file":
                if not isinstance(payload["path"], str):
                    raise TypeError
                self.context.select_state_file(payload["path"])
            elif path == "/api/library":
                if not isinstance(payload["path"], str):
                    raise TypeError
                self.context.manager().set_library(payload["path"])
            elif path == "/api/toggle":
                if (
                    not isinstance(payload["project"], str)
                    or not isinstance(payload["agent"], str)
                    or not isinstance(payload["enabled"], bool)
                ):
                    raise TypeError
                self.context.manager().set_enabled(
                    payload["project"],
                    payload["agent"],
                    payload["enabled"],
                )
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                return
            self.send_json(HTTPStatus.OK, self.context.dashboard())
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "请求参数不完整"})
        except SkillsManagerError as exc:
            self.send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except OSError as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, status: HTTPStatus, data: dict[str, Any]) -> None:
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        return


def create_server(
    state_file: Path,
    host: str,
    port: int,
    agent_paths: Mapping[str, str | Path] | None = None,
) -> ThreadingHTTPServer:
    context = WebContext(
        state_file=expand_path(state_file),
        agent_paths=agent_paths,
    )
    handler = type(
        "ConfiguredSkillsManagerHandler",
        (SkillsManagerHandler,),
        {"context": context},
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    state_file: Path = DEFAULT_STATE_FILE,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    server = create_server(state_file, host, port)
    url = f"http://{host}:{server.server_port}"
    print(f"Skills Manager 已启动: {url}")
    print("按 Ctrl+C 停止。")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
