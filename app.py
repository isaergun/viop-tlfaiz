"""VIOP döviz vadelilerinden ima edilen TL faizi takip paneli (Streamlit)."""
import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st

import store
from rates import cip_solve, days_to_maturity, forward_forward_rate, implied_try_rate, last_business_day
from viop import fetch_estr, fetch_sofr, fetch_spot, fetch_viop_fx

st.set_page_config(page_title="VIOP → İma TL Faizi", page_icon="📈", layout="wide")


@st.cache_data(ttl=300, show_spinner="VIOP verileri çekiliyor…")
def load_data():
    return fetch_spot(), fetch_viop_fx()


@st.cache_data(ttl=3600, show_spinner=False)
def load_foreign_rates():
    sofr, sd = fetch_sofr()
    estr, ed = fetch_estr()
    return sofr, sd, estr, ed


# ---------------- Sidebar ----------------
st.sidebar.header("Ayarlar")
if st.sidebar.button("🔄 Verileri yenile", use_container_width=True):
    load_data.clear()

sofr, sd, estr, ed = load_foreign_rates()
usd_default = sofr if sofr is not None else 4.30
eur_default = estr if estr is not None else 2.00
usd_rate = st.sidebar.number_input("USD faizi (SOFR) %", value=round(usd_default, 2), step=0.05, format="%.2f") / 100
st.sidebar.caption(f"↳ SOFR otomatik: %{sofr} ({sd})" if sofr is not None else "↳ SOFR çekilemedi, elle gir")
eur_rate = st.sidebar.number_input("EUR faizi (ESTR) %", value=round(eur_default, 2), step=0.05, format="%.2f") / 100
st.sidebar.caption(f"↳ €STR otomatik: %{estr} ({ed})" if estr is not None else "↳ €STR çekilemedi, elle gir")
spot_valor = st.sidebar.date_input(
    "Spot valör tarihi",
    value=dt.date.today(),
    help="Süre = forward vade − spot valör. Spot otomatik çekiliyor ama valör enstrümana/güne göre T+0/T+1/T+2 olabilir; buradan ayarla, tüm eğri yeniden hesaplanır.",
)
basis = int(st.sidebar.selectbox("Gün sayım", [365, 360], index=0))
method = st.sidebar.radio("Yöntem", ["cip", "basit"], format_func=lambda m: {"cip": "Faiz paritesi (CIP)", "basit": "Basit forward primi"}[m])
min_vol = st.sidebar.number_input("Min. hacim filtresi (kontrat)", value=0, step=10, help="Bu adetten az işlem gören (likit olmayan) vadeleri gizler.")
save_hist = st.sidebar.checkbox("Snapshot kaydet (geçmiş için)", value=True)

FOREIGN = {"USDTRY": usd_rate, "EURTRY": eur_rate}

# ---------------- Veri ----------------
spot, contracts = load_data()
today = dt.date.today()

rows = []
for c in contracts:
    fr = FOREIGN[c["underlying"]]
    s = spot.get(c["underlying"])
    days = days_to_maturity(c["maturity_year"], c["maturity_month"], spot_valor)
    imp = implied_try_rate(c["last"], s, days, fr, basis=basis, method=method)
    rows.append(
        {
            "symbol": c["symbol"],
            "underlying": c["underlying"],
            "maturity": f"{c['maturity_year']}-{c['maturity_month']:02d}",
            "expiry": last_business_day(c["maturity_year"], c["maturity_month"]),
            "days": days,
            "spot": s,
            "forward": c["last"],
            "prev_close": c["prev_close"],
            "change": (c["last"] / c["prev_close"] - 1) if (c["last"] and c["prev_close"]) else None,
            "implied": imp,
            "volume": c["volume"] or 0,
            "stale": (c["last"] is not None and c["last"] == c["prev_close"]) or not c["volume"],
            "time": c["time"],
        }
    )

df = pd.DataFrame(rows)
df_valid = df[(df["implied"].notna()) & (df["days"] > 0) & (df["volume"] >= min_vol)].copy()

# Snapshot kaydet
if save_hist and not df_valid.empty:
    ts = dt.datetime.now().replace(microsecond=0).isoformat()
    store.save_snapshot(ts, df_valid.to_dict("records"))

# ---------------- Başlık + spot ----------------
st.title("📈 VIOP → İma Edilen TL Faizi")
st.caption(
    f"Kaynak: Bigpara/Foreks (~15 dk gecikmeli) · Spot kaynağı: {spot.get('source','?')} · "
    f"Spot valör: {spot_valor} · "
    f"Veri saati: {df['time'].dropna().iloc[0] if not df['time'].dropna().empty else '—'}"
)
c1, c2, c3 = st.columns(3)
c1.metric("Spot USD/TRY", f"{spot.get('USDTRY', float('nan')):.4f}")
c2.metric("Spot EUR/TRY", f"{spot.get('EURTRY', float('nan')):.4f}")
c3.metric("Yöntem / baz", f"{'CIP' if method=='cip' else 'Basit'} · ACT/{basis}")

tab1, tab2, tab_calc, tab3 = st.tabs(
    ["İma Faiz Eğrisi", "Vadeler Arası (forward-forward)", "Hesaplayıcı", "Geçmiş"]
)

# ---------------- Tab 1: eğri ----------------
with tab1:
    if df_valid.empty:
        st.warning("Hesaplanabilir (likit, vadesi gelmemiş) kontrat bulunamadı.")
    else:
        chart = (
            alt.Chart(df_valid)
            .mark_line(point=True)
            .encode(
                x=alt.X("expiry:T", title="Vade"),
                y=alt.Y("implied:Q", title="İma TL faizi", axis=alt.Axis(format="%")),
                color=alt.Color("underlying:N", title="Dayanak"),
                tooltip=[
                    "symbol",
                    "maturity",
                    alt.Tooltip("days:Q", title="gün"),
                    alt.Tooltip("forward:Q", title="kontrat fiyatı", format=".4f"),
                    alt.Tooltip("change:Q", title="değişim", format="+.2%"),
                    alt.Tooltip("implied:Q", title="ima faiz", format=".2%"),
                    alt.Tooltip("volume:Q", title="hacim", format=",.0f"),
                ],
            )
            .properties(height=380)
        )
        st.altair_chart(chart, use_container_width=True)

        show = df_valid.copy()
        show["ima faiz"] = (show["implied"] * 100).map("{:.2f}%".format)
        show["değişim"] = show["change"].map(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "—")
        show["vade"] = show["expiry"].astype(str)
        st.dataframe(
            show[["symbol", "underlying", "vade", "days", "forward", "prev_close", "değişim", "spot", "ima faiz", "volume", "time"]]
            .rename(columns={
                "days": "gün",
                "forward": "kontrat fiyatı",
                "prev_close": "önceki kapanış",
                "volume": "hacim",
                "time": "saat",
            }),
            use_container_width=True,
            hide_index=True,
        )
    if df["stale"].any():
        st.caption("⚠️ Hacmi düşük/işlem görmemiş vadelerin fiyatı bayat olabilir; ima faizi yanıltıcı olabilir.")

# ---------------- Tab 2: forward-forward ----------------
with tab2:
    st.caption("Ardışık vadeler arası ima edilen TL kısa faizi — piyasanın gelecekteki faiz beklentisi.")
    ff_rows = []
    for u in df_valid["underlying"].unique():
        sub = df_valid[df_valid["underlying"] == u].sort_values("days")
        recs = sub.to_dict("records")
        for a, b in zip(recs, recs[1:]):
            r = forward_forward_rate(a["forward"], b["forward"], a["days"], b["days"], FOREIGN[u], basis=basis, method=method)
            if r is not None:
                ff_rows.append({"underlying": u, "dönem": f"{a['maturity']}→{b['maturity']}", "mid_expiry": b["expiry"], "fwd_faiz": r})
    ff = pd.DataFrame(ff_rows)
    if ff.empty:
        st.info("Forward-forward için en az iki likit vade gerekli.")
    else:
        ch = (
            alt.Chart(ff)
            .mark_line(point=True)
            .encode(
                x=alt.X("mid_expiry:T", title="Vade"),
                y=alt.Y("fwd_faiz:Q", title="İma kısa faiz", axis=alt.Axis(format="%")),
                color="underlying:N",
                tooltip=["underlying", "dönem", alt.Tooltip("fwd_faiz:Q", format=".2%")],
            )
            .properties(height=340)
        )
        st.altair_chart(ch, use_container_width=True)
        ff["ima kısa faiz"] = (ff["fwd_faiz"] * 100).map("{:.2f}%".format)
        st.dataframe(ff[["underlying", "dönem", "ima kısa faiz"]], use_container_width=True, hide_index=True)

# ---------------- Hesaplayıcı ----------------
with tab_calc:
    st.caption("CIP eşitliği:  F = S · (1 + r_TL·t) / (1 + r_yab·t),  "
               "t = (forward vade − spot valör) / baz. Hesaplanacak alanı seç, kalanından bulayım.")

    TARGETS = {
        "Kontrat fiyatı": "forward",
        "TL faizi": "r_try",
        "Yabancı faiz": "r_for",
        "Vade (gün)": "days",
        "Spot": "spot",
    }
    target_label = st.selectbox("Neyi hesaplayalım?", list(TARGETS), index=1)
    target = TARGETS[target_label]

    # Canlı veriden makul başlangıç değerleri (USDTRY yakın vade)
    nd = df_valid.sort_values("days")
    seed_df = nd[nd["underlying"] == "USDTRY"]
    seed = (seed_df if not seed_df.empty else nd).head(1)
    seed = seed.iloc[0] if not seed.empty else None
    d_spot = float(spot.get("USDTRY") or 46.0)
    d_fwd = float(seed["forward"]) if seed is not None and seed["forward"] else 47.0
    d_days = int(seed["days"]) if seed is not None else 30
    d_rtl = float(seed["implied"] * 100) if seed is not None and seed["implied"] else 40.0

    # Fiyat / faiz girdileri
    c = st.columns(4)
    v_spot = c[0].number_input("Spot kur", value=d_spot, step=0.1, format="%.4f", disabled=(target == "spot"))
    v_fwd = c[1].number_input("Kontrat fiyatı", value=d_fwd, step=0.1, format="%.4f", disabled=(target == "forward"))
    v_rtl = c[2].number_input("TL faizi %", value=round(d_rtl, 2), step=0.5, format="%.2f", disabled=(target == "r_try"))
    v_rfor = c[3].number_input("Yabancı faiz %", value=round(usd_rate * 100, 2), step=0.05, format="%.2f", disabled=(target == "r_for"))

    # Tarih / valör girdileri — süre = forward vade valörü − spot valörü
    d = st.columns(3)
    spot_date = d[0].date_input("Spot valör tarihi", value=spot_valor, help="Spot işlemin valörü (genelde işlem günü ya da T+1/T+2). Varsayılan: sidebar'daki değer.")
    with d[1]:
        if target == "days":
            st.markdown("**Forward vade**")
            st.caption("↓ hesaplanacak")
            v_days = d_days  # days hedefinde kullanılmaz
        else:
            mode = st.radio("Vade girişi", ["Tarih", "Gün"], horizontal=True, key="vade_mode")
            if mode == "Gün":
                v_days = st.number_input("Süre (gün)", value=d_days, step=1, min_value=1)
            else:
                fwd_date = st.date_input("Forward vade tarihi", value=spot_date + dt.timedelta(days=d_days), min_value=spot_date + dt.timedelta(days=1))
                v_days = (fwd_date - spot_date).days
    d[2].metric("Süre (gün)", "—" if target == "days" else v_days, help="forward vade − spot valör")

    res = cip_solve(
        target, spot=v_spot, forward=v_fwd,
        r_try=v_rtl / 100, r_for=v_rfor / 100, days=v_days, basis=basis,
    )
    if res is None or (isinstance(res, float) and res != res):
        st.error("Hesaplanamadı — girdileri kontrol et (ör. vade için kombinasyon tutarsız olabilir).")
    elif target in ("r_try", "r_for"):
        st.metric(f"➡️ {target_label}", f"{res * 100:.2f}%")
    elif target == "days":
        est_date = spot_date + dt.timedelta(days=int(round(res)))
        st.metric(f"➡️ {target_label}", f"{res:.0f} gün", help=f"Forward vade tarihi: {est_date}")
        st.caption(f"Spot valör {spot_date} → forward vade **{est_date}**")
    else:
        st.metric(f"➡️ {target_label}", f"{res:.4f}")

    st.divider()
    st.subheader("What-if forward tablosu")
    st.caption("Bir TL faizi varsayımı gir → her canlı vade için teorik forward ve piyasa fiyatıyla farkı. "
               "Fark %>0 = piyasa fiyatı teorikten pahalı (piyasa daha yüksek TL faizi ima ediyor).")
    assume = st.number_input("Varsayılan TL faizi %", value=round(d_rtl, 1), step=0.5, format="%.1f", key="assume") / 100
    trows = []
    for r in df_valid.sort_values(["underlying", "days"]).to_dict("records"):
        teo = cip_solve("forward", spot=r["spot"], r_try=assume, r_for=FOREIGN[r["underlying"]], days=r["days"], basis=basis)
        trows.append({
            "symbol": r["symbol"],
            "underlying": r["underlying"],
            "vade": str(r["expiry"]),
            "gün": r["days"],
            "piyasa fiyatı": round(r["forward"], 4) if r["forward"] else None,
            "teorik forward": round(teo, 4) if teo else None,
            "fark %": f"{(r['forward'] / teo - 1) * 100:+.2f}%" if teo and r["forward"] else "—",
            "piyasa ima faiz": f"{r['implied'] * 100:.2f}%",
        })
    st.dataframe(pd.DataFrame(trows), use_container_width=True, hide_index=True)


# ---------------- Tab 3: geçmiş ----------------
with tab3:
    st.caption("Açık oldukça / her yenilemede biriken snapshot'lardan zaman serisi. Sürekli toplamak için cron ile çalıştırabilirsin.")
    hist = store.load_history()
    if hist.empty:
        st.info("Henüz geçmiş yok. Snapshot kaydı açıkken veriyi yeniledikçe birikecek.")
    else:
        syms = sorted(hist["symbol"].unique())
        default = [s for s in syms if s in df_valid["symbol"].values][:4] or syms[:4]
        pick = st.multiselect("Kontratlar", syms, default=default)
        h = hist[hist["symbol"].isin(pick)]
        if not h.empty:
            ch = (
                alt.Chart(h)
                .mark_line()
                .encode(
                    x=alt.X("ts:T", title="Zaman"),
                    y=alt.Y("implied:Q", title="İma TL faizi", axis=alt.Axis(format="%")),
                    color="symbol:N",
                    tooltip=["ts:T", "symbol", alt.Tooltip("implied:Q", format=".2%")],
                )
                .properties(height=380)
            )
            st.altair_chart(ch, use_container_width=True)
        st.caption(f"Toplam snapshot kaydı: {len(hist):,} satır · {hist['ts'].nunique()} zaman noktası")
