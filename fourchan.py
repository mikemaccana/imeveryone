#!/usr/bin/env python2.6
'''4Chan provider for I'm Everyone'''
import httplib
from lxml import etree
from lxml.html.clean import clean_html
from lxml.html.clean import Cleaner
from lxml.html.soupparser import fromstring
import types
import pickle
import time
import threading
import Queue
import random
import sys
import re
import usermessages
import uuid
import logging
import urllib2
#import ipdb

debug = False

# Last thread added to our queue
lastadded = 0



def debugprint(text):
    if debug:
        print(text)

def expand(threads,thread):
    '''Expand a thread'''
    pass

myheaders = {
    'Host':'boards.4chan.org',
    'User-Agent':'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.5; en-US; rv:1.9.1.7) Gecko/20091221 Firefox/3.5.7',
    'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language':'en-us,en;q=0.5',
    #'Accept-Encoding':'gzip,deflate',
    'Accept-Charset':'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
    'Keep-Alive':'300',
    'Connection':'keep-alive',
    'Referer':'http://boards.4chan.org/b',
    #'If-Modified-Since':'Tue, 19 Jan 2010 19:46:10 GMT',
    }

def connect(channel):
    '''Connect to 4Chan page 1. Return data of threads.'''
    conn = httplib.HTTPConnection('boards.4chan.org')
    try:
        conn.request('GET', '/'+channel+'/', headers=myheaders)
    except:
        print 'Could not open 4chan. Check network connectivity.'
        sys.exit(1)    
    try:
        response = conn.getresponse()
    except:
        print '4chan has disconnected us'
        sys.exit(1)    
    debugprint(str(response.status)+response.reason)
    data = response.read()
    conn.close()
    return data

def gettree(data):
    '''Get serialized HTML, return a tree'''
    # Remove JS
    badtags = ['table','tr','td','noscript','style']
    cleaner = Cleaner(page_structure=False, javascript=False, annoying_tags=False, remove_tags=badtags)
    cleanhtml = cleaner.clean_html(data) 
    try:
        tree = fromstring(cleanhtml)
    except TypeError:
        print 'There was likely a unicode symbol' 
    return tree



def getnewposts(channel,lastadded,config):
    '''Return list of new threads. Each thread is a dict.'''
    newposts = []
    # Connect and get content
    data = connect(channel)
    # Parse content into etree
    tree = gettree(data)
    # Identify posts by the Reply link
    for element in tree.iter(tag=etree.Element):
        if element.tag == 'a' and element.text == 'Reply' and 'href' in element.attrib:
            # We've found a thread!
            destination = element.attrib['href']
            if destination.startswith('res/'):
                threadid = int(destination.split('/')[1])
                # Post text
                posttext = element.getparent().getnext().text
                if posttext is None:
                    posttext = ''                  
                # Author    
                author = element.getparent().getprevious().text
                if author is None:
                    author = ''
                # Time
                ## Convert to both a time and a serialized able format    
                timestring = etree.tostring(element.getparent().getprevious(),pretty_print=True).split()[-1]
                timenative = time.strptime(timestring,'%m/%d/%y(%a)%H:%M:%S')
                timetext = time.strftime("%a, %d %b %Y %H:%M:%S +0000", timenative)
                
                # Image
                try:
                    imageurl = element.getparent().getprevious().getprevious().getprevious().getprevious().attrib['href']   
                except (KeyError,IndexError):
                    imageurl = None   
                    
                # Fetch the image if necessary  
                if imageurl:
                    localfile = getimage(imageurl,config['images']['cachedir'])
                else:
                    localfile = None        
                    
                # Thumbnail    
                try:    
                    thumb = element.getparent().getprevious().getprevious().getprevious().getprevious()[0].attrib['src']                    
                except (IndexError,KeyError):
                    thumb = None
                # Link
                link = 'http://boards.4chan.org/'+channel+'/res/'+str(threadid)
                
                # Add the thread (as long as its new)    
                if threadid > lastadded:
                    newposts.append( {
                        'author':author,
                        'posttext':posttext,
                        'imageurl':imageurl,
                        'thumb':thumb,
                        'threadid':threadid,
                        'link':link,
                        #'posttime':timetext,
                        'posttime':time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        'localfile':localfile,
                        'preview':None,
                        'challenge':None,
                        'response':None,
                        'ip':'10.0.0.1',
                        'useragent':'4Chan test client',
                        'referer':None,
                        'imagedata':None,
                        'host':'www.imeveryone.com',
                        'comments':[],
                        'article':True,
                    })
                    lastadded = threadid
    return newposts,lastadded

def getbefore(element,amount):
    '''Fetch the element that is X beofre the current one'''
    count = 0
    while count < amount:
        element = element.getprevious()
        count += 1
    return element    

def expandthread(threads,thread):
    '''Expand a given thread. Return the updated threads list'''
    pass


def opendatabase(database):
    '''Open database and return threads'''
    try:
        threadfile = open(database,'r')
        threads = pickle.load(threadfile)
        threadfile.close()
    except IOError:
        threads = {}    
    return threads    


def getimage(imageurl,cachedir):
    '''Save an image to disk'''
    imagefile = imageurl.split('/')[-1]
    cachedfilename = cachedir+imagefile
    savedfile = open(cachedfilename,'wb')
    try:
        openurl = urllib2.urlopen(imageurl)
        savedfile.write(openurl.read())        
    except:
        logging.warn('Could not open URL '+imageurl)
        return None
    return cachedfilename

class ContentGetter(threading.Thread): 
    '''Gets messages from 4chan and puts them on our message queue'''
    def __init__(self, queue, config, database, app):
        self.__queue = queue
        self.__delay = config['injectors']['fourchan'].as_int('delay')
        self.__config = config
        self.__antispam = usermessages.startakismet(config['posting']['akismet'])
        self.dbconnect = database.connection
        threading.Thread.__init__(self)
        self.app = app
            
    def run(self):
        lastadded = 0
        while True:
            newposts,lastadded = getnewposts('b',lastadded,self.__config)
            for post in newposts:
                # Add new 4chan posts
                newid = self.app.getnextid()
                message = usermessages.Message(
                    config=self.__config,
                    antispam=self.__antispam,
                    _id=newid,
                    messagedata=post,
                    localfile=post['localfile']
                )
                # If no alerts, put post onto queue
                if len(message.useralerts) == 0: 
                    self.__queue.put(message) 
                
                # Save to DB
                self.dbconnect.messages.save(message.__dict__)
                
                delay = random.randint(self.__delay-2,self.__delay+3)
                time.sleep(delay)  


class ContentProcessor(threading.Thread): 
    '''Takes items off the messageQueue and prints them'''
    def __init__(self, queue):
        self.__queue = queue
        threading.Thread.__init__(self)    
    def run(self):
        while True: 
            message = self.__queue.get() 
    
