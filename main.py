import argparse
import logging
import requests
from bs4 import BeautifulSoup
import re
from time import sleep
import smtplib, ssl
import json
import os

DEFAULT_CHECK_PERIOD = 3 * 60 * 60 # seconds, 3h
SE_REGEX = re.compile(r"s(\d+)e(\d+)")
LOG_FILENAME = "bot.log"
LOCAL_HTML_FILENAME = "pb.html"
CREDENTIALS_FILENAME = "credentials.json"

def get_fullpath(filename):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(script_dir, filename)

def send_email(sender_email, sender_password, recipients, message):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, sender_password)
        logging.info("Sending email...")
        server.sendmail(sender_email, recipients, message)
    logging.info("Email sent successfully.")


def prepare_message(title, torrent_name, url):
    return f"""\
Subject: New {title.title()}!

There is available new episode: {torrent_name}.
Visit: {url}"""

def get_se(title):
    match = SE_REGEX.search(title.lower())
    if match:
        return int(match[1]), int(match[2])
    return None

def check_new_episode(title, season, episode):
    url = f"https://thepiratebay.asia/s/?q={title.replace(' ', '+')}&category=0&page=0&orderby=99"
    if DEBUG:
        logging.info("Reading local html file...")
        with open(get_fullpath(LOCAL_HTML_FILENAME), 'r', encoding='utf-8') as file:
            html = file.read() 
    else:
        logging.info("Fetching html data...")
        resp = requests.get(url)
        html = resp.text

        with open(get_fullpath(LOCAL_HTML_FILENAME), 'w', encoding='utf-8') as file:
            file.write(html)

    soup = BeautifulSoup(html, 'html.parser')
    for data in soup.find_all(class_="detLink"):
        torrent_name = data.get_text()
        se = get_se(torrent_name)
        if se:
            current_season, current_episode = se
            if current_season == season and current_episode == episode:
                return torrent_name, url

    return None

def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
        handlers=[logging.FileHandler(get_fullpath(LOG_FILENAME)), logging.StreamHandler()])

    logging.info("Night Bot started")
    parser = argparse.ArgumentParser()
    parser.add_argument("title", help="TV Series title")
    parser.add_argument("next_episode", help="Episode number to watch in format: sNNeNN")
    parser.add_argument("-o", "--once", action="store_true", default=False, help="Endless loop mode if not set")
    parser.add_argument("-p", "--period", type=int, default=DEFAULT_CHECK_PERIOD, help="Check period")
    parser.add_argument("-d", "--debug", action="store_true", default=False, help="Debug mode")
    args = parser.parse_args()

    title = args.title
    se_raw = args.next_episode
    once = args.once
    check_period = args.period
    global DEBUG
    DEBUG = args.debug

    credentials_fullpath = get_fullpath(CREDENTIALS_FILENAME)
    if os.path.exists(credentials_fullpath):
        try:
            with open(credentials_fullpath, "r") as file:
                data = json.load(file)
                sender_email = data["sender"]["email"]
                sender_password = data["sender"]["password"]
                recipients = data["recipients"]
                logging.debug(f"Sender: {sender_email}")
                logging.debug(f"Recipients: {recipients}")

                if not sender_email or not sender_password or not recipients:
                    raise ValueError("Empty credentials or no recipients given!")
        except KeyError as e:
            logging.error(f"Corrupted credentials file: {credentials_fullpath}")
            logging.error(f"Field {e} not found")
            return 1
        except Exception as e:
            logging.critical(e)
            return 1
    else:
        logging.error("Credentials file not found")
        return 1

    se = get_se(se_raw)
    if se:
        season, episode = se
    else:
        logging.error("Incorrect season / episode provided!")
        return 1

    logging.info(f"Checking periodically ({check_period} seconds) for '{title}' {se_raw}")
    while True:
        ret = check_new_episode(title, season, episode)
        if ret:
            logging.info("New episode is available!")
            send_email(sender_email, sender_password, recipients, prepare_message(title, *ret))
            episode += 1
        else:
            logging.info("No new episode")

        if once:
            logging.info("No loop mode, exiting")
            break

        logging.info(f"Next check in {check_period} seconds.")
        sleep(check_period)

if __name__ == '__main__':
    main()