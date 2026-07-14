from UKV2FSM_month import UKV2FSM_month, GEOJSON_DIR
from datetime import datetime
from dateutil.relativedelta import relativedelta
import sys
import traceback
import concurrent.futures

_GEOJSON_DIR = GEOJSON_DIR


def process_wrapper(args):
    y, m = args
    try:
        UKV2FSM_month(y, m, geojson_dir=_GEOJSON_DIR)
    except Exception as e:
        print(f"Failed processing {y}-{m}: {e}")
        traceback.print_exc()


if __name__ == '__main__':
    # Args: START_DATE END_DATE [NUM_WORKERS] [GEOJSON_DIR]
    start_date = str(sys.argv[1])
    end_date = str(sys.argv[2])
    num_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    if len(sys.argv) > 4:
        _GEOJSON_DIR = sys.argv[4]

    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')

    tasks = []
    current = start_datetime.replace(day=1)
    while current <= end_datetime:
        tasks.append((str(current.year), str(current.month).zfill(2)))
        current += relativedelta(months=1)

    print(f"Starting processing for {len(tasks)} months with {num_workers} workers.")
    print(f"GeoJSON region dir: {_GEOJSON_DIR}")

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        executor.map(process_wrapper, tasks)