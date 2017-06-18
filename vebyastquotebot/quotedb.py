import json
import git
import os
import vebyastquotebot.orderedenum

class QuoteDBCommit(vebyastquotebot.orderedenum.OrderedEnum):
    READONLY = 1
    LOG = 2
    FS = 3
    COMMIT = 4
    PUSH = 5

class QuoteDB(object):
    def __init__(self, docommit=QuoteDBCommit.LOG, commit_message=''):
        self.repo = None
        self.quotes = None
        self.docommit = docommit
        self.commit_message = commit_message
        self.index = None

    def __enter__(self):
        with open('quotes.json', 'r') as jsf:
            self.quotes = json.load(jsf)
        self.index = {q['id']: q for q in self.quotes}
        self.repo = git.Repo(os.getcwd())
        return self

    def commit(self):
        self.repo.index.add(['quotes.json'])
        self.repo.index.commit(self.commit_message)

    def push(self):
        self.repo.remote().push()

    def add_quote(self, json_obj):
        self.quotes.append(json_obj)

    def remove_quote(self, quote_id):
        self.quotes = [quote for quote in self.quotes if quote['id'] != quote_id]

    def __exit__(self, etype, value, traceback):
        if etype:
            return False

        if self.docommit == QuoteDBCommit.LOG:
            print("QuoteDB saving changes")

        if self.docommit >= QuoteDBCommit.FS:
            with open('quotes.json', 'w') as jsf:
                json.dump(self.quotes, jsf, indent=2)

        if self.docommit >= QuoteDBCommit.COMMIT:
            self.commit()

        if self.docommit >= QuoteDBCommit.PUSH:
            self.push()
