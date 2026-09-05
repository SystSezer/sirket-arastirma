"""EPC olcumu: bir bolgede haftada kac YENI kayit var ve kaci SATIS oncesi.

Emlak tezinin tamami buna bagli:
  yeni EPC kaydi = ev satisa hazirlaniyor (EPC yasal olarak satistan once alinir)

Ama sadece "kac tane" yetmez. EPC birden fazla sebeple alinir — kiralama, yeni
insaat, yesil kredi basvurusu. Asil soru: kacinin sebebi SATIS?

Anahtar epc-anahtar.txt'ten okunur (tek satir: bearer token).
Dosya .gitignore'da; anahtar ekrana basilmaz.

API: https://get-energy-performance-data.communities.gov.uk/api-technical-documentation
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import date, timedelta

import httpx

ADRES = "https://api.get-energy-performance-data.communities.gov.uk/api/domestic/search"


def jeton() -> str:
    try:
        with open("epc-anahtar.txt", encoding="utf-8-sig") as f:
            s = [x.strip() for x in f if x.strip()]
    except FileNotFoundError:
        sys.exit("epc-anahtar.txt yok. Icine TEK SATIR bearer token yaz.")
    if not s:
        sys.exit("epc-anahtar.txt bos. Icine bearer token yaz ve KAYDET (Ctrl+S).")
    return s[-1]


def cek(council: str, bas: date, bit: date, sayfa_boyu: int = 5000) -> list[dict]:
    """Bir belediye icin tarih araligindaki kayitlari, sayfalayarak ceker."""
    basliklar = {"Authorization": f"Bearer {jeton()}", "Accept": "application/json"}
    tum, sayfa = [], 1
    while True:
        p = {"council[]": council, "date_start": bas.isoformat(),
             "date_end": bit.isoformat(), "current_page": sayfa,
             "page_size": sayfa_boyu}
        y = httpx.get(ADRES, params=p, headers=basliklar, timeout=120)
        if y.status_code == 401:
            sys.exit("401 — token yanlis ya da suresi dolmus. Yeniden al.")
        if y.status_code != 200:
            sys.exit(f"HTTP {y.status_code}: {y.text[:300]}")
        veri = y.json()
        satirlar = veri.get("data") or veri.get("rows") or veri.get("results") or []
        if isinstance(satirlar, dict):
            satirlar = satirlar.get("assessments") or list(satirlar.values())
        if not satirlar:
            break
        tum += satirlar
        if len(satirlar) < sayfa_boyu:
            break
        sayfa += 1
        if sayfa > 6:          # guvenlik freni
            break
    return tum


def _al(r: dict, *adaylar: str) -> str:
    """API alan adlari surumden surume degisiyor; birkac adi dener."""
    for a in adaylar:
        if a in r and r[a] not in (None, ""):
            return str(r[a])
    return ""


def main() -> None:
    councils = sys.argv[1:] or ["Manchester"]
    bit = date.today() - timedelta(days=2)      # "bugun" kabul edilmiyor
    bas = bit - timedelta(days=90)
    print(f"Donem: {bas} → {bit}  ({(bit-bas).days} gun)")
    print(f"Belediyeler: {', '.join(councils)}\n")

    tum = []
    for c in councils:
        satirlar = cek(c, bas, bit)
        for r in satirlar:
            r["_council"] = c
        tum += satirlar
        hafta = len(satirlar) / ((bit - bas).days / 7)
        print(f"{c:16} {len(satirlar):6} kayit · HAFTADA ~{hafta:6.1f}")

    if not tum:
        sys.exit("\nHic kayit gelmedi. Yanit yapisi beklenenden farkli olabilir.")

    print(f"\n--- ilk kaydin alanlari ({len(tum[0])} alan) ---")
    print(", ".join(sorted(tum[0].keys()))[:900])

    islem = Counter(_al(r, "transactionType", "transaction-type", "transaction_type") or "(bos)"
                    for r in tum)
    print(f"\n=== NEDEN EPC ALINMIS ({len(tum)} kayit) ===")
    for k, v in islem.most_common(10):
        print(f"  {k[:42]:44} {v:6}  %{100*v//len(tum)}")

    satis = sum(v for k, v in islem.items() if "market" in k.lower() or "sale" in k.lower())
    if satis:
        hafta_satis = satis / ((bit - bas).days / 7) / len(councils)
        print(f"\nSATIS amacli: {satis}/{len(tum)} (%{100*satis//len(tum)})")
        print(f"Belediye basina HAFTADA ~{hafta_satis:.1f} satisa hazirlanan ev")

    with open("epc-ornek.csv", "w", newline="", encoding="utf-8-sig") as f:
        alanlar = sorted({k for r in tum[:50] for k in r})
        w = csv.DictWriter(f, fieldnames=alanlar, extrasaction="ignore")
        w.writeheader(); w.writerows(tum)
    print(f"\ncikti: epc-ornek.csv ({len(tum)} satir)")


if __name__ == "__main__":
    main()
