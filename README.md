# VIOP → İma Edilen TL Faizi

**🔗 Canlı uygulama: https://isaergun-viop-tlfaiz-app-x7nrcq.streamlit.app**

[![Streamlit'te aç](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://isaergun-viop-tlfaiz-app-x7nrcq.streamlit.app)

BIST VIOP döviz vadeli kontratlarından (USD/TRY, EUR/TRY) **örtülü faiz paritesi (CIP)** ile
ima edilen TL faiz vade eğrisini hesaplayan ve takip eden Streamlit paneli.

## Mantık

```
F = S · (1 + r_TL·t) / (1 + r_yab·t)   ⇒   r_TL = ((F/S)·(1 + r_yab·t) − 1) / t
```

- **F** = VIOP vadeli fiyat, **S** = spot kur, **t** = vadeye kalan gün / baz (365 ya da 360)
- **r_yab** = USD için SOFR, EUR için ESTR (sidebar'dan ayarlanır)

## Veri kaynağı

- **Vadeli + spot**: Bigpara / Foreks (~15 dk gecikmeli, ücretsiz, anahtar gerektirmez)
- **Spot yedeği**: `open.er-api.com` (günlük)
- **Yabancı faizler otomatik**: SOFR → New York Fed API, €STR → ECB API (sidebar'da elle ezilebilir)

## Çalıştırma (lokal)

```bash
cd viop-tlfaiz
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)

1. Üstteki **"Streamlit'te aç"** rozetine tıkla (ya da [share.streamlit.io](https://share.streamlit.io) → New app).
2. Repo `isaergun/viop-tlfaiz`, branch `main`, main file `app.py` → **Deploy**.
3. Birkaç dakikada `https://<ad>.streamlit.app` adresinden yayında olur.

> Not: Streamlit Cloud dosya sistemi geçici olduğundan `viop_history.db` (geçmiş)
> yeniden başlatmada sıfırlanır. Kalıcı geçmiş için harici DB (ör. Postgres) gerekir.

## Sekmeler

1. **İma Faiz Eğrisi** — her vade için ima TL faizi (USDTRY + EURTRY), tablo + likidite (hacim)
2. **Vadeler Arası** — ardışık vadeler arası ima kısa faizi (forward-forward), piyasanın faiz beklentisi
3. **Geçmiş** — her yenilemede `viop_history.db`'ye snapshot biriken zaman serisi

## Notlar

- Hacmi düşük uzak vadelerde fiyat bayat olabilir → ima faizi yanıltıcı; tabloda işaretlenir, sidebar'dan min. hacim filtresi uygulanabilir.
- Spot retail "serbest piyasa" kuru olduğu için interbank'a göre küçük bir baz farkı olabilir.
- Sürekli geçmiş toplamak istersen `streamlit run` yerine veriyi periyodik çeken bir cron + `store.save_snapshot` kurabilirsin.
```
