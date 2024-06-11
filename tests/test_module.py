# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.pool import Pool
from decimal import Decimal


class AccountImportContaplusTestCase(ModuleTestCase):
    'Test Account Import Contaplus module'
    module = 'account_import_contaplus'

    @with_transaction()
    def test_account_es(self):
        'Test taxes from account_es'
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        TaxTemplate = pool.get('account.tax.template')

        t_vat_21 = TaxTemplate(ModelData.get_id('account_es', 'iva_rep_21'))
        t_vat_0 = TaxTemplate(ModelData.get_id('account_es', 'iva_rep_ex'))
        self.assertEqual(t_vat_21.rate * 100, Decimal('21.00'))
        self.assertEqual(t_vat_0.rate * 100, Decimal(0))


del ModuleTestCase
