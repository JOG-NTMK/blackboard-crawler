import asyncio
import os
from crawl import crawl
from download import download
from prompt import prompt
import pyppeteer
from pyppeteer import launch
from pyppeteer.page import Page
import getpass
import getopt
import sys

from blackboard_crawler_constants import VALID_TYPES


async def try_login(page: Page, username, password):
    await page.goto('https://lyitbb.blackboard.com/')

    await page.waitForSelector('#agree_button')
    await page.focus('#agree_button')
    await page.click('#agree_button')

    await page.waitForSelector('#user_id')
    await page.focus('#user_id')
    await page.keyboard.down('Control')
    await page.keyboard.press('KeyA')
    await page.keyboard.up('Control')
    await page.keyboard.press('Backspace')
    await page.type('#user_id', username)

    await page.waitForSelector('#password')
    await page.focus('#password')
    await page.keyboard.down('Control')
    await page.keyboard.press('KeyA')
    await page.keyboard.up('Control')
    await page.keyboard.press('Backspace')
    await page.type('#password', password)

    await page.focus('#entry-login')
    await page.click('#entry-login')

    try:
        await page.waitForSelector("#user_id", timeout=1000)
    except Exception:
        return True

    return False


async def main():
    opts, args = getopt.getopt(sys.argv[1:], "hHp",
                               ["help", "headless", "no-indices", "module-regex=", "submodule-regex=", "crawl=",
                                "prompt=", "download=", "include-type=", "exclude-type="])

    headless = False
    no_downloads = False
    module_regex = ""
    submodule_regex = ""
    should_crawl = None
    should_prompt = None
    should_download = None
    type_choices = {t: True for t in VALID_TYPES}

    for o, a in opts:
        if o in ("-h", "--help"):
            h = open("help", "r")
            print(h.read(), end="")
            h.close()
            return
        elif o in ("-H", "--headless"):
            headless = True
        elif o in ("-U", "--update"):
            no_downloads = True
        elif o == "--module-regex":
            module_regex = a
        elif o == "--submodule-regex":
            submodule_regex = a
        elif o == "--crawl":
            should_crawl = a == 'yes'
        elif o in ('--p', "--prompt"):
            should_prompt = a == 'yes'
        elif o == "--download":
            should_download = a == 'yes'
        elif o == '--include-type':
            type_choices = {t: t in a.split(',') for t in VALID_TYPES}
        elif o == '--exclude-type':
            type_choices = {t: t not in a.split(',') for t in VALID_TYPES}

    browser = await launch(headless=headless, args=['--no-sandbox', '--disable-setuid-sandbox'])
    page = await browser.newPage()

    failed_attempts = 0

    if os.path.isfile('./credentials'):
        credentials = open('./credentials', 'r').read().split('\n')
        if not await try_login(page, credentials[0], credentials[1]):
            print('The credentials contained in the credentials file are invalid')
            exit()
    else:
        while not await try_login(page, input('LYIT Username: '), getpass.getpass(':YIT Password: ')):
            failed_attempts += 1
            print("Failed to login. ", end="")
            if failed_attempts < 3:
                print("Try again")
            else:
                print("Exceeded maximum attempts")
                exit()

    print("Logged in!")
    if should_crawl == None:
        should_crawl = not os.path.exists("crawl.json") or input(
            "Crawl.json exists.\n Regenerate? This will take some time. [y/n] ") == "y"
    if should_crawl:
        await crawl(page, module_regex=module_regex, submodule_regex=submodule_regex)
        print("Regenerated 'crawl.json'")

    if should_prompt == None:
        should_prompt = not os.path.exists("choices.json") or input(
            "There is a choices.json here.\n Regenerate? You will have to go through the prompt menu again. [y/n] ") == "y"
    if should_prompt:
        prompt(type_choices)

    if should_download == None:
        should_download = input("Download files?\n Download? [y/n] ") == 'y'
    if should_download:
        await page.reload()
        await page.waitFor(1000)
        JSESSIONID = next(filter(lambda cookie: cookie['name'] == 'JSESSIONID', await page.cookies()))['value']
        BbRouter = next(filter(lambda cookie: cookie['name'] == 'BbRouter', await page.cookies()))['value']
        download('crawl.json', 'choices.json', JSESSIONID, BbRouter,type_choices=type_choices)


debug = os.environ.get('DEBUG_BLACKBOARD_CRAWLER')

if debug == '1':
    import pdb
    pyppeteer.DEBUG = True
    pdb.run('asyncio.get_event_loop().run_until_complete(main())')
else:
    asyncio.get_event_loop().run_until_complete(main())
