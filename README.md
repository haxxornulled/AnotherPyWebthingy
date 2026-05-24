# Config Driven Python Web Server

A small HTTP server built with the Python standard library only.

## What it does

- Loads behavior from `config.json`
- Supports exact and wildcard path routing
- Handles `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, and automatic `OPTIONS`
- Renders simple placeholders like `{app_name}` and `{request_count}` from request context
- Supports text bodies and structured JSON route responses

## Files

- `server.py` - the server implementation
- `config.json` - active runtime config
- `config.example.json` - reference config with the same starter setup

## Run

```bash
python3 server.py --config config.json
```

You can also override the bound host or port at startup:

```bash
python3 server.py --config config.json --host 127.0.0.1 --port 8088
```

## Default endpoints

- `GET /` - quick welcome text
- `GET /health` - JSON health payload
- `GET /meta` - JSON server metadata and known routes
- `POST /echo` - echoes request data back as JSON

## Config shape

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

## Matching rules

- Paths are matched exactly unless the route ends with `*`
- `HEAD` reuses any matching `GET` route
- `OPTIONS` returns an automatic `Allow` header whenever the path exists
- Missing routes return `404`
- Path matches with the wrong method return `405`

## Placeholder examples

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
