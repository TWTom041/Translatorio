#!/usr/bin/env python3

from flask import Flask, Response, jsonify, url_for, abort, request
from functools import wraps
from opensubtitle_gtrans import get_best_sub

MANIFEST = {
    'id': 'com.twtom.translatorio',
    'version': '1.0.0',

    'name': 'Translatorio',
    'description': 'The translatorio addon provides subtitle translation for movies and series, powered by Google Translate.',

    'types': ['movie', 'series'],

    'catalogs': [],

    'resources': [
        'subtitles',
    ]
}


app = Flask(__name__)


def respond_with(data):
    resp = jsonify(data)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp


def parse_config(configs):
    conf_out = {
        'lang': 'en'
    }
    if configs == "default":
        return conf_out
    for k, v in (x.split('=') for x in configs.split('|')):
        conf_out[k] = v
    return conf_out


@app.route('/<configs>/manifest.json')
def addon_manifest(configs):
    return respond_with(MANIFEST)


@app.route('/<config>/subtitles/<type>/<id>.json')
def addon_stream(config, type, id):
    if type not in MANIFEST['types']:
        abort(404)
    
    parsed_config = parse_config(config)
    id_parsed = id.split(':')  # [imdb_id, season, episode] or [imdb_id]
    if len(id_parsed) == 3:
        imdb_id, season, episode = id_parsed
    else:
        imdb_id, season, episode = id_parsed[0], "", ""

    # output should be like {"id": "random", "url": "subtitles/subtitleidhashed", "lang": "en"}
    output = {
        "id": f"{id}-{parsed_config['lang']}",
        "url": url_for('get_sub_text', imdb_id=id, lang=parsed_config['lang'], season=season, episode=episode, _external=True),
        "lang": parsed_config['lang']
    }

@app.route('/get_sub_text/<imdb_id>/<lang>/<season>/<episode>')
def get_sub_text(imdb_id="", lang="", season="", episode=""):
    best_sub = get_best_sub(lang, season=season, episode=episode, imdb_id=imdb_id)
    return best_sub.to_string()


if __name__ == '__main__':
    app.run()