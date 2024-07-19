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

"""Unit tests for the slurmd operator."""

import unittest
from unittest.mock import PropertyMock, patch

from charm import SlurmdCharm
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    """Unit test slurmd charm."""

    def setUp(self) -> None:
        """Set up unit test."""
        self.harness = Harness(SlurmdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_config_changed_fail(self) -> None:
        """Test config_changed failure behavior."""
        self.harness.set_leader(True)
        self.harness.update_config({"partition-config": "FAILEVAL"})
        self.assertEqual(self.harness.charm._stored.user_supplied_partition_parameters, {})

    @patch("ops.framework.EventBase.defer")
    def test_config_changed_success(self, defer) -> None:
        """Test config_changed success behavior."""
        self.harness.set_leader(True)
        self.harness.update_config(
            {"partition-config": 'DenyAccounts="myacct,youracct" DisableRootJobs="YES"'}
        )
        defer.assert_not_called()

    @patch("slurmd_ops.SlurmdManager.install", return_value=False)
    @patch("ops.framework.EventBase.defer")
    def test_install_fail(self, _, defer) -> None:
        """Test install failure behavior."""
        self.harness.charm.on.install.emit()
        self.assertFalse(self.harness.charm._stored.slurm_installed)
        defer.assert_called()

    @patch("slurmd_ops.SlurmdManager.install")
    @patch("slurmd_ops.SlurmdManager.version", return_value="23.11.7")
    @patch("pathlib.Path.read_text", return_value="v1.0.0")
    @patch("ops.model.Unit.set_workload_version")
    @patch("ops.model.Resources.fetch")
    @patch("utils.slurmd.override_default")
    @patch("utils.slurmd.override_service")
    @patch("charms.operator_libs_linux.v0.juju_systemd_notices.SystemdNotices.subscribe")
    @patch("ops.framework.EventBase.defer")
    def test_install_success(self, defer, *_) -> None:
        """Test install success behavior."""
        self.harness.charm.on.install.emit()
        self.assertTrue(self.harness.charm._stored.slurm_installed)
        defer.assert_not_called()

    def test_service_slurmd_start(self) -> None:
        """Test service_slurmd_started event handler."""
        self.harness.charm.on.service_slurmd_started.emit()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    def test_service_slurmd_stopped(self) -> None:
        """Test service_slurmd_stopped event handler."""
        self.harness.charm.on.service_slurmd_stopped.emit()
        self.assertEqual(self.harness.charm.unit.status, BlockedStatus("slurmd not running"))

    def test_update_status_install_fail(self) -> None:
        """Test update_status failure behavior from install."""
        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, BlockedStatus("Error installing slurmd"))

    @patch("interface_slurmctld.Slurmctld.is_joined", new_callable=PropertyMock(return_value=True))
    @patch("slurmd_ops.SlurmdManager.check_munged", return_value=True)
    def test_update_status_success(self, *_) -> None:
        """Test update_status success behavior."""
        self.harness.charm._stored.slurm_installed = True
        self.harness.charm._stored.slurmctld_available = True

        self.harness.charm.unit.status = ActiveStatus()
        self.harness.charm.on.update_status.emit()
        # ActiveStatus is the expected value when _check_status does not
        # modify the current state of the unit and should return True.
        self.assertTrue(self.harness.charm._check_status())
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
