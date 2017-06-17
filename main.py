import discord
import asyncio
import os
import pyparsing as ps
import aiohttp
import async_timeout

COMMANDS = {}
def command(name):
    def fun(f):
        COMMANDS[name] = f
        return None
    return fun

client = discord.Client()
message_parser = None

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

    global message_parser
    message_parser = (
        ps.Suppress('<@' + client.user.id + '>') +
        ps.Or(ps.CaselessKeyword(com) for com in COMMANDS.keys()) +
        ps.restOfLine
    )

@client.event
async def on_message(message):
    print("message: ", message.content)
    try:
        (command, rest) = message_parser.parseString(message.content)
    except ps.ParseException as p:
        print("parse failure: ", p)
        return
    await COMMANDS[command](message, rest)

async def fetch(session, url):
    with async_timeout.timeout(10):
        async with session.get(url) as response:
            return await response.text()

@command('!quote')
async def command_quote(message, rest):
    parser = ps.Word(ps.alphanums)
    try:
        (pastebin_id,) = parser.parseString(rest)
    except ps.ParseException:
        print("!quote: malformed pastebin target: ", rest)

    print(pastebin_id)
    url = 'https://pastebin.com/raw/' + pastebin_id
    async with aiohttp.ClientSession(loop=asyncio.get_event_loop()) as session:
        html = await fetch(session, url)
        print(html)

client.run(os.environ['DISCORD_BOT_TOKEN'])
