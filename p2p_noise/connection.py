# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2018-2019 Fetch.AI Limited
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

"""This module contains the p2p noise connection."""

import asyncio
import logging
import os
import subprocess
import errno
import nacl.encoding
import nacl.signing
import struct
import posix
from pathlib import Path
from typing import List, Optional, Sequence, Union

from asyncio import AbstractEventLoop, CancelledError

from aea.configurations.base import ConnectionConfig, PublicId
from aea.connections.base import Connection
from aea.mail.base import Address, Envelope

logger = logging.getLogger(__name__)


NOISE_NODE_SOURCE = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "noise_node.go"
)
NOISE_NODE_CLARGS = list()

NOISE_NODE_LOG_FILE = "noise_node.log"


# TOFIX(LR) error: Cannot add child handler, the child watcher does not have a loop attached
async def _async_golang_get_deps(src: str, loop: AbstractEventLoop):
    cmd = ["go", "get", "-v", "-d", "."]

    try:
        logger.debug(cmd, loop)
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=os.path.dirname(src), loop=loop
        )
    except Exception as e:
        logger.error("While executing go get : {}".format(str(e)))
        raise e

    return proc


def _golang_get_deps(src: str, log_file_desc):
    cmd = ["go", "get", "-v", "-d", "."]

    try:
        logger.debug(cmd)
        proc = subprocess.Popen(
            cmd, cwd=os.path.dirname(src), stdout=log_file_desc, stderr=log_file_desc
        )
    except Exception as e:
        logger.error("While executing go get : {}".format(str(e)))
        raise e

    return proc


# TOFIX(LR) add typing
def _golang_run(src: str, args, env, log_file_desc):
    cmd = ["go", "run", src]

    cmd.extend(args)

    try:
        logger.debug(cmd)
        proc = subprocess.Popen(
            cmd, env=env, stdout=log_file_desc, stderr=log_file_desc
        )
    except Exception as e:
        logger.error("While executing go run {} {} : {}".format(src, args, str(e)))
        raise e

    return proc


class Curve25519PubKey:
    def __init__(
        self,
        *,
        strkey: Optional[str] = None,
        naclkey: Optional[nacl.signing.VerifyKey] = None
    ):
        if naclkey is not None:
            self._ed25519_pub = naclkey
        elif strkey is not None:
            self._ed25519_pub = nacl.signing.VerifyKey(
                strkey, encoder=nacl.encoding.HexEncoder
            )
        else:
            raise ValueError("Either 'strkey' or 'naclkey' must be set")

    def __str__(self):
        return self._ed25519_pub.encode(encoder=nacl.encoding.HexEncoder).decode(
            "ascii"
        )


class Curve25519PrivKey:
    def __init__(self, key: Optional[str] = None):
        if key is None:
            self._ed25519 = nacl.signing.SigningKey.generate()
        else:
            self._ed25519 = nacl.signing.SigningKey(
                key, encoder=nacl.encoding.HexEncoder
            )

    def __str__(self):
        return self._ed25519.encode(encoder=nacl.encoding.HexEncoder).decode("ascii")

    def hex(self):
        return self._ed25519.encode(encoder=nacl.encoding.HexEncoder).decode("ascii")

    def pub(self) -> Curve25519PubKey:
        return Curve25519PubKey(naclkey=self._ed25519.verify_key)


class Uri:
    def __init__(
        self,
        uri: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        if uri is not None:
            split = uri.split(":", 1)
            self._host = split[0]
            self._port = split[1]
        elif host is not None and port is not None:
            self._host = host
            self._port = port
        else:
            raise ValueError("Either 'uri' or both 'addr' and 'port' must be set")

    def __str__(self):
        return "{}:{}".format(self._host, self._port)

    def __repr__(self):
        return self.__str__()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port


# TOFIX(LR) NOT thread safe
class NoiseNode:
    r"""Noise p2p node as a subprocess with named pipes interface
    """

    def __init__(
        self,
        key: Curve25519PrivKey,
        source: Union[Path, str],
        clargs: Optional[List[str]] = [],
        uri: Optional[Uri] = None,
        entry_peers: Sequence[Uri] = [],
        log_file: Optional[str] = None,
    ):
        """
        Initialize a p2p noise node.

        :param key: ec25519 curve private key.
        :param uri: noise node ip address and port number in format ipaddress:port.
        :param entry_peers: noise entry peers ip address and port numbers.
        """

        # node id in the p2p network
        self.key = str(key)
        self.pub = str(key.pub())

        # node uri
        self.uri = uri

        # entry p
        self.entry_peers = entry_peers

        # node startup
        self.source = source
        self.clargs = clargs

        # log file
        self.log_file = log_file if log_file is not None else NOISE_NODE_LOG_FILE

        # named pipes (fifos)
        self.noise_to_aea_path = "/tmp/{}-noise_to_aea".format(self.pub[:5])
        self.aea_to_noise_path = "/tmp/{}-aea_to_noise".format(self.pub[:5])
        self._noise_to_aea = None
        self._aea_to_noise = None
        self._connection_attempts = 10

        #
        self._loop = None
        self.proc = None

    async def start(self) -> None:
        if self._loop is None:
            self._loop = asyncio.get_event_loop()

        # open log file
        self._log_file_desc = open(self.log_file, "a", 1)

        # get source deps
        # TOFIX(LR) async version
        # proc = await _async_golang_get_deps(self.source, loop=self._loop)
        # await proc.wait()
        proc = _golang_get_deps(self.source, self._log_file_desc)
        proc.wait()

        # setup fifos
        in_path = self.noise_to_aea_path
        out_path = self.aea_to_noise_path
        logger.debug("Creating pipes ({}, {})...".format(in_path, out_path))
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)
        os.mkfifo(in_path)
        os.mkfifo(out_path)

        # setup config
        env = os.environ
        env["ID"] = self.key + self.pub
        env["URI"] = str(self.uri)
        env["ENTRY_URI"] = ",".join(
            [str(uri) for uri in self.entry_peers if str(uri) != str(self.uri)]
        )
        env["NOISE_TO_AEA"] = in_path
        env["AEA_TO_NOISE"] = out_path

        # run node
        self.proc = _golang_run(self.source, self.clargs, env, self._log_file_desc)

        await self._connect()

    async def _connect(self) -> None:
        if self._connection_attempts == 1:
            logger.error("couldn't connect to noise p2p process")
            raise Exception("couldn't connect to noise p2p process")
            # TOFIX(LR) use proper exception
        self._connection_attempts -= 1

        logger.debug(
            "Attempt opening pipes {}, {}...".format(
                self.noise_to_aea_path, self.aea_to_noise_path
            )
        )

        self._noise_to_aea = posix.open(
            self.noise_to_aea_path, posix.O_RDONLY | os.O_NONBLOCK
        )

        try:
            self._aea_to_noise = posix.open(
                self.aea_to_noise_path, posix.O_WRONLY | os.O_NONBLOCK
            )
        except OSError as e:
            if e.errno == errno.ENXIO:
                await asyncio.sleep(0.8)
                await self._connect()
                return
            else:
                raise e

        # setup reader
        self._stream_reader = asyncio.StreamReader(loop=self._loop)
        self._reader_protocol = asyncio.StreamReaderProtocol(
            self._stream_reader, loop=self._loop
        )
        self._fileobj = os.fdopen(self._noise_to_aea, "r")
        await self._loop.connect_read_pipe(lambda: self._reader_protocol, self._fileobj)

        logger.info("Connected to noise node")

    @asyncio.coroutine
    def write(self, data: bytes) -> None:
        size = struct.pack("!I", len(data))
        posix.write(self._aea_to_noise, size)
        posix.write(self._aea_to_noise, data)
        # TOFIX(LR) can use asyncio.connect_write_pipe

    async def read(self) -> Optional[bytes]:
        try:
            logger.debug("Waiting for messages...")
            size = await self._stream_reader.readexactly(4)
            if not size:
                return None
            size = struct.unpack("!I", size)[0]
            data = await self._stream_reader.readexactly(size)
            if not data:
                return None
            return data
        except asyncio.streams.IncompleteReadError as e:
            logger.info(
                "Node disconnected while reading {}/{}".format(
                    len(e.partial), e.expected
                )
            )
            return None

    def stop(self) -> None:
        # TOFIX(LR) wait is blocking and proc can ignore terminate
        self.proc.terminate()
        self.proc.wait()


class P2PNoiseConnection(Connection):
    r"""A noise p2p node connection.
    """

    def __init__(
        self,
        key: Curve25519PrivKey,
        uri: Optional[Uri] = None,
        entry_peers: Sequence[Uri] = [],
        log_file: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize a p2p noise connection.

        :param key: ec25519 curve private key.
        :param uri: noise node ip address and port number in format ipaddress:port.
        :param entry_peers: noise entry peers ip address and port numbers.
        :param log_file: noise node log file
        """
        if kwargs.get("configuration") is None and kwargs.get("connection_id") is None:
            kwargs["connection_id"] = PublicId("fetchai", "p2p-noise", "0.1.0")
        super().__init__(**kwargs)

        if uri is None and len(entry_peers) == 0:
            raise ValueError("uri parameter must be set for genesis connection")

        # noise local node
        self.node = NoiseNode(
            key, NOISE_NODE_SOURCE, NOISE_NODE_CLARGS, uri, entry_peers, log_file
        )

    async def connect(self) -> None:
        """Set up the connection."""
        if self.connection_status.is_connected:
            return

        # start noise node
        await self.node.start()
        self.connection_status.is_connected = True

        # starting receiving msgs
        self._in_queue = asyncio.Queue()
        asyncio.ensure_future(self._receive_from_node(), loop=self._loop)

    async def disconnect(self) -> None:
        """
        Disconnect from the channel.

        """
        self.connection_status.is_connected = False
        await asyncio.coroutine(self.node.stop)()
        assert self._in_queue is not None, "Input queue not initialized."
        self._in_queue.put_nowait(None)

    async def receive(self, *args, **kwargs) -> Optional["Envelope"]:
        """
        Receive an envelope. Blocking.

        :return: the envelope received, or None.
        """
        try:
            assert self._in_queue is not None
            data = await self._in_queue.get()
            if data is None:
                logger.debug("Received None.")
                self.node.stop()
                self.connection_status.is_connected = False
                return None
                # TOFIX(LR) attempt restarting the node?
            logger.debug("Received data: {}".format(data))
            return Envelope.decode(data)
        except CancelledError:
            logger.debug("Receive cancelled.")
            return None
        except Exception as e:
            logger.exception(e)
            return None

    async def send(self, envelope: Envelope):
        """
        Send messages.

        :return: None
        """
        await self.node.write(envelope.encode())

    async def _receive_from_node(self) -> None:
        while True:
            data = await self.node.read()
            if data is None:
                break
            self._in_queue.put_nowait(data)

    @classmethod
    def from_config(
        cls, address: Address, configuration: ConnectionConfig
    ) -> "Connection":
        """
        Get the stub connection from the connection configuration.

        :param address: the address of the agent.
        :param configuration: the connection configuration object.
        :return: the connection object
        """
        noise_key_file = configuration.config.get("noise_key_file")  # Optional[str]
        noise_host = configuration.config.get("noise_host")  # Optional[str]
        noise_port = configuration.config.get("noise_port")  # Optional[int]
        entry_peers = list(configuration.config.get("noise_entry_peers"))
        log_file = configuration.config.get("log_file")  # Optional[str]

        if noise_key_file is None:
            key = Curve25519PrivKey()
        else:
            with open(noise_key_file, "r") as f:
                key = Curve25519PrivKey(f.read().strip)

        uri = None
        if noise_port is not None:
            if noise_host is not None:
                uri = Uri(host=noise_host, port=noise_port)
            else:
                uri = Uri(host="127.0.0.1", port=noise_port)

        entry_peers_uris = [Uri(uri) for uri in entry_peers]

        restricted_to_protocols_names = {
            p.name for p in configuration.restricted_to_protocols
        }
        excluded_protocols_names = {p.name for p in configuration.excluded_protocols}

        return P2PNoiseConnection(
            key,
            uri,
            entry_peers_uris,
            log_file,
            connection_id=configuration.public_id,
            restricted_to_protocols=restricted_to_protocols_names,
            excluded_protocols=excluded_protocols_names,
        )
