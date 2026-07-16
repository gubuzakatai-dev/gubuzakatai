import html
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from secondbrain.services.capture import detect_standalone_link
from secondbrain.storage.database import utc_now_text
from secondbrain.storage.repositories import LinkMetadataRepository

MAX_REDIRECTS = 5
MAX_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class FetchedHtml:
    body: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class LinkMetadata:
    title: str | None
    description: str | None


class LinkMetadataError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LinkMetadataService:
    def __init__(self, repository: LinkMetadataRepository, fetcher: "HtmlFetcher | None" = None) -> None:
        self._repository = repository
        self._fetcher = fetcher or HtmlFetcher()

    def process_next(self) -> bool:
        pending = self._repository.get_next_pending()
        if pending is None:
            return False

        started_at = utc_now_text()
        self._repository.mark_running(result_id=pending.result_id, started_at=started_at)
        try:
            fetched = self._fetcher.fetch(pending.url)
            metadata = parse_html_metadata(fetched.body)
        except LinkMetadataError as error:
            self._repository.mark_failed(
                result_id=pending.result_id,
                error_code=error.code,
                error_message=error.message,
                finished_at=utc_now_text(),
            )
            return True

        self._repository.mark_succeeded(
            pending=pending,
            title=metadata.title,
            description=metadata.description,
            finished_at=utc_now_text(),
        )
        return True


class HtmlFetcher:
    def fetch(self, url: str) -> FetchedHtml:
        current_url = url
        for _redirect in range(MAX_REDIRECTS + 1):
            validate_public_url(current_url)
            request = Request(
                current_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "SecondBrainBot/0.1",
                },
            )
            try:
                response = build_opener(_NoRedirectHandler()).open(
                    request, timeout=REQUEST_TIMEOUT_SECONDS
                )
            except HTTPError as error:
                if 300 <= error.code < 400:
                    location = error.headers.get("Location")
                    if not location:
                        raise LinkMetadataError("redirect_without_location", "Redirect has no Location")
                    current_url = urljoin(current_url, location)
                    continue
                raise _http_error(error.code) from error
            except (TimeoutError, socket.timeout, URLError, OSError) as error:
                raise LinkMetadataError("temporary_network_error", type(error).__name__) from error

            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type.casefold():
                raise LinkMetadataError("unsupported_content_type", "Response is not HTML")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise LinkMetadataError("content_too_large", "HTML response is larger than 2 MB")
            return FetchedHtml(body=body, content_type=content_type)

        raise LinkMetadataError("too_many_redirects", "More than five redirects")


class _NoRedirectHandler(HTTPRedirectHandler):
    def http_error_301(self, request: Request, file: object, code: int, message: str, headers: object) -> None:
        raise HTTPError(request.full_url, code, message, headers, file)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


def validate_public_url(url: str) -> None:
    if detect_standalone_link(url) is None:
        raise LinkMetadataError("unsupported_url", "URL is not a standalone public HTTP(S) URL")

    hostname = urlparse(url).hostname
    if hostname is None:
        raise LinkMetadataError("unsupported_url", "URL has no hostname")
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as error:
        raise LinkMetadataError("temporary_dns_error", "DNS lookup failed") from error

    for address in addresses:
        ip = ip_address(address[4][0])
        if not ip.is_global:
            raise LinkMetadataError("private_address", "DNS resolved to a non-public address")


def parse_html_metadata(body: bytes) -> LinkMetadata:
    parser = _MetadataParser()
    parser.feed(body[:MAX_BYTES].decode("utf-8", errors="replace"))
    parser.close()
    return LinkMetadata(title=_clean(parser.title), description=_clean(parser.description))


def _http_error(status_code: int) -> LinkMetadataError:
    if status_code == 429 or status_code >= 500:
        return LinkMetadataError("temporary_http_error", f"HTTP {status_code}")
    return LinkMetadataError("http_error", f"HTTP {status_code}")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(html.unescape(value).split())
    return cleaned or None


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "title":
            self._in_title = True
            return
        if tag.casefold() != "meta":
            return
        attributes = {name.casefold(): value for name, value in attrs if value is not None}
        name = attributes.get("name", "").casefold()
        prop = attributes.get("property", "").casefold()
        content = attributes.get("content")
        if content and self.description is None and (name == "description" or prop == "og:description"):
            self.description = content

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False
            if self.title is None:
                self.title = "".join(self._title_parts)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
