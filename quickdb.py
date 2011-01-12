#!/usr/bin/env python
'''Quickly drop DB - eg, ./quickdb.py dev'''
from database import Database
from configobj import ConfigObj
import usermessages
import time
import sys
import pickle
import os

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
    '''Save a message object to DB, return the message ID'''
    return db.connection.messages.save(mymessage.__dict__)

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

def updatealldates():
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

def updatetreecounts():
    '''Update comment counts on messages'''
    for doc in db.connection.messages.find():
        message = usermessages.Message(dehydrated=doc)
        message.updatetreecount(db.connection)
        savemessage(message)

def backupdb(filename):
    '''Backup DB to Python pickle format'''
    messages = []
    dumpfile = open(filename, 'wb')
    for doc in db.connection.messages.find():
        messages.append(doc)
    pickle.dump(messages, dumpfile)
    print('Saved to '+filename)
    return
    
def getbackup(filename):
    '''Open and read picked data'''
    dumpfile = open(filename, 'rb')
    return pickle.load(dumpfile)
    
def changeid(oldid,newid):
    '''ChangeID of a top-level message'''    
    message = getmessage(oldid)
    oldid = message._id
    try:
        os.rename('static/cache/'+str(oldid)+'.jpg', 'static/cache/'+str(newid)+'.jpg')    
        os.rename('static/thumbs/'+str(oldid)+'_preview.jpg','static/thumbs/'+str(newid)+'_preview.jpg')    
    except:
        pass    
    message._id, message.thread = newid,newid
    message.link = u'/discuss/'+str(message._id)
    if message.localfile:
        message.localfile = u'static/cache/'+str(message._id)+'.jpg'
    if message.preview: 
        message.preview = u'static/thumbs/'+str(message._id)+'_preview.jpg'
    savemessage(message)
    db.connection.messages.remove(oldid)
    
    