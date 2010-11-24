#!/usr/bin/env python
'''Quickly drop DB - eg, ./quickdb.py dev'''
from database import Database
from configobj import ConfigObj
import time
import sys
config = ConfigObj('imeveryone.conf')
stage = sys.argv[1]
db = Database(config,stage=stage)

db.start()
db.dbclient()
db.connection.messages.find_one()
db.connection.messages.find_one({'_id':1})

print('_')*80
print('_')*80
print('_')*80
print('_')*80
#raw_input('DROPPING DATABASE IN 3 SECONDS. Press enter to destroy data, or Ctrl C to cancel')
time.sleep(3)

db.connection.messages.drop()
