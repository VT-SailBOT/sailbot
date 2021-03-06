import socket, sys, json, time, modules.utils, autonomous, logging
from modules.utils import SocketType, socket_connect

logger = logging.getLogger('log')

# Define the global values, as generated by the configuration file
values = {}

def main():

    arduino_sock = socket_connect(SocketType.arduino)
    rudder_sock = socket_connect(SocketType.rudder)
    winch_sock = socket_connect(SocketType.winch)
    logger.debug('Built sockets!')

    time.sleep(1)
    logger.info('Starting sail boat RC control!')
    time.sleep(2)

    # Enter the main loop
    while True:
        try:
            arduino_sock.send(str(0).encode('utf-8'))
            states = json.loads(arduino_sock.recv(128).decode('utf-8'))

            rudder_angle = float(states['rudder']) * float(values['max_rudder_angle'])
            winch_angle = (float(states['winch']) * 20) + 60

            set_angle(rudder_sock, rudder_angle)
            set_angle(winch_sock, winch_angle)

            logger.info("Set %0.5f and %0.5f" % (winch_angle, rudder_angle))

            if states['switch']:
                generate_error('Leaving manual control for autonomous!')
                autonomous.main()
                generate_error('Manual control caught exited autonomous process! Continuing!')

        except Exception as e:
            logger.error("%r error!" % (e.__class__.__name__))

        time.sleep(0.25)

# Define servo control methods
def set_angle(connection, angle):
    connection.send(str(angle).encode('utf-8'))

if __name__ == '__main__':
    modules.utils.setup_config(values)
    if values['debug']:
        modules.utils.setup_logging()
        modules.utils.setup_terminal_logging()
    logger.debug('Read configuration values!')

    try:
        main()
    except:
        logger.critical("Shutting down!")
        time.sleep(2)
        modules.utils.shutdown_terminal()
