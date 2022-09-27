import sys
import asyncio
from asyncinit import asyncinit
import glob
import random
import typing
from typing import Union
import httpx
import json
import html
import re
import csv
import math
from bs4 import BeautifulSoup
import time
from datetime import datetime
import datetime
import os
from colorama import Fore, Back, Style, init
init(autoreset=True)

@asyncinit
class LacedSold:
    __slots__  = ['username','password','login_url','url','token','headers','login_data','token_parse','webhook','attempt','product_data','session',
                  'total_pending_parse','total_completed','tasks','date_parse']
    async def __init__(self, config) -> None:
        self.username = config['username']
        self.password = config['password']
        self.login_url = 'https://www.laced.co.uk/users/sign_in' #used for token & log in 
        self.url = 'https://www.laced.co.uk/account/selling?status=pending' #used for monitoring
        self.webhook = config['webhook']
        self.token_parse = re.compile(r'name="authenticity_token"\s*value="(.*?)"',re.I)
        self.total_pending_parse = re.compile(r"'sales'\s*:\s*(.*?),",re.I|re.M)
        self.date_parse = re.compile(r'Your\s*item\s*was\s*verified\s*on\s*(.*?)\s*and',re.I|re.M)
        self.headers = {
                 # 'authority': 'www.laced.co.uk',
                 # 'cache-control': 'max-age=0',
                  'sec-ch-ua': '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
                  'sec-ch-ua-mobile': '?0',
                  'sec-ch-ua-platform': '"Windows"',
                  'upgrade-insecure-requests': '1',
                  'origin': 'https://www.laced.co.uk',
                 'content-type': 'application/x-www-form-urlencoded',
                  'user-agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
                  'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                  'sec-fetch-site': 'same-origin',
                  'sec-fetch-mode': 'navigate',
                  'sec-fetch-user': '?1',
                  'sec-fetch-dest': 'document',
                  'referer': 'https://www.laced.co.uk/users/sign_in',
                  #'cookie':'',
                  'accept-language': 'en-US,en;q=0.9',
                }
        #variables modified on execution#:
        self.login_data = {'utf8': '%E2%9D%8C', #x
                            'authenticity_token': None, #modified later.
                            'user[email]': self.username,
                            'user[password]': self.password,
                            'user[remember_me]': '1',
                            'user[remember_me]': '1',
                            'commit': 'Log in'}

        
        self.tasks = []
        self.total_completed = 0
        self.product_data = []
        self.token = None
        self.attempt = 0
        await self.run()

    async def run(self) -> Union[None,bool]:
        while True:
           async with httpx.AsyncClient(event_hooks={'response':[self.responseHandler]},http2=False,verify=False,timeout=httpx.Timeout(30.0, connect=10.0)) as self.session:
               await self.tokenPull()
               if await self.logIn():
                   await self.pullCompleted()
                   if self.product_data:
                       for data in self.product_data:
                           self.tasks.append(self.pullDetails(data))
                       await asyncio.gather(*self.tasks)
                       print(Fore.YELLOW+ await self.printTotal())
                       if await self.writeCsv():
                           print(Fore.GREEN+'[csvWriter] Successfully Wrote to CSV')
                       break
                   else:
                       break
                       
        await asyncio.sleep(3)
        return True

    async def responseHandler(self, response:object) -> None:
        if ('slack' not in str(response.url)) and ('discord' not in str(response.url)):
            response.raise_for_status()

    async def tokenPull(self) -> bool:
        while True:
            try:
                r = await self.session.get(self.login_url,headers=self.headers)
                try:
                    self.token = self.token_parse.search(r.text).group(1)
                    self.login_data['authenticity_token'] = self.token
                    print('[tokenPull] Successfully Got Token!')
                    break
                except AttributeError:
                   print(Fore.RED+'[tokenPull] Failed to Pull Token - Retrying...')
                   await asyncio.sleep(1)
                   continue
            except httpx.HTTPStatusError as e:
                print(Fore.RED+'[tokenPull] HTTP Error - Retrying... {}'.format(e.response.status_code))
                await asyncio.sleep(1)
                continue
            except httpx.RequestError as e:
                print(Fore.RED+'[tokenPull] HTTP Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue
            except Exception as e:
                print(Fore.RED+'[tokenPull] External Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue

        return True



    async def pullPagecount(self, num: int = 20) -> bool:
        '''20 per page, (total count/ 20) = page'''
        return int(num) / 20

    async def netPrice(self, value : int) -> int:
        return float((value*0.85)-5.99)


    async def pullCompleted(self) -> bool:
        '''pull each page, of sales - create task for each ID'''
        print(Fore.YELLOW+f'[checkSold] {self.total_completed} Items Sold...')
        pages = await self.pullPagecount(self.total_completed)
        pages = math.floor(pages)
        if pages > 50:
            pages = 50
            print(Fore.YELLOW+f'[checkSold] Laced Does not allow us to view more than 50 pages!')
        else:pass
       # print(pages)
        x = 1
        while x <= pages:
            try:
                #total_pending = 'Unknown'
                r = await self.session.get(f'https://www.laced.co.uk/account/selling?status=sold&page={x}',headers=self.headers,allow_redirects=False)
                #print(r.url)
                if r.status_code == 302: #we've been signed out!
                    print('[checkSold] We have been signed out!')
                    break
                else:
                    print(Fore.WHITE+'[checkSold] Successful Request - Parsing...')
                    soup = BeautifulSoup(r.text, "lxml")
                    parse = soup.find_all('div',{'data-react-class':'ListItemSale'})
                    #print(parse)
                   # await asyncio.sleep(100)
                    if parse:
                        for item in parse:
                            item = json.loads(html.unescape(item['data-react-props']))
                            product_id = 'https://www.laced.co.uk'+item['actions'][0]['href']
                            #if product_id not in self.products_sold:
                            name = item['title']['label']
                            image = item['imageUrl']
                            price = item['price'].rstrip().lstrip()[1:]
                            net_price = await self.netPrice(int(price))
                            size = item['info']
                            fees = int(price) - net_price
                            csv_data = {'name':name,
                                            'size':size,
                                            'price':price,
                                            'netprice':net_price,
                                            'fees':f'{fees:.2f}',
                                            'date':'will be set in task function!',
                                            'producturl':product_id}
                                
                            self.product_data.append(csv_data)

                        print(Fore.CYAN+f'[checkSold][Page: {x}] Parse Successful!')
                        x+=1
                        soup.decompose()
                        #await asyncio.sleep(5)
                            
                    else:
                         soup.decompose()
                         print(Fore.YELLOW+'[checkSold] No Sold Items Found on this Page - Going to Write...') #when we try parse more pages than items sold.
                         break
                         #await asyncio.sleep(5)
                         #continue
            except httpx.HTTPStatusError as e:
                print(Fore.RED+'[checkSold] HTTP Error - Retrying... {}'.format(e.response.status_code))
                await asyncio.sleep(1)
                continue
            except httpx.RequestError as e:
                print(Fore.RED+'[checkSold] HTTP Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue
            except Exception as e:
                print(Fore.RED+'[checkSold] External Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue

        return True


    async def pullDetails(self, data : dict) -> bool:
        '''https://www.laced.co.uk/account/selling/{id}'''
        '''will need to pull the date, total sale price and write to csv'''
        url = data['producturl']
        while True:
            try:
                r = await self.session.get(f'{url}',headers=self.headers,allow_redirects=False)
                #print(r.url)
                if r.status_code == 302: #we've been signed out! - might need to do something global if this happens?!?!
                    print('[pullDetails] We have been signed out!')
                    break
                else:
                    print(Fore.WHITE+'[pullDetails] Successful Request - Parsing...')
                    parse = self.date_parse.search(r.text)
                    if parse:
                        parse = parse.group(1)
                        print(Fore.CYAN+'[pullDetails] Date Parsed!')
                        data['date'] = parse
                        break
                        #await asyncio.sleep(5)
                            
                    else:
                         print(Fore.YELLOW+'[pullDetails] No Sale Date Found for this Product...') #when we try parse more pages than items sold.
                         break
                         #await asyncio.sleep(5)
                         #continue
            except httpx.HTTPStatusError as e:
                print(Fore.RED+'[pullDetails] HTTP Error - Retrying... {}'.format(e.response.status_code))
                await asyncio.sleep(1)
                continue
            except httpx.RequestError as e:
                print(Fore.RED+'[pullDetails] HTTP Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue
            except Exception as e:
                print(Fore.RED+'[pullDetails] External Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue

        return True
        

    async def writeCsv(self, data : dict={}) -> bool:
        '''write details to csv. Can write all at once so that we don't need to open each time the csv and write.'''
        '''big 0 notation, O(1)'''
        fieldnames = ['name', 'size', 'price', 'netprice', 'fees','date','producturl']
        with open('laced_export.csv', 'w', encoding='UTF8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.product_data)
        return True


    async def printTotal(self) -> int:
        '''We can output the total statistics of our sales in ordr to know our total amount, prior to the csv write'''
        return f'Total Completed & Shipped : {len(self.product_data)}'
       

    async def logIn(self) -> bool:
        loggedin = False
        while True:
            try:
                r = await self.session.post(self.login_url,headers=self.headers,data=self.login_data)
                if r.url == 'https://www.laced.co.uk/':
                    print('[logIn] Successfully Logged-in!')
                    try:
                        self.total_completed = self.total_pending_parse.search(r.text).group(1)
                    except AttributeError:
                        self.total_completed = 3000 #failsafe.
                    loggedin = True
                    break
                else:
                   print(Fore.RED+'[logIn] Failed to Login - Restarting Cycle... (Invalid Password/User!)')
                   await asyncio.sleep(1)
                   break
            except httpx.HTTPStatusError as e:
                print(Fore.RED+'[logIn] HTTP Error - Retrying... {}'.format(e.response.status_code))
                await asyncio.sleep(1)
                continue
            except httpx.RequestError as e:
                print(Fore.RED+'[logIn] HTTP Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue
            except Exception as e:
                print(Fore.RED+'[logIn] External Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue

        return loggedin


class Utils:

    @staticmethod
    async def sendhook(data : dict, webhook : str, session : object) -> str:
        if(not len(data)):
            #raise Exception('[SLACK] Invalid Webhook Data! - Failed to Push!')
            return '[SLACK] Invalid Webhook Data! - Failed to Push!'
        
        #async with httpx.AsyncClient(http2=False,verify=False) as session: #not a good idea to make new session for each thread again. Memory ^^
        a = await session.post(url=webhook, json=data)
        iter1 = 0
        while a.status_code == 429 and iter1 <= 5:
            await asyncio.sleep(5)
            a = await session.post(url=webhook, json=data)
            iter1+=1
        if a.status_code == 429:
            return ('[SLACK] Failed to Push to Slack - {}'.format(a.status_code))
            #return False
        elif a.status_code == 200:
            #iter1 = 0
            return ('[SLACK] Successfully Pushed to Slack! - {}'.format(a.status_code))
            #return True
        else:
            return ('[SLACK] Unknown Error! - Failed to Push! - {}'.format(a.status_code))
            #return False'''

    @staticmethod
    def detectall(extension):
        files = glob.glob(f'{os.path.dirname(os.path.realpath(__file__))}/*{extension}',recursive=False)
        if (not len(files)):
            return False
        else:
            return files

    @staticmethod
    def jsondefault(name):
        if name.lower() == 'config':
            return {
                "username":"",
                "password":"",
                "webhook":"webhook not used"}

    @staticmethod
    def jsonloader():
       filecheck = Utils.detectall('config.json')
       if not filecheck:
           raise Exception('[CONFIG] File Not Found! - Program Closing...')
           return False
       with open(filecheck[0], 'r+') as f:
           try:
               config = json.load(f)
               error_list = [x for x in Utils.jsondefault('config') if not config.get(x)]
               if len(error_list):
                   raise Exception(f'[CONFIG] {error_list} Missing from Config!!')
           except ValueError:
                f.seek(0)
                f.truncate(0)
                json.dump(Utils.jsondefault('config'),f,indent=4)
                raise Exception('[CONFIG] File was Invalid - Go and put your info in my g!')
                return False
       return config




async def main() -> Union[None,bool]:
    try:
        config_main = Utils.jsonloader()
    except Exception as e:
        print(e)
        await asyncio.sleep(2)
        sys.exit(1)
    await asyncio.create_task(LacedSold(config_main))


if __name__ == '__main__':
    asyncio.run(main())
