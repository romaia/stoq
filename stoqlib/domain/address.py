# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005,2006 Async Open Source <http://www.async.com.br>
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
##  Author(s): Stoq Team <stoq-devel@async.com.br>
##

from kiwi.argcheck import argcheck
from kiwi.python import strip_accents
from zope.interface import implements

from stoqlib.database.orm import (ORMObject, AND, UnicodeCol, IntCol,
                                  BoolCol, ForeignKey, func)
from stoqlib.database.runtime import StoqlibTransaction
from stoqlib.domain.base import Domain
from stoqlib.domain.interfaces import IDescribable
from stoqlib.l10n.l10n import get_l10n_field
from stoqlib.lib.parameters import sysparam
from stoqlib.lib.translation import stoqlib_gettext

_ = stoqlib_gettext

# strip_accents return str, they should return the same type as the original
# value
_get_equal_clause = lambda table, value: (
    func.stoq_normalize_string(table) ==
    unicode(strip_accents(value.lower())))


class CityLocation(ORMObject):
    """Base class to store the locations. Used to store a person's address
    or birth location.
    """

    country = UnicodeCol(default=u"")
    city = UnicodeCol(default=u"")
    state = UnicodeCol(default=u"")
    city_code = IntCol(default=None)
    state_code = IntCol(default=None)

    #
    #  Classmethods
    #

    @classmethod
    @argcheck(StoqlibTransaction)
    def get_default(cls, trans):
        """Get a city location representing the default settings
        :returns: a :class:`city location <CityLocation>`
        """
        city = sysparam(trans).CITY_SUGGESTED
        state = sysparam(trans).STATE_SUGGESTED
        country = sysparam(trans).COUNTRY_SUGGESTED

        return cls.get_or_create(trans, city, state, country)

    @classmethod
    @argcheck(StoqlibTransaction, basestring, basestring, basestring)
    def get_or_create(cls, trans, city, state, country):
        """
        Returns a CityLocation. If it does not exist, create a new
        one and return it.

        :param trans: a database transaction
        :param city: city
        :param state: state
        :param country: country
        :returns: a :class:`CityLocation` or None
        """
        location = cls.selectOne(
            AND(_get_equal_clause(cls.q.city, city),
                _get_equal_clause(cls.q.state, state),
                _get_equal_clause(cls.q.country, country)),
            connection=trans)

        if location:
            return location

        return cls(city=city,
                   state=state,
                   country=country,
                   connection=trans)

    @classmethod
    def get_cities_by(cls, conn, state=None, country=None):
        """Fetch a list of cities given a state and a country.

        :param conn: a database connection
        :param state: state or None
        :param country: country or None
        :returns: a list of cities
        :rtype: string
        """
        clause = None

        if state:
            clause_ = _get_equal_clause(cls.q.state, state)
            clause = AND(clause, clause_) if clause else clause_
        if country:
            clause_ = _get_equal_clause(cls.q.country, country)
            clause = AND(clause, clause_) if clause else clause_

        return [result.city for result in
                cls.select(clause, connection=conn)]

    @classmethod
    def exists(cls, conn, city, state, country):
        return bool(cls.selectOne(
            AND(_get_equal_clause(cls.q.city, city),
                _get_equal_clause(cls.q.state, state),
                _get_equal_clause(cls.q.country, country)),
            connection=conn))

    #
    #  Public API
    #

    def is_valid_model(self):
        city_l10n = get_l10n_field(self.get_connection(), 'city', self.country)
        return bool(self.country and self.city and self.state and
                    city_l10n.validate(self.city,
                                       state=self.state, country=self.country))


class Address(Domain):
    """Class to store person's addresses.

    """

    implements(IDescribable)

    #: street of the address, something like ``"Wall street"``
    street = UnicodeCol(default='')

    #: streetnumber, eg ``100``
    streetnumber = IntCol(default=None)

    #: district, eg ``"Manhattan"``
    district = UnicodeCol(default='')

    #: postal code, eg ``"12345-678"``
    postal_code = UnicodeCol(default='')

    #: complement, eg ``"apartment 35"``
    complement = UnicodeCol(default='')

    #: defines if this object stores information for the main address
    is_main_address = BoolCol(default=False)

    #: :class:`person <stoqlib.domain.person.Person>` of this address
    person = ForeignKey('Person')

    #: :class:`city location <CityLocation>` of this address
    city_location = ForeignKey('CityLocation')

    #
    # IDescribable
    #

    def get_description(self):
        return self.get_address_string()

    # Public API

    def is_valid_model(self):
        return (self.street and self.district and
                self.city_location.is_valid_model())

    def get_city(self):
        """:returns: the city of this address"""
        return self.city_location.city

    def get_country(self):
        """:returns: the country of this address"""
        return self.city_location.country

    def get_state(self):
        """:returns: the state of this address"""
        return self.city_location.state

    def get_postal_code_number(self):
        """Returns the postal code without any non-numeric characters

        :returns: the postal code as a number
        """
        if not self.postal_code:
            return 0
        return int(''.join([c for c in self.postal_code
                                  if c in '1234567890']))

    def get_address_string(self):
        """Formats the address as a string

        :returns: the formatted address
        """
        if self.street and self.streetnumber and self.district:
            return u'%s %s, %s' % (self.street, self.streetnumber,
                                   self.district)
        elif self.street and self.district:
            return u'%s %s, %s' % (self.street, _(u'N/A'), self.district)
        elif self.street and self.streetnumber:
            return u'%s %s' % (self.street, self.streetnumber)
        elif self.street:
            return self.street

        return u''

    def get_details_string(self):
        """ Returns a string like ``postal_code - city - state``.
        If city or state are missing, return only postal_code; and
        if postal_code is missing, return ``city - state``, otherwise,
        return an empty string

        :returns: the detailed string
        """
        details = []
        if self.postal_code:
            details.append(self.postal_code)
        if self.city_location.city and self.city_location.state:
            details.extend([self.city_location.city,
                            self.city_location.state])
        details = u" - ".join(details)
        return details
