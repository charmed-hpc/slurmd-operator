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

"""Helpers for the slurmd integration tests."""

import logging
import pathlib
from typing import Dict
from urllib import request

logger = logging.getLogger(__name__)

NHC = "lbnl-nhc-1.4.3.tar.gz"
NHC_URL = f"https://github.com/mej/nhc/releases/download/1.4.3/{NHC}"


def get_slurmd_res() -> Dict[str, pathlib.Path]:
    """Get slurmd resources needed for charm deployment."""
    if not (nhc := pathlib.Path(NHC)).exists():
        logger.info(f"Getting resource {NHC} from {NHC_URL}")
        request.urlretrieve(NHC_URL, nhc)

    return {"nhc": nhc}
