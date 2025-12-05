from UKV2FSM_month import UKV2FSM_month
from datetime import datetime, timedelta
from calendar import monthrange
import numpy as np
from pyproj import Transformer
import sys

# Specify the date range
start_date = str(sys.argv[1])
end_date = str(sys.argv[2])
# start_date = '2016-10-01'
# end_date = '2020-09-30'
# start_date = '2020-10-01'
# end_date = '2021-09-30'
# end_date = '2021-10-02'

# Convert start and end dates to datetime objects
start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
end_datetime = datetime.strptime(end_date, '%Y-%m-%d')


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



# Loop over each month within the specified date range
current_datetime = start_datetime
while current_datetime <= end_datetime:
    # Extract year and month from the current date
    year = str(current_datetime.year)
    month = str(current_datetime.month).zfill(2)  # Zero-fill the month string

    # Get the number of days in the current month
    _, last_day = monthrange(current_datetime.year, current_datetime.month)

    # Call the UKV2FSM_month function for the current month
    UKV2FSM_month(year, month)

    # Move to the next month
    current_datetime = datetime(current_datetime.year, current_datetime.month, last_day) + timedelta(days=1)
