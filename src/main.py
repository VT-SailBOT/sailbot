#!/usr/bin/python
import time, threading, json, logging, tornado.websocket, modules.calc, math, modules.utils, modules.log, socket, sys
from modules.server import ServerThread
from modules.location import Location
from modules.calc import direction_to_point
from modules.control_thread import StoppableThread

# Variables and constants
data = {'category': 'data', 'timestamp': 0, 'location': Location(0, 0),
        'heading': 0, 'speed': 0, 'wind_dir': 0, 'roll': 0, 'pitch': 0,
        'yaw': 0}

target_locations = []
boundary_locations = []
location_pointer = 0

# Specifies the default values
values = {'debug': False, 'port': 80, 'transmission_delay': 5, 'eval_delay': 5, 'current_desired_heading': 0,
          'direction': 0, 'absolute_wind_direction': 0, 'max_turn_rate_angle': 70, 'max_rudder_angle': 30}

## ----------------------------------------------------------
    
class DataThread(StoppableThread):

    """ Transmits the data object to the server thread
    """

    server_thread = None
    rudder_sock = None
    winch_sock = None

    def __init__(self, *args, **kwargs):
        super(DataThread, self).__init__(*args, **kwargs)

        global server_thread
        server_thread = ServerThread(name='Server', kwargs={'port': values['port'], 'target_locations': target_locations, 'boundary_locations': boundary_locations})
        server_thread.start()

        global rudder_sock
        try:
            rudder_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            rudder_sock.connect(("localhost", 9107))
        except socket.error:
            # Connection refused error
            logging.critical("Could not connect to servo socket")

        global winch_sock
        try:
            winch_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            winch_sock.connect(("localhost", 9108))
        except socket.error:
            # Connection refused error
            logging.critical("Could not connect to servo socket")


        # Set up logging to the web server console
        logging.getLogger().addHandler(modules.log.WebSocketLogger(self))

    def set_rudder_angle(self, angle):
        try:
            rudder_sock.send(str(angle).encode('utf-8'))
        except socket.error:
            # Broken Pipe Error
            logging.error('The rudder socket is broken!')

    def set_winch_angle(self, angle):
        try:
            winch_sock.send(str(angle).encode('utf-8'))
        except socket.error:
            # Broken Pipe Error
            logging.error('The winch socket is broken!')

    def send_data(self, data):

        # do not log any data here, doing so would create an infinite loop
        try:
            server_thread.send_data(data)
        except tornado.websocket.WebSocketClosedError:
            print('Could not send data because the socket is closed.')

    def run(self):
        
        logging.info('Starting the data thread!')
        
        # Connect to the GPS socket
        try:
            gps_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            gps_sock.connect(("localhost", 8907))
        except socket.error:
            # Connection refused error
            logging.critical("Could not connect to GPS socket")

        # Connect to the wind sensor socket
        try:
            wind_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            wind_sock.connect(("localhost", 8894))
        except socket.error:
            logging.critical("Could not connect to wind sensor socket")
        
        while True:

            if self.stopped():
                # Stop the server thread
                server_thread.stop()
                break
            
            # Query and update the GPS data
            try:
                gps_sock.send(str(0).encode('utf-8'))
                gps_parsed = json.loads(gps_sock.recv(1024).decode('utf-8').strip('\x00'))

                # Update the data object
                data.update(gps_parsed)

                # Add the location as an embeded data structure
                data['location'] = Location(gps_parsed['latitude'], gps_parsed['longitude'])

                data['heading'] = 180
                
            except (AttributeError, ValueError, socket.error) as e:
                logging.error('The GPS socket is broken or sent malformed data!')
 
            # Query and update the wind sensor data
            try:
                wind_sock.send(str(0).encode('utf-8'))
                wind_parsed = json.loads(wind_sock.recv(1024).decode('utf-8'))
                data['wind_dir'] = wind_parsed
            except (ValueError, socket.error) as e:
                # Broken pipe error
                logging.error('The wind sensor socket is broken!')

            # Send data to the server
            server_thread.send_data(modules.utils.getJSON(data))
            logging.debug('Data sent to the server %s' % json.dumps(json.loads(modules.utils.getJSON(data))))

            # Wait in the loop
            time.sleep(float(values['transmission_delay']))


## ----------------------------------------------------------
class LogicThread(StoppableThread):

    preferred_tack = 0 # -1 means left tack and 1 means right tack; 0 not on a tack
    preferred_gybe = 0

    def run(self):
        logging.info('Beginning autonomous navigation routines....')
        logging.warn('The angle is: %d' % data['wind_dir'])
        
        while True:

            if self.stopped():
                break

            # Update direction
            values['direction'] = modules.calc.direction_to_point(data['location'], target_locations[0])
            values['absolute_wind_direction'] = (data['wind_dir'] + data['heading']) % 360
            
            time.sleep(float(values['eval_delay']))
            
            if self.sailable(target_locations[location_pointer]):
                values['current_desired_heading'] = values['direction']
                self.preferred_tack = 0
                
            else:
    
                if self.preferred_tack == 0:  # If the target is not sailable and you haven't chosen a tack, choose one
                    self.preferred_tack = (180 - ((data['heading'] - values['absolute_wind_direction']) % 360)) / math.fabs(180 - ((data['heading'] - values['absolute_wind_direction']) % 360))
    
                if self.preferred_tack == -1:  # If the boat is on a left-of-wind tack
                    values['current_desired_heading'] = (values['absolute_wind_direction'] - 45 + 360) % 360
                    
                elif self.preferred_tack == 1: # If the boat is on a right-of-wind tack
                    values['current_desired_heading'] = (values['absolute_wind_direction'] + 45 + 360) % 360
                    
                else:
                    logging.error('The preferred_tack was %d' % self.preferred_tack)

            self.turn_rudder()
            self.turn_winch()
            self.check_locations()
            logging.debug("Heading: %d, Direction: %d, Wind: %d, Absolute Wind Direction: %d, Current Desired Heading: %d, Preferred Tack: %d, Sailable: %r\n" % (data['heading'], values['direction'], data['wind_dir'], values['absolute_wind_direction'], values['current_desired_heading'], self.preferred_tack, self.sailable(target_locations[location_pointer])))

    def turn_rudder(self):

        # Heading differential
        a = values['current_desired_heading'] - data['heading']
        if (a > 180):
            a -= 360

        # Cap the turn speed
        if (a > values['max_turn_rate_angle']):
            a = values['max_turn_rate_angle']

        # Cap the turn speed
        if (a < (-1 * values['max_turn_rate_angle'])):
            a = -1 * values['max_turn_rate_angle']

        rudder_angle = 90 + a * (values['max_rudder_angle'] / values['max_turn_rate_angle'])

        logging.debug('Set the rudder angle to: %f' % rudder_angle)
        self._kwargs['data_thread'].set_rudder_angle(rudder_angle)


    def turn_winch(self):

        self._kwargs['data_thread'].set_winch_angle(winch_angle)
            
    # Checks to see if the target location is within a sailable region        
    def sailable(self, target_location):
        angle_of_target_off_the_wind = (values['direction'] - values['absolute_wind_direction'])
        
        if(math.fabs(angle_of_target_off_the_wind) < 45):
            return False
        
        return True

    def check_locations(self):
        global location_pointer
        logging.debug('Trying to sail to %s' % target_locations[location_pointer])

        if modules.calc.point_proximity(data['location'], target_locations[location_pointer]):
            logging.debug('Location %s has been reached! Now traveling to %s!' % (target_locations[location_pointer], target_locations[location_pointer + 1]))
            location_pointer += 1

## ----------------------------------------------------------

if __name__ == '__main__':
    try:
        threading.current_thread().setName('Main')

        # Sets up the program configuration
        modules.utils.setup_config(values)
        modules.utils.setup_locations(target_locations, boundary_locations)

        logging.info('Starting SailBOT!')

        data_thread = DataThread(name='Data')
        logic_thread = LogicThread(name='Logic', kwargs={'data_thread': data_thread})

        data_thread.start()
        time.sleep(0)
        logic_thread.start()

        while True:
            time.sleep(100)

    except KeyboardInterrupt:
        logging.critical('Program terminating!')
        # Stop the threads
        data_thread.stop()
        logic_thread.stop()

        # Join the threads into the main threads
        data_thread.join()
        logic_thread.join()

        # Terminate the program
        logging.critical('Program exited!')
        sys.exit()
            