#!/usr/bin/env python
'''Quickly drop DB - eg, ./quickdb.py dev'''
from database import Database
from configobj import ConfigObj
import usermessages
import time
import sys
config = ConfigObj('imeveryone.conf')
stage = 'dev'#sys.argv[1]
db = Database(config,stage=stage)


#db.start()
db.dbclient()
db.connection.messages.find_one()
db.connection.messages.find_one({'_id':1})

print('_')*80
print('_')*80
print('_')*80
print('_')*80
print('Ready')
#print('''db.connection.messages.drop()''')

def getscore(id):
    item = db.connection.messages.find_one({'_id':id})
    print item['_id']+':'+item['posttext']
    print item['score']
    return

def setscore(id):
    item = db.connection.messages.find_one({'_id':id})
    print item['_id']+':'+item['posttext']
    print item['score']
    db.connection.messages.save(item)
    return

def updateallitems():
    for doc in db.connection.messages.find():
        message = usermessages.Message(dehydrated=doc)
        message.prettydate = message.getprettydate()
        doc = message.__dict__
        db.connection.messages.save(doc)