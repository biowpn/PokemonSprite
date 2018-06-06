from urllib import request, parse
from html.parser import HTMLParser

import os, time, json, threading, queue, re, shutil


# Basics
NumThreads = 16
MaxNumOfFiles = 140000
PageLimit = 1000
BaseUrl = "https://archives.bulbagarden.net/w/index.php"
QueryModel = {
    "title": "Special:MIMESearch",
    "mime": "image/png",
    "limit": PageLimit,
    "offset": 0
}

# The folder to contain all images to download
GrandFolder = "Sprites_all"

# The file to record queued tasks
JobsQueuedFilename = 'queue.txt'

# How files matched the pattern will be handled in order.
# Each logic is a dictionary-like object with the following attributes:
#   - [cmd]
#   - [pat]
#   - [dst] (Optional)
# [cmd] may take the following values:
#   - "save": the file will be saved to a folder specified by [dst].
#   - "skip": skip this file. The subsequenet handling logics will be ignored

Patterns = [
    {
        "cmd": "save",
        "pat": "[0-9]{3}[A-Z]?[A-Z|a-z]*MS\.png",
        "dst": "Pattern_1"
    },
    {
        "cmd": "save",
        "pat": "Shuffle[0-9]{3}\.png",
        "dst": "Pattern_2"
    },
    {
        "cmd": "skip",
        "pat": ".*?_Channel\.png"
    },
    {
        "cmd": "skip",
        "pat": ".*?_Dream_.*?"
    },
    {
        "cmd": "save",
        "pat": "[0-9]{3}[A-Z][a-z]+([\.|\-|\:|\_][A-Z][a-z]*)*\.png",
        "dst": "Pattern_3"
    }
]

# in seconds
SyncIntervalS = 5

DefaultUserAgent = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"



if not os.path.isdir(GrandFolder):
    os.mkdir(GrandFolder)
if not os.path.isfile(JobsQueuedFilename):
    with open(JobsQueuedFilename, 'w') as F:
        F.write('[]')

# Organizing files
def iter_files(directory, pattern, cmd = 'count'):
    count = 0
    for file in os.listdir(directory):
        if re.fullmatch(pattern, file):
            count += 1
            fullFilepath = os.path.join(directory, file)
            cmds = cmd.split()
            if cmds[0] in ['sc', 'scan']:
                print(fullFilepath)
            elif cmds[0] == ['cp', 'copy']:
                if not os.path.isdir(cmds[1]):
                    os.mkdir(cmds[1])
                shutil.copyfile(fullFilepath, cmds[1])
            elif cmds[0] == ['mv', 'move']:
                if not os.path.isdir(cmds[1]):
                    os.mkdir(cmds[1])
                shutil.move(fullFilepath, cmds[1])
            elif cmds[0] == ['del', 'delete']:
                os.remove(fullFilepath)
    if cmds[0] in ['ct', 'count']:
        return count


# Get raw HTML codes from a page specified by [url]
def get_raw_data(url, headers=dict()):
        headers['User-Agent'] = DefaultUserAgent
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

# Download a file and save it to a directory specified by [dst]
def download_file(src, dst='', headers=dict()):
        dst = dst or url.split('/')[-1]
        headers['User-Agent'] = DefaultUserAgent
        try:
            req = request.Request(src, headers=headers)
            resp = request.urlopen(req)
            with open(dst, 'wb') as F:
                F.write(resp.read())
            return True
        except Exception as e:
            printQueue.put("Error while downloading " + src + ":" + str(e))
            return False


# To extract all unique image URLs from a page
class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.base_url = BaseUrl
        self.img_urls = set()
    
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            url = ''
            isTarget = False
            for k, v in attrs:
                if k == 'href':
                    url = parse.urljoin(self.base_url, v)
                elif k == 'class' and v == 'internal':
                    isTarget = True
            if isTarget and url:
                self.img_urls.add(url)


def worker_print():
    while True:
        job = printQueue.get()
        print(job)
        printQueue.task_done()


def worker_sync():
    hasEnded = False
    lastSyncTime = time.time()
    while not hasEnded:
        hasEnded = syncRequestQueue.get()
        currentTime = time.time()
        if hasEnded or currentTime - lastSyncTime >= SyncIntervalS:
            printQueue.put("Saving Progess...")
            with open(JobsQueuedFilename, 'w') as f:
                f.write(json.dumps(list(jobQueue.queue)))
            lastSyncTime = currentTime
        syncRequestQueue.task_done()


def worker():
    while True:
        job = jobQueue.get()
        
        if job.get('cmd') == 'parse': # new Pokemon page
            pageUrl = job.get('url')
            
            printQueue.put("Parsing Page: " + pageUrl)
            data = get_raw_data(pageUrl)
            
            p = MyHTMLParser()
            p.feed(data)
            for url in p.img_urls:
                filename = url.split('/')[-1]
                for i, logic in enumerate(Patterns):
                    if re.fullmatch(logic.get('pat'), filename):
                        if logic.get('cmd') == 'save':
                            dst = os.path.join(GrandFolder, logic.get('dst', "Pattern_" + str(i+1)), filename)
                            jobQueue.put({
                                "cmd": "retrieve",
                                "url": url,
                                "dst": dst
                            })
                        elif logic.get('cmd') == 'skip':
                            break
                        
        elif job.get('cmd') == 'retrieve': # download an image
            url, dst = job.get('url'), job.get('dst')
            dstdir = os.path.split(dst)[0]
            if not os.path.isdir(dstdir):
                os.mkdir(dstdir)
            if not os.path.isfile(dst):
                printQueue.put("Downloading: " + url)
                download_file(url, dst)

        if jobQueue.empty(): # All jobs done, force sync
            syncRequestQueue.put(1)
        else:
            syncRequestQueue.put(0)
            
        jobQueue.task_done()


printQueue = queue.Queue()
syncRequestQueue = queue.Queue()
jobQueue = queue.Queue()


pt = threading.Thread(target=worker_print)
pt.daemon = True
pt.start()

st = threading.Thread(target=worker_sync)
st.daemon = True
st.start()

with open(JobsQueuedFilename) as f:
    for j in json.load(f):
        jobQueue.put(j)
            
offset = 0
while offset < MaxNumOfFiles:
    q = QueryModel.copy()
    q['offset'] = offset
    jobQueue.put({
        "cmd": "parse",
        "url": BaseUrl + '?' + parse.urlencode(q)
    })
    offset += PageLimit
        
for i in range(NumThreads):
     t = threading.Thread(target=worker)
     t.daemon = True
     t.start()

jobQueue.join()
