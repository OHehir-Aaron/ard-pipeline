#!/usr/bin/env python

import tempfile
from os.path import join as pjoin
from posixpath import join as ppjoin

import h5py
import structlog

from gaip import constants
from gaip.acquisition import acquisitions
from gaip.ancillary import aggregate_ancillary, collect_ancillary
from gaip.constants import (
    ALBEDO_FMT,
    POINT_ALBEDO_FMT,
    POINT_FMT,
    BandType,
    GroupName,
    Model,
)
from gaip.dsm import get_dsm
from gaip.incident_exiting_angles import (
    exiting_angles,
    incident_angles,
    relative_azimuth_slope,
)
from gaip.interpolation import interpolate
from gaip.longitude_latitude_arrays import create_lon_lat_grids
from gaip.modtran import (
    calculate_coefficients,
    format_tp5,
    prepare_modtran,
    run_modtran,
)
from gaip.reflectance import calculate_reflectance
from gaip.satellite_solar_angles import calculate_angles
from gaip.slope_aspect import slope_aspect_arrays
from gaip.temperature import surface_brightness_temperature
from gaip.terrain_shadow_masks import (
    calculate_cast_shadow,
    combine_shadow_masks,
    self_shadow,
)

LOG = structlog.get_logger("luigi-interface")


def get_buffer(group):
    buf = {"product": 250, "R10m": 700, "R20m": 350, "R60m": 120}
    return buf[group]


def card4l(
    level1,
    model,
    vertices,
    method,
    pixel_quality,
    landsea,
    ecmwf_path,
    tle_path,
    aerosol_fname,
    brdf_path,
    brdf_premodis_path,
    ozone_path,
    water_vapour_path,
    dem_path,
    dsm_fname,
    invariant_fname,
    modtran_exe,
    out_fname,
    rori=0.52,
    compression="lzf",
    y_tile=100,
):
    """CEOS Analysis Ready Data for Land.
    A workflow for producing standardised products that meet the
    CARD4L specification.

    TODO: modtran path, ancillary paths, tle path, compression, ytile
    """
    tp5_fmt = pjoin(POINT_FMT, ALBEDO_FMT, "".join([POINT_ALBEDO_FMT, ".tp5"]))
    nvertices = vertices[0] * vertices[1]

    scene = acquisitions(level1)
    acqs = scene.get_acquisitions()
    satellite = acqs[0].spacecraft_id
    sensor = acqs[0].sensor_id

    # NBAR band id's
    nbar_constants = constants.NBARConstants(satellite, sensor)
    band_ids = nbar_constants.get_nbar_lut()
    nbar_bands = [a.band_num for a in acqs if a.band_num in band_ids]

    # SBT band id's
    band_ids = constants.sbt_bands(satellite, sensor)
    sbt_bands = [a.band_num for a in acqs if a.band_num in band_ids]

    if model == Model.standard or model == Model.sbt:
        sbt_path = ecmwf_path
    else:
        sbt_path = None

    with h5py.File(out_fname, "w") as fid:
        for grn_name in scene.granules:
            if grn_name is None:
                granule_group = fid["/"]
            else:
                granule_group = fid.create_group(grn_name)

            for grp_name in scene.groups:
                log = LOG.bind(
                    scene=scene.label, granule=grn_name, granule_group=grp_name
                )
                group = granule_group.create_group(grp_name)
                acqs = scene.get_acquisitions(granule=grn_name, group=grp_name)

                # longitude and latitude
                log.info("Latitude-Longitude")
                create_lon_lat_grids(
                    acqs[0].gridded_geo_box(),
                    group,
                    compression=compression,
                    y_tile=y_tile,
                )

                # satellite and solar angles
                log.info("Satellite-Solar-Angles")
                calculate_angles(
                    acqs[0],
                    group[GroupName.lon_lat_group.value],
                    group,
                    compression,
                    tle_path,
                    y_tile,
                )

                if model == Model.standard or model == model.nbar:
                    # DEM
                    log.info("DEM-retriveal")
                    get_dsm(
                        acqs[0],
                        dsm_fname,
                        get_buffer(grp_name),
                        group,
                        compression,
                        y_tile,
                    )

                    # slope & aspect
                    log.info("Slope-Aspect")
                    slope_aspect_arrays(
                        acqs[0],
                        group[GroupName.elevation_group.value],
                        get_buffer(grp_name),
                        group,
                        compression,
                        y_tile,
                    )

                    # incident angles
                    log.info("Incident-Angles")
                    incident_angles(
                        group[GroupName.sat_sol_group.value],
                        group[GroupName.slp_asp_group.value],
                        group,
                        compression,
                        y_tile,
                    )

                    # exiting angles
                    log.info("Exiting-Angles")
                    exiting_angles(
                        group[GroupName.sat_sol_group.value],
                        group[GroupName.slp_asp_group.value],
                        group,
                        compression,
                        y_tile,
                    )

                    # relative azimuth slope
                    log.info("Relative-Azimuth-Angles")
                    incident_group_name = GroupName.incident_group.value
                    exiting_group_name = GroupName.exiting_group.value
                    relative_azimuth_slope(
                        group[incident_group_name],
                        group[exiting_group_name],
                        group,
                        compression,
                        y_tile,
                    )

                    # self shadow
                    log.info("Self-Shadow")
                    self_shadow(
                        group[incident_group_name],
                        group[exiting_group_name],
                        group,
                        compression,
                        y_tile,
                    )

                    # cast shadow solar source direction
                    log.info("Cast-Shadow-Solar-Direction")
                    dsm_group_name = GroupName.elevation_group.value
                    calculate_cast_shadow(
                        acqs[0],
                        group[dsm_group_name],
                        group[GroupName.sat_sol_group.value],
                        get_buffer(grp_name),
                        500,
                        500,
                        group,
                        compression,
                        y_tile,
                    )

                    # cast shadow satellite source direction
                    log.info("Cast-Shadow-Satellite-Direction")
                    calculate_cast_shadow(
                        acqs[0],
                        group[dsm_group_name],
                        group[GroupName.sat_sol_group.value],
                        get_buffer(grp_name),
                        500,
                        500,
                        group,
                        compression,
                        y_tile,
                        False,
                    )

                    # combined shadow masks
                    log.info("Combined-Shadow")
                    combine_shadow_masks(
                        group[GroupName.shadow_group.value],
                        group[GroupName.shadow_group.value],
                        group[GroupName.shadow_group.value],
                        group,
                        compression,
                        y_tile,
                    )

            # nbar and sbt ancillary
            LOG.info(
                "Ancillary-Retrieval",
                scene=scene.label,
                granule=grn_name,
                granule_group=None,
            )
            nbar_paths = {
                "aerosol_fname": aerosol_fname,
                "water_vapour_path": water_vapour_path,
                "ozone_path": ozone_path,
                "dem_path": dem_path,
                "brdf_path": brdf_path,
                "brdf_premodis_path": brdf_premodis_path,
            }
            collect_ancillary(
                acqs[0],
                group[GroupName.sat_sol_group.value],
                nbar_paths,
                sbt_path,
                invariant_fname,
                vertices,
                granule_group,
                compression,
            )

        if scene.tiled:
            LOG.info(
                "Aggregate-Ancillary",
                scene=scene.label,
                granule="All Granules",
                granule_group=None,
            )
            granule_groups = [fid[granule] for granule in scene.granules]
            aggregate_ancillary(granule_groups, fid)

        # atmospherics
        for grn_name in scene.granules:
            log = LOG.bind(scene=scene.label, granule=grn_name, granule_group=None)
            log.info("Atmospherics")

            granule_group = fid[scene.get_root(granule=grn_name)]

            # any resolution group is fine
            grp_name = scene.groups[0]
            acqs = scene.get_acquisitions(granule=grn_name, group=grp_name)
            root_path = ppjoin(scene.get_root(granule=grn_name), grp_name)

            # TODO check that the average ancilary group can be parsed to reflectance and other functions
            if scene.tiled:
                ancillary_group = fid[GroupName.ancillary_group.value]
            else:
                pth = GroupName.ancillary_group.value
                ancillary_group = granule_group[pth]

            # satellite/solar angles and lon/lat for a resolution group
            pth = ppjoin(root_path, GroupName.sat_sol_group.value)
            sat_sol_grp = granule_group[pth]
            pth = ppjoin(root_path, GroupName.lon_lat_group.value)
            lon_lat_grp = granule_group[pth]

            # tp5 files
            tp5_data, _ = format_tp5(
                acqs, ancillary_group, sat_sol_grp, lon_lat_grp, model, granule_group
            )

            # atmospheric inputs group
            inputs_grp = granule_group[GroupName.atmospheric_inputs_grp.value]

            # radiative transfer for each point and albedo
            for key in tp5_data:
                point, albedo = key

                log.info("Radiative-Transfer", point=point, albedo=albedo)
                with tempfile.TemporaryDirectory() as tmpdir:
                    prepare_modtran(acqs, point, [albedo], tmpdir, modtran_exe)

                    # tp5 data
                    fname = pjoin(tmpdir, tp5_fmt.format(p=point, a=albedo))
                    with open(fname, "w") as src:
                        src.writelines(tp5_data[key])

                    run_modtran(
                        acqs,
                        inputs_grp,
                        model,
                        nvertices,
                        point,
                        [albedo],
                        modtran_exe,
                        tmpdir,
                        granule_group,
                        compression,
                    )

            # coefficients
            log.info("Coefficients")
            pth = GroupName.atmospheric_results_grp.value
            results_group = granule_group[pth]
            calculate_coefficients(results_group, granule_group, compression)

            # interpolate coefficients
            for grp_name in scene.groups:
                log = LOG.bind(
                    scene=scene.label, granule=grn_name, granule_group=grp_name
                )
                log.info("Interpolation")

                acqs = scene.get_acquisitions(granule=grn_name, group=grp_name)
                group = granule_group[grp_name]
                sat_sol_grp = group[GroupName.sat_sol_group.value]
                coef_grp = granule_group[GroupName.coefficients_group.value]

                for factor in model.factors:
                    if factor in Model.nbar.factors:
                        bands = nbar_bands
                    else:
                        bands = sbt_bands

                    for bn in bands:
                        log.info("Interpolate", band_number=bn, factor=factor)
                        acq = [acq for acq in acqs if acq.band_num == bn][0]
                        interpolate(
                            acq,
                            factor,
                            ancillary_group,
                            sat_sol_grp,
                            coef_grp,
                            group,
                            compression,
                            y_tile,
                            method,
                        )

                # standardised products
                band_acqs = []
                if model == Model.standard or model == model.nbar:
                    band_acqs.extend([a for a in acqs if a.band_num in nbar_bands])

                if model == Model.standard or model == model.sbt:
                    band_acqs.extend([a for a in acqs if a.band_num in sbt_bands])

                for acq in band_acqs:
                    interp_grp = group[GroupName.interp_group.value]
                    slp_asp_grp = group[GroupName.slp_asp_group.value]
                    rel_slp_asp = group[GroupName.rel_slp_group.value]
                    incident_grp = group[GroupName.incident_group.value]
                    exiting_grp = group[GroupName.exiting_group.value]
                    shadow_grp = group[GroupName.shadow_group.value]

                    if acq.band_type == BandType.Thermal:
                        log.info("SBT", band_number=acq.band_num)
                        surface_brightness_temperature(
                            acq, interp_grp, group, compression, y_tile
                        )
                    else:
                        log.info("Surface-Reflectance", band_number=acq.band_num)
                        calculate_reflectance(
                            acq,
                            interp_grp,
                            sat_sol_grp,
                            slp_asp_grp,
                            rel_slp_asp,
                            incident_grp,
                            exiting_grp,
                            shadow_grp,
                            ancillary_group,
                            rori,
                            group,
                            compression,
                            y_tile,
                        )
