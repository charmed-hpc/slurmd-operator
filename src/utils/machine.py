# Copyright 2020 Omnivector Solutions, LLC.
# See LICENSE file for licensing details.

"""machine.py module for slurmd charm."""

import os
import subprocess
import sys

from slurm_ops_manager.utils import get_real_mem


def lscpu():
    """Return lscpu as a python dictionary."""

    def format_key(lscpu_key):
        key_lower = lscpu_key.lower()
        replace_hyphen = key_lower.replace("-", "_")
        replace_lparen = replace_hyphen.replace("(", "")
        replace_rparen = replace_lparen.replace(")", "")
        return replace_rparen.replace(" ", "_")

    lscpu_out = subprocess.check_output(["lscpu"])
    lscpu_lines = lscpu_out.decode().strip().split("\n")

    return {
        format_key(line.split(":")[0].strip()): line.split(":")[1].strip() for line in lscpu_lines
    }


def cpu_info():
    """Return cpu info needed to generate node inventory."""
    ls_cpu = lscpu()

    return {
        "CPUs": ls_cpu["cpus"],
        "ThreadsPerCore": ls_cpu["threads_per_core"],
        "CoresPerSocket": ls_cpu["cores_per_socket"],
        "SocketsPerBoard": ls_cpu["sockets"],
    }


def lspci_nvidia():
    """Check for and return the count of nvidia gpus."""
    gpus = 0
    try:
        gpus = int(
            subprocess.check_output(
                "lspci | grep -i nvidia | awk '{print $1}' " "| cut -d : -f 1 | sort -u | wc -l",
                shell=True,
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError as e:
        print(e)
        sys.exit(-1)

    for graphics_processing_unit in range(gpus):
        gpu_path = "/dev/nvidia" + str(graphics_processing_unit)
        if not os.path.exists(gpu_path):
            return 0
    return gpus


def get_inventory(node_name, node_addr):
    """Assemble and return the node info."""
    inventory = {
        "NodeName": node_name,
        "NodeAddr": node_addr,
        "State": "UNKNOWN",
        "RealMemory": get_real_mem(),
        **cpu_info(),
    }

    gpus = lspci_nvidia()
    if gpus > 0:
        inventory["Gres"] = gpus
    return inventory
