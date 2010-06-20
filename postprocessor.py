#!/usr/bin/env python2.6
'''import httplib
from lxml import etree
from lxml.html.clean import clean_html
from lxml.html.clean import Cleaner
from lxml.html.soupparser import fromstring
import types
import GeoIP
import pickle
import fourchan
import re'''
from PIL import Image
'''import sys
import time
sys.path.append('/root')
import tesseract'''
import ipdb
import urllib2

#re.IGNORECASE

'''
* Rate my / rate my /Check out my pics /b/. What do you think of me?- display rating
* In return
* Timelines from nao to dead
* Need jokes on
* Looking for
* identify type of site
* ask X anything
* srvice / usernmae / pass|pword'''

'''
http://www.youtube.com/watch?v=w46Dwh4TMGA

<object width="425" height="344"><param name="movie" value="http://www.youtube.com/v/w46Dwh4TMGA&hl=en_US&fs=1&"></param><param name="allowFullScreen" value="true"></param><param name="allowscriptaccess" value="always"></param><embed src="http://www.youtube.com/v/w46Dwh4TMGA&hl=en_US&fs=1&" type="application/x-shockwave-flash" allowscriptaccess="always" allowfullscreen="true" width="425" height="344"></embed></object>

* GeoIP and match for countryfags
NLTK collocations
nltk relations

'''

def expandthreads(threads,threadid):
    '''Get thread content for a given thread'''
        
    return

def reducelargeimages(imagefile):
    '''Reduce images larger than a certain size'''
    myimage = Image.open(imagefile)
    width,height = myimage.size
    aspect = float(width) / float(height)
    maxwidth = 500
    maxheight = 500
    maxsize = (maxwidth,maxheight)    
    # Don't bother if image is already smaller
    if width < maxwidth and height < maxheight:
        return imagefile
    # Resize, save, return preview file name    
    else:    
        myimage.thumbnail(maxsize,Image.ANTIALIAS)
        newfilename = imagefile.split('.')[-2]+'_preview.'+imagefile.split('.')[-1]
        try:
            myimage.save(newfilename)
        except:
            return None    
        return newfilename


def getimage(imageurl,cachedir):
    '''Save an image to disk'''
    imagefile = imageurl.split('/')[-1]
    cachedfilename = cachedir+imagefile
    openurl = urllib2.urlopen(imageurl)
    savedfile = open(cachedfilename,'wb')
    savedfile.write(openurl.read())    
    return cachedfilename

def makeintro(posttext):
    postwords = posttext.split()
    if len(postwords) < 20:
        return posttext,None 
    else:
        posttext = ' '.join(postwords[0:20])+'...'
        intro = '...'+' '.join(postwords[20:]) 
        return (posttext, intro)    
    
def getuserpprops(ip):
    gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
    print gi.country_code_by_addr(ip)    


def getimagetext(imagefile):
    '''Recieve an image, return the text'''
    image = Image.open(imagefile)
    # Convert to black and white
    if image.mode != "L":
        image = image.convert("L")
    text = tesseract.image_to_string(image)
    return text
    

def getthreadprops(threads):
    '''Determines posts where there is a winner, or a decider'''
    for thread in threads:
        posttext = threads[thread]['posttext']
        # Determine what winning thread will be
        threads[thread]['winner'] = None 
        winnerre = re.compile('^[if ]*.*[ending ]*[in ]*(doubles|triples)')
        if len(winnerre.findall(posttext)) > 0:
            firstmatch = winnerre.findall(posttext)[0]
            remainingtext = posttext.partition(firstmatch)[2]
            print 'Doubles post found'
            print posttext
            print remainingtext
            # Work out whether the winning post determines or wins them 
            decidesre = re.compile('decide|tell')
            if decidesre.search(remainingtext):
                threads[thread]['winnerdecides'] = remainingtext
                print 'prize'
            # Otherwise the choice 
            else:
                threads[thread]['winnermeans'] = remainingtext
                print 'means'
            print '\n'    
                

        # Count amount of samefags in body but not subject line 
        #oldre = re.compile('sage|saeg|samefag|saemfag')
        #print oldre.findall(subject)
        
        # Identify item to be rated
        
    '''    winnerre = re.compile('ending in')
    threads[thread]['evaluate'] = 'rate my | what does b think of my'
    threads[thread]['location'] = 'britfags /b/ritains'
    threads[thread]['return'] = 'Post ending in X | ending doubles '
    threads[thread]['winner'] = '(wins | gets Y | tells me | decides)' '''
    return threads

if __name__ == '__main__':
    threads = fourchan.opendatabase('threads.db')
    threads = fourchan.updatethreadindex('b',threads)
    threads = getthreadprops(threads)
    #threads = expandthreads(threads,threadid)
    
    #threadlist = sorted(threads.keys())
    #
    for thread in threads:
        timestring = time.strftime('%Y-%m-%d %H-%M-%S',threads[thread]['posttime'])
        print str(thread)+' '+threads[thread]['author'].ljust(12)+' '+threads[thread]['posttext']+timestring+'\n'

