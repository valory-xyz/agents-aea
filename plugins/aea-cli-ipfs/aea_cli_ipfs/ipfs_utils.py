# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2022 Valory AG
#   Copyright 2018-2020 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------
"""Ipfs utils for `ipfs cli command`."""
import os
import shutil
import signal
import subprocess  # nosec
from pathlib import Path
from typing import Dict, List, Optional, Tuple, cast

import ipfshttpclient  # type: ignore
import requests


DEFAULT_IPFS_URL = "/ip4/127.0.0.1/tcp/5001"
ALLOWED_CONNECTION_TYPES = ("tcp",)
ALLOWED_ADDR_TYPES = ("ip4", "dns")
ALLOWED_PROTOCOL_TYPES = ("http", "https")
MULTIADDR_FORMAT = "/{dns,dns4,dns6,ip4}/<host>/tcp/<port>/protocol"
IPFS_NODE_CHECK_ENDPOINT = "/api/v0/id"


def _verify_attr(name: str, attr: str, allowed: Tuple[str, ...]) -> None:
    """Varify various attributes of ipfs address."""

    if attr not in allowed:
        raise ValueError(f"{name} should be one of the {allowed}, provided: {attr}")


def resolve_addr(addr: str) -> Tuple[str, ...]:
    """
    Multiaddr resolver.

    :param addr: multiaddr string.
    :return: http URL
    """
    _, addr_scheme, host, conn_type, *extra_data = addr.split("/")

    if len(extra_data) > 2:  # pylint: disable=no-else-raise
        raise ValueError(
            f"Invalid multiaddr string provided, valid format: {MULTIADDR_FORMAT}. Provided: {addr}"
        )
    elif len(extra_data) == 2:
        port, protocol, *_ = extra_data
    elif len(extra_data) == 1:
        (port,) = extra_data
        protocol = "http"
    else:
        port = "5001"
        protocol = "http"

    _verify_attr("Address type", addr_scheme, ALLOWED_ADDR_TYPES)
    _verify_attr("Connection", conn_type, ALLOWED_CONNECTION_TYPES)
    _verify_attr("Protocol", protocol, ALLOWED_PROTOCOL_TYPES)

    return addr_scheme, host, conn_type, port, protocol


def addr_to_url(addr: str) -> str:
    """Convert address to url."""

    _, host, _, port, protocol = resolve_addr(addr)
    return f"{protocol}://{host}:{port}"


class IPFSDaemon:
    """
    Set up the IPFS daemon.

    :raises Exception: if IPFS is not installed.
    """

    def __init__(self, offline: bool = False, api_url: str = "http://127.0.0.1:5001"):
        """Initialise IPFS daemon."""

        if api_url.endswith("/"):
            api_url = api_url[:-1]

        self.api_url = api_url + IPFS_NODE_CHECK_ENDPOINT
        self.process = None  # type: Optional[subprocess.Popen]
        self.offline = offline
        self._check_ipfs()

    @staticmethod
    def _check_ipfs() -> None:
        """Check if IPFS node is running."""
        res = shutil.which("ipfs")
        if res is None:
            raise Exception("Please install IPFS first!")
        process = subprocess.Popen(  # nosec
            ["ipfs", "--version"], stdout=subprocess.PIPE, env=os.environ.copy(),
        )
        output, _ = process.communicate()
        if b"0.6.0" not in output:
            raise Exception(
                "Please ensure you have version 0.6.0 of IPFS daemon installed."
            )

    def is_started_externally(self) -> bool:
        """Check daemon was started externally."""
        try:
            x = requests.post(self.api_url)
            return x.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def is_started_internally(self) -> bool:
        """Check daemon was started internally."""
        return bool(self.process)

    def is_started(self) -> bool:
        """Check daemon was started."""
        return self.is_started_externally() or self.is_started_internally()

    def start(self) -> None:
        """Run the ipfs daemon."""
        cmd = ["ipfs", "daemon", "--offline"] if self.offline else ["ipfs", "daemon"]
        self.process = subprocess.Popen(  # nosec
            cmd, stdout=subprocess.PIPE, env=os.environ.copy(),
        )
        empty_outputs = 0
        for stdout_line in iter(self.process.stdout.readline, ""):
            if b"Daemon is ready" in stdout_line:
                break
            if stdout_line == b"":
                empty_outputs += 1
                if empty_outputs >= 5:
                    raise RuntimeError("Could not start IPFS daemon.")

    def stop(self) -> None:  # pragma: nocover
        """Terminate the ipfs daemon if it was started internally."""
        if self.process is None:
            return
        self.process.stdout.close()
        self.process.send_signal(signal.SIGTERM)
        self.process.wait(timeout=30)
        poll = self.process.poll()
        if poll is None:
            self.process.terminate()
            self.process.wait(2)

    def __enter__(self) -> None:
        """Run the ipfs daemon."""
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Terminate the ipfs daemon."""
        self.stop()


class BaseIPFSToolException(Exception):
    """Base ipfs tool exception."""


class RemoveError(BaseIPFSToolException):
    """Exception on remove."""


class PublishError(BaseIPFSToolException):
    """Exception on publish."""


class NodeError(BaseIPFSToolException):
    """Exception for node connection check."""


class DownloadError(BaseIPFSToolException):
    """Exception on download failed."""


class IPFSTool:
    """IPFS tool to add, publish, remove, download directories."""

    _addr: Optional[str] = None

    def __init__(self, addr: Optional[str] = None, offline: bool = True):
        """
        Init tool.

        :param addr: multiaddr string for IPFS client.
        :param offline: ipfs mode.
        """

        if addr is not None:
            _ = resolve_addr(addr)  # verify addr
            self._addr = addr

        self.client = ipfshttpclient.Client(addr=self.addr)
        self.daemon = IPFSDaemon(offline=offline, api_url=addr_to_url(self.addr))

    @property
    def addr(self,) -> str:
        """Node address"""
        if self._addr is None:
            self._addr = os.environ.get("OPEN_AEA_IPFS_ADDR", DEFAULT_IPFS_URL)
        return cast(str, self._addr)

    def add(self, dir_path: str, pin: bool = True) -> Tuple[str, str, List]:
        """
        Add directory to ipfs.

        It wraps into directory.

        :param dir_path: str, path to dir to publish
        :param pin: bool, pin object or not

        :return: dir name published, hash, list of items processed
        """
        response = self.client.add(
            dir_path, pin=pin, recursive=True, wrap_with_directory=True
        )
        return response[-2]["Name"], response[-1]["Hash"], response[:-1]

    def remove(self, hash_id: str) -> Dict:
        """
        Remove dir added by it's hash.

        :param hash_id: str. hash of dir to remove

        :return: dict with unlinked items.
        """
        try:
            return self.client.pin.rm(hash_id, recursive=True)
        except ipfshttpclient.exceptions.ErrorResponse as e:
            raise RemoveError(f"Error on {hash_id} remove: {str(e)}") from e

    def download(self, hash_id: str, target_dir: str, fix_path: bool = True) -> None:
        """
        Download dir by it's hash.

        :param hash_id: str. hash of file to download
        :param target_dir: str. directory to place downloaded
        :param fix_path: bool. default True. on download don't wrap result in to hash_id directory.
        """
        if not os.path.exists(target_dir):  # pragma: nocover
            os.makedirs(target_dir, exist_ok=True)

        if os.path.exists(os.path.join(target_dir, hash_id)):  # pragma: nocover
            raise DownloadError(f"{hash_id} was already downloaded to {target_dir}")

        self.client.get(hash_id, target_dir)

        downloaded_path = str(Path(target_dir) / hash_id)

        if fix_path:
            # self.client.get creates result with hash name
            # and content, but we want content in the target dir
            try:
                for each_file in Path(downloaded_path).iterdir():  # grabs all files
                    shutil.move(str(each_file), target_dir)
            except shutil.Error as e:  # pragma: nocover
                raise DownloadError(f"error on move files {str(e)}") from e

        os.rmdir(downloaded_path)

    def publish(self, hash_id: str) -> Dict:
        """
        Publish directory by it's hash id.

        :param hash_id: hash of the directory to publish.

        :return: dict of names it was publish for.
        """
        try:
            return self.client.name.publish(hash_id)
        except ipfshttpclient.exceptions.TimeoutError as e:  # pragma: nocover
            raise PublishError(
                "can not publish within timeout, check internet connection!"
            ) from e

    def check_ipfs_node_running(self) -> None:
        """Check ipfs node running."""
        try:
            self.client.id()
        except ipfshttpclient.exceptions.CommunicationError as e:
            raise NodeError(f"Can not connect to node. Is node running?:\n{e}") from e
