import logging
import re

from streamlink.exceptions import PluginError
from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import useragents, validate
from streamlink.utils.parse import parse_json

log = logging.getLogger(__name__)


_url_re = re.compile(
    r'^https?://(?:www\.)?zbiornik\.tv/(?P<channel>[^/]+)/?$')


@pluginmatcher(_url_re)
class Zbiornik(Plugin):
    SWF_URL = 'https://zbiornik.tv/wowza.swf'
    _url_re = _url_re
    _streams_re = re.compile(r'''var\sstreams\s*=\s*(?P<data>\[.+\]);''')
    _user_re = re.compile(r'''var\suser\s*=\s*(?P<data>\{[^;]+\});''')

    _user_schema = validate.Schema({
        'wowzaIam': {
            'phash': str,
        }
    }, validate.get('wowzaIam'))

    _streams_schema = validate.Schema([{
        'nick': str,
        'broadcasturl': str,
        'server': str,
        'id': str,
    }])

    def _get_streams(self):
        raise PluginError("RTMP streams are not supported by current Streamlink versions")
        log.debug('Version 2018-07-12')
        log.info('This is a custom plugin. ')
        channel = self._url_re.match(self.url).group('channel')
        log.info('Channel: {0}'.format(channel))
        self.session.http.headers.update({'User-Agent': useragents.FIREFOX})
        self.session.http.parse_cookies('adult=1')
        res = self.session.http.get(self.url)

        m = self._streams_re.search(res.text)
        if not m:
            log.debug('No streams data found.')
            return

        m2 = self._user_re.search(res.text)
        if not m:
            log.debug('No user data found.')
            return

        _streams = parse_json(m.group('data'), schema=self._streams_schema)
        _user = parse_json(m2.group('data'), schema=self._user_schema)

        _x = []
        for _s in _streams:
            if _s.get('nick') == channel:
                _x = _s
                break

        if not _x:
            log.error('Channel is not available.')
            return

        app = 'videochat/?{0}'.format(_user['phash'])
        rtmp = 'rtmp://{0}/videochat/'.format(_x['server'])

        params = {
            'rtmp': rtmp,
            'pageUrl': self.url,
            'app': app,
            'playpath': _x['broadcasturl'],
            'swfVfy': self.SWF_URL,
            'live': True
        }
        return {'live': RTMPStream(self.session, params=params)}


__plugin__ = Zbiornik
