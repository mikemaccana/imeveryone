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
    queryresult = fqlhelper.get(page,querydict=querydict,usejson=True)
    likecount = queryresult[0]['total_count']
    return likecount
    
print getlikecount('http://imeveryone.com/discuss/1297')    