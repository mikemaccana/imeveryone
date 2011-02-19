#!/usr/bin/env python2.6
import re
from PIL import Image, ImageOps
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
import urllib
import simplejson as json
from math import log
import rest

def startakismet(akismetcfg):
    return Akismet(key=akismetcfg['apikey'], agent=akismetcfg['clientname'])


def getembedcode(url, **kwargs):
    '''Oembed + Oohembed. Accept a URL and one of the arguments below, return dict with JSON.
    From sample on http://api.embed.ly/docs/oembed'''
    api_url = 'http://api.embed.ly/1/oembed?'
    ACCEPTED_ARGS = ['maxwidth', 'maxheight', 'format']
    params = {'url':url }

    for key, value in kwargs.items():
        if key not in ACCEPTED_ARGS:
            raise ValueError("Invalid Argument %s" % key)
        params[key] = value

    oembed_call = "%s%s" % (api_url, urllib.urlencode(params))
    result = json.loads(urllib2.urlopen(oembed_call).read())
    if 'html' in result:
        return result['html']
    else:    
        return None




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
    def __init__(self,config=None,antispam=None,_id=None,parentid=None,localfile=None,handler=None,messagedata=None,dehydrated=None):
        '''Create message'''
        

        if dehydrated: 
            # Recreate from a dict
            # See http://stackoverflow.com/questions/1305532/convert-python-dict-to-object
            self.__dict__.update(dehydrated)     
            return   
        
        # FIXME: combine
        if config is None:
            logging.error('Please provide config when creating new messages')
            return
        if antispam is None:
            logging.error('Please provide antispam info when creating new messages')
            return
        if _id is None:
            logging.error('Please provide _id info when creating new messages')
            return

        
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
        self.prettydate = self.getprettydate()
        
        self._id = _id        
        self.localfile = localfile
        self.preview, self.embedcode, self.headline, self.intro, self.thread, self.availavatars, self.likecount = None, None, None, None, None, None, None
        self.treecount = 0
        self.useralerts, self.comments = [], []
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
            self.useragent = handler.request.headers['User-Agent']
            # nginx real IP
            if 'X-Real-Ip' in handler.request.headers:
                self.ip = handler.request.headers['X-Real-Ip'] 
            else:
                self.ip = handler.request.remote_ip
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
            self.sessionid = handler.getorsetsessionid()

        else:   
            logging.error('No handler specified, and not dehydrated! Cannot create message')        
        
        # Are we an article or a reply
        self.parentid = parentid
        if self.istop():
            # We're a top-level article
            logging.info('Creating new article '+str(self._id))
            # Available avatars for sessions - copy of config.
            self.availavatars = config['posting']['avatars']
            logging.info('DEBUG:'+str(len(self.availavatars))+' created in this article')
            random.shuffle(self.availavatars)
            # Create dict of session / avatar matchings
            self.sessionavatars = {}

            # Thread is myself
            self.thread = self._id
            
            # Grab an avatar from my own list!
            self.sessionavatars[self.sessionid] = self.availavatars.pop()
            logging.info('DEBUG:'+str(len(self.availavatars))+' left in this article')
            
            # Currently only top level messages can have links, pictures or embeds
            # Process embeds (FIXME - must come before saveimages due to check for existing embeds in saveimages)
            self.checklinksandembeds(config)

            # If there's no local image file, save image from web url
            if self.localfile is None:
                self.saveimages(config)

            # Make preview            
            if self.localfile is not None and config['images'].as_bool('enabled'):
                self.makepreviewpic(self.localfile,config['images'])
                logging.info('Made preview picture.')
            else:    
                logging.warn('Not making image as local file not specified or images disabled.')
            logging.info('Preview pic is: '+str(self.preview))
            
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

                # Save parent now
                # Note that 'ancestor' (later) may be the same comment, so we need to save this now.
                logging.info('Adding comment '+str(self._id)+' as child of parent '+str(parentid))
                handler.application.dbconnect.messages.save(parent)

                # Take an avatar from the sessions avatar/dict in ancestor
                ancestor = handler.application.dbconnect.messages.find_one({'_id':int(self.thread)})
                if self.sessionid not in ancestor['sessionavatars']:
                    # This is the first time this sessionid has commented
                    # Grab an available avatar from the ancestor to use for this sessionid
                    myavatar = ancestor['availavatars'].pop()
                    logging.info('DEBUG:'+str(len(ancestor['availavatars']))+' left in the parent')
                    ancestor['sessionavatars'][self.sessionid] = myavatar
                    logging.info('Sessionid '+self.sessionid+' has commented in this thread for the first time. Assigned '+myavatar+' for message '+str(self._id))
                    ancestor['treecount'] += 1
                    handler.application.dbconnect.messages.save(ancestor)
                    # Here ancestor is saved to db with correct info, but it gets overridden later                    
                else: 
                    logging.info('This sessionid '+self.sessionid+' has commented in this thread before, using existing avatar '+ancestor['sessionavatars'][self.sessionid])        
                                
            else:    
                logging.warn('Error! Could not find parent with parentid '+str(parentid)+' in DB')
                
        
        
        # Validate the users input    
        #self.getimagetext(self.localfile,config['images'])
        self.checktext(config)
        self.checkcaptcha(config)
        self.checkspam(config,antispam)
        self.checkporn(config)
        self.makeintro(config['posting'])
        
        # Override existing links
        self.link = '/discuss/'+str(self._id)
    
    def saveimages(self,config):
        '''Save images for original posts'''
        if config['images'].as_bool('enabled'):
            if self.imagedata is None and self.embedcode is None:
                self.useralerts.append(config['alerts']['noimageorembed'])
            elif self.imagedata is not None:
                # Save image data to local file
                imagefile = self.imagedata[0]
                logging.info('Saving image: '+imagefile['filename'])
                self.localfile = config['images']['cachedir']+str(self._id)+'.'+imagefile['filename'].split('.')[-1]
                open(self.localfile,'wb').write(imagefile['body'])
                # Set self.imagedata to None now we've saved our image data to a file.
                # We need this as leaving the unencoded messagedata around will screw mongo up.
                self.imagedata = None
            else:
                # We have no image data as we're an embed only post
                return    
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
            logging.info('Small image, using existing pic at: '+imagefile)
            self.preview = imagefile
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
        postwords = self.posttext.strip()
        wordlist = postwords.split()
        uniquewords = set(wordlist)
        # Zero sized posts
        if len(postwords) == 0:
            self.useralerts.append(config['alerts']['zero'])
        # Overlong posts    
        elif len(wordlist) > config['posting'].as_float('longpost'):     
            self.useralerts.append(config['alerts']['overlong'])
        else:
            # Check text isn't full of dupes
            totalwords = len(wordlist)
            totaluniquewords = len(uniquewords)
            # Float so our answer is a float 
            if totaluniquewords / float(totalwords) < config['posting'].as_float('threshhold'):
                self.useralerts.append(config['alerts']['notunique'])
            # Check post doesnt mention banned words
            for bannedword in config['posting']['bannedwords']:
                if bannedword in uniquewords:
                    self.useralerts.append(config['alerts']['bannedwords'])
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
        if config['posting']['akismet'].as_bool('enabled'):
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
        maxwidth = config['images'].as_int('maxwidth')
        maxheight = config['images'].as_int('maxheight')
        linkre = re.compile(r"(http://[^ ]+)")
        for link in linkre.findall(self.posttext):
            # lopp through links gettng embeds
            logging.info('Getting embed data for link: '+link)
            try:
                self.embedcode = getembedcode(link, maxwidth=maxwidth, maxheight=maxheight)
                if self.embedcode:
                    logging.info('Embed data found!')
                else:
                    logging.info('Embed data not found!')    
            except:
                logging.warn('Getting embed data for link failed - most likely embedly 404')
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
                    if config['images']['adultaction'] in ['gray','grey']:
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
        postwords = self.posttext.replace('\n',' NEWLINE ').split()
        leeway = postingconfig.as_int('leeway')
        choplen = postingconfig.as_int('choplen')
        longpost = postingconfig.as_int('longpost')
        if len(postwords) < leeway:
            self.headline = self.posttext
        else:
            self.headline = ' '.join(postwords[:choplen]).replace('NEWLINE','')+'...'
            self.intro = '...'+' '.join(postwords[choplen:longpost])
        return
            
    def getcountry(self,ip):
        '''Get user country - currently unused'''
        gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
        print gi.country_code_by_addr(ip)
        
    def getposttimedt(self):
        '''Return a datetime version of 'posttime' style dictionary '''
        return datetime(self.posttime['year'], self.posttime['month'], self.posttime['day'], self.posttime['hour'], self.posttime['minute'], self.posttime['second'])   
    
    def getprettydate(self):
        '''Return pretty printed date, with suffixes (st, nd) and no leading zeros'''
        posttimedt = self.getposttimedt()
        prettytime = str(int(posttimedt.strftime("%I")))+':'+posttimedt.strftime("%M %p")
        daysuffixes = ['st','nd','rd'] + 17*['th'] + ['st','nd','rd'] + 7*['th'] + ['st'] 
        prettydate = str(int(posttimedt.strftime("%d")))+daysuffixes[int(posttimedt.strftime("%d"))-1]+posttimedt.strftime(" %B %Y")
        return prettytime+' '+prettydate   
        
    def getrank(self):
        '''Get rank for message. Based on http://amix.dk/blog/post/19574 (Reddit style)
        '''
        order = log(max(abs(self.score), 1), 10)
        sign = 1 if self.score > 0 else -1 if self.score < 0 else 0
        seconds =  time.mktime(self.getposttimedt().timetuple()) - 1134028003
        rank = round(order + sign * seconds / 45000, 7)
        return rank

    def updatetreecount(self,db):
        '''Get total of children and grandchildren'''
        #logging.info('Updating tree count on '+str(self._id))
        
        def addchildrentototal(item):
            '''Add children of a post recursively'''
            # Only count down level posts, not top level 
            if item.parentid:
                self.treecount += 1
            if len(item.comments) == 0:
                return
            else:
                for commentid in item.comments:
                    commentdoc = db.messages.find_one(commentid)
                    # Some docs have been deleted from the DB
                    if commentdoc is not None:
                        comment = Message(dehydrated=commentdoc)
                        addchildrentototal(comment)
    
        self.treecount = 0
        addchildrentototal(self)
        return
    
    def getlikecount(self):
        '''Return count of Facebook likes for a target URL'''
        targeturl = 'http://imeveryone.com/discuss/'+str(self._id)
        endpoint = 'https://api.facebook.com'
        page = '/method/fql.query'
        querydict = {
            'query':'''SELECT total_count FROM link_stat WHERE url="'''+targeturl+'''"''',
            'format':'json',
        }

        fqlhelper = rest.RESTHelper(endpoint='https://api.facebook.com')
        queryresult = fqlhelper.get(page,querydict=querydict,usejson=True)
        self.likecount = queryresult[0]['total_count']
        return
    
    def istop(self):
        '''Check if message is toplevel'''
        return not self.parentid
