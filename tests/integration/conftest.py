#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configure slurmd operator integration tests."""

import logging
import os
from pathlib import Path
from typing import Union

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)
SLURMCTLD_DIR = Path(os.getenv("SLURMCTLD_DIR", "../slurmctld-operator"))
SLURMDBD_DIR = Path(os.getenv("SLURMDBD_DIR", "../slurmdbd-operator"))


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--charm-base",
        action="store",
        default="ubuntu@22.04",
        help="Charm base version to use for integration tests.",
    )
    parser.addoption(
        "--use-local",
        action="store_true",
        default=False,
        help="Use SLURM operators located on localhost rather than pull from Charmhub",
    )


@pytest.fixture(scope="module")
def charm_base(request) -> str:
    """Get slurmd charm base to use."""
    return request.config.option.charm_base


@pytest.fixture(scope="module")
async def slurmd_charm(ops_test: OpsTest) -> Path:
    """Pack slurmd charm to use for integration tests."""
    return await ops_test.build_charm(".")


@pytest.fixture(scope="module")
async def slurmctld_charm(request, ops_test: OpsTest) -> Union[str, Path]:
    """Pack slurmctld charm to use for integration tests when --use-local is specified.

    Returns:
        `str` "slurmctld" if --use-local not specified or if SLURMD_DIR does not exist.
    """
    if request.config.option.use_local:
        logger.info("Using local slurmctld operator rather than pulling from Charmhub")
        if SLURMCTLD_DIR.exists():
            return await ops_test.build_charm(SLURMCTLD_DIR)
        else:
            logger.warning(
                f"{SLURMCTLD_DIR} not found. "
                f"Defaulting to latest/edge slurmctld operator from Charmhub"
            )

    return "slurmctld"
