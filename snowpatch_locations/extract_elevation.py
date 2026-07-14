import os
import numpy as np
import pygrib
from netCDF4 import Dataset
from pyproj import Transformer

# =====================================================================
# CONFIGURATION
# =====================================================================
# Path to your UKV constants GRIB file
CONST_FILE = '/badc/ukmo-nwp/data/ukv-grib/constants/constant_u1096_ng_umqv_Wholesale.grib'
OUTPUT_NC = '/home/users/leamhowe/sensecdt/UKV_nc/constants/ukv_elevation_scotland.nc'

# Bounding box for Scotland in EPSG:27700 (British National Grid)
# This generous box fully covers the mainland, Hebrides, Orkney, and Shetland
SCOTLAND_BBOX = {
    'xmin': -100000,  # Far west islands
    'xmax': 500000,   # Far east (Shetland/Aberdeenshire)
    'ymin': 530000,   # Southern Uplands border
    'ymax': 1230000   # Shetland north tip
}

# Set to True to crop only to Scotland. Set to False to save the full UKV domain.
CROP_TO_SCOTLAND = True

# =====================================================================
# GRID DEFINITION
# =====================================================================
x_full = np.arange(-239000, 857000, 2000)      # eastings
y_full = np.arange(1223000, -185000, -2000)    # northings

# =====================================================================
# LOAD GRIB ELEVATION
# =====================================================================
def get_elevation(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Constants GRIB file not found at: {filepath}")
    
    print(f"Reading elevation from {filepath}...")
    with pygrib.open(filepath) as grbs:
        try:
            grb = grbs.select(name='Geometrical height')[0]
        except Exception:
            try:
                grb = grbs.select(parameterName='Orography')[0]
            except Exception:
                grb = grbs.message(1)
        return grb.values

# Load full 2D elevation grid
z_full = get_elevation(CONST_FILE)

# =====================================================================
# CROPPING / SLICING
# =====================================================================
if CROP_TO_SCOTLAND:
    print("Slicing grid to Scotland domain...")
    # Find matching indices
    x_mask = (x_full >= SCOTLAND_BBOX['xmin']) & (x_full <= SCOTLAND_BBOX['xmax'])
    y_mask = (y_full >= SCOTLAND_BBOX['ymin']) & (y_full <= SCOTLAND_BBOX['ymax'])
    
    x_idx = np.where(x_mask)[0]
    y_idx = np.where(y_mask)[0]
    
    x0, x1 = int(x_idx.min()), int(x_idx.max()) + 1
    y0, y1 = int(y_idx.min()), int(y_idx.max()) + 1
    
    # Slice arrays
    x = x_full[x0:x1]
    y = y_full[y0:y1]
    z = z_full[y0:y1, x0:x1]
else:
    print("Keeping full UKV domain...")
    x = x_full
    y = y_full
    z = z_full

# Generate 2D coordinate lat/lon grids for the chosen domain
transformer = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
xx, yy = np.meshgrid(x, y)
lon, lat = transformer.transform(xx, yy)

ny, nx = z.shape
print(f"Output Grid Size: {ny} rows x {nx} cols")

# =====================================================================
# WRITE TO NETCDF
# =====================================================================
print(f"Writing to NetCDF: {OUTPUT_NC}...")
with Dataset(OUTPUT_NC, 'w', format='NETCDF4') as nc:
    # Create Dimensions
    nc.createDimension('x', nx)
    nc.createDimension('y', ny)

    # Create Coordinate Variables (1D)
    xo = nc.createVariable('x', np.float32, ('x',))
    xo.units = 'm'
    xo.standard_name = 'projection_x_coordinate'
    xo[:] = x

    yo = nc.createVariable('y', np.float32, ('y',))
    yo.units = 'm'
    yo.standard_name = 'projection_y_coordinate'
    yo[:] = y

    # Create Lat/Lon Variables (2D)
    lat_v = nc.createVariable('lat', np.float32, ('y', 'x'))
    lat_v.units = 'degrees_north'
    lat_v.standard_name = 'latitude'
    lat_v[:] = lat

    lon_v = nc.createVariable('lon', np.float32, ('y', 'x'))
    lon_v.units = 'degrees_east'
    lon_v.standard_name = 'longitude'
    lon_v[:] = lon

    # Create Elevation Variable (2D) with compression
    elev_v = nc.createVariable('elevation', np.float32, ('y', 'x'), zlib=True, complevel=5)
    elev_v.units = 'm'
    elev_v.standard_name = 'height_above_mean_sea_level'
    elev_v.long_name = 'Orography / Geometrical height'
    elev_v[:] = z

print("Success! File saved successfully.")