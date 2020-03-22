broadsheet
==========

A single user, self-hosted RSS reader


## Installation

Requires Python 3.7+.

    pip install -r requirements.txt

## Usage

Render a single HTML file of all the subscriptions with articles
dated since yesterday.

    python crawler.py subscriptions.yaml -o output.html -s yesterday

