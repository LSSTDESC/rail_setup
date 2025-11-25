#!/usr/bin/env python3

"""
This script will install RAIL and its dependencies into a new, isolated virtual
environment.

It will perform the following steps:
    1. Check operating system compatibility, and system-level requirements
    2. Locate or install a Python virtual environment manager (conda or equivalent)
    3. Create a new virtal environment with a user-specfied name, containing RAIL
       dependencies
    4. Install the umbrella RAIL package pz-rail into the new environment
    5. Install additional user-specified packages into the environment, including other
       RAIL-related packages and useful development tools
    6. Provide instructions on operating the new environment

This script is not extensively tested on all systems, and may fail in specific
situations. It is intended for use with simple, generic setups. If your use case
involves non-standard hardware, strict versioning requirements, or an otherwise custom
workflow, we recommend using the action of this script as a starting point, and doing a
manual installation tailored to your use case.

This script was heavily inspired by the Poetry installation script developed at
https://github.com/python-poetry/install.python-poetry.org
"""

import sys

#  --- Modified from install-poetry.py ---
# Eager version check so we fail nicely before possible syntax errors
if sys.version_info < (3, 10):
    sys.stdout.write("RAIL installer requires Python 3.10 or newer to run!\n")
    sys.exit(1)
#  ------

import argparse
import json
import os
import re
import shutil
import subprocess
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#  --- Modified from install-poetry.py ---
FOREGROUND_COLORS = {
    # "black": 30,
    "red": 31,
    # "green": 32,
    # "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    # "white": 37,
}
OPTIONS = {"invert": 7}


def style(fg: str | None, invert: bool | None) -> str:
    """Combine a set of ASCII colour codes"""
    codes = []

    if fg:
        codes.append(FOREGROUND_COLORS[fg])
    if invert:
        codes.append(OPTIONS["invert"])

    codes_string = ";".join(map(str, codes))
    return f"\033[{codes_string}m"


STYLES = {
    "error": style("red", False),  # error messages
    "cmd": style("cyan", False),  # cli commands
    "path": style("cyan", False),  # filesystem paths
    "question": style("magenta", False),  # for `request_input`
    "highlight": style("blue", False),
}


def colorize(style_name: str, text: str) -> str:
    """Apply colour styles to a piece of text"""
    if sys.stdout.isatty():
        return f"{STYLES[style_name]}{text}\033[0m"
    return text


#  ------

RAIL_COLORIZED = colorize("highlight", "RAIL")
EXTRA_RAIL_PACKAGES = [
    "pz-rail-astro-tools",
    "pz-rail-bpz",
    "pz-rail-cmnn",
    "pz-rail-dnf",
    "pz-rail-dsps",
    "pz-rail-flexzboost",
    "pz-rail-fsps",
    "pz-rail-gpz-v1",
    "pz-rail-pzflow",
    "pz-rail-sklearn",
    "pz-rail-som",
    "pz-rail-yaw",
    "pz-rail-lephare",
]


ERROR_MISSING_PREREQUISITES = """
Missing prerequisite(s): {missing}

See the RAIL documentation page on required programs for more information.
"""
ERROR_NO_CLANG = """
Only GNU versions of C compilers are supported, but `{version_command}` found an LLVM
(clang) compiler.

Install the GNU versions (e.g., with Homebrew on MacOS), and set the C compiler
environment variable(s) accordingly before re-running the script.

`CC=/path/to/gnu/gcc CXX=/path/to/gnu/g++ ./install-rail.py`
"""
ERROR_NONINTERACTIVE_INPUT = """
User input needed, but output device is not a tty. To run the RAIL installation script
in an unattended mode, ensure all choices are given as command-line options.

Input needed: {prompt}
"""
ERROR_ENV_MANAGER_ALREADY_INSTALLED = """
Requested installation of `{to_install}` but `{already_installed}` was already found on
the system.
"""
ERROR_ENV_MANAGER_OUT_OF_DATE = """
The installed version of `{env_manager}` ({present}) is out of date, at least {required} is
required. Please manually upgrade or remove it.
"""
ERROR_SPECS_MESSAGE = """
If this error occurred while creating or installing into a Python virtual environment,
and the error message is vague, this may be related to hardware specifications. Please
visit the RAIL documentation on minimum requirements.

Working with the RAIL virtual environment requires at least 4GiB of RAM, and 5GiB of free storage.
"""
ERROR_ENV_MANAGER_EXISTS_WITHOUT_PATH = """
\n`{env_manager} is not present in $PATH, but an activation script exists at
{activation_script_path}. Follow the {env_manager} instructions for initializing your
shell, then restart your terminal session.
"""

MESSAGE_ENV_EXISTS = """
An environment named {name} already exists.
Please choose another name, or exit the script, remove the
environment, and try again. See the documentation on removing
environments at:
https://docs.conda.io/projects/conda/en/stable/commands/env/remove.html

Note that if this script was halted partway through environment creation, environment
removal may be less straightforward
"""
MESSAGE_NO_ENV_MANAGER_FOUND = """
Require one of {executables} to be present in $PATH.
If one of these is already installed, this script cannot find it.
"""
MESSAGE_POST_INSTALL = (
    """
To use the newly installed environment manager {env_manager}, restart your terminal
session or activate your shell's init script (with `{source_cmd}` or similar).

To enter the {env_name} virtual environment, run: `{activation_cmd}`

To install additional packages:
- From conda-forge (link) `{packages_conda_cmd}`
- From PyPI (link) `{packages_pip_cmd}`

In the environment you also have access to the rail cli.
"""
    + f"Run `{colorize('cmd','rail --help')}` and visit the documentation [link]."
)


@dataclass
class EnvironmentManager:
    """Class to hold information about a conda-compatible Python virtual environment manager"""

    # mandatory on creation
    name: str
    installable: bool = field(kw_only=True)
    # optional on creation
    executable: str = field(default="", kw_only=True)
    directory: str | Path | None = field(default=None, kw_only=True)
    installer_link: str | None = field(default=None, kw_only=True)
    installer_options: list[str] | None = field(default=None, kw_only=True)
    # generated only
    activation_script: Path | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.directory is not None:
            self.directory = Path(self.directory).expanduser()
            self.activation_script = self.directory / "bin" / "activate"

        if self.executable == "":
            self.executable = self.name


ENV_MANAGER_INFO = [
    EnvironmentManager("micromamba", installable=False),
    EnvironmentManager(
        "mamba",
        installable=True,
        directory="~/miniforge3",
        installer_link="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-{kernel}-{architecture}.sh",
        installer_options=["-b", "-u", "-p"],
    ),
    EnvironmentManager(
        "miniconda",
        installable=True,
        directory="~/miniconda3",
        executable="conda",
        installer_link="https://repo.anaconda.com/miniconda/Miniconda3-latest-{kernel}-{architecture}.sh",
        installer_options=["-b", "-u", "-c", "-p"],
    ),
    EnvironmentManager(
        "anaconda", installable=False, directory="~/anaconda3", executable="conda"
    ),
]


class RAILInstallationError(RuntimeError):
    """Custom error to provide a user-friendly error message and exit code rather than a
    traceback"""

    def __init__(self, message: str, return_code: int = 1) -> None:
        if not message.startswith("\n"):
            message = "\n" + message
        if not message.endswith("\n"):
            message = message + "\n"
        print(colorize("error", message))
        sys.exit(return_code)


@dataclass
class Installer:
    """Primary class for running the RAIL installation script"""

    # passed on creation
    fetcher: str
    dry_run: bool
    verbose: bool

    env_manager: None | EnvironmentManager = field(default=None, init=False)
    env_manager_preinitialized: bool = field(default=False, init=False)
    env_name: str = field(init=False)
    kernel: str = os.uname().sysname
    architecture: str = os.uname().machine

    def uname_convert(self, use_case: str) -> tuple[str, str]:
        """Get the current kernel and architecture formatted for a specific purpose

        Parameters
        ----------
        use_case : str
            One of a set number of purposes

        Returns
        -------
        tuple[str, str]
            (kernel, architecture)
        """

        match use_case:
            case "conda":
                # https://repo.anaconda.com/miniconda/
                kernel = "MacOSX" if self.kernel == "Darwin" else "Linux"
                architecture = (
                    self.architecture
                )  # accepts arm64 for mac and aarch64 for linux
            case "mamba":
                # https://github.com/conda-forge/miniforge/releases/tag/25.3.1-0
                kernel, architecture = (
                    self.kernel,
                    self.architecture,
                )  # accepts arm64 for mac and aarch64 for linux
            case "micromamba":
                # https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html#linux-and-macos
                kernel = "osx" if self.kernel == "Darwin" else "linux"
                architecture = "64" if self.architecture == "x86_64" else "arm64"
            case "conda-lock":
                # `conda-lock render`
                kernel = "osx" if self.kernel == "Darwin" else "linux"
                architecture = "64" if self.architecture == "x86_64" else "arm64"

        return (kernel, architecture)

    def run_cmd(
        self, cmd: str, as_comment: bool = False, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        """Convenience wrapper around top-level function `run_cmd()`"""
        return run_cmd(cmd, as_comment=as_comment, **kwargs)

    def run_fetch_cmd(
        self,
        url: str,
        output_filename: str,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Wrapper around `Installer.run_cmd` for running downloads

        Parameters
        ----------
        url : str
            URL to fetch from
        output_filename : str
            Location to save the file

        Returns
        -------
        subprocess.CompletedProcess[str]
            Subshell output
        """
        cmd = f"{self.fetcher} {url}"
        if self.fetcher == "curl":
            cmd = f"{cmd} --location --output {output_filename}"
            if not self.verbose:
                cmd += " --progress-bar"
        if self.fetcher == "wget":
            cmd = f"{cmd} --output-document {output_filename}"
            if not self.verbose:
                cmd += " --quiet --show-progress"
        return self.run_cmd(cmd, **kwargs)

    def run_env_manager_cmd(
        self, cmd: str, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        """Wrapper around `Installer.run_cmd` for running commands related to Python
        environment managers.

        Raises
        ------
        RAILInstallationError
            Raised if the script can't find the environment manager
        """

        if self.env_manager.activation_script is None:
            if shutil.which(self.env_manager.executable) is not None:
                # no need to activate, conda is in $PATH already, this probably means
                # it's init'ed
                return self.run_cmd(cmd, **kwargs)
            # something's gone wrong. we don't know where conda is, but we don't
            # have the activation script either
            raise RAILInstallationError(
                "Something went wrong finding/activating the Python virtual environment manager."
            )
        return self.run_cmd(
            f". {self.env_manager.activation_script} && {cmd}", **kwargs
        )

    def run_in_env_cmd(
        self, cmd: str, **kwargs: Any
    ) -> subprocess.CompletedProcess[str] | None:
        """Wrapper around `Installer.run_env_manager_cmd` for running commands inside a
        Python virtual environment.
        """

        full_command = """{env_manager} run {output_handle} --name {env_name} {cmd}"""
        return self.run_env_manager_cmd(
            full_command.format(
                env_manager=self.env_manager.executable,
                output_handle=(
                    " --no-capture-output"
                    if self.env_manager.executable == "conda"
                    else ""
                ),
                env_name=self.env_name,
                cmd=cmd,
            ),
            **kwargs,
        )

    def find_env_manager(self, name_to_install: str | None = None) -> None:
        """Locates a Python environment manager, either from $PATH, or by installing
        one.

        Parameters
        ----------
        to_install : str | None, optional
            The executable that should be installed, by default None

        Raises
        ------
        RAILInstallationError
            Raised if an environment manager was requested to be installed but one is
            installed already
        """

        print_header("Checking for a pre-installed Python virtual environment manager")

        for env_manager in ENV_MANAGER_INFO:
            in_path = shutil.which(env_manager.executable) is not None

            activation_script_exists = (
                False
                if env_manager.activation_script is None
                else env_manager.activation_script.exists()
            )

            if in_path or activation_script_exists:
                self.env_manager = env_manager
                if in_path:
                    self.env_manager_preinitialized = True

                print(
                    f"Using {env_manager.name} ({colorize('cmd', self.env_manager.executable)})"
                )
                break

        if (self.env_manager is not None) and (name_to_install is not None):
            error_message = ERROR_ENV_MANAGER_ALREADY_INSTALLED.format(
                to_install=name_to_install,
                already_installed=self.env_manager.executable,
            )
            if not self.env_manager_preinitialized:
                error_message += ERROR_ENV_MANAGER_EXISTS_WITHOUT_PATH.format(
                    env_manager=self.env_manager.executable,
                    activation_script_path=env_manager.activation_script,
                )
            raise RAILInstallationError(error_message)

        if self.env_manager is None:
            executables = {e.executable for e in ENV_MANAGER_INFO}
            executable_string = "/".join(
                [colorize("cmd", exec) for exec in executables]
            )
            print(MESSAGE_NO_ENV_MANAGER_FOUND.format(executables=executable_string))

            if name_to_install is None:
                name_to_install = request_input(
                    "Which Python environment manager should be installed?",
                    sorted([e.name for e in ENV_MANAGER_INFO if e.installable]),
                )

            self.install_env_manager(
                [e for e in ENV_MANAGER_INFO if e.name == name_to_install][0]
            )

        self.setup_env_manager()
        self.check_env_manager_version()

    def install_env_manager(self, to_install: EnvironmentManager) -> None:
        """Downloads and installs either miniconda or mamba, based on previous user
        selection."""

        print_header(f"Installing {to_install.name}")

        kernel, architecture = self.uname_convert(to_install.executable)
        installer_link = to_install.installer_link.format(
            kernel=kernel, architecture=architecture
        )
        installer_dir = Path(to_install.directory).expanduser()  # type: ignore[arg-type] # .directory is defined for all installable env managers
        installer_path = installer_dir / f"{to_install.name}-installer.sh"

        # download
        if not self.dry_run:
            installer_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {to_install.name} installer")
        self.run_fetch_cmd(installer_link, str(installer_path), as_comment=self.dry_run)

        # install
        print(
            f"\nInstalling {to_install.name} into {colorize('path',str(installer_dir))}, this may take up to 5 minutes"
        )
        self.run_cmd(
            f"bash {installer_path} {' '.join(to_install.installer_options)} {installer_dir}",  # type: ignore[arg-type] # .installer-options is defined
            as_comment=self.dry_run,
            capture_output=not self.verbose,
        )

        # remove installer
        if not self.dry_run:
            print(f"\nRemoving {to_install.name} installer")
            installer_path.unlink()

        # update env_manager properties
        self.env_manager = to_install

    def setup_env_manager(self) -> None:
        """Run preparatory steps to be able to use a Python environment manager."""

        print_header(f"Initializing {self.env_manager.executable}")
        match self.env_manager.executable:
            case "conda":
                # accept TOS
                for channel in [
                    "https://repo.anaconda.com/pkgs/main",
                    "https://repo.anaconda.com/pkgs/r",
                ]:
                    self.run_env_manager_cmd(
                        f"conda tos accept --override-channels --channel {channel}",
                        as_comment=self.dry_run,
                    )

            case "mamba":
                shell = str(Path(os.environ["SHELL"]).stem)
                cmd, as_comment = f"mamba shell init --shell {shell}", False
                if self.dry_run:
                    if self.env_manager_preinitialized:
                        cmd += " --dry-run"
                    else:
                        as_comment = True
                self.run_env_manager_cmd(cmd, as_comment=as_comment)
            case "micromamba":
                pass

    def check_env_manager_version(self) -> None:
        """Checks that the installed version of whichever Python environment manager is
        recent enough.

        Note that there is some strange behaviour with micromamba's version reporting.
        Compare the result of running these commands:

        >>> micromamba --version
        2.1.1
        >>> python -c "import subprocess; subprocess.run('micromamba --version',
        shell=True)"
        1.5.8

        Raises
        ------
        RAILInstallationError
            Raised if the version is too old.
        """

        print_header(f"Verifying {self.env_manager.executable} version")
        fake_version = self.dry_run and not self.env_manager_preinitialized

        match self.env_manager.executable:
            case "conda":
                version_cmd = "conda --version"
                output_to_version = lambda output: output[output.rindex(" ") + 1 :]
                required_version_string = "23.5.0"
            case "mamba":
                version_cmd = "conda --version"
                output_to_version = lambda output: output[output.rindex(" ") + 1 :]
                required_version_string = "23.5.0"
            case "micromamba":
                version_cmd = f"{self.env_manager.executable} --version"
                output_to_version = lambda output: output
                required_version_string = "1.5.8"

        version_result = self.run_env_manager_cmd(
            version_cmd,
            as_comment=fake_version,
            capture_output=True,
        )
        if fake_version:
            return

        present_version_string = output_to_version(version_result.stdout.strip())

        version_string_to_tuple = lambda vstring: tuple(
            int(i) for i in vstring.split(".")
        )
        if version_string_to_tuple(present_version_string) < version_string_to_tuple(
            required_version_string
        ):
            raise RAILInstallationError(
                ERROR_ENV_MANAGER_OUT_OF_DATE.format(
                    env_manager=self.env_manager.executable,
                    present=present_version_string,
                    required=required_version_string,
                )
            )

    def choose_env_name(self, env_name: str | None) -> None:
        """Get the name of the Python virtual environment to be created.

        Parameters
        ----------
        env_name : str | None, optional
            The environment name passed on the command line if any, by default None

        Raises
        ------
        RAILInstallationError
            Raised if an invalid name was given as a command line parameter
        """

        print_header("Getting virtual environment name")

        if self.env_manager_preinitialized:
            # get list of pre-existing environments
            env_list_output = self.run_cmd(
                f"{self.env_manager.executable} env list --json",
                capture_output=True,
            )
            existing_prefixes = json.loads(env_list_output.stdout)["envs"]

            base_prefix = list(
                json.loads(
                    self.run_cmd(
                        f"{self.env_manager.executable} info --base --json",
                        capture_output=True,
                    ).stdout
                ).values()
            )[0]
            existing_prefixes = [e for e in existing_prefixes if e != base_prefix]
            existing_names = [str(Path(e).stem) for e in existing_prefixes]
            if len(existing_names) > 0:
                print(f"Existing environments: {', '.join(existing_names)}")
        else:
            existing_names = []

        if env_name is not None:
            if check_env_name(env_name, existing_names):
                self.env_name = env_name
            else:
                raise RAILInstallationError(
                    f"Supplied environment name {env_name} already exists"
                )
            print(
                f"Using supplied environment name {colorize('highlight', self.env_name)}"
            )
        else:
            self.env_name = request_input(
                f"Name of new virtual environment to install {RAIL_COLORIZED} in:",
                [],
                allow_any=True,
                validator=lambda name: check_env_name(name, existing_names),
            )

    def create_env(self) -> None:
        """Create a new Python virtual environment with the RAIL environment.yml

        If possible, a lockfile is used to reduce the time spent running the environment
        solver.
        """

        environment_file = "https://raw.githubusercontent.com/LSSTDESC/rail/refs/heads/main/environment.yml"

        kernel, architecture = self.uname_convert("conda-lock")
        lockfile = f"lockfiles/conda-{kernel}-{architecture}.lock"

        # only because local? there is no explicit linux arm lockfile so that would also
        # be a fallback, but not sure how we want to test for the existence of a remote lockfile
        if not Path(lockfile).exists():
            lockfile = environment_file

        print_header(
            f"Creating a new {self.env_manager.executable} environment, this may take up to 10 minutes"
        )
        create_env_cmd = f"{self.env_manager.executable} env create --name {self.env_name} --file {lockfile} --yes"
        as_comment = False
        if self.dry_run:
            if self.env_manager_preinitialized:
                create_env_cmd += " --dry-run"
            else:
                as_comment = True
        if not self.verbose:
            create_env_cmd += " --quiet"

        self.run_env_manager_cmd(create_env_cmd, as_comment=as_comment)

    def pip_install(
        self,
        rail_selection: None | str | list[str],
        devtool_selection: None | str,
    ) -> None:
        """Install packages from PyPI

        Parameters
        ----------
        rail_selection : str | list[str], optional
            "all, "none", a list of rail packages, by default None
        devtool_selection : str, optional
            "yes" or "no", by default None
        """

        print_header(f"Adding {RAIL_COLORIZED} packages to environment")
        rail_packages = ["pz-rail"] + choose_algorithms(rail_selection)
        grouped_packages = choose_additional_dependencies(devtool_selection)

        print(f"Installing `{colorize('cmd','pip')}` packages")
        self.run_in_env_cmd("python -m ensurepip --upgrade", as_comment=self.dry_run)
        if len(grouped_packages) > 0:
            self.pip_install_package(" ".join(grouped_packages))

        for package in rail_packages:
            self.pip_install_package(package)

    def pip_install_package(self, package: str) -> None:
        """Run a single pip install command

        Parameters
        ----------
        package : str
            The package or packages to install
        """

        quiet = "" if self.verbose else " --quiet"
        pip_cmd = f"pip install {package}{quiet}"

        self.run_in_env_cmd(pip_cmd, as_comment=self.dry_run)

    def post_install(self, clean: bool) -> None:
        """Optionally clear pip/conda cache, and print post-install message

        Parameters
        ----------
        clean : bool
            Whether on not to run the cleaning, from CLI only
        """

        if clean:
            self.run_in_env_cmd(
                "conda clean --all --yes"
            )  # brings docker image size down from 5.7G to 4.4
            self.run_in_env_cmd("pip cache purge")  # brings size down from 4.4G

        print_header(colorize("highlight", "Installation complete!"))
        print(
            MESSAGE_POST_INSTALL.format(
                env_manager=colorize("cmd", self.env_manager.executable),
                source_cmd=colorize("cmd", "source ~/.bashrc"),
                env_name=colorize("highlight", self.env_name),
                activation_cmd=colorize(
                    "cmd", f"{self.env_manager.executable} activate {self.env_name}"
                ),
                packages_conda_cmd=colorize(
                    "cmd", f"{self.env_manager.executable} install <package name>"
                ),
                packages_pip_cmd=colorize("cmd", "pip install <package name>"),
            )
        )

    def run(
        self,
        env_manager_to_install: str | None,
        env_name: str | None,
        rail_selection: str | list[str] | None,
        devtool_selection: str | None,
        clean: bool,
    ) -> None:
        """Run all Installer steps in sequence"""

        try:
            self.find_env_manager(name_to_install=env_manager_to_install)
            self.choose_env_name(env_name=env_name)
            self.create_env()
            self.pip_install(
                rail_selection=rail_selection, devtool_selection=devtool_selection
            )
            self.post_install(clean=clean)

        except KeyboardInterrupt as error:
            # exit cleanly without traceback on ctrl-c
            raise RAILInstallationError("Aborting.") from error


def run_cmd(
    cmd: str, as_comment: bool = False, **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    """Run a command in a sub-shell

    Parameters
    ----------
    cmd : str
        The shell command to run
    as_comment : bool, optional
        Whether to prepend a hash, by default False

    Returns
    -------
    subprocess.CompletedProcess[str]
        Subshell output

    Raises
    ------
    RAILInstallationError
        Raised if the command errors out
    """

    if as_comment:
        cmd = "# " + cmd

    print(f"`{colorize('cmd', cmd)}`")

    output = subprocess.run(cmd, shell=True, encoding="utf-8", check=False, **kwargs)

    if output.returncode != 0:

        error_message = "CLI command failed"
        if output.stdout is not None or output.stderr is not None:

            stdout = (
                output.stdout.strip()
                if output.stdout is not None
                else "No output from command"
            )
            stderr = (
                output.stderr.strip()
                if output.stderr is not None
                else "No error from command"
            )
            error_message += f": {stdout}\n{stderr}"

        if output.returncode != 127:
            error_message = f"{error_message}\n{ERROR_SPECS_MESSAGE}"

        raise RAILInstallationError(
            error_message,
            return_code=output.returncode,
        )
    return output


def check_uname() -> None:
    """Validate the platform the script is running on"""

    #  --- From install-poetry.py ---
    windows = sys.platform.startswith("win") or (
        sys.platform == "cmd" and os.name == "nt"
    )
    mingw = sysconfig.get_platform().startswith("mingw")
    #  ------

    intel_mac = sys.platform == "darwin" and os.uname().machine != "arm64"  # NOT TESTED
    arm_linux = sys.platform == "linux" and os.uname().machine != "x86_64"

    if windows or mingw:
        # fitsio (in environment.yml) is not supported on windows
        raise RAILInstallationError(
            "The RAIL installation script is not supported on Windows. Please use WSL."
        )

    if intel_mac:
        # miniconda not supported
        raise RAILInstallationError(
            "The RAIL installation script is not supported for Intel Macs."
        )

    if arm_linux:
        # somoclu (conda-forge dep) not supported
        raise RAILInstallationError(
            "The RAIL installation script is not supported for non-x86 Linux."
        )


def request_input(
    prompt: str,
    options: list[str],
    allow_any: bool = False,
    validator: Callable[[str], bool] | None = None,
) -> str:
    """Request a choice from the user, with a potentially restricted set of choices

    Parameters
    ----------
    prompt : str
        Question/prompt (e.g., `"Do you want to continue?"`)
    options : set[str]
        List of valid options (e.g., `["y","n"]`)
    allow_any : bool, optional
        Whether to allow any generic (rather than forcing only a value from `options`),
        by default False
    validator : Callable[[str], bool], optional
        Additional validation function to be applied, to force re-asking for input, by
        default None

    Returns
    -------
    str
        One of the `options` that was chosen.
    """

    if not sys.stdout.isatty():
        raise RAILInstallationError(ERROR_NONINTERACTIVE_INPUT.format(prompt=prompt))

    options_string = "/".join(options)
    prompt = colorize("question", prompt)
    prompt_string = (
        f"{prompt} ({options_string}) " if len(options) > 0 else f"{prompt} "
    )

    ask = True
    while ask:
        result = input(prompt_string)

        # check result
        default_validation = (allow_any and result != "") or (
            not allow_any and result in options
        )
        extra_validation = (validator is None) or validator(result)

        # re-ask if user did not provide valid input
        ask = (not default_validation) or (not extra_validation)

    return result


def check_requirements() -> str:
    """Check for the presence of tools required to be installed on the system level in
    order to run the RAIL installer

    Returns
    -------
    str
        "curl" or "wget" - the fetcher tool to use

    Raises
    ------
    RAILInstallationError
        Raised if any requirements are missing
    """
    print_header("Checking installation requirements")

    required = ["bash", "gcc", "gfortran", "g++", "make"]
    missing = []
    for cmd in required:
        if shutil.which(cmd) is None:
            missing.append(cmd)

    required_options = [["curl", "wget"]]
    for alternatives in required_options:
        missing_fetcher = [shutil.which(cmd) is None for cmd in alternatives]
        if all(missing_fetcher):
            missing.append(" or ".join(alternatives))

    if len(missing) > 0:
        raise RAILInstallationError(
            ERROR_MISSING_PREREQUISITES.format(missing=", ".join(missing)),
            return_code=127,
        )

    # check that c compilers are gnu
    for compiler in [os.environ.get("CC", "gcc"), os.environ.get("CXX", "g++")]:
        version_command = f"{compiler} --version"
        version_output = run_cmd(
            version_command,
            capture_output=True,
        ).stdout

        if "clang" in version_output:
            raise RAILInstallationError(
                ERROR_NO_CLANG.format(version_command=version_command)
            )

    fetcher = "wget" if shutil.which("wget") is not None else "curl"

    return fetcher


def check_env_name(name: str, existing_names: list[str]) -> bool:
    """Check if the requested environment name already exists"""

    if name in existing_names:
        print(MESSAGE_ENV_EXISTS.format(name=colorize("highlight", name)))
        return False  # not ok, need to rerun
    return True  # ok


def check_algorithms_selection(
    cli_selection: list[str] | None,
) -> None | str | list[str]:
    """Validate the CLI-passed RAIL packages value, converting it into the same type
    that would be recived in interactive mode.

    Parameters
    ----------
    cli_selection : list[str] | None
        Value of --rail-packages option

    Returns
    -------
    None | str | list[str]
        None, "all", "none", or a list of packages

    Raises
    ------
    RAILInstallationError
        Raised if an invalid selection is made on the CLI
    """

    if cli_selection is None:
        return None
    if len(cli_selection) == 1 and cli_selection[0] in ["all", "none"]:
        return cli_selection[0]

    selections_are_invalid = [s not in EXTRA_RAIL_PACKAGES for s in cli_selection]

    if any(selections_are_invalid):
        algos_string = "\n\t".join(EXTRA_RAIL_PACKAGES)
        raise RAILInstallationError(
            f"""Invalid selection for RAIL packages. See the help text for valid options. Available RAIL packages:\n\t{algos_string}"""
        )

    return cli_selection


def choose_algorithms(cli_selection: None | str | list[str]) -> list[str]:
    """Get a list of RAIL pip packages to install based on user input

    Parameters
    ----------
    cli_selection : None | str | list[str]
        Selection made on command line - None, "all", "none", or list of packages

    Returns
    -------
    list[str]
        List of packages, can be empty
    """

    if cli_selection is None:
        algos_string = "\n\t".join(EXTRA_RAIL_PACKAGES)
        print(f"Available {RAIL_COLORIZED} algorithms:\n\t{algos_string}")
        cli_selection = request_input(
            "Which algorithms should be installed?", ["all", "none", "select"]
        )

    if cli_selection == "all":
        return EXTRA_RAIL_PACKAGES

    if cli_selection == "none":
        return []

    if isinstance(cli_selection, list):
        return cli_selection

    return [
        algo
        for algo in EXTRA_RAIL_PACKAGES
        if request_input(f"Install {algo}?", ["y", "n"]) == "y"
    ]


def choose_additional_dependencies(cli_selection: None | str) -> list[str]:
    """Get a list of non-RAIL pip packages to install based on user input

    Parameters
    ----------
    cli_selection : None | str
        Whether to install a list of packages, as set on CLI; None, "yes" or "no"

    Returns
    -------
    list[str]
        List of packages to install. May be empty
    """

    packages = ["jupyter", "seaborn", "corner", "matplotlib"]

    if (cli_selection == "yes") or (
        cli_selection is None
        and request_input(
            f"Install additional packages: {', '.join(packages)}?", ["y", "n"]
        )
        == "y"
    ):
        return packages
    return []


def print_header(message: str) -> None:
    """Print a message in a distinct header format"""

    max_width = shutil.get_terminal_size()[0]
    decolorize = re.compile(r"\x1B\[[0-?9;]*[mK]")
    message_length = len(decolorize.sub("", message))

    underline = "-" * min(message_length, max_width)
    print(f"\n\n{message}\n{underline}")


def main() -> int:
    """Main module function"""

    parser = argparse.ArgumentParser(
        description="""Creates a new Python virtual environment and installs RAIL into
                    it. Selections not set on the command line will be requested
                    interactively"""
    )

    parser.add_argument(
        "--dry-run",
        help="Make no changes to the system, only print what would be done",
        dest="dry_run",
        action="store_true",
    )
    parser.add_argument(
        "--clean",
        help="ClI-only option, intended for containerization. Clear conda and pip caches post-install",
        dest="clean",
        action="store_true",
    )
    parser.add_argument(
        "--verbose",
        help="Display additional output",
        dest="verbose",
        action="store_true",
    )

    env_manager_args = parser.add_argument_group(
        "Python Virtual Environment Manager",
        """`conda` refers to any anaconda-compatible package manager (pre-installed
        copies of Conda, Mamba, and Micromamba are supported)""",
    )
    env_manager_args.add_argument(
        "--install-conda",
        help="What to install. Only Miniconda and Mamba are supported",
        dest="to_install",
        action="store",
        choices=["miniconda", "mamba"],
    )

    environment_args = parser.add_argument_group("Virtual Environment Options")
    environment_args.add_argument(
        "--env-name",
        help="Name of new virtual environment",
        dest="env_name",
        action="store",
    )
    environment_args.add_argument(
        "--install-devtools",
        help="Whether to install additional tools (Jupyter, etc.)",
        dest="install_devtools",
        choices=["yes", "no"],
    )
    environment_args.add_argument(
        "--rail-packages",
        help="""Which rail packages should be installed. Accepts 'all', 'none' or a list
             of items. Note that 'pz-rail' is always installed. Install a subset of
             packages with `--rail-packages pz-rail-dnf pz-rail-yaw`""",
        dest="rail_packages",
        action="store",
        nargs="*",
    )

    # pre-run checks
    args = parser.parse_args()
    check_uname()
    fetcher = check_requirements()
    args.rail_packages = check_algorithms_selection(args.rail_packages)

    installer = Installer(fetcher=fetcher, dry_run=args.dry_run, verbose=args.verbose)
    installer.run(
        env_manager_to_install=args.to_install,
        env_name=args.env_name,
        rail_selection=args.rail_packages,
        devtool_selection=args.install_devtools,
        clean=args.clean,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
