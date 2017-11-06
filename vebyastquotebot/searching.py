import whoosh
import whoosh.index
import whoosh.qparser
import whoosh.fields
import whoosh.filedb
import whoosh.filedb.filestore
import vebyastquotebot.quotedb
import os
import os.path
import enum
import datetime


INDEX_PATH = "whoosh_index_dir"
WHOOSH_MESSAGE_SCHEMA = whoosh.fields.Schema(
    content=whoosh.fields.TEXT,
    reactions=whoosh.fields.KEYWORD,
    message_id=whoosh.fields.STORED,
    posttime=whoosh.fields.DATETIME,
    author=whoosh.fields.ID,
    channel=whoosh.fileds.ID
)

if not os.path.exists(INDEX_PATH):
    os.mkdir(INDEX_PATH)
    index.create_in(INDEX_PATH, WHOOSH_MESSAGE_SCHEMA)
    
WHOOSH_STORAGE = whoosh.index.open_dir(INDEX_PATH)


def index_message(*, message):
    pass

def reindex_logs(*, channel, after, before):
    pass

class MessageFindMode(enum.Enum):
    REACTION = 1
    QUERY = 2
    ID = 3

MESSAGE_FIND_FUNCTIONS = {
    MessageFindMode.REACTION: find_message_by_reaction,
    MessageFindMode.QUERY: find_message_by_query,a
    MessageFindMode.ID: find_message_by_id,
}

class MessageFindResult():
    def 

def find_message(*, mode, channel, **kwargs):
    message_id, return_message = MESSAGE_FIND_FUNCTIONS[mode](**kwargs)
    if not message_id:
        err = 'No posts matching query.'
        if 'querystring' in kwargs and kwargs['querystring'].isdigit():
            err += ' Did you mean to find by ID? See --help.'
        return (None, err)

    if message_id.length > 1:
        resultstring = 'Multiple posts matching query:\n{}'.format(
            vebyastquotebot.quotedb.format_messages(
                (logs_idx[sr] for sr in search_results[:3]),
                short=80,
            )
        )
        return (None, resultstring)

    return (await client.get_message(channel, message_id, **kwargs),
            'Found one post')

def find_message_by_ID(*, channel, message_id, **kwargs):
    return [message_id]

def find_message_by_reaction(*, channel, reaction, **kwargs):
    q = whoosh.query.Require(
        build_query_reaction(reaction),
        build_filters(channel),
    )
    return find_message_whoosh(q)

def find_message_by_querystring(*, channel, querystring):
    q = whoosh.query.Require(
        build_query_querystring(querystring),
        build_filters(channel),
    )
    return find_message_whoosh(q)
        
def find_message_whoosh(query):
    with WHOOSH_STORAGE.searcher() as searcher:
        resultset = searcher.search(query)
        results = [result['message_id'] for result in resultset]
        return results

def build_query_querystring(query):
    return whoosh.qparser.QueryParser('content', WHOOSH_STORAGE.schema).parse(querystring)

def build_query_reaction(reaction):
    return whoosh.query.Term('reactions', reaction)

def build_query_channel(channel):
    return whoosh.query.Term('channel', channel.id)

def build_query_recency(minutes_ago):
    return whoosh.query.DateRange(
        'posttime',
        datetime.datetime.now() - datetime.timedelta(minutes=15),
        datetime.datetime.now(),
    )

def build_filters(channel, minutes_ago=60):
    return build_query_recency(minutes_ago) + build_query_channel(channel.id)




async def pull_logs(*, client, limit, start_message=None, end_message=None, channel=None):
    logs = []
    # add the start message, since the "before" and "after" are an
    # open interval
    if start_message:
        if (not end_message or (end_message.id != start_message.id)):
            logs.append(start_message)
    # goes from end to start by default, so reverse it to get start to
    # end
    async for log in client.logs_from(
            channel or start_message.channel or end_message.channel,
            limit=limit,
            before=end_message,
            after=start_message,
            reverse=True):
        logs.append(log)
    if end_message:
        logs.append(end_message)
    return logs


def search_messages(*,
                    logs,
                    querystring,
                    reaction,
                    predicate=lambda _: True):
    idx = WHOOSH_STORAGE.create_index(WHOOSH_MESSAGE_SCHEMA)

    writer = idx.writer()
    for log in logs:
        if predicate(log):
            if reaction in log.reactions:
                return [log.id]
            writer.add_document(
                content=log.clean_content,
                message_id=log.id,
                author=log.author.display_name,
            )
    writer.commit()

    with idx.searcher() as searcher:
        query = whoosh.qparser.QueryParser(
            'content', idx.schema
        ).parse(querystring)
        resultset = searcher.search(query)
        results = [result['message_id'] for result in resultset]
    return results


async def find_message(*,
                       client,
                       channel,
                       querystring,
                       reaction,
                       limit,
                       predicate=lambda _: True):
    logs = await pull_logs(
        client=client,
        limit=limit,
        channel=channel,
    )
    logs_idx = {
        log.id: log for log in logs
    }

    search_results = search_messages(
        logs=logs,
        querystring=querystring,
        reaction=reaction,
        predicate=predicate,
    )

    if len(search_results) == 0:
        err = 'No posts matching query.'
        if querystring.isdigit():
            err += ' Did you mean to find by ID? See --help.'
        return (None, err)
    elif len(search_results) > 1:
        resultstring = 'Multiple posts matching query:\n{}'.format(
            vebyastquotebot.quotedb.format_messages(
                (logs_idx[sr] for sr in search_results[:5]),
                short=80,
            )
        )
        return (None, resultstring)
    else:
        return (await client.get_message(channel, search_results[0]), 'Found one post')
