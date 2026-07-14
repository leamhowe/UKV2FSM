"""
Convert UKV grib files to FSM netCDF input files.

Per-region version: instead of extracting one hardcoded rectangle, this reads a
directory of snowpatch GeoJSON files (EPSG:27700) and, for each snowpatch,
extracts every UKV (2 km) grid cell that the 5 km region overlaps. One set of
NetCDF forcing files is written per snowpatch into its own sub-directory.

Authors: Leam Howe, Richard Essery (UoE)
"""
from calendar import monthrange
from datetime import date, timedelta
from netCDF4 import Dataset
import numpy as np
import pygrib
from pyproj import Transformer
import os
import glob
import json
import gc

# =====================================================================
# FULL UKV GRID DEFINITION (no pre-slicing - regions are cut out later)
# =====================================================================
_x = np.arange(-239000, 857000, 2000)      # eastings  (ascending)
_y = np.arange(1223000, -185000, -2000)     # northings (descending)
_transformer = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
_xx, _yy = np.meshgrid(_x, _y)
_LON_FULL, _LAT_FULL = _transformer.transform(_xx, _yy)
_NY_FULL, _NX_FULL = _LAT_FULL.shape

CELL = 2000.0  # UKV cell size in metres

# Default location of the snowpatch GeoJSONs (override via the function arg)
GEOJSON_DIR = ('/home/users/leamhowe/sensecdt/snowpatch_locations/'
               'snowpatch_locations_AW_condensed_5km_geojsons')

# Cache so the GeoJSONs are only parsed once per worker process
_REGION_CACHE = {}


# =====================================================================
# REGION DEFINITION FROM GEOJSON
# =====================================================================
def _bbox_to_slice(coords, lo, hi, cell=CELL):
    """
    Return (i0, i1) such that coords[i0:i1] are every cell whose 2 km footprint
    overlaps the interval [lo, hi]. Works for ascending OR descending coords
    because the mask is built on values and coords are monotonic, so the
    selected indices are contiguous.
    """
    half = cell / 2.0
    mask = (coords + half > lo) & (coords - half < hi)
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return 0, 0
    return int(idx.min()), int(idx.max()) + 1


def load_regions(geojson_dir=GEOJSON_DIR):
    """
    Parse every *.geojson in geojson_dir and return a list of region dicts.
    Each region records the contiguous UKV index window (y0:y1, x0:x1) covering
    the union bounding box of its tiles, plus the sliced coordinate grids.
    """
    if geojson_dir in _REGION_CACHE:
        return _REGION_CACHE[geojson_dir]

    regions = []
    paths = sorted(glob.glob(os.path.join(geojson_dir, '*.geojson')))
    if not paths:
        raise FileNotFoundError(f"No .geojson files found in {geojson_dir}")

    for path in paths:
        name = os.path.basename(path)
        for suffix in ('_5x5_tiles.geojson', '.geojson'):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break

        with open(path) as f:
            gj = json.load(f)

        xs, ys = [], []
        for feat in gj.get('features', []):
            geom = feat.get('geometry') or {}
            for ring in geom.get('coordinates', []):
                for pt in ring:
                    xs.append(pt[0])
                    ys.append(pt[1])
        if not xs:
            print(f"WARNING: {name} has no coordinates, skipping.")
            continue

        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)

        x0, x1 = _bbox_to_slice(_x, xmin, xmax)
        y0, y1 = _bbox_to_slice(_y, ymin, ymax)

        if x1 <= x0 or y1 <= y0:
            print(f"WARNING: {name} does not overlap the UKV domain, skipping.")
            continue

        regions.append({
            'name': name,
            'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1,
            'nx': x1 - x0, 'ny': y1 - y0,
            'lat': _LAT_FULL[y0:y1, x0:x1].copy(),
            'lon': _LON_FULL[y0:y1, x0:x1].copy(),
            'xg': _x[x0:x1].copy(),
            'yg': _y[y0:y1].copy(),
        })

    print(f"Loaded {len(regions)} snowpatch regions from {geojson_dir}")
    _REGION_CACHE[geojson_dir] = regions
    return regions


# =====================================================================
# STATIC ELEVATION (full grid - sliced per region later)
# =====================================================================
def get_constant_elevation(ukv_dir):
    """Load the full static elevation field (NY_FULL, NX_FULL)."""
    const_file = os.path.join(ukv_dir, 'constants/constant_u1096_ng_umqv_Wholesale.grib')

    if not os.path.exists(const_file):
        print(f"WARNING: Constants file not found at {const_file}. Using 0 m elevation.")
        return np.zeros((_NY_FULL, _NX_FULL))

    try:
        with pygrib.open(const_file) as grbs:
            try:
                grb = grbs.select(name='Geometrical height')[0]
            except Exception:
                try:
                    grb = grbs.select(parameterName='Orography')[0]
                except Exception:
                    grb = grbs.message(1)
            return grb.values
    except Exception as e:
        print(f"WARNING: Could not load elevation from {const_file}: {e}. Using 0 m elevation.")
        return np.zeros((_NY_FULL, _NX_FULL))


# =====================================================================
# FILE SELECTION STRATEGY (unchanged)
# =====================================================================
def get_file_strategy(year, month, day, UKV_dir):
    s_year, s_month, s_day = str(year), str(month).zfill(2), str(day).zfill(2)

    # 1. Standard 00:00 run
    f1 = f'{UKV_dir}{s_year}/{s_month}/{s_day}/{s_year}{s_month}{s_day}0000_u1096_ng_umqv_Wholesale1.grib'
    f2 = f'{UKV_dir}{s_year}/{s_month}/{s_day}/{s_year}{s_month}{s_day}0000_u1096_ng_umqv_Wholesale2.grib'
    if os.path.exists(f1) and os.path.exists(f2):
        return f1, f2, 0

    # 2. Backup: previous-day runs (12:00 then deeper)
    current = date(int(year), int(month), int(day))
    for lookback in range(1, 5):
        prev = current - timedelta(days=lookback)
        p_year, p_month, p_day = str(prev.year), str(prev.month).zfill(2), str(prev.day).zfill(2)

        if lookback == 1:
            f1 = f'{UKV_dir}{p_year}/{p_month}/{p_day}/{p_year}{p_month}{p_day}1200_u1096_ng_umqv_Wholesale1.grib'
            f2 = f'{UKV_dir}{p_year}/{p_month}/{p_day}/{p_year}{p_month}{p_day}1200_u1096_ng_umqv_Wholesale2.grib'
            if os.path.exists(f1) and os.path.exists(f2):
                print(f"Using Backup: {f1}")
                return f1, f2, 12

        f1 = f'{UKV_dir}{p_year}/{p_month}/{p_day}/{p_year}{p_month}{p_day}0000_u1096_ng_umqv_Wholesale1.grib'
        f2 = f'{UKV_dir}{p_year}/{p_month}/{p_day}/{p_year}{p_month}{p_day}0000_u1096_ng_umqv_Wholesale2.grib'
        if os.path.exists(f1) and os.path.exists(f2):
            print(f"Using Deep Backup: {f1}")
            return f1, f2, 24 * lookback

    return None, None, 0


# =====================================================================
# TEMPORAL GAP FILLING (per-region data dict)
# =====================================================================
def interpolate_missing_time(data_dict, nh, ny, nx):
    """Fill remaining NaN timesteps by linear interpolation over time."""
    cy, cx = ny // 2, nx // 2
    for var_name, arr in data_dict.items():
        missing = np.where(np.isnan(arr[:, cy, cx]))[0]
        if len(missing) == 0:
            continue
        for t in missing:
            prev_t = t - 1
            while prev_t >= 0 and np.isnan(arr[prev_t, cy, cx]):
                prev_t -= 1
            next_t = t + 1
            while next_t < nh and np.isnan(arr[next_t, cy, cx]):
                next_t += 1

            if prev_t >= 0 and next_t < nh:
                w = (t - prev_t) / (next_t - prev_t)
                arr[t] = (1 - w) * arr[prev_t] + w * arr[next_t]
            elif prev_t < 0 and next_t < nh:
                arr[t] = arr[next_t]
            elif prev_t >= 0 and next_t >= nh:
                arr[t] = arr[prev_t]
    return data_dict


# =====================================================================
# MAIN MONTH WORKER
# =====================================================================
def UKV2FSM_month(year, month,
                  UKV_dir='/badc/ukmo-nwp/data/ukv-grib/',
                  outdir='/home/users/leamhowe/sensecdt/UKV_nc/2016_2025_FSM_snowpatches/',
                  geojson_dir=GEOJSON_DIR):

    regions = load_regions(geojson_dir)
    if not regions:
        print(f"No regions to process for {year}-{month}; aborting.")
        return

    if not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)

    nd = monthrange(int(year), int(month))[1]
    nh = 24 * nd

    z_full = get_constant_elevation(UKV_dir)

    # Variable name maps (File 1) and raw GRIB2 (discipline, category, number) maps
    name_map_1 = {
        'Precipitation rate': 'Pr',
        'Pressure reduced to MSL': 'Ps',
        'Temperature': 'Ta',
        'Dew point temperature': 'Td',
        '10 metre wind speed': 'Ua',
        '10 metre wind direction': 'Wd',
    }
    raw_map_1 = {
        (0, 1, 230): 'fr',     # Snow Fraction (name is "unknown" - anchor by raw ID)
    }
    raw_map_2 = {
        (0, 4, 7): 'SW',       # Shortwave
        (0, 5, 3): 'LW',       # Longwave
        (0, 6, 1): 'TCC',      # Total Cloud Cover
        (0, 1, 11): 'SD',      # Snow Depth
    }
    var_keys = ['fr', 'LW', 'Pr', 'Ps', 'SW', 'Ta', 'Td', 'Ua', 'Wd', 'TCC', 'SD']

    # Per-region data containers + per-region orography slice, initialised to NaN
    data = {}
    z_reg = {}
    for reg in regions:
        shape = (nh, reg['ny'], reg['nx'])
        data[reg['name']] = {v: np.full(shape, np.nan, dtype=np.float32) for v in var_keys}
        z_reg[reg['name']] = z_full[reg['y0']:reg['y1'], reg['x0']:reg['x1']]

    # -------------------- READ & EXTRACT --------------------
    for d in range(nd):
        file1, file2, offset = get_file_strategy(year, month, d + 1, UKV_dir)
        if not file1:
            continue

        try:
            grb1 = pygrib.open(file1); msgs1 = grb1.read(); grb1.close()
            grb2 = pygrib.open(file2); msgs2 = grb2.read(); grb2.close()
        except Exception as e:
            print(f"Error reading GRIBs for {year}-{month} day {d+1}: {e}")
            continue

        # File 1: name-based, then raw-ID based (Snow Fraction)
        for m in msgs1:
            try:
                step = int(m.step)          # some fields carry a string stepRange (e.g. "0-1")
            except (TypeError, ValueError):
                continue
            h = step - offset
            if not (0 <= h < 24):
                continue
            target = name_map_1.get(m.name)
            if target is None:
                target = raw_map_1.get((m.discipline, m.parameterCategory, m.parameterNumber))
            if target is None:
                continue
            vals = m.values                       # decode once
            t_idx = 24 * d + h
            for reg in regions:
                data[reg['name']][target][t_idx] = vals[reg['y0']:reg['y1'], reg['x0']:reg['x1']]

        # File 2: raw-ID based (fluxes, cloud, snow depth)
        for m in msgs2:
            try:
                step = int(m.step)
            except (TypeError, ValueError):
                continue
            h = step - offset
            if not (0 <= h < 24):
                continue
            target = raw_map_2.get((m.discipline, m.parameterCategory, m.parameterNumber))
            if target is None:
                continue
            vals = m.values                       # decode once
            t_idx = 24 * d + h
            for reg in regions:
                data[reg['name']][target][t_idx] = vals[reg['y0']:reg['y1'], reg['x0']:reg['x1']]

        # T+0 fix: backfill an empty first timestep (flux fields) from T+1
        if offset == 0:
            t0, t1 = 24 * d, 24 * d + 1
            for reg in regions:
                rd = data[reg['name']]
                if np.isnan(rd['Ta'][t0, reg['ny'] // 2, reg['nx'] // 2]):
                    for v in var_keys:
                        rd[v][t0] = rd[v][t1]

        del msgs1, msgs2

    # -------------------- DERIVE + WRITE PER REGION --------------------
    print(f"Deriving + writing {len(regions)} regions for {year}-{month}...")
    for reg in regions:
        rname = reg['name']
        rd = interpolate_missing_time(data[rname], nh, reg['ny'], reg['nx'])
        z = z_reg[rname]

        Tc = rd['Td'] - 273.15
        with np.errstate(over='ignore', invalid='ignore'):
            e = 611.213 * np.exp(17.5043 * Tc / (Tc + 241.3))
            # Hydrostatic pressure correction (MSL -> grid height)
            rd['Ps'] = rd['Ps'] - 101325 * (1 - (1 - z / 44307.69231) ** 5.253283)
            Qa = 0.622 * e / rd['Ps']
            Rf = (1 - rd['fr']) * rd['Pr']
            Sf = rd['fr'] * rd['Pr']

        region_outdir = os.path.join(outdir, rname)
        os.makedirs(region_outdir, exist_ok=True)

        def writenc(var_array, varname, varunits):
            out_path = os.path.join(region_outdir, f"{varname}{year}{month}.nc")
            with Dataset(out_path, 'w') as nc:
                nc.createDimension('x', reg['nx'])
                nc.createDimension('y', reg['ny'])
                nc.createDimension('time', nh)

                lat_v = nc.createVariable('lat', np.float32, ('y', 'x'))
                lat_v.units = 'degrees_north'; lat_v[:] = reg['lat']
                lon_v = nc.createVariable('lon', np.float32, ('y', 'x'))
                lon_v.units = 'degrees_east'; lon_v[:] = reg['lon']

                xo = nc.createVariable('x', np.float32, ('x',)); xo[:] = reg['xg']
                yo = nc.createVariable('y', np.float32, ('y',)); yo[:] = reg['yg']

                t = nc.createVariable('time', np.float32, ('time',))
                t.units = f'hours since {year}-{month}-01'
                t[:] = np.arange(nh)

                v = nc.createVariable(varname, np.float32, ('time', 'y', 'x'),
                                      fill_value=9999, zlib=True)
                v.units = varunits
                v[:] = np.where(np.isnan(var_array), 9999, var_array)

        writenc(rd['Ps'], 'PSurf', 'Pa')
        writenc(Qa,        'Qair', 'kg/kg')
        writenc(Rf,        'Rainf', 'kg/m2/s')
        writenc(Sf,        'Snowf', 'kg/m2/s')
        writenc(rd['SW'],  'SWdown', 'W/m2')
        writenc(rd['Ta'],  'Tair', 'K')
        writenc(rd['Ua'],  'Wind', 'm/s')
        writenc(rd['LW'],  'LWdown', 'W/m2')
        writenc(rd['Wd'],  'WindDir', 'degrees')
        writenc(rd['TCC'], 'TotCloud', '%')
        writenc(rd['SD'],  'SnowDepth', 'm')
        # writenc(z, 'Elevation', 'm')

    del data, z_reg
    gc.collect()
    print(f"Finished {year}-{month}")