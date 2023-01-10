import unittest
from unittest.mock import PropertyMock, patch

from charm import SlurmdCharm
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

class TestCharm(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness(SlurmdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.framework.EventBase.defer")
    def test_check_etcd_fail(self, defer):
        self.harness.charm.on.check_etcd.emit()
        defer.assert_called()

    @patch("charm.SlurmdCharm._on_slurmctld_started")
    @patch("json.loads", lambda _: ["test"])
    @patch("charm.SlurmdCharm.hostname", new_callable=PropertyMock(return_value="test"))
    @patch("omnietcd3.Etcd3AuthClient.get")
    @patch("charm.SlurmdCharm.etcd_ca_cert", new_callable=PropertyMock(return_value=""))
    @patch("charm.SlurmdCharm.etcd_use_tls", new_callable=PropertyMock(return_value=False))
    @patch("ops.framework.EventBase.defer")
    def test_check_etcd_success(self, defer, *_):
        self.harness.charm.on.check_etcd.emit()
        defer.assert_not_called()

    @patch("ops.framework.EventBase.defer")
    def test_config_changed_fail(self, defer):
        self.harness.set_leader(True)
        self.harness.charm.on.config_changed.emit()
        defer.assert_called()

    @patch("ops.framework.EventBase.defer")
    def test_config_changed_success(self, defer):
        self.harness.charm.on.config_changed.emit()
        defer.assert_not_called()
    
    @patch("ops.framework.EventBase.defer")
    def test_install_fail(self, defer):
        self.harness.charm.on.install.emit()
        self.assertFalse(self.harness.charm._stored.slurm_installed)
        defer.assert_called()

    @patch("slurm_ops_manager.SlurmManager.install")
    @patch("pathlib.Path.read_text")
    @patch("ops.model.Unit.set_workload_version")
    @patch("ops.model.Resources.fetch")
    @patch("ops.framework.EventBase.defer")
    def test_install_success(self, defer, *_):
        self.harness.charm.on.install.emit()
        self.assertTrue(self.harness.charm._stored.slurm_installed)
        defer.assert_not_called()
    
    def test_slurmctld_started(self):
        self.harness.charm.on.slurmctld_started.emit()
        self.assertTrue(self.harness.charm._stored.slurmctld_started)
    
    @patch("ops.framework.EventBase.defer")
    def test_slurmd_start_fail(self, defer):
        self.harness.charm.on.slurmd_start.emit()
        defer.assert_called()

    @patch("slurm_ops_manager.SlurmManager.needs_reboot", new_callable=PropertyMock(return_value=False))
    @patch("interface_slurmd.Slurmd.is_joined", new_callable=PropertyMock(return_value=True))
    @patch("slurm_ops_manager.SlurmManager.check_munged", lambda _: True)
    @patch("slurm_ops_manager.SlurmManager.slurm_is_active", lambda _: True)
    @patch("slurm_ops_manager.SlurmManager.slurm_systemctl", lambda *_: "stop", True)
    @patch("ops.framework.EventBase.defer")
    def test_slurmd_start_success(self, defer, *_):
        self.harness.charm._stored.slurm_installed = True
        self.harness.charm._stored.slurmctld_available = True
        self.harness.charm._stored.slurmctld_started = True

        self.harness.charm.on.slurmd_start.emit()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus("slurmd available"))
        defer.assert_not_called()

    def test_update_status_fail(self):
        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, BlockedStatus("Error installing slurmd"))

    @patch("slurm_ops_manager.SlurmManager.needs_reboot", new_callable=PropertyMock(return_value=False))
    @patch("interface_slurmd.Slurmd.is_joined", new_callable=PropertyMock(return_value=True))
    @patch("slurm_ops_manager.SlurmManager.check_munged", lambda _: True)
    def test_update_status_success(self, *_):
        self.harness.charm._stored.slurm_installed = True
        self.harness.charm._stored.slurmctld_available = True
        self.harness.charm._stored.slurmctld_started = True

        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus("slurmd available"))
