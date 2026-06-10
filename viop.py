"""VIOP döviz vadeli kontrat + spot kur veri çekme (kaynak: Bigpara / Foreks, ~15 dk gecikmeli)."""
import re
import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    )
}
VIOP_URL = "https://bigpara.hurriyet.com.tr/viop-varant/viop-verileri/"
DOVIZ_URL = "https://bigpara.hurriyet.com.tr/doviz/"

# Kontrat sembol formatı: F_<DAYANAK><AY><YIL>  ör. F_USDTRY0626 = Haziran 2026
SYM_RE = re.compile(r"^F_(USDTRY|EURTRY|EURUSD)(\d{2})(\d{2})$")


def _to_float(s):
    """Türkçe sayı biçimini ('46,97', '7.857.461', '%-0,04') float'a çevirir."""
    if s is None:
        return None
    s = s.strip().replace("%", "").replace(" ", "")
    if not s or s in ("-", "—"):
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fetch_viop_fx(underlyings=("USDTRY", "EURTRY"), timeout=20):
    """VIOP döviz vadeli kontratlarını liste of dict olarak döndürür."""
    r = requests.get(VIOP_URL, headers=UA, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for tr in soup.select("tr[data-symbol-id]"):
        m = SYM_RE.match(tr.get("data-symbol-id", ""))
        if not m:
            continue
        underlying, mm, yy = m.group(1), int(m.group(2)), 2000 + int(m.group(3))
        if underlying not in underlyings:
            continue
        cols = {td.get("data-column"): td.get_text(strip=True) for td in tr.find_all("td")}
        out.append(
            {
                "symbol": tr["data-symbol-id"],
                "underlying": underlying,
                "maturity_month": mm,
                "maturity_year": yy,
                "last": _to_float(cols.get("c")),
                "prev_close": _to_float(cols.get("yc")),
                "high": _to_float(cols.get("h")),
                "low": _to_float(cols.get("l")),
                "volume": _to_float(cols.get("tv")),  # işlem gören kontrat adedi (likidite)
                "time": cols.get("dt", ""),
            }
        )
    out.sort(key=lambda d: (d["underlying"], d["maturity_year"], d["maturity_month"]))
    return out


def fetch_spot(timeout=20):
    """Spot USDTRY/EURTRY. Birincil: Bigpara (futures ile aynı kaynak); yedek: er-api."""
    spot = {}
    try:
        r = requests.get(DOVIZ_URL, headers=UA, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for pair in ("USDTRY", "EURTRY"):
            el = soup.select_one(f'tr[data-symbol-id="{pair}"]')
            if el:
                tds = el.find_all("td")
                val = _to_float(tds[2].get_text(strip=True)) if len(tds) > 2 else None
                if val:
                    spot[pair] = val
        if {"USDTRY", "EURTRY"} <= set(spot):
            spot["source"] = "bigpara"
            return spot
    except Exception:
        pass
    # Yedek kaynak (günlük, keysiz)
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=timeout).json()
        rates = r["rates"]
        spot.setdefault("USDTRY", rates["TRY"])
        spot.setdefault("EURTRY", rates["TRY"] / rates["EUR"])
        spot["source"] = "er-api (yedek)"
    except Exception:
        pass
    return spot


def fetch_sofr(timeout=15):
    """New York Fed'den güncel SOFR. (oran_yüzde, tarih) ya da (None, None)."""
    try:
        url = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"
        r = requests.get(url, headers=UA, timeout=timeout).json()
        ref = r["refRates"][0]
        return float(ref["percentRate"]), ref.get("effectiveDate")
    except Exception:
        return None, None


def fetch_estr(timeout=15):
    """ECB'den güncel €STR (ESTR). (oran_yüzde, tarih) ya da (None, None)."""
    try:
        url = ("https://data-api.ecb.europa.eu/service/data/EST/"
               "B.EU000A2X2A25.WT?lastNObservations=1&format=jsondata")
        r = requests.get(url, headers=UA, timeout=timeout).json()
        series = next(iter(r["dataSets"][0]["series"].values()))
        obs = next(iter(series["observations"].values()))
        val = float(obs[0])
        dims = r["structure"]["dimensions"]["observation"][0]["values"]
        date = dims[-1]["id"] if dims else None
        return val, date
    except Exception:
        return None, None


if __name__ == "__main__":
    print("SPOT:", fetch_spot())
    print("SOFR:", fetch_sofr(), "ESTR:", fetch_estr())
    for c in fetch_viop_fx():
        print(c["symbol"], c["last"], "hacim:", c["volume"], "saat:", c["time"])
