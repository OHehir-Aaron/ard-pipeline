#!/usr/bin/env

import numpy as np
import rasterio

from gaip import ImageMargins, as_array, setup_spheroid, slope_aspect, write_img


def write_header_slope_file(file_name, margins, geobox):
    """Write the header slope file."""
    with open(file_name, "w") as output:
        # get dimensions, resolution and pixel origin
        rows, cols = geobox.shape
        res = geobox.pixelsize
        origin = geobox.origin

        # Now output the details
        output.write(f"{rows} {cols}\n")
        output.write(
            f"{margins.left} {margins.right}\n{margins.top} {margins.bottom}\n"
        )
        output.write(f"{res[1]} {res[0]}\n")
        output.write(f"{origin[1]} {origin[0]}\n")


def slope_aspect_arrays(
    acquisition,
    dsm_fname,
    margins,
    slope_out_fname,
    aspect_out_fname,
    header_slope_fname=None,
):
    """Calculates slope and aspect.

    :param acquisition:
        An instance of an acquisition object.

    :param dsm_fname:
        A string containing the full file path name to the Digital
        Surface Model to be used in deriving the surface angles.

    :param margins:
        An object with members top, bottom, left and right giving the
        size of the margins (in pixels) which have been added to the
        corresponding sides of dsm.

    :param slope_out_fname:
        A string containing the full file path name to be used for
        writing the slope image on disk.

    :param aspect_out_fname:
        A string containing the full file path name to be used for
        writing the aspect image on disk.

    :param header_slope_fname:
        A string containing the full file path name to be used for
        writing the header slope text file to disk.

    :return:
        None. Outputs are written to disk.
    """
    # Setup the geobox
    geobox = acquisition.gridded_geo_box()

    # Retrive the spheroid parameters
    # (used in calculating pixel size in metres per lat/lon)
    spheroid = setup_spheroid(geobox.crs.ExportToWkt())

    # Are we in projected or geographic space
    is_utm = not geobox.crs.IsGeographic()

    # Define Top, Bottom, Left, Right pixel margins
    pixel_margin = ImageMargins(margins)

    # Get the x and y pixel sizes
    _, y_origin = geobox.origin
    x_res, y_res = geobox.pixelsize
    dresx = x_res
    dresy = y_res

    # Get acquisition dimensions and add 1 pixel top, bottom, left & right
    cols, rows = geobox.get_shape_xy()
    ncol = cols + 2
    nrow = rows + 2

    # Define the index to read the DEM subset
    idx = (
        (pixel_margin.top - 1, -(pixel_margin.bottom - 1)),
        (pixel_margin.left - 1, -(pixel_margin.right - 1)),
    )

    with rasterio.open(dsm_fname) as dsm_ds:
        dsm_subset = as_array(
            dsm_ds.read(1, window=idx, masked=False), dtype=np.float32, transpose=True
        )

    # Define an array of latitudes
    # This will be ignored if is_utm == True
    alat = np.array(
        [y_origin - i * dresy for i in range(-1, nrow - 1)], dtype=np.float64
    )  # yes, I did mean float64.

    # Define the output arrays. These will be transposed upon input
    slope = np.zeros((rows, cols), dtype="float32")
    aspect = np.zeros((rows, cols), dtype="float32")

    slope_aspect(
        ncol,
        nrow,
        cols,
        rows,
        dresx,
        dresy,
        spheroid,
        alat,
        is_utm,
        dsm_subset,
        slope.transpose(),
        aspect.transpose(),
    )

    # Output the results
    write_img(slope, slope_out_fname, geobox=geobox, nodata=-999)
    write_img(aspect, aspect_out_fname, geobox=geobox, nodata=-999)

    if header_slope_fname:
        write_header_slope_file(header_slope_fname, pixel_margin, geobox)
