import pygrib

# Point this to a KNOWN GOOD file from the early years (e.g., 2017 or 2018)
old_working_file = "/badc/ukmo-nwp/data/ukv-grib/2018/01/01/201801010000_u1096_ng_umqv_Wholesale1.grib"

try:
    grbs = pygrib.open(old_working_file)
    
    # Grab the exact message your old script relied on
    target_grb = grbs.select()[369] 
    
    print(f"--- THE TRUE IDENTITY OF INDEX 369 ---")
    print(f"Name: {target_grb.name}")
    print(f"Discipline: {target_grb.discipline}")
    print(f"Category: {target_grb.parameterCategory}")
    print(f"Number: {target_grb.parameterNumber}")
    
    grbs.close()
except Exception as e:
    print(f"Error: {e}")