#!/bin/env python

import logging
import os

# TODO: remove soon
from glob import glob

import luigi
from acca_cloud_masking import calc_acca_cloud_mask
from cloud_shadow_masking import Cloud_Shadow
from constants import PQAConstants
from contiguity_masking import setContiguityBit
from EOtools.DatasetDrivers import SceneDataset
from fmask_cloud_masking_wrapper import FMaskCloudMask
from GriddedGeoBox import GriddedGeoBox
from land_sea_masking import setLandSeaBit
from memuseFilter import MemuseFilter
from pqa_result import PQAResult
from saturation_masking import setSaturationBits
from thermal_conversion import get_landsat_temperature


class PixelQualityTask(luigi.Task):
    # TODO: review each of these parameters, some could qualify as "Requires"
    l1t_path = luigi.Parameter()
    nbar_path = luigi.Parameter()
    land_sea_path = luigi.Parameter()
    pq_path = luigi.Parameter()

    def output(self):
        return PQDataset(self.pq_path)

    def requires(self):
        return NBARTask(self.nbar_path)

    def run(self):
        logging.info(
            "In PixelQualityTask.run method, L1T={} NBAR={}, output={}".format(
                self.l1t_path, self.input().nbar_path, self.output().path
            )
        )

        # read L1T data
        logging.debug("Creating L1T SceneDataset")
        l1t_sd = SceneDataset(self.l1t_path)
        logging.debug(f"Satellite is {l1t_sd.satellite.TAG}")
        logging.debug("Reading L1T bands")
        l1t_data = l1t_sd.ReadAsArray()
        logging.debug("l1t_data shape=%s" % (str(l1t_data.shape)))

        # get the GriddedGeoBox for this dataset
        # GriddedGeoBox encapsulates the bounding box, the pixel
        # grid and the Co-ordinate reference system
        # TODO: rework this to eliminate the reliance on SceneDataset

        geoBox = GriddedGeoBox.from_dataset(l1t_sd._root_dataset)
        logging.debug(str(geoBox))

        # read NBAR data
        logging.debug("Creating NBAR SceneDataset")
        nbar_sd = SceneDataset(self.nbar_path)
        logging.debug("Reading NBAR bands")
        nbar_data = nbar_sd.ReadAsArray()
        logging.debug("nbar_data shape=%s" % (str(nbar_data.shape)))

        # constants to be use for this PQA computation

        sensor = l1t_sd.sensor
        logging.debug(f"setting constants for sensor={sensor}")
        pq_const = PQAConstants(sensor)

        # the PQAResult object for this run

        pqaResult = PQAResult(l1t_data[0].shape, geoBox)

        # Saturation

        logging.debug("setting saturation bits")
        setSaturationBits(l1t_data, pq_const, pqaResult)
        logging.debug("done setting saturation bits")

        # contiguity

        logging.debug("setting contiguity bit")
        setContiguityBit(l1t_data, l1t_sd.satellite, pq_const, pqaResult)
        logging.debug("done setting contiguity bit")

        # land/sea

        logging.debug("setting land/sea bit")
        setLandSeaBit(l1t_data, l1t_sd, self.land_sea_path, pq_const, pqaResult)
        logging.debug("done setting land/sea bit")

        # get temperature data from thermal band in prepartion for cloud detection

        logging.debug("calculating kelvin band")
        kelvin_band = get_landsat_temperature(l1t_data, l1t_sd, pq_const)

        # acca cloud mask

        logging.debug("calculating acca cloud mask")
        contiguity_mask = (pqaResult.array & (1 << pq_const.contiguity)) > 0
        if pq_const.run_cloud:
            mask = None
            aux_data = {}  # for collecting result metadata
            if pq_const.oli_tirs:
                mask = calc_acca_cloud_mask(
                    nbar_data[1:, :, :],
                    kelvin_band,
                    pq_const,
                    contiguity_mask,
                    aux_data,
                )
            else:  # TM or ETM
                mask = calc_acca_cloud_mask(
                    nbar_data, kelvin_band, pq_const, contiguity_mask, aux_data
                )

            # set the result
            pqaResult.set_mask(mask, pq_const.acca)
            pqaResult.add_to_aux_data(aux_data)
        else:
            logging.warning(
                "ACCA Not Run! {} sensor not configured for the ACCA algorithm.".format(
                    sensor
                )
            )

            calc_fmask_cloud_mask(l1t_data, l1t_sd, pq_const, contiguity_mask, aux_data)

        # fmask cloud mask

        logging.debug("calculating fmask cloud mask")
        if pq_const.run_cloud:
            mask = None
            aux_data = {}  # for collecting result metadata

            # TODO: pass in scene metadata via Dale's new MTL reader
            mtl = glob(os.path.join(l1t_sd.pathname, "scene01/*_MTL.txt"))[
                0
            ]  # Crude but effective
            mask = FMaskCloudMask(
                mtl,
                null_mask=contiguity_mask,
                sat_tag=l1t_sd.satellite.TAG,
                aux_data=aux_data,
            )

            # set the result
            pqaResult.set_mask(mask, pq_const.fmask)
            pqaResult.add_to_aux_data(aux_data)
        else:
            logging.warning(
                "FMASK Not Run! {} sensor not configured for the FMASK algorithm.".format(
                    sensor
                )
            )

        logging.debug("done calculating fmask cloud mask")

        # parameters for cloud shadow masks

        contiguity_mask = pqaResult.get_mask(pq_const.contiguity)
        land_sea_mask = pqaResult.get_mask(pq_const.land_sea)

        # acca cloud shadow

        logging.debug("calculating ACCA cloud shadow mask")
        if pq_const.run_cloud_shadow:  # TM/ETM/OLI_TIRS
            mask = None
            aux_data = {}  # for collecting result metadata

            cloud_mask = pqaResult.get_mask(pq_const.acca)
            if pq_const.oli_tirs:
                mask = Cloud_Shadow(
                    nbar_data[1:, :, :],
                    kelvin_band,
                    cloud_mask,
                    l1t_sd,
                    pq_const,
                    land_sea_mask=land_sea_mask,
                    contiguity_mask=contiguity_mask,
                    cloud_algorithm="ACCA",
                    growregion=True,
                    aux_data=aux_data,
                )
            else:  # TM or ETM
                mask = Cloud_Shadow(
                    nbar_data,
                    kelvin_band,
                    cloud_mask,
                    l1t_sd,
                    pq_const,
                    land_sea_mask=land_sea_mask,
                    contiguity_mask=contiguity_mask,
                    cloud_algorithm="ACCA",
                    growregion=True,
                    aux_data=aux_data,
                )

            pqaResult.set_mask(mask, pq_const.acca_shadow)
            pqaResult.add_to_aux_data(aux_data)

        else:  # OLI/TIRS only
            logger.warning(
                "Cloud Shadow Algorithm Not Run! {} sensor not configured for the cloud shadow algorithm.".format(
                    sensor
                )
            )

        logging.debug("done calculating ACCA cloud shadow mask")

        # FMASK cloud shadow

        logging.debug("calculating FMASK cloud shadow mask")
        if pq_const.run_cloud_shadow:  # TM/ETM/OLI_TIRS
            mask = None
            aux_data = {}  # for collecting result metadata

            cloud_mask = pqaResult.get_mask(pq_const.fmask)
            if pq_const.oli_tirs:
                mask = Cloud_Shadow(
                    nbar_data[1:, :, :],
                    kelvin_band,
                    cloud_mask,
                    l1t_sd,
                    pq_const,
                    land_sea_mask=land_sea_mask,
                    contiguity_mask=contiguity_mask,
                    cloud_algorithm="FMASK",
                    growregion=True,
                    aux_data=aux_data,
                )
            else:  # TM or ETM
                mask = Cloud_Shadow(
                    nbar_data,
                    kelvin_band,
                    cloud_mask,
                    l1t_sd,
                    pq_const,
                    land_sea_mask=land_sea_mask,
                    contiguity_mask=contiguity_mask,
                    cloud_algorithm="FMASK",
                    growregion=True,
                    aux_data=aux_data,
                )

            pqaResult.set_mask(mask, pq_const.fmask_shadow)
            pqaResult.add_to_aux_data(aux_data)

        else:  # OLI/TIRS only
            logger.warning(
                "Cloud Shadow Algorithm Not Run! {} sensor not configured for the cloud shadow algorithm.".format(
                    sensor
                )
            )

        logging.debug("done calculating FMASK cloud shadow mask")

        # write PQA file as output

        logging.debug("saving PQA result GeoTiff")
        pqa_output_path = os.path.join(self.pq_path, "pqa.tif")
        pqaResult.save_as_tiff(pqa_output_path)
        logging.debug("done saving PQA result GeoTiff")


class PQDataset(luigi.Target):
    def __init__(self, path):
        self.path = path

    def exists(self):
        return os.path.exists(self.path)


class NBARTask(luigi.ExternalTask):
    nbar_path = luigi.Parameter()

    def output(self):
        return NBARdataset(self.nbar_path)


class NBARdataset(luigi.Target):
    def __init__(self, nbar_path):
        self.nbar_path = nbar_path
        self.dataset = SceneDataset(pathname=self.nbar_path)

    def exists(self):
        return os.path.exists(self.nbar_path)


if __name__ == "__main__":
    logging.config.fileConfig("logging.conf")  # Get basic config
    log = logging.getLogger("")  # Get root logger
    f = MemuseFilter()  # Create filter
    log.handlers[0].addFilter(f)  # The ugly part:adding filter to handler
    logging.info("PQA started")
    luigi.run()
    logging.info("PQA done")
