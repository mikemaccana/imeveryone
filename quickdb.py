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

def getmessage(id):
    '''Get a dict from DB and return a message object'''
    dbdict = db.connection.messages.find_one({'_id':id})
    return usermessages.Message(dehydrated=dbdict)

def savemessage(mymessage):
    '''Save a message object to DB'''
    quickdb.db.connection.messages.save(mymessage.__dict__)

def getscore(id):
    item = db.connection.messages.find_one({'_id':id})
    print item['_id']+':'+item['posttext']
    print item['score']
    return

def setscore(id,score):
    item = db.connection.messages.find_one({'_id':id})
    print item['_id']+':'+item['posttext']
    print item['score']
    item['score'] = score
    db.connection.messages.save(item)
    return
    
def updatetreecount(id):
    '''Update child count on messages'''
    mymessage = usermessages.Message(dehydrated=db.connection.messages.find_one(id))
    mymessage.updatetreecount(db.connection)
    quickdb.db.connection.messages.save(mymessage.__dict__)
    db.connection.messages.find_one(id).treecount
    return

def updateallitems():
    '''Update dates and remove old avatar variable'''
    for doc in db.connection.messages.find():
        message = usermessages.Message(dehydrated=doc)
        message.prettydate = message.getprettydate()
        doc = message.__dict__
        try:
            del doc['avatar']
        except:
            pass
        db.connection.messages.save(doc)
        
