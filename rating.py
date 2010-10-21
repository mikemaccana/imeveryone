

def calculate_score(votes, item_hour_age, gravity=1.8):
    '''http://amix.dk/blog/post/19574'''
    return (votes - 1) / pow((item_hour_age+2), gravity)