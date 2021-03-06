import logging
import os

from pywps import FORMATS, ComplexInput, ComplexOutput, Format, LiteralInput, LiteralOutput, Process
from pywps.app.Common import Metadata
from pywps.response.status import WPS_STATUS

from copernicus import runner, util

from .utils import default_outputs, model_experiment_ensemble, year_ranges

LOGGER = logging.getLogger("PYWPS")


class EnsClus(Process):
    def __init__(self):
        inputs = [
            # *model_experiment_ensemble(
            #     models=['Defaults'],
            #     experiments=['historical'],
            #     ensembles=['r1i1p1'],
            #     start_end_year=(1850, 2005),
            #     start_end_defaults=(1850, 2005)),
             *year_ranges((1850, 2005),(1990, 2005)),
            LiteralInput(
                'season',
                'Season',
                abstract='Choose a season like DJF.',
                data_type='string',
                allowed_values=['DJF', 'DJFM', 'NDJFM', 'JJA'],
                default='JJA'),
            LiteralInput(
                'area',
                'Area',
                abstract='Area',
                data_type='string',
                allowed_values=['EU', 'EAT', 'PNA', 'NH'],
                default='EU'),
            LiteralInput(
                'extreme',
                'Extreme',
                abstract='Extreme',
                data_type='string',
                allowed_values=[
                    '60th_percentile', '75th_percentile', '90th_percentile',
                    'mean', 'maximum', 'std', 'trend'
                ],
                default='75th_percentile'),
            LiteralInput(
                'numclus',
                'Number of Clusters',
                abstract='Numclus',
                data_type='string',
                allowed_values=['2', '3', '4'],
                default='3'),
            LiteralInput(
                'perc',
                'Percentage',
                abstract='Percentage of total Variance',
                data_type='string',
                allowed_values=['70', '80', '90'],
                default='80'),
        ]
        outputs = [
            ComplexOutput(
                'plot',
                'Output plot',
                abstract='Generated output plot of ESMValTool processing.',
                as_reference=True,
                supported_formats=[Format('image/eps')]),
            ComplexOutput(
                'ens_extreme',
                'ens_extreme',
                abstract='Generated output data of ESMValTool processing.',
                as_reference=True,
                supported_formats=[FORMATS.NETCDF]),
            ComplexOutput(
                'ens_climatologies',
                'ens_climatologies',
                abstract='Generated output data of ESMValTool processing.',
                as_reference=True,
                supported_formats=[FORMATS.NETCDF]),
            ComplexOutput(
                'ens_anomalies',
                'ens_anomalies',
                abstract='Generated output data of ESMValTool processing.',
                as_reference=True,
                supported_formats=[FORMATS.NETCDF]),
            ComplexOutput(
                'statistics',
                'Statistics',
                abstract='Clustering Statictics',
                as_reference=True,
                supported_formats=[Format('text/plain')]),
            ComplexOutput(
                'archive',
                'Archive',
                abstract=
                'The complete output of the ESMValTool processing as an zip archive.',
                as_reference=True,
                supported_formats=[Format('application/zip')]),
            *default_outputs(),
        ]

        super(EnsClus, self).__init__(
            self._handler,
            identifier="ensclus",
            title="EnsClus - Ensemble Clustering",
            version=runner.VERSION,
            abstract="""Cluster analysis tool based on the k-means algorithm
                for ensembles of climate model simulations. EnsClus group
                ensemble members according to similar characteristics and
                select the most representative member for each cluster.
                Currently included are the models: ACCESS1-0, ACCESS1-3,
                CanESM2, CCSM4, CESM1-BGC""",
            metadata=[
                Metadata('Estimated Calculation Time', '4 minutes'),
                Metadata('ESMValTool', 'http://www.esmvaltool.org/'),
                Metadata(
                    'Documentation',
                    'https://esmvaltool.readthedocs.io/en/latest/recipes/recipe_ensclus.html',
                    role=util.WPS_ROLE_DOC),
#                Metadata(
#                    'Media',
#                    util.diagdata_url() + '/ensclus/ensclus_thumbnail.png',
#                    role=util.WPS_ROLE_MEDIA),
            ],
            inputs=inputs,
            outputs=outputs,
            status_supported=True,
            store_supported=True)

    def _handler(self, request, response):
        response.update_status("starting ...", 0)
        workdir = self.workdir

        # build esgf search constraints
        constraints = dict(
            # model=request.inputs['model'][0].data, # currently not used in recipy
            experiment='historical', # request.inputs['experiment'][0].data,
            mip='Amon',
            ensemble='r1i1p1' # request.inputs['ensemble'][0].data,
        )

        options = dict(
            season=request.inputs['season'][0].data,
            area=request.inputs['area'][0].data,
            extreme=request.inputs['extreme'][0].data,
            numclus=request.inputs['numclus'][0].data,
            perc=request.inputs['perc'][0].data,
        )

        # generate recipe
        response.update_status("generate recipe ...", 10)
        recipe_file, config_file = runner.generate_recipe(
            workdir=workdir,
            diag='ensclus',
            constraints=constraints,
            start_year=request.inputs['start_year'][0].data,
            end_year=request.inputs['end_year'][0].data,
            output_format='png',
            options=options,
        )

        # recipe output
        response.outputs['recipe'].output_format = FORMATS.TEXT
        response.outputs['recipe'].file = recipe_file

        # run diag
        response.update_status("running diagnostic ...", 20)
        result = runner.run(recipe_file, config_file)

        # log output
        response.outputs['log'].output_format = FORMATS.TEXT
        response.outputs['log'].file = result['logfile']

        # debug log output
        response.outputs['debug_log'].output_format = FORMATS.TEXT
        response.outputs['debug_log'].file = result['debug_logfile']

        response.outputs['success'].data = result['success']

        if result['success']:
            try:
                self.get_outputs(result, response)
            except Exception as e:
                response.update_status("exception occured: " + str(e), 85)
        else:
            LOGGER.exception('esmvaltool failed!')
            response.update_status("exception occured: " + result['exception'],
                                   85)

        response.update_status("creating archive of diagnostic result ...", 90)

        response.outputs['archive'].output_format = Format('application/zip')
        response.outputs['archive'].file = runner.compress_output(
            os.path.join(workdir, 'output'), 'diagnostic_result.zip')

        response.update_status("done.", 100)
        return response

    def get_outputs(self, result, response):
        # result plot
        response.update_status("collecting output ...", 80)
        response.outputs['plot'].output_format = Format('application/eps')
        response.outputs['plot'].file = runner.get_output(
            result['plot_dir'],
            path_filter=os.path.join('EnsClus', 'main'),
            name_filter="anomalies*",
            output_format="png")

        response.outputs['ens_extreme'].output_format = FORMATS.NETCDF
        response.outputs['ens_extreme'].file = runner.get_output(
            result['work_dir'],
            path_filter=os.path.join('EnsClus', 'main'),
            name_filter="ens_extreme*",
            output_format="nc")
        
        response.outputs['ens_climatologies'].output_format = FORMATS.NETCDF
        response.outputs['ens_climatologies'].file = runner.get_output(
            result['work_dir'],
            path_filter=os.path.join('EnsClus', 'main'),
            name_filter="ens_anomalies*",
            output_format="nc")
        
        response.outputs['ens_anomalies'].output_format = FORMATS.NETCDF
        response.outputs['ens_anomalies'].file = runner.get_output(
            result['work_dir'],
            path_filter=os.path.join('EnsClus', 'main'),
            name_filter="ens_anomalies*",
            output_format="nc")

        response.outputs['statistics'].output_format = FORMATS.TEXT
        response.outputs['statistics'].file = runner.get_output(
            result['work_dir'],
            path_filter=os.path.join('EnsClus', 'main'),
            name_filter="statistics*",
            output_format="txt")
