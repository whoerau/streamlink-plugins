# Streamlink Plugins

A collection of third-party live-streaming plugins that can be loaded directly by Streamlink. The goal is for `streamlink <room-url> best` to produce real media data, not merely recognize the URL.

## Supported Sites

| Plugin | Room URL example | Playback method |
| --- | --- | --- |
| BongaCams | `https://bongacams.com/profile/<model>` | HLS |
| CAM4 | `https://cam4.com/<model>` | HLS |
| CamSoda | `https://camsoda.com/<model>` | Low-Latency HLS |
| Chaturbate | `https://chaturbate.com/<model>/` | HLS |
| MyFreeCams | `https://mfc.im/<model>` | HLS preview stream |
| ShowUp | `https://showup.tv/<model>` | Storm WebSocket / fMP4 |
| Stripchat | `https://stripchat.com/<model>` | Scrapling key recovery / Mouflon HLS |
| Zbiornik | `https://zbiornik.tv/<model>/` | Ant Media WebRTC / MPEG-TS |
| Generic | `generic://https://example.com/page` | HLS, DASH, or MP4 discovery |

MyFreeCams currently requires a username URL. Legacy numeric model-ID URLs are no longer supported.

## Installation

Python 3.10 or newer is required.

```bash
git clone https://github.com/whoerau/streamlink-plugins.git
cd streamlink-plugins
python -m pip install -e .
scrapling install
```

`scrapling install` performs the one-time browser setup required for Stripchat's dynamically obfuscated Mouflon streams.

To install the package as a dependency of another Python project:

```bash
python -m pip install \
  "whoerau-streamlink-plugins @ git+https://github.com/whoerau/streamlink-plugins.git"
scrapling install
```

For development with `uv`:

```bash
uv sync
uv run scrapling install
```

## Usage

Load the plugins from the repository directory:

```bash
streamlink --plugin-dir "$PWD" "https://stripchat.com/<model>" best
streamlink --plugin-dir "$PWD" "https://showup.tv/<model>" best
streamlink --plugin-dir "$PWD" "https://zbiornik.tv/<model>/" best
```

Select a named resolution when the broadcaster provides it:

```bash
streamlink --plugin-dir "$PWD" "https://stripchat.com/<model>" 1080p
streamlink --plugin-dir "$PWD" "https://showup.tv/<model>" 480p
streamlink --plugin-dir "$PWD" "https://zbiornik.tv/<model>/" 720p
```

Run `streamlink --plugin-dir "$PWD" <room-url>` without a quality argument to list the currently available resolutions. `best` and `worst` remain available as Streamlink aliases.

Write a stream to a file:

```bash
streamlink --plugin-dir "$PWD" "https://chaturbate.com/<model>/" best -o recording.ts
```

Applications can also register installed plugin modules directly:

```python
from streamlink import Streamlink
from stripchat import __plugin__ as StripchatPlugin

session = Streamlink()
session.plugins.update({"stripchat_custom": StripchatPlugin})
streams = session.streams("https://stripchat.com/<model>")
with streams["best"].open() as stream:
    data = stream.read(64 * 1024)
```

## Runtime Details

- Stripchat uses Scrapling's dynamic Chromium fetcher only to recover rotating Mouflon keys. Streamlink then parses and reads the native HLS variants, exposing resolutions such as `480p`, `720p`, and `1080p` when available.
- ShowUp reads the Storm `streamList`, exposes each server-provided resolution, and requests the exact selected fragmented-MP4 stream without relying on legacy RTMP.
- Zbiornik exposes the actual height of its single Ant Media WebRTC source, then encodes that source as H.264/AAC MPEG-TS. It does not invent extra transcoded qualities. This conversion adds some CPU usage and a small amount of latency.
- Plugins do not return a stream when a model is offline or broadcasting in a private or paid session.

## Verification

Run the offline regression tests:

```bash
python -m unittest -v
```

Check whether Streamlink is loading a plugin from this repository:

```bash
streamlink --plugin-dir "$PWD" --can-handle-url "https://stripchat.com/<model>"
streamlink --plugin-dir "$PWD" --show-matchers stripchat
```

Sites regularly change their APIs, CDNs, and playback protocols. For live verification, select a currently `public` or `online` model from the site's homepage and confirm that `best` can read media bytes rather than merely appearing in the stream list.
