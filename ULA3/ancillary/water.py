#!/usr/bin/env python

import logging
import os

import get_pixel  # Waiting on Dales work to be pushed
import rasterio

from ULA3.meta import print_call

logger = logging.getLogger("root." + __name__)


@print_call(logger.info)
def get_water_vapour_data(water_vapour_path, lonlat, date_time, scale_factor=0.1):
    """Retrieve the water vapour value given a longitude, latitude and
    date time.

    :param water_vapour_path:
        A string containing the full file path to a directory
        containing the water vapour ancillary data. Water vapour
        files should be of the form pr_wtr.eatm.{year}.tif with year
        indicating each years, i.e. 1999, 2000, 2001, worth of data.
        Each water vapour file contains a separate band for each
        day-of-year and hour.  Each band represents a continental
        scale 2D image.

    :param lonlat:
        The longitude and latitude are a 2 element floating point
        tuple (lon, lat) for the position of interest.

    :param date_time:
        A python datetime object containing the year, month, day,
        hour and second to be used in determining the correct band
        in the water vapour ancillary files.

    :param scale_factor:
        A scale factor to apply to the retrieve value. The water
        vapour ancillary files should be in kg/m^2, and the default
        action is to return the values in g/cm^2 for use within
        MODTRAN.
        Default is 0.1

    :return:
        A dictionary with 3 keys of the form:
        'data_source' -> Type of ancillary data.
        'data_file' -> File system path to the file of interest.
        'value' -> The retrieved data value.
    """

    def get_band_index():
        """Calculate the water vapour band number based on the datetime.

        Code and data layout are not documented in original
        extractVapour.c program, so we clone the code here.

        N.B: Water vapour datasets each cover a single year over the
        whole of Australia with day-of-year and hour in separate
        bands.

        :return:
            Integer representing the band index.
            The band index is 1 based, i.e. starting at 1.
        """
        doy = date_time.timetuple().tm_yday
        hour = date_time.timetuple().tm_hour
        band_number = (int(doy) - 1) * 4 + int((hour + 3) / 6)

        # Check for boundary condition: 1 Jan, 0-3 hours
        if band_number == 0 and doy == 1:
            band_number = 1

        # Get the number of bands
        with rasterio.open(datafile) as src:
            n_bands = src.count

        # Enable NBAR Near Real Time (NRT) processing
        if band_number > (n_bands + 1):
            rasterdoy = (((n_bands) - (int((hour + 3) / 6))) / 4) + 1
            if (doy - rasterdoy) < 7:
                band_number = (int(rasterdoy) - 1) * 4 + int((hour + 3) / 6)

        return band_number

    year = date_time.strftime("%Y")
    filename = f"pr_wtr.eatm.{year}.tif"
    datafile = os.path.join(water_vapour_path, filename)

    band_idx = get_band_index()

    try:
        value = get_pixel(datafile, lonlat)
    except IndexError:
        raise Exception(f"Invalid Water Vapour band number: {band_idx}")

    value = value * scale_factor

    water_vapour_data = {
        "data_source": "Water Vapour",
        "data_file": datafile,
        "value": value,
    }

    return water_vapour_data
