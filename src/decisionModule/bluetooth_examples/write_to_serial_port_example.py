import serial
import pickle
"""
Example Script for how to read from a serial conneciton
"""
# select the serial port and baud rate
# (the with statement will close connection even upon keyboard interrupt)
with serial.Serial('/dev/cu.PURC_HC05_2', 115200, timeout=1) as ser:
    while True:
        # read continuously
        line = input()
        # convert to serial
        ser.write(pickle.dumps(line)) # right now, it adds a period, not sure why
