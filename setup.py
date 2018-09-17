#!/usr/bin/env python

import versioneer
from setuptools import find_packages, setup

setup(
    name="eugl",
    version=versioneer.get_version(),
    description="Modules that deal with sensor and data quality characterisation.",
    packages=find_packages(),
    install_requires=[
        "eodatasets",
        "click",
        "click_datetime",
        "numpy",
        "rasterio",
        "rios",
        "python-fmask",
    ],
    package_data={"eugl.gqa": ["data/*.csv"]},
    dependency_links=[
        "hg+https://bitbucket.org/chchrsc/rios/get/rios-1.4.5.zip#egg=rios-1.4.5",
        "hg+https://bitbucket.org/chchrsc/python-fmask/get/python-fmask-0.4.5.zip#egg=python-fmask-0.4.5",
    ],
)
