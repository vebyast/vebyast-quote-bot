import whoosh
import whoosh.index
import whoosh.qparser
import whoosh.fields
import whoosh.filedb
import whoosh.filedb.filestore
import vebyastquotebot.quotedb

WHOOSH_STORAGE = whoosh.filedb.filestore.RamStorage()
WHOOSH_MESSAGE_SCHEMA = whoosh.fields.Schema(
    content=whoosh.fields.TEXT,
    message_id=whoosh.fields.ID(stored=True),
    author=whoosh.fields.KEYWORD
)

async def pull_logs(*, client, limit, start_message=None, end_message=None, channel=None):
    logs = []
    if end_message:
        logs.append(end_message)
    # goes from end to start
    async for log in client.logs_from(
            channel or start_message.channel or end_message.channel,
            limit=limit,
            before=end_message,
            after=start_message):
        logs.append(log)
    if start_message:
        if (not end_message or (end_message.id != start_message.id)):
            logs.append(start_message)
    logs.reverse()
    return logs


def search_messages(*,
                    logs,
                    querystring,
                    predicate=lambda _: True):
    idx = WHOOSH_STORAGE.create_index(WHOOSH_MESSAGE_SCHEMA)

    writer = idx.writer()
    for log in logs:
        if predicate(log):
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
                       feedback,
                       channel,
                       querystring,
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
        predicate=predicate,
    )

    if len(search_results) == 0:
        return (None, 'No posts matching query.')
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
