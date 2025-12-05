# UKV to FSM Converter

This repository contains a high-performance Python pipeline designed to process UK Met Office **UKV (UK Variable resolution)** GRIB files and convert them into NetCDF forcing files suitable for the **Factorial Snow Model (FSM)**.

The pipeline is specifically configured for the **Scottish Mountain domain** but can be adapted for other regions. It handles data extraction, coordinate transformation, physics-based variable derivation, and robust gap-filling for missing model timesteps.

## 🚀 Key Features

  * **Parallel Processing:** Uses `ProcessPoolExecutor` to process multiple months simultaneously, significantly reducing runtime on HPC environments.
  * **Optimized I/O:** Implements linear GRIB reading (scanning) rather than random access, reducing I/O bottlenecks.
  * **Robust Gap-Filling Strategy:**
      * **Automatic Backup Search:** If a standard 00:00 UTC run is missing, the script automatically searches for the previous day's 12:00 UTC run to bridge the gap.
      * **T+0 Correction:** Backfills missing flux data at the first timestep (T+0) using T+1 data.
      * **Temporal Interpolation:** Identifies and linearly interpolates any remaining `NaN` gaps (e.g., if a backup file falls short of covering the full 24h cycle).
  * **Resilient GRIB Parsing:** Uses raw GRIB2 keys (Discipline, Category, Number) to identify variables, bypassing issues where libraries like `pygrib` fail to recognize local Met Office parameter names (e.g., "Total Cloud Cover" appearing as "unknown").

## 🛠 Dependencies

The scripts rely on the following Python packages. If running on JASMIN, these are available in the `jaspy` environment.

  * `python >= 3.8`
  * `numpy`
  * `netCDF4`
  * `pygrib` (with ECCodes)
  * `pyproj`
  * `tqdm` (optional, for progress bars if enabled)

## 📂 Repository Structure

  * **`UKV2FSM_year.py`**: The main entry point. Orchestrates the parallel processing of months over a specified date range.
  * **`UKV2FSM_month.py`**: The core worker script. Handles GRIB file selection, reading, physics calculations, and NetCDF writing for a single month.
  * **`sub_ukv2fsm.sh`**: SLURM batch submission script optimized for HPC (e.g., JASMIN/ARCHER2).

## ⚙️ Configuration

### Domain Definitions

The spatial domain is hardcoded in `UKV2FSM_month.py`. To change the region, modify the slice indices:

```python
# Scottish mountain domain bounds
XMIN, XMAX = 220, 290
YMIN, YMAX = 188, 244
```

### Input/Output Paths

Default paths are set for the JASMIN file system structure. Update the `UKV_dir` and `outdir` arguments in the function definitions or script headers if running elsewhere.

## 🏃 Usage

### 1\. HPC / SLURM Submission (Recommended)

Use the provided batch script to submit a job. The script requests 12 CPUs to process a full year in parallel (1 month per core).

```bash
# Syntax: sbatch sub_ukv2fsm.sh <START_DATE> <END_DATE>
sbatch sub_ukv2fsm.sh 2016-10-01 2020-09-30
```

### 2\. Manual Execution

You can run the script directly from the command line. The third argument is optional (number of parallel workers, defaults to 4).

```bash
# Syntax: python UKV2FSM_year.py <START_DATE> <END_DATE> <NUM_WORKERS>
python UKV2FSM_year.py 2016-10-01 2017-09-30 12
```

## 📊 Output Variables

The script generates individual NetCDF files for each variable per month (format: `VarNameYYYYMM.nc`).

| Variable | FSM Name | Units | Notes |
| :--- | :--- | :--- | :--- |
| Surface Pressure | `PSurf` | Pa | Corrected for elevation differences |
| Specific Humidity | `Qair` | kg/kg | Derived from Dewpoint and Pressure |
| Rainfall Rate | `Rainf` | kg/m²/s | Partitioned using Snow Fraction |
| Snowfall Rate | `Snowf` | kg/m²/s | Partitioned using Snow Fraction |
| Shortwave Rad | `SWdown` | W/m² | Downward flux |
| Longwave Rad | `LWdown` | W/m² | Downward flux |
| Air Temperature | `Tair` | K | 1.5m Temperature |
| Wind Speed | `Wind` | m/s | 10m Wind Speed |
| Wind Direction | `WindDir` | Degrees | 10m Wind Direction |
| Total Cloud Cover | `TotCloud` | % | Extracted via raw GRIB keys |
| Snow Depth | `SnowDepth` | m | Surface snow depth |

## 🧠 Methodology details

### Variable Extraction

Variables are extracted from UKV "Wholesale" files. Due to inconsistent naming metadata in older GRIB files, **Cloud Cover** and **Snow Depth** are extracted using GRIB2 raw keys:

  * Total Cloud Cover: `(Discipline=0, Category=6, Number=1)`
  * Snow Depth: `(Discipline=0, Category=1, Number=11)`

### Derived Physics

  * **Specific Humidity (`Qair`):** Calculated from Dewpoint Temperature (`Td`) and corrected Surface Pressure (`Ps`).
  * **Pressure Correction:** `Ps` is adjusted hydrostatically based on the difference between the model grid height and the true orography.
  * **Precipitation Partitioning:** Total precipitation is split into `Rainf` and `Snowf` using the UKV `Snow Fraction` variable.

### Gap Filling Logic

1.  **Primary Search:** Looks for `00:00` run of the target day.
2.  **Backup Search:** If missing, looks for `12:00` run of the *previous* day (using forecast hours 12–36).
3.  **Deep Search:** Scans up to 5 days prior for a valid run.
4.  **T+0 Fix:** If the first hour of a file is empty (common for flux variables), data is backfilled from T+1.
5.  **Interpolation:** If gaps remain (e.g., missing 18:00 UTC due to a short backup run), a linear interpolation is applied to fill the void using the surrounding valid timesteps.

## 📝 Authors

  * **Leam Howe** (PhD Researcher, UoE)
  * **Richard Essery** (Prof, UoE)

## 📄 License

