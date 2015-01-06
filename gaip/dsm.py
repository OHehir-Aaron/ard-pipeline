#!/usr/bin/env python

from rasterio.warp import RESAMPLING

from gaip import GriddedGeoBox, ImageMargins, filter_dsm, reprojectFile2Array, write_img


def get_dsm(acquisition, national_dsm, margins, fname_subset, fname_smoothed):
    """Given an acquisition and a national Digitial Surface Model,
    extract a subset from the DSM based on the acquisition extents
    plus an x & y margins. The subset is then smoothed with a 3x3
    gaussian filter.
    A square margins is applied to the extents.

    :param acquisition:
        An instance of an acquisition object.

    :param national_dsm:
        A string containing the full filepath name to an image on
        disk containing national digital surface model.

    :param margin:
        An integer indictaing the number of pixels to be used as a
        margin around the aqcuisition.
        Eg, a value of 250 indicates that 250 pixels to the top,
        bottom, left and right will be added to the acquisition
        margin/border.

    :param fname_subset:
        A string containing the full filepath name to a location on
        disk that will contain the subsetted dsm.

    :param fname_smoothed:
        A string containing the full filepath name to a location on
        disk that will contain the subsetted and smoothed dsm.

    :return:
        None, the results will be written to disk.
    """
    # Use the 1st acquisition to setup the geobox
    geobox = acquisition.gridded_geo_box()

    # Define Top, Bottom, Left, Right pixel margins
    pixel_buf = ImageMargins(margins)

    # Get the dimensions and geobox of the new image
    dem_cols = geobox.getShapeXY()[0] + pixel_buf.left + pixel_buf.right
    dem_rows = geobox.getShapeXY()[1] + pixel_buf.top + pixel_buf.bottom
    dem_shape = (dem_rows, dem_cols)
    dem_origin = geobox.convert_coordinates((0 - pixel_buf.left, 0 - pixel_buf.top))
    dem_geobox = GriddedGeoBox(
        dem_shape,
        origin=dem_origin,
        pixelsize=geobox.pixelsize,
        crs=geobox.crs.ExportToWkt(),
    )

    # Retrive the DSM data
    dsm_data = reprojectFile2Array(
        national_dsm, dst_geobox=dem_geobox, resampling=RESAMPLING.bilinear
    )

    # Output the reprojected result
    write_img(dsm_data, fname_subset, geobox=dem_geobox)

    # Smooth the DSM
    dsm_data = filter_dsm(dsm_data)

    # Output the smoothed DSM
    write_img(dsm_data, fname_smoothed, geobox=dem_geobox)
