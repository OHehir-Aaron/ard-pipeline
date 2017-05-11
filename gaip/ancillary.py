#!/usr/bin/env python

"""Ancillary dataset retrieval and storage."""

import datetime
import glob
import logging
from os.path import basename, splitext
from os.path import join as pjoin
from posixpath import join as ppjoin

import h5py
import numpy as np
import pandas as pd
import rasterio
from geopandas import GeoSeries
from shapely import wkt
from shapely.geometry import Point, Polygon

from gaip.brdf import get_brdf_data
from gaip.calculate_angles import create_vertices
from gaip.constants import POINT_FMT, DatasetName
from gaip.data import get_pixel
from gaip.hdf5 import (
    attach_attributes,
    attach_table_attributes,
    dataset_compression_kwargs,
    read_table,
    write_dataframe,
    write_scalar,
)
from gaip.metadata import extract_ancillary_metadata, read_meatadata_tags

log = logging.getLogger()


ECWMF_LEVELS = [
    1,
    2,
    3,
    5,
    7,
    10,
    20,
    30,
    50,
    70,
    100,
    125,
    150,
    175,
    200,
    225,
    250,
    300,
    350,
    400,
    450,
    500,
    550,
    600,
    650,
    700,
    750,
    775,
    800,
    825,
    850,
    875,
    900,
    925,
    950,
    975,
    1000,
]


def get_4d_idx(day):
    """A small utility function for indexing into a 4D dataset
    represented as a 3D dataset.
    [month, level, y, x], where level contains 37 levels, and day
    contains 28, 29, 30 or 31 days.
    """
    start = 1 + 37 * (day - 1)
    stop = start + 37
    return list(range(start, stop, 1))


def kelvin_2_celcius(kelvin):
    """A small utility function for converting degrees Kelvin to
    degrees Celcius.
    """
    return kelvin - 273.15


def relative_humdity(surface_temp, dewpoint_temp, kelvin=True):
    """Calculates relative humidity given a surface temperature and
    dewpoint temperature.
    """
    if kelvin:
        surf_t = kelvin_2_celcius(surface_temp)
        dew_t = kelvin_2_celcius(dewpoint_temp)
    else:
        surf_t = surface_temp
        dew_t = dewpoint_temp

    rh = 100 * ((112.0 - 0.1 * surf_t + dew_t) / (112.0 + 0.9 * surf_t)) ** 8

    return rh


def _collect_ancillary(
    acquisition,
    satellite_solar_fname,
    nbar_paths,
    sbt_path=None,
    invariant_fname=None,
    vertices=(3, 3),
    out_fname=None,
    compression="lzf",
    work_path="",
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(satellite_solar_fname, "r") as fid:
        boxline_dset = fid[DatasetName.boxline.value][:]

    rfid = collect_ancillary(
        acquisition,
        boxline_dset,
        nbar_paths,
        sbt_path,
        invariant_fname,
        vertices,
        out_fname,
        compression,
        work_path,
    )

    rfid.close()
    return


def collect_ancillary(
    acquisition,
    boxline_dataset,
    nbar_paths,
    sbt_path=None,
    invariant_fname=None,
    vertices=(3, 3),
    out_fname=None,
    compression="lzf",
    work_path="",
):
    """Collects the ancillary required for NBAR and optionally SBT.
    This could be better handled if using the `opendatacube` project
    to handle ancillary retrieval, rather than directory passing,
    and filename grepping.

    :param acquisition:
        An instance of an `Acquisition` object.

    :param boxline:
        The dataset containing the bi-section (satellite track)
        coordinates. The datatype should be the same as that returned
        by the `calculate_angles.create_boxline` function.
    :type boxline:
        [('row_index', 'int64'), ('bisection_index', 'int64'),
         ('npoints', 'int64'), ('start_index', 'int64'),
         ('end_index', 'int64')]

    :param nbar_paths:
        A `dict` containing the ancillary pathnames required for
        retrieving the NBAR ancillary data. Required keys:

        * aerosol_fname
        * water_vapour_path
        * ozone_path
        * dem_path
        * brdf_path
        * brdf_premodis_path

    :param sbt_path:
        A `str` containing the base directory pointing to the
        ancillary products required for the SBT workflow.

    :param invariant_fname:
        A `str` containing the file path name to the invariant
        geopotential image file.

    :param vertices:
        An integer 2-tuple indicating the number of rows and columns
        of sample-locations ("coordinator") to produce.
        The vertex columns should be an odd number.
        Default is (3, 3).

    :param out_fname:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver.
        Otherwise it should be a string containing the full file path
        name to a writeable location on disk in which to save the HDF5
        file.

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :param work_path:
        A `str` containing the pathname to the work directory to be
        used for temporary files. Default is the current directory.

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """
    coordinator = create_vertices(acquisition, boxline_dataset, vertices)
    lonlats = zip(coordinator["longitude"], coordinator["latitude"])

    if sbt_path:
        sbt_fid = collect_sbt_ancillary(
            acquisition,
            lonlats,
            sbt_path,
            invariant_fname,
            out_fname=out_fname,
            compression=compression,
        )

    # close if we have a file on disk
    if sbt_path and out_fname is not None:
        sbt_fid.close()

    rfid = collect_nbar_ancillary(
        acquisition,
        out_fname=out_fname,
        compression=compression,
        work_path=work_path,
        **nbar_paths,
    )

    desc = (
        "Contains the row and column array coordinates used for the "
        "atmospheric calculations."
    )
    attrs = {"Description": desc, "array_coordinate_offset": 0}
    kwargs = dataset_compression_kwargs(compression=compression)
    dset_name = DatasetName.coordinator.value
    coord_dset = rfid.create_dataset(dset_name, data=coordinator, **kwargs)
    attach_table_attributes(coord_dset, title="Coordinator", attrs=attrs)

    # copy if we don't have a file on disk
    if sbt_path and out_fname is None:
        rfid.copy(sbt_fid, rfid)

    return rfid


def collect_sbt_ancillary(
    acquisition,
    lonlats,
    ancillary_path,
    invariant_fname=None,
    out_fname=None,
    compression="lzf",
):
    """Collects the ancillary data required for surface brightness
    temperature.

    :param acquisition:
        An instance of an `Acquisition` object.

    :param lonlats:
        A `list` of tuples containing (longitude, latitude) coordinates.

    :param ancillary_path:
        A `str` containing the directory pathname to the ECMWF
        ancillary data.

    :param invariant_fname:
        A `str` containing the file pathname to the invariant geopotential
        data.

    :param out_fname:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver.
        Otherwise it should be a string containing the full file path
        name to a writeable location on disk in which to save the HDF5
        file.

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
    # Initialise the output files
    if out_fname is None:
        fid = h5py.File("sbt-ancillary.h5", driver="core", backing_store=False)
    else:
        fid = h5py.File(out_fname, "w")

    fid.attrs["sbt-ancillary"] = True

    dt = acquisition.scene_center_datetime

    description = (
        "Combined Surface and Pressure Layer data retrieved from "
        "the ECWMF catalogue."
    )
    attrs = {"Description": description, "Date used for querying ECWMF": dt}

    for i, lonlat in enumerate(lonlats):
        pnt = POINT_FMT.format(p=i)
        # get data located at the surface
        dew = ecwmf_dewpoint_temperature(ancillary_path, lonlat, dt)
        t2m = ecwmf_temperature_2metre(ancillary_path, lonlat, dt)
        sfc_prs = ecwmf_surface_pressure(ancillary_path, lonlat, dt)
        sfc_hgt = ecwmf_elevation(invariant_fname, lonlat)
        sfc_rh = relative_humdity(t2m[0], dew[0])

        # output the scalar data along with the attrs
        dname = ppjoin(pnt, DatasetName.dewpoint_temperature.value)
        write_scalar(dew[0], dname, fid, dew[1])

        dname = ppjoin(pnt, DatasetName.temperature_2m.value)
        write_scalar(t2m[0], dname, fid, t2m[1])

        dname = ppjoin(pnt, DatasetName.surface_pressure.value)
        write_scalar(sfc_prs[0], dname, fid, sfc_prs[1])

        dname = ppjoin(pnt, DatasetName.surface_geopotential.value)
        write_scalar(sfc_hgt[0], dname, fid, sfc_hgt[1])

        dname = ppjoin(pnt, DatasetName.surface_relative_humidity.value)
        attrs = {"Description": "Relative Humidity calculated at the surface"}
        write_scalar(sfc_rh, dname, fid, attrs)

        # get the data from each of the pressure levels (1 -> 1000 ISBL)
        gph = ecwmf_geo_potential(ancillary_path, lonlat, dt)
        tmp = ecwmf_temperature(ancillary_path, lonlat, dt)
        rh = ecwmf_relative_humidity(ancillary_path, lonlat, dt)

        dname = ppjoin(pnt, DatasetName.geopotential.value)
        write_dataframe(gph[0], dname, fid, compression, attrs=gph[1])

        dname = ppjoin(pnt, DatasetName.temperature.value)
        write_dataframe(tmp[0], dname, fid, compression, attrs=tmp[1])

        dname = ppjoin(pnt, DatasetName.relative_humidity.value)
        write_dataframe(rh[0], dname, fid, compression, attrs=rh[1])

        # combine the surface and higher pressure layers into a single array
        cols = ["GeoPotential_Height", "Pressure", "Temperature", "Relative_Humidity"]
        df = pd.DataFrame(
            columns=cols, index=range(rh[0].shape[0] + 1), dtype="float64"
        )

        col = "GeoPotential_Height"
        df[col].iloc[1:] = gph[0][col].values / 10000

        df["Pressure"].iloc[1:] = ECWMF_LEVELS[::-1]

        col = "Temperature"
        df[col].iloc[1:] = tmp[0][col].values

        col = "Relative_Humidity"
        df[col].iloc[1:] = rh[0][col].values

        # insert the surface level
        df["GeoPotential_Height"].iloc[0] = sfc_hgt[0]
        df["Pressure"].iloc[0] = sfc_prs[0]
        df["Temperature"].iloc[0] = kelvin_2_celcius(t2m[0])
        df["Relative_Humidity"].iloc[0] = sfc_rh

        # MODTRAN requires the height to be ascending
        # remove any records that are less than the surface level
        subset = df[df["GeoPotential_Height"] >= sfc_hgt[0]]

        dname = ppjoin(pnt, DatasetName.atmospheric_profile.value)
        write_dataframe(subset, dname, fid, compression, attrs=attrs)

        fid[pnt].attrs["lonlat"] = lonlat

    return fid


def collect_nbar_ancillary(
    acquisition,
    aerosol_fname=None,
    water_vapour_path=None,
    ozone_path=None,
    dem_path=None,
    brdf_path=None,
    brdf_premodis_path=None,
    out_fname=None,
    compression="lzf",
    work_path="",
):
    """Collects the ancillary information required to create NBAR.

    :param acquisition:
        An instance of an `Acquisition` object.

    :param aerosol_fname:
        A `str` containing the full file pathname to the `HDF5` file
        containing the aerosol data.

    :param water_vapour_path:
        A `str` containing the full file pathname to the directory
        containing the water vapour data.

    :param ozone_path:
        A `str` containing the full file pathname to the directory
        containing the ozone data.

    :param dem_path:
        A `str` containing the full file pathname to the directory
        containing the digital elevation model data.

    :param brdf_path:
        A `str` containing the full file pathname to the directory
        containing the BRDF image mosaics.

    :param brdf_premodis_path:
        A `str` containing the full file pathname to the directory
        containing the premodis BRDF image mosaics.

    :param out_fname:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver.
        Otherwise it should be a string containing the full file path
        name to a writeable location on disk in which to save the HDF5
        file.

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :param work_path:
        A `str` containing the path to a temporary directory where
        any BRDF images will be extracted to. Defaults to the current
        working directory.

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """

    def _format_brdf_attrs(factor):
        """Converts BRDF shortnames to longnames."""
        scattering_names = {"iso": "isometric", "vol": "volumetric", "geo": "geometric"}

        attrs = {}
        description = (
            "Bidirectional Reflectance Distribution Function "
            "for the {} scattering fraction."
        )
        attrs["Description"] = description.format(scattering_names[factor])

        return attrs

    # Initialise the output files
    if out_fname is None:
        fid = h5py.File("ancillary.h5", driver="core", backing_store=False)
    else:
        fid = h5py.File(out_fname)

    dt = acquisition.scene_center_datetime
    geobox = acquisition.gridded_geo_box()

    aerosol = get_aerosol_data(acquisition, aerosol_fname)
    write_scalar(aerosol[0], DatasetName.aerosol.value, fid, aerosol[1])

    wv = get_water_vapour(acquisition, water_vapour_path)
    write_scalar(wv[0], DatasetName.water_vapour.value, fid, wv[1])

    ozone = get_ozone_data(ozone_path, geobox.centre_lonlat, dt)
    write_scalar(ozone[0], DatasetName.ozone.value, fid, ozone[1])

    elev = get_elevation_data(geobox.centre_lonlat, dem_path)
    write_scalar(elev[0], DatasetName.elevation.value, fid, elev[1])

    # brdf
    group = fid.create_group("brdf-image-datasets")
    data = get_brdf_data(
        acquisition,
        brdf_path,
        brdf_premodis_path,
        group,
        compression=compression,
        work_path=work_path,
    )
    dname_format = DatasetName.brdf_fmt.value
    for key in data:
        band, factor = key
        attrs = _format_brdf_attrs(factor)
        for k in attrs:
            data[key][k] = attrs[k]
        dname = dname_format.format(band=band, factor=factor)
        brdf_value = data[key].pop("value")
        write_scalar(brdf_value, dname, fid, data[key])

    return fid


def aggregate_ancillary(ancillary_fnames, out_fname):
    """If the acquisition is part of a `tiled` scene such as Sentinel-2a,
    then we need to average the point measurements gathereed from
    all tiles.
    """
    # Initialise the output files
    if out_fname is None:
        fid1 = h5py.File("ancillary.h5", driver="core", backing_store=False)
    else:
        fid1 = h5py.File(out_fname, "w")

    # initialise the mean result
    ozone = vapour = aerosol = elevation = 0.0

    n_tiles = len(ancillary_fnames)

    for fname in ancillary_fnames:
        with h5py.File(fname, "r") as fid2:
            ozone += fid2[DatasetName.ozone.value][()]
            vapour += fid2[DatasetName.water_vapour.value][()]
            aerosol += fid2[DatasetName.aerosol.value][()]
            elevation += fid2[DatasetName.elevation.value][()]

    ozone /= n_tiles
    vapour /= n_tiles
    aerosol /= n_tiles
    elevation /= n_tiles

    description = (
        "The {} value is an average from all the {} values "
        "retreived for each Granule."
    )
    attrs = {"data_source": "granule_average"}

    dset = fid1.create_dataset(DatasetName.ozone.value, data=ozone)
    attrs["Description"] = description.format(*(2 * ["Ozone"]))
    attach_attributes(dset, attrs)

    dset = fid1.create_dataset(DatasetName.water_vapour.value, data=vapour)
    attrs["Description"] = description.format(*(2 * ["Water Vapour"]))
    attach_attributes(dset, attrs)

    dset = fid1.create_dataset(DatasetName.aerosol.value, data=aerosol)
    attrs["Description"] = description.format(*(2 * ["Aerosol"]))
    attach_attributes(dset, attrs)

    dset = fid1.create_dataset(DatasetName.elevation.value, data=elevation)
    attrs["Description"] = description.format(*(2 * ["Elevation"]))
    attach_attributes(dset, attrs)

    return fid1


def get_aerosol_data(acquisition, aerosol_fname):
    """Extract the aerosol value for an acquisition.
    The version 2 retrieves the data from a HDF5 file, and provides
    more control over how the data is selected geo-metrically.
    Better control over timedeltas.
    """
    dt = acquisition.scene_center_datetime
    geobox = acquisition.gridded_geo_box()
    roi_poly = Polygon(
        [geobox.ul_lonlat, geobox.ur_lonlat, geobox.lr_lonlat, geobox.ll_lonlat]
    )

    descr = ["AATSR_PIX", "AATSR_CMP_YEAR_MONTH", "AATSR_CMP_MONTH"]
    names = ["ATSR_LF_%Y%m", "aot_mean_%b_%Y_All_Aerosols", "aot_mean_%b_All_Aerosols"]
    exts = ["/pix", "/cmp", "/cmp"]
    pathnames = [ppjoin(ext, dt.strftime(n)) for ext, n in zip(exts, names)]

    fid = h5py.File(aerosol_fname, "r")

    delta_tolerance = datetime.timedelta(days=0.5)

    data = None
    for pathname, description in zip(pathnames, descr):
        if pathname in fid:
            df = read_table(fid, pathname)
            aerosol_poly = wkt.loads(fid[pathname].attrs["extents"])

            if aerosol_poly.intersects(roi_poly):
                if description == "AATSR_PIX":
                    abs_diff = (df["timestamp"] - dt).abs()
                    df = df[abs_diff < delta_tolerance]
                    df.reset_index(inplace=True, drop=True)

                if df.shape[0] == 0:
                    continue

                intersection = aerosol_poly.intersection(roi_poly)
                pts = GeoSeries([Point(x, y) for x, y in zip(df["lon"], df["lat"])])
                idx = pts.within(intersection)
                data = df[idx]["aerosol"].mean()

                if np.isfinite(data):
                    metadata = {
                        "data_source": description,
                        "dataset_name": pathname,
                        "query_date": dt,
                        "extents": wkt.dumps(intersection),
                    }

                    # ancillary metadata tracking
                    md = extract_ancillary_metadata(aerosol_fname)
                    for key in md:
                        metadata[key] = md[key]

                    fid.close()
                    return data, metadata

    # default aerosol value
    # assumes we are only processing Australia in which case it it should
    # be a coastal scene
    data = 0.06
    metadata = {"data_source": "Default value used; Assumed a coastal scene"}

    fid.close()
    return data, metadata


def get_elevation_data(lonlat, dem_path):
    """Get elevation data for a scene.

    :param lon_lat:
        The latitude, longitude of the scene center.
    :type lon_lat:
        float (2-tuple)

    :dem_dir:
        The directory in which the DEM can be found.
    :type dem_dir:
        str
    """
    datafile = pjoin(dem_path, "DEM_one_deg.tif")
    data = get_pixel(datafile, lonlat) * 0.001  # scale to correct units

    metadata = {"data_source": "Elevation", "data_file": datafile}

    # ancillary metadata tracking
    md = extract_ancillary_metadata(datafile)
    for key in md:
        metadata[key] = md[key]

    return data, metadata


def get_ozone_data(ozone_path, lonlat, time):
    """Get ozone data for a scene. `lonlat` should be the (x,y) for the centre
    the scene.
    """
    filename = time.strftime("%b").lower() + ".tif"
    datafile = pjoin(ozone_path, filename)
    data = get_pixel(datafile, lonlat)

    metadata = {"data_source": "Ozone", "data_file": datafile, "query_date": time}

    # ancillary metadata tracking
    md = extract_ancillary_metadata(datafile)
    for key in md:
        metadata[key] = md[key]

    return data, metadata


def get_water_vapour(acquisition, vapour_path, scale_factor=0.1):
    """Retrieve the water vapour value for an `acquisition` and the
    path for the water vapour ancillary data.
    """
    dt = acquisition.scene_center_datetime
    geobox = acquisition.gridded_geo_box()

    year = dt.strftime("%Y")
    filename = f"pr_wtr.eatm.{year}.tif"
    datafile = pjoin(vapour_path, filename)

    # calculate the water vapour band number based on the datetime

    doy = dt.timetuple().tm_yday
    hour = dt.timetuple().tm_hour
    band = (int(doy) - 1) * 4 + int((hour + 3) / 6)

    # Check for boundary condition: 1 Jan, 0-3 hours
    if band == 0 and doy == 1:
        band = 1

    # Get the number of bands
    with rasterio.open(datafile) as src:
        n_bands = src.count

    # Enable NBAR Near Real Time (NRT) processing
    if band > (n_bands + 1):
        rasterdoy = (((n_bands) - (int((hour + 3) / 6))) / 4) + 1
        if (doy - rasterdoy) < 7:
            band = (int(rasterdoy) - 1) * 4 + int((hour + 3) / 6)

    try:
        data = get_pixel(datafile, geobox.centre_lonlat, band=band)
    except IndexError:
        msg = f"Invalid water vapour band number: {band}"
        raise IndexError(msg)

    data = data * scale_factor

    metadata = {"data_source": "Water Vapour", "data_file": datafile, "query_date": dt}

    # ancillary metadata tracking
    md = extract_ancillary_metadata(datafile)
    for key in md:
        metadata[key] = md[key]

    return data, metadata


def ecwmf_elevation(datafile, lonlat):
    """Retrieve a pixel from the ECWMF invariant geo-potential
    dataset.
    Converts to Geo-Potential height in KM.
    """
    data = get_pixel(datafile, lonlat) / 9.80665 / 1000.0

    metadata = {"data_source": "ECWMF Invariant Geo-Potential", "data_file": datafile}

    # ancillary metadata tracking
    md = extract_ancillary_metadata(datafile)
    for key in md:
        metadata[key] = md[key]

    return data, metadata


def ecwmf_temperature_2metre(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF 2 metre Temperature
    collection.
    """
    product = "temperature-2metre"
    files = glob.glob(pjoin(input_path, f"{product}_*.tif"))
    product = DatasetName.temperature_2m.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            data = get_pixel(f, lonlat)

            metadata = {
                "data_source": "ECWMF 2 metre Temperature",
                "data_file": f,
                "query_date": time,
            }

            # ancillary metadata tracking
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            return data, metadata

    if data is None:
        raise OSError("No ECWMF 2 metre Temperature ancillary data found.")


def ecwmf_dewpoint_temperature(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF 2 metre Dewpoint
    Temperature collection.
    """
    product = DatasetName.dewpoint_temperature.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            data = get_pixel(f, lonlat)

            metadata = {
                "data_source": "ECWMF 2 metre Dewpoint Temperature ",
                "data_file": f,
                "query_date": time,
            }

            # ancillary metadata tracking
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            return data, metadata

    if data is None:
        msg = "No ECWMF 2 metre Dewpoint Temperature ancillary data found."
        raise OSError(msg)


def ecwmf_surface_pressure(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF Surface Pressure
    collection.
    Scales the result by 100 before returning.
    """
    product = DatasetName.surface_pressure.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            data = get_pixel(f, lonlat) / 100.0

            metadata = {
                "data_source": "ECWMF Surface Pressure",
                "data_file": f,
                "query_date": time,
            }

            # ancillary metadata tracking
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            return data, metadata

    if data is None:
        raise OSError("No Surface Pressure ancillary data found.")


def ecwmf_water_vapour(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF Total Column Water Vapour
    collection.
    """
    product = DatasetName.water_vapour.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            data = get_pixel(f, lonlat)

            metadata = {
                "data_source": "ECWMF Total Column Water Vapour",
                "data_file": f,
                "query_date": time,
            }

            # ancillary metadata tracking
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            return data, metadata

    if data is None:
        msg = "No ECWMF Total Column Water Vapour ancillary data found."
        raise OSError(msg)


def ecwmf_temperature(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF Temperature collection
    across 37 height pressure levels, for a given longitude,
    latitude and time.

    Reverses the order of elements
    (1000 -> 1 mb, rather than 1 -> 1000 mb) before returning.
    """
    product = DatasetName.temperature.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            bands = list(range(1, 38))
            data = get_pixel(f, lonlat, bands)[::-1]

            metadata = {
                "data_source": "ECWMF Temperature",
                "data_file": f,
                "query_date": time,
            }

            # ancillary metadata tracking
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            # internal file metadata (and reverse the ordering)
            df = read_meatadata_tags(f, bands).iloc[::-1]
            df.insert(0, "Temperature", data)

            return df, metadata

    if data is None:
        raise OSError("No Temperature ancillary data found.")


def ecwmf_geo_potential(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF Geo-Potential collection
    across 37 height pressure levels, for a given longitude,
    latitude and time.

    Converts to geo-potential height in KM, and reverses the order of
    the elements (1000 -> 1 mb, rather than 1 -> 1000 mb) before
    returning.
    """
    product = DatasetName.geopotential.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            bands = list(range(1, 38))
            data = get_pixel(f, lonlat, bands)[::-1]
            scaled_data = data / 9.80665 / 1000.0

            metadata = {
                "data_source": "ECWMF Geo-Potential",
                "data_file": f,
                "query_date": time,
            }

            # ancillary metadata tracking
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            # internal file metadata (and reverse the ordering)
            df = read_meatadata_tags(f, bands).iloc[::-1]
            df.insert(0, "GeoPotential_Height", data)
            df.insert(1, "GeoPotential", scaled_data)

            return df, md

    if data is None:
        raise OSError("No Geo-Potential ancillary data found.")


def ecwmf_relative_humidity(input_path, lonlat, time):
    """Retrieve a pixel value from the ECWMF Relative Humidity collection
    across 37 height pressure levels, for a given longitude,
    latitude and time.

    Reverses the order of elements
    (1000 -> 1 mb, rather than 1 -> 1000 mb) before returning.
    """
    product = DatasetName.relative_humidity.value
    search = pjoin(input_path, DatasetName.ecmwf_path_fmt.value)
    files = glob.glob(search.format(product=product, year=time.year))
    data = None
    required_ymd = datetime.datetime(time.year, time.month, time.day)
    for f in files:
        ymd = splitext(basename(f))[0].split("_")[1]
        ancillary_ymd = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        if ancillary_ymd == required_ymd:
            bands = list(range(1, 38))
            data = get_pixel(f, lonlat, bands)[::-1]

            metadata = {
                "data_source": "ECWMF Relative Humidity",
                "data_file": f,
                "query_date": time,
            }

            # file level metadata
            md = extract_ancillary_metadata(f)
            for key in md:
                metadata[key] = md[key]

            # internal file metadata (and reverse the ordering)
            df = read_meatadata_tags(f, bands).iloc[::-1]
            df.insert(0, "Relative_Humidity", data)

            return df, metadata

    if data is None:
        raise OSError("No Relative Humidity ancillary data found.")
