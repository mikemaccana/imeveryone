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
import random
from datetime import datetime
#import ipdb

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
    def __init__(self,config,antispam,_id,parentid=None,localfile=None,handler=None,messagedata=None):
        '''Create message based on body of PUT form data'''
        
        # Info that's common across all messages
        # Note we store a list as it's JSON serializable. A native datetime object isn't.
        now = datetime.utcnow()
        self.posttime = {
            'year':now.year, 
            'month':now.month, 
            'day':now.day, 
            'hour':now.hour, 
            'minute':now.minute, 
            'second':now.second
        }
        
        self._id = _id        
        self.localfile = localfile
        self.preview, self.headline, self.intro, self.thread, self.availavatars = None, None, None, None, None
        self.useralerts, self.comments, self.embeds = [], [], []
        self.score = 1
        
        if messagedata:
            # Preconfigured data from injector
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
            self.sessionid = '1'
        elif handler:
            # Create message from handler data
            self.author = 'Anonymous'
            self.posttext = handler.get_argument('posttext')
            self.ip = handler.request.remote_ip
            self.useragent = handler.request.headers['User-Agent']
            self.referer = handler.request.headers['Referer']
            self.host = handler.request.headers['Host']
            # Add capctha info if enabled
            if handler.application.config['captcha'].as_bool('enabled'):
                self.challenge = handler.get_argument('recaptcha_challenge_field')
                self.response = handler.get_argument('recaptcha_response_field')
            else:
                self.challenge,self.response = None, None
            # Add image data if enabled
            if 'image' in handler.request.files:
                self.imagedata = handler.request.files['image']
            else:
                self.imagedata = None    
            self.sessionid = handler.get_cookie('sessionid')    
        else:   
            logging.warn('No handler and no messagedata specified!')        
        
        # Are we an article or a reply
        self.parentid = parentid
        if not parentid:
            # We're a top-level article
            logging.info('Creating new article '+str(self._id))
            # Available avatars for sessions - copy of config.
            self.availavatars = list(config['posting']['avatars'])
            random.shuffle(self.availavatars)
            # Create dict of session / avatar matchings
            self.sessionavatars = {}

            # Thread is myself
            self.thread = self._id
            
            # Grab an avatar from my own list!
            self.sessionavatars[self.sessionid] = self.availavatars.pop()
            self.avatar = self.sessionavatars[self.sessionid]
            
        else:
            # We're a reply
            logging.info('Creating new reply '+str(self._id))   

            # Add our new comment ID as a child of parent, increment parents score            
            parent = handler.application.dbconnect.messages.find_one({'_id':int(parentid)})
            if parentid:
                # We're a reply
                parent['comments'].append(_id)

                # Increment parent score for message
                parent['score'] += config['scoring'].as_int('comment')
                
                # Every reply copies its 'thread' from its parent, which points back to the original post 
                self.thread = parent['thread']
                logging.info('Thread is '+str(self.thread))

                # Take an avatar from the sessions avatar/dict in ancestor
                ancestor = handler.application.dbconnect.messages.find_one({'_id':int(self.thread)})
                if self.sessionid not in ancestor['sessionavatars']:
                    # This is the first time this sessionid has commented
                    ancestor['sessionavatars'][self.sessionid] = ancestor['availavatars'].pop()
                    handler.application.dbconnect.messages.save(ancestor)
                self.avatar = ancestor['sessionavatars'][self.sessionid]
                logging.info('Assigned new avatar: '+self.avatar+' for message '+str(self._id))    
                                
                logging.info('Adding comment '+str(self._id)+' as child of parent '+str(parentid))
                handler.application.dbconnect.messages.save(parent)
                                
            else:    
                logging.warn('Error! Could not find parent with parentid '+str(parentid)+' in DB')
                

        # If there's no local image file, save image from web url
        if self.localfile is None:
            self.saveimages(config)
        
        # Make preview            
        if self.localfile is not None and config['images'].as_bool('enabled'):
            self.makepreviewpic(self.localfile,config['images'])
        
        # Validate the users input    
        #self.getimagetext(self.localfile,config['images'])
        self.checktext(config)
        self.checkcaptcha(config)
        self.checkspam(config,antispam)
        self.checklinksandembeds(config)
        self.checkporn(config)
        self.makeintro(config['posting'])
        
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
        
    def makeintro(self,postingconfig):
        '''Reduce the headline text in very long posts if needed'''
        postwords = self.posttext.split()
        longpost = postingconfig.as_int('longpost')
        choplen = postingconfig.as_int('choplen')
        longpost = postingconfig.as_int('longpost')
        if len(postwords) < longpost:
            self.headline = self.posttext
        else:
            self.headline = ' '.join(postwords[:choplen])+'...'
            self.intro = '...'+' '.join(postwords[choplen:longpost])
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
        
    def getposttimedt(self, datedict):
        '''Return a datetime version of 'posttime' style dictionary '''
        return datetime(datedict['year'], datedict['month'], datedict['day'], datedict['hour'], datedict['minute'], datedict['second'])   

    def getrank(self, views, hoursold, GRAVITY=1.8):
        '''Get rank for message. Based on http://amix.dk/blog/post/19574'''
        posttimedt = getposttimedt()
        age = posttimedt - datetime.utcnow()
        hoursold = (age.days * 24) + age.seconds / 3600
        
        rank = (self.score - 1) / pow((hoursold+2), GRAVITY)
        return rank  
    
    def getprettydate(self, datedict):
        '''Return pretty printed date'''
        posttimedt = self.getposttimedt(datedict)
        daysuffixes = ['st','nd','rd'] + 17*['th'] + ['st','nd','rd'] + 7*['th'] + ['st'] 
        prettystring = posttimedt.strftime("%I:%M %p %d")+daysuffixes[int(posttimedt.strftime("%d"))]+posttimedt.strftime(" %B %Y")
        return prettystring
        
           
