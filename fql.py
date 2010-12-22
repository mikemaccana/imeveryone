#!/usr/bin/env python
import rest
import urllib
#from lxml import etree
import ipdb

endpoint = 'https://api.facebook.com'
subject = 'http://imeveryone.com/discuss/1297'

page = '/method/fql.query'
querydict = {
    'query':'SELECT total_count FROM link_stat WHERE url="'''+subject+'''"''',
    'format':'json',
}

fqlhelper = rest.RESTHelper(endpoint='https://api.facebook.com')
result = fqlhelper.get(page,querydict=querydict,usejson=True)

'''xmlresult = etree.XML(result)

countelement = xmlresult.xpath('/z:fql_query_response/z:link_stat/z:total_count', namespaces={
    'z':'http://api.facebook.com/1.0/',
    'xsi':'http://www.w3.org/2001/XMLSchema-instance'
})[0]
count = countelement.text
print count
'''

print result
ipdb.set_trace()