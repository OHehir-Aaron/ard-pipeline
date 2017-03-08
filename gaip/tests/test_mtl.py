import datetime
import os
import unittest

import gaip

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

L5_MTL1 = os.path.join(DATA_DIR, "L5090081_08120090407_MTL.txt")
L5_MTL2 = os.path.join(DATA_DIR, "LT05_L1TP_095066_20100601_20170222_01_T1_MTL.txt")
L7_MTL1 = os.path.join(DATA_DIR, "L71090081_08120090415_MTL.txt")
L7_MTL2 = os.path.join(DATA_DIR, "LE07_L1TP_112066_20020218_20170221_01_T1_MTL.txt")
L8_MTL1 = os.path.join(DATA_DIR, "LO80900842013284ASA00_MTL.txt")
L8_MTL2 = os.path.join(DATA_DIR, "LO80900842013284ASA00_MTL.txt")


class TypeParserTest(unittest.TestCase):
    def test_integer(self):
        num = gaip.parse_type("1")
        assert num == 1

    def test_float(self):
        num = gaip.parse_type("1.0")
        assert num == 1.0

    def test_datetime(self):
        dt0 = gaip.parse_type("2013-11-07T01:42:41Z")
        dt1 = datetime.datetime(2013, 11, 7, 1, 42, 41)
        assert dt0 == dt1

    def test_quoted_datetime(self):
        dt0 = gaip.parse_type('"2013-11-07T01:42:41Z"')
        dt1 = datetime.datetime(2013, 11, 7, 1, 42, 41)
        assert dt0 == dt1

    def test_date(self):
        dt0 = gaip.parse_type("2013-11-07")
        dt1 = datetime.date(2013, 11, 7)
        assert dt0 == dt1

    def test_time(self):
        dt0 = gaip.parse_type("23:46:09.1442826Z")
        dt1 = datetime.time(23, 46, 9, 144282)
        assert dt0 == dt1

    def test_quoted_time(self):
        dt0 = gaip.parse_type('"23:46:09.1442826Z"')
        dt1 = datetime.time(23, 46, 9, 144282)
        assert dt0 == dt1

    def test_yes(self):
        resp = gaip.parse_type("Y")
        assert resp is True

    def test_no(self):
        resp = gaip.parse_type("N")
        assert resp is False

    def test_none(self):
        val = gaip.parse_type("NONE")
        assert val is None

    def test_str(self):
        s = gaip.parse_type("1adsd")
        assert s == "1adsd"


class Landsat5MTL1ParserTest(unittest.TestCase):
    def test_load(self):
        tree = gaip.load_mtl(L5_MTL1)
        assert len(tree) == 9
        assert tree.has_key("METADATA_FILE_INFO")
        assert tree.has_key("PRODUCT_METADATA")
        assert tree.has_key("MIN_MAX_RADIANCE")
        assert tree.has_key("MIN_MAX_PIXEL_VALUE")
        assert tree.has_key("PRODUCT_PARAMETERS")
        assert tree.has_key("CORRECTIONS_APPLIED")
        assert tree.has_key("PROJECTION_PARAMETERS")
        assert tree.has_key("UTM_PARAMETERS")


class Landsat5MTL2ParserTest(unittest.TestCase):
    def test_load(self):
        tree = gaip.load_mtl(L5_MTL2)
        assert len(tree) == 10
        assert tree.has_key("METADATA_FILE_INFO")
        assert tree.has_key("PRODUCT_METADATA")
        assert tree.has_key("MIN_MAX_RADIANCE")
        assert tree.has_key("MIN_MAX_REFLECTANCE")
        assert tree.has_key("MIN_MAX_PIXEL_VALUE")
        assert tree.has_key("PRODUCT_PARAMETERS")
        assert tree.has_key("PROJECTION_PARAMETERS")
        assert tree.has_key("IMAGE_ATTRIBUTES")
        assert tree.has_key("THERMAL_CONSTANTS")


class Landsat7MTL1ParserTest(unittest.TestCase):
    def test_load(self):
        tree = gaip.load_mtl(L7_MTL1)
        assert len(tree) == 8
        assert tree.has_key("METADATA_FILE_INFO")
        assert tree.has_key("PRODUCT_METADATA")
        assert tree.has_key("MIN_MAX_RADIANCE")
        assert tree.has_key("MIN_MAX_PIXEL_VALUE")
        assert tree.has_key("PRODUCT_PARAMETERS")
        assert tree.has_key("CORRECTIONS_APPLIED")
        assert tree.has_key("PROJECTION_PARAMETERS")
        assert tree.has_key("UTM_PARAMETERS")


class Landsat7MTL2ParserTest(unittest.TestCase):
    def test_load(self):
        tree = gaip.load_mtl(L7_MTL2)
        assert len(tree) == 10
        assert tree.has_key("METADATA_FILE_INFO")
        assert tree.has_key("PRODUCT_METADATA")
        assert tree.has_key("MIN_MAX_RADIANCE")
        assert tree.has_key("MIN_MAX_REFLECTANCE")
        assert tree.has_key("MIN_MAX_PIXEL_VALUE")
        assert tree.has_key("PRODUCT_PARAMETERS")
        assert tree.has_key("PROJECTION_PARAMETERS")
        assert tree.has_key("IMAGE_ATTRIBUTES")
        assert tree.has_key("THERMAL_CONSTANTS")


class Landsat8MTL1ParserTest(unittest.TestCase):
    def test_load(self):
        tree = gaip.load_mtl(L8_MTL1)
        assert len(tree) == 9
        assert tree.has_key("METADATA_FILE_INFO")
        assert tree.has_key("PRODUCT_METADATA")
        assert tree.has_key("IMAGE_ATTRIBUTES")
        assert tree.has_key("MIN_MAX_RADIANCE")
        assert tree.has_key("MIN_MAX_REFLECTANCE")
        assert tree.has_key("MIN_MAX_PIXEL_VALUE")
        assert tree.has_key("RADIOMETRIC_RESCALING")
        assert tree.has_key("TIRS_THERMAL_CONSTANTS")
        assert tree.has_key("PROJECTION_PARAMETERS")


class Landsat8MTL2ParserTest(unittest.TestCase):
    def test_load(self):
        tree = gaip.load_mtl(L8_MTL2)
        assert len(tree) == 9
        assert tree.has_key("METADATA_FILE_INFO")
        assert tree.has_key("PRODUCT_METADATA")
        assert tree.has_key("IMAGE_ATTRIBUTES")
        assert tree.has_key("MIN_MAX_RADIANCE")
        assert tree.has_key("MIN_MAX_REFLECTANCE")
        assert tree.has_key("MIN_MAX_PIXEL_VALUE")
        assert tree.has_key("RADIOMETRIC_RESCALING")
        assert tree.has_key("TIRS_THERMAL_CONSTANTS")
        assert tree.has_key("PROJECTION_PARAMETERS")


if __name__ == "__main__":
    unittest.main()
