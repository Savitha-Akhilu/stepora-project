from django import template

register = template.Library()

@register.filter
def dict_get(dictionary, key):
    """
    Safely get dictionary[key] in Django template.
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, [])
    return []
