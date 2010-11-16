#!/usr/bin/env python
from database import Database
from configobj import ConfigObj
import time

config = ConfigObj('imeveryone.conf')
db = Database(config['database'])

db.start()
db.dbclient()
db.connection.messages.find_one()
db.connection.messages.find_one({'_id':1})

print('_')*80
print('_')*80
print('_')*80
print('_')*80
#raw_input('DROPPING DATABASE. Press enter to destroy data, or Ctrl C to cancel')
#time.sleep(3)

db.connection.messages.drop()
