"""Production settings. Every secret must come from the environment."""

from .base import *  # noqa: F403
from .base import SENTRY_DSN, env

DEBUG = False

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=63072000)  # 2 years
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-rlm_sid"
CSRF_COOKIE_NAME = "__Host-csrftoken"
TRUST_PROXY_IP_HEADER = env.bool("TRUST_PROXY_IP_HEADER", default=True)
# Bot protection is mandatory in production (rule 7). A missing key fails closed and is flagged by
# `manage.py check --deploy` (core.checks), instead of silently switching Turnstile off.
TURNSTILE_ENABLED = env.bool("TURNSTILE_ENABLED", default=True)

LOGGING["root"]["level"] = env("LOG_LEVEL", default="WARNING")

if SENTRY_DSN:
    import sentry_sdk

    from core.logging import sentry_before_send

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        before_send=sentry_before_send,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
