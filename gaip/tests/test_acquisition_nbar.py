import os
import unittest

import gaip

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

NBAR_DIR = os.path.join(
    DATA_DIR, "NBAR", "2009-01", "LS5_TM_NBAR_P54_GANBAR01-002_092_086_20090115"
)


class AcquisitionTest(unittest.TestCase):
    def test_load_acquisitions(self):
        acqs = gaip.acquisitions(NBAR_DIR)
        assert len(acqs) == 6

    def test_acquisition(self):
        acq = gaip.acquisitions(NBAR_DIR)[0]

        assert acq.band_name == "band1"
        assert acq.band_num == 1

        assert not hasattr(acq, "band1_sl_gain_change")


if __name__ == "__main__":
    unittest.main()
