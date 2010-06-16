#!/usr/bin/env python2.6
'''4Chan provider for EnterpriseChan'''
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
    #'If-Modified-Since':'Tue, 19 Jan 2010 19:46:10 GMT',
    }

def connect(channel):
    '''Connect to 4Chan page 1. Return data of threads.'''
    conn = httplib.HTTPConnection('boards.4chan.org')
    conn.request('GET', '/'+channel+'/', headers=myheaders)
    try:
        response = conn.getresponse()
    except error:
        print '4chan has disconnected us'
        sys.exit(1)    
    debugprint(str(response.status)+response.reason)
    data = response.read()
    conn.close()
    return data

def gettree(data):
    '''Get serialized HTML, return a tree'''
    # Remove JS
    badtags=['table','tr','td','noscript','style']
    cleaner = Cleaner(page_structure=False, javascript=False, annoying_tags=False, remove_tags=badtags)
    cleanhtml = cleaner.clean_html(data) 
    tree = fromstring(cleanhtml)
    return tree

def updatethreadindex(channel,lastadded):
    '''Return list of new threads. Each thread is a dict.'''
    newthreads = []
    # Connect and get content
    data = connect('b')
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
                timestring = etree.tostring(element.getparent().getprevious(),pretty_print=True).split()[-1]
                posttime = time.strptime(timestring,'%m/%d/%y(%a)%H:%M:%S')
                # Image
                try:
                    image = element.getparent().getprevious().getprevious().getprevious().getprevious().attrib['href']
                except (KeyError,IndexError):
                    image = 'No image'
                # Thumbnail    
                try:    
                    thumb = element.getparent().getprevious().getprevious().getprevious().getprevious()[0].attrib['src']
                except (IndexError,KeyError):
                    thumb = 'No thumb'
                # Add the thread (as long as its new)    
                if threadid > lastadded:
                    newthreads.append( {'author':author,'posttext':posttext,'image':image,'thumb':thumb,'posttime':posttime,'id':threadid})
                    lastadded = threadid
    return newthreads,lastadded

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
    
def savedatabase(threads,database):
    '''Save databae to a file'''    
    threadfile = open('threads.db','w')    
    pickle.dump(threads, threadfile)

class ContentGetter(threading.Thread): 
    '''Gets messages from 4chan and puts them on our message queue'''
    def __init__(self, queue):
        self.__queue = queue
        threading.Thread.__init__(self)
            
    def run(self):
        lastadded = 0
        while True:
            newthreads,lastadded = updatethreadindex('b',lastadded)
            for thread in newthreads:
                self.__queue.put(thread) 
                delay = random.randint(3,7)
                time.sleep(delay)  


class ContentProcessor(threading.Thread): 
    '''Takes items off the messageQueue and prints them'''
    def __init__(self, queue):
        self.__queue = queue
        threading.Thread.__init__(self)    
    def run(self):
        while True: 
            message = self.__queue.get() 
            print message['author']
            print message['posttext']
            print message['id']
            print '------------'

def main():
    '''start threads in perpetuity'''
    messageQueue = Queue.Queue(0)
    
    mycontentgetter = ContentGetter(messageQueue)
    mycontentgetter.start()
    mycontentprocessor = ContentProcessor(messageQueue)
    mycontentprocessor.start()

if __name__ == '__main__':
    main()
    
