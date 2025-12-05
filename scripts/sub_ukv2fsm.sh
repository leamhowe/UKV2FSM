#!/bin/bash 
#SBATCH --partition=long-serial          # dis your queue, try this but you might want to change
#SBATCH -o ./io_files/ukv2fsm_%j.out       # output from your script, %j will sub in the job number
#SBATCH -e ./io_files/ukv2fsm_%j.err      # errors from your script/SLURM
#SBATCH --time=48:00:00                   # time you want to schedule for
#SBATCH --account=sensecdt
### #SBATCH --mem=50000  you don't need this guy, but if you're coming up against "OOM" errors you
### can request extra memory. Units are MB, if you need more than 64GB you should use the high-mem
### queue. I think default memory is about 4 GB...

### Put your executable stuff here, e.g.:
date
module load jaspy     # if you need to set up an environment or compile something
python -u /home/users/leamhowe/phd/UKV2FSM/scripts/UKV2FSM_year.py $1 $2       # then run your script, make sure it's executable using chmod u+x 
date

