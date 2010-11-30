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
 

class Application(tornado.web.Application):
    def __init__(self,config,database,stage='dev'):
        # These handlers always get provided with the application, request and any transforms by Tornado
        handlers = [
            (r"/(page/[1-5])?", TopHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
            (r"/a/message/new", NewPostHandler),
            (r"/a/message/updates", ViewerUpdateHandler),
            (r"/discuss/([0-9\-]+)", DiscussHandler),
            (r"/about", AboutHandler),
            (r"/live", LiveHandler),
            (r"/admin", AdminHandler),
            (r"/admin/content", AdminContentHandler),
            (r"/(.*)", CatchAllHandler),
        ]
        self.stage = stage
                 
        self.config = config
        self.useralerts = {}
        self.textprefill = {}
        settings = config['application'][stage]
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
        '''Return next avail comment/reply ID'''
        self.currentid += 1
        nextid = self.currentid
        return nextid    
    def getusercount(self):    
        '''Generate user count
        In future: len(MessageMixin.waiters) provides an accurate measure'''
        hour = time.gmtime()[3]
        # change user count very 3 mins
        minutecache = time.gmtime()[4]/3
        minimum = self.config['usercount'].as_int('minimum')
        # FIXME should be actual user count in future!
        actual = self.config['usercount'].as_int('actual')
        multiplier = self.config['usercount'].as_int('multiplier')

        # Convert hours to peak multiplier
        peakhour = [3,2,1,1,1,5,6,7,8,9,10,10,10,10,10,10,9,8,9,10,10,10,10,7][hour]
        users = minimum + (peakhour * actual * multiplier) + minutecache
        return users

class BaseHandler(tornado.web.RequestHandler):
    '''Generic class for all URL handlers to inherit from'''
    def get_current_user(self):
        '''ensures users are always logged in'''
        user_json = self.get_secure_cookie("user")
        if not user_json:
            # User isn't logged in
            return None
        else:
            return tornado.escape.json_decode(user_json)
    def pick_one(self,alist):
        '''Pick an item from a list at random'''
        return alist[random.randrange(0,len(alist))]     
    def showalerts(handler):
        '''Show alerts for session''' 
        # FIXME self.sessionid perhaps?
        sessionid = handler.get_cookie('sessionid')
        # None would be for new clients
        alerts = []
        if sessionid is not None:
            if sessionid in handler.application.useralerts:
                alerts = handler.application.useralerts[sessionid]
                if len(alerts) > 0:
                    logging.info('About to show user alerts for cookie user: '+str(sessionid))
        return alerts
    def clearalerts(self):
        '''Clear alerts for session''' 
        sessionid = self.getorsetsessionid()
        if sessionid in self.application.useralerts:
            self.application.useralerts[sessionid] = []
        return
    def messagemaker(self,parentid=None):
        '''Get a request, return a message (used for both new posts and comments)'''
        _id = self.application.getnextid()
        message = usermessages.Message(
            config=self.application.config,
            antispam=antispam,
            _id=_id,
            handler=self,
            parentid=parentid
        )
        return message           
    def gettextprefill(self):
        '''Get previous text, to allow user to correct their old errors'''
        sessionid = self.getorsetsessionid()
        if sessionid in self.application.textprefill:
            textprefill = self.application.textprefill[sessionid]
            self.application.textprefill[sessionid] = ''
            return textprefill
        else:
            return ''
    def getorsetsessionid(self): 
        # Each user has a sessionid - we use this to present success / failure messages etc when posting
        if not self.get_cookie('sessionid'):
            self.set_cookie('sessionid', str(uuid.uuid4()))
        sessionid = self.get_cookie('sessionid')    
        return sessionid
            
class TopHandler(BaseHandler):
    '''Top handler''' 
    def get(self,page):
        # Always set a sessionID for first time visitors
        sessionid = self.getorsetsessionid()
        
        if page is None:
            page = 1
        else:
            page = int(page.split('/')[1])

        
        itemsperpage = self.application.config['scoring'].as_int('itemsperpage')
        
        limit = self.application.config['scoring'].as_int('toplimit')
        topmessages=[]
        messagedicts=[]
        
        descending = -1
        # Get our Mongo docs
        for messagedict in self.application.dbconnect.messages.find({'parentid':None},limit=limit).sort('score', descending):
            messagedicts.append(messagedict)
        # Turn the Mongo docs back into Message objects
        for messagedict in messagedicts:
            topmessages.append(usermessages.Message(dehydrated=messagedict))
        
        # Now get ranks, and make a ranked list of messages
        rankedmessages = []
        for topmessage in topmessages:
            topmessage.rank = topmessage.getrank()
            rankedmessages.append(topmessage)
        rankedmessages.sort(key=lambda x: x.rank, reverse=True)
        
        # Show subset of rankedmessages for page
        start = (page-1)*itemsperpage  
        end = start + itemsperpage
        logging.info('page is: '+str(page)+' woo, showing items '+str(start)+' to '+str(end))
        rankedmessages = rankedmessages[start:end]        
             
        # FIXME - DEBUG for occasional prod issue
        for message in topmessages: 
            if not hasattr(message, 'embedcode'): 
                logging.warn('Note, message ID '+str(message._id)+' is missing embedcode in DB')
            #else:
            #    logging.info('Note, message ID '+str(message._id)+' embedcode is OK.')    
                
                
        alerts = self.showalerts()
        
        self.render(
            "top.html",
            topmessages = rankedmessages,
            alerts = alerts,
            heading = self.pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = self.application.config['presentation']['top'],
            captcha = self.application.config['captcha'].as_bool('enabled'),
            sidebar = True,
            readmore = True,
            avatars = True,
            textprefill = self.gettextprefill(),
            emptydb = self.application.config['alerts']['emptydb'],
            usercount = self.application.getusercount(),
            witticism = self.pick_one(self.application.config['presentation']['witticism']),
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
        # Always set a sessionID for first time visitors
        sessionid = self.getorsetsessionid()
        
        messageid = int(messageid)
        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])
        mymessagedict = self.application.dbconnect.messages.find_one({'_id':messageid})
        
        # Check for discussion of invalid items
        if mymessagedict is None:
            logging.warn('Request for non existent message id: '+str(messageid))
            self.redirect('/notfound')
        
        # Increment score for message
        mymessagedict['score']+=self.application.config['scoring'].as_int('view')
        self.application.dbconnect.messages.save(mymessagedict)
        
        # Create a tree of comments 9this should reqlly be a Message method)
        commenttree = usermessages.buildtree(mymessagedict,messagedb=self.application.dbconnect.messages)
        
        alerts = self.showalerts()
        
        # Create message objects from our dictionary
        mymessage = usermessages.Message(dehydrated=mymessagedict)
        
        pagetitle = '''I'm Everyone - '''+' '.join(mymessage.posttext.split()[0:15])+'...'
        
        self.render(
            "discuss.html",
            message = mymessage,
            captcha = captchahtml,
            alerts = alerts,
            heading = self.pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = pagetitle,
            commenttree = commenttree,
            nexturl = self.request.uri,
            sidebar = None,
            readmore = True,
            avatars = True,
            witticism = self.pick_one(self.application.config['presentation']['witticism']),
        )
            
    def post(self,parentid):
        '''Add a new child comment'''
        logging.info('New comment request')
      
        # Clear alerts from previous posts
        sessionid = self.getorsetsessionid()
        self.application.useralerts[sessionid] = []        
        
        # Make message
        message = self.messagemaker(parentid=parentid)       
    
        # If there are errors, alert
        if len(message.useralerts) > 0:
            logging.info('Bad comment!: '+' '.join(message.useralerts))   
            # Add the messages alerts to our session alerts
            self.application.useralerts[sessionid] = message.useralerts
        else:
            # If there are no errors, add to queue
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
        # Always set a sessionID for first time visitors
        self.getorsetsessionid()

        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])     
        
        alerts = self.showalerts()
          
        # Show the messages and any alerts
        self.render(
            "about.html",
            alerts = alerts,
            heading = self.pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = '''Who Is Responsible for this Mess? - I'm Everyone''',
            captcha = self.application.config['captcha'].as_bool('enabled'),
            sidebar=True,
            textprefill = self.gettextprefill(),
            usercount = self.application.getusercount(),
            witticism = self.pick_one(self.application.config['presentation']['witticism']),
        )
            

class CatchAllHandler(BaseHandler):
    def get(self,url):
        '''404'''
        logging.warn('Bad URL: '+url)
        self.render('notfound.html',
            pagetitle='Not Found!',
            heading='Oops',
            prompt1='Doesnt Exist Heh?',
            prompt2='Make It',
            badurl=url,
            alerts=[],
            sidebar=False,
            witticism = self.pick_one(self.application.config['presentation']['witticism']),
        )
        raise tornado.web.HTTPError(404)


class LiveHandler(BaseHandler):
    '''Handle request for our front page'''
    def get(self):
        # Always set a sessionID for first time visitors
        sessionid = self.getorsetsessionid()
        if not sessionid in self.application.useralerts:
            self.application.useralerts[sessionid] = []
        
        # Ensure messages are ordered correctly on initial connect
        # should become a DB query
        sortedmessages = []
        descending = -1
        for sortedmessage in self.application.dbconnect.messages.find({'parentid':None},limit=50).sort('_id', descending):
            sortedmessages.append(usermessages.Message(dehydrated=sortedmessage))
        
        captchahtml = usermessages.captcha.displayhtml(self.application.config['captcha']['pubkey'])
        
        # Show the messages and any alerts
        alerts = self.showalerts()
        
        self.render(
            "live.html",
            messages = sortedmessages,
            alerts = alerts,
            heading = self.pick_one(self.application.config['presentation']['heading']),
            prompt1 = self.application.config['presentation']['prompt'].split()[0],
            prompt2 = ' '.join(self.application.config['presentation']['prompt'].split()[1:]),
            pagetitle = '''Live - I'm Everyone''',
            captcha = self.application.config['captcha'].as_bool('enabled'),
            sidebar = True,
            readmore = True,
            avatars = True,
            textprefill = self.gettextprefill(),
            usercount = self.application.getusercount(),
            witticism = self.pick_one(self.application.config['presentation']['witticism']),
        )
        self.clearalerts() 

class MessageMixin(object):
    '''This is where the magic of tornado happens - we add clients to a waiters list, and when new messages arrive, we run send_messages() '''
    waiters = []
    # Amount of messages to keep around for new connections
    cache = []
    cache_size = 10 
    # FIXME - should be from global config
    # cache_size = self.application.config['newclients'].as_int('cachesize')
    
    def wait_for_messages(self, callback, cursor=None):
        '''Add new clients to waiters list'''
        if cursor:
            index = 0
            # Loops each numbered message in the cache
            for num in xrange(len(MessageMixin.cache)):
                index = len(MessageMixin.cache) - num - 1
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
        sessionid = self.getorsetsessionid()
        self.application.useralerts[sessionid] = []        
        
        # Make message
        message = self.messagemaker() 
    
        # Check for errors
        if len(message.useralerts) > 0:
            # Add an alert to show once redirected
            
            logging.info('Bad post!: '+' '.join(message.useralerts))      
            self.application.useralerts[sessionid].extend(message.useralerts)    
            self.application.textprefill[sessionid] = message.posttext 
        else:
            # No errors, add to queue
            logging.info('Good post.')
            # Add alerts to dict and save dict to DB
            # FIXME - imagedata not being set to zero in usermessages, non-encoded so screwing mongo up.
            message.__dict__['imagedata'] = []
            self.application.dbconnect.messages.save(message.__dict__)
            if not message.parentid:
                # Put top-level posts onto the live queue.
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
        self.queue = queue
        # Change this to DB lookup of highest ID.
        threading.Thread.__init__(self)
        MessageMixin.__init__(self)
    def run(self):
        while True:
            message = self.queue.get()
            logging.info('Preparing to send message ID: '+str(message._id)+' to clients.')
            prettydate = message.getprettydate()
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
                'embedcode':newmessage.embedcode,
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
    # FIXME global should be app property
    global messageQueue
    
    def getstage():
        '''Determine whether prod or dev'''
        stage = 'dev'
        if len(sys.argv) > 1: 
            if sys.argv[1] == 'prod':
                stage = 'prod'
        return stage
    stage = getstage()    
    
    try:
        tornado.options.parse_command_line()
        messageQueue = Queue.Queue(0)
        config = ConfigObj('imeveryone.conf')
        # Set up logging
        logging.basicConfig(level=logging.DEBUG, filename=config['application'][stage]['logfile'])
        # Start MongoDB server and client.
        database = Database(config,stage)
        database.start()
        database.dbclient()
        # Start web app
        app = Application(config,database=database,stage=stage)
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
