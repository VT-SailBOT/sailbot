#!/usr/bin/python
import time, logging, sys

def generate_error(message):
    print '\033[31m\033[1m%s\033[0m\033[39m' % message
    
try:
    import smbus
except ImportError:
    generate_error('[Arduino Socket]: SMBUS not configured properly!')
    sys.exit(1)

import threading
import socket
from thread import *
import time
import json
import threading


arduino_device = None  # Global arduino_device variable
states = None

# Define the socket parameters

HOST = ''
PORT = 7893

connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 

# Bind socket to local host and port
try:
    connection.bind((HOST, PORT))
except socket.error, msg:
    generate_error('[Arduino Socket]: Bind failed. Error Code: ' + str(msg[0]) + ' Message ' \
        + msg[1])
    sys.exit()

print '[Arduino Socket]: Socket bind complete!'


class ArduinoDevice(threading.Thread):

    address = 0x07  # Address the port runs on
    analogs = [0x4000, 0x5000, 0x6000, 0x7000]
    normal = 0x0418

    def switch_bits(self, input):

        # Flips the bits of the input and returns the result
        return (input >> 8) + ((input & 0x00ff) << 8)

    def set_data_channel(self, input, bus):
        bus.write_word_data(self.address, 0x01, 0x1C40)
        time.sleep(0.01)

    def read_data(self, bus):

        # Read data from the bus
        time.sleep(0.01)
        return self.switch_bits(bus.read_word_data(self.address, 0))

    def setup(self, input, bus):

        # Write values to the registers
        bus.write_word_data(self.address, 0x02, self.switch_bits(input << 4))
        time.sleep(0.01)
        bus.write_word_data(self.address, 0x03, self.switch_bits(0x7fff))
        time.sleep(0.01)

    def run(self):

        try:
            bus = smbus.SMBus(0x01)
            self.setup(1500, bus)
            self.set_data_channel(self.analogs[0], bus)

            while True:
                global states
                recv = self.read_data(bus)
                binary = "{0:b}".format(recv)
                binary = ("0" * (16 - len(binary))) + binary

                rudder = binary[0:8]
                winch = binary[8:15]
                switch = binary[15:16]

                states = {"rudder": (2 * (int(rudder, 2)/128.0)) - 1, "winch": (2 * (int(winch, 2)/64.0)) - 1, "switch": True if switch == '1' else False }
                time.sleep(0.1)

        except IOError:
            generate_error('[Arduino Socket]: IO Error: device cannot be read, check your wiring or run as root')

# Create and start the wind_sensor thread
arduino_device = ArduinoDevice()
arduino_device.daemon = True # Needed to make the thread shutdown correctly
arduino_device.start()

# Start listening on socket
connection.listen(10)

# Function for handling connections; will be used to create threads

def clientthread(conn):

    # Infinite loop so that function do not terminate and thread do not end

    while True:

        # Receive data from the client
        data = conn.recv(1024)
        if not data:
            break

        conn.sendall(json.dumps(states).encode('utf-8'))

    # close the connection if the client if the client and server connection is interfered
    conn.close()


# Main loop to keep the server process going
while True:

    try:
        # Wait to accept a connection in a blocking call
        (conn, addr) = connection.accept()
        print '[Arduino Socket]: Connected with ' + addr[0] + ':' + str(addr[1])

        # Start new thread takes 1st argument as a function name to be run, second is the tuple of arguments to the function
        start_new_thread(clientthread, (conn, ))

    except KeyboardInterrupt, socket.error:
        connection.shutdown(socket.SHUT_RDWR)
        connection.close()
        break


            