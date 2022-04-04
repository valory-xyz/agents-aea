# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2022 Valory AG
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

"""Implementation of the 'aea init' subcommand."""

import click

from aea import __version__
from aea.cli.login import do_login
from aea.cli.register import do_register
from aea.cli.registry.settings import (
    DEFAULT_REGISTRY_CONFIG,
    REGISTRY_CONFIG_KEY,
    REGISTRY_HTTP,
    REGISTRY_IPFS,
    REGISTRY_LOCAL,
)
from aea.cli.registry.utils import check_is_author_logged_in, is_auth_token_present
from aea.cli.utils.click_utils import registry_flag_
from aea.cli.utils.config import get_or_create_cli_config, update_cli_config
from aea.cli.utils.constants import AEA_LOGO, AUTHOR_KEY
from aea.cli.utils.context import Context
from aea.cli.utils.decorators import pass_ctx
from aea.cli.utils.package_utils import validate_author_name, validate_registry_type


@click.command()
@click.option("--author", type=str, required=False)
@click.option("--reset", is_flag=True, help="To reset the initialization.")
@click.option("--no-subscribe", is_flag=True, help="For developers subscription.")
@registry_flag_()
@pass_ctx
def init(  # pylint: disable=unused-argument
    ctx: Context, author: str, reset: bool, no_subscribe: bool, registry: str,
) -> None:
    """Initialize your AEA configurations."""
    do_init(author, reset, no_subscribe, registry)


def do_init(author: str, reset: bool, no_subscribe: bool, registry_type: str) -> None:
    """
    Initialize your AEA configurations.

    :param author: str author username.
    :param reset: True, if resetting the author name
    :param no_subscribe: bool flag for developers subscription skip on register.
    :param registry_type: default registry type.
    """
    config = get_or_create_cli_config()
    if reset or config.get(AUTHOR_KEY, None) is None:
        author = validate_author_name(author)
        registry_type = validate_registry_type(registry_type)

        update_cli_config({AUTHOR_KEY: author})
        if registry_type == REGISTRY_HTTP:
            _registry_init_http(username=author, no_subscribe=no_subscribe)
        elif registry_type == REGISTRY_IPFS:
            _registry_init_ipfs()
        else:
            _registry_init_local()

        config = get_or_create_cli_config()
        config.pop(REGISTRY_CONFIG_KEY, None)  # for security reasons
        success_msg = "AEA configurations successfully initialized: {}".format(config)
    else:
        config.pop(REGISTRY_CONFIG_KEY, None)  # for security reasons
        success_msg = "AEA configurations already initialized: {}. To reset use '--reset'.".format(
            config
        )
    click.echo(AEA_LOGO + "v" + __version__ + "\n")
    click.echo(success_msg)


def _registry_init_ipfs() -> None:
    """Initialize ipfs registry"""
    registry_config = DEFAULT_REGISTRY_CONFIG.copy()
    registry_config["default"] = REGISTRY_IPFS
    update_cli_config({REGISTRY_CONFIG_KEY: registry_config})


def _registry_init_local() -> None:
    """Initialize ipfs local"""
    registry_config = DEFAULT_REGISTRY_CONFIG.copy()
    registry_config["default"] = REGISTRY_LOCAL
    update_cli_config({REGISTRY_CONFIG_KEY: registry_config})


def _registry_init_http(username: str, no_subscribe: bool) -> None:
    """
    Create an author name on the registry.

    :param username: the user name
    :param no_subscribe: bool flag for developers subscription skip on register.
    """
    if username is not None and is_auth_token_present():
        check_is_author_logged_in(username)
    else:
        is_registered = click.confirm("Do you have a Registry account?")
        if is_registered:
            password = click.prompt("Password", type=str, hide_input=True)
            do_login(username, password)
        else:
            click.echo("Create a new account on the Registry now:")
            email = click.prompt("Email", type=str)
            password = click.prompt("Password", type=str, hide_input=True)

            password_confirmation = ""  # nosec
            while password_confirmation != password:
                click.echo("Please make sure that passwords are equal.")
                password_confirmation = click.prompt(
                    "Confirm password", type=str, hide_input=True
                )

            do_register(username, email, password, password_confirmation, no_subscribe)
