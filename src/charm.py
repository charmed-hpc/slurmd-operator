#!/usr/bin/env python3
# Copyright 2020 Omnivector Solutions, LLC.
# See LICENSE file for licensing details.

"""SlurmdCharm."""

import json
import logging
from pathlib import Path
from time import sleep

from charms.fluentbit.v0.fluentbit import FluentbitClient
from interface_slurmd import Slurmd
from omnietcd3 import Etcd3AuthClient
from ops.charm import CharmBase, CharmEvents
from ops.framework import EventBase, EventSource, StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from slurm_ops_manager import SlurmManager

logger = logging.getLogger()


class SlurmdStart(EventBase):
    """Emitted when slurmd should start."""


class SlurmctldStarted(EventBase):
    """Emitted when slurmd should start."""


class CheckEtcd(EventBase):
    """Emitted when slurmd should start."""


class SlurmdCharmEvents(CharmEvents):
    """Slurmd emitted events."""

    slurmd_start = EventSource(SlurmdStart)
    slurmctld_started = EventSource(SlurmctldStarted)
    check_etcd = EventSource(CheckEtcd)


class SlurmdCharm(CharmBase):
    """Slurmd lifecycle events."""

    _stored = StoredState()
    on = SlurmdCharmEvents()

    def __init__(self, *args):
        """Init _stored attributes and interfaces, observe events."""
        super().__init__(*args)

        self._stored.set_default(
            nhc_conf=str(),
            slurm_installed=False,
            slurmctld_available=False,
            slurmctld_started=False,
            cluster_name=str(),
            etcd_slurmd_pass=str(),
            etcd_tls_cert=str(),
            etcd_ca_cert=str(),
        )

        self._slurm_manager = SlurmManager(self, "slurmd")
        self._fluentbit = FluentbitClient(self, "fluentbit")

        # interface to slurmctld, should only have one slurmctld per slurmd app
        self._slurmd = Slurmd(self, "slurmd")

        event_handler_bindings = {
            self.on.install: self._on_install,
            self.on.upgrade_charm: self._on_upgrade,
            self.on.update_status: self._on_update_status,
            self.on.config_changed: self._on_config_changed,
            self.on.slurmctld_started: self._on_slurmctld_started,
            self.on.slurmd_start: self._on_slurmd_start,
            self.on.check_etcd: self._on_check_etcd,
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

        custom_repo = self.config.get("custom-slurm-repo")
        successful_installation = self._slurm_manager.install(custom_repo, nhc_path)
        logger.debug(f"### slurmd installed: {successful_installation}")

        if successful_installation:
            self._stored.slurm_installed = True
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

        if not self._stored.slurmctld_started:
            self.unit.status = WaitingStatus("Waiting slurmctld to start")
            return False

        self.unit.status = ActiveStatus("slurmd available")
        return True

    def ensure_slurmd_starts(self, max_attemps=10) -> bool:
        """Ensure slurmd is up and running."""
        logger.debug("## Stopping slurmd")
        self._slurm_manager.slurm_systemctl("stop")

        for i in range(max_attemps):
            if self._slurm_manager.slurm_is_active():
                logger.debug("## Slurmd running")
                break
            else:
                logger.warning("## Slurmd not running, trying to start it")
                self.unit.status = WaitingStatus("Starting slurmd")
                self._slurm_manager.restart_slurm_component()
                sleep(2 + i)

        if self._slurm_manager.slurm_is_active():
            return True
        else:
            self.unit.status = BlockedStatus("Cannot start slurmd")
            return False

    def _set_slurmctld_available(self, flag: bool):
        """Change stored value for slurmctld availability."""
        self._stored.slurmctld_available = flag

    def _set_slurmctld_started(self, flag: bool):
        """Change stored value for slurmctld started."""
        self._stored.slurmctld_started = flag

    def _on_slurmctld_available(self, event):
        """Get data from slurmctld and send inventory."""
        if not self._stored.slurm_installed:
            event.defer()
            return

        logger.debug("#### Slurmctld available - setting overrides for configless")
        # get slurmctld host:port from relation and override systemd services
        host = self._slurmd.slurmctld_hostname
        port = self._slurmd.slurmctld_port
        self._slurm_manager.create_configless_systemd_override(host, port)
        self._slurm_manager.daemon_reload()

        self._write_munge_key_and_restart_munge()

        self._set_slurmctld_available(True)
        self._on_set_partition_info_on_app_relation_data(event)
        self._check_status()

        # check etcd for hostnames
        self.on.check_etcd.emit()

    @property
    def etcd_use_tls(self) -> bool:
        """Return whether TLS certificates are available."""
        return bool(self.etcd_tls_cert)

    @property
    def etcd_tls_cert(self) -> str:
        """Return TLS certificate."""
        return self._stored.etcd_tls_cert

    @etcd_tls_cert.setter
    def etcd_tls_cert(self, tls_cert: str):
        """Store TLS certificate."""
        self._stored.etcd_tls_cert = tls_cert

    @property
    def etcd_ca_cert(self) -> str:
        """Return CA TLS certificate."""
        return self._stored.etcd_ca_cert

    @etcd_ca_cert.setter
    def etcd_ca_cert(self, ca_cert: str):
        """Store CA TLS certificate."""
        self._stored.etcd_ca_cert = ca_cert

    def _on_check_etcd(self, event):
        """Check if node is accounted for.

        Check if slurmctld accounted for this node's inventory for the first
        time, if so, emit slurmctld_started event, so the node can start the
        daemon.
        """
        host = self._slurmd.slurmctld_address
        port = self._slurmd.etcd_port

        username = "slurmd"
        password = self._stored.etcd_slurmd_pass

        protocol = "http"
        ca_cert = None
        if self.etcd_use_tls:
            protocol = "https"
            ca_cert = Path("/etc/slurm/tls_cert.crt")
            ca_cert.write_text(self.etcd_tls_cert)
            ca_cert = Path.as_posix()
        if self.etcd_ca_cert:
            ca_cert = Path("/etc/slurm/ca_cert.crt")
            ca_cert.write_text(self.etcd_ca_cert)
            ca_cert = Path.as_posix()

        logger.debug(f"## Connecting to etcd3 in {protocol}://{host}:{port}, {ca_cert}")
        client = Etcd3AuthClient(
            host=host,
            port=port,
            protocol=protocol,
            ca_cert=ca_cert,
            username=username,
            password=password,
        )

        logger.debug("## Querying etcd3 for node list")
        try:
            v = client.get(key="nodes/all_nodes")
            logger.debug(f"## Got: {v}")
        except Exception as e:
            logger.error(f"## Unable to connect to {host} to get list of nodes: {e}")
            event.defer()
            return

        node_accounted = False
        if v:
            hostnames = json.loads(v[0])
            logger.debug(f"### etcd3 node list: {hostnames}")
            if self.hostname in hostnames:
                self.on.slurmctld_started.emit()
                node_accounted = True

        if not node_accounted:
            logger.debug("## Node not accounted for. Deferring.")
            event.defer()

    def _on_slurmctld_unavailable(self, event):
        logger.debug("## Slurmctld unavailable")
        self._set_slurmctld_available(False)
        self._set_slurmctld_started(False)
        self._slurm_manager.slurm_systemctl("stop")
        self._check_status()

    def _on_slurmctld_started(self, event):
        """Set flag to True and emit slurmd_start event."""
        self._set_slurmctld_started(True)
        self.on.slurmd_start.emit()

    def _on_slurmd_start(self, event):
        if not self._check_status():
            event.defer()
            return

        # only set up fluentbit if we have a relation to it
        if self._fluentbit._relation is not None:
            self._configure_fluentbit()

        # at this point, we have slurm installed, munge configured, and we know
        # slurmctld accounted for this node. It should be safe to start slurmd
        if self.ensure_slurmd_starts():
            logger.debug("## slurmctld started and slurmd is running")
        else:
            event.defer()
        self._check_status()

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

    def _on_node_configured_action(self, event):
        """Remove node from DownNodes."""
        # trigger reconfig
        self._slurmd.configure_new_node()
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
                    "partition_state": self.config.get("partition-config"),
                    "partition_config": self.config.get("partition-state"),
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

    def store_etcd_slurmd_pass(self, password: str):
        """Save the slurmd password for etcd in the stored state."""
        self._stored.etcd_slurmd_pass = password


if __name__ == "__main__":
    main(SlurmdCharm)
