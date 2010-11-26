#!/usr/bin/env python
import urllib
import urllib2
import simplejson as json





if __name__ == "__main__":
    urls = ["http://vimeo.com/9503416",
            "http://plixi.com/p/12870944"]

    for url in urls:
        print "\n\nurl: %s\n" % url
        print get_oembed(url)
        print "\n\n"