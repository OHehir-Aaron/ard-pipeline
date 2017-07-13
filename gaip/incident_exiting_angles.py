#!/usr/bin/env python

"""Calculates 2D grids of incident, exiting and relative azimuthal angles."""

import h5py
import numpy as np

from gaip.__exiting_angle import exiting_angle
from gaip.__incident_angle import incident_angle
from gaip.constants import DatasetName
from gaip.data import as_array
from gaip.geobox import GriddedGeoBox
from gaip.hdf5 import attach_image_attributes, dataset_compression_kwargs
from gaip.tiling import generate_tiles


def _incident_exiting_angles(
    satellite_solar_fname,
    slope_aspect_fname,
    out_fname,
    compression="lzf",
    y_tile=100,
    incident=True,
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(satellite_solar_fname, "r") as sat_sol, h5py.File(
        slope_aspect_fname, "r"
    ) as slp_asp, h5py.File(out_fname, "w") as out_fid:
        grp1 = sat_sol[GroupName.sat_sol_group.value]
        grp2 = slp_asp[DatasetName.slp_asp_group.value]
        if incident:
            incident_angles(grp1, grp2, out_fid, compression, y_tile)
        else:
            exiting_angles(grp1, grp2, out_fid, compression, y_tile)


def incident_angles(
    satellite_solar_group,
    slope_aspect_group,
    out_group=None,
    compression="lzf",
    y_tile=100,
):
    """Calculates the incident angle and the azimuthal incident angle.

    :param satellite_solar_group:
        The root HDF5 `Group` that contains the solar zenith and
        solar azimuth datasets specified by the pathnames given by:

        * DatasetName.solar_zenith
        * DatasetName.solar_azimuth

    :param slope_aspect_group:
        The root HDF5 `Group` that contains the slope and aspect
        datasets specified by the pathnames given by:

        * DatasetName.slope
        * DatasetName.aspect

    :param out_group:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver. Otherwise,
        a writeable HDF5 `Group` object.

        The dataset names will be as follows:

        * DatasetName.incident
        * DatasetName.azimuthal_incident

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :param y_tile:
        Defines the tile size along the y-axis. Default is 100.

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """
    # dataset arrays
    dname = DatasetName.solar_zenith.value
    solar_zenith_dataset = satellite_solar_group[dname]
    dname = DatasetName.solar_azimuth.value
    solar_azimuth_dataset = satellite_solar_group[dname]
    slope_dataset = slope_aspect_group[DatasetName.slope.value]
    aspect_dataset = slope_aspect_group[DatasetName.aspect.value]

    geobox = GriddedGeoBox.from_dataset(solar_zenith_dataset)
    shape = geobox.get_shape_yx()
    rows, cols = shape
    crs = geobox.crs.ExportToWkt()

    # Initialise the output files
    if out_group is None:
        fid = h5py.File("incident-angles.h5", driver="core", backing_store=False)
    else:
        fid = out_group

    grp = fid.create_group(DatasetName.incident_group.value)

    kwargs = dataset_compression_kwargs(
        compression=compression, chunks=(1, geobox.x_size())
    )
    no_data = -999
    kwargs["shape"] = shape
    kwargs["fillvalue"] = no_data
    kwargs["dtype"] = "float32"

    # output datasets
    dataset_name = DatasetName.incident.value
    incident_dset = grp.create_dataset(dataset_name, **kwargs)
    dataset_name = DatasetName.azimuthal_incident.value
    azi_inc_dset = grp.create_dataset(dataset_name, **kwargs)

    # attach some attributes to the image datasets
    attrs = {
        "crs_wkt": crs,
        "geotransform": geobox.transform.to_gdal(),
        "no_data_value": no_data,
    }
    desc = "Contains the incident angles in degrees."
    attrs["Description"] = desc
    attach_image_attributes(incident_dset, attrs)

    desc = "Contains the azimuthal incident angles in degrees."
    attrs["Description"] = desc
    attach_image_attributes(azi_inc_dset, attrs)

    # Initialise the tiling scheme for processing
    tiles = generate_tiles(cols, rows, cols, y_tile)

    # Loop over each tile
    for tile in tiles:
        # Row and column start and end locations
        ystart = tile[0][0]
        xstart = tile[1][0]
        yend = tile[0][1]
        xend = tile[1][1]
        idx = (slice(ystart, yend), slice(xstart, xend))

        # Tile size
        ysize = yend - ystart
        xsize = xend - xstart

        # Read the data for the current tile
        # Convert to required datatype and transpose
        sol_zen = as_array(solar_zenith_dataset[idx], dtype=np.float32, transpose=True)
        sol_azi = as_array(solar_azimuth_dataset[idx], dtype=np.float32, transpose=True)
        slope = as_array(slope_dataset[idx], dtype=np.float32, transpose=True)
        aspect = as_array(aspect_dataset[idx], dtype=np.float32, transpose=True)

        # Initialise the work arrays
        incident = np.zeros((ysize, xsize), dtype="float32")
        azi_incident = np.zeros((ysize, xsize), dtype="float32")

        # Process the current tile
        incident_angle(
            xsize,
            ysize,
            sol_zen,
            sol_azi,
            slope,
            aspect,
            incident.transpose(),
            azi_incident.transpose(),
        )

        # Write the current tile to disk
        incident_dset[idx] = incident
        azi_inc_dset[idx] = azi_incident

    if out_group is None:
        return fid


def exiting_angles(
    satellite_solar_group,
    slope_aspect_group,
    out_group=None,
    compression="lzf",
    y_tile=100,
):
    """Calculates the exiting angle and the azimuthal exiting angle.

    :param satellite_solar_group:
        The root HDF5 `Group` that contains the satellite view and
        satellite azimuth datasets specified by the pathnames given by:

        * DatasetName.satellite_view
        * DatasetName.satellite_azimuth

    :param slope_aspect_group:
        The root HDF5 `Group` that contains the slope and aspect
        datasets specified by the pathnames given by:

        * DatasetName.slope
        * DatasetName.aspect

    :param out_group:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver. Otherwise,
        a writeable HDF5 `Group` object.

        The dataset names will be as follows:

        * DatasetName.exiting
        * DatasetName.azimuthal_exiting

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :param y_tile:
        Defines the tile size along the y-axis. Default is 100.

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """
    # dataset arrays
    dname = DatasetName.satellite_view.value
    satellite_view_dataset = satellite_solar_group[dname]
    dname = DatasetName.satellite_azimuth.value
    satellite_azimuth_dataset = satellite_solar_group[dname]
    slope_dataset = slope_aspect_group[DatasetName.slope.value]
    aspect_dataset = slope_aspect_group[DatasetName.aspect.value]

    geobox = GriddedGeoBox.from_dataset(satellite_view_dataset)
    shape = geobox.get_shape_yx()
    rows, cols = shape
    crs = geobox.crs.ExportToWkt()

    # Initialise the output files
    if out_group is None:
        fid = h5py.File("exiting-angles.h5", driver="core", backing_store=False)
    else:
        fid = out_group

    grp = fid.create_group(DatasetName.exiting_group.value)

    kwargs = dataset_compression_kwargs(compression=compression, chunks=(1, cols))
    no_data = -999
    kwargs["shape"] = shape
    kwargs["fillvalue"] = no_data
    kwargs["dtype"] = "float32"

    # output datasets
    dataset_name = DatasetName.exiting.value
    exiting_dset = grp.create_dataset(dataset_name, **kwargs)
    dataset_name = DatasetName.azimuthal_exiting.value
    azi_exit_dset = grp.create_dataset(dataset_name, **kwargs)

    # attach some attributes to the image datasets
    attrs = {
        "crs_wkt": crs,
        "geotransform": geobox.transform.to_gdal(),
        "no_data_value": no_data,
    }
    desc = "Contains the exiting angles in degrees."
    attrs["Description"] = desc
    attach_image_attributes(exiting_dset, attrs)

    desc = "Contains the azimuthal exiting angles in degrees."
    attrs["Description"] = desc
    attach_image_attributes(azi_exit_dset, attrs)

    # Initialise the tiling scheme for processing
    tiles = generate_tiles(cols, rows, cols, y_tile)

    # Loop over each tile
    for tile in tiles:
        # Row and column start and end locations
        ystart = tile[0][0]
        xstart = tile[1][0]
        yend = tile[0][1]
        xend = tile[1][1]
        idx = (slice(ystart, yend), slice(xstart, xend))

        # Tile size
        ysize = yend - ystart
        xsize = xend - xstart

        # Read the data for the current tile
        # Convert to required datatype and transpose
        sat_view = as_array(
            satellite_view_dataset[idx], dtype=np.float32, transpose=True
        )
        sat_azi = as_array(
            satellite_azimuth_dataset[idx], dtype=np.float32, transpose=True
        )
        slope = as_array(slope_dataset[idx], dtype=np.float32, transpose=True)
        aspect = as_array(aspect_dataset[idx], dtype=np.float32, transpose=True)

        # Initialise the work arrays
        exiting = np.zeros((ysize, xsize), dtype="float32")
        azi_exiting = np.zeros((ysize, xsize), dtype="float32")

        # Process the current tile
        exiting_angle(
            xsize,
            ysize,
            sat_view,
            sat_azi,
            slope,
            aspect,
            exiting.transpose(),
            azi_exiting.transpose(),
        )

        # Write the current to disk
        exiting_dset[idx] = exiting
        azi_exit_dset[idx] = azi_exiting

    if out_group is None:
        return fid


def _relative_azimuth_slope(
    incident_angles_fname,
    exiting_angles_fname,
    out_fname,
    compression="lzf",
    y_tile=100,
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(incident_angles_fname, "r") as inci_fid, h5py.File(
        exiting_angles_fname, "r"
    ) as exit_fid, h5py.File(out_fname, "w") as out_fid:
        grp1 = inci_fid[DatasetName.incident_group.value]
        grp2 = exit_fid[DatasetName.exiting_group.value]
        relative_azimuth_slope(grp1, grp2, out_fid, compression, y_tile)


def relative_azimuth_slope(
    incident_angles_group,
    exiting_angles_group,
    out_group=None,
    compression="lzf",
    y_tile=100,
):
    """Calculates the relative azimuth angle on the slope surface.

    :param incident_angles_group:
        The root HDF5 `Group` that contains the azimuthal incident
        angle dataset specified by the pathname given by:

        * DatasetName.azimuthal_incident

    :param exiting_angles_group:
        The root HDF5 `Group` that contains the azimuthal exiting
        angle dataset specified by the pathname given by:

        * DatasetName.azimuthal_exiting

    :param out_group:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver. Otherwise,
        a writeable HDF5 `Group` object.

        The dataset names will be as follows:

        * DatasetName.relative_slope

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :param y_tile:
        Defines the tile size along the y-axis. Default is 100.

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """
    # dataset arrays
    dname = DatasetName.azimuthal_incident.value
    azimuth_incident_dataset = incident_angles_group[dname]
    dname = DatasetName.azimuthal_exiting.value
    azimuth_exiting_dataset = exiting_angles_group[dname]

    geobox = GriddedGeoBox.from_dataset(azimuth_incident_dataset)
    shape = geobox.get_shape_yx()
    rows, cols = shape
    crs = geobox.crs.ExportToWkt()

    # Initialise the output files
    if out_group is None:
        fid = h5py.File(
            "relative-azimuth-angles.h5", driver="core", backing_store=False
        )
    else:
        fid = out_group

    grp = fid.create_group(DatasetName.rel_slp_group.value)

    kwargs = dataset_compression_kwargs(
        compression=compression, chunks=(1, geobox.x_size())
    )
    no_data = -999
    kwargs["shape"] = shape
    kwargs["fillvalue"] = no_data
    kwargs["dtype"] = "float32"

    # output datasets
    out_dset = grp.create_dataset(DatasetName.relative_slope.value, **kwargs)

    # attach some attributes to the image datasets
    attrs = {
        "crs_wkt": crs,
        "geotransform": geobox.transform.to_gdal(),
        "no_data_value": no_data,
    }
    desc = "Contains the relative azimuth angles on the slope surface in " "degrees."
    attrs["Description"] = desc
    attach_image_attributes(out_dset, attrs)

    # Initialise the tiling scheme for processing
    tiles = generate_tiles(cols, rows, cols, y_tile)

    # Loop over each tile
    for tile in tiles:
        # Row and column start and end locations
        ystart, yend = tile[0]
        xstart, xend = tile[1]
        idx = (slice(ystart, yend), slice(xstart, xend))

        # Read the data for the current tile
        azi_inc = azimuth_incident_dataset[idx]
        azi_exi = azimuth_exiting_dataset[idx]

        # Process the tile
        rel_azi = azi_inc - azi_exi
        rel_azi[rel_azi <= -180.0] += 360.0
        rel_azi[rel_azi > 180.0] -= 360.0

        # Write the current tile to disk
        out_dset[idx] = rel_azi

    if out_group is None:
        return fid
