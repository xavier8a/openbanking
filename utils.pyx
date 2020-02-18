import ujson
from datetime import datetime, timedelta

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


json_attributes = [
        "origin",
        "target",
        "type",
        "number",
        "customer_id",
        "id",
        "account",
        "account_id",
        "alias",
        "brand",
        "transaction_id"
    ]


def handle_response(request, response, code, message, make_json=True):
    response['response']['code'] = code
    response['response']['message'] = message
    return request.Response(json=response) if make_json else response


def generic(product, error_message, request, make_json=True, condition='OR'):
    message = dict(response=dict(code=1, message="Something is wrong."))
    try:
        if request.method == 'GET':
            args = {}
            pre_args = request.query
            for k, v in pre_args.items():
                if k not in delete_query_strings:
                    args[k] = v
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
