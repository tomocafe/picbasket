import os
import sys
import time
from multiprocessing import cpu_count
import argparse
from . import picbasket as pb

def main():
    # Register callbacks to picbasket module
    pb.callback = {
        'warning': on_warning,
        'on_hashed': on_hashed,
        'on_copied': on_copied,
        'on_migrated': on_migrated,
        'on_found_cfgfile': on_found_cfgfile,
        'on_load_cfgfile': on_load_cfgfile
    }
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='TODO')
    parser.add_argument('dirs', nargs='*', help='Directories to search for images')
    parser.add_argument('-c', '--config', type=str, help='Configuration file')
    parser.add_argument('-o', '--output', type=str, help='Output directory')
    parser.add_argument('-j', '--threads', type=int, default=cpu_count(), help='Number of threads to use')
    parser.add_argument('--persist-input', action='store_true', help='Save input directories to configuration so that they are always indexed')
    parser.add_argument('--delete-input', action='store_true', help='Delete input files after copying to output directory')
    args = parser.parse_args()
    # Read and initialize configuration
    if args.config:
        cfgfile = os.path.abspath(args.config)
    elif args.output:
        cfgfile = pb.get_config(args.output)
    else:
        cfgfile = ''
    config = pb.load_config(cfgfile, args)
    if len(config['inputs']) == 0:
        error('No input directory given')
    if config['output'] == '':
        error('No output directory given')
    # Main flow
    db = pb.load_db(config)
    pb.discover(config, db)
    db = pb.migrate(config, db)
    pb.save_db(config, db)
    pb.save_config(config)

#
# Subroutines
#

def error(*msg):
    print('Error:', *msg, file=sys.stderr)
    exit(1)

def warn(*msg):
    print('Warning:', *msg, file=sys.stderr)

def info(*msg):
    print('Info:', *msg)

def statline(*msg):
    print(*msg, end='\r')

#
# Callback functions
#

def on_warning(**kwargs): # msg
    warn(kwargs['msg'])

starttime = time.time()
hashct = 0
def on_hashed(**kwargs): # hash, path, res, ts, ct, dup
    global hashct
    hashct += 1
    global starttime
    speed = (time.time() - starttime) / hashct
    path = ('..' + kwargs['path'][38:]) if len(kwargs['path']) > 40 else kwargs['path']
    statline('{:<40} {:6.2f} msec/img, processed {:<8d}'.format(path, speed, kwargs['ct']))

copyct = 0
def on_copied(**kwargs): # src, dst
    global copyct
    copyct += 1

def on_migrated(**kwargs): # db
    finalct = len(kwargs['db'])
    info('Processed {} images; stored {}, copied {}'.format(hashct, finalct, copyct))

def on_found_cfgfile(**kwargs): # cfgfile
    info('Found configuration file:', kwargs['cfgfile'])

def on_load_cfgfile(**kwargs): # cfgfile
    info('Loaded configuration from file:', kwargs['cfgfile'])
