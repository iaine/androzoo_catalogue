# Gunicorn configuration for the AndroZoo Flask app.
#
# Run with:   gunicorn -c gunicorn.conf.py app_flask:app
#
# IMPORTANT: keep workers = 1 (or use a shared job store).
# The job registry in app_flask.py lives in process memory, so a job
# started in one worker is invisible to another. With the default
# multi-worker setup, a poll request could land on a worker that has
# never heard of the job. One worker keeps it simple and correct for
# local / single-user use. To scale out, move JOBS into Redis.

bind = "127.0.0.1:8000"
workers = 1
threads = 4          # allow concurrent searches within the one worker

# Searches run on background threads and return immediately, so requests
# themselves are short. This generous timeout is just a safety margin.
timeout = 120
graceful_timeout = 30
keepalive = 5

accesslog = "-"      # log to stdout
errorlog = "-"
