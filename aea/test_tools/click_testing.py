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

"""
This module contains an adaptation of click.testing.CliRunner.

In particular, it fixes an issue in
CliRunner.invoke, in the 'finally' clause. More precisely, before reading from
the testing outstream, it checks whether it has been already closed.

Links:

    https://github.com/pallets/click/issues/824
    https://github.com/valory-xyz/open-aea/issues/171
    https://github.com/valory-xyz/open-aea/issues/353

"""

from contextlib import nullcontext, redirect_stderr
import shlex
import sys
from typing import Optional

from _pytest.capture import CaptureFixture
from click.testing import CliRunner as ClickCliRunner
from click.testing import Result


class CliRunner(ClickCliRunner):
    """Patch of click.testing.CliRunner."""

    # NOTE: always set on the instance, never the class
    capfd: Optional[CaptureFixture] = None

    def invoke(  # type: ignore
        self,
        cli,
        args=None,
        input=None,  # pylint: disable=redefined-builtin
        env=None,
        catch_exceptions=True,
        color=False,
        **extra
    ) -> Result:
        """Call a cli command with click.testing.CliRunner.invoke."""
        exc_info = None
        exception: Optional[BaseException] = None
        exit_code = 0

        if self.capfd:
            assert not (input or env or color)
            cm = redirect_stderr(sys.stdout) if self.mix_stderr else nullcontext()
        else:
            cm = self.isolation(input=input, env=env, color=color)

        with cm as outstreams:
            if isinstance(args, str):
                args = shlex.split(args)

            try:
                prog_name = extra.pop("prog_name")
            except KeyError:
                prog_name = self.get_default_prog_name(cli)

            try:
                cli.main(args=args or (), prog_name=prog_name, **extra)
            except SystemExit as e:
                exc_info = sys.exc_info()
                exit_code = e.code
                if exit_code is None:  # pragma: nocover
                    exit_code = 0

                if exit_code != 0:  # pragma: nocover
                    exception = e

                if not isinstance(exit_code, int):
                    sys.stdout.write(str(exit_code))
                    sys.stdout.write("\n")
                    exit_code = 1

            except Exception as e:  # pylint: disable=broad-except
                if not catch_exceptions:
                    raise
                exception = e
                exit_code = 1
                exc_info = sys.exc_info()
            finally:
                if self.capfd:
                    out, err = self.capfd.readouterr()
                    stdout, stderr = out.encode(), err.encode()
                else:
                    sys.stdout.flush()
                    stdout = outstreams[0].getvalue() if not outstreams[0].closed else b""  # type: ignore
                    if self.mix_stderr:
                        # when it mixed, stderr always empty cause all output goes to stdout
                        stderr: Optional[bytes] = None
                    else:
                        stderr = (
                            outstreams[1].getvalue() if not outstreams[1].closed else b""  # type: ignore
                        )

        return Result(
            runner=self,
            stdout_bytes=stdout,
            stderr_bytes=stderr,  # type: ignore
            exit_code=exit_code,
            exception=exception,
            exc_info=exc_info,  # type: ignore
            return_value=None,
        )
