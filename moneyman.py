from functools import wraps
from flask import Flask, request, session, g, abort, render_template, redirect, url_for, flash
import calendar
from datetime import date
import os
from itertools import groupby
import json

from constants import CHARTCOLOR_BYCAT

from dao import UsersDAO

TODAY = date.today
ALLCATEGORIES = ['Food', 'Entertainment', 'Travel', 'Utilities',
                 'Groceries', 'Rent', 'Family', 'Personal']
ALLYEARS = [2019, 2020, 2021, 2022, 2023]

class DevelopmentConfig:
    ENV = 'development'
    DEBUG = True
    SECRET_KEY = b'\xd34e+Pl\xc6xJE\xdd\x9b\xa9(T#'
    DBPATH = 'test/db'
    APP_NAME = 'Expense Manager'

def getparams(args):
    params = dict([
            (key, args.get(key, None))
            for key in ['name', 'year', 'month', 'day', 'category']
        ])
    return params

def verifyparams(form):
    if 'date' not in form or len(form['date']) == 0:
        return (False, "'date' is missing")

    year = int(form['date'].split('-')[0])
    if year not in ALLYEARS:
        return (False, "Invalid year '%s'" % form['date'])

    names = form.getlist('name')
    amounts = form.getlist('amount')
    categories = form.getlist('category')

    items = []
    for n,a,c in zip(names, amounts, categories):
        n = n.strip()
        if len(n) == 0 or len(a) == 0 or len(c) == 0:
            continue
        if c not in ALLCATEGORIES:
            return (False, "Invalid category '%s'" % form['category'])

        single = {
            'name': n,
            'category': c,
            'amount': a,
            'date': form['date']
        }
        items.append(single)

    if len(items) == 0:
        return (False, 'Fields are missing')

    return (True, items)

app = Flask(__name__)
app.config.from_object(DevelopmentConfig())
if 'MONEYMAN_CONFIG' in os.environ:
    app.config.from_envvar('MONEYMAN_CONFIG')

# Custom filters
monthname = lambda i: calendar.month_name[i]
app.jinja_env.filters['monthname'] = monthname
app.jinja_env.filters['currency'] = lambda c: '{:20,.2f}'.format(c)

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
    params = getparams(request.args)
    exps = g.expdao.query(**params)

    data = {
            'allcategories': ALLCATEGORIES,
            'allyears': ALLYEARS,
            'expenses': list(reversed(exps.sorted())),
           }
    return render_template('moneyman/home.html', **data)


@app.route('/single/<int:doc_id>')
@logged_in
def single(doc_id=0):
    exp = g.expdao.single(doc_id)
    if exp:
        return render_template('moneyman/single.html', exp=exp)
    else:
        flash('Record not found for ID: %d' % doc_id, 'error')
        return render_template('single.html', exp=NOTFOUNDEXP)


@app.route('/new', methods=['GET', 'POST'])
@logged_in
def newexp():
    data = {
            'allcategories': ALLCATEGORIES,
            'startdate': '{:d}-01-01'.format(ALLYEARS[0]),
            'enddate': TODAY().strftime('%Y-%m-%d'),
           }
    if request.method == 'POST':
        print(request.form)
        ver, val = verifyparams(request.form)
        if not ver:
            flash(val, 'error')
        else:
            for item in val:
                doc_id = g.expdao.create(item)
                if not doc_id:
                    flash('Could not create entry', 'error')
                    break
            else:
                flash('Successfully created %d entries' % len(val), 'success')
                return redirect(url_for('home'))
    return render_template('moneyman/new.html', **data)

@app.route('/update/<int:doc_id>', methods=['GET'])
@logged_in
def updexp(doc_id):
    exp = g.expdao.single(doc_id)
    data = {
            'allcategories': ALLCATEGORIES,
            'startdate': '{:d}-01-01'.format(ALLYEARS[0]),
            'enddate': TODAY().strftime('%Y-%m-%d'),
            'exp': exp,
           }
    return render_template('moneyman/update.html', **data)

@app.route('/update', methods=['POST'])
@logged_in
def updexp_submit():
    doc_id = int(request.form['doc_id'])
    ver, val = verifyparams(request.form)
    if not ver:
        flash(val, 'error')
    elif len(val) > 1:
        flash('Too many items', 'error')
    else:
        success = g.expdao.update(doc_id, val[0])
        if not success:
            flash('Could not update entry', 'error')
        else:
            flash('Successfully updated', 'success')
    return redirect(url_for('single', doc_id=doc_id))

@app.route('/delete', methods=['POST'])
@logged_in
def delexp():
    doc_id = int(request.form['doc_id'])
    g.expdao.delete(doc_id)
    flash('Successfully deleted', 'success')
    return redirect(url_for('home'))

@app.route('/summary')
@logged_in
def summary():
    exps = g.expdao.query()
    groupedexps = {}
    labels = []
    labelsdone = False
    for year, yearexps in exps.grouped('year'):
        for month, monthexps in yearexps.grouped('month'):
            labels.append("%s %s" % (monthname(month), str(year)))

            catwise = dict(zip(ALLCATEGORIES, [0]*len(ALLCATEGORIES)))
            for cat, catexps in monthexps.grouped('category'):
                catwise[cat] = catexps.total()
            for cat in catwise:
                if cat not in groupedexps:
                    groupedexps[cat] = {
                            "label": cat,
                            "data": [],
                            "backgroundColor": CHARTCOLOR_BYCAT[cat]
                    }
                groupedexps[cat]["data"].append(catwise[cat])

    chart_data = {
        'labels': labels,
        'datasets': list(groupedexps.values()),
    }

    return render_template('moneyman/summary.html', chart_data=json.dumps(chart_data))

@app.route('/api/query')
@logged_in
def api_query():
    params = getparams(request.args)
    exps = g.expdao.query(**params)
    return {'expenses': exps.sorted(), 'total': exps.total()}

@app.route('/api/expense/<int:doc_id>')
@logged_in
def api_single(doc_id=0):
    exp = g.expdao.single(doc_id)
    if exp:
        return exp
    else:
        abort(404)

