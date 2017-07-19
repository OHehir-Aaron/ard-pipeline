#!/usr/bin/env python
"""Single file workflow for producing NBAR and SBT
-----------------------------------------------.

This workflow is geared to minimise the number of files on disk
and provide a kind of direct to archive compute, and retain all
the necessary intermediate files, which comprise a mixture of
imagery, tables, and point/scalar datasets.

It also provides a consistant logical structure allowing an easier
comparison between 'archives' from different production runs, or
versions of gaip.

This workflow is more suited to full production runs, where testing
has ensured that the workflow is sound, and more easilt allows
thousands of scenes to be submitted to the scheduler at once.

Workflow settings can be configured in `luigi.cfg` file.
"""
# pylint: disable=missing-docstring,no-init,too-many-function-args
# pylint: disable=too-many-locals
# pylint: disable=protected-access

import logging
import traceback
from os.path import basename
from os.path import join as pjoin

import luigi

from gaip.constants import Model
from gaip.standardise import card4l

ERROR_LOGGER = logging.getLogger("luigi-error")
INTERFACE_LOGGER = logging.getLogger("luigi-interface")


def get_buffer(group):
    buf = {"product": 250, "R10m": 700, "R20m": 350, "R60m": 120}
    return buf[group]


@luigi.Task.event_handler(luigi.Event.FAILURE)
def on_failure(task, exception):
    """Capture any Task Failure here."""
    fmt = "Error processing scene:\n{}\npath:\n{}"
    msg = fmt.format(basename(task.level1), task.level1)
    excp_msg = exception.__str__()
    traceback_msg = traceback.format_exc()
    ERROR_LOGGER.error(msg)
    ERROR_LOGGER.error(excp_msg)
    ERROR_LOGGER.error(traceback_msg)


class Standard(luigi.Task):
    """Runs the standardised product workflow."""

    level1 = luigi.Parameter()
    outdir = luigi.Parameter()
    model = luigi.EnumParameter(enum=Model)
    vertices = luigi.TupleParameter(default=(5, 5))
    method = luigi.Parameter(default="shear")
    pixel_quality = luigi.BoolParameter()
    land_sea_path = luigi.Parameter()
    aerosol_fname = luigi.Parameter(significant=False)
    brdf_path = luigi.Parameter(significant=False)
    brdf_premodis_path = luigi.Parameter(significant=False)
    ozone_path = luigi.Parameter(significant=False)
    water_vapour_path = luigi.Parameter(significant=False)
    dem_path = luigi.Parameter(significant=False)
    ecmwf_path = luigi.Parameter(significant=False)
    invariant_height_fname = luigi.Parameter(significant=False)
    dsm_fname = luigi.Parameter(significant=False)
    modtran_exe = luigi.Parameter(significant=False)
    tle_path = luigi.Parameter(significant=False)
    rori = luigi.FloatParameter(default=0.52, significant=False)
    compression = luigi.Parameter(default="lzf", significant=False)
    y_tile = luigi.IntParameter(default=100, significant=False)

    def output(self):
        fmt = "{scene}_{model}.h5"
        scene = basename(self.level1)
        out_fname = fmt.format(scene=scene, model=self.model.name)
        return luigi.LocalTarget(pjoin(self.outdir, out_fname))

    def run(self):
        with self.output().temporary_path() as out_fname:
            card4l(
                self.level1,
                self.model,
                self.vertices,
                self.method,
                self.pixel_quality,
                self.land_sea_path,
                self.tle_path,
                self.aerosol_fname,
                self.brdf_path,
                self.brdf_premodis_path,
                self.ozone_path,
                self.water_vapour_path,
                self.dem_path,
                self.dsm_fname,
                self.invariant_height_fname,
                self.modtran_exe,
                out_fname,
                self.ecmwf_path,
                self.rori,
                self.compression,
                self.y_tile,
            )


class ARD(luigi.WrapperTask):
    """Kicks off ARD tasks for each level1 entry."""

    level1_list = luigi.Parameter()
    outdir = luigi.Parameter()
    model = luigi.EnumParameter(enum=Model)
    vertices = luigi.TupleParameter(default=(5, 5))
    method = luigi.Parameter(default="shear")
    pixel_quality = luigi.BoolParameter()
    land_sea_path = luigi.Parameter()
    aerosol_fname = luigi.Parameter(significant=False)
    brdf_path = luigi.Parameter(significant=False)
    brdf_premodis_path = luigi.Parameter(significant=False)
    ozone_path = luigi.Parameter(significant=False)
    water_vapour_path = luigi.Parameter(significant=False)
    dem_path = luigi.Parameter(significant=False)
    ecmwf_path = luigi.Parameter(significant=False)
    invariant_height_fname = luigi.Parameter(significant=False)
    dsm_fname = luigi.Parameter(significant=False)
    modtran_exe = luigi.Parameter(significant=False)
    tle_path = luigi.Parameter(significant=False)
    rori = luigi.FloatParameter(default=0.52, significant=False)
    compression = luigi.Parameter(default="lzf", significant=False)
    y_tile = luigi.IntParameter(default=100, significant=False)

    def requires(self):
        with open(self.level1_list) as src:
            level1_scenes = [scene.strip() for scene in src.readlines()]

        for scene in level1_scenes:
            kwargs = {
                "level1": scene,
                "model": self.model,
                "vertices": self.vertices,
                "pixel_quality": self.pixel_quality,
                "method": self.method,
                "modtran_exe": self.modtran_exe,
                "outdir": self.outdir,
                "land_sea_path": self.land_sea_path,
                "aerosol_fname": self.aerosol_fname,
                "brdf_path": self.brdf_path,
                "brdf_premodis_path": self.brdf_premodis_path,
                "ozone_path": self.ozone_path,
                "water_vapour_path": self.water_vapour_path,
                "dem_path": self.dem_path,
                "ecmwf_path": self.ecmwf_path,
                "invariant_height_fname": self.invariant_height_fname,
                "dsm_fname": self.dsm_fname,
                "tle_path": self.tle_path,
                "rori": self.rori,
            }
            yield Standard(**kwargs)


if __name__ == "__main__":
    luigi.run()
