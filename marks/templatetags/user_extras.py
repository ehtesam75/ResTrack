from django import template

register = template.Library()

def get_display_name(user):
    first = getattr(user, 'first_name', '').strip()
    if first:
        return first
    username = getattr(user, 'username', '')
    if '@' in username:
        return username.split('@')[0]
    return username

@register.filter
def display_name(user):
    return get_display_name(user)

@register.filter
def first_word(value):
    """Returns the first word of a string, or the whole string if no spaces."""
    if not isinstance(value, str):
        return value
    return value.split()[0] if value.split() else value
