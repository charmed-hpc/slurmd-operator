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
        self.maxDiff = None

    def test_update_status_fail(self):
        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, BlockedStatus("Error installing slurmd"))

    @patch("interface_slurmd.Slurmd.is_joined", new_callable=PropertyMock(return_value=True))
    @patch("slurm_ops_manager.SlurmManager.check_munged", lambda _: True)
    def test_update_status_success(self, _):
        self.harness.charm._stored.slurm_installed = True
        self.harness.charm._stored.slurmctld_available = True
        self.harness.charm._stored.slurmctld_started = True

        self.harness.charm.on.update_status.emit()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus("slurmd available"))