# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2022 Valory AG
#   Copyright 2018-2021 Fetch.AI Limited
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

"""Implementation of the 'aea delete' subcommand."""

import os
import shutil
from typing import cast

import click

from aea.cli.utils.click_utils import AgentDirectory
from aea.cli.utils.context import Context


@click.command()
@click.argument(
    "agent_name",
    type=AgentDirectory(),
    required=True,
)
@click.pass_context
def delete(click_context: click.Context, agent_name: str) -> None:
    """Delete an agent."""
    click.echo(f"Deleting AEA project directory './{agent_name}'...")
    ctx = cast(Context, click_context.obj)
    delete_aea(ctx, agent_name)


def delete_aea(ctx: Context, agent_name: str) -> None:
    """
    Delete agent's directory.

    :param ctx: click context
    :param agent_name: name of the agent (equal to folder name).

    :raises ClickException: if OSError occurred.
    """
    agent_path = os.path.join(ctx.cwd, agent_name)
    try:
        shutil.rmtree(agent_path, ignore_errors=False)
    except OSError:
        raise click.ClickException(
            "An error occurred while deleting the agent directory. Aborting..."
        )
