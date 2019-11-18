import os
import sys
from multiprocessing import cpu_count
import argparse
from . import picbasket as pb

def main():
    parser = argparse.ArgumentParser(description='TODO')
    parser.add_argument('dirs', nargs='*', help='Directories to search for images')
    parser.add_argument('-c', '--config', type=str, help='Configuration file')
    parser.add_argument('-o', '--output', type=str, help='Output directory')
    parser.add_argument('-j', '--threads', type=int, default=cpu_count(), help='Number of threads to use')
    parser.add_argument('--persist-input', action='store_true', help='Save input directories to configuration so that they are always indexed')
    parser.add_argument('--delete-input', action='store_true', help='Delete input files after copying to output directory')
    args = parser.parse_args()
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
    # Load, discover, migrate and save
    db = pb.load_db(config)
    pb.discover(config, db)
    import pprint as pp # temporary
    pp.pprint(db) # temporary
    db = pb.migrate(config, db)
    pp.pprint(db) # temporary
    pb.save_db(config, db)
    pb.save_config(config)

def error(*msg):
    print('Error:', *msg, file=sys.stderr)
    exit(1)

def warn(*msg):
    print('Warning:', *msg, file=sys.stderr)

def info(*msg):
    print('Info:', *msg)
