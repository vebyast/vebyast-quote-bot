import discord
import os
import logging
import pyparsing as ps
import shlex
import datetime
import pytz
import vebyastquotebot.quotedb
import vebyastquotebot.throwingargumentparser
import io

COMMANDS = {}
def command(name):
    def fun(f):
        COMMANDS[name] = f
        return None
    return fun

client = discord.Client()

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print(client.user.discriminator)
    print('------')

@client.event
async def on_message(message):
    # sorceror's apprentice protection, hopefully
    if message.author == client.user:
        return

    command_line = message.content
    if (message.server):
        try:
            parseresult = (
                ps.Keyword('<@' + client.user.id + '>').setResultsName('user_id') +
                ps.restOfLine.setResultsName('command_line')
            ).parseString(command_line)
            command_line = parseresult['command_line']
        except ps.ParseException:
            # public channel and it's not addressed to us, so bail out
            # there'll be a ton of this, so don't even bother logging it
            return

    parseresult = (
        ps.Or(ps.CaselessKeyword(com) for com in COMMANDS.keys()).setResultsName('command') +
        ps.restOfLine.setResultsName('argstring')
    ).parseString(command_line)

    feedback = await client.send_message(message.channel, 'Received command {}. Processing...'.format(parseresult.command))

    try:
        await COMMANDS[parseresult.command](
            message=message,
            argstring=parseresult.argstring,
            feedback=feedback)
    except Exception as e:
        await client.edit_message(feedback, "Error executing {}".format(parseresult.command))
        raise e

@command('/add')
async def command_addquote(*, message, feedback, argstring):
    parserio = io.StringIO()
    lexed = shlex.split(argstring)
    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/add',
        description='Add a quote.',
        outfile=parserio,
    )
    parser.add_argument('-S', '--start_id',
                        type=int,
                        help='The id of the first line of the quote, obtained using the discord developer mode')
    parser.add_argument('-E', '--end_id',
                        type=int,
                        help='The id of the last line of the quote, obtained using the discord developer mode')
    parser.add_argument('--limit',
                        type=int,
                        default=100,
                        help='Maximum number of lines to pull')
    try:
        args = parser.parse_args(args=lexed)
    except (vebyastquotebot.throwingargumentparser.ArgumentParserError,
            vebyastquotebot.throwingargumentparser.ArgumentParserExited):
        await client.edit_message(feedback, '```' + parserio.getvalue() + '```')
        return
    finally:
        parserio.close()

    await client.edit_message(feedback, "Processed command. Getting logs...")

    start_message = await client.get_message(message.channel, args.start_id)
    end_message = await client.get_message(message.channel, args.end_id)

    logs = []
    logs.append(end_message)
    # goes from end to start
    async for log in client.logs_from(message.channel,
                                      limit=args.limit,
                                      before=end_message,
                                      after=start_message):
        logs.append(log)
    logs.append(start_message)
    logs.reverse()

    await client.edit_message(feedback, "Got logs. Processing logs...")

    json_obj = {
        'id': int(message.id),  # reuse the id of the command message
        'lines': [{
            'author': log.author.display_name,
            'timestamp': pytz.utc.localize(log.timestamp).isoformat(),
            'edited': pytz.utc.localize(log.edited_timestamp).isoformat() if log.edited_timestamp else None,
            'content': log.content,
        } for log in logs],
        'quoted': datetime.datetime.utcnow().isoformat(),
    }
    print(json_obj)

    await client.edit_message(feedback, "Processed logs. Saving and uploading...")

    with vebyastquotebot.quotedb.QuoteDB(
            docommit=vebyastquotebot.quotedb.QuoteDBCommit[os.environ['QUOTE_DB_COMMIT']],
            commit_message='/add (by {}#{})'.format(message.author.name, message.author.discriminator),
    ) as quote:
        quote.add_quote(json_obj)

    await client.edit_message(feedback, "Done with /add! Quoted {nlines} lines. Quote ID: {quote_id}".format(
        nlines=len(json_obj['lines']),
        quote_id=json_obj['id'],
    ))

@command('/remove')
async def remove_quote(*, message, feedback, argstring):
    parserio = io.StringIO()
    lexed = shlex.split(argstring)
    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/remove',
        description='Remove a quote.',
        outfile=parserio,
    )
    parser.add_argument('quote_id',
                        type=int,
                        action='append',
                        help='An id of a quote to be deleted. Can be given multiple times.')
    try:
        args = parser.parse_args(args=lexed)
    except (vebyastquotebot.throwingargumentparser.ArgumentParserError,
            vebyastquotebot.throwingargumentparser.ArgumentParserExited):
        await client.edit_message(feedback, '```' + parserio.getvalue() + '```')
        return
    finally:
        parserio.close()

    await client.edit_message(feedback, "Processed command. Removing quote...")

    with vebyastquotebot.quotedb.QuoteDB(
            docommit=vebyastquotebot.quotedb.QuoteDBCommit[os.environ['QUOTE_DB_COMMIT']],
            commit_message='/remove (by {}#{})'.format(message.author.name, message.author.discriminator),
    ) as quote:
        before = len(quote.quotes)
        for quote_id in args.quote_id:
            quote.remove_quote(quote_id)
        after = len(quote.quotes)

    await client.edit_message(feedback, "Done with /remove! Removed {nremoved} quotes.".format(
        nremoved = before - after,
    ))

@command('/get')
async def get_quote(*, message, feedback, argstring):
    parserio = io.StringIO()
    lexed = shlex.split(argstring)
    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/get',
        description='Get a quote.',
        outfile=parserio,
    )
    parser.add_argument('quote_id',
                        type=int,
                        help='The id of the quote to be quoted.')
    try:
        args = parser.parse_args(args=lexed)
    except (vebyastquotebot.throwingargumentparser.ArgumentParserError,
            vebyastquotebot.throwingargumentparser.ArgumentParserExited):
        await client.edit_message(feedback, '```' + parserio.getvalue() + '```')
        return
    finally:
        parserio.close()

    await client.edit_message(feedback, "Processed command. Getting quote...")

    with vebyastquotebot.quotedb.QuoteDB(
            docommit=vebyastquotebot.quotedb.QuoteDBCommit.READONLY,
    ) as quote:
        if args.quote_id not in quote.index:
            await client.edit_message(feedback, "Could not find quote with ID {quoteid}.".format(
                quoteid = args.quote_id,
            ))
        else:
            q = quote.index[args.quote_id]
            await client.edit_message(feedback, "```{quoteformat}```".format(
                quoteformat = '\n'.join(
                    '[{ts}] {user}: {content}'.format(
                        ts=line['timestamp'],
                        user=line['author'],
                        content=line['content'],
                    ) for line in q['lines']
                )
            ))

logging.basicConfig(level=logging.INFO)
client.run(os.environ['DISCORD_BOT_TOKEN'])
