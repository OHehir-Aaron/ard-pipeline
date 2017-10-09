import datetime
import unittest
from os.path import abspath, dirname
from os.path import join as pjoin

from gaip.acquisition import Landsat8Acquisition, LandsatAcquisition, acquisitions
from gaip.constants import BandType

DATA_DIR = pjoin(dirname(abspath(__file__)), "data")

# TODO; update the scenes with resampled versions
L5_MTL1 = pjoin(DATA_DIR, "LANDSAT5", "L5090081_08120090407_MTL.txt")
L5_MTL2 = pjoin(
    DATA_DIR, "LANDSAT5", "LT05_L1TP_095066_20100601_20170222_01_T1_MTL.txt"
)
L7_MTL1 = pjoin(DATA_DIR, "LANDSAT7", "L71090081_08120090415_MTL.txt")
L7_MTL2 = pjoin(
    DATA_DIR, "LANDSAT7", "LE07_L1TP_112066_20020218_20170221_01_T1_MTL.txt"
)
L8_MTL1 = pjoin(DATA_DIR, "LANDSAT8", "LO80900842013284ASA00_MTL.txt")
L8_MTL2 = pjoin(DATA_DIR, "LANDSAT8", "LC80990842016277LGN00_MTL.txt")


class AcquisitionLoadMtlTest(unittest.TestCase):
    def test_load_acquisitions_l5_mtl1(self):
        acq = acquisitions(L5_MTL1).get_acquisitions()
        assert len(acq) == 7

    def test_load_acquisitions_l5_mtl2(self):
        acq = acquisitions(L5_MTL2).get_acquisitions()
        assert len(acq) == 8

    def test_load_acquisitions_l7_mtl1(self):
        acq = acquisitions(L7_MTL1).get_acquisitions()
        assert len(acq) == 9

    def test_load_acquisitions_l7_mtl2(self):
        acq = acquisitions(L7_MTL2).get_acquisitions()
        assert len(acq) == 10

    def test_load_acquisitions_l8_mtl1(self):
        acq = acquisitions(L8_MTL1).get_acquisitions()
        assert len(acq) == 10

    def test_load_acquisitions_l8_mtl2(self):
        acq = acquisitions(L8_MTL2).get_acquisitions()
        assert len(acq) == 12


class AcquisitionsContainerTest(unittest.TestCase):
    def test_groups_l5_mtl1(self):
        scene = acquisitions(L5_MTL1)
        assert len(scene.groups) == 1

    def test_groups_l5_mtl2(self):
        scene = acquisitions(L5_MTL2)
        assert len(scene.groups) == 1

    def test_groups_l7_mtl1(self):
        scene = acquisitions(L7_MTL1)
        assert len(scene.groups) == 1

    def test_groups_l7_mtl2(self):
        scene = acquisitions(L7_MTL2)
        assert len(scene.groups) == 1

    def test_groups_l8_mtl1(self):
        scene = acquisitions(L8_MTL1)
        assert len(scene.groups) == 1

    def test_granules_ls5_mtl1(self):
        scene = acquisitions(L5_MTL1)
        assert scene.granules[0] is None

    def test_granules_ls5_mtl2(self):
        scene = acquisitions(L5_MTL2)
        assert scene.granules[0] is None

    def test_granules_ls7_mtl1(self):
        scene = acquisitions(L7_MTL1)
        assert scene.granules[0] is None

    def test_granules_ls7_mtl2(self):
        scene = acquisitions(L7_MTL2)
        assert scene.granules[0] is None

    def test_granules_ls8_mtl1(self):
        scene = acquisitions(L8_MTL1)
        assert scene.granules[0] is None

    def test_granules_ls8_mtl2(self):
        scene = acquisitions(L8_MTL2)
        assert scene.granules[0] is None


class Landsat5Mtl1AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.acqs = acquisitions(L5_MTL1).get_acquisitions()

    def test_type(self):
        for acq in self.acqs:
            assert isinstance(acq, LandsatAcquisition)

    def test_band_type(self):
        assert self.acqs[0].band_type == BandType.Reflective
        assert self.acqs[1].band_type == BandType.Reflective
        assert self.acqs[2].band_type == BandType.Reflective
        assert self.acqs[3].band_type == BandType.Reflective
        assert self.acqs[4].band_type == BandType.Reflective
        assert self.acqs[5].band_type == BandType.Thermal
        assert self.acqs[6].band_type == BandType.Reflective

    def test_acquisition_datetime(self):
        for acq in self.acqs:
            assert acq.acquisition_datetime == datetime.datetime(
                2009, 4, 7, 23, 36, 9, 88050
            )

    def test_min_radiance_band1(self):
        assert self.acqs[0].min_radiance == -1.52

    def test_max_radiance_band1(self):
        assert self.acqs[0].max_radiance == 193.0

    def test_min_quantize_band1(self):
        assert self.acqs[0].min_quantize == 1.0

    def test_max_quantize_band1(self):
        assert self.acqs[0].max_quantize == 255.0

    def test_sun_azimuth(self):
        assert self.acqs[0].sun_azimuth == 48.1772887

    def test_sun_elevation(self):
        assert self.acqs[0].sun_elevation == 39.4014194

    def test_gain(self):
        self.assertAlmostEqual(self.acqs[0].gain, 0.7658267716535433)

    def test_bias(self):
        self.assertAlmostEqual(self.acqs[0].bias, -2.2858267716535465)

    def test_sensor_id(self):
        for acq in self.acqs:
            assert acq.sensor_id == "TM"

    def test_platform_id(self):
        for acq in self.acqs:
            assert acq.platform_id == "LANDSAT_5"


class Landsat5Mtl2AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.acqs = acquisitions(L5_MTL2).get_acquisitions()

    def test_type(self):
        for acq in self.acqs:
            assert isinstance(acq, LandsatAcquisition)

    def test_band_type(self):
        assert self.acqs[0].band_type == BandType.Reflective
        assert self.acqs[1].band_type == BandType.Reflective
        assert self.acqs[2].band_type == BandType.Reflective
        assert self.acqs[3].band_type == BandType.Reflective
        assert self.acqs[4].band_type == BandType.Reflective
        assert self.acqs[5].band_type == BandType.Thermal
        assert self.acqs[6].band_type == BandType.Reflective
        assert self.acqs[7].band_type == BandType.Quality

    def test_acquisition_datetime(self):
        for acq in self.acqs:
            assert acq.acquisition_datetime == datetime.datetime(
                2010, 6, 1, 0, 4, 43, 174081
            )

    def test_min_radiance_band1(self):
        assert self.acqs[0].min_radiance == -1.52

    def test_max_radiance_band1(self):
        assert self.acqs[0].max_radiance == 193.0

    def test_min_quantize_band1(self):
        assert self.acqs[0].min_quantize == 1.0

    def test_max_quantize_band1(self):
        assert self.acqs[0].max_quantize == 255.0

    def test_sun_azimuth(self):
        assert self.acqs[0].sun_azimuth == 43.24285506

    def test_sun_elevation(self):
        assert self.acqs[0].sun_elevation == 47.53234255

    def test_gain(self):
        self.assertAlmostEqual(self.acqs[0].gain, 0.7658267716535433)

    def test_bias(self):
        self.assertAlmostEqual(self.acqs[0].bias, -2.2858267716535465)

    def test_sensor_id(self):
        for acq in self.acqs:
            assert acq.sensor_id == "TM"

    def test_platform_id(self):
        for acq in self.acqs:
            assert acq.spacecraft_id == "LANDSAT_5"


class Landsat7Mtl1AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.acqs = acquisitions(L7_MTL1).get_acquisitions()

    def test_type(self):
        for acq in self.acqs:
            assert isinstance(acq, LandsatAcquisition)

    def test_band_type(self):
        assert self.acqs[0].band_type == BandType.Reflective
        assert self.acqs[1].band_type == BandType.Reflective
        assert self.acqs[2].band_type == BandType.Reflective
        assert self.acqs[3].band_type == BandType.Reflective
        assert self.acqs[4].band_type == BandType.Reflective
        assert self.acqs[5].band_type == BandType.Thermal
        assert self.acqs[6].band_type == BandType.Thermal
        assert self.acqs[7].band_type == BandType.Reflective
        assert self.acqs[8].band_type == BandType.Panchromatic

    def test_acquisition_datetime(self):
        for acq in self.acqs:
            assert acq.acquisition_datetime == datetime.datetime(
                2009, 4, 15, 23, 39, 26, 931462
            )

    def test_min_radiance_band1(self):
        assert self.acqs[0].min_radiance == -6.2

    def test_max_radiance_band1(self):
        assert self.acqs[0].max_radiance == 191.6

    def test_min_quantize_band1(self):
        assert self.acqs[0].min_quantize == 1.0

    def test_max_quantize_band1(self):
        assert self.acqs[0].max_quantize == 255.0

    def test_sun_azimuth(self):
        assert self.acqs[0].sun_azimuth == 44.5023798

    def test_sun_elevation(self):
        assert self.acqs[0].sun_elevation == 37.9491813

    def test_gain(self):
        self.assertAlmostEqual(self.acqs[0].gain, 0.7787401574803149)

    def test_bias(self):
        self.assertAlmostEqual(self.acqs[0].bias, -6.978740157480303)

    def test_sensor_id(self):
        for acq in self.acqs:
            assert acq.sensor_id == "ETM+"

    def test_platform_id(self):
        for acq in self.acqs:
            assert acq.platform_id == "LANDSAT_7"


class Landsat7Mtl2AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.acqs = acquisitions(L7_MTL2).get_acquisitions()

    def test_type(self):
        for acq in self.acqs:
            assert isinstance(acq, LandsatAcquisition)

    def test_band_type(self):
        assert self.acqs[0].band_type == BandType.Reflective
        assert self.acqs[1].band_type == BandType.Reflective
        assert self.acqs[2].band_type == BandType.Reflective
        assert self.acqs[3].band_type == BandType.Reflective
        assert self.acqs[4].band_type == BandType.Reflective
        assert self.acqs[5].band_type == BandType.Thermal
        assert self.acqs[6].band_type == BandType.Thermal
        assert self.acqs[7].band_type == BandType.Reflective
        assert self.acqs[8].band_type == BandType.Panchromatic
        assert self.acqs[9].band_type == BandType.Quality

    def test_acquisition_datetime(self):
        for acq in self.acqs:
            assert acq.acquisition_datetime == datetime.datetime(
                2002, 2, 18, 1, 47, 55, 878250
            )

    def test_min_radiance_band1(self):
        assert self.acqs[0].min_radiance == -6.2

    def test_max_radiance_band1(self):
        assert self.acqs[0].max_radiance == 191.6

    def test_min_quantize_band1(self):
        assert self.acqs[0].min_quantize == 1.0

    def test_max_quantize_band1(self):
        assert self.acqs[0].max_quantize == 255.0

    def test_sun_azimuth(self):
        assert self.acqs[0].sun_azimuth == 98.1470638

    def test_sun_elevation(self):
        assert self.acqs[0].sun_elevation == 55.95447861

    def test_gain(self):
        self.assertAlmostEqual(self.acqs[0].gain, 0.7787401574803149)

    def test_bias(self):
        self.assertAlmostEqual(self.acqs[0].bias, -6.978740157480303)

    def test_sensor_id(self):
        for acq in self.acqs:
            assert acq.sensor_id == "ETM+"

    def test_platform_id(self):
        for acq in self.acqs:
            assert acq.platform_id == "LANDSAT_7"


class Landsat8Mtl1AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.acqs = acquisitions(L8_MTL1).get_acquisitions()

    def test_type(self):
        for acq in self.acqs:
            assert isinstance(acq, Landsat8Acquisition)

    def test_band_type(self):
        assert self.acqs[0].band_type == BandType.Reflective
        assert self.acqs[1].band_type == BandType.Reflective
        assert self.acqs[2].band_type == BandType.Reflective
        assert self.acqs[3].band_type == BandType.Reflective
        assert self.acqs[4].band_type == BandType.Reflective
        assert self.acqs[5].band_type == BandType.Reflective
        assert self.acqs[6].band_type == BandType.Reflective
        assert self.acqs[7].band_type == BandType.Panchromatic
        assert self.acqs[8].band_type == BandType.Atmosphere
        assert self.acqs[9].band_type == BandType.Quality

    def test_acquisition_datetime(self):
        for acq in self.acqs:
            assert acq.acquisition_datetime == datetime.datetime(
                2013, 10, 11, 23, 52, 10, 108347
            )

    def test_min_radiance_band1(self):
        assert self.acqs[0].min_radiance == -64.75256

    def test_max_radiance_band1(self):
        assert self.acqs[0].max_radiance == 784.11609

    def test_min_quantize_band1(self):
        assert self.acqs[0].min_quantize == 1.0

    def test_max_quantize_band1(self):
        assert self.acqs[0].max_quantize == 65535

    def test_sun_azimuth(self):
        assert self.acqs[0].sun_azimuth == 50.86088724

    def test_sun_elevation(self):
        assert self.acqs[0].sun_elevation == 52.25003864

    def test_gain(self):
        self.assertAlmostEqual(self.acqs[0].gain, 0.012953)

    def test_bias(self):
        self.assertAlmostEqual(self.acqs[0].bias, -64.76551)

    def test_sensor_id(self):
        for acq in self.acqs:
            assert acq.sensor_id == "OLI"

    def test_platform_id(self):
        for acq in self.acqs:
            assert acq.platform_id == "LANDSAT_8"


class Landsat8Mtl2AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.acqs = acquisitions(L8_MTL2).get_acquisitions()

    def test_type(self):
        for acq in self.acqs:
            assert isinstance(acq, Landsat8Acquisition)

    def test_band_type(self):
        assert self.acqs[0].band_type == BandType.Reflective
        assert self.acqs[1].band_type == BandType.Thermal
        assert self.acqs[2].band_type == BandType.Thermal
        assert self.acqs[3].band_type == BandType.Reflective
        assert self.acqs[4].band_type == BandType.Reflective
        assert self.acqs[5].band_type == BandType.Reflective
        assert self.acqs[6].band_type == BandType.Reflective
        assert self.acqs[7].band_type == BandType.Reflective
        assert self.acqs[8].band_type == BandType.Reflective
        assert self.acqs[9].band_type == BandType.Panchromatic
        assert self.acqs[10].band_type == BandType.Atmosphere
        assert self.acqs[11].band_type == BandType.Quality

    def test_acquisition_datetime(self):
        for acq in self.acqs:
            assert acq.acquisition_datetime == datetime.datetime(
                2016, 10, 3, 0, 46, 10, 530409
            )

    def test_min_radiance_band1(self):
        assert self.acqs[0].min_radiance == -62.69242

    def test_max_radiance_band1(self):
        assert self.acqs[0].max_radiance == 759.16895

    def test_min_max_radiance_band2(self):
        assert self.acqs[3].min_radiance == -64.1978
        assert self.acqs[3].max_radiance == 777.39825

    def test_min_max_radiance_band3(self):
        assert self.acqs[4].min_radiance == -59.15772
        assert self.acqs[4].max_radiance == 716.36584

    def test_min_quantize_band1(self):
        assert self.acqs[0].min_quantize == 1.0

    def test_max_quantize_band1(self):
        assert self.acqs[0].max_quantize == 65535

    def test_sun_azimuth(self):
        assert self.acqs[0].sun_azimuth == 48.79660801

    def test_sun_elevation(self):
        assert self.acqs[0].sun_elevation == 48.83189159

    def test_gain(self):
        self.assertAlmostEqual(self.acqs[0].gain, 0.012541)

    def test_bias(self):
        self.assertAlmostEqual(self.acqs[0].bias, -62.70496)

    def test_sensor_id(self):
        for acq in self.acqs:
            assert acq.sensor_id == "OLI_TIRS"

    def test_platform_id(self):
        for acq in self.acqs:
            assert acq.platform_id == "LANDSAT_8"


if __name__ == "__main__":
    unittest.main()
