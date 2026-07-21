import json
import re
import sys

from streamlink.plugin import Plugin, pluginmatcher

from browser_stream import ProcessStream
from curl_cffi import requests
from curl_cffi.const import CurlWsFlag

_url_re = re.compile(r'https?://(\w+.)?showup\.tv/(?P<channel>[A-Za-z0-9_-]+)')
_api_url = "https://api.showup.tv/api/next/broadcast/home-list/{category}"


@pluginmatcher(_url_re)
class ShowUp(Plugin):
    def _get_streams(self):
        channel = self.match.group("channel")
        headers = {
            "Origin": "https://showup.tv",
            "Referer": "https://showup.tv/",
            "X-Accept-Language": "pl",
        }
        for category in ("female", "male", "couple", "trans"):
            response = requests.get(
                _api_url.format(category=category),
                params={"create_socket_token": 0, "attach_edge_addresses": 1},
                headers=headers,
                impersonate="chrome",
                timeout=20,
            )
            if not response.ok:
                continue
            data = response.json()
            for item in data.get("list", []):
                username = (item.get("host") or {}).get("username")
                if item.get("isOnline") and username and username.casefold() == channel.casefold():
                    alias = (item.get("broadcast") or {}).get("aliasStreamKey")
                    servers = data.get("streamServers", {}).get("EDGE", [])
                    hosts = [server["address"] for server in servers if server.get("address")]
                    if alias and hosts:
                        try:
                            variants = _probe_variants(alias, hosts)
                        except Exception as error:
                            self.logger.warning("Could not list ShowUp qualities: %s", error)
                            variants = []
                        streams = {}
                        for variant in variants:
                            info = variant.get("streamInfo") or {}
                            quality = info.get("label") or (
                                f"{info['height']}p" if info.get("height") else None
                            )
                            stream_key = variant.get("streamKey")
                            if quality and stream_key:
                                streams[quality] = ProcessStream(
                                    self.session, "showup", alias, stream_key, *hosts
                                )
                        if streams:
                            return streams
                        return {
                            "live": ProcessStream(
                                self.session, "showup", alias, alias, *hosts
                            ),
                        }


def _send(websocket, packet_id, data):
    websocket.send(
        json.dumps({"packetId": packet_id, "data": data}),
        CurlWsFlag.TEXT,
    )


def _connect(hosts):
    session = requests.Session(impersonate="chrome")
    error = None
    for host in hosts:
        try:
            return session.ws_connect(
                f"wss://{host}/storm/v2/live",
                headers={"Origin": "https://showup.tv"},
                impersonate="chrome",
                timeout=20,
            )
        except Exception as ex:
            error = ex
    raise error or RuntimeError("No ShowUp edge server is available")


def _subscribe(websocket, alias):
    handshake = {
        "player": {
            "type": "js",
            "version": "1.3.0-beta.8",
            "branch": "Experimental",
            "protocolVer": 1,
        },
        "environment": {
            "domain": "showup.tv",
            "userAgent": "Mozilla/5.0",
            "locale": "pl-PL",
            "timezone": "Europe/Warsaw",
            "timezoneOffset": -120,
        },
        "capabilities": {
            "mse": True,
            "webcodecs": False,
            "hls": False,
            "webtransport": False,
            "sharedArrayBuffer": False,
            "videoCodecs": ["h264", "h264-high"],
            "audioCodecs": ["aac", "aac-he"],
        },
        "userId": None,
    }
    _send(websocket, "clientHandshake", handshake)
    while True:
        payload, flags = websocket.recv()
        if not flags & CurlWsFlag.TEXT:
            continue
        packet = json.loads(payload)
        packet_id = packet.get("packetId")
        data = packet.get("data") or {}
        if packet_id == "appInfo":
            _send(websocket, "appAuthRequest", {"secret": None})
        elif packet_id == "appAuthResult":
            if data.get("result") != "success":
                raise RuntimeError("ShowUp Storm authentication failed")
            _send(websocket, "subscribeRequest", {"streamKey": alias})
        elif packet_id == "subscribeResult":
            if data.get("status") != "success":
                raise RuntimeError("ShowUp Storm subscription failed")
            return data.get("streamList") or []


def _probe_variants(alias, hosts):
    websocket = _connect(hosts)
    try:
        return _subscribe(websocket, alias)
    finally:
        try:
            websocket.close()
        except Exception:
            pass


def _capture(alias, selected_key, *hosts):
    websocket = _connect(hosts)
    try:
        variants = _subscribe(websocket, alias)
        selected = next(
            (variant for variant in variants if variant.get("streamKey") == selected_key),
            max(
                variants,
                key=lambda item: (
                    (item.get("streamInfo") or {}).get("height", 0),
                    (item.get("streamInfo") or {}).get("bitrate", 0),
                ),
                default={"streamKey": alias},
            ),
        )
        # Each named Streamlink quality requests its exact Storm stream key.
        # 每个 Streamlink 画质名称都请求对应的 Storm stream key。
        _send(websocket, "playRequest", {
            "streamKey": selected["streamKey"],
            "subscriptionKey": alias,
            "packetizer": "mse",
            "startTime": 0,
        })
        while True:
            payload, flags = websocket.recv()
            if flags & CurlWsFlag.BINARY:
                try:
                    sys.stdout.buffer.write(payload)
                    sys.stdout.buffer.flush()
                except BrokenPipeError:
                    return
                continue
            if flags & CurlWsFlag.TEXT:
                packet = json.loads(payload)
                if (
                    packet.get("packetId") == "playResult"
                    and (packet.get("data") or {}).get("status") != "success"
                ):
                    raise RuntimeError("ShowUp Storm playback failed")
    finally:
        try:
            websocket.close()
        except Exception:
            pass


__plugin__ = ShowUp


if __name__ == "__main__" and sys.argv[1:2] == ["--capture"]:
    _capture(sys.argv[2], sys.argv[3], *sys.argv[4:])
