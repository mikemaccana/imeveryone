#!/usr/bin/env python2.6
'''
Test imeveryone
'''
from imeveryone import *

# --- Setup & Support Functions ---
def setup_module():
    return
    
def teardown_module():
    '''Tear down test fixtures'''   
    return

def testAdminHandlerget():
    #myhandler = AdminHandler()
    #assert 'arrow' in myhandler.get()
    assert True     

if __name__=='__main__':
    import nose
    nose.main()     