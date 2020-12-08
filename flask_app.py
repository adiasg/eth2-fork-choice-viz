from flask import Flask, render_template, jsonify
from fork_choice_fetch import cache_get_fork_choice_data
import yaml

with open("/app/config.yml", "r") as config_file:
    cfg = yaml.safe_load(config_file)

title = cfg["page_title"]
graffiti = cfg["graffiti"]

if title is None:
    title = "Eth2.0 Fork Choice Visualizer"

app = Flask(__name__)


@app.route('/')
def serve_index():
    return render_template("fork_choice_viz.html", title=title, graffiti=graffiti)

@app.route('/data')
def serve_data():
    fc_data = cache_get_fork_choice_data()
    if fc_data["current_slot"] == -1:
        return 'Genesis has not happened yet! Checkout the Pyrmont testnet visualizer at <a href="http://pyrmont.eth2.ninja">pyrmont.eth2.ninja</a>', 404
    elif fc_data["current_slot"] == -2:
        fc_data = cache_get_fork_choice_data()
        if fc_data["current_slot"] < 0:
            return "There's a problem!", 400
    return jsonify(fc_data)
