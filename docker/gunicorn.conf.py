"""Gunicorn settings for production."""

import multiprocessing
import os

bind = "0.0.0.0:8000"  # only reachable on the internal Docker network
workers = int(os.environ.get("GUNICORN_WORKERS", min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = 30
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
worker_tmp_dir = "/dev/shm"  # noqa: S108  # nosec B108 - tmpfs for worker heartbeats (gunicorn docs)
accesslog = "-"
errorlog = "-"
# Never log query strings (tokens) or client IPs beyond what's needed.
access_log_format = '%(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)ss'
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "*")
limit_request_line = 4094
limit_request_fields = 100
