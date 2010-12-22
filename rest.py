#!/usr/bin/env python
'''REST API generic client'''

import base64
from urllib2 import Request, urlopen, URLError
import urllib
import re
from BaseHTTPServer import BaseHTTPRequestHandler
# Update Pythons list of error codes with some that are missing
newhttpcodes = {
    422:('Unprocessable Entity','HTTP_UNPROCESSABLE_ENTITY'),
    423:('Locked','HTTP_LOCKED'),
    424:('Failed Dependency','HTTP_FAILED_DEPENDENCY'),
    425:('No code','HTTP_NO_CODE'),
    426:('Upgrade Required','HTTP_UPGRADE_REQUIRED'),
}
for code in newhttpcodes:
    BaseHTTPRequestHandler.responses[code] = newhttpcodes[code]

import simplejson as json
import logging

class RESTHelper(object):
    def __init__(self,endpoint,useragent='Mike MacCana REST API',username=None,password=None):
        self.useragent = useragent
        self.endpoint = endpoint
        if username:
            self.authstring = self.getauthstring(authendpoint,username,password)
        else:
            self.authstring = None
        
        # This function also handles POSTS if postdata is supplied     
        self.post = self.get

    def getauthstring(self,__endpoint,username,password):
        encodedstring = base64.encodestring(username+':'+password)[:-1]
        return "Basic %s" % encodedstring

    def get(self,url,querydict=None,postdata=None,strict=True,usejson=False):    
        '''Does GET requests and (if postdata specified) POST requests.'''
        url = self.endpoint+url
        if querydict:
            # Add URL encoded query dict
            url += '?'+urllib.urlencode(querydict)
            
        if postdata:
            if strict:
                '''Some REST APIs expect square brackets which are normally encoded according to RFC 1738. 
                If you disable strict, we won't bother encoding the post data which will work around these buggy REST APIs'''
                postdata = urllib.urlencode(postdata)
        params = {'User-Agent': self.useragent, }     
        if self.authstring:
            params["Authorization": self.authstring]        
        request = Request(url, postdata, params)
        result = self.__requesthelper(request)
        if usejson: 
            if result:
                return json.loads(result)        
            else:
                return None
        else:
            return result        
    def delete(self,url):    
        '''Does DELETE requests.'''
        raise Exception('Not implemented yet')
                  
    def __requesthelper(self,request):
        '''Does requests and maps HTTP responses into delicious Python juice'''
        try:
            handle = urlopen(request)            
        except URLError, e:
            # Check returned URLError for issues and report 'em
            if hasattr(e, 'reason'):
                print 'We failed to reach a server.'
                print 'Reason: ', e.reason
                return
            elif hasattr(e, 'code'):
                print 'Error code: ', e.code
                print '\n'.join(BaseHTTPRequestHandler.responses[e.code])
                return
        else:
            return handle.read()