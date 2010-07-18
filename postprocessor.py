#!/usr/bin/env python2.6
import re
from PIL import Image
import sys
sys.path.append('lib/python2.6/site-packages/pytesser')
import pytesser
import urllib2
import oembed

# Oembed + Oohembed
consumer = oembed.OEmbedConsumer()
consumer.addEndpoint(oembed.OEmbedEndpoint('http://oohembed.com/oohembed/', [
    'http://*.youtube.com/watch*',
    'http://www.vimeo.com/*',
    'http://www.vimeo.com/groups/*/videos/*',
    'http://*.twitpic.com/*',
    'http://*.metacafe.com/watch/*'
    ]))


def getembeddata(link):
    '''Get embed codes for links'''
    global consumer
    response = consumer.embed(link)
    data = response.getData()
    if data:
        return data
    else:
        return None            

def processlinks(posttext):
    '''Remove links from text'''
    linkre = re.compile(r"(http://[^ ]+)")
    embeds = []
    for link in linkre.findall(posttext):
        try:
            embed = getembeddata(link)
            if embed:
                embeds.append(embed)         
        except:
            pass
    originaltext = posttext
    posttext = linkre.sub('', posttext)
    return posttext,originaltext,embeds

def reducelargeimages(imagefile,imageconfig):
    '''Reduce images larger than a certain size'''
    myimage = Image.open(imagefile)
    width,height = myimage.size
    aspect = float(width) / float(height)
    maxwidth = imageconfig.as_int('maxwidth')
    maxheight = imageconfig.as_int('maxheight')
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

def makeintro(posttext,postingconfig):
    '''Reduce the headline text in very long posts if needed'''
    postwords = posttext.split()
    longpost = postingconfig.as_int('longpost')
    choplen = postingconfig.as_int('choplen')
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

def checktext(text,postingconfig,alerts):
    '''Check text is OK'''
    totalwords = len(text.split())
    uniquewords = len(set(text.split()))
    if uniquewords / totalwords < postingconfig.as_int('threshhold'):
        return False, alerts['lame']
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



