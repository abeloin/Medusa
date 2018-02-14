# coding=utf-8

"""rTorrent Client."""

from __future__ import unicode_literals

import logging

from medusa import app, providers
from medusa.clients.torrent.generic import GenericClient
from medusa.helpers import is_info_hash_in_history, is_media_file, get_extension, is_already_processed_media, \
    is_info_hash_processed, get_provider_from_history
from medusa.logger.adapters.style import BraceAdapter
from medusa.providers.generic_provider import GenericProvider

try:
    import xmlrpc.client as xmlrpc_client
except ImportError:
    import xmlrpclib as xmlrpc_client

from lib.rtorrent import RTorrent

log = BraceAdapter(logging.getLogger(__name__))
log.logger.addHandler(logging.NullHandler())


class RTorrentAPI(GenericClient):
    """rTorrent API class."""

    def __init__(self, host=None, username=None, password=None):
        """Constructor.

        :param host:
        :type host: string
        :param username:
        :type username: string
        :param password:
        :type password: string
        """
        super(RTorrentAPI, self).__init__('rTorrent', host, username, password)

    def _get_auth(self):
        if self.auth is not None:
            return self.auth

        if not self.host:
            return

        tp_kwargs = {}
        if app.TORRENT_AUTH_TYPE != 'none':
            tp_kwargs['authtype'] = app.TORRENT_AUTH_TYPE

        if not app.TORRENT_VERIFY_CERT:
            tp_kwargs['check_ssl_cert'] = False

        if self.username and self.password:
            self.auth = RTorrent(self.host, self.username, self.password, True, tp_kwargs=tp_kwargs)
        else:
            self.auth = RTorrent(self.host, None, None, True)

        return self.auth

    @staticmethod
    def _get_params(result):
        params = []

        # Set label
        label = app.TORRENT_LABEL
        if result.series.is_anime:
            label = app.TORRENT_LABEL_ANIME
        if label:
            params.append('d.custom1.set={0}'.format(label))

        if app.TORRENT_PATH:
            params.append('d.directory.set={0}'.format(app.TORRENT_PATH))

        return params

    def _add_torrent_uri(self, result):

        if not (self.auth or result):
            return False

        try:
            params = self._get_params(result)
            # Send magnet to rTorrent and start it
            torrent = self.auth.load_magnet(result.url, result.hash, start=True, params=params)
            if not torrent:
                return False

        except Exception as msg:
            log.warning('Error while sending torrent: {error!r}',
                        {'error': msg})
            return False
        else:
            return True

    def _add_torrent_file(self, result):

        if not (self.auth or result):
            return False

        try:
            params = self._get_params(result)
            # Send torrent to rTorrent and start it
            torrent = self.auth.load_torrent(result.content, start=True, params=params)
            if not torrent:
                return False

        except Exception as msg:
            log.warning('Error while sending torrent: {error!r}',
                        {'error': msg})
            return False
        else:
            return True

    def test_authentication(self):
        """Test connection using authentication.

        :return:
        :rtype: tuple(bool, str)
        """
        try:
            self.auth = None
            self._get_auth()
        except xmlrpc_client.ProtocolError as e:
            log.warning('ProtocolError while trying to connect to {name}. Message is {message}',
                        {'name': self.name, 'message': e.errmsg})
            return False, 'Error: Unable to connect to {name}. Check log.'.format(name=self.name)
        except Exception:  # pylint: disable=broad-except
            log.warning('Exception while trying to connect to {name}.', name=self.name, exc_info=True)
            return False, 'Error: Unable to connect to {name}. Check log'.format(name=self.name)
        else:
            if self.auth is None:
                return False, 'Error: Unable to get {name} Authentication, check your config!'.format(name=self.name)
            else:
                return True, 'Success: Connected and Authenticated'

    def remove_ratio_reached(self):
        """Remove all Medusa torrents that ratio was reached.

        It loops in all hashes returned from client and check if it is in the snatch history
        if its then it checks if we already processed media from the torrent (episode status 'Downloaded')
        If is a RARed torrent then we don't have a media file so we check if that hash is from an
        episode that has a 'Downloaded' status


        # IDEA: A better implementation would be to add a specific view in rtorrent and methods.
        For more info: https://github.com/Sonarr/Sonarr/issues/2204#issuecomment-334925691
        """

        log.info('Checking rTorrent torrent status.')

        if not self.auth:
            try:
                self._get_auth()
            except xmlrpc_client.ProtocolError as e:
                log.warning('ProtocolError while trying to connect to {name}. Message is {message}',
                            {'name': self.name, 'message': e.errmsg}, exc_info=True)
                return False
            except Exception as e: # pylint: disable=broad-except
                log.warning('Exception while trying to connect to {name}.', name=self.name, exc_info=True)
                return False
            else:
                if self.auth is None:
                    log.warning('Unable to connect to {name}. Check settings? Host online?', name=self.name)
                    return False
                else:
                    log.debug('Connected and Authenticated to {name}.', name=self.name)

        all_providers = [temp_provider for temp_provider in providers.sorted_provider_list()
                         if temp_provider.provider_type == GenericProvider.TORRENT]

        for torrent in self.auth.get_torrents():
            log.debug('Torrent: {info_hash} - Name:{name}', {'info_hash': torrent.info_hash, 'name': torrent.name})
            if not is_info_hash_in_history(torrent.info_hash):
                log.debug('Torrent:{info_hash} - Not in history skipping.', info_hash=torrent.info_hash)
                continue

            # If both labels set, we expect to process only media with proper label.
            if ((torrent.get_custom(1) not in [app.TORRENT_LABEL, app.TORRENT_LABEL_ANIME]) and
               (app.TORRENT_LABEL and app.TORRENT_LABEL_ANIME)):

                log.debug('Torrent:{info_hash} - In history but label not '
                          '\'{torrent_label}\' or \'{torrent_label_anime}\' skipping.',
                          {'info_hash': torrent.info_hash, 'torrent_label': app.TORRENT_LABEL,
                           'torrent_label_anime': app.TORRENT_LABEL_ANIME})
                continue

            ingested = False
            for temp_file in torrent.get_files():
                log.debug('Torrent:{info_hash} - File: {file_path}',
                          {'info_hash': torrent.info_hash, 'file_path': temp_file.path})
                # Skipping all files that aren't a media or .rar file
                if not (is_media_file(temp_file.path) or get_extension(temp_file.path) == 'rar'):
                    log.debug('Torrent:{info_hash} - File: {file_path} - Skipping file.',
                              {'info_hash': torrent.info_hash, 'file_path': temp_file.path})
                    continue
                # Check if file was processed or check hash in case of RARed torrents
                if is_already_processed_media(temp_file.path) or is_info_hash_processed(torrent.info_hash):
                    log.debug('Torrent:{info_hash} - File: {file_path} - Torrent was processed,',
                              {'info_hash': torrent.info_hash, 'file_path': temp_file.path})
                    ingested = True

            # Don't need to check status if we are not going to remove it.
            if not ingested:
                log.debug('Torrent:{info_hash} - Not processed yet, skipping torrent.',
                          info_hash=torrent.info_hash)
                continue

            torrent_ratio = torrent.get_ratio()
            log.debug('Torrent:{info_hash} - Ratio is: {torrent_ratio}',
                      {'info_hash': torrent.info_hash, 'torrent_ratio': torrent_ratio})
            torrent_provider = get_provider_from_history(torrent.info_hash)
            log.debug('Torrent:{info_hash} - Provider is: {torrent_provider}',
                      {'info_hash': torrent.info_hash, 'torrent_provider': torrent_provider})
            # Default value to infinite
            provider_ratio = None
            for temp_provider in all_providers:
                if temp_provider.name == torrent_provider:
                    log.debug('Torrent:{info_hash} - Found provider info: {provider.name}',
                              {'info_hash': torrent.info_hash, 'provider.name': temp_provider.name})
                    provider_ratio = float(temp_provider.ratio)
                    break

            log.debug('Torrent:{info_hash} - Provider cutoff ratio is: {provider_ratio}',
                      {'info_hash': torrent.info_hash, 'provider_ratio': provider_ratio})

            if torrent_ratio >= provider_ratio and provider_ratio is not None and provider_ratio != -1:
                log.info('Torrent:{name} - Torrent Ratio: {torrent_ratio} - Provider cutoff ratio: {provider_ratio}'
                         ' - Torrent ratio is higher than the provider. Removing - Hash:{info_hash}',
                         {'info_hash': torrent.info_hash, 'name': torrent.name,
                          'torrent_ratio': torrent_ratio, 'provider_ratio': provider_ratio})

                torrent.erase()
            else:
                log.info('Torrent:{name} - Torrent Ratio: {torrent_ratio} - Provider cutoff ratio: {provider_ratio}'
                         ' - Torrent ratio is lower than the provider. Keeping - Hash:{info_hash}',
                         {'info_hash': torrent.info_hash, 'name': torrent.name,
                          'torrent_ratio': torrent_ratio, 'provider_ratio': provider_ratio})


api = RTorrentAPI
