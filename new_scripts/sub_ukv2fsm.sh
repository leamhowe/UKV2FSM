#!/bin/bash 
#SBATCH --partition=standard
#SBATCH -o ./io_files/ukv2fsm_%j.out
#SBATCH -e ./io_files/ukv2fsm_%j.err
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12       # Request 12 cores (one for each month of a year)
#SBATCH --mem=32G                # Increased RAM to handle parallel months
#SBATCH --account=sensecdt
#SBATCH --qos=high

date
module load jaspy

# Run the script
# Arguments: Start Date, End Date, Number of Workers (Parallel processes)
python -u /home/users/leamhowe/phd/UKV2FSM/new_scripts/UKV2FSM_year.py $1 $2 12

date