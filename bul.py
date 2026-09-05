"""CLI — sirket arastirma boru hatti.

Alti mod:
    isim    domainlerden karar verici cikar (sicil once, sonra site, sonra insan)
    kesif   nis + bolge -> hedef firma listesi
    dizin   sektor birligi uye dizininden hedef listesi (kesif icin DOGRU kapi)
    domain  firma adindan domain bul ve gercekten o firma mi diye dogrula
    adres   siteden yayinlanmis e-posta adreslerini ve desenini cikar
    ulke    bir ulkede ismin nereden bulunacagini anlat

Ornekler:
    python bul.py isim --ulke UK --dosya sirketler.txt
    python bul.py isim --ulke NL diqq.com iqstaffing.nl --js
    python bul.py kesif --nis emlak --bbox 52.33,4.83,52.41,4.96
    python bul.py ulke DE
"""
from __future__ import annotations

import argparse
import csv

from arastirma import (DIZINLER, NISLER, Firma, Istemci, adres_tara, bosluk_bul,
                       domain_bul, etiket, mx_kontrol, nis_dagilimi, sec,
                       uyeleri_getir,
                       osm_ara, puanla, rapor, sicilden_isim, siteden_isim,
                       zincir_ele, ULKELER)


def komut_isim(a: argparse.Namespace) -> None:
    hedefler = list(a.hedefler)
    if a.dosya:
        with open(a.dosya, encoding="utf-8") as f:
            hedefler += [s.strip() for s in f if s.strip() and not s.startswith("#")]
    if not hedefler:
        raise SystemExit("en az bir sirket/domain ver ya da --dosya kullan")

    u = ULKELER.get(a.ulke.upper())
    print(f"Ulke: {u.ad if u else a.ulke} · "
          f"{'sicil otomatik' if u and u.otomatik else 'sicil elle — site denenecek'}"
          f"{' · JS render acik' if a.js else ''}\n")

    istemci = Istemci(js=a.js)
    satirlar, bulunan = [], 0
    try:
        for i, hedef in enumerate(hedefler, 1):
            domain = hedef.split("//")[-1].split("/")[0].removeprefix("www.")
            sirket = a.ad or domain.rsplit(".", 1)[0].replace("-", " ")
            print(f"[{i}/{len(hedefler)}] {hedef}", end="  ", flush=True)

            mx = mx_kontrol(domain)
            kisiler, not_ = [], ""

            # 1) Resmi sicil — varsa en guvenilir kaynak
            if u and u.otomatik:
                kisiler, not_ = sicilden_isim(istemci, a.ulke, sirket)

            # 2) Sicil yoksa ya da bos donduyse: ekip sayfasi (gerekirse JS ile)
            if not kisiler:
                k2, h2 = siteden_isim(istemci, domain, sirket)
                if k2:
                    kisiler, not_ = k2, "site"
                elif not not_:
                    not_ = h2

            print(f"MX:{mx[:13]:15} {'OK' if kisiler else 'isim yok'}  {not_[:44]}")
            if kisiler:
                bulunan += 1
                for k in kisiler[:4]:
                    print(f"      [{k.guven:6}] {k.isim} — {k.unvan}")
                    satirlar.append([hedef, domain, mx, k.guven, k.isim, k.unvan, k.kaynak])
            else:
                satirlar.append([hedef, domain, mx, "", "", "", not_])
                # 3) Makine yapamadi: kullaniciya ne yapacagini soyle
                if u and not u.otomatik and u.elle_adimlar:
                    print(f"      -> {u.elle_adimlar[0]}")
    finally:
        istemci.kapat()

    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["hedef", "domain", "mx", "guven", "isim", "unvan", "kaynak"])
        w.writerows(satirlar)
    print(f"\n{bulunan}/{len(hedefler)} sirkette isim bulundu · cikti: {a.cikti}")
    if u and not u.otomatik:
        print(f"\nIsim cikmayanlar icin {u.ad}:")
        print(rapor(a.ulke))


def komut_kesif(a: argparse.Namespace) -> None:
    if a.nis not in NISLER:
        raise SystemExit(f"bilinmeyen nis. secenekler: {', '.join(NISLER)}")
    nis = NISLER[a.nis]
    print(f"nis: {nis.ad} ({nis.etiket}) · bolge: {a.bbox}\nOpenStreetMap sorgulaniyor...")
    ogeler = osm_ara(nis.etiket, a.bbox, a.limit)
    if not ogeler:
        raise SystemExit("sonuc yok — Overpass mesgul olabilir, birkac dakika sonra dene")

    atilan = 0
    if not a.zincir:
        ogeler, atilan = zincir_ele(ogeler)
    print(f"{len(ogeler)} bagimsiz isletme"
          + (f" ({atilan} zincir elendi)" if atilan else "") + ", inceleniyor:\n")

    istemci, firmalar = Istemci(js=a.js), []
    try:
        for i, oge in enumerate(ogeler, 1):
            t = oge.get("tags", {})
            f = Firma(ad=t.get("name") or "(isimsiz)",
                      site=(t.get("website") or t.get("contact:website") or ""),
                      telefon=t.get("phone") or t.get("contact:phone") or "",
                      adres=" ".join(x for x in [t.get("addr:street"),
                                                 t.get("addr:housenumber"),
                                                 t.get("addr:city")] if x))
            if f.site and not f.site.startswith("http"):
                f.site = "https://" + f.site
            if f.site:
                f.mx = mx_kontrol(f.site.split("//")[-1].split("/")[0].removeprefix("www."))
            bosluk_bul(istemci, f, nis)
            puanla(f)
            firmalar.append(f)
            print(f"  [{i}/{len(ogeler)}] {f.ad[:34]:36} firsat {f.firsat:3} · "
                  f"ulasim {f.ulasim:3} · {etiket(f):11} {', '.join(f.bosluklar) or '-'}")
    finally:
        istemci.kapat()

    firmalar.sort(key=lambda x: -(x.firsat + x.ulasim))
    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["etiket", "firsat", "ulasim", "ad", "site", "mx", "telefon",
                    "adres", "bosluklar", "teklif", "sorular"])
        for f in firmalar:
            w.writerow([etiket(f), f.firsat, f.ulasim, f.ad, f.site, f.mx, f.telefon,
                        f.adres, "; ".join(f.bosluklar), nis.teklif, "; ".join(f.sorular)])

    sicak = [f for f in firmalar if etiket(f) == "SICAK"]
    print(f"\n{len(firmalar)} firma · {len(sicak)} SICAK · "
          f"{sum(1 for f in firmalar if f.sorular)} tanesi insan gozu istiyor")
    print(f"cikti: {a.cikti}\nSatis argumani: {nis.teklif}")




def komut_domain(a: argparse.Namespace) -> None:
    """Firma adlarindan domain bulur. Sicil ad verir, site adresi vermez."""
    adlar = list(a.adlar)
    if a.dosya:
        with open(a.dosya, encoding="utf-8") as f:
            adlar += [s.strip() for s in f if s.strip() and not s.startswith("#")]
    if not adlar:
        raise SystemExit("en az bir firma adi ver ya da --dosya kullan")

    istemci, satirlar = Istemci(), []
    yuksek = orta = 0
    try:
        for i, ad in enumerate(adlar, 1):
            s = domain_bul(istemci, ad, sektor=a.sektor)
            if s.guven == "YUKSEK":
                yuksek += 1
            elif s.guven == "ORTA":
                orta += 1
            print(f"[{i}/{len(adlar)}] {ad[:36]:38} "
                  f"{(s.domain or '-'):32} {s.guven or '':7} {s.baslik[:40]}")
            if s.guven == "ORTA":
                print(f"      GOZLE DOGRULA: {s.kanit}")
            satirlar.append([ad, s.domain, s.guven, s.mx, s.baslik, s.kanit, s.denenen])
    finally:
        istemci.kapat()

    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["firma", "domain", "guven", "mx", "baslik", "kanit", "denenen"])
        w.writerows(satirlar)
    print(f"\n{yuksek} YUKSEK · {orta} ORTA (gozle bak) · "
          f"{len(adlar) - yuksek - orta} bulunamadi · cikti: {a.cikti}")


def komut_adres(a: argparse.Namespace) -> None:
    """Yayinlanmis e-posta adreslerini ve desenini cikarir."""
    hedefler = list(a.domainler)
    if a.dosya:
        with open(a.dosya, encoding="utf-8") as f:
            hedefler += [s.strip() for s in f if s.strip() and not s.startswith("#")]
    if not hedefler:
        raise SystemExit("en az bir domain ver ya da --dosya kullan")

    istemci, satirlar = Istemci(), []
    try:
        for i, h in enumerate(hedefler, 1):
            d = h.split("//")[-1].split("/")[0].removeprefix("www.")
            s = adres_tara(istemci, d)
            print(f"[{i}/{len(hedefler)}] {d:32} {len(s.adresler):3} adres · "
                  f"desen: {s.desen or '-':10} MX: {s.mx[:20]}")
            for o in s.ornekler:
                print(f"      {o}")
            for u in s.uyarilar:
                print(f"      !! {u}")
            satirlar.append([d, s.mail_domaini, s.mx, s.desen, len(s.adresler),
                             "; ".join(s.ornekler), " | ".join(s.uyarilar)])
    finally:
        istemci.kapat()

    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["domain_site", "mail_domaini", "mx", "desen", "adres_sayisi",
                    "ornekler", "uyarilar"])
        w.writerows(satirlar)
    print(f"\ncikti: {a.cikti}")


def komut_dizin(a: argparse.Namespace) -> None:
    """Sektor birligi uye dizininden hedef listesi."""
    istemci = Istemci()
    try:
        uyeler, uyari = uyeleri_getir(istemci, a.dizin)
    finally:
        istemci.kapat()
    if uyari:
        raise SystemExit(f"!! {uyari}")

    print(f"{DIZINLER[a.dizin.upper()].ad}: {len(uyeler)} uye\n")
    if a.dagilim:
        print("Nis dagilimi (firma ADINDAN tahmin — yaklasiktir):")
        for n, s in nis_dagilimi(uyeler):
            print(f"  {n:14} {s:5}")
        return

    secilen = sec(uyeler, sehirler=a.sehir, nis=a.nis, haric=a.haric)
    print(f"{len(secilen)} uye eslesti"
          + (f" (sehir: {', '.join(a.sehir)})" if a.sehir else "")
          + (f" (nis: {a.nis})" if a.nis else "") + "\n")
    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ad", "sehir", "nisler", "dilim"])
        for u in secilen[:a.limit]:
            print(f"  {u.ad[:44]:46} {u.sehir:12} {', '.join(u.nisler)}")
            w.writerow([u.ad, u.sehir, "; ".join(u.nisler), u.dilim])
    print(f"\ncikti: {a.cikti}")
    print("Sonraki adim: python bul.py domain --dosya <adlar.txt>")

def main() -> None:
    ap = argparse.ArgumentParser(description="Sirket arastirma boru hatti")
    alt = ap.add_subparsers(dest="komut", required=True)

    i = alt.add_parser("isim", help="domainlerden karar verici cikar")
    i.add_argument("hedefler", nargs="*")
    i.add_argument("--ulke", default="UK", help="UK, NL, DE, IE, BE, AT, TR, CN")
    i.add_argument("--ad", help="sicilde aranacak resmi sirket adi (tek hedefte)")
    i.add_argument("--dosya")
    i.add_argument("--js", action="store_true", help="JS ile render (playwright gerekir)")
    i.add_argument("--cikti", default="isimler.csv")
    i.set_defaults(fn=komut_isim)

    k = alt.add_parser("kesif", help="nis + bolge -> firma listesi")
    k.add_argument("--nis", required=True, help=", ".join(NISLER))
    k.add_argument("--bbox", required=True, help="guney,bati,kuzey,dogu")
    k.add_argument("--limit", type=int, default=30)
    k.add_argument("--zincir", action="store_true", help="zincirleri de dahil et")
    k.add_argument("--js", action="store_true")
    k.add_argument("--cikti", default="kesif.csv")
    k.set_defaults(fn=komut_kesif)

    dm = alt.add_parser("domain", help="firma adindan domain bul ve dogrula")
    dm.add_argument("adlar", nargs="*")
    dm.add_argument("--dosya")
    dm.add_argument("--sektor", default="isealim", help="isealim | emlak")
    dm.add_argument("--cikti", default="domainler.csv")
    dm.set_defaults(fn=komut_domain)

    ad = alt.add_parser("adres", help="siteden e-posta adresi ve desen cikar")
    ad.add_argument("domainler", nargs="*")
    ad.add_argument("--dosya")
    ad.add_argument("--cikti", default="adresler.csv")
    ad.set_defaults(fn=komut_adres)

    dz = alt.add_parser("dizin", help="sektor birligi uye dizininden hedef listesi")
    dz.add_argument("--dizin", default="REC", help=", ".join(DIZINLER))
    dz.add_argument("--sehir", nargs="*", help="ornek: london manchester")
    dz.add_argument("--nis", help="saglik, egitim, lojistik, bilisim, ...")
    dz.add_argument("--haric", nargs="*", default=["hays", "reed", "adecco", "randstad",
                                                   "manpower", "bae-systems", "brook-street"],
                    help="devleri ele — zincire satis yapilmaz")
    dz.add_argument("--dagilim", action="store_true", help="nis dagilimini yaz ve cik")
    dz.add_argument("--limit", type=int, default=60)
    dz.add_argument("--cikti", default="dizin.csv")
    dz.set_defaults(fn=komut_dizin)

    u = alt.add_parser("ulke", help="bir ulkede isim nereden bulunur")
    u.add_argument("kod", nargs="?")
    u.set_defaults(fn=lambda a: print(rapor(a.kod) if a.kod else
                                      "\n\n".join(rapor(x) for x in ULKELER)))

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
