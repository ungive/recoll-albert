# -*- coding: utf-8 -*-
from albert import *
from pathlib import Path
from sys import platform
from collections import Counter
import os
import traceback

import sys
sys.path.append('/usr/local/lib64/python3.13/site-packages')

from recoll import recoll

md_iid = "3.0"
md_version = "1.0"
md_name = "Recoll"
md_description = "Search Recoll index"
md_license = "MIT"
md_url = "https://github.com/gerardsimons/recoll-albert"
md_authors = "Gerard Simons"

config = {
    # Files are searched immediately when opening Albert.
    # This will make it impossible to use other actions.
    'always_search_files': True,
    'reveal-file-command': {
        # FIXME This is only for nautilus.
        # The order is important, otherwise Nautilus unzips ZIP archives.
        'linux': ['nautilus', '--select', '', '--new-window']
    }
}

icon_path = str(Path(__file__).parent / "recoll.svg")
remove_duplicates = True

def extract_around_match(query: str, abstract: str, N: int = 80) -> str:
    """
    Find the substring of abstract best matching the query and return up to N chars 
    centered on the entire matching substring (not just start).

    Args:
      query (str): the search query
      abstract (str): text to search in
      N (int): length of snippet around the best match

    Returns:
      str: snippet of abstract around best match
    """

    query = query.lower()
    abstract_lower = abstract.lower()

    qlen = len(query)
    alen = len(abstract)

    if qlen == 0 or alen == 0:
        return ""

    window_size = qlen
    best_pos = 0
    best_score = -1

    for i in range(alen - window_size + 1):
        window = abstract_lower[i:i+window_size]
        score = sum(1 for a, b in zip(window, query) if a == b)
        if score > best_score:
            best_score = score
            best_pos = i

    # Center snippet around the middle of the matched substring
    match_center = best_pos + (qlen // 2)
    half_len = N // 2

    start = max(0, match_center - half_len)
    end = start + N

    # Adjust if snippet goes past the abstract length
    if end > alen:
        end = alen
        start = max(0, end - N)

    snippet = abstract[start:end]

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < alen else ""

    return prefix + snippet + suffix

def replace_home_with_tilde(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path
    
from pathlib import Path

def find_system_mime_icon(mime_type: str):
    icon_name = mime_type.replace('/', '-')
    sizes = [32, 36, 48, 64, 72, 96, 128, 192, 256]
    icon_dirs = [
        '/usr/share/icons/breeze',
    ]
    extensions = ['.png', '.svg', '.xpm']

    for icon_dir in icon_dirs:
        for size in sizes:
            size_str = f"{size}x{size}"

            # First try: /size/mimetypes/icon_name.ext
            for ext in extensions:
                path1 = Path(icon_dir) / size_str / 'mimetypes' / (icon_name + ext)
                if path1.is_file():
                    return str(path1)

            # Fallback try: /mimetypes/size/icon_name.ext
            for ext in extensions:
                path2 = Path(icon_dir) / 'mimetypes' / str(size) / (icon_name + ext)
                if path2.is_file():
                    return str(path2)

        # Also fallback to mimetypes folder root without size
        for ext in extensions:
            path3 = Path(icon_dir) / 'mimetypes' / (icon_name + ext)
            if path3.is_file():
                return str(path3)

    return None



class Plugin(PluginInstance, TriggerQueryHandler):

    def __init__(self):
        PluginInstance.__init__(self)
        TriggerQueryHandler.__init__(self)
        
        self.cache_path = Path(self.cacheLocation()) / "recoll"
        self.config_path = Path(self.configLocation()) / "recoll"
        self.data_path = Path(self.dataLocation()) / "recoll"

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

    def defaultTrigger(self):
        return "" if config['always_search_files'] else "rc "

    def query_rec(self, query_str, max_results=10, max_chars=80, context_words=1):
        if not recoll:
            return []

        if not query_str:
            return []
            
        query_str = f'{query_str}*'

        try:
            db = recoll.connect()
            db.setAbstractParams(maxchars=max_chars, contextwords=context_words)
            query = db.query()
            nres = query.execute(query_str)
            if nres > max_results:
                nres = max_results
            docs = [query.fetchone() for _ in range(nres)]
            # print([d.abstract for d in docs])
            return docs
        except Exception:
            if __debug__:
                traceback.print_exc()
            return []

    def remove_duplicate_docs(self, docs):
        urls = [x.url for x in docs]
        url_count = Counter(urls)

        duplicates = [k for k in url_count if url_count[k] > 1]

        for dup in duplicates:
            best_doc = None
            best_rating = -1
            for doc in [x for x in docs if x.url == dup]:
                rating = float(doc.relevancyrating.replace("%", ""))
                if rating > best_rating:
                    best_doc = doc
                    best_rating = rating
            docs = [x for x in docs if x.url != dup]
            docs.append(best_doc)
        return docs

    def path_from_url(self, url: str) -> str:
        if not url.startswith("file://"):
            return None
        return url.replace("file://", "")

    def get_reveal_file_action(self, dir_path: str, file_path: str):
        print(dir_path, file_path)
        if sys.platform.startswith("linux"):
            return Action(
                id="reveal_in_file_browser",
                text="Reveal in file browser",
                callable=lambda: runDetachedProcess([file_path if x == "" else x for x in config['reveal-file-command']['linux']])
            )
        elif sys.platform == "darwin":
            # FIXME doesnt reveal the file
            return Action(
                id="reveal_in_file_browser",
                text="Reveal in file browser",
                callable=lambda: runDetachedProcess(['open', dir_path])
            )
        elif sys.platform == "win32":
            # FIXME doesnt reveal the file
            return Action(
                id="reveal_in_file_browser",
                text="Reveal in file browser",
                callable=lambda: os.startfile(dir_path)
            )
        else:
            return None

    def doc_to_icon_path(self, doc):
        mime_str = getattr(doc, "mtype", None)
        if not mime_str:
            return icon_path
        mime_str = mime_str.replace("/", "-")
        icon_p = find_system_mime_icon(mime_str)
        if not icon_p:
            icon_p = find_system_mime_icon("text-plain")
        if not icon_p:
            icon_p = icon_path
        return icon_p

    def recoll_docs_as_items(self, docs, query):
        items = []
        if remove_duplicates:
            docs = self.remove_duplicate_docs(docs)

        for doc in docs:
            path = self.path_from_url(doc.url)
            if not path:
                continue
            dir_path = os.path.dirname(path)
            dir_open = self.get_reveal_file_action(dir_path, path)

            # FIXME Albert does not show any actions and only starts the first one with Enter.
            actions = []
            if dir_open:
                actions.append(dir_open)
            actions.append(Action("open_with_default_application", "Open with default application", lambda u=doc.url: openUrl(u)))
                
            abstract = doc.abstract
            abstract = extract_around_match(query, abstract, 80)

            # FIXME
            """
            actions.extend([
                TermAction(
                    text="Open terminal at this path",
                    commandline=[""],
                    behavior=TermAction.CloseBehavior.DoNotClose,
                    cwd=dir_path
                ),
                ClipAction("Copy file to clipboard", open(path, 'rb').read()),
                ClipAction("Copy path to clipboard", path),
            ])
            """

            items.append(
                StandardItem(
                    id=self.id(),
                    iconUrls=[self.doc_to_icon_path(doc)],
                    text=f"{doc.filename} • {replace_home_with_tilde(dir_path)}",
                    subtext=abstract,
                    actions=actions
                )
            )
        return items

    def handleTriggerQuery(self, query):
        if not recoll:
            query.add(
                StandardItem(
                    id=self.id(),
                    iconUrls=[icon_path],
                    text="Recoll Python module not found",
                    subtext="Make sure Recoll Python bindings are installed and in your PYTHONPATH",
                )
            )
            return

        if not query.string.strip():
            return

        try:
            qs = query.string.strip()
            docs = self.query_rec(qs)
            items = self.recoll_docs_as_items(docs, qs)
            for item in items:
                query.add(item)
        except Exception:
            if __debug__:
                traceback.print_exc()
            query.add(
                StandardItem(
                    id=self.id(),
                    iconUrls=[icon_path],
                    text="Error querying Recoll",
                    subtext="Check logs for details",
                )
            )
