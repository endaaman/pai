from flask import Flask

App = Flask(__name__)

@App.route('/')
def hello():
    name = "Hello World"
    return name

@App.route('/good')
def good():
    name = "Good"
    return name


def start():
    print('server start')
    App.run(debug=False, host='0.0.0.0', port=3000)
