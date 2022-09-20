# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2022 Valory AG
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

"""This test module contains integration tests for P2PLibp2p connection."""

# pylint: skip-file

import itertools
import json
import os

import pytest

from aea.test_tools.test_cases import AEATestCaseMany

from packages.valory.connections import p2p_libp2p, p2p_libp2p_client
from packages.valory.connections.p2p_libp2p.connection import (
    PUBLIC_ID as P2P_CONNECTION_PUBLIC_ID,
)
from packages.valory.connections.p2p_libp2p.tests.base import libp2p_log_on_failure_all
from packages.valory.connections.p2p_libp2p_client.connection import (
    PUBLIC_ID as P2P_CLIENT_CONNECTION_PUBLIC_ID,
)
from packages.valory.connections.test_libp2p.tests.base import (
    BaseP2PLibp2pTest,
    LIBP2P_LEDGER,
    make_cert_request,
    ports,
)

from tests.conftest import DEFAULT_LEDGER, UseACNWithBootstrappedEntryNodes


LOCAL_DHT_MADDRS = [
    "/dns4/0.0.0.0/tcp/9000/p2p/16Uiu2HAm2yxmLQTZTrxjo5c4k5ka8AVMcpeD5zMMeasE6xDw1YQw",
    "/dns4/0.0.0.0/tcp/9001/p2p/16Uiu2HAkw99FW2GKb2qs24eLgfXSSUjke1teDaV9km63Fv3UGdnF",
    "/dns4/0.0.0.0/tcp/9002/p2p/16Uiu2HAm4aHr1iKR323tca8Zu8hKStEEVwGkE2gtCJw49S3gbuVj",
][1:]
LOCAL_DHT_DELEGATE_URIS = ["localhost:11000", "localhost:11001", "localhost:11002"][1:]
LOCAL_DHT_PUBLIC_KEYS = [
    "0270475f9b78c0285a6ac6067582f5e159ec147ccb03aee16a32731f68920b1ae8",
    "02197b55d736bd242311aaabb485f9db40881349873bb13e8b60c8a130ecb341d8",
    "0287ee61e8f939aeaa69bd7156463d698f8e74a3e1d5dd20cce997970f13ad4f12",
][1:]

AEA_DEFAULT_LAUNCH_TIMEOUT = 30
AEA_LIBP2P_LAUNCH_TIMEOUT = 30

p2p_libp2p_path = f"vendor.{p2p_libp2p.__name__.split('.', 1)[-1]}"
p2p_libp2p_client_path = f"vendor.{p2p_libp2p_client.__name__.split('.', 1)[-1]}"


@pytest.fixture
def maddrs(request):
    """Fixture for multi addresses."""
    return request.param


@pytest.fixture
def delegate_uris_public_keys(request):
    """Fixture for delegate uris and public keys."""
    return request.param


@pytest.mark.integration
@libp2p_log_on_failure_all
class TestLibp2pConnectionLocalDHTRelay(
    BaseP2PLibp2pTest,
    UseACNWithBootstrappedEntryNodes,
):
    """Test that public DHT's relay service is working properly"""

    maddrs = LOCAL_DHT_MADDRS

    def setup(self):
        """Setup test"""

        for maddr in self.maddrs:
            for _ in range(2):  # make pairs
                self.make_connection(relay=False, entry_peers=[maddr])

    def teardown(self):
        """Teardown after test method"""
        self._disconnect()
        self.multiplexers.clear()
        self.log_files.clear()

    @property
    def pairs_with_same_entry_peers(self):
        """Multiplexer pairs with the same entry peers"""
        return itertools.zip_longest(*[iter(self.multiplexers)] * 2)

    @property
    def pairs_with_different_entry_peers(self):
        """Multiplexer pairs with different entry peers"""
        return itertools.permutations(self.multiplexers[::2], 2)

    def test_connectivity(self):
        """Test connectivity."""
        assert self.all_connected

    def test_communication_direct(self):
        """Test direct communication through the same entry peer"""

        for mux_pair in self.pairs_with_same_entry_peers:
            sender, to = (c.address for m in mux_pair for c in m.connections)
            envelope = self.enveloped_default_message(to=to, sender=sender)
            mux_pair[0].put(envelope)
            delivered_envelope = mux_pair[1].get(block=True, timeout=30)
            assert self.sent_is_delivered_envelope(envelope, delivered_envelope)

    def test_communication_indirect(self):
        """Test indirect communication through another entry peer"""

        for mux_pair in self.pairs_with_different_entry_peers:
            sender, to = (c.address for m in mux_pair for c in m.connections)
            envelope = self.enveloped_default_message(to=to, sender=sender)
            mux_pair[0].put(envelope)
            delivered_envelope = mux_pair[1].get(block=True, timeout=30)
            assert self.sent_is_delivered_envelope(envelope, delivered_envelope)


@pytest.mark.integration
@libp2p_log_on_failure_all
class TestLibp2pConnectionLocalDHTDelegate(TestLibp2pConnectionLocalDHTRelay):
    """Test that public DHTs delegate service is working properly"""

    uris = LOCAL_DHT_DELEGATE_URIS
    public_keys = LOCAL_DHT_PUBLIC_KEYS

    def setup(self):  # overwrite the setup, reuse the rest
        """Set up test"""
        assert len(self.uris) == len(self.public_keys)
        for uri, public_keys in zip(self.uris, self.public_keys):
            for _ in range(2):
                self.make_client_connection(uri=uri, peer_public_key=public_keys)


@pytest.mark.integration
@libp2p_log_on_failure_all
class TestLibp2pConnectionLocalDHTRelayAEACli(
    AEATestCaseMany, UseACNWithBootstrappedEntryNodes
):
    """Test that public DHT's relay service is working properly, using aea cli"""

    @pytest.mark.parametrize("maddrs", [LOCAL_DHT_MADDRS], indirect=True)
    def test_connectivity(self, maddrs):
        """Test connectivity."""
        self.log_files = []
        self.agent_name = "some"
        self.create_agents(self.agent_name)
        self.set_agent_context(self.agent_name)
        self.conn_key_file = os.path.join(
            os.path.abspath(os.getcwd()), "./conn_key.txt"
        )
        agent_ledger_id, node_ledger_id = DEFAULT_LEDGER, LIBP2P_LEDGER
        # set config
        self.set_config("agent.default_ledger", agent_ledger_id)
        self.set_config(
            "agent.required_ledgers",
            json.dumps([agent_ledger_id, node_ledger_id]),
            "list",
        )
        self.set_config("agent.default_connection", str(P2P_CONNECTION_PUBLIC_ID))
        # agent keys
        self.generate_private_key(agent_ledger_id)
        self.add_private_key(agent_ledger_id, f"{agent_ledger_id}_private_key.txt")
        # libp2p node keys
        self.generate_private_key(node_ledger_id, private_key_file=self.conn_key_file)
        self.add_private_key(
            node_ledger_id, private_key_filepath=self.conn_key_file, connection=True
        )
        # add connection and build
        self.add_item("connection", str(P2P_CONNECTION_PUBLIC_ID))
        self.run_cli_command("build", cwd=self._get_cwd())
        # for logging
        log_file = f"libp2p_node_{self.agent_name}.log"
        log_file = os.path.join(os.path.abspath(os.getcwd()), log_file)

        config_path = f"{p2p_libp2p_path}.config"
        self.nested_set_config(
            config_path,
            {
                "local_uri": f"127.0.0.1:{next(ports)}",
                "entry_peers": maddrs,
                "log_file": log_file,
                "ledger_id": node_ledger_id,
            },
        )

        self.run_cli_command("issue-certificates", cwd=self._get_cwd())

        self.log_files = [log_file]
        process = self.run_agent()

        is_running = self.is_running(process, timeout=AEA_LIBP2P_LAUNCH_TIMEOUT)
        assert is_running, "AEA not running within timeout!"

        check_strings = "Peer running in "
        missing_strings = self.missing_from_output(process, check_strings)
        assert not missing_strings

        self.terminate_agents(process)
        assert self.is_successfully_terminated(process)

    def teardown(self):
        """Clean up after test case run."""
        self.unset_agent_context()
        self.run_cli_command("delete", self.agent_name)


@pytest.mark.integration
@libp2p_log_on_failure_all
class TestLibp2pConnectionLocalDHTDelegateAEACli(
    AEATestCaseMany, UseACNWithBootstrappedEntryNodes
):
    """Test that public DHT's delegate service is working properly, using aea cli"""

    @pytest.mark.parametrize(
        "delegate_uris_public_keys",
        [(LOCAL_DHT_DELEGATE_URIS, LOCAL_DHT_PUBLIC_KEYS)],
        indirect=True,
    )
    def test_connectivity(self, delegate_uris_public_keys):
        """Test connectivity."""

        delegate_uris, public_keys = delegate_uris_public_keys
        self.agent_name = "some"
        self.create_agents(self.agent_name)
        self.set_agent_context(self.agent_name)

        agent_ledger_id, node_ledger_id = DEFAULT_LEDGER, LIBP2P_LEDGER
        self.set_config("agent.default_ledger", agent_ledger_id)
        self.set_config(
            "agent.required_ledgers",
            json.dumps([agent_ledger_id, node_ledger_id]),
            "list",
        )
        # agent keys
        self.generate_private_key(agent_ledger_id)
        self.add_private_key(agent_ledger_id, f"{agent_ledger_id}_private_key.txt")

        self.add_item("connection", str(P2P_CLIENT_CONNECTION_PUBLIC_ID))
        config_path = f"{p2p_libp2p_client_path}.config"
        self.nested_set_config(
            config_path,
            {"nodes": [{"uri": uri} for uri in delegate_uris]},
        )
        zipper = zip(*delegate_uris_public_keys)
        nodes = [{"uri": uri, "public_key": public_key} for uri, public_key in zipper]
        self.nested_set_config(p2p_libp2p_client_path + ".config", {"nodes": nodes})

        # generate certificates for connection
        self.nested_set_config(
            p2p_libp2p_client_path + ".cert_requests",
            [
                make_cert_request(k, agent_ledger_id, f"./cli_test_{k}")
                for k in public_keys
            ],
        )
        self.run_cli_command("issue-certificates", cwd=self._get_cwd())

        process = self.run_agent()
        is_running = self.is_running(process, timeout=AEA_DEFAULT_LAUNCH_TIMEOUT)
        assert is_running, "AEA not running within timeout!"
        self.terminate_agents(process)
        assert self.is_successfully_terminated(process)

    def teardown(self):
        """Clean up after test case run."""
        self.unset_agent_context()
        self.run_cli_command("delete", self.agent_name)