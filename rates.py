"""İma edilen TL faizi hesabı (örtülü faiz paritesi / CIP) ve vade tarihi yardımcıları."""
import calendar
import datetime as dt


def last_business_day(year, month):
    """VIOP döviz vadeli kontratları, vade ayının son iş gününde sona erer."""
    d = dt.date(year, month, calendar.monthrange(year, month)[1])
    while d.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        d -= dt.timedelta(days=1)
    return d


def days_to_maturity(year, month, today=None):
    today = today or dt.date.today()
    return (last_business_day(year, month) - today).days


def implied_try_rate(forward, spot, days, foreign_rate, basis=365, method="cip"):
    """Yıllık basit ima TL faizi (ondalık). foreign_rate ondalık (ör. 0.043).

    cip   : r_TL = ((F/S)·(1 + r_yab·t) − 1) / t
    basit : r_TL = r_yab + (F/S − 1) / t
    """
    if not forward or not spot or days is None or days <= 0:
        return None
    t = days / basis
    ratio = forward / spot
    if method == "cip":
        return (ratio * (1 + foreign_rate * t) - 1) / t
    return foreign_rate + (ratio - 1) / t


def cip_solve(solve_for, *, spot=None, forward=None, r_try=None, r_for=None, days=None, basis=365):
    """CIP: F = S·(1 + r_try·t) / (1 + r_for·t),  t = days/basis.

    Verilen değişkenlerden `solve_for` ile belirtileni çözer.
    Faizler ondalık (ör. 0.45), days gün cinsinden. Çözülemezse None.
    """
    t = (days / basis) if (days is not None and solve_for != "days") else None
    try:
        if solve_for == "forward":
            return spot * (1 + r_try * t) / (1 + r_for * t)
        if solve_for == "spot":
            return forward * (1 + r_for * t) / (1 + r_try * t)
        if solve_for == "r_try":
            return ((forward / spot) * (1 + r_for * t) - 1) / t
        if solve_for == "r_for":
            return (spot * (1 + r_try * t) / forward - 1) / t
        if solve_for == "days":
            denom = forward * r_for - spot * r_try
            if denom == 0:
                return None
            return (spot - forward) / denom * basis
    except (TypeError, ZeroDivisionError):
        return None
    return None


def forward_forward_rate(f1, f2, d1, d2, foreign_rate, basis=365, method="cip"):
    """İki ardışık vade arasındaki ima edilen TL kısa faizi ([t1, t2] dönemi).

    Piyasanın gelecekteki kısa faiz beklentisini gösterir.
    """
    if not f1 or not f2 or d1 is None or d2 is None or d2 <= d1:
        return None
    dt_days = d2 - d1
    t = dt_days / basis
    ratio = f2 / f1
    if method == "cip":
        return (ratio * (1 + foreign_rate * t) - 1) / t
    return foreign_rate + (ratio - 1) / t
