import asyncio
import json
import re
import sys

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.utils.parse import parse_json

from browser_stream import ProcessStream
from curl_cffi import requests


_url_re = re.compile(
    r'^https?://(?:www\.)?zbiornik\.tv/(?P<channel>[^/]+)/?$')


@pluginmatcher(_url_re)
class Zbiornik(Plugin):
    _url_re = _url_re
    _streams_re = re.compile(r'''var\sstreams\s*=\s*(?P<data>\[.+?\]);''', re.S)

    _streams_schema = validate.Schema([{
        'nick': str,
        'broadcasturl': str,
        'server': str,
        'id': str,
        validate.optional('width'): validate.any(int, None),
        validate.optional('height'): validate.any(int, None),
    }])

    def _get_streams(self):
        channel = self._url_re.match(self.url).group('channel')
        res = requests.get(
            "https://zbiornik.tv/",
            cookies={"adult": "1"},
            impersonate="chrome",
            timeout=20,
        )
        res.raise_for_status()

        m = self._streams_re.search(res.text)
        if not m:
            return

        _streams = parse_json(m.group('data'), schema=self._streams_schema)
        for stream in _streams:
            if stream["nick"].casefold() == channel.casefold():
                height = stream.get("height")
                if not height:
                    try:
                        metadata = requests.get(
                            "https://{}/AntMediaZbiornik/rest/v2/broadcasts/{}".format(
                                stream["server"], stream["broadcasturl"]
                            ),
                            impersonate="chrome",
                            timeout=20,
                        ).json()
                        height = metadata.get("height")
                    except Exception:
                        height = None
                quality = f"{height}p" if isinstance(height, int) and height > 0 else "live"
                # Ant Media has one WebRTC source; expose its measured source height.
                # Ant Media 只有单一 WebRTC 源，按实测源高度命名。
                return {
                    quality: ProcessStream(
                        self.session,
                        "zbiornik",
                        stream["server"],
                        stream["broadcasturl"],
                    ),
                }


async def _capture_webrtc(server, stream_id):
    import websockets
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaRecorder
    from aiortc.sdp import candidate_from_sdp

    peer = RTCPeerConnection()
    recorder = MediaRecorder(
        sys.stdout.buffer,
        format="mpegts",
        options={"mpegts_flags": "resend_headers"},
    )
    recorder_started = False

    @peer.on("track")
    def on_track(track):
        recorder.addTrack(track)

    try:
        async with websockets.connect(
            f"wss://{server}/AntMediaZbiornik/websocket",
            origin="https://zbiornik.tv",
            user_agent_header="Mozilla/5.0",
            open_timeout=20,
        ) as websocket:
            await websocket.send(json.dumps({
                "command": "play",
                "streamId": stream_id,
                "token": "",
                "subscriberId": "",
                "subscriberCode": "",
                "viewerInfo": "streamlink",
            }))

            async for raw_message in websocket:
                message = json.loads(raw_message)
                if message.get("command") == "takeConfiguration" and message.get("type") == "offer":
                    await peer.setRemoteDescription(RTCSessionDescription(
                        sdp=message["sdp"],
                        type="offer",
                    ))
                    answer = await peer.createAnswer()
                    await peer.setLocalDescription(answer)
                    await websocket.send(json.dumps({
                        "command": "takeConfiguration",
                        "streamId": stream_id,
                        "type": "answer",
                        "sdp": peer.localDescription.sdp,
                    }))
                elif message.get("command") == "takeCandidate":
                    candidate = candidate_from_sdp(message["candidate"].split(":", 1)[-1])
                    candidate.sdpMid = message.get("id")
                    candidate.sdpMLineIndex = message.get("label")
                    await peer.addIceCandidate(candidate)
                elif message.get("definition") == "play_started" and not recorder_started:
                    await recorder.start()
                    recorder_started = True
    finally:
        if recorder_started:
            await recorder.stop()
        await peer.close()


__plugin__ = Zbiornik


if __name__ == "__main__" and sys.argv[1:2] == ["--capture"]:
    asyncio.run(_capture_webrtc(sys.argv[2], sys.argv[3]))
