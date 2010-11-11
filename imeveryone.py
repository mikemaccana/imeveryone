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
from database import Database
import random
import ipdb

antispam = usermessages.startakismet(ConfigObj('imeveryone.conf')['posting']['akismet'])

def stoplogging():
    '''Stop logging, start debugger.'''
    logging.getLogger().setLevel(logging.CRITICAL)
    print 'Stopped logging'

def pick_one(alist):
    return alist[random.randrange(0,len(alist))]


def messagemaker(handler,parentid=None):
    '''Get a request, return a message (used for both new posts and comments)
    FIXME: maybe move to usermessages, rename to requesttomessage? '''
    messagedata = {
        'top':False,
        'posttime':strftime("%Y-%m-%d %H:%M:%S", gmtime()),
        'author':'Anonymous',
        'posttext':handler.get_argument('posttext'),
        'ip':handler.request.remote_ip,
        'useragent':handler.request.headers['User-Agent'],
        'referer':handler.request.headers['Referer'],
        'host':handler.request.headers['Host'],
    }  

    # Add image data if enabled
    if 'image' in handler.request.files:
        messagedata['imagedata'] = handler.request.files['image']
    else:
        messagedata['imagedata'] = None
        
    # Add capctha info if enabled
    if handler.application.config['captcha'].as_bool('enabled'):
        messagedata['challenge'] = handler.get_argument('recaptcha_challenge_field')
        messagedata['response'] = handler.get_argument('recaptcha_response_field')
    else:
        messagedata['challenge'],messagedata['response'] = None, None
        
    if handler.request.path == '/a/message/new':
        messagedata['top'] = True
        
    _id = handler.application.getnextid()
    
    # Add out new comment ID as a child of parent
    if parentid:
        parent = handler.application.dbconnect.messages.find_one({'_id':int(parentid)})
        parent['comments'].append(_id)
        logging.info('Adding comment '+str(_id)+' as child of parent '+str(parentid))
        handler.application.dbconnect.messages.save(parent)
        
    message = usermessages.Message(
        messagedata,
        handler.application.config,
        antispam,
        _id
    )   
    return message    

class Application(tornado.web.Application):
    def __init__(self,config,database):
        # These handlers always get provided with the application, request and any transforms by Tornado
        handlers = [
            (r"/", RootHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
            (r"/a/message/new", NewPostHandler),
            (r"/a/message/updates", ViewerUpdateHandler),
            (r"/discuss/([0-9\-]+)", DiscussHandler),
            (r"/about", AboutHandler),
            (r"/top", TopHandler),
            (r"/admin", AdminHandler),
            (r"/admin/content", AdminContentHandler),
        ]
        self.config = config
        self.useralerts = {}
        settings = config['application']
        tornado.web.Application.__init__(self, handlers, **settings)
        self.dbconnect = database.connection
        def getstartid():
            '''Get highest _id of all messages in DB'''
            idlist = []
            for message in self.dbconnect.messages.find():
                idlist.append(int(message['_id'])) 
            sortedids = sorted(idlist, reverse=True)
            if not sortedids:
                # A fresh DB.
                biggest = -1
            else: 
                biggest = sortedids[0]   
            return biggest  
        self.currentid = getstartid()
    def getnextid(self):
        self.currentid += 1
        nextid = self.currentid
        return nextid

class BaseHandler(tornado.web.RequestHandler):
    '''Generic class for all URL handlers to inherit from - ensures users are always logged in'''
    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if not user_json:
            # User isn't logged in
            return None
        else:
            return tornado.escape.json_decode(user_json)

class TopHandler(BaseHandler):
    '''Top handler''' 
    def get(self):
        limit = self.application.config['scoring'].as_int('toplimit')
        topmessages=[]
        descending = -1
        for message in self.application.dbconnect.messages.find(limit=limit).sort('score', descending):
            topmessages.append(message)
        self.render(
            "top.html",
            #topmessages=self.application.dbconnect.messages.find({'tags':tag},limit=5):
            topmessages=topmessages,
            alerts=[],
            heading= pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = '''Today's top losers - I'm Everyone''',
            captcha = self.application.config['captcha'].as_bool('enabled'),
            )
        
class AdminHandler(BaseHandler):
    '''Handle admin'''
    @tornado.web.authenticated
    def get(self):
        self.render(
            "admin.html",
            name = self.current_user["first_name"],
            #pagetitle = '''Discuss - I'm Everyone''',
        )

class AdminContentHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        logging.info('/admin login from user :'+self.current_user["name"])
        if self.current_user["name"] != 'Mike MacCana':
            self.write('Access denied. User '+self.current_user["name"]+' is not allowed')
        else:    
            messages=[]
            for message in self.application.dbconnect.messages.find():
                messages.append(message)
            messages.sort()  
            self.render("admincontent.html",messages=messages,name=self.current_user["first_name"])

class DiscussHandler(BaseHandler):
    def get(self,messageid):
        '''Show discussion for a thread'''
        messageid = int(messageid)
        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])
        mymessage = self.application.dbconnect.messages.find_one({'_id':messageid})
        
        # Create a tree of comments.
        #commenttree = ['foo','bar','in','baz','woo','out','zam']   
        commenttree = usermessages.buildtree(mymessage,messagedb=self.application.dbconnect.messages)
        #ipdb.set_trace()
        
        self.render(
            "discuss.html",
            message=mymessage,
            captcha=captchahtml,
            alerts=[],
            heading= pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = '''Discuss - I'm Everyone''',
            commenttree=commenttree,
            nexturl=self.request.uri,
            )
            
    def post(self,parentid):
        '''Add a new child comment'''
        logging.info('New comment request')
      
        # Clear alerts from previous posts
        sessionid = self.get_cookie('sessionid')
        self.application.useralerts[sessionid] = []        
        
        # Make message
        message = messagemaker(self,parentid=parentid)       
    
        # If there are no errors, add to queue
        if len(message.useralerts) > 0:
            logging.info('Bad comment!: '+' '.join(message.useralerts))            
        else:
            logging.info('Good comment.')
        
        # Add alerts to dict and save dict to DB
        # FIXME - imagedata not being set to zero in usermessages, non-encoded so screwing mongo up.
        message.__dict__['imagedata'] = []
        self.application.dbconnect.messages.save(message.__dict__)
        
        # We're done - sent the user back to the comment
        self.redirect(self.get_argument('nexturl'))

class AboutHandler(BaseHandler):
    '''Handle conversations'''
    def get(self):
        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])       
        # Show the messages and any alerts
        self.render(
            "about.html",
            alerts=[],
            heading = pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = '''Who Is Responsible for this Mess? - I'm Everyone''',
            captcha = self.application.config['captcha'].as_bool('enabled'),
            )

class RootHandler(BaseHandler):
    '''Handle request for our front page'''
    def get(self):
        # Each user has a sessionid - we use this to present success / failure messages etc when posting
        if not self.get_cookie('sessionid'):
            self.set_cookie('sessionid', str(uuid.uuid4()))
        sessionid = self.get_cookie('sessionid')
        if not sessionid in self.application.useralerts:
            self.application.useralerts[sessionid] = []
        
        # Ensure messages are ordered corrrectly on initial connect
        sortedmessages = sorted(MessageMixin.cache, key=lambda message: message._id, reverse=True)
        
        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])
        
        # Show the messages and any alerts
        print self.application.useralerts[sessionid]
        self.render(
            "index.html",
            messages=sortedmessages,
            alerts=self.application.useralerts[sessionid],
            heading= pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = '''Live - I'm Everyone''',
            captcha = self.application.config['captcha'].as_bool('enabled'),
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
                logging.info('Cache index is %s', index)
                # Note cursor is unicode not int
                # Converting unicode to int seems to mysteriously break comparison!
                if str(MessageMixin.cache[index]._id) == str(cursor):
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
        logging.info('Done sending messages, setting waiters back to 0')
        MessageMixin.waiters = []
        logging.info('Adding messages to cache')
        MessageMixin.cache.extend(messages)
        if len(MessageMixin.cache) > self.cache_size:
            MessageMixin.cache = MessageMixin.cache[-self.cache_size:]
    

class NewPostHandler(BaseHandler, MessageMixin):
    '''Recieve new original content from users and add them to our message queue'''
    def post(self):
        global messageQueue
        logging.info("Post recieved from user!")        
        # Clear alerts from previous posts
        sessionid = self.get_cookie('sessionid')
        self.application.useralerts[sessionid] = []        
        
        # Make message
        message = messagemaker(self) 

    
        # If there are no errors, add to queue
        if len(message.useralerts) > 0:
            logging.info('Bad post!: '+' '.join(message.useralerts))            
        else:
            logging.info('Good post.')
            messageQueue.put(message)
        
        # Add alerts to dict and save dict to DB
        # FIXME - imagedata not being set to zero in usermessages, non-encoded so screwing mongo up.
        message.__dict__['imagedata'] = []
        self.application.dbconnect.messages.save(message.__dict__)
        
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
        self.queue = queue
        # Change this to DB lookup of highest ID.
        threading.Thread.__init__(self)
        MessageMixin.__init__(self)
    def run(self):
        while True:
            message = self.queue.get()
            logging.info('Preparing to send message ID: '+str(message._id)+' to clients.')
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
                'id':newmessage._id,
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
        # Start MongoDB server and client.
        database = Database(config['database'])
        database.start()
        database.dbclient()
        # Start web app
        app = Application(config,database=database)
        http_server = tornado.httpserver.HTTPServer(app)
        http_server.listen(config['server'].as_int('port'))
        print '_'*80        
        # Advertising content getter
        if config['injectors']['advertising'].as_bool('enabled'):
            advertising.ContentGetter(messageQueue,config).start()        
        # Test 4chan content getter to queue
        if config['injectors']['fourchan'].as_bool('enabled'):
            fourchan.ContentGetter(messageQueue,config,database=database, app=app).start()        
        # Take content from queue and send updates to waiting clients
        mycontentprocessor = QueueToWaitingClients(messageQueue,config)
        mycontentprocessor.start()        
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        print 'Server cancelled'
        sys.exit(1)


if __name__ == "__main__":
    main()
