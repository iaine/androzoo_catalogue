'''
Flask web front-end for the AndroZoo catalogue search.

A full catalogue scan can take several minutes, far longer than a normal
HTTP request (and any reverse proxy) will wait. So the search does NOT run
inside the request. Instead:

    POST /search          -> starts a background job, returns a job_id at once
    GET  /search/<id>     -> poll job status (running / done / failed)
    GET  /search/<id>/download -> download the result CSV once done

The browser submits once, polls until done, then downloads. The long search
never touches the request lifecycle, so Flask/Gunicorn/Nginx never time out.

Reuses androzoo.py unchanged.
'''
import os
import uuid
import threading

from flask import Flask, request, jsonify, send_file, render_template

from androzoo import AndroZoo

app = Flask(__name__)
az = AndroZoo()

# In-memory job registry. Fine for a single Gunicorn worker / local use.
# For multiple workers or persistence, back this with Redis or a database.
JOBS = {}
JOBS_LOCK = threading.Lock()


def _set_job(job_id, **fields):
    with JOBS_LOCK:
        JOBS.setdefault(job_id, {}).update(fields)


def _get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def _run_search(job_id, params):
    '''Background worker: runs the search and records the outcome.'''
    try:
        info = az.search(**params)
        _set_job(job_id, status="done",
                 path=info["path"], matches=info["matches"])
    except Exception as e:  # noqa: BLE001 - report message to the client
        _set_job(job_id, status="failed", error=str(e))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json(silent=True) or request.form
    params = {
        "apk_name": (data.get("apk_name") or "").strip(),
        "store": (data.get("store") or "").strip(),
        "start": (data.get("start") or "").strip(),
        "end": (data.get("end") or "").strip(),
    }
    if not any(params.values()):
        return jsonify(error="Provide at least one search filter."), 400

    job_id = uuid.uuid4().hex
    _set_job(job_id, status="running")
    threading.Thread(
        target=_run_search, args=(job_id, params), daemon=True
    ).start()
    # 202 Accepted: work started, result not ready yet.
    return jsonify(job_id=job_id, status="running"), 202


@app.route("/search/<job_id>")
def status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify(error="Unknown job id."), 404
    # Don't leak the server filesystem path to the client; expose a count
    # and a download URL instead.
    payload = {"status": job["status"]}
    if job["status"] == "done":
        payload["matches"] = job["matches"]
        payload["download_url"] = "/search/{}/download".format(job_id)
    elif job["status"] == "failed":
        payload["error"] = job.get("error", "Unknown error.")
    return jsonify(payload)


@app.route("/search/<job_id>/download")
def download(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify(error="Unknown job id."), 404
    if job.get("status") != "done":
        return jsonify(error="Result not ready."), 409
    path = job["path"]
    if not os.path.exists(path):
        return jsonify(error="Result file no longer exists."), 410
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path),
                     mimetype="text/csv")


if __name__ == "__main__":
    # Development server only. For deployment use Gunicorn (see README).
    app.run(host="127.0.0.1", port=5000, debug=True)
