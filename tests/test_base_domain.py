# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2006 Async Open Source <http://www.async.com.br>
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
## GNU General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s):   Johan Dahlin      <jdahlin@async.com.br>
##

from sqlobject import SQLObjectMoreThanOneResultError
from sqlobject.col import IntCol
from zope.interface import implements, Interface

from stoqlib.database.runtime import new_transaction
from stoqlib.domain.base import Domain, ModelAdapter

from tests.base import DomainTest

class IDong(Interface):
    pass

class Ding(Domain):
    field = IntCol(default=0)
    def __init__(self, connection, field=None):
        Domain.__init__(self, connection=connection, field=field)
        self.called = False

    def facet_IDong_add(self, **kwargs):
        self.called = True
        adapter_klass = self.getAdapterClass(IDong)
        return adapter_klass(self, **kwargs)

class DingAdaptToDong(ModelAdapter):
    implements(IDong)

Ding.registerFacet(DingAdaptToDong, IDong)

trans = new_transaction()
Ding.createTable(ifNotExists=True, connection=trans)
DingAdaptToDong.createTable(ifNotExists=True, connection=trans)
trans.commit()

class FacetTests(DomainTest):
    def testAdd(self):
        ding = Ding(connection=self.trans)
        self.assertEqual(IDong(ding, None), None)

        dong = ding.addFacet(IDong, connection=self.trans)
        self.assertEqual(IDong(ding), dong)

    def testAddHook(self):
        ding = Ding(connection=self.trans)
        self.assertEqual(ding.called, False)
        dong = ding.addFacet(IDong, connection=self.trans)
        self.assertEqual(ding.called, True)

    def testGetFacets(self):
        ding = Ding(connection=self.trans)
        self.assertEqual(ding.getFacets(), [])

        facet = ding.addFacet(IDong, connection=self.trans)
        self.assertEqual(ding.getFacets(), [facet])

    def testRegisterAndGetTypes(self):
        class IDang(Interface):
            pass

        class DingAdaptToDang(ModelAdapter):
            implements(IDang)

        self.assertEqual(Ding.getFacetTypes(), [DingAdaptToDong])

        Ding.registerFacet(DingAdaptToDang, IDang)

        self.failUnless(len(Ding.getFacetTypes()), 2)
        self.failUnless(DingAdaptToDang in Ding.getFacetTypes())

class TestSelect(DomainTest):
    def testSelectOne(self):
        self.assertEquals(Ding.selectOne(connection=self.trans), None)
        ding1 = Ding(connection=self.trans)
        self.assertEquals(Ding.selectOne(connection=self.trans), ding1)
        ding2 = Ding(connection=self.trans)
        self.assertRaises(SQLObjectMoreThanOneResultError,
                          Ding.selectOne, connection=self.trans)

    def testSelectOneWithInvalid(self):
        obj = Ding(connection=self.trans)
        obj._is_valid_model = False
        self.testSelectOne()

    def testSelectOneBy(self):
        Ding(connection=self.trans)

        self.assertEquals(
            None, Ding.selectOneBy(field=1, connection=self.trans))
        ding1 = Ding(connection=self.trans, field=1)
        self.assertEquals(
            ding1, Ding.selectOneBy(field=1, connection=self.trans))
        ding2 = Ding(connection=self.trans, field=1)
        self.assertRaises(
            SQLObjectMoreThanOneResultError,
            Ding.selectOneBy, field=1, connection=self.trans)

    def testSelectOneByWithInvalid(self):
        obj = Ding(connection=self.trans, field=1)
        obj._is_valid_model = False
        self.testSelectOneBy()

    def testISelect(self):
        self.assertEqual(Ding.iselect(IDong, connection=self.trans).count(), 0)
        ding = Ding(connection=self.trans)
        ding.addFacet(IDong, connection=self.trans)
        self.assertEqual(Ding.iselect(IDong, connection=self.trans).count(), 1)

    def testISelectWithInvalid(self):
        ding = Ding(connection=self.trans)
        dong = ding.addFacet(IDong, connection=self.trans)
        dong._is_valid_model = False
        self.testISelect()

    def testISelectOne(self):
        self.assertEqual(Ding.iselectOne(IDong, connection=self.trans), None)
        ding = Ding(connection=self.trans)
        dong = ding.addFacet(IDong, connection=self.trans)

        self.assertEqual(Ding.iselectOne(IDong, connection=self.trans), dong)

        ding2 = Ding(connection=self.trans)
        ding2.addFacet(IDong, connection=self.trans)

        self.assertRaises(
            SQLObjectMoreThanOneResultError,
            Ding.iselectOne, IDong, connection=self.trans)

    def testISelectOneWithInvalid(self):
        ding = Ding(connection=self.trans)
        dong = ding.addFacet(IDong, connection=self.trans)
        dong._is_valid_model = False
        self.testISelectOne()
