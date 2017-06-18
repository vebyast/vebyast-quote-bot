import discord
import os
import logging
import pyparsing as ps
import shlex
import datetime
import vebyastquotebot.quotedb
import vebyastquotebot.searching
import vebyastquotebot.throwingargumentparser
import io
import asyncio
import sys

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

COMMANDS = {}
def command(name):
    def fun(f):
        COMMANDS[name] = f
        return f
    return fun

client = discord.Client()

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print(client.user.discriminator)
    print('------')

def public_message_parse(command_line):
    try:
        parseresult = (
            ps.Keyword('<@' + client.user.id + '>').setResultsName('user_id') +
            ps.restOfLine.setResultsName('command_line')
        ).parseString(command_line)
        return parseresult['command_line']
    except ps.ParseException:
        return None

def command_line_parse(command_line):
    try:
        return (
            ps.Or(ps.CaselessKeyword(com) for com in COMMANDS.keys()).setResultsName('command') +
            ps.restOfLine.setResultsName('argstring')
        ).parseString(command_line)
    except ps.ParseException:
        return None

@client.event
async def on_message(message):
    # sorceror's apprentice protection, hopefully
    if message.author == client.user:
        return

    command_line = message.content
    if message.server:
        command_line = public_message_parse(command_line)
        if not command_line:
            # public channel and it doesn't parse as a command to us, so ignore
            # it.  there'll be a ton of this, so don't even bother logging it
            return

    parseresult = command_line_parse(command_line)
    if not parseresult:
        # feedback = await client.send_message(message.channel, 'No command recognized. Try `@{} /help`?'.format(
        #     client.user.display_name,
        # ))
        return

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
    try:
        lexed = shlex.split(argstring)
    except Exception as e:
        await client.edit_message(feedback, "Could not parse command string: {}".format(str(e)))
        return

    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/add',
        description='Add a quote.',
        outfile=parserio,
    )
    start_group = parser.add_mutually_exclusive_group(required=True)
    start_group.add_argument('-S', '--start_id',
                             type=int,
                             help='The id of the first line of the quote, obtained using the discord developer mode')
    start_group.add_argument('-s', '--start',
                             type=str,
                             help='A string to locate the first line of the quote. Does an unordered full-text fuzzy search over recent messages.')

    end_group = parser.add_mutually_exclusive_group(required=True)
    end_group.add_argument('-E', '--end_id',
                           type=int,
                           help='The id of the last line of the quote, obtained using the discord developer mode')
    end_group.add_argument('-e', '--end',
                           type=str,
                           help='A string to locate the last line of the quote. Does an unordered full-text fuzzy search over recent messages.')
    parser.add_argument('--limit',
                        type=int,
                        help='Maximum number of lines to pull')
    parser.add_argument('--around',
                        type=int,
                        help='The fuzzy start and end arguments search recent history. If you want to search older history, this argument will instruct the bot to search around an id for the start and end arguments.')

    try:
        args = parser.parse_args(args=lexed)
    except (vebyastquotebot.throwingargumentparser.ArgumentParserError,
            vebyastquotebot.throwingargumentparser.ArgumentParserExited) as e:
        await client.edit_message(feedback, vebyastquotebot.quotedb.wrap_triple(str(e)))
        return
    finally:
        parserio.close()

    limit = args.limit or DEFAULT_LIMIT
    limit = min(limit, MAX_LIMIT)

    def parseable(message):
        command_line = message.content
        if message.server:
            command_line = public_message_parse()
            if not command_line:
                return False
        parse_result = command_line_parse(command_line)
        return bool(parse_result)

    def find_message_filter_predicate(message):
        return ((message.author != client.user) and not parseable(message))

    if args.start_id:
        start_id = args.start_id
        start_message = await client.get_message(message.channel, start_id)
    elif args.start:
        (start_message, start_message_err) = await vebyastquotebot.searching.find_message(
            client=client,
            feedback=feedback,
            querystring=args.start,
            limit=limit,
            channel=message.channel,
            predicate=find_message_filter_predicate,
        )
    if not start_message:
        await client.edit_message(feedback, "Could not find start message: " + start_message_err)
        return

    if args.end_id:
        end_id = args.end_id
        end_message = await client.get_message(message.channel, end_id)
    elif args.end:
        (end_message, end_message_err) = await vebyastquotebot.searching.find_message(
            client=client,
            feedback=feedback,
            querystring=args.end,
            limit=limit,
            channel=message.channel,
            predicate=find_message_filter_predicate,
        )
    if not end_message:
        await client.edit_message(feedback, "Could not find end message: " + end_message_err)
        return

    if start_message.channel != end_message.channel:
        await client.edit_message(feedback, 'Error in /add: Messages must be from the same channel.')
        return

    start_block = vebyastquotebot.quotedb.format_message(start_message, short=30, wrap=True)
    end_block = vebyastquotebot.quotedb.format_message(end_message, short=30, wrap=True)
    quote_block = '{start_block} to {end_block}'.format(
        start_block=start_block,
        end_block=end_block,
    )
    quote_message = ' (quoting: ' + quote_block + ')'

    await client.edit_message(feedback, "Processed command. Getting logs..." + quote_message)

    logs = await vebyastquotebot.searching.pull_logs(
        client=client,
        start_message=start_message,
        end_message=end_message,
        limit=limit,
    )

    await client.edit_message(feedback, "Got logs. Processing logs..." + quote_message)

    json_obj = {
        'id': int(message.id),  # reuse the id of the command message
        'lines': [vebyastquotebot.quotedb.message_to_quotehash(log) for log in logs],
        'quoted': datetime.datetime.utcnow().isoformat(),
    }

    await client.edit_message(feedback, "Processed logs. Saving and uploading..." + quote_message)

    with vebyastquotebot.quotedb.QuoteDB(
            docommit=vebyastquotebot.quotedb.QuoteDBCommit[os.environ['QUOTE_DB_COMMIT']],
            commit_message='/add (by {}#{})'.format(message.author.name, message.author.discriminator),
    ) as quote:
        quote.add_quote(json_obj)

    await client.edit_message(feedback, "Done with /add! Quote ID: {quote_id}. Quoted {nlines}: {result}\nYou can view this bot's quotes at <{ui}>".format(
        nlines=len(json_obj['lines']),
        quote_id=json_obj['id'],
        result=quote_block,
        ui=os.environ['USER_INTERFACE_URL']
    ))

@command('/remove')
async def remove_quote(*, message, feedback, argstring):
    parserio = io.StringIO()
    try:
        lexed = shlex.split(argstring)
    except Exception as e:
        await client.edit_message(feedback, "Could not parse command string: {}".format(str(e)))
        return

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
            vebyastquotebot.throwingargumentparser.ArgumentParserExited) as e:
        await client.edit_message(feedback, vebyastquotebot.quotedb.wrap_triple(str(e)))
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
        await client.edit_message(feedback, "Removed {nremoved} quotes. Uploading changes...".format(
            nremoved = before - after,
        ))

    await client.edit_message(feedback, "Done with /remove! Removed {nremoved} quotes.".format(
        nremoved = before - after,
    ))

@command('/get')
async def get_quote(*, message, feedback, argstring):
    parserio = io.StringIO()
    try:
        lexed = shlex.split(argstring)
    except Exception as e:
        await client.edit_message(feedback, "Could not parse command string: {}".format(str(e)))
        return

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
            vebyastquotebot.throwingargumentparser.ArgumentParserExited) as e:
        await client.edit_message(feedback, vebyastquotebot.quotedb.wrap_triple(str(e)))
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
            await client.edit_message(feedback, vebyastquotebot.quotedb.format_quotehashes(q))

@command('/clean')
async def clean(*, message, feedback, argstring):
    parserio = io.StringIO()
    try:
        lexed = shlex.split(argstring)
    except Exception as e:
        await client.edit_message(feedback, "Could not parse command string: {}".format(str(e)))
        return

    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/clean',
        description='''Cleans up this bot's outputs.''',
        outfile=parserio,
    )
    volume_group = parser.add_mutually_exclusive_group(required=True)
    volume_group.add_argument('-c', '--count',
                              type=int,
                              help='Clean up all logs going back this many messages in the channel')
    volume_group.add_argument('-m', '--minutes',
                              type=int,
                              help='Clean up all logs going back this many minutes')
    try:
        args = parser.parse_args(args=lexed)
    except (vebyastquotebot.throwingargumentparser.ArgumentParserError,
            vebyastquotebot.throwingargumentparser.ArgumentParserExited) as e:
        await client.edit_message(feedback, vebyastquotebot.quotedb.wrap_triple(str(e)))
        return
    finally:
        parserio.close()

    await client.edit_message(feedback, "Processed command. Deleting posts ...")

    if args.minutes:
        log_args = {
            'after': datetime.datetime.utcnow() - datetime.timedelta(minutes=args.minutes),
            'limit': DEFAULT_LIMIT,
        }
    elif args.count:
        log_args = {
            'limit': min(args.count, MAX_LIMIT),
        }

    ndeletes = 0
    async for log in client.logs_from(
            channel=message.channel,
            **log_args
    ):
        if log.author == client.user and log.id != feedback.id:
            ndeletes += 1
            await client.delete_message(log)

    await client.edit_message(feedback, "Deleted {ndeletes} posts.".format(
        ndeletes=ndeletes,
    ))
    await asyncio.sleep(15)
    await client.delete_message(feedback)

@command('/help')
@command('help')
@command('--help')
async def print_help(*, message, feedback, argstring):
    await client.edit_message(
        feedback,
        '\n'.join([
            '```usage: @{} /command [arguments]'.format(client.user.display_name),
            '',
            'A bot for saving quotes from a discord server.',
            '',
            'Available commands:',
            '',
            '  {command:15} {help}'.format(command='/add', help='''Add a quote to the database'''),
            '  {command:15} {help}'.format(command='/remove', help='''Remove a quote from the database'''),
            '  {command:15} {help}'.format(command='/get', help='''Print out a quote from the database'''),
            '  {command:15} {help}'.format(command='/clean', help='''Clean up this bot's output'''),
            '  {command:15} {help}'.format(command='/help', help='''Output this message'''),
            '',
            'Issue "@{} /command --help" for help with each individual command.'.format(client.user.display_name),
            '',
            'Quotes uploaded using this bot can be viewed at {}.'.format(os.environ['USER_INTERFACE_URL']),
            '```'
        ])
    )

if 'QUOTE_DB_COMMIT' not in os.environ:
    print("Need to set the QUOTE_DB_COMMIT environment variable to one of the following values: {}".format(
        ', '.join(en.name for en in vebyastquotebot.quotedb.QuoteDBCommit)
    ), file=sys.stderr)
    sys.exit(-1)

if 'DISCORD_BOT_TOKEN' not in os.environ:
    print('Need to set the DISCORD_BOT_TOKEN environment variable', file=sys.stderr)
    sys.exit(-1)

if 'USER_INTERFACE_URL' not in os.environ:
    print('Need to set the USER_INTERFACE_URL environment variable', file=sys.stderr)
    sys.exit(-1)

logging.basicConfig(level=logging.INFO)
client.run(os.environ['DISCORD_BOT_TOKEN'])
