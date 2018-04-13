#!/usr/bin/env python

"""MODTRAN drivers
---------------.

"""

import glob
import os
import subprocess
from os.path import dirname, exists
from os.path import join as pjoin
from posixpath import join as ppjoin

import h5py
import numpy as np
import pandas as pd
from scipy.io import FortranFile

from wagl.constants import (
    ALBEDO_FMT,
    POINT_ALBEDO_FMT,
    POINT_FMT,
    Albedos,
    BandType,
    DatasetName,
    GroupName,
    Model,
)
from wagl.constants import AtmosphericCoefficients as AC
from wagl.hdf5 import (
    VLEN_STRING,
    create_external_link,
    read_h5_table,
    write_dataframe,
    write_scalar,
)
from wagl.modtran_profiles import (
    MIDLAT_SUMMER_ALBEDO,
    MIDLAT_SUMMER_TRANSMITTANCE,
    SBT_FORMAT,
    THERMAL_TRANSMITTANCE,
    TROPICAL_ALBEDO,
    TROPICAL_TRANSMITTANCE,
)


def prepare_modtran(acquisitions, coordinate, albedos, basedir, modtran_exe):
    """Prepares the working directory for a MODTRAN execution."""
    data_dir = pjoin(dirname(modtran_exe), "DATA")
    if not exists(data_dir):
        raise OSError("Cannot find MODTRAN")

    point_dir = pjoin(basedir, POINT_FMT.format(p=coordinate))
    for albedo in albedos:
        if albedo == Albedos.ALBEDO_TH:
            band_type = BandType.THERMAL
        else:
            band_type = BandType.REFLECTIVE

        acq = [acq for acq in acquisitions if acq.band_type == band_type][0]

        modtran_work = pjoin(point_dir, ALBEDO_FMT.format(a=albedo.value))

        if not exists(modtran_work):
            os.makedirs(modtran_work)

        out_fname = pjoin(modtran_work, "mod5root.in")
        with open(out_fname, "w") as src:
            src.write(POINT_ALBEDO_FMT.format(p=coordinate, a=albedo.value) + "\n")

        symlink_dir = pjoin(modtran_work, "DATA")
        if exists(symlink_dir):
            os.unlink(symlink_dir)

        os.symlink(data_dir, symlink_dir)

        out_fname = pjoin(modtran_work, acq.spectral_filter_file)
        response = acq.spectral_response(as_list=True)
        with open(out_fname, "wb") as src:
            src.writelines(response)


def _format_tp5(
    acquisitions,
    satellite_solar_angles_fname,
    longitude_latitude_fname,
    ancillary_fname,
    out_fname,
    model,
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(satellite_solar_angles_fname, "r") as sat_sol_fid, h5py.File(
        longitude_latitude_fname, "r"
    ) as lon_lat_fid, h5py.File(ancillary_fname, "r") as anc_fid, h5py.File(
        out_fname, "w"
    ) as fid:
        grp1 = anc_fid[GroupName.ANCILLARY_GROUP.value]
        grp2 = sat_sol_fid[GroupName.SAT_SOL_GROUP.value]
        grp3 = lon_lat_fid[GroupName.LON_LAT_GROUP.value]
        tp5_data, _ = format_tp5(acquisitions, grp1, grp2, grp3, model, fid)

    return tp5_data


def format_tp5(
    acquisitions,
    ancillary_group,
    satellite_solar_group,
    lon_lat_group,
    model,
    out_group,
):
    """Creates str formatted tp5 files for the albedo (0, 1) and
    transmittance (t).
    """
    # angles data
    sat_view = satellite_solar_group[DatasetName.SATELLITE_VIEW.value]
    sat_azi = satellite_solar_group[DatasetName.SATELLITE_AZIMUTH.value]
    longitude = lon_lat_group[DatasetName.LON.value]
    latitude = lon_lat_group[DatasetName.LAT.value]

    # retrieve the averaged ancillary if available
    anc_grp = ancillary_group.get(GroupName.ANCILLARY_AVG_GROUP.value)
    if anc_grp is None:
        anc_grp = ancillary_group

    # ancillary data
    coordinator = ancillary_group[DatasetName.COORDINATOR.value]
    aerosol = anc_grp[DatasetName.AEROSOL.value][()]
    water_vapour = anc_grp[DatasetName.WATER_VAPOUR.value][()]
    ozone = anc_grp[DatasetName.OZONE.value][()]
    elevation = anc_grp[DatasetName.ELEVATION.value][()]

    npoints = coordinator.shape[0]
    view = np.zeros(npoints, dtype="float32")
    azi = np.zeros(npoints, dtype="float32")
    lat = np.zeros(npoints, dtype="float64")
    lon = np.zeros(npoints, dtype="float64")

    for i in range(npoints):
        yidx = coordinator["row_index"][i]
        xidx = coordinator["col_index"][i]
        view[i] = sat_view[yidx, xidx]
        azi[i] = sat_azi[yidx, xidx]
        lat[i] = latitude[yidx, xidx]
        lon[i] = longitude[yidx, xidx]

    view_corrected = 180 - view
    azi_corrected = azi + 180
    rlon = 360 - lon

    # check if in western hemisphere
    idx = rlon >= 360
    rlon[idx] -= 360

    idx = (180 - view_corrected) < 0.1
    view_corrected[idx] = 180
    azi_corrected[idx] = 0

    idx = azi_corrected > 360
    azi_corrected[idx] -= 360

    # get the modtran profiles to use based on the centre latitude
    _, centre_lat = acquisitions[0].gridded_geo_box().centre_lonlat
    if centre_lat < -23.0:
        albedo_profile = MIDLAT_SUMMER_ALBEDO
        trans_profile = MIDLAT_SUMMER_TRANSMITTANCE
    else:
        albedo_profile = TROPICAL_ALBEDO
        trans_profile = TROPICAL_TRANSMITTANCE

    if out_group is None:
        out_group = h5py.File("atmospheric-inputs.h5", "w")

    if GroupName.ATMOSPHERIC_INPUTS_GRP.value not in out_group:
        out_group.create_group(GroupName.ATMOSPHERIC_INPUTS_GRP.value)

    group = out_group[GroupName.ATMOSPHERIC_INPUTS_GRP.value]
    iso_time = acquisitions[0].acquisition_datetime.isoformat()
    group.attrs["acquisition-datetime"] = iso_time

    tp5_data = {}

    # setup the tp5 files required by MODTRAN
    if model == Model.STANDARD or model == Model.NBAR:
        acqs = [a for a in acquisitions if a.band_type == BandType.REFLECTIVE]

        for p in range(npoints):
            for alb in Model.NBAR.albedos:
                input_data = {
                    "water": water_vapour,
                    "ozone": ozone,
                    "filter_function": acqs[0].spectral_filter_file,
                    "visibility": -aerosol,
                    "elevation": elevation,
                    "sat_height": acquisitions[0].altitude / 1000.0,
                    "sat_view": view_corrected[p],
                    "doy": acquisitions[0].julian_day(),
                    "binary": "T",
                }
                if alb == Albedos.ALBEDO_T:
                    input_data["albedo"] = 0.0
                    input_data["sat_view_offset"] = 180.0 - view_corrected[p]
                    data = trans_profile.format(**input_data)
                else:
                    input_data["albedo"] = float(alb.value)
                    input_data["lat"] = lat[p]
                    input_data["lon"] = rlon[p]
                    input_data["time"] = acquisitions[0].decimal_hour()
                    input_data["sat_azimuth"] = azi_corrected[p]
                    data = albedo_profile.format(**input_data)

                tp5_data[(p, alb)] = data

                dname = ppjoin(
                    POINT_FMT.format(p=p),
                    ALBEDO_FMT.format(a=alb.value),
                    DatasetName.TP5.value,
                )
                write_scalar(np.string_(data), dname, group, input_data)

    # create tp5 for sbt if it has been collected
    if ancillary_group.attrs.get("sbt-ancillary"):
        dname = ppjoin(POINT_FMT, DatasetName.ATMOSPHERIC_PROFILE.value)
        acqs = [a for a in acquisitions if a.band_type == BandType.THERMAL]

        for p in range(npoints):
            atmospheric_profile = []
            atmos_profile = read_h5_table(ancillary_group, dname.format(p=p))
            n_layers = atmos_profile.shape[0] + 6
            elevation = atmos_profile.iloc[0]["GeoPotential_Height"]

            for i, row in atmos_profile.iterrows():
                input_data = {
                    "gpheight": row["GeoPotential_Height"],
                    "pressure": row["Pressure"],
                    "airtemp": row["Temperature"],
                    "humidity": row["Relative_Humidity"],
                    "zero": 0.0,
                }
                atmospheric_profile.append(SBT_FORMAT.format(**input_data))

            input_data = {
                "ozone": ozone,
                "filter_function": acqs[0].spectral_filter_file,
                "visibility": -aerosol,
                "gpheight": elevation,
                "n": n_layers,
                "sat_height": acquisitions[0].altitude / 1000.0,
                "sat_view": view_corrected[p],
                "binary": "T",
                "atmospheric_profile": "".join(atmospheric_profile),
            }

            data = THERMAL_TRANSMITTANCE.format(**input_data)
            tp5_data[(p, Albedos.ALBEDO_TH)] = data
            out_dname = ppjoin(
                POINT_FMT.format(p=p),
                ALBEDO_FMT.format(a=Albedos.ALBEDO_TH.value),
                DatasetName.TP5.value,
            )
            write_scalar(np.string_(data), out_dname, group, input_data)

    # attach location info to each point Group
    for p in range(npoints):
        lonlat = (coordinator["longitude"][p], coordinator["latitude"][p])
        group[POINT_FMT.format(p=p)].attrs["lonlat"] = lonlat

    return tp5_data, out_group


def _run_modtran(
    acquisitions,
    modtran_exe,
    basedir,
    point,
    albedos,
    model,
    npoints,
    atmospheric_inputs_fname,
    out_fname,
    compression="lzf",
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(atmospheric_inputs_fname, "r") as atmos_fid, h5py.File(
        out_fname, "w"
    ) as fid:
        atmos_grp = atmos_fid[GroupName.ATMOSPHERIC_INPUTS_GRP.value]
        run_modtran(
            acquisitions,
            atmos_grp,
            model,
            npoints,
            point,
            albedos,
            modtran_exe,
            basedir,
            fid,
            compression,
        )


def run_modtran(
    acquisitions,
    atmospherics_group,
    model,
    npoints,
    point,
    albedos,
    modtran_exe,
    basedir,
    out_group,
    compression,
):
    """Run MODTRAN and return the flux and channel results."""
    lonlat = atmospherics_group[POINT_FMT.format(p=point)].attrs["lonlat"]

    # determine the output group/file
    if out_group is None:
        fid = h5py.File("atmospheric-results.h5", driver="core", backing_store=False)
    else:
        fid = out_group

    # initial attributes
    base_attrs = {
        "Point": point,
        "lonlat": lonlat,
        "datetime": acquisitions[0].acquisition_datetime,
    }

    base_path = ppjoin(
        GroupName.ATMOSPHERIC_RESULTS_GRP.value, POINT_FMT.format(p=point)
    )

    # what atmospheric calculations have been run and how many points
    group_name = GroupName.ATMOSPHERIC_RESULTS_GRP.value
    if group_name not in fid:
        fid.create_group(group_name)

    fid[group_name].attrs["npoints"] = npoints
    applied = model == Model.STANDARD or model == Model.NBAR
    fid[group_name].attrs["nbar_atmospherics"] = applied
    applied = model == Model.STANDARD or model == Model.SBT
    fid[group_name].attrs["sbt_atmospherics"] = applied

    acqs = acquisitions
    for albedo in albedos:
        base_attrs["Albedo"] = albedo.value
        workpath = pjoin(
            basedir, POINT_FMT.format(p=point), ALBEDO_FMT.format(a=albedo.value)
        )
        group_path = ppjoin(base_path, ALBEDO_FMT.format(a=albedo.value))

        subprocess.check_call([modtran_exe], cwd=workpath)
        chn_fname = glob.glob(pjoin(workpath, "*.chn"))[0]

        if albedo == Albedos.ALBEDO_TH:
            acq = [acq for acq in acqs if acq.band_type == BandType.THERMAL][0]
            channel_data = read_modtran_channel(chn_fname, acq, albedo)

            # upward radiation
            attrs = base_attrs.copy()
            dataset_name = DatasetName.UPWARD_RADIATION_CHANNEL.value
            attrs["description"] = "Upward radiation channel output from " "MODTRAN"
            dset_name = ppjoin(group_path, dataset_name)
            write_dataframe(channel_data[0], dset_name, fid, attrs=attrs)

            # downward radiation
            attrs = base_attrs.copy()
            dataset_name = DatasetName.DOWNWARD_RADIATION_CHANNEL.value
            attrs["description"] = "Downward radiation channel output from " "MODTRAN"
            dset_name = ppjoin(group_path, dataset_name)
            write_dataframe(channel_data[1], dset_name, fid, attrs=attrs)
        else:
            acq = [acq for acq in acqs if acq.band_type == BandType.REFLECTIVE][0]
            flux_fname = glob.glob(pjoin(workpath, "*_b.flx"))[0]
            flux_data, altitudes = read_modtran_flux(flux_fname)
            channel_data = read_modtran_channel(chn_fname, acq, albedo)

            # ouput the flux data
            attrs = base_attrs.copy()
            dset_name = ppjoin(group_path, DatasetName.FLUX.value)
            attrs["description"] = "Flux output from MODTRAN"
            write_dataframe(flux_data, dset_name, fid, attrs=attrs)

            # output the altitude data
            attrs = base_attrs.copy()
            attrs["description"] = "Altitudes output from MODTRAN"
            attrs["altitude_levels"] = altitudes.shape[0]
            attrs["units"] = "km"
            dset_name = ppjoin(group_path, DatasetName.ALTITUDES.value)
            write_dataframe(altitudes, dset_name, fid, attrs=attrs)

            # accumulate the solar irradiance
            transmittance = True if albedo == Albedos.ALBEDO_T else False
            response = acq.spectral_response()
            accumulated = calculate_solar_radiation(
                flux_data, response, altitudes.shape[0], transmittance
            )

            attrs = base_attrs.copy()
            dset_name = ppjoin(group_path, DatasetName.SOLAR_IRRADIANCE.value)
            description = "Accumulated solar irradiation for point {} " "and albedo {}."
            attrs["description"] = description.format(point, albedo.value)
            write_dataframe(accumulated, dset_name, fid, compression, attrs=attrs)

            attrs = base_attrs.copy()
            dataset_name = DatasetName.CHANNEL.value
            attrs["description"] = "Channel output from MODTRAN"
            dset_name = ppjoin(group_path, dataset_name)
            write_dataframe(channel_data, dset_name, fid, attrs=attrs)

    # metadata for a given point
    alb_vals = [alb.value for alb in model.albedos]
    fid[base_path].attrs["lonlat"] = lonlat
    fid[base_path].attrs["datetime"] = acqs[0].acquisition_datetime.isoformat()
    fid[base_path].attrs.create("albedos", data=alb_vals, dtype=VLEN_STRING)

    if out_group is None:
        return fid


def _calculate_coefficients(atmosheric_results_fname, out_fname, compression):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(atmosheric_results_fname, "r") as atmos_fid, h5py.File(
        out_fname, "w"
    ) as fid:
        results_group = atmos_fid[GroupName.ATMOSPHERIC_RESULTS_GRP.value]
        calculate_coefficients(results_group, fid, compression)


def calculate_coefficients(atmospheric_results_group, out_group, compression="lzf"):
    """Calculate the atmospheric coefficients from the MODTRAN output
    and used in the BRDF and atmospheric correction.
    Coefficients are computed for each band for each each coordinate
    for each atmospheric coefficient. The atmospheric coefficients can be
    found in `Model.STANDARD.atmos_coefficients`.

    :param atmospheric_results_group:
        The root HDF5 `Group` that contains the atmospheric results
        from each MODTRAN run.

    :param out_group:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver. Otherwise,
        a writeable HDF5 `Group` object.

        The datasets will be formatted to the HDF5 TABLE specification
        and the dataset names will be as follows:

        * DatasetName.NBAR_COEFFICIENTS (if Model.STANDARD or Model.NBAR)
        * DatasetName.SBT_COEFFICIENTS (if Model.STANDARD or Model.SBT)

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """
    nbar_coefficients = pd.DataFrame()
    sbt_coefficients = pd.DataFrame()
    accumulation_albedo_0 = accumulation_albedo_1 = None
    accumulation_albedo_t = None
    channel_data = upward = downward = None

    # Initialise the output group/file
    if out_group is None:
        fid = h5py.File(
            "atmospheric-coefficients.h5", driver="core", backing_store=False
        )
    else:
        fid = out_group

    res = atmospheric_results_group
    npoints = res.attrs["npoints"]
    nbar_atmos = res.attrs["nbar_atmospherics"]
    sbt_atmos = res.attrs["sbt_atmospherics"]

    for point in range(npoints):
        point_grp = res[POINT_FMT.format(p=point)]
        lonlat = point_grp.attrs["lonlat"]
        timestamp = pd.to_datetime(point_grp.attrs["datetime"])
        grp_path = ppjoin(POINT_FMT.format(p=point), ALBEDO_FMT)
        if nbar_atmos:
            dataset_name = DatasetName.SOLAR_IRRADIANCE.value
            albedo_0_path = ppjoin(
                grp_path.format(a=Albedos.ALBEDO_0.value), dataset_name
            )
            albedo_1_path = ppjoin(
                grp_path.format(a=Albedos.ALBEDO_1.value), dataset_name
            )
            albedo_t_path = ppjoin(
                grp_path.format(a=Albedos.ALBEDO_T.value), dataset_name
            )
            channel_path = ppjoin(
                grp_path.format(a=Albedos.ALBEDO_0.value), DatasetName.CHANNEL.value
            )

            accumulation_albedo_0 = read_h5_table(res, albedo_0_path)
            accumulation_albedo_1 = read_h5_table(res, albedo_1_path)
            accumulation_albedo_t = read_h5_table(res, albedo_t_path)
            channel_data = read_h5_table(res, channel_path)
        if sbt_atmos:
            dname = ppjoin(
                grp_path.format(a=Albedos.ALBEDO_TH.value),
                DatasetName.UPWARD_RADIATION_CHANNEL.value,
            )
            upward = read_h5_table(res, dname)
            dname = ppjoin(
                grp_path.format(a=Albedos.ALBEDO_TH.value),
                DatasetName.DOWNWARD_RADIATION_CHANNEL.value,
            )
            downward = read_h5_table(res, dname)

        kwargs = {
            "accumulation_albedo_0": accumulation_albedo_0,
            "accumulation_albedo_1": accumulation_albedo_1,
            "accumulation_albedo_t": accumulation_albedo_t,
            "channel_data": channel_data,
            "upward_radiation": upward,
            "downward_radiation": downward,
        }

        result = coefficients(**kwargs)

        # insert some datetime/geospatial fields
        if result[0] is not None:
            result[0].insert(0, "POINT", point)
            result[0].insert(1, "LONGITUDE", lonlat[0])
            result[0].insert(2, "LATITUDE", lonlat[1])
            result[0].insert(3, "DATETIME", timestamp)
            nbar_coefficients = nbar_coefficients.append(result[0])

        if result[1] is not None:
            result[1].insert(0, "POINT", point)
            result[1].insert(1, "LONGITUDE", lonlat[0])
            result[1].insert(2, "LATITUDE", lonlat[1])
            result[1].insert(3, "DATETIME", pd.to_datetime(timestamp))
            sbt_coefficients = sbt_coefficients.append(result[1])

        # TODO: check if number of records > (some chunksize)
        #       and write that portion of the table to disk
        # TODO: implement an append write_dataframe
        #       which will aid in reducing memory consumption

    nbar_coefficients.reset_index(inplace=True)
    sbt_coefficients.reset_index(inplace=True)

    attrs = {"npoints": npoints}
    description = "Coefficients derived from the VNIR solar irradiation."
    attrs["description"] = description
    dname = DatasetName.NBAR_COEFFICIENTS.value

    if GroupName.COEFFICIENTS_GROUP.value not in fid:
        fid.create_group(GroupName.COEFFICIENTS_GROUP.value)

    group = fid[GroupName.COEFFICIENTS_GROUP.value]
    if nbar_atmos:
        write_dataframe(nbar_coefficients, dname, group, compression, attrs=attrs)

    description = "Coefficients derived from the THERMAL solar irradiation."
    attrs["description"] = description
    dname = DatasetName.SBT_COEFFICIENTS.value

    if sbt_atmos:
        write_dataframe(sbt_coefficients, dname, group, compression, attrs=attrs)

    if out_group is None:
        return fid


def coefficients(
    accumulation_albedo_0=None,
    accumulation_albedo_1=None,
    accumulation_albedo_t=None,
    channel_data=None,
    upward_radiation=None,
    downward_radiation=None,
):
    """Calculate the coefficients for a given point.
    Calculate the atmospheric coefficients from the MODTRAN output
    and used in the BRDF and atmospheric correction.
    Coefficients are computed for each band.
    The atmospheric coefficients can be found in
    `Model.STANDARD.atmos_coefficients`.

    :param accumulation_albedo_0:
        A `pandas.DataFrame` containing the solar accumulated
        irradiance (for albedo 0) and structured as returned by the
        `calculate_solar_radiation` function.
        Only used for NBAR calculations.

    :param accumulation_albedo_1:
        A `pandas.DataFrame` containing the solar accumulated
        irradiance (for albedo 1) and structured as returned by the
        `calculate_solar_radiation` function.
        Only used for NBAR calculations.

    :param accumulation_albedo_t:
        A `pandas.DataFrame` containing the solar accumulated
        irradiance (for albed0 t; transmittance) and structured as
        returned by the `calculate_solar_radiation` function.
        Only used for NBAR calculations.

    :param channel_data:
        A `pandas.DataFrame` containing the channel data for that
        point, and structured as returned by the
        `read_modtran_channel` function.
        Only used for NBAR calculations.

    :param upward_radiation:
        A `pandas.DataFrame` containing the upward radiation data for
        that point, and structured as returned by the
        `read_modtran_channel` function.
        Only used for SBT calculations.

    :param downward_radiation:
        A `pandas.DataFrame` containing the downward radiation data for
        that point, and structured as returned by the
        `read_modtran_channel` function.
        Only used for SBT calculations.

    :return:
        A `tuple` (nbar_coefficients, sbt_coefficients) whereby each
        item is a `pandas.DataFrame` containing the atmospheric
        coefficients for each band.
        If `accumulation_albedo_0` is None, then the first item in
        the returned `tuple` will be None.
        If `upward_radiation` is None, then the second item in the
        returned `tuple` will be None.
    """
    nbar = sbt = None
    if accumulation_albedo_0 is not None:
        diff_0 = accumulation_albedo_0["diffuse"] * 10000000.0
        diff_1 = accumulation_albedo_1["diffuse"] * 10000000.0
        dir_0 = accumulation_albedo_0["direct"] * 10000000.0
        dir_1 = accumulation_albedo_1["direct"] * 10000000.0
        dir_t = accumulation_albedo_t["direct"]
        dir0_top = accumulation_albedo_0["direct_top"] * 10000000.0
        dirt_top = accumulation_albedo_t["direct_top"]
        tv_total = accumulation_albedo_t["transmittance"]
        ts_total = (diff_0 + dir_0) / dir0_top
        ts_dir = dir_0 / dir0_top
        tv_dir = dir_t / dirt_top

        columns = [v.value for v in Model.NBAR.atmos_coefficients]
        nbar = pd.DataFrame(columns=columns, index=channel_data.index)

        nbar[AC.FS.value] = ts_dir / ts_total
        nbar[AC.FV.value] = tv_dir / tv_total
        nbar[AC.A.value] = (diff_0 + dir_0) / np.pi * tv_total
        nbar[AC.B.value] = channel_data["3"] * 10000000
        nbar[AC.S.value] = 1 - (diff_0 + dir_0) / (diff_1 + dir_1)
        nbar[AC.DIR.value] = dir_0
        nbar[AC.DIF.value] = diff_0
        nbar[AC.TS.value] = ts_dir

    if upward_radiation is not None:
        columns = [v.value for v in Model.SBT.atmos_coefficients]
        columns.extend(["TRANSMITTANCE-DOWN"])  # Currently not required
        sbt = pd.DataFrame(columns=columns, index=upward_radiation.index)

        sbt[AC.PATH_UP.value] = upward_radiation["3"] * 10000000
        sbt[AC.TRANSMITTANCE_UP.value] = upward_radiation["14"]
        sbt[AC.PATH_DOWN.value] = downward_radiation["3"] * 10000000
        sbt["TRANSMITTANCE-DOWN"] = downward_radiation["14"]

    return nbar, sbt


def read_spectral_response(fname, as_list=False, spectral_range=None):
    """Read the spectral response function text file used during
    MODTRAN processing.

    :param fname:
        A `str` containing the full file path name, or an opened
        `file` buffer.

    :param as_list:
        A `bool` indicating whether or not to return the spectral
        response data as a list instead of a `pd.DataFrame`.
        Default is `False` which returns a `pd.DataFrame`.

    :param spectral_range:
        A `list` or `generator` of the [start, stop, step] for the
        spectral range to be used in defining the spectral response.
        Default is [2600, 349, -1].

    :return:
        A `pd.DataFrame` containing the spectral response
        function.
    """
    if isinstance(fname, str):
        with open(fname) as src:
            lines = src.readlines()
    else:
        lines = fname.readlines()

    if as_list:
        return lines

    lines = [line.strip().decode("utf-8") for line in lines]

    # find the starting locations of each band description label
    ids = []
    for i, val in enumerate(lines):
        if "B" in val:
            ids.append(i)

    # get the spectral response data up to band n-1
    response = {}
    for i, idx in enumerate(ids[0:-1]):
        data = np.array(
            [l.split("  ") for l in lines[idx + 1 : ids[i + 1]]], dtype="float"
        )
        df = pd.DataFrame(
            {"band_name": lines[idx], "wavelength": data[:, 0], "response": data[:, 1]}
        )
        response[lines[idx]] = df

    # get spectral response data for band n
    idx = ids[-1]
    data = np.array([l.split("  ") for l in lines[idx + 1 :]], dtype="float")
    df = pd.DataFrame(
        {"band_name": lines[idx], "wavelength": data[:, 0], "response": data[:, 1]}
    )
    response[lines[idx]] = df

    if spectral_range is None:
        wavelengths = range(2600, 349, -1)
    else:
        wavelengths = list(spectral_range)

    for band in response:
        base_df = pd.DataFrame(
            {"wavelength": wavelengths, "response": 0.0, "band_name": band},
            index=wavelengths,
        )
        df = response[band]
        base_df.ix[df["wavelength"], "response"] = df["response"].values

        response[band] = base_df

    spectral_response = pd.concat(response, names=["band_name", "wavelength"])
    spectral_response.drop(["band_name", "wavelength"], inplace=True, axis=1)

    return spectral_response


def read_modtran_flux(fname):
    """Read a MODTRAN output `*_b.flx` binary file.

    :param fname:
        A `str` containing the full file pathname of the flux
        data file.

    :return:
        Two `pandas.DataFrame's`. The first contains the spectral flux
        table data, and the second is contains the atmospheric height
        levels in km.
    """
    # define a datatype for the hdr info
    hdr_dtype = np.dtype(
        [
            ("record_length", "int32"),
            ("spectral_unit", "S1"),
            ("relabs", "S1"),
            ("linefeed", "S1"),
            ("mlflx", "int32"),
            ("iv1", "float32"),
            ("band_width", "float32"),
            ("fwhm", "float32"),
            ("ifwhm", "float32"),
        ]
    )

    # datatype for the dataframe containing the flux data
    flux_dtype = np.dtype(
        [
            ("upward_diffuse", "float64"),
            ("downward_diffuse", "float64"),
            ("direct_solar", "float64"),
        ]
    )

    with open(fname, "rb") as src:
        # read the hdr record
        hdr_data = np.fromfile(src, hdr_dtype, count=1)

        # maximum flux levels at a spectral grid point
        levels = hdr_data["mlflx"][0] + 1

        # define a datatype to read a record containing flux data
        dtype = np.dtype(
            [("wavelength", "float64"), ("flux_data", "float64", (levels, 3))]
        )

        # read the rest of the hdr which contains the altitude data
        altitude = np.fromfile(src, dtype="float32", count=levels)

        # read the record length end value
        _ = np.fromfile(src, "int32", count=1)

        # initialise the FORTRAN read
        ffile = FortranFile(src)

        # read data from 2600 down to 350
        flux = {}
        wavelength_steps = range(2600, 349, -1)
        for wv in wavelength_steps:
            data = ffile.read_record(dtype)
            df = pd.DataFrame(np.zeros(levels, dtype=flux_dtype))
            # df['wavelength'] = data['wavelength'][0]
            df["upward_diffuse"] = data["flux_data"].squeeze()[:, 0]
            df["downward_diffuse"] = data["flux_data"].squeeze()[:, 1]
            df["direct_solar"] = data["flux_data"].squeeze()[:, 2]
            flux[wv] = df

    # concatenate into a single table
    flux_data = pd.concat(flux, names=["wavelength", "level"])

    # setup a dataframe for the altitude
    altitude = pd.DataFrame({"altitude": altitude})
    altitude.index.name = "layer"

    return flux_data, altitude


def read_modtran_channel(fname, acquisition, albedo):
    """Read a MODTRAN output `*.chn` ascii file.

    :param fname:
        A `str` containing the full file pathname of the channel
        data file.

    :param acquisition:
        An instance of an acquisition object.

    :param albedo:
        An albedo identifier from either Model.nbar.albedos or
        Model.SBT.albedos

    :return:
        A `pandas.DataFrame` containing the channel data, and index
        by the `band_name`.
    """
    response = acquisition.spectral_response()
    nbands = response.index.get_level_values("band_name").unique().shape[0]
    if albedo == Albedos.ALBEDO_TH:
        upward_radiation = pd.read_csv(
            fname, skiprows=5, header=None, delim_whitespace=True, nrows=nbands
        )
        downward_radiation = pd.read_csv(
            fname,
            skiprows=10 + nbands,
            header=None,
            delim_whitespace=True,
            nrows=nbands,
        )
        upward_radiation["band_name"] = upward_radiation[16]
        downward_radiation["band_name"] = downward_radiation[16]
        upward_radiation.drop(16, inplace=True, axis=1)
        downward_radiation.drop(16, inplace=True, axis=1)
        upward_radiation.set_index("band_name", inplace=True)
        downward_radiation.set_index("band_name", inplace=True)
        upward_radiation.columns = upward_radiation.columns.astype(str)
        downward_radiation.columns = downward_radiation.columns.astype(str)

        return upward_radiation, downward_radiation

    chn_data = pd.read_csv(
        fname, skiprows=5, header=None, nrows=nbands, delim_whitespace=True
    )
    chn_data["band_name"] = chn_data[20]
    chn_data.drop(20, inplace=True, axis=1)
    chn_data.set_index("band_name", inplace=True)
    chn_data.columns = chn_data.columns.astype(str)

    return chn_data


def calculate_solar_radiation(
    flux_data, spectral_response, levels=36, transmittance=False
):
    """Retreive the flux data from the MODTRAN output `*.flx`, and
    calculate the solar radiation.

    The solar radiation will be calculated for each of the bands
    contained within the spectral response dataset.

    :param flux_data:
        A `pandas.DataFrame` structured as if read from the
        `read_modtran_flux` function.

    :param spectral_response:
        A `pandas.DataFrame` containing the spectral response
        and structured as if read from the `read_spectral_response`
        function.

    :param levels:
        The number of atmospheric levels. Default is 36.

    :param transmittance:
        If set to `True`, then calculate the solar radiation in
        transmittance mode. Default is to calculate from albedo.

    :return:
        A `pandas.DataFrame` containing the solar radiation
        accumulation.
    """
    # index location of the top atmospheric level
    idx = levels - 1

    # group via the available bands
    band_name = spectral_response.index.get_level_values("band_name")
    groups = spectral_response.groupby(band_name)

    # output dataframe
    # later on the process can be refined to only evaluate the bands
    # we wish to process
    if transmittance:
        columns = ["diffuse", "direct", "diffuse_top", "direct_top", "transmittance"]
    else:
        columns = ["diffuse", "direct", "direct_top"]
    df = pd.DataFrame(columns=columns, index=groups.groups.keys(), dtype="float64")

    # start wavelength and end wavelength, eg 2600 & 350 respectively
    st_wl = spectral_response.index[0][1]
    ed_wl = spectral_response.index[-1][1]

    # indices for flux at bottom and top of atmosphere layers
    wv_idx = range(st_wl - 1, ed_wl - 1, -1)
    wv_idx2 = [(i, 0) for i in wv_idx]
    wv_idx3 = [(i, idx) for i in wv_idx]

    # loop over each band and get the solar radiation
    for band, grp in groups:
        # downward diffuse at bottom of atmospheric levels
        diffuse_bottom = (
            grp.ix[band, st_wl]["response"] * flux_data.ix[st_wl, "downward_diffuse"][0]
            + grp.ix[band, ed_wl]["response"]
            * flux_data.ix[ed_wl, "downward_diffuse"][0]
        ) / 2

        # direct solar at bottom of atmospheric levels
        direct_bottom = (
            grp.ix[band, st_wl]["response"] * flux_data.ix[st_wl, "direct_solar"][0]
            + grp.ix[band, ed_wl]["response"] * flux_data.ix[ed_wl, "direct_solar"][0]
        ) / 2

        # direct solar at top of atmospheric levels
        direct_top = (
            grp.ix[band, st_wl]["response"] * flux_data.ix[st_wl, "direct_solar"][idx]
            + grp.ix[band, ed_wl]["response"] * flux_data.ix[ed_wl, "direct_solar"][idx]
        ) / 2

        response_sum = (
            grp.ix[band, st_wl]["response"] + grp.ix[band, ed_wl]["response"]
        ) / 2

        # Fuqin's code now loops over each wavelength, in -1 decrements
        # we'll use indices rather than a loop
        response_subs = grp.ix[band].ix[wv_idx]["response"].values
        flux_data_subs = flux_data.ix[wv_idx2]

        response_sum = response_sum + response_subs.sum()

        df.ix[band, "diffuse"] = (
            (flux_data_subs["downward_diffuse"].values * response_subs).sum()
            + diffuse_bottom
        ) / response_sum
        df.ix[band, "direct"] = (
            (flux_data_subs["direct_solar"].values * response_subs).sum()
            + direct_bottom
        ) / response_sum

        # direct solar at top of atmospheric levels
        flux_data_subs = flux_data.ix[wv_idx3]
        df.ix[band, "direct_top"] = (
            (flux_data_subs["direct_solar"].values * response_subs).sum() + direct_top
        ) / response_sum

        if transmittance:
            # downward diffuse at top of atmospheric levels
            diffuse_top = (
                grp.ix[band, st_wl]["response"]
                * flux_data.ix[st_wl, "downward_diffuse"][idx]
                + grp.ix[band, ed_wl]["response"]
                * flux_data.ix[ed_wl, "downward_diffuse"][idx]
            ) / 2

            edo_top = flux_data_subs["downward_diffuse"].values
            df.ix[band, "diffuse_top"] = (
                (edo_top * response_subs).sum() + diffuse_top
            ) / response_sum
            t_result = (df.ix[band, "diffuse"] + df.ix[band, "direct"]) / (
                df.ix[band, "diffuse_top"] + df.ix[band, "direct_top"]
            )
            df.ix[band, "transmittance"] = t_result

    df.sort_index(inplace=True)

    return df


def link_atmospheric_results(input_targets, out_fname, npoints, model):
    """Uses h5py's ExternalLink to combine the atmospheric results into
    a single file.

    :param input_targets:
        A `list` of luigi.LocalTargets.

    :param out_fname:
        A `str` containing the output filename.

    :param npoints:
        An `int` containing the number of points (vertices) used for
        evaluating the atmospheric conditions.

    :param model:
        An Enum given by wagl.constants.Model.

    :return:
        None. Results from each file in `input_targets` are linked
        into the output file.
    """
    base_group_name = GroupName.ATMOSPHERIC_RESULTS_GRP.value
    nbar_atmospherics = False
    sbt_atmospherics = False
    attributes = []
    for fname in input_targets:
        with h5py.File(fname.path, "r") as fid:
            points = list(fid[base_group_name].keys())

            # copy across several attributes on the POINT Group
            # as the linking we do here links direct to a dataset
            # which will create the required parent Groups
            for point in points:
                group = ppjoin(base_group_name, point)
                attributes.append(
                    (
                        point,
                        fid[group].attrs["lonlat"],
                        fid[group].attrs["datetime"],
                        fid[group].attrs["albedos"],
                    )
                )

        for point in points:
            for albedo in model.albedos:
                if albedo == Albedos.ALBEDO_TH:
                    datasets = [
                        DatasetName.UPWARD_RADIATION_CHANNEL.value,
                        DatasetName.DOWNWARD_RADIATION_CHANNEL.value,
                    ]
                    sbt_atmospherics = True
                else:
                    datasets = [
                        DatasetName.FLUX.value,
                        DatasetName.ALTITUDES.value,
                        DatasetName.SOLAR_IRRADIANCE.value,
                        DatasetName.CHANNEL.value,
                    ]
                    nbar_atmospherics = True

                grp_path = ppjoin(
                    base_group_name, point, ALBEDO_FMT.format(a=albedo.value)
                )

                for dset in datasets:
                    dname = ppjoin(grp_path, dset)
                    create_external_link(fname.path, dname, out_fname, dname)

    with h5py.File(out_fname) as fid:
        group = fid[GroupName.ATMOSPHERIC_RESULTS_GRP.value]
        group.attrs["npoints"] = npoints
        group.attrs["nbar_atmospherics"] = nbar_atmospherics
        group.attrs["sbt_atmospherics"] = sbt_atmospherics

        # assign the lonlat attribute for each POINT Group
        for point, lonlat, date_time, albedos in attributes:
            group[point].attrs["lonlat"] = lonlat
            group[point].attrs["datetime"] = date_time
            group[point].attrs.create("albedos", data=albedos, dtype=VLEN_STRING)
