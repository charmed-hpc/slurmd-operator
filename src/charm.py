#!/usr/bin/env python3
# Copyright 2020 Omnivector Solutions, LLC.
# See LICENSE file for licensing details.

"""SlurmdCharm."""

import logging
from pathlib import Path

import distro
from charms.fluentbit.v0.fluentbit import FluentbitClient
from charms.operator_libs_linux.v0.juju_systemd_notices import (
    ServiceStartedEvent,
    ServiceStoppedEvent,
    SystemdNotices,
)
from interface_slurmd import Slurmd
from ops.charm import ActionEvent, CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from slurm_ops_manager import SlurmManager
from utils import monkeypatch, slurmd

logger = logging.getLogger(__name__)
if distro.id() == "centos":
    logger.debug("Monkeypatching slurmd operator to support CentOS base")
    SystemdNotices = monkeypatch.juju_systemd_notices(SystemdNotices)
    slurmd = monkeypatch.slurmd_override_default(slurmd)
    slurmd = monkeypatch.slurmd_override_service(slurmd)


class SlurmdCharm(CharmBase):
    """Slurmd lifecycle events."""

    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        """Init _stored attributes and interfaces, observe events."""
        super().__init__(*args, **kwargs)

        self._stored.set_default(
            nhc_conf=str(),
            slurm_installed=False,
            slurmctld_available=False,
            slurmctld_started=False,
            cluster_name=str(),
        )

        self._slurm_manager = SlurmManager(self, "slurmd")
        self._fluentbit = FluentbitClient(self, "fluentbit")
        # interface to slurmctld, should only have one slurmctld per slurmd app
        self._slurmd = Slurmd(self, "slurmd")
        self._systemd_notices = SystemdNotices(self, ["slurmd"])

        event_handler_bindings = {
            self.on.install: self._on_install,
            self.on.upgrade_charm: self._on_upgrade,
            self.on.update_status: self._on_update_status,
            self.on.config_changed: self._on_config_changed,
            self.on.service_slurmd_started: self._on_slurmd_started,
            self.on.service_slurmd_stopped: self._on_slurmd_stopped,
            self._slurmd.on.slurmctld_available: self._on_slurmctld_available,
            self._slurmd.on.slurmctld_unavailable: self._on_slurmctld_unavailable,
            # fluentbit
            self.on["fluentbit"].relation_created: self._on_configure_fluentbit,
            # actions
            self.on.version_action: self._on_version_action,
            self.on.node_configured_action: self._on_node_configured_action,
            self.on.get_node_inventory_action: self._on_get_node_inventory_action,
            self.on.set_node_inventory_action: self._on_set_node_inventory_action,
            self.on.show_nhc_config_action: self._on_show_nhc_config,
        }
        for event, handler in event_handler_bindings.items():
            self.framework.observe(event, handler)

    def _on_install(self, event):
        """Perform installation operations for slurmd."""
        try:
            nhc_path = self.model.resources.fetch("nhc")
            logger.debug(f"## Found nhc resource: {nhc_path}")
        except Exception as e:
            logger.error(f"## Missing nhc resource: {e}")
            self.unit.status = BlockedStatus("Missing nhc resource")
            event.defer()
            return

        self.unit.set_workload_version(Path("version").read_text().strip())
        self.unit.status = WaitingStatus("Installing slurmd")
        successful_installation = self._slurm_manager.install(
            self.config.get("custom-slurm-repo"), nhc_path
        )
        slurmd.override_service()
        logger.debug(f"### slurmd installed: {successful_installation}")

        if successful_installation:
            self._stored.slurm_installed = True
            self._systemd_notices.subscribe()
        else:
            self.unit.status = BlockedStatus("Error installing slurmd")
            event.defer()

        self._check_status()

    def _on_configure_fluentbit(self, event):
        """Set up Fluentbit log forwarding."""
        self._configure_fluentbit()

    def _configure_fluentbit(self):
        logger.debug("## Configuring fluentbit")
        cfg = []
        cfg.extend(self._slurm_manager.fluentbit_config_nhc)
        cfg.extend(self._slurm_manager.fluentbit_config_slurm)
        self._fluentbit.configure(cfg)

    def _on_upgrade(self, event):
        """Perform upgrade operations."""
        self.unit.set_workload_version(Path("version").read_text().strip())

    def _on_update_status(self, event):
        """Handle update status."""
        self._check_status()

    def _check_status(self) -> bool:
        """Check if we have all needed components.

        - partition name
        - slurm installed
        - slurmctld available and working
        - munge key configured and working
        """
        if not self._stored.slurm_installed:
            self.unit.status = BlockedStatus("Error installing slurmd")
            return False

        if not self._slurmd.is_joined:
            self.unit.status = BlockedStatus("Need relations: slurmctld")
            return False

        if not self._stored.slurmctld_available:
            self.unit.status = WaitingStatus("Waiting on: slurmctld")
            return False

        if not self._slurm_manager.check_munged():
            self.unit.status = BlockedStatus("Error configuring munge key")
            return False

        return True

    def _set_slurmctld_available(self, flag: bool):
        """Change stored value for slurmctld availability."""
        self._stored.slurmctld_available = flag

    def _on_slurmctld_available(self, event):
        """Get data from slurmctld and send inventory."""
        if not self._stored.slurm_installed:
            event.defer()
            return

        logger.debug("#### Slurmctld available - setting overrides for configless")
        self._set_slurmctld_available(True)
        # Get slurmctld host:port from relation and override systemd services.
        slurmd.override_default(self._slurmd.slurmctld_hostname, self._slurmd.slurmctld_port)
        self._on_set_partition_info_on_app_relation_data(event)
        self._write_munge_key_and_restart_munge()
        # Only set up fluentbit if we have a relation to it.
        if self._fluentbit._relation is not None:
            self._configure_fluentbit()
        slurmd.restart()
        self._check_status()

    def _on_slurmctld_unavailable(self, event):
        logger.debug("## Slurmctld unavailable")
        self._set_slurmctld_available(False)
        slurmd.stop()
        self._check_status()

    def _on_slurmd_started(self, _: ServiceStartedEvent) -> None:
        """Handle event emitted by systemd after slurmd daemon successfully starts."""
        self.unit.status = ActiveStatus()

    def _on_slurmd_stopped(self, _: ServiceStoppedEvent) -> None:
        """Handle event emitted by systemd after slurmd daemon is stopped."""
        self.unit.status = BlockedStatus("slurmd not running")

    def _on_config_changed(self, event):
        """Handle charm configuration changes."""
        if self.model.unit.is_leader():
            logger.debug("## slurmd config changed - leader")
            self._on_set_partition_info_on_app_relation_data(event)

        nhc_conf = self.model.config.get("nhc-conf")
        if nhc_conf:
            if nhc_conf != self._stored.nhc_conf:
                self._stored.nhc_conf = nhc_conf
                self._slurm_manager.render_nhc_config(nhc_conf)

    def _write_munge_key_and_restart_munge(self):
        logger.debug("#### slurmd charm - writing munge key")

        self._slurm_manager.configure_munge_key(self._slurmd.get_stored_munge_key())

        if self._slurm_manager.restart_munged():
            logger.debug("## Munge restarted successfully")
        else:
            logger.error("## Unable to restart munge")

    def _on_version_action(self, event):
        """Return version of installed components.

        - Slurm
        - munge
        """
        version = {}
        version["slurm"] = self._slurm_manager.slurm_version()
        version["munge"] = self._slurm_manager.munge_version()

        event.set_results(version)

    def _on_node_configured_action(self, _: ActionEvent) -> None:
        """Remove node from DownNodes and mark as active."""
        # Trigger reconfiguration of slurmd node.
        self._slurmd.new_node = False
        slurmd.restart()
        logger.debug("### This node is not new anymore")

    def _on_get_node_inventory_action(self, event):
        """Return node inventory."""
        inventory = self._slurmd.node_inventory
        logger.debug(f"### Node inventory: {inventory}")

        # Juju does not like underscores in dictionaries
        inv = {k.replace("_", "-"): v for k, v in inventory.items()}
        event.set_results(inv)

    def _on_set_node_inventory_action(self, event):
        """Overwrite the node inventory."""
        inventory = self._slurmd.node_inventory

        # update local copy of inventory
        memory = event.params.get("real-memory", inventory["real_memory"])
        inventory["real_memory"] = memory

        # send it to slurmctld
        self._slurmd.node_inventory = inventory

        event.set_results({"real-memory": memory})

    def _on_show_nhc_config(self, event):
        """Show current nhc.conf."""
        nhc_conf = self._slurm_manager.get_nhc_config()
        event.set_results({"nhc.conf": nhc_conf})

    def _on_set_partition_info_on_app_relation_data(self, event):
        """Set the slurm partition info on the application relation data."""
        # Only the leader can set data on the relation.
        if self.model.unit.is_leader():
            # If the relation with slurmctld exists then set our
            # partition info on the application relation data.
            # This handler shouldn't fire if the relation isn't made,
            # but add this extra check here just in case.
            if self._slurmd.is_joined:
                if partition := {
                    "partition_name": self.app.name,
                    "partition_config": self.config.get("partition-config"),
                    "partition_state": self.config.get("partition-state"),
                }:
                    self._slurmd.set_partition_info_on_app_relation_data(partition)
                else:
                    event.defer()
            else:
                event.defer()

    @property
    def hostname(self) -> str:
        """Return the hostname."""
        return self._slurm_manager.hostname

    @property
    def cluster_name(self) -> str:
        """Return the cluster-name."""
        return self._stored.cluster_name

    @cluster_name.setter
    def cluster_name(self, name: str):
        """Set the cluster-name."""
        self._stored.cluster_name = name


if __name__ == "__main__":  # pragma: nocover
    main(SlurmdCharm)
