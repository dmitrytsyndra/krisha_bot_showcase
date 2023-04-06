import telebot
from telebot import types
import time
from datetime import timedelta
import uuid
from .user_connection import execute
import logging
from yookassa import Configuration, Payment
from yookassa import Payment #зайти в доку юмани и попросить доступ по телефону доступ как юзера, созданы 2 организации, нужна тестовая, поменять 16 и 17 строку
from .reciept import get_reciept, get_token
import requests
from . import headlines
from ..utils.nalog_proxy_switcher import make_proxy_revolver, switch_proxy #надо импортить функции
tb = telebot.TeleBot('6026665986:AAHW4j5U5eM3BBFWzGGzvHVBmdng-QjzRnI')
log = logging.getLogger('bot')
Configuration.account_id = '930545'
Configuration.secret_key = 'live_r60h7T8ZlqDDlHGzTF_RqSYJIqqeS5-vhRuRqpCBLo0'


@tb.message_handler(commands=['start', 'go'])
def start_handler(message):
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("Алматы"), types.KeyboardButton(
        "Астана"), types.KeyboardButton("Актобе"))
    markup.add(types.KeyboardButton("Атырау"), types.KeyboardButton(
        "Семей"), types.KeyboardButton("Петропавловск"))
    markup.add(types.KeyboardButton("Актау"), types.KeyboardButton(
        "Шымкент"), types.KeyboardButton("Павлодар"))
    markup.add(types.KeyboardButton("Караганда"), types.KeyboardButton(
        "Усть-Каменогорск"), types.KeyboardButton("Экибастуз"))
    markup.add(types.KeyboardButton("Купить недельную подписку"))
    log.debug(f'Start chat {message.chat.id}')
    msg = tb.send_message(message.chat.id, f'*Добро пожаловать, {message.from_user.first_name}!*\n\n Я - бот, который поможет получать информацию с сайта krisha.kz быстрее всех. Я умею находить только квартиры от хозяев и на долгосрочный период.\n\nДля продолжения выберите город\n\n_По любым вопросам можете обращаться к моими разработчикам_\n@notifysupport',  reply_markup=markup, parse_mode='Markdown')
    execute('add', **{'id': message.from_user.id, 'city': 'нет'})
    tb.register_next_step_handler(msg, add_function)


@tb.message_handler(content_types=["text"])
def add_function(message):
    if message.text.strip() == 'Купить недельную подписку':
        log.info(f'User - {message.chat.id} start payment')
        check = execute('check', **{'id': message.from_user.id})
        idempotence_key = uuid.uuid4()
        payment = Payment.create({
            "amount": {
                "value": f"{99}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/krisha_notification_info_bot"
            },
            "capture": True,
            "description": f"Заказ пользователя {check[0]} на сумму {99}"
        }, idempotence_key)
        tb.send_message(
            message.chat.id, f'*Ссылка на оплату через ЮКассу:*\n\n{payment.confirmation.confirmation_url}', parse_mode='Markdown')
        processed = False
        for _ in range(5):
            payment_id = payment.id
            payment = Payment.find_one(payment_id)
            if payment.status == 'succeeded':
                processed = True
                break
            elif payment.status == 'canceled':
                processed = True
                break
            else:
                time.sleep(100)
        if processed == False:
            log.error(f'User - {message.chat.id} didnt wait payment')
            msg = tb.send_message(
                check[0], f'*❌ Не удалось провести оплату.* В случае ошибки обратитесь в поддержку @notifysupport', parse_mode='Markdown')
            tb.register_next_step_handler(msg, add_function)
        elif payment.status == 'succeeded':
            log.info(f'User - {message.chat.id} success payment')
            tb.send_message(check[0], headlines.wait, parse_mode='Markdown')
            reciept_link = None
            # вот это хорошо, но дальше надо что то сделать если с проксями все плохо
            proxy = make_proxy_revolver()
            proxy_ping = requests.get(
                'https://lknpd.nalog.ru/', proxies=proxy)
            for i in range(5):
                if not proxy_ping.ok:
                    proxy = switch_proxy() 
                else:
                    break

            if i + 1 == 5:
                log.error(
                    f'User - {message.chat.id} cannot get token because of invalid lknpd proxy'
                )
            else:
                for _ in range(5):
                    try:
                        token = get_token(proxies=proxy)
                        reciept_link = get_reciept(
                            price=int(payment.amount.value), token=token, proxies=proxy)
                        break
                    except Exception as e:
                        log.error(
                            f'User - {message.chat.id} nalog cannot get reciept error {e}')
                    time.sleep(5)

            if reciept_link == None:
                msg = tb.send_message(
                    message.chat.id, f'*✅ Баланс успешно пополнен на {int(payment.amount.value)} рублей.*{headlines.cannot_get_reciept}\nМы продлим вашу подписку на неделю.', parse_mode='Markdown')
            else:
                msg = tb.send_message(
                    message.chat.id, f'*✅ Баланс успешно пополнен на {int(payment.amount.value)} рублей.*\n\nСсылка на чек: {reciept_link}\nМы продлим вашу подписку на неделю.', parse_mode='Markdown')
            execute('update_week', **{'id': message.from_user.id})
            tb.register_next_step_handler(msg, add_function)
        elif payment.status == 'canceled':
            log.error(f'User - {message.chat.id} cancel payment')
            msg = tb.send_message(
                message.chat.id, f'*❌ Не удалось провести оплату.* В случае ошибки обратитесь в поддержку @notifysupport', parse_mode='Markdown')
            tb.register_next_step_handler(msg, add_function)
            log.error(f'User - {message.chat.id} canceled payment')
    else:
        try:
            log.debug(
                f'User {message.chat.id} choose city {message.text.strip()}')
            execute('add', **{'id': message.from_user.id,
                    'city': message.text.strip()})
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True, one_time_keyboard=True)
            markup.add(types.KeyboardButton("Алматы"), types.KeyboardButton(
                "Астана"), types.KeyboardButton("Актобе"))
            markup.add(types.KeyboardButton("Атырау"), types.KeyboardButton(
                "Семей"), types.KeyboardButton("Петропавловск"))
            markup.add(types.KeyboardButton("Актау"), types.KeyboardButton(
                "Шымкент"), types.KeyboardButton("Павлодар"))
            markup.add(types.KeyboardButton("Караганда"), types.KeyboardButton(
                "Усть-Каменогорск"), types.KeyboardButton("Экибастуз"))
            markup.add(types.KeyboardButton("Купить недельную подписку"))
            msg = tb.send_message(
                message.chat.id, f'Успешно выбран город {message.text.strip()}.\n\nКогда в городе появятся квартиры от хозяев на долгосрочный период, я пришлю уведомление!', parse_mode='Markdown', reply_markup=markup)
            tb.register_next_step_handler(msg, add_function)
        except Exception as e:
            log.error(f'{message.chat.id} error {e}')
            msg = tb.send_message(
                message.chat.id, f'Возникла ошибка {e}', parse_mode='Markdown')


add_function("Купить недельную подписку")
tb.polling(none_stop=True, interval=0)
