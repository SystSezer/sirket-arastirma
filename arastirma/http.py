"""Ortak HTTP katmani: yavas, durust, robots.txt'e uyan istemci.

JS ile render edilen sayfalar icin istege bagli Playwright yedegi var.
Onemli ayrim: herkese acik bir sayfayi render etmek ile giris yapip kimlik
gizlemek ayni sey degil. Burada yalnizca birincisi yapilir.
"""
from __future__ import annotations

import re
import subprocess
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

UA = "SirketArastirma/1.0 (+arastirma amacli; iletisim: sezerkiras28@gmail.com)"
BEKLEME = 1.5
ZAMAN_ASIMI = 20.0


class Istemci:
    def __init__(self, js: bool = False) -> None:
        self._son = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._http = httpx.Client(headers={"User-Agent": UA},
                                  timeout=ZAMAN_ASIMI, follow_redirects=True)
        self._js_istendi = js
        self._pw = None
        self._tarayici = None

    # ---- nezaket ----

    def _bekle(self) -> None:
        gecen = time.monotonic() - self._son
        if gecen < BEKLEME:
            time.sleep(BEKLEME - gecen)
        self._son = time.monotonic()

    def izin_var_mi(self, url: str) -> bool:
        kok = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if kok not in self._robots:
            p = urllib.robotparser.RobotFileParser()
            try:
                self._bekle()
                y = self._http.get(f"{kok}/robots.txt")
                if y.status_code == 200:
                    p.parse(y.text.splitlines())
                else:
                    p = None  # type: ignore[assignment]
            except httpx.HTTPError:
                p = None  # type: ignore[assignment]
            self._robots[kok] = p
        p = self._robots[kok]
        return True if p is None else p.can_fetch(UA, url)

    # ---- statik ----

    def getir(self, url: str) -> httpx.Response | None:
        if not self.izin_var_mi(url):
            return None
        self._bekle()
        try:
            return self._http.get(url)
        except httpx.HTTPError:
            return None

    # ---- JS render (istege bagli) ----

    @property
    def js_var_mi(self) -> bool:
        if not self._js_istendi:
            return False
        if self._tarayici is not None:
            return True
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False
        try:
            self._pw = sync_playwright().start()
            self._tarayici = self._pw.chromium.launch(headless=True)
            return True
        except Exception:
            self._pw = self._tarayici = None
            return False

    def render(self, url: str) -> str:
        """Sayfayi tarayiciyla acip son HTML'i dondurur. robots.txt yine gecerli."""
        if not self.izin_var_mi(url) or not self.js_var_mi:
            return ""
        self._bekle()
        try:
            sayfa = self._tarayici.new_page(user_agent=UA)  # type: ignore[union-attr]
            sayfa.goto(url, timeout=25000, wait_until="networkidle")
            html = sayfa.content()
            sayfa.close()
            return html
        except Exception:
            return ""

    def kapat(self) -> None:
        self._http.close()
        if self._tarayici is not None:
            try:
                self._tarayici.close()
                self._pw.stop()  # type: ignore[union-attr]
            except Exception:
                pass


def mx_kontrol(domain: str) -> str:
    """Domain mail aliyor mu? 'YOK' donerse o adrese mail atma — geri doner."""
    try:
        cikti = subprocess.run(["nslookup", "-type=mx", domain],
                               capture_output=True, text=True, timeout=15).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return "?"
    bulunan = re.findall(r"mail exchanger = (\S+)", cikti)
    if not bulunan:
        return "YOK"
    ilk = bulunan[0].lower()
    if "outlook" in ilk or "microsoft" in ilk:
        return "Microsoft 365"
    if "google" in ilk:
        return "Google"
    return ilk[:40]
