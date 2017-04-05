#!/usr/bin/env python

"""Various routines for converting radiance to temperature
-------------------------------------------------------.
"""

import logging

import h5py
import numexpr
import numpy as np

from gaip.hdf5 import attach_image_attributes, dataset_compression_kwargs
from gaip.tiling import generate_tiles

DATASET_NAME_FMT = "surface-brightness-temperature-band-{band}"


def _surface_brightness_temperature(
    acquisition, bilinear_fname, out_fname, compression, x_tile, y_tile
):
    """A private wrapper for dealing with the internal custom workings of the
    NBAR workflow.
    """
    band_num = acquisition.band_num
    with h5py.File(bilinear_fname, "r") as fid:
        upwelling_dset = fid[f"path_up-band-{band_num}"]
        dname = f"transmittance_up-band-{band_num}"
        transmittance_dset = fid[dname]

        kwargs = {
            "acquisition": acquisition,
            "upwelling_radiation": upwelling_dset,
            "transmittance": transmittance_dset,
            "out_fname": out_fname,
            "compression": compression,
            "x_tile": x_tile,
            "y_tile": y_tile,
        }

        rfid = surface_brightness_temperature(**kwargs)

    rfid.close()
    return


def surface_brightness_temperature(
    acquisition,
    upwelling_radiation,
    transmittance,
    out_fname=None,
    compression="lzf",
    x_tile=None,
    y_tile=None,
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

    :param upwelling_radiation:
        A `NumPy` or `NumPy` like dataset that allows indexing
        and returns a `NumPy` dataset containing the MODTRAN
        factor `upwelling_radiation` data values when indexed/sliced.

    :param transmittance:
        A `NumPy` or `NumPy` like dataset that allows indexing
        and returns a `NumPy` dataset containing the MODTRAN
        factor `upwelling_transmittance` data values when indexed/sliced.

    :param out_fname:
        If set to None (default) then the results will be returned
        as an in-memory hdf5 file, i.e. the `core` driver.
        Otherwise it should be a string containing the full file path
        name to a writeable location on disk in which to save the HDF5
        file.

        The dataset names will be as follows:

        * surface-brightness-temperature-band-{number}

    :param compression:
        The compression filter to use. Default is 'lzf'.
        Options include:

        * 'lzf' (Default)
        * 'lz4'
        * 'mafisc'
        * An integer [1-9] (Deflate/gzip)

    :param x_tile:
        Defines the tile size along the x-axis. Default is None which
        equates to all elements along the x-axis.

    :param y_tile:
        Defines the tile size along the y-axis. Default is None which
        equates to all elements along the y-axis.

    :return:
        An opened `h5py.File` object, that is either in-memory using the
        `core` driver, or on disk.
    """
    rows = acquisition.lines
    cols = acquisition.samples
    geobox = acquisition.gridded_geo_box()

    # tiling scheme
    tiles = generate_tiles(cols, rows, x_tile, y_tile)

    # Initialise the output file
    if out_fname is None:
        fid = h5py.File("surface-temperature.h5", driver="core", backing_store=False)
    else:
        fid = h5py.File(out_fname, "w")

    kwargs = dataset_compression_kwargs(compression=compression, chunks=(1, cols))
    kwargs["shape"] = (rows, cols)
    kwargs["fillvalue"] = -999
    kwargs["dtype"] = "int16"

    # attach some attributes to the image datasets
    attrs = {
        "crs_wkt": geobox.crs.ExportToWkt(),
        "geotransform": geobox.transform.to_gdal(),
        "no_data_value": kwargs["fillvalue"],
        "sattelite": acquisition.spacecraft_id,
        "sensor": acquisition.sensor_id,
        "band number": acquisition.band_num,
    }

    dset_name = DATASET_NAME_FMT.format(band=acquisition.band_num)
    out_dset = fid.create_dataset(dset_name, **kwargs)

    desc = "Surface Brightness Temperature in Kelvin scaled by 100."
    attrs["Description"] = desc
    attach_image_attributes(out_dset, attrs)

    # constants

    # process each tile
    for tile in tiles:
        idx = (slice(tile[0][0], tile[0][1]), slice(tile[1][0], tile[1][1]))

        acq_args = {
            "window": tile,
            "masked": False,
            "apply_gain_offset": acquisition.scaled_radiance,
            "out_no_data": kwargs["fillvalue"],
        }

        radiance = acquisition.data(**acq_args)
        mask = radiance == kwargs["fillvalue"]
        upwelling_radiation[idx]
        transmittance[idx]
        expr = "k2 / log(k1 / ((radiance-path_up) / trans + 1)) * 100 + 0.5"
        brightness_temp = numexpr.evaluate(expr)
        brightness_temp[mask] = kwargs["fillvalue"]

        out_dset[idx] = brightness_temp

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


def get_landsat_temperature(l1t_stack, acquisitions, pq_const):
    """Converts a Landsat TM/ETM+ thermal band into degrees Kelvin.
    Required input is the image to be in byte scaled DN form (0-255).

    :param l1t_stack:
        A 3D `numpy.ndarray` containing the thermal band.

    :param acquisitions:
        A list of acquisition instances.

    :param pq_const:
        An instance of the PQ constants.

    :return:
        A 2D Numpy array containing degrees Kelvin.
    """
    acqs = acquisitions
    thermal_band = pq_const.thermal_band

    if type(thermal_band) == str:
        kelvin_array = np.zeros(
            (l1t_stack.shape[1], l1t_stack.shape[2]), dtype="float32"
        )
        return kelvin_array

    # Function returns a list of one item. Take the first item.
    thermal_band_index = pq_const.get_array_band_lookup([thermal_band])[0]

    logging.debug(
        "thermal_band = %d, thermal_band_index = %d", thermal_band, thermal_band_index
    )

    radiance_array = radiance_conversion(
        l1t_stack[thermal_band_index],
        acqs[thermal_band_index].gain,
        acqs[thermal_band_index].bias,
    )

    kelvin_array = temperature_conversion(
        radiance_array, acqs[thermal_band_index].K1, acqs[thermal_band_index].K2
    )

    return kelvin_array.astype("float32")
