import argparse
from datetime import datetime, date, timedelta
import itertools
import logging
from multiprocessing.dummy import Pool as ThreadPool
import re
import os
import sys
import time
from urllib.parse import urlparse

from cachelib.file import FileSystemCache
import dateparser
from jinja2 import Environment, FileSystemLoader
import yaml
import feedparser
import requests_cache


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

USER_AGENT = "Broadsheet/0.1 +http://dancraig.net/broadsheet/"
feedparser.USER_AGENT = USER_AGENT
feedparser._HTMLSanitizer.acceptable_elements.add("iframe")

session = requests_cache.CachedSession(
    os.path.join(os.environ.get("BROADSHEET_CACHE_DIR", ""), "broadsheet"),
    cache_control=True,
    always_revalidate=True,
    expire_after=timedelta(hours=24),
)
session.headers["User-Agent"] = USER_AGENT

seen_cache = FileSystemCache(
    os.path.join(os.environ.get("BROADSHEET_CACHE_DIR", ""), "seen_cache"),
    threshold=5000,
    default_timeout=30 * 24 * 60 * 60,
)


def crawl_feed(url, feed_title=None):
    """Take a feed, return articles"""
    try:
        response = session.get(url, timeout=10)
        log.info(f"{url} {response}")
        if not response.ok:
            return []
        result = feedparser.parse(response.text)

        if feed_title:
            result.feed["title"] = feed_title

        entries = [entry for entry in result.entries]
        for entry in entries:
            entry["feed"] = result.feed
        return entries
    except Exception as e:
        log.info(f"{url} {e}")
        return []


def first_seen_date(article):
    """Since feeds can be misconfigured for timezones or have invalid timestamps,
    we need to keep track of when an article was first observed so it can appear
    appropriately when it's new to you."""
    # Articles constructed with listify, like daily digests, won't have a link.
    if not hasattr(article, "link"):
        return None

    # .add() does not overwrite preexisting values
    seen_cache.add(article.link, time.localtime())
    return seen_cache.get(article.link)


def key_by_date(article):
    """Key function to sort articles by date"""
    return (
        first_seen_date(article)
        or article.get("published_parsed")
        or article.get("updated_parsed")
        or time.localtime()
    )


def listify(articles, title=None):
    """Take a list of articles, and create a new list of articles composed
    of lists of links to the original articles"""
    if not articles:
        return {}

    most_recent_article = sorted(articles, key=key_by_date, reverse=True)[0]

    return [
        feedparser.FeedParserDict(
            {
                "feed": most_recent_article.feed,
                "title": "",
                "links": most_recent_article.feed.get("links", [])
                + [
                    {
                        "href": article.get("link"),
                        "rel": "related",
                        "type": "text/html",
                        "title": article.get("title"),
                    }
                    for article in articles
                ],
                "published": most_recent_article.get("published"),
                "published_parsed": most_recent_article.get("published_parsed"),
                "updated": most_recent_article.get("updated"),
                "updated_parsed": most_recent_article.get("updated_parsed"),
            }
        )
    ]


def article_timestamp(article):
    timestruct = article.get("published_parsed") or article.get("updated_parsed")
    if not timestruct:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(timestruct))
    except ValueError:
        return None


def article_date(article):
    timestamp = article_timestamp(article)
    if not timestamp:
        return None
    return timestamp.date()


def daily_digest(articles):
    """Transform  articles into daily digests"""
    articles = sorted(articles, key=article_date, reverse=True)
    digests = []
    for _, articles_that_date in itertools.groupby(articles, article_date):
        digests.extend(listify(list(articles_that_date)))
    return digests


def filter_by_datetime_range(articles, start=None, end=None):
    """Filter articles within a start and stop range.

    Start and stop could be either dates or datetimes. If dates, start will
    be assumed to be the start of the day and end will be the end of the day"""
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


def pre(articles):
    for article in articles:
        article.preformatted = True
        yield article


def apod_fix_pubdate(articles):
    """Astronomy Picture of the Date (http://apod.nasa.gov/apod/) does not put dates
    in the articles, but can be derived from the URL"""
    for article in articles:
        url = urlparse(article["link"])
        if url.path == "/apod/astropix.html":
            article["published_parsed"] = date.today().timetuple()
        elif re.match(r"/apod/ap\d{6}.html", url.path):
            article["published_parsed"] = datetime.strptime(
                url.path, "/apod/ap%y%m%d.html"
            ).timetuple()
        yield article


def nws_afd_synopsis_only(articles):
    """NWS Area Forecast Discsussions are long. Only get the synposis"""
    for article in articles:
        article["description"] = article.get("description", "").split(r"&&")[0]
        yield article


def remove_redundant_title(articles):
    """kottke.org has short items, where the title is a truncated version of
    the body. Remove the title when it's just an ellipised version of the body."""
    for article in articles:
        if article["description"].startswith(article["title"].rstrip(".")):
            article["title"] = ""
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
    process_feed_args = [
        (sub["url"], sub.get("title"), sub.get("post_processors", []))
        for sub in subscriptions
    ]
    pool = ThreadPool(5)
    results = pool.map(process_feed_mapper, process_feed_args)
    all_articles = list(itertools.chain(*results))
    all_articles.sort(key=key_by_date, reverse=True)
    return list(all_articles)


def time_struct_to_datetime(time_struct):
    return datetime(*time_struct[:6])


def render(articles, timestamp=None, previous=None):
    timestamp = timestamp or datetime.now()
    env = Environment(
        loader=FileSystemLoader("templates"), extensions=["jinja2.ext.with_"]
    )
    env.filters["datetime"] = time_struct_to_datetime

    return env.get_template("index.html").render(
        articles=articles, timestamp=timestamp, previous=previous
    )


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
    raise argparse.ArgumentTypeError("%s did not parse as a datetime" % string)


def cli():
    parser = argparse.ArgumentParser(description="Generate a file of feeds")
    parser.add_argument(
        "-s", "--start", help="Start date", type=datetime_type, default=None
    )
    parser.add_argument(
        "-p", "--previous", help="Previous date", type=datetime_type, default=None
    )
    # parser.add_argument('-z', '--time-zone', help='Time zone', default='US/Pacific')
    # Not using FileType for the outfile so that it doesn't hold the file open
    # for write while the parser runs.
    parser.add_argument("-o", "--outfile", nargs="?", default="-")
    parser.add_argument(
        "subscriptions", nargs="?", type=argparse.FileType("r"), default=sys.stdin
    )

    args = parser.parse_args()

    subscriptions = yaml.safe_load(args.subscriptions)
    html = main(
        subscriptions,
        start=args.start,
        previous=args.previous,
    )

    if args.outfile == "-":
        sys.stdout.write(html)
    else:
        with open(args.outfile, "w") as outfile:
            outfile.write(html)


if __name__ == "__main__":
    cli()
