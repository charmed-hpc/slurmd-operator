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

"""Test slurmd charm against other SLURM charms in the latest/edge channel."""

import asyncio
import logging
import pathlib
from typing import Any, Coroutine

import pytest
from helpers import get_slurmctld_res, get_slurmd_res, modify_default_profile
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

SLURMD = "slurmd"
SLURMDBD = "slurmdbd"
SLURMCTLD = "slurmctld"
DATABASE = "mysql"
ROUTER = "mysql-router"


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
@pytest.mark.order(1)
async def test_build_and_deploy(
    ops_test: OpsTest, slurmd_charm: Coroutine[Any, Any, pathlib.Path], charm_base: str
) -> None:
    """Test that the slurmd charm can stabilize against slurmctld, slurmdbd and MySQL."""
    logger.info(f"Deploying {SLURMD} against {SLURMCTLD}, {SLURMDBD}, and {DATABASE}")
    modify_default_profile()
    res_slurmd = get_slurmd_res()
    res_slurmctld = get_slurmctld_res()
    await asyncio.gather(
        ops_test.model.deploy(
            SLURMCTLD,
            application_name=SLURMCTLD,
            channel="edge",
            num_units=1,
            resources=res_slurmctld,
            base=charm_base,
        ),
        ops_test.model.deploy(
            SLURMDBD,
            application_name=SLURMDBD,
            channel="edge",
            num_units=1,
            base=charm_base,
        ),
        ops_test.model.deploy(
            ROUTER,
            application_name=f"{SLURMDBD}-{ROUTER}",
            channel="dpe/edge",
            num_units=0,
            base=charm_base,
        ),
        ops_test.model.deploy(
            DATABASE,
            application_name=DATABASE,
            channel="8.0/edge",
            num_units=1,
            base="ubuntu@22.04",
        ),
    )
    # Attach resources to charms.
    await ops_test.juju("attach-resource", SLURMCTLD, f"etcd={res_slurmctld['etcd']}")
    # Set relations for charmed applications.
    await ops_test.model.integrate(f"{SLURMDBD}:{SLURMDBD}", f"{SLURMCTLD}:{SLURMDBD}")
    await ops_test.model.integrate(f"{SLURMDBD}-{ROUTER}:backend-database", f"{DATABASE}:database")
    await ops_test.model.integrate(f"{SLURMDBD}:database", f"{SLURMDBD}-{ROUTER}:database")
    # IMPORTANT: It's possible for slurmd to be stuck waiting for slurmctld despite slurmctld and slurmdbd
    # available. Relation between slurmd and slurmctld has to be added after slurmctld is ready
    # otherwise risk running into race-condition type behavior.
    await ops_test.model.wait_for_idle(apps=[SLURMCTLD], status="blocked", timeout=1000)
    # Build and Deploy Slurmd
    await ops_test.model.deploy(
        str(await slurmd_charm),
        application_name=SLURMD,
        num_units=1,
        resources=res_slurmd,
        base=charm_base,
    )
    # Attach resources to slurmd application.
    await ops_test.juju("attach-resource", SLURMD, f"nhc={res_slurmd['nhc']}")
    # Set relations for slurmd application.
    await ops_test.model.integrate(f"{SLURMD}:{SLURMD}", f"{SLURMCTLD}:{SLURMD}")
    # Reduce the update status frequency to accelerate the triggering of deferred events.
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[SLURMD], status="active", timeout=1000)
        assert ops_test.model.applications[SLURMD].units[0].workload_status == "active"


@pytest.mark.abort_on_fail
@pytest.mark.order(2)
async def test_munge_is_active(ops_test: OpsTest):
    """Test that munge is active."""
    logger.info("Checking that munge is active inside Juju unit")
    unit = ops_test.model.applications[SLURMD].units[0]
    cmd_res = (await unit.ssh(command="systemctl is-active munge")).strip("\n")
    assert cmd_res == "active"


# IMPORTANT: Currently there is a bug where slurmd can reach active status despite the
# systemd service failing.
@pytest.mark.xfail
@pytest.mark.abort_on_fail
@pytest.mark.order(3)
async def test_slurmd_is_active(ops_test: OpsTest):
    """Test that slurmd is active."""
    logger.info("Checking that slurmd is active inside Juju unit")
    unit = ops_test.model.applications[SLURMD].units[0]
    cmd_res = (await unit.ssh(command="systemctl is-active slurmd")).strip("\n")
    assert cmd_res == "active"
