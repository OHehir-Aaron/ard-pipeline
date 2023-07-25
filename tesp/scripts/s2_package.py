#!/usr/bin/env python

"""Test Packaging entrypoint."""

import click

from tesp.package import package
from wagl.acquisition import acquisitions


@click.command()
@click.option(
    "--level1-pathname",
    type=click.Path(exists=True, readable=True),
    help="The level1 pathname.",
    required=True,
)
@click.option(
    "--wagl-filename",
    type=click.Path(exists=True, readable=True),
    help="The filename of the wagl output.",
    required=True,
)
@click.option(
    "--fmask-pathname",
    type=click.Path(exists=True, readable=True),
    help=(
        "The pathname to the directory containing the fmask "
        "results for the level1 dataset."
    ),
    required=True,
)
@click.option(
    "--prepare-yamls",
    type=click.Path(exists=True, readable=True),
    help="The pathname to the level1 prepare yamls.",
    required=True,
)
@click.option(
    "--outdir", type=click.Path(), help="The output directory.", required=True
)
def package_output(
    level1_pathname, wagl_filename, fmask_pathname, prepare_yamls, outdir
):
    """Prepare or package a wagl output file."""
    container = acquisitions(level1_pathname, None)

    for granule in container.granules:
        package(
            level1_pathname,
            wagl_filename,
            fmask_pathname,
            prepare_yamls,
            outdir,
            granule,
        )


if __name__ == "__main__":
    package_output()
