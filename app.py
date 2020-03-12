#!/usr/bin/env python

## app.py
# Flask application entry point

from functools import wraps
from http import HTTPStatus

from flask import Flask, Response, request, jsonify
from flask_heroku import Heroku

import scraper


app = Flask(__name__)
heroku = Heroku(app)


def authenticate():
    """Send a 401 response that enables and requests basic auth"""
    return Response(
        'Florida Poly credentials needed for access',
        HTTPStatus.UNAUTHORIZED,
        {'WWW-Authenticate': 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.authorization:
            return authenticate()
        else:
            return f(*args, **kwargs)
    return decorated


@app.errorhandler(scraper.AuthError)
def handle_auth_error(e):
    # Just ask for credentials again
    return authenticate()


@app.route('/terms', methods=['GET'])
def get_terms():
    return jsonify(scraper.scrape_terms())


@app.route('/courses', methods=['GET'])
@requires_auth
def get_courses():
    # Use latest term if none provided
    term = request.args.get('term')
    if term is None:
        term = scraper.scrape_latest_term()

    return jsonify(scraper.scrape_courses(
        request.authorization.username,
        request.authorization.password,
        term,
    ))


if __name__ == '__main__':
    app.run()
