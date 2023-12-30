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

ENV BROADSHEET_CACHE_NAME=/var/cache/broadsheet/broadsheet
RUN mkdir /var/cache/broadsheet && chown -R appuser:appuser /var/cache/broadsheet
COPY crawler.py /home/appuser/crawler.py
COPY templates /home/appuser/templates
COPY subscriptions.yaml /home/appuser/subscriptions.yaml
USER appuser
CMD python crawler.py subscriptions.yaml -s yesterday