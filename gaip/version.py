#!/usr/bin/env python
"""
Get the current version number.

Public releases are expected to be tagged in the repository
with prefix 'gqa-' and a version number following PEP-440.

Eg. ::

    gqa-0.1.0
    gqa-0.2.0.dev1
    gqa-0.2.0+9f43bbc

Refer to PEP440: https://www.python.org/dev/peps/pep-0440

This script is derived from https://github.com/Changaco/version.py
"""

from __future__ import absolute_import, print_function

import re
from os.path import dirname, isdir, join, exists
from subprocess import CalledProcessError, check_output

import pkg_resources

PREFIX = "gqa-"

GIT_TAG_PATTERN = re.compile(r"\btag: %s([0-9][^,]*)\b" % PREFIX)
VERSION_PATTERN = re.compile(r"^Version: (.+)$", re.M)
NUMERIC = re.compile(r"^\d+$")

GIT_ARCHIVE_REF_NAMES = "$Format:%D$"
GIT_ARCHIVE_COMMIT_HASH = "$Format:%h$"


def get_version():
    package_dir = dirname(dirname(__file__))
    git_dir = join(package_dir, ".git")

    if isdir(git_dir):
        # Ask git for an annotated version number
        # (eg. "gqa-0.0.0-651-gcf335a9-dirty")
        cmd = [
            "git",
            "--git-dir",
            git_dir,
            "describe",
            "--tags",
            "--match",
            "[0-9]*",
            "--dirty",
        ]
        try:
            git_version = check_output(cmd).decode().strip()
        except CalledProcessError:
            raise RuntimeError("Unable to get version number from git tags")
        components = git_version.split("-")
        version = components.pop(0)

        # Any other suffixes imply this is not a release: Append an internal build number
        if components:
            # <commit count>.<git hash>.<whether the working tree is dirty>
            version += "+" + ".".join(components)

    return version


if __name__ == "__main__":
    print(get_version())
