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

"""Prometheus connection and channel."""

import asyncio
import logging
import prometheus_client
from typing import Optional, cast, Any, Dict, Union, Tuple
from concurrent.futures.thread import ThreadPoolExecutor

from aea.common import Address
from aea.configurations.base import ConnectionConfig, PublicId
from aea.connections.base import Connection, ConnectionStates
from aea.crypto.wallet import CryptoStore
from aea.exceptions import enforce
from aea.identity.base import Identity
from aea.mail.base import Envelope, Message
from packages.fetchai.protocols.prometheus.message import PrometheusMessage
from packages.fetchai.protocols.prometheus.dialogues import PrometheusDialogue
from packages.fetchai.protocols.prometheus.dialogues import PrometheusDialogues as BasePrometheusDialogues


from aea.protocols.dialogue.base import Dialogue as BaseDialogue
from aea.protocols.dialogue.base import DialogueLabel

_default_logger = logging.getLogger("aea.packages.fetchai.connections.prometheus")

PUBLIC_ID = PublicId.from_str("fetchai/prometheus:0.1.0")

class PrometheusDialogues(BasePrometheusDialogues):
    """The dialogues class keeps track of all prometheus dialogues."""

    def __init__(self, **kwargs) -> None:
        """
        Initialize dialogues.

        :return: None
        """

        def role_from_first_message(  # pylint: disable=unused-argument
            message: Message, receiver_address: Address
        ) -> BaseDialogue.Role:
            """Infer the role of the agent from an incoming/outgoing first message

            :param message: an incoming/outgoing first message
            :param receiver_address: the address of the receiving agent
            :return: The role of the agent
            """
            # The server connection maintains the dialogue on behalf of the agent
            return PrometheusDialogue.Role.SERVER

        BasePrometheusDialogues.__init__(
            self,
            self_address=str(PUBLIC_ID),
            role_from_first_message=role_from_first_message,
            **kwargs,
        )


class PrometheusChannel:
    """A wrapper of the prometheus environment."""

    THREAD_POOL_SIZE = 3

    def __init__(self, address: Address, metrics: Dict[str,Any]):
        """Initialize a prometheus channel."""
        self.address = address
        self.metrics = metrics
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self._threaded_pool: ThreadPoolExecutor = ThreadPoolExecutor(
            self.THREAD_POOL_SIZE
        )
        self.logger: Union[logging.Logger, logging.LoggerAdapter] = _default_logger
        self._dialogues = PrometheusDialogues()
        self._port = 8080

    def _get_message_and_dialogue(
        self, envelope: Envelope
    ) -> Tuple[PrometheusMessage, Optional[PrometheusDialogue]]:
        """
        Get a message copy and dialogue related to this message.

        :param envelope: incoming envelope

        :return: Tuple[Message, Optional[Dialogue]]
        """
        message = cast(PrometheusMessage, envelope.message)
        dialogue = cast(PrometheusDialogue, self._dialogues.update(message))
        return message, dialogue

    @property
    def queue(self) -> asyncio.Queue:
        """Check queue is set and return queue."""
        if self._queue is None:  # pragma: nocover
            raise ValueError("Channel is not connected")
        return self._queue

    async def connect(self) -> None:
        """
        Connect an address to the prometheus.

        :return: an asynchronous queue, that constitutes the communication channel.
        """
        if self._queue:  # pragma: nocover
            return None
        self._loop = asyncio.get_event_loop()
        self._queue = asyncio.Queue()
        prometheus_client.start_http_server(self._port)

    async def send(self, envelope: Envelope) -> None:
        """
        Process the envelopes to prometheus.

        :return: None
        """
        sender = envelope.sender
        self.logger.debug("Processing message from {}: {}".format(sender, envelope))
        if envelope.protocol_id != PrometheusMessage.protocol_id:
            raise ValueError("This protocol is not valid for prometheus.")
        await self.handle_prometheus_message(envelope)

    async def _run_in_executor(self, fn, *args):
        return await self._loop.run_in_executor(self._threaded_pool, fn, *args)

    async def handle_prometheus_message(self, envelope: Envelope) -> None:
        """
        Forward a message to prometheus.

        :param envelope: the envelope
        :return: None
        """
        enforce(
            isinstance(envelope.message, PrometheusMessage), "Message not of type PrometheusMessage"
        )
        message, dialogue = self._get_message_and_dialogue(envelope)

        if dialogue is None:
            self.logger.warning(
                "Could not create dialogue from message={}".format(message)
            )
            return

        if message.performative == PrometheusMessage.Performative.ADD_METRIC:

            if message.title in self.metrics:
                response_code = 409
                response_msg = "Metric already exists."
            else:
                metric_type = getattr(prometheus_client, message.type, None)
                if metric_type is None:
                    response_code = 404
                    response_msg = f"{message.type} is not a recognized prometheus metric."
                else:
                    self.metrics[message.title] = metric_type(message.title, message.description)
                    response_code = 200
                    response_msg = f"New {message.type} successfully added: {message.title}."

        elif message.performative == PrometheusMessage.Performative.UPDATE_METRIC:

            metric = message.title
            if metric not in self.metrics:
                response_code = 404
                response_msg = f"Metric {metric} not found."
            else:
                update_func = getattr(self.metrics[metric], message.callable, None)
                if update_func is None:
                    response_code = 400
                    response_msg = f"Update function {message.callable} not found for metric {metric}."
                else:
                    # Update the metric
                    update_func(message.value)
                    response_code = 200
                    response_msg = f"Metric {metric} successfully updated."

        msg = dialogue.reply(
            performative=PrometheusMessage.Performative.RESPONSE,
            target_message=message,
            code=response_code,
            message=response_msg,
        )
        envelope = Envelope(
            to=msg.to, sender=msg.sender, protocol_id=msg.protocol_id, message=msg,
        )
        await self._send(envelope)

    async def _send(self, envelope: Envelope) -> None:
        """Send a message.

        :param envelope: the envelope
        :return: None
        """
        await self.queue.put(envelope)

    async def disconnect(self) -> None:
        """
        Disconnect.

        :return: None
        """
        if self._queue is not None:
            await self._queue.put(None)
            self._queue = None

    async def get(self) -> Optional[Envelope]:
        """Get incoming envelope."""
        return await self.queue.get()


class PrometheusConnection(Connection):
    """Proxy to the functionality of prometheus."""

    connection_id = PUBLIC_ID

    def __init__(self, **kwargs):
        """
        Initialize a connection to a local prometheus environment.

        :param kwargs: the keyword arguments of the parent class.
        """
        super().__init__(**kwargs)

        self.metrics = {}
        self.channel = PrometheusChannel(self.address, self.metrics)
        self._connection = None  # type: Optional[asyncio.Queue]

    async def connect(self) -> None:
        """
        Connect to prometheus server.

        :return: None
        """
        if self.is_connected:  # pragma: nocover
            return

        with self._connect_context():
            self.channel.logger = self.logger
            await self.channel.connect()

    async def disconnect(self) -> None:
        """
        Disconnect from prometheus server.

        :return: None
        """
        if self.is_disconnected:  # pragma: nocover
            return

        self._state.set(ConnectionStates.disconnecting)
        await self.channel.disconnect()
        self._state.set(ConnectionStates.disconnected)

    async def send(self, envelope: Envelope) -> None:
        """
        Send an envelope.

        :param envelope: the envelop
        :return: None
        """
        self._ensure_connected()
        await self.channel.send(envelope)

    async def receive(self, *args, **kwargs) -> Optional["Envelope"]:
        """Receive an envelope."""
        self._ensure_connected()
        try:
            envelope = await self.channel.get()
            return envelope
        except asyncio.CancelledError:  # pragma: no cover
            return None
