from functools import wraps
from flask import Flask, request, session, g, abort, render_template, redirect, url_for, flash
from tinydb import TinyDB, Query
import calendar
from datetime import date
import time
import re
import os

DATEFMT = '{year:d}-{month:02d}-{date:02d}'
TODAY = date.today
ALLCATEGORIES = ['Food', 'Entertainment', 'Travel', 'Utilities',
                 'Groceries', 'Rent', 'Family']
ALLYEARS = [2019, 2020]
NOTFOUNDEXP={'doc_id': '', 'name': 'Not Found'}

class ExpenseList:
    def __init__(self, records):
        self.records = records
        for r in self.records:
            r['datestr'] = DATEFMT.format(**r)

    def data(self):
        return self.records

    def sorted(self):
        return sorted(self.records, key=lambda x: -x['ts'])

    def total(self):
        return sum(r['amount'] for r in self.records)

    def avg(self):
        return self.total() / len(self.records)

class ExpensesDAO:
    def __init__(self, dbpath, dbfile):
        self.db = TinyDB(dbpath + '/' + dbfile)

    def query(self, name=None, year=None, month=None, day=None, category=None):
        exp = Query()
        query = exp.name.exists()
        if name:
            words = name.split(' ')
            for w in words:
                query = query & (exp.name.search(w, flags=re.IGNORECASE))
        if year:
            query = query & (exp.year == int(year))
        if month:
            query = query & (exp.month == int(month))
        if day:
            query = query & (exp.date == int(day))
        if category:
            query = query & (exp.category == category)

        print(query)
        records = self.db.search(query)
        return ExpenseList(records)

    def single(self, doc_id):
        r = self.db.get(doc_id=doc_id)
        if r:
            r['datestr'] = DATEFMT.format(**r)
        return r

    def create(self, params):
        date = params['date'].split('-')
        year, month, day = tuple([int(d) for d in date])
        ts = int(time.mktime((year, month, day, 0,0,0,0,0,0)))
        newexp = {
            'name': params['name'],
            'category': params['category'],
            'amount': float(params['amount']),
            'year': year,
            'month': month,
            'date': day,
            'ts': ts
            }
        return self.db.insert(newexp)

    def update(self, doc_id, params):
        date = params['date'].split('-')
        year, month, day = tuple([int(d) for d in date])
        ts = int(time.mktime((year, month, day, 0,0,0,0,0,0)))
        newexp = {
            'name': params['name'],
            'category': params['category'],
            'amount': float(params['amount']),
            'year': year,
            'month': month,
            'date': day,
            'ts': ts
            }
        self.db.update(newexp, doc_ids=[doc_id])
        return True

    def delete(self, doc_id):
        self.db.remove(doc_ids=[doc_id])


class UsersDAO:
    def __init__(self, dbpath, dbfile):
        self.dbpath = dbpath
        self.db = TinyDB(dbpath + '/' + dbfile)
        if len(self.db) == 0:
            self.db.insert_multiple([
                {'username':'udiboy', 'password':'password', 'currsym': '₹'},
                {'username':'himani', 'password':'password', 'currsym': '$'},
            ])

        self.expdao_cache = {}

    def get(self, username):
        UserQ = Query()
        user = self.db.get(UserQ.username == username)
        if user:
            del user['password']
        return user

    def verify(self, form):
        UserQ = Query()
        user = self.db.get(UserQ.username == form['username'])
        if user and user['password'] == form['password']:
            return self.get(user['username'])
        return False

    def get_expdao(self, user):
        username = user['username']
        if username in self.expdao_cache:
            return self.expdao_cache[username]
        expfile = '%s.json' % username
        dao = ExpensesDAO(self.dbpath, expfile)
        self.expdao_cache[username] = dao
        return dao

class DevelopmentConfig:
    ENV = 'development'
    DEBUG = True
    SECRET_KEY = b'\xd34e+Pl\xc6xJE\xdd\x9b\xa9(T#'
    DBPATH = 'test/db'

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

app = Flask('MoneyMan')
app.config.from_object(DevelopmentConfig())
if 'MONEYMAN_CONFIG' in os.environ:
    app.config.from_envvar('MONEYMAN_CONFIG')

# Custom filters
app.jinja_env.filters['monthname'] = lambda i: calendar.month_name[i]
app.jinja_env.filters['currency'] = lambda c: '{:20,.2f}'.format(c)

usersdao = UsersDAO(app.config['DBPATH'], 'users.json')

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
            'expenses': exps.sorted(),
           }
    return render_template('home.html', **data)


@app.route('/single/<int:doc_id>')
@logged_in
def single(doc_id=0):
    exp = g.expdao.single(doc_id)
    if exp:
        return render_template('single.html', exp=exp)
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
    return render_template('new.html', **data)

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
    return render_template('update.html', **data)

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

