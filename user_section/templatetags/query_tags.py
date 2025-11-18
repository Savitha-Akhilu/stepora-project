# user_section/templatetags/query_tags.py
from django import template

register = template.Library()

@register.simple_tag
def remove_param(request, param):
    """
    Removes one query parameter while preserving others.
    """
    query = request.GET.copy()
    query.pop(param, None)

    # keep Men (gender) page intact

    query_string = query.urlencode()
    return f"?{query_string}" if query_string else "?"
