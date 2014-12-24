import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import threading
import os

wss = []

class WSHandler(tornado.websocket.WebSocketHandler):
    """ Creates the web socket server
    """
     
    def check_origin(self, origin):
        return True
    
    def open(self):
        print ('New connection established.')
        if self not in wss:
            wss.append(self)
            
    def on_message(self, message):
        print ('Received message: %s' % message)
 
    def on_close(self):
        print ('Connection closed.')
        if self in wss:
            wss.remove(self)
 
class IndexHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        self.render('web/index.html')


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/ws', WSHandler),
            (r'/', IndexHandler),
        ]
        settings = {
            "debug": True,
            "static_path": os.path.join(os.path.dirname(__file__), "web")
        }
        tornado.web.Application.__init__(self, handlers, **settings)


application = Application()
""" Defines the server parameters
"""


class ServerThread(threading.Thread):
    """ Creates thread which runs the web socket server
    """
    
    def send_data(self, message):
        for ws in wss:
            print ("Sending: %s" % message)
            ws.write_message(message);
            
    def close_sockets(self):
        print("Closing all connections....")
        for ws in wss:
            ws.close()
            
    def scheduled_func(self):
        print("Scheduled function!")
    
    def run(self):
        print ("Starting server.")
        http_server = tornado.httpserver.HTTPServer(application)
        http_server.listen(8888)
        
        # creates a periodic callback function
        interval_ms = 5000
        main_loop = tornado.ioloop.IOLoop.instance()
        sched = tornado.ioloop.PeriodicCallback(self.scheduled_func, interval_ms, io_loop=main_loop)
        
        # starts the callback and the main IO loop
        sched.start()
        main_loop.start()