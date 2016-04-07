# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .account import *


def register():
    Pool.register(
        AccountImportContaplusStart,
        ImportRecord,
        Move,
        module='account_import_contaplus', type_='model')
    Pool.register(
        AccountImportContaplus,
        module='account_import_contaplus', type_='wizard')
