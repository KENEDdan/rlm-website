"""Base settings shared by every environment. Secrets come only from the environment."""

from __future__ import annotations

from pathlib import Path

import environ
from celery.schedules import crontab
from csp.constants import NONCE, NONE, SELF

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# A local .env is read only if present (dev convenience). Production injects real env vars.
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
SITE_URL: str = env("SITE_URL", default="http://localhost:8010").rstrip("/")

# Obscure admin path, e.g. "manage-x7k2/". "/admin/" is intentionally not routed.
ADMIN_URL: str = env("DJANGO_ADMIN_URL", default="staff-portal/").strip("/") + "/"
# Staff portal (department dashboards). Separate from the Django admin, same 2FA/lockout/audit rules.
PORTAL_URL: str = env("PORTAL_URL", default="portal/").strip("/") + "/"

INSTALLED_APPS = [
    "core.apps.RLMAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    # third party
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "csp",
    # local
    "core.apps.CoreConfig",
    "accounts",
    "audit",
    "branches",
    "programs",
    "leadership",
    "events",
    "registrations",
    "prayer",
    "contact",
    "newsletter",
    "media_library",
    "resources",
    "news",
    "giving",
    "portal",
    "membership",
    "finance",
    "logistics",
    "missions",
    "discipleship",
    "communications",
    "development",
]

MIDDLEWARE = [
    "core.middleware.RealIPMiddleware",
    "core.middleware.RequestSizeLimitMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "accounts.middleware.StaffTwoFactorMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "csp.context_processors.nonce",
                "core.context_processors.site",
                "portal.context_processors.portal",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/0"),
        "KEY_PREFIX": "rlm",
    }
}

# ---------------------------------------------------------------- auth
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.ComplexityValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "portal:home"

# django-axes: lock a username+IP pair after 5 failures for 1 hour.
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = env.float("AXES_COOLOFF_HOURS", default=1.0)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_FORM_FIELD = "username"
AXES_LOCKOUT_TEMPLATE = "accounts/locked_out.html"
AXES_VERBOSE = False

# django-otp
OTP_TOTP_ISSUER = env("OTP_ISSUER", default="Rebuilding Lives Ministry")

# ---------------------------------------------------------------- sessions & cookies
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 2)  # 2 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True  # sliding idle timeout
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "rlm_sid"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_AGE = None  # browser-session cookie: the site sets no long-lived cookies at all
CSRF_FAILURE_VIEW = "core.views.csrf_failure"

# ---------------------------------------------------------------- security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=(), interest-cohort=()"
)

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF, NONCE],
        "style-src": [SELF, NONCE],
        "img-src": [SELF, "data:", "https://i.ytimg.com"],
        "font-src": [SELF],
        "connect-src": [SELF],
        "frame-src": ["https://www.youtube-nocookie.com", "https://challenges.cloudflare.com"],
        "frame-ancestors": [NONE],
        "form-action": [SELF],
        "base-uri": [SELF],
        "object-src": [NONE],
    }
}
# Extra script origins, e.g. a self-hosted analytics host ("https://stats.example.org").
CSP_EXTRA_SCRIPT_SRC: list[str] = env.list("CSP_EXTRA_SCRIPT_SRC", default=[])
CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"] += [
    "https://challenges.cloudflare.com",
    *CSP_EXTRA_SCRIPT_SRC,
]
CONTENT_SECURITY_POLICY["DIRECTIVES"]["connect-src"] += CSP_EXTRA_SCRIPT_SRC

# ---------------------------------------------------------------- i18n
LANGUAGE_CODE = "en"
TIME_ZONE = env("TIME_ZONE", default="Africa/Juba")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- static & media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 365
# Uploaded media live outside the code tree and the static root.
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "data" / "media")))
MEDIA_URL = "/uploads/"
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # bigger uploads are streamed to a temporary file
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # form fields other than files (no form needs more)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.TemporaryFileUploadHandler"]
# Whole request body caps (core.middleware.RequestSizeLimitMiddleware; Caddy enforces the same cap first).
# Public pages take no uploads at all; staff pages up to the largest upload policy (sermon audio 50 MB).
MAX_PUBLIC_REQUEST_BYTES = env.int("MAX_PUBLIC_REQUEST_BYTES", default=1 * 1024 * 1024)
MAX_STAFF_REQUEST_BYTES = env.int("MAX_STAFF_REQUEST_BYTES", default=60 * 1024 * 1024)

# Upload formats and limits are policies in core/upload_policy.py (Super Admin adjusts limits in the admin).
# Optional ClamAV scan of every upload before it is stored (docker compose --profile clamav). Fails closed.
CLAMAV_ENABLED = env.bool("CLAMAV_ENABLED", default=False)
CLAMAV_HOST = env("CLAMAV_HOST", default="clamav")
CLAMAV_PORT = env.int("CLAMAV_PORT", default=3310)
CLAMAV_TIMEOUT = env.int("CLAMAV_TIMEOUT", default=30)

# Private uploads (receipts, permits, member documents...): never under MEDIA_ROOT, never served directly.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "data" / "private")))

# ---------------------------------------------------------------- staff accounts & portal rules
SUPER_ADMIN_LIMIT = env.int("SUPER_ADMIN_LIMIT", default=2)  # at most this many active Super Admins
INVITE_TTL_HOURS = env.int("INVITE_TTL_HOURS", default=48)
INVITE_RATE = env("INVITE_RATE", default="20/h")  # invitations a Super Admin may send per hour
REAUTH_WINDOW_SECONDS = env.int(
    "REAUTH_WINDOW_SECONDS", default=300
)  # password + 2FA again before sensitive steps
DORMANT_FLAG_DAYS = env.int("DORMANT_FLAG_DAYS", default=60)
DORMANT_DISABLE_DAYS = env.int("DORMANT_DISABLE_DAYS", default=90)
REPORT_DUE_DAY = env.int("REPORT_DUE_DAY", default=10)  # monthly reports due by this day of the next month

# ---------------------------------------------------------------- encryption
# Comma separated Fernet keys. The FIRST key encrypts; all keys decrypt (rotation).
FIELD_ENCRYPTION_KEYS: list[str] = env.list("FIELD_ENCRYPTION_KEYS")
# Separate secret for HMAC blind indexes (email lookups) so it never doubles as an encryption key.
BLIND_INDEX_KEY: str = env("BLIND_INDEX_KEY")

# ---------------------------------------------------------------- email & celery
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Rebuilding Lives Ministry <no-reply@example.org>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULE = {
    "purge-expired-submissions": {
        "task": "core.tasks.purge_expired_submissions",
        "schedule": 60 * 60 * 24,
    },
    "account-integrity-check": {
        "task": "accounts.tasks.account_integrity_check",
        "schedule": 60 * 15,
    },
    "dormant-accounts": {
        "task": "accounts.tasks.dormant_accounts",
        "schedule": 60 * 60 * 24,
    },
    # Ministry decision 8: unsuccessful applications deleted after the retention period (daily, 02:30) and a
    # monthly count of applications nearing deletion for department heads (1st of the month, 07:00).
    "purge-unsuccessful-applications": {
        "task": "core.tasks.purge_unsuccessful_applications",
        "schedule": crontab(hour=2, minute=30),
    },
    "report-applications-nearing-purge": {
        "task": "core.tasks.report_applications_nearing_purge",
        "schedule": crontab(day_of_month="1", hour=7, minute=0),
    },
}

# ---------------------------------------------------------------- Turnstile
TURNSTILE_SITE_KEY: str = env("TURNSTILE_SITE_KEY", default="")
TURNSTILE_SECRET_KEY: str = env("TURNSTILE_SECRET_KEY", default="")
TURNSTILE_ENABLED: bool = env.bool("TURNSTILE_ENABLED", default=bool(TURNSTILE_SECRET_KEY))

# ---------------------------------------------------------------- rate limits
RATELIMIT_USE_CACHE = "default"
RATELIMIT_VIEW = "core.views.ratelimited"
RATELIMIT_ENABLE = env.bool("RATELIMIT_ENABLE", default=True)
FORM_RATE = env("FORM_RATE", default="5/h")
LOGIN_RATE = env("LOGIN_RATE", default="10/m")

# Trust X-Real-IP only when running behind our own reverse proxy (set in prod).
TRUST_PROXY_IP_HEADER: bool = env.bool("TRUST_PROXY_IP_HEADER", default=False)

# ---------------------------------------------------------------- payments
PAYMENT_WEBHOOK_SECRETS: dict[str, str] = {
    "gateway": env("PAYMENT_WEBHOOK_SECRET", default=""),
}

# ---------------------------------------------------------------- logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"scrub_pii": {"()": "core.logging.PIIScrubFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "filters": ["scrub_pii"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.security.DisallowedHost": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

SENTRY_DSN: str = env("SENTRY_DSN", default="")
