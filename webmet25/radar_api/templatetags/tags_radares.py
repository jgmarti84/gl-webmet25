from django import template

register = template.Library()

@register.filter
def format_ref(value):
    """
    Format numeric references:
      - integers -> no decimals ("3")
      - values >= 1 with fraction -> 1 decimal ("1.2")
      - abs(value) < 1 with fraction -> omit leading zero, 2 decimals (".25" or "-.25")
    Returns original value unchanged on invalid input.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return value

    abs_v = abs(v)
    frac = abs_v - int(abs_v)
    # consider tiny floating rounding
    if frac > 1e-9:
        if abs_v < 1:
            # keep sign, remove leading zero from "0.xx" -> ".xx"
            fmt = f"{abs_v:.2f}"  # "0.25"
            sign = '-' if v < 0 else ''
            return f"{sign}{fmt[1:]}"  # "-.25" or ".25"
        return f"{v:.1f}"
    return f"{v:.0f}"