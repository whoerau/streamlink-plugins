import base64
import importlib
import unittest
from unittest.mock import Mock, patch

from browser_stream import ProcessStream
from bongacams import BongaCams, _room_schema
from camsoda import _api_schema
from generic import Generic
from myfreecams import MyFreeCams
from showup import ShowUp
from streamlink import Streamlink
from stripchat import Stripchat, derive_mouflon_keys, rewrite_mouflon_playlist
from stripchat import _api_schema as stripchat_schema
from zbiornik import Zbiornik


class PluginTests(unittest.TestCase):
    def test_all_plugins_import(self):
        for name in (
            "bongacams", "cam4", "camsoda", "chaturbate", "generic",
            "myfreecams", "showup", "stripchat", "zbiornik",
        ):
            self.assertTrue(importlib.import_module(name).__plugin__)

    def test_current_api_shapes(self):
        _room_schema.validate({
            "status": "success",
            "localData": {"videoServerUrl": "//edge.example"},
            "performerData": {"username": "model", "isOnline": True, "showType": "public"},
        })
        _api_schema.validate({
            "stream": {
                "status": "online",
                "token": "token",
                "edge_servers": ["edge.example"],
                "stream_name": "stream",
            },
        })
        stripchat_schema.validate({
            "cam": [],
            "user": {"user": {"id": 1, "status": "off", "isLive": False}},
        })
        stripchat_schema.validate({"error": "Not Found"})

    def test_myfreecams_preview_url(self):
        html = """
            <div class="campreview"
                 data-cam-preview-server-id-value="123"
                 data-cam-preview-model-id-value="456"
                 data-cam-preview-is-wzobs-value="true"></div>
        """
        self.assertEqual(
            MyFreeCams._preview_url(html),
            "https://previews.myfreecams.com/hls/NxServer/123/"
            "ngrp:mfc_a_100000456.f4v_mobile_mhp1080_previewurl/playlist.m3u8",
        )
        self.assertIsNone(MyFreeCams._preview_url("<div></div>"))

    def test_homepage_model_urls_are_supported(self):
        cases = (
            (BongaCams, "https://bongacams.com/profile/Example-Model", "Example-Model"),
            (BongaCams, "https://www.bongacams.com/Example-Model", "Example-Model"),
            (MyFreeCams, "https://mfc.im/Example_Model", "Example_Model"),
            (
                MyFreeCams,
                "https://www.myfreecams.com/?go_to_room=Example_Model",
                "Example_Model",
            ),
        )

        for plugin, url, expected_username in cases:
            match = next(
                matcher.pattern.match(url)
                for matcher in plugin.matchers
                if matcher.pattern.match(url)
            )
            username = (
                match.groupdict().get("username")
                or match.groupdict().get("room_username")
                or match.groupdict().get("short_username")
            )
            self.assertEqual(expected_username, username)

    def test_generic_uses_current_streamlink_plugin_api(self):
        session = Streamlink()
        plugin = Generic(session, "generic://https://example.com/watch")
        self.assertEqual(plugin.url, "https://example.com/watch")
        self.assertTrue(any(
            matcher.pattern.match("generic://https://example.com/watch")
            for matcher in Generic.matchers
        ))

    @patch("stripchat.MouflonHLSStream.parse_variant_playlist")
    @patch("stripchat.refresh_mouflon_keys", return_value={"key": "xor:AA=="})
    @patch("stripchat.requests.get")
    def test_stripchat_returns_resolution_streams(self, get, _refresh, variants):
        response = Mock()
        response.json.return_value = {
            "cam": {"isCamAvailable": True, "streamName": "123"},
            "user": {"user": {"id": 1, "status": "public", "isLive": True}},
        }
        get.return_value = response
        variants.return_value = {"720p": Mock(), "480p": Mock()}

        streams = Stripchat(Streamlink(), "https://stripchat.com/model")._get_streams()
        self.assertEqual(set(streams), {"480p", "720p"})

    def test_stripchat_mouflon_key_derivation_and_rewrite(self):
        clear_token = "segment-token"
        xor_key = b"secret"
        encrypted = bytes(
            value ^ xor_key[index % len(xor_key)]
            for index, value in enumerate(clear_token.encode())
        )
        encoded = base64.b64encode(encrypted).decode().rstrip("=")[::-1]
        encrypted_uri = f"https://media-hls.doppiocdn.com/hls/1_2_{encoded}_3.mp4"
        clear_uri = f"https://media-hls.doppiocdn.com/hls/1_2_{clear_token}_3.mp4"
        playlist = "\n".join((
            "#EXTM3U",
            "#EXT-X-MOUFLON:PSCH:abc:key-id",
            f"#EXT-X-MOUFLON:URI:{encrypted_uri}",
            "https://media-hls.doppiocdn.com/hls/1_2/media.mp4",
        ))
        keys = derive_mouflon_keys([playlist], [clear_uri])
        self.assertIn("key-id", keys)
        rewritten = rewrite_mouflon_playlist(playlist, keys)
        self.assertIn(clear_token, rewritten)
        self.assertNotIn("#EXT-X-MOUFLON:URI", rewritten)

    @patch("showup._probe_variants")
    @patch("showup.requests.get")
    def test_showup_returns_resolution_streams(self, get, probe):
        response = Mock(ok=True)
        response.json.return_value = {
            "list": [{
                "isOnline": True,
                "host": {"username": "Model"},
                "broadcast": {"aliasStreamKey": "alias"},
            }],
            "streamServers": {"EDGE": [{"address": "edge.example"}]},
        }
        get.return_value = response
        probe.return_value = [
            {"streamKey": "alias", "streamInfo": {"label": "720p", "height": 720}},
            {"streamKey": "alias_480p", "streamInfo": {"label": "480p", "height": 480}},
        ]

        streams = ShowUp(Streamlink(), "https://showup.tv/model")._get_streams()
        self.assertEqual(set(streams), {"480p", "720p"})
        self.assertIsInstance(streams["480p"], ProcessStream)
        self.assertEqual(
            streams["480p"].command[-5:],
            ["showup", "--capture", "alias", "alias_480p", "edge.example"],
        )

    @patch("zbiornik.requests.get")
    def test_zbiornik_returns_webrtc_stream(self, get):
        response = Mock(text='''
            <script>var streams = [{
                "nick":"Model","broadcasturl":"123-public",
                "server":"edge.example","id":"123","width":854,"height":480
            }];</script>
        ''')
        get.return_value = response

        streams = Zbiornik(Streamlink(), "https://zbiornik.tv/model/")._get_streams()
        self.assertEqual(set(streams), {"480p"})
        self.assertIsInstance(streams["480p"], ProcessStream)
        self.assertEqual(
            streams["480p"].command[-4:],
            ["zbiornik", "--capture", "edge.example", "123-public"],
        )


if __name__ == "__main__":
    unittest.main()
