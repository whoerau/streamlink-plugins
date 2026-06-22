# streamlink-plugins

Third-party Streamlink plugin modules packaged for pip installation.

Install from Git:

```bash
python -m pip install "whoerau-streamlink-plugins @ git+ssh://git@github.com/whoerau/streamlink-plugins.git"
```

The plugin modules are installed as top-level modules, for example:

```python
import bongacams
import cam4
import camsoda
import myfreecams
```

Run the offline compatibility checks with:

```bash
python -m unittest -v
```

Known limitations:

- MyFreeCams supports username URLs; legacy numeric model-ID URLs are no longer resolved.
- Stripchat's current Mouflon-obfuscated HLS playlists are detected but not playable by Streamlink.
- ShowUp and Zbiornik use protocols unsupported by current Streamlink versions.
