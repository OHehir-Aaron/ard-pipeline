#!/bin/env python

import logging
import os

import luigi
from constants import PQAConstants
from contiguity_masking import setContiguityBit
from EOtools.DatasetDrivers import SceneDataset
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
        logging.debug("Reading L1T bands")
        l1t_data = l1t_sd.ReadAsArray()
        logging.debug("l1t_data shape=%s" % (str(l1t_data.shape)))

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

        pqaResult = PQAResult(l1t_data[0].shape)

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

        logging.debug("setting land/sea bit")
        get_landsat_temperature(l1t_data, l1t_sd, pq_const)


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
