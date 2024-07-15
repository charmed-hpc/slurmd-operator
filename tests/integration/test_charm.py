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

"""Test slurmd charm against other SLURM operators."""

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

SLURMD = "slurmd"
SLURMDBD = "slurmdbd"
SLURMCTLD = "slurmctld"
DATABASE = "mysql"
ROUTER = "mysql-router"
UNIT_NAME = f"{SLURMD}/0"


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
@pytest.mark.order(1)
async def test_build_and_deploy(
    ops_test: OpsTest, charm_base: str, slurmd_charm, slurmctld_charm
) -> None:
    """Test that the slurmd charm can stabilize against slurmctld, slurmdbd and MySQL."""
    logger.info(f"Deploying {SLURMD} against {SLURMCTLD}")
    # Pack charms and download NHC resource for slurmd operator.
    slurmd, slurmctld = await asyncio.gather(slurmd_charm, slurmctld_charm)
    # Deploy the test Charmed SLURM cloud.
    await asyncio.gather(
        ops_test.model.deploy(
            str(slurmd),
            application_name=SLURMD,
            num_units=1,
            base=charm_base,
        ),
        ops_test.model.deploy(
            str(slurmctld),
            application_name=SLURMCTLD,
            channel="edge" if isinstance(slurmctld, str) else None,
            num_units=1,
            base=charm_base,
        ),
    )
    # Set relations for charmed applications.
    await ops_test.model.integrate(f"{SLURMD}:{SLURMCTLD}", f"{SLURMCTLD}:{SLURMD}")
    # Reduce the update status frequency to accelerate the triggering of deferred events.
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[SLURMD], status="active", timeout=1000)
        assert ops_test.model.units.get(UNIT_NAME).workload_status == "active"


@pytest.mark.abort_on_fail
@pytest.mark.order(2)
async def test_munge_is_active(ops_test: OpsTest):
    """Test that munge is active."""
    logger.info("Checking that munge is active inside Juju unit")
    slurmd_unit = ops_test.model.units.get(UNIT_NAME)
    cmd_res = (await slurmd_unit.ssh(command="systemctl is-active munge")).strip("\n")
    assert cmd_res == "active"


@pytest.mark.abort_on_fail
@pytest.mark.order(3)
async def test_slurmd_is_active(ops_test: OpsTest):
    """Test that slurmd is active."""
    logger.info("Checking that slurmd is active inside Juju unit")
    slurmd_unit = ops_test.model.units.get(UNIT_NAME)
    cmd_res = (await slurmd_unit.ssh(command="systemctl is-active slurmd")).strip("\n")
    assert cmd_res == "active"
