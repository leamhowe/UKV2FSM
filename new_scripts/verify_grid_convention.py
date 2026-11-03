"""
verify_grid_convention.py
=========================
Are the coordinate labels written by UKV2FSM (x = -239000 + 2000 i,
y = 1223000 - 2000 j) cell CENTRES or cell CORNERS?

Two tests against the physical world, independent of the GRIB header:

  A. STATIONS (primary). Every MIDAS site in the UK with a surveyed elevation -
     thousands, from the SRCE station master file - is matched to a cell under
     each trial offset. The offset where station heights and model orography
     agree best is where the cells really are. Resampling the stations 100
     times shows how tightly that offset is pinned down.

  B. COASTLINE, only if the constants file carries a land-sea mask. A first
     version used "orography > 0" as the land mask; on the real UKV field that
     proxy fails (smoothed orography spills over the sea near the coast, giving
     ~72% agreement at every offset and no peak), so it is no longer used.

  best offset (0, 0)          -> the labels ARE centres; the old code was right
  best offset (+1000, -1000)  -> the labels are the NW CORNERS; the true centres
                                 are 1 km east and 1 km south of them

    python verify_grid_convention.py
    python verify_grid_convention.py --netcdf /path/to/Tair201601.nc

--netcdf also reads the x/y written into one of your own converter files, so
the result is tied to your actual files and not just to the formula.
"""

import argparse
import numpy as np
import pygrib
import geopandas as gpd
import shapely

GRIB = "/badc/ukmo-nwp/data/ukv-grib/constants/constant_u1096_ng_umqv_Wholesale.grib"
SHP = "/home/users/leamhowe/phd/boundaries/scotland/scotland.shp"

NX, NY = 548, 704
X_LABEL = -239000 + 2000 * np.arange(NX)      # what UKV2FSM writes as x
Y_LABEL = 1223000 - 2000 * np.arange(NY)      # what UKV2FSM writes as y


def orography():
    grbs = pygrib.open(GRIB)
    for sel in (dict(name="Geometrical height"), dict(parameterName="Orography")):
        try:
            g = grbs.select(**sel)[0]
            break
        except (ValueError, KeyError):
            g = None
    if g is None:
        grbs.rewind()
        g = grbs.message(1)
    hdr = {}
    for k in ("X1", "Y1", "Di", "Dj"):
        try:
            hdr[k] = g[k]
        except (KeyError, RuntimeError):
            pass
    return np.asarray(g.values, float), hdr


SRCE = "/badc/ukmo-midas/metadata/SRCE/SRCE.DATA"


def list_constants():
    """Every field in the constants file, so a land-sea mask can be found."""
    out = []
    for m in pygrib.open(GRIB):
        out.append((m.messagenumber, getattr(m, "name", "?"), getattr(m, "shortName", "?"),
                    getattr(m, "discipline", "?"), getattr(m, "parameterCategory", "?"),
                    getattr(m, "parameterNumber", "?")))
    return out


def land_sea_mask(msgs):
    """Land-sea mask or land fraction if the file has one (GRIB2 0/2/0)."""
    for num, name, short, d, c, p in msgs:
        if ("land" in str(name).lower() and ("mask" in str(name).lower()
                                             or "cover" in str(name).lower()
                                             or "fraction" in str(name).lower())) \
                or short in ("lsm", "lsmask") or (d, c, p) == (2, 0, 0):
            g = pygrib.open(GRIB).message(num)
            return np.asarray(g.values, float), f"{name} ({short})"
    return None, None


# ---------------------------------------------------------------- stations
def srce_stations():
    """All MIDAS sites with a location and elevation (UK-wide)."""
    import pandas as pd
    from pyproj import Transformer
    df = pd.read_csv(SRCE, header=None, usecols=[0, 2, 3, 13, 14, 22, 23],
                     engine="python", skipinitialspace=True)
    df.columns = ["id", "lat_std", "lon_std", "end", "elev", "lat_w", "lon_w"]
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["lat"] = df["lat_w"].fillna(df["lat_std"])
    df["lon"] = df["lon_w"].fillna(df["lon_std"])
    df = df.dropna(subset=["id", "lat", "lon", "elev"])
    df = df[(df["elev"] > 0) & (df["elev"] < 1400)]
    df = df.sort_values("end").drop_duplicates("id", keep="last")
    e, n = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(
        df["lon"].values, df["lat"].values)
    df["E"], df["N"] = e, n
    # stations at the same site repeat the same test point; keep one per 100 m
    df["site"] = (np.round(e / 100)).astype(int).astype(str) + "_" + \
                 (np.round(n / 100)).astype(int).astype(str)
    return df.drop_duplicates("site")[["E", "N", "elev"]].reset_index(drop=True)


def station_scan(oro, E, N, elev, offs):
    """Median |station elevation - model orography| for each hypothesis that
    the true cell centres are at label + (dx, dy)."""
    out = np.full((len(offs), len(offs)), np.nan)
    for a, dy in enumerate(offs):
        for b, dx in enumerate(offs):
            i = np.rint((E - (X_LABEL[0] + dx)) / 2000).astype(int)
            j = np.rint(((Y_LABEL[0] + dy) - N) / 2000).astype(int)
            ok = (i >= 0) & (i < NX) & (j >= 0) & (j < NY)
            out[a, b] = np.median(np.abs(oro[j[ok], i[ok]] - elev[ok]))
    return out


def station_test(oro, st, span=2000, step=250, n_boot=100, seed=0):
    offs = np.arange(-span, span + 1, step)
    E, N, z = st["E"].values, st["N"].values, st["elev"].values
    inside = ((E > X_LABEL[0] - 1000) & (E < X_LABEL[-1] + 1000)
              & (N < Y_LABEL[0] + 1000) & (N > Y_LABEL[-1] - 1000))
    E, N, z = E[inside], N[inside], z[inside]
    print(f"  {len(E):,} distinct MIDAS sites inside the grid "
          f"({(z > 200).sum():,} above 200 m)")

    mad = station_scan(oro, E, N, z, offs)
    a, b = np.unravel_index(np.nanargmin(mad), mad.shape)
    i0 = int(np.where(offs == 0)[0][0])
    at = lambda dx, dy: mad[np.where(offs == dy)[0][0], np.where(offs == dx)[0][0]]
    print(f"\n  median |station - model| height:")
    print(f"    labels as CENTRES (0, 0)            : {mad[i0, i0]:6.1f} m")
    print(f"    GRIB header position (+1000, -1000)  : {at(1000, -1000):6.1f} m")
    print(f"    best: dx={offs[b]:+.0f} dy={offs[a]:+.0f}                  : {mad[a, b]:6.1f} m")

    # How firmly is the best offset determined? Resample stations.
    rng = np.random.default_rng(seed)
    best = []
    for _ in range(n_boot):
        k = rng.integers(0, len(E), len(E))
        m = station_scan(oro, E[k], N[k], z[k], offs)
        r, c = np.unravel_index(np.nanargmin(m), m.shape)
        best.append((offs[c], offs[r]))
    best = np.array(best)
    near_hdr = np.mean((np.abs(best[:, 0] - 1000) <= 250) & (np.abs(best[:, 1] + 1000) <= 250))
    near_zero = np.mean((np.abs(best[:, 0]) <= 250) & (np.abs(best[:, 1]) <= 250))
    print(f"\n  resampled {n_boot}x: best dx {np.percentile(best[:, 0], 5):+.0f} to "
          f"{np.percentile(best[:, 0], 95):+.0f} m, dy {np.percentile(best[:, 1], 5):+.0f} to "
          f"{np.percentile(best[:, 1], 95):+.0f} m (90% range)")
    print(f"    within 250 m of the header position : {near_hdr:.0%} of resamples")
    print(f"    within 250 m of (0, 0)              : {near_zero:.0%} of resamples")
    return offs, mad, near_hdr, near_zero


def scotland():
    gdf = gpd.read_file(SHP)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:27700")
    gdf = gdf.to_crs("EPSG:27700")
    try:
        geom = gdf.geometry.union_all()
    except AttributeError:
        geom = gdf.geometry.unary_union
    shapely.prepare(geom)
    return geom


def coastline_test(land, geom, band_km=3.0, step=250, span=2000):
    xx, yy = np.meshgrid(X_LABEL, Y_LABEL)
    # North of 56 N (N > 670 km) the only land is Scottish - England and
    # Ireland both lie further south - and E < 600 km keeps Norway out. So
    # inside this box, "not in the Scotland polygon" really does mean sea.
    box = (yy > 670000) & (xx > 0) & (xx < 600000)
    band_geom = geom.boundary.buffer(band_km * 1000)
    shapely.prepare(band_geom)
    near = box & shapely.contains_xy(band_geom, xx, yy)
    x, y = xx[near], yy[near]
    land_model = land[near]
    print(f"  {near.sum():,} cells within {band_km:.0f} km of the coast; "
          f"{land_model.mean():.0%} land in the model")

    offs = np.arange(-span, span + 1, step)
    score = np.empty((len(offs), len(offs)))
    for a, dy in enumerate(offs):
        for b, dx in enumerate(offs):
            land_map = shapely.contains_xy(geom, x + dx, y + dy)
            score[a, b] = (land_map == land_model).mean()
    return offs, score


def report(offs, score):
    i0 = int(np.where(offs == 0)[0][0])
    a, b = np.unravel_index(np.argmax(score), score.shape)
    at = lambda dx, dy: score[np.where(offs == dy)[0][0], np.where(offs == dx)[0][0]]
    print(f"\n  agreement treating labels as CENTRES  (0, 0)       : {score[i0, i0]:.2%}")
    print(f"  agreement at the GRIB header position (+1000, -1000): {at(1000, -1000):.2%}")
    print(f"  best offset: dx={offs[b]:+.0f} m, dy={offs[a]:+.0f} m  -> {score[a, b]:.2%}")

    print("\n  agreement by offset (rows dy, columns dx; best marked *):")
    print("        " + "".join(f"{d:>8.0f}" for d in offs))
    for r, dy in enumerate(offs):
        cells = "".join(f"{score[r, c]:>7.1%}" + ("*" if (r, c) == (a, b) else " ")
                        for c in range(len(offs)))
        print(f"  {dy:>6.0f}{cells}")

    bx, by = offs[b], offs[a]
    if abs(bx) <= 250 and abs(by) <= 250:
        print("\n  VERDICT: the labels behave as cell centres. The half-cell diagnosis "
              "is WRONG\n  and nothing needs changing.")
    elif abs(bx - 1000) <= 250 and abs(by + 1000) <= 250:
        print("\n  VERDICT: the data sit ~1 km east and ~1 km south of the labels. The "
              "labels are\n  the north-west CORNERS of the cells. Reading them as centres "
              "(xarray, CF, nearest-\n  neighbour lookup) misplaces every value by "
              "half a cell in each direction.")
    else:
        print(f"\n  VERDICT: inconclusive - best offset ({bx:+.0f}, {by:+.0f}) matches "
              f"neither hypothesis.")


def check_netcdf(path):
    import xarray as xr
    ds = xr.open_dataset(path)
    x, y = ds["x"].values, ds["y"].values
    print(f"\n  {path}")
    print(f"  x: {x[0]:.0f} ... {x[-1]:.0f} ({len(x)} values)   "
          f"y: {y[0]:.0f} ... {y[-1]:.0f} ({len(y)} values)")
    i = np.where(np.isclose(X_LABEL, x[0]))[0]
    j = np.where(np.isclose(Y_LABEL, y[0]))[0]
    if len(i) and len(j):
        print(f"  -> these are the UKV2FSM labels: first cell is column {i[0]}, "
              f"row {j[0]} of the full grid, labelled at its corner, not its centre")
    else:
        print("  -> these do NOT match the UKV2FSM label formula; this file uses a "
              "different grid definition")
    bounds = {v: ds[v].attrs.get("bounds") for v in ("x", "y")}
    print(f"  bounds attributes: {bounds}  (None means tools will read x/y as centres)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--netcdf", help="one of your converter netCDFs, to check its labels")
    ap.add_argument("--boot", type=int, default=100)
    args = ap.parse_args()

    oro, hdr = orography()
    print("GRIB header (cm):", hdr)
    if hdr:
        print(f"  -> first grid POINT at E={hdr['X1'] / 100:.0f}, N={hdr['Y1'] / 100:.0f}; "
              f"the converter labels it E={X_LABEL[0]}, N={Y_LABEL[0]}")

    print("\nA. STATION TEST (all UK MIDAS sites)")
    offs, mad, near_hdr, near_zero = station_test(oro, srce_stations(), n_boot=args.boot)

    print("\nB. COASTLINE TEST")
    msgs = list_constants()
    lsm, lsm_name = land_sea_mask(msgs)
    if lsm is None:
        print("  no land-sea mask in the constants file - skipped. Fields available:")
        for num, name, short, d, c, p in msgs:
            print(f"    {num:>3}  {name:<40} {short:<10} ({d}/{c}/{p})")
    else:
        print(f"  using {lsm_name}, land where >= 0.5")
        coast = coastline_test(lsm >= 0.5, scotland())
        report(*coast)

    print("\n" + "=" * 70)
    if near_hdr >= 0.9:
        print("CONCLUSION: the station test places the cell centres at the GRIB header\n"
              f"position in {near_hdr:.0%} of resamples. The converter's labels are the\n"
              "cells' north-west corners, 1 km west and 1 km north of the centres.")
    elif near_zero >= 0.9:
        print("CONCLUSION: the station test places the cell centres at the labels\n"
              f"themselves in {near_zero:.0%} of resamples. The labels ARE centres, the\n"
              "half-cell diagnosis is wrong, and nothing needs changing.")
    else:
        print("CONCLUSION: not settled - the best offset is not firmly at either\n"
              "position. Do not change anything on this evidence.")

    if args.netcdf:
        print("\nYour file:")
        check_netcdf(args.netcdf)


if __name__ == "__main__":
    main()