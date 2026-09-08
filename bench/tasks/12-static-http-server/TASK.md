# Task: tiny static HTTP server

Write `run.sh PORT` (any language) that starts an HTTP server on
`127.0.0.1:PORT` serving static files from `./site` (so `GET /index.html`
returns `site/index.html`'s bytes, `GET /about.txt` returns
`site/about.txt`'s bytes) and answers `GET /health` with HTTP 200 and JSON
body `{"status": "ok"}`. `run.sh` must block/serve until killed.
