#!/usr/bin/env python

"""A module to contain information collected during the Pixel Quality
Assessment.
"""

import logging
import os

import h5py
import numpy as np
import rasterio as rio

from gaip.hdf5 import dataset_compression_kwargs, write_h5_image


def can_pq(scene):
    """A simple test to check if we can process a scene through the
    pq pipeline.

    :param scene:
        An `AcquisitionsContainer`.

    :return:
        True if the scene can be processed through PQ, else False.
    """
    supported = ["LANDSAT_7", "LANDSAT_7", "LANDSAT_8"]
    acq = scene.get_acquisitions()[0]
    return acq.spacecraft_id in supported


class PQAResult:
    """Represents the PQA result."""

    def __init__(self, shape, aGriddedGeoBox, dtype=np.uint16, aux_data={}):
        """Constructor.

        Arguments:
        ---------
            :shape:
                the shape of the numpy array holding the data
            :aGriddedGeoBox:
                an instance of class GriddedGeoBox providing the
                spatial location, scale and coordinate refernced system
                for this PQAResult
            :dtype:
                the datatype of the array
            :aux_data:
                a dictionary hold auxillary data associated with
                the PQAResult object. These may represent metadata
                elements that could be written to the final output
                file

        """
        assert shape is not None

        self.test_set = set()
        self.array = np.zeros(shape, dtype=dtype)
        self.dtype = dtype
        self.bitcount = self.array.itemsize * 8
        self.aux_data = aux_data
        self.geobox = aGriddedGeoBox

    def set_mask(self, mask, bit_index, unset_bits=False):
        """Takes a boolean mask array and sets the bit in the result array."""
        assert (
            mask.shape == self.array.shape
        ), f"Mask shape {mask.shape} does not match result array {self.array.shape}"
        assert mask.dtype == bool, "Mask must be of type bool"
        assert 0 <= bit_index < self.bitcount, "Invalid bit index"
        assert bit_index not in self.test_set, "Bit %d already set" % bit_index
        self.test_set.add(bit_index)

        c = sum(sum(mask))
        logging.debug("Setting result for bit %d, masking %d pixels" % (bit_index, c))
        np.bitwise_or(
            self.array, (mask << bit_index).astype(self.dtype), self.array
        )  # Set any 1 bits
        if unset_bits:
            np.bitwise_and(
                self.array, ~(~mask << bit_index).astype(self.dtype), self.array
            )  # Clear any 0 bits

    def get_mask(self, bit_index):
        """Return boolean mask for specified bit index."""
        assert 0 <= bit_index < self.bitcount, "Invalid bit index"
        assert bit_index in self.test_set, "Test %d not run" % bit_index
        return (self.array & (1 << bit_index)) > 0

    def add_to_aux_data(self, new_data={}):
        """Add the elements in the supplied dictionary to this objects
        aux_data property.
        """
        self.aux_data.update(new_data)

    def save_as_tiff(self, path, crs=None):
        """Save the PQ result and attribute information in a GeoTiff."""
        os.makedirs(os.path.dirname(path))
        (height, width) = self.array.shape
        with rio.open(
            path,
            mode="w",
            driver="GTiff",
            width=width,
            height=height,
            count=1,
            crs=self.geobox.crs.ExportToWkt(),
            transform=self.geobox.transform,
            dtype=rio.uint16,
        ) as ds:
            ds.write_band(1, self.array)
            ds.update_tags(1, **self.aux_data)

    def save_as_h5_dataset(self, out_fname, compression):
        """Save the PQ result and attribute information in a HDF5
        `IMAGE` Class dataset.
        """
        with h5py.File(out_fname) as fid:
            chunks = (1, self.geobox.x_size())
            kwargs = dataset_compression_kwargs(compression=compression, chunks=chunks)
            attrs = self.aux_data.copy()
            attrs["crs_wkt"] = self.geobox.crs.ExportToWkt()
            attrs["geotransform"] = self.geobox.transform.to_gdal()
            write_h5_image(
                self.array, "pixel-quality-assessment", fid, attrs=attrs, **kwargs
            )

    @property
    def test_list(self):
        """Returns a sorted list of all bit indices which have been set."""
        return sorted(self.test_set)

    @property
    def test_string(self):
        """Returns a string showing all bit indices which have been set."""
        bit_list = ["0"] * self.bitcount
        for test_index in self.test_set:
            bit_list[test_index] = "1"  # Show bits as big-endian
            # bit_list[15 - test_index] = '1' # Show bits as little-endian

        return "".join(bit_list)
