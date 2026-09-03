"""Yayinlanmis e-posta adreslerini bulur ve desenini cikarir.

Iki gercek olaydan dogdu.

1) Signify Technology: ekip sayfasi 41 calisanin adresini acikca yayinliyordu.
   Isim bulmak yetmiyordu — asil kazanc adresti. Ama sitenin adresi
   `signifytechnology.com` iken mailler `signify-tech.com` uzerindeydi. Site
   domainine mail atsaydik hicbiri ulasmazdi.

2) DIQQ: iletisim sayfasinda `info@qgroup.nl` yaziyordu. O domainin HIC MX
   kaydi yok; gonderilen mail 550 5.1.1 ile geri dondu.

Cikarilan kural: **adresin domaini sitenin domaininden AYRI dogrulanir.**
Bulunan her adresin kendi domaini icin MX sorulur, varsayim yapilmaz.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .http import Istemci, mx_kontrol

ILETISIM_YOLLARI = [
    "", "/contact", "/contact-us", "/contactus", "/get-in-touch", "/iletisim",
    "/team", "/our-team", "/meet-the-team", "/people", "/about-us", "/about",
    "/over-ons", "/contacto", "/kontakt",
]

EPOSTA_DESENI = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Site kodunda gecen ama insana ait olmayan adresler
COP = re.compile(r"(sentry|wixpress|example|domain|yourname|@2x|\.png|\.jpg|"
                 r"\.gif|\.svg|\.webp|sentry\.io|godaddy)", re.I)
KUTU_ADLARI = {"info", "contact", "hello", "enquiries", "enquiry", "sales",
               "admin", "office", "mail", "recruitment", "careers", "jobs",
               "support", "team", "hi"}


@dataclass
class EpostaSonuc:
    domain_site: str
    adresler: list[str] = field(default_factory=list)
    mail_domaini: str = ""
    mx: str = ""
    desen: str = ""            # ad.soyad | adsoyad | a.soyad | ad | (bos)
    ornekler: list[str] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)


def _desen_tahmin(yerel_parcalar: list[str]) -> str:
    """Kisi adreslerinin yerel kismindan yaziliş desenini cikarir."""
    sayac: Counter[str] = Counter()
    for y in yerel_parcalar:
        d = y.lower()
        if re.fullmatch(r"[a-z]+\.[a-z]+", d):
            sayac["ad.soyad"] += 1
        elif re.fullmatch(r"[a-z]\.[a-z]+", d):
            sayac["a.soyad"] += 1
        elif re.fullmatch(r"[a-z]+_[a-z]+", d):
            sayac["ad_soyad"] += 1
        elif re.fullmatch(r"[a-z]{4,}", d):
            sayac["ad"] += 1
    return sayac.most_common(1)[0][0] if sayac else ""


def adres_tara(istemci: Istemci, domain: str, azami_sayfa: int = 6) -> EpostaSonuc:
    """Iletisim ve ekip sayfalarini gezip yayinlanmis adresleri toplar."""
    s = EpostaSonuc(domain_site=domain)
    gorulen: set[str] = set()
    bakilan = 0
    for yol in ILETISIM_YOLLARI:
        if bakilan >= azami_sayfa:
            break
        y = istemci.getir(f"https://{domain}{yol}")
        if y is None or y.status_code != 200:
            continue
        bakilan += 1
        for e in EPOSTA_DESENI.findall(y.text):
            if COP.search(e):
                continue
            gorulen.add(e.strip(".,;:").lower())

    s.adresler = sorted(gorulen)
    if not s.adresler:
        s.uyarilar.append("hicbir adres yayinlanmamis — LinkedIn ya da form gerekir")
        return s

    # Mail domaini SITE domaininden farkli olabilir (Signify dersi)
    domainler = Counter(a.split("@", 1)[1] for a in s.adresler)
    s.mail_domaini = domainler.most_common(1)[0][0]
    if s.mail_domaini != domain and s.mail_domaini != domain.removeprefix("www."):
        s.uyarilar.append(
            f"DIKKAT: site '{domain}' ama mail domaini '{s.mail_domaini}'. "
            f"Site domainine gonderme.")

    s.mx = mx_kontrol(s.mail_domaini)
    if s.mx in ("YOK", "?"):
        s.uyarilar.append(
            f"'{s.mail_domaini}' icin MX kaydi YOK — buraya atilan mail geri doner. "
            f"Gonderme, baska adres ara.")

    kisisel = [a for a in s.adresler
               if a.split("@", 1)[0].lower() not in KUTU_ADLARI]
    s.desen = _desen_tahmin([a.split("@", 1)[0] for a in kisisel])
    s.ornekler = kisisel[:5]
    if not kisisel:
        s.uyarilar.append("sadece genel kutu (info@ vb.) var, kisiye ait adres yok")
    return s


def adres_uret(ad: str, soyad: str, mail_domaini: str, desen: str) -> str:
    """Bilinen desene gore bir kisinin adresini kurar. Desen yoksa bos doner —
    tahmin edip gondermek bounce ve itibar kaybi demektir."""
    a, s = ad.strip().lower(), soyad.strip().lower()
    if not (a and s and mail_domaini and desen):
        return ""
    yerel = {"ad.soyad": f"{a}.{s}", "a.soyad": f"{a[0]}.{s}",
             "ad_soyad": f"{a}_{s}", "adsoyad": f"{a}{s}", "ad": a}.get(desen, "")
    return f"{yerel}@{mail_domaini}" if yerel else ""
