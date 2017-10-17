#!/usr/bin/env python
"""Multifile workflow for producing NBAR and SBT
---------------------------------------------.

This workflow is geared around a Multiple Independent File workflow, thus
allowing a form a parallelism. HDF5 Linking via a post task then allows
the workflow to appear as if the IO is through a single file.

The multifile workflow approach does allow more freedom of control in
accessing individual components of the entire workflow, and easier for
a user to rapidly test new features.

This workflow can also pick-up exactly where it left off, if the files
generated persist on disk.
However, this method could flood the scheduler if thousands of scenes
are submitted at once in a single call.

Workflow settings can be configured in `luigi.cfg` file.
"""
# pylint: disable=missing-docstring,no-init,too-many-function-args
# pylint: disable=too-many-locals
# pylint: disable=protected-access

import logging
import traceback
from os.path import basename, dirname
from os.path import join as pjoin

import luigi
from luigi.local_target import LocalFileSystem
from luigi.util import inherits, requires
from structlog import wrap_logger
from structlog.processors import JSONRenderer

from gaip.acquisition import acquisitions
from gaip.ancillary import _aggregate_ancillary, _collect_ancillary
from gaip.constants import (
    ALBEDO_FMT,
    POINT_ALBEDO_FMT,
    POINT_FMT,
    BandType,
    Method,
    Model,
)
from gaip.dsm import _get_dsm
from gaip.incident_exiting_angles import (
    _incident_exiting_angles,
    _relative_azimuth_slope,
)
from gaip.interpolation import _interpolate, link_interpolated_data
from gaip.longitude_latitude_arrays import _create_lon_lat_grids
from gaip.modtran import (
    _calculate_coefficients,
    _format_tp5,
    _run_modtran,
    link_atmospheric_results,
    prepare_modtran,
)
from gaip.pq import can_pq, run_pq
from gaip.reflectance import _calculate_reflectance, link_standard_data
from gaip.satellite_solar_angles import _calculate_angles
from gaip.slope_aspect import _slope_aspect_arrays
from gaip.temperature import _surface_brightness_temperature
from gaip.terrain_shadow_masks import (
    _calculate_cast_shadow,
    _combine_shadow,
    _self_shadow,
)

ERROR_LOGGER = wrap_logger(
    logging.getLogger("gaip-error"), processors=[JSONRenderer(indent=1, sort_keys=True)]
)


def get_buffer(group):
    buf = {"product": 250, "R10m": 700, "R20m": 350, "R60m": 120}
    return buf[group]


@luigi.Task.event_handler(luigi.Event.FAILURE)
def on_failure(task, exception):
    """Capture any Task Failure here."""
    ERROR_LOGGER.error(
        task=task.get_task_family(),
        params=task.to_str_params(),
        scene=task.level1,
        exception=exception.__str__(),
        traceback=traceback.format_exc().splitlines(),
    )


class WorkRoot(luigi.Task):
    """Create the work root directory space, and sub directories that
    could compete later in a race condition of creation.
    """

    level1 = luigi.Parameter()
    work_root = luigi.Parameter(significant=False)
    reflectance_dir = "_standardised"
    shadow_dir = "_shadow"
    interpolation_dir = "_interpolation"

    def output(self):
        out_dirs = [self.reflectance_dir, self.shadow_dir, self.interpolation_dir]
        container = acquisitions(self.level1)
        for granule in container.granules:
            for group in container.groups:
                pth = container.get_root(self.work_root, group, granule)
                for out_dir in out_dirs:
                    yield luigi.LocalTarget(pjoin(pth, out_dir))

    def run(self):
        local_fs = LocalFileSystem()
        for target in self.output():
            local_fs.mkdir(target.path)


class CalculateLonLatGrids(luigi.Task):
    """Calculates the longitude and latitude grids."""

    level1 = luigi.Parameter()
    work_root = luigi.Parameter(significant=False)
    granule = luigi.Parameter(default=None)
    group = luigi.Parameter()
    compression = luigi.Parameter(default="lzf", significant=False)
    y_tile = luigi.IntParameter(default=100, significant=False)

    def requires(self):
        return WorkRoot(self.level1, self.work_root)

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "longitude-latitude.h5"))

    def run(self):
        acq = acquisitions(self.level1).get_acquisitions(self.group, self.granule)[0]

        with self.output().temporary_path() as out_fname:
            _create_lon_lat_grids(
                acq.gridded_geo_box(), out_fname, self.compression, y_tile=self.y_tile
            )


@inherits(CalculateLonLatGrids)
class CalculateSatelliteAndSolarGrids(luigi.Task):
    """Calculate the satellite and solar grids."""

    tle_path = luigi.Parameter(significant=False)

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.group]
        return CalculateLonLatGrids(*args)

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "satellite-solar.h5"))

    def run(self):
        acqs = acquisitions(self.level1).get_acquisitions(self.group, self.granule)

        with self.output().temporary_path() as out_fname:
            _calculate_angles(
                acqs[0],
                self.input().path,
                out_fname,
                self.compression,
                self.tle_path,
                self.y_tile,
            )


class AncillaryData(luigi.Task):
    """Get all ancillary data."""

    level1 = luigi.Parameter()
    work_root = luigi.Parameter(significant=False)
    granule = luigi.Parameter(default=None)
    vertices = luigi.TupleParameter()
    model = luigi.EnumParameter(enum=Model)
    aerosol_fname = luigi.Parameter(significant=False)
    brdf_path = luigi.Parameter(significant=False)
    brdf_premodis_path = luigi.Parameter(significant=False)
    ozone_path = luigi.Parameter(significant=False)
    water_vapour_path = luigi.Parameter(significant=False)
    dem_path = luigi.Parameter(significant=False)
    ecmwf_path = luigi.Parameter(significant=False)
    invariant_height_fname = luigi.Parameter(significant=False)
    compression = luigi.Parameter(default="lzf", significant=False)

    def requires(self):
        group = acquisitions(self.level1).groups[0]
        args = [self.level1, self.work_root, self.granule, group]
        return CalculateSatelliteAndSolarGrids(*args)

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, granule=self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "ancillary.h5"))

    def run(self):
        container = acquisitions(self.level1)
        acq = container.get_acquisitions(granule=self.granule)[0]
        sbt_path = None

        nbar_paths = {
            "aerosol_fname": self.aerosol_fname,
            "water_vapour_path": self.water_vapour_path,
            "ozone_path": self.ozone_path,
            "dem_path": self.dem_path,
            "brdf_path": self.brdf_path,
            "brdf_premodis_path": self.brdf_premodis_path,
        }

        if self.model == Model.standard or self.model == Model.sbt:
            sbt_path = self.ecmwf_path

        with self.output().temporary_path() as out_fname:
            _collect_ancillary(
                acq,
                self.input().path,
                nbar_paths,
                sbt_path,
                self.invariant_height_fname,
                self.vertices,
                out_fname,
                self.compression,
            )


class WriteTp5(luigi.Task):
    """Output the `tp5` formatted files."""

    level1 = luigi.Parameter()
    work_root = luigi.Parameter(significant=False)
    granule = luigi.Parameter(default=None)
    vertices = luigi.TupleParameter()
    model = luigi.EnumParameter(enum=Model)
    base_dir = luigi.Parameter(default="_atmospherics", significant=False)
    compression = luigi.Parameter(default="lzf", significant=False)

    def requires(self):
        # for consistancy, we'll wait for dependencies on all granules and
        # groups of acquisitions
        # current method requires to compute an average from all granules
        # if the scene is tiled
        container = acquisitions(self.level1)
        tasks = {}

        for granule in container.granules:
            args1 = [self.level1, self.work_root, granule, self.vertices, self.model]
            tasks[(granule, "ancillary")] = AncillaryData(*args1)
            for group in container.groups:
                args2 = [self.level1, self.work_root, granule, group]
                tsks = {
                    "sat_sol": CalculateSatelliteAndSolarGrids(*args2),
                    "lon_lat": CalculateLonLatGrids(*args2),
                }
                tasks[(granule, group)] = tsks

        return tasks

    def output(self):
        container = acquisitions(self.level1)
        out_path = container.get_root(self.work_root, granule=self.granule)
        return luigi.LocalTarget(pjoin(out_path, "atmospheric-inputs.h5"))

    def run(self):
        container = acquisitions(self.level1)
        # as we have an all granules groups dependency, it doesn't matter which
        # group, so just get the first and use it to retrieve the angles
        group = container.groups[0]
        acqs = container.get_acquisitions(group, granule=self.granule)

        # input data files, and the output format
        inputs = self.input()
        output_fmt = pjoin(POINT_FMT, ALBEDO_FMT, "".join([POINT_ALBEDO_FMT, ".tp5"]))

        # all ancillary filenames from each granule
        fnames = [inputs[key].path for key in inputs if "ancillary" in key]

        if container.tiled:
            # aggregate the necessary ancillary data
            ancillary_fname = inputs[(self.granule, "ancillary")].path
            _aggregate_ancillary(fnames, ancillary_fname)
        else:
            ancillary_fname = fnames[0]

        sat_sol_fname = inputs[(self.granule, group)]["sat_sol"].path
        lon_lat_fname = inputs[(self.granule, group)]["lon_lat"].path

        with self.output().temporary_path() as out_fname:
            tp5_data = _format_tp5(
                acqs,
                sat_sol_fname,
                lon_lat_fname,
                ancillary_fname,
                out_fname,
                self.model,
            )

            # keep this as an indented block, that way the target will remain
            # atomic and be moved upon closing
            for key in tp5_data:
                point, albedo = key
                tp5_fname = output_fmt.format(p=point, a=albedo)
                target = pjoin(dirname(out_fname), self.base_dir, tp5_fname)
                with luigi.LocalTarget(target).open("w") as src:
                    src.writelines(tp5_data[key])


@requires(WriteTp5)
class AtmosphericsCase(luigi.Task):
    """Run MODTRAN for a specific point (vertex) and albedo.
    This task is parameterised this wat to allow parallel instances
    of MODTRAN to run.
    """

    point = luigi.Parameter()
    albedos = luigi.ListParameter()
    exe = luigi.Parameter(significant=False)

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, granule=self.granule
        )
        albedos = "-".join(self.albedos)
        out_fname = "".join([POINT_ALBEDO_FMT.format(p=self.point, a=albedos), ".h5"])
        return luigi.LocalTarget(pjoin(out_path, self.base_dir, out_fname))

    def run(self):
        container = acquisitions(self.level1)
        out_path = container.get_root(self.work_root, granule=self.granule)
        acqs = container.get_acquisitions(granule=self.granule)
        atmospheric_inputs_fname = self.input().path
        base_dir = pjoin(out_path, self.base_dir)

        prepare_modtran(acqs, self.point, self.albedos, base_dir, self.exe)

        with self.output().temporary_path() as out_fname:
            nvertices = self.vertices[0] * self.vertices[1]
            _run_modtran(
                acqs,
                self.exe,
                base_dir,
                self.point,
                self.albedos,
                self.model,
                nvertices,
                atmospheric_inputs_fname,
                out_fname,
                self.compression,
            )


@inherits(WriteTp5)
class Atmospherics(luigi.Task):
    """Kicks off MODTRAN calculations for all points and albedos."""

    model = luigi.EnumParameter(enum=Model)
    separate = luigi.BoolParameter()

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.vertices]
        for point in range(self.vertices[0] * self.vertices[1]):
            kwargs = {"point": point, "model": self.model}
            if self.separate:
                for albedo in self.model.albedos:
                    kwargs["albedos"] = [albedo]
                    yield AtmosphericsCase(*args, **kwargs)
            else:
                kwargs["albedos"] = self.model.albedos
                yield AtmosphericsCase(*args, **kwargs)

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, granule=self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "atmospheric-results.h5"))

    def run(self):
        nvertices = self.vertices[0] * self.vertices[1]
        with self.output().temporary_path() as out_fname:
            link_atmospheric_results(self.input(), out_fname, nvertices, self.model)


@requires(Atmospherics)
class CalculateCoefficients(luigi.Task):
    """Calculate the atmospheric parameters needed by BRDF and atmospheric
    correction model.
    """

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, granule=self.granule
        )
        out_fname = pjoin(out_path, "coefficients.h5")
        return luigi.LocalTarget(out_fname)

    def run(self):
        with self.output().temporary_path() as out_fname:
            _calculate_coefficients(self.input().path, out_fname, self.compression)


@inherits(CalculateLonLatGrids)
class InterpolateCoefficient(luigi.Task):
    """Runs the interpolation function for a given band."""

    vertices = luigi.TupleParameter()
    band_id = luigi.Parameter()
    factor = luigi.Parameter()
    base_dir = luigi.Parameter(default="_interpolation", significant=False)
    model = luigi.EnumParameter(enum=Model)
    method = luigi.EnumParameter(enum=Method, default=Method.shear)

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.vertices]
        return {
            "coef": CalculateCoefficients(*args, model=self.model),
            "satsol": self.clone(CalculateSatelliteAndSolarGrids),
            "ancillary": AncillaryData(*args, model=self.model),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        out_fname = f"{self.factor}-band-{self.band_id}.h5"
        return luigi.LocalTarget(pjoin(out_path, self.base_dir, out_fname))

    def run(self):
        acqs = acquisitions(self.level1).get_acquisitions(self.group, self.granule)
        sat_sol_angles_fname = self.input()["satsol"].path
        coefficients_fname = self.input()["coef"].path
        ancillary_fname = self.input()["ancillary"].path

        acq = [acq for acq in acqs if acq.band_id == self.band_id][0]

        with self.output().temporary_path() as out_fname:
            _interpolate(
                acq,
                self.factor,
                sat_sol_angles_fname,
                coefficients_fname,
                ancillary_fname,
                out_fname,
                self.compression,
                self.y_tile,
                self.method,
            )


@inherits(CalculateLonLatGrids)
class InterpolateCoefficients(luigi.Task):
    """Issues InterpolateCoefficient tasks.
    This acts as a helper task, and links the results from each
    InterpolateCoefficient task single HDF5 file.
    """

    vertices = luigi.TupleParameter()
    model = luigi.EnumParameter(enum=Model)
    method = luigi.EnumParameter(enum=Method, default=Method.shear)

    def requires(self):
        container = acquisitions(self.level1)
        acqs = container.get_acquisitions(group=self.group, granule=self.granule)

        # NBAR & SBT acquisitions
        nbar_acqs = [a for a in acqs if a.band_type == BandType.Reflective]
        sbt_acqs = [a for a in acqs if a.band_type == BandType.Thermal]

        tasks = {}
        for factor in self.model.factors:
            if factor in Model.nbar.factors:
                band_acqs = nbar_acqs
            else:
                band_acqs = sbt_acqs

            for acq in band_acqs:
                key = (acq.band_id, factor)
                kwargs = {
                    "level1": self.level1,
                    "work_root": self.work_root,
                    "granule": self.granule,
                    "group": self.group,
                    "band_id": acq.band_id,
                    "factor": factor,
                    "model": self.model,
                    "vertices": self.vertices,
                    "method": self.method,
                }
                tasks[key] = InterpolateCoefficient(**kwargs)
        return tasks

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        out_fname = pjoin(out_path, "interpolated-coefficients.h5")
        return luigi.LocalTarget(out_fname)

    def run(self):
        fnames = {}
        for key, value in self.input().items():
            fnames[key] = value.path

        with self.output().temporary_path() as out_fname:
            link_interpolated_data(fnames, out_fname)


@inherits(CalculateLonLatGrids)
class DEMExctraction(luigi.Task):
    """Extract the DEM covering the acquisition extents plus an
    arbitrary buffer. The subset is then smoothed with a gaussian
    filter.
    """

    dsm_fname = luigi.Parameter(default="dsm.tif", significant=False)

    def requires(self):
        return WorkRoot(self.level1, self.work_root)

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "dsm-subset.h5"))

    def run(self):
        acqs = acquisitions(self.level1).get_acquisitions(self.group, self.granule)
        margins = get_buffer(self.group)

        with self.output().temporary_path() as out_fname:
            _get_dsm(
                acqs[0],
                self.dsm_fname,
                margins,
                out_fname,
                self.compression,
                self.y_tile,
            )


@requires(DEMExctraction)
class SlopeAndAspect(luigi.Task):
    """Compute the slope and aspect images."""

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "slope-aspect.h5"))

    def run(self):
        acqs = acquisitions(self.level1).get_acquisitions(self.group, self.granule)
        dsm_fname = self.input().path
        margins = get_buffer(self.group)

        with self.output().temporary_path() as out_fname:
            _slope_aspect_arrays(
                acqs[0], dsm_fname, margins, out_fname, self.compression, self.y_tile
            )


@inherits(CalculateLonLatGrids)
class IncidentAngles(luigi.Task):
    """Compute the incident angles."""

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.group]
        return {
            "sat_sol": self.clone(CalculateSatelliteAndSolarGrids),
            "slp_asp": SlopeAndAspect(*args),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "incident-angles.h5"))

    def run(self):
        # input filenames
        sat_sol_fname = self.input()["sat_sol"].path
        slope_aspect_fname = self.input()["slp_asp"].path

        with self.output().temporary_path() as out_fname:
            _incident_exiting_angles(
                sat_sol_fname,
                slope_aspect_fname,
                out_fname,
                self.compression,
                self.y_tile,
            )


@inherits(IncidentAngles)
class ExitingAngles(luigi.Task):
    """Compute the exiting angles."""

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.group]
        return {
            "sat_sol": self.clone(CalculateSatelliteAndSolarGrids),
            "slp_asp": SlopeAndAspect(*args),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "exiting-angles.h5"))

    def run(self):
        # input filenames
        sat_sol_fname = self.input()["sat_sol"].path
        slope_aspect_fname = self.input()["slp_asp"].path

        with self.output().temporary_path() as out_fname:
            _incident_exiting_angles(
                sat_sol_fname,
                slope_aspect_fname,
                out_fname,
                self.compression,
                self.y_tile,
                False,
            )


@inherits(IncidentAngles)
class RelativeAzimuthSlope(luigi.Task):
    """Compute the relative azimuth angle on the slope surface."""

    def requires(self):
        return {
            "incident": self.clone(IncidentAngles),
            "exiting": self.clone(ExitingAngles),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "relative-slope.h5"))

    def run(self):
        # input filenames
        incident_fname = self.input()["incident"].path
        exiting_fname = self.input()["exiting"].path

        with self.output().temporary_path() as out_fname:
            _relative_azimuth_slope(
                incident_fname, exiting_fname, out_fname, self.compression, self.y_tile
            )


@inherits(IncidentAngles)
class SelfShadow(luigi.Task):
    """Calculate the self shadow mask."""

    base_dir = luigi.Parameter(default="_shadow", significant=False)

    def requires(self):
        return {
            "incident": self.clone(IncidentAngles),
            "exiting": self.clone(ExitingAngles),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        out_fname = pjoin(out_path, self.base_dir, "self-shadow.h5")
        return luigi.LocalTarget(out_fname)

    def run(self):
        # input filenames
        incident_fname = self.input()["incident"].path
        exiting_fname = self.input()["exiting"].path

        with self.output().temporary_path() as out_fname:
            _self_shadow(
                incident_fname, exiting_fname, out_fname, self.compression, self.y_tile
            )


@inherits(SelfShadow)
class CalculateCastShadowSun(luigi.Task):
    """Calculates the Cast shadow mask in the direction back to the
    sun.
    """

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.group]
        return {
            "sat_sol": self.clone(CalculateSatelliteAndSolarGrids),
            "dsm": DEMExctraction(*args),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        out_fname = pjoin(out_path, self.base_dir, "cast-shadow-sun.h5")
        return luigi.LocalTarget(out_fname)

    def run(self):
        acqs = acquisitions(self.level1).get_acquisitions(self.group, self.granule)

        # input filenames
        dsm_fname = self.input()["dsm"].path
        sat_sol_fname = self.input()["sat_sol"].path

        # TODO: convert to a func of distance and resolution
        margins = get_buffer(self.group)
        window_height = 500
        window_width = 500

        with self.output().temporary_path() as out_fname:
            _calculate_cast_shadow(
                acqs[0],
                dsm_fname,
                margins,
                window_height,
                window_width,
                sat_sol_fname,
                out_fname,
                self.compression,
                self.y_tile,
            )


@inherits(SelfShadow)
class CalculateCastShadowSatellite(luigi.Task):
    """Calculates the Cast shadow mask in the direction back to the
    sun.
    """

    def requires(self):
        args = [self.level1, self.work_root, self.granule, self.group]
        return {
            "sat_sol": self.clone(CalculateSatelliteAndSolarGrids),
            "dsm": DEMExctraction(*args),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        out_fname = pjoin(out_path, self.base_dir, "cast-shadow-satellite.h5")
        return luigi.LocalTarget(out_fname)

    def run(self):
        acqs = acquisitions(self.level1).get_acquisitions(self.group, self.granule)

        # input filenames
        dsm_fname = self.input()["dsm"].path
        sat_sol_fname = self.input()["sat_sol"].path

        # TODO: convert to a func of distance and resolution
        margins = get_buffer(self.group)
        window_height = 500
        window_width = 500

        with self.output().temporary_path() as out_fname:
            _calculate_cast_shadow(
                acqs[0],
                dsm_fname,
                margins,
                window_height,
                window_width,
                sat_sol_fname,
                out_fname,
                self.compression,
                self.y_tile,
                False,
            )


@inherits(IncidentAngles)
class CalculateShadowMasks(luigi.Task):
    """Issues self and cast shadow tasks for two direction sources;
    the sun and the satellite. Acts as a helper task,
    but combines the results into a single file.
    """

    def requires(self):
        return {
            "sun": self.clone(CalculateCastShadowSun),
            "sat": self.clone(CalculateCastShadowSatellite),
            "self": self.clone(SelfShadow),
        }

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "shadow-masks.h5"))

    def run(self):
        with self.output().temporary_path() as out_fname:
            inputs = self.input()
            _combine_shadow(
                inputs["self"].path,
                inputs["sun"].path,
                inputs["sat"].path,
                out_fname,
                self.compression,
                self.y_tile,
            )


@inherits(InterpolateCoefficients)
class SurfaceReflectance(luigi.Task):
    """Run the terrain correction over a given band."""

    band_id = luigi.Parameter()
    rori = luigi.FloatParameter(default=0.52, significant=False)
    base_dir = luigi.Parameter(default="_standardised", significant=False)

    def requires(self):
        reqs = {
            "interpolation": self.clone(InterpolateCoefficients),
            "ancillary": self.clone(AncillaryData),
            "rel_slope": self.clone(RelativeAzimuthSlope),
            "shadow": self.clone(CalculateShadowMasks),
            "slp_asp": self.clone(SlopeAndAspect),
            "incident": self.clone(IncidentAngles),
            "exiting": self.clone(ExitingAngles),
            "sat_sol": self.clone(CalculateSatelliteAndSolarGrids),
        }

        return reqs

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        fname = f"reflectance-{self.band_id}.h5"
        return luigi.LocalTarget(pjoin(out_path, self.base_dir, fname))

    def run(self):
        container = acquisitions(self.level1)
        acqs = container.get_acquisitions(self.group, self.granule)

        # inputs
        inputs = self.input()
        interpolation_fname = inputs["interpolation"].path
        slp_asp_fname = inputs["slp_asp"].path
        incident_fname = inputs["incident"].path
        exiting_fname = inputs["exiting"].path
        relative_slope_fname = inputs["rel_slope"].path
        shadow_fname = inputs["shadow"].path
        sat_sol_fname = inputs["sat_sol"].path
        ancillary_fname = inputs["ancillary"].path

        # get the acquisition we wish to process
        acq = [acq for acq in acqs if acq.band_id == self.band_id][0]

        with self.output().temporary_path() as out_fname:
            _calculate_reflectance(
                acq,
                interpolation_fname,
                sat_sol_fname,
                slp_asp_fname,
                relative_slope_fname,
                incident_fname,
                exiting_fname,
                shadow_fname,
                ancillary_fname,
                self.rori,
                out_fname,
                self.compression,
                self.y_tile,
            )


@inherits(SurfaceReflectance)
class SurfaceTemperature(luigi.Task):
    """Calculates surface brightness temperature for a given band."""

    def requires(self):
        reqs = {
            "interpolation": self.clone(InterpolateCoefficients),
            "ancillary": self.clone(AncillaryData),
        }
        return reqs

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        fname = f"temperature-{self.band_id}.h5"
        return luigi.LocalTarget(pjoin(out_path, self.base_dir, fname))

    def run(self):
        container = acquisitions(self.level1)
        acqs = container.get_acquisitions(self.group, self.granule)
        acq = [acq for acq in acqs if acq.band_id == self.band_id][0]

        with self.output().temporary_path() as out_fname:
            interpolation_fname = self.input()["interpolation"].path
            ancillary_fname = self.input()["ancillary"].path
            _surface_brightness_temperature(
                acq,
                interpolation_fname,
                ancillary_fname,
                out_fname,
                self.compression,
                self.y_tile,
            )


@inherits(InterpolateCoefficients)
class DataStandardisation(luigi.Task):
    """Issues standardisation (analysis ready) tasks for both
    SurfaceReflectance and SurfaceTemperature.
    """

    land_sea_path = luigi.Parameter()
    pixel_quality = luigi.BoolParameter()

    def requires(self):
        band_acqs = []
        container = acquisitions(self.level1)
        acqs = container.get_acquisitions(group=self.group, granule=self.granule)

        # NBAR acquisitions
        if self.model == Model.standard or self.model == Model.nbar:
            band_acqs.extend([a for a in acqs if a.band_type == BandType.Reflective])

        # SBT acquisitions
        if self.model == Model.standard or self.model == Model.sbt:
            band_acqs.extend([a for a in acqs if a.band_type == BandType.Thermal])

        tasks = []
        for acq in band_acqs:
            kwargs = {
                "level1": self.level1,
                "work_root": self.work_root,
                "granule": self.granule,
                "group": self.group,
                "band_id": acq.band_id,
                "model": self.model,
                "vertices": self.vertices,
                "method": self.method,
            }
            if acq.band_type == BandType.Thermal:
                tasks.append(SurfaceTemperature(**kwargs))
            else:
                tasks.append(SurfaceReflectance(**kwargs))

        return tasks

    def output(self):
        out_path = acquisitions(self.level1).get_root(
            self.work_root, self.group, self.granule
        )
        return luigi.LocalTarget(pjoin(out_path, "standard-products.h5"))

    def run(self):
        with self.output().temporary_path() as out_fname:
            fnames = [target.path for target in self.input()]
            link_standard_data(fnames, out_fname, self.model)
            sbt_only = self.model == Model.sbt
            if self.pixel_quality and can_pq(self.level1) and not sbt_only:
                run_pq(self.level1, out_fname, self.land_sea_path, self.compression)


class ARD(luigi.WrapperTask):
    """Kicks off ARD tasks for each level1 entry."""

    level1_list = luigi.Parameter()
    outdir = luigi.Parameter()
    model = luigi.EnumParameter(enum=Model)
    vertices = luigi.TupleParameter(default=(5, 5))
    pixel_quality = luigi.BoolParameter()
    method = luigi.EnumParameter(enum=Method, default=Method.shear)

    def requires(self):
        with open(self.level1_list) as src:
            level1_scenes = [scene.strip() for scene in src.readlines()]

        for scene in level1_scenes:
            work_name = f"{basename(scene)}.gaip"
            work_root = pjoin(self.outdir, work_name)
            container = acquisitions(scene)
            for granule in container.granules:
                for group in container.groups:
                    kwargs = {
                        "level1": scene,
                        "work_root": work_root,
                        "granule": granule,
                        "group": group,
                        "model": self.model,
                        "vertices": self.vertices,
                        "pixel_quality": self.pixel_quality,
                        "method": self.method,
                    }
                    yield DataStandardisation(**kwargs)


class CallTask(luigi.WrapperTask):
    """An entry point for calling most tasks defined in the above
    workflow. Useful for submitting a list of scenes to process
    a given task that could be the entire workflow, or only to
    the desired task.
    """

    level1_list = luigi.Parameter()
    outdir = luigi.Parameter()
    task = luigi.TaskParameter()

    def requires(self):
        with open(self.level1_list) as src:
            level1_scenes = [scene.strip() for scene in src.readlines()]

        for scene in level1_scenes:
            work_name = f"{basename(scene)}.gaip"
            work_root = pjoin(self.outdir, work_name)
            container = acquisitions(scene)
            for granule in container.granules:
                if "group" in self.task.get_param_names():
                    for group in container.groups:
                        yield self.task(scene, work_root, granule, group)
                else:
                    yield self.task(scene, work_root, granule)


if __name__ == "__main__":
    luigi.run()
