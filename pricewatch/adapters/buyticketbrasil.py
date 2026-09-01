"""buyticketbrasil.com — Brazilian secondary-market ticket marketplace.

Reconnaissance, 2026-09-01 (full write-up in
`knowledge/ideas/website-price-watcher-scripts.md`, section "Recon"):

  * The site is a **Next.js App Router** front end over a **Bubble** backend. It is
    NOT a client-rendered SPA, so there is no XHR to intercept -- every price is
    server-rendered into the first response.
  * Sending the **`RSC: 1`** header returns the same payload as `text/x-component`
    at roughly half the bytes, and -- decisively -- with the embedded JSON
    **unescaped**. The plain HTML response escapes it (`\\"preco_min\\":27500`),
    which would force an unescaping pass. This adapter therefore requires the RSC
    endpoint.
  * No cookies, no JS execution, no User-Agent spoofing needed.
  * `robots.txt` is `Allow: /` with `Disallow: /api/` and `/_next/`. This adapter
    only ever touches `/evento/...`, which is explicitly allowed.

⚠️ `preco_min` is in **centavos** (27500 -> R$ 275,00). It is stored as-is.
"""

from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..models import AdapterError, Reading, utcnow_iso

BASE = "https://buyticketbrasil.com/evento/"

# Honest and identifiable rather than a spoofed Chrome string. The recon confirmed
# the site serves this endpoint to a request with no User-Agent at all, so there is
# nothing to work around.
USER_AGENT = "price-watcher/0.1 (personal price watcher; contact: repo owner)"

TIMEOUT_S = 30


def _grab(text: str, key: str):
    """Pull one top-level JSON value out of the RSC stream by key name.

    The RSC body is a length-prefixed text stream, not a single JSON document, so
    it cannot simply be `json.loads`-ed. Locating the key and letting
    `JSONDecoder.raw_decode` consume exactly one value from that offset is both
    correct and cheap.

    The whitespace handling is load-bearing, not defensive padding:
    `JSONDecoder.raw_decode` does **not** skip leading whitespace -- it raises on
    it. Today's payload is minified so `"key":{` has none, but a single pretty-
    printing change upstream would make every fetch report "payload shape changed"
    and the watcher would go silent while looking like it had caught a real
    site migration. Matching the separator with a regex removes that trap.
    """
    m = re.search(rf'"{re.escape(key)}"\s*:\s*', text)
    if not m:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[m.end():])
    except json.JSONDecodeError:
        return None
    return value


class BuyTicketBrasilAdapter:
    site = "buyticketbrasil"

    def build_url(self, target) -> str:
        p = target.params
        try:
            slug = p["event_slug"]
            query = {
                "data": p["data_millis"],
                "evento_local": p["evento_local"],
            }
        except KeyError as e:
            raise AdapterError(f"{target.id}: params missing {e}") from e
        if p.get("cidade"):
            query["cidade"] = p["cidade"]
        return BASE + urllib.parse.quote(slug) + "?" + urllib.parse.urlencode(query)

    def _get(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "RSC": "1",                     # <- the whole trick; see module docstring
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "gzip, identity",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise AdapterError(f"fetch failed for {url}: {e}") from e

    def parse(self, body: str, target, url: str) -> list[Reading]:
        matriz = _grab(body, "matriz_preco")
        if matriz is None:
            # The payload shape is gone -> this adapter is blind. Never confuse this
            # with "nothing on sale": that would silently turn a broken watcher into
            # a healthy-looking one that reports no results forever.
            raise AdapterError(
                f"{target.id}: 'matriz_preco' not found in the RSC payload "
                f"({len(body)} bytes from {url}). The site's payload shape likely "
                f"changed -- this adapter needs re-reading before it can be trusted."
            )
        if not isinstance(matriz, dict):
            raise AdapterError(f"{target.id}: 'matriz_preco' is {type(matriz).__name__}, expected object")

        captured_at = utcnow_iso()
        readings: list[Reading] = []
        for key, row in matriz.items():
            sector, _, entry_class = key.partition("||")
            sector, entry_class = sector.strip(), entry_class.strip()
            try:
                price_cents = int(row["preco_min"])
                quantity = int(row["disponivel"])
            except (KeyError, TypeError, ValueError):
                continue  # a malformed single row is skipped; a missing matriz raises

            # A zero/negative price is a placeholder row, not a listing (the site
            # carries e.g. "Meia aposentado" at preco_min 0 with 0 available). Left
            # in, it would win every min() and poison every threshold silently.
            if price_cents <= 0:
                continue

            readings.append(Reading(
                target_id=target.id,
                site=self.site,
                item=f"{sector} || {entry_class}",
                price_cents=price_cents,
                currency="BRL",
                quantity=quantity,
                captured_at=captured_at,
                source_url=url,
                extra={
                    "sector": sector,
                    "entry_class": entry_class,
                    "id_ref": row.get("id_ref"),
                },
            ))
        return readings

    def fetch(self, target) -> list[Reading]:
        url = self.build_url(target)
        return self.parse(self._get(url), target, url)
