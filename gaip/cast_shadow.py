#!/usr/bin/env python

from gaip import calculate_angles as ca
from gaip import read_img, run_castshadow, write_img


def calculate_cast_shadow(
    acquisition,
    DSM_fname,
    buffer,
    block_height,
    block_width,
    view_angle_fname,
    azimuth_angle_fname,
    outfname,
):
    """:param acquisition:
        An instance of an acquisition object.

    :param DSM_fname:
        A string containing the full file path name to the Digital
        Surface Model to be used in deriving the surface angles.

    :param buffer:
        An object with members top, bottom, left and right giving the
        size of the buffer (in pixels) which have been added to the
        corresponding sides of DSM.

    :param block_height:
        The height of the sub-array to be embedded (see notes above).

    :param block_width:
        The width of the sub-array to be embedded (see notes above).

    :param view_angle_fname:
        A string containing the full file path name to the view
        angle image. i.e. solar zenith angle or the the view angle to
        the satellite.

    :param azimuth_angle_fname:
        A string containing the full file path name to the azimuth
        angle image. i.e. Solar azimuth angle or the satellite azimuth
        angle.

    :param outfname:
        A string containing the full file path name to be used for
        creating the output image.

    :return:
        None. The result is written to disk.
    """
    # Setup the geobox
    geobox = acquisition.gridded_geo_box()

    # Retrive the spheroid parameters
    # (used in calculating pixel size in metres per lat/lon)
    spheroid = ca.setup_spheroid(geobox.crs.ExportToWkt())

    # Read the DSM and angle arrays into memory
    DSM = read_img(DSM_fname)
    view_angle = read_img(view_angle_fname)
    azimuth_angle = read_img(azimuth_angle_fname)

    # Define Top, Bottom, Left, Right pixel buffers
    pixel_buf = Buffers(buffer)

    # Compute the cast shadow mask
    mask = run_castshadow(
        acquisition,
        DSM,
        view_angle,
        azimuth_angle,
        pixel_buf,
        block_height,
        block_width,
        spheroid,
    )

    # Output the result to disk
    write_img(mask, outfname, geobox=geobox, nodata=-999)
