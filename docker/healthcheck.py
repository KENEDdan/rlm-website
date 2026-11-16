"""Container HEALTHCHECK: GET /healthz/ on the local gunicorn using an ALLOWED host name.

Django rejects unknown Host headers (400), and in production ALLOWED_HOSTS holds only the real domain,
so a plain request to 127.0.0.1 would always fail. Exit code 0 = healthy, 1 = unhealthy.
"""

import os
import sys
import urllib.request


def host_header(allowed: str) -> str:
    first = (allowed or "localhost").split(",")[0].strip()
    return first.lstrip(".").replace("*", "localhost") or "localhost"


def main() -> int:
    request = urllib.request.Request(
        "http://127.0.0.1:8000/healthz/",
        headers={"Host": host_header(os.environ.get("DJANGO_ALLOWED_HOSTS", ""))},
    )
    try:
        # Fixed local http URL, no user input.
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310  # nosec B310
            return 0 if response.status == 200 else 1
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
