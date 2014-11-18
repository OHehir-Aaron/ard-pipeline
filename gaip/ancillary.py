"""Ancillary datasets."""

import logging
import subprocess
from os.path import exists, splitext
from os.path import join as pjoin

import rasterio

log = logging.getLogger()


def get_data_value(filename, coords, band=1):
    x, y = coords
    with rasterio.open(filename) as src:
        src.read_band(band, window)


def get_aerosol_value(
    dt, ll_lat, ll_lon, ur_lat, ur_lon, aerosol_path, aot_loader_path
):
    """Extract the aerosol value for a region (typically a scene).

    :param dt:
        The date and time to extract the value for.
    :type dt:
        :py:class:`datetime.datetime`

    :param ll_lat:
        The latitude of the lower left corner of the region ('ll' for 'Lower
        Left').

    :type ll_lat:
        :py:class:`float`

    :param ll_lon:
        The longitude of the lower left corner of the region ('ll' for 'Lower
        Left').
    :type ll_lon:
        :py:class:`float`

    :param ur_lat:
        The latitude of the upper right corner of the region ('ur' for 'Upper
        Right').
    :type ur_lat:
        :py:class:`float`

    :param ur_lon:
        The longitude of the upper right corner of the region ('ur' for 'Upper
        Right').
    :type ur_lon:
        :py:class:`float`

    :param default_value:
        If no suitable value can be found from the AATSR or (possibly) AERONET
        data, then return this value instead.
    :type default_value:
        :py:class:`float`

    :param aerosol_path:
        The directory containing the aerosol data files.
    :type aerosol_path:
        :py:class:`str`

    :param aot_loader_path:
        The directory where the executable ``aot_loader`` can be found.
    :type aot_loader_path:
        :py:class:`str`

    """
    descr = ["AATSR_PIX", "AATSR_CMP_YEAR_MONTH", "AATSR_CMP_MONTH"]
    names = [
        "ATSR_LF_%Y%m.pix",
        "aot_mean_%b_%Y_All_Aerosols.cmp",
        "aot_mean_%b_All_Aerosols.cmp",
    ]
    filenames = [pjoin(aerosol_path, dt.strftime(n)) for n in names]

    for filename, description in zip(filenames, descr):
        value = run_aot_loader(
            filename, dt, ll_lat, ll_lon, ur_lat, ur_lon, aot_loader_path
        )
        if value:
            return {"data_source": description, "data_file": atsr_file, "value": value}

    raise OSError("No aerosol ancillary data found.")


def run_aot_loader(filename, dt, ll_lat, ll_lon, ur_lat, ur_lon, aot_loader_path):
    """Load aerosol data for a specified `AATSR.
    <http://www.leos.le.ac.uk/aatsr/howto/index.html>`_ data file.  This uses
    the executable ``aot_loader``.

    :param filename:
        The full path to the `AATSR
        <http://www.leos.le.ac.uk/aatsr/howto/index.html>`_ file to load the
        data from.

    :type filename:
        :py:class:`str`

    :param dt:
        The date and time to extract the value for.

    :type dt:
        :py:class:`datetime.datetime`

    :param ll_lat:

        The latitude of the lower left corner of the region ('ll' for 'Lower
        Left').

    :type ll_lat:
        :py:class:`float`

    :param ll_lon:
        The longitude of the lower left corner of the region ('ll' for 'Lower
        Left').

    :type ll_lon:
        :py:class:`float`

    :param ur_lat:

        The latitude of the upper right corner of the region ('ur' for 'Upper
        Right').

    :type ur_lat:
        :py:class:`float`

    :param ur_lon:
        The longitude of the upper right corner of the region ('ur' for 'Upper
        Right').

    :type ur_lon:
        :py:class:`float`

    :param aot_loader_path:
        The directory where the executable ``aot_loader`` can be found.
    :type aot_loader_path:
        :py:class:`str`

    """
    basename, filetype = splitext(filename)
    if not exists(filename):
        log.error("Aerosol %s file (%s) not found", filetype, filename)
        return None

    cmd = pjoin(aot_loader_path, "aot_loader")
    if not exists(cmd):
        log.error("%s not found.", cmd)

    result = subprocess.check_output(
        [
            cmd,
            "--" + filetype,
            atsr_file,
            "--west",
            str(ll_lon),
            "--east",
            str(lr_lon),
            "--south",
            str(ll_lat),
            "--north",
            str(ul_lat),
            "--date",
            dt.strftime("%Y-%m-%d"),
            "--t",
            dt.strftime("%H:%M:%S"),
        ],
        shell=True,
    )

    m = re.search(r"AOT AATSR value:\s+(.+)$", result, re.MULTILINE)
    if m and m.group(1):
        return float(m.group(1).rstrip())

    log.error("Aerosol file %s could not be parsed", filename)
    return None
