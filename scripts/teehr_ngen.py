"""Run a TEEHR evaluation on NGEN output.

This script assumes that the directory name of the NGEN output contains
a unique identifier for the simulation (e.g. AWI_16_2863657_007).
The script will read the NGEN output, extract the relevant data, and load
it into a local TEEHR Evaluation. USGS observations and NWM v3.0 retrospective
simulation timeseries are downloaded from the TEEHR-Cloud data warehouse
for the same locations and time period. It will then compute metrics
comparing the NGEN output and NWM simulation to observed USGS streamflow data
and write the metrics to a new table in the local TEEHR warehouse.

The location of the local TEEHR Evaluation can be specified by the user in the
runTeehr.sh script. This means that several NGIAB runs can point to the same
TEEHR Evaluation, so that metrics from different runs can be compared within
the same evaluation.
"""
from pathlib import Path
import argparse
import re
import logging
import shutil

import pandas as pd
from teehr import LocalReadWriteEvaluation
from teehr import Configuration
from teehr import DeterministicMetrics as dm

from utils import (
    get_gages_from_hydrofabric,
    get_simulation_start_end_time,
    get_simulation_output_format,
    write_netcdf_output_to_cache,
    write_csv_output_to_cache,
    write_parquet_output_to_cache
)

logger = logging.getLogger(__name__)

# NGEN_OUTPUT_DIR = Path("/home/slamont/NextGen/ngen-data/AWI_16_2863657_007")  # for testing
NGEN_OUTPUT_DIR = Path("data")

NGEN_METRICS_TABLE_NAME = "ngen_metrics"

rmsdr = dm.RootMeanStandardDeviationRatio()
rbias = dm.RelativeBias()
nse = dm.NashSutcliffeEfficiency()
kge = dm.KlingGuptaEfficiency()

rmsdr.add_epsilon = True
rbias.add_epsilon = True
nse.add_epsilon = True
kge.add_epsilon = True

SIM_METRICS = [
    rmsdr,
    rbias,
    nse,
    kge
]


def main(
    data_folder_stem: str,
    teehr_evaluation_dir: Path
):
    ngen_configuration_name = "ngen_" + data_folder_stem
    # Create a TEEHR Evaluation object and initialize a dataset.
    ev = LocalReadWriteEvaluation(
        dir_path=teehr_evaluation_dir,
        create_dir=True  # currently doesn't do anything if it already exists
    )
    ev.enable_logging()
    ngen_output_cache_dir = Path(
        ev.cache_dir,
        "ngen_output"
    )
    # If the ngen cache dir already exists delete it with shutil
    if ngen_output_cache_dir.exists():
        shutil.rmtree(ngen_output_cache_dir)
    ngen_output_cache_dir.mkdir(parents=True, exist_ok=True)
    # Get the start and end time of the simulation.
    start_date, end_date = get_simulation_start_end_time(NGEN_OUTPUT_DIR)
    # Get the NGEN-USGS gages from the hydrofabric.
    ngen_usgs_gages = get_gages_from_hydrofabric(NGEN_OUTPUT_DIR)
    if len(ngen_usgs_gages) == 0:
        raise ValueError(
            "No USGS gages found in the hydrofabric!"
            f" Output directory: {NGEN_OUTPUT_DIR.stem}"
        )
    usgs_location_ids = [
        "usgs-" + gage_pair[1] for gage_pair in ngen_usgs_gages
    ]
    # Load the location data (USGS points)
    ev.download.locations(
        ids=usgs_location_ids,
        load=True
    )
    teehr_usgs_locations = ev.locations.to_pandas()["id"].tolist()
    # Limit the ngen_stem_ids to those that are in teehr_usgs_locations
    ngen_stem_ids = [
        ngen_wb_id.split("-")[1] for ngen_wb_id, usgs_id in ngen_usgs_gages
        if "usgs-" + usgs_id in teehr_usgs_locations
    ]
    logger.info(
        f"Found {len(teehr_usgs_locations)} USGS gages in the hydrofabric"
        " that are present in the TEEHR-Cloud data warehouse."
    )
    # Check for netcdf or csv output files.
    sim_output_format = get_simulation_output_format(NGEN_OUTPUT_DIR)
    logger.info(f"Simulation output format: {sim_output_format}")

    # Read the NGEN output timeseries.
    if sim_output_format == "netcdf":
        write_netcdf_output_to_cache(
            ngen_stem_ids=ngen_stem_ids,
            folder_to_eval=NGEN_OUTPUT_DIR,
            ngen_configuration_name=ngen_configuration_name,
            secondary_cache_dir=ngen_output_cache_dir
        )
    elif sim_output_format == "csv":
        write_csv_output_to_cache(
            ngen_stem_ids=ngen_stem_ids,
            folder_to_eval=NGEN_OUTPUT_DIR,
            ngen_configuration_name=ngen_configuration_name,
            secondary_cache_dir=ngen_output_cache_dir
        )
    elif sim_output_format == "parquet":
        write_parquet_output_to_cache(
            ngen_stem_ids=ngen_stem_ids,
            folder_to_eval=NGEN_OUTPUT_DIR,
            ngen_configuration_name=ngen_configuration_name,
            secondary_cache_dir=ngen_output_cache_dir
        )
    ev.download.location_crosswalks(
        primary_location_id=teehr_usgs_locations,
        secondary_location_id_prefix="nwm30",
        load=True
    )
    # Load the USGS-NGEN Crosswalk.
    ngen_usgs_eval_xwalk_df = pd.DataFrame(
        ngen_usgs_gages,
        columns=["secondary_location_id", "primary_location_id"]
    )
    # Fix the prefixes.
    ngen_usgs_eval_xwalk_df["secondary_location_id"] = \
        ngen_usgs_eval_xwalk_df["secondary_location_id"].str.replace("wb-", "ngen-")
    ngen_usgs_eval_xwalk_df["primary_location_id"] = \
        "usgs-" + ngen_usgs_eval_xwalk_df["primary_location_id"]
    # Drop any entries not in the TEEHR locations table.
    ngen_usgs_eval_xwalk_df = ngen_usgs_eval_xwalk_df[
        ngen_usgs_eval_xwalk_df["primary_location_id"]
        .isin(teehr_usgs_locations)
    ]
    ev.location_crosswalks.load_dataframe(
        df=ngen_usgs_eval_xwalk_df,
        write_mode="append"
    )
    # Add the configuration names.
    ev.configurations.add(
        Configuration(
            name=ngen_configuration_name,
            type="secondary",
            description="Nextgen simulation output"
        )
    )
    ev.download.configurations(
        name="usgs_observations",
        load=True
    )
    ev.download.configurations(
        name="nwm30_retrospective",
        load=True
    )
    # Load the NGIAB output.
    ev.secondary_timeseries.load_parquet(in_path=ngen_output_cache_dir)
    # Download primary (USGS) timeseries from the TEEHR-Cloud warehouse.
    ev.download.primary_timeseries(
        configuration_name="usgs_observations",
        primary_location_id=teehr_usgs_locations,
        start_date=start_date,
        end_date=end_date,
        load=True,
        page_size=2000000,
        timeout=120
    )
    # Download secondary (NWM) timeseries from the TEEHR-Cloud warehouse.
    ev.download.secondary_timeseries(
        configuration_name="nwm30_retrospective",
        primary_location_id=teehr_usgs_locations,
        start_date=start_date,
        end_date=end_date,
        load=True,
        page_size=2000000,
        timeout=120
    )
    # Write metrics to a new table (overwrite if it already exists).
    (
        ev
        .joined_timeseries_view()
        .aggregate(
            group_by=["primary_location_id", "configuration_name"],
            metrics=SIM_METRICS
        )
        .order_by(["primary_location_id", "configuration_name"])
        .write(
            write_mode="create_or_replace",
            table_name=NGEN_METRICS_TABLE_NAME
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_folder_stem",
        type=str,
        help="Stem of the data folder (basename of DATA_FOLDER_PATH)"
    )
    parser.add_argument(
        "--teehr_evaluation_dir",
        type=str,
        help="Path to the directory where TEEHR evaluation output will be stored"
    )
    args = parser.parse_args()
    if args.data_folder_stem is None:
        # args.data_folder_stem = "AWI_16_2863657_007"  # for testing locally
        raise ValueError("Please provide a data folder stem using --data_folder_stem")
    data_folder_stem = re.sub(
        r"[^a-zA-Z0-9_]",
        "_",
        args.data_folder_stem
    ).lower()
    if args.teehr_evaluation_dir is None:
        # args.teehr_evaluation_dir = "/home/slamont/temp/ngiab_teehr_warehouse"  # for testing locally
        raise ValueError("Please provide a TEEHR evaluation directory using --teehr_evaluation_dir")
    teehr_evaluation_dir = Path(args.teehr_evaluation_dir)
    main(data_folder_stem, teehr_evaluation_dir)
