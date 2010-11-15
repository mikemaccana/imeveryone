#!/usr/bin/env python2.6
import re
from PIL import Image, ImageOps
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
import uuid
from time import gmtime, strftime


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




def buildtree(master,messagedb):
    '''Recieve a message, return a consolidated tree of all comments'''
    tree = []
    def expandchildren(commenttoexpand):
        '''Expand child comments, adding to tree'''
        childcommentids = commenttoexpand['comments']
        for childcommentid in childcommentids:
            childcomment = messagedb.find_one({'_id':childcommentid})         
            # Make sure DB actually returned some comments
            if childcomment is not None:
                tree.append(childcomment)
                if len(childcomment['comments']):    
                    tree.append('in')
                    expandchildren(childcomment)
                    tree.append('out')
    expandchildren(master)
    return tree

class Message(object):
    '''Submitted message'''
    def __init__(self,messagedata,config,antispam,_id,localfile=None):
        '''Create message based on body of PUT form data'''
        self.posttime = messagedata['posttime']
        self._id = _id
        
        self.localfile = localfile
        self.preview = None
        
        self.author = messagedata['author']
        self.posttext = messagedata['posttext']
        self.challenge = messagedata['challenge']
        self.response = messagedata['response']
        self.ip = messagedata['ip']
        self.useragent = messagedata['useragent']
        self.referer = messagedata['referer']
        self.imagedata = messagedata['imagedata']
        self.host = messagedata['host']
        self.article = messagedata['article']
        self.useralerts = []
        self.intro = None
        self.comments = []
        # threadid, is only for content getters , can remove later
        self.threadid = None
        self.embeds = []
        self.intro = None
        self.score = 1
        
        
        # If there's no local image file, save image from web url
        if self.localfile is None:
            self.saveimages(config)
        
        # Make preview            
        if self.localfile is not None and config['images'].as_bool('enabled'):
            self.makepreviewpic(self.localfile,config['images'])
            
        #self.getimagetext(self.localfile,config['images'])
        
        self.checktext(config)
        self.checkcaptcha(config)
        self.checkspam(config,antispam)
        self.checklinksandembeds(config)
        self.checkporn(config)
        self.makeintro(self.posttext,config['posting'])

        
        # Override existing links
        self.link = '/discuss/'+str(self._id)
    
    def saveimages(self,config):
        '''Save images for original posts'''
        if config['images'].as_bool('enabled'):
            if self.imagedata is None and len(self.embeds) < 1:
                self.useralerts.append(config['alerts']['noimage'])
            else:
                # Save image data to local file
                imagefile = self.imagedata[0]
                logging.info('Saving image: '+imagefile['filename'])
                self.localfile = config['images']['cachedir']+self._id+'.'+imagefile['filename'].split('.')[-1]
                open(self.localfile,'wb').write(imagefile['body'])
                # Set self.imagedata to None now we've saved our image data
                self.imagedata = None
        return
    
    def makepreviewpic(self,imagefile,imageconfig):
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
            newfilename = imagefile.replace('cache','thumbs').split('.')[-2]+'_preview.'+imagefile.split('.')[-1]
            try:
                myimage.save(newfilename)
                logging.info('Saved preview pic to: '+newfilename)
                self.preview = newfilename
            except:
                pass
            return
            
    
    def checktext(self,config):
        '''Ensure they're ranting enough, but not too much!'''
        # Zero sized posts
        if len(self.posttext.strip()) == 0:
            self.useralerts.append(config['alerts']['zero'])
        else:
            # Check text isn't full of dupes
            totalwords = len(self.posttext.split())
            uniquewords = len(set(self.posttext.split()))
            if uniquewords / totalwords < config['posting'].as_float('threshhold'):
                self.useralerts.append(config['alerts']['lame'])
        return    
    
    def checkcaptcha(self,config):
        '''Check for correct CAPTCHA answer'''
        if config['captcha'].as_bool('enabled'):
            recaptcha_response = captcha.submit(self.challenge, self.response, config['captcha']['privkey'], self.ip)
            if not recaptcha_response.is_valid:
                self.useralerts.append(config['alerts']['nothuman'])
                self.nothuman = True
        return

    def checkspam(self,config,antispam):
        '''Check for spam using Akismet'''
        try:
            spam = antispam.comment_check(self.posttext,data = {
            'user_ip':self.ip,
            'user_agent':self.useragent,
            'referrer':self.referer,
            'SERVER_ADDR':self.host
        }, build_data=True, DEBUG=False)
        # Python Akismet library can fail on some types of unicode
        except UnicodeEncodeError:
            spam = True
        if spam:
            self.useralerts.append(config['alerts']['spam'])
            self.spam = True
        return
    
    def checklinksandembeds(self,config):
        '''Process any links in the text'''
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
        linkre = re.compile(r"(http://[^ ]+)")
        self.embeds = []
        for link in linkre.findall(self.posttext):
            try:
                embed = getembeddata(link,config)
                if embed:
                    message.embeds.append(embed)
            except:
                pass
        self.original = self.posttext
        self.posttext = linkre.sub('', self.posttext)
        return
    
    def checkporn(self,config):
        '''Check images for porn'''
        def savegrayscale(imagefile):
            '''Convert image to greyscale and save'''
            adultimage = Image.open(imagefile)
            adultimage = ImageOps.grayscale(adultimage)
            adultimage.save(imagefile)
            return
        if self.localfile and config['images'].as_bool('enabled') and config['images'].as_bool('adult'):
            count = 1
            response = {}
            while count < 3:
                try:
                    logging.info('Checking for porn, try '+str(count))
                    response = pifilter.checkimage(
                        self.localfile,
                        config['posting']['pifilter']['customerid'],
                        aggressive = config['posting']['pifilter'].as_bool('aggressive')
                        )
                    break
                except:
                    logging.error('Could not open pifilter URL')
                    time.sleep(5)
                count = count+1
            if 'result' in response:
                if response['result']:
                    logging.warn('message submission '+str(self._id)+' with image '+self.localfile+' is porn.')
                    # Make a greyscale version and use that instead
                    if config['images']['adultaction'] == 'gray' or config['images']['adultaction'] == 'grey':
                        savegrayscale(self.localfile)
                        logging.info('Saving greyscale version...')
                    else:
                        self.useralerts.append(config['alerts']['porn'])
                else:
                    logging.info('image is clean')
            else:
                # No response from pifilter
                pass
        return
        
    def makeintro(self,posttext,postingconfig):
        '''Reduce the headline text in very long posts if needed'''
        postwords = posttext.split()
        longpost = postingconfig.as_int('longpost')
        choplen = postingconfig.as_int('choplen')
        if len(postwords) < longpost:
            return
        else:
            self.posttext = ' '.join(postwords[:choplen])+'...'
            self.intro = '...'+' '.join(postwords[choplen:])
            return
            
    def getcountry(self,ip):
        '''Get user country - currently unused'''
        gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
        print gi.country_code_by_addr(ip)

    def getimagetext(self,imagefile):
        '''Recieve an image, return the text'''
        if config['images'].as_bool('enabled') and message.localfile and config['images']['ocr']:
            # PIL is flaky.
            try:
                image = Image.open(imagefile)
                # Convert to black and white
                if image.mode != "L":
                    image = image.convert("L")
                # Now let's do this shit
                imagetext = pytesser.image_to_string(image)
                self.imagetext = None
                return
            except:
                pass
        return 

    def getscore(views, hoursold, gravity=1.8):
        '''Get score for moessage. Based on
        http://amix.dk/blog/post/19574'''
        return (views - 1) / pow((hoursold+2), gravity)







