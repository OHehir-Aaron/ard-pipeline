#!/usr/bin/env python

"""A temporary workflow for processing S2 data into an ARD package."""

import logging
import shutil
import traceback
from os.path import basename, dirname
from os.path import join as pjoin

import luigi
from luigi.local_target import LocalFileSystem
from structlog import wrap_logger
from structlog.processors import JSONRenderer
from wagl.acquisition import acquisitions
from wagl.singlefile_workflow import DataStandardisation

from s2pkg.fmask_cophub import fmask, prepare_dataset
from s2pkg.package import package

ERROR_LOGGER = wrap_logger(
    logging.getLogger("ard-error"), processors=[JSONRenderer(indent=1, sort_keys=True)]
)
INTERFACE_LOGGER = logging.getLogger("luigi-interface")


@luigi.Task.event_handler(luigi.Event.FAILURE)
def on_failure(task, exception):
    """Capture any Task Failure here."""
    ERROR_LOGGER.error(
        task=task.get_task_family(),
        params=task.to_str_params(),
        scene=task.level1,
        exception=exception.__str__(),
        traceback=traceback.format_exc().splitlines(),
    )


class WorkDir(luigi.Task):
    """Initialises the working directory in a controlled manner.
    Alternatively this could be initialised upfront during the
    ARD Task submission phase.
    """

    level1 = luigi.Parameter()
    outdir = luigi.Parameter()

    def output(self):
        return luigi.LocalTarget(self.outdir)

    def run(self):
        local_fs = LocalFileSystem()
        local_fs.mkdir(self.output().path)


class RunFmask(luigi.Task):
    """Execute the Fmask algorithm for a given granule."""

    level1 = luigi.Parameter()
    task = luigi.TupleParameter()
    outdir = luigi.Parameter()

    def requires(self):
        # for the time being have fmask require wagl,
        # no point in running fmask if wagl fails...
        # return WorkDir(self.level1, dirname(self.outdir))
        return DataStandardisation(self.level1, self.outdir, self.task[1])

    def output(self):
        out_fname = pjoin(self.outdir, f"{self.task[1]}.cloud.img")

        return luigi.LocalTarget(out_fname)

    def run(self):
        with self.output().temporary_path() as out_fname:
            fmask(self.level1, self.task, out_fname, self.outdir)


# useful for testing fmask via the CLI
class Fmask(luigi.WrapperTask):
    """A helper task that issues RunFmask Tasks."""

    level1 = luigi.Parameter()
    outdir = luigi.Parameter()
    acq_parser_hint = luigi.Parameter(default=None)

    def requires(self):
        # issues task per granule
        for task in prepare_dataset(self.level1, self.acq_parser_hint):
            yield RunFmask(self.level1, task, self.outdir)


# TODO: GQA implementation
# class Gqa(luigi.Task):

#     level1 = luigi.Parameter()
#     outdir = luigi.Parameter()


class Package(luigi.Task):
    """Creates the final packaged product once wagl, Fmask
    and gqa have executed successfully.
    """

    level1 = luigi.Parameter()
    work_dir = luigi.Parameter()
    granule = luigi.Parameter(default=None)
    pkg_dir = luigi.Parameter()
    yamls_dir = luigi.Parameter()
    cleanup = luigi.BoolParameter()
    s3_root = luigi.Parameter()
    acq_parser_hint = luigi.Parameter(default=None)

    def requires(self):
        # task items for fmask
        ftask = prepare_dataset(self.level1, self.acq_parser_hint, self.granule)

        tasks = {
            "wagl": DataStandardisation(self.level1, self.work_dir, self.granule),
            "fmask": RunFmask(self.level1, ftask, self.work_dir),
        }
        # TODO: GQA implementation
        # 'gqa': Gqa()}

        return tasks

    def output(self):
        granule = self.granule if self.granule else ""
        out_fname = pjoin(self.pkg_dir, granule.replace("L1C", "ARD"), "CHECKSUM.sha1")

        return luigi.LocalTarget(out_fname)

    def run(self):
        inputs = self.input()
        package(
            self.level1,
            inputs["wagl"].path,
            inputs["fmask"].path,
            self.yamls_dir,
            self.pkg_dir,
            self.s3_root,
            self.acq_parser_hint,
        )

        if self.cleanup:
            shutil.rmtree(self.work_dir)


class ARDP(luigi.WrapperTask):
    """A helper Task that issues Package Tasks for each Level-1
    dataset listed in the `level1_list` parameter.
    """

    level1_list = luigi.Parameter()
    outdir = luigi.Parameter()
    pkg_dir = luigi.Parameter()
    acq_parser_hint = luigi.Parameter(default=None)

    def requires(self):
        with open(self.level1_list) as src:
            level1_scenes = [scene.strip() for scene in src.readlines()]

        for scene in level1_scenes:
            work_root = pjoin(self.outdir, f"{basename(scene)}.ARD")
            container = acquisitions(scene, self.acq_parser_hint)
            for granule in container.granules:
                work_dir = container.get_root(work_root, granule=granule)
                # TODO; pkg_dir for landsat data
                pkg_dir = pjoin(self.pkg_dir, basename(dirname(scene)))
                yield Package(scene, work_dir, granule, pkg_dir)


if __name__ == "__main__":
    luigi.run()
