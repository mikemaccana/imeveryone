#!/usr/bin/env python
import rest

def getlikecount(targeturl):
    '''Return count of Facebook likes for a target URL'''
    endpoint = 'https://api.facebook.com'
    
    page = '/method/fql.query'
    querydict = {
        'query':'''SELECT total_count FROM link_stat WHERE url="'''+targeturl+'''"''',
        'format':'json',
    }

    fqlhelper = rest.RESTHelper(endpoint='https://api.facebook.com')
    result = fqlhelper.get(page,querydict=querydict,usejson=True)
    count = result[0]['total_count']
    return count
    
print getlikecount('http://imeveryone.com/discuss/1297')    