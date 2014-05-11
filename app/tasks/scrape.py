# -*- coding: utf-8 -*-

from __future__ import division
import logging, os, sys, pickle, pdb
from celery.signals import worker_init
from celery import group, chord, subtask

from socialscraper.twitter import TwitterScraper
from socialscraper.facebook import FacebookScraper

from sqlalchemy import or_, and_

from datetime import datetime

from app.tasks import celery
from app.models import db, FacebookUser, FacebookPage, Transaction
from ..utils import convert_result

logger = logging.getLogger(__name__)

"""

Need to fix up this code later.

Essentially, the requests session is based on a urllib3 pool which gets full if we 
try to do thousands of requests from the same session. Thus we're no longer going with
a module level facebook_scraper.

Instead we instantiate a scraper to login to Facebook and serialize the session object.

We keep this serialized_browser at the module level and instantiate a new FacebookScraper
in each task that uses the serialized_browser as a parameter.

I should remove code that deals with pickling stuff from socialscraper. Instead unpickle
here and pass the real objects around in the library.

If I can figure out those urllib pool problems properly I won't have to do any of this stuff.

Or perhaps in the library itself I create a new session object everytime I want to do anything?
Seems like a lot of overhead because I'd need to deepcopy the logged_in cookiejar each time.

---------------------------------------

The same stuff applies for the GraphAPI although its probably overkill. In order to prevent
stale user access tokens, I run the init_api method to test whether the access token works.

I only test it in worker_init and assume it'll continue to work throughout the rest of the code.

Although, these tokens are technically for like an hour a pop so that might not be the best assumption.

"""

@worker_init.connect
def worker_init(*args, **kwargs):

    # global facebook_scraper

    if not os.path.isfile('facebook_scraper.pickle'):
        facebook_scraper = FacebookScraper(scraper_type='nograph')
        facebook_scraper.add_user(email=os.getenv('FACEBOOK_EMAIL'), password=os.getenv('FACEBOOK_PASSWORD'))
        facebook_scraper.pick_random_user()
        facebook_scraper.login()
        facebook_scraper.init_api()
        pickle.dump(facebook_scraper, open('facebook_scraper.pickle', 'wb'))
    # else:
    #     facebook_scraper = pickle.load(open( "facebook_scraper.pickle", "rb" ))

@celery.task()
def get_uids(limit=None): 
    return filter(lambda uid: uid, map(lambda user: user.uid, FacebookUser.query.limit(limit).all()))

@celery.task()
def get_usernames(limit=None, get='all'): 

    if get == 'all':
        return filter(lambda username: username, map(lambda user: user.username, FacebookUser.query.limit(limit).all()))
    elif get == 'empty':
        return filter(lambda username: username, 
            map(lambda user: user.username, 
                FacebookUser.query.filter_by(
                    currentcity=None, 
                    hometown=None, 
                    college=None, 
                    highschool=None, 
                    employer=None, 
                    birthday=None
                ).limit(limit).all()
                )
            )
    elif get == 'nonempty_or':
        return filter(lambda username: username, 
            map(lambda user: user.username, 
                FacebookUser.query.filter(
                    or_(
                        FacebookUser.currentcity.isnot(None), 
                        FacebookUser.hometown.isnot(None), 
                        FacebookUser.college.isnot(None), 
                        FacebookUser.highschool.isnot(None), 
                        FacebookUser.employer.isnot(None), 
                        FacebookUser.birthday.isnot(None), 
                    )
                ).limit(limit).all()
                )
            )
    elif get == 'nonempty_and':
        return filter(lambda username: username, 
            map(lambda user: user.username, 
                FacebookUser.query.filter(
                    and_(
                        FacebookUser.currentcity.isnot(None), 
                        FacebookUser.hometown.isnot(None), 
                        FacebookUser.college.isnot(None), 
                        FacebookUser.highschool.isnot(None), 
                        FacebookUser.employer.isnot(None), 
                        FacebookUser.birthday.isnot(None), 
                    )
                ).limit(limit).all()
                )
            )
    elif get == 'haslikes':
        return filter( username: username,
                map(lambda user: user.username,
                    FacebookUser.query.filter(FacebookUser.pages != None).limit(limit).all()
                )
            )
    elif get == 'nolikes':
        return filter( username: username,
                map(lambda user: user.username,
                    FacebookUser.query.filter(FacebookUser.pages == None).limit(limit).all()
                )
            )

@celery.task()
def get_unscraped_usernames(limit=None):
    return 

@celery.task()
def get_pages(limit=None): 
    return map(lambda page: page.username, FacebookPage.query.limit(limit).all())

# change scraper_type from graphapi to nograph to see different results
@celery.task()
def get_about(username):

    facebook_scraper = pickle.load(open( "facebook_scraper.pickle", "rb" ))
    try:
        result = facebook_scraper.get_about(username)
        user = FacebookUser.query.filter_by(username=username).first()

        if not user:
            user = FacebookUser()
            convert_result(user, result)
            user.created_at = datetime.now()
            db.session.add(user)
            transact_type = 'create'
        else:
            convert_result(user, result)
            transact_type = 'update'

        user.updated_at = datetime.now()
    except Exception as e:
        transaction = Transaction(
            timestamp = datetime.utcnow(),
            transact_type = 'error',
            func = 'get_about(%s)' % username,
            ref = "%s: %s" % (str(e.errno), e.strerror)
            )
        if 'result' in locals():
            transaction.data = str(result)
            transaction.ref = "%s.%s" % (FacebookUser.__tablename__, str(result.uid))

        db.session.add(transaction)
        db.session.commit()
        return


    ## Scrape Transaction

    transact_type = 'create' if len(FacebookUser.query.filter_by(uid=result.uid).all()) == 0 else 'update'
    
    transaction = Transaction(
        timestamp = datetime.utcnow(),
        transact_type = transact_type,
        ref = "%s.%s" % (FacebookUser.__tablename__, str(result.uid)),
        func = 'get_about(%s)' % username,
        data = str(result)
    )

    db.session.add(transaction)
    db.session.commit()

    return result

@celery.task
def get_likes(username):
    
    facebook_scraper = pickle.load(open( "facebook_scraper.pickle", "rb" ))
    facebook_scraper.scraper_type = "graphsearch"

    user = FacebookUser.query.filter_by(username=username).first()

    if not user: raise Exception("scrape the dude's about information first plz")

    results = []

    for result in facebook_scraper.graph_search(username, "pages-liked"):
        try:
            page = FacebookPage.query.filter_by(username=result.username).first()

            if not page:
                page = FacebookPage()
                convert_result(page, result)
                page.created_at = datetime.now()
                db.session.add(page)
                transact_type = 'create'
            else:
                convert_result(page, result)
                transact_type = 'update'

        except Exception as e:
            transaction = Transaction(
                timestamp = datetime.utcnow(),
                transact_type = 'error',
                func = 'get_about(%s)' % username,
                ref = "%s: %s" % (str(e.errno), e.strerror)
                )
            if 'result' in locals():
                transaction.data = str(result)
                
            db.session.add(transaction)
            db.session.commit()
        return

        page.updated_at = datetime.now()
        page.users.append(user)

        ## Scrape Transaction
        
        transaction = Transaction(
            timestamp = datetime.utcnow(),
            transact_type = transact_type,
            ref = "%s.%s" % (FacebookPage.__tablename__, str(result.page_id)),
            func = 'get_likes(%s)' % username,
            data = str(result)
        )

        db.session.add(transaction)        
        db.session.commit()

        results.append(result)
        print result
        logger.info(result)

    return results

@celery.task()
def dmap(it, callback):
    callback = subtask(callback)
    return group(callback.clone([arg,]) for arg in it)()

# http://stackoverflow.com/questions/13271056/how-to-chain-a-celery-task-that-returns-a-list-into-a-group
# process_list = (scrape.get_users.s(10) | scrape.dmap.s(scrape.get_about.s()))
