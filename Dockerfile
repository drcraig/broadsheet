FROM python:3.7

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN useradd --create-home appuser
WORKDIR /home/appuser

COPY requirements.txt /home/appuser/requirements.txt
RUN --mount=type=cache,target=/var/cache/pip \
    PIP_CACHE_DIR=/var/cache/pip \
    python3 -m pip install -r requirements.txt

ENV BROADSHEET_CACHE_DIR=/var/cache/broadsheet
RUN mkdir $BROADSHEET_CACHE_DIR && chown -R appuser:appuser $BROADSHEET_CACHE_DIR
COPY crawler.py /home/appuser/crawler.py
RUN python -m compileall .
COPY templates /home/appuser/templates
COPY subscriptions.yaml /home/appuser/subscriptions.yaml
USER appuser
RUN mkdir -p /home/appuser/output
CMD python crawler.py subscriptions.yaml -s "1 week ago" -o /home/appuser/output/index.html