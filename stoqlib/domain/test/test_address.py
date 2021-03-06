# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2006 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##

from stoqlib.domain.address import Address, CityLocation
from stoqlib.lib.parameters import sysparam

from stoqlib.domain.test.domaintest import DomainTest


class TestCityLocation(DomainTest):
    """Tests for CityLocation class"""

    def testIsValidModel(self):
        location = self.create_city_location()
        self.failUnless(location.is_valid_model())
        invalid_location = CityLocation(store=self.store)
        self.failIf(invalid_location.is_valid_model())

    def testGetOrCreate(self):
        loc = CityLocation.get_or_create(self.store, u'City',
                                         u'State', u'Country')
        self.failUnless(loc)
        self.assertEqual(loc.city, u'City')
        self.assertEqual(loc.state, u'State')
        self.assertEqual(loc.country, u'Country')

        loc2 = CityLocation.get_or_create(self.store, u'city',
                                          u'state', u'country')
        self.failUnless(loc2)
        self.assertEqual(loc2.city, u'City')
        self.assertEqual(loc2.state, u'State')
        self.assertEqual(loc2.country, u'Country')
        self.assertEqual(loc2, loc)

        location = CityLocation.get_or_create(self.store, u'São Carlos',
                                              u'SP', u'Brazil')
        for city, state, country in [
            (u'sao carlos', u'SP', u'Brazil'),
            (u'Sao carlos', u'SP', u'Brazil'),
            (u'São carlos', u'SP', u'Brazil'),
            (u'sao Carlos', u'SP', u'Brazil'),
            (u'sao Carlos', u'sp', u'Brazil'),
            (u'sao Carlos', u'sp', u'brazil'),
            (u'sao Carlos', u'Sp', u'brazil'),
            ]:
            self.assertEqual(CityLocation.get_or_create(self.store, city,
                                                        state, country),
                             location)
        for city, state, country in [
            (u'Sao', u'SP', u'Brazil'),
            (u'sao', u'SP', u'Brazil'),
            (u'Carlos', u'SP', u'Brazil'),
            (u'carlos', u'SP', u'Brazil'),
            ]:
            self.assertNotEqual(CityLocation.get_or_create(self.store, city,
                                                           state, country),
                                location)

    def testGetCitiesBy(self):
        location = CityLocation.get_or_create(self.store, u'Sao Carlos',
                                              u'SP', u'Brazil')
        for state, country in [
            (u'SP', u'Brazil'),
            (u'Sp', u'brazil'),
            (u'SP', u'brazil'),
            (u'sp', u'Brazil'),
            (u'sp', u'BraZIL'),
            (None, u'Brazil'),
            (u'SP', None),
            (None, None),
            ]:
            self.assertTrue(location.city in
                            CityLocation.get_cities_by(self.store,
                                                       state=state,
                                                       country=country))
        for state, country in [
            (u'SP', u'Brazi'),
            (u'RJ', u'Brazil'),
            (u'RJ', None),
            (u'BA', None),
            (u'SP', u'Albânia'),
            ]:
            self.assertFalse(location.city in
                             CityLocation.get_cities_by(self.store,
                                                        state=state,
                                                        country=country))

        # Make sure no duplicates are returned
        CityLocation.get_or_create(self.store, u'Sao Carlos', u'SP', u'BR')
        CityLocation.get_or_create(self.store, u'Sao Carlos', u'SP', u'BR_')
        CityLocation.get_or_create(self.store, u'Sao Carlos', u'SP', u'BR__')
        cities = list(CityLocation.get_cities_by(self.store, state=u'SP'))
        self.assertEqual(len(cities), len(set(cities)))

    def testGetDefault(self):
        location = CityLocation.get_default(self.store)
        self.failUnless(isinstance(location, CityLocation))
        self.assertEquals(location.city,
                          sysparam(self.store).CITY_SUGGESTED)
        self.assertEquals(location.state,
                          sysparam(self.store).STATE_SUGGESTED)
        self.assertEquals(location.country,
                          sysparam(self.store).COUNTRY_SUGGESTED)


class TestAddress(DomainTest):
    def testIsValidModel(self):
        person = self.create_person()
        empty_location = CityLocation(store=self.store)
        empty_address = Address(store=self.store,
                                person=person,
                                city_location=empty_location)
        is_valid_model = empty_address.is_valid_model()
        assert bool(is_valid_model) is False

    def test_get_city_location_attributes(self):
        person = self.create_person()
        city = u'Acapulco'
        country = u'Brazil'
        state = u'Cracovia'
        location = CityLocation(city=city, state=state, country=country,
                                store=self.store)
        address = Address(person=person, city_location=location,
                          store=self.store)
        self.assertEquals(address.get_city(), u'Acapulco')
        self.assertEquals(address.get_country(), u'Brazil')
        self.assertEquals(address.get_state(), u'Cracovia')

    def test_get_address_string(self):
        person = self.create_person()
        location = self.create_city_location()

        street = u'Rua das Couves'
        streetnumber = 283
        district = u'Federal'
        address = Address(person=person, city_location=location,
                          street=street, streetnumber=streetnumber,
                          district=district,
                          store=self.store)
        string = address.get_address_string()
        self.assertEquals(string, u'%s %s, %s' % (street, streetnumber,
                                                  district))

        address.streetnumber = None
        string = address.get_address_string()
        self.assertEquals(string, u'%s %s, %s' % (street, u'N/A', district))

        address.street = u""
        string = address.get_address_string()
        self.assertEquals(string, u'')

    def testGetPostalNumber(self):
        person = self.create_person()
        location = self.create_city_location()
        address = Address(person=person, city_location=location,
                          postal_code=u'12345-678', store=self.store)

        self.assertEquals(address.get_postal_code_number(), 12345678)

    def testGetDetailsString(self):
        person = self.create_person()
        city = u'Stoqlandia'
        state = u'SP'
        country = u'Brazil'
        postal_code = u'12345-678'
        location = CityLocation(city=city, state=state, country=country,
                                store=self.store)
        address = Address(person=person, city_location=location,
                          postal_code=postal_code, store=self.store)
        string = address.get_details_string()
        self.assertEquals(string, u'%s - %s - %s' % (postal_code,
                                                     city, state))
        location.city = u''
        string = address.get_details_string()
        self.assertEquals(string, u'%s' % postal_code)
        location.state = u''
        string = address.get_details_string()
        self.assertEquals(string, u'%s' % postal_code)
        address.postal_code = u''
        string = address.get_details_string()
        self.assertEquals(string, u'')
        location.city = city
        location.state = state
        string = address.get_details_string()
        self.assertEquals(string, u'%s - %s' % (city, state))
