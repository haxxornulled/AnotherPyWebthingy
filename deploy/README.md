# Deployment

This folder contains example deployment files for running the app behind Nginx and systemd.

## Files

- `nginx/anotherpywebthingy.conf` - reverse proxy template with the standard forwarded headers
- `systemd/anotherpywebthingy.service` - systemd unit that launches `server.py` on `127.0.0.1:7212`

## Typical install steps

1. Copy the repo to a stable path such as `/opt/AnotherPyWebthingy`.
2. Replace the placeholder domain names in the Nginx config.
3. Install the systemd unit into `/etc/systemd/system/`.
4. Install the Nginx config into `/etc/nginx/sites-available/` and enable it.
5. Run `systemctl daemon-reload`, `systemctl enable --now anotherpywebthingy`, and `nginx -t`.
6. If you want TLS, run `certbot --nginx` after DNS points at the host.

