#!/usr/bin/env python

## app.py
# Flask application entry point

import json
from functools import wraps

from flask import Flask, Response, request
from flask_heroku import Heroku

import scraper


app = Flask(__name__)
heroku = Heroku(app)


def to_json(obj, pretty=False):
    if pretty or request.args.get('pretty', '') == 'true':
        return json.dumps(obj, indent=2)
    else:
        return json.dumps(obj, separators=(',', ':'))


def authenticate():
    """Send a 401 responce that enables and requests basic auth"""
    return Response('Florida Poly credentials needed for access',
        401, {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.authorization:
            return authenticate()
        else:
            return f(*args, **kwargs)
    return decorated


@app.route('/terms', methods=['GET'])
def get_terms():
    return Response(to_json(scraper.scrape_terms()),
        mimetype='application/json')


@app.route('/courses', methods=['GET'])
@requires_auth
def get_courses():
    # TODO Reply back with authenticate() if the scraper says the credentials
    # are invalid
    try:
        return Response(to_json(scraper.scrape_courses(
            request.authorization.username,
            request.authorization.password,
            request.args.get('term', 27) # TODO Pull most recent from CAMS
        )), mimetype='application/json')
    except:
        return authenticate()


if __name__ == '__main__':
    app.run()

