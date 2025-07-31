from tinydb import TinyDB, Query
import calendar
from datetime import date
import time
import re
import os
from itertools import groupby

from constants import DATEFMT

class RecordsList(object):
    def __init__(self, records):
        self.records = records
        for r in self.records:
            r['datestr'] = DATEFMT.format(**r)

    def data(self):
        return self.records

    def sorted(self, key='ts'):
        return sorted(self.records, key=lambda x: x[key])

    def grouped(self, key='category'):
        grouping = groupby(self.sorted(key=key), key=lambda x: x[key])
        return [(k, self.__class__(list(g))) for k,g in grouping]


class ExpenseList(RecordsList):
    def __init__(self, records):
        super().__init__(records)

    def total(self):
        return sum(r['amount'] for r in self.records)

class ExpensesDAO:
    def __init__(self, dbpath):
        self.db = TinyDB(dbpath)

    def query(self, name=None, year=None, month=None, day=None, category=None, source=None):
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
        if source:
            query = query & (exp.source == source)

        records = self.db.search(query)
        return ExpenseList(records)

    def single(self, doc_id):
        r = self.db.get(doc_id=doc_id)
        if r:
            r['datestr'] = DATEFMT.format(**r)
        return r

    def create(self, params):
        date = params['date'].split('-')
        if len(date) == 3:
            year, month, day = tuple([int(d) for d in date])
        elif len(date) == 2:
            year, month = tuple([int(d) for d in date])
            day = 1
        else:
            raise Exception("Date format wrong, expecting yyyy-mm or yyyy-mm-dd: %s" % params["date"])
        ts = int(time.mktime((year, month, day, 0,0,0,0,0,0)))
        newexp = {
            'name': params['name'],
            'category': params['category'],
            'source': params['source'],
            'amount': float(params['amount']),
            'year': year,
            'month': month,
            'date': day,
            'ts': ts
            }
        return self.db.insert(newexp)

    def update(self, doc_id, params):
        date = params['date'].split('-')
        if len(date) == 3:
            year, month, day = tuple([int(d) for d in date])
        elif len(date) == 2:
            year, month = tuple([int(d) for d in date])
            day = 1
        else:
            raise Exception("Date format wrong, expecting yyyy-mm or yyyy-mm-dd: %s" % params["date"])
        ts = int(time.mktime((year, month, day, 0,0,0,0,0,0)))
        newexp = {
            'name': params['name'],
            'category': params['category'],
            'source': params['source'],
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

class TransactionList(RecordsList):
    def __init__(self, records):
        super().__init__(records)

class HoldingList(RecordsList):
    def __init__(self, records):
        super().__init__(records)

class PortfolioDAO:
    def __init__(self, dbpath):
        self.db = TinyDB(dbpath)
        self.transactions = self.db.table('transactions')
        self.holdings = self.db.table('holdings')

class UsersDAO:
    def __init__(self, dbpath):
        self.dbpath = dbpath
        self.db = TinyDB(os.path.join(dbpath, 'users.json'))
        if len(self.db) == 0:
            self.db.insert_multiple([
                {'username':'udiboy', 'password':'password', 'currsym': '₹'},
                {'username':'himani', 'password':'password', 'currsym': '$'},
            ])

        self.expdao_cache = {}
        self.portdao_cache = {}

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
        dbfile = '%s.json' % username
        dao = ExpensesDAO(os.path.join(self.dbpath, 'expenses', dbfile))
        self.expdao_cache[username] = dao
        return dao

    def get_portdao(self, user):
        username = user['username']
        if username in self.portdao_cache:
            return self.portdao_cache[username]
        dbfile = '%s.json' % username
        dao = PortfolioDAO(os.path.join(self.dbpath, 'portfolios', dbfile))
        self.portdao_cache[username] = dao
        return dao
