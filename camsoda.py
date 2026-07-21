import re
from urllib.parse import urlencode

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import useragents, validate
from streamlink.stream.hls import HLSStream


_url_re = re.compile(r"https?://(?:www\.)?camsoda\.com/(?P<username>[\w-]+)")
_api_schema = validate.Schema({
    validate.optional("stream"): {
        "status": str,
        "token": str,
        "edge_servers": [str],
        "stream_name": str,
    },
})


@pluginmatcher(_url_re)
class Camsoda(Plugin):
    API_URL = "https://www.camsoda.com/api/v1/chat/react/{0}"

    def _get_streams(self):
        username = self.match.group("username")
        response = self.session.http.get(
            self.API_URL.format(username),
            headers={"User-Agent": useragents.CHROME},
        )
        data = self.session.http.json(response, schema=_api_schema)
        stream = data.get("stream") or {}
        self.logger.info("Stream status: %s", stream.get("status", "unknown"))
        if not stream.get("edge_servers") or not stream.get("stream_name") or not stream.get("token"):
            return

        query = urlencode({
            "filter": "tracks:v4v3v2v1a1a2",
            "multitrack": "true",
            "token": stream["token"],
        })
        hls_url = (
            f"https://{stream['edge_servers'][0]}/{stream['stream_name']}_v1/index.ll.m3u8?{query}"
        )
        yield from HLSStream.parse_variant_playlist(self.session, hls_url).items()


__plugin__ = Camsoda
