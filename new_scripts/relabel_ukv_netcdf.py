"""
relabel_ukv_netcdf.py
=====================
Correct the x / y / lat / lon coordinates in netCDF files written by UKV2FSM,
IN PLACE. The data arrays are not touched - every value is already in the
right cell; only the coordinate labels move.

UKV2FSM wrote each cell's NORTH-WEST CORNER as its coordinate
(x = -239000 + 2000 i, y = 1223000 - 2000 j). netCDF/CF tools read coordinates
as cell CENTRES, which sit 1 km east and 1 km south of those corners
(x = -238000 + 2000 i, y = 1222000 - 2000 j, as in the GRIB header).

    python relabel_ukv_netcdf.py /path/to/UKV_nc/2016_2025_FSM_new            # dry run
    python relabel_ukv_netcdf.py /path/to/UKV_nc/2016_2025_FSM_new --apply    # write

Safe to re-run. Whether a file needs correcting is decided from its own
coordinate values: old corner labels fall on ODD thousands of metres
(201000, 847000), corrected centres on EVEN thousands (202000, 846000). A file
already corrected is skipped, so nothing can ever be shifted twice. Files
whose coordinates match neither pattern are reported and left alone.

Point it at any directory of UKV2FSM-derived files: the monthly forcing, the
constants (elevation.nc) and FSM output if it copied the input coordinates.

It also writes CF cell bounds (x_bnds, y_bnds), so each file states both
conventions explicitly: centres as the coordinates, edges in the bounds.
Anything that needs the cell edges (building a GeoTIFF, drawing cells with
pcolormesh) should read the bounds rather than assume. Files corrected by an
earlier run without bounds get them added.
"""

import os
import glob
import argparse
from datetime import datetime

import numpy as np
from netCDF4 import Dataset
from pyproj import Transformer

TO_LATLON = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def classify(x0, y0):
    """'corners' (needs fixing), 'centres' (already fixed) or 'unknown'."""
    old = np.isclose(np.mod(x0 + 239000, 2000), 0) and np.isclose(np.mod(1223000 - y0, 2000), 0)
    new = np.isclose(np.mod(x0 + 238000, 2000), 0) and np.isclose(np.mod(1222000 - y0, 2000), 0)
    return "corners" if old else "centres" if new else "unknown"


def add_bounds(ds, xc, yc):
    """CF bounds: each cell's two edges, ordered like its coordinate."""
    if "nv" not in ds.dimensions:
        ds.createDimension("nv", 2)
    xb = ds.createVariable("x_bnds", "f8", ("x", "nv"))
    xb[:] = np.column_stack([xc - 1000.0, xc + 1000.0])
    yb = ds.createVariable("y_bnds", "f8", ("y", "nv"))
    yb[:] = np.column_stack([yc + 1000.0, yc - 1000.0])      # y runs north -> south
    ds["x"].bounds = "x_bnds"
    ds["y"].bounds = "y_bnds"


def process(path, apply):
    with Dataset(path, "r+" if apply else "r") as ds:
        if "x" not in ds.variables or "y" not in ds.variables:
            return "no x/y", None
        x = np.array(ds["x"][:], dtype=float)
        y = np.array(ds["y"][:], dtype=float)
        state = classify(x[0], y[0])
        if state == "centres" and "x_bnds" not in ds.variables:
            # corrected before bounds were written - add them now
            if not apply:
                return "would add bounds", None
            add_bounds(ds, x, y)
            return "added bounds", None
        if state != "corners":
            return state, None

        xc, yc = x + 1000.0, y - 1000.0
        change = f"x {x[0]:.0f}->{xc[0]:.0f}, y {y[0]:.0f}->{yc[0]:.0f}"
        if not apply:
            return "would fix", change

        ds["x"][:] = xc
        ds["y"][:] = yc
        for v, sn in (("x", "projection_x_coordinate"), ("y", "projection_y_coordinate")):
            ds[v].units = "m"
            ds[v].standard_name = sn
            ds[v].long_name = f"{sn.split('_')[1]} of cell centre, British National Grid"

        if "x_bnds" not in ds.variables:
            add_bounds(ds, xc, yc)

        if "lat" in ds.variables and "lon" in ds.variables:
            lon, lat = TO_LATLON.transform(*np.meshgrid(xc, yc))
            if ds["lat"].shape == lat.shape:
                ds["lat"][:] = lat
                ds["lon"][:] = lon

        ds.setncattr("grid_coordinates_fix",
                     "x/y/lat/lon moved from cell north-west corners to cell centres "
                     "(+1000 m E, -1000 m N) to match the GRIB header; data unchanged")
        hist = ds.getncattr("history") if "history" in ds.ncattrs() else ""
        ds.setncattr("history", f"{datetime.now():%Y-%m-%d %H:%M} relabel_ukv_netcdf.py: "
                                f"coordinates corner->centre\n" + hist)
        return "fixed", change


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--pattern", default="*.nc")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.directory, "**", args.pattern), recursive=True))
    if not files:
        raise SystemExit(f"no files matching {args.pattern} under {args.directory}")

    counts, example = {}, None
    for f in files:
        try:
            state, change = process(f, args.apply)
        except Exception as e:
            state, change = f"error: {type(e).__name__}", str(e)
        counts[state] = counts.get(state, 0) + 1
        if change and example is None:
            example = (os.path.basename(f), change)
        if state.startswith("error") or state == "unknown":
            print(f"  {state:<10} {f}  {change or ''}")

    print(f"\n{len(files)} file(s) under {args.directory}:")
    for k, n in sorted(counts.items()):
        print(f"  {k:<12} {n}")
    if example:
        print(f"  e.g. {example[0]}: {example[1]}")
    if not args.apply and (counts.get("would fix") or counts.get("would add bounds")):
        print("\nDry run - nothing written. Re-run with --apply to correct these files.")


if __name__ == "__main__":
    main()