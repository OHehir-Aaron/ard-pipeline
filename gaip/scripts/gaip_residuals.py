#!/usr/bin/env python

"""A recursive utility that compares and evaluates datasets within a
reference file, with the equivalent dataset from a test file.
"""

import argparse
from functools import partial
from posixpath import basename as pbasename
from posixpath import join as ppjoin

import h5py
import numpy as np
from idl_functions import histogram

from gaip.geobox import GriddedGeoBox
from gaip.hdf5 import dataset_compression_kwargs, write_h5_image, write_h5_table


def distribution(data):
    """Evaluates the distribution of a `NumPy` array. Floating point
    arrays will use 256 bins, while integer arrays will use
    a binsize of 1.
    """
    if data.dtype.name in ["float", "float32", "float64"]:
        try:
            h = histogram(data, omin="omin", omax="omax", locations="loc", nbins=256)
        except ValueError:
            h = {}
            h["histogram"] = np.zeros((256), dtype="uint32")
            h["omin"] = 0
            h["omax"] = 0
            h["loc"] = np.zeros((256), dtype=data.dtype.name)
            h["histogram"][0] = data.size
    else:
        h = histogram(data, omin="omin", omax="omax", locations="loc")

    return h


def residuals(ref_fid, test_fid, out_fid, compression, pathname, save_inputs):
    """ """
    pathname = pathname.decode("utf-8")
    if pathname in test_fid:
        ref_dset = ref_fid[pathname]
        if ref_dset.attrs["CLASS"] == "IMAGE":
            test_dset = test_fid[pathname]

            # ignore no data values for the time being
            residual = ref_dset[:] - test_dset
            min_residual = residual.min()
            max_residual = residual.max()
            pct_difference = (residual != 0).sum() / residual.size * 100

            geobox = GriddedGeoBox.from_dataset(ref_dset)
            chunks = ref_dset.chunks
            kwargs = dataset_compression_kwargs(compression=compression, chunks=chunks)

            # output residual
            attrs = {}
            attrs["crs_wkt"] = geobox.crs.ExportToWkt()
            attrs["geotransform"] = (geobox.transform.to_gdal(),)
            attrs["Description"] = "Residual"
            attrs["min_residual"] = min_residual
            attrs["max_residual"] = max_residual
            attrs["percent_difference"] = pct_difference

            base_dname = pbasename(pathname)
            group_name = ref_dset.parent.name.strip("/")
            dname = ppjoin("difference-data", group_name, base_dname)
            write_h5_image(residual, dname, out_fid, attrs=attrs, **kwargs)

            if save_inputs:
                # output the reference data
                kwargs["attrs"] = {k: v for k, v in ref_dset.attrs.items()}
                dname = ppjoin("reference-data", group_name, base_dname)
                write_h5_image(ref_dset[:], dname, out_fid, **kwargs)

                # output the test data
                kwargs["attrs"] = {k: v for k, v in test_dset.attrs.items()}
                dname = ppjoin("test-data", group_name, base_dname)
                write_h5_image(test_dset[:], dname, out_fid, **kwargs)

            # residuals distribution
            h = distribution(residual)
            hist = h["histogram"]

            attrs = {}
            attrs["Description"] = "Frequency distribution of the residuals"
            attrs["omin"] = h["omin"]
            attrs["omax"] = h["omax"]
            dtype = np.dtype(
                [
                    ("bin_locations", h["loc"].dtype.name),
                    ("residuals_distribution", hist.dtype.name),
                ]
            )
            table = np.zeros(hist.shape, dtype=dtype)
            table["bin_locations"] = h["loc"]
            table["residuals_distribution"] = hist

            # output
            dname = ppjoin("frequency-distribution", group_name, base_dname)
            write_h5_table(table, dname, out_fid, compression=compression, attrs=attrs)

            # cumulative distribution
            h = distribution(np.abs(residual))
            hist = h["histogram"]
            cdf = np.cumsum(hist / hist.sum())

            attrs = {}
            attrs["Description"] = "Cumulative distribution of the residuals"
            attrs["omin"] = h["omin"]
            attrs["omax"] = h["omax"]
            attrs["90_percent"] = h["loc"][np.searchsorted(cdf, 0.9)]
            attrs["99_percent"] = h["loc"][np.searchsorted(cdf, 0.99)]
            dtype = np.dtype(
                [
                    ("bin_locations", h["loc"].dtype.name),
                    ("cumulative_distribution", cdf.dtype.name),
                ]
            )
            table = np.zeros(cdf.shape, dtype=dtype)
            table["bin_locations"] = h["loc"]
            table["residuals_distribution"] = cdf

            # output
            dname = ppjoin("cumulative-distribution", group_name, base_dname)
            write_h5_table(table, dname, out_fid, compression=compression, attrs=attrs)
        else:
            print("Only processing images at this time: Skipping")
    else:
        print(f"{pathname} not found in test file: Skipping")


def run(reference_fname, test_fname, out_fname, compression):
    """Run dataset conversion tree."""
    # note: lower level h5py access is required in order to visit links
    with h5py.File(reference_fname, "r") as ref_fid:
        with h5py.File(test_fname, "r") as test_fid:
            with h5py.File(out_fname, "w") as out_fid:
                root = h5py.h5g.open(ref_fid.id, b"/")
                root.links.visit(
                    partial(residuals, ref_fid, test_fid, out_fid, compression)
                )


def _parser():
    """Argument parser."""
    description = "Extracts HDF5 datasets to either GeoTiff or CSV."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--test_filename",
        required=True,
        help=("The filename of the file containing the test " "datasets."),
    )
    parser.add_argument(
        "--reference_filename",
        required=True,
        help=("The filename of the file containing the " "reference datasets."),
    )
    parser.add_argument(
        "--out_filename",
        required=True,
        help=("The filename of the file to contain the " "results."),
    )
    parser.add_argument(
        "--compression", default="lzf", help="The comression filter to use."
    )
    parser.add_argument(
        "--save-inputs",
        action="store_true",
        help=(
            "Save the reference and test datasets "
            "alongside the resdiual/difference datasets."
        ),
    )

    return parser


def main():
    """Main execution."""
    parser = _parser()
    args = parser.parse_args()
    run(
        args.test_filename,
        args.reference_filename,
        args.out_filename,
        args.compression,
        args.save_inputs,
    )
