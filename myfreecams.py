import re
from html import unescape

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import useragents
from streamlink.stream.hls import HLSStream


_url_re = re.compile(r"""https?://(?:
    (?:\w+\.)?myfreecams\.com/
    (?:(?:models/)?\#?(?P<username>\w+)
       |\?(?:id=(?P<user_id>\d+)|go_to_room=(?P<room_username>\w+)))
    |mfc\.im/(?P<short_username>\w+)
)/?(?:[&#].*)?$""", re.VERBOSE)
_tag_re = re.compile(r"<[^>]+>")
_class_re = re.compile(r"\bclass=[\"'][^\"']*\bcampreview\b[^\"']*[\"']", re.I)
_attr_re = re.compile(r"(data-cam-preview-[\w-]+)=[\"']([^\"']*)", re.I)


@pluginmatcher(_url_re)
class MyFreeCams(Plugin):
    @staticmethod
    def _preview_url(html):
        tag = next((tag for tag in _tag_re.findall(html) if _class_re.search(tag)), None)
        if not tag:
            return None

        attrs = {name.lower(): unescape(value) for name, value in _attr_re.findall(tag)}
        server_id = attrs.get("data-cam-preview-server-id-value")
        model_id = attrs.get("data-cam-preview-model-id-value")
        if not server_id or not model_id:
            return None

        # wzobs 房间使用 a_ 前缀。 / wzobs rooms use the a_ stream prefix.
        prefix = "a_" if attrs.get("data-cam-preview-is-wzobs-value") == "true" else ""
        try:
            room_id = 100000000 + int(model_id)
        except ValueError:
            return None
        return (
            f"https://previews.myfreecams.com/hls/NxServer/{server_id}/"
            f"ngrp:mfc_{prefix}{room_id}.f4v_mobile_mhp1080_previewurl/playlist.m3u8"
        )

    def _get_streams(self):
        # Homepage LIVE links use mfc.im; normalize all supported URL forms to a username.
        # 主页 LIVE 链接使用 mfc.im；先把所有支持的 URL 形式统一为用户名。
        username = (
            self.match.group("username")
            or self.match.group("room_username")
            or self.match.group("short_username")
        )
        if not username:
            self.logger.error("Numeric model IDs are no longer supported by MyFreeCams share pages")
            return

        response = self.session.http.get(
            f"https://share.myfreecams.com/{username}",
            headers={"User-Agent": useragents.CHROME},
            acceptable_status=(200, 404),
        )
        if response.status_code == 404:
            return

        hls_url = self._preview_url(response.text)
        if hls_url:
            yield from HLSStream.parse_variant_playlist(self.session, hls_url).items()


__plugin__ = MyFreeCams
