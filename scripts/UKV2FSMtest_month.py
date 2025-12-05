"""
Convert UKV grib files to FSM netCDF input files
"""
import subprocess
from netCDF4 import Dataset
import numpy as np
import pygrib
from pyproj import Transformer
from tqdm import tqdm
import os
from calendar import monthrange


    
    
def UKV2FSM_month(year,month, UKV_dir = '/badc/ukmo-nwp/data/ukv-grib/', outdir = '/home/users/leamhowe/sensecdt/users/leamhowe/UKV_nc/'):

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
    nd = 10
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

        # UKV files
        wholesale1_file = f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale1.grib'
        wholesale2_file = f'{UKV_dir}{year}/{month}/{day}/{year}{month}{day}0000_u1096_ng_umqv_Wholesale2.grib'

        # Backup files
        if day == '01' and month == '01':
            # use last day from previous month.
            search_year = str(int(year) - 1)
            search_month = '12'
            day_in_search_month = '31'
            wholesale1_backup = f'{UKV_dir}{search_year}/{search_month}/{day_in_search_month}/{search_year}{search_month}{day_in_search_month}1200_u1096_ng_umqv_Wholesale1.grib'
            wholesale2_backup = f'{UKV_dir}{search_year}/{search_month}/{day_in_search_month}/{search_year}{search_month}{day_in_search_month}1200_u1096_ng_umqv_Wholesale2.grib'
        elif day == '01':
            # use last day from previous month, or next day. Problem if both are missing.
            search_year = year
            search_month = str(int(month) - 1).zfill(2)
            day_in_search_month = str(monthrange(int(year),int(search_month))[1])
            wholesale1_backup = f'{UKV_dir}{search_year}/{search_month}/{day_in_search_month}/{search_year}{search_month}{day_in_search_month}1200_u1096_ng_umqv_Wholesale1.grib'
            wholesale2_backup = f'{UKV_dir}{search_year}/{search_month}/{day_in_search_month}/{search_year}{search_month}{day_in_search_month}1200_u1096_ng_umqv_Wholesale2.grib'
        else:
            wholesale1_backup = f'{UKV_dir}{year}/{month}/{str(d).zfill(2)}/{year}{month}{str(d).zfill(2)}1200_u1096_ng_umqv_Wholesale1.grib'
            wholesale2_backup = f'{UKV_dir}{year}/{month}/{str(d).zfill(2)}/{year}{month}{str(d).zfill(2)}1200_u1096_ng_umqv_Wholesale2.grib'

        
        # Check if files exist before opening them and extracting data
        if os.path.exists(wholesale1_file) and os.path.exists(wholesale2_file):
            
            print(f'Extracting from files: {wholesale1_file}, {wholesale2_file}')

            grb1 = pygrib.open(wholesale1_file)
            grb2 = pygrib.open(wholesale2_file)

            
                
            for h in tqdm(range(24), desc=f'Processing Day {day}', unit='hour', total=24):
            # for h in tqdm([12,13], desc=f'Processing Day {day}', unit='hour', total=2):
                t = 24*d + h
                # grb = grb1.select()[369+h]   # 369 is index at which snow fraction is found because name is not correctly documented in grib files.
                # fr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Precipitation rate')[h]
                # Pr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Pressure reduced to MSL')[h]
                # Ps[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Temperature')[h]
                # Ta[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Dew point temperature')[h]
                # Td[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='10 metre wind speed')[h]
                # Ua[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                grb = grb2.select(name='Downward short-wave radiation flux')[h]
                SW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb2.select(name='Downward long-wave radiation flux')[h]
                # LW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
            
        elif os.path.exists(wholesale1_backup) and os.path.exists(wholesale2_backup): # if the files are not found, try the backup files which is the previous day at 12:00. Each run is 36 hours so 12:00 run from prev day covers the entire next day.

            grb1 = pygrib.open(wholesale1_backup)
            grb2 = pygrib.open(wholesale2_backup)
            print(f'One or both of {wholesale1_file} and {wholesale2_file} do not exist, using backup files: {wholesale1_backup} and {wholesale2_backup}')

            
            
            for i, h in tqdm(enumerate(np.arange(0,24)+12), desc=f'Processing Day {day}', unit='hour', total=24):
                t = 24*d + i
                # grb = grb1.select()[369+h]   # 369 is index at which snow fraction is found because name is not correctly documented in grib files.
                # fr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Precipitation rate')[h]
                # Pr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Pressure reduced to MSL')[h]
                # Ps[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Temperature')[h]
                # Ta[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Dew point temperature')[h]
                # Td[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='10 metre wind speed')[h]
                # Ua[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                grb = grb2.select(name='Downward short-wave radiation flux')[h]
                SW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb2.select(name='Downward long-wave radiation flux')[h]
                # LW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]

        else:# If 1200 file from previous day is not found, keep going back through 0000 files until one is found.
            
            search_year = year
            search_month = month
            day_in_search_month = day
            while not os.path.exists(wholesale1_backup) or not os.path.exists(wholesale2_backup):
                day_in_search_month = str(int(day_in_search_month) - 1).zfill(2)
                print(day_in_search_month)
                if day_in_search_month == '00':

                    if search_month == '01':
                        search_year = str(int(year) - 1)
                        search_month = '12'
                        day_in_search_month = '31'
                    else:
                        search_month = str(int(search_month) - 1).zfill(2)
                        day_in_search_month = str(monthrange(int(search_year), int(search_month))[1]).zfill(2)

                wholesale1_backup = f'{UKV_dir}{search_year}/{search_month}/{day_in_search_month}/{search_year}{search_month}{day_in_search_month}0000_u1096_ng_umqv_Wholesale1.grib'
                wholesale2_backup = f'{UKV_dir}{search_year}/{search_month}/{day_in_search_month}/{search_year}{search_month}{day_in_search_month}0000_u1096_ng_umqv_Wholesale2.grib'

            grb1 = pygrib.open(wholesale1_backup)
            grb2 = pygrib.open(wholesale2_backup)
            print(f'One or both of {wholesale1_file} and {wholesale2_file} do not exist, using backup files: {wholesale1_backup} and {wholesale2_backup}')

            
            for h in tqdm(range(0,24), desc=f'Processing Day {day}', unit='hour', total=24):
                t = 24*d + h
                # grb = grb1.select()[369+h]   # 369 is index at which snow fraction is found because name is not correctly documented in grib files.
                # fr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Precipitation rate')[h]
                # Pr[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Pressure reduced to MSL')[h]
                # Ps[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Temperature')[h]
                # Ta[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='Dew point temperature')[h]
                # Td[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb1.select(name='10 metre wind speed')[h]
                # Ua[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                grb = grb2.select(name='Downward short-wave radiation flux')[h]
                SW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]
                # grb = grb2.select(name='Downward long-wave radiation flux')[h]
                # LW[t,:,:] = grb.values[ymin:ymax,xmin:xmax]

    
    # variable conversions
    Tc = Td - 273.15
    e = 611.213*np.exp(17.5043*Tc/(Tc + 241.3))
    Ps = Ps - 101325*(1 - (1 - z/44307.69231)**5.253283)
    Qa = 0.622*e/Ps
    Rf = (1 - fr)*Pr
    Sf = fr*Pr
    
    # write netCDF
    # writenc(LW,'LWdown','W/m2')
    # writenc(Ps,'PSurf','Pa')
    # writenc(Qa,'Qair','kg/kg')
    # writenc(Rf,'Rainf','kg/m2/s')
    # writenc(Sf,'Snowf','kg/m2/s')
    writenc(SW,'SWdown','W/m2')
    # writenc(Ta,'Tair','K')
    # writenc(Ua,'Wind','m/s')

