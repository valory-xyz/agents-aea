#!/usr/bin/env python3
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

"""Script to generate a markdown package table."""
import json
from pathlib import Path


COL_WIDTH = 61


def generate_table() -> None:
    """Generates a markdown table containing a package list"""

    # Load packages.json
    with open(
        Path("packages", "packages.json"), mode="r", encoding="utf-8"
    ) as packages_file:
        data = json.load(packages_file)

    # Table header
    content = (
        f"| {'Package name'.ljust(COL_WIDTH, ' ')} | {'Package hash'.ljust(COL_WIDTH, ' ')} |\n"
        f"| {'-'*COL_WIDTH} | {'-'*COL_WIDTH} |\n"
    )

    # Table rows
    for package, package_hash in data.items():
        package_cell = package.ljust(COL_WIDTH, " ")
        hash_cell = f"`{package_hash}`".ljust(COL_WIDTH, " ")
        content += f"| {package_cell} | {hash_cell} |\n"

    # Write table
    with open(
        Path("docs", "package_list.md"), mode="w", encoding="utf-8"
    ) as packages_list:
        packages_list.write(content)


if __name__ == "__main__":
    generate_table()
