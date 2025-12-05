"""
Convert UKV grib files to FSM netCDF input files
"""
import subprocess
from netCDF4 import Dataset
import numpy as np
import pygrib
from pyproj import Transformer
from tqdm import tqdm


def cmdExec(command):
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")

cmd = 'module load jaspy'
cmdExec(cmd)

# define where data is stored
UKV_dir = '/badc/ukmo-nwp/data/ukv-grib/'
outdir = '/home/users/leamhowe/sensecdt/users/leamhowe/UKV_nc/' 


# select year and month
year = '2017'
month = '02'



def writenc(var,varname,varunits):
    """
    Write a netCDF file

    Parameters
    ----------
    var      : variable
    varname  : variable shortname and filename
    varunits : variable units
    """
    ncfile = Dataset(outdir+varname+year+month+'.nc','w')
    x_dim = ncfile.createDimension('x',nx)
    y_dim = ncfile.createDimension('y',ny)
    t_dim = ncfile.createDimension('time',nh)
    latitude = ncfile.createVariable('lat',np.float32,('y','x'))
    latitude.units = 'degrees_north'
    longitude = ncfile.createVariable('lon',np.float32,('y','x'))
    longitude.units = 'degrees_east'
    xo = ncfile.createVariable('x',np.float32,('x',))
    xo.units = 'm'
    yo = ncfile.createVariable('y',np.float32,('y',))
    yo.units = 'm'
    t = ncfile.createVariable('time',np.float32,('time',))
    t.units = 'hours since '+year+'-'+month+'-01'
    v = ncfile.createVariable(varname,np.float32,('time','y','x'),fill_value=9999)
    v.units = varunits
    latitude[:,:] = lat[:,:]
    longitude[:,:] = lon[:,:]
    xo[:] = x[:]
    yo[:] = y[:]
    t[:] = np.arange(nh)
    v[:,:,:] = var[:,:,:]
    ncfile.close()
    
# OSGB and lat/lon coordinates of UKV grid
x = np.arange(-239000,857000,2000)
y = np.arange(1223000,-185000,-2000)
transformer = Transformer.from_crs('EPSG:27700','EPSG:4326')
xx, yy = np.meshgrid(x,y)
lat, lon = transformer.transform(xx,yy)

# limit to Scottish mountain domain
xmin = 220
xmax = 290
ymin = 188
ymax = 244
lon = lon[ymin:ymax,xmin:xmax]
lat = lat[ymin:ymax,xmin:xmax]
x = x[xmin:xmax]
y = y[ymin:ymax] 
ny, nx = lat.shape

# number of days and hours
nd = 2
nh = 24*nd

# surface elevation
# grbs = pygrib.open('constant_u1096_ng_umqv_Wholesale.grib')
grbs = pygrib.open('/badc/ukmo-nwp/data/ukv-grib/constants/constant_u1096_ng_umqv_Wholesale.grib')
grb = grbs.select(name='Geometrical height')[0]
z = grb.values[ymin:ymax,xmin:xmax]

# UKV and FSM2 variables
fr = np.zeros((nh,ny,nx))  # fraction of precipitation as snow
LW = np.zeros((nh,ny,nx))  # longwave radiation
Pr = np.zeros((nh,ny,nx))  # precipitation rate
Ps = np.zeros((nh,ny,nx))  # surface pressure
Qa = np.zeros((nh,ny,nx))  # specific humidity
Rf = np.zeros((nh,ny,nx))  # rainfall rate
Sf = np.zeros((nh,ny,nx))  # snowfall rate
SW = np.zeros((nh,ny,nx))  # shortwave radiation
Ta = np.zeros((nh,ny,nx))  # air temperature
Td = np.zeros((nh,ny,nx))  # dew point temperature
Ua = np.zeros((nh,ny,nx))  # wind speed

# loop over days
for d in range(nd):
    day = str(d+1)
    print(f'processing day {day} / {nd}')
    # if d<9: day = '0'+day 
    if d<9: day = day.zfill(2)  # zero-fill the string

    # read grib
    grb1 = pygrib.open(f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale1.grib') #why is the hour not changing?
    grb2 = pygrib.open(f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale2.grib')
    for h in tqdm(range(24), desc=f'Processing Day {day}', unit='hour', total=24):
        t = 24*d + h
        grb = grb1.select()[369+h]   # 369 is index at which snow fraction is found because name is not correctly documented in grib files.
        fr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb1.select(name='Precipitation rate')[h]
        Pr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb1.select(name='Pressure reduced to MSL')[h]
        Ps[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb1.select(name='Temperature')[h]
        Ta[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb1.select(name='Dew point temperature')[h]
        Td[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb1.select(name='10 metre wind speed')[h]
        Ua[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb2.select(name='Downward short-wave radiation flux')[h]
        SW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
        grb = grb2.select(name='Downward long-wave radiation flux')[h]
        LW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]

# variable conversions
Tc = Td - 273.15
e = 611.213*np.exp(17.5043*Tc/(Tc + 241.3))
Ps = Ps - 101325*(1 - (1 - z/44307.69231)**5.253283)
Qa = 0.622*e/Ps
Rf = (1 - fr)*Pr
Sf = fr*Pr

# write netCDF
writenc(LW,'LWdown','W/m2')
writenc(Ps,'PSurf','Pa')
writenc(Qa,'Qair','kg/kg')
writenc(Rf,'Rainf','kg/m2/s')
writenc(Sf,'Snowf','kg/m2/s')
writenc(SW,'SWdown','W/m2')
writenc(Ta,'Tair','K')
writenc(Ua,'Wind','m/s')

