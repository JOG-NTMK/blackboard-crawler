# This file is derived from download.py, except it only produces a crawlfile

import asyncio
import json
import getpass
import sys
import pyppeteer
from pyppeteer import launch
from pyppeteer.page import Page
import urllib.request
import getopt

pyppeteer.DEBUG = True  

MODULE_LINK = ".courseListing > li > a"
SUBMODULE_LINK = "#courseMenuPalette_contents li a"
CONTENT = "#content_listContainer > li"
CONTENT_HEADER_LINK = "h3 a"
CONTENT_BODY_LINK = ".details a"
CONTENT_LINK = CONTENT_BODY_LINK + "," + CONTENT_HEADER_LINK
PANOPTO_CONTENT = "a.detail-title"

crawlfile_path = "crawl.json"
agreed_to_cookies = False

async def try_login(page: Page):
    await page.waitForSelector('#username')

    await page.focus('#username')
    await page.keyboard.down('Control')
    await page.keyboard.press('KeyA')
    await page.keyboard.up('Control')
    await page.keyboard.press('Backspace')

    await page.type('#username', input('TCD Username: '))
    await page.waitForSelector('#password')

    await page.focus('#password')
    await page.keyboard.down('Control')
    await page.keyboard.press('KeyA')
    await page.keyboard.up('Control')
    await page.keyboard.press('Backspace')

    await page.type('#password', getpass.getpass('TCD Password: '))
    await page.click('.form-button')

    for cookie in await page.cookies():
        if cookie.get('name') in ('shib_idp_session', 's_session_id'):
            return True

    return False

async def traverse_module(module_text: str, page: Page):
    module = {"name" : module_text, "link" : module_link, "submodules" : []};

    print("Traversing module %s" % module_text)
    for submodule_link, submodule_text in await page.JJeval(SUBMODULE_LINK, "links => links.map(link => [link.href, link.innerText])"):
        await page.goto(submodule_link)
        module["submodules"].append(await traverse_submodule(submodule_link, submodule_text, page))

    return module

async def crawl(page: Page):
    modules = []

    await page.waitFor(1000)
    await page.goto("https://tcd.blackboard.com/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_2_1")
    
    await page.waitForSelector("#agree_button", timeout=3000)
    await page.click("#agree_button") # Need to accept privacy policy
    agreed_to_cookies = True

    for module_link, module_text in page.JJeval(MODULE_LINK, "links => links.map(link => [link.href, link.innerText])"):
        await page.goto(module_link)
        modules.append(await traverse_module(module_text, page))

    crawlfile = open(crawlfile_path, "w")
    json.dump(modules, crawlfile)

async def traverse_submodule(submodule_text: str, page: Page):
    submodule = {
        "name" : submodule_text,
        "link" : submodule_link,
        "files" : [],
        "panoptoVideos" : [],
        "submodules" : [] # AAHHHHH
    }
    
    print(" Traversing submodule '%s' " % submodule_text)
    
    indices = await index(page, "  ")
    if indices:
        submodule["files"] = indices.get("files", [])
        submodule["panoptoVideos"] = indices.get("panoptoVideos", [])
        submodule["submodules"] = indices.get("submodules", [])

    return submodule

async def index(page: Page, level: str):
    if "/listContent" in page.url:
        return await traverse_list(page, level)
    elif "/ppto-PanoptoCourseTool-BBLEARN" in page.url:
        await page.goto(await page.Jeval("iframe", "iframe => iframe.src"))
        return await traverse_panopto_list(page, level)
    else:
        print(level + "Unsupported content type")

async def traverse_list(page: Page, level: str):
    indices = {"files" : [], "videos" : [], "submodules" : []}

    content_root = page.url
    
    for link, link_text, header in page.JJeval("%(0)s .details a, %(0)s h3 a" % {'0', CONTENT}, "links => links.map(a => [a.href, a.innerText, a.parentElement.tagName == 'H3'])"):
        if "webapps" not in link:
            indices["files"].append(await get_real_filename(link, await page.cookies(), level))
        elif header and link not in page.url:
            print(level + "Descending into : '%s'" % link_text)
            await page.goto(link)
            indices["submodules"].append(await index(page, level + " "))
            await page.goto(content_root)

    return indices

async def traverse_panopto_list(page: Page, level: str):
    indices = { "files": [], "videos": [], "submodules": [] }
    await page.waitForSelector(PANOPTO_CONTENT, timeout=5000)
    await page.waitFor(3000)
    print (level + "There are %d videos " % len(await page.JJ(PANOPTO_CONTENT)))
    for link, link_text in await page.JJeval(PANOPTO_CONTENT, "links => links.map(link => [link.href, link.innerText])"):
        if link:
            indices["videos"].append({"name" : link_text, "link" : link})
            print(level + " Found panopto video : " + link_text)
    return indices

async def get_real_filename(url: str, cookies: list, level: str):
    if "bbcswebdav" in url:
        s_session_id = next(filter(lambda cookie: cookie['name'] == 's_session_id', cookies))['value']
        request = urllib.request.Request(url)
        request.add_header("Cookie", "s_session_id=" + s_session_id)
        try:
            response = urllib.request.urlopen(request, timeout=5)
            url = response.url
        except Exception as e:
            print(level + str(e))
    
    print(level + "Found : " + url)
    return url
            

async def main():
    opts, args = getopt.getopt(sys.argv[1:], "hH0", ["help", "headless", "no-indices"])

    headless = False
    
    for o, a in opts:
        if o in ("-h", "--help"):
            print("-h/--help - print this help menu")
            print("-H/--headless - run in headless mode")
            return
        elif o in ("-H", "--headless"):
            headless = True

    browser = await launch(headless=headless, args=['--no-sandbox',  '--disable-setuid-sandbox'])
    page = await browser.newPage()
    await page.goto('https://tcd.blackboard.com/webapps/bb-auth-provider-shibboleth-BBLEARN/execute/shibbolethLogin?authProviderId=_102_1')

    failed_attempts = 0

    while not await try_login(page):
        failed_attempts += 1
        print("Failed to login. ", end="")
        if failed_attempts < 3:
            print("Try again")
        else:
            print("Exceeded maximum attempts")
            exit()

    print("Logged in!")
    await crawl(page)

try:
    asyncio.get_event_loop().run_until_complete(main())
finally:
    pass
