import sys
import asyncio
from asyncinit import asyncinit
import glob
import random
import typing
from typing import Union
import httpx
import json
from PyPDF2 import PdfFileWriter, PdfFileReader
import re
from bs4 import BeautifulSoup
import time
from datetime import datetime
import datetime
import html
import os
from colorama import Fore, Back, Style, init
init(autoreset=True)

@asyncinit
class LacedSold:
    __slots__  = ['username','password','login_url','url','token','headers','login_data','token_parse','webhook','attempt','products_sold','session','total_pending_parse',
                  'addyid_parse',]
    async def __init__(self, config) -> None:
        self.username = config['username']
        self.password = config['password']
        self.login_url = 'https://www.laced.co.uk/users/sign_in' #used for token & log in 
        self.url = 'https://www.laced.co.uk/account/selling?status=pending' #used for monitoring
        self.webhook = config['webhook']
        self.token_parse = re.compile(r'name="csrf-token"\s*content="(.*?)"',re.I)
        self.addyid_parse = re.compile(r'data-react-class="addresses/AddressListInput.*?data-react-props="(.*?)"',re.I)
        self.total_pending_parse = re.compile(r'pending\s*\((.*?)\)',re.I|re.M)
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

        self.products_sold = []
        self.token = None
        self.attempt = 0
        await self.run()

    async def run(self) -> Union[None,bool]:
        while True:
           async with httpx.AsyncClient(event_hooks={'response':[self.responseHandler]},http2=False,verify=False,timeout=httpx.Timeout(30.0, connect=10.0)) as self.session:
               await self.tokenPull()
               if await self.logIn():
                   await self.checkSold()

        return True #uncalled

    async def responseHandler(self, response:object) -> None:
        if ('slack' not in str(response.url)) and ('discord' not in str(response.url)):
            response.raise_for_status()

    async def tokenPull(self) -> bool:
        '''pull csrf token'''
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


    async def netPrice(self, value : int) -> int:
        '''calculate our net payout price to output in webhook'''
        return float((value*0.85)-5.99)
            

    async def logIn(self) -> bool:
        '''log in to Laced using our credentials from config'''
        loggedin = False
        while True:
            try:
                r = await self.session.post(self.login_url,headers=self.headers,data=self.login_data)
                if r.url == 'https://www.laced.co.uk/':
                    print('[logIn] Successfully Logged-in!')
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

    async def cropPdf(self,_id:str) -> bool:
        '''crop the provided label to output a label printer version!'''
        output = PdfFileWriter()
        path = f"{os.path.dirname(os.path.realpath(__file__))}/labels/{_id.split('/')[-1]}.pdf"
        output_path = f"{os.path.dirname(os.path.realpath(__file__))}/labels/{_id.split('/')[-1]}-cropped.pdf"
        _input = PdfFileReader(open(path, 'rb')) #close?
        n = _input.getNumPages()
        for i in range(n):
          #print(i)
          page = _input.getPage(i)
          #print(page.cropBox.getLowerRight())
          #print(page.cropBox.getLowerLeft())
          #print(page.cropBox.getUpperRight())
          #print(page.cropBox.getUpperLeft())
          if i == 0: #packing slip
            page.cropBox.lowerRight = (510,490) #x,0
           # page.cropBox.lowerLeft = (0,0) #0,0
            page.cropBox.upperRight = (510,660) #x,y
            page.cropBox.upperLeft = (95,660) #0, y
          elif i == 1: #label
            page.cropBox.lowerRight = (545,240)
           # page.cropBox.lowerLeft = (25,240)
            page.cropBox.upperRight = (550,520)
            page.cropBox.upperLeft = (31,550)
          else:
            pass
          output.addPage(page)

        outputStream = open(output_path,'wb+') #context?
        output.write(outputStream) 
        outputStream.close()
        return True


    '''async def printPdf(self, _id:str, printer_name="Munbyn ITPP941", secs=5) -> bool: #optional function.
        cmd = r'2printer.exe' #you can use any client! adobe, etc.
        path = f"{os.path.dirname(os.path.realpath(__file__))}/labels/{_id.split('/')[-1]}-cropped.pdf"
        #print(path)
        if cmd is None:
            return False

        cmd = '{} -src "{}" -prn "{}" -options silent:no alerts:no'.format(cmd, path, printer_name) #PUT OWN PRINTER HERE!#
        #try:
        proc = subprocess.Popen(cmd) #we should use asyncio.subprocess.exec, but ignoring as program is single task :)
        try:
            outs, errs = proc.communicate(timeout=10) #blocking func.
        except TimeoutExpired:
            proc.kill()
            #outs, errs = proc.communicate()
            return False
        proc.kill()
        return True'''


    async def postLabel(self, token, address_id, _id) -> bool:
        '''initialize address for the label + save full size label to file'''
        data = {'utf8': '%E2%9D%8C', #x
                'authenticity_token': token,
                'order_item[address_id]': address_id,
                'after_action': 'view',
                '_method': 'put',
                'commit': 'Select+Address'}
        gotLabel = False
        while True:
            try:
                r = await self.session.post(f'https://www.laced.co.uk{_id}/shipping-label',headers=self.headers,data=data)
                if r.url == f'https://www.laced.co.uk{_id}/shipping-label.pdf':
                    print('[postLabel] Successfully Initiated Label!')
                    gotLabel = True
                    break
                else:
                   print(Fore.RED+'[postLabel] Failed to Initiate Label - Passing')
                   break
            except httpx.HTTPStatusError as e:
                print(Fore.RED+'[postLabel] HTTP Error - Retrying... {}'.format(e.response.status_code))
                await asyncio.sleep(1)
                continue
            except httpx.RequestError as e:
                print(Fore.RED+'[postLabel] HTTP Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue
            except Exception as e:
                print(Fore.RED+'[postLabel] External Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue

        if gotLabel:
            try:
                with open(f"{os.path.dirname(os.path.realpath(__file__))}/labels/{_id.split('/')[-1]}.pdf", 'wb+') as f:
                    f.write(r.content)
                    return True
            except OSError as e:
                print(Fore.RED+'[postLabel] OSError - Retrying... {}'.format(e))
                return False

        else:
            return gotLabel #false
            

    async def getAddressID(self, _id:str) -> Union[None,dict]:
        gotId = False
        while True:
            try:
                r = await self.session.get(f'https://www.laced.co.uk{_id}/shipping-label.pdf',headers=self.headers)
                content_type = r.headers.get('content-type',None)
                if 'application/pdf' in content_type:
                    print('[getAddressID] Label Has Already Been Initiated!')
                    break
                else:
                    try:
                        token = self.token_parse.search(r.text).group(1)
                        address_id = json.loads(html.unescape(self.addyid_parse.search(r.text).group(1)))['addresses'][0]['id']
                        gotId = True
                        print('[getAddressID] Successfully Got AddressID!')
                        break
                    except:
                        print('[getAddressID] Failed to get Info! - Breaking')
                        break
            except httpx.HTTPStatusError as e:
                print(Fore.RED+'[getAddressID] HTTP Error - Retrying... {}'.format(e.response.status_code))
                await asyncio.sleep(1)
                continue
            except httpx.RequestError as e:
                print(Fore.RED+'[getAddressID] HTTP Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue
            except Exception as e:
                print(Fore.RED+'[getAddressID] External Error - Retrying... {}'.format(e))
                await asyncio.sleep(1)
                continue

        return {'token':token,'address_id':address_id, '_id':_id} if gotId else False
        
        

    async def checkSold(self) -> bool:
        while True:
            try:
                #total_pending = 'Unknown'
                r = await self.session.get(self.url,headers=self.headers,allow_redirects=False)
                if r.status_code == 302: #we've been signed out!
                    print('[checkSold] We have been signed out!')
                    break
                else:
                    print(Fore.WHITE+'[checkSold] Successful Request - Parsing...')
                    soup = BeautifulSoup(r.text, "lxml")
                    parse = soup.find_all('li',{'class':'list-item'})
                    try:
                        total_pending = self.total_pending_parse.search(r.text).group(1)
                    except AttributeError:
                        total_pending = len(parse)
                        #print(Fore.WHITE+f'[checkSold] We Failed to Pull Total Pending Sale Number! - It\'s ok! - Continuing...')
                    print(Fore.YELLOW+f'[checkSold] {total_pending} Items Sold & Pending...')
                   # await asyncio.sleep(100)
                    if parse:
                        for item in parse:
                            product_id = item.find('div',{'class':'list-item__actions'}).find('a',{'class':'list-item__actions--link'})['href']
                            if product_id not in self.products_sold:
                                self.products_sold.append(product_id)
                                if self.attempt > 0:
                                    name = item.find('img')['alt']
                                    image = item.find('img')['src']
                                    price = item.find('div',{'class':'list-item__stats__inner--info'}).text.rstrip().lstrip()[1:]
                                    net_price = await self.netPrice(int(price))
                                    sale_url = f'https://www.laced.co.uk{product_id}'
                                    size = item.find('span',{'class':'list-item__info text-info'}).text
                                    slack_data = {'attachments': [
                                                 {'title':f'{name} -> {size}',
                                                  #'text':f'Site Name -> {self.site_hook}',
                                                  "author_name":"Brrrrrrrrrr, Item sold on Laced!",
                                                  'title_link':sale_url,
                                                  'fields':[
                                                      {'title':'Sale Price',
                                                       'value':f'£{price}',
                                                       'short':True},
                                                      {'title':'Net Price',
                                                       'value':f'£{net_price}',
                                                       'short':True},],
                                                #  'color':'#%02X%02X%02X' % (colour(),colour(),colour()),
                                                  'thumb_url': image,
                                                  #'footer_icon':'https://pbs.twimg.com/profile_images/1053258374572318724/ILdGLRUM_400x400.jpg',
                                                  'footer':"Laced Checker "+datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d [%H:%M:%S.%f')[:-3] + "]"}]}
                                    #print(await Utils.sendhook(slack_data,self.webhook,self.session)) may cause fake pings if page x items go to page 1.
                                    getaddy = await self.getAddressID(product_id)
                                    if getaddy:
                                        if await self.postLabel(**getaddy):
                                            print(await Utils.sendhook(slack_data,self.webhook,self.session))
                                            slack_data = {'attachments': [
                                                 {'title':f'Successfully Initiated Label!',
                                                  'text':f'Labels saved in ./labels!',
                                                  "author_name":"Laced Label",
                                                  'title_link':f'https://www.laced.co.uk{product_id}/shipping-label.pdf',
                                                  'thumb_url': image,
                                                 # 'footer_icon':'https://pbs.twimg.com/profile_images/1053258374572318724/ILdGLRUM_400x400.jpg',
                                                  'footer':"Laced Label "+datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d [%H:%M:%S.%f')[:-3] + "]"}]}
                                            print(await Utils.sendhook(slack_data,self.webhook,self.session))
                                            
                                            if await self.cropPdf(product_id):
                                                #if await self.printPdf(product_id): optional function call here.
                                                pass
                                            else:
                                                continue

                                        else:
                                            continue
                                    else:
                                        continue
                                        
                                        
                                else:
                                    continue
                            else:
                                continue
                        print(Fore.CYAN+'[checkSold] Parse Successful!')
                        self.attempt+=1
                        soup.decompose()
                        await asyncio.sleep(5)
                            
                    else:
                         self.attempt+=1
                         soup.decompose()
                         print(Fore.YELLOW+'[checkSold] No Sold Items Found - Retrying...')
                         await asyncio.sleep(5)
                         continue
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
                "webhook":"webhook not used!"}

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
