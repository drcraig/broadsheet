import argparse
from datetime import datetime, date, time
import itertools
from multiprocessing.dummy import Pool as ThreadPool
import re
import sys
from time import mktime
from urlparse import urlparse

import dateparser
from jinja2 import Environment, FileSystemLoader
import yaml

import ssl
if hasattr(ssl, '_create_unverified_context'):
        ssl._create_default_https_context = ssl._create_unverified_context

import feedparser
import requests

USER_AGENT = "Broadsheet/0.1 +http://dancraig.net/broadsheet/"
feedparser.USER_AGENT = USER_AGENT
feedparser._HTMLSanitizer.acceptable_elements.add('iframe')


def crawl_feed(url, feed_title=None):
    """Take a feed, return articles"""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT})
        print url, response
        if not response.ok:
            return []
        result = feedparser.parse(response.text)

        if feed_title:
            result.feed['title'] = feed_title

        entries = [entry for entry in result.entries]
        for entry in entries:
            entry['feed'] = result.feed
        return entries
    except Exception as e:
        print e
        return []


def key_by_date(article):
    """Key function to sort articles by date"""
    return article.get('published_parsed') or article.get('updated_parsed')


def listify(articles, title=None):
    """Take a list of articles, and create a new list of articles composed
    of lists of links to the original articles"""
    if not articles:
        return {}

    most_recent_article = sorted(articles, key=key_by_date, reverse=True)[0]

    return [feedparser.FeedParserDict({
        'feed': most_recent_article.feed,
        'title': '',
        'links': most_recent_article.feed.get('links', []) + [
            {
                'href': article.get('link'),
                'rel': 'related',
                'type': 'text/html',
                'title': article.get('title')
            } for article in articles],
        'published': most_recent_article.get('published'),
        'published_parsed': most_recent_article.get('published_parsed'),
        'updated': most_recent_article.get('updated'),
        'updated_parsed': most_recent_article.get('updated_parsed'),
    })]


def truncate(articles, max_num=5):
    return articles[:max_num]


def article_timestamp(article):
    timestruct = article.get('published_parsed') or article.get('updated_parsed')
    if not timestruct:
        return None
    return datetime.fromtimestamp(mktime(timestruct))


def article_date(article):
    timestamp = article_timestamp(article)
    if not timestamp:
        return None
    return timestamp.date()


def daily_digest(articles):
    '''Transform  articles into daily digests'''
    articles = sorted(articles, key=article_date, reverse=True)
    digests = []
    for _, articles_that_date in itertools.groupby(articles, article_date):
        digests.extend(listify(list(articles_that_date)))
    return digests


def filter_by_datetime_range(articles, start=None, end=None):
    '''Filter articles within a start and stop range.

    Start and stop could be either dates or datetimes. If dates, start will
    be assumed to be the start of the day and end will be the end of the day'''
    if type(start) is date:
        start = datetime.combine(start, time.min)
    if type(end) is date:
        end = datetime.combine(end, time.min)

    for article in articles:
        timestamp = article_timestamp(article)
        if not timestamp:
            yield article
            continue
        if start and timestamp < start:
            continue
        if end and timestamp > end:
            continue
        yield article


def daily(articles, day=None):
    day = day or date.today()
    return filter_by_datetime_range(articles, start=day)


def pre(articles):
    for article in articles:
        article.preformatted = True
        yield article


def apod_fix_pubdate(articles):
    """Astronomy Picture of the Date (http://apod.nasa.gov/apod/) does not put dates
    in the articles, but can be derived from the URL"""
    for article in articles:
        url = urlparse(article['link'])
        if url.path == '/apod/astropix.html':
            article['published_parsed'] = date.today().timetuple()
        elif re.match(r'/apod/ap\d{6}.html', url.path):
            article['published_parsed'] = datetime.strptime(url.path, '/apod/ap%y%m%d.html').timetuple()
        yield article


def nws_afd_synopsis_only(articles):
    """NWS Area Forecast Discsussions are long. Only get the synposis"""
    for article in articles:
        article['description'] = article['description'].split(r'&&')[0]
        yield article


def process_feed(url, alternate_title=None, post_procs=None):
    post_procs = post_procs or []
    articles = crawl_feed(url, feed_title=alternate_title)
    for post_processor in post_procs:
        articles = list(globals()[post_processor](articles))
    return articles


def process_feed_mapper(args):
    return process_feed(*args)


def process_subscriptions(subscriptions):
    process_feed_args = [(sub['url'], sub.get('title'), sub.get('post_processors', []))
                         for sub in subscriptions]
    pool = ThreadPool(20)
    results = pool.map(process_feed_mapper, process_feed_args)
    all_articles = list(itertools.chain(*results))
    all_articles.sort(key=key_by_date, reverse=True)
    return list(all_articles)


def time_struct_to_datetime(time_struct):
    return datetime(*time_struct[:6])


def render(articles, timestamp=None, previous=None):
    timestamp = timestamp or datetime.now()
    env = Environment(loader=FileSystemLoader('broadsheet/templates'),
                      extensions=['jinja2.ext.with_'])
    env.filters['datetime'] = time_struct_to_datetime

    return env.get_template('index.html').render(articles=articles,
                                                 timestamp=timestamp,
                                                 previous=previous)


def main(subscriptions, start=None, stop=None, previous=None):
    all_articles = process_subscriptions(subscriptions)
    all_articles = filter_by_datetime_range(all_articles, start=start)
    return render(articles=all_articles, previous=previous)


def datetime_type(string):
    if not string:
        return None
    dt = dateparser.parse(string)
    if isinstance(dt, datetime):
        return dt
    raise argparse.ArgumentTypeError('%s did not parse as a datetime' % string)


def cli():
    parser = argparse.ArgumentParser(description="Generate a file of feeds")
    parser.add_argument('-s', '--start', help='Start date', type=datetime_type, default=None)
    parser.add_argument('-p', '--previous', help='Previous date', type=datetime_type, default=None)
    # parser.add_argument('-z', '--time-zone', help='Time zone', default='US/Pacific')
    parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'),
                        default=sys.stdout)
    parser.add_argument('subscriptions', nargs='?', type=argparse.FileType('r'),
                        default=sys.stdin)

    args = parser.parse_args()

    subscriptions = yaml.load(args.subscriptions)
    html = main(subscriptions, start=args.start, previous=args.previous)
    args.outfile.write(html.encode('utf-8'))


if __name__ == '__main__':
    cli()
