###
### Dependencies
###

import os
import sys
import time
import shutil
import json
import pickle
from collections import defaultdict
from multiprocessing import Pool, TimeoutError, cpu_count
from PIL import Image
import imagehash
import exifread

###
### External API
###

# See cli.py for example of how to use these APIs together

def load_config(cfgfile, args):
    """
    Loads and outputs config dict
    ARGUMENTS:
    - cfgfile : (Optional) path to configuration file
    - args : (Optional) argparse object
    """
    # Defaults
    config = {
        'file_naming': '%Y/%B/%d_{filename}_{resy}', # time.strftime format specifiers (%) plus the following keys ({}): filename, resx, resy
        'duplicate_handling': 'highest_resolution', # lowest_resolution, newest, oldest, none
        'delete_input': False,
        'persist_input': False,
        'inputs': [],
        'output': '',
        'threads': cpu_count()
    }
    # Override defaults with config file settings
    if cfgfile and os.path.exists(cfgfile):
        info('Loading configuration from', cfgfile)
        with open(cfgfile, 'r') as fd:
            config.update(json.load(fd))
    # Override or append config file settings with CLI arguments
    if args:
        config['inputs'].extend([os.path.abspath(d) for d in args.dirs])
        if args.output:
            config['output'] = os.path.abspath(args.output)
        config['threads'] = args.threads
        config['persist_input'] = args.persist_input
        config['delete_input'] = args.delete_input
    return config

def get_config(outdir):
    """
    Returns the configuration file path (if it exists) from an output directory path
    ARGUMENTS:
    - outdir : output directory path
    """
    f = os.path.join(os.path.abspath(outdir), '.picbasket.cfg')
    if os.path.exists(f):
        return f
    return ''

def save_config(config):
    """
    Saves config dict to the output directory
    ARGUMENTS:
    - config : the config dict
    """
    f = os.path.join(os.path.abspath(config['output']), '.picbasket.cfg')
    # Don't store certain non-persistent settings, e.g. threads as it's machine dependent
    persistent_config = config.copy()
    persistent_config.pop('threads', None)
    persistent_config.pop('persist_input', None)
    if not config['persist_input']:
        persistent_config.pop('inputs', None)
    with open(f, 'w', encoding='utf-8') as fd:
        json.dump(persistent_config, fd, ensure_ascii=False, indent=4)

def load_db(config):
    """
    Loads the pickled image database from the output directory and returns the unpickled dict
    ARGUMENTS:
    - config : the config dict
    """
    f = os.path.join(os.path.abspath(config['output']), '.picbasket.db')
    if os.path.exists(f):
        with open(f, 'rb') as fd:
            return pickle.load(fd)
    else:
        return defaultdict(list)

def save_db(config, db):
    """
    Pickles and saves the database to the output directory
    ARGUMENTS:
    - config : the config dict
    - db : the image database dict
    """
    f = os.path.join(os.path.abspath(config['output']), '.picbasket.db')
    with open(f, 'wb') as fd:
        pickle.dump(db, fd)

def discover(config, db):
    """
    Discovers and processes images in the input directories
    ARGUMENTS:
    - config : the config dict
    - db : the image database dict (to be populated by this function)
    """
    with Pool(processes=config['threads']) as pool:
        for d in config['inputs']:
            p = os.path.abspath(d)
            if not os.path.isdir(p):
                continue
            for root, dirs, files in os.walk(p):
                for base in files:
                    f = os.path.join(root, base)
                    try:
                        h, res, ts = pool.apply_async(_hash_img, (f,)).get(timeout=1000)
                    except TimeoutError:
                        warn('Timeout hashing file', f)
                        continue
                    if h:
                        db[h].append([f, res, ts])

def migrate(config, db):
    """
    Migrates files from the input directories to the output directory
    after resolving duplicates, using the configured naming scheme
    ARGUMENTS:
    - config : the config dict
    - db : the unresolved image database dict (potentially with duplicates)
    RETURNS:
    - newdb : the resolved image database dict (with no duplicates)
    """
    os.makedirs(os.path.abspath(config['output']), mode=0o755, exist_ok=True)
    newdb = defaultdict(list)
    with Pool(processes=min(config['threads'], 4)) as pool: # cap at 4 threads for IO bandwidth
        for h, imgs in db.items():
            for src, dst in _resolve(config, imgs, h, newdb):
                try:
                   pool.apply_async(_copy, (src, dst, config['delete_input'],)).get(timeout=10000)
                except TimeoutError:
                   warn('Timeout copying file', src, 'to', dst)
    return newdb

###
### Internal methods
###

### TODO: deprecate these in favor of callback-style logging API
def error(*msg):
    print('Error:', *msg, file=sys.stderr)
    exit(1)

def warn(*msg):
    print('Warning:', *msg, file=sys.stderr)

def info(*msg):
    print('Info:', *msg)

def _get_timestamp(fd, f):
    """
    Gets the timestamp of an image, from EXIF data if available, else from file modification time
    ARGUMENTS:
    - fd : file descriptor of the opened image file (for reading EXIF data)
    - f : image path (for getting fallback modification time)
    RETURNS:
    """
    tags = exifread.process_file(fd, details=False, stop_tag='Image DateTime')
    if 'Image DateTime' in tags:
        return int(time.mktime(time.strptime(str(tags['Image DateTime']), '%Y:%m:%d %H:%M:%S')))
    else:
        return int(os.path.getmtime(f))

def _hash_img(f):
    """
    Hashes the image at the given path
    ARGUMENTS:
    - f : image path
    RETURNS:
    - h : hash value (string)
    - res : resolution of the image
    - ts : timestamp
    """
    with open(f, 'rb') as fd:
        try:
            img = Image.open(fd)
        except:
            # This is not an image, skip this file
            return ['', None, '']
        res = img.size
        h = str(imagehash.phash(img))
        ts = _get_timestamp(fd, f)
        return [h, res, ts]

def _name(config, img):
    """
    Returns a name for the migrated image based on the file_naming setting in the config dict
    ARGUMENTS:
    - config : the config dict
    - img : PIL image object
    """
    template = time.strftime(config['file_naming'], time.localtime(img[2]))
    bn, ext = os.path.splitext(os.path.basename(img[0]))
    # TODO: sanitize bn (spaces, special chars, etc.)
    return os.path.join(config['output'], template.format(filename=bn, resx=img[1][0], resy=img[1][1]) + ext)

def _resolve(config, imgs, h, newdb):
    """
    Picks the image to keep among duplicates
    ARGUMENTS:
    - config : the config dict
    - imgs : the duplicate images
    - h : the hash value of these images
    - newdb : the final post-resolved database dict (with no duplicates), to be updated after this resolution
    RETURNS:
    Nothing, if no image file from the inputs need to be copied into the output area.
    Otherwise, a source-destination pair of file paths: the path of the input image
    and the path it needs to be copied to in the output directory.
    """
    strategy = config['duplicate_handling']
    if strategy == 'none':
        newdb[h] = imgs
        return [[img[0], _name(config, img)] for img in imgs]
    candidate = []
    for img in imgs:
        if not candidate:
            candidate = img
        elif strategy == 'highest_resolution':
            if img[1][0] > candidate[1][0]: # TODO: check both dimensions, or assume scaled same?
                candidate = img
        elif strategy == 'lowest_resolution':
            if img[1][0] < candidate[1][0]: # TODO: check both dimensions, or assume scaled same?
                candidate = img
        elif strategy == 'newest':
            if img[2] > candidate[2]:
                candidate = img
        elif strategy == 'oldest':
            if img[2] < candidate[2]:
                candidate = img
    src = candidate[0]
    if src.startswith(config['output']): # no action needed, the one in the output is already the selected one
        newdb[h].append([src, candidate[1], candidate[2]])
        return []
    dst = _name(config, candidate)
    newdb[h].append([dst, candidate[1], candidate[2]])
    return [[src, dst]]

def _copy(src, dst, removesrc):
    """
    Copies an input image to the output directory
    ARGUMENTS:
    - src : image file path from one of the input directories
    - dst : image file path to be created or updated in the output directory
    - removesrc : flag informing us we should delete the image file from the input directory after it has been moved to the output directory
    """
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if removesrc:
            shutil.move(src, dst)
        else:
            shutil.copy2(src, dst)
    except:
        warn('Failed to copy', src, 'to', dst)
