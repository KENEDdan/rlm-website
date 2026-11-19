from typing import Any

from django import template

register = template.Library()


@register.filter
def get_param(params: Any, key: str) -> str:
    try:
        return str(params.get(key, ""))
    except AttributeError:
        return ""


@register.filter
def department_name(code: str) -> str:
    from portal.models import Department

    return Department.Code(code).label if code in Department.Code.values else code
