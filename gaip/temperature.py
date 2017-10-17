#!/usr/bin/env python

"""Various routines for converting radiance to temperature
-------------------------------------------------------.
"""

import logging

import h5py
import numexpr
import numpy as np

from gaip.constants import DatasetName, GroupName
from gaip.hdf5 import attach_image_attributes, dataset_compression_kwargs
from gaip.metadata import create_ard_yaml
from gaip.tiling import generate_tiles


def _surface_brightness_temperature(
    acquisition, bilinear_fname, ancillary_fname, out_fname, compression, y_tile
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    with h5py.File(bilinear_fname, "r") as interp_fid, h5py.File(
        ancillary_fname, "r"
    ) as fid_anc, h5py.File(out_fname, "w") as fid:
        grp1 = interp_fid[GroupName.interp_group.value]
        surface_brightness_temperature(acquisition, grp1, fid, compression, y_tile)

        grp2 = fid_anc[GroupName.ancillary_group.value]
        create_ard_yaml(acquisition, grp2, fid, True)


def surface_brightness_temperature(
    acquisition, interpolation_group, out_group=None, compression="lzf", y_tile=100
):
    """Convert Thermal acquisition to Surface Brightness Temperature.

    T[Kelvin] = k2 / ln( 1 + (k1 / I[0]) )

    where T is the surface brightness temperature (the surface temperature
    if the surface is assumed to be an ideal black body i.e. unit emissivity),
    k1 & k2 are calibration constants specific to the platform/sensor/band,
    and I[0] is the surface radiance (the integrated band radiance, in
    Watts per square metre per steradian per thousand nanometres).

    I = t I[0] + d

    where I is the radiance at the sensor, t is the transmittance (through
    the atmosphere), and d is radiance from the atmosphere itself.

    :param acquisition:
        An instance of an acquisition object.

    :param interpolation_group:
        The root HDF5 `Group` that contains the interpolated
        atmospheric coefficients.
        The dataset pathnames are given by the following string format:

        * DatasetName.interpolation_fmt

    :param out_group:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver. Otherwise,
        a writeable HDF5 `Group` object.

        The dataset names will be given by the format string detailed
        by:

        * DatasetName.temperature_fmt

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

    :notes:
        This function used to accept `NumPy` like datasets as inputs,
        but as this functionality was never used, it was simpler to
        parse through the H5 Group object, which in most cases
        reduced the number or parameters being parsed through.
        Thereby simplifying the overall workflow, and making it
        consistant with other functions within the overall workflow.
    """
    acq = acquisition
    geobox = acq.gridded_geo_box()
    bn = acq.band_name

    # retrieve the upwelling radiation and transmittance datasets
    dname_fmt = DatasetName.interpolation_fmt.value
    dname = dname_fmt.format(factor="path-up", band=bn)
    upwelling_radiation = interpolation_group[dname]
    dname = dname_fmt.format(factor="transmittance-up", band=bn)
    transmittance = interpolation_group[dname]

    # tiling scheme
    tiles = generate_tiles(acq.samples, acq.lines, acq.samples, y_tile)

    # Initialise the output file
    if out_group is None:
        fid = h5py.File("surface-temperature.h5", driver="core", backing_store=False)
    else:
        fid = out_group

    if GroupName.standard_group.value not in fid:
        fid.create_group(GroupName.standard_group.value)

    group = fid[GroupName.standard_group.value]
    kwargs = dataset_compression_kwargs(
        compression=compression, chunks=(1, acq.samples)
    )
    kwargs["shape"] = (acq.lines, acq.samples)
    kwargs["fillvalue"] = -999
    kwargs["dtype"] = "float32"

    # attach some attributes to the image datasets
    attrs = {
        "crs_wkt": geobox.crs.ExportToWkt(),
        "geotransform": geobox.transform.to_gdal(),
        "no_data_value": kwargs["fillvalue"],
        "platform_id": acq.platform_id,
        "sensor_id": acq.sensor_id,
        "band_id": acq.band_id,
        "band_name": bn,
    }

    name_fmt = DatasetName.temperature_fmt.value
    dataset_name = name_fmt.format(band=acq.band_name)
    out_dset = group.create_dataset(dataset_name, **kwargs)

    desc = "Surface Brightness Temperature in Kelvin."
    attrs["Description"] = desc
    attach_image_attributes(out_dset, attrs)

    # constants

    # process each tile
    for tile in tiles:
        idx = (slice(tile[0][0], tile[0][1]), slice(tile[1][0], tile[1][1]))

        acq_args = {
            "window": tile,
            "masked": False,
            "apply_gain_offset": acq.scaled_radiance,
            "out_no_data": kwargs["fillvalue"],
        }

        acq.data(**acq_args)
        upwelling_radiation[idx]
        trans = transmittance[idx]
        mask = ~np.isfinite(trans)
        expr = "(radiance-path_up) / trans"
        corrected_radiance = numexpr.evaluate(expr)
        mask |= corrected_radiance <= 0
        expr = "k2 / log(k1 / corrected_radiance + 1)"
        brightness_temp = numexpr.evaluate(expr)
        brightness_temp[mask] = kwargs["fillvalue"]

        out_dset[idx] = brightness_temp

    if out_group is None:
        return fid


def radiance_conversion(band_array, gain, bias):
    """Converts the input image into radiance using the gain and bias
    method.

    :param band_array:
        A `NumPy` array containing the scaled DN to be converted
        to radiance at sensor.

    :param gain:
        Floating point value.

    :param bias:
        Floating point value.

    :return:
        The thermal band converted to at-sensor radiance in
        watts/(meter squared * ster * um) as a 2D Numpy array.
    """
    logging.debug("gain = %f, bias = %f", gain, bias)

    return numexpr.evaluate("gain * band_array + bias")


def temperature_conversion(band_array, k1, k2):
    """Converts the radiance image to degrees Kelvin.

    :param image:
        A 2D Numpy array containing the thermal band converted to
        radiance.

    :param k1:
        Conversion constant 1.

    :param k2:
        Conversion constant 2.

    :return:
        A 2D Numpy array of the thermal band coverted to at-sensor
        degrees Kelvin.
    """
    logging.debug("k1 = %f, k2 = %f", k1, k2)

    return k2 / (np.log(k1 / band_array + 1))


def get_landsat_temperature(acquisitions, pq_const):
    """Converts a Landsat TM/ETM+ thermal band into degrees Kelvin.
    Required input is the image to be in byte scaled DN form (0-255).

    :param acquisitions:
        A list of acquisition instances.

    :param pq_const:
        An instance of the PQ constants.

    :return:
        A 2D Numpy array containing degrees Kelvin.
    """
    acqs = acquisitions
    thermal_band = pq_const.thermal_band

    # Function returns a list of one item. Take the first item.
    acq = [a for a in acqs if a.band_id == thermal_band][0]
    radiance = acq.data(apply_gain_offset=True)

    kelvin_array = temperature_conversion(radiance, acq.K1, acq.K2)

    return kelvin_array.astype("float32")
