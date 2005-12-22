# -*- Mode: Python; coding: iso-8859-1 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005 Async Open Source <http://www.async.com.br>
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
## Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
## USA.
##
## Author(s):   Evandro Vale Miquelito      <evandro@async.com.br>
##              Henrique Romano             <henrique@async.com.br>
##              Ariqueli Tejada Fonseca     <aritf@async.com.br>
##
"""
stoq/gui/pos/pos.py:

    Main interface definition for pos application.
"""

import gettext

from kiwi.datatypes import currency
from kiwi.ui.widgets.list import Column, SummaryLabel
from stoqlib.exceptions import DatabaseInconsistency
from stoqlib.database import rollback_and_begin
from stoqlib.gui.dialogs import notify_dialog
from stoqlib.gui.search import get_max_search_results

from stoq.gui.application import AppWindow
from stoq.lib.runtime import new_transaction, get_current_user
from stoq.lib.validators import (format_quantity, get_price_format_str)
from stoq.lib.parameters import sysparam
from stoq.domain.sellable import AbstractSellable, FancySellable
from stoq.domain.sale import Sale
from stoq.domain.service import ServiceSellableItem
from stoq.domain.product import ProductSellableItem, FancyProduct
from stoq.domain.person import Person
from stoq.domain.till import get_current_till_operation
from stoq.domain.interfaces import ISellable, ISalesPerson, IClient
from stoq.gui.editors.person import ClientEditor
from stoq.gui.editors.delivery import DeliveryEditor
from stoq.gui.editors.service import ServiceItemEditor
from stoq.gui.wizards.sale import SaleWizard
from stoq.gui.wizards.person import run_person_role_dialog
from stoq.gui.search.sellable import SellableSearch
from stoq.gui.search.person import ClientSearch

_ = gettext.gettext


class POSApp(AppWindow):
   
    app_name = _('Point of Sales')
    gladefile = "pos"
    client_widgets =  ('client',)
    product_widgets = ('product',)
    sellable_widgets = ('price',
                        'quantity')
    widgets = (('order_list',
                'list_vbox',
                'add_button',
                'advanced_search',
                'anonymous_check',
                'client_check',
                'client_edit_button',
                'client_details_button',
                'delivery_button',
                'checkout_button',
                'remove_item_button',
                'search_box',
                'SalesMenu') + client_widgets + product_widgets +
                               sellable_widgets)
    
    def __init__(self, app):
        AppWindow.__init__(self, app)
        self.conn = new_transaction()
        if not get_current_till_operation(self.conn):
            notify_dialog(_("You need to open the till before start doing "
                            "sales."), _("Error"))
            self.app.shutdown()
        self.max_results = get_max_search_results()
        self.client_table = Person.getAdapterClass(IClient)
        self._setup_widgets()
        self._setup_proxies()
        self.reset_order()
        self._update_widgets()
        self._update_client_widgets()

    def _delete_sellable_item(self, item):
        self.order_list.remove(item)
        table = type(item)
        table.delete(item.id, connection=self.conn)

    def _setup_proxies(self):
        self.client_proxy = self.add_proxy(widgets=POSApp.client_widgets)
        self.sellable_proxy = self.add_proxy(FancySellable(),
                                             widgets=POSApp.sellable_widgets)
        self.product_proxy = self.add_proxy(FancyProduct(),
                                            POSApp.product_widgets)

    def _setup_client_entry(self):
        # TODO Waiting for improvements in kiwi entry completion. We need a
        # better way to query strings immediately when typing in the
        # entry
        # q1 = self.client_table.q._originalID == Person.q.id
        # search_str = '%%%s%%' % self.client.get_text().upper()
        # q2 = LIKE(func.UPPER(Person.q.name), search_str)
        # query = AND(q1, q2)
        # clients = self.client_table.get_active_clients(self.conn, query)
        clients = self.client_table.get_active_clients(self.conn)
        clients = clients[:self.max_results]
        strings = [c.get_adapted().name for c in clients]
        self.client.set_completion_strings(strings, list(clients))

    def _setup_entry_completion(self):
        # TODO Waiting for improvements in kiwi entry completion. We need a
        # better way to query strings immediately when typing in the
        # entry
        self._setup_client_entry()
        sellables = AbstractSellable.get_available_sellables(self.conn)
        sellables = sellables[:self.max_results]
        strings = [s.get_short_description() for s in sellables]
        self.product.set_completion_strings(strings, list(sellables))

    def _setup_widgets(self):
        if not sysparam(self.conn).EDIT_SELLABLE_PRICE:
            self.price.set_sensitive(False)
        self.price.set_data_format(get_price_format_str())
        self.order_list.set_columns(self._get_columns())
        value_format = '<b>%s</b>' % get_price_format_str()
        self.summary_label = SummaryLabel(klist=self.order_list,
                                          column='total',
                                          label='<b>Total:</b>',
                                          value_format=value_format)
        self.summary_label.show()
        self.list_vbox.pack_start(self.summary_label, False)
        self.product.grab_focus()
        if not sysparam(self.conn).HAS_DELIVERY_MODE:
            self.delivery_button.hide()
        self._setup_entry_completion()

    def _update_totals(self, *args):
        self.summary_label.update_total()

    def _get_sellable_by_code(self, code):
        sellable = AbstractSellable.selectBy(code=code,
                                             connection=self.conn)
        qty = sellable.count()
        if not qty:
            msg = _("The item '%s' doesn't exists" % code)
            self.product.set_invalid(msg)
            return
        if qty != 1:
            raise DatabaseInconsistency('You should have only one '
                                        'sellable with code %s' 
                                        % code)
        return sellable[0]

    def _update_order_list(self, sellable, notify_on_entry=False):
        table = type(sellable)
        if not ISellable.implementedBy(table):
            raise TypeError("The object must implement a sellable facet.")
        sellables = [s.sellable for s in self.order_list]
        if sellable in sellables:
            if notify_on_entry:
                msg = _("The item '%s' was already added to the order" 
                        % sellable.base_sellable_info.description)
                self.product.set_invalid(msg)
            return
        else:
            sellable = table.get(sellable.id, connection=self.conn)
            quantity = self.sellable_proxy.model.quantity
            price = self.sellable_proxy.model.price
            sellable_item = sellable.add_sellable_item(self.sale,
                                                       quantity=quantity, 
                                                       price=price)
        if isinstance(sellable_item, ServiceSellableItem):
            model = self.run_dialog(ServiceItemEditor, self.conn, sellable_item)
            if not model:
                return
        self.order_list.append(sellable_item)
        self.order_list.select(sellable_item)
        self.product.set_text('')

    def _get_sellable(self):
        if self.product_proxy.model:
            sellable = self.product_proxy.model.product
        else:
            sellable = None
        if not sellable:
            code = self.product.get_text()
            sellable = self._get_sellable_by_code(code)
            if sellable:
                # Waiting for a select method on kiwi entry using entry
                # completions
                self.product.set_text(sellable.get_short_description())
        self.add_button.set_sensitive(sellable is not None)
        return sellable

    def add_sellable_item(self):
        if not self.add_button.get_property('sensitive'):
            return
        self.add_button.set_sensitive(False)
        sellable = self._get_sellable()
        if not sellable:
            return
        self._update_order_list(sellable, notify_on_entry=True)
        self.product.grab_focus()

    def select_first_item(self):
        if len(self.order_list):
            # XXX Probably kiwi should handle this for us. Waiting for
            # support
            self.order_list.select(self.order_list[0])

    def reset_order(self):
        self.order_list.clear()
        rollback_and_begin(self.conn)
        user = get_current_user()
        till = get_current_till_operation(self.conn)
        salesperson = ISalesPerson(user.get_adapted(), connection=self.conn)
        self.sale = Sale(connection=self.conn, till=till, 
                         salesperson=salesperson)
        self.client_proxy.new_model(self.sale)
        self._update_widgets()
        self._update_totals()

    def _update_client_widgets(self):
        client_selected = self.client_check.get_active()
        self.client.set_sensitive(client_selected)

    def _update_widgets(self):
        has_sellables = len(self.order_list[:]) >= 1
        widgets = [self.checkout_button, self.remove_item_button]
        for widget in widgets:
            widget.set_sensitive(has_sellables)
        has_client = self.sale.client is not None
        widgets = [self.client_details_button, self.delivery_button]
        for widget in widgets:
            widget.set_sensitive(has_client)
        model = self.order_list.get_selected()
        self._update_totals()
        has_sellable_str = self.product.get_text() != ''
        self.add_button.set_sensitive(has_sellable_str)

    def _get_columns(self):
        return [Column('sellable.code', title=_('Code'), sorted=True, 
                       data_type=str, width=90),
                Column('sellable.base_sellable_info.description', 
                       title=_('Description'), data_type=str, expand=True, 
                       searchable=True),
                Column('price', title=_('Price'), data_type=currency, 
                       width=90),
                Column('quantity', title=_('Quantity'), data_type=float,
                       width=90, format_func=format_quantity),
                Column('total', title=_('Total'), data_type=currency,
                       width=100)]
                       
    def _search_clients(self):
        self.run_dialog(ClientSearch, hide_footer=True)

    #
    # AppWindow Hooks
    #

    def setup_focus(self): 
        self.search_box.set_focus_chain([self.product, self.quantity, 
                                         self.price, self.add_button])

    #
    # Callbacks
    #

    def key_control_r(self, *args):
        # FIXME Waiting for a bugfix in gazpacho. Accelerators doesn't work
        # for menuitems
        self.reset_order()

    def key_control_l(self, *args):
        # FIXME Waiting for a bugfix in gazpacho. Accelerators doesn't work
        # for menuitems
        # Implement a search dialog for sales
        pass
        
    def key_control_p(self, *args):
        # FIXME Waiting for a bugfix in gazpacho. Accelerators doesn't work
        # for menuitems
        self._search_clients()

    def on_product__changed(self, *args):
        self.product.set_valid()

    def on_advanced_search__clicked(self, *args):
        items = self.run_dialog(SellableSearch, self.conn)
        for item in items:
            self._update_order_list(item)
        self.select_first_item()
        self._update_totals()

    def on_add_button__clicked(self, *args):
        self.add_sellable_item()

    def on_product__activate(self, *args):
        self._get_sellable()
        self.quantity.grab_focus()

    def on_quantity__activate(self, *args):
        self.add_sellable_item()

    def on_price__activate(self, *args):
        self.add_sellable_item()

    def on_order_list__selection_changed(self, *args):
        self._update_widgets()

    def on_client_edit_button__clicked(self, *args):
        if run_person_role_dialog(ClientEditor, self, self.conn, 
                                  self.sale.client):
            self.conn.commit()
            # FIXME waiting for entry completion bug fix in kiwi. This part
            # doesn't work properly when editing a client previously set in
            # POS interface
            self._setup_client_entry()
            
    def _on_clients_action__clicked(self, *args):
        self._search_clients()

    def after_client__changed(self, *args):
        # FIXME A bug in kiwi or gtk doesn't allow us to call this 
        # method rigth here.
        # self._setup_client_entry()
        self._update_widgets()

    def after_product__changed(self, *args):
        self._update_widgets()
        sellable = self.product_proxy.model.product
        if not (sellable and self.product.get_text()):
            self.sellable_proxy.new_model(FancySellable())
            return
        sellable_item = FancySellable(price=sellable.get_price())
        self.sellable_proxy.new_model(sellable_item)

    def on_remove_item_button__clicked(self, *args):
        item = self.order_list.get_selected()
        self._delete_sellable_item(item)
        self.select_first_item()
        self._update_widgets()

    def _on_resetorder_action__clicked(self, *args):
        self.reset_order()

    def _on_sales_action__clicked(self, *args):
        pass
                      
    def on_delivery_button__clicked(self, *args):
        if not self.order_list:
            notify_dialog(_("You don't have products to delivery."),
                          _("Error"))
            return
        products = [obj for obj in self.order_list
                        if isinstance(obj, ProductSellableItem)
                           and obj.delivery_data is None]
        if not products:
            notify_dialog(_("All the products already have delivery "
                            "instructions"), _("Error"))
            return
        service = self.run_dialog(DeliveryEditor, self.conn, None, 
                                  self.sale, products)
        if not service:
            return
        if service in self.order_list:
            self.order_list.update(service)
        else:
            self.order_list.append(service)
        self.order_list.select(service)

    def _sale_checkout(self, *args):
        param = sysparam(self.conn)
        skip_payment_step = (param.CONFIRM_SALES_ON_TILL and
                             param.SET_PAYMENT_METHODS_ON_TILL)
        if self.run_dialog(SaleWizard, self.conn, self.sale,
                           skip_payment_step=skip_payment_step):
            self.conn.commit()
            self.reset_order()

    def on_checkout_button__clicked(self, *args):
        self._sale_checkout()

    def on_client_check__toggled(self, *args):
        self._update_client_widgets()
        self._update_widgets()

    def on_anonymous_check__toggled(self, *args):
        self._update_client_widgets()
        self.client.model = None
        self.client.set_text('')
        self._update_widgets()
