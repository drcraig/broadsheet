from datetime import datetime, date, time, timedelta
import itertools
from time import mktime

from jinja2 import Environment, PackageLoader
import eventlet
import yaml


feedparser = eventlet.import_patched('feedparser')

feedparser._HTMLSanitizer.acceptable_elements.add('iframe')

pool = eventlet.GreenPool()

def crawl_feed(url, feed_title=None):
    """Take a feed, return articles"""
    result = feedparser.parse(url)
    print url, result.get('status', 'No Status')

    entries = [entry for entry in result.entries]
    for entry in entries:
        entry['feed'] = result.feed
    return entries


def key_by_date(article):
    """Key function to sort articles by date"""
    return article.get('updated_parsed') or article.get('published_parsed')


def listify(articles, title=None):
    """Take a list of articles, and create a new list of articles composed
    of lists of links to the original articles"""
    if not articles:
        return {}

    most_recent_article = sorted(articles, key=key_by_date, reverse=True)[0]

    return [feedparser.FeedParserDict({
        'feed': most_recent_article.feed,
        'title': '', # title or most_recent_article.feed.get('title', ''),
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
    timestruct = article.get('updated_parsed') or article.get('published_parsed')
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
    for date, articles_that_date in itertools.groupby(articles, article_date):
        digests.extend(listify(list(articles_that_date)))
    return digests


def filter_by_datetime_range(articles, start=None, end=None):
    '''Filter articles within a start and stop range.
    
    Start and stop could be either dates or datetimes. If dates, start will
    be assumed to be the start of the day and end will be the end of the day'''
    if isinstance(start, date):
        start = datetime.combine(start, time.min)
    if isinstance(end, date):
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


def apod_add_pubdate(articles):
    for article in articles:
        # Parse article link
        # apod/apYYMMDD.html
        # create struct_time for that
        yield article


def process_feed(url, alternate_title=None, post_procs=None):
    post_procs = post_procs or []
    articles = crawl_feed(url, feed_title=alternate_title)
    for post_processor in post_procs:
        articles = list(globals()[post_processor](articles))
    return articles

    
def process_subscriptions(subscriptions):
    all_articles = []
    pile = eventlet.GreenPile(pool)
    for subscription in subscriptions:
        url = subscription['url']
        alternate_title = subscription.get('title')
        post_processors = subscription.get('post_processors', [])
        pile.spawn(process_feed, url, alternate_title, post_processors)
    all_articles = list(itertools.chain.from_iterable(pile))
    all_articles.sort(key=key_by_date, reverse=True)
    return list(all_articles)


def time_struct_to_datetime(time_struct):
    return datetime(*time_struct[:6])


def render(articles):
    env = Environment(loader=PackageLoader('broadsheet', 'templates'),
                      extensions=['jinja2.ext.with_'])
    env.filters['datetime'] = time_struct_to_datetime

    return env.get_template('index.html').render(articles=articles, timestamp=datetime.now())


def main():
    with open('subscriptions.yaml') as file_:
        subscriptions = yaml.load(file_)
    start = date.today() - timedelta(days=7)
    all_articles = process_subscriptions(subscriptions)
    all_articles = filter_by_datetime_range(all_articles, start=start)
    html = render(articles=all_articles)
    with open('feeds.html', 'w') as f:
        f.write(html.encode('utf-8'))
    return all_articles

if __name__ == '__main__':
    main()
