# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account


def register():
    Pool.register(
        account.AccountImportContaplusStart,
        account.ImportRecord,
        account.Move,
        account.Invoice,
        module='account_import_contaplus', type_='model')
    Pool.register(
        account.AccountImportContaplus,
        module='account_import_contaplus', type_='wizard')
