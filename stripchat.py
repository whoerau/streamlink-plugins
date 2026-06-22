import re

from streamlink.exceptions import PluginError
from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.stream.hls import HLSStream


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


@pluginmatcher(_url_re)
class Stripchat(Plugin):
    def _get_streams(self):
        username = self.match.group("username")
        response = self.session.http.get(
            f"https://stripchat.com/api/front/v2/models/username/{username}/cam",
            headers={"Referer": self.url, "X-Requested-With": "XMLHttpRequest"},
        )
        data = self.session.http.json(response, schema=_api_schema)
        user = (data.get("user") or {}).get("user")
        if not user:
            return

        self.logger.info("Stream status: %s", user["status"])
        if not user["isLive"] or user["status"] != "public" or not isinstance(data.get("cam"), dict):
            return

        room_id = user["id"]
        hls_url = f"https://edge-hls.doppiocdn.com/hls/{room_id}/master/{room_id}_auto.m3u8"
        headers = {"Referer": self.url}

        # 当前协议会混淆媒体 URI，Streamlink 无法安全播放。 / Current Mouflon playlists obfuscate media URIs.
        playlist = self.session.http.get(hls_url, headers=headers)
        if "#EXT-X-MOUFLON:" in playlist.text:
            raise PluginError("Stripchat Mouflon HLS playlists are not supported")

        yield from HLSStream.parse_variant_playlist(self.session, hls_url, headers=headers).items()


__plugin__ = Stripchat
