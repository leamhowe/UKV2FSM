"""
Convert UKV grib files to FSM netCDF input files (Robust, Optimized & Feature Complete)
"""
from calendar import monthrange
from netCDF4 import Dataset
import numpy as np
import pygrib
from pyproj import Transformer
from tqdm import tqdm
import os
import gc

# --- PRE-CALCULATE GRID ---
XMIN, XMAX = 220, 290
YMIN, YMAX = 188, 244

_x = np.arange(-239000, 857000, 2000)
_y = np.arange(1223000, -185000, -2000)
_transformer = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
_xx, _yy = np.meshgrid(_x, _y)
_lon, _lat = _transformer.transform(_xx, _yy)

LAT_GRID = _lat[YMIN:YMAX, XMIN:XMAX]
LON_GRID = _lon[YMIN:YMAX, XMIN:XMAX]
X_GRID = _x[XMIN:XMAX]
Y_GRID = _y[YMIN:YMAX]
NY, NX = LAT_GRID.shape

def get_constant_elevation(ukv_dir):
    """Load static elevation data with fallback logic."""
    const_file = os.path.join(ukv_dir, 'constants/constant_u1096_ng_umqv_Wholesale.grib')
    
    if not os.path.exists(const_file):
        print(f"WARNING: Constants file not found at {const_file}. Using 0m elevation.")
        return np.zeros((NY, NX))

    try:
        with pygrib.open(const_file) as grbs:
            # Try by name first
            try:
                grb = grbs.select(name='Geometrical height')[0]
            except:
                try:
                    grb = grbs.select(parameterName='Orography')[0]
                except:
                    # Last resort
                    grb = grbs.message(1)
                    
            return grb.values[YMIN:YMAX, XMIN:XMAX]
            
    except Exception as e:
        print(f"WARNING: Could not load elevation from {const_file}: {e}. Using 0m elevation.")
        return np.zeros((NY, NX))

def get_file_strategy(year, month, day, UKV_dir):
    s_year, s_month, s_day = str(year), str(month).zfill(2), str(day).zfill(2)
    
    # 1. Try Standard Files (00:00 run)
    f1 = f'{UKV_dir}{s_year}/{s_month}/{s_day}/{s_year}{s_month}{s_day}0000_u1096_ng_umqv_Wholesale1.grib'
    f2 = f'{UKV_dir}{s_year}/{s_month}/{s_day}/{s_year}{s_month}{s_day}0000_u1096_ng_umqv_Wholesale2.grib'
    
    if os.path.exists(f1) and os.path.exists(f2):
        return f1, f2, 0 

    # 2. Try Backup (Previous Day 12:00 run)
    from datetime import date, timedelta
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

def interpolate_missing_time(data_dict, nh, ny, nx):
    """
    Fills remaining NaNs by interpolating over time.
    """
    print("  Checking for missing timesteps to interpolate...")
    for var_name in data_dict:
        arr = data_dict[var_name]
        missing_indices = np.where(np.isnan(arr[:, ny//2, nx//2]))[0]
        
        if len(missing_indices) == 0:
            continue
            
        print(f"    Interpolating {len(missing_indices)} missing hours for {var_name}")

        for t in missing_indices:
            prev_t = t - 1
            while prev_t >= 0 and np.isnan(arr[prev_t, ny//2, nx//2]):
                prev_t -= 1
            
            next_t = t + 1
            while next_t < nh and np.isnan(arr[next_t, ny//2, nx//2]):
                next_t += 1
            
            if prev_t >= 0 and next_t < nh:
                weight = (t - prev_t) / (next_t - prev_t)
                arr[t, :, :] = (1 - weight) * arr[prev_t, :, :] + weight * arr[next_t, :, :]
            elif prev_t < 0 and next_t < nh:
                arr[t, :, :] = arr[next_t, :, :]
            elif prev_t >= 0 and next_t >= nh:
                arr[t, :, :] = arr[prev_t, :, :]

    return data_dict

def UKV2FSM_month(year, month, UKV_dir='/badc/ukmo-nwp/data/ukv-grib/', outdir='/home/users/leamhowe/sensecdt/users/leamhowe/UKV_nc/2016_2025_FSM_new/'):
    
    if not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)

    nd = monthrange(int(year), int(month))[1]
    nh = 24 * nd

    z = get_constant_elevation(UKV_dir)

    shape = (nh, NY, NX)
    
    # INITIALIZE WITH NaN TO PREVENT MATH ERRORS ON MISSING DAYS
    data = {
        'fr': np.full(shape, np.nan, dtype=np.float32),
        'LW': np.full(shape, np.nan, dtype=np.float32),
        'Pr': np.full(shape, np.nan, dtype=np.float32),
        'Ps': np.full(shape, np.nan, dtype=np.float32),
        'SW': np.full(shape, np.nan, dtype=np.float32),
        'Ta': np.full(shape, np.nan, dtype=np.float32),
        'Td': np.full(shape, np.nan, dtype=np.float32),
        'Ua': np.full(shape, np.nan, dtype=np.float32),
        'Wd': np.full(shape, np.nan, dtype=np.float32),
        'TCC': np.full(shape, np.nan, dtype=np.float32), # Added Cloud Cover
        'SD': np.full(shape, np.nan, dtype=np.float32),  # Added Snow Depth
    }

    # Map Names for File 1 (These usually work fine by name)
    name_map_1 = {
        'Precipitation rate': 'Pr',
        'Pressure reduced to MSL': 'Ps',
        'Temperature': 'Ta',
        'Dew point temperature': 'Td',
        '10 metre wind speed': 'Ua',
        '10 metre wind direction': 'Wd' 
    }

    # Map RAW IDs for File 2 (Bypasses "unknown" names)
    # Format: (Discipline, Category, Number)
    raw_map_2 = {
        (0, 4, 7): 'SW',    # Shortwave
        (0, 5, 3): 'LW',    # Longwave
        (0, 6, 1): 'TCC',   # Total Cloud Cover
        (0, 1, 11): 'SD'    # Snow Depth
    }

    for d in range(nd):
        day_str = str(d + 1)
        
        file1, file2, offset = get_file_strategy(year, month, d+1, UKV_dir)
        
        if not file1:
            continue

        msgs1 = None
        msgs2 = None

        try:
            grb1 = pygrib.open(file1)
            msgs1 = grb1.read()
            grb1.close()
            
            grb2 = pygrib.open(file2)
            msgs2 = grb2.read()
            grb2.close()
        except Exception as e:
            print(f"Error reading GRIBs for day {day_str}: {e}")
            continue

        if msgs1 is None or msgs2 is None:
            continue

        for h in range(24):
            t_idx = 24 * d + h 
            step_req = offset + h 

            # Extract 'fr' (Snow Fraction) - Legacy Index Method
            try:
                snow_idx = 369 + step_req 
                if snow_idx < len(msgs1):
                    data['fr'][t_idx,:,:] = msgs1[snow_idx].values[YMIN:YMAX, XMIN:XMAX]
            except:
                pass

            # File 1 Extraction (Name based)
            for m in msgs1:
                if m.step == step_req and m.name in name_map_1:
                    data[name_map_1[m.name]][t_idx,:,:] = m.values[YMIN:YMAX, XMIN:XMAX]

            # File 2 Extraction (Raw ID based - Handles Unknowns)
            for m in msgs2:
                if m.step == step_req:
                    # Create tuple of raw identifiers
                    keys = (m.discipline, m.parameterCategory, m.parameterNumber)
                    if keys in raw_map_2:
                        var_name = raw_map_2[keys]
                        data[var_name][t_idx,:,:] = m.values[YMIN:YMAX, XMIN:XMAX]
        
        # --- FIX: HANDLE MISSING T+0 (First Timestep) ---
        if offset == 0:
            t_0 = 24 * d      # Index of 00:00
            t_1 = 24 * d + 1  # Index of 01:00
            
            # Check center pixel of Temperature
            if np.isnan(data['Ta'][t_0, NY//2, NX//2]):
                for var_name in data:
                    data[var_name][t_0, :, :] = data[var_name][t_1, :, :]
        # -----------------------------------------------
        
        del msgs1, msgs2

    # --- INTERPOLATE MISSING TIMESTEPS ---
    data = interpolate_missing_time(data, nh, NY, NX)

    # --- POST PROCESSING ---
    print(f"Calculating derived variables for {year}-{month}...")
    
    Tc = data['Td'] - 273.15
    
    with np.errstate(over='ignore', invalid='ignore'):
        e = 611.213 * np.exp(17.5043 * Tc / (Tc + 241.3))
        
        # Fix Ps
        data['Ps'] = data['Ps'] - 101325 * (1 - (1 - z / 44307.69231)**5.253283)
        
        Qa = 0.622 * e / data['Ps']
        Rf = (1 - data['fr']) * data['Pr']
        Sf = data['fr'] * data['Pr']

    # --- WRITING NETCDF ---
    def writenc(var_array, varname, varunits):
        out_path = f"{outdir}{varname}{year}{month}.nc"
        with Dataset(out_path, 'w') as ncfile:
            ncfile.createDimension('x', NX)
            ncfile.createDimension('y', NY)
            ncfile.createDimension('time', nh)
            
            lat_v = ncfile.createVariable('lat', np.float32, ('y', 'x'))
            lat_v.units = 'degrees_north'
            lat_v[:] = LAT_GRID
            
            lon_v = ncfile.createVariable('lon', np.float32, ('y', 'x'))
            lon_v.units = 'degrees_east'
            lon_v[:] = LON_GRID
            
            xo = ncfile.createVariable('x', np.float32, ('x',))
            yo = ncfile.createVariable('y', np.float32, ('y',))
            xo[:] = X_GRID
            yo[:] = Y_GRID

            t = ncfile.createVariable('time', np.float32, ('time',))
            t.units = f'hours since {year}-{month}-01'
            t[:] = np.arange(nh)
            
            v = ncfile.createVariable(varname, np.float32, ('time', 'y', 'x'), fill_value=9999, zlib=True)
            v.units = varunits
            
            clean_data = np.where(np.isnan(var_array), 9999, var_array)
            v[:,:,:] = clean_data

    print(f"Writing NetCDF files for {year}-{month}...")
    writenc(data['Ps'], 'PSurf', 'Pa')
    writenc(Qa, 'Qair', 'kg/kg')
    writenc(Rf, 'Rainf', 'kg/m2/s')
    writenc(Sf, 'Snowf', 'kg/m2/s')
    writenc(data['SW'], 'SWdown', 'W/m2')
    writenc(data['Ta'], 'Tair', 'K')
    writenc(data['Ua'], 'Wind', 'm/s')
    writenc(data['LW'], 'LWdown', 'W/m2')
    writenc(data['Wd'], 'WindDir', 'degrees')
    writenc(data['TCC'], 'TotCloud', '%')   # Added output
    writenc(data['SD'], 'SnowDepth', 'm')   # Added output

    del data
    gc.collect()
    print(f"Finished {year}-{month}")