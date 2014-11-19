#!/bin/env python

import logging
import os

import luigi
from EOtools.DatasetDrivers import SceneDataset
from memuseFilter import MemuseFilter


class PixelQualityTask(luigi.Task):
    l1t_path = luigi.Parameter()
    nbar_path = luigi.Parameter()
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
    log.info("PQA started")
    luigi.run()
    log.info("PQA done")
