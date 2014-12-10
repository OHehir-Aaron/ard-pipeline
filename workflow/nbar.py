from os.path import dirname
from os.path import join as pjoin

import cPickle as pickle
import luigi

import gaip

CONFIG = luigi.configuration.get_config()
CONFIG.add_config_path(pjoin(dirname(__file__), "nbar.cfg"))


def save(target, value):
    with target.open("w") as outfile:
        if target.fn.endswith("pkl"):
            pickle.dump(value, outfile)
        else:
            print >> outfile, value


def load(target):
    if not target.fn.endswith("pkl"):
        raise OSError("Cannot load non-pickled object")
    with target.open("r") as infile:
        return pickle.load(infile)


class GetElevationAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "dem_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        geobox = acqs[0].gridded_geo_box()
        dem_path = CONFIG.get("ancillary", "dem_path")
        value = gaip.get_elevation_data(geobox.centre_lonlat, dem_path)
        save(self.output(), value)


class GetOzoneAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "ozone_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        geobox = acqs[0].gridded_geo_box()
        ozone_path = CONFIG.get("ancillary", "ozone_path")
        centre = geobox.centre_lonlat
        dt = acqs[0].scene_center_datetime
        value = gaip.get_ozone_data(ozone_path, centre, dt)
        save(self.output(), value)


class GetSolarIrradianceAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "irrad_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        solar_path = CONFIG.get("ancillary", "solarirrad_path")
        value = gaip.get_solar_irrad(acqs, solar_path)
        save(self.output(), value)


class GetSolarDistanceAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "sundist_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        sundist_path = CONFIG.get("ancillary", "sundist_path")
        value = gaip.get_solar_dist(acqs[0], sundist_path)
        save(self.output(), value)


class GetWaterVapourAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "vapour_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        vapour_path = CONFIG.get("ancillary", "vapour_path")
        value = gaip.get_water_vapour(acqs[0], vapour_path)
        save(self.output(), value)


class GetAerosolAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "aerosol_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        aerosol_path = CONFIG.get("ancillary", "aerosol_path")
        value = gaip.get_aerosol_data(acqs[0], aerosol_path)
        save(self.output(), value)


class GetBrdfAncillaryDataTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "brdf_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        brdf_path = CONFIG.get("ancillary", "brdf_path")
        brdf_premodis_path = CONFIG.get("ancillary", "brdf_premodis_path")
        work_path = CONFIG.get("work", "path")
        value = gaip.get_brdf_data(acqs[0], brdf_path, brdf_premodis_path, work_path)
        save(self.output(), value)


class GetAncillaryData(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return [
            GetElevationAncillaryDataTask(self.l1t_path),
            GetOzoneAncillaryDataTask(self.l1t_path),
            GetSolarDistanceAncillaryDataTask(self.l1t_path),
            GetWaterVapourAncillaryDataTask(self.l1t_path),
            GetAerosolAncillaryDataTask(self.l1t_path),
            GetBrdfAncillaryDataTask(self.l1t_path),
        ]

    def complete(self):
        return all([d.complete() for d in self.requires()])


class CalculateLonGrid(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "lon_grid_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        target = self.output()
        gaip.create_lon_grid(acqs[0], target.fn)


class CalculateLatGrid(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "lat_grid_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        target = self.output()
        gaip.create_lat_grid(acqs[0], target.fn)


class CalculateLatLonGrids(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return [CalculateLatGrid(self.l1t_path), CalculateLonGrid(self.l1t_path)]

    def complete(self):
        return all([d.complete() for d in self.requires()])


class CalculateSatelliteGrids(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "lat_grid_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        target = self.output()
        gaip.create_lat_grid(acqs[0], target.fn)


class CalculateSolarGrids(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        target = CONFIG.get("work", "lat_grid_target")
        return luigi.LocalTarget(target)

    def run(self):
        acqs = gaip.acquisitions(self.l1t_path)
        target = self.output()
        gaip.create_lat_grid(acqs[0], target.fn)


class CalculateGridsTask(luigi.Task):
    l1t_path = luigi.Parameter()

    def requires(self):
        return [
            CalculateLatLonGrids(self.l1t_path),
            CalculateSatelliteGrids(self.l1t_path),
            CalculateSolarGrids(self.l1t_path),
        ]

    def complete(self):
        return all([d.complete() for d in self.requires()])


class PrepareModtranInputTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class RunModtranTask(luigi.Task):
    albedo = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class RunFluxTask(luigi.Task):
    albedo = luigi.Parameter()

    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class RunCoefficientTask(luigi.Task):
    coef = luigi.Parameter()
    # TL, TM, TR, ML, MM, MR, BL, BM, BR

    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class ReadModtranTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class BilinearOrthoTask(luigi.Task):
    param = luigi.Parameter()  # fv, fs, b, s, a

    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class RadiativeTransferPrepTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class BrdfTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class WriteTiffFilesTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class RadiativeTransferNbarTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


class RadiativeTransferPostprocessingTask(luigi.Task):
    def requires(self):
        return []

    def output(self):
        pass

    def run(self):
        pass


if __name__ == "__main__":
    l1t_path = "../gaip/tests/data/L1T/LS7_90-81_2009-04-15/UTM/LS7_ETM_OTH_P51_GALPGS01-002_090_081_20090415"
    luigi.build([GetElevationAncillaryDataTask(l1t_path)], local_scheduler=True)
