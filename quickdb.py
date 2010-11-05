from database import Database
from configobj import ConfigObj

config = ConfigObj('imeveryone.conf')
database = Database(config['database'])

database.start()
database.dbclient()
database.connection.messages.find_one()
database.connection.messages.find_one({'_id':1})