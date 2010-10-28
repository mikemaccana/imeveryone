#!/usr/bin/env python
'''MongoDB database juice'''
import logging
from pymongo import Connection
from subprocess import Popen
import time

class Database(object):
    '''MongoDB object'''
    def __init__(self,dbconfig):
        self.config = dbconfig
        self.pid = None
        self.connection = None
        
    def start(self):
        '''Start Database server'''
        logging.info('Starting DB...')
        process = Popen([self.config['mongod'],'--dbpath',self.config['dbpath'],'--port',self.config['port']])
        logging.info('started, PID is '+str(process.pid))
        print '_'*80        
        print('Database server started.')
        self.pid = process.pid
        return

    def stop(self):
        '''Stop DB server'''
        process = Popen('/bin/kill','-TERM',str(self.pid))
        self.pid = None
        return

    def repairdb(self):
        '''Repairing Database server'''
        logging.info('Repairing DB...')
        process = Popen([self.config['mongod'],'--repair','--dbpath',self.config['dbpath'],'--port',self.config['port']])
        logging.info('Repaired, PID is '+str(process.pid))
        self.pid = process.pid
        return

    def dbclient(self):
        '''Start database client, sets connection property'''
        print 'Starting DB client'
        tries = 1
        while tries < self.config['maxretries']:
            logging.info('Connecting to database server, try '+str(tries)+'...')
            try:
                dbconnection = Connection(self.config['host'],self.config.as_int('port'))
                break
            except:    
                time.sleep(5)
            tries += 1    
        self.connection = dbconnection[self.config['dbname']]
        return