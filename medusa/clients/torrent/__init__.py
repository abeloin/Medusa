# coding=utf-8
# Author: Nic Wolfe <nic@wolfeden.ca>
#
# This file is part of Medusa.
#
# Medusa is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Medusa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Medusa. If not, see <http://www.gnu.org/licenses/>.
"""Clients module."""

from __future__ import unicode_literals

from generic import GenericClient
from deluge_client import DelugeAPI
from deluged_client import DelugeDAPI
from download_station_client import DownloadStationAPI
from mlnet_client import MLNetAPI
from qbittorrent_client import QBittorrentAPI
from rtorrent_client import RTorrentAPI
from transmission_client import TransmissionAPI
from utorrent_client import UTorrentAPI

_clients = [
    'deluge',
    'deluged',
    'download_station',
    'mlnet',
    'qbittorrent',
    'rtorrent',
    'transmission',
    'utorrent',
]


def get_client_module(name):
    """Import the client module for the given name."""
    return __import__('{prefix}.{name}_client'.format(prefix=__name__, name=name.lower()), fromlist=_clients)


def get_client_class(name):
    """Return the client API class for the given name.

    :param name:
    :type name: string
    :return:
    :rtype: class
    """
    return get_client_module(name).api


def get_client_instance(name):
    """Return the client API class for the given name.

    :param name:
    :type name: string
    :return:
    :rtype: instance
    """
    for subclass in get_all_subclasses():
        if name == subclass().external_name:
            return subclass()


def get_all_subclasses():
    """Return list of immediate subclasses for GenericClient."""
    return GenericClient.__subclasses__()


def is_torrent_client(client):
    """Return True if client in all supported clients.

    :param client:
    :type client: string
    :return:
    :rtype: bool
    """
    if client in _clients:
        return True
    return False


def is_remove_client_supported(client):
    """Return True if client support remove torrent.

    :param client:
    :type client: string
    :return:
    :rtype: bool
    """
    for subclass in get_all_subclasses():
        if client == subclass().external_name and subclass().support_remove_from_client:
            return True

    return False
