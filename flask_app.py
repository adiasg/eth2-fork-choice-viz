from flask import Flask, render_template, jsonify
from fork_choice_fetch import get_fork_choice_data, cache_get_fork_choice_data

app = Flask(__name__)


@app.route('/')
def hello():
    fc_data = cache_get_fork_choice_data()
    if fc_data["current_slot"] == -1:
        return "Genesis has not happened yet! 404 - Eth2 not found", 404
    elif fc_data["current_slot"] == -2:
        return "There's a problem!", 400
    return render_template("fork_choice_viz.html", fc_data=fc_data)
