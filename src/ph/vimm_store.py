"""Vimm's Lair store implementation and HTML parsers."""

import re
import ssl
import string
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from ph.cache_policy import DEFAULT_CATALOGUE_TTL_DAYS, catalogue_ttl_seconds
from ph.models import Platform, SearchResult
from ph.store import USER_AGENT, CatalogProgress, GameStore, StoreError

CATALOG_SECTIONS = ("number", *string.ascii_uppercase)


@dataclass(slots=True)
class _Cell:
    text_parts: list[str] = field(default_factory=list)
    link: str = ""
    image_titles: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.text_parts).split())


class _SearchTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_Cell]] = []
        self._table_depth = 0
        self._target_depth: int | None = None
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None
        self._ignore_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            self._table_depth += 1
            classes = (attributes.get("class") or "").split()
            if self._target_depth is None and "rounded" in classes:
                self._target_depth = self._table_depth
            return
        if self._target_depth is None:
            return
        if tag == "tr" and self._table_depth == self._target_depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = _Cell()
        elif tag == "a" and self._cell is not None:
            style = (attributes.get("style") or "").replace(" ", "").casefold()
            self._ignore_anchor = "display:none" in style
            if not self._ignore_anchor:
                self._cell.link = attributes.get("href") or ""
        elif tag == "img" and self._cell is not None:
            title = attributes.get("title")
            if title:
                self._cell.image_titles.append(title)

    def handle_endtag(self, tag: str) -> None:
        if self._target_depth is None:
            if tag == "table" and self._table_depth:
                self._table_depth -= 1
            return
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "a":
            self._ignore_anchor = False
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_depth == self._target_depth:
                self._target_depth = None
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._ignore_anchor and data.strip():
            self._cell.text_parts.append(data.strip())


class _DownloadFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action = ""
        self.media_id = ""
        self._inside_form = False
        self._form_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form" and attributes.get("id") == "dl_form":
            self._inside_form = True
            self._form_depth = 1
            self.action = attributes.get("action") or ""
        elif self._inside_form:
            if tag == "form":
                self._form_depth += 1
            elif tag == "input" and not self.media_id:
                self.media_id = attributes.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if self._inside_form and tag == "form":
            self._form_depth -= 1
            if self._form_depth == 0:
                self._inside_form = False


def parse_search_results(html: str, base_url: str, system_code: str) -> list[SearchResult]:
    """Parse both all-platform and platform-specific result table layouts."""

    parser = _SearchTableParser()
    parser.feed(html)
    results: list[SearchResult] = []

    for cells in parser.rows:
        if system_code:
            if len(cells) < 3 or not cells[0].link:
                continue
            results.append(
                SearchResult(
                    title=cells[0].text,
                    link=urljoin(base_url, cells[0].link),
                    region=" ".join(cells[1].image_titles),
                    version=cells[2].text,
                    languages=cells[3].text if len(cells) > 3 and cells[3].text else "-",
                    rating=cells[4].text if len(cells) > 4 and cells[4].text else "-",
                )
            )
        else:
            if len(cells) < 4 or not cells[1].link:
                continue
            results.append(
                SearchResult(
                    system=cells[0].text,
                    title=cells[1].text,
                    link=urljoin(base_url, cells[1].link),
                    region=" ".join(cells[2].image_titles),
                    version=cells[3].text,
                )
            )
    return results


def parse_download_url(html: str, base_url: str) -> str:
    """Extract a media URL from a detail page download form."""

    parser = _DownloadFormParser()
    parser.feed(html)
    if not parser.action or not parser.media_id:
        raise StoreError("The page does not contain an available download.")
    action = urljoin(base_url, parser.action)
    separator = "&" if "?" in action else "?"
    return "{}{}{}".format(action, separator, urlencode({"mediaId": parser.media_id}))


class VimmStore(GameStore):
    """Vimm's Lair store implementation and HTML client."""

    store_id = "vimm"
    display_name = "Vimm's Lair"
    description = "Vimm game vault"

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        cache_directory: Path | None = None,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        parsed = urlparse(self._base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        self._base = parsed
        self._ssl_context = ssl.create_default_context()
        self._configure_catalogue_cache(cache_directory, ttl_seconds)

    @property
    def base_url(self) -> str:
        """Return the configured Vimm root URL."""

        return self._base_url

    @property
    def download_referrer(self) -> str:
        """Return the Vimm vault referrer used for media downloads."""

        return f"{self.base_url}/vault/"

    def platform_code(self, platform: Platform) -> str:
        """Return the Vimm system code stored in shared platform metadata."""

        return platform.code

    @property
    def headers(self) -> Mapping[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/octet-stream;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
        }

    def validate_detail_url(self, url: str) -> bool:
        parsed = urlparse(url.strip())
        query = parse_qs(parsed.query, keep_blank_values=True)
        valid_query = not query or (set(query) == {"v"} and len(query["v"]) == 1 and query["v"][0])
        return bool(
            parsed.scheme == self._base.scheme
            and parsed.netloc.casefold() == self._base.netloc.casefold()
            and re.fullmatch(r"/vault/[0-9]+/?", parsed.path)
            and valid_query
            and not parsed.fragment
        )

    def search(
        self,
        system_code: str,
        query: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        """Return case-insensitive title-prefix matches, or a platform catalogue when empty."""

        catalogue = self._load_catalogue(system_code, catalog_progress)
        needle = " ".join(query.split()).casefold()
        return [result for result in catalogue if result.title.casefold().startswith(needle)]

    def _fetch_catalogue(
        self,
        system_code: str,
        catalog_progress: CatalogProgress | None,
    ) -> list[SearchResult]:
        def fetch(section: str) -> list[SearchResult]:
            parameters = {"p": "list", "section": section}
            if system_code:
                parameters["system"] = system_code
            query = urlencode(parameters)
            url = f"{self.base_url}/vault/?{query}"
            try:
                html = self._get_text(url)
            except StoreError as error:
                if error.status_code == 404:
                    return []
                raise
            return parse_search_results(html, self.base_url, system_code)

        results: list[SearchResult] = []
        seen_links: set[str] = set()
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="catalog") as executor:
            for completed, section_results in enumerate(
                executor.map(fetch, CATALOG_SECTIONS),
                start=1,
            ):
                for result in section_results:
                    if result.link not in seen_links:
                        seen_links.add(result.link)
                        results.append(result)
                if catalog_progress is not None:
                    catalog_progress(completed, len(CATALOG_SECTIONS))
        return results

    def retrieve_download_url(self, detail_url: str) -> str:
        if not self.validate_detail_url(detail_url):
            raise StoreError(f"Not a valid detail URL for {self._base.netloc}.")
        return parse_download_url(self._get_text(detail_url), self.base_url)

    def _get_text(self, url: str) -> str:
        request = Request(url, headers=dict(self.headers))
        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
                context=self._ssl_context,
            ) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return cast(str, response.read().decode(charset, errors="replace"))
        except HTTPError as error:
            raise StoreError("The server returned HTTP %d." % error.code, error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise StoreError(f"Could not reach the server: {reason}") from error
