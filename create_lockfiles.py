#!/usr/bin/env python3
"""
Create RAIL conda lockfiles.

Create lockfiles which specify exact version requirements for the full
dependency tree of `environment.yml` for a set of Python versions.
Requires pyyaml and conda-lock.

Run by the rail_setup GitHub action to attach lockfiles to a GitHub release
that can later be downloaded by the setup script.
"""
import subprocess
from copy import deepcopy
from pathlib import Path

import yaml

PYTHON_VERSIONS = ["3.12", "3.13", "3.14"]

# load the environment.yml
with Path("environment.yml").open(encoding="utf-8") as file:
    environment = yaml.safe_load(file)

for version in PYTHON_VERSIONS:
    filename = f"environment-{version}.yml"

    # create a new version of the environment spec, with a specific python version
    environment_version = deepcopy(environment)
    environment_version["dependencies"].append(f"python={version}")
    Path(filename).write_text(yaml.safe_dump(environment_version), encoding="utf-8")

    # create a lockfile based on the spec
    # conda-lock is a python-based program but they don't explicitly expose a python API
    command = f"conda-lock lock --kind explicit --platform linux-64 --platform osx-arm64 --file {filename} --filename-template conda-{{platform}}-py{version}.lock"
    print(command)
    subprocess.run(command, shell=True, encoding="utf-8", check=True)
