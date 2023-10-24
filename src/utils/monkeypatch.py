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

"""Monkeypatch slurmd operator classes and methods to work on CentOS 7."""

import inspect
import logging
import textwrap
from pathlib import Path

from charms.operator_libs_linux.v0.juju_systemd_notices import (
    SystemdNotices,
    _daemon_reload,
    _enable_service,
    _start_service,
)
from charms.operator_libs_linux.v1 import systemd

from . import slurmd

_logger = logging.getLogger(__name__)


def juju_systemd_notices(notices: SystemdNotices) -> SystemdNotices:
    """Patch SystemdNotices object from juju_systemd_notices.

    This function will patch the subscribe method of SystemdNotices
    to use `/usr/bin/env python3.8` as the PYTHONEXE for running the
    juju_systemd_notices daemon when on CentOS 7.

    Args:
        notices: SystemdNotices class reference to patch.
    """
    _logger.debug("Monkeypatching SystemdNotices subscribe method")

    def patched_subscribe(self) -> None:  # pragma: nocover
        _logger.debug("Generating systemd notice hooks for %s", self._services)
        start_hooks = [Path(f"hooks/service-{service}-started") for service in self._services]
        stop_hooks = [Path(f"hooks/service-{service}-stopped") for service in self._services]
        for hook in start_hooks + stop_hooks:
            if hook.exists():
                _logger.debug("Hook %s already exists. Skipping...", hook.name)
            else:
                hook.symlink_to(self._charm.framework.charm_dir / "dispatch")

        _logger.debug("Starting %s daemon", self._service_file.name)
        if self._service_file.exists():
            _logger.debug("Overwriting existing service file %s", self._service_file.name)
        self._service_file.write_text(
            textwrap.dedent(
                f"""
                [Unit]
                Description=Juju systemd notices daemon
                After=multi-user.target

                [Service]
                Type=simple
                Restart=always
                WorkingDirectory={self._charm.framework.charm_dir}
                Environment="PYTHONPATH={self._charm.framework.charm_dir / "venv"}"
                ExecStart=/usr/bin/env python3.8 {inspect.getfile(notices)} {self._charm.unit.name}

                [Install]
                WantedBy=multi-user.target
                """
            ).strip()
        )
        _logger.debug("Service file %s written. Reloading systemd", self._service_file.name)
        _daemon_reload()
        # Notices daemon is enabled so that the service will start even after machine reboot.
        # This functionality is needed in the event that a charm is rebooted to apply updates.
        _enable_service(self._service_file.name)
        _start_service(self._service_file.name)
        _logger.debug("Started %s daemon", self._service_file.name)

    notices.subscribe = patched_subscribe
    return notices


def slurmd_override_default(slurmd_module: slurmd) -> slurmd:
    """Patch override_default function for slurmd utility.

    This function will patch the override_default function of the slurmd utility
    to save

    Args:
        slurmd_module: slurmd utility module reference to patch.
    """
    _logger.debug("Monkeypatching slurmd.override_default function")

    def patched_override_default(host: str, port: int) -> None:  # pragma: nocover
        _logger.debug(f"Overriding /etc/default/slurmd with hostname {host} and port {port}")
        Path("/etc/sysconfig/slurmd").write_text(
            textwrap.dedent(
                f"""
                SLURMD_OPTIONS="--conf-server {host}:{port}"
                PYTHONPATH={Path.cwd() / "lib"}
                """
            ).strip()
        )

    slurmd_module.override_default = patched_override_default
    return slurmd_module


def slurmd_override_service(slurmd_module: slurmd) -> slurmd:
    """Patch override_service function from slurmd utility.

    This function will patch the override_service function of the slurmd utility
    to use `/usr/bin/env python3.8` as the PYTHONEXE for running the custom slurmd
    ExecStart script in the slurmd service file.

    Args:
        slurmd_module: slurmd utility module reference to patch.
    """
    _logger.debug("Monkeypatching slurmd.override_service function")

    def patched_override_service() -> None:  # pragma: nocover
        _logger.debug("Overriding default slurmd service file")
        if not (override_dir := Path("/etc/systemd/system/slurmd.service.d")).is_dir():
            override_dir.mkdir()

        overrides = override_dir / "99-slurmd-charm.conf"
        overrides.write_text(
            textwrap.dedent(
                f"""
                    [Unit]
                    ConditionPathExists=

                    [Service]
                    Type=forking
                    ExecStart=
                    ExecStart=/usr/bin/env python3.8 {inspect.getfile(slurmd_module)}
                    LimitMEMLOCK=infinity
                    LimitNOFILE=1048576
                    TimeoutSec=900
                    """
            ).strip()
        )
        systemd.daemon_reload()

    slurmd_module.override_service = patched_override_service
    return slurmd_module
