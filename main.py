import discord
import asyncio
import os
import pyparsing as ps
import async_timeout
import json
import datetime
import git
import requests
import logging

COMMANDS = {}
def command(name):
    def fun(f):
        COMMANDS[name] = f
        return None
    return fun

client = discord.Client()
public_message_parser = None

async def fetch(session, url):
    with async_timeout.timeout(10):
        async with session.get(url) as response:
            return await response.text()

async def log(st, logfun, feedback):
    logfun(st)
    await client.edit_message(feedback, st)

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

    global public_message_parser
    global pm_message_parser
    pm_message_parser = (
        ps.Or(ps.CaselessKeyword(com) for com in COMMANDS.keys()) +
        ps.restOfLine
    )
    public_message_parser = (
        ps.Suppress('<@' + client.user.id + '>') +
        pm_message_parser
    )

@client.event
async def on_message(message):
    try:
        if (message.server):
            (command, rest) = public_message_parser.parseString(message.content)
        else:
            (command, rest) = pm_message_parser.parseString(message.content)
    except ps.ParseException:
        return
    feedback = await client.send_message(message.channel, 'Received command {}...'.format(command))
    try:
        await COMMANDS[command](message, rest, feedback)
    except Exception as e:
        await log("Error executing {}: {}".format(command, str(e)),
                  logging.info, feedback)

@command('/add')
async def command_addquote(message, rest, feedback):
    parser = ps.Word(ps.alphanums)
    try:
        (pastebin_id,) = parser.parseString(rest)
    except ps.ParseException:
        await log("Error in /add: Malformed pastebin target: {}".format(rest),
                  logging.info, feedback)
        return

    url = 'https://pastebin.com/raw/' + pastebin_id
    await log("/add: fetching quotes from {}".format(url),
              logging.info, feedback)
    loop = asyncio.get_event_loop()
    request_future = loop.run_in_executor(None, requests.get, url)
    request = await request_future
    await add_quote(request.text.splitlines(), message, feedback)


def parse_users(quotelines):
    user_parser = (
        ps.Suppress('[' + ps.OneOrMore(ps.Word(ps.alphanums + ':')) + ']') +
        ps.Regex('[^:]+') +
        ps.Suppress(':') +
        ps.Suppress(ps.restOfLine)
    )

    def extract_name(line):
        try:
            (uname,) = user_parser.parseString(line)
            uname = ''.join(uname)
            return uname
        except ps.ParseException:
            print("parse_users: failed to parse line" + line)
            return None
    unames = {extract_name(line) for line in quotelines}
    if None in unames:
        unames.remove(None)
    return unames


async def add_quote(quotelines, message, feedback):
    await log("/add: Parsing users...", logging.info, feedback)
    users = parse_users(quotelines)

    # HORRIBLE HACK, I PREDICT PERFORMANCE PROBLEMS. To make the javascript
    # easier, this file stays as valid json. However, json is not easy to append
    # to. What we'll do here, as a hideous kludge that *will* cause performance
    # problems down the road but is fast to write, is we'll parse the entire
    # file as json, append to it, and then write it back.
    await log("/add: Adding new quote...", logging.info, feedback)
    with open('quotes.json', 'r') as jsf:
        quotes = json.load(jsf)

    maxid = max(q["id"] for q in quotes)
    newid = maxid + 1
    quotes.append({
        'id': newid,
        'users': list(users),
        'uploaded': datetime.datetime.utcnow().isoformat(),
        'lines': quotelines,
    })

    await log("/add: Writing quotes back...", logging.info, feedback)
    with open('quotes.json', 'w') as jsf:
        json.dump(quotes, jsf, indent=2)
    # END HORRIBLE HACK
    await commit("add quote (submitted by {})".format(str(message.author)), feedback)
    await log("Quote added with id {}!".format(newid), logging.info, feedback)

async def commit(commit_message, feedback):
    await log("Committing changes...", logging.info, feedback)
    repo = git.Repo(os.getcwd())
    repo.index.add(['quotes.json'])
    repo.index.commit(commit_message)

    if "DO_PUSH" in os.environ and os.environ["DO_PUSH"]:
        await log("Pushing changes...", logging.info, feedback)
        origin = repo.remote()
        origin.push()
        await log("Pushed changes!", logging.info, feedback)
    else:
        await log("Done! Not pushing because debug mode.", logging.info, feedback)

@command('/remove')
async def remove_quote(message, rest, feedback):
    await log("/remove: Updating quotes...", logging.info, feedback)
    ref_parser = (
        ps.Word(ps.nums),
    )
    try:
        (quote_id,) = ref_parser.parseString(rest)
    except ps.ParseException:
        await log("Error in /remove: Malformed quote id: {}".format(rest),
                  logging.info, feedback)
        return

    await log("/remove: Removing quote with id {}...".format(quote_id),
              logging.info, feedback)
    with open('quotes.json', 'r') as jsf:
        quotes = json.load(jsf)

    quotes = [quote for quote in quotes if quote["id"] != int(quote_id)]

    await log("/remove: Writing quotes back...", logging.info, feedback)
    with open('quotes.json', 'w') as jsf:
        json.dump(quotes, jsf, indent=2)

    await commit("remove quote (submitted by {})".format(str(message.author)), feedback)
    await log("Quote with id {} removed.".format(quote_id), logging.info, feedback)


logging.basicConfig(level=logging.INFO)
client.run(os.environ['DISCORD_BOT_TOKEN'])
