import os
import sys
import random
import ujson as json
import uuid
import asyncio
import asyncio_redis
import calendar
import concurrent
import selectors
from datetime import datetime, timedelta
from decimal import *

try:
    sys.path.append(os.path.abspath('./'))
except Exception as ex:
    print(str(ex.args))
    exit(1)

from quart import send_from_directory
from quart import Quart, request, jsonify

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

delete_query_strings = [
    "apikey",
    "secret",
    "secretid",
    "cientid",
    "api-key",
    "secret-id",
    "client_id",
    "code",
    "error"
]

app = Quart(__name__)
if not hasattr(sys, 'loop'):
    executor = concurrent.futures.ThreadPoolExecutor()
    selector = selectors.SelectSelector()
    sys.loop = asyncio.SelectorEventLoop(selector)
    sys.loop.set_default_executor(executor)
    asyncio.set_event_loop(sys.loop)
conn = None


def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)


async def serialize(data):
    global lists

    async def push(key, items):
        values = [json.dumps(item) for item in items]
        if len(values) > 0:
            await conn.rpush(key, values)

    try:
        keys = [i.lower() for i in data]
        if len(keys) > 0:
            await conn.delete(keys)

        tasks = [push(k, v) for k, v in lists.items()]
        await asyncio.gather(*tasks)

    except Exception as ex:
        print(str(ex))
        raise ex


def handle_response(response, code, message, make_jsonify=True):
    response['response']['code'] = code
    response['response']['message'] = message
    return jsonify(response) if make_jsonify else response


def generic(product, error_message, args, make_jsonify=True, condition='OR'):
    message = dict(response=dict(code=1, message="Something is wrong."))
    try:
        if request.method == 'GET':
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
            for k, v in args.items():
                if k in delete_query_strings:
                    del args[k]
            if len(args) == 0:
                return handle_response(message, 0, product, make_jsonify)
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

                return handle_response(message, 0, content, make_jsonify)
        else:
            return handle_response(message, 2, "Method Not Allowed", make_jsonify)
    except Exception as ex:
        message['response']['error'] = str(ex.args)
        return jsonify(message) if make_jsonify else message


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


@app.route("/transfers", methods=['POST'])
async def transfers():
    global CUSTOMERS
    global TRANSACTIONS
    global MOVEMENTS
    global ACCOUNTS
    global CREDIT_CARDS

    message = dict(
        response=dict(
            code=1,
            message="Sorry, your transaction can't be completed!"
        )
    )
    try:
        successful = False
        if request.method == 'POST':
            input_body = await request.json
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
                        transaction['amount'] *= -1
                        debit(transaction)
            elif input_body["type"] == "DEBIT":
                successful = debit(transaction)
            elif input_body["type"] == "CREDIT":
                successful = accredit(transaction)
            resp = jsonify(message)
            if successful:
                TRANSACTIONS.append(transaction)
                resp = handle_response(message, 0, "Transaction completed successfully!")
                asyncio.ensure_future(
                    serialize(['ACCOUNTS', 'CREDIT_CARDS', 'MOVEMENTS', 'TRANSACTIONS']),
                    loop=sys.loop
                )
        else:
            resp = handle_response(message, 2, "Method Not Allowed")
    except Exception as ex:
        resp = handle_response(
            message,
            1,
            "Sorry, your data is wrong. %s" % str(ex.args)
        )
    finally:
        return resp


@app.route("/credit_cards", methods=['GET'])
def credit_cards(condition='OR'):
    global CREDIT_CARDS
    args = request.args
    return generic(CREDIT_CARDS, 'Wrong Account Id', args, condition)


@app.route("/credit_cards/statement", methods=['GET'])
def credit_cards_statement():
    global CREDIT_CARDS
    global MOVEMENTS
    current_credit_card_movements = []
    message = dict(response=dict(code=1, message="Not enough arguments."))
    resp = handle_response(message, 1, 'Not enough arguments.')
    args = request.args
    try:
        if len(args) > 0 and ('number' in args or ('brand' in args and 'customer_id' in args)):
            response = generic(
                CREDIT_CARDS,
                'Wrong Credit Card Number',
                args,
                False,
                'AND'
            )['response']
            if response['code'] == 0 and len(response['message']) > 0:
                credit_card = response['message'][0]
                credit_card_movements = generic(
                    MOVEMENTS,
                    'Wrong Credit Card Number',
                    {'account': credit_card['number']},
                    False
                )['response']['message']
                next_court_day = datetime.strptime(
                    credit_card['next_payment_day'],
                    "%m/%d/%Y") - timedelta(days=15)
                last_court_day = add_months(next_court_day, -1)
                total_to_payment = Decimal("0.0")
                for movement in credit_card_movements:
                    movement_date = datetime.strptime(
                        movement['date'].split(',')[0],
                        "%m/%d/%Y"
                    )
                    if last_court_day < movement_date < next_court_day:
                        current_credit_card_movements.append(movement)
                        if movement['type'] == 'DEBIT':
                            total_to_payment += Decimal(movement['amount'])
                        elif movement['type'] == 'CREDIT':
                            total_to_payment -= Decimal(movement['amount'])
                resp = handle_response(
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
            resp = handle_response(message, 1, 'Not enough arguments.')
    except Exception as ex:
        resp = handle_response(
            message,
            1,
            "Sorry, your data is wrong. %s" % str(ex.args)
        )
    finally:
        return resp


@app.route("/accounts", methods=['GET'])
def accounts():
    global ACCOUNTS
    args = request.args
    return generic(ACCOUNTS, 'Wrong Account Id', args)


@app.route("/movements", methods=['GET'])
def movements():
    global MOVEMENTS
    args = request.args
    return generic(MOVEMENTS, 'Wrong Account Id', args)


@app.route("/transactions", methods=['GET'])
def transactions():
    global TRANSACTIONS
    args = request.args
    return generic(TRANSACTIONS, 'Wrong Transaction Id', args)


@app.route("/fill", methods=['GET'])
def fill():
    global CUSTOMERS
    message = dict(response=dict(code=1, message="Something is wrong."))
    try:
        if request.method == 'GET':
            if len(ACCOUNTS) == 0:
                for customer in CUSTOMERS:
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
                        ACCOUNTS.append(loan_account)
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
                        CREDIT_CARDS.append(credit_card)

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
                    ACCOUNTS.append(deposit_account)
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
                    CREDIT_CARDS.append(credit_card)
                    asyncio.ensure_future(
                        serialize(['ACCOUNTS', 'CREDIT_CARDS']),
                        loop=sys.loop
                    )
                resp = handle_response(message, 0, 'Accounts & Credit Cards created!')
            else:
                resp = handle_response(message, 0, "Accounts & Credit Cards already exist!")
        else:
            resp = handle_response(message, 2, "Method Not Allowed")

    except Exception as ex:
        message['response']['error'] = str(ex.args)
        resp = jsonify(message)
    finally:
        return resp


@app.route("/clear", methods=['GET'])
async def clear():
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


@app.route("/customers", methods=['GET'])
def customers():
    global CUSTOMERS
    args = request.args
    return generic(CUSTOMERS, 'Client not exist.', args)


@app.route("/customers/register", methods=['POST'])
async def customer_register():
    global CUSTOMERS
    message = dict(response=dict(code=1, message="Sorry, your data is wrong."))
    try:
        if request.method == 'POST':
            input_body = await request.json
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
                asyncio.ensure_future(serialize(['CUSTOMERS']), loop=sys.loop)
            resp = jsonify(message)
        else:
            resp = handle_response(message, 2, "Method Not Allowed")
    except Exception as ex:
        message['response']['error'] = str(ex.args)
        resp = handle_response(message, 1, "Sorry, your data is wrong.")
    finally:
        return resp


async def main():
    global lists
    global app
    global conn

    try:
        conn = await asyncio_redis.Pool.create(
            host=os.getenv('REDIS_SERVER', '127.0.0.1'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD'),
            poolsize=int(os.getenv('REDIS_POOL', 7))
        )

        for k, v in lists.items():
            data = await conn.lrange(k, 0, -1)
            for i in data:
                v.append(json.loads(await i))

        app.run(
            host="0.0.0.0",
            port=int(os.getenv('PORT', 8080)),
            debug=False,
            loop=sys.loop
        )
    except Exception as ex:
        if ex.args[0] != "This event loop is already running":
            print(
                "Can't connect to REDIS Server %s PORT %s" %
                (
                    os.getenv('REDIS_SERVER', '127.0.0.1'),
                    int(os.getenv('REDIS_PORT', 6379))
                )
            )
            print(ex.args[0])


@app.route('/')
def root():
    global app
    return app.send_static_file('index.html')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )


if __name__ == "__main__":
    asyncio.ensure_future(main())
    sys.loop.run_forever()
