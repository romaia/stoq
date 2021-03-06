# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005-2012 Async Open Source <http://www.async.com.br>
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
## Author(s): Stoq Team <stoq-devel@async.com.br>
##
##
""" Sale wizard definition """

import gtk
from kiwi.component import get_utility
from kiwi.currency import currency
from kiwi.datatypes import ValidationError
from kiwi.python import Settable
from storm.expr import And

from stoqlib.api import api
from stoqlib.database.exceptions import IntegrityError
from stoqlib.domain.costcenter import CostCenter
from stoqlib.domain.events import CreatePaymentEvent
from stoqlib.domain.fiscal import CfopData
from stoqlib.domain.payment.card import CreditProvider
from stoqlib.domain.payment.method import PaymentMethod
from stoqlib.domain.payment.payment import Payment
from stoqlib.domain.person import Client, SalesPerson, Transporter
from stoqlib.domain.sale import Sale
from stoqlib.enums import CreatePaymentStatus
from stoqlib.exceptions import SellError, StoqlibError
from stoqlib.lib.message import warning, yesno, marker
from stoqlib.lib.parameters import sysparam
from stoqlib.lib.pluginmanager import get_plugin_manager
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.gui.base.wizards import WizardEditorStep, BaseWizard, BaseWizardStep
from stoqlib.gui.base.dialogs import run_dialog
from stoqlib.gui.dialogs.clientdetails import ClientDetailsDialog
from stoqlib.gui.editors.fiscaleditor import CfopEditor
from stoqlib.gui.editors.noteeditor import NoteEditor
from stoqlib.gui.editors.personeditor import ClientEditor, TransporterEditor
from stoqlib.gui.interfaces import IDomainSlaveMapper
from stoqlib.gui.printing import print_report
from stoqlib.gui.slaves.cashchangeslave import CashChangeSlave
from stoqlib.gui.slaves.paymentmethodslave import SelectPaymentMethodSlave
from stoqlib.gui.slaves.paymentslave import (register_payment_slaves,
                                             MultipleMethodSlave)
from stoqlib.gui.slaves.saleslave import SaleDiscountSlave
from stoqlib.gui.wizards.personwizard import run_person_role_dialog
from stoqlib.reporting.boleto import BillReport
from stoqlib.reporting.booklet import BookletReport

N_ = _ = stoqlib_gettext


#
# Wizard Steps
#

class PaymentMethodStep(BaseWizardStep):
    gladefile = 'HolderTemplate'
    slave_holder = 'place_holder'

    def __init__(self, wizard, previous, store, model, method,
                 outstanding_value=None, finish_on_total=True):
        """
        :param wizard: the wizard this step is in
        :param previous: the previous step if there is any
        :param store: the store this step is executed
        :param model: the model of this step
        :param method: the payment method
        :param finish_on_total: if it is ``True`` automatically closes
           the wizard when payments total is equals to the total cost
           of the operation. When it is ``False``, waits for the user to
           click the finish button
        :param outstanding_value: if this value is not ``None``, it will
            be used as the total value of the payment
        """
        self._method_name = method
        self._method_slave = None
        self.model = model

        if outstanding_value is None:
            outstanding_value = currency(0)
        self._outstanding_value = outstanding_value
        self._finish_on_total = finish_on_total

        BaseWizardStep.__init__(self, store, wizard, previous)

        register_payment_slaves()
        self._create_ui()

    def _create_ui(self):
        slave = self._create_slave(self._method_name)
        self._attach_slave(slave)

    def _create_slave(self, method):
        dsm = get_utility(IDomainSlaveMapper)
        slave_class = dsm.get_slave_class(method)
        assert slave_class
        method = self.store.fetch(method)
        if slave_class is MultipleMethodSlave:
            slave = slave_class(self.wizard, self, self.store, self.model,
                                method, outstanding_value=self._outstanding_value,
                                finish_on_total=self._finish_on_total)
        else:
            slave = slave_class(self.wizard, self, self.store, self.model,
                                method, outstanding_value=self._outstanding_value)
        self._method_slave = slave
        return slave

    def _attach_slave(self, slave):
        if self.get_slave(self.slave_holder):
            self.detach_slave(self.slave_holder)
        self.attach_slave(self.slave_holder, slave)

    #
    # WizardStep hooks
    #

    def validate_step(self):
        return self._method_slave.finish()

    def has_next_step(self):
        return False

    def post_init(self):
        self._method_slave.update_view()


class BaseMethodSelectionStep(object):
    """Base class for method selection when doing client sales

    Classes using this base class should have a select_method_holder EventBox
    and a cash_change_holder EventBox in the glade file
    """

    #
    #   Private API
    #

    def _update_next_step(self, method):
        if method and method.method_name == u'money':
            self.wizard.enable_finish()
            if self.wizard.need_create_payment():
                self.cash_change_slave.enable_cash_change()
            else:
                self.cash_change_slave.disable_cash_change()
        else:
            self.wizard.disable_finish()
            self.cash_change_slave.disable_cash_change()

    #
    #   Public API
    #

    def get_selected_method(self):
        return self.pm_slave.get_selected_method()

    def setup_cash_payment(self, total=None):
        money_method = PaymentMethod.get_by_name(self.store, u'money')
        total = total or self.wizard.get_total_to_pay()
        return money_method.create_inpayment(self.model.group,
                                             self.model.branch, total)

    #
    # WizardStep hooks
    #

    def post_init(self):
        if not self.wizard.need_create_payment():
            for widget in [self.select_method_holder,
                           self.subtotal_expander]:
                widget.hide()

        self._update_next_step(self.pm_slave.get_selected_method())

    def setup_slaves(self):
        marker('SelectPaymentMethodSlave')
        self.pm_slave = SelectPaymentMethodSlave(store=self.store,
                                                 payment_type=Payment.TYPE_IN)
        self.pm_slave.connect('method-changed', self.on_payment_method_changed)
        self.attach_slave('select_method_holder', self.pm_slave)

        marker('CashChangeSlave')
        self.cash_change_slave = CashChangeSlave(self.store, self.model, self.wizard)
        self.attach_slave('cash_change_holder', self.cash_change_slave)
        self.cash_change_slave.received_value.connect(
            'activate', lambda entry: self.wizard.go_to_next())

    def next_step(self):
        if not self.wizard.need_create_payment():
            return

        selected_method = self.get_selected_method()
        if selected_method.method_name == u'money':
            if not self.cash_change_slave.can_finish():
                warning(_(u"Invalid value, please verify if it was "
                          "properly typed."))
                self.cash_change_slave.received_value.select_region(
                    0, len(self.cash_change_slave.received_value.get_text()))
                self.cash_change_slave.received_value.grab_focus()
                return self

            # We have to modify the payment, so the fiscal printer can
            # calculate and print the payback, if necessary.
            payment = self.setup_cash_payment()
            total = self.cash_change_slave.get_received_value()
            payment.base_value = total

            # Return None here means call wizard.finish, which is exactly
            # what we need
            return None
        elif selected_method.method_name == u'store_credit':
            client = self.model.client
            total = self.wizard.get_total_amount()

            assert client.can_purchase(selected_method, total)

            step_class = PaymentMethodStep
        elif selected_method.method_name == 'card':
            providers = CreditProvider.get_card_providers(self.store)
            if providers.is_empty():
                warning(_("You need active credit providers to use the "
                          "card payment method."))
                return self
            step_class = PaymentMethodStep
        else:
            step_class = PaymentMethodStep

        retval = CreatePaymentEvent.emit(selected_method, self.model,
                                         self.store)

        # None means no one catched this event
        if retval is None or retval == CreatePaymentStatus.UNHANDLED:
            # FIXME: We cannot send outstanding_value to multiple editor
            # since if we have a trade going on, it will be calculated wrong
            if selected_method.method_name == 'multiple':
                outstanding_value = None
            else:
                outstanding_value = self.wizard.get_total_to_pay()

            return step_class(self.wizard, self, self.store, self.model,
                              selected_method,
                              outstanding_value=outstanding_value)

        # finish the wizard
        if retval == CreatePaymentStatus.SUCCESS:
            return None

        # returning self to stay on this step
        return self

    #
    #   Callbacks
    #

    def on_payment_method_changed(self, slave, method_name):
        self._update_next_step(method_name)


class SalesPersonStep(BaseMethodSelectionStep, WizardEditorStep):
    """ An abstract step which allows to define a salesperson, the sale's
    discount and surcharge, when it is needed.
    """
    gladefile = 'SalesPersonStep'
    model_type = Sale
    proxy_widgets = ('salesperson',
                     'client',
                     'transporter',
                     'cost_center')

    invoice_widgets = ('invoice_number', )
    cfop_widgets = ('cfop', )

    def __init__(self, wizard, store, model, payment_group,
                 invoice_model):
        self.invoice_model = invoice_model

        self.payment_group = payment_group

        BaseMethodSelectionStep.__init__(self)
        marker("WizardEditorStep.__init__")
        WizardEditorStep.__init__(self, store, wizard, model)

        self._update_totals()
        self.update_discount_and_surcharge()

    #
    # Private API
    #

    def _update_totals(self):
        subtotal = self.wizard.get_subtotal()
        self.subtotal_lbl.update(subtotal)

        total_paid = self.wizard.get_total_paid()
        self.total_paid_lbl.update(total_paid)

        to_pay = self.model.get_total_sale_amount(subtotal=subtotal) - total_paid
        self.cash_change_slave.update_total_sale_amount(to_pay)
        self.total_lbl.update(to_pay)

    def _update_widgets(self):
        has_client = bool(self.client.get_selected())
        self.pm_slave.method_set_sensitive(u'store_credit', has_client)
        self.pm_slave.method_set_sensitive(u'bill', has_client)

    def _fill_clients_combo(self):
        marker('Filling clients')
        # FIXME: This should not be using a normal ProxyComboEntry,
        #        we need a specialized widget that does the searching
        #        on demand.

        clients = Client.get_active_clients(self.store)
        self.client.prefill(api.for_person_combo(clients))
        self.client.set_sensitive(len(self.client.get_model()))
        marker('Filled clients')

    def _fill_transporter_combo(self):
        marker('Filling transporters')
        transporters = Transporter.get_active_transporters(self.store)
        items = api.for_person_combo(transporters)
        self.transporter.prefill(items)
        self.transporter.set_sensitive(len(items))
        marker('Filled transporters')

    def _fill_cost_center_combo(self):
        marker('Filling cost centers')
        cost_centers = CostCenter.get_active(self.store)

        # we keep this value because each call to is_empty() is a new sql query
        # to the database
        cost_centers_exists = not cost_centers.is_empty()

        if cost_centers_exists:
            self.cost_center.prefill(api.for_combo(cost_centers, attr='name',
                                                   empty=_('No cost center.')))
        self.cost_center.set_visible(cost_centers_exists)
        self.cost_center_lbl.set_visible(cost_centers_exists)
        marker('Filled cost centers')

    def _fill_cfop_combo(self):
        marker('Filling CFOPs')
        cfops = self.store.find(CfopData)
        self.cfop.prefill(api.for_combo(cfops))
        marker('Filled CFOPs')

    def _create_client(self):
        store = api.new_store()
        client = run_person_role_dialog(ClientEditor, self.wizard, store, None)
        store.confirm(client)
        client = self.store.fetch(client)
        store.close()
        if not client:
            return
        if len(self.client) == 0:
            self._fill_clients_combo()
            return
        clients = self.client.get_model_items().values()
        if client in clients:
            if client.is_active:
                self.client.select(client)
            else:
                # remove client from combo
                self.client.select_item_by_data(client)
                iter = self.client.get_active_iter()
                model = self.client.get_model()
                model.remove(iter)
                # just in case the inactive client was selected before.
                self.client.select_item_by_position(0)
        elif client.is_active:
            self.client.append_item(client.person.name, client)
            self.client.select(client)
        self._update_widgets()

    #
    # Public API
    #

    def update_discount_and_surcharge(self):
        marker("update_discount_and_surcharge")
        # Here we need avoid to reset sale data defined when creating the
        # Sale in the POS application, i.e, we should not reset the
        # discount and surcharge if they are already set (this is the
        # case when CONFIRM_SALES_ON_TILL parameter is enabled).
        if not sysparam(self.store).CONFIRM_SALES_ON_TILL:
            self.model.discount_value = currency(0)
            self.model.surcharge_value = currency(0)

    def setup_widgets(self):
        marker('Setting up widgets')
        # Only quotes have expire date.
        self.expire_date.hide()
        self.expire_label.hide()

        # Hide operation nature widgets
        self.operation_nature.hide()
        self.nature_lbl.hide()

        # Hide client category widgets
        self.client_category_lbl.hide()
        self.client_category.hide()

        # if the NF-e plugin is active, the client is mandantory in this
        # wizard (in this situation, we have only quote sales).
        if self.model.status == Sale.STATUS_QUOTE:
            manager = get_plugin_manager()
            mandatory_client = manager.is_active('nfe')
            self.client.set_property('mandatory', mandatory_client)

        marker('Filling sales persons')
        salespersons = self.store.find(SalesPerson)
        self.salesperson.prefill(api.for_person_combo(salespersons))
        marker('Finished filling sales persons')

        marker('Read parameter')
        if not sysparam(self.store).ACCEPT_CHANGE_SALESPERSON:
            self.salesperson.set_sensitive(False)
        else:
            self.salesperson.grab_focus()
        marker('Finished reading parameter')
        self._fill_clients_combo()
        self._fill_transporter_combo()
        self._fill_cost_center_combo()

        if sysparam(self.store).ASK_SALES_CFOP:
            self._fill_cfop_combo()
        else:
            self.cfop_lbl.hide()
            self.cfop.hide()
            self.create_cfop.hide()

        # the maximum number allowed for an invoice is 999999999.
        self.invoice_number.set_adjustment(
            gtk.Adjustment(lower=1, upper=999999999, step_incr=1))

        if not self.model.invoice_number:
            new_invoice_number = Sale.get_last_invoice_number(self.store) + 1
            self.invoice_model.invoice_number = new_invoice_number
        else:
            new_invoice_number = self.model.invoice_number
            self.invoice_model.invoice_number = new_invoice_number
            self.invoice_number.set_sensitive(False)

        self.invoice_model.original_invoice = new_invoice_number
        marker('Finished setting up widgets')

    def _refresh_next(self, validation_value):
        self.client.validate(force=True)
        client_valid = self.client.is_valid()
        self.wizard.refresh_next(validation_value and client_valid)

    #
    # WizardStep hooks
    #

    def post_init(self):
        BaseMethodSelectionStep.post_init(self)

        marker('Entering post_init')
        self.toogle_client_details()
        if self.wizard.need_create_payment():
            self.wizard.payment_group.clear_unused()
        self.register_validate_function(self._refresh_next)
        self._update_next_step(self.get_selected_method())
        if hasattr(self, 'cash_change_slave'):
            self.cash_change_slave.received_value.grab_focus()

        self.force_validation()
        marker('Leaving post_init')

    def setup_slaves(self):
        marker('Setting up slaves')
        BaseMethodSelectionStep.setup_slaves(self)
        marker('Finished parent')

        self.pm_slave.method_set_sensitive(u'store_credit',
                                           bool(self.model.client))
        self.pm_slave.method_set_sensitive(u'bill',
                                           bool(self.model.client))

        marker('Setting discount')
        self.discount_slave = SaleDiscountSlave(self.store, self.model,
                                                self.model_type)
        marker('Finshed setting up discount')

        self.discount_slave.connect('discount-changed',
                                    self.on_discount_slave_changed)
        slave_holder = 'discount_surcharge_slave'
        if self.get_slave(slave_holder):
            self.detach_slave(slave_holder)
        self.attach_slave(slave_holder, self.discount_slave)
        marker('Finished setting up slaves')

    def setup_proxies(self):
        marker('Setting up proxies')
        self.setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    SalesPersonStep.proxy_widgets)
        self.invoice_proxy = self.add_proxy(self.invoice_model,
                                            self.invoice_widgets)
        if self.model.client:
            self.client.set_sensitive(False)
            self.create_client.set_sensitive(False)
        if sysparam(self.store).ASK_SALES_CFOP:
            self.add_proxy(self.model, SalesPersonStep.cfop_widgets)
        marker('Finished setting up proxies')

    def toogle_client_details(self):
        client = self.client.read()
        self.client_details.set_sensitive(bool(client))

    #
    # Callbacks
    #

    def on_client__changed(self, entry):
        self.toogle_client_details()
        self._update_widgets()
        self.discount_slave.update_max_discount()

    def on_payment_method_changed(self, slave, method_name):
        self.client.validate(force=True)
        self._update_next_step(method_name)

    def on_client__validate(self, widget, client):
        if not client:
            return

        # this is used to avoid some tests from crashing
        if not hasattr(self, 'pm_slave'):
            return

        method = self.pm_slave.get_selected_method()
        try:
            client.can_purchase(method, self.model.get_total_sale_amount())
            self.wizard.refresh_next(True)
        except SellError as e:
            self.wizard.refresh_next(False)
            return ValidationError(e)

    def on_create_client__clicked(self, button):
        self._create_client()

    def on_create_transporter__clicked(self, button):
        store = api.new_store()
        transporter = store.fetch(self.model.transporter)
        model = run_person_role_dialog(TransporterEditor, self.wizard, store,
                                       transporter)
        rv = store.confirm(model)
        store.close()
        if rv:
            self._fill_transporter_combo()
            model = self.store.fetch(model)
            self.transporter.select(model)

    def on_discount_slave_changed(self, slave):
        self._update_totals()
        self.client.validate()

    def on_notes_button__clicked(self, *args):
        run_dialog(NoteEditor, self.wizard, self.store, self.model, 'notes',
                   title=_("Additional Information"))

    def on_create_cfop__clicked(self, widget):
        self.store.savepoint('before_run_editor_cfop')
        cfop = run_dialog(CfopEditor, self.wizard, self.store, None)
        if cfop:
            self.cfop.append_item(cfop.get_description(), cfop)
            self.cfop.select_item_by_data(cfop)
        else:
            self.store.rollback_to_savepoint('before_run_editor_cfop')

    def on_invoice_number__validate(self, widget, value):
        if not 0 < value <= 999999999:
            return ValidationError(
                _("Invoice number must be between 1 and 999999999"))

        exists = self.store.find(
            Sale, And(Sale.invoice_number == value,
                      Sale.id != self.model.id))
        if not exists.is_empty():
            return ValidationError(_(u'Invoice number already used.'))

    def on_client_details__clicked(self, button):
        client = self.model.client
        run_dialog(ClientDetailsDialog, self.wizard, self.store, client)


#
# Wizards for sales
#

class ConfirmSaleWizard(BaseWizard):
    """A wizard used when confirming a sale order. It means generate
    payments, fiscal data and update stock
    """
    size = (600, 400)
    first_step = SalesPersonStep
    title = _("Sale Checkout")
    help_section = 'sale-confirm'

    # FIXME: In the long term, we should only create the sale at the end
    #        of this process, but that requires major surgery of the
    #        interaction between salewizard.py, pos.py and fiscalprinter.py
    def __init__(self, store, model,
                 subtotal,
                 total_paid=0):
        """Creates a new SaleWizard that confirms a sale.
        To avoid excessive querying of the database we pass
        some data already queried/calculated before hand.

        :param store: a store
        :param model: a |sale|
        :param subtotal: subtotal of the sale
        :param total_paid: totaly value already paid
        """
        marker('ConfirmSaleWizard')
        self._check_payment_group(model, store)

        self._subtotal = subtotal
        self._total_paid = total_paid
        self.model = model

        # invoice_model is a Settable so avoid bug 4218, where more
        # than one checkout may try to use the same invoice number.
        self.invoice_model = Settable(invoice_number=None,
                                     original_invoice=None)
        marker('running SalesPersonStep')
        first_step = self.first_step(self, store, model, self.payment_group,
                                     self.invoice_model)
        marker('finished creating SalesPersonStep')
        BaseWizard.__init__(self, store, first_step, model)

        if not sysparam(self.store).CONFIRM_SALES_ON_TILL:
            # This was added to allow us to work even if an error
            # happened while adding a payment, where we already order
            # but cannot confirm and are thrown back to the main
            # POS interface
            if self.model.can_order():
                self.model.order()

        marker('leaving ConfirmSaleWizard.__init__')

    def _check_payment_group(self, model, store):
        if not isinstance(model, Sale):
            raise StoqlibError("Invalid datatype for model, it should be "
                               "of type Sale, got %s instead" % model)
        self.payment_group = model.group

    def _invoice_changed(self):
        return (self.invoice_model.invoice_number !=
                self.invoice_model.original_invoice)

    def get_subtotal(self):
        """Fetch the sale subtotal without querying the database.
        The subtotal is the value of all items that are being sold

        :returns: the subtotal of the current sale
        """
        return self._subtotal

    def get_total_amount(self):
        """Fetch the total sale amount without querying the database.
        The total sale amount is the subtotal with discount and markups
        taken into account.

        :returns: the total amount of the current sale
        """
        return self.model.get_total_sale_amount(subtotal=self._subtotal)

    def get_total_paid(self):
        """Fetch the value already paid for this sale.
        This is only used when we return a project we already paid for.

        :returns: the total paid value for the current sale
        """
        return self._total_paid

    def get_total_to_pay(self):
        """Fetch the value the client still needs to pay.

        This is a short hand for self.get_total_amount() - self.get_total_paid()
        """
        return self.get_total_amount() - self.get_total_paid()

    def need_create_payment(self):
        return self.get_total_amount() > 0

    def finish(self):
        self.retval = True
        invoice_number = self.invoice_model.invoice_number

        # Workaround for bug 4218: If the invoice is was already used by
        # another store (another cashier), try using the next one
        # available, or show a warning if the number was manually set.
        while True:
            try:
                self.store.savepoint('before_set_invoice_number')
                self.model.invoice_number = invoice_number
                # We need to flush the database here, or a possible collision
                # of invoice_number will only be detected later on, when the
                # execution flow is not in the try-except anymore.
                self.store.flush()
            except IntegrityError:
                self.store.rollback_to_savepoint('before_set_invoice_number')
                if self._invoice_changed():
                    warning(_(u"The invoice number %s is already used. "
                              "Confirm the sale again to chose another one.") %
                            invoice_number)
                    self.retval = False
                    break
                else:
                    invoice_number += 1
            else:
                break

        self.close()

        group = self.model.group
        # FIXME: This is set too late on Sale.confirm(). If PaymentGroup don't
        #        have a payer, we won't be able to print bills/booklets.
        group.payer = self.model.client and self.model.client.person

        booklets = list(group.get_payments_by_method_name(u'store_credit'))
        bills = list(group.get_payments_by_method_name(u'bill'))

        if (booklets and
            yesno(_("Do you want to print the booklets for this sale?"),
                  gtk.RESPONSE_YES, _("Print booklets"), _("Don't print"))):
            print_report(BookletReport, booklets)

        if (bills and BillReport.check_printable(bills) and
            yesno(_("Do you want to print the bills for this sale?"),
                  gtk.RESPONSE_YES, _("Print bills"), _("Don't print"))):
            print_report(BillReport, bills)


def test():  # pragma nocover
    creator = api.prepare_test()
    sale_item = creator.create_sale_item()
    retval = run_dialog(ConfirmSaleWizard, None, creator.store,
                        sale_item.sale)
    creator.store.confirm(retval)


if __name__ == '__main__':  # pragma nocover
    test()
