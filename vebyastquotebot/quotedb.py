import json
import git
import os
import vebyastquotebot.orderedenum
import pytz
import re
import discord

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
        self.changed = False

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
        self.changed = True

    def remove_quote(self, quote_id):
        before = len(self.quotes)
        self.quotes = [quote for quote in self.quotes if quote['id'] != quote_id]
        after = len(self.quotes)
        self.changed = (before != after)

    def __exit__(self, etype, value, traceback):
        if etype:
            return False

        if not self.changed:
            return

        if self.docommit == QuoteDBCommit.LOG:
            print("QuoteDB saving changes")

        if self.docommit >= QuoteDBCommit.FS:
            with open('quotes.json', 'w') as jsf:
                json.dump(self.quotes, jsf, indent=2)

        if self.docommit >= QuoteDBCommit.COMMIT:
            self.commit()

        if self.docommit >= QuoteDBCommit.PUSH:
            self.push()

def message_to_json(log):
    return {
        'author': log.author.display_name,
        'author_id': log.author.id,
        'timestamp': pytz.utc.localize(log.timestamp).isoformat(),
        'edited': pytz.utc.localize(log.edited_timestamp).isoformat() if log.edited_timestamp else None,
        'content': log.clean_content,
        'authorcolor': '#{:06X}'.format(log.author.colour.value) if log.author.color.value else None,
    }

def format_quotehash(line, short=None, wrap=False):
    fstring = '**{user}:** {content}'
    content = line['content']
    if short:
        content = content[:short]
    if wrap:
        content = wrap_single(content)
    return fstring.format(
        user=line['author'],
        content=content,
    )

def format_message(m, **kwargs):
    return format_quotehash(message_to_json(m), **kwargs)

def format_messages(messages, **kwargs):
    return '\n'.join(format_message(m, **kwargs) for m in messages)

def format_quotehashes(lines, **kwargs):
    return '\n'.join(format_quotehash(line, **kwargs) for line in lines)

def format_quote(q, **kwargs):
    return format_quotehashes(q['lines'], **kwargs)

def wrap_single(s):
    return '`' + re.sub('`[^`]', r'\\\g<0>', s) + '`'

def wrap_triple(s):
    return '```' + re.sub('```', r'`', s) + ' ```'
