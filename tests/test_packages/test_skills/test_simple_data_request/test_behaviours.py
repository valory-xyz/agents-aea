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
"""This module contains the tests of the behaviour classes of the simple_data_request skill."""

import json
from pathlib import Path
from typing import cast

import pytest

from aea.test_tools.test_skill import BaseSkillTestCase

from packages.fetchai.protocols.http.message import HttpMessage
from packages.fetchai.skills.simple_data_request.behaviours import (
    HTTP_CLIENT_PUBLIC_ID,
    HttpRequestBehaviour,
)

from tests.conftest import ROOT_DIR


class TestHttpRequestBehaviour(BaseSkillTestCase):
    """Test http_request behaviour of http_request."""

    path_to_skill = Path(
        ROOT_DIR, "packages", "fetchai", "skills", "simple_data_request"
    )

    @classmethod
    def setup(cls):
        """Setup the test class."""
        cls.mocked_method = "some_method"
        cls.mocked_url = "some_url"
        cls.mocked_shared_state_key = "some_name_for_data"

        config_overrides = {
            "behaviours": {
                "http_request": {
                    "args": {"method": cls.mocked_method, "url": cls.mocked_url}
                }
            },
            "handlers": {
                "http": {"args": {"shared_state_key": cls.mocked_shared_state_key}}
            },
        }

        super().setup(config_overrides=config_overrides)
        cls.http_request_behaviour = cast(
            HttpRequestBehaviour, cls._skill.skill_context.behaviours.http_request
        )

    def test__init__i(self):
        """Test the __init__ method of the http_request behaviour."""
        assert self.http_request_behaviour.url == "some_url"
        assert self.http_request_behaviour.method == "some_method"
        assert self.http_request_behaviour.body == ""

    def test__init__ii(self):
        """Test the __init__ method of the http_request behaviour where ValueError is raise."""
        with pytest.raises(ValueError, match="Url, method and body must be provided."):
            self.http_request_behaviour.__init__(
                url=None, method="some_method", body="some_body"
            )

    def test_setup(self):
        """Test the setup method of the http_request behaviour."""
        assert self.http_request_behaviour.setup() is None
        self.assert_quantity_in_outbox(0)

    def test_act(self):
        """Test the act method of the http_request behaviour."""
        # operation
        self.http_request_behaviour.act()

        # after
        self.assert_quantity_in_outbox(1)
        has_attributes, error_str = self.message_has_attributes(
            actual_message=self.get_message_from_outbox(),
            message_type=HttpMessage,
            performative=HttpMessage.Performative.REQUEST,
            to=str(HTTP_CLIENT_PUBLIC_ID),
            sender=self.skill.skill_context.agent_address,
            method=self.mocked_method,
            url=self.mocked_url,
            headers="",
            version="",
            body=json.dumps(self.http_request_behaviour.body).encode("utf-8"),
        )
        assert has_attributes, error_str

    def test_teardown(self):
        """Test the teardown method of the http_request behaviour."""
        assert self.http_request_behaviour.teardown() is None
        self.assert_quantity_in_outbox(0)
