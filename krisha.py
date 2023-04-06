from os import link
from pydoc import describe
import requests
import re
import logging
import concurrent.futures
import urllib
import json
from datetime import datetime, timedelta
import time
from ...utils.proxy_switcher import ProxyRevolver
from ...utils import backoff
from requests_html import HTMLSession
    
log = logging.getLogger('shops')

executor = concurrent.futures.ThreadPoolExecutor(10)


class ShopSkipIteration(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class BaseShopApi():
    def __init__(self):
        self.request_headers = {
            'authority': 'krisha.kz',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'accept-language': 'ru,en;q=0.9',
            'cache-control': 'max-age=0',
            'referer': 'https://krisha.kz/arenda/kvartiry/petropavlovsk/?das[rent.period]=2&das[who]=1',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="102", "Yandex";v="22"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.5005.167 YaBrowser/22.7.5.937 Yowser/2.5 Safari/537.36',
        }
        self.log = logging.getLogger('krisha')
        self.refresh_delay = backoff.MinDelay
        self.SHOP_URL = 'https://krisha.kz/arenda/kvartiry/?das[rent.period]=2&das[who]=1'
        self.shop_name = 'Krisha KZ'
        self.session = HTMLSession()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.session.headers.update(self.request_headers)
        self.timeout = 7
        self.proxy_revolver = ProxyRevolver(self.refresh_delay)
        self.proxy_revolver.make_proxy_pool()
        self.keywords = None
        self.last_refresh_timestamp = None
        self.cookies = {
            'krishauid': '6f351a54ba9ea097a45f3b14427a6d2cfed93b1a',
            '_ga': 'GA1.2.1494152977.1657685019',
            'ssaid': 'c77edf10-0260-11ed-9766-5369036eff01',
            '_ym_uid': '1657685021874643730',
            '_ym_d': '1657685021',
            '_gcl_au': '1.1.477637006.1657685022',
            '_tt_enable_cookie': '1',
            '_ttp': 'd08319ce-8b56-4d69-b9f5-564f664ab28a',
            'tutorial': '%7B%22advPage%22%3A%22viewed%22%7D',
            'krssid': 'qjrlsuftv8nq314lhlo3dimj6v',
            '_gid': 'GA1.2.111438000.1664093071',
            '_ym_isad': '1',
            '_fbp': 'fb.1.1664093073584.1279944553',
            'hist_region': '267',
            'kr_cdn_host': '//astps-kz.kcdn.online',
            '_ym_visorc': 'b',
            'nps': '1',
            '__tld__': 'null',
        }
        self.timestamp_sleep = datetime.now()
        self.latest_items = None

    def switch_proxy(self, on_error=False):
        if on_error:
            self.proxy_revolver.switch_on_error()
        proxy = self.proxy_revolver.current_proxy
        self.timestamp_sleep = proxy[0]
        self.refresh_delay = proxy[1]
        self.session.proxies = {
            'http' : proxy[2],
            'https' : proxy[2]
        }

    def get_keywords(self):
        time = datetime.now()
        if not(self.keywords and time < self.last_refresh_timestamp + timedelta(hours=12)):
            self.refresh_filters()
        return self.keywords

    def parse_items(self, resp):
        items = resp.html.find('div.a-card')
        if items == []:
            raise ShopSkipIteration('Cannot get items')
        self.parse_no(items[0])
        self.parse_name(items[0])
        self.parse_description(items[0])
        self.get_price(items[0])
        self.parse_adress(items[0])
        self.parse_city(items[0])
        self.parse_pic(items[0])
        self.parse_link(items[0])
        return items

    def parse_no(self, item):
        return item.attrs['data-id']

    def parse_name(self, item):
        name = item.find('a.a-card__title ')
        return name[0].text

    def parse_description(self, item):
        description = item.find('div.a-card__text-preview')
        return description[0].text

    def get_price(self, item):
        price = item.find('div.a-card__price')
        return price[0].text.replace(u'\xa0', u' ')

    def parse_adress(self, item):
        adr = item.find('div.a-card__subtitle ')
        return adr[0].text

    def parse_city(self, item):
        city = item.find('div.card-stats__item')
        return city[0].text

    def parse_pic(self, item):
        try:
            pic = item.find('img')
            return pic[0].attrs['src']
        except Exception:
            return 'https://kamzp.ru/img/o7sx5evgcf3249bue0022pgrm1gejw2m.jpeg'
    
    def parse_link(self, item):
        link = item.find('a.a-card__image')
        return f"https://krisha.kz{link[0].attrs['href']}"

    def item_sub_update(self, item):
        return item

    def http_requests(self, uri):
        try:
            resp_raw = self.session.get(uri, timeout=self.timeout, cookies=self.cookies)
            resp_raw.raise_for_status()
            return resp_raw
        except Exception as err:
            raise err

    def get_items(self):
        uri = self.SHOP_URL
        resp_raw = self.http_requests(uri)   
        items = self.parse_items(resp_raw)
        latest_items = {}

        def update_latest_items(item, item_title):
            no = self.parse_no(item)
            name = self.parse_name(item)
            description = self.parse_description(item)
            adress = self.parse_adress(item)
            city = self.parse_city(item)
            price = self.get_price(item)
            link = self.parse_link(item)
            pic = self.parse_pic(item)
            latest_items.update({no: {'item_name': name,
                                        'shop_name': "krisha kz",
                                        'item_link': link,
                                        'description': description,
                                        'adress': adress,
                                        'city': city,
                                        'price': price,
                                        'pic' : pic
                                        }})

        def preprocess_item(item):
            item = self.item_sub_update(item)
            item_title = self.parse_no(item)
            return (item, item_title)
        if type(items) != dict:
            res = executor.map(preprocess_item, items)
            for r in res:
                if r:
                    update_latest_items(*r)
        else:
            latest_items = items

        self.log.debug(f"Got items: {len(latest_items)} time stamp: {self.timestamp_sleep}")
        return latest_items

    def get_new_items(self, old_items):
        latest_items = self.get_items()
        latest_items.update({key: val for key, val in old_items.items() if key not in latest_items})
        new_ids = [id for id in latest_items if id not in old_items]
        relevant_old_ids = [id for id in latest_items if id not in new_ids]
        event_type = ''
        new_changes_ids = []
        for id in relevant_old_ids:
            new_values = [value for value in latest_items[id]
                            if latest_items[id][value] != old_items[id][value]]
            if len(new_values) > 0:
                new_changes_ids.append(id)
                event_type = 'Change in order\n'
                for changing in new_values:
                    event_type += f'{changing} -> old: {old_items[id][changing]} -> new:{latest_items[id][changing]}\n'
        update = []

        def notify_with_event(new_ids, event_type):
            if len(new_ids) > 0:
                new_items = [
                    item for id, item in latest_items.items() if id in new_ids]
                for item in new_items:
                    item.update({'event_type': event_type})
                    update.append(item)

        notify_with_event(new_ids, f'New order')
        notify_with_event(new_changes_ids, event_type)
        if update:
            self.log.info(f'New items: {update}')
        return update, latest_items