from UKV2FSM_month import UKV2FSM_month
from datetime import datetime
from dateutil.relativedelta import relativedelta
import sys
import concurrent.futures

# Function to be mapped
def process_wrapper(args):
    y, m = args
    try:
        UKV2FSM_month(y, m)
    except Exception as e:
        print(f"Failed processing {y}-{m}: {e}")

if __name__ == '__main__':
    # Specify the date range
    start_date = str(sys.argv[1])
    end_date = str(sys.argv[2])
    
    # How many parallel workers? (Default to 4, but can pass as arg 3)
    num_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4

    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')

    # Generate list of Year/Month tuples
    tasks = []
    current = start_datetime.replace(day=1)
    while current <= end_datetime:
        year = str(current.year)
        month = str(current.month).zfill(2)
        tasks.append((year, month))
        current += relativedelta(months=1)

    print(f"Starting processing for {len(tasks)} months with {num_workers} workers.")
    
    # Process in parallel
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        executor.map(process_wrapper, tasks)