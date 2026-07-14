import matplotlib.pyplot as plt
from netCDF4 import Dataset
import numpy as np
import os

# =====================================================================
# CONFIGURATION
# =====================================================================
# Path to the NetCDF file generated in the previous step
NC_FILE = '/home/users/leamhowe/sensecdt/UKV_nc/constants/ukv_elevation_scotland.nc'


def plot_elevation_check(filepath):
    if not os.path.exists(filepath):
        print(f"Error: Could not find {filepath}")
        return

    print(f"Loading data from {filepath}...")
    
    # 1. Read the NetCDF file
    with Dataset(filepath, 'r') as nc:
        x = nc.variables['x'][:]
        y = nc.variables['y'][:]
        z = nc.variables['elevation'][:]
        
    print(f"Data loaded successfully. Grid shape: {z.shape}")

    # 2. Set up the plot
    fig, ax = plt.subplots(figsize=(8, 10))

    # 3. Plot using pcolormesh (great for coordinate arrays)
    # cmap='terrain' provides a nice intuitive color scale for landmass/sea
    mesh = ax.pcolormesh(x, y, z, cmap='terrain', shading='auto', vmin=0)

    # 4. Add colorbar and labels
    cbar = plt.colorbar(mesh, ax=ax, pad=0.02, fraction=0.05)
    cbar.set_label('Elevation / Height above MSL (m)', rotation=270, labelpad=15)

    ax.set_title('UKV Elevation Data Check\n(British National Grid - EPSG:27700)', pad=15)
    ax.set_xlabel('Eastings (m)')
    ax.set_ylabel('Northings (m)')

    # 5. Lock aspect ratio so Scotland doesn't look stretched
    ax.set_aspect('equal')
    
    # Optional: Add a light grid
    ax.grid(True, linestyle=':', alpha=0.6)

    plt.tight_layout()
    plt.show()
    plt.savefig('ukv_elevation_check.png', dpi=300)

if __name__ == '__main__':
    plot_elevation_check(NC_FILE)