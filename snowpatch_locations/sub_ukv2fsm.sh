#!/bin/bash 
#SBATCH --partition=standard
#SBATCH -o ./io_files/ukv2fsm_%j.out
#SBATCH -e ./io_files/ukv2fsm_%j.err
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12       # Request 12 cores (one for each month of a year)
#SBATCH --mem=32G                # RAM to handle parallel months
#SBATCH --account=sensecdt
#SBATCH --qos=high

date
module load jaspy

# Arguments: Start Date, End Date, Number of Workers, [optional GeoJSON dir]
# e.g. sbatch sub_ukv2fsm.sh 2016-10-01 2020-09-30
python -u /home/users/leamhowe/phd/UKV2FSM/snowpatch_locations/UKV2FSM_year.py $1 $2 12

date