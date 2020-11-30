from flask import Flask, render_template
from fork_choice_fetch import cache_get_fork_choice_data

app = Flask(__name__)


@app.route('/')
def hello():
    fc_data = cache_get_fork_choice_data()
    if fc_data["current_slot"] == -1:
        return 'Genesis has not happened yet! Checkout the Pyrmont testnet visualizer at <a href="http://pyrmont.eth2.ninja">pyrmont.eth2.ninja</a>'
    elif fc_data["current_slot"] == -2:
        fc_data = cache_get_fork_choice_data()
        if fc_data["current_slot"] < 0:
            return "There's a problem!", 400
    return render_template("fork_choice_viz.html", fc_data=fc_data)
