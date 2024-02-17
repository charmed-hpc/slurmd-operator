#!/usr/bin/env python3
"""Nodes Interface.

Node config or `node_config` is a json string that contains the node configuration.

The `node_config` is set by each slurmd unit on its relation data on the `nodes`
interface.

The `node_config` can contain any slurm Node level configuration data and can be found here:
https://slurm.schedmd.com/slurm.conf.html#SECTION_NODE-CONFIGURATION.

Example `node_config`:

{
    'node_name': 'compute-gpu-0',
    'node_addr': '10.204.129.33',
    'real_memory': '64012',
    'cpus': '2',
    'state': 'UNKNOWN',
    'sockets': '2'
{

"""
import copy
import json
import logging

from ops.framework import Object
from ops.model import Relation

from utils import machine

logger = logging.getLogger()


class Nodes(Object):
    """Nodes inventory interface."""

    def __init__(self, charm, relation_name):
        """Set self._relation_name and self.charm."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[self._relation_name].relation_created,
            self._on_relation_created,
        )

    def _on_relation_created(self, event):
        """Handle the relation-created event.

        Set the node_config on the unit relation data.
        """
        self.send_node_config_to_slurmctld()

    @property
    def _relation(self) -> Relation:
        """Return the relation."""
        return self.framework.model.get_relation(self._relation_name)

    def _get_node_config(self, node_name: str, node_addr: str) -> dict:
        """Get the inventory as returned by machine.inventory(),
        and combine with what we have in stored state to
        assemble the full inventory.
        """
        node_inventory = machine.get_inventory(node_name, node_addr)
        node_config = self._charm.node_config.split()
        if len(node_config) > 0:
            user_supplied_node_config = {item.split("=")[0]: item.split("=")[1] for item in node_config}
            return {**node_inventory, **user_supplied_node_config}
        return node_inventory

    def send_node_config_to_slurmctld(self) -> None:
        """Send node_conifguration to slurmctld via nodes relation."""
        node_name = self._charm.hostname
        node_addr = self.model.get_binding(self._relation_name).network.ingress_address

        self._relation.data[self.model.unit]["node"] = json.dumps(
            {
                "node_config": self._get_node_config(node_name, f"{node_addr}"),
                "partition_name": self._charm.app.name,
                "new_node": self._charm.new_node,
            }
        )
