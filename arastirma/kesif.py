"""Kesif: nis + bolge verince hedef firmalari bulur.

Kaynak OpenStreetMap (Overpass API) — acik veri, ucretsiz, yapisal.
Google Maps kazimak ToS ihlali; Places API parali. OSM'de ise `website`,
`phone`, `brand` gibi alanlar zaten etiketli — kazima degil, veri okuma.

BILINEN SINIR: OSM'de `website` etiketi yoksa bu "sitesi yok" demek DEGILDIR,
"OSM kaydetmemis" demektir. Olculen ornekte 13 ajansin 8'inin sitesi vardi ama
OSM 5'ini bos gosteriyordu. Bu yuzden bosluklar SINYAL olarak isaretlenir,
gercek olarak degil.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from .http import UA, Istemci
from .isim import Kisi

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]


@dataclass
class Nis:
    etiket: str
    ad: str
    kontroller: list[str]
    teklif: str


NISLER: dict[str, Nis] = {
    "fastfood": Nis("amenity=fast_food", "Fast food / snackbar",
                    ["site_yok", "menu_yok", "siparis_yok", "mobil_degil", "ssl_yok"],
                    "QR menu sitesi + online siparis + gelen mesaj otomasyonu"),
    "restoran": Nis("amenity=restaurant", "Restoran",
                    ["site_yok", "menu_yok", "rezervasyon_yok", "mobil_degil", "ssl_yok"],
                    "Menu sitesi + rezervasyon formu + otomatik yanit"),
    "emlak": Nis("office=estate_agent", "Emlak ofisi",
                 ["site_yok", "ilan_yok", "mobil_degil", "ssl_yok"],
                 "Ilan izleme + gelen talep eleme + otomatik yanit"),
    "isealim": Nis("office=employment_agency", "Ise alim ajansi",
                   ["site_yok", "ilan_yok", "mobil_degil", "ssl_yok"],
                   "Aday kaynak tarama + ilan izleme + uyari hatti"),
    "disci": Nis("amenity=dentist", "Dis klinigi",
                 ["site_yok", "randevu_yok", "mobil_degil", "ssl_yok"],
                 "Randevu formu + gelen arama/mesaj otomasyonu"),
    "otel": Nis("tourism=hotel", "Otel",
                ["site_yok", "rezervasyon_yok", "mobil_degil", "ssl_yok"],
                "Rezervasyon takibi + gelen talep otomasyonu"),
    "kuafor": Nis("shop=hairdresser", "Kuafor / berber",
                  ["site_yok", "randevu_yok", "mobil_degil"],
                  "Randevu sistemi + hatirlatma otomasyonu"),
    "spor": Nis("leisure=fitness_centre", "Spor salonu",
                ["site_yok", "uyelik_yok", "mobil_degil"],
                "Uyelik formu + takip otomasyonu"),
}

IZLER = {
    "menu_yok": ["menu", "menukaart", "speisekarte", "carte", "yemek"],
    "siparis_yok": ["order", "bestel", "bestellen", "siparis", "thuisbezorgd",
                    "deliveroo", "ubereats", "takeaway", "afhalen"],
    "rezervasyon_yok": ["reserve", "reserveren", "reservation", "booking", "boek",
                        "rezervasyon", "opentable"],
    "randevu_yok": ["afspraak", "appointment", "booking", "randevu", "termin", "boek"],
    "ilan_yok": ["aanbod", "woningen", "listings", "properties", "vacatures",
                 "te koop", "te huur", "ilan", "jobs"],
    "uyelik_yok": ["lidmaatschap", "membership", "abonnement", "uyelik", "tarieven"],
}


@dataclass
class Firma:
    ad: str
    site: str = ""
    telefon: str = ""
    adres: str = ""
    mx: str = ""
    bosluklar: list[str] = field(default_factory=list)
    kisiler: list[Kisi] = field(default_factory=list)
    firsat: int = 0       # ne kadar ihtiyaci var
    ulasim: int = 0       # ona ulasabiliyor muyuz
    sorular: list[str] = field(default_factory=list)


def osm_ara(etiket: str, bbox: str, limit: int, deneme: int = 3) -> list[dict]:
    """Ucretsiz Overpass sunuculari yogunlukta 504 doner; artan beklemeyle tekrar dener."""
    anahtar, deger = etiket.split("=", 1)
    sorgu = f'[out:json][timeout:25];nwr["{anahtar}"="{deger}"]({bbox});out center tags;'
    for tur in range(deneme):
        for adres in OVERPASS:
            try:
                y = httpx.post(adres, data={"data": sorgu}, timeout=60,
                               headers={"User-Agent": UA})
                if y.status_code == 200:
                    ogeler = y.json().get("elements", [])
                    if ogeler:
                        return ogeler[:limit]
            except (httpx.HTTPError, ValueError):
                pass
        if tur < deneme - 1:
            time.sleep(5 * (tur + 1))
    return []


def zincir_ele(ogeler: list[dict]) -> tuple[list[dict], int]:
    """Zincirleri at — bagimsiz isletme hedeftir; zincirde karari merkez verir.

    Iki sinyal: OSM'de 'brand' etiketi, ya da ayni ismin sonuc kumesinde tekrari.
    """
    sayac: dict[str, int] = {}
    for o in ogeler:
        ad = (o.get("tags", {}).get("name") or "").strip().lower()
        sayac[ad] = sayac.get(ad, 0) + 1
    bagimsiz, atilan = [], 0
    for o in ogeler:
        et = o.get("tags", {})
        ad = (et.get("name") or "").strip().lower()
        if et.get("brand") or et.get("brand:wikidata") or et.get("operator:wikidata") \
                or sayac.get(ad, 0) > 1:
            atilan += 1
            continue
        bagimsiz.append(o)
    return bagimsiz, atilan


def _site_temizle(ham: str) -> str:
    s = (ham or "").strip()
    return "" if not s else (s if s.startswith("http") else "https://" + s)


def bosluk_bul(istemci: Istemci, f: Firma, nis: Nis) -> None:
    if not f.site:
        f.bosluklar.append("site_yok")
        f.sorular.append("OSM'de site kayitli degil — GERCEKTEN yok mu, elle dogrula")
        return
    if f.site.startswith("http://"):
        f.bosluklar.append("ssl_yok")
    y = istemci.getir(f.site)
    if y is None:
        f.sorular.append("siteye ulasilamadi (robots.txt / ag) — elle bak")
        return
    if y.status_code >= 400:
        f.bosluklar.append("site_yok")
        f.sorular.append(f"site HTTP {y.status_code} — kapanmis olabilir")
        return
    dusuk = y.text.lower()
    if not BeautifulSoup(y.text, "html.parser").find("meta", attrs={"name": "viewport"}):
        f.bosluklar.append("mobil_degil")
    for k in nis.kontroller:
        if k in ("site_yok", "ssl_yok", "mobil_degil"):
            continue
        izler = IZLER.get(k, [])
        if izler and not any(i in dusuk for i in izler):
            f.bosluklar.append(k)


def puanla(f: Firma) -> None:
    """Firsat ve ulasim AYRI hesaplanir.

    Onceki surumde tek skor vardi ve yapisal olarak bozuktu: sitesi olmayan
    firma en buyuk firsat ama MX'i, ekip sayfasi ve ismi olmadigi icin puan
    toplayamiyor, tavana carpiyordu. Hicbir kosuda 'sicak' firma cikmamasinin
    sebebi buydu. Ikisi ayri gercek — tek sayiya sikistirilmamali.
    """
    agirlik = {"site_yok": 45, "menu_yok": 20, "siparis_yok": 20,
               "rezervasyon_yok": 20, "randevu_yok": 20, "ilan_yok": 20,
               "uyelik_yok": 15, "mobil_degil": 20, "ssl_yok": 15}
    f.firsat = min(sum(agirlik.get(b, 10) for b in f.bosluklar), 100)

    u = 0
    if f.mx not in ("", "YOK", "?"):
        u += 40
    if f.kisiler:
        u += 35
    if f.telefon:
        u += 15
    if f.site:
        u += 10
    f.ulasim = min(u, 100)


def etiket(f: Firma) -> str:
    """Iki skoru insan diline cevirir."""
    if f.firsat >= 50 and f.ulasim >= 50:
        return "SICAK"          # ihtiyaci var ve ulasabiliyoruz
    if f.firsat >= 50:
        return "IHTIYAC VAR"    # ama ulasmak zor — telefon/kapi gerekir
    if f.ulasim >= 50:
        return "ULASILIR"       # ama belirgin eksigi yok — baska aciyla gidilir
    return "ZAYIF"
