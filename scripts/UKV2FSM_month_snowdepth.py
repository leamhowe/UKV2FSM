"""
Convert UKV grib files to FSM netCDF input files
"""
from calendar import monthrange
from netCDF4 import Dataset
import numpy as np
import pygrib
from pyproj import Transformer
from tqdm import tqdm
import os



def UKV2FSM_month(year,month, UKV_dir = '/badc/ukmo-nwp/data/ukv-grib/', outdir = '/home/users/leamhowe/sensecdt/users/leamhowe/UKV_nc/snowdepth/'):

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
    
    # number of days and hours in month
    nd = monthrange(int(year),int(month))[1]
    # nd = 2
    nh = 24*nd
    
    # surface elevation
    grbs = pygrib.open(f'{UKV_dir}constants/constant_u1096_ng_umqv_Wholesale.grib')
    grb = grbs.select(name='Geometrical height')[0]
    z = grb.values[ymin:ymax,xmin:xmax]
    
    # UKV and FSM2 variables
    SD = np.zeros((nh,ny,nx))  # snow depth (water equivalent)

    
    # loop over days
    for d in range(nd):
        day = str(d+1)
        print(f'processing day {year}-{month}-{day.zfill(2)}')
        # if d<9: day = '0'+day 
        if d<9: day = day.zfill(2)  # zero-fill the string
        
        # Check if GRIB files exist before attempting to open them
        # wholesale1_file = f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale1.grib'
        wholesale2_file = f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale2.grib'
    
        if os.path.exists(wholesale2_file):
            # grb1 = pygrib.open(wholesale1_file)
            grb2 = pygrib.open(wholesale2_file)
        
        # # read grib
        # grb1 = pygrib.open(f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale1.grib')
        # grb2 = pygrib.open(f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale2.grib')
            for h in tqdm(range(24), desc=f'Processing Day {day}', unit='hour', total=24):
                t = 24*d + h 
                grb = grb2.select(name='Snow depth')[h]
                SD[t,:,:] = grb.values[ymin:ymax,xmin:xmax]

    
    # variable conversions
    # Tc = Td - 273.15
    # e = 611.213*np.exp(17.5043*Tc/(Tc + 241.3))
    # Ps = Ps - 101325*(1 - (1 - z/44307.69231)**5.253283)
    # Qa = 0.622*e/Ps
    # Rf = (1 - fr)*Pr
    # Sf = fr*Pr
    
    # write netCDF
    writenc(SD,'SnowDepth','m')

