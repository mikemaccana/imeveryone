#!/usr/bin/env python
# Create a tree of comments.
# ['foo','bar','in','baz','woo','out','zam']

commentdb = {
    'foo':{
        'text':'foo',
        'comments':['bar','zam'],
    },

    'bar':{
        'text':'bar',
        'comments':['baz','woo'],
    },

    'baz':{
        'text':'baz',
        'comments':[],
    },

    'woo':{
        'text':'woo',
        'comments':['zug',],
    },

    'zam':{
        'text':'zam',
        'comments':[],
    },
    
    'zug':{
        'text':'zug',
        'comments':[],
    },
    
}

def buildtree(master):
    '''Return a consolidated tree of all comments'''
    tree = [master['text'],]
    def expandchildren(commenttoexpand):
        '''Expand commento expand'''
        for childcomment in commenttoexpand['comments']:
            tree.append(childcomment)
            if len(commentdb[childcomment]['comments']):    
                tree.append('in')
                expandchildren(commentdb[childcomment])
                tree.append('out')
    expandchildren(master)
    return tree
    
print buildtree(commentdb['foo'])    