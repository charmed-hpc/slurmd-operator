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

"""Configure integration test run."""

import pathlib

from helpers import ETCD, NHC, VERSION
from pytest import fixture
from pytest_operator.plugin import OpsTest


@fixture(scope="module")
async def slurmd_charm(ops_test: OpsTest):
    """Build slurmd charm to use for integration tests."""
    charm = await ops_test.build_charm(".")
    return charm


def pytest_sessionfinish(session, exitstatus) -> None:
    """Clean up repository after test session has completed."""
    pathlib.Path(ETCD).unlink(missing_ok=True)
    pathlib.Path(NHC).unlink(missing_ok=True)
    pathlib.Path(VERSION).unlink(missing_ok=True)
