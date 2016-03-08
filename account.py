from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button

__all__ = ['AccountImportContaplus', 'AccountImportContaplusStart']


class AccountImportContaplusStart(ModelView):
    'Account Import Contaplus Start'
    __name__ = 'account.import.contaplus.start'
    data = fields.Binary('File', required=True)


class AccountImportContaplus(Wizard):
    'Account Import Contaplus'
    __name__ = 'account.import.contaplus'
    start = StateView("account.import.contaplus.start",
                      'account_import_contaplus.account_import_contaplus_start_view_form',[
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Import', 'import_', 'tryton-ok', default=True)
                      ])
    import_ = StateTransition()

    def transition_import_(self):
        data_file = self.start.data
        pool = Pool()
        Account = pool.get('account.account')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')
        for line in lines:
            move = Move()
            move.date =
            move.period =
            line = Line()
            accounts = Account.search(['code', '=', line.cuenta], limit=1)
            if not accounts:
                self.raise_user_error()
            line.account = accounts[0]
            line.debit
            line.credit
            line.party
            move.lines.append()
        print('click ok')
        return 'end'
