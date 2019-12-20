import os
import sys
import random
import ujson as json
import uuid
import asyncio
import asyncio_redis
import calendar
from datetime import datetime, timedelta
from multiprocessing import Process, Queue
from decimal import *

try:
    sys.path.append(os.path.abspath('./'))
except Exception as e:
    print(str(e.args))
    exit(1)

import uvloop
from japronto import Application

uvloop.install()
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
asyncio.set_event_loop(uvloop.new_event_loop())

CUSTOMERS = []
ACCOUNTS = []
CREDIT_CARDS = []
MOVEMENTS = []
TRANSACTIONS = []

lists = {
    "accounts": ACCOUNTS,
    "credit_cards": CREDIT_CARDS,
    "customers": CUSTOMERS,
    "movements": MOVEMENTS,
    "transactions": TRANSACTIONS
}

json_attributes = [
    'origin',
    'target',
    'type',
    'number',
    'customer_id',
    'id',
    'account',
    'account_id',
    'alias',
    'brand',
    'transaction_id'
]

port = int(os.getenv('PORT', 8080))

redis_params = {
    'host': os.getenv('REDIS_SERVER', '127.0.0.1'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASSWORD', None),
    'poolsize': int(os.getenv('REDIS_POOL', 7))
}

conn = None
queue = Queue()
app = Application(debug=False)
rt = app.router


def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)


def serialize(process_queue):
    async def redis_serialize(p_queue):

        async def push(key, items):
            values = [ujson.dumps(item) for item in items]
            if len(values) > 0:
                await redis_conn.rpush(key, values)

        redis_conn = await asyncio_redis.Pool.create(**redis_params)

        while True:
            obj = ujson.loads(p_queue.get())
            keys = [i.lower() for i in obj["data"]]
            tasks = [push(k, v) for k, v in obj["lists"].items()]
            if len(keys) > 0:
                await redis_conn.delete(keys)
            await asyncio.gather(*tasks)

    try:
        import concurrent
        import selectors
        import asyncio
        import asyncio_redis
        import ujson

        executor = concurrent.futures.ThreadPoolExecutor()
        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(selector)
        loop.set_default_executor(executor)
        asyncio.set_event_loop(loop)
        asyncio.ensure_future(redis_serialize(process_queue))
        loop.run_forever()

    except Exception as exception:
        print(str(exception.args))
        exit(1)


def handle_response(request, response, code, message, make_json=True):
    response['response']['code'] = code
    response['response']['message'] = message
    return request.Response(json=response) if make_json else response


def generic(product, error_message, request, make_json=True, condition='OR'):
    message = dict(response=dict(code=1, message="Something is wrong."))
    try:
        if request.method == 'GET':
            args = request.query
            for item in product:
                if 'brand' in item:
                    today = datetime.today()
                    court_date = datetime(
                        today.year,
                        today.month,
                        item['court_date']
                    )
                    if court_date > datetime(today.year, today.month, 1):
                        next_payment_day = \
                            datetime(
                                today.year,
                                today.month,
                                item['court_date']
                            ) + timedelta(days=15)
                    else:
                        if today.month < 12:
                            next_payment_day = \
                                datetime(
                                    today.year,
                                    today.month + 1,
                                    item['court_date']
                                ) + timedelta(days=15)
                        else:
                            next_payment_day = \
                                datetime(
                                    today.year + 1,
                                    1,
                                    item['court_date']
                                ) + timedelta(days=15)
                    item['next_payment_day'] = next_payment_day
                    item['next_payment_day'] = item['next_payment_day'].strftime("%m/%d/%Y")
            if not args:
                return handle_response(request, message, 0, product, make_json)
            else:
                content = error_message
                for k, v in args.items():
                    if k in json_attributes:
                        content = []
                        for item in product:
                            if v in [
                                item[attribute] if attribute in item else ''
                                for attribute in json_attributes
                            ]:
                                content.append(item)
                if condition == 'AND':
                    for k, v in args.items():
                        counter = len(content)
                        i = 0
                        while i < counter:
                            if content[i][k] != v:
                                content.remove(content[i])
                                counter -= 1
                            else:
                                i += 1

                return handle_response(request, message, 0, content, make_json)
        else:
            return handle_response(request, message, 2, "Method Not Allowed", make_json)
    except Exception as exception:
        message['response']['error'] = str(exception.args)
        return request.Response(json=message) if make_json else message


def debit(transaction):
    global MOVEMENTS

    result = 0
    before = 0
    successful = False
    if transaction['origin_type'] == 'ACCOUNTS':
        for a in ACCOUNTS:
            available_balance = Decimal(a['available_balance'])
            if a['number'] == transaction['origin'] and \
                    available_balance > transaction['amount'] and \
                    a['type'] != 'loan':
                before = a['available_balance']
                result = available_balance - transaction['amount']
                a['available_balance'] = '{0:.2f}'.format(result)
                successful = True
                break
    elif transaction['origin_type'] == 'CREDIT_CARDS':
        for a in CREDIT_CARDS:
            available_quota = Decimal(a['available_quota'])
            if a['number'] == transaction['origin'] and \
                    available_quota > transaction['amount']:
                before = a['available_quota']
                result = available_quota - transaction['amount']
                a['available_quota'] = '{0:.2f}'.format(result)
                successful = True
                break
    if successful:
        MOVEMENTS.append(
            {
                "transaction_id": transaction["id"],
                "date": transaction["date"],
                "account": transaction["origin"],
                "amount": str(transaction["amount"]),
                "description": transaction["description"],
                "before": before,
                "after": '{0:.2f}'.format(result),
                "type": "DEBIT" if transaction["amount"] > 0 else "CREDIT"
            }
        )
    return successful


def accredit(transaction):
    global MOVEMENTS

    result = 0
    before = 0
    successful = False
    if transaction['target_type'] == 'ACCOUNTS':
        for a in ACCOUNTS:
            if a['number'] == transaction['target']:
                before = a['available_balance']
                if a['type'] == 'savings':
                    result = Decimal(a['available_balance']) + transaction['amount']
                elif a['type'] == 'loan':
                    result = Decimal(a['available_balance']) - transaction['amount']
                a['available_balance'] = '{0:.2f}'.format(result)
                successful = True
                break
    elif transaction['target_type'] == 'CREDIT_CARDS':
        for a in CREDIT_CARDS:
            if a['number'] == transaction['target']:
                before = a['available_quota']
                result = Decimal(a['available_quota']) + transaction['amount']
                a['available_quota'] = '{0:.2f}'.format(result)
                successful = True
                break

    if successful:
        MOVEMENTS.append(
            {
                "transaction_id": transaction["id"],
                "date": transaction["date"],
                "account": transaction["target"],
                "amount": str(transaction["amount"]),
                "description": transaction["description"],
                "before": before,
                "after": '{0:.2f}'.format(result),
                "type": "CREDIT"
            }
        )
    return successful


async def transfers(request):
    global TRANSACTIONS

    message = dict(
        response=dict(
            code=1,
            message="Sorry, your transaction can't be completed!"
        )
    )
    try:
        successful = False
        if request.method == 'POST':
            input_body = request.json
            transaction = {
                "id": str(uuid.uuid4()),
                "date": datetime.now().strftime("%m/%d/%Y, %H:%M:%S"),
                "type": input_body['type'],
                "origin": input_body['origin'],
                "origin_type": input_body['origin_type'],
                "target": input_body['target'],
                "target_type": input_body['target_type'],
                "description": input_body['description'],
                "amount": Decimal(input_body['amount'])
            }
            if input_body['type'] == 'FOUNDS_TRANSFER':
                if debit(transaction):
                    if accredit(transaction):
                        successful = True
                    else:
                        transaction['amount'] = transaction['amount'] * -1
                        debit(transaction)
            elif input_body["type"] == "DEBIT":
                successful = debit(transaction)
            elif input_body["type"] == "CREDIT":
                successful = accredit(transaction)
            if successful:
                transaction["amount"] = str(transaction["amount"])
                TRANSACTIONS.append(transaction)
                data = {
                    "data": ['ACCOUNTS', 'CREDIT_CARDS', 'MOVEMENTS', 'TRANSACTIONS'],
                    "lists": lists
                }
                queue.put(json.dumps(data))
                return handle_response(request, message, 0, "Transaction completed successfully!")
            else:
                return handle_response(request, message, 0, "Sorry, your transaction can't be completed!")
        else:
            return handle_response(request, message, 2, "Method Not Allowed")
    except Exception as exception:
        return handle_response(
            request,
            message,
            1,
            "Sorry, your data is wrong. %s" % str(exception.args)
        )


def credit_cards_statement(request):
    global CREDIT_CARDS
    global MOVEMENTS
    current_credit_card_movements = []
    message = dict(response=dict(code=1, message="Not enough arguments."))
    args = request.query
    try:
        if len(args) > 0 and ('number' in args or ('brand' in args and 'customer_id' in args)):
            response = generic(
                CREDIT_CARDS,
                'Wrong Credit Card Number',
                request,
                False,
                'AND'
            )['response']
            if response['code'] == 0 and len(response['message']) > 0:
                credit_card = response['message'][0]
                request.query["account"] = credit_card['number']
                del request.query["brand"]
                credit_card_movements = generic(
                    MOVEMENTS,
                    'Wrong Credit Card Number',
                    request,
                    False
                )['response']['message']
                next_court_day = datetime.strptime(
                    credit_card['next_payment_day'],
                    "%m/%d/%Y"
                ) - timedelta(days=15)
                last_court_day = add_months(next_court_day, -1)
                total_to_payment = Decimal("0.0")
                for movement in credit_card_movements:
                    movement_date = datetime.strptime(movement['date'].split(',')[0], "%m/%d/%Y")
                    if last_court_day < movement_date < next_court_day:
                        current_credit_card_movements.append(movement)
                        if movement['type'] == 'DEBIT':
                            total_to_payment += Decimal(movement['amount'])
                        elif movement['type'] == 'CREDIT':
                            total_to_payment -= Decimal(movement['amount'])
                return handle_response(
                    request,
                    message,
                    0,
                    {
                        "credit_card": credit_card["obfuscated"],
                        "last_court_day": last_court_day.strftime("%m/%d/%Y"),
                        "next_court_day": next_court_day.strftime("%m/%d/%Y"),
                        "total_to_payment": str(total_to_payment),
                        "next_payment_day": credit_card["next_payment_day"],
                        "movements": current_credit_card_movements
                    }
                )
        else:
            return handle_response(request, message, 1, 'Not enough arguments.')
    except Exception as e:
        return handle_response(
            request,
            message,
            1,
            "Sorry, your data is wrong. %s" % str(e.args)
        )


async def fill(request):
    global lists
    message = dict(response=dict(code=1, message="Something is wrong."))
    try:
        if request.method == 'GET':
            if len(lists['accounts']) == 0:
                for customer in lists['customers']:
                    if int(customer["id"]) % 2 != 0:
                        loan_account = {
                            "customer_id": customer["id"],
                            "number": str(random.randint(100000, 200000)),
                            "available_balance": '10000.00',
                            "alias": 'Crédito',
                            "type": "loan"
                        }
                        loan_account["obfuscated"] = ''.join(
                            [
                                'XXXX',
                                loan_account["number"][-2:]
                            ]
                        )
                        lists['accounts'].append(loan_account)
                        last_code = str(random.randint(5000, 6000))
                        credit_card = {
                            "customer_id": customer["id"],
                            "number": '-'.join(
                                [
                                    '4118',
                                    str(random.randint(7000, 8000)),
                                    str(random.randint(3000, 4000)),
                                    last_code
                                ]
                            ),
                            "obfuscated": ''.join(['4118-XXXX-XXXX-', last_code]),
                            "brand": "Visa Titanium",
                            "alias": 'Tarjeta de Crédito',
                            "available_quota": '3000.00',
                            "court_date": 1
                        }
                        lists['credit_cards'].append(credit_card)

                    deposit_account = {
                        "customer_id": customer["id"],
                        "number": str(random.randint(100000, 200000)),
                        "available_balance": '1000.00',
                        "alias": 'Ahorros',
                        "type": "savings"
                    }
                    deposit_account["obfuscated"] = ''.join(
                        [
                            'XXXX',
                            deposit_account["number"][-2:]
                        ]
                    )
                    lists['accounts'].append(deposit_account)
                    last_code = str(random.randint(5000, 6000))
                    credit_card = {
                        "customer_id": customer["id"],
                        "number": '-'.join(
                            [
                                '3608',
                                str(random.randint(670200, 880200)),
                                last_code
                            ]
                        ),
                        "obfuscated": ''.join(['3608-XXXXXX-', last_code]),
                        "brand": "Diners Club",
                        "alias": 'Tarjeta de Crédito',
                        "available_quota": '1500.00',
                        "court_date": 24
                    }
                    lists['credit_cards'].append(credit_card)
                    data = {
                        "data": ['ACCOUNTS', 'CREDIT_CARDS'],
                        "lists": lists
                    }
                    queue.put(json.dumps(data))
                resp = handle_response(request, message, 0, 'Accounts & Credit Cards created!')
            else:
                resp = handle_response(request, message, 0, "Accounts & Credit Cards already exist!")
        else:
            resp = handle_response(request, message, 2, "Method Not Allowed")

    except Exception as e:
        message['response']['error'] = str(e.args)
        resp = request.Response(json=message)
    finally:
        return resp


async def clear(request):
    global lists
    message = dict(response=dict(code=1, message="Something is wrong."))
    try:
        if request.method == 'GET':
            await conn.flushdb()
            [v.clear() for k, v in lists.items()]
            resp = handle_response(request, message, 0, 'FLUSH DB OK!')
        else:
            resp = handle_response(request, message, 2, "Method Not Allowed")

    except Exception as exception:
        message['response']['error'] = str(exception.args)
        resp = request.Response(json=message)
    finally:
        return resp


async def customer_register(request):
    global CUSTOMERS
    message = dict(response=dict(code=1, message="Sorry, your data is wrong."))
    try:
        if request.method == 'POST':
            input_body = request.json
            user_exist = False
            for customer in CUSTOMERS:
                if customer["email"] == input_body["email"]:
                    message['response']['message'] = "User already exist!"
                    user_exist = True
                    break
            if not user_exist:
                message['response']['code'] = 0
                message['response']['message'] = "".join(
                    [
                        "Hello ",
                        input_body["name"],
                        ' ',
                        input_body["last_name"],
                        " your mail ",
                        input_body["email"],
                        " is registered. Thank you"
                    ]
                )
                input_body["id"] = str(len(CUSTOMERS) + 1)
                CUSTOMERS.append(input_body)
                data = {
                    "data": ['CUSTOMERS'],
                    "lists": lists
                }
                queue.put(json.dumps(data))
            return request.Response(json=message)
        else:
            return handle_response(request, message, 2, "Method Not Allowed")
    except Exception as exception:
        message['response']['error'] = str(exception.args)
        return handle_response(request, message, 1, "Sorry, your data is wrong.")


def credit_cards(request, condition='OR'):
    global CREDIT_CARDS
    return generic(CREDIT_CARDS, 'Wrong Account Id', request, condition)


def customers(request):
    global CUSTOMERS
    return generic(CUSTOMERS, 'Client not exist.', request)


def accounts(request):
    global ACCOUNTS
    return generic(ACCOUNTS, 'Wrong Account Id', request)


def movements(request):
    global MOVEMENTS
    return generic(MOVEMENTS, 'Wrong Account Id', request)


def transactions(request):
    global TRANSACTIONS
    return generic(TRANSACTIONS, 'Wrong Transaction Id', request)


def root(request):
    with open('./static/index.html') as html_file:
        return request.Response(text=html_file.read(), mime_type='text/html')


async def main():
    global lists
    global conn
    global redis_params

    try:
        conn = await asyncio_redis.Pool.create(**redis_params)

        redis_accounts = (await conn.lrange('accounts', 0, -1))._result
        redis_credit_cards = (await conn.lrange('credit_cards', 0, -1))._result
        redis_customers = (await conn.lrange('customers', 0, -1))._result
        redis_movements = (await conn.lrange('movements', 0, -1))._result
        redis_transactions = (await conn.lrange('transactions', 0, -1))._result

        if redis_accounts.count > 0 or redis_credit_cards.count > 0 or redis_customers.count > 0:
            [lists['accounts'].append(json.loads(account)) for account in redis_accounts._data_queue]
            [lists['credit_cards'].append(json.loads(credit_card)) for credit_card in redis_credit_cards._data_queue]
            [lists['customers'].append(json.loads(customer)) for customer in redis_customers._data_queue]
            [lists['movements'].append(json.loads(movement)) for movement in redis_movements._data_queue]
            [lists['transactions'].append(json.loads(transaction)) for transaction in redis_transactions._data_queue]

        p = Process(name='serializer', target=serialize, args=(queue,))
        p.start()
        print("Process SERIALIZER was created with PID: %s" % str(p.pid))

    except Exception as e:
        if e.args[0] != "This event loop is already running":
            print(
                "Can't connect to REDIS Server %s PORT %s" %
                (redis_params['host'], redis_params['port'])
            )
            print(e.args[0])


if __name__ == "__main__":
    asyncio.run(main())
    rt.add_route('/', root)
    rt.add_route('/fill', fill)
    rt.add_route('/clear', clear)
    rt.add_route('/accounts', accounts)
    rt.add_route('/movements', movements)
    rt.add_route('/customers', customers)
    rt.add_route('/customers/register', customer_register)
    rt.add_route('/transactions', transactions)
    rt.add_route('/transfers', transfers)
    rt.add_route('/credit_cards', credit_cards)
    rt.add_route('/credit_cards/statement', credit_cards_statement)
    app.run(host="0.0.0.0", port=port)
