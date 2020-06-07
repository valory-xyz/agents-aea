# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
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

"""HTTP client connection and channel"""

import asyncio
import json
import logging
from asyncio import CancelledError
from typing import Optional, Set, Union, cast

import requests

from aea.configurations.base import PublicId
from aea.connections.base import Connection
from aea.mail.base import Address, Envelope, EnvelopeContext

from packages.fetchai.protocols.http.message import HttpMessage

SUCCESS = 200
NOT_FOUND = 404
REQUEST_TIMEOUT = 408
SERVER_ERROR = 500
PUBLIC_ID = PublicId.from_str("fetchai/http_client:0.3.0")

logger = logging.getLogger("aea.packages.fetchai.connections.http_client")

RequestId = str


class HTTPClientChannel:
    """A wrapper for a HTTPClient."""

    def __init__(
        self,
        agent_address: Address,
        address: str,
        port: int,
        connection_id: PublicId,
        excluded_protocols: Optional[Set[PublicId]] = None,
        restricted_to_protocols: Optional[Set[PublicId]] = None,
    ):
        """
        Initialize an http client channel.

        :param agent_address: the address of the agent.
        :param address: server hostname / IP address
        :param port: server port number
        :param excluded_protocols: this connection cannot handle messages adhering to any of the protocols in this set
        :param restricted_to_protocols: this connection can only handle messages adhering to protocols in this set
        """
        self.agent_address = agent_address
        self.address = address
        self.port = port
        self.connection_id = connection_id
        self.restricted_to_protocols = restricted_to_protocols
        self.in_queue = None  # type: Optional[asyncio.Queue]  # pragma: no cover
        self.loop = (
            None
        )  # type: Optional[asyncio.AbstractEventLoop]  # pragma: no cover
        self.excluded_protocols = excluded_protocols
        self.is_stopped = True
        logger.info("Initialised the HTTP client channel")

    def connect(self):
        """Connect."""
        pass

    def send(self, request_envelope: Envelope) -> None:
        """
        Convert an http envelope into an http request, send the http request, wait for and receive its response, translate the response into a response envelop,
        and send the response envelope to the in-queue.

        :param request_envelope: the envelope containing an http request
        :return: None
        """
        if self.excluded_protocols is not None:
            if request_envelope.protocol_id in self.excluded_protocols:
                logger.error(
                    "This envelope cannot be sent with the http client connection: protocol_id={}".format(
                        request_envelope.protocol_id
                    )
                )
                raise ValueError("Cannot send message.")

            if request_envelope is not None:
                assert isinstance(
                    request_envelope.message, HttpMessage
                ), "Message not of type HttpMessage"
                request_http_message = cast(HttpMessage, request_envelope.message)
                if (
                    request_http_message.performative
                    == HttpMessage.Performative.REQUEST
                ):
                    response = requests.request(
                        method=request_http_message.method,
                        url=request_http_message.url,
                        headers=request_http_message.headers,
                        data=request_http_message.bodyy,
                    )
                    response_envelope = self.to_envelope(
                        self.connection_id, request_http_message, response
                    )
                    self.in_queue.put_nowait(response_envelope)  # type: ignore
                else:
                    logger.warning(
                        "The HTTPMessage performative must be a REQUEST. Envelop dropped."
                    )

    def to_envelope(
        self,
        connection_id: PublicId,
        http_request_message: HttpMessage,
        http_response: requests.models.Response,
    ) -> Envelope:
        """
        Convert an HTTP response object (from the 'requests' library) into an Envelope containing an HttpMessage (from the 'http' Protocol).

        :param connection_id: the connection id
        :param http_request_message: the message of the http request envelop
        :param http_response: the http response object
        """

        context = EnvelopeContext(connection_id=connection_id)
        http_message = HttpMessage(
            dialogue_reference=http_request_message.dialogue_reference,
            target=http_request_message.target,
            message_id=http_request_message.message_id,
            performative=HttpMessage.Performative.RESPONSE,
            status_code=http_response.status_code,
            headers=json.dumps(dict(http_response.headers)),
            status_text=http_response.reason,
            bodyy=http_response.content if http_response.content is not None else b"",
            version="",
        )
        envelope = Envelope(
            to=self.agent_address,
            sender="HTTP Server",
            protocol_id=PublicId.from_str("fetchai/http:0.2.0"),
            context=context,
            message=http_message,
        )
        return envelope

    def disconnect(self) -> None:
        """Disconnect."""
        if not self.is_stopped:
            logger.info("HTTP Client has shutdown on port: {}.".format(self.port))
            self.is_stopped = True


class HTTPClientConnection(Connection):
    """Proxy to the functionality of the web client."""

    connection_id = PUBLIC_ID

    def __init__(self, **kwargs):
        """Initialize a HTTP client connection."""
        super().__init__(**kwargs)
        host = cast(str, self.configuration.config.get("host"))
        port = cast(int, self.configuration.config.get("port"))
        assert host is not None and port is not None, "host and port must be set!"
        self.channel = HTTPClientChannel(
            self.address,
            host,
            port,
            connection_id=self.connection_id,
            excluded_protocols=self.excluded_protocols,
        )

    async def connect(self) -> None:
        """
        Connect to a HTTP server.

        :return: None
        """
        if not self.connection_status.is_connected:
            self.connection_status.is_connected = True
            self.channel.in_queue = asyncio.Queue()
            self.channel.loop = self.loop
            self.channel.connect()

    async def disconnect(self) -> None:
        """
        Disconnect from a HTTP server.

        :return: None
        """
        if self.connection_status.is_connected:
            self.connection_status.is_connected = False
            self.channel.disconnect()

    async def send(self, envelope: "Envelope") -> None:
        """
        Send an envelope.

        :param envelope: the envelop
        :return: None
        """
        if not self.connection_status.is_connected:
            raise ConnectionError(
                "Connection not established yet. Please use 'connect()'."
            )  # pragma: no cover
        self.channel.send(envelope)

    async def receive(self, *args, **kwargs) -> Optional[Union["Envelope", None]]:
        """
        Receive an envelope.

        :return: the envelope received, or None.
        """
        if not self.connection_status.is_connected:
            raise ConnectionError(
                "Connection not established yet. Please use 'connect()'."
            )  # pragma: no cover
        assert self.channel.in_queue is not None
        try:
            envelope = await self.channel.in_queue.get()
            if envelope is None:
                return None  # pragma: no cover
            return envelope
        except CancelledError:  # pragma: no cover
            return None
