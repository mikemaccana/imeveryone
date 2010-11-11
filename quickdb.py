from database import Database
from configobj import ConfigObj

config = ConfigObj('imeveryone.conf')
db = Database(config['database'])

db.start()
db.dbclient()
db.connection.messages.find_one()
db.connection.messages.find_one({'_id':1})