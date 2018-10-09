#!/usr/bin/env python

## app.py
# Flask application entry point

import json

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


@app.route('/terms', methods=['GET'])
def get_terms():
    return Response(to_json(scraper.scrape_terms()),
        mimetype='application/json')


@app.route('/courses', methods=['POST'])
def get_courses():
    return Response(to_json(scraper.scrape_courses(
        request.authorization.username,
        request.authorization.password,
        request.form['term']
    )), mimetype='application/json')


if __name__ == '__main__':
    app.run()

