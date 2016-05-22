"""Shadow Casting
--------------.
"""

import rasterio

from gaip import ImageMargins, run_castshadow, setup_spheroid, write_img


def calculate_cast_shadow(
    acquisition,
    dsm_fname,
    margins,
    block_height,
    block_width,
    view_angle_fname,
    azimuth_angle_fname,
    outfname,
):
    """:param acquisition:
        An instance of an acquisition object.

    :param dsm_fname:
        A string containing the full file path name to the Digital
        Surface Model to be used in deriving the surface angles.

    :param margins:
        An object with members top, bottom, left and right giving the
        size of the margins (in pixels) which have been added to the
        corresponding sides of dsm.

    :param block_height:
        The height (rows) of the window/submatrix used in the cast
        shadow algorithm.

    :param block_width:
        The width (rows) of the window/submatrix used in the cast
        shadow algorithm.

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
    spheroid = setup_spheroid(geobox.crs.ExportToWkt())

    # Read the dsm and angle arrays into memory
    with rasterio.open(dsm_fname) as ds:
        dsm = ds.read(1)
    with rasterio.open(view_angle_fname) as ds:
        view_angle = ds.read(1)
    with rasterio.open(azimuth_angle_fname) as ds:
        azimuth_angle = ds.read(1)

    # Define Top, Bottom, Left, Right pixel margins
    pixel_buf = ImageMargins(margins)

    # Compute the cast shadow mask
    mask = run_castshadow(
        acquisition,
        dsm,
        view_angle,
        azimuth_angle,
        pixel_buf,
        block_height,
        block_width,
        spheroid,
    )

    # Output the result to disk
    write_img(
        mask,
        outfname,
        fmt="GTiff",
        geobox=geobox,
        nodata=-999,
        compress="deflate",
        options={"zlevel": 1},
    )
