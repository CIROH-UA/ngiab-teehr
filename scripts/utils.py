"""A collection of helper functions for the TEEHR-Nextgen project."""
import glob
import os
import logging
import sqlite3
import json
from typing import List
from pathlib import Path

import pandas as pd
import xarray as xr

from teehr.fetching.utils import write_timeseries_parquet_file

logger = logging.getLogger(__name__)

UNIT_NAME = "m^3/s"
VARIABLE_NAME = "streamflow_hourly_inst"


def get_simulation_output_format(folder_to_eval):
    """
    determines the output format from files in the outputs/troute folder
    the troute config was called ngen.yaml and now is called troute.yaml
    so we can just check the output folder for the types
    """
    # check for netcdf files
    nc_file = folder_to_eval / "outputs" / "troute" / "*.nc"
    nc_files = glob.glob(str(nc_file))
    if len(nc_files) > 0:
        return "netcdf"
    # check for csv files
    csv_file = folder_to_eval / "outputs" / "troute" / "*.csv"
    csv_files = glob.glob(str(csv_file))
    if len(csv_files) > 0:
        return "csv"
    # check for parquet files
    parquet_file = folder_to_eval / "outputs" / "troute" / "*.parquet"
    parquet_files = glob.glob(str(parquet_file))
    if len(parquet_files) > 0:
        return "parquet"
    raise FileNotFoundError(
        "No .nc, .csv, or .parquet output files found "
        "in the outputs/troute folder"
    )


def write_parquet_output_to_cache(
    ngen_stem_ids: List[str],
    folder_to_eval: Path,
    ngen_configuration_name: str,
    secondary_cache_dir: Path
):
    """
    Read Nextgen simulation output from parquet file for a single gage.

    Convert the file to TEEHR secondary timeseries format and write to the cache
    as parquet.
    """
    parquet_file = folder_to_eval / "outputs" / "troute_parquet" / "*.parquet"
    parquet_files = glob.glob(str(parquet_file))
    if len(parquet_files) == 0:
        raise FileNotFoundError(
            "No parquet file found in the outputs/troute folder"
        )
    if len(parquet_files) > 1:
        logger.warning(
            "Multiple parquet files found in the outputs/troute folder"
        )
        logger.warning("Using the most recent file")
        parquet_files.sort(key=os.path.getmtime)
        file_to_open = parquet_files[-1]
    if len(parquet_files) == 1:
        file_to_open = parquet_files[0]
    all_output = pd.read_parquet(file_to_open)
    all_output.rename(
        columns={
            "time": "value_time",
            "flow": "value",
            "feature_id": "location_id"
        }, inplace=True
    )
    all_output.drop(columns=["type", "velocity", "depth", "nudge"], inplace=True)
    # limit location_id to ngen_stem_ids
    # all_output = all_output[all_output["location_id"].isin([int(id_stem) for id_stem in ngen_stem_ids])]
    all_output["location_id"] = "ngen-" + all_output["location_id"].astype(str)
    all_output["reference_time"] = None
    all_output["unit_name"] = UNIT_NAME
    all_output["variable_name"] = VARIABLE_NAME
    all_output["configuration_name"] = ngen_configuration_name
    all_output["member"] = None
    write_timeseries_parquet_file(
        filepath=secondary_cache_dir / f"ngen_output_{ngen_configuration_name}.parquet",
        data=all_output,
        timeseries_type="secondary",
        overwrite_output=True
    )


def write_netcdf_output_to_cache(
    ngen_stem_ids: List[str],
    folder_to_eval: Path,
    ngen_configuration_name: str,
    secondary_cache_dir: Path
):
    """Read Nextgen simulation output from netcdf file for a single gage.

    Convert the file to TEEHR secondary timeseries format and write to the cache
    as parquet.

    Ref: https://github.com/JoshCu/ngiab_eval/blob/b39e5af6eb382d64f07a5c55a7acb0109dd26f8f/ngiab_eval/core.py#L109  # noqa
    """
    nc_file = folder_to_eval / "outputs" / "troute" / "*.nc"
    nc_files = glob.glob(str(nc_file))
    if len(nc_files) == 0:
        raise FileNotFoundError(
            "No netcdf file found in the outputs/troute folder"
        )
    if len(nc_files) > 1:
        logger.warning(
            "Multiple netcdf files found in the outputs/troute folder"
        )
        logger.warning("Using the most recent file")
        nc_files.sort(key=os.path.getmtime)
        file_to_open = nc_files[-1]
    if len(nc_files) == 1:
        file_to_open = nc_files[0]
    all_output = xr.open_dataset(file_to_open)
    all_output = all_output.drop_vars(
        ["type", "velocity", "depth", "nudge"]
    )
    all_output = all_output.rename(
        {"time": "value_time", "flow": "value", "feature_id": "location_id"}
    )
    for id_stem in ngen_stem_ids:
        gage_output = all_output.sel(location_id=int(id_stem))
        gage_output = gage_output.to_dataframe().reset_index()
        gage_output["reference_time"] = None
        gage_output["unit_name"] = UNIT_NAME
        gage_output["variable_name"] = VARIABLE_NAME
        gage_output["configuration_name"] = ngen_configuration_name
        gage_output["member"] = None
        gage_output["location_id"] = "ngen-" + gage_output["location_id"].astype(str)
        write_timeseries_parquet_file(
            filepath=secondary_cache_dir / f"ngen_output_{id_stem}.parquet",
            data=gage_output,
            timeseries_type="secondary",
            overwrite_output=True
        )


def write_csv_output_to_cache(
    ngen_stem_ids: List[str],
    folder_to_eval: Path,
    ngen_configuration_name: str,
    secondary_cache_dir: Path
):
    """
    NOTE: Not sure if this is still needed.

    Ref: https://github.com/JoshCu/ngiab_eval/blob/2e8fd96b21a369bb93b2a491b0c303a4018a290e/ngiab_eval/core.py
    """
    csv_file = folder_to_eval / "outputs" / "troute" / "*.csv"
    csv_files = glob.glob(str(csv_file))
    if len(csv_files) == 0:
        raise FileNotFoundError(
            "No CSV file found in the outputs/troute folder"
        )
    if len(csv_files) > 1:
        logger.warning("Multiple CSV files found in the outputs/troute folder")
        logger.warning("Using the most recent file")
        csv_files.sort(key=os.path.getmtime)
        file_to_open = csv_files[-1]
    if len(csv_files) == 1:
        file_to_open = csv_files[0]
    all_output = pd.read_csv(file_to_open)
    all_output.rename(
        columns={
            "current_time": "value_time",
            "flow": "value",
            "featureID": "location_id"
        }, inplace=True
    )
    # limit location_id to ngen_stem_ids
    all_output = all_output[all_output["location_id"].isin([int(id_stem) for id_stem in ngen_stem_ids])]
    all_output["location_id"] = "ngen-" + all_output["location_id"].astype(str)
    all_output["reference_time"] = None
    all_output["unit_name"] = UNIT_NAME
    all_output["variable_name"] = VARIABLE_NAME
    all_output["configuration_name"] = ngen_configuration_name
    all_output["member"] = None
    write_timeseries_parquet_file(
        filepath=secondary_cache_dir / f"ngen_output_{ngen_configuration_name}.parquet",
        data=all_output,
        timeseries_type="secondary",
        overwrite_output=True
    )


def get_gages_from_hydrofabric(folder_to_eval):
    """
    Get the gages from the hydrofabric.

    Ref: https://github.com/JoshCu/ngiab_eval/blob/2e8fd96b21a369bb93b2a491b0c303a4018a290e/ngiab_eval/core.py
    """
    # search inside the folder for _subset.gpkg recursively
    gpkg_file = None
    config_dir = os.path.join(folder_to_eval, "config")
    for root, dirs, files in os.walk(config_dir):
        for file in files:
            if file.endswith(".gpkg"):
                gpkg_file = os.path.join(root, file)
                break

    if gpkg_file is None:
        raise FileNotFoundError("No subset.gpkg file found in folder")

    # figure out if the hf is v20.1 or v2.2
    # 2.2 has a pois table, 20.1 does not
    with sqlite3.connect(gpkg_file) as conn:
        results = conn.execute(
            "SELECT count(*) FROM gpkg_contents WHERE table_name = 'pois'"
        ).fetchall()

    if results[0][0] == 0:
        with sqlite3.connect(gpkg_file) as conn:
            results = conn.execute(
                "SELECT id, rl_gages FROM flowpath_attributes WHERE rl_gages IS NOT NULL"
            ).fetchall()
            # Fixme Take only the first result if a gage shows up more than once.
            # Should be fixed upstream in hydrofabric with only error handling here.
            results = [(r[0], r[1].split(",")[0]) for r in results]
    else:
        with sqlite3.connect(gpkg_file) as conn:
            results = conn.execute(
                "SELECT id, gage FROM 'flowpath-attributes' WHERE gage IS NOT NULL"
            ).fetchall()

    return results


def get_simulation_start_end_time(folder_to_eval):
    """
    Get start and  end time of the simulation.

    Ref: https://github.com/JoshCu/ngiab_eval/blob/2e8fd96b21a369bb93b2a491b0c303a4018a290e/ngiab_eval/core.py#L77 # noqa
    """
    realization = folder_to_eval / "config" / "realization.json"
    with open(realization) as f:
        realization = json.load(f)
    start = realization["time"]["start_time"]
    end = realization["time"]["end_time"]
    return start, end
