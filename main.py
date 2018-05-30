from urllib import request
from urllib import parse
from html.parser import HTMLParser

import os, time, json, threading, queue


# list of jobs
JOB_LIST_FILENAME = 'targets.txt'

# the grand folder to contain all images to download
TARGET_FOLDER_NAME = 'Sprites_all'

# in seconds
SYNC_INTERVAL = 15

USER_AGENT = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
NUM_THREADS = 16


if not os.path.isdir(TARGET_FOLDER_NAME):
    os.mkdir(TARGET_FOLDER_NAME)



def get_raw_data(url, headers=dict()):
        headers['User-Agent'] = USER_AGENT
        try:
            req = request.Request(url, headers=headers)
            resp = request.urlopen(req)
            encoding = 'utf-8'
            for val in resp.getheader('Content-Type').split(';'):
                if 'charset' in val:
                    encoding = val.split('=')[-1].strip()
            if resp.readable():
                return resp.read().decode(encoding)
        except Exception as e:
            printQueue.put("Error while accessing " + url + ":" + str(e))
            return ''



def download_file(url, filename='', headers=dict()):
        filename = filename or url.split('/')[-1]
        headers['User-Agent'] = USER_AGENT
        try:
            req = request.Request(url, headers=headers)
            resp = request.urlopen(req)
            with open(filename, 'wb') as F:
                F.write(resp.read())
            return True
        except Exception as e:
            printQueue.put("Error while downloading " + url + ":" + str(e))
            return False


# To extract all unique images from a page
class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.base_url = 'https://archives.bulbagarden.net/'
        self.img_urls = set()
    
    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            for k, v in attrs:
                if k == 'src':
                    url = parse.urljoin(self.base_url, v)
                    self.img_urls.add(url)


def worker_print():
    while True:
        job = printQueue.get()
        print(job)
        printQueue.task_done()


def worker_sync():
    lastSyncTime = time.time()
    while True:
        syncRequestQueue.get()
        currentTime = time.time()
        if currentTime - lastSyncTime >= SYNC_INTERVAL:
            printQueue.put("Syncing to " + JOB_LIST_FILENAME)
            with open(JOB_LIST_FILENAME) as f:
                f.write(json.dumps(list(jobQueue.queue)))
            lastSyncTime = currentTime
        syncRequestQueue.task_done()


def worker():
    while True:
        job = jobQueue.get()
        
        if job[0] == 'parse': # new Pokemon page
            dex, name = job[1], job[2].split(':')[-1]
            printQueue.put("Parsing Pokemon Page: " + name)
            
            data = get_raw_data(job[2])
            p = MyHTMLParser()
            p.feed(data)
            for url in p.img_urls:
                filename = url.split('/')[-1]
                if dex in filename or name.lower() in filename.lower():
                    subFolderPath = os.path.join(TARGET_FOLDER_NAME, dex)
                    filepath = os.path.join(subFolderPath, filename)
                    if not os.path.isdir(subFolderPath):
                        os.mkdir(subFolderPath)
                    if not os.path.isfile(filepath):
                        jobQueue.put(['retrieve', url, filepath])
                        
        elif job[0] == 'retrieve': # download an image
            printQueue.put("Downloading: " + job[1])
            download_file(job[1], job[2])

        syncRequestQueue.put(0)
        jobQueue.task_done()





printQueue = queue.Queue()
pt = threading.Thread(target=worker_print)
pt.daemon = True
pt.start()

syncRequestQueue = queue.Queue()
st = threading.Thread(target=worker_sync)
st.daemon = True
st.start()


jobQueue = queue.Queue()
with open(JOB_LIST_FILENAME) as f:
    for j in json.load(f):
        jobQueue.put(j)

for i in range(NUM_THREADS):
     t = threading.Thread(target=worker)
     t.daemon = True
     t.start()

jobQueue.join()

# printQueue.join()
