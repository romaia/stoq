# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005-2011 Async Open Source
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU Lesser General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##

#
# Dependency checking
#


PSYCOPG_REQUIRED = [2, 0, 5]
KIWI_REQUIRED = (1, 9, 26)
STOQDRIVERS_REQUIRED = (0, 9, 8)

def psycopg_check(mod):
    version = mod.__version__.split(' ', 1)[0]
    return map(int, version.split('.'))

dependencies = [('ZopeInterface', 'zope.interface', '3.0',
                 'http://www.zope.org/Products/ZopeInterface',
                 None),
                ('kiwi', 'kiwi', KIWI_REQUIRED,
                 'http://www.async.com.br/projects/kiwi/',
                 lambda x: x.kiwi_version),
                ('Gazpacho', 'gazpacho', '0.6.6',
                 'http://gazpacho.sicem.biz',
                 lambda x: x.__version__),
                ('Psycopg', 'psycopg2', PSYCOPG_REQUIRED,
                 'http://www.initd.org/projects/psycopg2',
                 psycopg_check),
                ('Stoqdrivers', 'stoqdrivers', STOQDRIVERS_REQUIRED,
                 'http://www.stoq.com.br',
                 lambda x: x.__version__),
                ('Python Imaging Library (PIL)', 'PIL', '1.1.5',
                 'http://www.pythonware.com/products/pil/', None),
                ('Reportlab', 'reportlab', '1.20',
                 'http://www.reportlab.org/', lambda x: x.Version)]

for (package_name, module_name, required_version, url,
     get_version) in dependencies:
    try:
        module = __import__(module_name, {}, {}, [])
    except ImportError:
        raise SystemExit("The '%s' module could not be found\n"
                         "Please install %s which can be found at %s"
                         % (module_name, package_name, url))

    if not get_version:
        continue

    installed_version = get_version(module)
    if isinstance(installed_version, bool):
        if not installed_version:
            raise SystemExit(
                "The '%s' module was found but it is too new for stoqlib.\n "
                "requirements. Please install at least version %s of %s. "
                "Visit %s." % (
                module_name, required_version, package_name, url))

    elif required_version > installed_version:
        raise SystemExit(
            "The '%s' module was found but it was not recent enough.\n"
            "Please install at least version %s of %s. Visit %s."
            % (module_name, required_version, package_name, url))


#
# Package installation
#

from kiwi.dist import setup, listfiles, listpackages

from stoq import version
from stoqlib import website

def listexternal():
    dirs = []
    for package in listpackages('external'):
        # strip external
        dirs.append(package.replace('.', '/'))
    files = []
    for directory in dirs:
        files.append(('lib/stoqlib/' + directory[9:],
                      listfiles(directory, '*.py')))
    return files

def listplugins():
    dirs = []
    for package in listpackages('plugins'):
        # strip plugins
        dirs.append(package.replace('.', '/'))
    files = []
    for directory in dirs:
        install_dir = 'lib/stoqlib/%s' % directory
        files.append((install_dir, listfiles(directory, '*.py')))
        files.append((install_dir, listfiles(directory, '*.plugin')))
    return files

packages = listpackages('stoq')
packages.extend(listpackages('stoqlib', exclude='stoqlib.tests'))

scripts = [
    'bin/stoq',
    'bin/stoqdbadmin',
    'bin/stoqruncmd',
    ]
data_files = [
    ('$datadir/csv', listfiles('data', 'csv', '*.csv')),
    ('$datadir/glade', listfiles('data', 'glade', '*.glade')),
    ('$datadir/glade', listfiles('data', 'glade', '*.ui')),
    ('$datadir/fonts', listfiles('data', 'fonts', '*.ttf')),
    ('$datadir/misc', listfiles('data/misc', '*.*')),
    ('$datadir/pixmaps', listfiles('data', 'pixmaps', '*.png')),
    ('$datadir/sql', listfiles('data', 'sql', '*.sql')),
    ('$datadir/sql', listfiles('data', 'sql', '*.py')),
    ('$datadir/template', listfiles('data', 'template', '*.rml')),
    ('$sysconfdir/stoq',  ''),
    ('share/doc/stoq',
     ('AUTHORS', 'CONTRIBUTORS', 'COPYING', 'COPYING.stoqlib', 'README'))]
data_files += listexternal()
templates = [
    ('share/applications', ['stoq.desktop'])]

# Pyboleto bank logos
data_files += [
    ('lib/stoqlib/pyboleto/media',
     listfiles('external', 'pyboleto', 'media', '*.jpg')),
    ('lib/stoqlib/pyboleto/media',
     listfiles('external', 'pyboleto', 'media', '*.gif')),
    ]

resources = dict(
    locale='$prefix/share/locale',
    plugin='$prefix/lib/stoqlib/plugins',
    )
global_resources = dict(
    config='$sysconfdir/stoq',
    csv='$datadir/csv',
    docs='$prefix/share/doc/stoq',
    fonts='$datadir/fonts',
    glade='$datadir/glade',
    misc='$datadir/misc',
    pixmaps='$datadir/pixmaps',
    sql='$datadir/sql',
    template='$datadir/template',
    )

# ECFPlugin
data_files += listplugins()
data_files += [
    ('$prefix/lib/stoqlib/plugins/ecf/glade',
     listfiles('plugins', 'ecf', 'glade', '*.glade')),
    ('$prefix/lib/stoqlib/plugins/ecf/sql',
     listfiles('plugins', 'ecf', 'sql', '*.sql')),
    ]

# NFePlugin
data_files += [
    ('$prefix/lib/stoqlib/plugins/nfe/csv',
     listfiles('plugins', 'nfe', 'csv', '*.csv')),
    ('$prefix/lib/stoqlib/plugins/nfe/sql',
     listfiles('plugins', 'nfe', 'sql', '*.sql')),
    ('$prefix/lib/stoqlib/plugins/nfe/sql',
     listfiles('plugins', 'nfe', 'sql', '*.py')),
    ]

# Books Plugin
data_files += [
    ('$prefix/lib/stoqlib/plugins/books/glade',
     listfiles('plugins', 'books', 'glade', '*.glade')),
    ('$prefix/lib/stoqlib/plugins/books/sql',
     listfiles('plugins', 'books', 'sql', '*.sql')),
    ('$prefix/lib/stoqlib/plugins/books/sql',
     listfiles('plugins', 'books', 'sql', '*.py')),
    ]

setup(name='stoq',
      version=version,
      author="Async Open Source",
      author_email="stoq-devel@async.com.br",
      description="A powerful retail system",
      long_description="""
      Stoq is an advanced retails system which has as main goals the
      usability, good devices support, and useful features for retails.
      """,
      url=website,
      license="GNU LGPL 2.1 (see COPYING)",
      packages=packages,
      data_files=data_files,
      scripts=scripts,
      resources=resources,
      global_resources=global_resources,
      templates=templates,
      )
