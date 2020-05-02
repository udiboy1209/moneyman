from functools import wraps
from flask import Flask, request, session, g, abort, render_template, redirect, url_for, flash
import calendar
from datetime import date
import os

from constants import DATEFMT
from dao import UsersDAO

class DevelopmentConfig:
    ENV = 'development'
    DEBUG = True
    SECRET_KEY = b'\xd34e+Pl\xc6xJE\xdd\x9b\xa9(T#'
    DBPATH = 'test/db'
    APP_NAME = 'MF Portfolio'

app = Flask(__name__)
app.config.from_object(DevelopmentConfig())
if 'PORTFOLIO_CONFIG' in os.environ:
    app.config.from_envvar('PORTFOLIO_CONFIG')

TODAY = date.today

usersdao = UsersDAO(app.config['DBPATH'])

def logged_in(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if hasattr(g, 'user') and g.user:
            return f(*args, **kwargs)
        if 'username' in session:
            g.user = usersdao.get(session['username'])
            if not g.user:
                session.pop('username', None)
                return redirect(url_for('login'))
            g.expdao = usersdao.get_expdao(g.user)
            return f(*args, **kwargs)
        return redirect(url_for('login'))
    return decorated

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        print(request.form)
        user = usersdao.verify(request.form)
        if user:
            session['username'] = user['username']
            g.user = user
            flash('Login successful', 'success')
            return redirect(url_for('home'))
        flash('Invalid login', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logout successful', 'success')
    return redirect(url_for('login'))

@app.route('/')
@logged_in
def home():
    return render_template('portfolio/home.html')
