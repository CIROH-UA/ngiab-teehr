"""This is an example of how to use TEEHR in NGEN."""
from pathlib import Path
import shutil
import logging
from typing import List

import os
import pandas as pd
import teehr

from utils import (
    get_usgs_nwm30_crosswalk,
    get_usgs_point_geometry,
    get_simulation_output_csv,
    get_simulation_output_netcdf,
    get_gages_from_hydrofabric,
    get_simulation_start_end_time,
    get_simulation_output_format,
)

logger = logging.getLogger(__name__)

# In NGEN this will be provided by NGEN.
NGEN_DATA_DIR = Path("data")
# NGEN_DATA_DIR = Path("/home/sam/ngiab_preprocess_output/cat-508412")

# Set a path to the directory where the evaluation will be created
TEST_STUDY_DIR = Path(NGEN_DATA_DIR, "teehr")

LOCATIONS = Path(TEST_STUDY_DIR, "cache", "locations.parquet")
NWM_USGS_XWALK = Path(TEST_STUDY_DIR, "nwm_usgs_crosswalk.parquet")
NGEN_USGS_XWALK = Path(TEST_STUDY_DIR, "ngen_usgs_crosswalk.parquet")
NGEN_CACHE_OUTPUT = Path(TEST_STUDY_DIR, "cache", "ngen_output.parquet")


def main(run_options: List[int]):

    ev = None

    if 1 in run_options:
        # Create a new TEEHR Evaluation object and initialize a dataset.
        shutil.rmtree(TEST_STUDY_DIR, ignore_errors=True)
        ev = teehr.Evaluation(dir_path=TEST_STUDY_DIR, create_dir=True)
        ev.enable_logging()
        ev.clone_template()

        # Get the start and end time of the simulation.
        start_date, end_date = get_simulation_start_end_time(NGEN_DATA_DIR)

        # Get the USGS to NWM crosswalk and USGS point geometry from s3.
        usgs_nwm_xwalk_df = get_usgs_nwm30_crosswalk()
        usgs_nwm_xwalk_df = usgs_nwm_xwalk_df.set_index("primary_location_id")
        usgs_point_geom = get_usgs_point_geometry()
        usgs_point_geom = usgs_point_geom.set_index("id")

        # Get the NGEN-USGS gages from the hydrofabric.
        ngen_usgs_gages = get_gages_from_hydrofabric(NGEN_DATA_DIR)
        if len(ngen_usgs_gages) == 0:
            raise ValueError(
                "No USGS gages found in the hydrofabric!"
                f" Output directory: {NGEN_DATA_DIR.stem}"
            )
        logger.info(f"Found {len(ngen_usgs_gages)} USGS gages in the hydrofabric.")

        # Check for netcdf or csv output files.
        sim_output_format = get_simulation_output_format(NGEN_DATA_DIR)
        logger.info(f"Simulation output format: {sim_output_format}")

        # Read the NGEN output timeseries and link to USGS and NWM ID's
        gage_output_list = []
        for gage_pair in ngen_usgs_gages:
            if "usgs-" + gage_pair[1] not in usgs_nwm_xwalk_df.index:
                continue
            if sim_output_format == "netcdf":
                gage_output = get_simulation_output_netcdf(
                    gage_pair[0],
                    NGEN_DATA_DIR
                )
            elif sim_output_format == "csv":
                gage_output = get_simulation_output_csv(
                    gage_pair[0],
                    NGEN_DATA_DIR
                )
            gage_output["ngen_id"] = "ngen-" + gage_pair[0].split("-")[1]
            gage_output["usgs_id"] = "usgs-" + gage_pair[1]
            gage_output["nwm_id"] = usgs_nwm_xwalk_df["secondary_location_id"].loc["usgs-" + gage_pair[1]]
            gage_output_list.append(gage_output)
        all_ngen_output = pd.concat(gage_output_list)
        # print(all_ngen_output)
        all_ngen_output.to_parquet(NGEN_CACHE_OUTPUT)

        # Get primary locations and load to dataset.
        locations_df = usgs_point_geom.loc[all_ngen_output["usgs_id"].unique()]
        locations_df.reset_index(inplace=True)
        locations_df.to_parquet(LOCATIONS)

        # Load the location data (USGS points)
        ev.locations.load_spatial(in_path=LOCATIONS)

        # Load the USGS-NWM Crosswalk.
        usgs_nwm_eval_xwalk_df = usgs_nwm_xwalk_df.loc[locations_df.id]
        usgs_nwm_eval_xwalk_df.reset_index(inplace=True)
        usgs_nwm_eval_xwalk_df.to_parquet(NWM_USGS_XWALK)
        ev.location_crosswalks.load_parquet(
            in_path=NWM_USGS_XWALK
        )
        # Load the USGS-NGEN Crosswalk.
        tmp_df = all_ngen_output[~all_ngen_output["ngen_id"].duplicated()]
        ngen_usgs_eval_xwalk_df = tmp_df[["usgs_id", "ngen_id"]].copy()
        ngen_usgs_eval_xwalk_df.rename(
            columns={
                "usgs_id": "primary_location_id",
                "ngen_id": "secondary_location_id"
            }, inplace=True
        )
        ngen_usgs_eval_xwalk_df.to_parquet(NGEN_USGS_XWALK)
        ev.location_crosswalks.load_parquet(
            in_path=NGEN_USGS_XWALK
        )
        # Load the NGEN simulation timeseries
        ev.configurations.add(
            teehr.Configuration(
                name="ngen",
                type="secondary",
                description="Nextgen simulation output"
            )
        )
        # Load the NWM retrospective timeseries
        ev.fetch.nwm_retrospective_points(
            nwm_version="nwm30",
            variable_name="streamflow",
            start_date=start_date,
            end_date=end_date
        )
        # Load the NGEN simulation timeseries
        ev.secondary_timeseries.load_parquet(
            in_path=NGEN_CACHE_OUTPUT,
            field_mapping={
                "current_time": "value_time",
                "flow": "value",
                "ngen_id": "location_id"
            },
            constant_field_values={
                "reference_time": None,
                "unit_name": "m^3/s",
                "variable_name": "streamflow_hourly_inst",
                "configuration_name": "ngen"
            }
        )
        # Load the USGS observations timeseries
        ev.fetch.usgs_streamflow(
            start_date=start_date,
            end_date=end_date
        )
        # Create the joined timeseries table
        ev.joined_timeseries.create()

    if 2 in run_options:
        if not os.path.exists(TEST_STUDY_DIR):
            raise ValueError(
                "The TEEHR evaluation directory does not exist. "
                "Please run option 1 first."
            )
        if ev is None:
            ev = teehr.Evaluation(dir_path=TEST_STUDY_DIR)
            ev.enable_logging()

        # Calculate some metrics
        df = ev.metrics.query(
            order_by=["primary_location_id", "configuration_name"],
            group_by=["primary_location_id", "configuration_name"],
            include_metrics=[
                teehr.DeterministicMetrics.KlingGuptaEfficiency(),
                teehr.DeterministicMetrics.NashSutcliffeEfficiency(),
                teehr.DeterministicMetrics.RelativeBias(),
                teehr.DeterministicMetrics.RootMeanStandardDeviationRatio(),
            ]
        ).to_pandas()
        df.to_csv(Path(TEST_STUDY_DIR, "metrics.csv"), index=False)

    # # Plotting functionality is in development.
    # ts_df = ev.secondary_timeseries.to_pandas()
    # ts_df.teehr.timeseries_plot(
    #     output_dir=TEST_STUDY_DIR
    # )


if __name__ == "__main__":
    """Main function to run the TEEHR evaluation.

    Run option values:
        1: Set up the TEEHR evaluation
        2: Calculate metrics
    """
    run_options = os.environ.get("RUN_OPTIONS")
    if run_options:
        run_options = [int(opt) for opt in run_options.split(",")]
        logger.info(f"Run options: {run_options}")
    else:
        logger.info("No run options provided, running all.")

    main(run_options=run_options)
