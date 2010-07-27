#!/usr/bin/env python2.6
import re
from PIL import Image
import sys
sys.path.append('lib/python2.6/site-packages/pytesser')
import pytesser
import urllib2
import oembed
from recaptcha.client import captcha
from akismet import Akismet
import pifilter
import logging
import time

def startakismet(akismetcfg):
    return Akismet(key=akismetcfg['apikey'], agent=akismetcfg['clientname'])

# Oembed + Oohembed
consumer = oembed.OEmbedConsumer()
consumer.addEndpoint(oembed.OEmbedEndpoint('http://api.embed.ly/oembed/api/v1', [
'http://www.5min.com/Video/*',
    'http://*.viddler.com/explore/*/videos/*',
    'http://qik.(ly|com)/video/*',
    'http://qik.(ly|com)/*',
    'http://www.hulu.com/watch/*',
    'http://*.revision3.com/*',
    'http://*nfb.ca/film/*',
    'http://*.dailymotion.com/video/*',
    'http://blip.tv/file/*',
    'http://*.scribd.com/doc/*',
    'http://*.movieclips.com/watch/*',
    'http://screenr.com/.+',
    'http://twitpic.com/*',
    'http://*.youtube.com/watch*',
    'http://yfrog.*/*',
    'http://*amazon.*/gp/product/*',
    'http://*amazon.*/*/dp/*',
    'http://*flickr.com/*',
    'http://www.vimeo.com/groups/*/videos/*',
    'http://www.vimeo.com/*',
    'http://tweetphoto.com/*',
    'http://www.collegehumor.com/video:*',
    'http://www.funnyordie.com/videos/*',
    'http://video.google.com/videoplay?*',
    'http://www.break.com/*/*',
    'http://www.slideshare.net/*/*',
    'http://www.ustream.tv/recorded/*',
    'http://www.ustream.tv/channel/*',
    'http://www.twitvid.com/*',
    'http://www.justin.tv/clip/*',
    'http://www.justin.tv/*',
    'http://vids.myspace.com/index.cfm\?fuseaction=vids.individual&videoid*',
    'http://www.metacafe.com/watch/*',
    'http://*crackle.com/c/*',
    'http://www.veoh.com/*/watch/*',
    'http://www.fancast.com/(tv|movies)/*/videos',
    'http://*imgur.com/*',
    'http://*.posterous.com/*',
    ]))


def getembeddata(link,config):
    '''Get embed codes for links'''
    global consumer
    options = {
        'maxwidth':config['images'].as_int('maxwidth'),
        'maxheight':config['images'].as_int('maxheight'),
    }
    response = consumer.embed(link, format='json', )
    data = response.getData()
    if data:
        return data
    else:
        return None            

def checkcaptcha(message,config):
    '''Check for captcha correct answer'''
    recaptcha_response = captcha.submit(message['challenge'], message['response'], config['captcha']['privkey'], message['ip'])
    if not recaptcha_response.is_valid:
        message['useralerts'].append(config['alerts']['nothuman'])
        message['nothuman'] = True   
    return message    

def checkspam(message,config,antispam):
    try:
        spam = antispam.comment_check(message['posttext'],data={
        'user_ip':message['ip'],
        'user_agent':message['useragent'],
        'referrer':message['referer'],
        'SERVER_ADDR':message['host']
    }, build_data=True, DEBUG=False)
    # Python Akismet library can fail on some types of unicode
    except UnicodeEncodeError:
        spam = True
    if spam:
        message['useralerts'].append(config['alerts']['spam'])
        message['spam'] = True     
    return message

def checkporn(message,config):  
    '''Check images for porn'''
    print message['localfile']
    print message
    print '------------------------------------'
    if message['localfile'] and config['images'].as_bool('enabled'):            
        #try:
        logging.info('Checking for porn...')
        time.sleep(1)
        response = pifilter.checkimage(
            message['localfile'],
            config['posting']['pifilter']['customerid'],
            aggressive=config['posting']['pifilter'].as_bool('aggressive')
            )
        #except:
        #    logging.error('Could not open pifilter URL')   
        #    return message        
        if response['result']:    
            logging.warn('image is porn.')
            message['useralerts'].append(config['alerts']['porn'])  
        else:
            logging.info('image is clean')        
    return message      

def checklinksandembeds(message,config):
    '''Remove links from text'''
    linkre = re.compile(r"(http://[^ ]+)")
    message['embeds'] = []
    for link in linkre.findall(message['posttext']):
        try:
            embed = getembeddata(link,config)
            if embed:
                message['embeds'].append(embed)         
        except:
            pass
    message['original'] = message['posttext']
    message['posttext'] = linkre.sub('', message['posttext'])
    return message

def saveimages(message,imageconfig):
    '''Save images for original posts'''                
    if imageconfig.as_bool('enabled'):
        if len(message['images']) < 1 and len(embeds) < 1:
            message['useralerts'].append(config['alerts']['noimage'])
            message['localfile'] = None
        else:
            # Save image data to local file
            # Set imageurl to be none as this isn't a message from an injector
            message['imageurl'] = None
            imagefile = message['images'][0]
            print 'Saving image: '+imagefile['filename']
            message['localfile'] = imageconfig['cachedir']+message['id']+'.'+imagefile['filename'].split('.')[-1]
            open(message['localfile'],'wb').write(imagefile['body'])
    return message      


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



