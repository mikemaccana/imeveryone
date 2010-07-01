#!/usr/bin/env python2.6
'''import httplib
import GeoIP
import pickle'''
import re
from PIL import Image
import sys
sys.path.append('pytesser')
import pytesser
'''
import time
'''
#import ipdb
import urllib2
import oembed

consumer = oembed.OEmbedConsumer()

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


* GeoIP and match for countryfags
NLTK collocations
nltk relations

'''
def texttolinks(string):
    '''Make clickable links from text'''
    linkre = re.compile(r"(http://[^ ]+)")
    linkstring = linkre.sub(r'<a href="\1">\1</a>', string)
    return linkstring

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
    try:
        openurl = urllib2.urlopen(imageurl)
    except:
        return None    
    savedfile = open(cachedfilename,'wb')
    savedfile.write(openurl.read())    
    return cachedfilename

def makeintro(posttext):
    '''Reduce the headline text in very long posts if needed'''
    postwords = posttext.split()
    longpost = 40
    choplen = 20
    if len(postwords) < longpost:
        return posttext,None 
    else:
        posttext = ' '.join(postwords[:choplen])+'...'
        intro = '...'+' '.join(postwords[choplen:]) 
        return (posttext, intro)    
    
def getcountry(ip):
    '''Get user country - currently unused'''
    gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
    print gi.country_code_by_addr(ip)    

def checktext(text):
    '''Check text is OK'''
    threshhold = 0.8
    totalwords = len(text.split())
    uniquewords = len(set(text.split()))
    if uniquewords / totalwords < threshhold:
        print 'woo'
        return False, 'Looks like you accidentally triggered our lameness filter. Sorry! Try changing a few words.'
    else:    
        return True, ''

def getimagetext(imagefile):
    '''Recieve an image, return the text'''
    # PIL is flaky.
    try:
        image = Image.open(imagefile)
        # Convert to black and white
        if image.mode != "L":
            image = image.convert("L")
        # Now let's do this shit    
        imagetext = pytesser.image_to_string(image)
        return imagetext
    except:
        return None    



