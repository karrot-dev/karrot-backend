from base64 import b64encode

import telegram
from django.core import signing
from django.core.management import BaseCommand
from telegram import Bot
from telegram.ext import Updater, CommandHandler

TOKEN = '572241187:AAGu2lyeYJSyLqeOcRmr4S1tlD4BTeBedPs'


def addgroup(bot, update):
    try:
        chat_id = update['message']['chat']['id']
        print('chat id is', chat_id)
        encoded = b64encode(signing.dumps([chat_id]).encode('utf8')).decode('utf8')

        text = 'Hello {} go to karrot.world and paste in this token:\n```\n{}\n```\n'.format(
            update.message.from_user.first_name, encoded)
        bot.send_message(chat_id=chat_id, text=text, parse_mode=telegram.ParseMode.MARKDOWN)

    except Exception as e:
        print('exception!', e)


class Command(BaseCommand):

    def handle(self, *args, **options):
        bot = Bot(token=TOKEN)
        updater = Updater(bot=bot)
        updater.dispatcher.add_handler(CommandHandler('addgroup', addgroup))
        updater.start_polling()
        updater.idle()
