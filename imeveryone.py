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
import advertising
import fourchan
import threading
import Queue
import sys
import postprocessor
from tornado import template
from operator import itemgetter
from configobj import ConfigObj
from tornado.options import define, options
from time import gmtime, strftime
from subprocess import Popen

config = ConfigObj('imeveryone.conf')

antispam = postprocessor.startakismet(config['posting']['akismet'])

define("port", default=config['server'].as_int('port'), help="run on the given port", type=int)

useralerts = {}

class Application(tornado.web.Application):
    def __init__(self):
        # These handlers always get provided with the application, request and any transforms by Tornado
        handlers = [
            (r"/", RootHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
            (r"/a/message/new", NewPostHandler),
            (r"/a/message/updates", ViewerUpdateHandler),
            (r"/discuss/([a-z0-9\-]+)", DiscussHandler),
            (r"/about", AboutHandler),
            (r"/admin", AdminHandler),
            (r"/contact", ContactHandler),
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



class AdminHandler(BaseHandler):
    '''Handle admin'''
    @tornado.web.authenticated
    def get(self):
        self.write('Harrow! Admin goes here!')

class DiscussHandler(BaseHandler):
    '''Handle conversations'''
    def get(self,discuss):
        self.write('Harrow! Discussion goes here!'+discuss)
        # Expand graph here.
        

class AboutHandler(BaseHandler):
    '''Handle conversations'''
    def get(self):
        self.write('Harrow! About page goes here!')


class ContactHandler(BaseHandler):
    '''Handle conversations'''
    def get(self):
        self.write('Harrow! Contact page goes here!')


class RootHandler(BaseHandler):
    '''Handle request for our front page'''
    def get(self):
        global useralerts,config
        # Each user has a sessionid - we use this to present success / failure messages etc when posting
        if not self.get_cookie('sessionid'):
            self.set_cookie('sessionid', str(uuid.uuid4()))
        sessionid = self.get_cookie('sessionid')
        if not sessionid in useralerts:
            useralerts[sessionid] = []
            
        # Ensure messages are ordered corrrectly on initial connect
        sortedmessages = sorted(MessageMixin.cache, key=itemgetter('id'), reverse=True)
        captchahtml = postprocessor.captcha.displayhtml(config['captcha']['pubkey'])
        
        # Show the messages and any alerts
        print useralerts[sessionid]
        self.render(
            "index.html", 
            messages=sortedmessages, 
            captcha=captchahtml, 
            alerts=useralerts[sessionid], 
            heading=config['presentation']['heading'],
            prompt1 = config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(config['presentation']['prompt'].split()[1:]),
            )   


class MessageMixin(object):
    '''This is where the magic of tornado happens - we add clients to a waiters list, and when new messages arrive, we run send_messages() '''
    waiters = []
    # Amount of messages to keep around for new connections
    cache = []
    cache_size = config['newclients'].as_int('cachesize')
    def wait_for_messages(self, callback, cursor=None):
        '''Add new clients to waiters list'''
        if cursor:
            index = 0
            for i in xrange(len(MessageMixin.cache)):
                index = len(MessageMixin.cache) - i - 1
                # Note cursor is unicode not int
                # Converting unicode to int seems to mysteriously break comparison!
                if str(MessageMixin.cache[index]["id"]) == str(cursor): 
                    # Client is up to date now    
                    break
            recent = MessageMixin.cache[index + 1:]
            if recent:
                callback(recent)
                return
        MessageMixin.waiters.append(callback)
    def send_messages(self, messages):
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

def dbclient(dbconfig):
    dbconnection = Connection(dbconfig['host'],dbconfig.as_int('port'))
    messagesdb = dbconnection[dbconfig['messagesdb']]
    messagesdb.insert(post)
    

class NewPostHandler(BaseHandler, MessageMixin):
    '''Recieve new content from users and add them to our message queue'''
    def post(self):
        global messageQueue, config, useralerts
        logging.info("Post recieved from user!")

        # Clear alerts from previous posts
        sessionid = self.get_cookie('sessionid')
        useralerts[sessionid] = []    

        # Create message based on body of PUT form data
        message = {
            'submitid':str(uuid.uuid4()),
            'author':self.current_user["first_name"],
            'posttext':self.get_argument('posttext'), 
            'ip':self.request.remote_ip,
            'posttime':strftime("%Y-%m-%d %H:%M:%S", gmtime()),
            'threadid':None,                
            'challenge':self.get_argument('recaptcha_challenge_field'),
            'response':self.get_argument('recaptcha_response_field'),
            'useragent':self.request.headers['User-Agent'],
            'referer':self.request.headers['Referer'],
            'images':self.request.files['image'],
            'host':self.request.headers['Host'],
            'useralerts':[]
        }

        # Now for the image
        message = postprocessor.saveimages(message,config['images'])

        # Lets check our messages
        if len(message['posttext'].strip()) == 0:
            message['useralerts'].append('Cat got your tongue?')
        message = postprocessor.checkcaptcha(message,config)
        message = postprocessor.checkspam(message,config,antispam)
        message = postprocessor.checklinksandembeds(message,config)
        message = postprocessor.checkporn(message,config)
        logging.warn('---------------')
                    
        # If there are no errors
        if len(message['useralerts']) > 0:
            logging.info('Bad post!: '+' '.join(message['useralerts']))
        else:    
            logging.info('Good post.')
            messageQueue.put(message) 
            
        # We're done - sent the user back to wherever 'next' input pointed to.  
        if self.get_argument("next", None):
            self.redirect(self.get_argument("next"))            
    # Just in case someone tries to access this URL via a GET        
    def get(self):
        self.redirect('/')        



def render_template(template_name, **kwargs):
    '''Render a template (independent of requests)'''
    loader = template.Loader(os.path.join(os.path.dirname(__file__), "templates"))
    t = loader.load(template_name)
    return t.generate(**kwargs)
    
class QueueToWaitingClients(MessageMixin, threading.Thread):
    '''Take messages off the messageQueue, and send them to client'''
    def __init__(self, queue, config):
        self.__queue = queue
        self.__startid = config['posting'].as_int('startid')
        threading.Thread.__init__(self)  
        MessageMixin.__init__(self)        
    def run(self):
        while True: 
            message = self.__queue.get()   
            message['id'] = self.__startid
            logging.info('Preparing to send message ID: '+str(message['id'])+' with submit id '+str(message['submitid'])+' to clients.')
            self.__startid = self.__startid+1

            # Add an intro for particularly large text
            message['posttext'],message['intro'] = postprocessor.makeintro(message['posttext'],config['posting'])

            # Override existing links    
            message['link'] = '/discuss/'+str(message['id'])

            # Images    
            if config['images'].as_bool('enabled'):
            
                # Work on the image       
                if message['localfile']:   
                    # Get image text via OCR
                    if config['images']['ocr']:
                        message['imagetext'] = postprocessor.getimagetext(message['localfile'])
                    # Make picture preview 
                    logging.info('Local file is: '+message['localfile'])
                    message['preview'] = postprocessor.reducelargeimages(message['localfile'],config['images'])
                    logging.info('preview  is: '+message['preview'])
         
            message['html'] = render_template('message.html', message=message) 
            self.send_messages([message])

class ViewerUpdateHandler(BaseHandler, MessageMixin):
    '''Do updates. All clients continually send posts, which we only respond to when where there are new messages (where we run on_send_messages() )'''
    @tornado.web.asynchronous
    def post(self):
        logging.info('Update request') 
        cursor = self.get_argument("cursor", None)
        self.wait_for_messages(self.async_callback(self.on_send_messages),cursor=cursor)
    def on_send_messages(self, messages):
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
        
        # Start MongoDB
        startdb(config['database'])

        # Advertising content getter
        if config['injectors']['advertising'].as_bool('enabled'):            
            advertising.ContentGetter(messageQueue,config).start()

        # Test 4chan content getter to queue
        if config['injectors']['fourchan'].as_bool('enabled'):            
            fourchan.ContentGetter(messageQueue,config).start()
        
        # Take content from queue and send updates to waiting clients
        mycontentprocessor = QueueToWaitingClients(messageQueue,config)
        mycontentprocessor.start()
        
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        print 'Server cancelled'
        sys.exit(1)

def startdb(dbconfig):
    '''Start Database'''
    logging.info('Starting DB...')
    process = Popen([dbconfig['mongod'],'--dbpath',dbconfig['dbpath']])
    logging.info('started, PID is '+str(process.pid))
    return

if __name__ == "__main__":
    main()
