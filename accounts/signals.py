from typing import Any

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from audit.models import AuditLog
from audit.services import log_event


@receiver(user_login_failed)
def _login_failed(sender: Any, credentials: dict[str, Any], request: Any = None, **kwargs: Any) -> None:
    attempted = str(credentials.get("username", ""))[:254]
    log_event(AuditLog.Action.LOGIN_FAILED, request=request, actor_email=attempted)
