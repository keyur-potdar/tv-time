import datetime
import json
import logging
import os
import re
import subprocess
import sys
import tkinter as tk
from multiprocessing import Process

import requests
from bs4 import BeautifulSoup

DIR_NAME = os.path.dirname(__file__)

with open(os.path.join(DIR_NAME, 'config.json')) as f:
    config = json.load(f)

WEBSITE_NAME = config['website']['name']
WEBSITE_PREFIX = config['website']['prefix']
WEBSITE_SPACE = config['website']['space']
WEBSITE_SUFFIX = config['website']['suffix']

USERNAME = config['login']['username']
PASSWORD = config['login']['password']

DATE_TODAY = str(datetime.date.today())
DATE_YESTERDAY = str(datetime.date.today() - datetime.timedelta(1))

JSON_FILE = os.path.join(DIR_NAME, 'shows.json')
LOG_FILE = os.path.join(DIR_NAME, 'log.log')
logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, format='%(asctime)s %(message)s')

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36'}


def format_episode(season, episode):
    """
    Returns the complete episode formed using `season` and `episode`.

    Example:
    >>> format_episode(3, 11)
    's03e11'
    """
    return 's{:02d}e{:02d}'.format(season, episode)


def format_url(name, season=None, episode=None):
    """
    Returns the URL formed by using `name`, `season` and `episode`.

    Example:
    >>> format_url('the office', 4, 11)
    'https://bayhypertpb.be/s/?q=the+office+s04e11&page=0&orderby=99'

    >>> format_url('the office', 's04e11')
    'https://bayhypertpb.be/s/?q=the+office+s04e11&page=0&orderby=99'

    >>> format_url('the office s04e11')
    'https://bayhypertpb.be/s/?q=the+office+s04e11&page=0&orderby=99'
    """
    if season is None and episode is None:
        return WEBSITE_NAME + WEBSITE_PREFIX + name.replace(' ', WEBSITE_SPACE) + WEBSITE_SUFFIX
    if episode:
        episode = format_episode(season, episode)
    else:
        episode = season
    return WEBSITE_NAME + WEBSITE_PREFIX + name.replace(' ', WEBSITE_SPACE) + WEBSITE_SPACE + episode + WEBSITE_SUFFIX


def download_torrent(link, root=None):
    """
    Starts the torrent download. Requires any torrent application pre-installed (uTorrent, BitTorrent, etc).
    """
    try:
        if root:
            root.destroy()
        r = requests.get(WEBSITE_NAME+link, headers=headers)
        soup = BeautifulSoup(r.text, 'lxml')
        magnet = soup.find('a', {'title': 'Get this torrent'}).get('href')

        # Linux
        if sys.platform.startswith('linux'):
            subprocess.Popen(['xdg-open', magnet], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Windows
        elif sys.platform.startswith('win32'):
            os.startfile(magnet)
        # Cygwin
        elif sys.platform.startswith('cygwin'):
            os.startfile(magnet)
        # macOS
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(['open', magnet], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            subprocess.Popen(['xdg-open', magnet], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logging.error(str(e), exc_info=True)


def show_torrents(url):
    """
    Scrapes the PirateBay proxy and displays all available torrents.
    """
    # Establish connection and get page content
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
    except (requests.ConnectionError, requests.HTTPError) as e:
        root = tk.Tk()
        tk.Label(root, text=str(e)).pack()
        root.mainloop()
        return
    except Exception as e:
        logging.error(str(e), exc_info=True)
        return

    root = tk.Tk()
    root.title(url)
    for col, label in enumerate(['Sr No', 'NAME', 'SE', 'LE', 'SIZE', 'UPLOADED', 'LINK'], 1):
        tk.Label(root, text=label).grid(column=col, row=1, sticky=tk.W, padx=10, pady=10)

    # Scrape the page
    soup = BeautifulSoup(r.text, 'lxml')
    for row, tr in enumerate(soup.select('#searchResult tr')[1:15], 1):
        det_link = tr.find('a', {'class': 'detLink'})
        name = det_link.text
        href = det_link.get('href')
        seeders, leechers = [x.text for x in tr.find_all('td', {'align': 'right'})]
        info_regex = re.compile(r'Uploaded (.*), Size (.*), ULed by (.*)')
        uploaded, size, uploader = info_regex.search(tr.find('font', {'class': 'detDesc'}).text).groups()

        for col, label in enumerate([row, name, seeders, leechers, size, uploaded], 1):
            tk.Label(root, text=label).grid(column=col, row=row+1, sticky=tk.W, padx=5, pady=5)
        tk.Button(root, text='Download', command=lambda c=href: download_torrent(c, root))\
            .grid(column=7, row=row+1, sticky=tk.W, padx=10, pady=5)

    root.mainloop()


def scrape_shows_list():
    """
    Scrapes the user's calender from www.tvtime.com and gets all the shows aired today and yesterday.
    Saves the scraped list in `JSON_FILE` and returns the list.
    """
    base_url = 'https://www.tvtime.com'
    with requests.Session() as s:
        form = {
            'username': USERNAME,
            'password': PASSWORD,
            'redirect_path': base_url + '/en'
        }
        # Login
        r = s.post(base_url+'/signin', data=form, headers=headers)
        soup = BeautifulSoup(r.text, 'lxml')
        try:
            calendar = soup.find('li', class_='calendar ').a['href']
        except AttributeError:
            logging.info('Invalid login credentials.')
            return
        # Get calender
        r = s.get(base_url+calendar, headers=headers)
    # Extract the data from the page and convert it to JSON
    script = re.findall(r'calendar\s*:\s*\'(\[{.*}])', r.text)[0]
    data = json.loads(script.replace(r'\&quot;', '"').replace(r'\&#039;', "'"))
    # print(json.dumps(data, indent=4))

    shows_json = {DATE_TODAY: [], DATE_YESTERDAY: []}

    # Scrape all shows
    for show in data:
        if show['air_date'] == DATE_TODAY or show['air_date'] == DATE_YESTERDAY:
            name, season, episode = show['show']['name'].replace("'s", 's'), show['season_number'], show['number']
            url = format_url(name, season, episode)
            shows_json[show['air_date']].append({'name': name,
                                                 'season': season,
                                                 'episode': episode,
                                                 'url': url})

    # Save scraped data in a file for future use
    with open(JSON_FILE, 'w') as f:
        json.dump(shows_json, f)

    return shows_json


def get_shows():
    """
    Returns shows from `JSON_FILE` if shows already scraped, otherwise scrapes them and returns the list.
    """
    try:
        with open(JSON_FILE, 'r') as f:
            shows_json = json.load(f)
        if DATE_TODAY not in shows_json:
            return scrape_shows_list()
        return shows_json
    except (FileNotFoundError, json.JSONDecodeError):
        try:
            return scrape_shows_list()
        except Exception as e:
            logging.error(str(e), exc_info=True)
    except Exception as e:
        logging.error(str(e), exc_info=True)


def display_shows():
    """
    Displays list of shows aired today and yesterday.
    """
    shows_json = get_shows()

    root = tk.Tk()
    root.title('TV Time')

    def _download_all(date):
        for show in shows_json[date]:
            if sys.platform.startswith('win32'):
                Process(target=show_torrents, args=(show['url'],)).start()
            else:
                show_torrents(show['url'])

    curr_row = 0

    # TODAY
    tk.Label(root, text='Release date: {} (Today)'.format(DATE_TODAY)) \
        .grid(row=curr_row, column=0, padx=10, pady=(10, 4), sticky='w')
    tk.Button(root, text='Download all', command=lambda: _download_all(DATE_TODAY)) \
        .grid(row=curr_row, column=1, padx=10, pady=(10, 4), sticky='e')
    curr_row += 1

    if not shows_json[DATE_TODAY]:
        tk.Label(root, text='No shows').grid(row=curr_row, column=0, padx=10, pady=(4, 10))
        curr_row += 1
    else:
        for show in shows_json[DATE_TODAY]:
            tk.Label(root, text='{} {}'.format(show['name'], format_episode(show['season'], show['episode']))) \
                .grid(row=curr_row, column=0, padx=10, pady=1, sticky='w')
            tk.Button(root, text='Download', command=lambda url=show['url']: show_torrents(url)) \
                .grid(row=curr_row, column=1, padx=10, pady=1, sticky='e')
            curr_row += 1

    # Seperator
    tk.Label(root, text='').grid(row=curr_row, columnspan=2)
    curr_row += 1

    # YESTERDAY
    tk.Label(root, text='Release date: {} (Yesterday)'.format(DATE_YESTERDAY)) \
        .grid(row=curr_row, column=0, padx=10, pady=(10, 4))
    tk.Button(root, text='Download all', command=lambda: _download_all(DATE_YESTERDAY)) \
        .grid(row=curr_row, column=1, padx=10, pady=(10, 4), sticky='e')
    curr_row += 1

    if not shows_json[DATE_YESTERDAY]:
        tk.Label(root, text='No shows').grid(row=curr_row, column=0, padx=10, pady=(4, 10))
        curr_row += 1
    else:
        for show in shows_json[DATE_YESTERDAY]:
            tk.Label(root, text='{} {}'.format(show['name'], format_episode(show['season'], show['episode']))) \
                .grid(row=curr_row, column=0, padx=10, pady=1, sticky='w')
            tk.Button(root, text='Download', command=lambda url=show['url']: show_torrents(url)) \
                .grid(row=curr_row, column=1, padx=10, pady=1, sticky='e')
            curr_row += 1

    # Padding
    tk.Label(root, text='').grid(row=curr_row, columnspan=2)

    root.mainloop()


if __name__ == '__main__':
    display_shows()
