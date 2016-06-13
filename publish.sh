#! /bin/bash
set -e -x
mkdir -p issues

cp broadsheet/templates/*.css issues/

today=$(date +%Y-%m-%d)
yesterday=$(date -v-1d +%Y-%m-%d)

yesterday_mtime=$(stat -f "%Sm" -n issues/$yesterday.html)

python broadsheet/crawler.py subscriptions.yaml -o issues/$today.html -s "$yesterday_mtime" -p "$yesterday"
cd issues
ln -sf $today.html index.html
cd -

rsync -vcr --links -e 'ssh -i ~/Personal/ssh/id_rsa -p 30000' issues/ drcraig@dancraig.net:~/public_html/dancraig.net/public/broadsheet/
