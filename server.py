#!/usr/bin/env python3
"""Config-driven HTTP server built with the Python standard library only."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
FULL_PLACEHOLDER_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")
METHOD_ORDER = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@dataclass(frozen=True)
class RouteDefinition:
    methods: tuple[str, ...]
    path: str
    status: int = 200
    content_type: str | None = None
    headers: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    json_body: Any = None

    @property
    def is_wildcard(self) -> bool:
        return self.path.endswith("*")

    @property
    def path_prefix(self) -> str:
        return self.path[:-1] if self.is_wildcard else self.path

    def matches_path(self, request_path: str) -> bool:
        if self.is_wildcard:
            return request_path.startswith(self.path_prefix)
        return request_path == self.path


@dataclass
class AppState:
    name: str
    version: str
    host: str
    port: int
    config_path: Path
    defaults: dict[str, Any]
    routes: list[RouteDefinition]
    known_paths: list[str]
    known_routes: list[str]
    started_at: float = field(default_factory=time.monotonic)
    request_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def config_source(self) -> str:
        return str(self.config_path.resolve())

    @property
    def json_indent(self) -> int:
        raw = self.defaults.get("json_indent", 2)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 2

    @property
    def text_content_type(self) -> str:
        return str(self.defaults.get("content_type", "text/plain; charset=utf-8"))

    @property
    def json_content_type(self) -> str:
        return str(self.defaults.get("json_content_type", "application/json; charset=utf-8"))


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_methods(route: dict[str, Any]) -> tuple[str, ...]:
    raw_methods: list[str] = []

    if "method" in route and route["method"] is not None:
        raw_methods.append(str(route["method"]))

    methods_value = route.get("methods")
    if methods_value is not None:
        if isinstance(methods_value, str):
            raw_methods.append(methods_value)
        else:
            raw_methods.extend(str(method) for method in methods_value)

    if not raw_methods:
        raw_methods = ["GET"]

    normalized: list[str] = []
    for method in raw_methods:
        upper = method.strip().upper()
        if upper and upper not in normalized:
            normalized.append(upper)

    return tuple(normalized)


def parse_route(route: dict[str, Any]) -> RouteDefinition:
    path = str(route.get("path", "/"))
    status_raw = route.get("status", 200)
    try:
        status = int(status_raw)
    except (TypeError, ValueError):
        status = 200

    headers = dict(route.get("headers") or {})
    return RouteDefinition(
        methods=normalize_methods(route),
        path=path,
        status=status,
        content_type=(str(route["content_type"]) if route.get("content_type") is not None else None),
        headers=headers,
        body=route.get("body"),
        json_body=route.get("json"),
    )


def build_routes(config: dict[str, Any]) -> list[RouteDefinition]:
    raw_routes = config.get("routes") or []
    return [parse_route(route) for route in raw_routes]


def build_known_paths(routes: list[RouteDefinition]) -> list[str]:
    known: list[str] = []
    for route in routes:
        if route.path not in known:
            known.append(route.path)
    return known


def build_known_routes(routes: list[RouteDefinition]) -> list[str]:
    known: list[str] = []
    for route in routes:
        method_label = ", ".join(route.methods)
        known.append(f"{method_label} {route.path}")
    return known


def render_text(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            return match.group(0)
        return str(context[key])

    return PLACEHOLDER_RE.sub(replace, template)


def render_structure(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        full_match = FULL_PLACEHOLDER_RE.match(value)
        if full_match:
            key = full_match.group(1)
            if key in context:
                return context[key]
        return render_text(value, context)

    if isinstance(value, list):
        return [render_structure(item, context) for item in value]

    if isinstance(value, dict):
        return {str(key): render_structure(item, context) for key, item in value.items()}

    return value


def stringify_query_params(query_params: dict[str, list[str]]) -> str:
    if not query_params:
        return "(none)"
    parts: list[str] = []
    for key, values in query_params.items():
        for value in values:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def stringify_headers(headers: dict[str, str]) -> str:
    if not headers:
        return "(none)"
    return ", ".join(f"{key}: {value}" for key, value in headers.items())


def build_context(
    state: AppState,
    method: str,
    path: str,
    full_path: str,
    request_headers: dict[str, str],
    query_params: dict[str, list[str]],
    request_body: bytes,
    client_address: tuple[str, int],
) -> dict[str, Any]:
    body_text = request_body.decode("utf-8", errors="replace")
    return {
        "app_name": state.name,
        "version": state.version,
        "host": state.host,
        "port": state.port,
        "method": method,
        "path": path,
        "full_path": full_path,
        "client_address": f"{client_address[0]}:{client_address[1]}",
        "query_params": stringify_query_params(query_params),
        "query_params_json": json.dumps(query_params, indent=2, sort_keys=True),
        "headers": stringify_headers(request_headers),
        "headers_json": json.dumps(request_headers, indent=2, sort_keys=True),
        "body_size": len(request_body),
        "body_raw": body_text,
        "body_text": body_text,
        "request_count": state.request_count,
        "uptime_seconds": round(time.monotonic() - state.started_at, 3),
        "known_paths": state.known_paths,
        "known_routes": state.known_routes,
        "config_source": state.config_source,
    }


def load_state(config_path: Path, host_override: str | None, port_override: int | None) -> AppState:
    raw = load_json_file(config_path)
    server_config = dict(raw.get("server") or {})
    defaults = dict(raw.get("defaults") or {})
    routes = build_routes(raw)

    name = str(server_config.get("name", "Config Driven Python Web Server"))
    version = str(server_config.get("version", "1.0.0"))
    host = host_override or str(server_config.get("host", "127.0.0.1"))
    port_value = port_override if port_override is not None else server_config.get("port", 7212)
    try:
        port = int(port_value)
    except (TypeError, ValueError):
        port = 7212

    return AppState(
        name=name,
        version=version,
        host=host,
        port=port,
        config_path=config_path,
        defaults=defaults,
        routes=routes,
        known_paths=build_known_paths(routes),
        known_routes=build_known_routes(routes),
    )


def route_matches_path(route: RouteDefinition, request_path: str) -> bool:
    return route.matches_path(request_path)


def allowed_methods_for_path(routes: list[RouteDefinition], request_path: str) -> list[str]:
    methods: list[str] = []

    for route in routes:
        if not route_matches_path(route, request_path):
            continue

        for method in route.methods:
            if method not in methods:
                methods.append(method)

        if "GET" in route.methods and "HEAD" not in methods:
            methods.append("HEAD")

    if methods:
        if "OPTIONS" not in methods:
            methods.append("OPTIONS")
        return sort_methods(methods)

    return []


def sort_methods(methods: list[str]) -> list[str]:
    order = {method: index for index, method in enumerate(METHOD_ORDER)}
    return sorted(dict.fromkeys(methods), key=lambda item: order.get(item, len(METHOD_ORDER) + 1))


def find_route(routes: list[RouteDefinition], method: str, request_path: str) -> RouteDefinition | None:
    method = method.upper()

    for route in routes:
        if route_matches_path(route, request_path) and method in route.methods:
            return route

    if method == "HEAD":
        for route in routes:
            if route_matches_path(route, request_path) and "GET" in route.methods:
                return route

    return None


def path_exists(routes: list[RouteDefinition], request_path: str) -> bool:
    return any(route_matches_path(route, request_path) for route in routes)


def build_body(route: RouteDefinition, context: dict[str, Any], state: AppState) -> tuple[bytes, str]:
    if route.json_body is not None:
        payload = render_structure(route.json_body, context)
        body = json.dumps(payload, indent=state.json_indent, ensure_ascii=False).encode("utf-8")
        content_type = route.content_type or state.json_content_type
        return body, content_type

    if route.body is None:
        return b"", route.content_type or state.text_content_type

    rendered = render_structure(route.body, context)
    if isinstance(rendered, str):
        body_text = rendered
    else:
        body_text = json.dumps(rendered, indent=state.json_indent, ensure_ascii=False)

    return body_text.encode("utf-8"), route.content_type or state.text_content_type


def response_headers_for(route: RouteDefinition | None, context: dict[str, Any], state: AppState) -> dict[str, str]:
    headers: dict[str, str] = {}

    defaults = state.defaults.get("headers") or {}
    if isinstance(defaults, dict):
        rendered_defaults = render_structure(defaults, context)
        for key, value in rendered_defaults.items():
            headers[str(key)] = str(value)

    if route is not None:
        rendered_route_headers = render_structure(route.headers, context)
        for key, value in rendered_route_headers.items():
            headers[str(key)] = str(value)

    return headers


def make_handler(state: AppState):
    class ConfigDrivenRequestHandler(BaseHTTPRequestHandler):
        server_version = f"{state.name}/{state.version}"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_HEAD(self) -> None:  # noqa: N802
            self._handle("HEAD")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def do_PUT(self) -> None:  # noqa: N802
            self._handle("PUT")

        def do_PATCH(self) -> None:  # noqa: N802
            self._handle("PATCH")

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle("DELETE")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._handle("OPTIONS")

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            message = "%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args)
            sys.stderr.write(message)

        def _read_request_body(self) -> bytes:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return b""
            return self.rfile.read(length)

        def _handle(self, method: str) -> None:
            with state.lock:
                state.request_count += 1

            parsed = urlsplit(self.path)
            request_path = unquote(parsed.path or "/")
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            full_path = request_path + (f"?{parsed.query}" if parsed.query else "")
            request_body = self._read_request_body()
            request_headers = {key: value for key, value in self.headers.items()}
            context = build_context(
                state=state,
                method=method,
                path=request_path,
                full_path=full_path,
                request_headers=request_headers,
                query_params=query_params,
                request_body=request_body,
                client_address=self.client_address,
            )

            if method == "OPTIONS":
                if not path_exists(state.routes, request_path):
                    self._send_simple_response(HTTPStatus.NOT_FOUND, "Not Found\n", context)
                    return

                allow = allowed_methods_for_path(state.routes, request_path)
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Allow", ", ".join(allow))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            route = find_route(state.routes, method, request_path)
            if route is None:
                if path_exists(state.routes, request_path):
                    allow = allowed_methods_for_path(state.routes, request_path)
                    body_text = f"Method Not Allowed\nAllowed: {', '.join(allow)}\n"
                    self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
                    self.send_header("Allow", ", ".join(allow))
                    self.send_header("Content-Type", state.text_content_type)
                    self.send_header("Content-Length", str(len(body_text.encode("utf-8"))))
                    self.end_headers()
                    if method != "HEAD":
                        self.wfile.write(body_text.encode("utf-8"))
                    return

                self._send_simple_response(HTTPStatus.NOT_FOUND, "Not Found\n", context)
                return

            body_bytes, content_type = build_body(route, context, state)
            headers = response_headers_for(route, context, state)
            headers.setdefault("Content-Type", content_type)

            self.send_response(route.status)
            for header_name, header_value in headers.items():
                self.send_header(header_name, str(header_value))
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()

            if method != "HEAD" and route.status not in (HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED):
                self.wfile.write(body_bytes)

        def _send_simple_response(self, status: HTTPStatus, message: str, context: dict[str, Any]) -> None:
            body_bytes = message.encode("utf-8")
            self.send_response(status)
            headers = response_headers_for(None, context, state)
            headers.setdefault("Content-Type", state.text_content_type)
            for header_name, header_value in headers.items():
                self.send_header(header_name, str(header_value))
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body_bytes)

    return ConfigDrivenRequestHandler


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def run_server(state: AppState) -> None:
    handler = make_handler(state)
    server = ReusableThreadingHTTPServer((state.host, state.port), handler)
    server.daemon_threads = True

    print(
        f"{state.name} {state.version} listening on {state.host}:{state.port} "
        f"(config: {state.config_source})",
        file=sys.stderr,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the config-driven Python web server.")
    parser.add_argument("--config", default="config.json", help="Path to the JSON config file.")
    parser.add_argument("--host", help="Override the configured host.")
    parser.add_argument("--port", type=int, help="Override the configured port.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    state = load_state(config_path, args.host, args.port)
    run_server(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
