#!/usr/bin/env python3

import os
import sys
from vision import MovementProcessor

ADDRESS = os.environ.get("BIND_ADDRESS","10.9.28.246")    # address of game engine server
PORT = os.environ.get("BIND_PORT", 11297)               # port game engine server is listening on

def main():
    
    top = ('-t' in sys.argv or os.environ.get("TOP",False))
    bottom = ('-b' in sys.argv or os.environ.get("BOTTOM",False))
    windows = ('-s' in sys.argv or os.environ.get("BOTTOM",False))

    flip_v = '-fv' in sys.argv
    flip_h = '-fh' in sys.argv

    if not (top or bottom):
        print('select either -t for top cam of -b for bottom cam')
        sys.exit(1)
    if top:
        # 0
        camera_number = 0
        processor = MovementProcessor(ADDRESS, PORT, camera_number, 15, 16, 27, windows, flip_v, flip_h)
    elif bottom:
        # 1
        camera_number = 0
        processor = MovementProcessor(ADDRESS, PORT, camera_number, 1, 15, 27, windows, flip_v, flip_h)
    processor.run()

if __name__ == "__main__":
    main()
