#!/usr/bin/env python
'''
Realtime anonmymous chat app
'''

import logging
import tornado.auth
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import os.path
import uuid
import fourchan
import threading
import Queue
import sys
import postprocessor

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)


class Application(tornado.web.Application):
    def __init__(self):
        # These handlers always get provided with the application, request and any transforms by Tornado
        handlers = [
            (r"/", InitialConnectHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
            (r"/a/message/new", NewPostHandler),
            (r"/a/message/updates", ViewerUpdateHandler),
        ]
        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            login_url="/auth/login",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
        )
        tornado.web.Application.__init__(self, handlers, **settings)


class BaseHandler(tornado.web.RequestHandler):
    '''Generic class for all URL handlers to inherit from - ensures users are always logged in'''
    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if not user_json: 
            # User isn't logged in
            return None
        else:    
            return tornado.escape.json_decode(user_json)


class InitialConnectHandler(BaseHandler):
    '''Handle initial get request for root dir, send client HTML which gets JS to do a post and get further messages!'''
    @tornado.web.authenticated
    def get(self):
        self.render("index.html", messages=MessageMixin.cache)


class MessageMixin(object):
    '''This is where the magic of tornado happens - we add clients to a waiters list, and when new messages arrive, we run new_messages() '''
    waiters = []
    cache = []
    cache_size = 200
    def wait_for_messages(self, callback, cursor=None):
        '''Add new clients to waiters list'''
        if cursor:
            index = 0
            for i in xrange(len(MessageMixin.cache)):
                index = len(MessageMixin.cache) - i - 1
                if MessageMixin.cache[index]["id"] == cursor: break
            recent = MessageMixin.cache[index + 1:]
            if recent:
                callback(recent)
                return
        MessageMixin.waiters.append(callback)
    def new_messages(self, messages):
        '''Send messages to connected clients!'''
        logging.info("Sending new message to %r viewers", len(MessageMixin.waiters))
        for callback in MessageMixin.waiters:
            try:
                callback(messages)
            except:
                logging.error("Error in waiter callback", exc_info=True)
        MessageMixin.waiters = []
        MessageMixin.cache.extend(messages)
        if len(MessageMixin.cache) > self.cache_size:
            MessageMixin.cache = MessageMixin.cache[-self.cache_size:]


class NewPostHandler(BaseHandler, MessageMixin):
    '''Take new messages sent from clients and add them to our message queue'''
    @tornado.web.authenticated 
    def post(self):
        global messageQueue
        logging.info("Post recieved from user!") 
        # Create message based on body of PUT form data
        message = {
            'id': str(uuid.uuid4()),
            'author': self.current_user["first_name"],
            'posttext': self.get_argument("body"),
            # Some dummy info before I add these to local posts 
            'link':'http://www.google.com',
            'posttime':'Just now',
            'threadid':'007',
            'image':None
            
        }
        messageQueue.put(message) 


    
class QueueToWaitingClients(MessageMixin, BaseHandler, threading.Thread):
    '''Takes items off the messageQueue and sends them to client'''
    def __init__(self, queue):
        #super( QueueToWaitingClients, self ).__init__()
        self.__queue = queue
        threading.Thread.__init__(self)  
        MessageMixin.__init__(self)        
    def run(self):
        while True: 
            message = self.__queue.get()   
            message['id'] = str(uuid.uuid4())
            # Comes from BaseHandler, which inherits from tornado.web.RequestHandler, which provides
            #message["html"] = self.render_string("message.html", message=message)
            basicpost = '''<DIV class="timestamp"><H3><A href="'''+message['link']+'''">'''+message['posttime']+'''</A> '''+message['author']+'''</H3></DIV><H2>'''+message['posttext']+'''</H2><DIV class="endpost">'''
            
            # Now fetch the image and make the include  
            if message['image']:       
                localfile = fourchan.getimage(message['image'])
                localfile = postprocessor.reducelargeimages(localfile)
                pictureinclude = '''<P><A href="'''+message['link']+'''"><IMG class="lede" src="'''+localfile+'''" alt=""></A></P>'''
            else:
                pictureinclude = ''                 
                                
            #textybit = '''<P class="intro"><SPAN class="drop">"</SPAN>'''+'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin nec arcu a est vulputate ultrices. Donec orci orci, porttitor sed luctus id, porttitor sed dolor.'+'''</P><P>"Mauris mattis quam at arcu scelerisque fringilla. Pellentesque porta porttitor urna ac varius. Duis in sem eget enim rhoncus tincidunt a ut urna. Fusce bibendum interdum lectus id molestie. Etiam dignissim luctus magna pretium placerat. Fusce sed ornare nibh. Donec in arcu ac neque commodo ultricies. Nam et turpis in orci accumsan mattis sed ut felis."</P>'''
            tag = '''<P><CITE><A href="'''+message['link']+'''">Read more...</A> '''+str(message['threadid'])+'''</CITE></P><HR>'''            

            message["html"] = basicpost + pictureinclude + tag
            self.new_messages([message])


class ViewerUpdateHandler(BaseHandler, MessageMixin):
    '''Do updates. All clients continually send posts, which we only respond to when where there are new messges (where we run on_new_Messages() )'''
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def post(self):
        logging.info('Recieved request for content') 
        cursor = self.get_argument("cursor", None)
        self.wait_for_messages(self.async_callback(self.on_new_messages),cursor=cursor)
    def on_new_messages(self, messages):
        # Closed client connection
        if self.request.connection.stream.closed():
            return
        self.finish(dict(messages=messages))


class AuthLoginHandler(BaseHandler, tornado.auth.GoogleMixin):
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("openid.mode", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authenticate_redirect(ax_attrs=["name"])
    
    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Google auth failed")
        self.set_secure_cookie("user", tornado.escape.json_encode(user))
        self.redirect("/")


class AuthLogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.write("You are now logged out")



def main():
    '''Separate main for unittesting and calling from other modules'''
    global messageQueue
    try:
        tornado.options.parse_command_line()
        messageQueue = Queue.Queue(0)
        
        http_server = tornado.httpserver.HTTPServer(Application())
        http_server.listen(options.port)

        # Keep supplying new content to queue
        mycontentgetter = fourchan.ContentGetter(messageQueue)
        mycontentgetter.start()
        
        # Take content from queue and send updates to waiting clients
        mycontentprocessor = QueueToWaitingClients(messageQueue)
        mycontentprocessor.start()
        
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        print 'Server cancelled'
        sys.exit(1)

if __name__ == "__main__":
    main()
