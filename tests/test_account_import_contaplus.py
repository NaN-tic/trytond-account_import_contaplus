# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase
from trytond.pool import Pool


class AccountImportContaplusTestCase(ModuleTestCase):
    'Test Account Import Contaplus module'
    module = 'account_import_contaplus'


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        AccountImportContaplusTestCase))
    return suite
