import importlib
import unittest

from bongacams import _room_schema
from camsoda import _api_schema
from myfreecams import MyFreeCams
from stripchat import _api_schema as stripchat_schema


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


if __name__ == "__main__":
    unittest.main()
