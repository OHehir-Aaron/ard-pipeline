#!/bin/env python

import unittest

import affine
import gdal
import h5py
import rasterio as rio
from osgeo import gdal

from gaip import unittesting_tools as ut
from gaip.geobox import GriddedGeoBox

affine.EPSILON = 1e-9
affine.EPSILON2 = 1e-18


def getFlindersIsletGGB():
    flindersOrigin = (150.927659, -34.453309)
    flindersCorner = (150.931697, -34.457915)

    return GriddedGeoBox.from_corners(flindersOrigin, flindersCorner)


class TestGriddedGeoBox(unittest.TestCase):
    def test_create_shape(self):
        scale = 0.00025
        shape = (3, 2)
        origin = (150.0, -34.0)
        (shape[1] * scale + origin[0], origin[1] - shape[0] * scale)
        ggb = GriddedGeoBox(shape, origin)
        assert shape == ggb.shape

    def test_create_origin(self):
        scale = 0.00025
        shape = (3, 2)
        origin = (150.0, -34.0)
        (shape[1] * scale + origin[0], origin[1] - shape[0] * scale)
        ggb = GriddedGeoBox(shape, origin)
        assert origin == ggb.origin

    def test_create_corner(self):
        scale = 0.00025
        shape = (3, 2)
        origin = (150.0, -34.0)
        corner = (shape[1] * scale + origin[0], origin[1] - shape[0] * scale)
        ggb = GriddedGeoBox(shape, origin)
        assert corner == ggb.corner

    def test_shape_create_unit_GGB_using_corners(self):
        # create small GGB centred on (150.00025,-34.00025)
        expectedShape = (1, 1)
        scale = 0.00025
        origin = (150.0, -34.0)
        corner = (150.0 + scale, -34.0 - scale)
        ggb = GriddedGeoBox.from_corners(origin, corner)
        assert expectedShape == ggb.shape

    def test_corner_create_unit_GGB_using_corners(self):
        # create small GGB centred on (150.00025,-34.00025)
        scale = 0.00025
        origin = (150.0, -34.0)
        corner = (150.0 + scale, -34.0 - scale)
        ggb = GriddedGeoBox.from_corners(origin, corner)
        assert corner == ggb.corner

    def test_real_world_shape(self):
        # Flinders Islet, NSW
        flindersOrigin = (150.927659, -34.453309)
        flindersCorner = (150.931697, -34.457915)
        shapeShouldBe = (19, 17)
        (
            flindersOrigin[0] + shapeShouldBe[1] * 0.00025,
            flindersOrigin[1] - shapeShouldBe[0] * 0.00025,
        )

        ggb = GriddedGeoBox.from_corners(flindersOrigin, flindersCorner)
        assert shapeShouldBe == ggb.shape

    def test_real_world_origin_lon(self):
        # Flinders Islet, NSW
        flindersOrigin = (150.927659, -34.453309)
        flindersCorner = (150.931697, -34.457915)
        originShouldBe = flindersOrigin
        shapeShouldBe = (19, 17)
        (
            flindersOrigin[0] + shapeShouldBe[1] * 0.00025,
            flindersOrigin[1] - shapeShouldBe[0] * 0.00025,
        )

        ggb = GriddedGeoBox.from_corners(flindersOrigin, flindersCorner)
        assert shapeShouldBe == ggb.shape
        self.assertAlmostEqual(originShouldBe[0], ggb.origin[0])

    def test_real_world_origin_lat(self):
        # Flinders Islet, NSW
        flindersOrigin = (150.927659, -34.453309)
        flindersCorner = (150.931697, -34.457915)
        originShouldBe = flindersOrigin
        shapeShouldBe = (19, 17)
        (
            flindersOrigin[0] + shapeShouldBe[1] * 0.00025,
            flindersOrigin[1] - shapeShouldBe[0] * 0.00025,
        )

        ggb = GriddedGeoBox.from_corners(flindersOrigin, flindersCorner)
        self.assertAlmostEqual(originShouldBe[1], ggb.origin[1])

    def test_real_world_corner_lon(self):
        # Flinders Islet, NSW
        flindersOrigin = (150.927659, -34.453309)
        flindersCorner = (150.931697, -34.457915)
        shapeShouldBe = (19, 17)
        cornerShouldBe = (
            flindersOrigin[0] + shapeShouldBe[1] * 0.00025,
            flindersOrigin[1] - shapeShouldBe[0] * 0.00025,
        )

        ggb = GriddedGeoBox.from_corners(flindersOrigin, flindersCorner)
        self.assertAlmostEqual(cornerShouldBe[0], ggb.corner[0])

    def test_real_world_corner_lat(self):
        # Flinders Islet, NSW
        flindersOrigin = (150.927659, -34.453309)
        flindersCorner = (150.931697, -34.457915)
        shapeShouldBe = (19, 17)
        cornerShouldBe = (
            flindersOrigin[0] + shapeShouldBe[1] * 0.00025,
            flindersOrigin[1] - shapeShouldBe[0] * 0.00025,
        )

        ggb = GriddedGeoBox.from_corners(flindersOrigin, flindersCorner)
        self.assertAlmostEqual(cornerShouldBe[1], ggb.corner[1])

    def test_ggb_transform_from_rio_dataset(self):
        img, geobox = ut.create_test_image()
        kwargs = {
            "driver": "MEM",
            "width": img.shape[1],
            "height": img.shape[0],
            "count": 1,
            "transform": geobox.transform,
            "crs": geobox.crs.ExportToWkt(),
            "dtype": img.dtype.name,
        }

        with rio.open("tmp.tif", "w", **kwargs) as ds:
            new_geobox = GriddedGeoBox.from_rio_dataset(ds)

            assert new_geobox.transform == geobox.transform

    def test_ggb_crs_from_rio_dataset(self):
        img, geobox = ut.create_test_image()
        kwargs = {
            "driver": "MEM",
            "width": img.shape[1],
            "height": img.shape[0],
            "count": 1,
            "transform": geobox.transform,
            "crs": geobox.crs.ExportToWkt(),
            "dtype": img.dtype.name,
        }

        with rio.open("tmp.tif", "w", **kwargs) as ds:
            new_geobox = GriddedGeoBox.from_rio_dataset(ds)

            assert new_geobox.crs.ExportToWkt() == geobox.crs.ExportToWkt()

    def test_ggb_shape_from_rio_dataset(self):
        img, geobox = ut.create_test_image()
        kwargs = {
            "driver": "MEM",
            "width": img.shape[1],
            "height": img.shape[0],
            "count": 1,
            "transform": geobox.transform,
            "crs": geobox.crs.ExportToWkt(),
            "dtype": img.dtype.name,
        }

        with rio.open("tmp.tif", "w", **kwargs) as ds:
            new_geobox = GriddedGeoBox.from_rio_dataset(ds)

            assert new_geobox.shape == img.shape

    def test_ggb_transform_from_gdal_dataset(self):
        img, geobox = ut.create_test_image()
        drv = gdal.GetDriverByName("MEM")
        ds = drv.Create("tmp.tif", img.shape[1], img.shape[0], 1, 1)
        ds.SetGeoTransform(geobox.transform.to_gdal())
        ds.SetProjection(geobox.crs.ExportToWkt())

        new_geobox = GriddedGeoBox.from_gdal_dataset(ds)
        assert new_geobox.transform == geobox.transform
        drv = None
        ds = None

    def test_ggb_crs_from_gdal_dataset(self):
        img, geobox = ut.create_test_image()
        drv = gdal.GetDriverByName("MEM")
        ds = drv.Create("tmp.tif", img.shape[1], img.shape[0], 1, 1)
        ds.SetGeoTransform(geobox.transform.to_gdal())
        ds.SetProjection(geobox.crs.ExportToWkt())

        new_geobox = GriddedGeoBox.from_gdal_dataset(ds)
        assert new_geobox.crs.ExportToWkt() == geobox.crs.ExportToWkt()
        drv = None
        ds = None

    def test_ggb_shape_from_gdal_dataset(self):
        img, geobox = ut.create_test_image()
        drv = gdal.GetDriverByName("MEM")
        ds = drv.Create("tmp.tif", img.shape[1], img.shape[0], 1, 1)
        ds.SetGeoTransform(geobox.transform.to_gdal())
        ds.SetProjection(geobox.crs.ExportToWkt())

        new_geobox = GriddedGeoBox.from_gdal_dataset(ds)
        assert new_geobox.shape == img.shape
        drv = None
        ds = None

    def test_ggb_transform_from_h5_dataset(self):
        img, geobox = ut.create_test_image()
        with h5py.File("tmp.h5", driver="core", backing_store=False) as fid:
            ds = fid.create_dataset("test", data=img)
            ds.attrs["geotransform"] = geobox.transform.to_gdal()
            ds.attrs["crs_wkt"] = geobox.crs.ExportToWkt()

            new_geobox = GriddedGeoBox.from_h5_dataset(ds)
            assert new_geobox.transform == geobox.transform

    def test_ggb_crs_from_h5_dataset(self):
        img, geobox = ut.create_test_image()
        with h5py.File("tmp.h5", driver="core", backing_store=False) as fid:
            ds = fid.create_dataset("test", data=img)
            ds.attrs["geotransform"] = geobox.transform.to_gdal()
            ds.attrs["crs_wkt"] = geobox.crs.ExportToWkt()

            new_geobox = GriddedGeoBox.from_h5_dataset(ds)
            assert new_geobox.crs.ExportToWkt() == geobox.crs.ExportToWkt()

    def test_ggb_shape_from_h5_dataset(self):
        img, geobox = ut.create_test_image()
        with h5py.File("tmp.h5", driver="core", backing_store=False) as fid:
            ds = fid.create_dataset("test", data=img)
            ds.attrs["geotransform"] = geobox.transform.to_gdal()
            ds.attrs["crs_wkt"] = geobox.crs.ExportToWkt()

            new_geobox = GriddedGeoBox.from_h5_dataset(ds)
            assert new_geobox.shape == img.shape

    def test_convert_coordinate_to_map(self):
        """Test that an input image/array co-ordinate is correctly
        converted to a map co-cordinate.
        Simple case: The first pixel.
        """
        _, geobox = ut.create_test_image()
        xmap, ymap = geobox.convert_coordinates((0, 0))
        assert geobox.origin == (xmap, ymap)

    def test_convert_coordinate_to_image(self):
        """Test that an input image/array co-ordinate is correctly
        converted to a map co-cordinate.
        Simple case: The first pixel.
        """
        _, geobox = ut.create_test_image()
        ximg, yimg = geobox.convert_coordinates(geobox.origin, to_map=False)
        assert (0, 0) == (ximg, yimg)

    def test_convert_coordinate_to_map_offset(self):
        """Test that an input image/array co-ordinate is correctly
        converted to a map co-cordinate using a pixel centre offset.
        Simple case: The first pixel.
        """
        _, geobox = ut.create_test_image()
        xmap, ymap = geobox.convert_coordinates((0, 0), centre=True)

        # Get the actual centre co-ordinate of the first pixel
        xcentre, ycentre = geobox.convert_coordinates((0.5, 0.5))
        assert (xcentre, ycentre) == (xmap, ymap)

    # def test_pixelscale_metres(self):
    #     scale = 0.00025
    #     shape = (4000, 4000)
    #     origin = (150.0, -34.0)
    #     ggb = GriddedGeoBox(shape, origin, pixelsize=(scale, scale))
    #     (size_x, size_y) = ggb.get_pixelsize_metres(xy=(0, 0))
    #     self.assertAlmostEqual(size_x, 23.0962, places=4)
    #     self.assertAlmostEqual(size_y, 27.7306, places=4)

    # def test_all_pixelscale_metres(self):
    #    scale = 0.00025
    #    shape = (4000, 4000)
    #    origin = (150.0, -34.0)
    #    ggb = GriddedGeoBox(shape, origin, pixelsize=(scale, scale))
    #    size_array = ggb.get_all_pixelsize_metres()
    #
    #    self.assertEqual(len(size_array), 4000)
    #    (size_x, size_y) = size_array[0]
    #    self.assertAlmostEqual(size_x, 23.0962, places=4)
    #    self.assertAlmostEqual(size_y, 27.7306, places=4)
    #    (size_x, size_y) = size_array[3999]
    #    self.assertAlmostEqual(size_x, 22.8221, places=4)
    #    self.assertAlmostEqual(size_y, 27.7351, places=4)


if __name__ == "__main__":
    unittest.main()
