import re

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import useragents, validate
from streamlink.stream.hls import HLSStream


INFO_URL = "https://hu.cam4.com/rest/v1.0/profile/{0}/info"
ACCESS_URL = "https://webchat.cam4.com/requestAccess?roomname={0}"
STREAM_INFO_URL = "https://hu.cam4.com/rest/v1.0/profile/{0}/streamInfo"

_url_re = re.compile(r"https?://(?:\w+\.)?cam4\.com/(?P<username>[\w-]+)")
_info_schema = validate.Schema({"online": bool})
_access_schema = validate.Schema({validate.optional("privateStream"): bool})
_stream_schema = validate.Schema({validate.optional("cdnURL"): validate.any(None, str)})


@pluginmatcher(_url_re)
class Cam4(Plugin):
    def _get_streams(self):
        username = self.match.group("username")
        headers = {
            "User-Agent": useragents.CHROME,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }

        response = self.session.http.get(INFO_URL.format(username), headers=headers)
        info = self.session.http.json(response, schema=_info_schema)
        self.logger.info("Stream status: %s", "online" if info["online"] else "offline")
        if not info["online"]:
            return

        response = self.session.http.get(ACCESS_URL.format(username), headers=headers)
        access = self.session.http.json(response, schema=_access_schema)
        if access.get("privateStream"):
            self.logger.info("Access: private")
            return

        response = self.session.http.get(
            STREAM_INFO_URL.format(username),
            headers=headers,
            acceptable_status=(200, 204),
        )
        if response.status_code == 204:
            return

        data = self.session.http.json(response, schema=_stream_schema)
        if data.get("cdnURL"):
            yield from HLSStream.parse_variant_playlist(self.session, data["cdnURL"]).items()


__plugin__ = Cam4
