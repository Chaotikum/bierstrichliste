#!/usr/bin/env python3

import asyncio
import yaml
import re
import json
import pickle
from aiohttp import web

from monads import *


class Beverage:
    def __init__(self, name, price):
        self.name = name
        self.price = price

    def toDict(self):
        return dict(name=self.name, price=self.price)

    def __repr__(self):
        return "Beverage(name=%s, price=%f)" % (self.name, self.price)


class Account:
    def __init__(self, nick, balance=0):
        self.nick = nick
        self.balance = balance
        self.history = []

    def drink(self, beverage):
        if self.balance >= beverage.price:
            self.balance -= beverage.price
            self.history.append("hat %s getrunken" % beverage)
            return Right(self)
        else:
            return Left("Nicht genug Guthaben um %s zu trinken" % beverage)

    def topup(self, amount):
        # TODO validate amount somehow

        if amount < 0:
            return Left("Betrag muss positiv sein")
        else:
            self.balance += amount
            self.history.append("hat %s aufgeladen" % amount)
            return Right(self)

    def toJSON(self):
        return json.dumps(dict(nick=self.nick, balance=self.balance, history=self.history))

    def __repr__(self):
        return "Account(nick=%s, balance=%f)" % (self.nick, self.balance)


class BeverageManager:
    def __init__(self, config):
        self.accounts = dict()
        self.config = config
        self.beverages = dict()

        for beverage in config["beverages"]:
            self.beverages[beverage["name"]] = Beverage(**beverage)

        self.load()

    def load(self):
        try:
            self.accounts = pickle.load(open("accounts.dat", "rb"))
        except Exception as e:
            print(e)

    def save(self):
        pickle.dump(self.accounts, open("accounts.dat", "wb"))

    def change(self, msg):
        self.save()
        self.stream(msg)

    def newAccount(self, nick):
        if not re.match("^[a-zA-Z0-9_]{3,20}", nick):
            return Left("Ungültiger Nickname")

        if not nick in self.accounts:
            account = Account(nick)
            self.accounts[nick] = account
            self.change(("Account %s angelegt" % account))
            return Right(account)
        else:
            return Left("Account existiert bereits")

    def drink(self, nick, beverageName):
        if not nick in self.accounts:
            return Left("Account existiert nicht")
        elif not beverageName in self.beverages:
            return Left("Unbekanntes Getränk")
        else:
            beverage = self.beverages[beverageName]
            account = self.accounts[nick]
            r = account.drink(beverage)

            if type(r) is Right:
                self.change("%s hat %s getrunken" % (account, beverage))

            return r

    def topup(self, nick, amount):
        if not nick in self.accounts:
            return Left("Account existiert nicht")
        else:
            account = self.accounts[nick]
            r = account.topup(amount)

            if type(r) is Right:
                self.change("%s um %s aufgeladen" % (account, amount))

            return r

    def getAccount(self, nick):
        if not nick in self.accounts:
            return Left("Account existiert nicht")
        else:
            return Right(self.accounts[nick])

    def getAccounts(self):
        return list(map(lambda x: dict(nick=x.nick, balance=x.balance), self.accounts.values()))

    def getBeverages(self):
        return list(map(lambda x: x.toDict(), self.beverages.values()))


class Webserver:
    def __init__(self, host, port, manager):
        self.host = host
        self.port = port
        self.queues = set()
        self.manager = manager
        self.manager.stream = self.stream

    def stream(self, msg):
        for queue in set(self.queues):
            queue.put_nowait(msg)

        print(msg)

    @asyncio.coroutine
    def handle_get_stream(self, request):
        stream = web.StreamResponse()
        stream.content_type = "text/event-stream"
        stream.start(request)

        queue = asyncio.Queue()

        self.queues.add(queue)

        while True:
            stream.write(b"data: " + json.dumps(self.manager.getAccounts()).encode("UTF-8") + b"\n\n")
            msg = yield from queue.get()
            #stream.write(b"data: " + msg.encode("UTF-8") + b"\n\n")

    @asyncio.coroutine
    def handle_get_beverages(self, request):
        return web.Response(content_type="application/json", body=json.dumps(self.manager.getBeverages()).encode("UTF-8"))

    @asyncio.coroutine
    def handle_put_drink(self, request):
        text = yield from request.text()
        r = self.manager.drink(request.match_info.get("nick"), text)

        if type(r) is Right:
            return web.Response(body="ACK".encode("UTF-8"))
        else:
            return web.Response(status=400, body=r.value.encode("UTF-8"))

    @asyncio.coroutine
    def handle_post_account(self, request):
        text = yield from request.text()
        r = self.manager.newAccount(text)

        if type(r) is Right:
            return web.Response(body="ACK".encode("UTF-8"))
        else:
            return web.Response(status=400, body=r.value.encode("UTF-8"))

    @asyncio.coroutine
    def handle_put_topup(self, request):
        text = yield from request.text()

        try:
            amount = float(text)
            r = self.manager.topup(request.match_info.get("nick"), amount)
        except ValueError:
            r = Left("Ungültiger Betrag")

        if type(r) is Right:
            return web.Response(body="ACK".encode("UTF-8"))
        else:
            return web.Response(status=400, body=r.value.encode("UTF-8"))

    @asyncio.coroutine
    def handle_get_account(self, request):
        r = self.manager.getAccount(request.match_info.get("nick"))

        if type(r) is Right:
            return web.Response(content_type="application/json", body=r.value.toJSON().encode("UTF-8"))
        else:
            return web.HTTPNotFound()

    @asyncio.coroutine
    def start(self, loop):
        app = web.Application(loop=loop)
        app.router.add_route("GET", "/stream", self.handle_get_stream)
        app.router.add_route("GET", "/account/{nick}", self.handle_get_account)
        app.router.add_route("GET", "/beverages", self.handle_get_beverages)
        app.router.add_route("PUT", "/account/{nick}/drink", self.handle_put_drink)
        app.router.add_route("PUT", "/account/{nick}/topup", self.handle_put_topup)
        app.router.add_route("POST", "/account", self.handle_post_account)

        return (yield from loop.create_server(app.make_handler(), self.host, self.port))


if __name__ == "__main__":
    config = yaml.load(open("config.yaml"))

    manager = BeverageManager(config)

    webserver = Webserver("localhost", config["port"], manager)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(webserver.start(loop))
    loop.run_forever()
