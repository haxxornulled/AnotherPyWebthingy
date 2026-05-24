# Config Driven Python Web Server

This is a fun test server project, not a production app.

It was built to be a clean target for trying out reverse proxies, TLS, headers, and basic deployment glue without dragging in a big framework. If you want to test Nginx proxy behavior, certbot flows, forwarding headers, or a simple systemd service, this project is meant to make that easy.

## What We Designed

- A tiny HTTP server built with the Python standard library only
- A config-driven request model in `config.json`
- Exact and wildcard route matching
- Automatic `HEAD` and `OPTIONS` behavior
- Text and JSON responses with placeholder expansion from request context
- A simple deployment layout for Nginx and systemd

## Why It Exists

- Test Nginx reverse proxy routing
- Verify forwarded headers like `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`
- Exercise certbot and TLS setup
- Provide a lightweight backend for smoke tests and experiments
- Keep the app small enough that the config is easy to read and change

## Project Files

- `server.py` - the server implementation
- `config.json` - active runtime config
- `config.example.json` - reference config with the same starter setup
- `deploy/` - example Nginx and systemd deployment files

## Running It

```bash
python3 server.py --config config.json
```

You can also override the bound host or port at startup:

```bash
python3 server.py --config config.json --host 127.0.0.1 --port 8088
```

The bundled config listens on `127.0.0.1:7212`, which is a good fit for putting Nginx in front of it.

## Default Endpoints

- `GET /` - quick welcome text
- `GET /health` - JSON health payload
- `GET /meta` - JSON server metadata and known routes
- `POST /echo` - echoes request data back as JSON

## Config Shape

The config has three top-level sections:

- `server` - `name`, `version`, `host`, `port`
- `defaults` - default content type and headers
- `routes` - list of route definitions

Each route can define:

- `method` or `methods`
- `path`
- `status`
- `content_type`
- `headers`
- `body`
- `json`

## Matching Rules

- Paths are matched exactly unless the route ends with `*`
- `HEAD` reuses any matching `GET` route
- `OPTIONS` returns an automatic `Allow` header whenever the path exists
- Missing routes return `404`
- Path matches with the wrong method return `405`

## Placeholder Examples

Useful placeholders include:

- `app_name`
- `version`
- `host`
- `port`
- `method`
- `path`
- `full_path`
- `query_params`
- `headers`
- `body_text`
- `body_raw`
- `request_count`
- `uptime_seconds`
- `known_paths`
- `known_routes`
- `config_source`

Exact placeholder strings keep the underlying type when possible, so a JSON route can use `{request_count}` as a number or `{known_paths}` as a list.

## Deployment

Example Nginx and systemd deployment files live under [`deploy/`](deploy/README.md).
