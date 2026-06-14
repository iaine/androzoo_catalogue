# AndroZoo Catalogue Search

Search the [AndroZoo](https://androzoo.uni.lu/) catalogue list
(`latest.csv.gz`) and export matching rows to a CSV file.

A full scan of the catalogue can take several minutes — far longer than a normal
HTTP request will wait — so in both versions below the search runs in the
background and the result is delivered when it is ready. The interface never
freezes and nothing times out.

The same backend (`androzoo.py`) powers two front-ends; pick the one that fits:

| Version             | When to use it                                       | Front-end |
| ------------------- | ---------------------------------------------------- | --------- |
| **Desktop** (`app.py`) | Local, single user. No server, no proxy — just run it. | pywebview |
| **Web** (`web/app_flask.py`) | Reachable from other machines / a browser. Sits behind Gunicorn + Nginx. | Flask |

`androzoo.py` has no UI dependency, so it is shared unchanged between the two;
only the front-end differs.

## How the desktop version works

The desktop app uses [pywebview](https://pywebview.flowrl.com/): a native
window rendering an HTML/JS front-end, with Python supplying the search logic.
There is no web server and no HTTP request, so there is no request timeout to
work around — long searches simply run off the UI thread.

```
┌─────────────────────┐   js_api call    ┌──────────────────┐
│  index.html + JS    │ ───────────────► │  app.py (Api)    │
│  (search form / UI) │                  │  starts a thread │
│                     │ ◄─────────────── │                  │
└─────────────────────┘  evaluate_js     └────────┬─────────┘
        ▲   onSearchDone / onSearchError          │
        │                                          ▼
        │                               ┌──────────────────────┐
        └─── shows count + CSV path ◄── │  androzoo.py         │
                                        │  zcat | grep | awk   │
                                        │  → result CSV        │
                                        └──────────────────────┘
```

Searching is done with a shell pipeline (`zcat | grep | awk`) rather than
parsing the ~25 GB CSV in Python, which keeps memory usage flat and is much
faster.

## Files

| File                  | Purpose                                                        |
| --------------------- | ------------------------------------------------------------- |
| `androzoo.py`         | Backend logic: build the search command, run it, save the CSV, optionally download APKs. Pure logic with no UI dependency, so it also works from the command line. |
| `app.py`              | pywebview desktop app. Wires the UI to the backend and runs searches on a background thread. |
| `assets/index.html`   | The search form UI.                                           |
| `assets/script.js`    | Front-end logic and the `onSearchDone` / `onSearchError` callbacks. |
| `assets/styles.css`   | Styling.                                                      |
| `web/app_flask.py`    | **Web version.** Flask app with the submit/poll/download job pattern. Reuses `androzoo.py`. |
| `web/templates/index.html` | Search form (Jinja template).                            |
| `web/static/script.js` | Browser logic: submit a search, poll for completion, download the CSV. |
| `web/static/styles.css` | Styling for the web UI.                                      |
| `web/gunicorn.conf.py` | Gunicorn configuration for serving the Flask app.            |
| `web/nginx.conf.sample` | Sample Nginx reverse-proxy config (HTTP and HTTPS).         |
| `web/requirements.txt` | Python dependencies for the web version.                     |

## Requirements

- Python 3.8+
- A local copy of the AndroZoo catalogue (`latest.csv.gz`)
- An [AndroZoo API key](https://androzoo.uni.lu/access) (only needed if you
  want to download APKs, not for searching)

Install the Python dependencies:

```bash
pip install pywebview requests
```

> On Linux, pywebview needs a GUI backend (e.g. `pip install pywebview[qt]` or
> `pywebview[gtk]`). See the
> [pywebview installation docs](https://pywebview.flowrl.com/guide/installation.html).

## Getting the catalogue

Download the catalogue list from AndroZoo (this is the file the app searches):

```bash
wget https://androzoo.uni.lu/static/lists/latest.csv.gz
```

The app does **not** decompress it — it streams through the gzip directly.

## Configuration

All paths and keys are set with environment variables (with sensible defaults):

| Variable          | Default                          | Description                                   |
| ----------------- | -------------------------------- | --------------------------------------------- |
| `AZ_CATALOGUE`    | `../../historical/latest.csv.gz` | Path to the gzipped catalogue.                |
| `AZ_APIKEY`       | _(empty)_                        | AndroZoo API key, required only for downloads.|
| `AZ_RESULTS_DIR`  | `results`                        | Where result CSVs are written.                |
| `AZ_EXTRACT_DIR`  | `extract`                        | Where downloaded APKs are saved.              |

Example:

```bash
export AZ_CATALOGUE=/data/androzoo/latest.csv.gz
export AZ_APIKEY=your_api_key_here
```

## Running the desktop app

From the project root:

```bash
python app.py
```

Fill in any combination of the search fields and click **Search**. Filters are
**additive** — supplying a package name *and* a store *and* a date range returns
only rows matching all of them. When the search finishes, the app shows the
number of matches and the full path to the result CSV.

### Search fields

- **Package name** — matches the `pkg_name` column. Use `*` as a wildcard at the
  start and/or end (e.g. `com.example.*`). Without `*`, the match is anchored to
  the whole field.
- **Market / store** — matches the `markets` column (e.g. `play.google.com`).
- **From / To date** — filters on the `dex_date` column (`YYYY-MM-DD`).

  > Note: AndroZoo warns that `dex_date` is unreliable for many Google Play apps
  > (often reported as 1980), so date filtering may exclude apps unexpectedly.

## Command-line use

`androzoo.py` also runs standalone, without the desktop UI:

```bash
# Search by package name (wildcard supported)
python androzoo.py --name "com.example.*"

# Combine filters
python androzoo.py --name "com.example.*" --store play.google.com --start 2020-01-01

# Search and then download the matching APKs (requires AZ_APIKEY)
python androzoo.py --name "com.example.app" --download
```

Run `python androzoo.py --help` for the full list of options.

## Output

Result CSVs are written to the results directory with a timestamped name, e.g.:

```
results/20250614-2129_com.example.csv
```

Each row is a full catalogue line:
`sha256, sha1, md5, dex_date, apk_size, pkg_name, vercode, vt_detection, vt_scan_date, dex_date, markets`.

Downloaded APKs (if you use `--download`) are saved to the extract directory,
named by their sha256.

## Running the web version (Flask + Gunicorn + Nginx)

The web version exposes the same search over HTTP so it can be reached from a
browser on another machine. Because the search can take minutes, it uses a
**submit / poll / download** pattern — the long search never runs inside a
request, so neither Flask, Gunicorn, nor Nginx ever time out:

```
POST /search                 -> starts a background job, returns a job_id at once
GET  /search/<id>            -> poll: running / done / failed
GET  /search/<id>/download   -> download the result CSV once done
```

The browser submits once, polls every few seconds, and offers a download link
when the job is done.

```
Browser ──HTTP──► Nginx ──proxy──► Gunicorn ──► Flask (app_flask.py)
                  (TLS, static)                      │
                                                     ▼
                                            androzoo.py (zcat|grep|awk)
                                                     │
                                            background thread → result CSV
```

### Project layout

The web app imports `androzoo.py`. Either copy it into `web/` or symlink it so
the two versions share one backend:

```bash
cd web
ln -s ../androzoo.py androzoo.py
```

### 1. Install dependencies

```bash
cd web
pip install -r requirements.txt
```

### 2. Run locally (development)

```bash
export AZ_CATALOGUE=/data/androzoo/latest.csv.gz
python app_flask.py          # http://127.0.0.1:5000
```

This uses Flask's built-in development server — fine for testing, not for
deployment.

### 3. Serve with Gunicorn (production WSGI server)

```bash
export AZ_CATALOGUE=/data/androzoo/latest.csv.gz
gunicorn -c gunicorn.conf.py app_flask:app
```

Gunicorn listens on `127.0.0.1:8000` (see `gunicorn.conf.py`).

> **Keep `workers = 1`.** The job registry lives in process memory, so a job
> started in one worker is invisible to another — a poll could hit a worker
> that never saw the job. One worker with several threads handles concurrent
> searches correctly for local / small-team use. To run multiple workers,
> move the `JOBS` dict into Redis or a database.

### 4. Put Nginx in front

`nginx.conf.sample` is a ready-to-edit reverse-proxy config: Nginx terminates
client connections, serves `/static/` directly, and proxies everything else to
Gunicorn. To install:

```bash
sudo cp nginx.conf.sample /etc/nginx/sites-available/androzoo
# edit server_name and the /static/ alias path to match your install
sudo ln -s /etc/nginx/sites-available/androzoo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

The sample includes a commented HTTPS block; for production, obtain a
certificate (e.g. with [certbot](https://certbot.eff.org/)) and use the
TLS variant to terminate HTTPS at Nginx.

### 5. (Optional) run Gunicorn as a service

So the app starts on boot and restarts on failure, create a systemd unit at
`/etc/systemd/system/androzoo.service`:

```ini
[Unit]
Description=AndroZoo catalogue search
After=network.target

[Service]
WorkingDirectory=/opt/androzoo/web
Environment=AZ_CATALOGUE=/data/androzoo/latest.csv.gz
Environment=AZ_RESULTS_DIR=/opt/androzoo/web/results
ExecStart=/usr/bin/gunicorn -c gunicorn.conf.py app_flask:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now androzoo
```

## A note on performance

Each search streams the entire catalogue through `zcat | grep | awk`, which
takes a few minutes on the full list. If you run searches frequently, a
worthwhile upgrade is to import `latest.csv` into a local SQLite database once,
with indexes on the columns you search (`pkg_name`, `sha256`, `markets`,
`dex_date`). That turns a multi-minute scan into a sub-second indexed lookup:

```bash
sqlite3 androzoo.db
sqlite> .mode csv
sqlite> .import latest.csv apks
sqlite> CREATE INDEX idx_pkg ON apks(pkg_name);
sqlite> CREATE INDEX idx_market ON apks(markets);
```

The backend would then query the database instead of building a shell pipeline.

## Troubleshooting

- **The window is blank or unstyled** — make sure you run `python app.py` from
  the project root so `assets/index.html` and its `styles.css` / `script.js` are
  found.
- **"Search failed" with a path error** — check `AZ_CATALOGUE` points to an
  existing `.csv.gz` file.
- **Downloads fail** — confirm `AZ_APIKEY` is set and valid.
