#!/usr/bin/env python
# encoding: utf-8

import hashlib

import math
import wget
import logging

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, TelegramError
from telegram.ext import Updater, CallbackQueryHandler
from telegram.ext import CommandHandler
from lxml import etree
from StringIO import StringIO
import requests
import sys

reload(sys)
sys.setdefaultencoding('utf8')

CHAT_ID = 00000 # your Telegram User ChatId with the bot
TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
DOWN_TORRENT = '/where/to/store/downloaded/torrents/'
URL_DOMAIN = 'https://descargas2020.com'
DOWNLOAD_TORRENT_START = '//descargas2020.com/descargar-torrent/'

cached_movies = {}


def start_callback(bot, update):
    chat_id = update.message.chat_id
    if chat_id != CHAT_ID:
        bot.send_message(chat_id=chat_id, text="Ups. No tienes permisos para usar este bot!")
        return
    send_menu(bot, None)


def menu_callback(bot, update):
    chat_id = update.callback_query.message.chat_id
    if chat_id != CHAT_ID:
        bot.send_message(chat_id=chat_id, text="Ups. No tienes permisos para usar este bot!")
        return
    bot.answerCallbackQuery(callback_query_id=update.callback_query.id)
    send_menu(bot, update.callback_query.message.message_id)


def send_menu(bot, message_id):
    btn = InlineKeyboardButton(text="Últimas películas MicroHD", callback_data="list.1")
    kbs = [btn]
    markup = InlineKeyboardMarkup(inline_keyboard=[kbs])
    html = "<b>Raspberry Pi</b>\nElige entre las opciones disponibles:"
    if message_id is None:
        bot.send_message(chat_id=CHAT_ID,
                         text=html,
                         parse_mode="HTML",
                         reply_markup=markup)
    else:
        bot.editMessageText(chat_id=CHAT_ID,
                            message_id=message_id,
                            text=html,
                            parse_mode="HTML",
                            reply_markup=markup)


def download_callback(bot, update):
    chat_id = update.callback_query.message.chat_id
    if chat_id != CHAT_ID:
        bot.send_message(chat_id=chat_id, text="Ups. No tienes permisos para usar este bot!")
        return
    key = int(update.callback_query.data.replace('down.', ''))
    movie = cached_movies[key]
    if movie is None:
        bot.send_message(chat_id=chat_id, text="Ups. No se encuentra la peli!")
        return
    html = get_tree(movie["link"])
    script = html.xpath("//a[@class='btn-torrent']/following-sibling::node()[2]/text()")[0]
    idx = script.find("\"" + DOWNLOAD_TORRENT_START) + 1
    end = script.find("\"", idx)
    torrent = 'http:' + script[idx:end]
    wget.download(torrent, out=DOWN_TORRENT + str(key) + '.torrent')
    bot.answerCallbackQuery(callback_query_id=update.callback_query.id, text='Fichero torrent descargado!')

    message_id = update.callback_query.message.message_id
    movie_page = movie["page"]
    movie_name = movie["name"]
    url = 'https://www.filmaffinity.com/es/search.php?stext=' + movie_name
    kbs = [[InlineKeyboardButton(text="Buscar en Filmaffinity", url=url)],
           [InlineKeyboardButton(text="<< Volver <<", callback_data="list." + str(movie_page))]]
    markup = InlineKeyboardMarkup(inline_keyboard=kbs)
    html = get_movie_detail_html(movie)
    bot.editMessageText(chat_id=CHAT_ID,
                        message_id=message_id,
                        text=html,
                        parse_mode="HTML",
                        reply_markup=markup)


def get_movie_detail(movie):
    if "detail" in movie:
        return movie["detail"]
    html = get_tree(movie["link"])
    type_nodes = html.xpath("//div[@class='page-box']/h1/strong/following-sibling::text()")
    sinopsis_nodes = html.xpath("//div[@class='sinopsis']/text()")
    size_nodes = html.xpath("//div[@class='entry-left']/span[@class='imp']/text()")
    return {
        "type": type_nodes[0].strip() if len(type_nodes) > 0 else "-",
        "sinopsis": sinopsis_nodes[0].strip() if len(sinopsis_nodes) > 1 else "-",
        "size": size_nodes[0].strip() if len(size_nodes) > 1 else "-"
    }


def get_movie_detail_html(movie):
    if "detail" not in movie:
        movie["detail"] = get_movie_detail(movie)
    movie_detail = movie["detail"]
    html = '<b>' + movie["name"] + '</b>\n\n'
    html += '<b>Tipo:</b> <i>' + movie_detail["type"] + "</i>\n"
    html += '<b>Tamaño:</b> <i>' + movie_detail["size"] + "</i>\n"
    html += '<b>Sinopsis:</b> <i>' + movie_detail["sinopsis"] + "</i>"
    return html


def movie_callback(bot, update):
    chat_id = update.callback_query.message.chat_id
    if chat_id != CHAT_ID:
        bot.send_message(chat_id=chat_id, text="Ups. No tienes permisos para usar este bot!")
        return
    message_id = update.callback_query.message.message_id

    key = int(update.callback_query.data.replace('mov.', ''))
    movie = cached_movies[key]
    if movie is None:
        bot.send_message(chat_id=chat_id, text="Ups. No se encuentra la peli!")
        return

    movie_page = movie["page"]
    movie_name = movie["name"]
    movie_id = str(movie["id"])
    url = 'https://www.filmaffinity.com/es/search.php?stext=' + movie_name
    kbs = [[InlineKeyboardButton(text="Buscar en Filmaffinity", url=url)],
           [InlineKeyboardButton(text="Descargar", callback_data="down." + movie_id)],
           [InlineKeyboardButton(text="<< Volver <<", callback_data="list." + str(movie_page))]]
    markup = InlineKeyboardMarkup(inline_keyboard=kbs)
    html = get_movie_detail_html(movie)
    bot.answerCallbackQuery(callback_query_id=update.callback_query.id)
    bot.editMessageText(chat_id=CHAT_ID,
                        message_id=message_id,
                        text=html,
                        parse_mode="HTML",
                        reply_markup=markup)


def prepare_movie_button(movie):
    name = movie["name"]
    movie_id = movie["id"]
    return InlineKeyboardButton(text=name, callback_data="mov." + str(movie_id))


def page_text(current, page, last_page):
    if page < current:
        if page == 1 and current - 2 > 1:
            return "<< 1"
        if page == 1:
            return "1"
        if page > last_page - 3 or page < 3:
            return str(page)
        return "< " + str(page)
    if page > current:
        if page == last_page and page - 2 > current:
            return str(last_page) + " >>"
        if page == last_page:
            return str(last_page)
        if page < 4 or page > last_page - 2:
            return str(page)
        return str(page) + " >"
    return "- " + str(page) + " -"


def prepare_pagination(page, last_page):
    nav = []
    nav.append(InlineKeyboardButton(text=page_text(page, 1, last_page), callback_data="list.1"))
    second = page - 1
    if second < 2:
        second = 2
    elif second > last_page - 3:
        second = last_page - 3
    if second <= last_page:
        nav.append(InlineKeyboardButton(text=page_text(page, second, last_page), callback_data="list." + str(second)))
    third = second + 1
    if third <= last_page:
        nav.append(InlineKeyboardButton(text=page_text(page, third, last_page), callback_data="list." + str(third)))
    fourth = third + 1
    if fourth <= last_page:
        nav.append(InlineKeyboardButton(text=page_text(page, fourth, last_page), callback_data="list." + str(fourth)))
    if fourth < last_page:
        nav.append(
            InlineKeyboardButton(text=page_text(page, last_page, last_page), callback_data="list." + str(last_page)))
    return nav


def prepare_markup(movies, page, last_page):
    kbs = []
    cols = []
    movies_len = len(movies)
    col_num = int(math.floor(movies_len / 10))
    if col_num > 4:
        col_num = 4
    if col_num < 2:
        col_num = 2
    for movie in movies:
        cols.append(prepare_movie_button(movie))
        if len(cols) == col_num:
            kbs.append(cols)
            cols = []
    if len(cols) > 0:
        kbs.append(cols)
    nav = prepare_pagination(page, last_page)
    kbs.append(nav)
    kbs.append([InlineKeyboardButton(text="- Volver al menú -", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=kbs)


def get_tree(url):
    parser = etree.HTMLParser()
    page = requests.get(url)
    return etree.parse(StringIO(page.content), parser)


def update_latest_movies(page):
    html = get_tree(URL_DOMAIN + '/peliculas-hd/pg/' + str(page))
    anchors = html.xpath("//ul[@class='pelilist']/li[contains(.,'MicroHD')]/a")

    latest_movies = []
    for anchor in anchors:
        name = anchor.xpath("h2/text()")[0].strip()
        link = anchor.xpath("@href")[0]
        movie_id = int(hashlib.md5(link).hexdigest(), 16)
        movie = {"name": name, "link": link, "id": movie_id, "page": page}
        if movie_id not in cached_movies:
            cached_movies[movie_id] = movie
        latest_movies.append(movie)
    return latest_movies


def get_last_page():
    html = get_tree(URL_DOMAIN + '/peliculas-hd/pg/1')
    url = html.xpath("//ul[@class='pagination']/li/a[contains(.,'Last')]/@href")[-1]
    last_page = url.replace(URL_DOMAIN + '/peliculas-hd/pg/', '')
    return int(last_page)


def list_movies_callback(bot, update):
    chat_id = update.callback_query.message.chat_id
    if chat_id != CHAT_ID:
        bot.send_message(chat_id=chat_id, text="Ups. No tienes permisos para usar este bot!")
        return
    page = int(update.callback_query.data.replace('list.', ''))
    message_id = update.callback_query.message.message_id
    latest_movies = update_latest_movies(page)
    last_page = get_last_page()
    markup = prepare_markup(latest_movies, page, last_page)
    bot.answerCallbackQuery(callback_query_id=update.callback_query.id)
    try:
        bot.editMessageText(chat_id=CHAT_ID,
                            message_id=message_id,
                            text="Últimas películas disponibles en MicroHD:",
                            reply_markup=markup)
    except TelegramError as e:
        logging.error(e)


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.info("Levantando Raspberry Pi Bot...")

updater = Updater(token=TOKEN)
dispatcher = updater.dispatcher

download_handler = CallbackQueryHandler(download_callback, pattern='down.*')
movie_handler = CallbackQueryHandler(movie_callback, pattern='mov.*')
list_movies_handler = CallbackQueryHandler(list_movies_callback, pattern='list.*')
menu_handler = CallbackQueryHandler(menu_callback, pattern='menu')

dispatcher.add_handler(download_handler)
dispatcher.add_handler(movie_handler)
dispatcher.add_handler(list_movies_handler)
dispatcher.add_handler(menu_handler)

start_handler = CommandHandler('start', start_callback)
dispatcher.add_handler(start_handler)

updater.start_polling()
logging.info("Raspberry Pi Bot listo!")
updater.idle()
logging.info("Deteniendo Raspberry Pi Bot...")
updater.stop()
