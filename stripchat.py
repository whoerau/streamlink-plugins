import base64
import hashlib
import itertools
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from curl_cffi import requests
from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.stream.hls import HLSStream, HLSStreamReader, HLSStreamWorker


_url_re = re.compile(r"https?://(?:\w+\.)?stripchat\.com/(?P<username>[a-zA-Z0-9_@-]+)")
_api_schema = validate.Schema({
    validate.optional("error"): str,
    validate.optional("cam"): validate.any(list, dict),
    validate.optional("user"): {
        "user": {
            "id": int,
            "status": str,
            "isLive": bool,
        },
    },
})

_MOUFLON_PSCH_PREFIX = "#EXT-X-MOUFLON:PSCH:"
_MOUFLON_URI_PREFIX = "#EXT-X-MOUFLON:URI:"
_MOUFLON_MEDIA_PLACEHOLDER = "media.mp4"
_MOUFLON_XOR_KEY_PREFIX = "xor:"
_MOUFLON_CACHE_TTL = 6 * 60 * 60
_MOUFLON_SEGMENT_RE = re.compile(
    r"(?P<prefix>.*_\d+_)(?P<token>[^_]+)(?P<suffix>_\d+(?:_part\d+)?\.mp4)$"
)
_mouflon_cache = {"keys": {}, "updated_at": 0.0, "page_url": "https://stripchat.com/"}


def _is_mouflon_playlist_url(url):
    return "media-hls.doppio" in url and ".m3u8" in url and "pkey=" in url


def _parse_mouflon_segment(url):
    match = _MOUFLON_SEGMENT_RE.search(urlsplit(url).path)
    if not match:
        return None
    return match.group("prefix"), match.group("suffix"), match.group("token")


def _is_mouflon_segment_url(url):
    return (
        "media-hls.doppio" in url
        and ".mp4" in url
        and _MOUFLON_MEDIA_PLACEHOLDER not in url
        and "_init_" not in url
        and _parse_mouflon_segment(url) is not None
    )


def _decode_base64(value):
    return base64.b64decode(value + "=" * (-len(value) % 4))


def _recover_mouflon_xor_key(encrypted_token, clear_token):
    try:
        encrypted = _decode_base64(encrypted_token[::-1])
        clear = clear_token.encode("utf-8")
    except Exception:
        return None
    if not encrypted or len(encrypted) != len(clear):
        return None
    return bytes(left ^ right for left, right in zip(encrypted, clear))


def derive_mouflon_keys(playlist_texts, segment_urls):
    # Match one obfuscated URI with the player's clear request to recover its XOR key.
    # 将同一分段的混淆 URI 与播放器明文请求配对，以恢复 XOR 密钥。
    keys = {}
    for playlist in playlist_texts:
        pkey = next((
            line.rsplit(":", 1)[-1]
            for line in playlist.splitlines()
            if line.startswith(_MOUFLON_PSCH_PREFIX)
        ), None)
        if not pkey or pkey in keys:
            continue

        encrypted_uris = (
            line[len(_MOUFLON_URI_PREFIX):]
            for line in playlist.splitlines()
            if line.startswith(_MOUFLON_URI_PREFIX)
        )
        for encrypted_uri in encrypted_uris:
            encrypted = _parse_mouflon_segment(encrypted_uri)
            if not encrypted:
                continue
            for segment_url in segment_urls:
                clear = _parse_mouflon_segment(segment_url)
                if not clear or encrypted[:2] != clear[:2]:
                    continue
                key = _recover_mouflon_xor_key(encrypted[2], clear[2])
                if key:
                    keys[pkey] = _MOUFLON_XOR_KEY_PREFIX + base64.b64encode(key).decode("ascii")
                    break
            if pkey in keys:
                break
    return keys


def _fetch_dynamic_mouflon_keys(page_url):
    from scrapling import DynamicFetcher

    playlist_texts = []
    segment_urls = []
    keys = {}

    def setup(page):
        def remember_request(request):
            if _is_mouflon_segment_url(request.url):
                segment_urls.append(request.url)

        def remember_response(response):
            if not _is_mouflon_playlist_url(response.url):
                return
            try:
                playlist_texts.append(response.text())
            except Exception:
                pass

        page.on("request", remember_request)
        page.on("response", remember_response)

    def action(page):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            keys.update(derive_mouflon_keys(playlist_texts, segment_urls))
            if keys:
                return
            page.wait_for_timeout(500)

    options = {
        "headless": True,
        "timeout": 60_000,
        "wait": 0,
        "network_idle": False,
        "load_dom": True,
        "cookies": [{
            "name": "isVisitorsAgreementAccepted",
            "value": "1",
            "domain": "stripchat.com",
            "path": "/",
        }],
        "page_setup": setup,
        "page_action": action,
    }
    for real_chrome in (True, False):
        try:
            DynamicFetcher.fetch(page_url, real_chrome=real_chrome, **options)
        except Exception:
            if real_chrome:
                continue
            raise
        if keys:
            break
        # Retry with Scrapling's managed browser if local Chrome yielded no key.
        # 本机 Chrome 未取得密钥时，改用 Scrapling 管理的浏览器重试。
    return keys


def refresh_mouflon_keys(page_url, force=False):
    now = time.monotonic()
    cached = _mouflon_cache["keys"]
    if cached and not force and now - _mouflon_cache["updated_at"] < _MOUFLON_CACHE_TTL:
        return dict(cached)

    keys = _fetch_dynamic_mouflon_keys(page_url)
    if keys:
        cached.update(keys)
        _mouflon_cache.update({"updated_at": now, "page_url": page_url})
    return dict(cached)


def _mouflon_key_bytes(key):
    if isinstance(key, str) and key.startswith(_MOUFLON_XOR_KEY_PREFIX):
        return base64.b64decode(key[len(_MOUFLON_XOR_KEY_PREFIX):])
    return hashlib.sha256(str(key).encode("utf-8")).digest()


def _decode_mouflon_uri(uri, key):
    if not key:
        return uri
    segment = _parse_mouflon_segment(uri)
    if not segment:
        return uri
    encoded = segment[2]
    encrypted = _decode_base64(encoded[::-1])
    decoded = bytes(
        left ^ right
        for left, right in zip(encrypted, itertools.cycle(_mouflon_key_bytes(key)))
    ).decode("utf-8")
    decoded_uri = uri.replace(encoded, decoded)
    parts = decoded_uri.split("/", maxsplit=4)
    return parts[4] if len(parts) == 5 else decoded_uri


def _add_mouflon_query(url, psch, pkey):
    split_url = urlsplit(url)
    query = dict(parse_qsl(split_url.query, keep_blank_values=True))
    query.update({"psch": psch, "pkey": pkey})
    return urlunsplit(split_url._replace(query=urlencode(query)))


def rewrite_mouflon_playlist(playlist, mouflon_keys=None):
    keys = dict(mouflon_keys if mouflon_keys is not None else _mouflon_cache["keys"])
    lines = playlist.splitlines()
    required = {
        line.rsplit(":", 1)[-1]
        for line in lines
        if line.startswith(_MOUFLON_PSCH_PREFIX)
    }
    if mouflon_keys is None and required and not required.intersection(keys):
        keys = refresh_mouflon_keys(_mouflon_cache["page_url"], force=True)

    psch = pkey = None
    for line in lines:
        if not line.startswith(_MOUFLON_PSCH_PREFIX):
            continue
        parts = line.rsplit(":", 3)
        if len(parts) == 4 and parts[-1] in keys:
            _, _, psch, pkey = parts
            break

    key = keys.get(pkey)
    rewritten = []
    pending_uri = None
    # Decode each custom URI tag into the following standard HLS media placeholder.
    # 将每个自定义 URI 标签解码到紧随其后的标准 HLS 媒体占位符。
    for line in lines:
        if line.startswith(_MOUFLON_URI_PREFIX):
            pending_uri = _decode_mouflon_uri(line[len(_MOUFLON_URI_PREFIX):], key)
            continue
        if pending_uri and line and _MOUFLON_MEDIA_PLACEHOLDER in line:
            rewritten.append(line.replace(_MOUFLON_MEDIA_PLACEHOLDER, pending_uri))
            pending_uri = None
            continue
        if psch and pkey and line and not line.startswith("#") and ".m3u8" in line:
            rewritten.append(_add_mouflon_query(line, psch, pkey))
            continue
        rewritten.append(line)
    return "\n".join(rewritten)


class MouflonHLSStreamWorker(HLSStreamWorker):
    def _fetch_playlist(self):
        response = super()._fetch_playlist()
        response._content = rewrite_mouflon_playlist(response.text).encode(
            response.encoding or "utf-8"
        )
        return response


class MouflonHLSStreamReader(HLSStreamReader):
    __worker__ = MouflonHLSStreamWorker


class MouflonHLSStream(HLSStream):
    __reader__ = MouflonHLSStreamReader

    @classmethod
    def _fetch_playlist(cls, session, url, **request_args):
        response = super()._fetch_playlist(session, url, **request_args)
        response._content = rewrite_mouflon_playlist(response.text).encode(
            response.encoding or "utf-8"
        )
        return response


@pluginmatcher(_url_re)
class Stripchat(Plugin):
    def _get_streams(self):
        username = self.match.group("username")
        response = requests.get(
            f"https://stripchat.com/api/front/v2/models/username/{username}/cam",
            headers={"Referer": self.url, "X-Requested-With": "XMLHttpRequest"},
            impersonate="chrome",
            timeout=20,
        )
        response.raise_for_status()
        data = _api_schema.validate(response.json())
        user = (data.get("user") or {}).get("user")
        cam = data.get("cam")
        if not user:
            return

        self.logger.info("Stream status: %s", user["status"])
        if (
            not user["isLive"]
            or user["status"] != "public"
            or not isinstance(cam, dict)
            or not cam.get("isCamAvailable", True)
            or not cam.get("streamName")
        ):
            return

        # Recover Mouflon keys once, then let Streamlink expose native HLS variants.
        # 先恢复 Mouflon 密钥，再由 Streamlink 暴露原生 HLS 分辨率档位。
        if not refresh_mouflon_keys(self.url):
            self.logger.error("Could not recover Stripchat Mouflon keys")
            return

        stream_name = cam["streamName"]
        playlist_urls = (
            f"https://edge-hls.doppiocdn.com/hls/{stream_name}/master/{stream_name}.m3u8",
            f"https://edge-hls.doppiocdn.com/hls/{stream_name}/master/{stream_name}_auto.m3u8",
        )
        streams = {}
        for playlist_url in playlist_urls:
            try:
                variants = MouflonHLSStream.parse_variant_playlist(self.session, playlist_url)
            except Exception as error:
                self.logger.debug("Could not parse %s: %s", playlist_url, error)
                continue
            for quality, stream in variants.items():
                streams.setdefault(quality, stream)
        if streams:
            return streams
        return {"live": MouflonHLSStream(self.session, playlist_urls[0])}


__plugin__ = Stripchat
