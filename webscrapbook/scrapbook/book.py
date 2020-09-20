#!/usr/bin/env python3
"""Scrapbook book handler.
"""
import os
import re
import json
import mimetypes
from .. import Config
from .. import util


class TreeFileError(OSError):
    pass


class TreeFileIOError(TreeFileError):
    pass


class TreeFileMalformedError(TreeFileError):
    pass


class Book:
    """Main scrapbook book controller.
    """
    REGEX_TREE_FILE_PREFIX = re.compile(r'^(?:/\*.*\*/|[^(])+\(([\s\S]*)\)(?:/\*.*\*/|[\s;])*$')
    SAVE_META_THRESHOLD = 256 * 1024
    SAVE_TOC_THRESHOLD = 4 * 1024 * 1024
    SAVE_FULLTEXT_THRESHOLD = 128 * 1024 * 1024

    def __init__(self, root, config=None, book_id=''):
        if not config:
            config = Config()
            config.load(root)

        book = config['book'][book_id]
        self.id = book_id
        self.name = book.get('name', 'scrapbook')
        self.top_dir = os.path.normpath(os.path.join(root, book.get('top_dir', '')))
        self.data_dir = os.path.normpath(os.path.join(self.top_dir, book.get('data_dir', '')))
        self.tree_dir = os.path.normpath(os.path.join(self.top_dir, book.get('tree_dir', '.wsb/tree')))
        self.index = os.path.normpath(os.path.join(self.top_dir, book.get('index', '.wsb/tree/map.html')))
        self.no_tree = book.get('no_tree', False)
        self.meta = None
        self.toc = None
        self.fulltext = None

    def __repr__(self):
        data_str = repr({
            'id': self.id,
            'name': self.name,
            'top_dir': self.top_dir,
            })
        return f'{self.__class__.__name__}({data_str})'

    def get_tree_file(self, name, index=0):
        return os.path.join(self.tree_dir, f'{name}{index or ""}.js')

    def iter_tree_files(self, name):
        i = 0
        while True:
            file = self.get_tree_file(name, i)
            if not os.path.exists(file):
                break
            yield file
            i += 1

    def iter_meta_files(self):
        yield from self.iter_tree_files('meta')

    def iter_toc_files(self):
        yield from self.iter_tree_files('toc')

    def iter_fulltext_files(self):
        yield from self.iter_tree_files('fulltext')

    def load_tree_file(self, file):
        try:
            fh = open(file, encoding='UTF-8')
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise TreeFileIOError(f'failed to load tree file: {exc}')
        else:
            with fh as fh:
                text = fh.read()

        m = self.REGEX_TREE_FILE_PREFIX.search(text)

        if not m:
            raise TreeFileMalformedError(f'malformed tree file "{file}"')

        try:
            return json.loads(m.group(1))
        except json.decoder.JSONDecodeError as exc:
            raise TreeFileMalformedError(f'malformed tree file "{file}": {exc}')

    def load_tree_files(self, name):
        data = {}
        for file in self.iter_tree_files(name):
            d = self.load_tree_file(file)
            data.update(d)
        return data

    def load_meta_files(self, refresh=False):
        if refresh or self.meta is None:
            self.meta = self.load_tree_files('meta')

    def load_toc_files(self, refresh=False):
        if refresh or self.toc is None:
            self.toc = self.load_tree_files('toc')

    def load_fulltext_files(self, refresh=False):
        if refresh or self.fulltext is None:
            self.fulltext = self.load_tree_files('fulltext')

    def save_tree_file(self, name, index, data):
        file = self.get_tree_file(name, index)
        try:
            fh = open(file, 'w', encoding='UTF-8', newline='\n')
        except OSError as exc:
            raise TreeFileIOError(f'failed to open tree file: {exc}')
        else:
            with fh as fh:
                fh.write(data)

    def save_meta_file(self, i, data):
        self.save_tree_file('meta', i, f"""/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.meta({json.dumps(data, ensure_ascii=False, indent=2)})""")

    def save_meta_files(self):
        """Save to tree/meta#.js

        A javascript string >= 256 MiB (UTF-16 chars) causes an error
        in the browser. Split each js file at around 256 K items to
        prevent the issue. (An item is mostly < 512 bytes)
        """
        os.makedirs(os.path.join(self.tree_dir), exist_ok=True)
        i = 0
        size = 1
        meta = {}
        for id in self.meta:
            meta[id] = self.meta[id]
            size += 1
            if size >= self.SAVE_META_THRESHOLD:
                self.save_meta_file(i, meta)
                i += 1
                size = 0
                meta = {}

        if size:
            self.save_meta_file(i, meta)
            i += 1

        # remove unused tree/meta#.js
        while True:
            file = self.get_tree_file('meta', i)
            try:
                os.remove(file)
            except FileNotFoundError:
                break
            i += 1

    def save_toc_file(self, i, data):
        self.save_tree_file('toc', i, f"""/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.toc({json.dumps(data, ensure_ascii=False, indent=2)})""")

    def save_toc_files(self):
        """Save to tree/toc#.js

        A javascript string >= 256 MiB (UTF-16 chars) causes an error
        in the browser. Split each js file at around 4 M entries to
        prevent the issue. (An entry is mostly < 32 bytes)
        """
        os.makedirs(os.path.join(self.tree_dir), exist_ok=True)
        i = 0
        size = 1
        toc = {}
        for id in self.toc:
            toc[id] = self.toc[id]
            size += 1 + len(toc[id])
            if size >= self.SAVE_TOC_THRESHOLD:
                self.save_toc_file(i, toc)
                i += 1
                size = 0
                toc = {}

        if size:
            self.save_toc_file(i, toc)
            i += 1

        # remove unused tree/toc#.js
        while True:
            file = self.get_tree_file('toc', i)
            try:
                os.remove(file)
            except FileNotFoundError:
                break
            i += 1

    def save_fulltext_file(self, i, data):
        self.save_tree_file('fulltext', i, f"""/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({json.dumps(data, ensure_ascii=False, indent=1)})""")

    def save_fulltext_files(self):
        """Save to tree/fulltext#.js

        A javascript string >= 256 MiB (UTF-16 chars) causes an error
        in the browser. Split each js file at at around 128 MiB to
        prevent the issue.
        """
        os.makedirs(os.path.join(self.tree_dir), exist_ok=True)
        i = 0
        size = 1
        fulltext = {}
        for id in self.fulltext:
            fulltext[id] = self.fulltext[id]
            for path in fulltext[id]:
                size += len(fulltext[id][path]['content'])
            if size >= self.SAVE_FULLTEXT_THRESHOLD:
                self.save_fulltext_file(i, fulltext)
                i += 1
                size = 0
                fulltext = {}

        if size:
            self.save_fulltext_file(i, fulltext)
            i += 1

        # remove unused tree/fulltext#.js
        while True:
            file = self.get_tree_file('fulltext', i)
            try:
                os.remove(file)
            except FileNotFoundError:
                break
            i += 1

    def mime_is_html(self, mime):
        return mime in {'text/html', 'application/xhtml+xml'}

    def mime_is_archive(self, mime):
        return mime in {'application/html+zip', 'application/x-maff'}

    def mime_is_htz(self, mime):
        return mime == 'application/html+zip'

    def mime_is_maff(self, mime):
        return mime == 'application/x-maff'

    def is_html(self, filename):
        mime, _ = mimetypes.guess_type(filename)
        return self.mime_is_html(mime)

    def is_archive(self, filename):
        mime, _ = mimetypes.guess_type(filename)
        return self.mime_is_archive(mime)

    def is_htz(self, filename):
        mime, _ = mimetypes.guess_type(filename)
        return self.mime_is_htz(mime)

    def is_maff(self, filename):
        mime, _ = mimetypes.guess_type(filename)
        return self.mime_is_maff(mime)

    def get_index_paths(self, index):
        if self.is_maff(index):
            pages = util.get_maff_pages(os.path.join(self.data_dir, index))
            return [p.indexfilename for p in pages]

        if self.is_htz(index):
            return ['index.html']

        return [os.path.basename(index)]
