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

"""This module contains the agent context class."""

from queue import Queue

from aea.decision_maker.base import OwnershipState, Preferences
from aea.mail.base import OutBox


class AgentContext:
    """Provide read access to relevant data of the agent for the skills."""

    def __init__(self, agent_name: str,
                 public_key: str,
                 outbox: OutBox,
                 decision_maker_message_queue: Queue,
                 ownership_state: OwnershipState,
                 preferences: Preferences):
        """
        Initialize an agent context.

        :param agent_name: the agent's name
        :param public_key: the public key of the agent
        :param outbox: the outbox
        :param decision_maker_queue: the (in) queue of the decision maker
        :param ownership_state: the ownership state of the agent
        :param preferences: the preferences of the agent
        """
        self._agent_name = agent_name
        self._public_key = public_key
        self._outbox = outbox
        self._decision_maker_message_queue = decision_maker_message_queue
        self._ownership_state = ownership_state
        self._preferences = preferences

    @property
    def agent_name(self) -> str:
        """Get agent name."""
        return self._agent_name

    @property
    def public_key(self) -> str:
        """Get public key."""
        return self._public_key

    @property
    def outbox(self) -> OutBox:
        """Get outbox."""
        return self._outbox

    @property
    def decision_maker_message_queue(self) -> Queue:
        """Get decision maker queue."""
        return self._decision_maker_message_queue

    @property
    def ownership_state(self) -> OwnershipState:
        """Get the ownership state of the agent."""
        return self._ownership_state

    @property
    def preferences(self) -> Preferences:
        """Get the preferences of the agent."""
        return self._preferences
