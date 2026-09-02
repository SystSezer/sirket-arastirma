"""Ekip sayfalarindan karar verici cikarma.

Uc katman, guvenilirden sezgisele:
  1. YUKSEK  class/id icinde "person-name" gibi anlamsal isaretler
  2. ORTA    <h3>Isim</h3> ardindan unvan iceren kisa metin
  3. DUSUK   serbest metinde unvan yakininda isim deseni

Olculen isabet: rastgele secilmis 21 sirkette ~%10 (bkz. README).
Bu yuzden BIRINCIL kaynak degil — resmi sicil varsa once oraya bakilir,
burasi yalnizca sicil olmayan ulkelerde yedek olarak kullanilir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .http import Istemci

EKIP_YOLLARI = [
    "/team", "/our-team", "/about-us/our-team", "/about/team", "/people",
    "/over-ons", "/over-ons/team", "/ons-team", "/onze-mensen", "/medewerkers",
    "/about-us", "/about", "/wie-zijn-wij", "/uber-uns", "/unser-team", "/collega-s",
    "/who-we-are", "/meet-the-team", "/leadership", "/management",
]

UNVANLAR = [
    "managing director", "managing partner", "managing consultant",
    "algemeen directeur", "general manager", "vestigingsmanager",
    "geschaftsfuhrer", "geschäftsführer",
    "co-founder", "founder", "oprichter", "eigenaar", "owner",
    "director", "directeur", "partner", "head of",
    "ceo", "cto", "coo", "cfo",
]
# Kelime siniri sart: duz "in" kontrolu 'coo' unvanini 'cookie' icinde,
# 'partner' kelimesini 'partnership' icinde eslestiriyordu.
UNVAN_DESENI = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(u) for u in UNVANLAR) + r")(?![a-z])", re.I)

TUSSENVOEGSEL = r"(?:van|van der|van den|van de|de|den|der|ter|te|op)"
ISIM_DESENI = re.compile(
    rf"\b([A-Z][a-zà-ÿ'’\-]+(?:\s+{TUSSENVOEGSEL})?(?:\s+[A-Z][a-zà-ÿ'’\-]+){{1,2}})\b")

KARA_LISTE = {
    "our team", "the team", "over ons", "about us", "contact us", "read more",
    "lees meer", "meer weten", "view profile", "linked in", "privacy policy",
    "algemene voorwaarden", "cookie policy", "neem contact", "onze mensen",
    "last published", "business analist", "read more about", "meer over",
    "mission vision", "our services", "our story",
}
YASAK_KELIME = {"it", "ict", "search", "recruitment", "recruiter", "bureau",
                "consultancy", "management", "executive", "wat", "een", "hoe",
                "waarom", "onze", "meer", "solutions", "services", "group",
                "technology", "digital", "the", "and", "mission", "vision"}
KUYRUK = {"managing", "director", "partner", "founder", "owner", "consultant",
          "manager", "directeur", "oprichter", "eigenaar", "head"}


@dataclass
class Kisi:
    isim: str
    unvan: str
    guven: str = "ORTA"      # YUKSEK | ORTA | DUSUK
    kaynak: str = ""         # nereden geldi: sicil adi ya da URL


def _temiz(ham: str) -> str:
    p = ham.split()
    while p and p[-1].lower().strip(",.-") in KUYRUK:
        p.pop()
    return " ".join(p)


def _isim_mi(aday: str, sirket: str = "") -> bool:
    d = aday.lower().strip()
    if len(aday) < 5 or d in KARA_LISTE or UNVAN_DESENI.search(aday):
        return False
    p = aday.split()
    if any(x.lower().strip(",.-?") in YASAK_KELIME for x in p):
        return False
    # Sirketin kendi adini kisi sanma: "Blue Lynx — partner" hatasi
    if sirket and d in sirket.lower():
        return False
    return 2 <= len(p) <= 4


def _k1_yapisal(corba: BeautifulSoup, sirket: str) -> list[Kisi]:
    isim_re = re.compile(r"(person|member|team|employee|staff|medewerker)[-_]?name|name", re.I)
    out: list[Kisi] = []
    for d in corba.find_all(attrs={"class": isim_re}):
        if not isinstance(d, Tag):
            continue
        isim = _temiz(" ".join(d.get_text(" ").split()))
        if not _isim_mi(isim, sirket):
            continue
        baglam = " ".join(d.parent.get_text(" ").split()) if d.parent else ""
        m = UNVAN_DESENI.search(baglam)
        if m:
            out.append(Kisi(isim, m.group(1).lower(), "YUKSEK"))
    return out


def _k2_baslik(corba: BeautifulSoup, sirket: str) -> list[Kisi]:
    out: list[Kisi] = []
    for h in corba.find_all(["h2", "h3", "h4", "h5", "strong", "b"]):
        isim = _temiz(" ".join(h.get_text(" ").split()))
        if not _isim_mi(isim, sirket):
            continue
        sonra = ""
        for k in h.find_all_next(string=True, limit=6):
            t = " ".join(str(k).split())
            if t and t != isim:
                sonra += " " + t
            if len(sonra) > 120:
                break
        m = UNVAN_DESENI.search(sonra)
        if m:
            out.append(Kisi(isim, m.group(1).lower(), "ORTA"))
    return out


def _k3_sezgisel(corba: BeautifulSoup, sirket: str) -> list[Kisi]:
    out: list[Kisi] = []
    for d in corba.find_all(string=UNVAN_DESENI):
        blok = " ".join((d.parent.get_text(" ") if d.parent else str(d)).split())[:200]
        m = UNVAN_DESENI.search(blok)
        if not m:
            continue
        for ham in ISIM_DESENI.findall(blok):
            isim = _temiz(ham)
            if _isim_mi(isim, sirket):
                out.append(Kisi(isim, m.group(1).lower(), "DUSUK"))
                break
    return out


def kisileri_cikar(html: str, sirket: str = "") -> list[Kisi]:
    corba = BeautifulSoup(html, "html.parser")
    for e in corba(["script", "style", "nav", "footer", "noscript"]):
        e.decompose()
    for katman in (_k1_yapisal, _k2_baslik, _k3_sezgisel):
        bulunan = katman(corba, sirket)
        if bulunan:
            benzersiz: dict[str, Kisi] = {}
            for k in bulunan:
                benzersiz.setdefault(k.isim, k)
            return list(benzersiz.values())[:8]
    return []


def aday_sayfalar(istemci: Istemci, domain: str) -> tuple[list[str], str]:
    taban = f"https://{domain}"
    ana = istemci.getir(taban)
    if ana is None:
        return [], "ana sayfaya ulasilamadi (robots.txt veya ag hatasi)"
    if ana.status_code == 403:
        return [], "403 — site otomatik erisimi engelliyor, zorlanmadi"
    if ana.status_code >= 400:
        return [], f"ana sayfa HTTP {ana.status_code}"

    corba = BeautifulSoup(ana.text, "html.parser")
    anahtar = ("team", "over-ons", "over ons", "about", "mensen", "people",
               "medewerker", "collega", "wie zijn wij", "uber-uns", "leadership")
    adaylar: list[str] = []
    for a in corba.find_all("a", href=True):
        metin = (a.get_text() or "").strip().lower()
        href = a["href"].lower()
        if any(k in metin for k in anahtar) or any(k in href for k in anahtar):
            tam = urljoin(taban, a["href"]).split("#")[0]
            if urlparse(tam).netloc.endswith(domain) and tam not in adaylar:
                adaylar.append(tam)
    for y in EKIP_YOLLARI:
        if taban + y not in adaylar:
            adaylar.append(taban + y)
    return adaylar, ""


def siteden_isim(istemci: Istemci, domain: str, sirket: str = "",
                 max_sayfa: int = 4) -> tuple[list[Kisi], str]:
    """Ekip sayfasindan isim cikarir. Statik HTML bosa cikarsa JS ile tekrar dener."""
    adaylar, hata = aday_sayfalar(istemci, domain)
    if not adaylar:
        return [], hata

    denenen = 0
    ilk_url = ""
    for url in adaylar:
        if denenen >= max_sayfa:
            break
        y = istemci.getir(url)
        if y is None or y.status_code != 200:
            continue
        denenen += 1
        ilk_url = ilk_url or url
        kisiler = kisileri_cikar(y.text, sirket)
        if kisiler:
            for k in kisiler:
                k.kaynak = url
            return kisiler, ""

    # Statik bos: sayfa JS ile kuruluyor olabilir
    if istemci.js_var_mi and ilk_url:
        html = istemci.render(ilk_url)
        if html:
            kisiler = kisileri_cikar(html, sirket)
            if kisiler:
                for k in kisiler:
                    k.kaynak = ilk_url + " (JS)"
                return kisiler, ""
    return [], "ekip sayfasi bulundu ama isim cikarilamadi"
