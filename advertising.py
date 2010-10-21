#!/usr/bin/env python2.6
'''Advertising injector for I'm Everyone'''
import threading
import Queue
import random
import time


class ContentGetter(threading.Thread): 
    '''Periodically ads avertisements to our message queue'''
    def __init__(self, queue, config):
        self.__queue = queue
        self.__delay = config['injectors']['advertising'].as_int('delay')
        self.__config = config
        threading.Thread.__init__(self)
            
    def run(self):
        while True:
            ads = [
                    {
                    'link':'http://www.google.com',
                    'copy':'Buy stuff!',
                    'image':'static/cache/ad1.jpg'
                    },
                ]
            for ad in ads:
                delay = random.randint(self.__delay-2,self.__delay+3)
                time.sleep(delay)
                message = {
                'ad':True,
                'referer': None, 
                'ip': '10.0.0.1', 
                'submitid':None,
                'imageurl': None, 
                'host': 'www.imeveryone.com', 
                'link': ad['link'], 
                'posttime': 'Sat, 31 Jul 2010 16:37:55 +0000', 
                'posttext': '[AD] '+ad['copy'], 
                'thumb': 'http://1.thumbs.4chan.org/b/thumb/1280608675456s.jpg', 
                'author': 'Anonymous', 
                'embeds': [], 
                'useralerts': [], 
                'threadid': 259653846, 
                'useragent': 'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.5; en-US; rv:1.9.1.7) Gecko/20091221 Firefox/3.5.7', 
                'preview': None, 
                'original': 'fubdubadubblubslubbabubba', 
                'localfile': ad['image']
                }
                
                self.__queue.put(message) 