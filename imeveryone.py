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
import time
import usermessages
from tornado import template
from operator import itemgetter
from configobj import ConfigObj
from tornado.options import define, options
from time import gmtime, strftime
from subprocess import Popen
from pymongo import Connection
import ipdb

antispam = usermessages.startakismet(ConfigObj('imeveryone.conf')['posting']['akismet'])

useralerts = {}

class Application(tornado.web.Application):
    def __init__(self,config):
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
        self.config = config
        settings = config['application']
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
    def delete(self,discuss):
        self.write('Harrow! Discussion goes here!'+discuss)


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
        sortedmessages = sorted(MessageMixin.cache, key=lambda message: message.id, reverse=True)
        
        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])
        
        # Show the messages and any alerts
        print useralerts[sessionid]
        self.render(
            "index.html",
            messages=sortedmessages,
            captcha=captchahtml,
            alerts=useralerts[sessionid],
            heading=self.application.config['presentation']['heading'],
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            )


class MessageMixin(object):
    '''This is where the magic of tornado happens - we add clients to a waiters list, and when new messages arrive, we run send_messages() '''
    waiters = []
    # Amount of messages to keep around for new connections
    cache = []
    cache_size = 10 
    # FIXME - should be from global config
    #cache_size = config['newclients'].as_int('cachesize')
    
    def wait_for_messages(self, callback, cursor=None):
        '''Add new clients to waiters list'''
        if cursor:
            index = 0
            for i in xrange(len(MessageMixin.cache)):
                index = len(MessageMixin.cache) - i - 1
                # Note cursor is unicode not int
                # Converting unicode to int seems to mysteriously break comparison!
                if str(MessageMixin.cache[index].id) == str(cursor):
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
    

class NewPostHandler(BaseHandler, MessageMixin):
    '''Recieve new content from users and add them to our message queue'''
    def post(self):
        global messageQueue, config, useralerts
        logging.info("Post recieved from user!")
        
        # Clear alerts from previous posts
        sessionid = self.get_cookie('sessionid')
        useralerts[sessionid] = []
        
        # Let's make our message
        request = self.request        
        messagedata = {
            'posttime':strftime("%Y-%m-%d %H:%M:%S", gmtime()),
            'author':'Anonymous',
            'posttext':self.get_argument('posttext'),
            'challenge':self.get_argument('recaptcha_challenge_field'),
            'response':self.get_argument('recaptcha_response_field'),
            'ip':request.remote_ip,
            'useragent':request.headers['User-Agent'],
            'referer':request.headers['Referer'],
            'images':request.files['image'],
            'host':request.headers['Host'],
        }        
        message = usermessages.Message(messagedata,config,antispam)        
        
        # If there are no errors
        if len(message.useralerts) > 0:
            logging.info('Bad post!: '+' '.join(message.useralerts))
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
            message.id = self.__startid
            logging.info('Preparing to send message ID: '+str(message.id)+' with submit id '+str(message.submitid)+' to clients.')
            self.__startid = self.__startid+1
            message.html = render_template('message.html', message=message)
            self.send_messages([message])

class ViewerUpdateHandler(BaseHandler, MessageMixin):
    '''Do updates. All clients continually send posts, which we only respond to when where there are new messages (where we run on_send_messages() )'''
    @tornado.web.asynchronous
    def post(self):
        logging.info('Update request')
        cursor = self.get_argument("cursor", None)
        self.wait_for_messages(self.async_callback(self.on_send_messages),cursor=cursor)
    def on_send_messages(self, newmessages):
        # Finishes this response, ending the HTTP request.
        # Check for closed client connection
        if self.request.connection.stream.closed():
            return
        # Need to make a dict of our message objects k/v pairs so we can send it as JSON
        jsonmessages = []
        for newmessage in newmessages:
            jsonmessages.append({
                'link':newmessage.link,
                'posttime':newmessage.posttime,
                'posttext':newmessage.posttext,
                'intro':newmessage.intro,
                'embeds':newmessage.embeds,
                'preview':newmessage.preview,
                'id':newmessage.id,
                'html':newmessage.html,
                })  
        # We send a dict with one key, 'messages', which is the jsonmessages list
        self.finish(dict(messages=jsonmessages))

              


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


def startdb(dbconfig):
    '''Start Database'''
    logging.info('Starting DB...')
    process = Popen([dbconfig['mongod'],'--dbpath',dbconfig['dbpath'],'--port',dbconfig['port']])
    logging.info('started, PID is '+str(process.pid))
    return

def dbclient(dbconfig):
    '''Start database client, return messages collection'''
    dbconnection = Connection(dbconfig['host'],dbconfig.as_int('port'))
    messagesdb = dbconnection[dbconfig['messagesdb']]
    messagecollect = messagesdb.messages
    return messagecollect

def main():
    '''Separate main for unittesting and calling from other modules'''
    global messageQueue
    try:
        tornado.options.parse_command_line()
        messageQueue = Queue.Queue(0)
        
        config = ConfigObj('imeveryone.conf')
        
        http_server = tornado.httpserver.HTTPServer(Application(config))
        http_server.listen(config['server'].as_int('port'))
                
        # Start MongoDB, wait to start, start client.
        startdb(config['database'])
        time.sleep(5)
        messagecollect = dbclient(config['database'])
        logging.info('Database server and client started.')
        print '_'*80
        
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


if __name__ == "__main__":
    main()
