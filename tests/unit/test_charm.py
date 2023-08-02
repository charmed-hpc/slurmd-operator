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

"""Test default charm events such as upgrade charm, install, etc."""

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

    @patch("charm.SlurmdCharm._on_slurmctld_started")
    @patch("charm.SlurmdCharm.hostname", new_callable=PropertyMock(return_value="test"))
    @patch("ops.framework.EventBase.defer")
    def test_check_etcd_success(self, defer, *_) -> None:
        """Test check_etcd method success behavior."""
        self.harness.charm.on.check_etcd.emit()
        defer.assert_not_called()

    @patch("ops.framework.EventBase.defer")
    def test_config_changed_fail(self, defer) -> None:
        """Test config_changed failure behavior."""
        self.harness.set_leader(True)
        self.harness.charm.on.config_changed.emit()
        defer.assert_called()

    @patch("ops.framework.EventBase.defer")
    def test_config_changed_success(self, defer) -> None:
        """Test config_changed success behavior."""
        self.harness.charm.on.config_changed.emit()
        defer.assert_not_called()

    @patch("ops.framework.EventBase.defer")
    def test_install_fail(self, defer) -> None:
        """Test install failure behavior."""
        self.harness.charm.on.install.emit()
        self.assertFalse(self.harness.charm._stored.slurm_installed)
        defer.assert_called()

    @patch("slurm_ops_manager.SlurmManager.install")
    @patch("pathlib.Path.read_text", return_value="v1.0.0")
    @patch("ops.model.Unit.set_workload_version")
    @patch("ops.model.Resources.fetch")
    @patch("ops.framework.EventBase.defer")
    def test_install_success(self, defer, *_) -> None:
        """Test install success behavior."""
        self.harness.charm.on.install.emit()
        self.assertTrue(self.harness.charm._stored.slurm_installed)
        defer.assert_not_called()

    def test_slurmctld_started(self) -> None:
        """Test slurmctld_started works."""
        self.harness.charm.on.slurmctld_started.emit()
        self.assertTrue(self.harness.charm._stored.slurmctld_started)

    @patch("ops.framework.EventBase.defer")
    def test_slurmd_start_fail(self, defer) -> None:
        """Test slurmd_start failure behavior."""
        self.harness.charm.on.slurmd_start.emit()
        defer.assert_called()

    @patch("interface_slurmd.Slurmd.is_joined", new_callable=PropertyMock(return_value=True))
    @patch("slurm_ops_manager.SlurmManager.check_munged", return_value=True)
    @patch("slurm_ops_manager.SlurmManager.slurm_is_active", return_value=True)
    @patch("slurm_ops_manager.SlurmManager.slurm_systemctl", lambda *_: "stop", True)
    @patch("ops.framework.EventBase.defer")
    def test_slurmd_start_success(self, defer, *_) -> None:
        """Test slurmd_start success behavior."""
        self.harness.charm._stored.slurm_installed = True
        self.harness.charm._stored.slurmctld_available = True
        self.harness.charm._stored.slurmctld_started = True

        self.harness.charm.on.slurmd_start.emit()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus("slurmd available"))
        defer.assert_not_called()

    def test_update_status_install_fail(self) -> None:
        """Test update_status failure behavior from install."""
        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, BlockedStatus("Error installing slurmd"))

    @patch("interface_slurmd.Slurmd.is_joined", new_callable=PropertyMock(return_value=True))
    @patch("slurm_ops_manager.SlurmManager.check_munged", return_value=True)
    def test_update_status_success(self, *_) -> None:
        """Test update_status success behavior."""
        self.harness.charm._stored.slurm_installed = True
        self.harness.charm._stored.slurmctld_available = True
        self.harness.charm._stored.slurmctld_started = True

        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus("slurmd available"))
