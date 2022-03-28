import json
import os
import os.path
import re
import ffmpeg
import urllib3
from urllib.parse import unquote

current_output_dir = ""
crawlfile_path = "crawl.json"
http = urllib3.PoolManager()
        
def download_panopto_stream(stream_url: str, link_text: str, level: str):
    master_response = http.request("GET", stream_url)
    master_data = master_response.data
    master = master_data.decode('utf-8')

    first_master_entry = re.findall(r"\d+/index\.m3u8", master, re.MULTILINE)[0]

    url = re.sub(r"master\.m3u8.*", "", stream_url) + first_master_entry
    index_response = http.request("GET", url)
    index_data = index_response.data
    index = index_data.decode('utf-8')

    ts = current_output_dir + link_text.strip() + ".ts"
    mp4 = current_output_dir + link_text.strip() + ".mp4"

    output_ts = open(ts, 'wb')
    ts_files = re.sub(r"#.*\n", "", index).splitlines()
    total_parts = int(ts_files[-1].strip(".ts")) # Very hacky, may change later
    for ts_file in ts_files:
        if ts_file:
            print(level + 'Downloading part %d/%d' % (int(ts_file.strip(".ts")),  total_parts))
            part_url = re.sub(r"master\.m3u8.*", first_master_entry.split('/')[0] + '/' + ts_file, stream_url)
            part_response = http.request("GET", part_url)
            output_ts.write(part_response.data)

    output_ts.close()

    stream = ffmpeg.input(ts)
    stream = ffmpeg.output(stream, mp4, **{'bsf:a': 'aac_adtstoasc', 'acodec': 'copy', 'vcodec': 'copy'})
    ffmpeg.run(stream)
    
    try:
        os.remove(ts)
    except Exception:
        pass

def download_file(url: str, JSESSIONID: str, level: str):
    try:
        response = http.request("GET", url, headers={"Cookie" : "JSESSIONID="+JSESSIONID}, timeout=3)
    except Exception as e:
        print(level + "└" + str(e))
        return
    output_file_path = os.path.basename(unquote(url))
    if not output_file_path:
        output_file_path = os.path.basename(url.strip("/"))
    temp_file_path = output_file_path + ".uncompleted-write"

    if not os.path.isfile(output_file_path):
        print(level + "└" + output_file_path + " does not exist. Downloading...")
        temp_file = open(temp_file_path, "wb")
        temp_file.write(response.data)
        temp_file.close()
        os.rename(temp_file_path, output_file_path)
    else:
        print(level + "└" + output_file_path + " exists. Not downloading!")

def download_submodule(submodule: dict, JSESSIONID: str, level: str, type_choices: dict):
    if type_choices['documents'] | type_choices['other']:
        for file in submodule.get('files', []):
            print(level + "Downloading : " + file)
            download_file(file, JSESSIONID, level)
    if type_choices['videos']:
        for video in submodule.get('videos', []):
            print(level + "Downloading video '%s'" % video['name'])
            download_panopto_stream(video['link'], video['name'], level + " ")
    for submodule in submodule.get('submodules', []):
        if submodule:
            download_submodule(submodule, JSESSIONID, level + " ", type_choices)

def download(crawl_path: str, choices_path: str, JSESSIONID: str, type_choices: dict):
    choices_file = open(choices_path, "r")
    crawl_file = open(crawl_path, "r")
    choices = json.load(choices_file)
    modules = json.load(crawl_file)
    choices_file.close()
    crawl_file.close()
    module_choices = choices['module_choices']
    type_choices = choices['type_choices']

    pruned_crawl = []
    for module in modules:
        pruned_crawl.append({'name' : module['name'], 'submodules' : [submodule for submodule in module['submodules'] if module_choices[module['name']][submodule['name']]] })

    if not os.path.exists("downloads"):
        os.mkdir("downloads")
    os.chdir("downloads")
    downloads_dir = os.getcwd()
    for module in pruned_crawl:
        print("Downloading module '%s'" % module['name'])
        folder_name = module['name'].replace("/", "")
        if not os.path.exists(folder_name):
            os.mkdir(folder_name)
        os.chdir(folder_name)
        for submodule in module['submodules']:
            sub_folder_name = submodule['name'].replace("/", "")
            print(" Downloading submodule '%s'" % sub_folder_name)
            download_submodule(submodule, JSESSIONID, "  ", type_choices)
        os.chdir(downloads_dir)
