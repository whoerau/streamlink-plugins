import re
from urllib.parse import urljoin

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import useragents, validate
from streamlink.stream.hls import HLSStream


_url_re = re.compile(
    r"https?://(?:\w{2}\.)?(?P<host>bongacams\d*\.(?:com|net))/(?P<username>[\w-]+)"
)
_room_schema = validate.Schema({
    "status": str,
    validate.optional("localData"): {
        validate.optional("videoServerUrl"): str,
    },
    validate.optional("performerData"): {
        "username": str,
        validate.optional("isOnline"): bool,
        validate.optional("showType"): str,
    },
})


@pluginmatcher(_url_re)
class BongaCams(Plugin):
    def _get_streams(self):
        host = self.match.group("host")
        username = self.match.group("username")
        response = self.session.http.post(
            f"https://{host}/tools/amf.php",
            data=[("method", "getRoomData"), ("args[]", username), ("args[]", "false")],
            headers={
                "User-Agent": useragents.CHROME,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        data = self.session.http.json(response, schema=_room_schema)
        performer = data.get("performerData") or {}
        server = (data.get("localData") or {}).get("videoServerUrl")

        if not server or not performer.get("isOnline") or performer.get("showType") != "public":
            return

        # 站点返回 //host；补 HTTPS 后再拼播放列表。 / The API returns //host; normalize it first.
        server = urljoin("https:", server).rstrip("/")
        hls_url = f"{server}/hls/stream_{performer['username']}/playlist.m3u8"
        yield from HLSStream.parse_variant_playlist(self.session, hls_url).items()


__plugin__ = BongaCams
bongacams = BongaCams
