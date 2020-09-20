from unittest import mock
import unittest
import os
import shutil
import io
import zipfile
import time
import functools
from webscrapbook import WSB_DIR, Config
from webscrapbook.scrapbook import book as wsb_book
from webscrapbook.scrapbook.book import Book

root_dir = os.path.abspath(os.path.dirname(__file__))
test_root = os.path.join(root_dir, 'test_scrapbook_book')

def setUpModule():
    # mock out WSB_USER_CONFIG
    global mocking
    mocking = mock.patch('webscrapbook.WSB_USER_CONFIG', test_root)
    mocking.start()

def tearDownModule():
    # stop mock
    mocking.stop()

class TestBook(unittest.TestCase):
    def setUp(self):
        """Set up a general temp test folder
        """
        self.maxDiff = 8192
        self.test_root = os.path.join(test_root, 'general')
        self.test_wsbdir = os.path.join(self.test_root, WSB_DIR)
        self.test_config = os.path.join(self.test_root, WSB_DIR, 'config.ini')

        try:
            shutil.rmtree(self.test_root)
        except NotADirectoryError:
            os.remove(self.test_root)
        except FileNotFoundError:
            pass

        os.makedirs(self.test_wsbdir)

    def tearDown(self):
        """Remove general temp test folder
        """
        try:
            shutil.rmtree(self.test_root)
        except NotADirectoryError:
            os.remove(self.test_root)
        except FileNotFoundError:
            pass

    def create_general_config(self):
        with open(self.test_config, 'w', encoding='UTF-8') as f:
            f.write("""[book ""]
name = scrapbook
top_dir =
data_dir = data
tree_dir = tree
index = tree/map.html
no_tree = false
""")

    def test_init01(self):
        """Check basic"""
        with open(self.test_config, 'w', encoding='UTF-8') as f:
            f.write("""[book ""]
name = scrapbook
top_dir = 
data_dir = data
tree_dir = tree
index = tree/map.html
no_tree = false
""")

        book = Book(self.test_root)

        self.assertEqual(book.id, '')
        self.assertEqual(book.name, 'scrapbook')
        self.assertEqual(book.top_dir, self.test_root)
        self.assertEqual(book.data_dir, os.path.join(self.test_root, 'data'))
        self.assertEqual(book.tree_dir, os.path.join(self.test_root, 'tree'))
        self.assertEqual(book.index, os.path.join(self.test_root, 'tree', 'map.html'))
        self.assertFalse(book.no_tree)

    def test_init02(self):
        """Check book_id param"""
        with open(self.test_config, 'w', encoding='UTF-8') as f:
            f.write("""[book "book1"]
name = scrapbook1
top_dir =
data_dir =
tree_dir = .wsb/tree
index = .wsb/tree/map.html
no_tree = false
""")

        book = Book(self.test_root, book_id='book1')
        self.assertEqual(book.id, 'book1')
        self.assertEqual(book.name, 'scrapbook1')
        self.assertEqual(book.top_dir, self.test_root)
        self.assertEqual(book.data_dir, self.test_root)
        self.assertEqual(book.tree_dir, os.path.join(self.test_root, '.wsb', 'tree'))
        self.assertEqual(book.index, os.path.join(self.test_root, '.wsb', 'tree', 'map.html'))
        self.assertFalse(book.no_tree)

    def test_init03(self):
        """Check config param"""
        other_root = os.path.join(self.test_root, 'rootdir')
        os.makedirs(other_root)
        with open(self.test_config, 'w', encoding='UTF-8') as f:
            f.write("""[book ""]
name = book1
top_dir = sb1
data_dir = data
tree_dir = tree
index = tree/map.html
no_tree = true
""")
        conf = Config()
        conf.load(self.test_root)

        book = Book(other_root, config=conf)
        self.assertEqual(book.id, '')
        self.assertEqual(book.name, 'book1')
        self.assertEqual(book.top_dir, os.path.join(self.test_root, 'rootdir', 'sb1'))
        self.assertEqual(book.data_dir, os.path.join(self.test_root, 'rootdir', 'sb1', 'data'))
        self.assertEqual(book.tree_dir, os.path.join(self.test_root, 'rootdir', 'sb1', 'tree'))
        self.assertEqual(book.index, os.path.join(self.test_root, 'rootdir', 'sb1', 'tree', 'map.html'))
        self.assertTrue(book.no_tree)

    def test_init04(self):
        """Use default value if not configured in the book_id"""
        with open(self.test_config, 'w', encoding='UTF-8') as f:
            f.write("""[book "book1"]
""")

        book = Book(self.test_root, book_id='book1')
        self.assertEqual(book.id, 'book1')
        self.assertEqual(book.name, 'scrapbook')
        self.assertEqual(book.top_dir, self.test_root)
        self.assertEqual(book.data_dir, self.test_root)
        self.assertEqual(book.tree_dir, os.path.join(self.test_root, '.wsb', 'tree'))
        self.assertEqual(book.index, os.path.join(self.test_root, '.wsb', 'tree', 'map.html'))
        self.assertFalse(book.no_tree)

    def test_get_tree_file(self):
        self.create_general_config()
        book = Book(self.test_root)
        self.assertEqual(book.get_tree_file('meta'), os.path.join(self.test_root, 'tree', 'meta.js'))
        self.assertEqual(book.get_tree_file('toc', 1), os.path.join(self.test_root, 'tree', 'toc1.js'))

    def test_iter_tree_files01(self):
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'tree'))
        with open(os.path.join(self.test_root, 'tree', 'meta.js'), 'w', encoding='UTF-8') as f:
            pass
        with open(os.path.join(self.test_root, 'tree', 'meta1.js'), 'w', encoding='UTF-8') as f:
            pass
        with open(os.path.join(self.test_root, 'tree', 'meta2.js'), 'w', encoding='UTF-8') as f:
            pass

        book = Book(self.test_root)
        self.assertEqual(list(book.iter_tree_files('meta')), [
            os.path.join(self.test_root, 'tree', 'meta.js'),
            os.path.join(self.test_root, 'tree', 'meta1.js'),
            os.path.join(self.test_root, 'tree', 'meta2.js'),
            ])

    def test_iter_tree_files02(self):
        """Break since nonexisting index"""
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'tree'))
        with open(os.path.join(self.test_root, 'tree', 'meta.js'), 'w', encoding='UTF-8') as f:
            pass
        with open(os.path.join(self.test_root, 'tree', 'meta1.js'), 'w', encoding='UTF-8') as f:
            pass
        with open(os.path.join(self.test_root, 'tree', 'meta3.js'), 'w', encoding='UTF-8') as f:
            pass

        book = Book(self.test_root)
        self.assertEqual(list(book.iter_tree_files('meta')), [
            os.path.join(self.test_root, 'tree', 'meta.js'),
            os.path.join(self.test_root, 'tree', 'meta1.js'),
            ])

    def test_iter_tree_files03(self):
        """Works when directory not exist"""
        book = Book(self.test_root)
        self.assertEqual(list(book.iter_tree_files('meta')), [])

    @mock.patch('webscrapbook.scrapbook.book.Book.iter_tree_files')
    def test_iter_meta_files(self, mock_func):
        book = Book(self.test_root)
        for i in book.iter_meta_files():
            pass
        mock_func.assert_called_once_with('meta')

    @mock.patch('webscrapbook.scrapbook.book.Book.iter_tree_files')
    def test_iter_toc_files(self, mock_func):
        book = Book(self.test_root)
        for i in book.iter_toc_files():
            pass
        mock_func.assert_called_once_with('toc')

    @mock.patch('webscrapbook.scrapbook.book.Book.iter_tree_files')
    def test_iter_fulltext_files(self, mock_func):
        book = Book(self.test_root)
        for i in book.iter_fulltext_files():
            pass
        mock_func.assert_called_once_with('fulltext')

    def test_load_tree_file01(self):
        """Test normal loading"""
        self.create_general_config()
        with open(os.path.join(self.test_root, 'meta.js'), 'w', encoding='UTF-8') as f:
            f.write("""/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.meta({
  "20200101000000000": {
    "index": "20200101000000000/index.html",
    "title": "Dummy",
    "type": "",
    "create": "20200101000000000",
    "modify": "20200101000000000"
  }
})""")

        book = Book(self.test_root)
        self.assertEqual(
            book.load_tree_file(os.path.join(self.test_root, 'meta.js')), {
                '20200101000000000': {
                    'index': '20200101000000000/index.html',
                    'title': 'Dummy',
                    'type': '',
                    'create': '20200101000000000',
                    'modify': '20200101000000000',
                    },
                })

    def test_load_tree_file02(self):
        """Test malformed wrapping"""
        self.create_general_config()
        with open(os.path.join(self.test_root, 'meta.js'), 'w', encoding='UTF-8') as f:
            f.write("""
scrapbook.meta({
  "20200101000000000": {
    "index": "20200101000000000/index.html",
    "title": "Dummy",
    "type": "",
    "create": "20200101000000000",
    "modify": "20200101000000000"
  }
}""")

        book = Book(self.test_root)
        with self.assertRaises(wsb_book.TreeFileMalformedError):
            book.load_tree_file(os.path.join(self.test_root, 'meta.js'))

    def test_load_tree_file03(self):
        """Test malformed wrapping"""
        self.create_general_config()
        with open(os.path.join(self.test_root, 'meta.js'), 'w', encoding='UTF-8') as f:
            f.write("""
scrapbook.meta{
  "20200101000000000": {
    "index": "20200101000000000/index.html",
    "title": "Dummy",
    "type": "",
    "create": "20200101000000000",
    "modify": "20200101000000000"
  }
})""")

        book = Book(self.test_root)
        with self.assertRaises(wsb_book.TreeFileMalformedError):
            book.load_tree_file(os.path.join(self.test_root, 'meta.js'))

    def test_load_tree_file04(self):
        """Test malformed wrapping"""
        self.create_general_config()
        with open(os.path.join(self.test_root, 'meta.js'), 'w', encoding='UTF-8') as f:
            f.write("""({
  "20200101000000000": {
    "index": "20200101000000000/index.html",
    "title": "Dummy",
    "type": "",
    "create": "20200101000000000",
    "modify": "20200101000000000"
  }
})""")

        book = Book(self.test_root)
        with self.assertRaises(wsb_book.TreeFileMalformedError):
            book.load_tree_file(os.path.join(self.test_root, 'meta.js'))

    def test_load_tree_file05(self):
        """Test malformed JSON"""
        self.create_general_config()
        with open(os.path.join(self.test_root, 'meta.js'), 'w', encoding='UTF-8') as f:
            f.write("""
scrapbook.meta({
  '20200101000000000': {
    index: '20200101000000000/index.html',
    title: 'Dummy',
    type: '',
    create: '20200101000000000',
    modify: '20200101000000000'
  }
}""")

        book = Book(self.test_root)
        with self.assertRaises(wsb_book.TreeFileMalformedError):
            book.load_tree_file(os.path.join(self.test_root, 'meta.js'))

    def test_load_tree_files01(self):
        """Test normal loading"""
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'tree'))
        with open(os.path.join(self.test_root, 'tree', 'meta.js'), 'w', encoding='UTF-8') as f:
            f.write("""/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.meta({
  "20200101000000000": {
    "index": "index.html",
    "title": "Dummy",
    "type": "",
    "create": "20200101000000000",
    "modify": "20200101000000000"
  },
  "20200101000000001": {
    "index": "index.html",
    "title": "Dummy2",
    "type": "",
    "create": "20200101000000001",
    "modify": "20200101000000001"
  }
})""")
        with open(os.path.join(self.test_root, 'tree', 'meta1.js'), 'w', encoding='UTF-8') as f:
            f.write("""/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.meta({
  "20200101000000001": {
    "index": "index.html",
    "title": "Dummy2rev",
    "type": "",
    "create": "20200101000000001",
    "modify": "20200101000000011"
  },
  "20200101000000002": {
    "index": "index.html",
    "title": "Dummy3",
    "type": "",
    "create": "20200101000000002",
    "modify": "20200101000000002"
  }
})""")

        book = Book(self.test_root)
        self.assertEqual(book.load_tree_files('meta'), {
            '20200101000000000': {
                'index': 'index.html',
                'title': 'Dummy',
                'type': '',
                'create': '20200101000000000',
                'modify': '20200101000000000',
                },
            '20200101000000001': {
                'index': 'index.html',
                'title': 'Dummy2rev',
                'type': '',
                'create': '20200101000000001',
                'modify': '20200101000000011',
                },
            '20200101000000002': {
                'index': 'index.html',
                'title': 'Dummy3',
                'type': '',
                'create': '20200101000000002',
                'modify': '20200101000000002',
                },
            })

    def test_load_tree_files02(self):
        """Works when directory not exist"""
        book = Book(self.test_root)
        self.assertEqual(book.load_tree_files('meta'), {})

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_meta_files01(self, mock_func):
        book = Book(self.test_root)
        book.load_meta_files()
        mock_func.assert_called_once_with('meta')

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_meta_files02(self, mock_func):
        book = Book(self.test_root)
        book.meta = {}
        book.load_meta_files()
        mock_func.assert_not_called()

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_meta_files03(self, mock_func):
        book = Book(self.test_root)
        book.meta = {}
        book.load_meta_files(refresh=True)
        mock_func.assert_called_once_with('meta')

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_toc_files01(self, mock_func):
        book = Book(self.test_root)
        book.load_toc_files()
        mock_func.assert_called_once_with('toc')

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_toc_files02(self, mock_func):
        book = Book(self.test_root)
        book.toc = {}
        book.load_toc_files()
        mock_func.assert_not_called()

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_toc_files03(self, mock_func):
        book = Book(self.test_root)
        book.toc = {}
        book.load_toc_files(refresh=True)
        mock_func.assert_called_once_with('toc')

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_fulltext_files01(self, mock_func):
        book = Book(self.test_root)
        book.load_fulltext_files()
        mock_func.assert_called_once_with('fulltext')

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_fulltext_files02(self, mock_func):
        book = Book(self.test_root)
        book.fulltext = {}
        book.load_fulltext_files()
        mock_func.assert_not_called()

    @mock.patch('webscrapbook.scrapbook.book.Book.load_tree_files')
    def test_load_fulltext_files03(self, mock_func):
        book = Book(self.test_root)
        book.fulltext = {}
        book.load_fulltext_files(refresh=True)
        mock_func.assert_called_once_with('fulltext')

    def test_save_meta_files01(self):
        self.create_general_config()
        book = Book(self.test_root)
        book.meta = {
            '20200101000000000': {'title': 'Dummy 1 中文'},
            '20200101000000001': {'title': 'Dummy 2 中文'},
            }

        book.save_meta_files()

        with open(os.path.join(self.test_root, 'tree', 'meta.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.meta({
  "20200101000000000": {
    "title": "Dummy 1 中文"
  },
  "20200101000000001": {
    "title": "Dummy 2 中文"
  }
})""")

    @mock.patch('webscrapbook.scrapbook.book.Book.SAVE_META_THRESHOLD', 3)
    def test_save_meta_files02(self):
        self.create_general_config()
        book = Book(self.test_root)
        book.meta = {
            '20200101000000000': {'title': 'Dummy 1 中文'},
            '20200101000000001': {'title': 'Dummy 2 中文'},
            '20200101000000002': {'title': 'Dummy 3 中文'},
            '20200101000000003': {'title': 'Dummy 4 中文'},
            }

        book.save_meta_files()

        with open(os.path.join(self.test_root, 'tree', 'meta.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.meta({
  "20200101000000000": {
    "title": "Dummy 1 中文"
  },
  "20200101000000001": {
    "title": "Dummy 2 中文"
  }
})""")
        with open(os.path.join(self.test_root, 'tree', 'meta1.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.meta({
  "20200101000000002": {
    "title": "Dummy 3 中文"
  },
  "20200101000000003": {
    "title": "Dummy 4 中文"
  }
})""")

    def test_save_meta_files03(self):
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'tree'))
        with open(os.path.join(self.test_root, 'tree', 'meta.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy')
        with open(os.path.join(self.test_root, 'tree', 'meta1.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy1')
        with open(os.path.join(self.test_root, 'tree', 'meta2.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy2')
        with open(os.path.join(self.test_root, 'tree', 'meta3.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy3')

        book = Book(self.test_root)
        book.meta = {
            '20200101000000000': {'title': 'Dummy 1 中文'},
            '20200101000000001': {'title': 'Dummy 2 中文'},
            }

        book.save_meta_files()

        with open(os.path.join(self.test_root, 'tree', 'meta.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.meta({
  "20200101000000000": {
    "title": "Dummy 1 中文"
  },
  "20200101000000001": {
    "title": "Dummy 2 中文"
  }
})""")
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'meta1.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'meta2.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'meta3.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'meta4.js')))

    def test_save_toc_files01(self):
        self.create_general_config()
        book = Book(self.test_root)
        book.toc = {
            'root': [
                '20200101000000000',
                '20200101000000001',
                '20200101000000002',
                ],
            '20200101000000000': [
                '20200101000000003'
                ]
            }

        book.save_toc_files()

        with open(os.path.join(self.test_root, 'tree', 'toc.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.toc({
  "root": [
    "20200101000000000",
    "20200101000000001",
    "20200101000000002"
  ],
  "20200101000000000": [
    "20200101000000003"
  ]
})""")

    @mock.patch('webscrapbook.scrapbook.book.Book.SAVE_TOC_THRESHOLD', 3)
    def test_save_toc_files02(self):
        self.create_general_config()
        book = Book(self.test_root)
        book.toc = {
            'root': [
                '20200101000000000',
                '20200101000000001',
                '20200101000000002',
                '20200101000000003',
                '20200101000000004',
                ],
            '20200101000000001': [
                '20200101000000011'
                ],
            '20200101000000002': [
                '20200101000000021'
                ],
            '20200101000000003': [
                '20200101000000031',
                '20200101000000032'
                ],
            }

        book.save_toc_files()

        with open(os.path.join(self.test_root, 'tree', 'toc.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.toc({
  "root": [
    "20200101000000000",
    "20200101000000001",
    "20200101000000002",
    "20200101000000003",
    "20200101000000004"
  ]
})""")
        with open(os.path.join(self.test_root, 'tree', 'toc1.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.toc({
  "20200101000000001": [
    "20200101000000011"
  ],
  "20200101000000002": [
    "20200101000000021"
  ]
})""")
        with open(os.path.join(self.test_root, 'tree', 'toc2.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.toc({
  "20200101000000003": [
    "20200101000000031",
    "20200101000000032"
  ]
})""")

    def test_save_toc_files03(self):
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'tree'))
        with open(os.path.join(self.test_root, 'tree', 'toc.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy')
        with open(os.path.join(self.test_root, 'tree', 'toc1.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy1')
        with open(os.path.join(self.test_root, 'tree', 'toc2.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy2')
        with open(os.path.join(self.test_root, 'tree', 'toc4.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy4')

        book = Book(self.test_root)
        book.toc = {
            'root': [
                '20200101000000000',
                '20200101000000001',
                '20200101000000002',
                ],
            '20200101000000000': [
                '20200101000000003'
                ]
            }

        book.save_toc_files()

        with open(os.path.join(self.test_root, 'tree', 'toc.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * Feel free to edit this file, but keep data code valid JSON format.
 */
scrapbook.toc({
  "root": [
    "20200101000000000",
    "20200101000000001",
    "20200101000000002"
  ],
  "20200101000000000": [
    "20200101000000003"
  ]
})""")
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'toc1.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'toc2.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'toc3.js')))
        self.assertTrue(os.path.exists(os.path.join(self.test_root, 'tree', 'toc4.js')))

    def test_save_fulltext_files01(self):
        self.create_general_config()
        book = Book(self.test_root)
        book.fulltext = {
            "20200101000000000": {
                'index.html': {
                    'content': 'dummy text 1 中文',
                    }
                },
            "20200101000000001": {
                'index.html': {
                    'content': 'dummy text 2 中文',
                    }
                },
            }

        book.save_fulltext_files()

        with open(os.path.join(self.test_root, 'tree', 'fulltext.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({
 "20200101000000000": {
  "index.html": {
   "content": "dummy text 1 中文"
  }
 },
 "20200101000000001": {
  "index.html": {
   "content": "dummy text 2 中文"
  }
 }
})""")

    @mock.patch('webscrapbook.scrapbook.book.Book.SAVE_FULLTEXT_THRESHOLD', 10)
    def test_save_fulltext_files02(self):
        self.create_general_config()
        book = Book(self.test_root)
        book.fulltext = {
            "20200101000000000": {
                'index.html': {
                    'content': 'dummy text 1 中文',
                    },
                'frame.html': {
                    'content': 'frame page content',
                    },
                },
            "20200101000000001": {
                'index.html': {
                    'content': 'dummy text 2 中文',
                    },
                },
            "20200101000000002": {
                'index.html': {
                    'content': 'dummy text 3 中文',
                    },
                },
            }

        book.save_fulltext_files()

        with open(os.path.join(self.test_root, 'tree', 'fulltext.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({
 "20200101000000000": {
  "index.html": {
   "content": "dummy text 1 中文"
  },
  "frame.html": {
   "content": "frame page content"
  }
 }
})""")
        with open(os.path.join(self.test_root, 'tree', 'fulltext1.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({
 "20200101000000001": {
  "index.html": {
   "content": "dummy text 2 中文"
  }
 }
})""")
        with open(os.path.join(self.test_root, 'tree', 'fulltext2.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({
 "20200101000000002": {
  "index.html": {
   "content": "dummy text 3 中文"
  }
 }
})""")

    @mock.patch('webscrapbook.scrapbook.book.Book.SAVE_FULLTEXT_THRESHOLD', 10)
    def test_save_fulltext_files03(self):
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'tree'))
        with open(os.path.join(self.test_root, 'tree', 'fulltext.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy')
        with open(os.path.join(self.test_root, 'tree', 'fulltext1.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy1')
        with open(os.path.join(self.test_root, 'tree', 'fulltext2.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy2')
        with open(os.path.join(self.test_root, 'tree', 'fulltext3.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy3')
        with open(os.path.join(self.test_root, 'tree', 'fulltext4.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy4')
        with open(os.path.join(self.test_root, 'tree', 'fulltext6.js'), 'w', encoding='UTF-8') as fh:
            fh.write('dummy6')

        book = Book(self.test_root)
        book.fulltext = {
            "20200101000000000": {
                'index.html': {
                    'content': 'dummy text 1 中文',
                    },
                'frame.html': {
                    'content': 'frame page content',
                    },
                },
            "20200101000000001": {
                'index.html': {
                    'content': 'dummy text 2 中文',
                    },
                },
            }

        book.save_fulltext_files()

        with open(os.path.join(self.test_root, 'tree', 'fulltext.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({
 "20200101000000000": {
  "index.html": {
   "content": "dummy text 1 中文"
  },
  "frame.html": {
   "content": "frame page content"
  }
 }
})""")
        with open(os.path.join(self.test_root, 'tree', 'fulltext1.js'), encoding='UTF-8') as fh:
            self.assertEqual(fh.read(), """/**
 * This file is generated by WebScrapBook and is not intended to be edited.
 */
scrapbook.fulltext({
 "20200101000000001": {
  "index.html": {
   "content": "dummy text 2 中文"
  }
 }
})""")
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'fulltext2.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'fulltext3.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'fulltext4.js')))
        self.assertFalse(os.path.exists(os.path.join(self.test_root, 'tree', 'fulltext5.js')))
        self.assertTrue(os.path.exists(os.path.join(self.test_root, 'tree', 'fulltext6.js')))

    def test_mime_is_html(self):
        book = Book(self.test_root)
        self.assertTrue(book.mime_is_html('text/html'))
        self.assertTrue(book.mime_is_html('application/xhtml+xml'))
        self.assertFalse(book.mime_is_html('application/html+zip'))
        self.assertFalse(book.mime_is_html('application/x-maff'))
        self.assertFalse(book.mime_is_html('text/plain'))
        self.assertFalse(book.mime_is_html('text/xml'))
        self.assertFalse(book.mime_is_html('image/svg+xml'))
        self.assertFalse(book.mime_is_html('application/octet-stream'))

    def test_mime_is_archive(self):
        book = Book(self.test_root)
        self.assertFalse(book.mime_is_archive('text/html'))
        self.assertFalse(book.mime_is_archive('application/xhtml+xml'))
        self.assertTrue(book.mime_is_archive('application/html+zip'))
        self.assertTrue(book.mime_is_archive('application/x-maff'))
        self.assertFalse(book.mime_is_archive('text/plain'))
        self.assertFalse(book.mime_is_archive('text/xml'))
        self.assertFalse(book.mime_is_archive('image/svg+xml'))
        self.assertFalse(book.mime_is_archive('application/octet-stream'))

    def test_mime_is_htz(self):
        book = Book(self.test_root)
        self.assertFalse(book.mime_is_htz('text/html'))
        self.assertFalse(book.mime_is_htz('application/xhtml+xml'))
        self.assertTrue(book.mime_is_htz('application/html+zip'))
        self.assertFalse(book.mime_is_htz('application/x-maff'))
        self.assertFalse(book.mime_is_htz('text/plain'))
        self.assertFalse(book.mime_is_htz('text/xml'))
        self.assertFalse(book.mime_is_htz('image/svg+xml'))
        self.assertFalse(book.mime_is_htz('application/octet-stream'))

    def test_mime_is_maff(self):
        book = Book(self.test_root)
        self.assertFalse(book.mime_is_maff('text/html'))
        self.assertFalse(book.mime_is_maff('application/xhtml+xml'))
        self.assertFalse(book.mime_is_maff('application/html+zip'))
        self.assertTrue(book.mime_is_maff('application/x-maff'))
        self.assertFalse(book.mime_is_maff('text/plain'))
        self.assertFalse(book.mime_is_maff('text/xml'))
        self.assertFalse(book.mime_is_maff('image/svg+xml'))
        self.assertFalse(book.mime_is_maff('application/octet-stream'))

    def test_is_html(self):
        book = Book(self.test_root)
        self.assertTrue(book.is_html('index.html'))
        self.assertTrue(book.is_html('index.xhtml'))
        self.assertFalse(book.is_html('20200101000000000.htz'))
        self.assertFalse(book.is_html('20200101000000000.maff'))
        self.assertFalse(book.is_html('20200101000000000/index.md'))
        self.assertFalse(book.is_html('20200101000000000/test.txt'))
        self.assertFalse(book.is_html('20200101000000000/test.xml'))
        self.assertFalse(book.is_html('20200101000000000/test.svg'))
        self.assertFalse(book.is_html('20200101000000000/whatever'))

    def test_is_archive(self):
        book = Book(self.test_root)
        self.assertFalse(book.is_archive('index.html'))
        self.assertFalse(book.is_archive('index.xhtml'))
        self.assertTrue(book.is_archive('20200101000000000.htz'))
        self.assertTrue(book.is_archive('20200101000000000.maff'))
        self.assertFalse(book.is_archive('20200101000000000/index.md'))
        self.assertFalse(book.is_archive('20200101000000000/test.txt'))
        self.assertFalse(book.is_archive('20200101000000000/test.xml'))
        self.assertFalse(book.is_archive('20200101000000000/test.svg'))
        self.assertFalse(book.is_archive('20200101000000000/whatever'))

    def test_is_htz(self):
        book = Book(self.test_root)
        self.assertFalse(book.is_htz('index.html'))
        self.assertFalse(book.is_htz('index.xhtml'))
        self.assertTrue(book.is_htz('20200101000000000.htz'))
        self.assertFalse(book.is_htz('20200101000000000.maff'))
        self.assertFalse(book.is_htz('20200101000000000/index.md'))
        self.assertFalse(book.is_htz('20200101000000000/test.txt'))
        self.assertFalse(book.is_htz('20200101000000000/test.xml'))
        self.assertFalse(book.is_htz('20200101000000000/test.svg'))
        self.assertFalse(book.is_htz('20200101000000000/whatever'))

    def test_is_maff(self):
        book = Book(self.test_root)
        self.assertFalse(book.is_maff('index.html'))
        self.assertFalse(book.is_maff('index.xhtml'))
        self.assertFalse(book.is_maff('20200101000000000.htz'))
        self.assertTrue(book.is_maff('20200101000000000.maff'))
        self.assertFalse(book.is_maff('20200101000000000/index.md'))
        self.assertFalse(book.is_maff('20200101000000000/test.txt'))
        self.assertFalse(book.is_maff('20200101000000000/test.xml'))
        self.assertFalse(book.is_maff('20200101000000000/test.svg'))
        self.assertFalse(book.is_maff('20200101000000000/whatever'))

    def test_get_index_paths01(self):
        self.create_general_config()
        book = Book(self.test_root)
        self.assertEqual(book.get_index_paths('20200101000000000/index.html'), ['index.html'])
        self.assertEqual(book.get_index_paths('20200101000000000.html'), ['20200101000000000.html'])
        self.assertEqual(book.get_index_paths('20200101000000000.htz'), ['index.html'])

    def test_get_index_paths02(self):
        """MAFF with single page"""
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'data'))
        archive_file = os.path.join(self.test_root, 'data', '20200101000000000.maff')
        with zipfile.ZipFile(archive_file, 'w') as zh:
            zh.writestr('20200101000000000/index.html', """dummy""")
        book = Book(self.test_root)

        self.assertEqual(book.get_index_paths('20200101000000000.maff'), ['20200101000000000/index.html'])

    def test_get_index_paths03(self):
        """MAFF with multiple pages"""
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'data'))
        archive_file = os.path.join(self.test_root, 'data', '20200101000000000.maff')
        with zipfile.ZipFile(archive_file, 'w') as zh:
            zh.writestr('20200101000000000/index.html', """dummy""")
            zh.writestr('20200101000000001/index.html', """dummy""")
        book = Book(self.test_root)

        self.assertEqual(book.get_index_paths('20200101000000000.maff'), ['20200101000000000/index.html', '20200101000000001/index.html'])

    def test_get_index_paths04(self):
        """MAFF with no page"""
        self.create_general_config()
        os.makedirs(os.path.join(self.test_root, 'data'))
        archive_file = os.path.join(self.test_root, 'data', '20200101000000000.maff')
        with zipfile.ZipFile(archive_file, 'w') as zh:
            pass
        book = Book(self.test_root)

        self.assertEqual(book.get_index_paths('20200101000000000.maff'), [])


if __name__ == '__main__':
    unittest.main()
