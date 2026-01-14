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
