#!/usr/bin/env python2.6
'''Test for pifilter'''
import pifilter
import shutil
import os
import glob

count = 0
customerid = 'pTkGDZuAJmoy9E7JkYMeRJ9X6DAssu'
while count < 100:
    for file in glob.glob( 'static/cache/*.jpg' ):
        if 'preview' not in file:
            if '-' not in file:
                print '-----------------'
                print count
                print 'Checking file: '+ file
                response = pifilter.checkimage(file,customerid,aggressive=True)
                if response['result']:
                    print 'Looks like porn'
                    shutil.copy(file, 'static/cache/porn')
                else:
                    print 'Looks clean'
                    shutil.copy(file, 'static/cache/notporn')
                count+=1    
print 'Done!'                