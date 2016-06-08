#!/usr/bin/env python
"""
Get the current version number.

Public releases are expected to be tagged in the repository
with prefix 'gaip-' and a version number following PEP-440.

Eg. ::

    gaip-0.1.0
    gaip-0.2.0.dev1
    gaip-0.2.0+9f43bbc

Refer to PEP440: https://www.python.org/dev/peps/pep-0440

This script is derived from https://github.com/Changaco/version.py
"""

from __future__ import absolute_import, print_function

import re
import os
from os.path import dirname, isdir, join, exists
from subprocess import CalledProcessError, check_output

import pkg_resources

PREFIX = 'gaip-'

GIT_TAG_PATTERN = re.compile(r'\btag: %s([0-9][^,]*)\b' % PREFIX)
VERSION_PATTERN = re.compile(r'^Version: (.+)$', re.M)
NUMERIC = re.compile(r'^\d+$')

GIT_ARCHIVE_REF_NAMES = '$Format:%D$'
GIT_ARCHIVE_COMMIT_HASH = '$Format:%h$'


def get_version():
    package_dir = dirname(dirname(__file__))
    git_dir = join(package_dir, '.git')

    if isdir(git_dir):
        # Ask git for an annotated version number
        # (eg. "gaip-0.0.0-651-gcf335a9-dirty")
        cmd = [
            'git',
            'describe', '--tags', '--match', '[0-9]*', '--dirty'
        ]
    with remember_cwd():
        os.chdir(package_dir)
            try:
                git_version = check_output(cmd).decode().strip()
            except CalledProcessError:
                raise RuntimeError('Unable to get version number from git tags')

    components = git_version.split('-')
    version = components.pop(0)

    # Any other suffixes imply this is not a release: Append an internal build number
    if components:
        # <commit count>.<git hash>.<whether the working tree is dirty>
        version += '+' + '.'.join(components)

    return version


def remember_cwd():
    current_dir = os.getcwd()
    try:
        yield
    finally:
        os.chdir(current_dir)


if __name__ == '__main__':
    print(get_version())
