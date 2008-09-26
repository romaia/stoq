# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2008 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
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
## Author(s):  George Kussumoto          <george@async.com.br>
##
"""CSV Exporter Dialog"""


import gtk

from kiwi.python import Settable
from kiwi.ui.objectlist import ObjectList

from stoqlib.database.orm import ORMObject, SelectResults, export_csv, Viewable
from stoqlib.gui.editors.baseeditor import BaseEditor
from stoqlib.gui.csvexporter import objectlist2csv
from stoqlib.lib.translation import stoqlib_gettext

_ = stoqlib_gettext


class CSVExporterDialog(BaseEditor):
    gladefile = 'CSVExporterDialog'
    title = _(u'CSV Exporter Dialog')
    size = (400, 150)
    model_type = Settable

    def __init__(self, conn, klass, results=None):
        """A dialog to export data in CSV format.

        @param conn: a database connection
        @param klass:
        @param results:
        """
        if not results or isinstance(results, SelectResults):
            if not issubclass(klass, (ORMObject, Viewable)):
                raise TypeError("The klass argument should be a ORMObject or "
                                "Viewable class or subclass, got '%s' instead" %
                                klass.__class__.__name__)

        model = Settable(klass=klass, results=results)
        self.conn = conn
        BaseEditor.__init__(self, conn, model=model)
        self._setup_widgets()

    #
    # BaseEditor
    #

    def validate_confirm(self):
        filename = self._run_filechooser()
        if filename:
            self._save(filename)
            return True
        return False

    #
    # Private
    #

    def _setup_widgets(self):
        self.main_dialog.ok_button.set_label('gtk-save-as')

        # (encoding name, python encoding codec)
        # see http://docs.python.org/lib/standard-encodings.html
        encodings = [('Unicode', 'utf8'),
                     ('ASCII', 'ascii'),
                     ('Latin-1', 'latin1')]
        self.encoding.prefill(encodings)

    def _run_filechooser(self):
        chooser = gtk.FileChooserDialog(_(u"Export CSV..."), None,
                                        gtk.FILE_CHOOSER_ACTION_SAVE,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        chooser.set_do_overwrite_confirmation(True)

        csv_filter = gtk.FileFilter()
        csv_filter.set_name(_(u'CSV Files'))
        csv_filter.add_pattern('*.csv')
        chooser.add_filter(csv_filter)

        response = chooser.run()

        filename = None
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()
            if not filename.endswith('.csv'):
                filename += '.csv'

        chooser.destroy()
        return filename

    def _get_csv_content(self, encoding):
        if isinstance(self.model.results, ObjectList):
            return objectlist2csv(self.model.results, encoding)

        if self.model.klass and self.model.results is None:
            results = self.model.klass.select(connection=self.conn)
        else:
            results = self.model.results

        content = export_csv(self.model.klass, select=results,
                             connection=self.conn)
        return content.encode(encoding, 'replace')

    def _save(self, filename):
        encoding = self.encoding.get_selected()
        writer = open(filename, 'w')
        writer.write(self._get_csv_content(encoding))
        writer.close()
