# RAIL Setup and Distribution Assets and Scripts

All assets and scripts related to the setup and distribution of RAIL, including convenience setup scripts and Docker files. All documentation regarding setup and distribution for end-users is available on [the official documentation](https://rail-hub.readthedocs.io/).

This repository contains no underlying RAIL code or files related to the PyPI distribution of RAIL or related packages. Please see [the RAIL base](https://github.com/LSSTDESC/rail_base) or [Top level RAIL](https://github.com/LSSTDESC/rail) repositories for details.

For instructions on using the setup script, visit the [Releases tab](https://github.com/LSSTDESC/rail_setup/releases/latest)

## Updating the setup script

1. Make your changes to the script, and update the version number at the top of the file.
2. Commit and push your changes to GitHub (making a PR to the main branch if necessary).
3. On the [repository releases page](https://github.com/LSSTDESC/rail_setup/releases), create a new release.
4. In the "select tag" drop down, choose "Create new tag".
5. Name the tag with the same text as the `__version__` variable, and title the release the same thing.
6. Click "Publish release"
7. The GitHub action will then create the conda lock files, and copy them and the setup script into the release assets, as well as build the Docker image.
