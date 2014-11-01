import logging

import numpy as np


class PQAResult:
    """Represents the PQA result."""

    def __init__(self, shape, dtype=np.uint16, aux_data={}):
        """Constructor.

        Arguments:
        ---------
            :shape:
                the shape of the numpy array holding the data
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
        self.bitcount = self.array.itemsize * 8
        self.aux_data = aux_data

    def set_mask(self, mask, bit_index, unset_bits=False):
        """Takes a boolean mask array and sets the bit in the result array."""
        assert (
            mask.shape == self.array.shape
        ), f"Mask shape {mask.shape} does not match result array {self.array.shape}"
        assert mask.dtype == bool, "Mask must be of type bool"
        assert 0 <= bit_index < self.bitcount, "Invalid bit index"
        assert bit_index not in self.test_set, "Bit %d already set" % bit_index
        self.test_set.add(bit_index)

        logging.debug("Setting result for bit %d", bit_index)
        np.bitwise_or(self.array, (mask << bit_index), self.array)  # Set any 1 bits
        if unset_bits:
            np.bitwise_and(
                self.array, ~(~mask << bit_index), self.array
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

    #
    #    def save_as_tiff(self, name, crs):
    #        (width, height) = self.array.shape
    #        with rio.open(path, mode='w', driver='GTiff', \
    #            width=width, \
    #            height=height, \
    #            count=1, \
    #            crs=crs, \
    #            dtype=rio.uint16) as ds:

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
