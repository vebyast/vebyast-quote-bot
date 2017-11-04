import discord
import os
import logging
import logging.handlers
from pythonjsonlogger import jsonlogger
import pyparsing as ps
import shlex
import datetime
import vebyastquotebot.helpformatter
import vebyastquotebot.quotedb
import vebyastquotebot.searching
import vebyastquotebot.throwingargumentparser
import io
import asyncio
import sys
import json

LOG_FILENAME = 'vebyastquotebot.log'

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# log to rotating logfiles
rotating_handler = logging.handlers.RotatingFileHandler(
    LOG_FILENAME,
    maxBytes=20000000,
    backupCount=3,
)
rotating_handler.setFormatter(
    jsonlogger.JsonFormatter(" ".join("%({0})".format(l) for l in [
        'asctime',
        'filename',
        'pathname',
        'funcname',
        'levelname',
        'lineno',
        'message',
    ]))
)
logger.addHandler(rotating_handler)
# plus log to stderr
logger.addHandler(logging.StreamHandler())
logging.info("Startup!")

DEFAULT_LIMIT = 1000

COMMANDS = {}
def command(name):
    def fun(f):
        COMMANDS[name] = f
        return f
    return fun

client = discord.Client()

def extra_custom(**kwargs):
    return { 'extra': { 'custom' : {
        **kwargs,
        'client_username': client.user.name if client.user else ""
    } } }

@client.event
async def on_ready():
    logging.info('Successfully logged in', **extra_custom(
        uid = client.user.id,
        discriminator = client.user.discriminator,
    ))


async def delete_if_x(reaction, user):
    # ignore reactions that aren't on our own messages
    if reaction.message.author != client.user:
        return

    if reaction.emoji == '❌':
        logger.info("Deleting own post on X reaction", **extra_custom(
            user_responsible = user.name,
            reaction = reaction.emoji,
        ))
        await client.delete_message(reaction.message)

@client.event
async def on_reaction_add(reaction, user):
    try:
        logger.info('Received reaction', **extra_custom(
            emoji = reaction.emoji,
            is_me = user == client.user,
        ))

        # ignore reactions that we made ourself
        if user == client.user:
            return

        await delete_if_x(reaction, user)

    except Exception as e:
        logging.error(e, **extra_custom())
        raise e


def public_message_parse(command_line):
    try:
        parseresult = (
            ('<@' + ps.Optional('!') + client.user.id + '>').setResultsName('user_id')
            + ps.restOfLine.setResultsName('command_line')
        ).parseString(command_line)
        return (parseresult['command_line'], None)
    except ps.ParseException as e:
        return (None, e)

def command_line_parse(command_line):
    try:
        return ((
            ps.Or(ps.CaselessKeyword(com) for com in COMMANDS.keys()).setResultsName('command') +
            ps.restOfLine.setResultsName('argstring')
        ).parseString(command_line), None)
    except ps.ParseException as e:
        return (None, e)

def channel_id_parse(arg):
    try:
        p = ps.Or((
            ps.Word(ps.nums).setResultsName('channel_id'),
            '<#' + ps.Word(ps.nums).setResultsName('channel_id') + '>',
        ))
        return (p.parseString(arg)['channel_id'], None)
    except ps.ParseException as e:
        return (None, e)

async def handle_channel_arg(arg):
    (channel_id, e) = channel_id_parse(arg)
    if not channel_id:
        return (None, "Error reading channel: {}".format(str(e)))
    channel = client.get_channel(channel_id)
    if not channel:
        return (None, "Channel not found")
    return (channel, None)

async def argstring_parse(argstring, parser, parserio):
    try:
        lexed = shlex.split(argstring)
    except Exception as e:
        return (None, "Could not parse command string: {}".format(str(e)))

    try:
        args = parser.parse_args(args=lexed)
    except (vebyastquotebot.throwingargumentparser.ArgumentParserError) as e:
        return (None, vebyastquotebot.quotedb.wrap_triple(str(e)))
    except (vebyastquotebot.throwingargumentparser.ArgumentParserExited) as e:
        return (None, vebyastquotebot.quotedb.wrap_triple(parserio.getvalue()))
    return (args, None)


def parseable(message):
    command_line = message.content
    if message.server:
        (command_line, _) = public_message_parse(command_line)
        if not command_line:
            return False
    (parse_result, _) = command_line_parse(command_line)
    return bool(parse_result)

def find_message_filter_predicate(message):
    return ((message.author != client.user) and not parseable(message))

async def user_exists(user_id):
    try:
        await client.get_user_info(user_id)
        return True
    except discord.NotFound:
        return False

def channel_exists(channel_id):
    return not not client.get_channel(channel_id)

async def handle_message_arg(id_arg, query_arg, limit, channel):
    message = None
    err = None
    if id_arg:
        message_id = id_arg
        try:
            message = await client.get_message(channel, message_id)
        except discord.errors.NotFound as e:
            if await user_exists(message_id):
                suggestion = "It's a valid user ID, though; did you misclick?"
            elif channel_exists(message_id):
                suggestion = "It's a valid channel ID, though; did you misclick?"
            else:
                suggestion = "Do you need a different `--channel`?"

            return (None, "Could not find message with ID {m_id}: {err}. {suggestion}".format(
                m_id = message_id,
                err = str(e),
                suggestion = suggestion,
            ))
    elif query_arg:
        (message, err) = await vebyastquotebot.searching.find_message(
            client=client,
            querystring=query_arg,
            limit=limit,
            channel=channel,
            predicate=find_message_filter_predicate,
        )

    if not message:
        return (None, "Could not find message: {}".format(err))
    return (message, err)

@client.event
async def on_message(message):
    # sorceror's apprentice protection, hopefully
    if message.author == client.user:
        return

    command_line = message.content
    if message.server:
        (command_line, _) = public_message_parse(command_line)
        if not command_line:
            # public channel and it doesn't parse as a command to us, so ignore
            # it.  there'll be a ton of this, so don't even bother logging it
            return

    (parseresult, _) = command_line_parse(command_line)
    if not parseresult:
        return

    feedback = await client.send_message(message.channel, 'Received command {}. Processing...'.format(parseresult.command))

    logging.info('handling command', **extra_custom(
        command = parseresult.command,
        argstring = parseresult.argstring,
        messageid = message.id,
    ))

    try:
        await COMMANDS[parseresult.command](
            message=message,
            argstring=parseresult.argstring,
            feedback=feedback)

        logging.info('successfully handled command', **extra_custom(
            command = parseresult.command,
            argstring = parseresult.argstring,
            messageid = message.id,
        ))
    except Exception as e:
        await client.edit_message(feedback, "Error executing {}".format(parseresult.command))
        logging.error(e, **extra_custom(
            command = parseresult.command,
            argstring = parseresult.argstring,
            messageid = message.id,
        ))
        raise e
    finally:
        await client.add_reaction(feedback, '❌')

@command('/add')
async def command_addquote(*, message, feedback, argstring):
    parserio = io.StringIO()

    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/add',
        description='add a quote.',
        outfile=parserio,
        formatter_class=vebyastquotebot.helpformatter.QuotebotHelpFormatter,
    )
    start_group = parser.add_mutually_exclusive_group(required=True)
    start_group.add_argument(
        '-S', '--start_id',
        type=int,
        help='The start of the quote, identified using a message ID. Get the ID using developer mode: User Settings -> Appearance -> Developer Mode, then right-click and Get ID.')
    start_group.add_argument(
        '-s', '--start_query',
        type=str,
        help='''The start of the quote, identified using a "quoted set of words" that will be looked for in recent messages. Words need not be contiguous or in order. This line of help-text, for example, would be found by a query like '--start "search start contiguous"'.''')

    end_group = parser.add_mutually_exclusive_group(required=True)
    end_group.add_argument(
        '-E', '--end_id',
        type=int,
        help='The end of the quote, identified using a message ID. Get the ID using developer mode: User Settings -> Appearance -> Developer Mode, then right-click and Get ID.')
    end_group.add_argument(
        '-e', '--end_query',
        type=str,
        help='''The end of the quote, identified using a "quoted set of words" that will be looked for in recent messages. Words need not be contiguous or in order. This line of help-text, for example, would be found by a query like '--start "search end contiguous"'.''')

    parser.add_argument(
        '-c', '--channel',
        type=str,
        help='The channel to pull quotes from. Must be a clickable channel link.')

    parser.add_argument(
        '-n', '--noop',
        action='store_true',
        help="""Don't do the final upload. For testing purposes.""")

    (args, args_err) = await argstring_parse(argstring, parser, parserio)
    if not args:
        await client.edit_message(feedback, args_err)
        return

    if not args.channel:
        channel = message.channel
    else:
        (channel, channel_err) = await handle_channel_arg(args.channel)
        if not channel:
            await client.edit_message(feedback, channel_err)
            return

    limit = DEFAULT_LIMIT

    (start_message, start_err) = await handle_message_arg(args.start_id, args.start_query, limit, channel)
    (end_message, end_err) = await handle_message_arg(args.end_id, args.end_query, limit, channel)

    if not start_message or not end_message:
        errs = []
        if not start_message:
            errs.append(start_err)
        if not end_message:
            errs.append(end_err)
        await client.edit_message(feedback, '\n'.join(errs))
        return

    if start_message.channel != end_message.channel:
        # this should never happen. just in case, though...
        await client.edit_message(feedback, 'Error in /add: Start and end messages must be from the same channel.')
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

    if len(logs) == limit:
        await client.edit_message(feedback, "Got exactly {limit} logs. If your quote is long it may have been truncated, so the add has been aborted. Specify a larger limit? See `--help`".format(
            limit=limit,
        ))
        return

    await client.edit_message(feedback, "Got logs. Processing logs..." + quote_message)

    json_obj = {
        'id': str(message.id),  # reuse the id of the command message, but
                                # tostring because javascript is shit
        'lines': [vebyastquotebot.quotedb.message_to_json(log) for log in logs],
        'quoted': datetime.datetime.utcnow().isoformat(),
        'server': channel.server.name if channel.server else 'Private Messages',
        'channel': channel.name or 'Private Messages',
    }

    await client.edit_message(feedback, "Processed logs. Saving and uploading..." + quote_message)

    log_args = {
        'num_lines': len(json_obj['lines']),
        'quote_id': json_obj['id'],
        'quote_block': quote_block,
        'quote_url': os.environ['USER_INTERFACE_URL'] + '#/quote_id/' + str(json_obj['id']),
    }

    if not args.noop:
        with vebyastquotebot.quotedb.QuoteDB(
                docommit=vebyastquotebot.quotedb.QuoteDBCommit[os.environ['QUOTE_DB_COMMIT']],
                commit_message='/add (by {}#{})'.format(message.author.name, message.author.discriminator),
        ) as quote:
            quote.add_quote(json_obj)

        await client.edit_message(feedback, "Done with /add! Quoted {quote_block} ({num_lines} lines).\nResult (maybe after a wait): <{quote_url}>".format(**log_args))
        logging.info('adding quote', **extra_custom(**log_args))
    else:
        await client.edit_message(feedback, "NOOP passed, but /add would have been Done: {result} ({nlines} lines).".format(**log_args))
        logging.info('adding quote with noop', **extra_custom(**log_args))

@command('/remove')
async def remove_quote(*, message, feedback, argstring):
    parserio = io.StringIO()
    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/remove',
        description='remove a quote.',
        outfile=parserio,
        formatter_class=vebyastquotebot.helpformatter.QuotebotHelpFormatter,
    )
    parser.add_argument(
        'quote_id',
        type=str,
        action='append',
        help='ID of a quote to be deleted. Can be given multiple times.')
    (args, args_err) = await argstring_parse(argstring, parser, parserio)
    if not args:
        await client.edit_message(feedback, args_err)
        return

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
    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/get',
        description='get a quote.',
        outfile=parserio,
        formatter_class=vebyastquotebot.helpformatter.QuotebotHelpFormatter,
    )
    parser.add_argument('quote_id',
                        type=str,
                        help='The ID of the quote to be quoted.')
    (args, args_err) = await argstring_parse(argstring, parser, parserio)
    if not args:
        await client.edit_message(feedback, args_err)
        return

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
            await client.edit_message(feedback, vebyastquotebot.quotedb.format_quote(q))

@command('/clear')
@command('/clean')
async def clean(*, message, feedback, argstring):
    parserio = io.StringIO()
    parser = vebyastquotebot.throwingargumentparser.ThrowingArgumentParser(
        prog='/clean',
        description='''Cleans up this bot's outputs.''',
        outfile=parserio,
        formatter_class=vebyastquotebot.helpformatter.QuotebotHelpFormatter,
    )
    volume_group = parser.add_mutually_exclusive_group(required=True)
    volume_group.add_argument(
        '-n', '--count',
        type=int,
        help='''Clean up this bot's messages going back this many messages in the channel.''')
    volume_group.add_argument(
        '-m', '--minutes',
        type=int,
        help='''Clean up this bot's messages going back this many minutes in the channel.''')

    parser.add_argument(
        '-c', '--channel',
        type=str,
        help='Channel to clean up.')

    (args, args_err) = await argstring_parse(argstring, parser, parserio)
    if not args:
        await client.edit_message(feedback, args_err)
        return

    if not args.channel:
        channel = message.channel
    else:
        (channel, err) = await handle_channel_arg(args.channel)
        if not channel:
            await client.edit_message(feedback, err)
            return

    await client.edit_message(feedback, "Processed command. Deleting posts ...")

    if args.minutes:
        log_args = {
            'after': datetime.datetime.utcnow() - datetime.timedelta(minutes=args.minutes),
            'limit': DEFAULT_LIMIT,
        }
    elif args.count:
        log_args = {
            'limit': min(args.count, DEFAULT_LIMIT),
        }

    ndeletes = 0
    async for log in client.logs_from(
            channel=channel,
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
    logging.error("Need to set the QUOTE_DB_COMMIT environment variable to one of the following values: {}".format(
        ', '.join(en.name for en in vebyastquotebot.quotedb.QuoteDBCommit)
    ))
    sys.exit(1)

if 'DISCORD_BOT_TOKEN' not in os.environ:
    logging.error('Need to set the DISCORD_BOT_TOKEN environment variable')
    sys.exit(1)

if 'USER_INTERFACE_URL' not in os.environ:
    logging.error('Need to set the USER_INTERFACE_URL environment variable')
    sys.exit(1)

client.run(os.environ['DISCORD_BOT_TOKEN'])
