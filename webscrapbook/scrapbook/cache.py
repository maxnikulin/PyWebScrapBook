#!/usr/bin/env python3
"""Generator of fulltext cache and/or static site pages.
"""
import os
import traceback
import io
import zipfile
import mimetypes
import time
import re
from copy import deepcopy
from collections import namedtuple, UserDict
from urllib.parse import urlsplit, urljoin, quote, unquote

from lxml import etree

from .. import Config
from .book import Book
from .. import util
from .._compat import zip_stream


Info = namedtuple('Info', ['type', 'msg'])
FulltextCacheItem = namedtuple('FulltextCacheItem', ['id', 'meta', 'index', 'indexfile', 'files_to_update'])


class MutatingDict(UserDict):
    """Support mutation during dict iteration.
    """
    def __init__(self, *args, **kwargs):
        self._keys = []

        # this calls __setitem__ internally
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        if key not in self:
            self._keys.append(key)
        super().__setitem__(key, value)

    def __iter__(self):
        return iter(self._keys)

    def __delitem__(self, key):
        return NotImplemented


class FulltextCacheGenerator():
    def run(self, book, inclusive_frames=True):
        yield Info('info', f'Generating fulltext cache...')

        self.book = book
        self.inclusive_frames = inclusive_frames

        try:
            self.cache_last_modified = max(os.stat(f).st_mtime for f in book.iter_fulltext_files())
        except ValueError:
            # no fulltext file
            self.cache_last_modified = 0

        book.load_meta_files()
        book.load_toc_files()
        book.load_fulltext_files()
        book_fulltext_orig = deepcopy(book.fulltext)

        # Remove stale cache for nonexist items
        for id in list(book.fulltext):
            if id not in book.meta:
                del book.fulltext[id]
                yield Info('info', f'Removed stale cache for "{id}".')

        # Index each items
        for id, meta in book.meta.items():
            index = meta.get('index')

            # no index: remove cache for id
            if not index:
                try:
                    del book.fulltext[id]
                except KeyError:
                    pass
                else:
                    yield Info('info', f'Removed stale cache for "{id}".')
                continue

            indexfile = os.path.join(book.data_dir, index)

            # no index file: remove cache for id
            if not os.path.exists(indexfile):
                try:
                    del book.fulltext[id]
                except KeyError:
                    pass
                else:
                    yield Info('info', f'Removed stale cache for "{id}".')
                continue

            # a mapping file path => status
            # status: True for a file to be checked; False for a file (mostly
            # an inclusive iframe) that is not available as inline,
            # (already added to cache or to be removed from cache)
            files_to_update = MutatingDict()

            item = FulltextCacheItem(id, meta, index, indexfile, files_to_update)
            self._collect_files_to_update(item)
            yield from self._handle_files_to_update(item)

        if book.fulltext != book_fulltext_orig:
            book.save_fulltext_files()
        else:
            # touch fulltext cache files to prevent falsely detected as outdated
            for file in book.iter_fulltext_files():
                os.utime(file)

    def _collect_files_to_update(self, item):
        book = self.book
        id, meta, index, indexfile, files_to_update = item

        # create cache for this id if not exist yet
        if id not in book.fulltext:
            book.fulltext[id] = {}
            for path in book.get_index_paths(index):
                files_to_update[path] = True
            return

        # presume no change if archive file not newer than cache file
        if book.is_archive(indexfile):
            if os.stat(indexfile).st_mtime <= self.cache_last_modified:
                return

        # add index file(s) to update list
        for path in book.get_index_paths(index):
            files_to_update[path] = True

        # add files in cache to update list
        for path in book.fulltext[id]:
            files_to_update[path] = True

    def _handle_files_to_update(self, item):
        def report_update():
            nonlocal has_update
            if has_update:
                return
            if book.fulltext[id]:
                yield Info('info', f'Updating cache for "{id}"...')
            else:
                yield Info('info', f'Creating cache for "{id}"...')
            has_update = True
            
        book = self.book
        id, meta, index, indexfile, files_to_update = item
        is_archive = book.is_archive(indexfile)
        has_update = False

        for path in files_to_update:
            # remove from cache if marked False
            if not files_to_update[path]:
                if path in book.fulltext[id]:
                    yield from report_update()
                    del book.fulltext[id][path]
                continue

            # mark False to prevent added otherwhere
            files_to_update[path] = False

            mtime = self._get_mtime(item, path)
            if mtime is None:
                # path not exist => delete from cache
                if path in book.fulltext[id]:
                    yield from report_update()
                    del book.fulltext[id][path]
                continue

            # check if update is needed
            if path not in book.fulltext[id]:
                pass
            elif mtime <= self.cache_last_modified:
                continue

            yield from report_update()

            # set updated fulltext
            try:
                fulltext = self._get_fulltext_cache(item, path) or ''
            except Exception:
                fulltext = ''
                traceback.print_exc()
                yield Info('error', f'Unable to generate cache for "{id}" ({path})')

            book.fulltext[id][path] = {
                'content': fulltext,
                }

    def _get_mtime(self, item, path):
        if self.book.is_archive(item.index):
            with zipfile.ZipFile(os.path.join(self.book.data_dir, item.index)) as zh:
                try:
                    info = zh.getinfo(path)
                    return util.zip_timestamp(info)
                except KeyError:
                    return None

        file = os.path.join(self.book.data_dir, os.path.dirname(item.index), path)
        try:
            return os.stat(file).st_mtime
        except OSError:
            return None

    def _open_file(self, item, path):
        if self.book.is_archive(item.index):
            with zipfile.ZipFile(os.path.join(self.book.data_dir, item.index)) as zh:
                try:
                    return zh.open(path)
                except KeyError:
                    return None

        file = os.path.join(self.book.data_dir, os.path.dirname(item.index), path)
        try:
            return open(file, 'rb')
        except OSError:
            # @TODO: show error message for exist but unreadable file?
            return None

    def _get_fulltext_cache(self, item, path):
        fh = self._open_file(item, path)
        if not fh:
            return None

        fh = zip_stream(fh)
        try:
            mime, _ = mimetypes.guess_type(path)
            return self._get_fulltext_cache_for_fh(item, path, fh, mime)
        finally:
            fh.close()

    def _get_fulltext_cache_for_fh(self, item, path, fh, mime):
        if not mime:
            pass
        elif self.book.mime_is_html(mime):
            return self._get_fulltext_cache_html(item, path, fh)
        elif mime.startswith('text/'):
            return self._get_fulltext_cache_txt(item, fh)

    def _get_fulltext_cache_html(self, item, path, fh):
        def get_relative_file_path(url):
            # skip when inside a data URL page (can't resolve)
            if path is None:
                return None

            urlparts = urlsplit(url)

            # skip absolute URLs
            if urlparts.scheme != '':
                return None

            if urlparts.netloc != '':
                return None

            if urlparts.path.startswith('/'):
                return None

            base = get_relative_file_path.base = getattr(get_relative_file_path, 'base', 'file:///!/')
            ref = get_relative_file_path.ref = getattr(get_relative_file_path, 'ref', urljoin(base, quote(path)))
            target = urljoin(ref, urlparts.path)

            # skip if URL contains '..'
            if not target.startswith(base):
                return None

            target = unquote(target)

            # ignore referring self
            if target == ref:
                return None

            target = target[len(base):]

            return target

        # @TODO: show message for malformed data URLs
        def add_datauri_content(url):
            try:
                data = util.parse_datauri(url)
            except util.DataUriMalformedError:
                return
            fh = io.BytesIO(data.bytes)
            fulltext = self._get_fulltext_cache_for_fh(item, None, fh, data.mime)
            if fulltext:
                results.append(fulltext)

        # Seek for the correct charset (encoding).
        # If a charset is not specified, lxml may select a wrong encoding for
        # the entire document if there is text before first meta charset.
        # Priority: BOM > meta charset > item charset > assume UTF-8
        charset = util.sniff_bom(fh)
        if charset:
            # lxml does not accept "UTF-16-LE" or so, but can auto-detect
            # encoding from BOM if encoding is None
            # ref: https://bugs.launchpad.net/lxml/+bug/1463610
            charset = None
            fh.seek(0)
        else:
            charset = util.get_charset(fh) or item.meta.get('charset') or 'UTF-8'
            charset = util.fix_codec(charset)
            fh.seek(0)

        results = []
        has_instant_redirect = False
        for time, url in util.iter_meta_refresh(fh):
            if time == 0:
                has_instant_redirect = True

            if url:
                if url.startswith('data:'):
                    add_datauri_content(url)
                else:
                    target = get_relative_file_path(url)
                    if target and target not in item.files_to_update:
                        item.files_to_update[target] = True

        # Add data URL content of meta refresh targets to fulltext index if the
        # page has an instant meta refresh.
        if has_instant_redirect:
            if results:
                return self.REGEX_TEXT_SPACE_CONVERTER.sub(' ', ' '.join(results)).strip()
            return None

        # add main content
        # Note: adding elem.text at start event or elem.tail at end event is
        # not reliable as the parser hasn't load full content of text or tail
        # at that time yet.
        # @TODO: better handle content
        # (no space between inline nodes, line break between block nodes, etc.)
        fh.seek(0)
        exclusion_stack = []
        for event, elem in etree.iterparse(fh, html=True, events=('start', 'end'),
                remove_comments=True, encoding=charset):
            if event == 'start':
                # skip if we are in an excluded element
                if exclusion_stack:
                    continue

                # Add last text before starting of this element.
                prev = elem.getprevious()
                attr = 'tail'
                if prev is None:
                    prev = elem.getparent()
                    attr = 'text'

                if prev is not None:
                    text = getattr(prev, attr)
                    if text:
                        results.append(text)
                        setattr(prev, attr, None)

                if elem.tag in ('a', 'area'):
                    # include linked pages in fulltext index
                    try:
                        url = elem.attrib['href']
                    except KeyError:
                        pass
                    else:
                        if url.startswith('data:'):
                            add_datauri_content(url)
                        else:
                            target = get_relative_file_path(url)
                            if target and target not in item.files_to_update:
                                item.files_to_update[target] = True

                elif elem.tag in ('iframe', 'frame'):
                    # include frame page in fulltext index
                    try:
                        url = elem.attrib['src']
                    except KeyError:
                        pass
                    else:
                        if url.startswith('data:'):
                            add_datauri_content(url)
                        else:
                            target = get_relative_file_path(url)
                            if target:
                                if self.inclusive_frames:
                                    # Add frame content to the current page
                                    # content if the targeted file hasn't
                                    # been indexed.
                                    if item.files_to_update.get(target) is not False:
                                        item.files_to_update[target] = False
                                        fulltext = self._get_fulltext_cache(item, target)
                                        if fulltext:
                                            results.append(fulltext)
                                else:
                                    if target not in item.files_to_update:
                                        item.files_to_update[target] = True

                # exclude everything inside certain tags
                if elem.tag in self.FULLTEXT_EXCLUDE_TAGS:
                    exclusion_stack.append(elem)
                    continue

            elif event == 'end':
                # Add last text before ending of this element.
                if not exclusion_stack:
                    try:
                        prev = elem[-1]
                        attr = 'tail'
                    except IndexError:
                        prev = elem
                        attr = 'text'

                    if prev is not None:
                        text = getattr(prev, attr)
                        if text:
                            results.append(text)
                            setattr(prev, attr, None)
            
                # stop exclusion at the end of an excluding element
                try:
                    if elem is exclusion_stack[-1]:
                        exclusion_stack.pop()
                except IndexError:
                    pass

                # clean up to save memory
                # remember to keep tail
                elem.clear(keep_tail=True)
                while elem.getprevious() is not None:
                    try:
                        del elem.getparent()[0]
                    except TypeError:
                        # broken html may generate extra root elem
                        break

        return self.REGEX_TEXT_SPACE_CONVERTER.sub(' ', ' '.join(results)).strip()

    def _get_fulltext_cache_txt(self, item, fh):
        charset = util.sniff_bom(fh) or item.meta.get('charset') or 'UTF-8'
        charset = util.fix_codec(charset)
        text = fh.read().decode(charset, errors='replace')
        return self.REGEX_TEXT_SPACE_CONVERTER.sub(' ', text).strip()

    REGEX_TEXT_SPACE_CONVERTER = re.compile(r'\s+')
    FULLTEXT_EXCLUDE_TAGS = {
        'title', 'style', 'script',
        'frame', 'iframe',
        'object', 'applet',
        'audio', 'video',
        'canvas',
        'noframes', 'noscript', 'noembed',
        # 'parsererror',
        'svg', 'math',
        }


def generate(root, books=[],
        fulltext=True, inclusive_frames=True):
    start = time.time()

    config = Config()
    config.load(root)

    # cache all books if none specified
    if not books:
        books = list(config['book'])

    _books = set(config['book'])
    for book_id in books:
        # skip invalid book ID
        if book_id not in _books:
            yield Info('warn', f'Skipping invalid book "{book_id}".')
            continue

        yield Info('info', f'Caching book "{book_id}".')

        try:
            book = Book(root, config, book_id)

            if fulltext:
                yield from FulltextCacheGenerator().run(book, inclusive_frames)
        except Exception as exc:
            traceback.print_exc()
            yield Info('error', f'Unexpected error: {exc}')
        else:
            yield Info('info', 'Done.')

        yield Info('info', '')

    elapsed = time.time() - start
    yield Info('debug', f'Time spent: {elapsed} seconds.')
